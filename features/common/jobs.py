from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
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
from features.common.diagnostics.runtime import DiagnosticsRuntime, _trusted_frame
from features.common.diagnostics.schema import new_context, safe_exception_failure
from features.common.diagnostics.support import (
    bind_context,
    bind_failure_cache,
    current_context,
    current_request_id,
    remember_failure,
    remembered_failure,
)
from features.common.workspace import data_dir


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = data_dir()
JOBS_PATH = DATA_DIR / "jobs.json"
JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOB_LOCK = threading.RLock()
JOBS: dict[str, dict[str, JsonValue]] = {}
FUTURES: dict[str, Future[None] | threading.Thread] = {}
_LIFECYCLES: dict[str, JobPrivateLifecycle] = {}
_DIAGNOSTICS_RUNTIME: DiagnosticsRuntime | None = None
_DIAGNOSTICS_ROOT: str | None = None
_DIAGNOSTIC_VERSION = re.compile(r"\d+(?:\.\d+){1,3}\Z")


def _clock() -> datetime:
    return datetime.now(UTC)


def _store() -> SharedJobStore:
    return SharedJobStore(JOBS_PATH.with_name("jobs-v2.json"), JOBS_PATH, clock=_clock)


def _lifecycle() -> JobPrivateLifecycle:
    root = JOBS_PATH.parent / "job-context"
    key = str(root.resolve())
    with JOB_LOCK:
        if key not in _LIFECYCLES:
            _LIFECYCLES[key] = JobPrivateLifecycle(
                root,
                clock=_clock,
                terminal_observer=_diagnostic_authority_terminal,
                cleanup_started=_diagnostic_cleanup_started,
                cleanup_finished=_diagnostic_cleanup_finished,
                cleanup_failed=_diagnostic_cleanup_failed,
            )
    return _LIFECYCLES[key]


def shared_store() -> SharedJobStore:
    return _store()


def private_lifecycle() -> JobPrivateLifecycle:
    return _lifecycle()


def data_root() -> Path:
    return JOBS_PATH.parent


def _diagnostic_app_version() -> str:
    """Read only a verified shipped VERSION; never infer a workspace value."""
    try:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise OSError("diagnostic_version_unavailable") from error
    if _DIAGNOSTIC_VERSION.fullmatch(version) is None:
        raise OSError("diagnostic_version_unavailable")
    return version


def diagnostics_runtime() -> DiagnosticsRuntime:
    """Return the one closeable observer runtime for the current jobs root."""
    global _DIAGNOSTICS_RUNTIME, _DIAGNOSTICS_ROOT
    root = str(data_root().resolve(strict=False))
    with JOB_LOCK:
        if _DIAGNOSTICS_RUNTIME is not None and _DIAGNOSTICS_ROOT != root:
            _DIAGNOSTICS_RUNTIME.close()
            _DIAGNOSTICS_RUNTIME = None
        if _DIAGNOSTICS_RUNTIME is None:
            _DIAGNOSTICS_RUNTIME = DiagnosticsRuntime(
                data_root(), app_version=_diagnostic_app_version(),
            )
            _DIAGNOSTICS_ROOT = root
        return _DIAGNOSTICS_RUNTIME


def close_diagnostics_runtime() -> None:
    global _DIAGNOSTICS_RUNTIME, _DIAGNOSTICS_ROOT
    with JOB_LOCK:
        runtime, _DIAGNOSTICS_RUNTIME = _DIAGNOSTICS_RUNTIME, None
        _DIAGNOSTICS_ROOT = None
    if runtime is not None:
        runtime.close()


def _diagnostic_submission(job: SharedJob, request_id: str | None, parent_run_id: str | None = None):
    try:
        return diagnostics_runtime().observe_submission(
            job, request_id=request_id, parent_run_id=parent_run_id,
        )
    except Exception:
        return None


def _diagnostic_worker_started(recorder) -> None:
    try:
        diagnostics_runtime().worker_started(recorder)
    except Exception:
        return


