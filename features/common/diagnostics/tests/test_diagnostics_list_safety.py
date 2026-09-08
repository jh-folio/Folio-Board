from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep any lazy workspace lookup away from the real user's home."""

    monkeypatch.setenv("FOLIO_HOME", str(tmp_path / "home"))


def _authority(revision: str = "stable"):
    from features.common.diagnostics.authority import AuthoritySnapshot

    return AuthoritySnapshot((), frozenset(), (), 0, 0, revision)


def _direct(store, status: str = "failed") -> str:
    from features.common.diagnostics.schema import new_context

    recorder = store.start(
        new_context(feature_code="http", route_code="http_unhandled", authority_kind="direct")
    )
    assert recorder is not None
    assert recorder.finish(status)
    return recorder.context.run_id


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_cursor_ttl_expires_but_pages_keep_the_same_snapshot_at(tmp_path: Path) -> None:
    from features.common.diagnostics.listing import (
        DiagnosticsListService,
        ListCursorError,
        ListQuery,
        SNAPSHOT_TTL_SECONDS,
    )
    from features.common.diagnostics.store import DiagnosticsStore

    store = DiagnosticsStore(tmp_path / "data")
    _direct(store)
    _direct(store)
    clock = _FakeClock()
    wall = [datetime(2026, 9, 5, 1, 2, 3, 456000, tzinfo=UTC)]
    service = DiagnosticsListService(
        authority_provider=lambda: _authority(),
        clock=clock,
        wall_clock=lambda: wall[0],
    )
    try:
        query = ListQuery(limit=1)
        first = service.list(store, query)
        token = first["nextCursor"]
        assert token
        wall[0] = datetime(2026, 9, 5, 2, 2, 3, tzinfo=UTC)
        second = service.list(store, query, token)
        assert second["snapshotAt"] == first["snapshotAt"]

        clock.advance(SNAPSHOT_TTL_SECONDS)
        with pytest.raises(ListCursorError) as expired:
            service.list(store, query, token)
        assert expired.value.code == "cursor_expired"
    finally:
        store.close()


def test_cursor_is_not_valid_after_service_restart(tmp_path: Path) -> None:
    from features.common.diagnostics.listing import DiagnosticsListService, ListCursorError, ListQuery
    from features.common.diagnostics.store import DiagnosticsStore

    store = DiagnosticsStore(tmp_path / "data")
    _direct(store)
    _direct(store)
    query = ListQuery(limit=1)
    try:
        token = DiagnosticsListService(authority_provider=lambda: _authority()).list(store, query)["nextCursor"]
        assert token
        restarted = DiagnosticsListService(authority_provider=lambda: _authority())
        with pytest.raises(ListCursorError) as missing:
            restarted.list(store, query, token)
        assert missing.value.code == "cursor_expired"
    finally:
        store.close()


def test_cursor_is_evicted_when_snapshot_cache_reaches_its_bound(tmp_path: Path) -> None:
    from features.common.diagnostics.listing import (
        MAX_SNAPSHOTS,
        DiagnosticsListService,
        ListCursorError,
        ListQuery,
    )
    from features.common.diagnostics.store import DiagnosticsStore

    store = DiagnosticsStore(tmp_path / "data")
    _direct(store)
    _direct(store)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    query = ListQuery(limit=1)
    try:
        token = service.list(store, query)["nextCursor"]
        assert token
        for _ in range(MAX_SNAPSHOTS):
            service.list(store, query)
        with pytest.raises(ListCursorError) as evicted:
            service.list(store, query, token)
        assert evicted.value.code == "cursor_expired"
    finally:
        store.close()


@pytest.mark.parametrize(
    ("main_name", "backup_name"),
    [
        ("jobs-v2.json", "jobs-v2.json.bak"),
        ("jobs.json", "jobs.json.bak"),
        ("automation-runs.json", "automation-runs.json.bak"),
    ],
)
def test_corrupt_authority_files_fail_closed_without_backup_restore(
    tmp_path: Path, main_name: str, backup_name: str
) -> None:
    from features.common.diagnostics.authority import (
        AuthoritySnapshotUnavailable,
        ReadOnlyAuthoritySnapshotProvider,
    )

    main = tmp_path / main_name
    backup = tmp_path / backup_name
    main_bytes = b"{\"private_canary\":"
    backup_bytes = b"BACKUP-MUST-NOT-BE-RESTORED"
    main.write_bytes(main_bytes)
    backup.write_bytes(backup_bytes)
    provider = ReadOnlyAuthoritySnapshotProvider(
        v2_path=tmp_path / "jobs-v2.json",
        legacy_path=tmp_path / "jobs.json",
        work_log_path=tmp_path / "agent-work-log.json",
        automation_path=tmp_path / "automation-runs.json",
    )

    with pytest.raises(AuthoritySnapshotUnavailable):
        provider.snapshot()
    assert main.read_bytes() == main_bytes
    assert backup.read_bytes() == backup_bytes
    assert not (tmp_path / "private_canary").exists()


