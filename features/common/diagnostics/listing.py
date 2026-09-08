"""Read-only, bounded diagnostic run list projection.

The detail endpoint deliberately remains a full-record read.  This module is
the separate list path: a fresh request validates each run once into a small
safe header, then cursor requests reuse that immutable header snapshot and
only re-check current authority visibility.  It never calls ``DiagnosticsStore``
accounting, a writer lease, ``WorkLogService``, or a durable store recovery
method.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import json
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from typing import Any, Callable, Final, Iterable, Mapping

from .authority import (
    AuthoritySnapshot,
    AuthoritySnapshotUnavailable,
    _safe_path,
    default_authority_snapshot,
)
from .record import DiagnosticRecord, record_from_dict
from .schema import (
    FEATURE_CODES,
    DiagnosticValidationError,
    valid_id,
    valid_utc_z,
)
from .store import MAX_DOCUMENT_BYTES, DiagnosticsStore, _is_reparse


LIST_VERSION: Final = 1
DEFAULT_LIMIT: Final = 20
MAX_LIMIT: Final = 100
MAX_HEADERS: Final = 4096
MAX_SNAPSHOTS: Final = 8
MAX_CURSOR_TOKENS: Final = MAX_HEADERS
SNAPSHOT_TTL_SECONDS: Final = 300.0
SCAN_ENTRY_LIMIT: Final = 5000
SCAN_DEADLINE_SECONDS: Final = 0.250
MAX_SCAN_ERRORS: Final = 8

FAILED_STATUSES: Final = frozenset(
    {
        "failed",
        "failed_cancel",
        "failed_commit",
        "failed_restart",
        "failed_commit_recovery",
    }
)
ACTIVE_STATUSES: Final = frozenset(
    {"queued", "running", "cancel_requested", "committing"}
)
OUTCOMES: Final = frozenset({"all", "succeeded", "failed", "cancelled", "running", "unknown"})
FALLBACK_FILTERS: Final = frozenset({"all", "observed"})


class ListQueryError(ValueError):
    """A closed query parameter failed validation."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ListCursorError(ValueError):
    """A client cursor cannot be used for the current list request."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ListUnavailable(RuntimeError):
    """A diagnostics directory cannot be read safely."""

    def __init__(self, code: str = "diagnostics_unavailable") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ListQuery:
    version: int = LIST_VERSION
    limit: int = DEFAULT_LIMIT
    feature: str | None = None
    outcome: str = "all"
    fallback: str = "all"
    from_at: datetime | None = None
    to_at: datetime | None = None

    def canonical(self) -> tuple[object, ...]:
        return (
            self.version,
            self.limit,
            self.feature,
            self.outcome,
            self.fallback,
            self.from_at.isoformat() if self.from_at is not None else None,
            self.to_at.isoformat() if self.to_at is not None else None,
        )


@dataclass(frozen=True, slots=True)
class RunHeader:
    """Validated safe fields retained after the cold scan."""

    run_id: str
    created_at: str
    created_dt: datetime
    finished_at: str | None
    observed_status: str
    feature_code: str
    route_code: str
    authority_kind: str
    task_type: str | None
    job_id: str | None
    adapter: str | None
    attempted_engine: str | None
    final_engine: str | None
    fallback_reason: str | None
    required_coverage: str
    failure_reason: str | None
    failure_stage: str | None
    fallback_observed: bool | None


@dataclass(frozen=True, slots=True)
class ListItem:
    payload: dict[str, Any]
    created_dt: datetime
    run_id: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    headers: tuple[RunHeader, ...]
    entries_scanned: int
    runs_scanned: int
    complete: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CachedSnapshot:
    snapshot_id: str
    query: ListQuery
    items: tuple[ListItem, ...]
    authority_revision: str
    snapshot_at: str
    created_monotonic: float
    entries_scanned: int
    runs_scanned: int
    complete: bool
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CursorState:
    token: str
    snapshot_id: str
    query: ListQuery
    index: int
    expires_monotonic: float


def _parse_utc(value: str, field: str) -> datetime:
    try:
        normalized = valid_utc_z(value)
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(UTC)
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise ListQueryError(f"invalid_{field}") from error


def parse_list_query(query_params: Mapping[str, Any]) -> tuple[ListQuery, str | None]:
    """Parse exactly one value for each closed query key.

    ``query_params`` may be Starlette's ``QueryParams`` or a plain mapping.
    The route performs duplicate detection using ``multi_items`` before
    calling this helper; accepting a mapping here keeps unit tests simple.
    """

    allowed = {"version", "limit", "cursor", "feature", "outcome", "fallback", "from", "to"}
    if hasattr(query_params, "keys"):
        unknown = set(query_params.keys()) - allowed
        if unknown:
            raise ListQueryError("unknown_query_parameter")

    def one(key: str, default: str | None = None) -> str | None:
        value = query_params.get(key, default)
        if isinstance(value, (list, tuple)):
            if len(value) != 1:
                raise ListQueryError("duplicate_query_parameter")
            value = value[0]
        if value is None:
            return default
        if not isinstance(value, str) or len(value) > 128:
            raise ListQueryError(f"invalid_{key}")
        return value

    version_raw = one("version", "1")
    if version_raw != "1":
        raise ListQueryError("unsupported_version")
    limit_raw = one("limit", str(DEFAULT_LIMIT))
    if limit_raw is None or not limit_raw.isdecimal():
        raise ListQueryError("invalid_limit")
    limit = int(limit_raw)
    if not 1 <= limit <= MAX_LIMIT:
        raise ListQueryError("invalid_limit")

    feature = one("feature")
    if feature is not None and feature not in FEATURE_CODES:
        raise ListQueryError("invalid_feature")
    outcome = one("outcome", "all") or "all"
    if outcome not in OUTCOMES:
        raise ListQueryError("invalid_outcome")
    fallback = one("fallback", "all") or "all"
    if fallback not in FALLBACK_FILTERS:
        raise ListQueryError("invalid_fallback")
    from_raw, to_raw = one("from"), one("to")
    from_at = _parse_utc(from_raw, "from") if from_raw is not None else None
    to_at = _parse_utc(to_raw, "to") if to_raw is not None else None
    if from_at is not None and to_at is not None and from_at >= to_at:
        raise ListQueryError("invalid_period")
    cursor = one("cursor")
    if cursor == "":
        raise ListCursorError("cursor_expired")
    return ListQuery(version=1, limit=limit, feature=feature, outcome=outcome, fallback=fallback, from_at=from_at, to_at=to_at), cursor


def _readable_stat(path: Path) -> os.stat_result:
    try:
        item = path.lstat()
    except FileNotFoundError as error:
        raise ListUnavailable("diagnostics_unavailable") from error
    except OSError as error:
        raise ListUnavailable() from error
    if _is_reparse(path):
        raise ListUnavailable("diagnostics_reparse")
    return item


def _header_from_record(record: DiagnosticRecord, run_id: str) -> RunHeader:
    if record.run_id != run_id:
        raise DiagnosticValidationError("invalid_record_path")
    try:
        created_dt = datetime.fromisoformat(record.created_at.replace("Z", "+00:00")).astimezone(UTC)
    except (TypeError, ValueError) as error:
        raise DiagnosticValidationError("invalid_timestamp") from error
    failure = record.terminal_failure or record.first_failure
    return RunHeader(
        run_id=record.run_id,
        created_at=record.created_at,
        created_dt=created_dt,
        finished_at=record.finished_at,
        observed_status=record.observed_status,
        feature_code=record.context.feature_code,
        route_code=record.context.route_code,
        authority_kind=record.context.authority_kind,
        task_type=record.context.task_type,
        job_id=record.context.job_id,
        adapter=record.adapter,
        attempted_engine=record.attempted_engine,
        final_engine=record.final_engine,
        fallback_reason=record.fallback_reason,
        required_coverage=record.required_producer_coverage,
        failure_reason=failure.reason_code if failure is not None else None,
        failure_stage=failure.stage_code if failure is not None else None,
        fallback_observed=(
            True
            if record.fallback_reason is not None or any(event.event_code == "fallback" for event in record.events)
            else None
        ),
    )


def _append_error(errors: list[str], code: str) -> None:
    if code not in errors and len(errors) < MAX_SCAN_ERRORS:
        errors.append(code)


@dataclass(slots=True)
class _HeaderScanState:
    validation_key: tuple[str, tuple[tuple[str, str], ...], tuple[tuple[str, tuple[int, int, int] | None], ...]]
    directory_path: str
    directory_signature: tuple[int, int, int]
    iterator: Any
    headers: dict[str, RunHeader]
    signatures: dict[str, tuple[int, int, int]]
    seen_paths: set[str]
    entries_scanned: int = 0
    runs_scanned: int = 0
    errors: list[str] | None = None
    complete: bool = False
    terminal: bool = False
    refresh_iterator: Any | None = None
    refresh_seen_paths: set[str] | None = None
    refresh_entries_scanned: int = 0

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
        if self.refresh_seen_paths is None:
            self.refresh_seen_paths = set()


class DiagnosticsHeaderCache:
    """Resumable bounded scan/cache independent of DiagnosticsStore accounting."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._state: _HeaderScanState | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _directory_signature(path: Path) -> tuple[int, int, int]:
        item = _readable_stat(path)
        if not stat.S_ISDIR(item.st_mode):
            raise ListUnavailable("diagnostics_unavailable")
        return (item.st_size, item.st_mtime_ns, getattr(item, "st_ino", 0))

    def _close(self) -> None:
        state, self._state = self._state, None
        if state is not None:
            try:
                state.iterator.close()
            except Exception:
                pass
            if state.refresh_iterator is not None:
                try:
                    state.refresh_iterator.close()
                except Exception:
                    pass

    def _empty(self) -> ScanResult:
        self._close()
        return ScanResult((), 0, 0, True, ())

    @staticmethod
    def _validation_key(store: DiagnosticsStore) -> tuple[str, tuple[tuple[str, str], ...], tuple[tuple[str, tuple[int, int, int] | None], ...]]:
        app_root = Path(store.app_root)
        # Validate the source root even when a producer supplied an empty
        # registry; otherwise the canonical app-root stamp below could follow
        # a junction before the next request notices it.
        try:
            _safe_path(app_root)
        except AuthoritySnapshotUnavailable as error:
            raise ListUnavailable(error.code) from error
        source_registry = tuple(sorted(tuple(item) for item in store.source_registry))
        if len(source_registry) > 256:
            raise ListUnavailable("diagnostics_unavailable")
        source_stamps: list[tuple[str, tuple[int, int, int] | None]] = []
        for module_code, _function_code in source_registry:
            source_path = app_root / (module_code.replace(".", "/") + ".py")
            try:
                _safe_path(source_path)
                item = source_path.lstat()
            except FileNotFoundError:
                source_stamps.append((module_code, None))
                continue
            except AuthoritySnapshotUnavailable as error:
                raise ListUnavailable(error.code) from error
            except OSError as error:
                raise ListUnavailable() from error
            if not stat.S_ISREG(item.st_mode):
                raise ListUnavailable("diagnostics_unavailable")
            source_stamps.append((module_code, (item.st_size, item.st_mtime_ns, getattr(item, "st_ino", 0))))
        return (
            str(app_root.resolve(strict=False)),
            source_registry,
            tuple(source_stamps),
        )

    def _open(
        self,
        store: DiagnosticsStore,
        runs_root: Path,
        signature: tuple[int, int, int],
    ) -> _HeaderScanState:
        try:
            iterator = os.scandir(runs_root)
        except OSError as error:
            raise ListUnavailable() from error
        validation_key = self._validation_key(store)
        state = _HeaderScanState(
            validation_key,
            str(runs_root.resolve(strict=False)),
            signature,
            iterator,
            {},
            {},
            set(),
        )
        self._state = state
        return state

    def _state_result(self, state: _HeaderScanState, *, complete: bool | None = None, extra_errors: Iterable[str] = ()) -> ScanResult:
        headers = list(state.headers.values())
        headers.sort(key=lambda item: item.run_id)
        headers.sort(key=lambda item: item.created_dt, reverse=True)
        errors = list(state.errors or ())
        for code in extra_errors:
            _append_error(errors, code)
        return ScanResult(
            tuple(headers),
            state.entries_scanned,
            state.runs_scanned,
            state.complete if complete is None else complete,
            tuple(errors),
        )

    def _read_one(self, store: DiagnosticsStore, state: _HeaderScanState, entry: os.DirEntry[str]) -> None:
        path = Path(entry.path)
        try:
            item_stat = path.lstat()
        except OSError as error:
            raise ListUnavailable() from error
        if _is_reparse(path):
            raise ListUnavailable("diagnostics_reparse")
        if not stat.S_ISREG(item_stat.st_mode):
            return
        if path.name == ".writer.lock" or path.suffix != ".json":
            return
        state.runs_scanned += 1
        if state.runs_scanned > MAX_HEADERS:
            _append_error(state.errors, "scan_limit")
            state.complete = False
            state.terminal = True
            try:
                state.iterator.close()
            except Exception:
                pass
            return
        run_id = path.stem
        try:
            valid_id(run_id, "run")
        except DiagnosticValidationError:
            _append_error(state.errors, "invalid_record_path")
            return
        signature = (item_stat.st_size, item_stat.st_mtime_ns, getattr(item_stat, "st_ino", 0))
        state.seen_paths.add(path.name)
        state.signatures[run_id] = signature
        if item_stat.st_size > MAX_DOCUMENT_BYTES:
            _append_error(state.errors, "record_oversized")
            return
        try:
            # Existing bounded JSON, closed schema, and source/AST validation
            # are reused once per changed file.  Nothing here updates writer
            # accounting, leases, or recovery caches.
            raw = store._bounded_json(path)
            record = record_from_dict(raw)
            store._verify_sources(record)
            state.headers[run_id] = _header_from_record(record, run_id)
        except (DiagnosticValidationError, OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError, RecursionError):
            state.headers.pop(run_id, None)
            _append_error(state.errors, "record_corrupt")

    def _refresh_external(
        self,
        store: DiagnosticsStore,
        runs_root: Path,
        state: _HeaderScanState,
        deadline: float,
    ) -> tuple[bool | None, str | None]:
        """Check names and stat signatures without reparsing unchanged records.

        ``None`` means the bounded refresh itself hit its cooperative deadline;
        callers surface that uncertainty as explicit scan progress rather than
        pretending an unchanged complete cache is authoritative.
        """
        if state.refresh_iterator is None:
            try:
                state.refresh_iterator = os.scandir(runs_root)
            except OSError as error:
                raise ListUnavailable() from error
            state.refresh_seen_paths.clear()
            state.refresh_entries_scanned = 0
        try:
            while self.clock() < deadline:
                try:
                    entry = next(state.refresh_iterator)
                except StopIteration:
                    try:
                        state.refresh_iterator.close()
                    except Exception:
                        pass
                    state.refresh_iterator = None
                    changed = state.refresh_seen_paths != state.seen_paths
                    state.refresh_seen_paths.clear()
                    state.refresh_entries_scanned = 0
                    return (True, None) if changed else (False, None)
                state.refresh_entries_scanned += 1
                if state.refresh_entries_scanned > SCAN_ENTRY_LIMIT:
                    return None, "scan_limit"
                path = Path(entry.path)
                item_stat = path.lstat()
                if _is_reparse(path):
                    raise ListUnavailable("diagnostics_reparse")
                state.refresh_seen_paths.add(path.name)
                if not stat.S_ISREG(item_stat.st_mode) or path.name == ".writer.lock" or path.suffix != ".json":
                    continue
                run_id = path.stem
                if run_id not in state.signatures:
                    return True, None
                signature = (item_stat.st_size, item_stat.st_mtime_ns, getattr(item_stat, "st_ino", 0))
                if state.signatures[run_id] != signature:
                    return True, None
            return None, "scan_progress"
        except OSError as error:
            raise ListUnavailable() from error

    def scan(self, store: DiagnosticsStore) -> ScanResult:
        root = Path(store.root)
        runs_root = Path(store.runs_root)
        with self._lock:
            # No mkdir, lease, quota reconciliation, or writer-state mutation.
            try:
                _safe_path(root)
                _safe_path(runs_root)
                _readable_stat(root)
            except AuthoritySnapshotUnavailable as error:
                raise ListUnavailable(error.code) from error
            except ListUnavailable as error:
                try:
                    root.lstat()
                except FileNotFoundError:
                    return self._empty()
                raise error
            try:
                runs_signature = self._directory_signature(runs_root)
            except ListUnavailable as error:
                try:
                    runs_root.lstat()
                except FileNotFoundError:
                    return self._empty()
                raise error

            state = self._state
            directory_path = str(runs_root.resolve(strict=False))
            validation_key = self._validation_key(store)
            if (
                state is None
                or state.directory_path != directory_path
                or state.directory_signature != runs_signature
                or state.validation_key != validation_key
            ):
                self._close()
                state = self._open(store, runs_root, runs_signature)

            # One request gets one cooperative budget, including the bounded
            # warm signature pass and any cold restart it triggers.
            deadline = self.clock() + SCAN_DEADLINE_SECONDS

            # A complete cache is reused without reading every record.  A
            # bounded stat/name pass still notices normal external edits,
            # creates, and deletes; if the pass itself is slow, report progress.
            if state.complete:
                refreshed, refresh_error = self._refresh_external(
                    store, runs_root, state, deadline
                )
                if refreshed is True:
                    self._close()
                    state = self._open(store, runs_root, self._directory_signature(runs_root))
                elif refreshed is None:
                    return self._state_result(state, complete=False, extra_errors=(refresh_error or "scan_progress",))
                else:
                    return self._state_result(state)

            while not state.complete and not state.terminal and self.clock() < deadline:
                try:
                    entry = next(state.iterator)
                except StopIteration:
                    state.complete = True
                    try:
                        state.iterator.close()
                    except Exception:
                        pass
                    break
                state.entries_scanned += 1
                if state.entries_scanned > SCAN_ENTRY_LIMIT:
                    _append_error(state.errors, "scan_limit")
                    state.terminal = True
                    try:
                        state.iterator.close()
                    except Exception:
                        pass
                    break
                state.seen_paths.add(entry.name)
                self._read_one(store, state, entry)
            if state.complete:
                return self._state_result(state)
            return self._state_result(state, complete=False)


