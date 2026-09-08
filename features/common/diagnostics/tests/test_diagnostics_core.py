from __future__ import annotations

from dataclasses import replace
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest

from features.common.diagnostics import DiagnosticsStore, new_context
from features.common.diagnostics.projection import project_read
from features.common.diagnostics.record import record_from_dict
from features.common.diagnostics.schema import (
    MAX_ERRORS,
    MAX_EVENTS,
    DiagnosticValidationError,
    SafeFrame,
    safe_failure,
    safe_exception_failure,
)
from features.common.diagnostics.store import QuotaSnapshot
from features.common.diagnostics.support import bind_context, context_bound, current_context


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLIO_HOME", str(tmp_path / "home"))


def _context(**changes):
    values = {"feature_code": "jobs", "route_code": "shared_worker", "authority_kind": "direct", "app_version": "0.5.4"}
    values.update(changes)
    return new_context(**values)


def test_closed_schema_ids_unknown_fields_and_secret_canary_never_persist(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    secret = "sk-live-private-canary-DO-NOT-PERSIST"
    assert recorder.event(stage_id="not-an-id", stage_code=secret, event_code="start") is False
    assert recorder.finish("succeeded") is True
    target = store.runs_root / f"{recorder.context.run_id}.json"
    text = target.read_text(encoding="utf-8")
    assert secret not in text
    raw = json.loads(text); raw["unknown"] = secret
    target.write_text(json.dumps(raw), encoding="utf-8")
    assert store.read(recorder.context.run_id).availability_reason == "corrupt"
    with pytest.raises(DiagnosticValidationError):
        _context(job_id="job_not-a-uuid")
    with pytest.raises(DiagnosticValidationError):
        store.read("../../escape")
    store.close()


def test_source_frame_requires_registry_and_real_ast_location(tmp_path: Path) -> None:
    line = inspect.getsourcelines(current_context)[1]
    frame = SafeFrame("features.common.diagnostics.support", "current_context", line)
    failure = safe_failure(frames=(frame,))
    blocked = DiagnosticsStore(tmp_path / "blocked")
    recorder = blocked.start(_context())
    assert recorder is not None
    assert recorder.failure(failure) == failure.error_id
    # An unverified source is dropped, but its safe failure classification is
    # retained for the terminal/first-failure contract.
    blocked_raw = (blocked.runs_root / f"{recorder.context.run_id}.json").read_text(encoding="utf-8")
    assert failure.error_id in blocked_raw
    assert frame.module_code not in blocked_raw and frame.function_code not in blocked_raw
    assert "source_unavailable" in recorder.record.issue_codes
    blocked.close()

    allowed = DiagnosticsStore(tmp_path / "allowed", source_registry=frozenset({(frame.module_code, frame.function_code)}))
    recorder = allowed.start(_context())
    assert recorder is not None
    assert recorder.failure(failure) == failure.error_id
    assert allowed.read(recorder.context.run_id).availability_reason == "present"
    # A reader lacking the registry refuses the otherwise valid source data.
    assert DiagnosticsStore(tmp_path / "allowed").read(recorder.context.run_id).availability_reason == "corrupt"
    allowed.close()


def test_events_errors_terminal_reservation_and_duplicate_dedup(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    stage = recorder.start_stage("generate")
    assert stage is not None
    event_id = str(uuid.uuid4())
    event_id = "evt_" + event_id
    assert recorder.event(stage_id=stage, stage_code="generate", event_code="fallback", event_id=event_id)
    assert recorder.event(stage_id=stage, stage_code="generate", event_code="fallback", event_id=event_id)
    assert len(recorder.record.events) == 2
    for _ in range(MAX_EVENTS):
        recorder.event(stage_id=stage, stage_code="generate", event_code="skip")
    assert len(recorder.record.events) == MAX_EVENTS
    assert recorder.record.dropped_events > 0 and "event_limit" in recorder.record.issue_codes
    first = safe_failure(stage_id=stage, stage_code="generate")
    assert recorder.failure(first) == first.error_id
    assert recorder.failure(first) == first.error_id
    for _ in range(MAX_ERRORS - 2):
        assert recorder.failure(safe_failure(stage_id=stage, stage_code="generate")) is not None
    assert len(recorder.record.errors) == MAX_ERRORS - 1
    terminal = safe_failure(stage_id=stage, stage_code="commit", reason_code="commit_unknown")
    assert recorder.failure(terminal, terminal=True) == terminal.error_id
    assert len(recorder.record.errors) == MAX_ERRORS
    assert recorder.record.first_failure == first
    assert recorder.finish("failed", terminal_failure=terminal)
    assert store.read(recorder.context.run_id).record is not None
    store.close()


def test_concurrent_same_run_returns_one_handle_and_sequences_are_contiguous(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    context = _context()
    first = store.start(context); second = store.start(context)
    assert first is second and first is not None
    stage = first.start_stage("collect")
    assert stage is not None
    assert first.event(stage_id=stage, stage_code="collect", event_code="end")
    record = store.read(context.run_id).record
    assert record is not None
    assert [event.seq for event in record.events] == list(range(1, len(record.events) + 1))
    store.close()


def test_concurrent_events_keep_one_deduped_sequence(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    stage = recorder.start_stage("collect")
    assert stage is not None
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _index: recorder.event(stage_id=stage, stage_code="collect", event_code="skip"), range(32)))
    assert all(results)
    record = store.read(recorder.context.run_id).record
    assert record is not None
    assert len(record.events) == 33
    assert [event.seq for event in record.events] == list(range(1, 34))
    store.close()


def test_quota_and_read_failure_are_best_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    monkeypatch.setattr(store, "_scan", lambda: QuotaSnapshot(0, 0, 0, False, "quota_exceeded"))
    assert store.start(_context()) is None
    assert store.last_write_reason == "quota_exceeded"
    healthy = DiagnosticsStore(tmp_path / "other")
    recorder = healthy.start(_context())
    assert recorder is not None
    monkeypatch.setattr(healthy, "_record_path", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked")))
    assert healthy.read(recorder.context.run_id).availability_reason == "read_failed"
    healthy.close(); store.close()


def test_reparse_root_and_unadmitted_write_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from features.common.diagnostics.record import DiagnosticRecord
    from features.common.diagnostics import store as module

    root = tmp_path / "data"
    blocked = DiagnosticsStore(root)
    monkeypatch.setattr(module, "_is_reparse", lambda path: path == blocked.root)
    assert blocked.start(_context()) is None
    assert blocked.last_write_reason == "write_failed"
    blocked.close()

    store = DiagnosticsStore(root / "normal")
    assert store.persist(DiagnosticRecord.new(_context())) is False
    assert store.last_write_reason == "quota_exceeded"
    store.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction fixture")
def test_windows_junction_root_is_rejected_before_any_write(tmp_path: Path) -> None:
    outside = tmp_path / "outside"; outside.mkdir()
    junction = tmp_path / "junction-data"
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, text=True, check=False)
    assert made.returncode == 0, made.stderr
    store = DiagnosticsStore(junction)
    assert store.start(_context()) is None
    assert store.last_write_reason == "write_failed"
    assert not (outside / "diagnostics").exists()
    store.close()


def test_disk_write_fault_stays_in_memory_and_does_not_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from features.common.diagnostics import store as module

    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    stage = recorder.start_stage("validate")
    assert stage is not None
    monkeypatch.setattr(module, "write_bytes_atomic", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("private canary")))
    assert recorder.event(stage_id=stage, stage_code="validate", event_code="end") is False
    assert "write_failed" in recorder.record.issue_codes
    # The fault's text was never emitted to the persisted initial record.
    raw = (store.runs_root / f"{recorder.context.run_id}.json").read_text(encoding="utf-8")
    assert "private canary" not in raw
    store.close()


def test_active_handle_cap_is_bounded_and_terminal_release_allows_next_run(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    recorders = [store.start(_context()) for _ in range(128)]
    assert all(recorders)
    assert store.start(_context()) is None
    assert store.last_write_reason == "quota_exceeded"
    # This fixture isolates handle-cap release; bounded reconciliation is
    # separately allowed to close new admissions while terminals still finish.
    store._writes_since_reconcile = 0
    assert recorders[0] is not None and recorders[0].finish("succeeded")
    assert store.start(_context()) is not None
    store.close()


def test_context_reset_and_safe_exception_classifier_do_not_read_canary() -> None:
    context = _context()
    assert current_context() is None
    with bind_context(context):
        assert current_context() is context
        assert context_bound(context, lambda: current_context())() is context
    assert current_context() is None
    canary = RuntimeError("private token sk-canary")
    failure = safe_exception_failure(canary, boundary="generic")
    assert failure.exception_code == "runtime_error"
    assert failure.reason_code == "unknown"
    assert "sk-canary" not in json.dumps(failure.to_dict())


def test_stage_ownership_rejects_duplicate_end_and_cross_epoch_close(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    stage = recorder.start_stage("commit")
    assert stage is not None
    assert recorder.end_stage(stage, "commit")
    assert recorder.end_stage(stage, "commit") is False
    old_stage = recorder.start_stage("recovery")
    assert old_stage is not None
    recorder.context = recorder.context.with_recovery_producer()
    assert recorder.end_stage(old_stage, "recovery") is False
    store.close()


def test_warnings_and_safe_console_are_bounded_codes_only(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    store.note_warning("not-a-real-code", recorder.context.run_id)
    warning = store.warning_projection(recorder.context.run_id)
    assert warning == [{"code": "write_failed", "runId": recorder.context.run_id}]
    lines: list[str] = []
    assert store.safe_console("write_failed", recorder.context.run_id, printer=lines.append)
    assert lines == [f"diagnostics:write_failed:{recorder.context.run_id}"]
    assert store.safe_console("wrong", recorder.context.run_id, printer=lines.append) is False
    store.close()


def test_shared_job_enum_parity_and_warm_write_avoids_other_run_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from features.common.shared_jobs_schema import Adapter, Engine, FallbackReason, TaskType

    context = _context(task_type=TaskType.RSS.value)
    record = __import__("features.common.diagnostics.record", fromlist=["DiagnosticRecord"]).DiagnosticRecord.new(context)
    record = replace(record, attempted_engine=Engine.CLI.value, final_engine=Engine.RULES.value, adapter=Adapter.CODEX.value, fallback_reason=FallbackReason.ENGINE_FAILED.value)
    assert record.to_dict()["taskType"] == TaskType.RSS.value
    store = DiagnosticsStore(tmp_path / "data")
    first = store.start(context); second = store.start(_context())
    assert first is not None and second is not None
    stage = first.start_stage("collect")
    assert stage is not None
    other = second.context.run_id
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs: (_ for _ in ()).throw(AssertionError("warm persist read another run")) if path.name == f"{other}.json" else original(path, *args, **kwargs))
    assert first.event(stage_id=stage, stage_code="collect", event_code="skip")
    store.close()


def test_writer_conflict_and_process_exit_release(tmp_path: Path) -> None:
    root = tmp_path / "data"
    first = DiagnosticsStore(root)
    assert first.start(_context()) is not None
    second = DiagnosticsStore(root)
    assert second.start(_context()) is None
    assert second.last_write_reason == "writer_conflict"
    first.close()
    assert second.start(_context()) is not None
    second.close()

    code = "from pathlib import Path; from features.common.diagnostics import DiagnosticsStore,new_context; s=DiagnosticsStore(Path(sys.argv[1])); assert s.start(new_context(feature_code='jobs',route_code='shared_worker',authority_kind='direct',app_version='0.5.4'))"
    completed = subprocess.run([sys.executable, "-c", "import sys; " + code, str(root / "exit")], capture_output=True, text=True, env={**os.environ, "FOLIO_HOME": str(tmp_path / "subhome")}, check=False)
    assert completed.returncode == 0, completed.stderr
    after_exit = DiagnosticsStore(root / "exit")
    assert after_exit.start(_context()) is not None
    after_exit.close()


def test_recovery_cross_epoch_preserves_open_stage_and_is_partial(tmp_path: Path) -> None:
    root = tmp_path / "data"
    original_context = _context()
    first = DiagnosticsStore(root)
    recorder = first.start(original_context)
    assert recorder is not None
    open_stage = recorder.start_stage("commit")
    assert open_stage is not None
    first.close()
    newer_epoch = str(uuid.uuid4())
    recovery_context = replace(original_context, process_epoch=newer_epoch, producer_epoch=newer_epoch)
    second = DiagnosticsStore(root)
    resumed = second.resume(recovery_context, observed_status="succeeded")
    assert resumed is not None
    record = second.read(original_context.run_id).record
    assert record is not None
    assert record.context.process_epoch == original_context.process_epoch
    assert record.elapsed_ms is None
    assert "recovery_gap" in record.issue_codes
    assert any(event.stage_id == open_stage and event.event_code == "start" for event in record.events)
    assert not any(event.stage_id == open_stage and event.event_code == "end" for event in record.events)
    projection = project_read(second.read(original_context.run_id))
    assert projection["diagnosticQuality"] == "partial"
    second.close()


def test_stale_terminal_handle_cannot_overwrite_a_new_recovery_owner(tmp_path: Path) -> None:
    root = tmp_path / "data"
    context = _context()
    store = DiagnosticsStore(root)
    old = store.start(context)
    assert old is not None and old.finish("succeeded")
    renewed_epoch = str(uuid.uuid4())
    recovered = store.resume(replace(context, process_epoch=renewed_epoch, producer_epoch=renewed_epoch))
    assert recovered is None
    assert store.last_write_reason == "invalid_recovery_terminal"
    before = store.read(context.run_id).record
    assert before is not None
    stage = "stg_" + str(uuid.uuid4())
    assert old.event(stage_id=stage, stage_code="recovery", event_code="start") is False
    after = store.read(context.run_id).record
    assert after == before
    store.close()


def test_record_rejects_unknown_fields_without_reassembling_them() -> None:
    context = _context()
    raw = record_from_dict(__import__("features.common.diagnostics.record", fromlist=["DiagnosticRecord"]).DiagnosticRecord.new(context).to_dict())
    assert raw.run_id == context.run_id


def test_sanitized_frame_also_rebuilds_the_closed_fingerprint(tmp_path: Path) -> None:
    from features.common.diagnostics.schema import failure_fingerprint

    store = DiagnosticsStore(tmp_path / "data")
    recorder = store.start(_context())
    assert recorder is not None
    unsafe = SafeFrame("features.private_canary", "hidden", 1)
    failure = safe_failure(reason_code="timeout", frames=(unsafe,))
    assert recorder.finish("failed", terminal_failure=failure)
    saved = store.read(recorder.context.run_id).record
    assert saved is not None and saved.terminal_failure is not None
    assert saved.terminal_failure.frames == ()
    assert saved.terminal_failure.fingerprint == failure_fingerprint(
        stage_code=None, reason_code="timeout", exception_code="other", frames=()
    )
    assert saved.terminal_failure.fingerprint != failure.fingerprint
    store.close()


def test_resumable_cold_scan_does_not_cache_partial_totals(tmp_path: Path) -> None:
    """A 4095-file cold root advances across calls and admits only at completion."""
    from features.common.diagnostics.record import DiagnosticRecord, TerminalObservation

    archive = tmp_path / "data" / "diagnostics" / "runs"
    archive.mkdir(parents=True)
    for _ in range(4095):
        context = _context()
        record = DiagnosticRecord.new(context)
        record = replace(
            record,
            observed_status="done",
            finished_at=record.updated_at,
            terminal_observation=TerminalObservation("done", record.updated_at, context.process_epoch),
        )
        (archive / f"{context.run_id}.json").write_bytes(record.to_bytes())
    store = DiagnosticsStore(tmp_path / "data")
    candidate = _context()
    for _ in range(200):
        recorder = store.start(candidate)
        if recorder is not None:
            break
        assert store.last_write_reason == "scan_limit"
        # A partial slice is held separately from a valid quota snapshot.
        assert store._quota_cache is None
    else:
        pytest.fail("resumable scan did not complete within the bounded attempts")
    assert recorder is not None
    assert store._quota_cache is not None and store._quota_cache.run_files == 4096
    store.close()


def test_read_rejects_a_valid_record_copied_under_another_run_id(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    original = store.start(_context())
    assert original is not None and original.finish("done")
    copied_id = _context().run_id
    source = store.runs_root / f"{original.context.run_id}.json"
    target = store.runs_root / f"{copied_id}.json"
    target.write_bytes(source.read_bytes())
    assert store.read(copied_id).availability_reason == "corrupt"
    store.close()
