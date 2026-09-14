"""Preflight checks before or immediately after report generation."""
from __future__ import annotations

import re

from features.common.research_schema.data_gaps import normalize_data_gap, data_gap_rows
from features.common.utils import now_iso


def _count_sources(artifact: dict, context: dict) -> int:
    def _safe_int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    for value in (
        len(artifact.get("sourceLedger") or []),
        len(artifact.get("sources") or []),
        len(artifact.get("evidenceItems") or []),
        _safe_int((artifact.get("stats") or {}).get("sourceCount")),
        _safe_int(context.get("sourceCount")),
        _safe_int(context.get("documentCount")),
    ):
        if value:
            return value
    return 0


def _market_tape_status(artifact: dict, context: dict) -> str:
    tape = artifact.get("marketTape") or context.get("marketTape") or {}
    if not isinstance(tape, dict) or not tape:
        return "missing"
    status = str(tape.get("status") or tape.get("freshnessStatus") or "").lower()
    if status:
        return status
    rows = tape.get("items") or tape.get("rows") or tape.get("markets") or []
    if rows:
        return "available"
    return "partial"


def _has_counter_evidence(artifact: dict) -> bool:
    markdown = str(artifact.get("markdown") or "")
    if re.search(r"반론|반대 근거|리스크|틀릴 수|counter", markdown, re.I):
        return True
    for item in artifact.get("evidenceItems") or []:
        role = str(item.get("role") or item.get("evidenceRole") or "").lower()
        if role in {"challenging", "counter", "contradicting"}:
            return True
    return False


def _numeric_support(artifact_type: str, artifact: dict, context: dict) -> str:
    if artifact_type == "company_analysis":
        inputs = artifact.get("analysisInputs") or context.get("analysisInputs") or {}
        if inputs.get("secFactsOk") or inputs.get("rankedFilingOk"):
            return "available"
        return "weak"
    markdown = str(artifact.get("markdown") or "")
    return "available" if len(re.findall(r"\d+(?:\.\d+)?%?", markdown)) >= 5 else "weak"


def _required_sections_status(artifact_type: str, artifact: dict) -> str:
    markdown = str(artifact.get("markdown") or "")
    low = markdown.lower()
    if not markdown:
        return "missing"
    if artifact_type == "briefing":
        return "available" if ("체크포인트" in markdown or "확인" in markdown) else "partial"
    if artifact_type == "company_analysis":
        markers = ("financial", "재무", "valuation", "밸류에이션", "risk", "리스크")
        return "available" if sum(1 for m in markers if m in low) >= 2 else "partial"
    if artifact_type == "topic_report":
        # "결론"은 0.6 Phase 1(2026-09-13)부터 고정 헤딩 이름이 아니다 — "정리"처럼
        # 다른 이름을 쓸 수 있으므로 어느 한쪽이라도 있으면 닫는 절이 있다고 본다.
        has_close = "결론" in low or "정리" in low
        return "available" if "source & data" in low and "체크포인트" in low and has_close else "partial"
    return "available"


def preflight_from_context(artifact_type: str, artifact: dict | None = None, context: dict | None = None) -> dict:
    artifact = artifact or {}
    context = context or {}
    artifact_id = str(artifact.get("id") or artifact.get("date") or context.get("artifactId") or "")
    source_count = _count_sources(artifact, context)
    data_gaps = data_gap_rows(artifact.get("dataGaps")) or data_gap_rows(context.get("dataGaps"))
    checkpoints = list(artifact.get("checkpoints") or context.get("checkpoints") or [])
    evidence = list(artifact.get("evidenceItems") or context.get("evidenceItems") or [])
    source_ledger = list(artifact.get("sourceLedger") or context.get("sourceLedger") or [])
    tape_status = _market_tape_status(artifact, context)
    numeric = _numeric_support(artifact_type, artifact, context)
    sections = _required_sections_status(artifact_type, artifact)

    risks: list[str] = []
    derived_gaps: list[dict] = []
    if source_count < 3:
        risks.append(f"관련 자료가 적습니다({source_count}건).")
        derived_gaps.append(normalize_data_gap(
            {"category": "evidence", "message": f"관련 자료가 적습니다({source_count}건).", "severity": "medium"},
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            source_section="quality_generation.preflight",
        ))
    if tape_status in {"missing", "stale", "failed"} and artifact_type in {"briefing", "topic_report"}:
        risks.append("marketTape가 없거나 최신성이 낮습니다.")
        derived_gaps.append(normalize_data_gap(
            {"category": "market_data", "message": "marketTape가 없거나 최신성이 낮습니다.", "severity": "medium"},
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            source_section="quality_generation.preflight",
        ))
    if not checkpoints:
        risks.append("구조화된 체크포인트가 없습니다.")
    if numeric == "weak":
        risks.append("수치 근거가 약합니다. 확인되지 않은 숫자는 추정하지 않아야 합니다.")
    if not _has_counter_evidence(artifact):
        risks.append("반론 또는 이 판단이 틀릴 조건이 약합니다.")
    if data_gaps:
        risks.append(f"dataGap이 {len(data_gaps)}개 남아 있습니다.")
    if sections != "available":
        risks.append("보고서 유형별 필수 섹션이 일부 부족합니다.")

    blocking = any((g.get("severity") in {"blocking", "high"}) for g in data_gaps if isinstance(g, dict)) and source_count == 0
    prompt_hints = [
        "근거가 부족한 수치나 가격 반응은 추정하지 말고 '확인 필요' 또는 데이터 한계로 표시하세요.",
        "강세/약세 또는 supporting/challenging 근거를 분리하고, 판단이 틀릴 조건을 명시하세요.",
        "체크포인트는 관찰 가능한 지표와 positive/negative signal을 포함하세요.",
        "남은 dataGap과 suggestedAction은 Source & Data Notes 또는 데이터 한계에 명시하세요.",
    ]
    if artifact_type == "company_analysis":
        prompt_hints.append("기업분석 숫자는 SEC companyfacts/DART/공식 공시로 확인된 범위에서만 단정하세요.")
    if artifact_type == "briefing":
        prompt_hints.append("미국장/한국장 날짜 정합성과 marketTape 최신성을 구분해 쓰세요.")

    return {
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "status": "fail" if blocking else ("warn" if risks else "pass"),
        "requiredInputs": {
            "sourceCount": source_count,
            "marketTape": tape_status,
            "sourceLedger": "available" if source_ledger else "missing",
            "evidenceItems": "available" if evidence else "missing",
            "checkpoints": "available" if checkpoints else "missing",
            "numericSupport": numeric,
            "counterEvidence": "available" if _has_counter_evidence(artifact) else "weak",
            "requiredSections": sections,
        },
        "risks": list(dict.fromkeys(risks))[:10],
        "promptHints": prompt_hints,
        "derivedDataGaps": derived_gaps[:6],
        "generatedAt": now_iso(),
    }
