"""In-memory lifecycle recorder for one diagnostic run.

All mutation is private to this module.  Public observer calls are explicitly
best effort: malformed producer input is converted into ``invalid_event`` and
storage trouble never replaces the producer's own error path.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import threading
import time
from typing import TYPE_CHECKING, Any, Mapping

from features.common.canonical_json import canonical_json_bytes

from .schema import (
    AUTHORITY_KINDS, EVENT_CODES, FEATURE_CODES, ISSUE_CODES, MAX_ERRORS,
    MAX_EVENTS, MAX_ISSUES, OBSERVED_STATUSES, RESERVED_TERMINAL_BYTES,
    ROUTE_CODES, SCHEMA_VERSION, STAGE_CODES, DiagnosticContext,
    DiagnosticValidationError, Failure, SafeFrame, _bounded_int, _code,
    new_id, safe_failure, utc_z, valid_id, valid_utc_z,
)

if TYPE_CHECKING:
    from .store import DiagnosticsStore


# ``complete`` is deliberately narrower than the schema's code registries.
# These two SharedJob producers have an audited authority transition and
# bounded producer boundary in L1c. Other known route codes remain partial
# until their complete call-chain audit exists; enum membership is never proof.
_COMPLETE_SHARED_JOB_PATHS = frozenset({
    ("index", "index_build", "index"),
    ("rss", "rss_collect", "rss"),
})
_TERMINAL_AUTHORITY_STATUSES = frozenset({
    "done", "cancelled", "failed", "failed_cancel", "failed_commit",
    "failed_restart", "failed_commit_recovery",
})


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    seq: int
    event_id: str
    stage_id: str
    stage_code: str
    event_code: str
    producer_epoch: str
    at: str
    duration_ms: int | None = None
    error_id: str | None = None
    count: int = 1

    def __post_init__(self) -> None:
        _bounded_int(self.seq, "event_seq", 1)
        valid_id(self.event_id, "evt")
        valid_id(self.stage_id, "stg")
        _code(self.stage_code, STAGE_CODES, "stage_code")
        _code(self.event_code, EVENT_CODES, "event_code")
        from .schema import _valid_uuid
        _valid_uuid(self.producer_epoch, "producer_epoch")
        valid_utc_z(self.at)
        if self.duration_ms is not None:
            _bounded_int(self.duration_ms, "duration_ms", 0, 604_800_000)
        if self.error_id is not None:
            valid_id(self.error_id, "err")
        _bounded_int(self.count, "event_count", 1)

    def to_dict(self) -> dict[str, object]:
        return {"seq": self.seq, "eventId": self.event_id, "stageId": self.stage_id, "stageCode": self.stage_code, "eventCode": self.event_code, "producerEpoch": self.producer_epoch, "at": self.at, "durationMs": self.duration_ms, "errorId": self.error_id, "count": self.count}


@dataclass(frozen=True, slots=True)
class TerminalObservation:
    observed_status: str
    observed_at: str
    process_epoch: str

    def __post_init__(self) -> None:
        _code(self.observed_status, OBSERVED_STATUSES, "observed_status")
        valid_utc_z(self.observed_at)
        from .schema import _valid_uuid
        _valid_uuid(self.process_epoch, "observation_epoch")

    def to_dict(self) -> dict[str, object]:
        return {"observedStatus": self.observed_status, "observedAt": self.observed_at, "processEpoch": self.process_epoch}


@dataclass(frozen=True, slots=True)
class DiagnosticRecord:
    context: DiagnosticContext
    created_at: str
    updated_at: str
    finished_at: str | None
    elapsed_ms: int | None
    observed_status: str
    attempted_engine: str | None
    final_engine: str | None
    adapter: str | None
    fallback_reason: str | None
    events: tuple[DiagnosticEvent, ...]
    errors: tuple[Failure, ...]
    first_failure: Failure | None
    terminal_failure: Failure | None
    terminal_observation: TerminalObservation | None
    dropped_events: int
    dropped_errors: int
    dropped_issues: int
    issue_codes: tuple[str, ...]
    required_producer_coverage: str = "partial"

    def __post_init__(self) -> None:
        valid_utc_z(self.created_at); valid_utc_z(self.updated_at)
        if self.finished_at is not None:
            valid_utc_z(self.finished_at)
        if self.elapsed_ms is not None:
            _bounded_int(self.elapsed_ms, "elapsed_ms", 0, 604_800_000)
        _code(self.observed_status, OBSERVED_STATUSES, "observed_status")
        from .schema import ADAPTERS, ENGINES, FALLBACK_REASONS
        _code(self.attempted_engine, ENGINES, "attempted_engine", nullable=True)
        _code(self.final_engine, ENGINES, "final_engine", nullable=True)
        _code(self.adapter, ADAPTERS, "adapter", nullable=True)
        _code(self.fallback_reason, FALLBACK_REASONS, "fallback_reason", nullable=True)
        if type(self.events) is not tuple or type(self.errors) is not tuple or type(self.issue_codes) is not tuple:
            raise DiagnosticValidationError("invalid_record_collections")
        if len(self.events) > MAX_EVENTS or len(self.errors) > MAX_ERRORS:
            raise DiagnosticValidationError("record_limit_exceeded")
        if len({item.event_id for item in self.events}) != len(self.events):
            raise DiagnosticValidationError("duplicate_event_id")
        if [item.seq for item in self.events] != list(range(1, len(self.events) + 1)):
            raise DiagnosticValidationError("invalid_event_sequence")
        if len({item.error_id for item in self.errors if isinstance(item, Failure)}) != len(self.errors) or not all(isinstance(item, Failure) for item in self.errors):
            raise DiagnosticValidationError("invalid_errors")
        for candidate, code in ((self.first_failure, "first_failure_not_stored"), (self.terminal_failure, "terminal_failure_not_stored")):
            if candidate is not None:
                matching = next((item for item in self.errors if item.error_id == candidate.error_id), None)
                if matching != candidate:
                    raise DiagnosticValidationError(code)
        for value in (self.dropped_events, self.dropped_errors, self.dropped_issues):
            _bounded_int(value, "dropped_count")
        if len(self.issue_codes) > MAX_ISSUES or len(set(self.issue_codes)) != len(self.issue_codes):
            raise DiagnosticValidationError("invalid_issue_codes")
        if not all(code in ISSUE_CODES for code in self.issue_codes):
            raise DiagnosticValidationError("invalid_issue_codes")
        if self.required_producer_coverage not in {"complete", "partial"}:
            raise DiagnosticValidationError("invalid_producer_coverage")
        opened: dict[str, tuple[str, str]] = {}
        seen_stages: set[str] = set()
        for event in self.events:
            if event.event_code == "start":
                if event.stage_id in seen_stages:
                    raise DiagnosticValidationError("duplicate_stage_start")
                seen_stages.add(event.stage_id)
                opened[event.stage_id] = (event.stage_code, event.producer_epoch)
                continue
            state = opened.get(event.stage_id)
            if state is None or state != (event.stage_code, event.producer_epoch):
                raise DiagnosticValidationError("invalid_stage_ownership")
            if event.event_code == "end":
                del opened[event.stage_id]
        if self.required_producer_coverage == "complete" and not _can_be_complete(self, opened):
            raise DiagnosticValidationError("invalid_complete_coverage")

    @property
    def run_id(self) -> str:
        return self.context.run_id

    def to_dict(self) -> dict[str, object]:
        return {"schemaVersion": SCHEMA_VERSION, **self.context.to_identity_dict(), "createdAt": self.created_at, "updatedAt": self.updated_at, "finishedAt": self.finished_at, "elapsedMs": self.elapsed_ms, "observedStatus": self.observed_status, "attemptedEngine": self.attempted_engine, "finalEngine": self.final_engine, "adapter": self.adapter, "fallbackReason": self.fallback_reason, "events": [event.to_dict() for event in self.events], "errors": [failure.to_dict() for failure in self.errors], "firstFailure": self.first_failure.to_dict() if self.first_failure else None, "terminalFailure": self.terminal_failure.to_dict() if self.terminal_failure else None, "terminalObservation": self.terminal_observation.to_dict() if self.terminal_observation else None, "droppedEvents": self.dropped_events, "droppedErrors": self.dropped_errors, "droppedIssues": self.dropped_issues, "issueCodes": list(self.issue_codes), "requiredProducerCoverage": self.required_producer_coverage}

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    @classmethod
    def new(cls, context: DiagnosticContext, *, now: str | None = None) -> "DiagnosticRecord":
        instant = now or utc_z()
        return cls(context, instant, instant, None, 0, "running", None, None, None, None, (), (), None, None, None, 0, 0, 0, ())


def _can_be_complete(record: DiagnosticRecord, opened: Mapping[str, tuple[str, str]] | None = None) -> bool:
    """Validate the deliberately small L1c complete-coverage claim.

    A completed product job can still have incomplete diagnostics.  This
    predicate therefore requires the audited path, an authority terminal
    observation, no observer loss markers, and no open stage in the original
    process.  Current-authority agreement is checked again by projection.
    """
    context = record.context
    if (
        context.authority_kind != "shared_job"
        or context.job_id is None
        or (context.feature_code, context.route_code, context.task_type) not in _COMPLETE_SHARED_JOB_PATHS
        or record.finished_at is None
        or record.terminal_observation is None
        or record.observed_status not in _TERMINAL_AUTHORITY_STATUSES
        or record.terminal_observation.observed_status != record.observed_status
        or record.dropped_events != 0
        or record.dropped_errors != 0
        or record.dropped_issues != 0
        or record.issue_codes
        or any(not failure.frames for failure in record.errors)
    ):
        return False
    if opened is None:
        active: dict[str, tuple[str, str]] = {}
        for event in record.events:
            if event.event_code == "start":
                active[event.stage_id] = (event.stage_code, event.producer_epoch)
            elif event.event_code == "end":
                active.pop(event.stage_id, None)
        opened = active
    return not opened


def _exact(mapping: object, keys: set[str], code: str) -> Mapping[str, Any]:
    if type(mapping) is not dict or set(mapping) != keys:
        raise DiagnosticValidationError(code)
    return mapping


def _frame_from_dict(raw: object) -> SafeFrame:
    row = _exact(raw, {"moduleCode", "functionCode", "line"}, "invalid_frame_fields")
    return SafeFrame(row["moduleCode"], row["functionCode"], row["line"])


def _failure_from_dict(raw: object) -> Failure:
    row = _exact(raw, {"errorId", "stageId", "stageCode", "errorCode", "reasonCode", "exceptionCode", "frames", "confirmation", "nextActionCode", "fingerprint"}, "invalid_failure_fields")
    if not isinstance(row["frames"], list):
        raise DiagnosticValidationError("invalid_frames")
    return Failure(row["errorId"], row["stageId"], row["stageCode"], row["errorCode"], row["reasonCode"], row["exceptionCode"], tuple(_frame_from_dict(item) for item in row["frames"]), row["confirmation"], row["nextActionCode"], row["fingerprint"])


def _event_from_dict(raw: object) -> DiagnosticEvent:
    row = _exact(raw, {"seq", "eventId", "stageId", "stageCode", "eventCode", "producerEpoch", "at", "durationMs", "errorId", "count"}, "invalid_event_fields")
    return DiagnosticEvent(row["seq"], row["eventId"], row["stageId"], row["stageCode"], row["eventCode"], row["producerEpoch"], row["at"], row["durationMs"], row["errorId"], row["count"])


def _record_from_dict_unchecked(raw: object) -> DiagnosticRecord:
    keys = {"schemaVersion", "runId", "jobId", "requestId", "parentRunId", "retryOfRunId", "processEpoch", "featureCode", "routeCode", "taskType", "authorityKind", "appVersion", "buildId", "os", "pythonVersion", "createdAt", "updatedAt", "finishedAt", "elapsedMs", "observedStatus", "attemptedEngine", "finalEngine", "adapter", "fallbackReason", "events", "errors", "firstFailure", "terminalFailure", "terminalObservation", "droppedEvents", "droppedErrors", "droppedIssues", "issueCodes", "requiredProducerCoverage"}
    row = _exact(raw, keys, "invalid_record_fields")
    if type(row["schemaVersion"]) is not int or row["schemaVersion"] != SCHEMA_VERSION:
        raise DiagnosticValidationError("unsupported_schema")
    context = DiagnosticContext(run_id=row["runId"], request_id=row["requestId"], feature_code=row["featureCode"], route_code=row["routeCode"], task_type=row["taskType"], authority_kind=row["authorityKind"], process_epoch=row["processEpoch"], producer_epoch=row["processEpoch"], job_id=row["jobId"], parent_run_id=row["parentRunId"], retry_of_run_id=row["retryOfRunId"], app_version=row["appVersion"], build_id=row["buildId"], os_code=row["os"], python_version=row["pythonVersion"])
    if type(row["events"]) is not list or type(row["errors"]) is not list or type(row["issueCodes"]) is not list:
        raise DiagnosticValidationError("invalid_record_collections")
    observation = row["terminalObservation"]
    terminal_observation = None if observation is None else TerminalObservation(**{"observed_status": _exact(observation, {"observedStatus", "observedAt", "processEpoch"}, "invalid_terminal_fields")["observedStatus"], "observed_at": observation["observedAt"], "process_epoch": observation["processEpoch"]})
    return DiagnosticRecord(context=context, created_at=row["createdAt"], updated_at=row["updatedAt"], finished_at=row["finishedAt"], elapsed_ms=row["elapsedMs"], observed_status=row["observedStatus"], attempted_engine=row["attemptedEngine"], final_engine=row["finalEngine"], adapter=row["adapter"], fallback_reason=row["fallbackReason"], events=tuple(_event_from_dict(item) for item in row["events"]), errors=tuple(_failure_from_dict(item) for item in row["errors"]), first_failure=None if row["firstFailure"] is None else _failure_from_dict(row["firstFailure"]), terminal_failure=None if row["terminalFailure"] is None else _failure_from_dict(row["terminalFailure"]), terminal_observation=terminal_observation, dropped_events=row["droppedEvents"], dropped_errors=row["droppedErrors"], dropped_issues=row["droppedIssues"], issue_codes=tuple(row["issueCodes"]), required_producer_coverage=row["requiredProducerCoverage"])


def record_from_dict(raw: object) -> DiagnosticRecord:
    try:
        return _record_from_dict_unchecked(raw)
    except DiagnosticValidationError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise DiagnosticValidationError("invalid_record") from None


class DiagnosticRecorder:
    """A lifecycle handle which cannot propagate diagnostics failures."""

    def __init__(self, store: "DiagnosticsStore", record: DiagnosticRecord, context: DiagnosticContext, *, owner_token: object, run_lock: threading.RLock | None = None, monotonic_started: float | None = None) -> None:
        self._store, self._record, self.context = store, record, context
        self._owner_token = owner_token
        self._lock = run_lock or threading.RLock()
        self._monotonic_started = monotonic_started
        self._stage_started: dict[str, float] = {}
        # This exists only on a live handle.  A route/task enum is not proof:
        # the concrete producer must attest after its own audited boundary.
        self._complete_coverage_proven = False

    @property
    def record(self) -> DiagnosticRecord:
        with self._lock:
            return self._record

    @property
    def complete_coverage_proven(self) -> bool:
        with self._lock:
            return self._complete_coverage_proven

    def prove_complete_coverage(self) -> bool:
        """Accept only an internal attestation for the two audited paths."""
        with self._lock:
            context = self.context
            if (
                self._record.finished_at is not None
                or context.authority_kind != "shared_job"
                or (context.feature_code, context.route_code, context.task_type) not in _COMPLETE_SHARED_JOB_PATHS
            ):
                return False
            self._complete_coverage_proven = True
            return True

    def _issue(self, code: str) -> None:
        record = self._record
        if code not in ISSUE_CODES:
            code = "invalid_event"
        issues = list(record.issue_codes)
        dropped = record.dropped_issues
        if code not in issues:
            if len(issues) < MAX_ISSUES - 1 or code == "issue_limit":
                issues.append(code)
            elif "issue_limit" not in issues:
                issues.append("issue_limit")
                dropped = min(1_000_000, dropped + 1)
            else:
                dropped = min(1_000_000, dropped + 1)
        self._record = replace(record, issue_codes=tuple(issues), dropped_issues=dropped, required_producer_coverage="partial")

    def _sync(self) -> bool:
        try:
            persisted = self._store.persist(self._record, owner_token=self._owner_token)
            if not persisted:
                # This in-memory marker is intentionally not retried: storage
                # may be the failure and diagnostics must not recurse.
                self._issue("write_failed")
                self._store.note_warning("write_failed", self.context.run_id)
            return persisted
        except Exception:  # diagnostic best effort must not escape a producer
            self._issue("write_failed")
            self._store.note_warning("write_failed", self.context.run_id)
            return False

    def observe_authority_status(self, observed_status: str) -> bool:
        """Persist a real authority transition without inventing a stage."""
        with self._lock:
            try:
                _code(observed_status, OBSERVED_STATUSES, "observed_status")
                if self._record.finished_at is not None:
                    return False
                if self._record.observed_status == observed_status:
                    return True
                self._record = replace(
                    self._record,
                    observed_status=observed_status,
                    updated_at=utc_z(),
                )
                return self._sync()
            except (DiagnosticValidationError, ValueError, TypeError):
                self._issue("invalid_event")
                self._sync()
                return False

    def observe_execution(
        self,
        *,
        attempted_engine: str | None = None,
        final_engine: str | None = None,
        adapter: str | None = None,
        fallback_reason: str | None = None,
    ) -> bool:
        """Persist only closed execution facts observed at a producer edge."""
        with self._lock:
            try:
                from .schema import ADAPTERS, ENGINES, FALLBACK_REASONS

                if attempted_engine is not None:
                    _code(attempted_engine, ENGINES, "attempted_engine")
                if final_engine is not None:
                    _code(final_engine, ENGINES, "final_engine")
                if adapter is not None:
                    _code(adapter, ADAPTERS, "adapter")
                if fallback_reason is not None:
                    _code(fallback_reason, FALLBACK_REASONS, "fallback_reason")
                if self._record.finished_at is not None:
                    return False
                self._record = replace(
                    self._record,
                    # Execution facts belong to the primary producer edge.
                    # Later helper calls (quality/context/auxiliary CLI) must
                    # not rewrite an already observed report outcome.
                    attempted_engine=self._record.attempted_engine or attempted_engine,
                    final_engine=self._record.final_engine or final_engine,
                    adapter=self._record.adapter or adapter,
                    fallback_reason=self._record.fallback_reason or fallback_reason,
                    updated_at=utc_z(),
                )
                return self._sync()
            except (DiagnosticValidationError, ValueError, TypeError):
                self._issue("invalid_event")
                self._sync()
                return False

    def event(self, *, stage_id: str, stage_code: str, event_code: str, event_id: str | None = None, duration_ms: int | None = None, error_id: str | None = None, at: str | None = None) -> bool:
        with self._lock:
            try:
                valid_id(stage_id, "stg"); _code(stage_code, STAGE_CODES, "stage_code"); _code(event_code, EVENT_CODES, "event_code")
                if event_id is not None:
                    valid_id(event_id, "evt")
                    if event_id in {item.event_id for item in self._record.events}:
                        return True
                if len(self._record.events) >= MAX_EVENTS:
                    self._record = replace(self._record, dropped_events=min(1_000_000, self._record.dropped_events + 1))
                    self._issue("event_limit")
                    self._sync(); return False
                candidate = DiagnosticEvent(len(self._record.events) + 1, event_id or new_id("evt"), stage_id, stage_code, event_code, self.context.producer_epoch, at or utc_z(), duration_ms, error_id)
                # Preserve terminal capacity: normal events cannot consume its reserved tail.
                proposed = replace(self._record, events=self._record.events + (candidate,), updated_at=candidate.at)
                if len(proposed.to_bytes()) > 128 * 1024 - RESERVED_TERMINAL_BYTES:
                    self._record = replace(self._record, dropped_events=min(1_000_000, self._record.dropped_events + 1))
                    self._issue("byte_limit"); self._sync(); return False
                self._record = proposed
                return self._sync()
            except (DiagnosticValidationError, ValueError, TypeError):
                self._issue("invalid_event"); self._sync(); return False

    def start_stage(self, stage_code: str, *, at: str | None = None) -> str | None:
        stage_id = new_id("stg")
        if not self.event(stage_id=stage_id, stage_code=stage_code, event_code="start", at=at):
            return None
        if self._monotonic_started is not None and self.context.producer_epoch == self._record.context.process_epoch:
            self._stage_started[stage_id] = time.monotonic()
        return stage_id

    def end_stage(self, stage_id: str, stage_code: str, *, duration_ms: int | None = None, at: str | None = None) -> bool:
        if duration_ms is None:
            started = self._stage_started.get(stage_id)
            if started is not None and self.context.producer_epoch == self._record.context.process_epoch:
                duration_ms = max(0, min(604_800_000, int((time.monotonic() - started) * 1000)))
        persisted = self.event(stage_id=stage_id, stage_code=stage_code, event_code="end", duration_ms=duration_ms, at=at)
        if persisted:
            self._stage_started.pop(stage_id, None)
        return persisted

    def failure(self, failure: Failure | None = None, *, stage_id: str | None = None, stage_code: str | None = None, reason_code: str = "unknown", exception_code: str = "other", terminal: bool = False) -> str | None:
        with self._lock:
            try:
                item = failure or safe_failure(stage_id=stage_id, stage_code=stage_code, reason_code=reason_code, exception_code=exception_code)
                item, source_dropped = self._store.sanitize_failure(item)
                if source_dropped:
                    self._issue("source_unavailable")
                existing = next((saved for saved in self._record.errors if saved.error_id == item.error_id), None)
                if existing is not None:
                    if terminal:
                        self._record = replace(self._record, terminal_failure=existing, updated_at=utc_z())
                        self._sync()
                    return existing.error_id
                # One slot is permanently held for a distinct terminal failure.
                limit = MAX_ERRORS if terminal else MAX_ERRORS - 1
                if len(self._record.errors) >= limit:
                    self._record = replace(self._record, dropped_errors=min(1_000_000, self._record.dropped_errors + 1))
                    self._issue("error_limit"); self._sync(); return None
                now = utc_z()
                first = self._record.first_failure or item
                self._record = replace(self._record, errors=self._record.errors + (item,), first_failure=first, terminal_failure=item if terminal else self._record.terminal_failure, updated_at=now)
                if item.stage_id is not None and item.stage_code is not None:
                    self.event(stage_id=item.stage_id, stage_code=item.stage_code, event_code="failure", error_id=item.error_id, at=now)
                self._sync()
                return item.error_id
            except (DiagnosticValidationError, ValueError, TypeError):
                self._issue("invalid_event"); self._sync(); return None

    def finish(
        self,
        observed_status: str,
        *,
        terminal_failure: Failure | None = None,
        at: str | None = None,
        coverage_complete: bool = False,
    ) -> bool:
        with self._lock:
            try:
                _code(observed_status, OBSERVED_STATUSES, "observed_status")
                instant = at or utc_z()
                stored_terminal = self._record.terminal_failure
                if terminal_failure is not None and terminal_failure.error_id not in {item.error_id for item in self._record.errors}:
                    # ``finish`` must not leave a terminal reference outside
                    # bounded storage.  The reserved slot is handled by failure.
                    if self.failure(terminal_failure, terminal=True) is None:
                        return False
                if terminal_failure is not None:
                    # ``failure`` may deliberately strip an unregistered
                    # source frame.  Never put the caller's unsanitized
                    # object back into the terminal reference.
                    stored_terminal = next(
                        (item for item in self._record.errors if item.error_id == terminal_failure.error_id),
                        self._record.terminal_failure,
                    )
                elapsed: int | None = None
                # Wall-clock deltas are not elapsed time.  A handle recreated
                # after a crash has no trusted monotonic origin and stays null.
                if self._monotonic_started is not None and self.context.producer_epoch == self._record.context.process_epoch:
                    elapsed = max(0, min(604_800_000, int((time.monotonic() - self._monotonic_started) * 1000)))
                terminal_record = replace(
                    self._record,
                    observed_status=observed_status,
                    finished_at=instant,
                    elapsed_ms=elapsed,
                    terminal_failure=stored_terminal,
                    terminal_observation=TerminalObservation(observed_status, instant, self.context.producer_epoch),
                    updated_at=instant,
                )
                # Terminal persistence releases the store owner, so the
                # narrowly audited label must be part of this same atomic
                # terminal document—not a best-effort follow-up write.
                if coverage_complete and _can_be_complete(terminal_record):
                    terminal_record = replace(terminal_record, required_producer_coverage="complete")
                self._record = terminal_record
                persisted = self._sync()
                if not persisted:
                    self._store.abandon_terminal(self.context.run_id, owner_token=self._owner_token)
                return persisted
            except (DiagnosticValidationError, ValueError, TypeError):
                self._issue("invalid_event"); self._sync(); return False

    def promote_complete(self) -> bool:
        """Persist the narrow audited complete claim, or leave partial."""
        with self._lock:
            if self._record.required_producer_coverage == "complete":
                return True
            try:
                candidate = replace(self._record, required_producer_coverage="complete", updated_at=utc_z())
                # Construction re-runs the closed audit predicate; it is not
                # enough for a caller merely to request a complete label.
                if not _can_be_complete(candidate):
                    return False
                self._record = candidate
                if self._sync():
                    return True
            except (DiagnosticValidationError, ValueError, TypeError):
                return False
            self._record = replace(candidate, required_producer_coverage="partial")
            return False

    def recover(self, observed_status: str = "unknown") -> bool:
        with self._lock:
            if self.context.producer_epoch == self._record.context.process_epoch:
                self.context = self.context.with_recovery_producer()
            self._record = replace(self._record, elapsed_ms=None, updated_at=utc_z())
            self._issue("recovery_gap")
            stage = self.start_stage("recovery")
            if stage is not None:
                self.event(stage_id=stage, stage_code="recovery", event_code="resume")
            if observed_status != "unknown":
                return self.finish(observed_status)
            return self._sync()