def scan_headers(
    store: DiagnosticsStore,
    *,
    clock: Callable[[], float] = time.monotonic,
    cache: DiagnosticsHeaderCache | None = None,
) -> ScanResult:
    """Scan one bounded slice, optionally continuing a prior warm/cold pass."""

    return (cache or DiagnosticsHeaderCache(clock=clock)).scan(store)


def _observed_outcome(status: str) -> str:
    if status in FAILED_STATUSES:
        return "failed"
    if status in {"done", "succeeded"}:
        return "succeeded"
    if status == "cancelled":
        return "cancelled"
    if status in ACTIVE_STATUSES:
        return "running"
    return "unknown"


def _authority_outcome(state: str, status: str | None) -> str | None:
    return _observed_outcome(status) if state == "matched" and status is not None else None


def _project_item(
    header: RunHeader,
    authority: AuthoritySnapshot,
    *,
    jobs_by_id: Mapping[str, Any] | None = None,
    automation_by_run: Mapping[str, str] | None = None,
) -> ListItem | None:
    state = "unavailable"
    authority_status: str | None = None
    work_log_id: str | None = None
    job = None
    if header.job_id is not None:
        job_map = authority.jobs_by_id if jobs_by_id is None else jobs_by_id
        job = job_map.get(header.job_id)
        # Any job-linked run without a current authority is suppressed.  This
        # includes pruned/deleted rows and avoids a stale diagnostic resurrecting
        # a Work Log card.
        if job is None or header.job_id in authority.hidden_job_ids:
            return None
        authority_status = job.status
        state = "matched" if authority_status == header.observed_status else "changed"
        if job.work_log_eligible:
            work_log_id = job.work_log_id
    elif header.authority_kind == "automation":
        automation_map = authority.automation_by_run if automation_by_run is None else automation_by_run
        authority_status = automation_map.get(header.run_id)
        # Unlike a job-linked diagnostic, a historical automation record is
        # still useful when its bounded authority file has pruned the parent.
        # Keep it visible as unavailable rather than resurrecting a job card.
        state = "unavailable" if authority_status is None else (
            "matched" if authority_status == header.observed_status else "changed"
        )
    elif header.authority_kind == "direct":
        state = "not_applicable"
    else:
        # A shared/recovery record without its declared job is not a safe
        # standalone row.  Do not expose an authority-unavailable phantom.
        return None

    observed_outcome = _observed_outcome(header.observed_status)
    authoritative_outcome = _authority_outcome(state, authority_status)
    payload: dict[str, Any] = {
        "runId": header.run_id,
        "createdAt": header.created_at,
        "finishedAt": header.finished_at,
        "observedStatus": header.observed_status,
        "observedOutcome": observed_outcome,
        "outcome": authoritative_outcome,
        "featureCode": header.feature_code,
        "routeCode": header.route_code,
        "authorityKind": header.authority_kind,
        "authorityState": state,
        "authorityStatus": authority_status if state in {"matched", "changed"} else None,
        "taskType": header.task_type,
        "jobId": header.job_id,
        "workLogId": work_log_id,
        "diagnosticQuality": "complete" if header.required_coverage == "complete" and state == "matched" else "partial",
        "adapter": header.adapter,
        "attemptedEngine": header.attempted_engine,
        "finalEngine": header.final_engine,
        "fallbackReason": header.fallback_reason,
        # None means absence was not observed; it is not a negative proof.
        "fallbackObserved": header.fallback_observed,
        "failureReasonCode": header.failure_reason,
        "failureStageCode": header.failure_stage,
    }
    # Keep the public header genuinely closed and bounded even if a future
    # schema adds a large safe-looking field.
    try:
        if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_DOCUMENT_BYTES:
            return None
    except (TypeError, ValueError):
        return None
    return ListItem(payload=payload, created_dt=header.created_dt, run_id=header.run_id)


