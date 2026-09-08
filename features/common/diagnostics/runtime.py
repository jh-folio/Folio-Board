"""Owned runtime bridge for bounded diagnostics observers.

The bridge is deliberately small: it owns one store for the currently active
jobs data root, passes a frozen context into workers, and performs bounded
reconciliation outside request/worker paths.  It never changes job authority.
"""
from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from . import schema as diagnostics_schema
from .authority import default_authority_snapshot
from .record import DiagnosticRecorder
from .retention import DiagnosticsRetentionService
from .schema import DiagnosticContext, SafeFrame, safe_exception_failure, new_context
from .store import DiagnosticsStore, MAX_RUN_FILES, SCAN_ENTRY_LIMIT
from .support import remembered_failure

if TYPE_CHECKING:
    from features.common.shared_jobs_schema import SharedJob


_SOURCE_REGISTRY = frozenset({
    ("features.common.change_intelligence.service", "decorate_candidate"),
    ("features.common.change_intelligence.semantic", "evaluate_semantic_changes"),
    ("features.llm_settings.client", "selected_llm_config"),
    ("features.llm_settings.client", "configured_global_reasoning_effort"),
    ("features.agent_mode.job_runtime", "commit_json_output"),
    ("features.agent_mode.job_runtime", "_prepare_rules_briefing_fallback"),
    ("features.agent_mode.service", "write_briefing_from_markdown"),
    ("features.agent_mode.service", "build_rules_briefing_markdown_from_pack"),
    ("features.common.job_json_producers", "stage_briefing"),
    ("features.common.job_briefing_producer", "briefing_specs"),
    ("features.daily_briefing.finalize", "finalize_briefing_candidate"),
    ("features.common.quality_generation.call_budget", "check_active"),
    ("features.common.jobs", "run_job"),
    ("features.common.shared_jobs_private", "_persist_terminal"),
    ("features.common.shared_jobs_private", "recover_startup"),
    ("features.agent_mode.bridge", "_run_agent_task_locked"),
    ("features.agent_mode.bridge", "run_agent_prompt"),
    ("features.agent_mode.bridge", "_invoke_agent_cli"),
    ("features.agent_mode.bridge", "run_market_memory_update_task"),
    ("features.common.job_json_commit", "commit"),
    ("features.common.sql_job_lifecycle", "complete"),
    ("features.common.sql_job_lifecycle", "fail_commit"),
    ("features.common.sql_job_lifecycle", "fail_run"),
    ("features.company_analysis.direct_observer", "run_direct_analysis"),
    ("features.company_analysis.generation_context", "_build_generation_inputs"),
    ("features.company_analysis.generation_service", "analyze_company"),
    ("features.company_analysis.service", "generate_llm_company_analysis"),
    ("features.daily_briefing.direct_observer", "run_direct_briefings"),
    ("features.daily_briefing.builder", "generate_scope_results"),
    ("features.daily_briefing.builder", "build_briefing"),
    ("features.daily_briefing.service", "generate_llm_briefing"),
    ("features.automation.service", "_run_briefing_rss_prerequisite"),
    ("features.automation.service", "run_automation_once"),
    ("features.common.research_library.indexing.service", "build_index"),
    ("features.common.research_library.rss.service", "_import_rssarchive_locked"),
    ("features.topic_report.approved_jobs", "_run"),
    ("features.topic_report.approved_generation", "build_approved_report"),
    ("features.topic_report.approved_generation_support", "attempt_direct"),
    ("features.topic_report.deep_pipeline", "run_deep_pipeline"),
    ("features.agent_mode.job_runtime", "run_consultation_job"),
    ("features.agent_mode.chat", "run_agent_chat"),
    ("features.thesis_tracking.service", "run_thesis_delta"),
    ("features.thesis_tracking.direct_observer", "run_direct_thesis_delta"),
    ("features.investment_review.service", "build_review"),
    ("features.investment_review.direct_observer", "run_direct_review"),
    ("features.personal_overlay.service", "attach_overlay_to_briefing"),
    ("features.personal_overlay.service", "attach_overlay_to_report"),
    ("features.personal_overlay.direct_observer", "run_direct_overlay"),
    ("features.personal_overlay.service", "generate_overlay"),
    ("features.thesis_tracking.delta", "generate_delta"),
    ("features.topic_report.service", "attach_overlay_to_topic_report"),
    ("features.market_memory.direct_observer", "run_direct_market_memory"),
    ("features.market_memory.service", "run_llm_market_memory"),
    ("features.market_memory.service", "finalize_role_classification"),
    ("features.market_memory.evidence_roles", "safe_build_role_candidates"),
    ("features.market_memory.evidence_roles", "classify_role_payload"),
    ("features.market_memory.evidence_roles", "_safe_remaining_primary"),
})

