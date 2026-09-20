from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from threading import RLock

from pydantic import ValidationError

from features.common.jcs import JsonValue, sha256_hex
from features.common.shared_jobs_completion import (
    ArtifactCompletionProof,
    _validated_artifact_completion,
)
from features.common.shared_jobs_legacy import normalize_legacy_job
from features.common.shared_jobs_projection import ARTIFACT_TASKS, project_terminal_result, utc_z
from features.common.shared_jobs_schema import (
    ArtifactRef,
    CommitIntent,
    ErrorCode,
    JobStatus,
    JobsStoreFile,
    ResultProjection,
    SharedJob,
    TERMINAL_STATUSES,
)
from features.common.atomic_replace import write_bytes_atomic


@dataclass(frozen=True, slots=True)
class JobsStoreUnavailableError(Exception):
    code: str = "jobs_store_unavailable"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class JobTransitionError(Exception):
    source: JobStatus
    target: JobStatus

    def __str__(self) -> str:
        return f"invalid job transition: {self.source} -> {self.target}"


@dataclass(frozen=True, slots=True)
class LegacyJobCollisionError(Exception):
    legacy_id: str

    def __str__(self) -> str:
        return f"legacy_job_collision:{self.legacy_id}"


@dataclass(frozen=True, slots=True)
class JobCommitClaimError(Exception):
    job_id: str
    reason: str

    def __str__(self) -> str:
        return f"job_commit_claim_failed:{self.job_id}:{self.reason}"


@dataclass(frozen=True, slots=True)
class LegacyCollision:
    legacy_id: str
    reason: str = "id_collision"


@dataclass(frozen=True, slots=True)
class LegacyPreview:
    legacy_jobs: int
    migratable_jobs: int
    collisions: tuple[LegacyCollision, ...]


@dataclass(frozen=True, slots=True)
class StoreState:
    store_revision: int
    updated_at: str
    jobs: tuple[SharedJob, ...]
    recovered: bool = False


@cache
def store_lock(path: str) -> RLock:
    # Production stores live under a finite set of configured data roots. Lock
    # identity must remain stable for the process lifetime so path churn cannot
    # create two writers for one durable store.
    return RLock()


TRANSITIONS = {
    # QUEUED→FAILED는 첫 RUNNING 전이 쓰기가 실패해 잡이 시작조차 못 한 경우다.
    # 이 칸이 비어 있으면 `run_job`의 예외 처리가 JobTransitionError로 되튕기고,
    # 그때 pack은 이미 지워진 뒤라 잡이 `cleanup_blocked`에 프로세스 수명 내내
    # 남아 `/api/jobs`와 Work Log가 계속 503이 된다(§서버 재시작의 fail-closed).
    # 재시작 복구용 FAILED_RESTART로 대신하면 "서버 재시작" 메시지가 붙어
    # 원인을 잘못 말한다.
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({JobStatus.CANCEL_REQUESTED, JobStatus.COMMITTING, JobStatus.FAILED, JobStatus.DONE}),
    JobStatus.CANCEL_REQUESTED: frozenset({JobStatus.CANCELLED, JobStatus.FAILED_CANCEL}),
    JobStatus.COMMITTING: frozenset({JobStatus.FAILED_COMMIT}),
}
RECOVERY_TRANSITIONS = {
    JobStatus.QUEUED: frozenset({JobStatus.FAILED_RESTART}),
    JobStatus.RUNNING: frozenset({JobStatus.FAILED_RESTART}),
    JobStatus.CANCEL_REQUESTED: frozenset({JobStatus.FAILED_RESTART}),
    JobStatus.COMMITTING: frozenset({JobStatus.FAILED_COMMIT_RECOVERY}),
}


