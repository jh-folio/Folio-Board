from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, assert_never
from uuid import uuid4

from features.common.shared_jobs_schema import (
    Adapter,
    ArtifactProjection,
    CancelledProjection,
    CompanionProjection,
    Engine,
    ErrorCode,
    FailedProjection,
    FallbackReason,
    GenerationMode,
    IndexProjection,
    JobKind,
    JobMode,
    JobStatus,
    LabelCode,
    RequestedMode,
    ResultProjection,
    RssProjection,
    SetupProjection,
    SharedJob,
    TaskType,
)


ARTIFACT_TASKS: Final = frozenset(
    {
        TaskType.BRIEFING,
        TaskType.COMPANY_ANALYSIS,
        TaskType.TOPIC_REPORT,
        TaskType.PERSONAL_OVERLAY,
        TaskType.THESIS_DELTA,
        TaskType.MARKET_MEMORY_LLM,
        TaskType.MARKET_STATE_SNAPSHOT,
        TaskType.MARKET_MEMORY_UPDATE,
        TaskType.QUALITY_REPAIR,
        TaskType.INVESTMENT_REVIEW,
    }
)


@dataclass(frozen=True, slots=True)
class ProjectionStatusError(Exception):
    status: JobStatus

    def __str__(self) -> str:
        return f"nonterminal status cannot be projected: {self.status}"


@dataclass(frozen=True, slots=True)
class ProjectionTaskError(Exception):
    task_type: TaskType

    def __str__(self) -> str:
        return f"task has no artifact projection: {self.task_type}"


class ProjectionValueError(ValueError):
    def __init__(self, task_type: TaskType, key: str) -> None:
        super().__init__(f"invalid terminal projection value: {task_type.value}.{key}")
        self.task_type = task_type
        self.key = key


def utc_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def default_label(kind: JobKind, task_type: TaskType) -> LabelCode:
    match task_type:
        case TaskType.INDEX:
            return LabelCode.INDEX_REBUILD
        case TaskType.RSS:
            return LabelCode.RSS_IMPORT
        case TaskType.SETUP:
            return LabelCode.AGENT_CLI_INSTALL if kind == JobKind.AGENT_CLI_INSTALL else LabelCode.SETUP
        case TaskType.COMPANION:
            return LabelCode.AGENT_CHAT
        case TaskType.BRIEFING:
            return LabelCode.BRIEFING
        case TaskType.COMPANY_ANALYSIS:
            return LabelCode.COMPANY_ANALYSIS
        case TaskType.TOPIC_REPORT:
            return LabelCode.TOPIC_REPORT
        case TaskType.MARKET_STATE_SNAPSHOT:
            return LabelCode.MARKET_STATE
        case (
            TaskType.PERSONAL_OVERLAY
            | TaskType.THESIS_DELTA
            | TaskType.MARKET_MEMORY_LLM
            | TaskType.MARKET_MEMORY_UPDATE
            | TaskType.QUALITY_REPAIR
            | TaskType.INVESTMENT_REVIEW
        ):
            return LabelCode.AGENT_TASK
        case unreachable:
            assert_never(unreachable)


