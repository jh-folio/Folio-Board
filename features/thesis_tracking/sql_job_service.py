from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from features.common.canonical_json import JsonValue
from features.common.shared_jobs_completion import (
    ArtifactCompletionSource,
    _mint_artifact_completion_proof,
)
from features.common.shared_jobs_projection import project_terminal_result
from features.common.shared_jobs_schema import (
    ExpectedArtifact,
    JobStatus,
    StorageKind,
    TaskType,
)
from features.common.sqlite_receipts import ReceiptVerificationError
from features.common.sql_job_lifecycle import SqlJobLifecycle, SqlJobLifecycleError
from features.thesis_tracking.job_writes import (
    commit_thesis_delta,
    prepare_thesis_delta,
    recover_thesis_delta,
    recover_thesis_receipt,
)


@dataclass(frozen=True, slots=True)
class ThesisDeltaJobRequest:
    job_id: str
    operation_id: str
    ticker: str
    generated_at: str
    delta: dict[str, JsonValue]
    created_at: str


@dataclass(frozen=True, slots=True)
class ThesisDeltaJobResult:
    delta_id: str
    target_hash: str


def deterministic_delta_id(ticker: str, generated_at: str, operation_id: str) -> str:
    raw = f"{ticker.strip().upper()}\0{generated_at}\0{operation_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def run_thesis_delta_job(
    connection: sqlite3.Connection,
    lifecycle: SqlJobLifecycle,
    request: ThesisDeltaJobRequest,
) -> ThesisDeltaJobResult:
    job = lifecycle.job(request.job_id)
    if job is None:
        raise SqlJobLifecycleError("job_not_found")
    if job.taskType is not TaskType.THESIS_DELTA or job.status is not JobStatus.RUNNING:
        raise SqlJobLifecycleError("thesis_job_state_invalid")
    delta_id = deterministic_delta_id(request.ticker, request.generated_at, request.operation_id)
    supplied = request.delta.get("deltaId")
    if supplied is not None and supplied != delta_id:
        raise SqlJobLifecycleError("delta_id_mismatch")
    delta = {**request.delta, "deltaId": delta_id, "generatedAt": request.generated_at}
    safe_result = {"artifactId": delta_id, "reportId": delta_id}
    projection = project_terminal_result(job, JobStatus.DONE, safe_result)
    try:
        prepared = prepare_thesis_delta(
            connection,
            ticker=request.ticker,
            delta=delta,
            job_id=request.job_id,
            operation_id=request.operation_id,
            terminal_projection=projection.model_dump(mode="json"),
            created_at=request.created_at,
        )
    except (sqlite3.Error, ReceiptVerificationError) as error:
        lifecycle.fail_run(request.job_id, error)
        raise
    lifecycle.claim(
        request.job_id,
        request.operation_id,
        (
            ExpectedArtifact(
                storage=StorageKind.SQLITE,
                type="thesis_delta",
                id=delta_id,
                baseHash=prepared.base_hash,
                baseMarker=None,
                targetRevision=None,
                targetHash=prepared.target_hash,
            ),
        ),
        projection,
    )
    try:
        committed = commit_thesis_delta(connection, prepared)
        verified = recover_thesis_delta(connection, prepared)
        if verified != projection.model_dump(mode="json"):
            raise ReceiptVerificationError("receipt_intent_projection_mismatch")
        committing = lifecycle.job(request.job_id)
        if committing is None:
            raise SqlJobLifecycleError("committing_job_required")
        proof = _mint_artifact_completion_proof(
            committing,
            ArtifactCompletionSource.SQLITE,
        )
    except (sqlite3.Error, ReceiptVerificationError) as error:
        lifecycle.fail_commit(request.job_id, error)
        raise
    lifecycle.complete(request.job_id, proof)
    return ThesisDeltaJobResult(committed.delta_id, committed.target_hash)


def recover_thesis_delta_job(
    connection: sqlite3.Connection,
    lifecycle: SqlJobLifecycle,
    job_id: str,
) -> JobStatus:
    job = lifecycle.job(job_id)
    if (
        job is None
        or job.taskType is not TaskType.THESIS_DELTA
        or job.status is not JobStatus.COMMITTING
        or job.commitIntent is None
    ):
        raise SqlJobLifecycleError("committing_thesis_job_required")
    artifacts = job.commitIntent.expectedArtifacts
    if (
        len(artifacts) != 1
        or artifacts[0].storage is not StorageKind.SQLITE
        or artifacts[0].type != "thesis_delta"
    ):
        raise SqlJobLifecycleError("thesis_intent_invalid")
    artifact = artifacts[0]
    try:
        projection = recover_thesis_receipt(
            connection,
            job_id=job_id,
            operation_id=job.commitIntent.operationId,
            delta_id=artifact.id,
            target_hash=artifact.targetHash,
        )
        if projection != job.commitIntent.terminalProjection.model_dump(mode="json"):
            raise ReceiptVerificationError("receipt_intent_projection_mismatch")
    except (sqlite3.Error, ReceiptVerificationError):
        lifecycle.fail_recovery(job_id)
        return JobStatus.FAILED_COMMIT_RECOVERY
    proof = _mint_artifact_completion_proof(
        job,
        ArtifactCompletionSource.SQLITE,
    )
    lifecycle.complete(job_id, proof)
    return JobStatus.DONE


__all__ = [
    "ThesisDeltaJobRequest",
    "ThesisDeltaJobResult",
    "deterministic_delta_id",
    "run_thesis_delta_job",
    "recover_thesis_delta_job",
]
