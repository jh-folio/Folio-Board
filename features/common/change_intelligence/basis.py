"""Canonical ChangeBasis schema and bounded normalization."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

ARTIFACT_KINDS = {"briefing", "company_analysis", "topic_report", "market_memory"}
BASIS_STATUSES = {"ready", "partial", "insufficient"}
HORIZONS = {"short_term", "medium_term", "long_term"}
# 단위의 정체성이 산출물 사이에 이어지는가. `churning`은 매 생성마다 집합이 다시
# 뽑히는 단위(그날 고른 이슈)라 "어제 목록에 없었다"가 변화의 근거가 되지 않는다.
CONTINUITY_MODES = {"stable", "churning"}


def clean(value: Any, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(clean(part, 500) for part in parts)
    return f"{prefix}_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]


def content_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_source_ref(value: dict, index: int) -> dict:
    row = value or {}
    tier = row.get("reliabilityTier", row.get("reliability_tier", row.get("sourcePriority", 3)))
    try:
        tier = max(1, min(int(tier), 4))
    except (TypeError, ValueError):
        tier = 3
    title = clean(row.get("title"), 220)
    url = clean(row.get("url"), 1200)
    path = clean(row.get("path"), 500)
    source_type = clean(row.get("sourceType") or row.get("source_type") or row.get("type") or "unknown", 80)
    source = clean(row.get("source") or row.get("provider") or "unknown", 120)
    intake_stage = clean(row.get("intakeStage") or row.get("intake_stage") or "evidence", 20).lower()
    signal_status = clean(row.get("signalStatus") or row.get("signal_status"), 30).lower()
    independent = clean(row.get("independentGroup") or row.get("independent_group") or source, 120).lower()
    ref_id = clean(row.get("id") or row.get("sourceId"), 100) or stable_id("ref", source, url or path, title, index)
    return {
        "id": ref_id,
        "title": title,
        "url": url,
        "path": path,
        "sourceType": source_type,
        "source": source,
        "reliabilityTier": tier,
        "independentGroup": independent,
        "intakeStage": intake_stage,
        "signalStatus": signal_status,
        "publishedAt": clean(row.get("publishedAt") or row.get("published_at") or row.get("date"), 50),
        "contentHash": clean(row.get("contentHash") or row.get("content_hash"), 80) or content_hash({"title": title, "url": url, "path": path}),
    }


def normalize_delta_spec(value: Any) -> dict | None:
    """변화량 측정법 선언. 없으면 comparator가 선언된 magnitude를 그대로 쓴다.

    선언된 `magnitude`는 "이 단위가 그날 얼마나 큰가"(동인 비중, 이슈 상수)이지
    "직전 대비 얼마나 움직였나"가 아니다. 둘을 같은 값으로 쓰면 매일 같은 크기로
    존재하기만 해도 변화 크기가 그만큼 잡힌다.
    """
    if not isinstance(value, dict):
        return None
    try:
        scale = float(value.get("scale") or 0)
    except (TypeError, ValueError):
        return None
    if scale <= 0:
        return None
    try:
        deadband = max(0.0, float(value.get("deadband") or 0))
    except (TypeError, ValueError):
        deadband = 0.0
    return {
        "field": clean(value.get("field"), 60) or None,
        "relative": bool(value.get("relative")),
        "scale": scale,
        "deadband": deadband,
    }


def normalize_change_unit(value: dict, index: int) -> dict:
    row = value or {}
    subject = clean(row.get("subject") or row.get("label") or row.get("title"), 220)
    kind = clean(row.get("kind") or "observation", 80)
    horizon = clean(row.get("horizon") or "medium_term", 30)
    if horizon not in HORIZONS:
        horizon = "medium_term"
    try:
        magnitude = float(row.get("magnitude")) if row.get("magnitude") is not None else None
        magnitude = max(0.0, min(abs(magnitude), 1.0)) if magnitude is not None else None
    except (TypeError, ValueError):
        magnitude = None
    refs = row.get("sourceRefIds") or row.get("source_ref_ids") or []
    continuity = clean(row.get("continuity") or "stable", 20).lower()
    if continuity not in CONTINUITY_MODES:
        continuity = "stable"
    return {
        "id": clean(row.get("id"), 100) or stable_id("unit", kind, subject, index),
        "kind": kind,
        "subject": subject,
        "previousValue": row.get("previousValue"),
        "currentValue": row.get("currentValue"),
        "direction": clean(row.get("direction") or "changed", 40),
        "magnitude": magnitude,
        "continuity": continuity,
        "delta": normalize_delta_spec(row.get("delta")),
        "horizon": horizon,
        "sourceRefIds": [clean(ref, 100) for ref in refs if clean(ref, 100)][:12],
        # 의미 비교·변화 상세용 대표 자료 제목. currentValue 밖에 두는 이유:
        # 제목은 매일 회전하므로 hash 비교에 넣으면 모든 단위가 매일 "changed"가 된다.
        "contextDocs": [clean(doc, 160) for doc in row.get("contextDocs") or [] if clean(doc, 160)][:3],
    }


def normalize_basis(payload: dict) -> dict:
    raw = payload or {}
    artifact_kind = clean(raw.get("artifactKind"), 40)
    if artifact_kind not in ARTIFACT_KINDS:
        raise ValueError("change_basis_artifact_kind_invalid")
    refs = [normalize_source_ref(row, idx) for idx, row in enumerate(raw.get("sourceRefs") or [], 1) if isinstance(row, dict)][:32]
    units = [normalize_change_unit(row, idx) for idx, row in enumerate(raw.get("changeUnits") or [], 1) if isinstance(row, dict)][:24]
    countable = [row for row in refs if row["intakeStage"] != "lead" and row["sourceType"] not in {"user_note", "user_consultation"}]
    status = clean(raw.get("basisStatus"), 20)
    if status not in BASIS_STATUSES:
        status = "ready" if units and countable else ("partial" if units or countable else "insufficient")
    if not units and not countable:
        status = "insufficient"
    coverage = raw.get("coverage") if isinstance(raw.get("coverage"), dict) else {}
    coverage = {
        key: max(0.0, min(float(coverage.get(key) or 0), 1.0))
        for key in ("source", "comparison", "counter", "market", "overall")
    }
    if not coverage["overall"]:
        coverage["source"] = coverage["source"] or min(1.0, len(countable) / 3)
        coverage["counter"] = coverage["counter"] or (1.0 if raw.get("counterSignals") else 0.0)
        coverage["market"] = coverage["market"] or (1.0 if raw.get("metrics") else 0.0)
        coverage["overall"] = round(sum(coverage[key] for key in ("source", "counter", "market")) / 3, 3)
    return {
        "schemaVersion": 1,
        "adapterVersion": clean(raw.get("adapterVersion") or "0.4.0", 30),
        "artifactKind": artifact_kind,
        "artifactId": clean(raw.get("artifactId"), 160),
        "lineageId": clean(raw.get("lineageId") or raw.get("artifactId"), 160),
        "scope": raw.get("scope") if isinstance(raw.get("scope"), dict) else {},
        "asOf": clean(raw.get("asOf") or dt.datetime.now(dt.timezone.utc).isoformat(), 50),
        "basisStatus": status,
        "changeUnits": units,
        "sourceRefs": refs,
        "counterSignals": [clean(row, 400) for row in raw.get("counterSignals") or [] if clean(row, 400)][:12],
        "uncertainties": [clean(row, 400) for row in raw.get("uncertainties") or [] if clean(row, 400)][:12],
        "metrics": [row for row in raw.get("metrics") or [] if isinstance(row, dict)][:24],
        "coverage": coverage,
    }