# SharedJob task types are an existing closed authority enum.  This mapping is
# deliberately local/static: producers never supply a feature or route string.
_JOB_CONTEXT_CODES: dict[str, tuple[str, str]] = {
    "index": ("index", "index_build"),
    "rss": ("rss", "rss_collect"),
    "companion": ("agent_chat", "chat_cli"),
    "briefing": ("briefing", "report_cli"),
    "company_analysis": ("company_analysis", "report_cli"),
    "topic_report": ("topic_report", "topic_approved"),
    "personal_overlay": ("personal_judgment", "judgment_json"),
    "thesis_delta": ("personal_judgment", "judgment_sql"),
    "market_memory_llm": ("personal_judgment", "judgment_sql"),
    "market_state_snapshot": ("personal_judgment", "judgment_sql"),
    "market_memory_update": ("personal_judgment", "judgment_sql"),
    "investment_review": ("personal_judgment", "judgment_json"),
}

def _trusted_frame(error: BaseException) -> tuple[SafeFrame, ...]:
    """Extract one allow-listed code-location fact without retaining a traceback."""
    root = Path(__file__).resolve().parents[3]
    trace = error.__traceback__
    location = ()
    while trace is not None:
        code = trace.tb_frame.f_code
        for module_code, function_code in _SOURCE_REGISTRY:
            if code.co_name != function_code:
                continue
            try:
                expected = (root / (module_code.replace(".", "/") + ".py")).resolve(strict=True)
                if Path(code.co_filename).resolve(strict=True) == expected:
                    location = (SafeFrame(module_code, function_code, trace.tb_lineno),)
                    break
            except OSError:
                continue
        trace = trace.tb_next
    return location


