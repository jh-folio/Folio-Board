"""Common research quality evaluator.

This is the generalized Step 7 version of Topic Report v2's Quality Gate. It
keeps the old flat Topic Report fields for UI/test compatibility while adding
status, sourceGrounding, suggestedFixes, and structured artifact inputs.
"""
from __future__ import annotations

import re

from features.common.utils import now_iso
from features.common.research_quality.schema import grade_from_score, level_from_ratio, risk_level, status_from_score
from features.common.research_quality.source_grounding import evaluate_source_grounding
from features.common.research_schema.data_gaps import data_gap_rows
from features.common.research_schema.tracked_checkpoints import checkpoint_labels

_WEIGHTS = {
    "topic_answered": 12,
    "scope_defined": 7,
    "data_coverage": 14,
    "source_coverage": 10,
    "numeric_support": 10,
    "counterargument_present": 12,
    "scenario_quality": 8,
    "checkpoint_quality": 8,
    "source_grounding": 10,
    "hallucination_risk": 7,
    "personal_bias_risk": 5,
    "deep_question_coverage": 8,
    "source_diversity": 4,
}

_SECTION_MARKERS = {
    "executive": ("executive summary", "핵심 결론", "현재 판단", "요약"),
    "scope": ("분석 범위", "질문 정의", "포함 범위", "제외 범위"),
    "counter": ("반론", "리스크", "틀릴 수 있", "반대 근거", "counter"),
    "scenario": ("시나리오",),
    "checkpoint": ("체크포인트", "확인할", "지켜볼", "next checkpoint"),
    "sources": ("source & data", "데이터 메모", "데이터 한계", "source and data", "참고자료"),
}

_CONDITION_WORDS = ("넘으면", "아래로", "위로", "이상", "이하", "돌파", "하회", "상회", "되면", "라면", "초과", "미만")


def _has_section(markdown_lower: str, key: str) -> bool:
    return any(marker in markdown_lower for marker in _SECTION_MARKERS[key])


def _section_body(markdown: str, markers: tuple) -> str:
    lines = str(markdown or "").split("\n")
    out: list[str] = []
    capturing = False
    for line in lines:
        is_header = line.lstrip().startswith("#")
        if is_header:
            low = line.lower()
            if any(m in low for m in markers):
                capturing = True
                continue
            if capturing:
                break
        if capturing:
            out.append(line)
    return "\n".join(out)


# 기업분석 보고서의 고정 섹션 이름(`company_analysis/report_contract.py`와 같다).
_COMPANY_SCENARIO_SECTION = "성장 전망과 체크포인트"
_H2_NUMBER = re.compile(r"^\s*\d+[.)]\s*")


def _top_section_body(markdown: str, title: str) -> str:
    """번호를 무시하고 그 이름의 최상위(`## `) 절 본문. 하위 헤딩은 포함하고 다음 `## `에서 멈춘다."""
    out: list[str] = []
    capturing = False
    for line in str(markdown or "").split("\n"):
        stripped = line.lstrip()
        top = stripped.startswith("## ") or (stripped.startswith("# ") and not stripped.startswith("##"))
        if top:
            if capturing:
                break
            heading = _H2_NUMBER.sub("", stripped.lstrip("#").strip())
            capturing = heading.startswith(title)
            continue
        if capturing:
            out.append(line)
    return "\n".join(out)


def _artifact_markdown(artifact_type: str, artifact: dict) -> str:
    if artifact_type == "regime_state":
        return "\n\n".join([
            f"# {artifact.get('stateLabel') or artifact.get('state_label') or artifact.get('story') or 'Regime State'}",
            "## 요약",
            str(artifact.get("summary") or ""),
            "## 근거",
            str(artifact.get("rationale") or artifact.get("conclusion") or ""),
            "## 다음 체크포인트",
            # 구조화 체크포인트(dict)가 섞인 목록이다 — 그대로 f-string에 넣으면 dict
            # repr이 평가용 markdown에 실려 품질 점수가 서식 잡음에 흔들린다.
            "\n".join(f"- {x}" for x in checkpoint_labels(artifact.get("nextCheckpoints"))),
        ])
    return str((artifact or {}).get("markdown") or "")


