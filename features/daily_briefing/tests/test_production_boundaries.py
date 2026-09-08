from __future__ import annotations

import inspect
import json

import pytest

from features.agent_mode import service as agent_service
from features.common.quality_generation import loop as quality_loop
from features.common.quality_generation.call_budget import SharedRepairBudget
from features.daily_briefing import builder, finalize
from features.daily_briefing import local_fact_repair, style_check
from features.daily_briefing.concentration import runtime as concentration_runtime
from features.daily_briefing.finalize import BriefingFinalizationError, finalize_briefing_candidate


def _candidate(markdown: str = "# Brief\n\nContradictory but format-valid prose.") -> dict:
    return {
        "marketScope": "us",
        "markdown": markdown,
        "sources": [],
        "generationEvidence": {"status": "declared"},
        "claimLedger": {"claims": []},
    }


def _fail(name):
    def fail(*_args, **_kwargs):
        raise AssertionError(f"production path called {name}")

    return fail


def test_production_finalizer_preserves_body_without_semantic_style_repair_or_model_calls(monkeypatch):
    monkeypatch.setattr(finalize, "_evaluate", _fail("semantic evaluator"))
    monkeypatch.setattr(finalize, "_semantic_source_check", _fail("semantic source checker"))
    monkeypatch.setattr(finalize, "_repair_markdown", _fail("fact repair"))
    monkeypatch.setattr(style_check, "briefing_style_check", _fail("style checker"))
    monkeypatch.setattr(local_fact_repair, "correct_verified_passages", _fail("local repair"))
    monkeypatch.setattr(quality_loop, "improve_sections_with_llm", _fail("quality model"))

    candidate = _candidate("# US Briefing\n\nNVDA는 -1.48% 하락했다.")
    result = finalize_briefing_candidate(candidate, allow_repair=True)

    assert result["markdown"] == candidate["markdown"]
    assert result["finalValidation"]["assessmentStatus"] == "not_assessed"
    assert result["finalValidation"]["contentAssessment"] == "not_assessed"
    assert result["finalValidation"]["contradictionCount"] is None
    assert result["finalValidation"]["verifiedClaimCount"] is None
    assert result["validationRun"]["contentAssessment"] == "not_assessed"
    assert result["validationRun"]["semanticStatus"] == "not_assessed"
    assert result["finalValidation"]["repairApplied"] is False


def test_briefing_quality_loop_replaces_stale_content_metadata_without_touching_body(monkeypatch):
    monkeypatch.setattr(quality_loop, "evaluate_artifact", _fail("quality evaluator"))
    monkeypatch.setattr(quality_loop, "detect_weak_sections", _fail("weak-section evaluator"))
    monkeypatch.setattr(quality_loop, "should_llm_rewrite", _fail("repair policy"))
    monkeypatch.setattr(quality_loop, "improve_sections_with_llm", _fail("quality model"))

    candidate = _candidate()
    candidate["quality"] = {"status": "pass", "score": 99, "verifiedClaims": ["stale"]}
    candidate["qualityGeneration"] = {"contentAssessment": "pass", "repairApplied": True}
    result = quality_loop.apply_quality_loop("briefing", candidate, mode="strict")

    assert result["markdown"] == candidate["markdown"]
    assert result["quality"]["status"] == "not_assessed"
    assert result["quality"]["assessmentStatus"] == "not_assessed"
    assert result["quality"]["contentAssessment"] == "not_assessed"
    assert result["quality"]["verifiedClaimCount"] is None
    assert result["quality"]["contradictionCount"] is None
    assert result["qualityGeneration"]["contentAssessment"] == "not_assessed"
    assert result["qualityGeneration"]["repairApplied"] is False


def test_briefing_read_paths_do_not_lazily_assess_content(monkeypatch, tmp_path):
    from features.daily_briefing import service as briefing_service

    report = {"date": "2099-01-05", "marketScope": "us", "markdown": "# Authored"}
    (tmp_path / "2099-01-05.us.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    monkeypatch.setattr(briefing_service, "BRIEFINGS_DIR", tmp_path)
    monkeypatch.setattr(
        "features.common.research_quality.evaluator.evaluate_artifact",
        _fail("read-path semantic evaluator"),
    )

    listed = briefing_service.list_briefings()

    assert listed == [report]
    assert "quality" not in listed[0]


def test_production_paths_have_no_style_evaluator_call():
    assert "briefing_style_check(" not in inspect.getsource(builder)
    assert "briefing_style_check(" not in inspect.getsource(agent_service)


def test_production_concentration_finalizer_does_not_audit_or_repair(monkeypatch):
    monkeypatch.setattr(concentration_runtime, "audit_concentration", _fail("concentration audit"))
    monkeypatch.setattr(concentration_runtime, "configured_repair", _fail("concentration repair"))
    control = {"mode": "active", "signatures": [{"candidateId": "c1", "subject": "NVDA"}],
               "leaderDecision": {"finalPair": ["c1"]}}

    markdown, result = concentration_runtime.finalize_concentration("authored body", control)

    assert markdown == "authored body"
    assert result["audit"]["assessmentStatus"] == "not_assessed"
    assert result["audit"]["repair"]["applied"] is False


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("supportingSourceIds", ["missing-source"], "source_outside_whitelist"),
        ("section", "not-a-final-heading", "section_outside_whitelist"),
    ],
)
def test_production_source_whitelist_boundaries_remain_enforced(field, value, reason):
    candidate = _candidate("# Brief\n\nBody")
    candidate["sources"] = [{"sourceId": "src-1", "url": "https://example.com/a"}]
    candidate["claimLedger"] = {"claims": [{"claim": "declared", field: value}]}

    with pytest.raises(BriefingFinalizationError) as raised:
        finalize_briefing_candidate(candidate)

    assert reason in raised.value.validation["reasonCodes"]


def test_production_visible_link_must_be_in_source_whitelist():
    candidate = _candidate("# Brief\n\n[unlisted](https://example.com/not-listed)")
    with pytest.raises(BriefingFinalizationError) as raised:
        finalize_briefing_candidate(candidate)
    assert "visible_link_outside_whitelist" in raised.value.validation["reasonCodes"]


def test_format_invalid_and_cancelled_candidates_do_not_commit():
    with pytest.raises(BriefingFinalizationError) as empty:
        finalize_briefing_candidate(_candidate(""))
    assert "format_empty" in empty.value.validation["reasonCodes"]

    with pytest.raises(BriefingFinalizationError) as cancelled:
        finalize_briefing_candidate(
            _candidate(), repair_budget=SharedRepairBudget(cancelled=lambda: True)
        )
    assert "cancelled" in cancelled.value.validation["reasonCodes"]
