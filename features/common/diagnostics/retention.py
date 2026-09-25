"""Bounded, opt-in retention for diagnostic run documents.

Retention is deliberately a second, narrow surface beside the read-only list
and detail projections.  It never owns a job or a report.  A run can be
removed only after a preview captured the exact file fingerprint and current
terminal authority, and the same facts are checked again immediately before
the unlink.  The only deletion target accepted by this module is
``diagnostics/runs/run_<uuid>.json``.

The small ``expired.json`` ledger is not a replacement diagnostic record.  It
keeps only an allow-listed summary so a later detail request can say that the
detail was explicitly expired.  A missing file without a ledger entry remains
``missing_unknown``; retention never infers expiry from absence.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Callable, Iterable, Mapping

from features.common.atomic_replace import write_bytes_atomic

from .authority import AuthoritySnapshot, AuthoritySnapshotUnavailable
from .record import DiagnosticRecord, record_from_dict
from .schema import (
    AUTHORITY_KINDS,
    DiagnosticValidationError,
    FEATURE_CODES,
    OBSERVED_STATUSES,
    REASON_CODES,
    ROUTE_CODES,
    STAGE_CODES,
    TASK_TYPES,
    valid_id,
    run_id_for_job,
    valid_utc_z,
    utc_z,
)
from .store import (
    MAX_DISK_BYTES,
    MAX_DOCUMENT_BYTES,
    MAX_RUN_FILES,
    SCAN_ENTRY_LIMIT,
    DiagnosticsStore,
    _is_reparse,
)


RETENTION_SCHEMA_VERSION = 1
RETENTION_CHOICES = (7, 30, 90, 180, 365)
DEFAULT_RETENTION_DAYS = 30
DEFAULT_AUTO_DELETE = False

# These are retention-specific bounds.  The diagnostic document/file/disk
# caps are imported from store.py and are intentionally not redefined here.
MAX_RETENTION_TOKENS = 128
RETENTION_TOKEN_TTL_SECONDS = 10 * 60
MAX_TOMBSTONES = MAX_RUN_FILES
MAX_TOMBSTONE_BYTES = 256 * 1024
MAX_TOMBSTONE_ITEM_BYTES = 2 * 1024
MAX_RETENTION_CANDIDATES = 64
# Retention scans validate complete JSON records and may inspect a normal
# desktop archive of dozens of files.  This is intentionally more generous
# than the lightweight D3 list slice while remaining a hard cooperative cap.
RETENTION_SCAN_DEADLINE_SECONDS = 5.0
TOMBSTONE_FILE_NAME = "expired.json"
SETTINGS_FILE_NAME = "retention-settings.json"
RETENTION_TOKEN_PREFIX = "drt1_"

TERMINAL_STATUSES = frozenset(
    {
        "done",
        "succeeded",
        "cancelled",
        "failed",
        "failed_cancel",
        "failed_commit",
        "failed_restart",
        "failed_commit_recovery",
    }
)

EXCLUDED_KEYS = (
    "running",
    "unknown",
    "recovery",
    "privateBlocked",
    "authorityChanged",
    "corrupt",
    "other",
)


class RetentionError(Exception):
    """Stable, code-only retention failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RetentionValidationError(RetentionError, ValueError):
    """Invalid request or malformed retention state."""


class RetentionUnavailable(RetentionError, RuntimeError):
    """A safe read/write boundary was unavailable."""


class RetentionConflict(RetentionError, RuntimeError):
    """A preview no longer describes the current file or authority."""


@dataclass(frozen=True, slots=True)
class RetentionSettings:
    retention_days: int = DEFAULT_RETENTION_DAYS
    auto_delete: bool = DEFAULT_AUTO_DELETE

    def __post_init__(self) -> None:
        normalize_retention_days(self.retention_days)
        if type(self.auto_delete) is not bool:
            raise RetentionValidationError("invalid_auto_delete")

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": RETENTION_SCHEMA_VERSION,
            "retentionDays": self.retention_days,
            "autoDelete": self.auto_delete,
        }


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    run_id: str
    path: Path
    size: int
    file_hash: str
    created_at: str
    finished_at: str
    observed_status: str
    authority_signature: str
    summary: dict[str, object]


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    token: str
    retention_days: int
    cutoff_at: str
    expires_at: str
    candidates: tuple[RetentionCandidate, ...]
    excluded_counts: dict[str, int]
    fingerprint: str
    generated_at: str
    status: str = "ready"


@dataclass(slots=True)
class _Token:
    digest: str
    purpose: str
    expires_at: datetime
    fingerprint: str
    retention_days: int
    auto_delete: bool | None
    candidates: tuple[RetentionCandidate, ...] = ()
    settings_digest: str | None = None
    used: bool = False
    issued_monotonic: float = 0.0


@dataclass(frozen=True, slots=True)
class _Inventory:
    records: tuple[RetentionCandidate, ...]
    bytes_used: int
    run_files: int
    entries: int
    tombstones: tuple[dict[str, object], ...]
    errors: tuple[str, ...]


