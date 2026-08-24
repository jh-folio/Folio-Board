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


def test_deep_plan_rejects_more_than_six_in_one_round() -> None:
    with pytest.raises(ValidationError, match="too_many_round_1_questions"):
        DeepResearchPlan.model_validate(
            {
                "enabled": True,
                "maxRounds": 2,
                "subQuestions": [_question(i, 1) for i in range(1, 8)],
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
