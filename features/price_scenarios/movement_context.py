"""Exact immutable price references for an explicitly requested hypothesis conversation."""
from datetime import date
import json
import re
import sqlite3

from .service import movement_view
from .store import PriceStoreError


def normalize_movement(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    fields = {k: value.get(k) for k in ("instrumentId", "snapshotId", "startDate", "endDate")}
    if not isinstance(fields["instrumentId"], str) or not re.fullmatch(r"(?:US:[A-Z0-9.\-]{1,10}|KR:[0-9][A-Z0-9]{5})", fields["instrumentId"]):
        return None
    if fields["snapshotId"] is not None and (not isinstance(fields["snapshotId"], str) or len(fields["snapshotId"]) > 160):
        return None
    try:
        if any(not isinstance(fields[k], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fields[k]) for k in ("startDate", "endDate")):
            return None
        if date.fromisoformat(fields["startDate"]) >= date.fromisoformat(fields["endDate"]):
            return None
    except ValueError:
        return None
    return fields


def render_movement_context(root, value) -> str:
    fields = normalize_movement(value)
    if fields is None:
        return ""
    # An absent ID must stay absent rather than attach a newer snapshot later.
    if not fields["snapshotId"]:
        facts = {"status": "not_applicable", "reason": {"code": "comparison_inputs_missing"}}
    else:
        try:
            facts = movement_view(root, fields["instrumentId"], fields["startDate"], fields["endDate"], fields["snapshotId"])
        except (ValueError, OSError, sqlite3.Error, PriceStoreError):
            facts = {"status": "unavailable", "reason": {"code": "comparison_inputs_missing"}}
    return ("명시적으로 선택한 주가 움직임의 계산 사실(서버가 저장 입력에서 다시 계산):\n"
            + json.dumps({"selection": fields, "facts": facts}, ensure_ascii=False)
            + "\n배당 제외 가격 수익이며, 같은 날짜 가격지수와 비교합니다. PER 변화의 원인이나 투자 판정을 단정하지 마세요. "
              "가능한 설명은 가설로, 확인된 사실과 미확인 자료는 구분하세요. 대화는 hypothesis, reuseAsEvidence=false입니다.")
