from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Callable, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from features.common.canonical_identity import ReportKind
from features.common.canonical_json import JsonValue
from features.common.canonical_report_types import PreparedCanonicalWrite, WriteKind
from features.common.shared_jobs_schema import (
    CommitIntent,
    ExpectedArtifact,
    JOB_ID_PATTERN,
    SharedJob,
    StorageKind,
    TaskType,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CommitJournalStatus(StrEnum):
    PREPARED = "prepared"
    ARTIFACTS_WRITTEN = "artifacts_written"


class ManifestArtifact(StrictModel):
    expected: ExpectedArtifact
    targetRelativePath: Annotated[str, Field(min_length=1, max_length=500)]
    stageFile: Annotated[str, Field(pattern=r"^[0-9]{3}\.(?:json|json\.gz)$")]
    reportKind: ReportKind | None
    canonicalContentHash: str | None
    canonicalChanged: bool | None

    @model_validator(mode="after")
    def validate_paths_and_kind(self) -> Self:
        target = PurePosixPath(self.targetRelativePath)
        if (
            target.is_absolute()
            or ".." in target.parts
            or target.as_posix() != self.targetRelativePath
            or not target.parts
            or target.parts[0] in {"job-staging", "job-context", "job-commits"}
        ):
            msg = "invalid target relative path"
            raise ValueError(msg)
        canonical = self.reportKind is not None
        if canonical != (self.canonicalContentHash is not None):
            msg = "canonical manifest fields disagree"
            raise ValueError(msg)
        if canonical != (self.canonicalChanged is not None):
            msg = "canonical manifest change flag disagrees"
            raise ValueError(msg)
        if canonical != (self.expected.targetRevision is not None):
            msg = "canonical manifest revision disagrees"
            raise ValueError(msg)
        if canonical and self.expected.storage != StorageKind.JSON:
            msg = "canonical artifact storage must be JSON"
            raise ValueError(msg)
        expected_suffix = ".json.gz" if self.expected.storage == StorageKind.GZIP_JSON else ".json"
        if not self.targetRelativePath.endswith(expected_suffix) or not self.stageFile.endswith(expected_suffix):
            msg = "artifact storage and file suffix disagree"
            raise ValueError(msg)
        return self


class JobStageManifest(StrictModel):
    schemaVersion: Literal[1] = 1
    jobId: str
    operationId: Annotated[str, Field(min_length=1, max_length=160)]
    taskType: TaskType
    artifacts: list[ManifestArtifact]

    @model_validator(mode="after")
    def validate_owner_and_refs(self) -> Self:
        if JOB_ID_PATTERN.fullmatch(self.jobId) is None:
            msg = "invalid manifest job id"
            raise ValueError(msg)
        keys = [(item.expected.storage, item.expected.type, item.expected.id) for item in self.artifacts]
        stage_files = [item.stageFile for item in self.artifacts]
        target_paths = [item.targetRelativePath for item in self.artifacts]
        if (
            not keys
            or keys != sorted(keys)
            or len(keys) != len(set(keys))
            or len(stage_files) != len(set(stage_files))
            or len(target_paths) != len(set(target_paths))
        ):
            msg = "manifest artifact refs must be unique and sorted"
            raise ValueError(msg)
        return self


class JobCommitJournal(StrictModel):
    schemaVersion: Literal[1] = 1
    jobId: str
    operationId: Annotated[str, Field(min_length=1, max_length=160)]
    taskType: TaskType
    expectedArtifacts: list[ExpectedArtifact]
    artifacts: list[ManifestArtifact]
    status: CommitJournalStatus
    createdAt: str
    updatedAt: str

    @model_validator(mode="after")
    def validate_owner_and_artifacts(self) -> Self:
        if JOB_ID_PATTERN.fullmatch(self.jobId) is None:
            msg = "invalid journal job id"
            raise ValueError(msg)
        if [item.expected for item in self.artifacts] != self.expectedArtifacts:
            msg = "journal artifacts disagree with expected artifacts"
            raise ValueError(msg)
        return self


@dataclass(frozen=True, slots=True)
class CanonicalArtifactSpec:
    artifact_type: str
    artifact_id: str
    report_kind: ReportKind
    exact_path: Path
    write_kind: WriteKind
    candidate: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class JsonArtifactSpec:
    storage: StorageKind
    artifact_type: str
    artifact_id: str
    exact_path: Path
    payload: dict[str, JsonValue]
    # Runs while the exact artifact lock is held, before the stager captures
    # its base hash.  Feature contracts can validate a candidate without
    # writing around the job lifecycle.
    payload_validator: Callable[[dict[str, JsonValue], dict[str, JsonValue] | None], dict[str, JsonValue]] | None = None
    # Staging can be long-lived.  A feature with external authoritative inputs
    # may reject promotion if those inputs moved after staging; this must run
    # before the job claims COMMITTING or creates a recovery journal.
    pre_promotion_validator: Callable[[], None] | None = None


type ArtifactSpec = CanonicalArtifactSpec | JsonArtifactSpec


@dataclass(frozen=True, slots=True)
class StagedArtifact:
    manifest: ManifestArtifact
    exact_path: Path
    staged_path: Path
    canonical: PreparedCanonicalWrite | None
    pre_promotion_validator: Callable[[], None] | None = None


@dataclass(frozen=True, slots=True)
class StagedJobBundle:
    job: SharedJob
    operation_id: str
    manifest: JobStageManifest
    intent: CommitIntent
    terminal_result: dict[str, str | int | bool | None]
    artifacts: tuple[StagedArtifact, ...]


FaultHook = Callable[[str], None]


class JobArtifactValidationError(Exception):
    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return self.reason


class JobArtifactConflictError(Exception):
    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return self.reason


class CommitInterruptedError(Exception):
    __slots__ = ("phase",)

    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase

    def __str__(self) -> str:
        return self.phase
