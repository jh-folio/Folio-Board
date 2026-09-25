"""Lazy bounded persistence for diagnostic records.

The store is deliberately separate from jobs and has no module-level instance.
Its lease is advisory: failure to obtain it makes diagnostics read-only while
the authoritative product operation continues unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from collections import deque
import json
import os
from pathlib import Path
import stat
import threading
import time
from typing import Final, Iterator

from features.common.atomic_replace import write_bytes_atomic

from .record import DiagnosticRecord, DiagnosticRecorder, record_from_dict
from .schema import ISSUE_CODES, MAX_DOCUMENT_BYTES, DiagnosticContext, DiagnosticValidationError, Failure, failure_fingerprint, valid_id

MAX_DISK_BYTES: Final = 50 * 1024 * 1024
MAX_RUN_FILES: Final = 4096
SCAN_ENTRY_LIMIT: Final = 5000
SCAN_DEADLINE_SECONDS: Final = 0.250
# Keep a complete incremental snapshot through the documented 128 live-handle
# cap.  The next admission then begins the bounded external-change reconcile.
RECONCILE_AFTER_WRITES: Final = 128

_LOCAL_LEASE_LOCK = threading.RLock()
_LOCAL_LEASES: set[str] = set()
_RUN_LOCKS: dict[str, threading.RLock] = {}
_CONSOLE_LOCK = threading.RLock()
_CONSOLE_TIMES: deque[float] = deque()


def _is_reparse(path: Path) -> bool:
    """Detect POSIX symlinks and Windows junction/reparse points before use."""
    try:
        item = os.lstat(path)
    except FileNotFoundError:
        return False
    attrs = getattr(item, "st_file_attributes", 0)
    return stat.S_ISLNK(item.st_mode) or bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


@dataclass(frozen=True, slots=True)
class ReadResult:
    record: DiagnosticRecord | None
    availability_reason: str
    # A bounded, allow-listed retention summary is available only when the
    # exact run file is absent and the retention ledger explicitly records its
    # deletion.  Existing callers remain source-compatible via the default.
    tombstone: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    bytes_used: int
    run_files: int
    entries: int
    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticWarning:
    code: str
    run_id: str
    at_monotonic: float


@dataclass(slots=True)
class _ScanState:
    iterator: Iterator[Path]
    entries: int = 0
    bytes_used: int = 0
    run_files: int = 0
    sizes: dict[str, int] = None  # type: ignore[assignment]
    headers: dict[str, dict[str, str | None]] = None  # type: ignore[assignment]
    signatures: dict[str, tuple[int, int, int]] = None  # type: ignore[assignment]
    file_sizes: dict[str, int] = None  # type: ignore[assignment]
    file_runs: dict[str, str] = None  # type: ignore[assignment]
    seen: set[str] = None  # type: ignore[assignment]
    dirty: set[str] = None  # type: ignore[assignment]
    exhausted: bool = False

    def __post_init__(self) -> None:
        self.sizes = {} if self.sizes is None else self.sizes
        self.headers = {} if self.headers is None else self.headers
        self.signatures = {} if self.signatures is None else self.signatures
        self.file_sizes = {} if self.file_sizes is None else self.file_sizes
        self.file_runs = {} if self.file_runs is None else self.file_runs
        self.seen = set() if self.seen is None else self.seen
        self.dirty = set() if self.dirty is None else self.dirty


class _WriterLease:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None
        self._local_key: str | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and _is_reparse(self.path):
            return False
        key = str(self.path.resolve())
        with _LOCAL_LEASE_LOCK:
            if key in _LOCAL_LEASES:
                return False
            handle = self.path.open("a+b")
            try:
                handle.seek(0)
                if handle.read(1) == b"":
                    handle.seek(0); handle.write(b"0"); handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                return False
            _LOCAL_LEASES.add(key)
            self._handle, self._local_key = handle, key
            return True

    def close(self) -> None:
        handle, self._handle = self._handle, None
        key, self._local_key = self._local_key, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()
            if key is not None:
                with _LOCAL_LEASE_LOCK:
                    _LOCAL_LEASES.discard(key)


class DiagnosticsStore:
    """Owns one optional writer lease over ``<data_root>/diagnostics``.

    ``data_root`` is injectable and should be ``jobs.data_root()`` for job
    observers.  Omitting it is supported for direct observers, but resolves the
    workspace only when an instance is explicitly constructed.
    """

    def __init__(self, data_root: Path | None = None, *, source_registry: frozenset[tuple[str, str]] | None = None, app_root: Path | None = None) -> None:
        if data_root is None:
            from features.common.workspace import data_dir
            data_root = data_dir()
        self.data_root = Path(data_root)
        self.root = self.data_root / "diagnostics"
        self.runs_root = self.root / "runs"
        self.app_root = app_root or Path(__file__).resolve().parents[3]
        # Frames are opt-in until an observer supplies its shipped source
        # registry.  Regex-valid source text is never enough to be persisted.
        self.source_registry = source_registry or frozenset()
        self._lease: _WriterLease | None = None
        self._lock = threading.RLock()
        self._reserved: dict[str, int] = {}
        self._handles: dict[str, DiagnosticRecorder] = {}
        self._owners: dict[str, object] = {}
        self._quota_cache: QuotaSnapshot | None = None
        self._known_run_sizes: dict[str, int] = {}
        self._headers: dict[str, dict[str, str | None]] = {}
        self._run_signatures: dict[str, tuple[int, int, int]] = {}
        self._runs_directory_accounted = False
        self._writes_since_reconcile = 0
        self._admission_blocked_reason: str | None = None
        self._scan_state: _ScanState | None = None
        self._warnings: deque[DiagnosticWarning] = deque()
        self.last_write_reason: str | None = None

    def close(self) -> None:
        with self._lock:
            if self._lease is not None:
                self._lease.close()
            self._lease = None
            active = tuple(self._handles)
            self._reserved.clear()
            self._handles.clear()
            self._owners.clear()
            self._quota_cache = None
            self._known_run_sizes.clear()
            self._headers.clear()
            self._run_signatures.clear()
            self._runs_directory_accounted = False
            self._writes_since_reconcile = 0
            self._admission_blocked_reason = None
            self._scan_state = None
            self._warnings.clear()
            with _LOCAL_LEASE_LOCK:
                for run_id in active:
                    _RUN_LOCKS.pop(f"{self.runs_root.resolve(strict=False)}::{run_id}", None)

    def _run_lock(self, run_id: str) -> threading.RLock:
        key = f"{self.runs_root.resolve(strict=False)}::{run_id}"
        with _LOCAL_LEASE_LOCK:
            return _RUN_LOCKS.setdefault(key, threading.RLock())

    def _release_handle(self, run_id: str) -> None:
        self._handles.pop(run_id, None)
        self._owners.pop(run_id, None)
        key = f"{self.runs_root.resolve(strict=False)}::{run_id}"
        with _LOCAL_LEASE_LOCK:
            _RUN_LOCKS.pop(key, None)

    def abandon_terminal(self, run_id: str, *, owner_token: object) -> None:
        """Drop a terminal observer handle when its final write cannot persist.

        The already-authoritative product terminal must not consume one of the
        128 diagnostic slots forever.  This intentionally does not retry or
        rewrite any partial disk record.
        """
        with self._lock:
            if self._owners.get(run_id) is not owner_token:
                return
            self._reserved.pop(run_id, None)
            self._release_handle(run_id)

    def _prepare_root(self) -> None:
        """Make only owned directories after proving no reparse pivot exists."""
        if self.data_root.exists() and _is_reparse(self.data_root):
            raise OSError("diagnostic_data_root_reparse")
        if not self.data_root.exists():
            self.data_root.mkdir(parents=True, exist_ok=False)
        if _is_reparse(self.data_root):
            raise OSError("diagnostic_data_root_reparse")
        if self.root.exists() and _is_reparse(self.root):
            raise OSError("diagnostic_root_reparse")
        if not self.root.exists():
            self.root.mkdir(exist_ok=False)
        if _is_reparse(self.root):
            raise OSError("diagnostic_root_reparse")

    def _verify_sources(self, record: DiagnosticRecord) -> None:
        from .support import verified_source_frame
        for failure in record.errors:
            for frame in failure.frames:
                if (frame.module_code, frame.function_code) not in self.source_registry:
                    raise DiagnosticValidationError("unregistered_source")
                if verified_source_frame(app_root=self.app_root, module_code=frame.module_code, function_code=frame.function_code, line=frame.line) != frame:
                    raise DiagnosticValidationError("unregistered_source")

    def sanitize_failure(self, failure: Failure) -> tuple[Failure, bool]:
        """Drop unverified source hints while retaining the safe classification."""
        from .support import verified_source_frame
        verified = tuple(
            frame for frame in failure.frames
            if (frame.module_code, frame.function_code) in self.source_registry
            and verified_source_frame(app_root=self.app_root, module_code=frame.module_code, function_code=frame.function_code, line=frame.line) == frame
        )
        return replace(
            failure,
            frames=verified,
            fingerprint=failure_fingerprint(
                stage_code=failure.stage_code,
                reason_code=failure.reason_code,
                exception_code=failure.exception_code,
                frames=verified,
            ),
        ), len(verified) != len(failure.frames)

    def note_warning(self, code: str, run_id: str) -> None:
        """Keep a volatile, code-only bounded warning for the next projection."""
        if not isinstance(code, str) or code not in ISSUE_CODES:
            code = "write_failed"
        try:
            valid_id(run_id, "run")
        except DiagnosticValidationError:
            return
        now = time.monotonic()
        with self._lock:
            while self._warnings and now - self._warnings[0].at_monotonic > 1800:
                self._warnings.popleft()
            if len(self._warnings) >= 100:
                self._warnings.popleft()
            self._warnings.append(DiagnosticWarning(code, run_id, now))

    def warning_projection(self, run_id: str | None = None) -> list[dict[str, str]]:
        """Safe in-memory warnings; never exception text, paths, or bodies."""
        now = time.monotonic()
        with self._lock:
            while self._warnings and now - self._warnings[0].at_monotonic > 1800:
                self._warnings.popleft()
            return [{"code": item.code, "runId": item.run_id} for item in self._warnings if run_id is None or item.run_id == run_id]

    def safe_console(self, code: str, run_id: str, *, printer=print) -> bool:
        """Rate-limited opt-in console fallback using only fixed codes and IDs."""
        if not isinstance(code, str) or code not in ISSUE_CODES:
            return False
        try:
            valid_id(run_id, "run")
        except DiagnosticValidationError:
            return False
        now = time.monotonic()
        with _CONSOLE_LOCK:
            while _CONSOLE_TIMES and now - _CONSOLE_TIMES[0] > 60:
                _CONSOLE_TIMES.popleft()
            if len(_CONSOLE_TIMES) >= 10:
                return False
            _CONSOLE_TIMES.append(now)
        try:
            printer(f"diagnostics:{code}:{run_id}")
            return True
        except Exception:
            return False

    def __enter__(self) -> "DiagnosticsStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _ensure_lease(self) -> bool:
        if self._lease is not None:
            return True
        try:
            self._prepare_root()
        except OSError:
            self.last_write_reason = "write_failed"
            return False
        lease = _WriterLease(self.root / ".writer.lock")
        try:
            acquired = lease.acquire()
        except OSError:
            acquired = False
        if not acquired:
            self.last_write_reason = "writer_conflict"
            return False
        self._lease = lease
        return True

    def _admission_failure(self, context: DiagnosticContext, code: str) -> None:
        """Record an ephemeral, closed-code warning even before a recorder exists."""
        self.last_write_reason = code if code in ISSUE_CODES else "write_failed"
        self.note_warning(self.last_write_reason, context.run_id)

    def _record_path(self, run_id: str, *, create_root: bool = False) -> Path:
        valid_id(run_id, "run")
        if create_root:
            self._prepare_root()
            if self.runs_root.exists() and _is_reparse(self.runs_root):
                raise OSError("diagnostic_runs_reparse")
            if not self.runs_root.exists():
                self.runs_root.mkdir(exist_ok=False)
        # Resolving after mkdir plus a relative check blocks a reparse/symlink
        # pivot both at the runs root and at the final target.
        if self.runs_root.is_symlink():
            raise OSError("diagnostic_runs_reparse")
        root = self.runs_root.resolve(strict=create_root)
        target = root / f"{run_id}.json"
        if target.exists() and _is_reparse(target):
            raise OSError("diagnostic_target_reparse")
        target.resolve(strict=False).relative_to(root)
        return target

    def _bounded_json(self, path: Path) -> object:
        """Read at most one byte past the document cap; never trust stat size."""
        with path.open("rb") as handle:
            raw = handle.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise DiagnosticValidationError("oversized_record")
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _signature(item_stat: os.stat_result) -> tuple[int, int, int]:
        return (item_stat.st_size, item_stat.st_mtime_ns, getattr(item_stat, "st_ino", 0))

    @staticmethod
    def _header(record: DiagnosticRecord) -> dict[str, str | None]:
        return {"runId": record.run_id, "updatedAt": record.updated_at, "finishedAt": record.finished_at, "observedStatus": record.observed_status}

    def _scan_failure(self, reason: str, entries: int = 0) -> QuotaSnapshot:
        # A partial scan is never made an accounting snapshot.  Retrying starts
        # a fresh pass so a repaired disk/corrupt file can become admissible.
        self._scan_state = None
        self._admission_blocked_reason = reason
        return QuotaSnapshot(0, 0, entries, False, reason)

    def _scan_run_file(self, state: _ScanState, item: Path, item_stat: os.stat_result, relative: str) -> None:
        run_id = item.stem
        valid_id(run_id, "run")
        signature = self._signature(item_stat)
        header = self._headers.get(run_id)
        if self._run_signatures.get(run_id) != signature or header is None:
            candidate = record_from_dict(self._bounded_json(item))
            if candidate.run_id != run_id:
                raise DiagnosticValidationError("invalid_record_path")
            self._verify_sources(candidate)
            header = self._header(candidate)
        state.sizes[run_id] = item_stat.st_size
        state.headers[run_id] = header
        state.signatures[run_id] = signature
        state.file_runs[relative] = run_id

    def _scan_item(self, state: _ScanState, item: Path) -> None:
        relative = item.relative_to(self.root).as_posix()
        if relative in state.seen:
            return
        if state.entries >= SCAN_ENTRY_LIMIT:
            raise DiagnosticValidationError("scan_limit")
        state.seen.add(relative)
        state.entries += 1
        item_stat = item.lstat()
        if _is_reparse(item):
            raise OSError("diagnostic_reparse")
        if not item.is_file():
            return
        state.file_sizes[relative] = item_stat.st_size
        state.bytes_used += item_stat.st_size
        if item.parent == self.runs_root and item.suffix == ".json":
            state.run_files += 1
            self._scan_run_file(state, item, item_stat, relative)

    def _drain_dirty(self, state: _ScanState, deadline: float) -> bool:
        """Reconcile owned writes that landed after their directory was walked."""
        while state.dirty:
            if time.monotonic() >= deadline:
                return False
            relative = state.dirty.pop()
            target = (self.root / relative)
            target.resolve(strict=False).relative_to(self.root.resolve(strict=True))
            old_size = state.file_sizes.get(relative)
            old_run = state.file_runs.pop(relative, None)
            if old_run is not None:
                state.run_files -= 1
                state.sizes.pop(old_run, None)
                state.headers.pop(old_run, None)
                state.signatures.pop(old_run, None)
            if not target.exists():
                if old_size is not None:
                    state.bytes_used -= old_size
                    state.file_sizes.pop(relative, None)
                continue
            item_stat = target.lstat()
            if _is_reparse(target) or not target.is_file():
                raise OSError("diagnostic_reparse")
            if old_size is None:
                if state.entries >= SCAN_ENTRY_LIMIT:
                    raise DiagnosticValidationError("scan_limit")
                state.entries += 1
                state.seen.add(relative)
                old_size = 0
            state.file_sizes[relative] = item_stat.st_size
            state.bytes_used += item_stat.st_size - old_size
            if target.parent == self.runs_root and target.suffix == ".json":
                state.run_files += 1
                self._scan_run_file(state, target, item_stat, relative)
        return True

    def _scan(self) -> QuotaSnapshot | None:
        """Advance one resumable, lease-owned validation pass.

        ``None`` means the 250 ms cooperative slice is still in progress.  No
        partial totals escape this function or become a quota cache.
        """
        try:
            if not self.root.exists():
                self._scan_state = None
                return QuotaSnapshot(0, 0, 0, True)
            state = self._scan_state
            if state is None:
                state = _ScanState(iter(self.root.rglob("*")))
                self._scan_state = state
            deadline = time.monotonic() + SCAN_DEADLINE_SECONDS
            while not state.exhausted and time.monotonic() < deadline:
                try:
                    self._scan_item(state, next(state.iterator))
                except StopIteration:
                    state.exhausted = True
                    break
            if not state.exhausted:
                return None
            if not self._drain_dirty(state, deadline):
                return None
            if state.bytes_used > MAX_DISK_BYTES or state.run_files > MAX_RUN_FILES:
                return self._scan_failure("quota_exceeded", state.entries)
            snapshot = QuotaSnapshot(state.bytes_used, state.run_files, state.entries, True)
            # Publish the whole validated snapshot atomically only after both
            # the iterator and writes missed by it have been reconciled.
            self._known_run_sizes = state.sizes
            self._headers = state.headers
            self._run_signatures = state.signatures
            self._runs_directory_accounted = "runs" in state.seen
            self._scan_state = None
            return snapshot
        except DiagnosticValidationError as error:
            return self._scan_failure("scan_limit" if str(error) == "scan_limit" else "read_failed")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
            return self._scan_failure("read_failed")

    def _accounting(self) -> QuotaSnapshot:
        """Advance reconciliation and return only the last complete snapshot."""
        needs_pass = self._quota_cache is None or self._scan_state is not None or self._admission_blocked_reason is not None or self._writes_since_reconcile >= RECONCILE_AFTER_WRITES
        if needs_pass:
            scanned = self._scan()
            if scanned is None:
                self._admission_blocked_reason = "scan_limit"
            elif scanned.available:
                self._quota_cache = scanned
                self._admission_blocked_reason = None
                self._writes_since_reconcile = 0
            else:
                # Preserve a prior complete snapshot for existing admitted
                # writers; admissions remain closed until a future full pass.
                self._admission_blocked_reason = scanned.reason or "read_failed"
        return self._quota_cache or QuotaSnapshot(0, 0, 0, False, self._admission_blocked_reason or "read_failed")

    def reconcile_step(self) -> str:
        """Advance at most one owned accounting slice outside user work.

        This is intentionally a no-op before diagnostics has ever created a
        root.  A lifecycle helper can call it repeatedly, but it never opens a
        workspace or spins an unbounded loop on behalf of an HTTP request.
        """
        with self._lock:
            if not self.root.exists():
                return "complete"
            if not self._ensure_lease():
                return "blocked"
            self._accounting()
            if self._scan_state is not None:
                return "pending"
            return "complete" if self._admission_blocked_reason is None else "blocked"

    def mark_external_deletions(self) -> None:
        """Invalidate the incremental accounting snapshot after owned unlink.

        Retention holds this store's writer lock while deleting exact run
        files.  Clearing the warm snapshot here makes the next writer
        admission perform a bounded filesystem pass instead of retaining
        stale byte/file counts.  No file is opened or modified by this
        invalidation itself.
        """
        with self._lock:
            self._quota_cache = None
            self._scan_state = None
            self._known_run_sizes.clear()
            self._headers.clear()
            self._run_signatures.clear()
            self._runs_directory_accounted = False
            self._writes_since_reconcile = 0
            self._admission_blocked_reason = None

    def unfinished_run_ids(self) -> tuple[str, ...]:
        """Return only headers from the last fully validated scan snapshot.

        This deliberately performs no filesystem read or partial accounting.
        Lifecycle recovery uses it only after ``reconcile_step`` reports
        complete, so a crash-gap observer never turns a terminal authority
        row into a new admission or a speculative status.
        """
        with self._lock:
            if self._quota_cache is None or self._scan_state is not None or self._admission_blocked_reason is not None:
                return ()
            return tuple(
                run_id for run_id, header in self._headers.items()
                if header.get("finishedAt") is None
            )

    def _account_written_record(self, record: DiagnosticRecord, data: bytes) -> None:
        if self._quota_cache is None:
            return
        run_id = record.run_id
        previous = self._known_run_sizes.get(run_id, 0)
        current = len(data)
        self._known_run_sizes[run_id] = current
        self._headers[run_id] = self._header(record)
        # A write knows its exact candidate size.  Do not re-open/re-read the
        # file just to account for it; warm scans will obtain a fresh signature.
        self._run_signatures.pop(run_id, None)
        self._quota_cache = replace(
            self._quota_cache,
            bytes_used=self._quota_cache.bytes_used + current - previous,
            run_files=self._quota_cache.run_files + (0 if previous else 1),
            # The first owned record creates both ``runs/`` and its document
            # after the cold scan.  Directory entries count toward the 5000
            # bounded-scan admission ceiling even though they carry no bytes.
            entries=self._quota_cache.entries + (0 if previous else 1 + (0 if self._runs_directory_accounted else 1)),
        )
        if not previous:
            self._runs_directory_accounted = True
        if self._scan_state is not None:
            self._scan_state.dirty.add(f"runs/{run_id}.json")
        # Reservation is the *remaining* possible growth, not a second full
        # document on top of bytes already accounted for on disk.
        if run_id in self._reserved:
            self._reserved[run_id] = max(0, MAX_DOCUMENT_BYTES - current)
        self._writes_since_reconcile += 1

    def start(self, context: DiagnosticContext, *, observed_status: str = "running") -> DiagnosticRecorder | None:
        """Admit a new run, returning ``None`` rather than disturbing work."""
        with self._lock:
            if context.run_id in self._handles:
                return self._handles[context.run_id]
            if len(self._handles) >= 128:
                self._admission_failure(context, "quota_exceeded")
                return None
            if not self._ensure_lease():
                self._admission_failure(context, self.last_write_reason or "write_failed")
                return None
            # Always advance a pending/faulted pass before deciding.  Otherwise
            # the first 250 ms slice would close admission forever.
            quota = self._accounting()
            if self._admission_blocked_reason is not None:
                self._admission_failure(context, self._admission_blocked_reason)
                return None
            if not quota.available:
                self._admission_failure(context, quota.reason or "read_failed")
                return None
            if context.run_id not in self._reserved:
                # Reserve final document capacity and one concurrent atomic temp
                # file before admitting a producer; be conservative at quota.
                required = quota.bytes_used + sum(self._reserved.values()) + 2 * MAX_DOCUMENT_BYTES
                if quota.run_files >= MAX_RUN_FILES or required > MAX_DISK_BYTES:
                    self._admission_failure(context, "quota_exceeded")
                    return None
                self._reserved[context.run_id] = MAX_DOCUMENT_BYTES
            try:
                target = self._record_path(context.run_id, create_root=True)
                if target.exists():
                    self._admission_failure(context, "write_failed")
                    self.last_write_reason = "existing_run"
                    self._reserved.pop(context.run_id, None)
                    return None
                owner = object()
                self._owners[context.run_id] = owner
                initial = replace(
                    DiagnosticRecord.new(context),
                    observed_status=observed_status,
                )
                recorder = DiagnosticRecorder(self, initial, context, owner_token=owner, run_lock=self._run_lock(context.run_id), monotonic_started=time.monotonic())
                if not self.persist(recorder.record, owner_token=owner):
                    self._reserved.pop(context.run_id, None)
                    self._release_handle(context.run_id)
                    return None
                self._handles[context.run_id] = recorder
                return recorder
            except (OSError, DiagnosticValidationError):
                self._admission_failure(context, "write_failed")
                self._reserved.pop(context.run_id, None)
                self._release_handle(context.run_id)
                return None

    def resume(self, context: DiagnosticContext, *, observed_status: str = "unknown") -> DiagnosticRecorder | None:
        """Open an existing record without inventing pre-crash events."""
        with self._lock:
            if context.run_id in self._handles:
                return self._handles[context.run_id]
            if len(self._handles) >= 128:
                self._admission_failure(context, "quota_exceeded")
                return None
            if not self._ensure_lease():
                self._admission_failure(context, self.last_write_reason or "write_failed")
                return None
            quota = self._accounting()
            if self._admission_blocked_reason is not None:
                self._admission_failure(context, self._admission_blocked_reason)
                return None
            if not quota.available or quota.bytes_used + sum(self._reserved.values()) + MAX_DOCUMENT_BYTES > MAX_DISK_BYTES:
                self._admission_failure(context, quota.reason or "quota_exceeded")
                return None
            result = self.read(context.run_id)
            if result.record is None:
                self._admission_failure(context, "read_failed")
                self.last_write_reason = result.availability_reason
                return None
            record = result.record
            if record.finished_at is not None:
                # A terminal observation is immutable.  Recovery is for a
                # crash-gap record, never a way to reopen a completed run.
                self._admission_failure(context, "write_failed")
                self.last_write_reason = "invalid_recovery_terminal"
                return None
            if record.context.process_epoch == context.process_epoch:
                self._admission_failure(context, "write_failed")
                self.last_write_reason = "invalid_recovery_epoch"
                return None
            # The original identity remains authoritative; only the active
            # producer epoch changes for recovery events.
            recovery_context = record.context.with_recovery_producer(context.producer_epoch)
            owner = object()
            self._owners[record.run_id] = owner
            recorder = DiagnosticRecorder(self, record, recovery_context, owner_token=owner, run_lock=self._run_lock(context.run_id))
            # The existing recovery record is already part of the complete
            # accounting snapshot; reserve only its possible remaining growth.
            self._reserved[record.run_id] = max(0, MAX_DOCUMENT_BYTES - len(record.to_bytes()))
            if not recorder.recover(observed_status):
                self._reserved.pop(record.run_id, None)
                self._release_handle(record.run_id)
                return None
            # A recovery observation may itself be terminal.  ``persist`` has
            # already released its owner/reservation in that case; never put a
            # stale live handle back into the registry.
            if recorder.record.finished_at is None:
                self._handles[record.run_id] = recorder
            return recorder

    def persist(self, record: DiagnosticRecord, *, owner_token: object | None = None) -> bool:
        with self._lock:
            if not self._ensure_lease():
                self.note_warning(self.last_write_reason or "write_failed", record.run_id)
                return False
            try:
                if record.run_id not in self._reserved or self._owners.get(record.run_id) is not owner_token:
                    self.last_write_reason = "quota_exceeded"
                    self.note_warning("quota_exceeded", record.run_id)
                    return False
                quota = self._accounting()
                remaining = sum(size for run_id, size in self._reserved.items() if run_id != record.run_id)
                # Existing admitted writers retain their reservation during a
                # pending/faulted warm reconcile.  New start/resume admissions
                # are the only operations closed by _admission_blocked_reason.
                if not quota.available or quota.bytes_used + remaining + MAX_DOCUMENT_BYTES > MAX_DISK_BYTES:
                    self.last_write_reason = quota.reason or "quota_exceeded"
                    self.note_warning(self.last_write_reason, record.run_id)
                    return False
                self._verify_sources(record)
                data = record.to_bytes()
                if len(data) > MAX_DOCUMENT_BYTES:
                    self.last_write_reason = "byte_limit"
                    return False
                target = self._record_path(record.run_id, create_root=True)
                write_bytes_atomic(target, data)
                self._account_written_record(record, data)
                self.last_write_reason = None
                if record.finished_at is not None:
                    self._reserved.pop(record.run_id, None)
                    self._release_handle(record.run_id)
                return True
            except (OSError, DiagnosticValidationError, TypeError, ValueError):
                self.last_write_reason = "write_failed"
                self.note_warning("write_failed", record.run_id)
                return False

    def read(self, run_id: str) -> ReadResult:
        """Read-only access: never acquires the writer lease or repairs files."""
        valid_id(run_id, "run")
        try:
            if (self.data_root.exists() and _is_reparse(self.data_root)) or (self.root.exists() and _is_reparse(self.root)) or (self.runs_root.exists() and _is_reparse(self.runs_root)):
                return ReadResult(None, "read_failed")
            target = self._record_path(run_id, create_root=False)
            if not target.exists():
                # Retention is an optional extension and imported lazily to
                # avoid a store/retention module cycle.  A present file always
                # wins; the ledger is consulted only after the exact target is
                # confirmed absent.  Corrupt/unavailable ledger data is a
                # read failure, never an inferred expiry.
                try:
                    from .retention import _load_tombstones
                    tombstone = next(
                        (item for item in _load_tombstones(self) if item.get("runId") == run_id),
                        None,
                    )
                except Exception:
                    return ReadResult(None, "read_failed")
                if tombstone is not None:
                    return ReadResult(None, "expired", tombstone)
                return ReadResult(None, "missing_unknown")
            if _is_reparse(target):
                return ReadResult(None, "read_failed")
            record = record_from_dict(self._bounded_json(target))
            if record.run_id != run_id:
                return ReadResult(None, "corrupt")
            self._verify_sources(record)
            return ReadResult(record, "present")
        except DiagnosticValidationError as error:
            reason = "unsupported_version" if str(error) == "unsupported_schema" else "corrupt"
            return ReadResult(None, reason)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
            return ReadResult(None, "read_failed")