def new_shared_job(
    *,
    kind: JobKind | str,
    task_type: TaskType | str,
    generation_mode: GenerationMode | str,
    adapter: Adapter | str,
    requested_mode: RequestedMode | str | None,
    mode: JobMode | str,
    attempted_engine: Engine | str | None,
    clock: Callable[[], datetime],
    proposal_id: str | None = None,
) -> SharedJob:
    parsed_kind = JobKind(kind)
    parsed_task = TaskType(task_type)
    parsed_generation = GenerationMode(generation_mode)
    parsed_adapter = Adapter(adapter)
    parsed_requested = RequestedMode(requested_mode) if requested_mode is not None else None
    parsed_attempted = Engine(attempted_engine) if attempted_engine is not None else None
    engine = parsed_attempted or Engine.NONE
    now = utc_z(clock())
    return SharedJob(
        id=f"job_{uuid4()}",
        kind=parsed_kind,
        taskType=parsed_task,
        labelCode=default_label(parsed_kind, parsed_task),
        status=JobStatus.QUEUED,
        progress=0,
        messageCode=JobStatus.QUEUED,
        createdAt=now,
        startedAt=None,
        updatedAt=now,
        finishedAt=None,
        errorCode=None,
        generationMode=parsed_generation,
        engine=engine,
        adapter=parsed_adapter,
        requestedMode=parsed_requested,
        mode=JobMode(mode),
        attemptedEngine=parsed_attempted,
        finalEngine=None,
        fallbackReason=None,
        operationId=None,
        artifactRefs=[],
        commitIntent=None,
        proposalId=proposal_id,
        resultProjection=None,
    )


def _text(result: Mapping[str, str | int | bool | None], key: str) -> str | None:
    value = result.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _integer(result: Mapping[str, str | int | bool | None], key: str) -> int | None:
    value = result.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _required_text(
    task_type: TaskType,
    result: Mapping[str, str | int | bool | None],
    key: str,
) -> str:
    value = _text(result, key)
    if value is None:
        raise ProjectionValueError(task_type, key)
    return value


def _optional_text(
    task_type: TaskType,
    result: Mapping[str, str | int | bool | None],
    key: str,
) -> str | None:
    raw = result.get(key)
    if raw is None:
        return None
    value = _text(result, key)
    if value is None:
        raise ProjectionValueError(task_type, key)
    return value


def _required_integer(
    task_type: TaskType,
    result: Mapping[str, str | int | bool | None],
    key: str,
) -> int:
    value = _integer(result, key)
    if value is None or value < 0:
        raise ProjectionValueError(task_type, key)
    return value


def _artifact_projection(job: SharedJob, result: Mapping[str, str | int | bool | None]) -> ArtifactProjection:
    artifact_id: str
    report_id: str | None = None
    date: str | None = None
    title: str | None = None
    saved_count: int | None = None
    snapshot_id: str | None = None
    proposal_id: str | None = None
    match job.taskType:
        case (
            TaskType.BRIEFING
            | TaskType.COMPANY_ANALYSIS
            | TaskType.TOPIC_REPORT
        ):
            artifact_id = _required_text(job.taskType, result, "artifactId")
            report_id = _required_text(job.taskType, result, "reportId")
            date = _required_text(job.taskType, result, "date")
            title = _required_text(job.taskType, result, "title")
        case TaskType.PERSONAL_OVERLAY:
            artifact_id = _required_text(job.taskType, result, "artifactId")
            report_id = _required_text(job.taskType, result, "reportId")
        case TaskType.THESIS_DELTA | TaskType.MARKET_MEMORY_LLM:
            artifact_id = _required_text(job.taskType, result, "artifactId")
        case TaskType.MARKET_STATE_SNAPSHOT:
            artifact_id = _required_text(job.taskType, result, "artifactId")
            snapshot_id = _required_text(job.taskType, result, "snapshotId")
            if artifact_id != snapshot_id:
                raise ProjectionValueError(job.taskType, "artifactId")
        case TaskType.MARKET_MEMORY_UPDATE:
            artifact_id = _required_text(job.taskType, result, "artifactId")
            if artifact_id != job.id:
                raise ProjectionValueError(job.taskType, "artifactId")
            saved_count = _required_integer(job.taskType, result, "savedCount")
            snapshot_id = _optional_text(job.taskType, result, "snapshotId")
        case TaskType.QUALITY_REPAIR:
            artifact_id = _required_text(job.taskType, result, "artifactId")
            report_id = _required_text(job.taskType, result, "reportId")
            proposal_id = _optional_text(job.taskType, result, "proposalId") or job.proposalId
        case TaskType.INVESTMENT_REVIEW:
            artifact_id = _required_text(job.taskType, result, "artifactId")
            report_id = _required_text(job.taskType, result, "reportId")
        case TaskType.INDEX | TaskType.RSS | TaskType.SETUP | TaskType.COMPANION:
            raise ProjectionTaskError(job.taskType)
        case unreachable:
            assert_never(unreachable)
    return ArtifactProjection(
        artifactType=job.taskType.value,
        artifactId=artifact_id,
        reportId=report_id,
        date=date,
        title=title,
        savedCount=saved_count,
        snapshotId=snapshot_id,
        proposalId=proposal_id,
        requestedMode=job.requestedMode,
        attemptedEngine=job.attemptedEngine,
        finalEngine=job.finalEngine or job.attemptedEngine,
        fallbackReason=job.fallbackReason,
        adapter=job.adapter,
        mode=job.mode,
    )