class DiagnosticsRuntime:
    """One bounded, closeable observer runtime for one authoritative root."""

    def __init__(self, data_root: Path, *, app_version: str = "0.0.0") -> None:
        self.data_root = Path(data_root)
        # Production injects the verified package VERSION.  The conservative
        # default keeps this small core usable by isolated store tests only.
        self.app_version = app_version
        self.store = DiagnosticsStore(self.data_root, source_registry=_SOURCE_REGISTRY)
        # Retention has no worker of its own.  The existing terminal observer
        # invokes this bounded, best-effort hook; default settings keep it
        # disabled and the missing authority provider fail-closes job-linked
        # records.
        self.retention_service = DiagnosticsRetentionService(
            self.store,
            authority_provider=default_authority_snapshot,
        )
        self._closed = False
        self._recorders: dict[str, DiagnosticRecorder] = {}
        self._direct_recorders: dict[str, DiagnosticRecorder] = {}
        self._failed_direct_requests: dict[str, str] = {}
        self._direct_lock = threading.Lock()
        self._cleanup_stages: dict[str, str] = {}
        # A startup authority repair can happen while the cold quota pass is
        # incomplete.  Retain only its frozen safe identity/status so a
        # background slice can observe the already-completed authority later.
        self._pending_recoveries: dict[str, tuple[DiagnosticContext, str]] = {}
        self._pending_terminal_authority: dict[str, tuple[DiagnosticContext, str]] = {}
        self._pending_recovery_lock = threading.Lock()
        self._reconcile_lock = threading.Lock()
        self._reconcile_thread: threading.Thread | None = None
        self._reconcile_requested = False
        self._reconcile_retiring = False

    def context_for_job(self, job: "SharedJob", *, request_id: str | None = None, parent_run_id: str | None = None) -> DiagnosticContext:
        feature_code, route_code = _JOB_CONTEXT_CODES.get(
            job.taskType.value, ("jobs", "shared_worker"),
        )
        return new_context(
            feature_code=feature_code,
            route_code=route_code,
            authority_kind="shared_job",
            task_type=job.taskType.value,
            job_id=job.id,
            request_id=request_id,
            parent_run_id=parent_run_id,
            app_version=self.app_version,
        )

    def recorder_for_context(self, context: DiagnosticContext | None) -> DiagnosticRecorder | None:
        """Return only the live recorder explicitly bound into this worker."""
        if context is None:
            return None
        if context.job_id is None:
            recorder = self._direct_recorders.get(context.run_id)
            return recorder if recorder is not None and recorder.context == context else None
        recorder = self._recorders.get(context.job_id)
        return recorder if recorder is not None and recorder.context.run_id == context.run_id else None

    def start_direct(self, context: DiagnosticContext) -> DiagnosticRecorder | None:
        if self._closed:
            return None
        recorder = self.store.start(context)
        if recorder is None:
            self.schedule_reconcile()
            return None
        with self._direct_lock:
            self._direct_recorders[context.run_id] = recorder
        return recorder

    def finish_direct(self, recorder: DiagnosticRecorder | None, observed_status: str) -> None:
        if recorder is None or recorder.record.finished_at is not None:
            return
        recorder.finish(observed_status, terminal_failure=recorder.record.terminal_failure)
        if recorder.record.finished_at is not None:
            with self._direct_lock:
                self._direct_recorders.pop(recorder.context.run_id, None)
                request_id = recorder.context.request_id
                if request_id is not None and recorder.record.terminal_failure is not None:
                    self._failed_direct_requests[request_id] = recorder.context.run_id
                    while len(self._failed_direct_requests) > 128:
                        self._failed_direct_requests.pop(next(iter(self._failed_direct_requests)))
            self.schedule_reconcile()

    def finish_direct_run(self, run_id: str, observed_status: str) -> None:
        with self._direct_lock:
            recorder = self._direct_recorders.get(run_id)
        if recorder is not None:
            self.finish_direct(recorder, observed_status)
            return
        # Automation authority can outlive this observer process.  Resume
        # only a persisted, unfinished direct record across a new epoch; never
        # reopen an already-terminal run or mutate the authority row.
        try:
            result = self.store.read(run_id)
            if result.record is None or result.record.finished_at is not None:
                return
            # ``resume`` requires the caller's current epoch to differ from
            # the stored one, then preserves the stored run epoch internally.
            # Both supplied recovery facts therefore use this real process,
            # never a synthetic per-call UUID.
            recovery_context = replace(
                result.record.context,
                process_epoch=diagnostics_schema.PROCESS_EPOCH,
                producer_epoch=diagnostics_schema.PROCESS_EPOCH,
            )
            recorder = self.store.resume(recovery_context, observed_status=observed_status)
            if recorder is None and self._queue_pending_terminal(recovery_context, observed_status):
                # Cold accounting deliberately rejects resume until its whole
                # bounded pass is validated. Keep this already-authoritative
                # terminal observation for the owned background drain rather
                # than losing it after the automation row is terminal.
                self.schedule_reconcile()
        except Exception:
            return

    def observe_submission(self, job: "SharedJob", *, request_id: str | None = None, parent_run_id: str | None = None) -> DiagnosticRecorder | None:
        if self._closed:
            return None
        # ``SharedJobStore.add`` is already authoritative at this point.  The
        # initial record must say queued until the worker's real transition.
        recorder = self.store.start(
            self.context_for_job(job, request_id=request_id, parent_run_id=parent_run_id),
            observed_status=job.status.value,
        )
        if recorder is None:
            self.schedule_reconcile()
            return None
        # Queued is an authority fact established only after SharedJobStore.add.
        recorder.start_stage("queued")
        self._recorders[job.id] = recorder
        return recorder

    def worker_started(self, recorder: DiagnosticRecorder | None) -> None:
        if recorder is None:
            return
        # jobs.run_job invokes this strictly after SharedJobStore.transition
        # succeeded; do not infer running from executor submission/progress.
        recorder.observe_authority_status("running")
        for event in recorder.record.events:
            if event.stage_code == "queued" and event.event_code == "start":
                recorder.end_stage(event.stage_id, "queued")
                break

    def observe_exception(self, recorder: DiagnosticRecorder | None, error: BaseException) -> None:
        if recorder is None:
            return
        # Generic worker boundary has no permission to infer a save/adapter
        # cause.  This intentionally ignores text, args, traceback and attrs.
        # A concrete producer may already have captured this exact exception
        # at an owned stage.  Reuse its sanitized stored failure so terminal
        # observation does not overwrite the real cause with a generic one.
        failure = remembered_failure(error)
        if failure is None:
            failure = safe_exception_failure(error, boundary="generic", frames=_trusted_frame(error))
        recorder.failure(failure, terminal=True)

    def observe_terminal(self, recorder: DiagnosticRecorder | None, status: str) -> None:
        if recorder is None:
            return
        if recorder.record.finished_at is not None:
            return
        recorder.finish(
            status,
            terminal_failure=recorder.record.terminal_failure,
            coverage_complete=recorder.complete_coverage_proven,
        )
        if recorder.record.finished_at is not None:
            self._recorders.pop(recorder.context.job_id or "", None)
            self._cleanup_stages.pop(recorder.context.job_id or "", None)
            self.schedule_reconcile()

    def observe_authority_terminal(self, job_id: str, status: str) -> None:
        """Private lifecycle callback after its cleanup + terminal write."""
        self.observe_terminal(self._recorders.get(job_id), status)

    def cleanup_started(self, job_id: str) -> None:
        recorder = self._recorders.get(job_id)
        if recorder is None or job_id in self._cleanup_stages:
            return
        stage_id = recorder.start_stage("cleanup")
        if stage_id is not None:
            self._cleanup_stages[job_id] = stage_id

    def cleanup_finished(self, job_id: str) -> None:
        recorder = self._recorders.get(job_id)
        stage_id = self._cleanup_stages.pop(job_id, None)
        if recorder is not None and stage_id is not None:
            recorder.end_stage(stage_id, "cleanup")

    def cleanup_failed(self, job_id: str, error: BaseException) -> None:
        recorder = self._recorders.get(job_id)
        if recorder is None:
            return
        stage_id = self._cleanup_stages.get(job_id)
        recorder.failure(
            safe_exception_failure(
                error,
                stage_id=stage_id,
                stage_code="cleanup" if stage_id is not None else None,
                boundary="cleanup",
            ),
            terminal=True,
        )

    def observe_unhandled_http(self, request_id: str, error: BaseException) -> str | None:
        """Best-effort direct run for an actual unhandled 500 only."""
        if self._closed:
            return None
        # Feature-owned direct code may have recorded the concrete boundary
        # before FastAPI converts the rethrow into a generic 500.  Reuse that
        # run instead of manufacturing a second HTTP-only diagnosis.
        with self._direct_lock:
            existing = self._failed_direct_requests.pop(request_id, None)
        if existing is not None:
            return existing
        context = new_context(
            feature_code="http",
            route_code="http_unhandled",
            authority_kind="direct",
            request_id=request_id,
            app_version=self.app_version,
        )
        recorder = self.store.start(context)
        if recorder is None:
            self.schedule_reconcile()
            return None
        recorder.failure(safe_exception_failure(error, boundary="generic", frames=_trusted_frame(error)), terminal=True)
        recorder.finish("failed", terminal_failure=recorder.record.terminal_failure)
        return context.run_id

    def observe_recovery(self, job: "SharedJob") -> None:
        """Best-effort terminal observation after existing startup authority."""
        if self._closed:
            return
        context = self.context_for_job(job)
        recorder = self.store.resume(context, observed_status=job.status.value)
        if recorder is None:
            # Queue before the next slice: it may be the final cold-scan slice
            # and immediately report ``complete``.  This contains frozen
            # identity/status only, is capped by the record-file limit, and is
            # drained once rather than becoming an observer retry loop.
            if not self._queue_pending_recovery(context, job.status.value):
                return
            try:
                state = self.store.reconcile_step()
                if state == "complete":
                    self._drain_pending_recoveries()
                elif state == "pending":
                    self.schedule_reconcile()
            except Exception:
                # Diagnostics never makes startup authority recovery fail.
                self._discard_pending_recovery(context.run_id)
                return

    def _queue_pending_recovery(self, context: DiagnosticContext, observed_status: str) -> bool:
        with self._pending_recovery_lock:
            self._pending_terminal_authority.pop(context.run_id, None)
            if context.run_id in self._pending_recoveries:
                self._pending_recoveries[context.run_id] = (context, observed_status)
                return True
            if len(self._pending_recoveries) + len(self._pending_terminal_authority) >= MAX_RUN_FILES:
                try:
                    self.store.note_warning("recovery_gap", context.run_id)
                except Exception:
                    pass
                return False
            self._pending_recoveries[context.run_id] = (context, observed_status)
            return True

    def observe_existing_terminal_authority(self, job: "SharedJob") -> None:
        """Close a pre-existing unfinished diagnostic after authority startup.

        A process may die after SharedJob terminal persistence but before its
        observer's terminal atomic write.  This receives a *current already
        terminal* authority row after normal recovery, retains no authority
        object, and waits for a complete bounded header scan before attempting
        the diagnostic-only cross-epoch recovery.
        """
        if self._closed or not self.store.root.exists():
            return
        context = self.context_for_job(job)
        if self._queue_pending_terminal(context, job.status.value):
            self.schedule_reconcile()

    def _queue_pending_terminal(self, context: DiagnosticContext, observed_status: str) -> bool:
        """Retain one terminal observation until a validated header scan."""
        with self._pending_recovery_lock:
            if context.run_id in self._pending_recoveries:
                return False
            if context.run_id in self._pending_terminal_authority:
                self._pending_terminal_authority[context.run_id] = (context, observed_status)
                return True
            if len(self._pending_recoveries) + len(self._pending_terminal_authority) >= MAX_RUN_FILES:
                try:
                    self.store.note_warning("recovery_gap", context.run_id)
                except Exception:
                    pass
                return False
            self._pending_terminal_authority[context.run_id] = (context, observed_status)
            return True

    def _discard_pending_recovery(self, run_id: str) -> None:
        with self._pending_recovery_lock:
            self._pending_recoveries.pop(run_id, None)

    def _drain_pending_recoveries(self) -> None:
        """Attempt each cold-scan-delayed observation once after readiness."""
        with self._pending_recovery_lock:
            pending, self._pending_recoveries = self._pending_recoveries, {}
        for context, observed_status in pending.values():
            if self._closed:
                return
            try:
                self.store.resume(context, observed_status=observed_status)
            except Exception:
                # The captured authority remains authoritative; an observer
                # I/O fault must not turn this into an unbounded retry loop.
                continue

    def _drain_pending_terminal_authority(self) -> None:
        """Recover only scanned unfinished records that match current authority."""
        try:
            unfinished = frozenset(self.store.unfinished_run_ids())
        except Exception:
            return
        with self._pending_recovery_lock:
            pending, self._pending_terminal_authority = self._pending_terminal_authority, {}
        for run_id, (context, observed_status) in pending.items():
            if self._closed:
                return
            if run_id not in unfinished:
                continue
            try:
                self.store.resume(context, observed_status=observed_status)
            except Exception:
                continue

    def schedule_reconcile(self) -> None:
        """Drive the finite 5000-entry pass outside a request/worker path."""
        if self._closed or not self.store.root.exists():
            return
        with self._reconcile_lock:
            # This dirty bit is the handoff between a caller and an owned
            # worker that may be draining its final map right now.
            self._reconcile_requested = True
            if (
                self._reconcile_thread is not None
                and self._reconcile_thread.is_alive()
                and not self._reconcile_retiring
            ):
                return
            # A retiring worker has already finished its last store operation.
            # Replacing its reference before it returns is safe and prevents a
            # caller from attaching new work to an exiting daemon.
            self._reconcile_retiring = False
            self._reconcile_thread = threading.Thread(
                target=self._reconcile_pending,
                name="folio-diagnostics-reconcile",
                daemon=True,
            )
            self._reconcile_thread.start()

    def _reconcile_pending(self) -> None:
        # A pass itself is capped at 5000 filesystem entries.  This worker
        # advances that finite pass even when no subsequent user job arrives;
        # blocked corruption/lease states stop rather than retry-spinning.
        try:
            while not self._closed:
                # Consume all requests known before this bounded pass.  A
                # request arriving during drain sets it again and forces one
                # more pass before this thread can retire.
                with self._reconcile_lock:
                    self._reconcile_requested = False
                state = "blocked"
                for _ in range(SCAN_ENTRY_LIMIT):
                    if self._closed:
                        return
                    state = self.store.reconcile_step()
                    if state == "complete":
                        self._drain_pending_recoveries()
                        self._drain_pending_terminal_authority()
                        # Retention runs on this existing bounded lifecycle
                        # worker, after the observer has released any job
                        # authority locks.  It creates no scheduler/thread of
                        # its own and remains disabled by default.
                        try:
                            self.retention_service.run_automatic()
                        except Exception:
                            pass
                        break
                    if state != "pending":
                        break
                    time.sleep(0.01)
                if state != "complete":
                    # A blocked/faulted accounting pass remains truthful and
                    # waits for a future lifecycle request; never retry-spin.
                    return
                with self._reconcile_lock:
                    if self._reconcile_requested and not self._closed:
                        continue
                    # Retire under the same lock used by schedule_reconcile.
                    # A racing caller therefore starts a new worker rather
                    # than attaching its request to a thread that is exiting.
                    if self._reconcile_thread is threading.current_thread():
                        self._reconcile_retiring = True
                    return
        except Exception:
            # A daemon exception would otherwise reach threading's default
            # hook, exposing a filesystem/provider message in stderr.  There
            # may be no associated run (ordinary cold reconciliation), so a
            # code-only warning is emitted only for a retained safe context.
            with self._pending_recovery_lock:
                pending = next(
                    iter((*self._pending_recoveries.values(), *self._pending_terminal_authority.values())),
                    None,
                )
            if pending is not None:
                try:
                    self.store.note_warning("read_failed", pending[0].run_id)
                except Exception:
                    pass
            return

    def close(self) -> None:
        self._closed = True
        thread = self._reconcile_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        self.store.close()
        self._recorders.clear()
        with self._direct_lock:
            self._direct_recorders.clear()
            self._failed_direct_requests.clear()
        self._cleanup_stages.clear()
        with self._pending_recovery_lock:
            self._pending_recoveries.clear()
            self._pending_terminal_authority.clear()