class SharedJobStore:
    def __init__(self, path: Path, legacy_path: Path, *, clock: Callable[[], datetime]) -> None:
        self.path = path
        self.backup = path.with_name(path.name + ".bak")
        self.legacy_path = legacy_path
        self.clock = clock
        self.lock = store_lock(str(path.resolve()))

    def _parse(self, path: Path) -> JobsStoreFile:
        try:
            return JobsStoreFile.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError, ValueError) as error:
            raise JobsStoreUnavailableError() from error

    def _replace(self, path: Path, data: bytes, suffix: str) -> None:
        try:
            write_bytes_atomic(path, data, suffix=suffix)
        except OSError as error:
            raise JobsStoreUnavailableError() from error

    def load(self) -> StoreState:
        with self.lock:
            if self.path.exists():
                try:
                    value = self._parse(self.path)
                except JobsStoreUnavailableError:
                    if not self.backup.exists():
                        raise
                    value = self._parse(self.backup)
                    self._replace(self.path, value.model_dump_json(indent=2).encode(), ".restore.tmp")
                    return StoreState(value.storeRevision, value.updatedAt, tuple(value.jobs), True)
                return StoreState(value.storeRevision, value.updatedAt, tuple(value.jobs))
            if self.backup.exists():
                value = self._parse(self.backup)
                self._replace(self.path, value.model_dump_json(indent=2).encode(), ".restore.tmp")
                return StoreState(value.storeRevision, value.updatedAt, tuple(value.jobs), True)
            return StoreState(0, "", ())

    def _retained(self, jobs: Iterable[SharedJob]) -> tuple[SharedJob, ...]:
        cutoff = self.clock().astimezone(UTC) - timedelta(days=30)
        active = [job for job in jobs if job.status not in TERMINAL_STATUSES]
        terminal = [job for job in jobs if job.status in TERMINAL_STATUSES]
        terminal.sort(key=lambda item: (item.finishedAt or item.updatedAt, item.id), reverse=True)
        recent = [job for job in terminal if datetime.fromisoformat((job.finishedAt or job.updatedAt).replace("Z", "+00:00")) >= cutoff]
        return tuple(active + recent[:200])

    def _write(self, jobs: Iterable[SharedJob], revision: int) -> StoreState:
        retained = self._retained(jobs)
        ledger = JobsStoreFile(storeRevision=revision, updatedAt=utc_z(self.clock()), jobs=list(retained))
        if self.path.exists():
            current = self._parse(self.path)
            self._replace(self.backup, current.model_dump_json(indent=2).encode(), ".tmp")
            self._parse(self.backup)
        self._replace(self.path, ledger.model_dump_json(indent=2).encode(), ".tmp")
        written = self._parse(self.path)
        return StoreState(written.storeRevision, written.updatedAt, tuple(written.jobs))

    def add(self, job: SharedJob) -> StoreState:
        with self.lock:
            state = self.load()
            if any(current.id == job.id for current in state.jobs):
                raise LegacyJobCollisionError(job.id)
            return self._write((*state.jobs, job), state.store_revision + 1)

    def get(self, job_id: str) -> SharedJob | None:
        return next((job for job in self.load().jobs if job.id == job_id), None)

    def _terminalized(
        self,
        current: SharedJob,
        target: JobStatus,
        projection: ResultProjection,
    ) -> SharedJob:
        now = utc_z(self.clock())
        values = current.model_dump(mode="json")
        values.update(
            {
                "status": target.value,
                "messageCode": target.value,
                "updatedAt": now,
                "finishedAt": now,
                "progress": 100 if target is JobStatus.DONE else current.progress,
                "errorCode": (
                    projection.errorCode.value
                    if hasattr(projection, "errorCode") and projection.errorCode is not None
                    else None
                ),
                "resultProjection": projection.model_dump(mode="json"),
                "commitIntent": None,
            }
        )
        return SharedJob.model_validate(values)

    def transition(
        self,
        job_id: str,
        target: JobStatus,
        *,
        result: Mapping[str, str | int | bool | None] | None = None,
        error_code: ErrorCode | str | None = None,
    ) -> StoreState:
        with self.lock:
            state = self.load()
            current = next((job for job in state.jobs if job.id == job_id), None)
            if current is None:
                raise KeyError(job_id)
            allowed = TRANSITIONS.get(current.status, frozenset())
            if target not in allowed:
                raise JobTransitionError(current.status, target)
            if target is JobStatus.DONE and current.taskType in ARTIFACT_TASKS:
                raise JobTransitionError(current.status, target)
            now = utc_z(self.clock())
            values = current.model_dump(mode="json")
            values.update({"status": target.value, "messageCode": target.value, "updatedAt": now})
            if target == JobStatus.RUNNING:
                values.update({"startedAt": now, "progress": 0})
            if target in TERMINAL_STATUSES:
                projection = project_terminal_result(current, target, result, error_code)
                updated = self._terminalized(current, target, projection)
            else:
                updated = SharedJob.model_validate(values)
            jobs = [updated if job.id == job_id else job for job in state.jobs]
            return self._write(jobs, state.store_revision + 1)

    def transition_recovery(
        self,
        job_id: str,
        target: JobStatus,
    ) -> StoreState:
        with self.lock:
            state = self.load()
            current = next((job for job in state.jobs if job.id == job_id), None)
            if current is None:
                raise KeyError(job_id)
            if target not in RECOVERY_TRANSITIONS.get(current.status, frozenset()):
                raise JobTransitionError(current.status, target)
            error_code = (
                ErrorCode.RESTART_INTERRUPTED
                if target is JobStatus.FAILED_RESTART
                else ErrorCode.COMMIT_RECOVERY_FAILED
            )
            projection = project_terminal_result(current, target, error_code=error_code)
            updated = self._terminalized(current, target, projection)
            rows = [updated if job.id == job_id else job for job in state.jobs]
            return self._write(rows, state.store_revision + 1)

    def complete_artifact(
        self,
        job_id: str,
        proof: ArtifactCompletionProof | object,
    ) -> StoreState:
        with self.lock:
            state = self.load()
            current = next((job for job in state.jobs if job.id == job_id), None)
            if current is None:
                raise KeyError(job_id)
            projection = _validated_artifact_completion(proof, current)
            updated = self._terminalized(current, JobStatus.DONE, projection)
            rows = [updated if job.id == job_id else job for job in state.jobs]
            return self._write(rows, state.store_revision + 1)

    def claim_committing(self, job_id: str, intent: CommitIntent) -> StoreState:
        with self.lock:
            state = self.load()
            current = next((job for job in state.jobs if job.id == job_id), None)
            if current is None:
                raise JobCommitClaimError(job_id, "not_found")
            if current.status != JobStatus.RUNNING:
                raise JobCommitClaimError(job_id, "not_running")
            if current.taskType not in ARTIFACT_TASKS:
                raise JobCommitClaimError(job_id, "task_not_registered")
            if not intent.operationId or current.operationId not in {None, intent.operationId}:
                raise JobCommitClaimError(job_id, "operation_conflict")
            expected = sorted(
                intent.expectedArtifacts,
                key=lambda item: (item.storage.value, item.type, item.id),
            )
            values = current.model_dump(mode="json")
            values.update(
                {
                    "status": JobStatus.COMMITTING.value,
                    "messageCode": JobStatus.COMMITTING.value,
                    "updatedAt": utc_z(self.clock()),
                    "operationId": intent.operationId,
                    "artifactRefs": [
                        ArtifactRef(type=item.type, id=item.id).model_dump(mode="json")
                        for item in expected
                    ],
                    "commitIntent": intent.model_dump(mode="json"),
                }
            )
            updated = SharedJob.model_validate(values)
            rows = [updated if job.id == job_id else job for job in state.jobs]
            return self._write(rows, state.store_revision + 1)

    def update_runtime(self, job_id: str, changes: Mapping[str, JsonValue]) -> StoreState:
        safe_fields = {
            "progress",
            "generationMode",
            "engine",
            "adapter",
            "requestedMode",
            "mode",
            "attemptedEngine",
            "finalEngine",
            "fallbackReason",
            "failureDetail",
            "proposalId",
            "phaseCode",
            "queueWaitMs",
            "contextMs",
            "cliMs",
            "postprocessMs",
            "totalMs",
        }
        with self.lock:
            state = self.load()
            current = next((job for job in state.jobs if job.id == job_id), None)
            if current is None:
                raise KeyError(job_id)
            values = current.model_dump(mode="json")
            values.update({key: value for key, value in changes.items() if key in safe_fields})
            values["updatedAt"] = utc_z(self.clock())
            updated = SharedJob.model_validate(values)
            rows = [updated if job.id == job_id else job for job in state.jobs]
            return self._write(rows, state.store_revision + 1)

    def mark_private_cleanup_failed(self, job_id: str) -> StoreState:
        with self.lock:
            state = self.load()
            current = next((job for job in state.jobs if job.id == job_id), None)
            if current is None:
                raise KeyError(job_id)
            if current.status in TERMINAL_STATUSES:
                raise JobTransitionError(current.status, current.status)
            values = current.model_dump(mode="json")
            values.update(
                {
                    "errorCode": ErrorCode.PRIVATE_CLEANUP_FAILED.value,
                    "updatedAt": utc_z(self.clock()),
                }
            )
            updated = SharedJob.model_validate(values)
            rows = [updated if job.id == job_id else job for job in state.jobs]
            return self._write(rows, state.store_revision + 1)

    def _legacy(self) -> tuple[SharedJob, ...]:
        if not self.legacy_path.exists():
            return ()
        try:
            raw = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise JobsStoreUnavailableError() from error
        if not isinstance(raw, dict):
            raise JobsStoreUnavailableError()
        normalized = []
        for job_id, item in raw.items():
            if not isinstance(job_id, str) or not isinstance(item, dict):
                raise JobsStoreUnavailableError()
            normalized.append(normalize_legacy_job(job_id, item, self.clock))
        return tuple(normalized)

    def merged(self) -> StoreState:
        state = self.load()
        indexed = {job.id: job for job in state.jobs}
        for legacy in self._legacy():
            indexed.setdefault(legacy.id, legacy)
        ordered = sorted(indexed.values(), key=lambda job: job.id)
        ordered.sort(key=lambda job: job.createdAt, reverse=True)
        return StoreState(state.store_revision, state.updated_at, tuple(ordered), state.recovered)

    def legacy_preview(self) -> LegacyPreview:
        current = {job.id: job for job in self.load().jobs}
        migratable = 0
        collisions = []
        legacy = self._legacy()
        for job in legacy:
            existing = current.get(job.id)
            if existing is None:
                migratable += 1
            elif sha256_hex(existing.model_dump(mode="json")) != sha256_hex(job.model_dump(mode="json")):
                collisions.append(LegacyCollision(job.id))
        return LegacyPreview(len(legacy), migratable, tuple(collisions))

    def content_hash(self, jobs: Iterable[SharedJob] | None = None) -> str:
        rows = tuple(jobs) if jobs is not None else self.load().jobs
        normalized = sorted(
            (job.model_dump(mode="json") for job in rows),
            key=lambda item: str(item["id"]),
        )
        return sha256_hex(normalized)

    def migration_additions(self) -> tuple[SharedJob, ...]:
        current = {job.id for job in self.load().jobs}
        return tuple(job for job in self._legacy() if job.id not in current)

    def write_migrated(self, jobs: Iterable[SharedJob]) -> StoreState:
        with self.lock:
            state = self.load()
            current = {job.id: job for job in state.jobs}
            for job in jobs:
                current.setdefault(job.id, job)
            return self._write(current.values(), state.store_revision + 1)

    def rollback_migration(self, *, had_v2: bool, before_hash: str) -> None:
        with self.lock:
            if not had_v2:
                self.path.unlink(missing_ok=True)
                return
            backup = self._parse(self.backup)
            if self.content_hash(backup.jobs) != before_hash:
                raise JobsStoreUnavailableError()
            self._replace(self.path, backup.model_dump_json(indent=2).encode(), ".rollback.tmp")

    def migrate_legacy(self, *, keep_original: bool) -> int:
        preview = self.legacy_preview()
        if preview.collisions:
            raise LegacyJobCollisionError(preview.collisions[0].legacy_id)
        current = {job.id for job in self.load().jobs}
        additions = [job for job in self._legacy() if job.id not in current]
        self.write_migrated(additions)
        if not keep_original and self.legacy_path.exists():
            self.legacy_path.unlink()
        return len(additions)
