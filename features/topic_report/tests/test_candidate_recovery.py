from __future__ import annotations

from datetime import UTC, datetime

from features.common.quality_generation.candidate_store import CandidateStore
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import JobStatus
from features.common.shared_jobs_store import SharedJobStore
from features.topic_report.candidate_recovery import recover_deep_candidates_startup


NOW = datetime(2026, 8, 24, tzinfo=UTC)


def _running(tmp_path):
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=lambda: NOW)
    lifecycle = JobPrivateLifecycle(tmp_path / "job-context", clock=lambda: NOW)
    job = new_shared_job(
        kind="topic_report", task_type="topic_report", generation_mode="llm_api",
        adapter="openai_api", requested_mode="direct", mode="generate",
        attempted_engine="api", clock=lambda: NOW,
    )
    store.add(job)
    store.transition(job.id, JobStatus.RUNNING)
    lifecycle.set_private(job.id, {"approvedRequest": {"deepResearch": True}})
    return store, lifecycle, job


def _report(report_id: str) -> dict:
    return {
        "id": report_id,
        "saved": False,
        "date": "2026-08-24",
        "generatedAt": "2026-08-24T00:00:00Z",
        "title": "Deep report",
        "topicKey": "custom",
        "topicLabel": "Deep report",
        "deepResearch": True,
        "markdown": "# Deep report\n\nValidated body",
        "executionProvenance": {},
    }


def test_startup_commits_latest_validated_candidate_once(tmp_path) -> None:
    store, lifecycle, job = _running(tmp_path)
    report_id = "2026-08-24-custom-deep"
    CandidateStore(tmp_path / "job-context").write(
        job.id, 0, report_id=report_id, accepted=True, validation={"valid": True},
        provenance={"pass": 0}, report=_report(report_id),
    )

    recovered = recover_deep_candidates_startup(tmp_path, store, lifecycle, clock=lambda: NOW)

    assert recovered == [job.id]
    assert store.get(job.id).status is JobStatus.DONE
    saved_path = next((tmp_path / "topic-reports").glob(f"*_{report_id}.json"))
    saved = saved_path.read_text(encoding="utf-8")
    assert '"completedFromCheckpoint": true' in saved
    assert recover_deep_candidates_startup(tmp_path, store, lifecycle, clock=lambda: NOW) == []


def test_startup_does_not_commit_rejected_candidate(tmp_path) -> None:
    store, lifecycle, job = _running(tmp_path)
    report_id = "2026-08-24-custom-deep"
    CandidateStore(tmp_path / "job-context").write(
        job.id, 0, report_id=report_id, accepted=False, validation={"valid": False},
        provenance={"pass": 0}, report=_report(report_id),
    )

    assert recover_deep_candidates_startup(tmp_path, store, lifecycle, clock=lambda: NOW) == []
    assert store.get(job.id).status is JobStatus.RUNNING
    assert not list((tmp_path / "topic-reports").glob(f"*_{report_id}.json"))
