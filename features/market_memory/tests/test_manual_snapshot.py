from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from features.automation import service as automation_service
from features.market_memory.attempt_store import (
    AttemptMode,
    AttemptScope,
    AttemptStatus,
    AttemptStore,
    AttemptStoreUnavailableError,
    UpdateAttemptRef,
)
from features.market_memory.manual_snapshot import (
    CommittedManualSnapshot,
    ManualLifecycleAdapters,
    ManualSnapshotBoundary,
    ManualSnapshotCandidate,
    ManualSnapshotLifecycle,
    ManualSnapshotRequest,
    ManualSnapshotRepairRequiredError,
    recover_manual_attempts,
)
from features.market_memory.snapshot import save_market_state_snapshot


NOW = datetime(2026, 7, 17, 3, 0, tzinfo=UTC)


class SimulatedCrash(BaseException):
    pass


class FakeSnapshotSurface:
    def __init__(self, crash_at: ManualSnapshotBoundary | None = None) -> None:
        self.now = NOW
        self.crash_at = crash_at
        self.prepared = 0
        self.committed: list[CommittedManualSnapshot] = []

    def clock(self) -> datetime:
        current = self.now
        self.now += timedelta(seconds=1)
        return current

    def prepare(self, reference: UpdateAttemptRef) -> ManualSnapshotCandidate:
        self.prepared += 1
        return ManualSnapshotCandidate(
            payload={"headline": "bounded", "updateAttemptRef": reference.model_dump(mode="json")},
            updateAttemptRef=reference,
        )

    def save(self, candidate: ManualSnapshotCandidate) -> CommittedManualSnapshot:
        snapshot = CommittedManualSnapshot(
            snapshotId=f"mss_{len(self.committed) + 1}",
            savedAt=self.clock(),
            updateAttemptRef=candidate.updateAttemptRef,
        )
        self.committed.append(snapshot)
        return snapshot

    def hook(self, boundary: ManualSnapshotBoundary) -> None:
        if boundary is self.crash_at:
            raise SimulatedCrash(boundary)

    def adapters(self) -> ManualLifecycleAdapters:
        return ManualLifecycleAdapters(self.clock, self.prepare, self.save, self.hook)


class SqliteSnapshotSurface(FakeSnapshotSurface):
    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = db_path

    def prepare(self, reference: UpdateAttemptRef) -> ManualSnapshotCandidate:
        payload = {
            "id": "mss_sqlite",
            "asOf": "2026-07-17T03:00:01Z",
            "headline": "시장 상태",
            "oneLineSummary": "선별적 위험선호가 이어진다.",
            "actionPosture": "추격보다 확인",
            "keyDrivers": [{"title": "금리", "summary": "상단을 제한한다."}],
            "watchItems": ["금리"],
            "counterEvidence": ["실적 상향은 위험선호를 지지한다."],
            "sourceRefs": [{"id": "rss:1", "title": "Rates", "source": "Reuters"}],
            "updateAttemptRef": reference.model_dump(mode="json"),
        }
        return ManualSnapshotCandidate(payload=payload, updateAttemptRef=reference)

    def save(self, candidate: ManualSnapshotCandidate) -> CommittedManualSnapshot:
        saved = save_market_state_snapshot(self.db_path, candidate.payload)
        return CommittedManualSnapshot(
            snapshotId=str(saved["id"]),
            savedAt=datetime.fromisoformat(str(saved["asOf"]).replace("Z", "+00:00")),
            updateAttemptRef=candidate.updateAttemptRef,
        )


def request(scope: AttemptScope = AttemptScope.GLOBAL) -> ManualSnapshotRequest:
    return ManualSnapshotRequest(scope=scope, inputWatermark="2026-07-17T02:00:00Z")


@pytest.mark.parametrize(
    "watermark",
    [
        "2026-07-17T02:00:00+00:00",
        "2026-99-99T99:99:99Z",
        "2026-02-29T03:00:00Z",
    ],
)
def test_manual_request_rejects_invalid_input_watermark(watermark: str) -> None:
    with pytest.raises(ValidationError):
        ManualSnapshotRequest(
            scope=AttemptScope.US,
            inputWatermark=watermark,
        )


