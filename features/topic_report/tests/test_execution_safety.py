from concurrent.futures import CancelledError
from dataclasses import replace
import json

import pytest

from features.common.execution_result import ExecutionResult
from features.common.provider_result import ProviderPayload, Citation
from features.common.quality_generation.candidate_store import CandidateStore
from features.topic_report import approved_generation_support as support
from features.topic_report import execution, resume_store
from features.topic_report.deep_pipeline import DeepResearchGenerationError, run_deep_pipeline
from features.topic_report.editor import edit_report
from features.topic_report.tests.test_deep_pipeline import _command, _markdown, _outcome, JOB_ID
from features.topic_report.tests.test_candidate_recovery import _running, _report, NOW
from features.topic_report.candidate_recovery import recover_deep_candidates_startup


@pytest.mark.parametrize("status", ["incomplete", "failed"])
def test_complete_looking_partial_is_never_accepted(tmp_path, status):
    outcome = _outcome(_markdown(), final_engine="cli")
    outcome.report["executionFacts"] = ExecutionResult(completion_status=status).safe_projection()
    store = CandidateStore(tmp_path / "job-context")
    with pytest.raises(DeepResearchGenerationError) as caught:
        run_deep_pipeline(outcome, _command(), job_id=JOB_ID, report_id="report-a", candidate_store=store)
    assert "provider_incomplete" in caught.value.defects
    assert store.latest_accepted(JOB_ID) is None
    assert store.read(JOB_ID, 0).report["markdown"] == outcome.report["markdown"]


def test_startup_does_not_promote_old_accepted_flag_on_partial(tmp_path):
    store, lifecycle, job = _running(tmp_path)
    report = _report("report-a")
    report["executionFacts"] = {"completionStatus": "incomplete"}
    CandidateStore(tmp_path / "job-context").write(job.id, 0, report_id="report-a", accepted=True,
        validation={"valid": True}, provenance={}, report=report)
    assert recover_deep_candidates_startup(tmp_path, store, lifecycle, clock=lambda: NOW) == []
    assert not list((tmp_path / "topic-reports").glob("*.json"))


@pytest.mark.parametrize("error", [CancelledError("cancelled"), TimeoutError("deadline"), RuntimeError("cancelled")])
def test_optional_editor_never_hides_interruption(error):
    def call(*args):
        raise error
    with pytest.raises((CancelledError, TimeoutError)):
        edit_report(_markdown(), run_call=call)


def test_cancel_during_repair_prevents_next_call_and_result(tmp_path, monkeypatch):
    status = ["running"]
    monkeypatch.setattr(execution, "get_job", lambda _: {"status": status[0]})
    calls = []
    def repair(*args):
        calls.append(1)
        status[0] = "cancel_requested"
        return "{}"
    with pytest.raises(CancelledError):
        run_deep_pipeline(_outcome(_markdown(thin="현재 상황")), _command(), job_id=JOB_ID,
                          report_id="report-a", candidate_store=CandidateStore(tmp_path), repair_call=repair)
    assert len(calls) == 1


@pytest.mark.parametrize("factory", ["configured_axis_call", "configured_editor_call"])
def test_auxiliary_calls_reject_partial_even_with_valid_text(monkeypatch, factory):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(execution, "get_job", lambda _: None)
    def prompt(*a, **kwargs):
        assert kwargs["model"] == "frozen-model" and kwargs["reasoning_effort"] == "high"
        kwargs["result_sink"]["result"] = ExecutionResult(text='{"findings":["valid"]}', completion_status="incomplete")
        return {"output": '{"findings":["valid"]}'}
    monkeypatch.setattr(support.agent_bridge, "run_agent_prompt", prompt)
    call = getattr(support, factory)(_command().approved, requested_mode="cli", adapter="claude", job_id=JOB_ID,
                                     model="frozen-model", reasoning_effort="high")
    with pytest.raises(execution.IncompleteExecutionError):
        call("prompt", "context")


