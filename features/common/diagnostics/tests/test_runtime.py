from __future__ import annotations

from contextlib import redirect_stderr
from dataclasses import replace
import io
from types import SimpleNamespace

import pytest


def test_briefing_finalization_failure_is_typed_without_private_payload():
    from features.daily_briefing.finalize import BriefingFinalizationError
    error = BriefingFinalizationError("PRIVATE", candidate={"markdown": "PRIVATE"})
    failure = safe_exception_failure(error, boundary="generic")
    assert failure.reason_code == "validation"
    assert "PRIVATE" not in str(failure.to_dict())


def test_deepest_allowed_briefing_location_is_retained():
    from features.common.diagnostics.runtime import _trusted_frame
    from features.common.quality_generation.call_budget import SharedRepairBudget
    try:
        SharedRepairBudget(deadline=0).remaining_seconds()
    except TimeoutError as error:
        frames = _trusted_frame(error)
    assert len(frames) == 1
    assert frames[0].function_code == "check_active"

from features.common.diagnostics.projection import project_record
from features.common.diagnostics.runtime import DiagnosticsRuntime
from features.common.diagnostics.schema import DiagnosticValidationError, new_context, safe_exception_failure
from features.common.diagnostics.support import bind_request_id, current_request_id


def test_runtime_injects_verified_app_version_into_job_context(tmp_path) -> None:
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    job = SimpleNamespace(
        id="job_" + new_context(
            feature_code="jobs", route_code="shared_worker", authority_kind="direct",
        ).run_id[4:],
        taskType=SimpleNamespace(value="index"),
    )
    assert runtime.context_for_job(job, request_id="req_00000000-0000-4000-8000-000000000000").app_version == "0.5.4"
    runtime.close()


def test_request_id_binding_resets_after_request_boundary() -> None:
    request_id = "req_00000000-0000-4000-8000-000000000000"
    assert current_request_id() is None
    with bind_request_id(request_id):
        assert current_request_id() == request_id
    assert current_request_id() is None


def test_observe_recovery_retries_the_final_pending_cold_scan_slice(monkeypatch, tmp_path) -> None:
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    job = SimpleNamespace(
        id="job_" + new_context(
            feature_code="jobs", route_code="shared_worker", authority_kind="direct",
        ).run_id[4:],
        taskType=SimpleNamespace(value="index"),
        status=SimpleNamespace(value="failed_restart"),
    )
    resumed: list[tuple[str, str]] = []
    monkeypatch.setattr(runtime.store, "reconcile_step", lambda: "complete")
    monkeypatch.setattr(
        runtime.store,
        "resume",
        lambda item, *, observed_status: resumed.append((item.run_id, observed_status)),
    )

    runtime.observe_recovery(job)

    assert resumed == [
        ("run_" + job.id[4:], "failed_restart"),
        ("run_" + job.id[4:], "failed_restart"),
    ]
    assert runtime._pending_recoveries == {}
    runtime.close()


def test_background_reconcile_never_emits_a_private_exception(monkeypatch, tmp_path) -> None:
    canary = "SYNTHETIC_PRIVATE_DIAGNOSTICS_CANARY"
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    recorder = runtime.store.start(
        new_context(feature_code="http", route_code="http_unhandled", authority_kind="direct"),
    )
    assert recorder is not None and recorder.finish("failed")

    def broken() -> str:
        raise OSError(canary)

    monkeypatch.setattr(runtime.store, "reconcile_step", broken)
    captured = io.StringIO()
    with redirect_stderr(captured):
        runtime.schedule_reconcile()
        thread = runtime._reconcile_thread
        if thread is not None:
            thread.join(timeout=5)
    assert canary not in captured.getvalue()
    assert "Traceback" not in captured.getvalue()
    runtime.close()


def test_unhandled_http_reuses_the_concrete_failed_direct_run(tmp_path) -> None:
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    request_id = "req_00000000-0000-4000-8000-000000000000"
    context = new_context(
        feature_code="company_analysis",
        route_code="report_api",
        authority_kind="direct",
        request_id=request_id,
        app_version="0.5.4",
    )
    recorder = runtime.start_direct(context)
    assert recorder is not None
    recorder.failure(safe_exception_failure(RuntimeError(), boundary="generic"), terminal=True)
    runtime.finish_direct(recorder, "failed")

    before = list((tmp_path / "diagnostics" / "runs").glob("*.json"))
    assert runtime.observe_unhandled_http(request_id, RuntimeError("PRIVATE_HTTP_CANARY")) == context.run_id
    after = list((tmp_path / "diagnostics" / "runs").glob("*.json"))

    assert after == before
    assert "PRIVATE_HTTP_CANARY" not in before[0].read_text(encoding="utf-8")
    runtime.close()


def test_execution_facts_keep_the_primary_producer_observation(tmp_path) -> None:
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    recorder = runtime.start_direct(
        new_context(feature_code="company_analysis", route_code="report_api", authority_kind="direct")
    )
    assert recorder is not None
    assert recorder.observe_execution(attempted_engine="api", final_engine="api", adapter="openai_api")
    assert recorder.observe_execution(attempted_engine="cli", final_engine="rules", adapter="codex")
    assert recorder.record.attempted_engine == "api"
    assert recorder.record.final_engine == "api"
    assert recorder.record.adapter == "openai_api"
    runtime.close()


def _audited_index_context() -> object:
    seed = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct")
    return new_context(
        feature_code="index",
        route_code="index_build",
        authority_kind="shared_job",
        task_type="index",
        job_id="job_" + seed.run_id[4:],
        app_version="0.5.4",
    )


def test_audited_index_can_be_complete_only_after_closed_authority_terminal(tmp_path) -> None:
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    recorder = runtime.store.start(_audited_index_context())
    assert recorder is not None
    stage_id = recorder.start_stage("commit")
    assert stage_id is not None and recorder.end_stage(stage_id, "commit")
    assert recorder.prove_complete_coverage()

    runtime.observe_terminal(recorder, "done")

    assert recorder.record.required_producer_coverage == "complete"
    persisted = runtime.store.read(recorder.context.run_id).record
    assert persisted is not None and persisted.required_producer_coverage == "complete"
    assert project_record(recorder.record, authority_status="done", authority_available=True)["diagnosticQuality"] == "complete"
    assert project_record(recorder.record, authority_status="failed", authority_available=True)["diagnosticQuality"] == "partial"
    runtime.close()


def test_complete_coverage_rejects_loss_and_recovery_gap(tmp_path) -> None:
    runtime = DiagnosticsRuntime(tmp_path, app_version="0.5.4")
    recorder = runtime.store.start(_audited_index_context())
    assert recorder is not None
    stage_id = recorder.start_stage("commit")
    assert stage_id is not None and recorder.end_stage(stage_id, "commit")
    assert recorder.prove_complete_coverage()
    recorder.recover("done")

    assert recorder.record.required_producer_coverage == "partial"
    assert "recovery_gap" in recorder.record.issue_codes
    assert recorder.promote_complete() is False
    with pytest.raises(DiagnosticValidationError):
        replace(recorder.record, required_producer_coverage="complete")
    runtime.close()
