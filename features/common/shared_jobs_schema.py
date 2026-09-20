from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


UTC_Z_PATTERN: Final = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
JOB_ID_PATTERN: Final = re.compile(
    r"^job_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
UtcZ = Annotated[str, Field(pattern=UTC_Z_PATTERN)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JobKind(StrEnum):
    INDEX = "index"
    RSS = "rss"
    SETUP = "setup"
    AGENT_BRIDGE = "agent_bridge"
    AGENT_CLI_INSTALL = "agent_cli_install"
    BRIEFING = "briefing"
    COMPANY_ANALYSIS = "company_analysis"
    TOPIC_REPORT = "topic_report"
    MARKET_STATE_SNAPSHOT = "market_state_snapshot"


class TaskType(StrEnum):
    INDEX = "index"
    RSS = "rss"
    SETUP = "setup"
    COMPANION = "companion"
    BRIEFING = "briefing"
    COMPANY_ANALYSIS = "company_analysis"
    TOPIC_REPORT = "topic_report"
    PERSONAL_OVERLAY = "personal_overlay"
    THESIS_DELTA = "thesis_delta"
    MARKET_MEMORY_LLM = "market_memory_llm"
    MARKET_STATE_SNAPSHOT = "market_state_snapshot"
    MARKET_MEMORY_UPDATE = "market_memory_update"
    QUALITY_REPAIR = "quality_repair"
    INVESTMENT_REVIEW = "investment_review"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMMITTING = "committing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"
    FAILED_CANCEL = "failed_cancel"
    FAILED_COMMIT = "failed_commit"
    FAILED_RESTART = "failed_restart"
    FAILED_COMMIT_RECOVERY = "failed_commit_recovery"


class GenerationMode(StrEnum):
    LLM_API = "llm_api"
    LLM_CLI = "llm_cli"
    RULES = "rules"
    NONE = "none"


class Engine(StrEnum):
    API = "api"
    CLI = "cli"
    RULES = "rules"
    NONE = "none"


class Adapter(StrEnum):
    AUTO = "auto"
    CODEX = "codex"
    CLAUDE = "claude"
    ANTIGRAVITY = "antigravity"
    OPENAI_API = "openai_api"
    GEMINI_API = "gemini_api"
    CLAUDE_API = "claude_api"
    RULES = "rules"
    NONE = "none"


class RequestedMode(StrEnum):
    DIRECT = "direct"
    CLI = "cli"


class JobMode(StrEnum):
    COLLECT = "collect"
    INDEX = "index"
    INSTALL = "install"
    ANSWER = "answer"
    GENERATE = "generate"
    REVISE = "revise"
    FALLBACK = "fallback"


class FallbackReason(StrEnum):
    ENGINE_UNAVAILABLE = "engine_unavailable"
    ENGINE_FAILED = "engine_failed"
    CONFIRMED_ZERO_EVIDENCE = "confirmed_zero_evidence"


class PhaseCode(StrEnum):
    """Live observation of where a running job actually is.

    Additive to ``status``/``messageCode``, never a substitute: those two stay
    equal by contract (see ``validate_state``). This distinguishes, within a
    single ``running`` status, whether the job is still queued behind another
    Agent CLI call (``wait_engine``) or actually generating.
    """

    CONTEXT = "context"
    WAIT_ENGINE = "wait_engine"
    GENERATE = "generate"
    POSTPROCESS = "postprocess"
    COMMIT = "commit"


class LabelCode(StrEnum):
    INDEX_REBUILD = "index_rebuild"
    RSS_IMPORT = "rss_import"
    SETUP = "setup"
    AGENT_CHAT = "agent_chat"
    AGENT_CLI_INSTALL = "agent_cli_install"
    AGENT_TASK = "agent_task"
    BRIEFING = "briefing"
    COMPANY_ANALYSIS = "company_analysis"
    TOPIC_REPORT = "topic_report"
    MARKET_STATE = "market_state"


class ErrorCode(StrEnum):
    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    ADAPTER_FAILED = "adapter_failed"
    VALIDATION_FAILED = "validation_failed"
    SAVE_FAILED = "save_failed"
    CANCEL_FAILED = "cancel_failed"
    RESTART_INTERRUPTED = "restart_interrupted"
    COMMIT_RECOVERY_FAILED = "commit_recovery_failed"
    PRIVATE_CLEANUP_FAILED = "private_cleanup_failed"
    STORE_UNAVAILABLE = "store_unavailable"
    INTERNAL_ERROR = "internal_error"


class StorageKind(StrEnum):
    JSON = "json"
    GZIP_JSON = "gzip_json"
    SQLITE = "sqlite"


class ArtifactRef(StrictModel):
    type: Annotated[str, Field(min_length=1, max_length=80)]
    id: Annotated[str, Field(min_length=1, max_length=200)]


class JobMarker(StrictModel):
    jobId: str
    operationId: Annotated[str, Field(min_length=1, max_length=160)]


class ExpectedArtifact(ArtifactRef):
    storage: StorageKind
    baseHash: Sha256 | None
    baseMarker: JobMarker | None
    targetRevision: Annotated[int, Field(ge=1)] | None
    targetHash: Sha256


class CancelledProjection(StrictModel):
    status: Annotated[str, Field(pattern="^cancelled$")] = "cancelled"
    errorCode: None = None


class FailedProjection(StrictModel):
    status: Annotated[str, Field(pattern="^failed$")] = "failed"
    errorCode: ErrorCode


class IndexProjection(StrictModel):
    status: Annotated[str, Field(pattern="^done$")] = "done"
    count: Annotated[int, Field(ge=0)]
    generatedAt: UtcZ
    incremental: bool
    sqlite: str


class RssProjection(StrictModel):
    status: Annotated[str, Field(pattern="^done$")] = "done"
    added: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    # 수집·정리가 건너뛴 이유(예: workspace_moved). 없으면 None이라 옛 저장분도 그대로 읽힌다.
    skipped: Annotated[str, Field(max_length=40)] | None = None


class SetupProjection(StrictModel):
    status: Annotated[str, Field(pattern="^done$")] = "done"
    ok: Annotated[bool, Field(pattern=None)] = True
    adapter: Adapter


class CompanionProjection(StrictModel):
    status: Annotated[str, Field(pattern="^done$")] = "done"
    requestedMode: RequestedMode | None
    attemptedEngine: Engine | None
    finalEngine: Engine | None
    fallbackReason: FallbackReason | None
    adapter: Adapter
    mode: JobMode
    proposalId: str | None
    # Agent Dock Stage C: lets the Dock fetch the exact reply instead of
    # re-reading the whole thread. Optional with a None default so a job
    # record persisted before this field existed keeps validating unchanged.
    sessionId: str | None = None
    assistantMessageId: str | None = None


class ArtifactProjection(StrictModel):
    status: Annotated[str, Field(pattern="^done$")] = "done"
    artifactType: str
    artifactId: str
    reportId: str | None
    date: str | None
    title: str | None
    savedCount: Annotated[int, Field(ge=0)] | None
    snapshotId: str | None
    proposalId: str | None
    requestedMode: RequestedMode | None
    attemptedEngine: Engine | None
    finalEngine: Engine | None
    fallbackReason: FallbackReason | None
    adapter: Adapter
    mode: JobMode


type ResultProjection = (
    CancelledProjection
    | FailedProjection
    | IndexProjection
    | RssProjection
    | SetupProjection
    | CompanionProjection
    | ArtifactProjection
)


class CommitIntent(StrictModel):
    operationId: Annotated[str, Field(min_length=1, max_length=160)]
    expectedArtifacts: list[ExpectedArtifact]
    terminalProjection: ResultProjection


TERMINAL_STATUSES: Final = frozenset(
    {
        JobStatus.DONE,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
        JobStatus.FAILED_CANCEL,
        JobStatus.FAILED_COMMIT,
        JobStatus.FAILED_RESTART,
        JobStatus.FAILED_COMMIT_RECOVERY,
    }
)


class SharedJob(StrictModel):
    id: str
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
    engine: Engine
    adapter: Adapter
    requestedMode: RequestedMode | None
    mode: JobMode
    attemptedEngine: Engine | None
    finalEngine: Engine | None
    fallbackReason: FallbackReason | None
    # 실패 원인을 코드로만 남기는 진단 필드. 본문·프롬프트 조각은 담지 않는다.
    failureDetail: Annotated[str, Field(max_length=200)] | None = None
    operationId: str | None
    artifactRefs: list[ArtifactRef]
    commitIntent: CommitIntent | None
    proposalId: str | None
    # Observation-only timing/phase fields (Agent Dock Stage A). Optional with
    # a None default so job records persisted before this field existed keep
    # validating unchanged.
    phaseCode: PhaseCode | None = None
    queueWaitMs: Annotated[int, Field(ge=0)] | None = None
    contextMs: Annotated[int, Field(ge=0)] | None = None
    cliMs: Annotated[int, Field(ge=0)] | None = None
    postprocessMs: Annotated[int, Field(ge=0)] | None = None
    totalMs: Annotated[int, Field(ge=0)] | None = None
    resultProjection: ResultProjection | None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.id.startswith("job_") and JOB_ID_PATTERN.fullmatch(self.id) is None:
            msg = "invalid job id"
            raise ValueError(msg)
        if self.messageCode != self.status:
            msg = "messageCode must equal status"
            raise ValueError(msg)
        terminal = self.status in TERMINAL_STATUSES
        if terminal != (self.resultProjection is not None):
            msg = "terminal state and resultProjection disagree"
            raise ValueError(msg)
        if terminal != (self.finishedAt is not None):
            msg = "terminal state and finishedAt disagree"
            raise ValueError(msg)
        if self.status == JobStatus.COMMITTING:
            if self.commitIntent is None or self.operationId != self.commitIntent.operationId:
                msg = "committing requires matching intent"
                raise ValueError(msg)
        elif self.commitIntent is not None:
            msg = "commitIntent is committing-only"
            raise ValueError(msg)
        if terminal and self.commitIntent is not None:
            msg = "terminal job cannot retain commitIntent"
            raise ValueError(msg)
        return self


class JobsStoreFile(StrictModel):
    schemaVersion: Annotated[int, Field(ge=2, le=2)] = 2
    storeRevision: Annotated[int, Field(ge=1)]
    updatedAt: UtcZ
    jobs: list[SharedJob]
