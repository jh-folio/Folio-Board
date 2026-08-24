from __future__ import annotations

import pytest

from features.topic_report.candidate_pipeline import candidate_improves
from features.topic_report.depth_policy import build_depth_policy
from features.topic_report.report_contract import validate_deep_report
from features.topic_report.section_repair import merge_section_patches, parse_patch_response
from features.topic_report.topic_schema import EXPECTED_SECTIONS_V2


def _report(*, unknown_source: bool = False, repeated: bool = False) -> str:
    rows = ["# 심층 보고서"]
    for heading in EXPECTED_SECTIONS_V2:
        body = (f"{heading}에 대한 확인된 분석입니다. 조건과 근거를 연결해 설명합니다. " * 18).strip()
        if repeated and heading == "현재 상황":
            body = ("같은 문장을 장황하게 반복하여 보고서 분량을 채우는 잘못된 문장입니다. " * 3).strip()
        source_id = "ev_unknown" if unknown_source and heading == "현재 상황" else "ev_001"
        rows += [f"## {heading}", body, f"<!-- folio-source-ids: {source_id} -->"]
    return "\n\n".join(rows)


def _validation(markdown: str) -> dict:
    policy = build_depth_policy(
        deep_research=True, analysis_axis_count=4, subquestion_count=8, evidence_count=20, report_type="macro_analysis"
    )
    return validate_deep_report(
        markdown,
        source_ledger=[{"sourceId": "ev_001", "usedInSections": [], "evidenceRole": "challenging"}],
        depth_policy=policy,
        material_resolution={"market": [], "macro": []},
        internal_score=80,
    )


def test_unknown_source_is_blocking_even_if_report_is_long() -> None:
    result = _validation(_report(unknown_source=True))
    assert result["valid"] is False
    assert any(row["code"] == "unknown_source_tag" for row in result["defects"])


def test_candidate_comparator_never_accepts_new_boundary_violation() -> None:
    before = _validation(_report(repeated=True))
    after = _validation(_report(unknown_source=True))
    after["metrics"]["internalScore"] = 99
    assert candidate_improves(before, after) is False


def test_section_patch_changes_only_allowlisted_section_and_parses_local_json_wrapper() -> None:
    patches = parse_patch_response(
        'prefix {"patches":[{"heading":"현재 상황","replacementBody":"새 분석 본문","sourceIds":["ev_001"]}]} suffix'
    )
    updated = merge_section_patches(_report(), patches, allowed_sections={"현재 상황"})
    assert "새 분석 본문" in updated
    assert "## 작동 경로" in updated
    with pytest.raises(ValueError):
        merge_section_patches(
            _report(),
            [{"heading": "결론", "replacementBody": "허용 밖", "sourceIds": ["ev_001"]}],
            allowed_sections={"현재 상황"},
        )
