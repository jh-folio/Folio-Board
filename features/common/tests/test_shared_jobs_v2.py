from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from features.common import jobs
from features.common.shared_jobs_schema import (
    ArtifactProjection,
    CommitIntent,
    ExpectedArtifact,
    JobMarker,
    StorageKind,
)
from features.common.shared_jobs_store import JobCommitClaimError


NOW = datetime(2026, 7, 17, 0, 0, tzinfo=UTC)


def _clock() -> datetime:
    return NOW


def _queued(task_type: str = "companion"):
    return jobs.new_shared_job(
        kind="agent_bridge",
        task_type=task_type,
        generation_mode="llm_cli",
        adapter="codex",
        requested_mode="cli",
        mode="answer" if task_type == "companion" else "generate",
        attempted_engine="cli",
        clock=_clock,
    )


def test_shared_job_schema_rejects_unknown_fields_and_nonterminal_projection() -> None:
    # Given: a valid queued SharedJob
    job = _queued()

    # When / Then: unknown durable input and a nonterminal result are rejected.
    with pytest.raises(ValidationError):
        jobs.SharedJob.model_validate({**job.model_dump(mode="json"), "privateText": "CANARY"})
    with pytest.raises(ValidationError):
        jobs.SharedJob.model_validate(
            {**job.model_dump(mode="json"), "resultProjection": {"status": "done"}}
        )


def test_a_job_persisted_before_stage_a_timing_fields_still_validates() -> None:
    """Agent Dock Stage A added phaseCode/queueWaitMs/contextMs/cliMs/postprocessMs/totalMs.

    They must default to `None` so a job JSON written before this change (missing
    the keys entirely, not just null) keeps validating unchanged on read."""
    job = _queued()
    dumped = job.model_dump(mode="json")
    for key in ("phaseCode", "queueWaitMs", "contextMs", "cliMs", "postprocessMs", "totalMs"):
        assert key in dumped
        del dumped[key]

    restored = jobs.SharedJob.model_validate(dumped)

    assert restored.phaseCode is None
    assert restored.queueWaitMs is None
    assert restored.totalMs is None


def test_store_recovers_backup_and_fails_closed_when_both_are_corrupt(tmp_path: Path) -> None:
    # Given: a store with one valid write and then a corrupt primary
    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    written = store.add(_queued())
    store.add(_queued())
    store.path.write_text("{broken", encoding="utf-8")

    # When: the store is loaded
    recovered = store.load()

    # Then: the valid sibling backup is restored.
    assert recovered.recovered is True
    assert recovered.store_revision == written.store_revision
    assert json.loads(store.path.read_text(encoding="utf-8"))["schemaVersion"] == 2

    # Given / When / Then: corrupt primary and backup fail closed without overwrite.
    store.path.write_text("{primary", encoding="utf-8")
    store.backup.write_text("{backup", encoding="utf-8")
    before = (store.path.read_bytes(), store.backup.read_bytes())
    with pytest.raises(jobs.JobsStoreUnavailableError):
        store.load()
    assert (store.path.read_bytes(), store.backup.read_bytes()) == before


@pytest.mark.parametrize(
    ("task_type", "result", "expected_status"),
    [
        ("index", {"count": 3, "generatedAt": "2026-07-17T00:00:00Z", "incremental": True, "sqlite": "research-index.sqlite3"}, "done"),
        ("rss", {"added": 2, "total": 4, "failed": 0}, "done"),
        ("setup", {"ok": True, "adapter": "codex"}, "done"),
        ("companion", {"proposalId": None}, "done"),
        ("briefing", {"artifactId": "2026-07-17.us", "reportId": "2026-07-17.us", "date": "2026-07-17", "title": "US"}, "done"),
        ("company_analysis", {"artifactId": "SPCX:2026-07-17", "reportId": "SPCX:2026-07-17", "date": "2026-07-17", "title": "SPCX"}, "done"),
        ("topic_report", {"artifactId": "r1", "reportId": "r1", "date": "2026-07-17", "title": "Topic"}, "done"),
        ("personal_overlay", {"artifactId": "r1", "reportId": "r1"}, "done"),
        ("thesis_delta", {"artifactId": "d1"}, "done"),
        ("market_memory_llm", {"artifactId": "m1"}, "done"),
        ("market_state_snapshot", {"artifactId": "s1", "snapshotId": "s1"}, "done"),
        ("market_memory_update", {"savedCount": 2, "snapshotId": "s1"}, "done"),
        ("quality_repair", {"artifactId": "r1", "reportId": "r1", "proposalId": "a" * 32}, "done"),
        ("investment_review", {"artifactId": "2026-07-17", "reportId": "2026-07-17"}, "done"),
    ],
)
def test_projection_matrix_is_task_specific(
    task_type: str, result: dict[str, str | int | bool | None], expected_status: str
) -> None:
    # Given: a task-specific worker result
    job = _queued(task_type)
    if task_type == "market_memory_update":
        result = {**result, "artifactId": job.id}

    # When: it is projected for durable terminal storage
    projection = jobs.project_terminal_result(job, "done", result)

    # Then: the strict projection is valid and contains no unknown worker key.
    assert projection.status == expected_status
    assert "privateText" not in projection.model_dump(mode="json")