def project_terminal_result(
    job: SharedJob,
    status: JobStatus | str,
    result: Mapping[str, str | int | bool | None] | None = None,
    error_code: ErrorCode | str | None = None,
) -> ResultProjection:
    parsed_status = JobStatus(status)
    safe = result or {}
    match parsed_status:
        case JobStatus.CANCELLED:
            return CancelledProjection()
        case (
            JobStatus.FAILED
            | JobStatus.FAILED_CANCEL
            | JobStatus.FAILED_COMMIT
            | JobStatus.FAILED_RESTART
            | JobStatus.FAILED_COMMIT_RECOVERY
        ):
            return FailedProjection(errorCode=ErrorCode(error_code or ErrorCode.INTERNAL_ERROR))
        case JobStatus.DONE:
            pass
        case JobStatus.QUEUED | JobStatus.RUNNING | JobStatus.CANCEL_REQUESTED | JobStatus.COMMITTING:
            raise ProjectionStatusError(parsed_status)
        case unreachable:
            assert_never(unreachable)
    match job.taskType:
        case TaskType.INDEX:
            return IndexProjection(
                count=_integer(safe, "count") or 0,
                generatedAt=_text(safe, "generatedAt") or job.updatedAt,
                incremental=bool(safe.get("incremental")),
                sqlite=_text(safe, "sqlite") or "research-index.sqlite3",
            )
        case TaskType.RSS:
            return RssProjection(
                added=_integer(safe, "added") or 0,
                total=_integer(safe, "total") or 0,
                failed=_integer(safe, "failed") or 0,
                # 코드 식별자만 싣는다. `지금 정리`의 bool 형태는 이유가 아니므로 버리고,
                # 길이는 잘라서 담는다 — 여기서 ValidationError가 나면 잡이 종결되지 못한다.
                skipped=(_text(safe, "skipped") or "")[:40] or None,
            )
        case TaskType.SETUP:
            return SetupProjection(ok=True, adapter=job.adapter)
        case TaskType.COMPANION:
            return CompanionProjection(
                requestedMode=job.requestedMode,
                attemptedEngine=job.attemptedEngine,
                finalEngine=job.finalEngine or job.attemptedEngine,
                fallbackReason=job.fallbackReason,
                adapter=job.adapter,
                mode=job.mode,
                proposalId=_text(safe, "proposalId") or job.proposalId,
                sessionId=_text(safe, "sessionId") or None,
                assistantMessageId=_text(safe, "assistantMessageId") or None,
            )
        case (
            TaskType.BRIEFING
            | TaskType.COMPANY_ANALYSIS
            | TaskType.TOPIC_REPORT
            | TaskType.PERSONAL_OVERLAY
            | TaskType.THESIS_DELTA
            | TaskType.MARKET_MEMORY_LLM
            | TaskType.MARKET_STATE_SNAPSHOT
            | TaskType.MARKET_MEMORY_UPDATE
            | TaskType.QUALITY_REPAIR
            | TaskType.INVESTMENT_REVIEW
        ):
            return _artifact_projection(job, safe)
        case unreachable:
            assert_never(unreachable)
