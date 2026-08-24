"""Startup recovery for validated Deep Research candidates.

Only a still-running topic-report job with an owner-scoped, hash-verified accepted
candidate may be completed from a checkpoint. Cancellation always wins.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from features.common.job_json_producer_types import ReportJobRequest
from features.common.job_json_producers import JobJsonProducers
from features.common.quality_generation.candidate_store import CandidateStore
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_schema import JobStatus, TaskType
from features.common.shared_jobs_store import SharedJobStore


def recover_deep_candidates_startup(
    data_root: Path,
    store: SharedJobStore,
    lifecycle: JobPrivateLifecycle,
    *,
    clock: Callable[[], datetime],
) -> list[str]:
    recovered: list[str] = []
    candidates = CandidateStore(data_root / "job-context")
    producer = JobJsonProducers(data_root, clock=clock)
    for job in store.load().jobs:
        if job.taskType is not TaskType.TOPIC_REPORT or job.status is not JobStatus.RUNNING:
            continue
        try:
            _recover_one(job, store, lifecycle, candidates, producer, recovered)
        except Exception:  # noqa: BLE001 - 체크포인트 하나가 기동·나머지 복구를 막으면 안 된다
            continue
    return recovered


def _recover_one(job, store, lifecycle, candidates, producer, recovered) -> None:
    checkpoint = candidates.latest_accepted(job.id)
    if checkpoint is None:
        return
    current = store.get(job.id)
    if current is None or current.status is not JobStatus.RUNNING:
        return
    report = dict(checkpoint.report)
    if report.get("deepResearch") is not True and not bool(
        ((report.get("evidencePackSummary") or {}).get("deepResearch") or {}).get("enabled")
    ):
        return
    report["id"] = checkpoint.reportId
    provenance = dict(report.get("executionProvenance") or {})
    provenance.update(
        {
            "completedFromCheckpoint": True,
            "recoveredCandidateIndex": checkpoint.candidateIndex,
        }
    )
    report["executionProvenance"] = provenance
    terminal = {
        "artifactId": checkpoint.reportId,
        "reportId": checkpoint.reportId,
        "date": str(report.get("date") or ""),
        "title": str(report.get("title") or ""),
    }
    bundle = producer.stage_topic(
        current,
        ReportJobRequest(report=report, terminal_result=terminal),
    )
    # A cancellation that reached the store between discovery and staging wins.
    staged = store.get(job.id)
    if staged is not None and staged.status is JobStatus.CANCEL_REQUESTED:
        producer.workspace.discard(bundle)
        lifecycle.terminalize(store, job.id, JobStatus.CANCELLED)
        return
    producer.workspace.commit(bundle, store, lifecycle)
    recovered.append(job.id)


__all__ = ["recover_deep_candidates_startup"]