def test_transition_rules_and_retention_are_deterministic(tmp_path: Path) -> None:
    # Given: a queued job in a strict v2 store
    current = NOW
    store = jobs.SharedJobStore(
        tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=lambda: current
    )
    job = _queued()
    store.add(job)

    # When / Then: illegal transitions are rejected, legal transitions increment once.
    with pytest.raises(jobs.JobTransitionError):
        store.transition(job.id, jobs.JobStatus.DONE, result={"proposalId": None})
    running = store.transition(job.id, jobs.JobStatus.RUNNING)
    assert running.store_revision == 2
    done = store.transition(job.id, jobs.JobStatus.DONE, result={"proposalId": None})
    assert done.store_revision == 3

    # Given / When: 205 newer terminal jobs are retained at one instant.
    for _ in range(205):
        candidate = _queued()
        store.add(candidate)
        store.transition(candidate.id, jobs.JobStatus.RUNNING)
        store.transition(candidate.id, jobs.JobStatus.DONE, result={"proposalId": None})

    # Then: only the newest 200 terminal jobs survive.
    assert len(store.load().jobs) == 200


@pytest.mark.parametrize("source_status", (jobs.JobStatus.QUEUED, jobs.JobStatus.RUNNING))
def test_artifact_job_cannot_reach_done_without_commit_intent(
    tmp_path: Path,
    source_status: jobs.JobStatus,
) -> None:
    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    job = _queued("topic_report")
    store.add(job)
    if source_status is jobs.JobStatus.RUNNING:
        store.transition(job.id, source_status)
    before = store.path.read_bytes()

    with pytest.raises(jobs.JobTransitionError):
        store.transition(
            job.id,
            jobs.JobStatus.DONE,
            result={
                "artifactId": "topic-01",
                "reportId": "topic-01",
                "date": "2026-07-17",
                "title": "Topic",
            },
        )

    assert store.path.read_bytes() == before
    assert store.get(job.id).status is source_status


