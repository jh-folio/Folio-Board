from __future__ import annotations

import sqlite3

from features.common.canonical_json import JsonValue
from features.common.shared_jobs_completion import (
    ArtifactCompletionProof,
    ArtifactCompletionSource,
    _mint_artifact_completion_proof,
)
from features.common.shared_jobs_projection import project_terminal_result
from features.common.shared_jobs_schema import ExpectedArtifact, JobStatus, SharedJob, StorageKind, TaskType
from features.common.sqlite_receipts import ReceiptVerificationError
from features.common.sql_job_lifecycle import SqlJobLifecycle, SqlJobLifecycleError
from features.market_memory.attempt_store import (
    AttemptErrorCode,
    AttemptMode,
    AttemptStart,
    MarketStateAttempt,
)
from features.market_memory.graph_plan import prepare_graph_plan
from features.market_memory.job_writes import (
    commit_combined_update,
    commit_memory_batch,
    commit_snapshot_update,
    prepare_combined_update,
    prepare_snapshot_update,
    reconcile_snapshot_attempt,
    recover_combined_update,
    recover_memory_batch,
    recover_snapshot_update,
)
from features.market_memory.sql_job_recovery import recover_market_sql_job
from features.market_memory.sql_job_types import (
    CombinedMarketJobRequest,
    CombinedMarketJobResult,
    MarketMemoryJobRequest,
    MarketMemoryJobResult,
    MarketSqlJobRuntime,
    MarketStateJobRequest,
    MarketStateJobResult,
)


def _running_job(runtime: MarketSqlJobRuntime, job_id: str, task_type: TaskType) -> SharedJob:
    job = runtime.lifecycle.job(job_id)
    if job is None:
        raise SqlJobLifecycleError("job_not_found")
    if job.taskType is not task_type or job.status is not JobStatus.RUNNING:
        raise SqlJobLifecycleError("market_job_state_invalid")
    return job


def _completion_proof(
    lifecycle: SqlJobLifecycle,
    job_id: str,
    verified_projection: dict[str, JsonValue],
) -> ArtifactCompletionProof:
    job = lifecycle.job(job_id)
    if job is None or job.status is not JobStatus.COMMITTING or job.commitIntent is None:
        raise SqlJobLifecycleError("committing_job_required")
    if verified_projection != job.commitIntent.terminalProjection.model_dump(mode="json"):
        raise ReceiptVerificationError("receipt_intent_projection_mismatch")
    return _mint_artifact_completion_proof(job, ArtifactCompletionSource.SQLITE)


def _attempt(
    runtime: MarketSqlJobRuntime,
    request: MarketStateJobRequest | CombinedMarketJobRequest,
    mode: AttemptMode,
) -> MarketStateAttempt:
    return runtime.attempts.start(
        AttemptStart(
            scope=request.scope,
            mode=mode,
            jobId=request.job_id,
            operationId=request.operation_id,
            startedAt=request.started_at,
            inputWatermark=request.input_watermark,
        )
    )


def _fail_snapshot_commit(
    runtime: MarketSqlJobRuntime,
    job_id: str,
    attempt_id: str,
    error: BaseException | None = None,
) -> None:
    try:
        runtime.attempts.fail(attempt_id, runtime.clock(), AttemptErrorCode.SAVE_FAILED)
    finally:
        runtime.lifecycle.fail_commit(job_id, error)


def _fail_snapshot_run(
    runtime: MarketSqlJobRuntime,
    job_id: str,
    attempt_id: str,
    error: BaseException | None = None,
) -> None:
    try:
        runtime.attempts.fail(attempt_id, runtime.clock(), AttemptErrorCode.VALIDATION_FAILED)
    finally:
        runtime.lifecycle.fail_run(job_id, error)


def run_market_memory_job(
    connection: sqlite3.Connection,
    runtime: MarketSqlJobRuntime,
    request: MarketMemoryJobRequest,
) -> MarketMemoryJobResult:
    job = _running_job(runtime, request.job_id, TaskType.MARKET_MEMORY_LLM)
    try:
        prepared = prepare_graph_plan(connection, request.entries, request.prepared_at)
    except (sqlite3.Error, ReceiptVerificationError) as error:
        runtime.lifecycle.fail_run(request.job_id, error)
        raise
    projection = project_terminal_result(
        job,
        JobStatus.DONE,
        {"artifactId": request.job_id, "savedCount": prepared.saved_count},
    )
    runtime.lifecycle.claim(
        request.job_id,
        request.operation_id,
        (
            ExpectedArtifact(
                storage=StorageKind.SQLITE,
                type="market_memory_batch",
                id=request.job_id,
                baseHash=prepared.graph_base_hash,
                baseMarker=None,
                targetRevision=None,
                targetHash=prepared.target_hash,
            ),
        ),
        projection,
    )
    try:
        commit_memory_batch(
            connection,
            prepared,
            job_id=request.job_id,
            operation_id=request.operation_id,
            terminal_projection=projection.model_dump(mode="json"),
            created_at=request.prepared_at,
        )
        verified = recover_memory_batch(
            connection,
            prepared,
            request.job_id,
            request.operation_id,
        )
        proof = _completion_proof(runtime.lifecycle, request.job_id, verified)
    except (sqlite3.Error, ReceiptVerificationError) as error:
        runtime.lifecycle.fail_commit(request.job_id, error)
        raise
    runtime.lifecycle.complete(request.job_id, proof)
    return MarketMemoryJobResult(prepared.saved_count, prepared.target_hash)