def _matches(item: ListItem, query: ListQuery) -> bool:
    payload = item.payload
    if query.feature is not None and payload.get("featureCode") != query.feature:
        return False
    if query.outcome != "all":
        observed = payload.get("outcome")
        if query.outcome == "unknown":
            if observed is not None:
                return False
        elif observed != query.outcome:
            return False
    if query.fallback == "observed" and payload.get("fallbackObserved") is not True:
        return False
    if query.from_at is not None and item.created_dt < query.from_at:
        return False
    if query.to_at is not None and item.created_dt >= query.to_at:
        return False
    return True


def _safe_errors(errors: Iterable[str]) -> list[dict[str, str]]:
    return [{"code": code} for code in tuple(dict.fromkeys(errors))[:MAX_SCAN_ERRORS]]


class DiagnosticsListService:
    """Own bounded list snapshots for one application process."""

    def __init__(
        self,
        *,
        authority_provider: Callable[[], AuthoritySnapshot] | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] | None = None,
        token_bytes: Callable[[int], bytes] | None = None,
    ) -> None:
        self.authority_provider = authority_provider or default_authority_snapshot
        self.clock = clock
        self.wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self.token_bytes = token_bytes or secrets.token_bytes
        self._lock = threading.RLock()
        self._header_cache = DiagnosticsHeaderCache(clock=clock)
        self._snapshots: OrderedDict[str, CachedSnapshot] = OrderedDict()
        self._cursors: dict[str, CursorState] = {}
        self._cursor_keys: dict[tuple[str, int], str] = {}

    def _new_token(self) -> str:
        raw = self.token_bytes(32)
        if not isinstance(raw, bytes) or len(raw) != 32:
            raise ListCursorError("cursor_unavailable")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _purge(self, now: float) -> None:
        expired = [
            snapshot_id
            for snapshot_id, snapshot in self._snapshots.items()
            if now - snapshot.created_monotonic >= SNAPSHOT_TTL_SECONDS
        ]
        for snapshot_id in expired:
            self._snapshots.pop(snapshot_id, None)
        for token, cursor in tuple(self._cursors.items()):
            if cursor.snapshot_id not in self._snapshots or now >= cursor.expires_monotonic:
                self._cursors.pop(token, None)
                self._cursor_keys.pop((cursor.snapshot_id, cursor.index), None)

    def _admit(self, snapshot: CachedSnapshot) -> None:
        self._snapshots[snapshot.snapshot_id] = snapshot
        self._snapshots.move_to_end(snapshot.snapshot_id)
        while len(self._snapshots) > MAX_SNAPSHOTS:
            evicted_id, _ = self._snapshots.popitem(last=False)
            for token, cursor in tuple(self._cursors.items()):
                if cursor.snapshot_id == evicted_id:
                    self._cursors.pop(token, None)
                    self._cursor_keys.pop((cursor.snapshot_id, cursor.index), None)

    def _cursor_for(self, snapshot: CachedSnapshot, index: int) -> str:
        key = (snapshot.snapshot_id, index)
        existing = self._cursor_keys.get(key)
        if existing is not None and existing in self._cursors:
            return existing
        token = self._new_token()
        self._cursors[token] = CursorState(
            token=token,
            snapshot_id=snapshot.snapshot_id,
            query=snapshot.query,
            index=index,
            expires_monotonic=snapshot.created_monotonic + SNAPSHOT_TTL_SECONDS,
        )
        self._cursor_keys[key] = token
        while len(self._cursors) > MAX_CURSOR_TOKENS:
            evicted_token, evicted_cursor = next(iter(self._cursors.items()))
            self._cursors.pop(evicted_token, None)
            self._cursor_keys.pop((evicted_cursor.snapshot_id, evicted_cursor.index), None)
        return token

    def _new_snapshot(self, store: DiagnosticsStore, query: ListQuery) -> CachedSnapshot:
        # Scan first; the authority read below is the list's visibility
        # linearization point.  A clear that completes during the scan is then
        # excluded, while a clear after that point expires continuation cursors.
        scan = scan_headers(store, clock=self.clock, cache=self._header_cache)
        authority = self.authority_provider()
        # The authority read is the visibility linearization point.  Keep a
        # human-readable UTC timestamp from that same snapshot creation on
        # every page so a UI can label the frozen observed outcomes without
        # implying that continuation re-read the full diagnostic archive.
        snapshot_at = self.wall_clock().astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        jobs_by_id = authority.jobs_by_id
        automation_by_run = authority.automation_by_run
        items = tuple(
            item
            for header in scan.headers
            for item in (
                _project_item(
                    header,
                    authority,
                    jobs_by_id=jobs_by_id,
                    automation_by_run=automation_by_run,
                ),
            )
            if item is not None and _matches(item, query)
        )
        # The order is already deterministic from validated createdAt/runId;
        # keep an explicit sort after projection for future scanner changes.
        items = tuple(sorted(items, key=lambda item: item.run_id))
        items = tuple(sorted(items, key=lambda item: item.created_dt, reverse=True))
        snapshot_id = secrets.token_hex(16)
        return CachedSnapshot(
            snapshot_id=snapshot_id,
            query=query,
            items=items,
            authority_revision=authority.visibility_revision,
            snapshot_at=snapshot_at,
            created_monotonic=self.clock(),
            entries_scanned=scan.entries_scanned,
            runs_scanned=scan.runs_scanned,
            complete=scan.complete,
            errors=scan.errors,
        )

    def list(self, store: DiagnosticsStore, query: ListQuery, cursor: str | None = None) -> dict[str, Any]:
        now = self.clock()
        with self._lock:
            self._purge(now)
            if cursor is None:
                snapshot = self._new_snapshot(store, query)
                self._admit(snapshot)
                index = 0
            else:
                cursor_state = self._cursors.get(cursor)
                if cursor_state is None:
                    raise ListCursorError("cursor_expired")
                if cursor_state.query.canonical() != query.canonical():
                    raise ListCursorError("cursor_query_mismatch")
                snapshot = self._snapshots.get(cursor_state.snapshot_id)
                if snapshot is None:
                    raise ListCursorError("cursor_expired")
                authority = self.authority_provider()
                if authority.visibility_revision != snapshot.authority_revision:
                    self._snapshots.pop(snapshot.snapshot_id, None)
                    raise ListCursorError("cursor_visibility_changed")
                index = cursor_state.index

            page = snapshot.items[index : index + query.limit]
            next_cursor: str | None = None
            next_index = index + len(page)
            # Truncated cold scans are explicit and are never presented as a
            # complete pageable snapshot; a caller must retry a fresh query.
            if snapshot.complete and next_index < len(snapshot.items):
                next_cursor = self._cursor_for(snapshot, next_index)
            return {
                "version": LIST_VERSION,
                "snapshotAt": snapshot.snapshot_at,
                # Cache entries are immutable by contract; return a fresh
                # scalar-only dict so a caller cannot mutate a replayed page.
                "items": [dict(item.payload) for item in page],
                "nextCursor": next_cursor,
                "truncated": not snapshot.complete,
                "scan": {
                    "entriesScanned": snapshot.entries_scanned,
                    "runsScanned": snapshot.runs_scanned,
                    "complete": snapshot.complete,
                    "deadlineMs": int(SCAN_DEADLINE_SECONDS * 1000),
                },
                "errors": _safe_errors(snapshot.errors),
            }


__all__ = [
    "DEFAULT_LIMIT",
    "DiagnosticsListService",
    "FALLBACK_FILTERS",
    "ListCursorError",
    "ListQuery",
    "ListQueryError",
    "MAX_LIMIT",
    "OUTCOMES",
    "parse_list_query",
    "scan_headers",
]