def _artifact_evidence_summary(artifact_type: str, artifact: dict) -> dict:
    if artifact_type == "topic_report":
        return artifact.get("evidencePackSummary") or {}
    if artifact_type == "briefing":
        return {
            "totalDocs": (artifact.get("stats") or {}).get("sourceCount") or len(artifact.get("sources") or []),
            "roleCounts": {},
            "axisCoverage": {},
        }
    if artifact_type == "thesis_delta":
        evidence = artifact.get("evidenceItems") or artifact.get("evidence") or []
        role_counts: dict[str, int] = {}
        for item in evidence:
            role = item.get("role") or item.get("evidenceRole") or "neutral"
            role_counts[role] = role_counts.get(role, 0) + 1
        return {"totalDocs": len(evidence), "roleCounts": role_counts, "axisCoverage": {}}
    if artifact_type == "company_analysis":
        return {
            "totalDocs": len(artifact.get("sources") or []),
            "roleCounts": {},
            "axisCoverage": {},
        }
    if artifact_type == "regime_state":
        total = int(artifact.get("evidenceCount90d") or artifact.get("evidence_count_90d") or 0)
        return {"totalDocs": total, "roleCounts": {}, "axisCoverage": {}}
    return {}


def _artifact_user_context(artifact_type: str, artifact: dict, explicit: bool) -> bool:
    return bool(explicit or artifact_type in {"personal_overlay", "thesis_delta"} or artifact.get("userContext"))