def run_market_state_job(
    connection: sqlite3.Connection,
    runtime: MarketSqlJobRuntime,
    request: MarketStateJobRequest,
) -> MarketStateJobResult:
    job = _running_job(runtime, request.job_id, TaskType.MARKET_STATE_SNAPSHOT)
    attempt = _attempt(runtime, request, AttemptMode.STANDALONE_JOB)
    try:
        prepared = prepare_snapshot_update(connection, request.payload, attempt.reference())
    except (sqlite3.Error, ReceiptVerificationError) as error:
        _fail_snapshot_run(runtime, request.job_id, attempt.id, error)
        raise
    projection = project_terminal_result(
        job,
        JobStatus.DONE,
        {"artifactId": prepared.snapshot_id, "snapshotId": prepared.snapshot_id},
    )
    runtime.lifecycle.claim(
        request.job_id,
        request.operation_id,
        (
            ExpectedArtifact(
                storage=StorageKind.SQLITE,
                type="market_state_snapshot",
                id=prepared.snapshot_id,
                baseHash=prepared.base_hash,
                baseMarker=None,
                targetRevision=None,
                targetHash=prepared.target_hash,
            ),
        ),
        projection,
    )
    try:
        commit_snapshot_update(
            connection,
            prepared,
            projection.model_dump(mode="json"),
            request.created_at,
        )
        verified = recover_snapshot_update(connection, prepared)
        proof = _completion_proof(runtime.lifecycle, request.job_id, verified)
    except (sqlite3.Error, ReceiptVerificationError) as error:
        _fail_snapshot_commit(runtime, request.job_id, attempt.id, error)
        raise
    reconcile_snapshot_attempt(runtime.attempts, prepared, runtime.clock())
    runtime.lifecycle.complete(request.job_id, proof)
    return MarketStateJobResult(prepared.snapshot_id, attempt.id, prepared.target_hash)


def run_combined_market_job(
    connection: sqlite3.Connection,
    runtime: MarketSqlJobRuntime,
    request: CombinedMarketJobRequest,
) -> CombinedMarketJobResult:
    job = _running_job(runtime, request.job_id, TaskType.MARKET_MEMORY_UPDATE)
    attempt = _attempt(runtime, request, AttemptMode.COMBINED_JOB)
    try:
        prepared = prepare_combined_update(
            connection,
            entries=request.entries,
            snapshot_builder=request.snapshot_builder,
            update_attempt_ref=attempt.reference(),
            prepared_at=request.prepared_at,
        )
    except (sqlite3.Error, ReceiptVerificationError) as error:
        _fail_snapshot_run(runtime, request.job_id, attempt.id, error)
        raise
    projection = project_terminal_result(
        job,
        JobStatus.DONE,
        {
            "artifactId": request.job_id,
            "savedCount": prepared.graph_plan.saved_count,
            "snapshotId": prepared.snapshot.snapshot_id,
        },
    )
    artifacts = (
        ExpectedArtifact(
            storage=StorageKind.SQLITE,
            type="market_memory_batch",
            id=request.job_id,
            baseHash=prepared.graph_plan.graph_base_hash,
            baseMarker=None,
            targetRevision=None,
            targetHash=prepared.graph_plan.target_hash,
        ),
        ExpectedArtifact(
            storage=StorageKind.SQLITE,
            type="market_state_snapshot",
            id=prepared.snapshot.snapshot_id,
            baseHash=prepared.snapshot.base_hash,
            baseMarker=None,
            targetRevision=None,
            targetHash=prepared.snapshot.target_hash,
        ),
    )
    runtime.lifecycle.claim(request.job_id, request.operation_id, artifacts, projection)
    try:
        committed = commit_combined_update(
            connection,
            prepared,
            terminal_projection=projection.model_dump(mode="json"),
            created_at=request.prepared_at,
        )
        verified = recover_combined_update(connection, prepared)
        proof = _completion_proof(runtime.lifecycle, request.job_id, verified)
    except (sqlite3.Error, ReceiptVerificationError) as error:
        _fail_snapshot_commit(runtime, request.job_id, attempt.id, error)
        raise
    reconcile_snapshot_attempt(runtime.attempts, prepared.snapshot, runtime.clock())
    runtime.lifecycle.complete(request.job_id, proof)
    return CombinedMarketJobResult(
        committed.saved_count,
        prepared.snapshot.snapshot_id,
        attempt.id,
    )


__all__ = [
    "CombinedMarketJobRequest",
    "CombinedMarketJobResult",
    "MarketMemoryJobRequest",
    "MarketMemoryJobResult",
    "MarketSqlJobRuntime",
    "MarketStateJobRequest",
    "MarketStateJobResult",
    "run_combined_market_job",
    "run_market_memory_job",
    "run_market_state_job",
    "recover_market_sql_job",
]