def test_run_job_fails_artifact_worker_that_returns_without_commit_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobs, "JOBS_PATH", tmp_path / "jobs.json")
    jobs._LIFECYCLES.clear()
    job = _queued("topic_report")
    jobs.shared_store().add(job)
    jobs.private_lifecycle().set_private(job.id, {"context": "PRIVATE_BYPASS_CANARY"})

    jobs.run_job(
        job.id,
        lambda *, progress: {
            "artifactId": "topic-01",
            "reportId": "topic-01",
            "date": "2026-07-17",
            "title": "Topic",
        },
    )

    terminal = jobs.shared_store().get(job.id)
    assert terminal is not None
    assert terminal.status is jobs.JobStatus.FAILED
    assert terminal.errorCode is jobs.ErrorCode.SAVE_FAILED
    assert terminal.commitIntent is None
    assert terminal.artifactRefs == []
    assert "PRIVATE_BYPASS_CANARY" not in (tmp_path / "jobs-v2.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("task_type", "result"),
    [
        ("briefing", {}),
        ("company_analysis", {"artifactId": "company-01", "reportId": "company-01", "date": "2026-07-17"}),
        ("topic_report", {"artifactId": "topic-01", "reportId": "topic-01", "title": "Topic"}),
        ("personal_overlay", {"artifactId": "overlay-01"}),
        ("thesis_delta", {}),
        ("market_memory_llm", {}),
        ("market_state_snapshot", {"artifactId": "snapshot-01"}),
        ("market_memory_update", {"artifactId": "not-the-job-id"}),
        ("quality_repair", {"artifactId": "repair-01"}),
        ("investment_review", {"artifactId": "2026-07-17"}),
    ],
)
def test_artifact_done_projection_rejects_missing_or_invalid_task_keys(
    task_type: str,
    result: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        jobs.project_terminal_result(_queued(task_type), jobs.JobStatus.DONE, result)


def test_equal_created_at_jobs_sort_id_ascending(tmp_path: Path) -> None:
    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    high = _queued().model_copy(update={"id": "job_00000000-0000-4000-8000-000000000002"})
    low = _queued().model_copy(update={"id": "job_00000000-0000-4000-8000-000000000001"})
    store.add(high)
    store.add(low)

    assert [job.id for job in store.merged().jobs] == [low.id, high.id]


def _artifact_intent(operation_id: str = "op-briefing-01") -> CommitIntent:
    return CommitIntent(
        operationId=operation_id,
        expectedArtifacts=[
            ExpectedArtifact(
                storage=StorageKind.GZIP_JSON,
                type="briefing_visual",
                id="2026-07-17.us",
                baseHash=None,
                baseMarker=None,
                targetRevision=None,
                targetHash="b" * 64,
            ),
            ExpectedArtifact(
                storage=StorageKind.JSON,
                type="briefing_report",
                id="2026-07-17.us",
                baseHash="a" * 64,
                baseMarker=JobMarker(jobId="prior-job", operationId="prior-operation"),
                targetRevision=2,
                targetHash="c" * 64,
            ),
        ],
        terminalProjection=ArtifactProjection(
            artifactType="briefing",
            artifactId="2026-07-17.us",
            reportId="2026-07-17.us",
            date="2026-07-17",
            title="US",
            savedCount=None,
            snapshotId=None,
            proposalId=None,
            requestedMode="cli",
            attemptedEngine="cli",
            finalEngine="cli",
            fallbackReason=None,
            adapter="codex",
            mode="generate",
        ),
    )


def test_claim_committing_persists_intent_and_sorted_exact_refs_once(tmp_path: Path) -> None:
    # Given: a running artifact-producing job with no final artifact writes.
    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    queued = _queued("briefing")
    store.add(queued)
    store.transition(queued.id, jobs.JobStatus.RUNNING)

    # When: the complete CommitIntent is claimed.
    claimed = store.claim_committing(queued.id, _artifact_intent())

    # Then: one store revision records committing, ownership, intent, and sorted refs.
    assert claimed.store_revision == 3
    current = store.get(queued.id)
    assert current is not None
    assert current.status == jobs.JobStatus.COMMITTING
    assert current.operationId == "op-briefing-01"
    assert current.commitIntent == _artifact_intent()
    assert [(ref.type, ref.id) for ref in current.artifactRefs] == [
        ("briefing_visual", "2026-07-17.us"),
        ("briefing_report", "2026-07-17.us"),
    ]


def test_claim_committing_rejects_unlisted_nonrunning_and_conflicting_owner(tmp_path: Path) -> None:
    # Given: queued/non-artifact and conflicting-operation fixtures.
    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=_clock)
    companion = _queued("companion")
    store.add(companion)
    store.transition(companion.id, jobs.JobStatus.RUNNING)
    before_unlisted = store.path.read_bytes()

    # When / Then: an unlisted task cannot enter committing or mutate the store.
    with pytest.raises(JobCommitClaimError):
        store.claim_committing(companion.id, _artifact_intent())
    assert store.path.read_bytes() == before_unlisted

    briefing = _queued("briefing")
    owned_values = briefing.model_dump(mode="json")
    owned_values["operationId"] = "owned-by-another-operation"
    owned = jobs.SharedJob.model_validate(owned_values)
    store.add(owned)
    store.transition(owned.id, jobs.JobStatus.RUNNING)
    before_conflict = store.path.read_bytes()

    with pytest.raises(JobCommitClaimError):
        store.claim_committing(owned.id, _artifact_intent())
    assert store.path.read_bytes() == before_conflict

    queued = _queued("briefing")
    store.add(queued)
    before_queued = store.path.read_bytes()
    with pytest.raises(JobCommitClaimError):
        store.claim_committing(queued.id, _artifact_intent())
    assert store.path.read_bytes() == before_queued