def evaluate_report(
    markdown: str,
    *,
    evidence_summary: dict | None = None,
    topic_plan: dict | None = None,
    user_context_present: bool = False,
    checkpoints: list | None = None,
    source_ledger: list | None = None,
    evidence_items: list | None = None,
    data_gaps: list | None = None,
    market_tape: dict | None = None,
    verified_claims: list | None = None,
    artifact_type: str = "topic_report",
) -> dict:
    md = markdown or ""
    low = md.lower()
    evidence_summary = evidence_summary or {}
    axis_coverage = evidence_summary.get("axisCoverage") or {}
    question_coverage = evidence_summary.get("questionCoverage") or {}
    deep_enabled = bool((evidence_summary.get("deepResearch") or {}).get("enabled"))
    role_counts = evidence_summary.get("roleCounts") or {}
    total_docs = int(evidence_summary.get("totalDocs") or len(evidence_items or []) or 0)

    scores: dict[str, float] = {}
    warnings: list[str] = []
    suggested: list[str] = []

    answered = 0.0
    if _has_section(low, "executive"):
        answered += 0.6
    if any(term in md for term in ("현재 판단", "판정", "결론", "정리", "요약")):
        answered += 0.4
    scores["topic_answered"] = min(1.0, answered)
    if answered < 0.6:
        warnings.append("핵심 결론/현재 판단이 명확하지 않습니다.")
        suggested.append("요약 또는 현재 판단 섹션에서 질문에 직접 답하세요.")

    if artifact_type in {"briefing", "thesis_delta", "regime_state"}:
        scores["scope_defined"] = 0.7
    else:
        scores["scope_defined"] = 1.0 if _has_section(low, "scope") else 0.3
        if scores["scope_defined"] < 0.7:
            warnings.append("분석 범위(포함/제외)가 명시되지 않았습니다.")

    if axis_coverage:
        level_score = {"high": 1.0, "medium": 0.6, "low": 0.3, "none": 0.0}
        avg = sum(level_score.get(c.get("level", "none"), 0.0) for c in axis_coverage.values()) / len(axis_coverage)
        scores["data_coverage"] = avg
        weak = [c.get("label", "") for c in axis_coverage.values() if c.get("level") in ("none", "low")]
        if weak:
            warnings.append(f"자료가 부족한 분석 축: {', '.join(w for w in weak if w)[:120]}")
    else:
        scores["data_coverage"] = min(1.0, total_docs / 6) if total_docs else 0.35

    scores["source_coverage"] = min(1.0, total_docs / 8) if total_docs else 0.25
    if total_docs and total_docs < 3:
        warnings.append(f"관련 자료가 적습니다({total_docs}건).")

    if deep_enabled and question_coverage:
        level_score = {"high": 1.0, "medium": 0.65, "low": 0.35, "none": 0.0}
        # round 1이 충분해 건너뛴 질문(not_executed)은 결측이지 0점이 아니다 —
        # 0으로 세면 커버리지가 가장 좋았던 실행일수록 점수가 깎인다.
        scored = [c for c in question_coverage.values() if c.get("level") != "not_executed"]
        scored = scored or list(question_coverage.values())
        q_avg = sum(level_score.get(c.get("level", "none"), 0.0) for c in scored) / len(scored)
        scores["deep_question_coverage"] = q_avg
        weak_questions = [c.get("question", "") for c in question_coverage.values() if c.get("level") in ("none", "low")]
        if weak_questions:
            warnings.append(f"근거가 부족한 심층 질문: {', '.join(q for q in weak_questions if q)[:140]}")
            suggested.append("심층 모드에서는 근거가 부족한 하위 질문을 Source & Data Notes와 데이터 갭에 명시하세요.")
    elif deep_enabled:
        scores["deep_question_coverage"] = 0.0
        warnings.append("심층 모드지만 하위 질문 커버리지가 저장되지 않았습니다.")
    else:
        scores["deep_question_coverage"] = 1.0

    if deep_enabled:
        source_rows = source_ledger or evidence_items or []
        distinct_sources = {
            str(row.get("source") or row.get("type") or "").strip().lower()
            for row in source_rows
            if isinstance(row, dict) and str(row.get("source") or row.get("type") or "").strip()
        }
        scores["source_diversity"] = min(1.0, len(distinct_sources) / 3)
        if scores["source_diversity"] < 0.67:
            warnings.append("심층 리서치 출처 다양성이 낮습니다.")
            suggested.append("뉴스 외 공식자료·거시지표·시장 데이터 등 서로 다른 출처 유형을 보강하세요.")
    else:
        scores["source_diversity"] = 1.0

    # Briefings have a final deterministic fact validator.  Count only its
    # distinct factKey/kind pairs so URLs, dates, reference titles, and
    # repeated raw numbers cannot manufacture numeric support.  Other
    # artifacts retain the historical evaluator rule for compatibility.
    raw_numbers = len(re.findall(r"\d+(?:\.\d+)?%?", md))
    if artifact_type == "briefing":
        distinct_facts = {
            (str(row.get("factKey") or ""), str(row.get("kind") or ""))
            for row in (verified_claims or [])
            if isinstance(row, dict)
            and str(row.get("factKey") or "").strip()
            and str(row.get("kind") or "").strip()
        }
        numeric_count = len(distinct_facts)
        scores["numeric_support"] = min(1.0, numeric_count / 5)
    else:
        numeric_count = raw_numbers
        scores["numeric_support"] = min(1.0, raw_numbers / 25)
    if numeric_count < 5 and artifact_type not in {"regime_state"}:
        warnings.append("숫자 근거가 부족합니다.")

    counter = 0.0
    if _has_section(low, "counter"):
        counter += 0.6
    if role_counts.get("challenging") or "반대 근거" in md or "counterEvidence" in md:
        counter += 0.3
    if artifact_type == "briefing":
        counter = max(counter, 0.5)
    scores["counterargument_present"] = min(1.0, counter)
    if counter < 0.6:
        warnings.append("반론과 리스크가 약합니다(확증편향 방지).")
        suggested.append("반대 근거 또는 이 판단이 틀릴 조건을 추가하세요.")

    if artifact_type == "company_analysis":
        # 기업분석의 조건은 PER 배수 표('PER 조건별 시나리오')가 아니라 성장 체크포인트 절에
        # 있다. 첫 '시나리오' 헤딩을 잡으면 PER 표만 읽고 뒤의 조건을 놓친다(HWM 2026-09).
        scenario_body = _top_section_body(md, _COMPANY_SCENARIO_SECTION)
        has_scenario = bool(scenario_body.strip())
    else:
        scenario_body = _section_body(md, _SECTION_MARKERS["scenario"])
        has_scenario = _has_section(low, "scenario")
    if has_scenario:
        cond_hits = sum(1 for w in _CONDITION_WORDS if w in scenario_body)
        scores["scenario_quality"] = min(1.0, 0.5 + cond_hits * 0.17)
        if cond_hits == 0:
            warnings.append("시나리오가 조건 기반(예: 'X를 넘으면')이 아닙니다.")
    else:
        scores["scenario_quality"] = 0.5 if artifact_type in {"briefing", "thesis_delta", "regime_state"} else 0.2

    checkpoint_body = _section_body(md, _SECTION_MARKERS["checkpoint"])
    structured_checkpoints = checkpoints or []
    if structured_checkpoints:
        scores["checkpoint_quality"] = min(1.0, 0.65 + len(structured_checkpoints) * 0.08)
    elif _has_section(low, "checkpoint"):
        scores["checkpoint_quality"] = 1.0 if re.search(r"\d", checkpoint_body) else 0.6
    else:
        scores["checkpoint_quality"] = 0.2
        warnings.append("확인할 체크포인트가 없습니다.")

    grounding = evaluate_source_grounding(
        md,
        source_ledger=source_ledger,
        evidence_items=evidence_items,
        market_tape=market_tape,
        data_gaps=data_gaps,
    )
    scores["source_grounding"] = grounding["score"]
    warnings.extend(grounding["warnings"])
    for gap in data_gaps or []:
        if isinstance(gap, dict) and gap.get("suggestedAction"):
            suggested.append(str(gap["suggestedAction"]))

    if total_docs == 0 and raw_numbers > 12:
        scores["hallucination_risk"] = 0.3
        warnings.append("근거 자료 없이 수치가 많습니다. 추정 여부를 확인하세요.")
    elif data_gaps and any(g.get("severity") in {"high", "blocking"} for g in data_gaps if isinstance(g, dict)):
        scores["hallucination_risk"] = 0.55
    elif "추정" in md or _has_section(low, "sources") or grounding["score"] >= 0.55:
        scores["hallucination_risk"] = 1.0
    else:
        scores["hallucination_risk"] = 0.6

    if user_context_present and counter < 0.7:
        scores["personal_bias_risk"] = 0.3
        warnings.append("사용자 관점에 끌려갔을 수 있습니다. 반대 근거를 보강하세요.")
    else:
        scores["personal_bias_risk"] = 1.0

    total = sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS) / sum(_WEIGHTS.values())
    score_100 = int(round(total * 100))

    # 근거가 하나도 없는 분석 축이 있으면 점수에 상한을 건다.
    #
    # 가중 평균만으로는 이런 보고서가 A-로 통과한다 — 실제로 분석축 5개 중 3개가
    # 0건이고 본문이 그 사실을 "팩에 자료가 없다"고 반복해 적은 보고서가 87점/A-/pass를
    # 받았다. 잘 쓴 문장은 없는 근거를 대신하지 못하고, 등급이 통과라고 말하면 사용자는
    # 무엇이 비었는지 보지 못한다. 축 하나가 통째로 비는 것은 감점이 아니라 결격이다.
    ceiling = 100
    ceiling_reasons: list[str] = []
    if axis_coverage:
        empty_axes = [c for c in axis_coverage.values() if c.get("level") == "none"]
        empty_ratio = len(empty_axes) / len(axis_coverage)
        if empty_ratio >= 0.5:
            ceiling = min(ceiling, 59)
        elif empty_axes:
            ceiling = min(ceiling, 74)
        if empty_axes:
            labels = ", ".join(str(c.get("label") or "") for c in empty_axes if c.get("label"))
            ceiling_reasons.append(
                f"근거가 0건인 분석 축 {len(empty_axes)}/{len(axis_coverage)}개({labels[:80]})"
            )
    if deep_enabled and question_coverage:
        executed = [c for c in question_coverage.values() if c.get("level") != "not_executed"]
        empty_questions = [c for c in executed if c.get("level") == "none"]
        if executed and len(empty_questions) / len(executed) >= 0.34:
            ceiling = min(ceiling, 69)
            ceiling_reasons.append(
                f"근거가 0건인 심층 하위 질문 {len(empty_questions)}/{len(executed)}개"
            )
    if score_100 > ceiling:
        warnings.append(
            f"자료 커버리지 결격으로 점수를 {ceiling}점으로 제한했습니다: {'; '.join(ceiling_reasons)}"
        )
        suggested.append("빈 축의 검색어를 넓히거나 해당 주제의 자료를 research-inbox에 보강한 뒤 인덱스를 갱신하세요.")
        score_100 = ceiling

    grade = grade_from_score(score_100)
    return {
        "score": score_100,
        "grade": grade,
        "status": status_from_score(score_100),
        "generatedAt": now_iso(),
        "artifactType": artifact_type,
        "dataCoverage": level_from_ratio(scores["data_coverage"]),
        "sourceCoverage": level_from_ratio(scores["source_coverage"]),
        "numericSupport": level_from_ratio(scores["numeric_support"]),
        "counterArgument": "present" if scores["counterargument_present"] >= 0.7 else "weak",
        "scenarioQuality": level_from_ratio(scores["scenario_quality"]),
        "checkpointQuality": level_from_ratio(scores["checkpoint_quality"]),
        "sourceGrounding": grounding["level"],
        "hallucinationRisk": risk_level(scores["hallucination_risk"]),
        "personalBiasRisk": "low" if scores["personal_bias_risk"] >= 0.8 else "elevated",
        "coverageCeiling": {"applied": ceiling < 100, "ceiling": ceiling, "reasons": ceiling_reasons},
        "checks": {k: round(v, 2) for k, v in scores.items()},
        "sourceGroundingDetail": grounding,
        "warnings": list(dict.fromkeys(warnings))[:10],
        "suggestedFixes": list(dict.fromkeys(suggested))[:6],
    }


def evaluate_artifact(artifact_type: str, artifact: dict) -> dict:
    artifact = artifact or {}
    markdown = _artifact_markdown(artifact_type, artifact)
    final_validation = artifact.get("finalValidation") or {}
    return evaluate_report(
        markdown,
        evidence_summary=_artifact_evidence_summary(artifact_type, artifact),
        topic_plan=artifact.get("topicPlan"),
        user_context_present=_artifact_user_context(artifact_type, artifact, False),
        checkpoints=artifact.get("checkpoints") or [],
        source_ledger=artifact.get("sourceLedger") or artifact.get("sources") or [],
        evidence_items=artifact.get("evidenceItems") or [],
        data_gaps=data_gap_rows(artifact.get("dataGaps")),
        market_tape=artifact.get("marketTape") or {},
        verified_claims=final_validation.get("verifiedClaims") or [],
        artifact_type=artifact_type,
    )
