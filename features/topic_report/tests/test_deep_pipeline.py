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