def test_manual_running_to_success_embeds_complete_reference(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    surface = FakeSnapshotSurface()

    result = ManualSnapshotLifecycle(store, surface.adapters()).run(request())

    assert result.attempt.status is AttemptStatus.SUCCESS
    assert result.attempt.snapshotId == result.snapshot.snapshotId
    assert result.snapshot.updateAttemptRef == result.running.reference()
    assert result.snapshot.updateAttemptRef.jobId is None
    assert result.snapshot.updateAttemptRef.operationId is None


def test_manual_lifecycle_persists_exact_reference_in_snapshot_sqlite(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    db_path = tmp_path / "market-memory.sqlite3"
    surface = SqliteSnapshotSurface(db_path)

    result = ManualSnapshotLifecycle(store, surface.adapters()).run(request(AttemptScope.US))
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM market_state_snapshots WHERE snapshot_id = ?",
            (result.snapshot.snapshotId,),
        ).fetchone()
    payload = json.loads(row[0])

    assert payload["updateAttemptRef"] == result.running.reference().model_dump(mode="json")
    assert store.get(result.running.id).status is AttemptStatus.SUCCESS


def test_pre_snapshot_crash_recovers_failed_interrupted_at_recovery_now(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    surface = FakeSnapshotSurface(crash_at=ManualSnapshotBoundary.BEFORE_SNAPSHOT_SAVE)
    with pytest.raises(SimulatedCrash):
        ManualSnapshotLifecycle(store, surface.adapters()).run(request(AttemptScope.US))
    recovery_now = NOW + timedelta(hours=1)

    state = recover_manual_attempts(store, tuple(surface.committed), recovery_now)

    attempt = state.attempts[0]
    assert attempt.status is AttemptStatus.FAILED
    assert attempt.finishedAt == recovery_now
    assert attempt.errorCode == "interrupted"


def test_post_snapshot_crash_recovers_receipt_free_success(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    surface = FakeSnapshotSurface(crash_at=ManualSnapshotBoundary.AFTER_SNAPSHOT_SAVE)
    with pytest.raises(SimulatedCrash):
        ManualSnapshotLifecycle(store, surface.adapters()).run(request(AttemptScope.KR))
    committed = surface.committed[0]

    state = recover_manual_attempts(store, tuple(surface.committed), NOW + timedelta(hours=1))

    attempt = state.attempts[0]
    assert attempt.status is AttemptStatus.SUCCESS
    assert attempt.finishedAt == committed.savedAt
    assert attempt.snapshotId == committed.snapshotId


def test_missing_attempt_is_reconstructed_from_valid_manual_reference(tmp_path: Path) -> None:
    source = AttemptStore(tmp_path / "source.json")
    running = source.start(
        request(AttemptScope.US).to_attempt_start(NOW),
        attempt_id="msa_12345678-1234-4234-8234-123456789abc",
    )
    committed = CommittedManualSnapshot(
        snapshotId="mss_reconstruct",
        savedAt=NOW + timedelta(seconds=1),
        updateAttemptRef=running.reference(),
    )
    target = AttemptStore(tmp_path / "target.json")

    state = recover_manual_attempts(target, (committed,), NOW + timedelta(hours=1))

    assert state.attempts[0].id == running.id
    assert state.attempts[0].status is AttemptStatus.SUCCESS


def test_job_snapshot_is_ignored_before_manual_timestamp_validation(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    reference = UpdateAttemptRef(
        id="msa_12345678-1234-4234-8234-123456789abc",
        scope=AttemptScope.GLOBAL,
        mode=AttemptMode.COMBINED_JOB,
        jobId="job_12345678-1234-4234-8234-123456789abc",
        operationId="op_market_memory_update",
        startedAt=NOW + timedelta(milliseconds=20),
        inputWatermark=None,
    )
    committed = CommittedManualSnapshot(
        snapshotId="mss_combined",
        savedAt=NOW,
        updateAttemptRef=reference,
    )

    state = recover_manual_attempts(store, (committed,), NOW + timedelta(hours=1))

    assert state.attempts == ()


def test_mismatched_reference_fails_closed_without_rewriting_store(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    running = store.start(request(AttemptScope.US).to_attempt_start(NOW))
    mismatched = running.reference().model_copy(update={"scope": AttemptScope.KR})
    committed = CommittedManualSnapshot(
        snapshotId="mss_wrong",
        savedAt=NOW + timedelta(seconds=1),
        updateAttemptRef=mismatched,
    )
    before = store.path.read_bytes()

    with pytest.raises(ManualSnapshotRepairRequiredError):
        recover_manual_attempts(store, (committed,), NOW + timedelta(hours=1))

    assert store.path.read_bytes() == before


def test_corrupt_attempt_store_stops_before_snapshot_preparation(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    store.path.write_text("{broken", encoding="utf-8")
    surface = FakeSnapshotSurface()

    with pytest.raises(AttemptStoreUnavailableError, match="attempt_store_unavailable"):
        ManualSnapshotLifecycle(store, surface.adapters()).run(request())

    assert surface.prepared == 0


def test_rss_and_index_prerequisite_automation_create_no_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        automation_service,
        "import_rssarchive",
        lambda **_kwargs: calls.append("rss") or {"ok": True},
    )
    monkeypatch.setattr(
        automation_service,
        "run_rss_market_memory_update",
        lambda: calls.append("index-memory") or {"ok": True},
    )
    monkeypatch.setattr(automation_service, "default_generation_mode", lambda: "rules")
    monkeypatch.setattr(automation_service, "_append_run", lambda _row: None)
    attempt_path = tmp_path / "market-state-update-attempts.json"

    automation_service.run_automation_once("briefingPrerequisites")

    assert calls == ["rss", "index-memory"]
    assert not attempt_path.exists()


def test_empty_recovery_is_read_only(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")

    state = recover_manual_attempts(store, (), NOW)

    assert state.attempts == ()
    assert not store.path.exists()


def test_recovery_is_idempotent_after_pre_and_post_snapshot_interruptions(tmp_path: Path) -> None:
    pre_store = AttemptStore(tmp_path / "pre.json")
    pre_store.start(request().to_attempt_start(NOW))
    recover_manual_attempts(pre_store, (), NOW + timedelta(seconds=5))
    pre_bytes = pre_store.path.read_bytes()
    recover_manual_attempts(pre_store, (), NOW + timedelta(seconds=10))
    post_store = AttemptStore(tmp_path / "post.json")
    running = post_store.start(request().to_attempt_start(NOW))
    snapshot = CommittedManualSnapshot(
        snapshotId="mss_repeat",
        savedAt=NOW + timedelta(seconds=1),
        updateAttemptRef=running.reference(),
    )
    recover_manual_attempts(post_store, (snapshot,), NOW + timedelta(seconds=5))
    post_bytes = post_store.path.read_bytes()
    recover_manual_attempts(post_store, (snapshot,), NOW + timedelta(seconds=10))

    assert pre_store.path.read_bytes() == pre_bytes
    assert post_store.path.read_bytes() == post_bytes


def test_stale_recovery_now_fails_closed(tmp_path: Path) -> None:
    store = AttemptStore(tmp_path / "attempts.json")
    store.start(request().to_attempt_start(NOW))
    before = store.path.read_bytes()

    with pytest.raises(ManualSnapshotRepairRequiredError):
        recover_manual_attempts(store, (), NOW - timedelta(seconds=1))

    assert store.path.read_bytes() == before


def test_snapshot_prompt_asks_for_every_product_market():
    """프롬프트가 세 시장만 요구하면 Agent 경로는 유럽·일본 view를 아예 쓰지 않는다.

    2026-08-06 저장본이 그랬다: 백엔드 scope는 네 시장인데 프롬프트가 overall/us/kr만
    요구해서 agent_authored 스냅샷에 europe/jp가 없었다.
    """
    from features.market_memory.snapshot import MARKET_VIEW_KEYS, MARKET_STATE_SNAPSHOT_PROMPT

    for key in MARKET_VIEW_KEYS:
        assert f"marketViews.{key}" in MARKET_STATE_SNAPSHOT_PROMPT, key
