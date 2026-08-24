from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from features.common.jcs import JsonValue
from features.common.job_json_recovery import recover_json_jobs_startup
from features.common.shared_jobs_compat import (
    MESSAGES,
    compatibility_job,
    job_identity,
    safe_private,
    terminal_live_detail,
    worker_projection,
)
from features.common.shared_jobs_private import JobPrivateLifecycle, PrivateCleanupError
from features.common.shared_jobs_projection import ARTIFACT_TASKS, new_shared_job, project_terminal_result
from features.common.shared_jobs_schema import (
    Adapter,
    Engine,
    ErrorCode,
    GenerationMode,
    JobKind,
    JobMode,
    JobStatus,
    RequestedMode,
    SharedJob,
    TaskType,
)
from features.common.shared_jobs_store import (
    JobTransitionError,
    JobsStoreUnavailableError,
    LegacyJobCollisionError,
    SharedJobStore,
)
from features.common.atomic_replace import write_bytes_atomic
from features.common.workspace import data_dir


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = data_dir()
JOBS_PATH = DATA_DIR / "jobs.json"
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOB_LOCK = threading.RLock()
JOBS: dict[str, dict[str, JsonValue]] = {}
FUTURES: dict[str, Future[None] | threading.Thread] = {}
_LIFECYCLES: dict[str, JobPrivateLifecycle] = {}


def _clock() -> datetime:
    return datetime.now(UTC)


def _store() -> SharedJobStore:
    return SharedJobStore(JOBS_PATH.with_name("jobs-v2.json"), JOBS_PATH, clock=_clock)


def _lifecycle() -> JobPrivateLifecycle:
    root = JOBS_PATH.parent / "job-context"
    key = str(root.resolve())
    with JOB_LOCK:
        if key not in _LIFECYCLES:
            _LIFECYCLES[key] = JobPrivateLifecycle(root, clock=_clock)
    return _LIFECYCLES[key]


def shared_store() -> SharedJobStore:
    return _store()


def private_lifecycle() -> JobPrivateLifecycle:
    return _lifecycle()


def data_root() -> Path:
    return JOBS_PATH.parent


def write_job_pack(job_id: str, pack_id: str, pack: dict[str, JsonValue]) -> Path:
    return _lifecycle().write_pack(job_id, pack_id, pack)


def get_shared_job(job_id: str) -> SharedJob | None:
    return _store().get(str(job_id))


def _recover_sql_jobs_startup(store: SharedJobStore, lifecycle: JobPrivateLifecycle) -> None:
    committing = [
        job
        for job in store.load().jobs
        if job.status is JobStatus.COMMITTING
        and job.taskType in {
            TaskType.THESIS_DELTA,
            TaskType.MARKET_MEMORY_LLM,
            TaskType.MARKET_STATE_SNAPSHOT,
            TaskType.MARKET_MEMORY_UPDATE,
        }
    ]
    if not committing:
        return
    from features.common.sql_job_lifecycle import SqlJobLifecycle
    from features.market_memory.attempt_store import AttemptStore
    from features.market_memory.memory import init_db
    from features.market_memory.snapshot import ensure_snapshot_table
    from features.market_memory.sql_job_service import MarketSqlJobRuntime, recover_market_sql_job
    from features.thesis_tracking import store as thesis_store
    from features.thesis_tracking.sql_job_service import recover_thesis_delta_job

    root = JOBS_PATH.parent
    connection = thesis_store.connect(root / "market-memory.sqlite3")
    init_db(connection)
    ensure_snapshot_table(connection, initialize_graph=False)
    connection.commit()
    sql_lifecycle = SqlJobLifecycle(store, lifecycle)
    runtime = MarketSqlJobRuntime(
        lifecycle=sql_lifecycle,
        attempts=AttemptStore(root / "market-state-update-attempts.json"),
        clock=_clock,
    )
    try:
        for job in committing:
            if job.taskType is TaskType.THESIS_DELTA:
                recover_thesis_delta_job(connection, sql_lifecycle, job.id)
            else:
                recover_market_sql_job(connection, runtime, job.id)
    finally:
        connection.close()


def _compat(job: SharedJob, *, detail: bool) -> dict[str, JsonValue]:
    record = _lifecycle().live_terminal.get(job.id) if detail else None
    return compatibility_job(job, record.detail if record is not None else None)


def _refresh_cache() -> None:
    global JOBS
    merged = _store().merged().jobs
    JOBS = {job.id: _compat(job, detail=False) for job in merged}


LEGACY_INTERRUPTED_STATUSES = frozenset({"queued", "running", "cancel_requested"})


