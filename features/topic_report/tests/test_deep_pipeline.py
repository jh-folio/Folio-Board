from __future__ import annotations

from datetime import UTC, datetime

import pytest

from features.agent_mode.market_state_context import MarketStateProjection
from features.common.quality_generation.candidate_store import CandidateStore
from features.topic_report.approved_generation import (
    ApprovedGenerationInput,
    ApprovedGenerationOutcome,
)
from features.topic_report.approved_research import PreparedResearch
from features.topic_report.approved_schema import ApprovedRequest
from features.topic_report.deep_pipeline import DeepResearchGenerationError, run_deep_pipeline
from features.topic_report.depth_policy import build_depth_policy
from features.topic_report.resolution_schema import ProviderGenerations, ResearchPreview, ResolutionSnapshotV1, ZeroEvidence
from features.topic_report.topic_schema import EXPECTED_SECTIONS_V2


JOB_ID = "job_12345678-1234-4234-9234-1234567890ab"


def _markdown(thin: str | None = None) -> str:
    rows = ["# Deep"]
    for heading in EXPECTED_SECTIONS_V2:
        body = "확인된 근거와 조건을 연결한 상세 분석 문장입니다. " * (2 if heading == thin else 30)
        rows += [f"## {heading}", body, "<!-- folio-source-ids: ev_001 -->"]
    return "\n\n".join(rows)


def _approved_request() -> ApprovedRequest:
    # Reuse the typed boundary through a minimal frozen payload assembled by existing test helpers.
    from features.topic_report.tests.test_approved_generation import approved_request
    from pathlib import Path
    import tempfile

    return approved_request(Path(tempfile.mkdtemp()))


def _command() -> ApprovedGenerationInput:
    approved = _approved_request()
    resolution = ResolutionSnapshotV1(
        schemaVersion=1, collectionId=None, collectionRevision=None, collectionDefinitionHash=None,
        eligibleTotal=None, candidateCap=None, truncated=False, resolvedCandidateIds=[],
        executionUniverseIds=[], unusableCandidates=[], selectedEvidenceIds=[],
        providerGenerations=ProviderGenerations(indexGeneration=None, rssGeneration=None), inputWatermark=None,
    )
    preview = ResearchPreview(
        resolution=resolution, resolvedAt="2026-08-24T00:00:00Z",
        zeroEvidence=ZeroEvidence(required=False, reasonCode=None, resolutionFingerprint=None),
    )
    return ApprovedGenerationInput(
        approved=approved, approvalId="approval", requestedMode="direct", adapter="auto", preview=preview,
        research=PreparedResearch(resolution=resolution, evidencePack={"items": []}),
        marketState=MarketStateProjection(resolution={}, context={}),
    )


def _outcome(markdown: str, *, final_engine: str = "api") -> ApprovedGenerationOutcome:
    policy = build_depth_policy(
        deep_research=True, analysis_axis_count=4, subquestion_count=8, evidence_count=20, report_type="macro_analysis"
    )
    report = {
        "id": "report-a", "date": "2026-08-24", "topicKey": "custom", "topicLabel": "Deep",
        "markdown": markdown, "depthPolicy": policy, "materialResolution": {"market": [], "macro": []},
        "sourceLedger": [{"sourceId": "ev_001", "usedInSections": [], "evidenceRole": "challenging", "date": "2026-08-23"}],
        "evidencePackSummary": {"deepResearch": {"enabled": True}, "totalDocs": 1, "roleCounts": {"challenging": 1}},
        "evidenceItems": [], "dataGaps": [], "checkpoints": [], "marketTape": {}, "quality": {"score": 80},
        "executionProvenance": {"schemaVersion": 2}, "userContext": False,
    }
    return ApprovedGenerationOutcome(report, final_engine, final_engine, None, "test", "llm_api", "generate")