def test_writer_keeps_e0_private_and_partial_body(monkeypatch, tmp_path):
    monkeypatch.setattr(support.agent_schema, "write_pack", lambda *a, **k: tmp_path / "pack.json")
    def prompt(*a, **k):
        k["result_sink"]["result"] = ExecutionResult(text="partial", completion_status="incomplete",
            provider=ProviderPayload(adapter="claude", session_id="PRIVATE_SESSION"))
        return {"output": "partial", "adapter": "claude"}
    monkeypatch.setattr(support.agent_bridge, "run_agent_prompt", prompt)
    output = support.attempt_cli("prompt", "context", adapter="claude", job_id=JOB_ID,
                                 approved=_command().approved, evidence_items=[])
    assert output.markdown == "partial" and output.execution.completion_status == "incomplete"
    assert "PRIVATE_SESSION" not in repr(output)


def test_writer_uses_frozen_web_setting_without_rereading_globals(monkeypatch, tmp_path):
    monkeypatch.setattr(support.agent_schema, "write_pack", lambda *a, **k: tmp_path / "pack.json")
    monkeypatch.setattr(support, "use_web_search_for_analysis", lambda: pytest.fail("must use frozen policy"))
    def prompt(*a, **k):
        assert k["web_search"] is False
        return {"output": "body"}
    monkeypatch.setattr(support.agent_bridge, "run_agent_prompt", prompt)
    assert support.attempt_cli("prompt", "context", adapter="claude", job_id=JOB_ID,
        approved=_command().approved, evidence_items=[], web_search=False).markdown == "body"


def test_canonical_guard_preserves_existing_topic(tmp_path):
    from features.common.canonical_reports import prepare
    from features.common.canonical_report_types import CanonicalValidationError, WriteKind
    from features.common.canonical_identity import ReportKind
    report = _report("report-a")
    path = tmp_path / "2026-08-24_report-a.json"
    # Use the canonical API so no feature write path can bypass the guard.
    path.write_text(json.dumps(report), encoding="utf-8")
    before = path.read_bytes()
    report["executionFacts"] = {"completionStatus": "incomplete"}
    with pytest.raises(CanonicalValidationError, match="완료"):
        prepare(report_kind=ReportKind.TOPIC_REPORT, write_kind=WriteKind.CANONICAL, exact_path=path, candidate=report, operation_id="partial")
    assert path.read_bytes() == before


def test_resume_content_and_web_policy_changes_invalidate_same_ids():
    common = dict(plan_hash="plan", as_of_date="2026-09-22", selected_evidence_ids=["same"],
                  adapter="claude", requested_mode="cli")
    a = resume_store.fingerprint(**common, input_snapshot={"evidence": "before", "web": False})
    b = resume_store.fingerprint(**common, input_snapshot={"evidence": "after", "web": False})
    c = resume_store.fingerprint(**common, input_snapshot={"evidence": "before", "web": True})
    assert len({a, b, c}) == 3


def test_failed_lookup_and_unsafe_or_corrupt_resume_do_not_get_reused(tmp_path):
    store = resume_store.ResumeStore(tmp_path, key="safe", fingerprint="fp")
    store.put_web_lookup({"axisKey": "x", "status": "unavailable"})
    assert store.web_lookups() == []
    (tmp_path / "safe.json").write_text('{"schemaVersion": "broken"}', encoding="utf-8")
    assert resume_store.ResumeStore(tmp_path, key="safe", fingerprint="fp").load() == {}
    invalid = resume_store.ResumeStore(tmp_path, key="../outside", fingerprint="fp")
    invalid.put_thesis({"claim": "never written"})
    assert not invalid.enabled and not (tmp_path.parent / "outside.json").exists()