def test_cancelled_worker_exception_terminalizes_cancelled_and_scrubs_private_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobs, "JOBS_PATH", tmp_path / "jobs.json")
    jobs._LIFECYCLES.clear()
    job = _queued()
    jobs.shared_store().add(job)
    jobs.private_lifecycle().set_private(job.id, {"context": "PRIVATE_CANCEL_CANARY"})

    def cancelled_worker(*, progress) -> None:
        del progress
        jobs.shared_store().transition(job.id, jobs.JobStatus.CANCEL_REQUESTED)
        raise RuntimeError("worker terminated after cancellation")

    jobs.run_job(job.id, cancelled_worker)

    terminal = jobs.shared_store().get(job.id)
    assert terminal is not None
    assert terminal.status is jobs.JobStatus.CANCELLED
    assert terminal.resultProjection is not None
    assert terminal.resultProjection.status == "cancelled"
    assert "PRIVATE_CANCEL_CANARY" not in (tmp_path / "jobs-v2.json").read_text(encoding="utf-8")
    assert not (tmp_path / "job-context" / job.id).exists()


def test_legacy_jobs_accept_iso_utc_offsets_without_rewriting_legacy_file(tmp_path: Path) -> None:
    legacy_path = tmp_path / "jobs.json"
    payload = {
        "legacy-offset": {
            "id": "legacy-offset",
            "kind": "index",
            "status": "done",
            "createdAt": "2026-07-17T00:00:00.123456+00:00",
            "startedAt": "2026-07-17T00:00:01+00:00",
            "updatedAt": "2026-07-17T00:00:02+00:00",
            "finishedAt": "2026-07-17T00:00:03+00:00",
            "result": {
                "count": 1,
                "generatedAt": "2026-07-17T00:00:03+00:00",
                "incremental": True,
                "sqlite": "x",
            },
        }
    }
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")
    before = legacy_path.read_text(encoding="utf-8")

    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", legacy_path, clock=_clock)
    job = store.merged().jobs[0]

    assert job.createdAt == "2026-07-17T00:00:00.123456Z"
    assert job.startedAt == "2026-07-17T00:00:01Z"
    assert job.updatedAt == "2026-07-17T00:00:02Z"
    assert job.finishedAt == "2026-07-17T00:00:03Z"
    assert legacy_path.read_text(encoding="utf-8") == before


def test_v2_wins_identical_collision_and_reports_distinct_collision(tmp_path: Path) -> None:
    # Given: one normalized legacy job migrated into v2
    legacy_path = tmp_path / "jobs.json"
    legacy_path.write_text(
        json.dumps({"legacy-1": {"id": "legacy-1", "kind": "index", "status": "done", "createdAt": "2026-07-17T00:00:00Z", "updatedAt": "2026-07-17T00:00:00Z", "finishedAt": "2026-07-17T00:00:00Z", "result": {"count": 1, "generatedAt": "2026-07-17T00:00:00Z", "incremental": True, "sqlite": "x"}}}),
        encoding="utf-8",
    )
    store = jobs.SharedJobStore(tmp_path / "jobs-v2.json", legacy_path, clock=_clock)
    preview = store.legacy_preview()
    assert preview.migratable_jobs == 1
    store.migrate_legacy(keep_original=True)

    # When / Then: byte-identical normalized collision is skipped and v2 wins.
    assert store.legacy_preview().migratable_jobs == 0
    assert store.merged().jobs[0].id == "legacy-1"

    # Given / When / Then: a distinct exact-id collision is explicit and non-mutating.
    payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    payload["legacy-1"]["result"]["count"] = 9
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")
    before = store.path.read_bytes()
    collision = store.legacy_preview()
    assert collision.collisions[0].legacy_id == "legacy-1"
    with pytest.raises(jobs.LegacyJobCollisionError):
        store.migrate_legacy(keep_original=True)
    assert store.path.read_bytes() == before