def test_external_changed_and_deleted_runs_are_removed_from_warm_projection(tmp_path: Path) -> None:
    from features.common.diagnostics.listing import DiagnosticsListService, ListQuery
    from features.common.diagnostics.store import DiagnosticsStore

    store = DiagnosticsStore(tmp_path / "data")
    changed = _direct(store)
    deleted = _direct(store)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    try:
        initial = service.list(store, ListQuery())
        assert {item["runId"] for item in initial["items"]} == {changed, deleted}

        secret = "PRIVATE-LIST-CANARY"
        (store.runs_root / f"{changed}.json").write_text(
            json.dumps({"secret": secret}), encoding="utf-8"
        )
        after_change = service.list(store, ListQuery())
        assert changed not in {item["runId"] for item in after_change["items"]}
        assert deleted in {item["runId"] for item in after_change["items"]}
        assert any(error["code"] == "record_corrupt" for error in after_change["errors"])
        assert secret not in json.dumps(after_change, ensure_ascii=False)

        (store.runs_root / f"{deleted}.json").unlink()
        after_delete = service.list(store, ListQuery())
        assert after_delete["items"] == []
    finally:
        store.close()


def test_registered_source_edit_invalidates_cached_header_and_fails_closed(tmp_path: Path) -> None:
    from features.common.diagnostics.listing import DiagnosticsListService, ListQuery
    from features.common.diagnostics.schema import SafeFrame, new_context, safe_failure
    from features.common.diagnostics.store import DiagnosticsStore

    app_root = tmp_path / "app"
    app_root.mkdir()
    source_path = app_root / "features" / "common"
    source_path.mkdir(parents=True)
    (source_path / "fixture_mod.py").write_text("def worker():\n    return 1\n", encoding="utf-8")
    store = DiagnosticsStore(
        tmp_path / "data",
        app_root=app_root,
        source_registry=frozenset({("features.common.fixture_mod", "worker")}),
    )
    recorder = store.start(
        new_context(feature_code="http", route_code="http_unhandled", authority_kind="direct")
    )
    assert recorder is not None
    failure = safe_failure(
        stage_code="generate",
        reason_code="timeout",
        frames=(SafeFrame("features.common.fixture_mod", "worker", 1),),
    )
    assert recorder.finish("failed", terminal_failure=failure)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    try:
        run_id = recorder.context.run_id
        assert [item["runId"] for item in service.list(store, ListQuery())["items"]] == [run_id]

        (source_path / "fixture_mod.py").write_text(
            "def another_worker():\n    return 2\n\n# source changed\n", encoding="utf-8"
        )
        refreshed = service.list(store, ListQuery())
        assert refreshed["items"] == []
        assert any(error["code"] == "record_corrupt" for error in refreshed["errors"])
    finally:
        store.close()


def test_scanner_reports_a_bounded_cap_without_claiming_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from features.common.diagnostics import listing
    from features.common.diagnostics.record import DiagnosticRecord
    from features.common.diagnostics.schema import new_context
    from features.common.diagnostics.store import DiagnosticsStore

    data_root = tmp_path / "data"
    runs_root = data_root / "diagnostics" / "runs"
    runs_root.mkdir(parents=True)
    store = DiagnosticsStore(data_root)
    for _ in range(4):
        record = DiagnosticRecord.new(
            new_context(feature_code="http", route_code="http_unhandled", authority_kind="direct")
        )
        (runs_root / f"{record.run_id}.json").write_bytes(record.to_bytes())
    monkeypatch.setattr(listing, "SCAN_ENTRY_LIMIT", 2)
    result = listing.scan_headers(store)
    assert result.complete is False
    assert "scan_limit" in result.errors
    assert result.entries_scanned > 2


def test_scanner_errors_are_closed_bounded_and_do_not_echo_record_canaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from features.common.diagnostics import listing
    from features.common.diagnostics.listing import DiagnosticsListService, ListQuery
    from features.common.diagnostics.schema import new_context
    from features.common.diagnostics.store import DiagnosticsStore, MAX_DOCUMENT_BYTES

    data_root = tmp_path / "data"
    runs_root = data_root / "diagnostics" / "runs"
    runs_root.mkdir(parents=True)
    store = DiagnosticsStore(data_root)
    malformed_id = new_context(feature_code="http", route_code="http_unhandled", authority_kind="direct").run_id
    oversized_id = new_context(feature_code="http", route_code="http_unhandled", authority_kind="direct").run_id
    (runs_root / f"{malformed_id}.json").write_bytes(b'{"private_canary":"DO-NOT-ECHO"')
    (runs_root / f"{oversized_id}.json").write_bytes(b"x" * (MAX_DOCUMENT_BYTES + 1))
    (runs_root / "not-a-run.json").write_bytes(b"{}")
    monkeypatch.setattr(listing, "MAX_SCAN_ERRORS", 2)

    result = DiagnosticsListService(authority_provider=lambda: _authority()).list(store, ListQuery())
    assert result["items"] == []
    assert len(result["errors"]) <= 2
    assert all(set(error) == {"code"} for error in result["errors"])
    assert "DO-NOT-ECHO" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction fixture")
def test_scanner_rejects_windows_junction_runs_root(tmp_path: Path) -> None:
    from features.common.diagnostics.listing import ListUnavailable, scan_headers
    from features.common.diagnostics.store import DiagnosticsStore

    store = DiagnosticsStore(tmp_path / "data")
    store.root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(store.runs_root), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip(f"junction unavailable: {made.stderr.strip()}")
    with pytest.raises(ListUnavailable) as blocked:
        scan_headers(store)
    assert blocked.value.code == "authority_reparse"