def _fail_legacy_interrupted_jobs() -> None:
    """legacy `data/jobs.json`에 남은 queued/running 행을 failed_restart로 못박는다.

    API는 `JOBS` 캐시가 아니라 매 요청 `_store().merged()`를 다시 읽고, merged()는
    legacy 행을 그대로 싣는다. 복구 경로(`recover_startup`)는 jobs-v2.json만 순회하므로
    이 파일을 고치지 않으면 구버전에서 남은 running 행이 영원히 실행 중으로 보이고
    화면은 끝나지 않는 작업을 계속 폴링한다(§서버 재시작의 좀비 잡 방지).

    상태만 바꾸고 나머지 필드와 다른 행은 그대로 둔다. 파일을 못 읽거나 못 쓰면
    조용히 넘어간다 — 좀비 한 줄이 남는 쪽이 서버가 안 켜지는 쪽보다 낫다.
    """
    try:
        raw = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return
    if not isinstance(raw, dict):
        return
    changed = False
    for row in raw.values():
        if not isinstance(row, dict) or row.get("status") not in LEGACY_INTERRUPTED_STATUSES:
            continue
        row["status"] = JobStatus.FAILED_RESTART.value
        row["message"] = MESSAGES[JobStatus.FAILED_RESTART.value]
        # 끝난 잡은 막대도 끝나야 한다. 멈춘 시점의 진행률(예: 40%)을 그대로 두면
        # 화면에 40%짜리 실패 잡이 남아 아직 도는 것처럼 보인다.
        row["progress"] = 100
        changed = True
    if not changed:
        return
    try:
        write_bytes_atomic(JOBS_PATH, json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8"))
    except OSError:
        return


def load_jobs() -> None:
    store = _store()
    lifecycle = _lifecycle()
    from features.topic_report.candidate_recovery import recover_deep_candidates_startup

    steps: tuple[Callable[[], None], ...] = (
        lambda: recover_json_jobs_startup(JOBS_PATH.parent, store, lifecycle, clock=_clock),
        lambda: _recover_sql_jobs_startup(store, lifecycle),
        lambda: recover_deep_candidates_startup(JOBS_PATH.parent, store, lifecycle, clock=_clock),
        lambda: lifecycle.recover_startup(store),
    )
    for step in steps:
        try:
            step()
        except PrivateCleanupError:
            # 비공개 pack 삭제가 끝내 막혀도 기동은 막지 않는다. 차단 사실은
            # lifecycle.cleanup_blocked에 남아 잡 조회가 503으로 닫히고(fail-closed),
            # 잠금이 풀린 다음 시작에서 같은 복구를 다시 시도한다.
            continue
    _fail_legacy_interrupted_jobs()
    _refresh_cache()


def persist_jobs() -> None:
    _refresh_cache()


def update_job(job_id: str, **changes) -> dict[str, JsonValue] | None:
    store = _store()
    current = store.get(job_id)
    if current is None:
        return None
    status_value = changes.get("status")
    if isinstance(status_value, str) and status_value != current.status.value:
        target = JobStatus(status_value)
        store.transition(job_id, target, result=worker_projection(changes.get("result")), error_code=changes.get("errorCode"))
    else:
        store.update_runtime(job_id, changes)
    _refresh_cache()
    return get_job(job_id)


def job_progress(job_id: str):
    def _progress(_message, progress=None, **extra) -> None:
        changes: dict[str, JsonValue] = {}
        if isinstance(progress, int):
            changes["progress"] = max(0, min(progress, 99))
        for key in ("engine", "adapter", "attemptedEngine", "finalEngine", "fallbackReason", "proposalId"):
            if key not in extra:
                continue
            value = extra[key]
            if key in {"engine", "adapter"} and value is None:
                continue
            if value is None or isinstance(value, str):
                changes[key] = value
        if changes:
            _store().update_runtime(job_id, changes)
            _refresh_cache()

    return _progress


def compact_job_result(result):
    return worker_projection(result)


def run_job(job_id: str, fn, *args, **kwargs) -> None:
    store = _store()
    try:
        store.transition(job_id, JobStatus.RUNNING)
        fn_job_id = kwargs.pop("_folio_job_id", "")
        if fn_job_id:
            kwargs["job_id"] = fn_job_id
        result = fn(*args, progress=job_progress(job_id), **kwargs)
        current = store.get(job_id)
        if current is None:
            return
        if current.status in {
            JobStatus.DONE,
            JobStatus.CANCELLED,
            JobStatus.FAILED,
            JobStatus.FAILED_CANCEL,
            JobStatus.FAILED_COMMIT,
            JobStatus.FAILED_RESTART,
            JobStatus.FAILED_COMMIT_RECOVERY,
            JobStatus.COMMITTING,
        }:
            return
        if current.status == JobStatus.CANCEL_REQUESTED:
            _lifecycle().terminalize(store, job_id, JobStatus.CANCELLED)
        elif current.taskType in ARTIFACT_TASKS:
            _lifecycle().terminalize(
                store,
                job_id,
                JobStatus.FAILED,
                error_code=ErrorCode.SAVE_FAILED,
            )
        else:
            projection = worker_projection(result)
            proposal_id = projection.get("proposalId")
            if isinstance(proposal_id, str):
                store.update_runtime(job_id, {"proposalId": proposal_id})
            _lifecycle().terminalize(
                store,
                job_id,
                JobStatus.DONE,
                result=projection,
                live_detail=terminal_live_detail(current, result),
            )
    except Exception:  # noqa: BROAD_EXCEPT_OK
        current = store.get(job_id)
        if current is not None and current.status not in {
            JobStatus.CANCELLED,
            JobStatus.DONE,
            JobStatus.COMMITTING,
            JobStatus.FAILED,
            JobStatus.FAILED_CANCEL,
            JobStatus.FAILED_COMMIT,
            JobStatus.FAILED_RESTART,
            JobStatus.FAILED_COMMIT_RECOVERY,
        }:
            try:
                target = (
                    JobStatus.CANCELLED
                    if current.status is JobStatus.CANCEL_REQUESTED
                    else JobStatus.FAILED
                )
                _lifecycle().terminalize(
                    store,
                    job_id,
                    target,
                    error_code=(
                        None
                        if target is JobStatus.CANCELLED
                        else ErrorCode.INTERNAL_ERROR
                    ),
                )
            except PrivateCleanupError:
                return
    finally:
        _refresh_cache()


def submit_job(kind, _label, fn, *args, pass_job_id=False, executor=None, dedicated_thread=False, **kwargs):
    identity = job_identity(kind, getattr(fn, "__name__", ""), args, kwargs.get("adapter"))
    parsed_kind, task, generation, adapter, mode, attempted = identity
    requested_mode = (
        RequestedMode.CLI
        if parsed_kind is JobKind.AGENT_BRIDGE
        else RequestedMode.DIRECT
        if parsed_kind is JobKind.TOPIC_REPORT
        else None
    )
    job = new_shared_job(
        kind=parsed_kind,
        task_type=task,
        generation_mode=generation,
        adapter=adapter,
        requested_mode=requested_mode,
        mode=mode,
        attempted_engine=attempted,
        clock=_clock,
    )
    _store().add(job)
    _lifecycle().set_private(job.id, safe_private(args, kwargs))
    if pass_job_id:
        kwargs["_folio_job_id"] = job.id
    if dedicated_thread:
        future = threading.Thread(target=run_job, args=(job.id, fn, *args), kwargs=kwargs, name=f"folio-job-{kind}-{job.id[-6:]}", daemon=True)
        future.start()
    else:
        future = (executor or JOB_EXECUTOR).submit(run_job, job.id, fn, *args, **kwargs)
    FUTURES[job.id] = future
    _refresh_cache()
    return _compat(job, detail=False)


def get_job(job_id: str) -> dict[str, JsonValue] | None:
    _lifecycle().assert_readable()
    job = _store().merged()
    matched = next((item for item in job.jobs if item.id == str(job_id)), None)
    return _compat(matched, detail=True) if matched is not None else None


def cancel_job(job_id: str) -> dict[str, JsonValue]:
    store = _store()
    current = store.get(str(job_id))
    if current is None:
        return {"cancelled": False, "error": "Job not found"}
    if current.status in {JobStatus.DONE, JobStatus.CANCELLED} or current.status.value.startswith("failed"):
        return {"cancelled": False, "job": _compat(current, detail=False)}
    if current.status == JobStatus.COMMITTING:
        return {"cancelled": False, "job": _compat(current, detail=False)}
    future = FUTURES.get(current.id)
    if current.status == JobStatus.QUEUED and isinstance(future, Future) and future.cancel():
        _lifecycle().terminalize(store, current.id, JobStatus.CANCELLED)
        return {"cancelled": True, "job": get_job(current.id)}
    if current.status == JobStatus.QUEUED:
        store.transition(current.id, JobStatus.RUNNING)
    store.transition(current.id, JobStatus.CANCEL_REQUESTED)
    _refresh_cache()
    return {"cancelled": True, "job": get_job(current.id)}


def recent_jobs(limit: int = 20) -> list[dict[str, JsonValue]]:
    _lifecycle().assert_readable()
    rows = [_compat(job, detail=False) for job in _store().merged().jobs]
    return rows[: max(0, min(limit, 200))]