def test_generation_does_not_edit_or_retry_observed_partial_and_keeps_private_citations(tmp_path, monkeypatch):
    from features.topic_report import approved_generation as generation
    from features.topic_report.tests.test_approved_generation import prepared_input, fake_materials, _deep_markdown
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "resume_root", lambda: tmp_path / "resume")
    monkeypatch.setattr(generation, "_read_prompt", lambda: "prompt")
    body = _deep_markdown()
    result = ExecutionResult(text=body, completion_status="incomplete", provider=ProviderPayload(
        adapter="claude", session_id="PRIVATE_SESSION", citations=(Citation(0, 0, 3, source_id="PRIVATE_SOURCE"),)))
    calls = []
    def writer(*a, **k):
        calls.append(1)
        return support.EngineOutput(body, "claude", "external_agent", "", "", result)
    monkeypatch.setattr(generation, "attempt_cli", writer)
    monkeypatch.setattr(generation, "edit_report", lambda *a, **k: pytest.fail("partial draft must not be edited"))
    outcome = generation.build_approved_report(prepared_input(tmp_path, "cli"), job_id=JOB_ID, clock=lambda: NOW)
    assert len(calls) == 1 and outcome.report["executionFacts"]["completionStatus"] == "incomplete"
    assert outcome.execution.provider.citations[0].source_id == "PRIVATE_SOURCE"
    assert "PRIVATE" not in json.dumps(outcome.report)


def test_real_generation_changes_resume_fingerprint_when_same_document_changes(tmp_path, monkeypatch):
    from features.topic_report import approved_generation as generation
    from features.topic_report.tests.test_approved_generation import prepared_input, fake_materials
    from features.topic_report.approved_research import PreparedResearch
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "resume_root", lambda: tmp_path / "resume")
    monkeypatch.setattr(generation, "_read_prompt", lambda: "prompt")
    monkeypatch.setattr(generation, "attempt_cli", lambda *a, **k: (_ for _ in ()).throw(support.EngineFailedError("cli")))
    fingerprints = []
    original = generation.resume_fingerprint
    def record(**kwargs):
        value = original(**kwargs)
        fingerprints.append(value)
        return value
    monkeypatch.setattr(generation, "resume_fingerprint", record)
    command = prepared_input(tmp_path, "cli")
    generation.build_approved_report(command, job_id=JOB_ID, clock=lambda: NOW)
    pack = dict(command.research.evidencePack)
    pack["items"] = [{**row, "snippet": "The same document now contains different evidence."} for row in command.research.evidence_items]
    changed = replace(command, research=PreparedResearch(command.research.resolution, pack))
    generation.build_approved_report(changed, job_id=JOB_ID, clock=lambda: NOW)
    assert fingerprints[0] != fingerprints[1]


def test_resume_ignores_fetch_clock_but_keeps_prices_and_observation_dates(tmp_path, monkeypatch):
    from features.topic_report import approved_generation as generation
    from features.topic_report.tests.test_approved_generation import prepared_input, fake_materials

    market = {"asOf": "2026-07-16T10:00:00+09:00",
              "tickers": {"TEST": {"price": 100, "asOf": "2026-07-15"}}}
    monkeypatch.setattr(generation, "_materials",
                        lambda approved, rows: (fake_materials(approved, rows)[0], market, {"ok": False}))
    monkeypatch.setattr(generation, "resume_root", lambda: tmp_path / "resume")
    monkeypatch.setattr(generation, "_read_prompt", lambda: "prompt")
    monkeypatch.setattr(generation, "attempt_cli",
                        lambda *a, **k: (_ for _ in ()).throw(support.EngineFailedError("cli")))
    fingerprints = []
    original = generation.resume_fingerprint

    def record(**kwargs):
        value = original(**kwargs)
        fingerprints.append(value)
        return value

    monkeypatch.setattr(generation, "resume_fingerprint", record)
    command = prepared_input(tmp_path, "cli")
    generation.build_approved_report(command, job_id=JOB_ID, clock=lambda: NOW)
    market["asOf"] = "2026-07-16T10:05:00+09:00"
    generation.build_approved_report(command, job_id=JOB_ID, clock=lambda: NOW)
    market["tickers"]["TEST"]["price"] = 101
    generation.build_approved_report(command, job_id=JOB_ID, clock=lambda: NOW)
    market["tickers"]["TEST"]["asOf"] = "2026-07-16"
    generation.build_approved_report(command, job_id=JOB_ID, clock=lambda: NOW)
    assert fingerprints[0] == fingerprints[1]
    assert fingerprints[1] != fingerprints[2]
    assert fingerprints[2] != fingerprints[3]
