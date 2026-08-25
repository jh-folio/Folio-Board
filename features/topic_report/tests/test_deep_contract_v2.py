from __future__ import annotations

import pytest
from pydantic import ValidationError

# `approved_schema` defines the shared strict base before importing the plan schema.
# Preserve that established import order until the legacy compatibility cycle is removed.
import features.topic_report.approved_schema  # noqa: F401
from features.topic_report.approved_plan_schema import (
    FALSIFICATION_TRIGGERS,
    REQUIRED_OUTPUTS,
    DeepResearchPlan,
)
from features.topic_report.depth_policy import build_depth_policy, visible_character_count
from features.topic_report.research_trace import build_research_trace_summary
from features.topic_report.section_sources import apply_section_usage


def _question(index: int, round_no: int) -> dict:
    return {
        "id": f"dq_{index:02d}",
        "question": f"질문 {index}",
        "axisKey": "axis",
        "round": round_no,
        "searchQueries": [f"검색 {index}"],
    }


def test_deep_plan_accepts_six_questions_per_round() -> None:
    plan = DeepResearchPlan.model_validate(
        {
            "enabled": True,
            "maxRounds": 2,
            "subQuestions": [_question(i, 1 if i <= 6 else 2) for i in range(1, 13)],
            "falsificationTriggers": FALSIFICATION_TRIGGERS,
            "requiredOutputs": REQUIRED_OUTPUTS,
        }
    )
    assert len(plan.subQuestions) == 12


def test_deep_plan_rejects_more_than_ten_round_1_questions() -> None:
    # 라운드1은 "연구질문 + 분석축 전체"를 담아야 해서 상한이 10이다. 6이던 시절에는
    # 축이 5개일 때 첫 축만 질문을 받고 나머지 축은 검색조차 되지 않았다.
    with pytest.raises(ValidationError, match="too_many_round_1_questions"):
        DeepResearchPlan.model_validate(
            {
                "enabled": True,
                "maxRounds": 2,
                "subQuestions": [_question(i, 1) for i in range(1, 12)],
                "falsificationTriggers": FALSIFICATION_TRIGGERS,
                "requiredOutputs": REQUIRED_OUTPUTS,
            }
        )


def test_depth_policy_targets_deep_range_and_ignores_hidden_tags() -> None:
    policy = build_depth_policy(
        deep_research=True,
        analysis_axis_count=6,
        subquestion_count=12,
        evidence_count=28,
        report_type="macro_analysis",
    )
    assert 12_000 <= policy["targetChars"] <= 16_000
    assert policy["safetyMaxChars"] == 18_000
    assert visible_character_count("본문<!-- folio-source-ids: ev_001 -->") == 2


def test_section_sources_reject_unknown_and_project_known_usage() -> None:
    markdown = """## 현재 상황
본문
<!-- folio-source-ids: ev_001, ev_unknown -->
## 결론
결론
<!-- folio-source-ids: ev_001 -->
"""
    ledger, result = apply_section_usage(
        markdown,
        [{"sourceId": "ev_001", "title": "자료", "usedInSections": []}],
    )
    assert result["unknownSourceIds"] == ["ev_unknown"]
    assert ledger[0]["usedInSections"] == ["현재 상황", "결론"]


def test_research_trace_counts_only_sources_used_in_body() -> None:
    summary = build_research_trace_summary(
        [
            {"sourceId": "ev_001", "date": "2026-08-21", "evidenceRole": "challenging", "usedInSections": ["반론과 리스크"]},
            {"sourceId": "ev_002", "date": "2026-08-23", "evidenceRole": "supporting", "usedInSections": []},
        ],
        [{"message": "공식 거시 데이터가 없습니다."}],
    )
    assert summary == {
        "schemaVersion": 1,
        "usedSourceCount": 1,
        "latestSourceDate": "2026-08-21",
        "challengingSourceCount": 1,
        "unresolvedDataGapCount": 1,
        "cautionReasons": ["공식 거시 데이터가 없습니다."],
    }


def test_numbered_headings_still_link_sources():
    """실제 보고서는 `## 1. Executive Summary`처럼 번호를 붙인다 — usage 키를 원문으로
    두면 정규화 이름 조회가 한 번도 맞지 않아 연결이 항상 0이었다."""
    from features.topic_report.section_sources import parse_section_source_ids

    usage, malformed = parse_section_source_ids(
        "## 1. Executive Summary\n본문 <!-- folio-source-ids: ev_001 -->\n"
    )
    assert usage.get("Executive Summary") == ["ev_001"]
    assert malformed == []


def test_unknown_tag_is_warning_not_blocking():
    """모르는 id는 usage에서 이미 제외된다 — 차단으로 두면 id 하나 잘못 베낀 것으로
    다 만든 보고서가 통째로 버려진다. 자기참조(forbidden)만 차단이다."""
    from features.topic_report.report_contract import validate_deep_report

    result = validate_deep_report(
        "## 1. Executive Summary\n본문 <!-- folio-source-ids: ev_nope -->\n",
        source_ledger=[{"sourceId": "ev_001"}],
        depth_policy={},
        material_resolution={},
        internal_score=80,
    )
    codes = {(d["code"], d["category"]) for d in result["defects"]}
    assert ("unknown_source_tag", "major") in codes
    assert not any(code == "unknown_source_tag" and cat == "blocking" for code, cat in codes)


def test_material_source_ids_are_tag_safe():
    """^KS11 같은 티커가 sourceId에 그대로 들어가면 모델이 계약대로 인용하는 순간
    malformed가 된다 — id 문자로 정규화한다."""
    import re
    from features.topic_report.material_requirements import material_source_items
    from features.topic_report.section_sources import _SOURCE_ID

    items = material_source_items(
        {"market": [{"symbol": "^KS11", "status": "available"}], "macro": []},
        {"tickers": {"^KS11": {"symbol": "^KS11", "close": 1.0}}},
        {},
    )
    for row in items:
        if row.get("sourceId"):
            assert _SOURCE_ID.fullmatch(row["sourceId"]), row["sourceId"]
