"""Closed v1 schema for persisted diagnostics.

The values in this module are deliberately codes, never caller supplied prose.
It is safe to persist a model only through ``to_dict``: both construction and
deserialization reject unknown fields and reconstruct an allow-listed shape.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
import json
import platform
import re
import subprocess
import uuid
from typing import Any, Final, Iterable, Mapping

from features.common.shared_jobs_schema import Adapter, Engine, ErrorCode, FallbackReason, JobStatus, TaskType

SCHEMA_VERSION: Final = 1
MAX_DOCUMENT_BYTES: Final = 128 * 1024
RESERVED_TERMINAL_BYTES: Final = 16 * 1024
MAX_EVENTS: Final = 200
MAX_ERRORS: Final = 16
MAX_ISSUES: Final = 8

FEATURE_CODES: Final = frozenset({"briefing", "company_analysis", "topic_report", "agent_chat", "automation", "rss", "index", "personal_judgment", "jobs", "http", "startup"})
ROUTE_CODES: Final = frozenset({"shared_worker", "report_api", "report_cli", "topic_approved", "topic_resume", "chat_cli", "chat_api", "automation_run", "rss_collect", "index_build", "judgment_json", "judgment_sql", "http_unhandled", "startup_recovery"})
AUTHORITY_KINDS: Final = frozenset({"shared_job", "automation", "direct", "recovery"})
STAGE_CODES: Final = frozenset({"queued", "preflight", "collect", "context", "wait_engine", "generate", "validate", "commit", "cleanup", "recovery"})
EVENT_CODES: Final = frozenset({"start", "end", "failure", "skip", "fallback", "resume"})
ISSUE_CODES: Final = frozenset({"producer_missing", "event_limit", "error_limit", "byte_limit", "quota_exceeded", "writer_conflict", "write_failed", "read_failed", "scan_limit", "invalid_event", "recovery_gap", "authority_changed", "authority_unavailable", "clock_discontinuity", "source_unavailable", "issue_limit"})
REASON_CODES: Final = frozenset({"timeout", "rate_limit", "adapter_unavailable", "adapter_failed", "validation", "save_permission", "save_failed", "cancelled", "interrupted", "commit_recovery_failed", "private_cleanup_failed", "store_unavailable", "commit_unknown", "unknown"})
EXCEPTION_CODES: Final = frozenset({"runtime_error", "timeout_error", "process_timeout", "llm_request_error", "permission_error", "file_not_found", "validation_error", "private_cleanup_error", "jobs_store_error", "other"})
NEXT_ACTION_CODES: Final = frozenset({"none", "wait", "check_settings", "inspect_result", "explicit_retry", "contact_support"})
CONFIRMATIONS: Final = frozenset({"observed", "inferred", "unknown"})
OBSERVED_STATUSES: Final = frozenset(item.value for item in JobStatus) | frozenset({"succeeded", "unknown"})
ENGINES: Final = frozenset(item.value for item in Engine)
ADAPTERS: Final = frozenset(item.value for item in Adapter)
FALLBACK_REASONS: Final = frozenset(item.value for item in FallbackReason)
TASK_TYPES: Final = frozenset(item.value for item in TaskType)

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
_ID_PATTERNS: Final = {
    "run": re.compile(rf"run_({_UUID})\Z"), "req": re.compile(rf"req_({_UUID})\Z"),
    "stg": re.compile(rf"stg_({_UUID})\Z"), "evt": re.compile(rf"evt_({_UUID})\Z"),
    "err": re.compile(rf"err_({_UUID})\Z"), "job": re.compile(rf"job_({_UUID})\Z"),
}
_BUILD = re.compile(r"[0-9a-f]{7,40}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
_VERSION = re.compile(r"\d+(?:\.\d+){1,3}\Z")
# A process epoch is a process fact, not an execution fact.  It is generated
# at import without resolving a workspace or opening a file.
PROCESS_EPOCH: Final = str(uuid.uuid4())


class DiagnosticValidationError(ValueError):
    """A schema error expressed as a stable code, never a raw input value."""


def _fail(code: str) -> None:
    raise DiagnosticValidationError(code)


def _code(value: object, allowed: frozenset[str], field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or value not in allowed:
        _fail(f"invalid_{field}")
    return value


def _bounded_int(value: object, field: str, low: int = 0, high: int = 1_000_000) -> int:
    if type(value) is not int or not low <= value <= high:
        _fail(f"invalid_{field}")
    return value


def new_id(prefix: str) -> str:
    if prefix not in _ID_PATTERNS or prefix == "job":
        _fail("invalid_id_prefix")
    return f"{prefix}_{uuid.uuid4()}"


def valid_id(value: object, prefix: str) -> str:
    pattern = _ID_PATTERNS.get(prefix)
    if pattern is None or not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(f"invalid_{prefix}_id")
    return value


def run_id_for_job(job_id: str) -> str:
    return "run_" + valid_id(job_id, "job")[4:]


def utc_z(value: datetime | None = None) -> str:
    instant = value or datetime.now(UTC)
    if instant.tzinfo is None:
        _fail("invalid_timestamp")
    return instant.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def valid_utc_z(value: object) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _fail("invalid_timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("invalid_timestamp")
    return value


def _optional_id(value: object, prefix: str, own: str | None = None) -> str | None:
    if value is None:
        return None
    parsed = valid_id(value, prefix)
    if parsed == own:
        _fail("self_reference")
    return parsed


def _safe_os() -> str:
    name = platform.system().lower()
    return name if name in {"windows", "linux", "macos"} else ("macos" if name == "darwin" else "other")


@dataclass(frozen=True, slots=True)
class DiagnosticContext:
    run_id: str
    request_id: str | None
    feature_code: str
    route_code: str
    authority_kind: str
    task_type: str | None
    process_epoch: str
    producer_epoch: str
    job_id: str | None = None
    parent_run_id: str | None = None
    retry_of_run_id: str | None = None
    app_version: str = "0.0.0"
    build_id: str | None = None
    os_code: str = "other"
    python_version: str = "0"

    def __post_init__(self) -> None:
        valid_id(self.run_id, "run")
        if self.request_id is not None:
            valid_id(self.request_id, "req")
        if self.job_id is not None:
            valid_id(self.job_id, "job")
            if self.run_id != run_id_for_job(self.job_id):
                _fail("job_run_mismatch")
        _code(self.feature_code, FEATURE_CODES, "feature_code")
        _code(self.route_code, ROUTE_CODES, "route_code")
        _code(self.authority_kind, AUTHORITY_KINDS, "authority_kind")
        _code(self.task_type, TASK_TYPES, "task_type", nullable=True)
        valid_id(self.process_epoch, "run") if False else _valid_uuid(self.process_epoch, "process_epoch")
        _valid_uuid(self.producer_epoch, "producer_epoch")
        _optional_id(self.parent_run_id, "run", self.run_id)
        _optional_id(self.retry_of_run_id, "run", self.run_id)
        if not isinstance(self.app_version, str) or _VERSION.fullmatch(self.app_version) is None or len(self.app_version) > 32:
            _fail("invalid_app_version")
        if self.build_id is not None and (not isinstance(self.build_id, str) or _BUILD.fullmatch(self.build_id) is None):
            _fail("invalid_build_id")
        if self.os_code not in {"windows", "linux", "macos", "other"}:
            _fail("invalid_os")
        if not isinstance(self.python_version, str) or not re.fullmatch(r"\d+(?:\.\d+){0,3}", self.python_version) or len(self.python_version) > 32:
            _fail("invalid_python_version")

    def with_recovery_producer(self, producer_epoch: str | None = None) -> "DiagnosticContext":
        return replace(self, producer_epoch=producer_epoch or str(uuid.uuid4()))

    def to_identity_dict(self) -> dict[str, object]:
        return {"runId": self.run_id, "jobId": self.job_id, "requestId": self.request_id, "parentRunId": self.parent_run_id, "retryOfRunId": self.retry_of_run_id, "processEpoch": self.process_epoch, "featureCode": self.feature_code, "routeCode": self.route_code, "taskType": self.task_type, "authorityKind": self.authority_kind, "appVersion": self.app_version, "buildId": self.build_id, "os": self.os_code, "pythonVersion": self.python_version}


def _valid_uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        _fail(f"invalid_{field}")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        _fail(f"invalid_{field}")
    if str(parsed) != value or parsed.version != 4:
        _fail(f"invalid_{field}")
    return value


def new_context(*, feature_code: str, route_code: str, authority_kind: str, task_type: str | None = None, job_id: str | None = None, request_id: str | None = None, parent_run_id: str | None = None, retry_of_run_id: str | None = None, app_version: str = "0.0.0", build_id: str | None = None, process_epoch: str | None = None, producer_epoch: str | None = None) -> DiagnosticContext:
    run_id = run_id_for_job(job_id) if job_id is not None else new_id("run")
    epoch = process_epoch or PROCESS_EPOCH
    return DiagnosticContext(run_id=run_id, request_id=request_id or new_id("req"), feature_code=feature_code, route_code=route_code, authority_kind=authority_kind, task_type=task_type, process_epoch=epoch, producer_epoch=producer_epoch or epoch, job_id=job_id, parent_run_id=parent_run_id, retry_of_run_id=retry_of_run_id, app_version=app_version, build_id=build_id, os_code=_safe_os(), python_version=platform.python_version())


@dataclass(frozen=True, slots=True)
class SafeFrame:
    module_code: str
    function_code: str
    line: int

    def __post_init__(self) -> None:
        if not re.fullmatch(r"features(?:\.[a-z_][a-z0-9_]*)+", self.module_code):
            _fail("invalid_source_frame")
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", self.function_code):
            _fail("invalid_source_frame")
        _bounded_int(self.line, "source_line", 1)

    def to_dict(self) -> dict[str, object]:
        return {"moduleCode": self.module_code, "functionCode": self.function_code, "line": self.line}


@dataclass(frozen=True, slots=True)
class Failure:
    error_id: str
    stage_id: str | None
    stage_code: str | None
    error_code: str | None
    reason_code: str
    exception_code: str
    frames: tuple[SafeFrame, ...]
    confirmation: str
    next_action_code: str
    fingerprint: str

    def __post_init__(self) -> None:
        valid_id(self.error_id, "err")
        if self.stage_id is not None:
            valid_id(self.stage_id, "stg")
        _code(self.stage_code, STAGE_CODES, "stage_code", nullable=True)
        if self.error_code is not None:
            if self.error_code not in {item.value for item in ErrorCode}:
                _fail("invalid_error_code")
        _code(self.reason_code, REASON_CODES, "reason_code")
        _code(self.exception_code, EXCEPTION_CODES, "exception_code")
        _code(self.confirmation, CONFIRMATIONS, "confirmation")
        _code(self.next_action_code, NEXT_ACTION_CODES, "next_action_code")
        if type(self.frames) is not tuple or len(self.frames) > 6 or not all(isinstance(item, SafeFrame) for item in self.frames):
            _fail("invalid_frames")
        if not isinstance(self.fingerprint, str) or re.fullmatch(r"[0-9a-f]{64}", self.fingerprint) is None:
            _fail("invalid_fingerprint")

    def to_dict(self) -> dict[str, object]:
        return {"errorId": self.error_id, "stageId": self.stage_id, "stageCode": self.stage_code, "errorCode": self.error_code, "reasonCode": self.reason_code, "exceptionCode": self.exception_code, "frames": [frame.to_dict() for frame in self.frames], "confirmation": self.confirmation, "nextActionCode": self.next_action_code, "fingerprint": self.fingerprint}


def failure_fingerprint(*, stage_code: str | None, reason_code: str, exception_code: str, frames: Iterable[SafeFrame]) -> str:
    """Hash only the closed, already-safe failure basis (never exception text)."""
    basis = json.dumps({"stage": stage_code, "reason": reason_code, "exception": exception_code, "frames": [item.to_dict() for item in frames]}, sort_keys=True, separators=(",", ":"))
    return sha256(basis.encode("utf-8")).hexdigest()


def safe_failure(*, stage_id: str | None = None, stage_code: str | None = None, reason_code: str = "unknown", exception_code: str = "other", error_code: str | None = None, confirmation: str = "unknown", next_action_code: str = "contact_support", frames: Iterable[SafeFrame] = ()) -> Failure:
    safe_frames = tuple(frames)
    return Failure(error_id=new_id("err"), stage_id=stage_id, stage_code=stage_code, error_code=error_code, reason_code=reason_code, exception_code=exception_code, frames=safe_frames, confirmation=confirmation, next_action_code=next_action_code, fingerprint=failure_fingerprint(stage_code=stage_code, reason_code=reason_code, exception_code=exception_code, frames=safe_frames))


def safe_exception_failure(error: BaseException, *, stage_id: str | None = None, stage_code: str | None = None, boundary: str = "generic", frames: Iterable[SafeFrame] = ()) -> Failure:
    """Classify only type/boundary facts without reading exception text/data.

    ``boundary`` is a closed internal hint supplied by the observer where the
    exception occurred.  In particular, a generic ``FileNotFoundError`` is not
    an adapter outage and generic ``PermissionError`` is not a save failure.
    """
    if boundary not in {"generic", "adapter", "save", "validation", "cleanup", "store", "recovery", "cancel"}:
        _fail("invalid_failure_boundary")
    reason, exception, confirmation = "unknown", "other", "unknown"
    # The bridge and HTTP client expose two closed, typed failure contracts.
    # Do not inspect their messages, response bodies, CLI hints, or arbitrary
    # attributes: the module/type pair plus the documented numeric status are
    # enough to distinguish a retry-later rate limit from an unknown failure.
    error_type = type(error)
    qualified_type = (error_type.__module__, error_type.__name__)
    if qualified_type in {
        ("features.daily_briefing.finalize", "BriefingFinalizationError"),
        ("features.common.job_json_schema", "JobArtifactValidationError"),
    }:
        reason, exception, confirmation = "validation", "validation_error", "observed"
    elif qualified_type == ("features.agent_mode.bridge", "AgentRateLimitError"):
        reason, exception, confirmation = "rate_limit", "runtime_error", "observed"
    elif qualified_type == ("features.agent_mode.bridge", "AgentOutputValidationError"):
        reason, exception, confirmation = "validation", "validation_error", "observed"
    elif qualified_type == ("features.agent_mode.bridge", "AgentProcessError"):
        reason, exception, confirmation = "adapter_failed", "runtime_error", "observed"
    elif qualified_type == ("features.agent_mode.bridge", "AgentAdapterUnavailableError"):
        reason, exception, confirmation = "adapter_unavailable", "runtime_error", "observed"
    elif (
        qualified_type == ("features.llm_settings.client", "LlmRequestError")
        and type(getattr(error, "status_code", None)) is int
        and getattr(error, "status_code") == 429
    ):
        reason, exception, confirmation = "rate_limit", "llm_request_error", "observed"
    elif isinstance(error, subprocess.TimeoutExpired):
        reason, exception, confirmation = "timeout", "process_timeout", "observed"
    elif isinstance(error, TimeoutError):
        reason, exception, confirmation = "timeout", "timeout_error", "observed"
    elif isinstance(error, PermissionError):
        exception = "permission_error"
        if boundary == "save":
            reason, confirmation = "save_permission", "observed"
    elif isinstance(error, FileNotFoundError):
        exception = "file_not_found"
        if boundary == "adapter":
            reason, confirmation = "adapter_unavailable", "observed"
    elif isinstance(error, ValueError):
        exception = "validation_error" if boundary == "validation" else "other"
        if boundary == "validation":
            reason, confirmation = "validation", "observed"
        elif boundary == "save":
            reason, confirmation = "save_failed", "observed"
    elif isinstance(error, RuntimeError):
        exception = "runtime_error"
        if boundary == "save":
            reason, confirmation = "save_failed", "observed"
    if boundary == "cleanup":
        # The observer should use this only for its already-typed cleanup
        # boundary; no attribute or message inspection happens here.
        reason, exception, confirmation = "private_cleanup_failed", "private_cleanup_error", "observed"
    elif boundary == "store":
        reason, exception, confirmation = "store_unavailable", "jobs_store_error", "observed"
    elif boundary == "recovery":
        reason, confirmation = "commit_recovery_failed", "observed"
    elif boundary == "cancel":
        reason, confirmation = "cancelled", "observed"
    next_action = "inspect_result" if reason in {"commit_unknown", "commit_recovery_failed", "store_unavailable"} else "contact_support"
    return safe_failure(stage_id=stage_id, stage_code=stage_code, reason_code=reason, exception_code=exception, confirmation=confirmation, next_action_code=next_action, frames=frames)