def _diagnostic_exception(recorder, error: BaseException) -> None:
    try:
        diagnostics_runtime().observe_exception(recorder, error)
    except Exception:
        return


def _diagnostic_terminal(recorder, status: str) -> None:
    try:
        diagnostics_runtime().observe_terminal(recorder, status)
    except Exception:
        return


def _diagnostic_schedule() -> None:
    try:
        diagnostics_runtime().schedule_reconcile()
    except Exception:
        return


def _diagnostic_authority_terminal(job_id: str, status: JobStatus) -> None:
    try:
        diagnostics_runtime().observe_authority_terminal(job_id, status.value)
    except Exception:
        return


def _diagnostic_cleanup_started(job_id: str) -> None:
    try:
        diagnostics_runtime().cleanup_started(job_id)
    except Exception:
        return


def _diagnostic_cleanup_finished(job_id: str) -> None:
    try:
        diagnostics_runtime().cleanup_finished(job_id)
    except Exception:
        return


def _diagnostic_cleanup_failed(job_id: str, error: PrivateCleanupError) -> None:
    try:
        diagnostics_runtime().cleanup_failed(job_id, error)
    except Exception:
        return


def current_diagnostic_recorder():
    """Best-effort access for a concrete producer inside a bound job worker."""
    context = current_context()
    if context is None:
        return None
    try:
        return diagnostics_runtime().recorder_for_context(context)
    except Exception:
        return None


@contextmanager
def _worker_diagnostic_context(context):
    """Bind both immutable context and one exception-to-failure cache."""
    with bind_context(context) if context is not None else nullcontext():
        with bind_failure_cache():
            yield


def diagnostic_stage_start(stage_code: str) -> tuple[object | None, str | None]:
    recorder = current_diagnostic_recorder()
    if recorder is None:
        return None, None
    try:
        return recorder, recorder.start_stage(stage_code)
    except Exception:
        return None, None


def diagnostic_stage_end(recorder, stage_id: str | None, stage_code: str) -> None:
    if recorder is None or stage_id is None:
        return
    try:
        recorder.end_stage(stage_id, stage_code)
    except Exception:
        return


_TIMED_STAGE_CODES = ("wait_engine", "context", "generate", "postprocess")


def stage_timing_summary(recorder) -> dict[str, int | None]:
    """Sum this run's already-measured stage durations into bounded job-facing keys.

    Reads the diagnostics record the caller already wrote to via
    ``diagnostic_stage_start``/``diagnostic_stage_end`` — it does not start a
    second clock. A stage that never ran (e.g. no CLI attempt) sums to 0,
    which is a real fact; ``None`` means the run has no diagnostics record at
    all (diagnostics unavailable), not that the stage was skipped.
    """
    keys = {"wait_engine": "queueWaitMs", "context": "contextMs", "generate": "cliMs", "postprocess": "postprocessMs"}
    if recorder is None:
        return {key: None for key in keys.values()}
    totals = dict.fromkeys(_TIMED_STAGE_CODES, 0)
    try:
        events = recorder.record.events
    except Exception:
        events = ()
    for event in events:
        if event.event_code == "end" and event.duration_ms is not None and event.stage_code in totals:
            totals[event.stage_code] += event.duration_ms
    return {keys[stage_code]: total for stage_code, total in totals.items()}


def diagnostic_resume(stage_code: str = "context") -> None:
    """Record only a concrete producer's consumption of a saved checkpoint."""
    recorder, stage_id = diagnostic_stage_start(stage_code)
    if recorder is None or stage_id is None:
        return
    try:
        recorder.event(stage_id=stage_id, stage_code=stage_code, event_code="resume")
    except Exception:
        return
    finally:
        diagnostic_stage_end(recorder, stage_id, stage_code)


