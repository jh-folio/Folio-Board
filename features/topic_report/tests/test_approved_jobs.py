from __future__ import annotations

from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from features.common.shared_jobs_schema import JobStatus
from features.common.job_json_producers import JobJsonProducers
from features.topic_report import approved_jobs as jobs_module
from features.topic_report.approval_store import ApprovalStore, ApprovalStoreRuntime
from features.topic_report.approved_generation import ApprovedGenerationOutcome
from features.topic_report.approved_jobs import ApprovedTopicJobs


class HoldingExecutor:
    def submit(self, *_args, **_kwargs):
        return Future()


@pytest.mark.parametrize(
    (
        "requested_mode",
        "adapter",
        "confirmed_zero",
        "expected_kind",
        "expected_generation_mode",
        "expected_attempted_engine",
    ),
    [
        ("direct", "auto", False, "topic_report", "rules", "none"),
        ("cli", "codex", False, "agent_bridge", "llm_cli", "cli"),
        ("cli", "codex", True, "agent_bridge", "rules", "none"),
    ],
)
def test_queued_job_kind_preserves_execution_entrypoint(
    tmp_path: Path,
    requested_mode: str,
    adapter: str,
    confirmed_zero: bool,
    expected_kind: str,
    expected_generation_mode: str,
    expected_attempted_engine: str,
) -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    approvals = ApprovalStore(
        ApprovalStoreRuntime(
            path=tmp_path / "topic-plan-approvals.json",
            clock=lambda: now,
            entropy=lambda size: bytes(size),
            uuidFactory=lambda: UUID("12345678-1234-4567-9234-567812345678"),
        )
    )
    scheduler = ApprovedTopicJobs(
        tmp_path,
        approvals,
        clock=lambda: now,
        executor=HoldingExecutor(),
    )

    job = scheduler.queued_job(
        requested_mode=requested_mode,
        adapter=adapter,
        confirmed_zero=confirmed_zero,
    )

    assert job.kind.value == expected_kind
    assert job.taskType.value == "topic_report"
    assert job.requestedMode.value == requested_mode
    assert job.generationMode.value == expected_generation_mode
    assert job.attemptedEngine.value == expected_attempted_engine


def test_cancel_requested_before_commit_writes_no_report(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    approvals = ApprovalStore(
        ApprovalStoreRuntime(
            path=tmp_path / "topic-plan-approvals.json",
            clock=lambda: now,
            entropy=lambda size: bytes(size),
            uuidFactory=lambda: UUID("12345678-1234-4567-9234-567812345678"),
        )
    )
    scheduler = ApprovedTopicJobs(
        tmp_path,
        approvals,
        clock=lambda: now,
        executor=HoldingExecutor(),
    )
    job = scheduler.queued_job(
        requested_mode="direct",
        adapter="auto",
        confirmed_zero=False,
    )
    scheduler.store.add(job)
    scheduler.lifecycle.set_private(job.id, {"canary": "PRIVATE_CANCEL_CANARY"})

    def cancel_during_generation(_command, *, job_id, **_kwargs):
        scheduler.store.transition(job_id, JobStatus.CANCEL_REQUESTED)
        return ApprovedGenerationOutcome(
            report={},
            attemptedEngine="api",
            finalEngine="api",
            fallbackReason=None,
            adapter="openai_api",
            generationMode="llm_api",
            mode="generate",
        )

    monkeypatch.setattr(jobs_module, "build_approved_report", cancel_during_generation)
    scheduler._run(job.id, object())

    terminal = scheduler.store.get(job.id)
    assert terminal is not None and terminal.status is JobStatus.CANCELLED
    assert terminal.artifactRefs == []
    assert not list((tmp_path / "topic-reports").glob("*.json"))
    assert not list((tmp_path / "job-staging").rglob("*.json"))
    durable = (tmp_path / "jobs-v2.json").read_text(encoding="utf-8")
    assert "PRIVATE_CANCEL_CANARY" not in durable


def test_cancel_after_staging_discards_bundle_and_writes_no_report(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    approvals = ApprovalStore(
        ApprovalStoreRuntime(
            path=tmp_path / "topic-plan-approvals.json",
            clock=lambda: now,
            entropy=lambda size: bytes(size),
            uuidFactory=lambda: UUID("12345678-1234-4567-9234-567812345678"),
        )
    )
    scheduler = ApprovedTopicJobs(tmp_path, approvals, clock=lambda: now, executor=HoldingExecutor())
    job = scheduler.queued_job(requested_mode="direct", adapter="auto", confirmed_zero=False)
    scheduler.store.add(job)
    scheduler.lifecycle.set_private(job.id, {"canary": "PRIVATE_STAGED_CANCEL"})
    report = {
        "date": "2026-07-16",
        "topicKey": "custom",
        "topicLabel": "Synthetic",
        "title": "Synthetic",
        "generatedAt": "2026-07-16T00:00:00Z",
        "markdown": "# Synthetic",
        "sources": [],
    }
    outcome = ApprovedGenerationOutcome(
        report=report,
        attemptedEngine="api",
        finalEngine="api",
        fallbackReason=None,
        adapter="openai_api",
        generationMode="llm_api",
        mode="generate",
    )
    monkeypatch.setattr(jobs_module, "build_approved_report", lambda *_args, **_kwargs: outcome)
    original_stage = JobJsonProducers.stage_topic

    def cancel_after_stage(producer, staged_job, request):
        bundle = original_stage(producer, staged_job, request)
        scheduler.store.transition(staged_job.id, JobStatus.CANCEL_REQUESTED)
        return bundle

    monkeypatch.setattr(JobJsonProducers, "stage_topic", cancel_after_stage)
    scheduler._run(job.id, object())

    terminal = scheduler.store.get(job.id)
    assert terminal is not None and terminal.status is JobStatus.CANCELLED
    assert not list((tmp_path / "topic-reports").glob("*.json"))
    assert not list((tmp_path / "job-staging").rglob("*.json"))
    assert "PRIVATE_STAGED_CANCEL" not in (tmp_path / "jobs-v2.json").read_text(encoding="utf-8")
