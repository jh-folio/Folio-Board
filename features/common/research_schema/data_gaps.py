"""Common Data Gap schema."""
from __future__ import annotations

import hashlib
import re

from features.common.research_schema.enums import normalize_artifact_type, normalize_data_gap_severity


_SUGGESTED_ACTIONS = {
    "market_data": "시장 데이터 provider 상태를 확인하거나 research-inbox/market-data/에 수동 CSV를 보강하세요.",
    "evidence": "관련 RSS/article 자료를 추가한 뒤 인덱스를 갱신하세요.",
    "checkpoint": "보고서의 체크포인트 섹션을 명시적으로 작성하거나 재생성하세요.",
}


def _clean(value, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _stable_id(*parts: str) -> str:
    return "gap_" + hashlib.sha256("|".join(str(p or "") for p in parts).encode("utf-8")).hexdigest()[:12]


def normalize_data_gap(
    item,
    *,
    artifact_type: str,
    artifact_id: str = "",
    category: str = "evidence",
    severity: str = "medium",
    source_section: str = "",
    market: str = "",
) -> dict:
    src = item if isinstance(item, dict) else {"message": item}
    artifact_type = normalize_artifact_type(src.get("artifactType") or src.get("artifact_type") or artifact_type)
    artifact_id = str(src.get("artifactId") or src.get("artifact_id") or artifact_id or "")
    category = _clean(src.get("category") or category, 80) or "evidence"
    message = _clean(src.get("message") or src.get("gap") or src.get("text"))
    severity = normalize_data_gap_severity(src.get("severity") or severity)
    suggested = _clean(src.get("suggestedAction") or src.get("suggested_action") or _SUGGESTED_ACTIONS.get(category, _SUGGESTED_ACTIONS["evidence"]))
    source_section = _clean(src.get("sourceSection") or src.get("source_section") or source_section, 120)
    market = str(src.get("market") or market or "").strip().lower()
    if market not in {"", "us", "kr", "jp", "europe", "both", "all", "multi"}:
        market = ""
    gid = str(src.get("id") or "").strip() or _stable_id(artifact_type, artifact_id, category, market, message)
    return {
        "id": gid,
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "category": category,
        "message": message,
        "severity": severity,
        "suggestedAction": suggested,
        "sourceSection": source_section,
        "market": market,
    }


def data_gaps_from_messages(
    values,
    *,
    artifact_type: str,
    artifact_id: str = "",
    category: str = "evidence",
    severity: str = "medium",
    source_section: str = "",
    market: str = "",
    limit: int = 12,
) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    source_values = values if isinstance(values, list) else ([values] if values else [])
    for value in source_values:
        gap = normalize_data_gap(
            value,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            category=category,
            severity=severity,
            source_section=source_section,
            market=market,
        )
        if not gap["message"] or gap["message"].lower() in seen:
            continue
        seen.add(gap["message"].lower())
        rows.append(gap)
        if len(rows) >= limit:
            break
    return rows


def data_gap_applies_to(item: dict, market: str) -> bool:
    """Whether a structured gap belongs in a single-market projection."""
    if not isinstance(item, dict):
        return True
    item_market = str(item.get("market") or "").strip().lower()
    target = str(market or "").strip().lower()
    return not item_market or item_market in {target, "both", "all", "multi"}


def data_gap_rows(value) -> list[dict]:
    """Return gap dicts from either stored shape.

    기업분석은 {"gaps": [...], "summary": {...}}로, 나머지 산출물은 list로 저장한다.
    dict를 그대로 순회하면 키 문자열("gaps", "summary")이 나와 isinstance 필터에
    전부 걸러지므로, 읽는 쪽마다 기업분석의 gap이 조용히 사라진다.
    """
    if isinstance(value, dict):
        value = value.get("gaps")
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]
