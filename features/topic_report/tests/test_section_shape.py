"""보고서 골격 계약 — 머리·꼬리는 고정, 본문은 주제가 정한다."""
from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import planner as P
from features.topic_report.axis_analysis import axis_evidence, build_axis_briefs, render_axis_briefs
from features.topic_report.depth_policy import build_depth_policy
from features.topic_report.report_contract import validate_deep_report
from features.topic_report.topic_schema import (
    BODY_SECTION_MAX,
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
    body_sections,
    compose_sections,
)


# ------------------------------------------------------------------ 계획이 골격을 정한다

def test_plan_sections_follow_the_analysis_axes():
    plan = P.build_rule_plan("기대심리가 국채금리와 통화정책 전망에 미치는 영향")
    labels = [axis["label"] for axis in plan["analysisAxes"]]
    assert body_sections(plan["expectedSections"]) == labels[:BODY_SECTION_MAX]
    assert plan["expectedSections"][: len(REPORT_HEAD_SECTIONS)] == list(REPORT_HEAD_SECTIONS)
    assert plan["expectedSections"][-len(REPORT_TAIL_SECTIONS):] == list(REPORT_TAIL_SECTIONS)


def test_reserved_names_and_duplicates_are_filtered_out():
    sections = compose_sections(["반론과 리스크", "나만의 축", "Executive Summary", "또 다른 축", "나만의 축"])
    assert body_sections(sections) == ["나만의 축", "또 다른 축"]
    assert sections.count("반론과 리스크") == 1, "꼬리 이름을 본문에 다시 쓰지 않는다"
    assert sections.count("Executive Summary") == 1


def test_too_few_usable_body_sections_falls_back_to_the_default_skeleton():
    # 계획이 쓸 수 있는 본문을 못 내놓으면 기존 골격으로 되돌린다 — 섹션 하나짜리
    # 보고서를 내보내는 것보다 낫다. "결론"은 0.6 Phase 1(2026-09-13)부터 예약 이름이
    # 아니라서(꼬리 헤딩에서 빠졌다) 여기서는 계속 예약 이름인 "반론과 리스크"로 예시를 든다.
    sections = compose_sections(["반론과 리스크", "나만의 축"])
    assert body_sections(sections) == ["현재 상황", "작동 경로", "수혜/피해 자산과 기업"]


def test_numbered_and_hashed_labels_are_cleaned():
    assert body_sections(compose_sections(["## 2. 장기금리 분해", "1. 엔캐리"])) == ["장기금리 분해", "엔캐리"]


def _plan_payload(sections):
    plan = P.apply_deep_research_plan(P.build_rule_plan("금리와 환율"))
    plan["expectedSections"] = list(sections)
    return plan


def _validate_plan(sections):
    from features.topic_report.approved_plan_schema import TopicPlanV1

    return TopicPlanV1.model_validate(_plan_payload(sections))


def test_approval_accepts_a_topic_shaped_body():
    sections = compose_sections(["실질금리와 기간프리미엄", "엔캐리 전이", "정책 기대", "위험선호"])
    assert _validate_plan(sections).expectedSections == sections


def test_approval_still_refuses_a_missing_tail_section():
    broken = [s for s in compose_sections(["축 하나", "축 둘"]) if s != "반론과 리스크"]
    with pytest.raises(ValidationError, match="fixed_tail_sections"):
        _validate_plan(broken)


def test_approval_refuses_too_few_body_sections():
    with pytest.raises(ValidationError, match="body_section_count_out_of_range"):
        _validate_plan([*REPORT_HEAD_SECTIONS, "축 하나", *REPORT_TAIL_SECTIONS])


# ------------------------------------------------------------------------ 분량 배분

def test_budgets_follow_the_declared_sections():
    sections = compose_sections(["축1", "축2", "축3", "축4", "축5"])
    policy = build_depth_policy(
        deep_research=True,
        analysis_axis_count=5,
        subquestion_count=12,
        evidence_count=34,
        report_type="macro_analysis",
        sections=sections,
    )
    assert list(policy["sectionBudgets"]) == sections
    body_total = sum(policy["sectionBudgets"][h] for h in policy["bodySections"])
    # 분석축이 표·꼬리에 밀려 축당 400자를 받던 구조를 되돌린다.
    assert body_total / policy["targetChars"] > 0.35
    assert min(policy["sectionBudgets"][h] for h in policy["bodySections"]) > 900


# ------------------------------------------------------------------------ 본문 검증

_TAIL_BODY = "\n\n".join(f"## {name}\n\n내용 {name} 4.75% 이상이면 악화." for name in REPORT_TAIL_SECTIONS)


def _report(body_headings):
    head = "\n\n".join(f"## {name}\n\n내용." for name in REPORT_HEAD_SECTIONS)
    body = "\n\n".join(f"## {name}\n\n내용." for name in body_headings)
    return f"{head}\n\n{body}\n\n{_TAIL_BODY}"


def _validate(markdown, expected):
    return validate_deep_report(
        markdown,
        source_ledger=[],
        depth_policy={"recommendedMinChars": 0, "safetyMaxChars": 99_999, "sections": expected},
        material_resolution={},
        internal_score=90,
    )