def test_deep_rules_fallback_is_not_saved_as_candidate(tmp_path) -> None:
    with pytest.raises(DeepResearchGenerationError, match="without_candidate"):
        run_deep_pipeline(
            _outcome(_markdown(), final_engine="rules"), _command(), job_id=JOB_ID, report_id="report-a",
            candidate_store=CandidateStore(tmp_path / "job-context"), repair_call=lambda *_: "",
        )


def test_malformed_repair_keeps_last_validated_initial_candidate(tmp_path) -> None:
    store = CandidateStore(tmp_path / "job-context")
    result = run_deep_pipeline(
        _outcome(_markdown(thin="현재 상황")), _command(), job_id=JOB_ID, report_id="report-a",
        candidate_store=store, repair_call=lambda *_: "not json",
    )
    assert result.report["executionProvenance"]["selectedCandidateIndex"] == 0
    assert result.report["markdown"] == _markdown(thin="현재 상황")
    assert store.latest_accepted(JOB_ID).candidateIndex == 0


def test_valid_section_repair_can_be_selected_without_touching_other_sections(tmp_path) -> None:
    def repair(_pass, _context):
        return '{"patches":[{"heading":"현재 상황","replacementBody":"' + ("확인된 근거와 조건을 연결한 보강 분석입니다. " * 32) + '","sourceIds":["ev_001"]}]}'

    result = run_deep_pipeline(
        _outcome(_markdown(thin="현재 상황")), _command(), job_id=JOB_ID, report_id="report-a",
        candidate_store=CandidateStore(tmp_path / "job-context"), repair_call=repair,
    )
    assert result.report["executionProvenance"]["selectedCandidateIndex"] == 1
    assert "보강 분석" in result.report["markdown"]
    assert "## 작동 경로" in result.report["markdown"]


# ------------------------------------------------- 계약 결함이 점수를 누른다

def test_contract_defects_cap_the_quality_score():
    # 실측: 결함 14건인 보고서가 93점/A/pass를 받았다. 계약은 제대로 잡았는데
    # 점수가 그것을 읽지 않아 사용자에게는 A로 보였다.
    from features.topic_report.deep_pipeline import apply_contract_ceiling

    quality = {"score": 93, "grade": "A", "status": "pass"}
    validation = {"defects": [
        {"code": "low_source_linkage", "severity": 70},
        {"code": "below_recommended_length", "severity": 45},
        {"code": "body_sections_differ", "severity": 45},
        {"code": "unlinked_section", "severity": 35},
    ]}
    out = apply_contract_ceiling(quality, validation)
    assert out["score"] == 69 and out["status"] != "pass"
    assert out["contractCeiling"]["applied"] is True
    assert any("low_source_linkage" in reason for reason in out["contractCeiling"]["reasons"])
    assert any("계약 결함" in warning for warning in out["warnings"])


def test_three_major_defects_block_an_a_grade():
    from features.topic_report.deep_pipeline import apply_contract_ceiling

    validation = {"defects": [{"code": f"c{n}", "severity": 45} for n in range(3)]}
    assert apply_contract_ceiling({"score": 95, "grade": "A"}, validation)["score"] == 79


def test_a_clean_report_keeps_its_score():
    from features.topic_report.deep_pipeline import apply_contract_ceiling

    assert apply_contract_ceiling({"score": 92}, {"defects": []})["score"] == 92
    # 경미한 결함 하나로 점수를 깎지 않는다.
    light = apply_contract_ceiling({"score": 92}, {"defects": [{"code": "unlinked_section", "severity": 35}]})
    assert light["score"] == 92 and light["contractCeiling"]["applied"] is False


def test_a_score_already_below_the_ceiling_is_left_alone():
    from features.topic_report.deep_pipeline import apply_contract_ceiling

    out = apply_contract_ceiling({"score": 40, "grade": "F"}, {"defects": [{"code": "x", "severity": 70}]})
    assert out["score"] == 40 and out["contractCeiling"]["applied"] is False