@contextmanager
def diagnostic_stage(stage_code: str, *, boundary: str = "generic"):
    """Best-effort real boundary span that always closes on a local catch."""
    recorder, stage_id = diagnostic_stage_start(stage_code)
    try:
        yield recorder, stage_id
    except BaseException as error:
        diagnostic_stage_failure(
            recorder, error, stage_id=stage_id,
            stage_code=stage_code if stage_id is not None else None,
            boundary=boundary,
        )
        raise
    finally:
        diagnostic_stage_end(recorder, stage_id, stage_code)


_DIAGNOSTIC_AUXILIARY_EXECUTION: ContextVar[bool] = ContextVar(
    "folio_diagnostic_auxiliary_execution", default=False,
)


@contextmanager
def diagnostic_auxiliary_execution():
    """Keep a nested engine helper from claiming its caller's outcome."""
    token = _DIAGNOSTIC_AUXILIARY_EXECUTION.set(True)
    try:
        yield
    finally:
        _DIAGNOSTIC_AUXILIARY_EXECUTION.reset(token)


def diagnostic_execution(
    *,
    attempted_engine: str | None = None,
    final_engine: str | None = None,
    adapter: str | None = None,
    fallback_reason: str | None = None,
    primary: bool = True,
) -> None:
    """Persist execution facts only for the owning producer operation.

    Auxiliary lookup/quality calls may use an engine inside the same frozen
    context, but they are not the report's execution outcome.  They still
    emit their own stages and failures; ``primary=False`` merely prevents
    their call order from claiming the report's engine fields.
    """
    if not primary or _DIAGNOSTIC_AUXILIARY_EXECUTION.get():
        return
    recorder = current_diagnostic_recorder()
    if recorder is None:
        return
    try:
        recorder.observe_execution(
            attempted_engine=attempted_engine,
            final_engine=final_engine,
            adapter=adapter,
            fallback_reason=fallback_reason,
        )
    except Exception:
        return


def diagnostic_prove_complete_coverage() -> None:
    """Allow only a concrete audited producer to attest its live boundary."""
    recorder = current_diagnostic_recorder()
    if recorder is None:
        return
    try:
        recorder.prove_complete_coverage()
    except Exception:
        return


def diagnostic_stage_failure(recorder, error: BaseException, *, stage_id: str | None, stage_code: str | None, boundary: str, terminal: bool = False) -> None:
    if recorder is None:
        return
    try:
        failure = remembered_failure(error)
        if failure is None:
            failure = safe_exception_failure(
                error,
                stage_id=stage_id,
                stage_code=stage_code,
                boundary=boundary,
                frames=_trusted_frame(error),
            )
        error_id = recorder.failure(failure, terminal=terminal)
        if error_id is not None:
            stored = next((item for item in recorder.record.errors if item.error_id == error_id), None)
            if stored is not None:
                remember_failure(error, stored)
    except Exception:
        return


def start_direct_diagnostic(*, feature_code: str, route_code: str, authority_kind: str, parent_run_id: str | None = None):
    """Open a best-effort non-SharedJob observation at a real producer edge."""
    try:
        runtime = diagnostics_runtime()
        context = new_context(
            feature_code=feature_code,
            route_code=route_code,
            authority_kind=authority_kind,
            parent_run_id=parent_run_id,
            request_id=current_request_id(),
            app_version=runtime.app_version,
        )
        return runtime.start_direct(context)
    except Exception:
        return None


def finish_direct_diagnostic(recorder, observed_status: str) -> None:
    if recorder is None:
        return
    try:
        diagnostics_runtime().finish_direct(recorder, observed_status)
    except Exception:
        return


def finish_direct_diagnostic_run(run_id: str, observed_status: str) -> None:
    try:
        diagnostics_runtime().finish_direct_run(run_id, observed_status)
    except Exception:
        return


