from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import threading

import pytest
from fastapi import HTTPException

from features.common.diagnostics import DiagnosticsStore, new_context
from features.common.diagnostics.record import TerminalObservation
from features.common.diagnostics.retention import (
    DEFAULT_RETENTION_DAYS,
    DiagnosticsRetentionService,
    MAX_RETENTION_CANDIDATES,
    RetentionConflict,
    RetentionUnavailable,
    RetentionValidationError,
)
from features.common.diagnostics import retention as retention_module
from features.common.diagnostics.retention_routes import create_retention_router
from features.common.diagnostics.store import ReadResult


def _at(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _old_direct(store: DiagnosticsStore, days_ago: int = 45) -> tuple[str, Path]:
    recorder = store.start(new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct"))
    assert recorder is not None
    assert recorder.finish("succeeded")
    result = store.read(recorder.context.run_id)
    assert result.record is not None
    instant = _at(days_ago)
    record = replace(
        result.record,
        created_at=instant,
        updated_at=instant,
        finished_at=instant,
        terminal_observation=TerminalObservation("succeeded", instant, result.record.context.producer_epoch),
    )
    path = store.runs_root / f"{record.run_id}.json"
    path.write_bytes(record.to_bytes())
    return record.run_id, path


def _old_terminal(store: DiagnosticsStore, context, status: str = "done", days_ago: int = 45) -> tuple[str, Path]:
    recorder = store.start(context)
    assert recorder is not None
    instant = _at(days_ago)
    assert recorder.finish(status, at=instant)
    result = store.read(context.run_id)
    assert result.record is not None
    # Keep createdAt old as well so the fixture represents an old completed
    # archive, not merely a terminal write whose finish time is old.
    record = replace(result.record, created_at=instant, updated_at=instant)
    path = store.runs_root / f"{context.run_id}.json"
    path.write_bytes(record.to_bytes())
    return context.run_id, path


def _authority(job_id: str, status: str = "done", revision: str = "r1") -> dict[str, object]:
    return {"jobsById": {job_id: {"status": status}}, "visibilityRevision": revision}


def test_defaults_are_closed_and_settings_preview_confirm_can_create_owned_root(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    service = DiagnosticsRetentionService(store)
    status = service.usage_status()
    assert status["settings"]["retentionDays"] == DEFAULT_RETENTION_DAYS
    assert status["settings"]["autoDelete"] is False
    assert status["settings"]["choices"] == [7, 30, 90, 180, 365]

    preview = service.settings_preview(90, True)
    saved = service.settings_confirm(preview["previewToken"], confirm=True)
    assert saved["retentionDays"] == 90 and saved["autoDelete"] is True
    assert service.read_settings().retention_days == 90
    assert store.root.exists() and (store.root / "retention-settings.json").exists()
    store.close()


def test_preview_confirm_deletes_only_old_direct_terminal_runs_and_marks_expired(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    old_id, old_path = _old_direct(store, 45)
    recent_id, _recent_path = _old_direct(store, 2)
    service = DiagnosticsRetentionService(store)

    preview = service.preview(30)
    assert preview["eligibleCount"] == 1
    assert old_id != recent_id
    assert preview["excludedCounts"]["other"] >= 1
    result = service.confirm(preview["previewToken"], confirm=True)
    assert result["deletedCount"] == 1
    assert not old_path.exists()
    assert store.read(old_id).availability_reason == "expired"
    assert store.read(old_id).tombstone is not None
    assert store.read(recent_id).availability_reason == "present"
    with pytest.raises(RetentionConflict, match="preview_token_replayed"):
        service.confirm(preview["previewToken"], confirm=True)
    store.close()


def test_preview_revalidates_fingerprint_and_running_or_job_without_authority_is_excluded(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    run_id, path = _old_direct(store, 45)
    service = DiagnosticsRetentionService(store)
    preview = service.preview(30)
    assert preview["eligibleCount"] == 1
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["updatedAt"] = _at(45)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RetentionConflict, match="preview_changed"):
        service.confirm(preview["previewToken"], confirm=True)
    assert path.exists() and store.read(run_id).availability_reason == "present"

    job_recorder = store.start(
        new_context(
            feature_code="jobs",
            route_code="shared_worker",
            authority_kind="shared_job",
            job_id="job_00000000-0000-4000-8000-000000000000",
        )
    )
    assert job_recorder is not None and job_recorder.finish("succeeded", at=_at(45))
    blocked = DiagnosticsRetentionService(store)
    blocked_preview = blocked.preview(30)
    assert blocked_preview["eligibleCount"] >= 1  # the unchanged direct fixture remains eligible
    assert blocked_preview["excludedCounts"]["privateBlocked"] >= 1
    store.close()


def test_retention_router_has_only_closed_status_preview_confirm_forms(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    runtime = type("Runtime", (), {"store": store})()
    router = create_retention_router(runtime_provider=lambda: runtime)
    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}
    assert paths == {
        ("/api/diagnostics/retention", ("GET",)),
        ("/api/diagnostics/retention/preview", ("POST",)),
        ("/api/diagnostics/retention/confirm", ("POST",)),
        ("/api/diagnostics/retention/settings/preview", ("POST",)),
        ("/api/diagnostics/retention/settings/confirm", ("POST",)),
    }
    preview = next(route.endpoint for route in router.routes if route.path.endswith("/preview") and route.path.count("/") == 4)
    with pytest.raises(HTTPException) as error:
        preview({"retentionDays": 30, "unexpected": True})
    assert error.value.status_code == 422
    store.close()


def test_retention_confirmation_requires_literal_true_and_invalid_period_is_rejected(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    service = DiagnosticsRetentionService(store)
    with pytest.raises(RetentionValidationError, match="invalid_retention_days"):
        service.preview(31)
    with pytest.raises(RetentionValidationError, match="confirmation_required"):
        service.confirm("drt1_invalid", confirm=1)  # type: ignore[arg-type]
    store.close()


def test_same_delete_preview_is_single_use_under_concurrent_confirmations(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    _old_direct(store, 45)
    service = DiagnosticsRetentionService(store)
    token = service.preview(30)["previewToken"]
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def confirm() -> None:
        barrier.wait()
        try:
            outcomes.append(service.confirm(token, confirm=True))
        except Exception as error:  # assertion below checks the stable code
            outcomes.append(error)

    threads = [threading.Thread(target=confirm) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(outcomes) == 2
    assert sum(isinstance(item, dict) and item["deletedCount"] == 1 for item in outcomes) == 1
    conflicts = [item for item in outcomes if isinstance(item, RetentionConflict)]
    assert len(conflicts) == 1 and conflicts[0].code == "preview_token_replayed"
    store.close()


def test_same_settings_preview_is_single_use_under_concurrent_confirmations(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    service = DiagnosticsRetentionService(store)
    token = service.settings_preview(90, False)["previewToken"]
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def confirm() -> None:
        barrier.wait()
        try:
            outcomes.append(service.settings_confirm(token, confirm=True))
        except Exception as error:
            outcomes.append(error)

    threads = [threading.Thread(target=confirm) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(outcomes) == 2
    assert sum(isinstance(item, dict) and item["status"] == "saved" for item in outcomes) == 1
    conflicts = [item for item in outcomes if isinstance(item, RetentionConflict)]
    assert len(conflicts) == 1 and conflicts[0].code == "preview_token_replayed"
    store.close()


def test_tombstone_enum_canary_is_rejected_without_projection_leak(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    run_id, _path = _old_direct(store, 45)
    service = DiagnosticsRetentionService(store)
    token = service.preview(30)["previewToken"]
    assert service.confirm(token, confirm=True)["deletedCount"] == 1
    ledger = store.root / "expired.json"
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    canary = "D4_PRIVATE_ENUM_CANARY"
    payload["items"][0]["featureCode"] = canary
    ledger.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RetentionUnavailable, match="tombstone_corrupt"):
        DiagnosticsRetentionService(store).usage_status()
    result = store.read(run_id)
    assert result.availability_reason == "read_failed"
    assert canary not in json.dumps({"reason": result.availability_reason})
    store.close()


def test_filename_record_identity_mismatch_is_partial_and_not_eligible(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    _run_id, path = _old_direct(store, 45)
    mismatched = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct").run_id
    bad_path = store.runs_root / f"{mismatched}.json"
    bad_path.write_bytes(path.read_bytes())
    preview = DiagnosticsRetentionService(store).preview(30)
    assert preview["status"] == "partial"
    assert preview["excludedCounts"]["corrupt"] >= 1
    assert mismatched not in json.dumps(preview)
    store.close()


def test_live_handle_is_rechecked_at_unlink_and_authority_change_blocks(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    context = new_context(
        feature_code="jobs",
        route_code="shared_worker",
        authority_kind="shared_job",
        job_id="job_00000000-0000-4000-8000-000000000000",
    )
    run_id, _path = _old_terminal(store, context)
    authority = _authority(context.job_id or "")
    service = DiagnosticsRetentionService(store, authority_provider=lambda: authority)
    token = service.preview(30)["previewToken"]
    # A live reservation can appear after preview and must win immediately
    # before the unlink, even though the file fingerprint is unchanged.
    with store._lock:
        store._handles[run_id] = object()  # type: ignore[assignment]
    with pytest.raises(RetentionConflict, match="live_handle"):
        service.confirm(token, confirm=True)
    with store._lock:
        store._handles.pop(run_id, None)

    token = service.preview(30)["previewToken"]
    authority["jobsById"][context.job_id or ""]["status"] = "failed"  # type: ignore[index]
    with pytest.raises(RetentionConflict, match="authority_changed"):
        service.confirm(token, confirm=True)
    assert store.read(run_id).record is not None
    store.close()


def test_private_recovery_running_and_reparse_cases_are_excluded_or_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    running = store.start(new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct"))
    assert running is not None
    _old_terminal(store, new_context(feature_code="startup", route_code="startup_recovery", authority_kind="recovery"))
    preview = DiagnosticsRetentionService(store).preview(30)
    assert preview["excludedCounts"]["running"] >= 1
    assert preview["excludedCounts"]["recovery"] >= 1
    monkeypatch.setattr(retention_module, "_is_reparse", lambda value: Path(value) == store.runs_root)
    with pytest.raises(RetentionUnavailable, match="diagnostics_reparse"):
        DiagnosticsRetentionService(store).preview(30)
    store.close()


def test_corrupt_archive_is_explicitly_partial_not_clean_empty_preview(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    _old_direct(store, 45)
    corrupt_id = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct").run_id
    (store.runs_root / f"{corrupt_id}.json").write_text("{not-json", encoding="utf-8")
    preview = DiagnosticsRetentionService(store).preview(30)
    assert preview["status"] == "partial"
    assert preview["excludedCounts"]["corrupt"] >= 1
    store.close()


def test_retention_scan_deadline_fails_closed_instead_of_reporting_complete(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    _old_direct(store, 45)
    ticks = iter([0.0] + [6.0] * 100)
    service = DiagnosticsRetentionService(store, monotonic_clock=lambda: next(ticks))
    with pytest.raises(RetentionUnavailable, match="scan_deadline"):
        service.preview(30)
    store.close()


def test_automatic_cleanup_uses_current_shared_job_authority_and_stays_disabled_by_default(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    context = new_context(
        feature_code="jobs",
        route_code="shared_worker",
        authority_kind="shared_job",
        job_id="job_00000000-0000-4000-8000-000000000000",
    )
    run_id, path = _old_terminal(store, context)
    authority = _authority(context.job_id or "")
    service = DiagnosticsRetentionService(store, authority_provider=lambda: authority)
    assert service.run_automatic()["status"] == "disabled"
    settings = service.settings_preview(30, True)
    assert service.settings_confirm(settings["previewToken"], confirm=True)["autoDelete"] is True
    result = service.run_automatic()
    assert result["deletedCount"] == 1
    assert not path.exists()
    assert store.read(run_id).availability_reason == "expired"
    store.close()


def test_retention_uses_a_64_record_batch_and_tombstones_only_deleted_batch(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    base_id, base_path = _old_direct(store, 45)
    base = store.read(base_id).record
    assert base is not None
    # Clone one validated, terminal direct record into distinct UUID identities
    # to exercise the bounded batch without admitting 65 live handles.
    for _index in range(MAX_RETENTION_CANDIDATES + 1):
        context = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct")
        clone = replace(base, context=context)
        (store.runs_root / f"{context.run_id}.json").write_bytes(clone.to_bytes())
    base_path.unlink()
    service = DiagnosticsRetentionService(store)
    usage = service.usage_status()
    assert usage["usage"]["runFiles"] == MAX_RETENTION_CANDIDATES + 1
    preview = service.preview(30)
    assert preview["eligibleCount"] == MAX_RETENTION_CANDIDATES
    assert preview["excludedCounts"]["other"] >= 1
    result = service.confirm(preview["previewToken"], confirm=True)
    assert result["deletedCount"] == MAX_RETENTION_CANDIDATES
    ledger = json.loads((store.root / "expired.json").read_text(encoding="utf-8"))
    assert len(ledger["items"]) == MAX_RETENTION_CANDIDATES
    assert sum(path.exists() for path in store.runs_root.glob("run_*.json")) == 1
    store.close()


def test_candidate_cap_is_after_eligibility_so_an_old_record_after_64_recent_ones_is_found(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    old_id, _old_path = _old_direct(store, 45)
    base = store.read(old_id).record
    assert base is not None
    recent = _at(2)
    for _index in range(MAX_RETENTION_CANDIDATES):
        context = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct")
        clone = replace(
            base,
            context=context,
            created_at=recent,
            updated_at=recent,
            finished_at=recent,
            terminal_observation=TerminalObservation("succeeded", recent, context.producer_epoch),
        )
        (store.runs_root / f"{context.run_id}.json").write_bytes(clone.to_bytes())
    preview = DiagnosticsRetentionService(store).preview(30)
    assert preview["status"] == "ready"
    assert preview["eligibleCount"] == 1
    assert preview["excludedCounts"]["other"] >= MAX_RETENTION_CANDIDATES
    store.close()


def test_automatic_tombstone_contains_only_the_deleted_64_record_batch(tmp_path: Path) -> None:
    store = DiagnosticsStore(tmp_path / "data")
    base_id, base_path = _old_direct(store, 45)
    base = store.read(base_id).record
    assert base is not None
    for _index in range(MAX_RETENTION_CANDIDATES + 1):
        context = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="direct")
        (store.runs_root / f"{context.run_id}.json").write_bytes(replace(base, context=context).to_bytes())
    base_path.unlink()
    service = DiagnosticsRetentionService(store)
    settings = service.settings_preview(30, True)
    assert service.settings_confirm(settings["previewToken"], confirm=True)["autoDelete"] is True
    result = service.run_automatic()
    assert result["deletedCount"] == MAX_RETENTION_CANDIDATES
    ledger = json.loads((store.root / "expired.json").read_text(encoding="utf-8"))
    assert len(ledger["items"]) == MAX_RETENTION_CANDIDATES
    assert sum(path.exists() for path in store.runs_root.glob("run_*.json")) == 1
    store.close()