def normalize_retention_days(value: object) -> int:
    """Accept only the closed user-facing retention period enum."""

    # ``bool`` is an ``int`` subclass; accepting it would make malformed JSON
    # settings silently opt into a retention policy.
    if type(value) is not int or value not in RETENTION_CHOICES:
        raise RetentionValidationError("invalid_retention_days")
    return value


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RetentionUnavailable("clock_unavailable")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_timestamp(value: object, field: str) -> datetime:
    try:
        parsed = valid_utc_z(value)
        return datetime.fromisoformat(parsed.replace("Z", "+00:00")).astimezone(UTC)
    except (DiagnosticValidationError, TypeError, ValueError) as error:
        raise RetentionValidationError(f"invalid_{field}") from error


def _safe_path(path: Path, *, missing_ok: bool = True) -> None:
    """Reject symlink/reparse pivots on the whole application-owned path."""

    candidate = Path(path)
    current = candidate
    while True:
        try:
            current.lstat()
        except FileNotFoundError:
            if not missing_ok:
                raise RetentionUnavailable("diagnostics_missing")
        except OSError as error:
            raise RetentionUnavailable("diagnostics_unavailable") from error
        else:
            if _is_reparse(current):
                raise RetentionUnavailable("diagnostics_reparse")
        if current.parent == current:
            break
        current = current.parent