@contextmanager
def bound_direct_diagnostic(
    *,
    feature_code: str,
    route_code: str,
    authority_kind: str = "direct",
    parent_run_id: str | None = None,
):
    """Bind an optional direct recorder around one concrete producer route."""
    recorder = start_direct_diagnostic(
        feature_code=feature_code,
        route_code=route_code,
        authority_kind=authority_kind,
        parent_run_id=parent_run_id,
    )
    context = recorder.context if recorder is not None else None
    with bind_context(context) if context is not None else nullcontext():
        # Direct API boundaries may catch/rethrow through several feature
        # helpers.  Keep their first concrete Failure identity run-local,
        # exactly as a SharedJob worker does.
        with bind_failure_cache():
            try:
                yield recorder
            except Exception as error:
                # Preserve a feature's already-recorded concrete failure;
                # otherwise capture only a safe generic terminal before the
                # HTTP exception boundary sees the rethrow.
                diagnostic_stage_failure(
                    recorder,
                    error,
                    stage_id=None,
                    stage_code=None,
                    boundary="generic",
                    terminal=True,
                )
                finish_direct_diagnostic(recorder, "failed")
                raise


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


def _recover_deep_candidates_safe(store, lifecycle) -> None:
    try:
        from features.topic_report.candidate_recovery import recover_deep_candidates_startup

        recover_deep_candidates_startup(JOBS_PATH.parent, store, lifecycle, clock=_clock)
    except Exception:  # noqa: BLE001 - 백신 잠금·스키마 드리프트가 서버 기동을 막으면 안 된다
        pass


