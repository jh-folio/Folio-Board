from __future__ import annotations

from dataclasses import dataclass
from typing import Final, assert_never

from features.common.shared_jobs_completion import ArtifactCompletionProof
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_schema import (
    ArtifactProjection,
    CancelledProjection,
    CompanionProjection,
    CommitIntent,
    ErrorCode,
    ExpectedArtifact,
    FailedProjection,
    IndexProjection,
    JobStatus,
    ResultProjection,
    RssProjection,
    SetupProjection,
    SharedJob,
    StorageKind,
    TaskType,
)
from features.common.shared_jobs_store import SharedJobStore


SQL_TASKS: Final = frozenset(
    {
        TaskType.THESIS_DELTA,
        TaskType.MARKET_MEMORY_LLM,
        TaskType.MARKET_STATE_SNAPSHOT,
        TaskType.MARKET_MEMORY_UPDATE,
    }
)
SQL_ARTIFACT_TYPES: Final = {
    TaskType.THESIS_DELTA: frozenset({"thesis_delta"}),
    TaskType.MARKET_MEMORY_LLM: frozenset({"market_memory_batch"}),
    TaskType.MARKET_STATE_SNAPSHOT: frozenset({"market_state_snapshot"}),
    TaskType.MARKET_MEMORY_UPDATE: frozenset(
        {"market_memory_batch", "market_state_snapshot"}
    ),
}


@dataclass(frozen=True, slots=True)
class SqlJobLifecycleError(Exception):
    code: str

    def __str__(self) -> str:
        return self.code


class SqlJobLifecycle:
    def __init__(self, store: SharedJobStore, private: JobPrivateLifecycle) -> None:
        self._store = store
        self._private = private
        self._commit_stages: dict[str, tuple[object | None, str | None]] = {}

    @staticmethod
    def _start_commit_stage() -> tuple[object | None, str | None]:
        from features.common.jobs import diagnostic_stage_start

        return diagnostic_stage_start("commit")

    @staticmethod
    def _end_commit_stage(recorder: object | None, stage_id: str | None) -> None:
        from features.common.jobs import diagnostic_stage_end

        diagnostic_stage_end(recorder, stage_id, "commit")

    @staticmethod
    def _fail_commit_stage(
        recorder: object | None,
        stage_id: str | None,
        error: BaseException | None,
    ) -> None:
        if error is not None:
            from features.common.jobs import diagnostic_stage_failure

            diagnostic_stage_failure(
                recorder,
                error,
                stage_id=stage_id,
                stage_code="commit" if stage_id is not None else None,
                boundary="save",
            )
        SqlJobLifecycle._end_commit_stage(recorder, stage_id)

    def _discard_commit_stage(self, job_id: str, error: BaseException | None = None) -> None:
        recorder, stage_id = self._commit_stages.pop(job_id, (None, None))
        self._fail_commit_stage(recorder, stage_id, error)

    def claim(
        self,
        job_id: str,
        operation_id: str,
        expected_artifacts: tuple[ExpectedArtifact, ...],
        terminal_projection: ResultProjection,
    ) -> CommitIntent:
        job = self._store.get(job_id)
        if job is None:
            raise SqlJobLifecycleError("job_not_found")
        if job.taskType not in SQL_TASKS:
            raise SqlJobLifecycleError("sql_job_task_invalid")
        if not operation_id or operation_id.strip() != operation_id:
            raise SqlJobLifecycleError("operation_id_required")
        if not expected_artifacts or any(
            artifact.storage is not StorageKind.SQLITE for artifact in expected_artifacts
        ):
            raise SqlJobLifecycleError("sqlite_artifacts_required")
        ordered = sorted(
            expected_artifacts,
            key=lambda artifact: (artifact.storage.value, artifact.type, artifact.id),
        )
        if {artifact.type for artifact in ordered} != SQL_ARTIFACT_TYPES[job.taskType] or len(
            ordered
        ) != len(SQL_ARTIFACT_TYPES[job.taskType]):
            raise SqlJobLifecycleError("sql_artifact_set_invalid")
        by_type = {artifact.type: artifact for artifact in ordered}
        match terminal_projection:
            case ArtifactProjection(artifactType=artifact_type, artifactId=artifact_id):
                if artifact_type != job.taskType.value:
                    raise SqlJobLifecycleError("sql_projection_task_invalid")
                memory_id = by_type.get("market_memory_batch")
                snapshot_id = by_type.get("market_state_snapshot")
                thesis_id = by_type.get("thesis_delta")
                expected_id = (
                    thesis_id.id
                    if thesis_id is not None
                    else snapshot_id.id
                    if memory_id is None and snapshot_id is not None
                    else job.id
                )
                if (
                    artifact_id != expected_id
                    or memory_id is not None and memory_id.id != job.id
                    or snapshot_id is not None
                    and terminal_projection.snapshotId != snapshot_id.id
                ):
                    raise SqlJobLifecycleError("sql_projection_linkage_invalid")
            case (
                CancelledProjection()
                | CompanionProjection()
                | FailedProjection()
                | IndexProjection()
                | RssProjection()
                | SetupProjection()
            ):
                raise SqlJobLifecycleError("sql_projection_task_invalid")
            case unreachable:
                assert_never(unreachable)
        intent = CommitIntent(
            operationId=operation_id,
            expectedArtifacts=ordered,
            terminalProjection=terminal_projection,
        )
        recorder, stage_id = self._start_commit_stage()
        try:
            self._store.claim_committing(job_id, intent)
        except Exception as error:
            self._fail_commit_stage(recorder, stage_id, error)
            raise
        self._commit_stages[job_id] = (recorder, stage_id)
        return intent

    def job(self, job_id: str) -> SharedJob | None:
        return self._store.get(job_id)

    def complete(
        self,
        job_id: str,
        proof: ArtifactCompletionProof,
    ) -> None:
        # The SQL receipt/proof has been verified by the producer.  Close its
        # concrete stage before private cleanup and terminal authority invoke
        # the observer callback.
        self._discard_commit_stage(job_id)
        self._private.complete_artifact(
            self._store,
            job_id,
            proof,
        )

    def fail_commit(self, job_id: str, error: BaseException | None = None) -> None:
        self._discard_commit_stage(job_id, error)
        self._private.terminalize(
            self._store,
            job_id,
            JobStatus.FAILED_COMMIT,
            error_code=ErrorCode.SAVE_FAILED,
        )

    def fail_run(self, job_id: str, error: BaseException | None = None) -> None:
        self._discard_commit_stage(job_id, error)
        self._private.terminalize(
            self._store,
            job_id,
            JobStatus.FAILED,
            error_code=ErrorCode.VALIDATION_FAILED,
        )

    def fail_recovery(self, job_id: str) -> None:
        self._discard_commit_stage(job_id)
        self._private.terminalize_recovery(
            self._store,
            job_id,
            JobStatus.FAILED_COMMIT_RECOVERY,
        )


__all__ = [
    "SQL_ARTIFACT_TYPES",
    "SQL_TASKS",
    "SqlJobLifecycle",
    "SqlJobLifecycleError",
]