def test_missing_required_tail_blocks():
    expected = compose_sections(["축1", "축2"])
    # "결론"은 0.6 Phase 1(2026-09-13)부터 고정 꼬리가 아니라서 꼬리 가운데 항목인
    # "앞으로 확인할 체크포인트"를 지워 같은 회귀(필수 꼬리 하나 누락)를 재현한다.
    broken = _report(["축1", "축2"]).replace(
        "## 앞으로 확인할 체크포인트\n\n내용 앞으로 확인할 체크포인트 4.75% 이상이면 악화.\n\n", ""
    )
    codes = {row["code"] for row in _validate(broken, expected)["defects"]}
    assert "required_sections_missing" in codes


def test_a_different_body_is_a_defect_not_a_block():
    expected = compose_sections(["축1", "축2"])
    result = _validate(_report(["다른 축", "또 다른 축"]), expected)
    codes = {row["code"] for row in result["defects"]}
    assert "body_sections_differ" in codes
    assert result["valid"] is True, "본문 구성이 달라도 결과물을 버리지 않는다"


def test_matching_body_has_no_structure_defect():
    expected = compose_sections(["축1", "축2"])
    codes = {row["code"] for row in _validate(_report(["축1", "축2"]), expected)["defects"]}
    assert "body_sections_differ" not in codes
    assert "required_sections_missing" not in codes


# ------------------------------------------------------------------------ 축별 분석

_PLAN = {
    "analysisAxes": [
        {"key": "a", "label": "실질금리", "questions": ["무엇이 올렸나?"]},
        {"key": "b", "label": "엔캐리", "questions": []},
    ],
    "deepResearch": {"subQuestions": [{"id": "dq_01", "axisKey": "a", "question": "실질금리 기여도는?"}]},
}
_EVIDENCE = [
    {"id": "ev_001", "axisKey": "a", "relevance": 0.9, "title": "실질금리", "source": "Reuters", "date": "2026-08-20", "summary": "올랐다", "path": ""},
    {"id": "ev_002", "researchQuestionId": "dq_01", "relevance": 0.8, "title": "기여도", "source": "FT", "date": "2026-08-21", "summary": "분해", "path": ""},
    {"id": "ev_003", "axisKey": "b", "relevance": 0.7, "title": "엔캐리", "source": "CNBC", "date": "2026-08-22", "summary": "엔화", "path": ""},
]
_ANSWER = (
    '{"findings": ["실질금리가 상승분의 대부분"], "numbers": ["DFII10 = 2.35%"],'
    ' "counterEvidence": ["기대인플레이션은 하락"], "uncertainties": ["기간프리미엄 분해 없음"],'
    ' "sourceIds": ["ev_001", "ev_999"]}'
)


def test_axis_evidence_collects_axis_and_question_matches():
    rows = axis_evidence("a", {"dq_01"}, _EVIDENCE)
    assert {row["id"] for row in rows} == {"ev_001", "ev_002"}


def test_each_axis_gets_its_own_call():
    seen = []

    def call(prompt, context):
        seen.append(context)
        return _ANSWER

    briefs = build_axis_briefs(_PLAN, _EVIDENCE, run_call=call)
    assert len(seen) == 2, "축마다 한 번씩 답을 만든다"
    assert [row["status"] for row in briefs] == ["ok", "ok"]
    assert "실질금리" in seen[0] and "엔캐리" in seen[1]


def test_hallucinated_source_ids_are_dropped():
    briefs = build_axis_briefs(_PLAN, _EVIDENCE, run_call=lambda p, c: _ANSWER)
    assert briefs[0]["sourceIds"] == ["ev_001"], "그 축이 실제로 본 근거만 남는다"


def test_one_failed_axis_does_not_kill_the_report():
    def call(prompt, context):
        # 자기 축의 라벨로만 가른다. 이제 모든 컨텍스트가 **다른 축의 이름도** 싣기
        # 때문에(영역 침범 방지) 낱말만 보면 엉뚱한 축이 함께 걸린다.
        if "분석축: 엔캐리" in context:
            raise RuntimeError("engine down")
        return _ANSWER

    briefs = build_axis_briefs(_PLAN, _EVIDENCE, run_call=call)
    assert [row["status"] for row in briefs] == ["ok", "unavailable"]
    assert "실질금리" in render_axis_briefs(briefs)


def test_call_budget_stops_the_pass():
    briefs = build_axis_briefs(_PLAN, _EVIDENCE, run_call=lambda p, c: _ANSWER, max_calls=1)
    assert [row["status"] for row in briefs] == ["ok", "skipped_budget"]


_TEACHING_ANSWER = (
    '{"concept": ["실질금리는 물가를 뺀 진짜 이자다"], "mechanism": ["실질금리가 오르면 → 미래 이익의 현재가치가 낮아진다"],'
    ' "findings": ["실질금리가 상승분의 대부분"], "numbers": ["DFII10 = 2.35%"],'
    ' "counterEvidence": ["기대인플레이션은 하락"], "uncertainties": [], "sourceIds": ["ev_001"]}'
)


def test_brief_carries_concept_and_mechanism():
    """본문이 개념 → 원리 → 사례 → 답 순서로 쓰려면 브리프가 그 재료를 갖고 있어야 한다."""
    briefs = build_axis_briefs(_PLAN, _EVIDENCE, run_call=lambda p, c: _TEACHING_ANSWER)
    assert briefs[0]["concept"] and briefs[0]["mechanism"]
    rendered = render_axis_briefs(briefs)
    assert "개념:" in rendered and "작동 원리:" in rendered


def test_axis_prompt_asks_for_a_beginner_explanation():
    from features.topic_report.axis_analysis import _PROMPT

    assert "처음 보는 개인 투자자" in _PROMPT
    assert "concept" in _PROMPT and "mechanism" in _PROMPT