def load_jobs() -> None:
    store = _store()
    lifecycle = _lifecycle()
    # Recovery observation is strictly post-authority: only records that were
    # nonterminal before this startup pass and terminal after it are eligible.
    try:
        pre_recovery_active = {
            job.id for job in store.load().jobs
            if job.status not in {
                JobStatus.DONE, JobStatus.CANCELLED, JobStatus.FAILED,
                JobStatus.FAILED_CANCEL, JobStatus.FAILED_COMMIT,
                JobStatus.FAILED_RESTART, JobStatus.FAILED_COMMIT_RECOVERY,
            }
        }
    except Exception:
        pre_recovery_active = set()
    steps: tuple[Callable[[], None], ...] = (
        lambda: recover_json_jobs_startup(JOBS_PATH.parent, store, lifecycle, clock=_clock),
        lambda: _recover_sql_jobs_startup(store, lifecycle),
        # 이 단계는 어떤 예외에도 기동을 막지 않는다 — 체크포인트 복구는 부가 기능이고,
        # 실패해도 아래 lifecycle.recover_startup()이 해당 잡을 failed_restart로 정리한다.
        lambda: _recover_deep_candidates_safe(store, lifecycle),
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
    terminal_statuses = {
        JobStatus.DONE, JobStatus.CANCELLED, JobStatus.FAILED,
        JobStatus.FAILED_CANCEL, JobStatus.FAILED_COMMIT,
        JobStatus.FAILED_RESTART, JobStatus.FAILED_COMMIT_RECOVERY,
    }
    recovered_jobs: tuple[SharedJob, ...] = ()
    try:
        recovered_jobs = store.load().jobs
    except Exception:
        recovered_jobs = ()
    if pre_recovery_active:
        try:
            for job in recovered_jobs:
                if job.id in pre_recovery_active and job.status in terminal_statuses:
                    diagnostics_runtime().observe_recovery(job)
        except Exception:
            # Diagnostics is an observer; repair authority must never depend on
            # a diagnostic filesystem or schema being available.
            pass
    # A process can instead die in the narrow gap after an already-terminal
    # SharedJob persisted and before its observer terminal write.  This is a
    # diagnostic-only, post-authority pass: runtime scans validated unfinished
    # headers and resumes only those that still match this current terminal
    # authority.  It never changes jobs, private cleanup, or recovery policy.
    try:
        runtime = diagnostics_runtime()
        for job in recovered_jobs:
            if job.id not in pre_recovery_active and job.status in terminal_statuses:
                runtime.observe_existing_terminal_authority(job)
    except Exception:
        pass
    _diagnostic_schedule()
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


_PHASE_CODES = {"context", "wait_engine", "generate", "postprocess", "commit"}
_TIMING_KEYS = ("queueWaitMs", "contextMs", "cliMs", "postprocessMs", "totalMs")


def job_progress(job_id: str):
    def _progress(_message=None, progress=None, **extra) -> None:
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
        if "phaseCode" in extra:
            phase = extra["phaseCode"]
            if phase is None or (isinstance(phase, str) and phase in _PHASE_CODES):
                changes["phaseCode"] = phase
        for key in _TIMING_KEYS:
            if key not in extra:
                continue
            value = extra[key]
            if value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
                changes[key] = value
        if changes:
            _store().update_runtime(job_id, changes)
            _refresh_cache()

    return _progress


def compact_job_result(result):
    return worker_projection(result)


def _dump_job_traceback(job_id: str, error: BaseException) -> None:
    """Write one job traceback to a local file when asked.

    아래 broad catch가 모든 예외를 INTERNAL_ERROR 하나로 뭉갠다.  진단 기록은
    개인정보 때문에 메시지를 담지 않으므로, 실패한 잡의 원인을 되짚을 방법이
    코드 위치 하나뿐이었다 — 실제로 밤새 같은 실패를 추측만 하게 만들었다.
    `FOLIO_JOB_ERROR_DUMP_DIR`(없으면 `BRIEFING_REJECTION_DUMP_DIR`)을 설정한
    실행에서만 쓰고, 진단이 종료 처리를 막지 않도록 실패는 삼킨다.
    """
    import os

    target = str(os.environ.get("FOLIO_JOB_ERROR_DUMP_DIR")
                 or os.environ.get("BRIEFING_REJECTION_DUMP_DIR") or "").strip()
    if not target:
        return
    try:
        import traceback
        from datetime import datetime
        from pathlib import Path

        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        (directory / f"error-{job_id}-{stamp}.txt").write_text(text, encoding="utf-8")
    except Exception:
        return


def run_job(job_id: str, fn, *args, **kwargs) -> None:
    store = _store()
    recorder = kwargs.pop("_diagnostic_recorder", None)
    context = recorder.context if recorder is not None else None
    # Keep the exception-to-failure cache through the historical outer catch:
    # a producer's concrete stage failure and the terminal job failure must
    # refer to the same stored error rather than manufacture a generic second.
    with _worker_diagnostic_context(context):
        try:
            store.transition(job_id, JobStatus.RUNNING)
            _diagnostic_worker_started(recorder)
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
        except PrivateCleanupError:
            # The private lifecycle has already recorded its typed cleanup fact
            # and intentionally left authority fail-closed (the existing 503
            # contract).
            return
        except Exception as error:  # noqa: BROAD_EXCEPT_OK
            # Capture a typed, message-free fact before this historical broad
            # catch maps every error to INTERNAL_ERROR.
            _diagnostic_exception(recorder, error)
            _dump_job_traceback(job_id, error)
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
            current = store.get(job_id)
            if current is not None and current.status in {
                JobStatus.DONE,
                JobStatus.CANCELLED,
                JobStatus.FAILED,
                JobStatus.FAILED_CANCEL,
                JobStatus.FAILED_COMMIT,
                JobStatus.FAILED_RESTART,
                JobStatus.FAILED_COMMIT_RECOVERY,
            }:
                # Terminal diagnostics follows the existing private cleanup and
                # authoritative job write; it is never the proof for either.
                _diagnostic_terminal(recorder, current.status.value)
            _refresh_cache()


def submit_job(kind, _label, fn, *args, pass_job_id=False, executor=None, dedicated_thread=False, diagnostic_request_id=None, **kwargs):
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
    bound_context = current_context()
    recorder = _diagnostic_submission(
        job,
        diagnostic_request_id or current_request_id(),
        bound_context.run_id if bound_context is not None else None,
    )
    if pass_job_id:
        kwargs["_folio_job_id"] = job.id
    if recorder is not None:
        kwargs["_diagnostic_recorder"] = recorder
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


def diagnostic_job_lookup(job_id: str) -> dict[str, JsonValue] | None:
    """Feature-owned read that retains the existing private-cleanup 503 guard."""
    return get_job(job_id)


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
