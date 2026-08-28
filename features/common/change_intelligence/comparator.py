"""Rules-only comparator; never reads report Markdown."""
from __future__ import annotations

import datetime as dt

from features.common.change_intelligence.basis import content_hash
from features.common.change_intelligence.schema import validate_change_summary


def _unit_map(basis: dict | None) -> dict[str, dict]:
    return {str(row.get("id")): row for row in (basis or {}).get("changeUnits") or [] if isinstance(row, dict) and row.get("id")}


def _numeric(value, field: str | None):
    if field:
        if not isinstance(value, dict):
            return None
        value = value.get(field)
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _change_magnitude(row: dict, before: dict | None) -> float:
    """변화의 크기. 선언된 `magnitude`는 그 단위의 비중이지 움직인 양이 아니다.

    둘을 같은 값으로 쓰던 시절 이슈 단위 상수 0.35와 종가 차이가 매일 그대로
    materiality가 되어, 어떤 브리핑도 `no_material_change`가 될 수 없었다
    (실측 61건 중 0건). 이제 측정법(`delta`)을 선언한 단위는 직전 값과의 차이로
    재고, 집합이 매번 새로 뽑히는 단위(`churning`)의 등장·퇴장은 0으로 둔다.
    """
    declared = float(row.get("magnitude") or 0.0)
    if before is None:
        # 매번 새로 뽑히는 집합에서 "어제 목록에 없었다"는 변화의 근거가 아니다.
        return 0.0 if row.get("continuity") == "churning" else declared
    spec = row.get("delta")
    if not isinstance(spec, dict):
        return declared
    current = _numeric(row.get("currentValue"), spec.get("field"))
    previous = _numeric(before.get("currentValue"), spec.get("field"))
    if current is None or previous is None:
        return declared
    raw = abs(current - previous)
    if spec.get("relative"):
        if not previous:
            return declared
        raw /= abs(previous)
    raw = max(0.0, raw - float(spec.get("deadband") or 0.0))
    scale = float(spec.get("scale") or 0) or 1.0
    # 소수점을 자른다. deadband에 딱 걸친 값이 부동소수점 잔여(7e-16)로 0을 넘으면
    # "움직인 단위"로 세어져 건수 가산이 붙는다 — 안 움직인 하루에 크기가 생긴다.
    return round(max(0.0, min(1.0, raw / scale)), 4)


def _materiality(changed: list[dict]) -> float:
    """가장 크게 움직인 단위 + 실제로 움직인 단위 수의 작은 가산.

    가산은 움직인 단위만 센다. 전부 세던 시절 브리핑은 지표 12개가 종가 차이만으로
    늘 changed였고 가산이 상한 0.25에 매일 고정돼, 이슈 상수와 합쳐 0.60 바닥이 생겼다.
    """
    magnitudes = [float(row.get("magnitude") or 0) for row in changed]
    moved = [value for value in magnitudes if value > 0]
    if not moved:
        return 0.0
    return min(1.0, max(moved) + min(0.12, len(moved) * 0.03))


def _changed(current: dict, previous: dict | None) -> list[dict]:
    current_units = _unit_map(current)
    previous_units = _unit_map(previous)
    rows = []
    for uid, row in current_units.items():
        before = previous_units.get(uid)
        if before is None:
            rows.append({"id": uid, "kind": row.get("kind"), "subject": row.get("subject"), "change": "added", "previousValue": None, "currentValue": row.get("currentValue"), "horizon": row.get("horizon"), "magnitude": _change_magnitude(row, None), "continuity": row.get("continuity") or "stable", "contextDocs": row.get("contextDocs") or [], "previousContextDocs": []})
        elif content_hash(before.get("currentValue")) != content_hash(row.get("currentValue")):
            rows.append({"id": uid, "kind": row.get("kind"), "subject": row.get("subject"), "change": "changed", "previousValue": before.get("currentValue"), "currentValue": row.get("currentValue"), "horizon": row.get("horizon"), "magnitude": _change_magnitude(row, before), "continuity": row.get("continuity") or "stable", "contextDocs": row.get("contextDocs") or [], "previousContextDocs": before.get("contextDocs") or []})
    for uid, row in previous_units.items():
        if uid not in current_units:
            rows.append({"id": uid, "kind": row.get("kind"), "subject": row.get("subject"), "change": "removed", "previousValue": row.get("currentValue"), "currentValue": None, "horizon": row.get("horizon"), "magnitude": _change_magnitude(row, None), "continuity": row.get("continuity") or "stable", "contextDocs": [], "previousContextDocs": row.get("contextDocs") or []})
    return rows[:24]


