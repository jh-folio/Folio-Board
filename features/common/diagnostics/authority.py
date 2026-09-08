"""Read-only authority snapshots for the diagnostics list.

The diagnostic archive is deliberately observational.  This module joins a
validated diagnostic header to the current SharedJob/Work Log/automation
authority without going through the normal stores' recovery paths.  In
particular, ``WorkLogService`` and the ``load`` methods of the durable stores
are not used here: both are allowed to repair a backup as part of their
normal lifecycle, which is not acceptable for a GET list request.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import Callable, Final, Iterable

from pydantic import ValidationError

from features.agent_mode.work_log_schema import WorkLogStoreFile
from features.agent_mode.work_log_store import work_log_lock
from features.common.shared_jobs_legacy import normalize_legacy_job
from features.common.shared_jobs_projection import ARTIFACT_TASKS
from features.common.shared_jobs_schema import JobsStoreFile, SharedJob, TaskType
from features.common.shared_jobs_store import store_lock

from .schema import valid_id
from .store import _is_reparse


MAX_AUTHORITY_FILE_BYTES: Final = 2 * 1024 * 1024
MAX_AUTOMATION_ROWS: Final = 200
AUTOMATION_STATUSES: Final = frozenset({"submitted", "done", "failed"})


class AuthoritySnapshotUnavailable(RuntimeError):
    """A current authority/control snapshot could not be read safely."""

    def __init__(self, code: str = "authority_unavailable") -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class AuthorityJob:
    """The small, safe subset of a SharedJob needed by a list projection."""

    id: str
    status: str
    task_type: str
    created_at: str
    work_log_id: str | None
    work_log_eligible: bool


@dataclass(frozen=True, slots=True)
class AutomationAuthority:
    run_id: str
    status: str


@dataclass(frozen=True, slots=True)
class AuthoritySnapshot:
    """One read-only authority view used as a cursor visibility boundary.

    SharedJob/Work Log and automation are observed in separate critical
    sections because automation reconciliation may hold its lock while
    reading SharedJob.  ``visibility_revision`` makes that bounded observation
    explicit to cursor continuation; it is not a cross-process transaction.
    """

    jobs: tuple[AuthorityJob, ...]
    hidden_job_ids: frozenset[str]
    automation: tuple[AutomationAuthority, ...]
    jobs_revision: int
    work_log_revision: int
    visibility_revision: str

    @property
    def jobs_by_id(self) -> dict[str, AuthorityJob]:
        return {job.id: job for job in self.jobs}

    @property
    def automation_by_run(self) -> dict[str, str]:
        # The durable file is newest-first.  Keep the first row if a malformed
        # external writer duplicated an id after validation; this mirrors the
        # existing automation screen's newest-row semantics.
        result: dict[str, str] = {}
        for row in self.automation:
            result.setdefault(row.run_id, row.status)
        return result


def work_log_id_for_job(job_id: str) -> str:
    """Return the exact ID algorithm used by ``WorkLogView``."""

    # SharedJob validates UUID-shaped ids, while legacy normalization retains
    # older non-UUID ids.  WorkLogView hashes both, so do not apply the v2
    # regex again here (doing so would turn one legacy row into a 503).
    if not isinstance(job_id, str) or not job_id:
        raise AuthoritySnapshotUnavailable("jobs_store_unavailable")
    return f"wl_{hashlib.sha256(job_id.encode()).hexdigest()[:24]}"


def _lstat_exists(path: Path) -> bool:
    """Use lstat so dangling links are still treated as present."""

    try:
        Path(path).lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise AuthoritySnapshotUnavailable() from error
    return True


def _safe_path(path: Path) -> None:
    """Reject a reparse/symlink pivot on an application-owned path."""

    candidate = Path(path)
    # Check every existing parent and the leaf with lstat.  ``Path.exists``
    # follows links and therefore misses a dangling symlink; ``resolve`` alone
    # follows a junction before the caller has a chance to reject it.
    current = candidate
    while True:
        if _lstat_exists(current) and _is_reparse(current):
            raise AuthoritySnapshotUnavailable("authority_reparse")
        if current.parent == current:
            break
        current = current.parent


def _read_bounded(path: Path) -> bytes:
    _safe_path(path)
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_AUTHORITY_FILE_BYTES + 1)
    except OSError as error:
        raise AuthoritySnapshotUnavailable() from error
    if len(raw) > MAX_AUTHORITY_FILE_BYTES:
        raise AuthoritySnapshotUnavailable("authority_oversized")
    return raw


def _parse_model(path: Path, model: type, backup: Path) -> object | None:
    """Parse the current main file without restoring or resurrecting backup."""

    _safe_path(path)
    _safe_path(backup)
    main_exists = _lstat_exists(path)
    backup_exists = _lstat_exists(backup)
    # Recovery is an explicit lifecycle operation.  A list request must not
    # claim an older backup is current when the main file is missing/corrupt.
    if not main_exists:
        if backup_exists:
            raise AuthoritySnapshotUnavailable()
        return None
    try:
        return model.model_validate_json(_read_bounded(path))
    except (AuthoritySnapshotUnavailable, ValidationError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise AuthoritySnapshotUnavailable() from error


def _work_log_id(job_id: str) -> str:
    return work_log_id_for_job(job_id)


def _authority_job(job: SharedJob) -> AuthorityJob:
    task_type = job.taskType.value
    eligible = job.taskType == TaskType.COMPANION or job.taskType in ARTIFACT_TASKS
    return AuthorityJob(
        id=job.id,
        status=job.status.value,
        task_type=task_type,
        created_at=job.createdAt,
        work_log_id=_work_log_id(job.id) if eligible else None,
        work_log_eligible=eligible,
    )


def _parse_jobs(
    v2_path: Path,
    legacy_path: Path,
    *,
    clock: Callable[[], datetime],
) -> tuple[int, tuple[AuthorityJob, ...]]:
    """Read v2 and legacy jobs with the same merge precedence as ``merged``."""

    v2 = _parse_model(v2_path, JobsStoreFile, v2_path.with_name(v2_path.name + ".bak"))
    current: dict[str, SharedJob] = {}
    revision = 0
    if v2 is not None:
        revision = int(v2.storeRevision)
        current = {job.id: job for job in v2.jobs}

    # The legacy file is not a v2 backup.  It is an independent compatibility
    # source and is intentionally parsed without calling ``SharedJobStore``.
    _safe_path(legacy_path)
    if _lstat_exists(legacy_path):
        raw = _read_bounded(legacy_path)
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise AuthoritySnapshotUnavailable("jobs_store_unavailable") from error
        if not isinstance(decoded, dict):
            raise AuthoritySnapshotUnavailable("jobs_store_unavailable")
        for job_id, item in decoded.items():
            if not isinstance(job_id, str) or not isinstance(item, dict):
                raise AuthoritySnapshotUnavailable("jobs_store_unavailable")
            try:
                legacy = normalize_legacy_job(job_id, item, clock)
            except Exception as error:  # parser emits no safe partial authority
                raise AuthoritySnapshotUnavailable("jobs_store_unavailable") from error
            current.setdefault(legacy.id, legacy)

    rows = tuple(_authority_job(job) for job in current.values())
    return revision, rows


def _parse_work_log(path: Path, jobs: tuple[AuthorityJob, ...]) -> tuple[int, frozenset[str]]:
    model = _parse_model(path, WorkLogStoreFile, path.with_name(path.name + ".bak"))
    if model is None:
        state_revision = 0
        hidden: Iterable[str] = ()
    else:
        state_revision = int(model.storeRevision)
        hidden = tuple(item.jobId for item in model.hiddenJobs)
    # Preserve hidden IDs in the revision even if their current job was pruned;
    # a later job with the same ID must not resurrect an old hidden row.
    return state_revision, frozenset(str(item) for item in hidden)


def _automation_status(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or raw not in AUTOMATION_STATUSES:
        raise AuthoritySnapshotUnavailable("automation_store_unavailable")
    return "running" if raw == "submitted" else raw


def _parse_automation(path: Path) -> tuple[AutomationAuthority, ...]:
    _safe_path(path)
    backup = path.with_name(path.name + ".bak")
    _safe_path(backup)
    if not _lstat_exists(path):
        # There is no normal automation recovery path.  If a backup-shaped
        # sibling is present, fail closed rather than presenting an older run
        # authority as current; an entirely absent store remains empty.
        if _lstat_exists(backup):
            raise AuthoritySnapshotUnavailable("automation_store_unavailable")
        return ()
    raw = _read_bounded(path)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise AuthoritySnapshotUnavailable("automation_store_unavailable") from error
    if not isinstance(decoded, list) or len(decoded) > MAX_AUTOMATION_ROWS:
        raise AuthoritySnapshotUnavailable("automation_store_unavailable")
    rows: list[AutomationAuthority] = []
    for item in decoded:
        if not isinstance(item, dict):
            raise AuthoritySnapshotUnavailable("automation_store_unavailable")
        diagnostic_id = item.get("diagnosticRunId")
        status = _automation_status(item.get("status"))
        if diagnostic_id is None:
            continue
        if status is None or not isinstance(diagnostic_id, str):
            raise AuthoritySnapshotUnavailable("automation_store_unavailable")
        try:
            valid_id(diagnostic_id, "run")
        except Exception as error:
            raise AuthoritySnapshotUnavailable("automation_store_unavailable") from error
        rows.append(AutomationAuthority(diagnostic_id, status))
    return tuple(rows)


def _visibility_revision(
    jobs: tuple[AuthorityJob, ...],
    hidden: frozenset[str],
    automation: tuple[AutomationAuthority, ...],
    jobs_revision: int,
    work_log_revision: int,
) -> str:
    payload = {
        # SharedJob revisions change for progress/status writes.  Those do not
        # change list membership, and expiring a cursor for every progress tick
        # would make pagination unusable while a job runs.  Membership and
        # WorkLog control revision below are the visibility facts.
        "workLogRevision": work_log_revision,
        "jobs": [
            {
                "id": job.id,
                "eligible": job.work_log_eligible,
            }
            for job in sorted(jobs, key=lambda item: item.id)
        ],
        "hidden": sorted(hidden),
        "automation": sorted({row.run_id for row in automation}),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class ReadOnlyAuthoritySnapshotProvider:
    """Read current authority exactly once per request under existing locks."""

    def __init__(
        self,
        *,
        v2_path: Path,
        legacy_path: Path,
        work_log_path: Path,
        automation_path: Path,
        assert_readable: Callable[[], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.v2_path = Path(v2_path)
        self.legacy_path = Path(legacy_path)
        self.work_log_path = Path(work_log_path)
        self.automation_path = Path(automation_path)
        self.assert_readable = assert_readable
        self.clock = clock or (lambda: datetime.now(UTC))

    def snapshot(self) -> AuthoritySnapshot:
        if self.assert_readable is not None:
            try:
                self.assert_readable()
            except Exception as error:
                raise AuthoritySnapshotUnavailable("jobs_store_unavailable") from error
        # Match the existing writer order for the job/control domain.  No
        # diagnostics write lease is taken by this read-only provider.
        try:
            # Reject reparse points before resolving paths for lock names.  A
            # lock key is not a read, but resolving an attacker-controlled
            # symlink/junction before this guard would still cross the
            # application boundary and make the read protection misleading.
            for control_path in (
                self.v2_path,
                self.legacy_path,
                self.work_log_path,
                self.automation_path,
            ):
                _safe_path(control_path)
            job_lock = store_lock(str(self.v2_path.resolve(strict=False)))
            control_lock = work_log_lock(str(self.work_log_path.resolve(strict=False)))
            from features.automation import service as automation_service
            automation_lock = getattr(automation_service, "_RUNS_LOCK", None)
            if automation_lock is None:
                automation_lock = RLock()
        except AuthoritySnapshotUnavailable:
            raise
        except Exception as error:
            raise AuthoritySnapshotUnavailable() from error
        try:
            # Automation reconciliation can hold _RUNS_LOCK and then call the
            # SharedJob reader.  Keep domains in separate critical sections;
            # a cross-domain job->automation nesting would deadlock with that
            # existing writer path.  The revision below makes the resulting
            # independently observed snapshot a cursor boundary.
            with job_lock:
                with control_lock:
                    jobs_revision, jobs = _parse_jobs(self.v2_path, self.legacy_path, clock=self.clock)
                    work_log_revision, hidden = _parse_work_log(self.work_log_path, jobs)
                    # An unfinished migration journal means the visibility
                    # projection is in-flight.  The normal service repairs
                    # it; a GET must fail closed and never repair it.
                    journal = next(self.work_log_path.parent.glob("job-migration-*.json"), None)
                    if journal is not None:
                        _safe_path(journal)
                        raise AuthoritySnapshotUnavailable("work_log_store_unavailable")
            with automation_lock:
                automation = _parse_automation(self.automation_path)
        except AuthoritySnapshotUnavailable:
            raise
        except OSError as error:
            raise AuthoritySnapshotUnavailable() from error
        revision = _visibility_revision(jobs, hidden, automation, jobs_revision, work_log_revision)
        return AuthoritySnapshot(
            jobs=jobs,
            hidden_job_ids=hidden,
            automation=automation,
            jobs_revision=jobs_revision,
            work_log_revision=work_log_revision,
            visibility_revision=revision,
        )

    def __call__(self) -> AuthoritySnapshot:
        return self.snapshot()


def default_authority_snapshot() -> AuthoritySnapshot:
    """Resolve the configured Folio workspace only when a list request runs."""

    from features.common import jobs

    legacy = jobs.JOBS_PATH
    provider = ReadOnlyAuthoritySnapshotProvider(
        v2_path=legacy.with_name("jobs-v2.json"),
        legacy_path=legacy,
        work_log_path=legacy.with_name("agent-work-log.json"),
        automation_path=legacy.with_name("automation-runs.json"),
        assert_readable=jobs.private_lifecycle().assert_readable,
    )
    return provider.snapshot()


__all__ = [
    "AuthorityJob",
    "AuthoritySnapshot",
    "AuthoritySnapshotUnavailable",
    "AutomationAuthority",
    "ReadOnlyAuthoritySnapshotProvider",
    "default_authority_snapshot",
    "work_log_id_for_job",
]
