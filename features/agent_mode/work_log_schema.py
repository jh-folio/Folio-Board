from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from features.common.shared_jobs_schema import (
    Adapter,
    Engine,
    ErrorCode,
    FallbackReason,
    GenerationMode,
    JobKind,
    JobMode,
    JobStatus,
    LabelCode,
    RequestedMode,
    TaskType,
    UtcZ,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkLogCategory(StrEnum):
    COMPANION = "companion"
    TASK = "task"


class WorkLogFilter(StrEnum):
    ALL = "all"
    COMPANION = "companion"
    TASK = "task"


class TokenPurpose(StrEnum):
    CLEAR = "clear"
    MIGRATION = "migration"


class TokenScope(StrEnum):
    ALL = "all"
    COMPANION = "companion"
    TASK = "task"
    LEGACY_JOBS = "legacy_jobs"


class TokenStatus(StrEnum):
    ISSUED = "issued"
    IN_PROGRESS = "in_progress"
    USED = "used"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLYING = "applying"
    APPLIED = "applied"
    REJECTED = "rejected"
    STALE = "stale"
    CONFLICT = "conflict"
    FAILED_APPLY = "failed_apply"
    UNAVAILABLE = "unavailable"


class ResultStatus(StrEnum):
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class HiddenJob(StrictModel):
    jobId: str
    hiddenAt: UtcZ


class PreviewTokenRecord(StrictModel):
    nonceHash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    purpose: TokenPurpose
    jobsStoreRevision: Annotated[int, Field(ge=0)]
    count: Annotated[int, Field(ge=0)]
    scope: TokenScope
    expiresAt: UtcZ
    status: TokenStatus
    operationId: str | None


class WorkLogStoreFile(StrictModel):
    schemaVersion: Annotated[int, Field(ge=1, le=1)] = 1
    storeRevision: Annotated[int, Field(ge=1)]
    updatedAt: UtcZ
    hiddenJobs: list[HiddenJob]
    tokens: list[PreviewTokenRecord]


class MigrationJournal(StrictModel):
    schemaVersion: Annotated[int, Field(ge=1, le=1)] = 1
    operationId: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    action: Annotated[str, Field(pattern=r"^migrate_(?:keep|delete)_original$")]
    tokenHash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    beforeHash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    targetHash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    hadV2: bool


class WorkLogEntry(StrictModel):
    id: Annotated[str, Field(pattern=r"^wl_[0-9a-f]{24}$")]
    jobId: str
    category: WorkLogCategory
    kind: JobKind
    taskType: TaskType
    labelCode: LabelCode
    status: JobStatus
    progress: Annotated[int, Field(ge=0, le=100)]
    messageCode: JobStatus
    createdAt: UtcZ
    startedAt: UtcZ | None
    updatedAt: UtcZ
    finishedAt: UtcZ | None
    errorCode: ErrorCode | None
    generationMode: GenerationMode
    adapter: Adapter
    requestedMode: RequestedMode | None
    mode: JobMode
    attemptedEngine: Engine | None
    finalEngine: Engine | None
    fallbackReason: FallbackReason | None
    artifactTypes: list[str]
    artifactCount: Annotated[int, Field(ge=0)]
    proposalId: str | None
    proposalStatus: ProposalStatus | None
    resultStatus: ResultStatus | None
    queueWaitMs: Annotated[int, Field(ge=0)] | None
    contextMs: Annotated[int, Field(ge=0)] | None
    cliMs: Annotated[int, Field(ge=0)] | None
    postprocessMs: Annotated[int, Field(ge=0)] | None
    totalMs: Annotated[int, Field(ge=0)] | None


WORK_LOG_ENTRY_KEYS: Final = frozenset(WorkLogEntry.model_fields)