def _evidence_gate(basis: dict) -> tuple[float, int, list[str], int]:
    countable = [
        row for row in basis.get("sourceRefs") or []
        if row.get("intakeStage") != "lead" and row.get("sourceType") not in {"user_note", "user_consultation"}
    ]
    tier1 = sum(1 for row in countable if int(row.get("reliabilityTier") or 4) == 1)
    tier2_groups = {
        row.get("independentGroup") for row in countable
        if int(row.get("reliabilityTier") or 4) <= 2 and row.get("independentGroup")
    }
    reliability = 1.0 if tier1 else (0.85 if len(tier2_groups) >= 2 else (0.55 if countable else 0.0))
    return reliability, tier1, sorted(tier2_groups), len(countable)


def _signal_refs(basis: dict) -> list[dict]:
    rows = []
    for ref in basis.get("sourceRefs") or []:
        if ref.get("intakeStage") != "lead":
            continue
        rows.append({
            "id": ref.get("id"), "provider": ref.get("source"), "displayTitle": str(ref.get("title") or "")[:220],
            "publishedAt": ref.get("publishedAt"), "receivedAt": ref.get("receivedAt"),
            "signalStatus": ref.get("signalStatus") or "unconfirmed", "titleHash": content_hash(ref.get("title"))[:20],
        })
    return rows[:8]


def compare_basis(current: dict, previous: dict | None, *, current_ref: dict, baseline_ref: dict | None = None) -> dict:
    # The comparison is part of the Canonical document. Tie its timestamp to the
    # generation artifact instead of wall-clock comparison time so an identical
    # regeneration remains a canonical no-op.
    now = str(current.get("asOf") or "").strip() or dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if current.get("basisStatus") == "insufficient":
        return validate_change_summary({
            "schemaVersion": 1, "comparatorVersion": "0.4.0", "basisAdapterVersion": current.get("adapterVersion"),
            "status": "insufficient_basis", "artifactKind": current.get("artifactKind"), "artifactId": current.get("artifactId"),
            "lineageId": current.get("lineageId"), "basisStatus": "insufficient", "basisCoverage": current.get("coverage"),
            "baselineRef": baseline_ref, "currentRef": current_ref, "horizonSignals": {"shortTerm": [], "mediumTerm": [], "longTerm": []},
            "changedItems": [], "materiality": 0.0, "reliability": 0.0, "corroboration": {"tier1": 0, "independentTier2": 0, "countableSources": 0},
            "counterEvidence": current.get("counterSignals") or [], "uncertainties": current.get("uncertainties") or [], "signalRefs": _signal_refs(current), "generatedAt": now,
        })
    reliability, tier1, tier2_groups, source_count = _evidence_gate(current)
    if previous is None:
        status = "baseline_created"
        changed = []
    else:
        changed = _changed(current, previous)
        materiality = _materiality(changed)
        has_conflict = bool(current.get("counterSignals")) and reliability >= 0.55 and bool(changed)
        major_gate = materiality >= 0.7 and (tier1 >= 1 or len(tier2_groups) >= 2)
        if has_conflict and materiality >= 0.45:
            status = "conflicting_uncertain"
        elif major_gate:
            status = "major_change"
        elif materiality >= 0.3:
            # 근거 등급만으로 승격하지 않는다. 브리핑은 발행처가 수십 곳이라
            # reliability가 언제나 0.85였고, 그 대안 조건이 "단위 하나라도
            # 바뀌면 신호"라는 두 번째 바닥이었다.
            status = "developing_signal"
        else:
            status = "no_material_change"
    materiality = _materiality(changed)
    horizons = {"shortTerm": [], "mediumTerm": [], "longTerm": []}
    keys = {"short_term": "shortTerm", "medium_term": "mediumTerm", "long_term": "longTerm"}
    for row in changed:
        horizons[keys.get(row.get("horizon"), "mediumTerm")].append({"id": row.get("id"), "subject": row.get("subject"), "change": row.get("change")})
    return validate_change_summary({
        "schemaVersion": 1, "comparatorVersion": "0.4.0", "basisAdapterVersion": current.get("adapterVersion"),
        "status": status, "artifactKind": current.get("artifactKind"), "artifactId": current.get("artifactId"),
        "lineageId": current.get("lineageId"), "basisStatus": current.get("basisStatus"), "basisCoverage": current.get("coverage"),
        "baselineRef": baseline_ref, "currentRef": current_ref, "horizonSignals": horizons,
        "changedItems": changed, "materiality": round(materiality, 3), "reliability": round(reliability, 3),
        "corroboration": {"tier1": tier1, "independentTier2": len(tier2_groups), "independentGroups": tier2_groups, "countableSources": source_count},
        "counterEvidence": current.get("counterSignals") or [], "uncertainties": current.get("uncertainties") or [],
        "signalRefs": _signal_refs(current), "generatedAt": now,
    })