def _relative_owned(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve(strict=False).relative_to(Path(root).resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def _exact_run_path(store: DiagnosticsStore, run_id: str, *, must_exist: bool = False) -> Path:
    try:
        valid_id(run_id, "run")
    except DiagnosticValidationError as error:
        raise RetentionValidationError("invalid_run_id") from error
    root = Path(store.runs_root)
    _safe_path(root, missing_ok=not must_exist)
    if not root.exists() or not root.is_dir():
        raise RetentionUnavailable("diagnostics_missing")
    target = root / f"{run_id}.json"
    _safe_path(target, missing_ok=not must_exist)
    if not _relative_owned(target, root):
        raise RetentionUnavailable("diagnostics_path_escape")
    if target.exists() and not target.is_file():
        raise RetentionUnavailable("diagnostics_target_invalid")
    if must_exist and not target.exists():
        raise RetentionConflict("preview_changed")
    return target


def _safe_json_bytes(path: Path, cap: int) -> bytes:
    _safe_path(path, missing_ok=False)
    try:
        with path.open("rb") as handle:
            data = handle.read(cap + 1)
    except OSError as error:
        raise RetentionUnavailable("diagnostics_read_failed") from error
    if len(data) > cap:
        raise RetentionUnavailable("diagnostics_oversized")
    return data


def _record_file(store: DiagnosticsStore, path: Path) -> tuple[DiagnosticRecord, bytes, str]:
    raw = _safe_json_bytes(path, MAX_DOCUMENT_BYTES)
    try:
        record = record_from_dict(json.loads(raw.decode("utf-8")))
        if record.run_id != path.stem:
            raise DiagnosticValidationError("invalid_record_path")
        store._verify_sources(record)
    except (DiagnosticValidationError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, RecursionError) as error:
        raise RetentionUnavailable("record_corrupt") from error
    return record, raw, hashlib.sha256(raw).hexdigest()


def _status_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    candidate = getattr(value, "value", None)
    return candidate if isinstance(candidate, str) else None


def _authority_for_job(authority: object, job_id: str) -> tuple[str, str | None, str]:
    """Return ``(state, status, signature)`` for a job-linked diagnostic."""

    if authority is None:
        return "private_blocked", None, "none"
    try:
        jobs_by_id = getattr(authority, "jobs_by_id", None)
        if jobs_by_id is None and isinstance(authority, Mapping):
            jobs_by_id = authority.get("jobsById") or authority.get("jobs_by_id")
        job = jobs_by_id.get(job_id) if isinstance(jobs_by_id, Mapping) else None
        hidden = getattr(authority, "hidden_job_ids", frozenset())
        if isinstance(authority, Mapping):
            hidden = authority.get("hiddenJobIds", authority.get("hidden_job_ids", hidden))
        if job is None or job_id in set(hidden or ()):
            return "private_blocked", None, "missing"
        status = _status_value(getattr(job, "status", None))
        if status is None and isinstance(job, Mapping):
            status = _status_value(job.get("status"))
        revision = getattr(authority, "visibility_revision", None)
        if revision is None and isinstance(authority, Mapping):
            revision = authority.get("visibilityRevision") or authority.get("visibility_revision")
        signature = _digest_json({"kind": "job", "id": job_id, "status": status, "revision": revision})
        if status in {"queued", "running", "cancel_requested", "committing", "submitted"}:
            return "running", status, signature
        if status is None or status not in OBSERVED_STATUSES:
            return "unknown", status, signature
        return "matched", status, signature
    except (AttributeError, TypeError, ValueError):
        return "private_blocked", None, "invalid"


def _authority_for_automation(authority: object, run_id: str) -> tuple[str, str | None, str]:
    if authority is None:
        return "private_blocked", None, "none"
    try:
        rows = getattr(authority, "automation_by_run", None)
        if rows is None and isinstance(authority, Mapping):
            rows = authority.get("automationByRun") or authority.get("automation_by_run")
        status = rows.get(run_id) if isinstance(rows, Mapping) else None
        revision = getattr(authority, "visibility_revision", None)
        if revision is None and isinstance(authority, Mapping):
            revision = authority.get("visibilityRevision") or authority.get("visibility_revision")
        signature = _digest_json({"kind": "automation", "id": run_id, "status": status, "revision": revision})
        if status in {"submitted", "queued", "running", "cancel_requested", "committing"}:
            return "running", status, signature
        if status is None:
            return "private_blocked", None, signature
        if status not in OBSERVED_STATUSES:
            return "unknown", status, signature
        return "matched", status, signature
    except (AttributeError, TypeError, ValueError):
        return "private_blocked", None, "invalid"


def _authority_state(record: DiagnosticRecord, authority: object) -> tuple[str, str | None, str]:
    if record.context.authority_kind == "recovery":
        return "recovery", None, "recovery"
    if record.context.authority_kind == "direct":
        return "not_applicable", None, "direct"
    if record.context.job_id is not None:
        return _authority_for_job(authority, record.context.job_id)
    if record.context.authority_kind == "automation":
        return _authority_for_automation(authority, record.run_id)
    return "unknown", None, "unknown"


def _digest_json(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _summary(record: DiagnosticRecord, *, deleted_at: str | None = None, retention_days: int | None = None, file_bytes: int | None = None) -> dict[str, object]:
    failure = record.terminal_failure or record.first_failure
    return {
        "runId": record.run_id,
        "createdAt": record.created_at,
        "finishedAt": record.finished_at,
        "observedStatus": record.observed_status,
        "featureCode": record.context.feature_code,
        "routeCode": record.context.route_code,
        "authorityKind": record.context.authority_kind,
        "taskType": record.context.task_type,
        "jobId": record.context.job_id,
        "failureReasonCode": failure.reason_code if failure is not None else None,
        "failureStageCode": failure.stage_code if failure is not None else None,
        "diagnosticQuality": "complete" if record.required_producer_coverage == "complete" else "partial",
        "deletedAt": deleted_at,
        "retentionDays": retention_days,
        "fileBytes": file_bytes,
    }


def _validate_summary(raw: object) -> dict[str, object]:
    keys = {
        "runId", "createdAt", "finishedAt", "observedStatus", "featureCode", "routeCode",
        "authorityKind", "taskType", "jobId", "failureReasonCode", "failureStageCode",
        "diagnosticQuality", "deletedAt", "retentionDays", "fileBytes",
    }
    if type(raw) is not dict or set(raw) != keys:
        raise RetentionValidationError("tombstone_corrupt")
    valid_id(raw["runId"], "run")
    _parse_timestamp(raw["createdAt"], "created_at")
    if raw["finishedAt"] is None:
        raise RetentionValidationError("tombstone_corrupt")
    _parse_timestamp(raw["finishedAt"], "finished_at")
    if raw["deletedAt"] is None:
        raise RetentionValidationError("tombstone_corrupt")
    _parse_timestamp(raw["deletedAt"], "deleted_at")
    if raw["observedStatus"] not in TERMINAL_STATUSES:
        raise RetentionValidationError("tombstone_corrupt")
    if raw["diagnosticQuality"] not in {"complete", "partial"}:
        raise RetentionValidationError("tombstone_corrupt")
    if raw["retentionDays"] is None:
        raise RetentionValidationError("tombstone_corrupt")
    normalize_retention_days(raw["retentionDays"])
    if type(raw["fileBytes"]) is not int or not 0 <= raw["fileBytes"] <= MAX_DOCUMENT_BYTES:
        raise RetentionValidationError("tombstone_corrupt")
    enum_fields = (
        ("featureCode", FEATURE_CODES),
        ("routeCode", ROUTE_CODES),
        ("authorityKind", AUTHORITY_KINDS),
    )
    for field, allowed in enum_fields:
        if raw[field] not in allowed:
            raise RetentionValidationError("tombstone_corrupt")
    if raw["taskType"] is not None and raw["taskType"] not in TASK_TYPES:
        raise RetentionValidationError("tombstone_corrupt")
    if raw["jobId"] is not None:
        try:
            valid_id(raw["jobId"], "job")
            if run_id_for_job(raw["jobId"]) != raw["runId"]:
                raise RetentionValidationError("tombstone_corrupt")
        except DiagnosticValidationError as error:
            raise RetentionValidationError("tombstone_corrupt") from error
    for field, allowed in (("failureReasonCode", REASON_CODES), ("failureStageCode", STAGE_CODES)):
        value = raw[field]
        if value is not None and value not in allowed:
            raise RetentionValidationError("tombstone_corrupt")
    encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_TOMBSTONE_ITEM_BYTES:
        raise RetentionValidationError("tombstone_oversized")
    return dict(raw)


def _load_tombstones(store: DiagnosticsStore) -> tuple[dict[str, object], ...]:
    path = Path(store.root) / TOMBSTONE_FILE_NAME
    _safe_path(path)
    if not path.exists():
        return ()
    try:
        raw = _safe_json_bytes(path, MAX_TOMBSTONE_BYTES)
        decoded = json.loads(raw.decode("utf-8"))
    except RetentionError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, OSError) as error:
        raise RetentionUnavailable("tombstone_corrupt") from error
    if type(decoded) is not dict or set(decoded) != {"schemaVersion", "updatedAt", "items"}:
        raise RetentionUnavailable("tombstone_corrupt")
    if decoded["schemaVersion"] != RETENTION_SCHEMA_VERSION or not isinstance(decoded["items"], list) or len(decoded["items"]) > MAX_TOMBSTONES:
        raise RetentionUnavailable("tombstone_corrupt")
    try:
        _parse_timestamp(decoded["updatedAt"], "updated_at")
        result = tuple(_validate_summary(item) for item in decoded["items"])
    except (RetentionError, DiagnosticValidationError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, RetentionError) else "tombstone_corrupt"
        raise RetentionUnavailable(code) from error
    if len({item["runId"] for item in result}) != len(result):
        raise RetentionUnavailable("tombstone_corrupt")
    return result


def _write_tombstones(store: DiagnosticsStore, items: Iterable[dict[str, object]], now: datetime) -> tuple[dict[str, object], ...]:
    root = Path(store.root)
    _safe_path(root, missing_ok=False)
    existing = list(_load_tombstones(store))
    by_id: dict[str, dict[str, object]] = {str(item["runId"]): dict(item) for item in existing}
    for item in items:
        validated = _validate_summary(item)
        by_id.setdefault(str(validated["runId"]), validated)
    ordered = sorted(by_id.values(), key=lambda item: (str(item["deletedAt"]), str(item["runId"])), reverse=True)
    ordered = ordered[:MAX_TOMBSTONES]
    # Keep the ledger bounded even if a future safe field grows unexpectedly.
    while ordered:
        payload = {
            "schemaVersion": RETENTION_SCHEMA_VERSION,
            "updatedAt": _timestamp(now),
            "items": ordered,
        }
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(data) <= MAX_TOMBSTONE_BYTES:
            path = root / TOMBSTONE_FILE_NAME
            _safe_path(path)
            try:
                write_bytes_atomic(path, data)
            except OSError as error:
                raise RetentionUnavailable("tombstone_write_failed") from error
            return tuple(ordered)
        ordered.pop()
    if by_id:
        raise RetentionUnavailable("tombstone_oversized")
    return ()


def _safe_record_path(store: DiagnosticsStore, path: Path) -> bool:
    root = Path(store.runs_root)
    try:
        _safe_path(root, missing_ok=False)
        _safe_path(path, missing_ok=False)
    except RetentionError:
        return False
    return (
        path.parent == root
        and path.name.startswith("run_")
        and path.suffix == ".json"
        and _relative_owned(path, root)
    )


class DiagnosticsRetentionService:
    """Read usage and execute bounded, preview-confirmed diagnostic retention."""

    def __init__(
        self,
        store: DiagnosticsStore,
        *,
        authority_provider: Callable[[], AuthoritySnapshot | Any] | None = None,
        settings_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        token_bytes: Callable[[int], bytes] | None = None,
    ) -> None:
        self.store = store
        self.authority_provider = authority_provider
        self.settings_path = Path(settings_path or (Path(store.root) / SETTINGS_FILE_NAME))
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic_clock = monotonic_clock
        self.token_bytes = token_bytes or secrets.token_bytes
        self._lock = threading.RLock()
        self._tokens: dict[str, _Token] = {}

    def _purge_tokens(self) -> None:
        now = self.monotonic_clock()
        for digest, token in tuple(self._tokens.items()):
            # ``expires_at`` is wall-clock based for API display.  Token age is
            # also bounded by a monotonic issuance marker to resist clock jumps.
            if now >= token.issued_monotonic + RETENTION_TOKEN_TTL_SECONDS:
                self._tokens.pop(digest, None)
        while len(self._tokens) > MAX_RETENTION_TOKENS:
            self._tokens.pop(next(iter(self._tokens)))

    def _issue(
        self,
        *,
        purpose: str,
        fingerprint: str,
        retention_days: int,
        auto_delete: bool | None = None,
        candidates: tuple[RetentionCandidate, ...] = (),
        settings_digest: str | None = None,
        now: datetime,
    ) -> str:
        raw = self.token_bytes(32)
        if not isinstance(raw, bytes) or len(raw) != 32:
            raise RetentionUnavailable("token_source_invalid")
        token = RETENTION_TOKEN_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        digest = hashlib.sha256(raw).hexdigest()
        entry = _Token(
            digest=digest,
            purpose=purpose,
            expires_at=now + timedelta(seconds=RETENTION_TOKEN_TTL_SECONDS),
            fingerprint=fingerprint,
            retention_days=retention_days,
            auto_delete=auto_delete,
            candidates=candidates,
            settings_digest=settings_digest,
            issued_monotonic=self.monotonic_clock(),
        )
        self._tokens[digest] = entry
        self._purge_tokens()
        return token

    def _token(self, value: object, *, purpose: str) -> _Token:
        if not isinstance(value, str) or not value.startswith(RETENTION_TOKEN_PREFIX):
            raise RetentionConflict("preview_token_invalid")
        encoded = value[len(RETENTION_TOKEN_PREFIX):]
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * ((4 - len(encoded) % 4) % 4))
        except (ValueError, TypeError):
            raise RetentionConflict("preview_token_invalid") from None
        if len(raw) != 32:
            raise RetentionConflict("preview_token_invalid")
        digest = hashlib.sha256(raw).hexdigest()
        with self._lock:
            self._purge_tokens()
            entry = self._tokens.get(digest)
            if entry is None or not hmac.compare_digest(entry.digest, digest):
                raise RetentionConflict("preview_token_invalid")
            if entry.purpose != purpose:
                raise RetentionConflict("preview_token_mismatch")
            if entry.used:
                raise RetentionConflict("preview_token_replayed")
            if _now(self.clock) >= entry.expires_at:
                raise RetentionConflict("preview_token_expired")
            # Claim before any filesystem/provider I/O.  A concurrent
            # confirmation therefore cannot reuse the same single-use token.
            entry.used = True
            return entry

    def _settings_file_digest(self) -> str:
        _safe_path(self.settings_path)
        if not self.settings_path.exists():
            return "missing"
        try:
            raw = _safe_json_bytes(self.settings_path, 16 * 1024)
        except RetentionError as error:
            raise RetentionUnavailable(error.code) from error
        return hashlib.sha256(raw).hexdigest()

    def read_settings(self) -> RetentionSettings:
        _safe_path(self.settings_path)
        if not self.settings_path.exists():
            return RetentionSettings()
        try:
            decoded = json.loads(_safe_json_bytes(self.settings_path, 16 * 1024).decode("utf-8"))
        except (RetentionError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            code = error.code if isinstance(error, RetentionError) else "settings_corrupt"
            raise RetentionUnavailable(code) from error
        if type(decoded) is not dict or set(decoded) != {"schemaVersion", "retentionDays", "autoDelete"}:
            raise RetentionUnavailable("settings_corrupt")
        if decoded["schemaVersion"] != RETENTION_SCHEMA_VERSION:
            raise RetentionUnavailable("settings_unsupported_version")
        try:
            return RetentionSettings(
                retention_days=normalize_retention_days(decoded["retentionDays"]),
                auto_delete=decoded["autoDelete"],
            )
        except RetentionError as error:
            raise RetentionUnavailable(error.code) from error

    def _authority_snapshot(self) -> object | None:
        if self.authority_provider is None:
            return None
        try:
            return self.authority_provider()
        except Exception as error:
            raise RetentionUnavailable("authority_unavailable") from error

    def _inventory(self) -> _Inventory:
        root = Path(self.store.root)
        runs_root = Path(self.store.runs_root)
        _safe_path(root)
        _safe_path(runs_root)
        if not root.exists():
            return _Inventory((), 0, 0, 0, (), ())
        if not root.is_dir():
            raise RetentionUnavailable("diagnostics_unavailable")
        entries = 0
        bytes_used = 0
        run_files = 0
        errors: list[str] = []
        records: list[RetentionCandidate] = []
        stack = [root]
        deadline = self.monotonic_clock() + RETENTION_SCAN_DEADLINE_SECONDS
        while stack:
            directory = stack.pop()
            _safe_path(directory, missing_ok=False)
            try:
                scanner = os.scandir(directory)
            except OSError as error:
                raise RetentionUnavailable("diagnostics_read_failed") from error
            try:
                while True:
                    try:
                        item = next(scanner)
                    except StopIteration:
                        break
                    if self.monotonic_clock() >= deadline:
                        # A partial inventory is never reported as a complete
                        # preview/status.  The route maps this stable code to
                        # 503, while automatic cleanup records a blocked
                        # result and waits for the next existing lifecycle
                        # hook.  No incremental scan contract is introduced.
                        raise RetentionUnavailable("scan_deadline")
                    entries += 1
                    if entries > SCAN_ENTRY_LIMIT:
                        raise RetentionUnavailable("scan_limit")
                    path = Path(item.path)
                    _safe_path(path, missing_ok=False)
                    try:
                        item_stat = path.lstat()
                    except OSError as error:
                        raise RetentionUnavailable("diagnostics_read_failed") from error
                    if _is_reparse(path):
                        raise RetentionUnavailable("diagnostics_reparse")
                    if path.is_dir():
                        stack.append(path)
                        continue
                    if not path.is_file():
                        continue
                    bytes_used += item_stat.st_size
                    if path.parent != runs_root or path.suffix != ".json" or not path.name.startswith("run_"):
                        continue
                    run_files += 1
                    if run_files > MAX_RUN_FILES:
                        raise RetentionUnavailable("quota_exceeded")
                    run_id = path.stem
                    try:
                        valid_id(run_id, "run")
                    except DiagnosticValidationError:
                        errors.append("invalid_record_path")
                        continue
                    if item_stat.st_size > MAX_DOCUMENT_BYTES:
                        errors.append("record_oversized")
                        continue
                    try:
                        record, raw, file_hash = _record_file(self.store, path)
                    except RetentionUnavailable as error:
                        errors.append(error.code)
                        continue
                    records.append(
                        RetentionCandidate(
                            run_id=run_id,
                            path=path,
                            size=item_stat.st_size,
                            file_hash=file_hash,
                            created_at=record.created_at,
                            finished_at=record.finished_at or "",
                            observed_status=record.observed_status,
                            authority_signature="",
                            summary=_summary(record),
                        )
                    )
            finally:
                scanner.close()
            if self.monotonic_clock() >= deadline:
                raise RetentionUnavailable("scan_deadline")
        if bytes_used > MAX_DISK_BYTES:
            errors.append("quota_exceeded")
        try:
            tombstones = _load_tombstones(self.store)
        except RetentionUnavailable:
            raise
        return _Inventory(tuple(records), bytes_used, run_files, entries, tombstones, tuple(dict.fromkeys(errors)))

    def _candidate_preview(self, retention_days: int, now: datetime) -> RetentionPreview:
        inventory = self._inventory()
        authority = self._authority_snapshot()
        cutoff = now - timedelta(days=retention_days)
        excluded = {key: 0 for key in EXCLUDED_KEYS}
        # Inventory errors are represented only as a bounded count.  The
        # response is explicitly partial so a corrupt/oversized record is not
        # silently presented as a clean, complete preview.
        partial_codes = {"scan_deadline", "quota_exceeded"}
        excluded["corrupt"] = sum(error not in partial_codes for error in inventory.errors)
        excluded["other"] += sum(error in partial_codes for error in inventory.errors)
        candidates: list[RetentionCandidate] = []
        for candidate in inventory.records:
            record, _raw, _hash = _record_file(self.store, candidate.path)
            if record.finished_at is None or record.observed_status not in TERMINAL_STATUSES:
                excluded["running" if record.finished_at is None else "unknown"] += 1
                continue
            if record.context.authority_kind == "recovery":
                excluded["recovery"] += 1
                continue
            state, authority_status, authority_signature = _authority_state(record, authority)
            if state == "running":
                excluded["running"] += 1
                continue
            if state == "unknown":
                excluded["unknown"] += 1
                continue
            if state == "private_blocked":
                excluded["privateBlocked"] += 1
                continue
            if state == "matched" and authority_status != record.observed_status:
                excluded["authorityChanged"] += 1
                continue
            try:
                finished = _parse_timestamp(record.finished_at, "finished_at")
            except RetentionError:
                excluded["corrupt"] += 1
                continue
            if finished >= cutoff:
                excluded["other"] += 1
                continue
            if len(candidates) >= MAX_RETENTION_CANDIDATES:
                excluded["other"] += 1
                continue
            # Use the exact bytes read for this preview.  Re-reading gives a
            # fingerprint bound to the candidate actually placed in the token.
            raw = _safe_json_bytes(candidate.path, MAX_DOCUMENT_BYTES)
            refreshed = RetentionCandidate(
                run_id=candidate.run_id,
                path=candidate.path,
                size=len(raw),
                file_hash=hashlib.sha256(raw).hexdigest(),
                created_at=record.created_at,
                finished_at=record.finished_at,
                observed_status=record.observed_status,
                authority_signature=authority_signature,
                summary=_summary(record),
            )
            candidates.append(refreshed)
        candidates.sort(key=lambda item: item.run_id)
        candidate_basis = [
            {
                "runId": item.run_id,
                "size": item.size,
                "hash": item.file_hash,
                "createdAt": item.created_at,
                "finishedAt": item.finished_at,
                "status": item.observed_status,
                "authority": item.authority_signature,
            }
            for item in candidates
        ]
        fingerprint = _digest_json({
            "retentionDays": retention_days,
            "cutoffAt": _timestamp(cutoff),
            "candidates": candidate_basis,
        })
        expires = now + timedelta(seconds=RETENTION_TOKEN_TTL_SECONDS)
        token = self._issue(
            purpose="delete",
            fingerprint=fingerprint,
            retention_days=retention_days,
            candidates=tuple(candidates),
            now=now,
        )
        return RetentionPreview(
            token=token,
            retention_days=retention_days,
            cutoff_at=_timestamp(cutoff),
            expires_at=_timestamp(expires),
            candidates=tuple(candidates),
            excluded_counts=excluded,
            fingerprint=fingerprint,
            generated_at=_timestamp(now),
            status="partial" if inventory.errors else "ready",
        )

    def preview(self, retention_days: object) -> dict[str, object]:
        days = normalize_retention_days(retention_days)
        now = _now(self.clock)
        with self._lock:
            result = self._candidate_preview(days, now)
        dates = [item.created_at for item in result.candidates]
        return {
            "version": RETENTION_SCHEMA_VERSION,
            "previewToken": result.token,
            "retentionDays": result.retention_days,
            "cutoffAt": result.cutoff_at,
            "expiresAt": result.expires_at,
            "eligibleCount": len(result.candidates),
            "eligibleBytes": sum(item.size for item in result.candidates),
            "oldestCreatedAt": min(dates) if dates else None,
            "newestCreatedAt": max(dates) if dates else None,
            "excludedCounts": dict(result.excluded_counts),
            "status": result.status,
        }

    def _authority_matches(self, record: DiagnosticRecord, expected: str, authority: object) -> bool:
        state, status, signature = _authority_state(record, authority)
        return state in {"not_applicable", "matched"} and (state == "not_applicable" or (status == record.observed_status and signature == expected))

    def _revalidate_candidate(self, item: RetentionCandidate, authority: object, cutoff: datetime) -> tuple[DiagnosticRecord, bytes]:
        path = _exact_run_path(self.store, item.run_id, must_exist=True)
        try:
            record, raw, file_hash = _record_file(self.store, path)
        except RetentionUnavailable as error:
            raise RetentionConflict("preview_changed") from error
        if len(raw) != item.size or file_hash != item.file_hash:
            raise RetentionConflict("preview_changed")
        if record.finished_at is None or record.observed_status not in TERMINAL_STATUSES:
            raise RetentionConflict("preview_changed")
        if record.context.authority_kind == "recovery":
            raise RetentionConflict("preview_changed")
        if not self._authority_matches(record, item.authority_signature, authority):
            raise RetentionConflict("authority_changed")
        if _parse_timestamp(record.finished_at, "finished_at") >= cutoff:
            raise RetentionConflict("preview_changed")
        with self.store._lock:
            if item.run_id in self.store._handles:
                raise RetentionConflict("live_handle")
        return record, raw

    def confirm(self, preview_token: object, *, confirm: bool = False) -> dict[str, object]:
        if confirm is not True:
            raise RetentionValidationError("confirmation_required")
        token = self._token(preview_token, purpose="delete")
        now = _now(self.clock)
        cutoff = now - timedelta(days=token.retention_days)
        authority = self._authority_snapshot()
        validated: list[tuple[RetentionCandidate, DiagnosticRecord, bytes]] = []
        for item in token.candidates:
            record, raw = self._revalidate_candidate(item, authority, cutoff)
            validated.append((item, record, raw))
        # The service must use the store's existing writer lease and lock.  It
        # never creates a second lease or bypasses live reservations.
        with self.store._lock:
            if not self.store._ensure_lease():
                raise RetentionUnavailable(self.store.last_write_reason or "writer_conflict")
            quota = self.store._accounting()
            if not quota.available:
                raise RetentionUnavailable(quota.reason or "quota_exceeded")
            # Re-check paths while the lease is held, immediately before the
            # intent ledger and unlink.  No other retention request can enter.
            for item, _record, _raw in validated:
                if item.run_id in self.store._handles:
                    raise RetentionConflict("live_handle")
                if not _safe_record_path(self.store, item.path):
                    raise RetentionConflict("diagnostics_reparse")
                current = _safe_json_bytes(item.path, MAX_DOCUMENT_BYTES)
                if len(current) != item.size or hashlib.sha256(current).hexdigest() != item.file_hash:
                    raise RetentionConflict("preview_changed")
            summaries = [
                _summary(record, deleted_at=_timestamp(now), retention_days=token.retention_days, file_bytes=len(raw))
                for _item, record, raw in validated
            ]
            # Writing the explicit ledger before unlink protects the detail
            # contract across a crash between delete and state persistence.
            _write_tombstones(self.store, summaries, now)
            deleted = 0
            deleted_bytes = 0
            skipped: dict[str, int] = {}
            for item, _record, raw in validated:
                try:
                    _safe_path(item.path, missing_ok=False)
                    # Restrict the actual mutation to the exact generated name.
                    if not _safe_record_path(self.store, item.path):
                        raise OSError("invalid_target")
                    item.path.unlink()
                except OSError:
                    skipped["deleteFailed"] = skipped.get("deleteFailed", 0) + 1
                    continue
                deleted += 1
                deleted_bytes += len(raw)
            if deleted:
                self.store.mark_external_deletions()
        token.used = True
        dates = [item.created_at for item, _record, _raw in validated]
        return {
            "version": RETENTION_SCHEMA_VERSION,
            "retentionDays": token.retention_days,
            "deletedCount": deleted,
            "deletedBytes": deleted_bytes,
            "tombstoneCount": deleted,
            "oldestCreatedAt": min((item.created_at for item, _r, _raw in validated), default=None),
            "newestCreatedAt": max((item.created_at for item, _r, _raw in validated), default=None),
            "status": "complete" if not skipped else "partial",
            "skippedCounts": skipped,
        }

    def settings_preview(self, retention_days: object, auto_delete: object) -> dict[str, object]:
        days = normalize_retention_days(retention_days)
        if type(auto_delete) is not bool:
            raise RetentionValidationError("invalid_auto_delete")
        now = _now(self.clock)
        current = self.read_settings()
        current_digest = self._settings_file_digest()
        fingerprint = _digest_json({
            "retentionDays": days,
            "autoDelete": auto_delete,
            "current": current.to_dict(),
            "settingsDigest": current_digest,
        })
        with self._lock:
            token = self._issue(
                purpose="settings",
                fingerprint=fingerprint,
                retention_days=days,
                auto_delete=auto_delete,
                settings_digest=current_digest,
                now=now,
            )
        return {
            "version": RETENTION_SCHEMA_VERSION,
            "previewToken": token,
            "retentionDays": days,
            "autoDelete": auto_delete,
            "changed": current.retention_days != days or current.auto_delete != auto_delete,
            "expiresAt": _timestamp(now + timedelta(seconds=RETENTION_TOKEN_TTL_SECONDS)),
            "current": {
                "retentionDays": current.retention_days,
                "autoDelete": current.auto_delete,
            },
            "status": "ready",
        }

    def settings_confirm(self, preview_token: object, *, confirm: bool = False) -> dict[str, object]:
        if confirm is not True:
            raise RetentionValidationError("confirmation_required")
        token = self._token(preview_token, purpose="settings")
        if token.auto_delete is None:
            raise RetentionConflict("preview_token_mismatch")
        settings = RetentionSettings(token.retention_days, token.auto_delete)
        # Settings live beside the diagnostic runs.  Create only the owned
        # diagnostics directory after taking the existing writer lease; this
        # also lets a user choose a policy before the first run exists.
        with self.store._lock:
            if not self.store._ensure_lease():
                raise RetentionUnavailable(self.store.last_write_reason or "writer_conflict")
            try:
                # Re-read the compare-and-swap basis under the same store
                # lock used for the durable replacement.
                current_digest = self._settings_file_digest()
                if current_digest != token.settings_digest:
                    raise RetentionConflict("settings_changed")
                self.store._prepare_root()
                root = Path(self.store.root)
                _safe_path(root, missing_ok=False)
                _safe_path(self.settings_path)
                write_bytes_atomic(self.settings_path, json.dumps(settings.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                # The settings file is part of the bounded diagnostics root;
                # invalidate any warm quota snapshot so a later admission
                # accounts for its newly-created bytes/entry.
                self.store.mark_external_deletions()
            except RetentionError:
                raise
            except OSError as error:
                raise RetentionUnavailable("settings_write_failed") from error
        token.used = True
        return {
            "version": RETENTION_SCHEMA_VERSION,
            "retentionDays": settings.retention_days,
            "autoDelete": settings.auto_delete,
            "updatedAt": _timestamp(_now(self.clock)),
            "status": "saved",
        }

    def usage_status(self) -> dict[str, object]:
        """Read usage/settings without acquiring the diagnostics writer lease."""

        settings = self.read_settings()
        inventory = self._inventory()
        available = not inventory.errors and inventory.bytes_used <= MAX_DISK_BYTES and inventory.run_files <= MAX_RUN_FILES
        reason = inventory.errors[0] if inventory.errors else None
        return {
            "version": RETENTION_SCHEMA_VERSION,
            "settings": {
                "retentionDays": settings.retention_days,
                "autoDelete": settings.auto_delete,
                "choices": list(RETENTION_CHOICES),
                "defaultRetentionDays": DEFAULT_RETENTION_DAYS,
            },
            "usage": {
                "bytesUsed": inventory.bytes_used,
                "runFiles": inventory.run_files,
                "tombstones": len(inventory.tombstones),
                "entries": inventory.entries,
            },
            "limits": {
                "maxBytes": MAX_DISK_BYTES,
                "maxRunFiles": MAX_RUN_FILES,
                "maxTombstones": MAX_TOMBSTONES,
            },
            "status": {
                "code": "ready" if available else "partial",
                "available": available,
                "reason": reason,
            },
        }

    def run_automatic(self) -> dict[str, object]:
        """Best-effort bounded cleanup called by an existing terminal hook.

        No worker/thread/scheduler is created here.  A missing authority
        provider deliberately means only direct diagnostics are eligible; a
        job-linked record is private-blocked until the host supplies a current
        authority snapshot.
        """

        try:
            settings = self.read_settings()
            if not settings.auto_delete:
                return {"status": "disabled", "deletedCount": 0, "deletedBytes": 0}
            with self._lock:
                preview = self._candidate_preview(settings.retention_days, _now(self.clock))
            # Automatic terminal cleanup is still bounded by the same internal
            # fingerprints and exact-file checks, but does not expose or issue
            # a user token.
            authority = self._authority_snapshot()
            now = _now(self.clock)
            cutoff = now - timedelta(days=settings.retention_days)
            validated: list[tuple[RetentionCandidate, DiagnosticRecord, bytes]] = []
            for item in preview.candidates:
                try:
                    record, raw = self._revalidate_candidate(item, authority, cutoff)
                except RetentionError:
                    continue
                validated.append((item, record, raw))
            if not validated:
                return {"status": "complete", "deletedCount": 0, "deletedBytes": 0}
            with self.store._lock:
                if not self.store._ensure_lease():
                    return {"status": "blocked", "reason": self.store.last_write_reason or "writer_conflict", "deletedCount": 0, "deletedBytes": 0}
                quota = self.store._accounting()
                if not quota.available:
                    return {"status": "blocked", "reason": quota.reason or "quota_exceeded", "deletedCount": 0, "deletedBytes": 0}
                batch = validated[:MAX_RETENTION_CANDIDATES]
                summaries = [_summary(record, deleted_at=_timestamp(now), retention_days=settings.retention_days, file_bytes=len(raw)) for _i, record, raw in batch]
                _write_tombstones(self.store, summaries, now)
                deleted = 0
                deleted_bytes = 0
                for item, _record, raw in batch:
                    try:
                        if not _safe_record_path(self.store, item.path):
                            continue
                        current = _safe_json_bytes(item.path, MAX_DOCUMENT_BYTES)
                        if hashlib.sha256(current).hexdigest() != item.file_hash:
                            continue
                        item.path.unlink()
                    except OSError:
                        continue
                    deleted += 1
                    deleted_bytes += len(raw)
                if deleted:
                    self.store.mark_external_deletions()
            return {"status": "complete", "deletedCount": deleted, "deletedBytes": deleted_bytes}
        except RetentionError as error:
            return {"status": "blocked", "reason": error.code, "deletedCount": 0, "deletedBytes": 0}
        except Exception:
            return {"status": "blocked", "reason": "retention_unavailable", "deletedCount": 0, "deletedBytes": 0}


__all__ = [
    "DEFAULT_AUTO_DELETE",
    "DEFAULT_RETENTION_DAYS",
    "DiagnosticsRetentionService",
    "EXCLUDED_KEYS",
    "MAX_TOMBSTONES",
    "MAX_TOMBSTONE_BYTES",
    "MAX_RETENTION_CANDIDATES",
    "RETENTION_SCAN_DEADLINE_SECONDS",
    "RETENTION_CHOICES",
    "RetentionConflict",
    "RetentionError",
    "RetentionSettings",
    "RetentionUnavailable",
    "RetentionValidationError",
    "normalize_retention_days",
]
