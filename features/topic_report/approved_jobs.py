from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import assert_never

from features.common import jobs as common_jobs
from features.common.jcs import JsonValue
from features.common.job_json_producer_types import ReportJobRequest
from features.common.job_json_producers import JobJsonProducers
from features.common.shared_jobs_compat import compatibility_job
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import (
    Engine,
    ErrorCode,
    FallbackReason,
    JobKind,
    JobStatus,
    RequestedMode,
    SharedJob,
)
from features.common.shared_jobs_store import SharedJobStore
from features.common.diagnostics.support import bind_context, bind_failure_cache, current_context, current_request_id
from features.topic_report.approval_store import ApprovalProof, ApprovalStore
from features.topic_report.approval_submission import (
    JobMetadata,
    SubmissionCoordinator,
    SubmissionJobs,
    SubmissionJournal,
    SubmissionRequest,
)
from features.topic_report.approved_generation import ApprovedGenerationInput, build_approved_report
from features.topic_report.approved_generation import resume_root
from features.topic_report.resume_store import ResumeStore, prune as prune_resume, resume_key
from features.topic_report.deep_pipeline import DeepResearchGenerationError, run_deep_pipeline
from features.common.quality_generation.candidate_store import CandidateStore
from features.topic_report.service import _stable_topic_id
from features.llm_settings.task_runtime import bind_task_policy


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="folio-approved-topic")


@dataclass(frozen=True, slots=True)
class SubmittedApprovedJob:
    job: SharedJob
    created: bool


class SharedSubmissionJobs(SubmissionJobs):
    def __init__(
        self,
        data_dir: Path,
        store: SharedJobStore,
        queued_job: SharedJob | None = None,
        metadata: JobMetadata | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._store = store
        self._queued_job = queued_job
        self._metadata = metadata

    def write_queued(self, metadata: JobMetadata) -> None:
        if self._queued_job is None or self._metadata != metadata:
            raise ValueError("queued_job_metadata_mismatch")
        self._store.add(self._queued_job)

    def _journal_metadata(self, job_id: str) -> JobMetadata | None:
        directory = self._data_dir / "topic-plan-submissions"
        for path in sorted(directory.glob("*.json")) if directory.exists() else []:
            try:
                journal = SubmissionJournal.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue
            if journal.jobId == job_id:
                return JobMetadata(
                    id=journal.jobId,
                    approvalId=journal.approvalId,
                    planHash=journal.planHash,
                )
        return None

    def read(self, job_id: str) -> JobMetadata | None:
        if self._store.get(job_id) is None:
            return None
        if self._metadata is not None:
            return JobMetadata(
                id=job_id,
                approvalId=self._metadata.approvalId,
                planHash=self._metadata.planHash,
            )
        return self._journal_metadata(job_id)


def _clear_resume(command: ApprovedGenerationInput) -> None:
    """성공한 실행의 재개 파일 제거. 실패해도 잡을 죽이지 않는다(유효기간이 받는다)."""
    approved = getattr(command, "approved", None)
    if approved is None or not getattr(approved, "deepResearch", False):
        return
    try:
        key = resume_key(approved.asOfDate, approved.planHash)
        if key:
            ResumeStore(resume_root(), key=key, fingerprint="-").clear()
        prune_resume(resume_root())
    except Exception:  # noqa: BLE001 - 정리 실패가 저장을 되돌리지 않는다
        return


def _failure_detail(exc: BaseException) -> str:
    """무엇을 어겼는지 코드로만. 본문은 담지 않는다."""
    if not isinstance(exc, DeepResearchGenerationError):
        return ""
    codes = [code for code in getattr(exc, "defects", []) if code]
    return (f"{exc}: " + ",".join(codes))[:200] if codes else str(exc)[:200]


def _failure_code(exc: BaseException) -> ErrorCode:
    """실패 원인을 잡 상태로 드러낸다.

    실패 결과는 `FailedProjection`(status/errorCode) 고정 계약이라 자유 필드를 실을 수
    없다. 그래서 원인은 ErrorCode로 말해야 한다 — 딥 파이프라인이 산출물을 계약 위반으로
    되돌린 것(`deep_initial_candidate_invalid` 등)과 진짜 내부 오류를 `internal_error`
    하나로 뭉뚱그리면, 사용자는 CLI를 몇 분 돌리고도 무엇이 문제인지 알 수 없다.
    """
    if isinstance(exc, DeepResearchGenerationError):
        # 엔진이 결과를 못 내서 규칙으로 떨어진 것과, 결과가 계약을 어긴 것은 사용자가
        # 할 일이 다르다. 하나로 뭉뚱그리면 어느 쪽인지 알 수 없다.
        if "engine_failed" in str(exc):
            return ErrorCode.ADAPTER_FAILED
        return ErrorCode.VALIDATION_FAILED
    return ErrorCode.INTERNAL_ERROR


class ApprovedTopicJobs:
    def __init__(
        self,
        data_dir: Path,
        approvals: ApprovalStore,
        *,
        clock: Callable[[], datetime],
        executor: Executor | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.clock = clock
        self.store = SharedJobStore(
            data_dir / "jobs-v2.json",
            data_dir / "jobs.json",
            clock=clock,
        )
        # The lifecycle remains the sole cleanup/persistence authority.  These
        # callbacks observe only after it has completed those actions.
        self.lifecycle = JobPrivateLifecycle(
            data_dir / "job-context",
            clock=clock,
            terminal_observer=common_jobs._diagnostic_authority_terminal,
            cleanup_started=common_jobs._diagnostic_cleanup_started,
            cleanup_finished=common_jobs._diagnostic_cleanup_finished,
            cleanup_failed=common_jobs._diagnostic_cleanup_failed,
        )
        self.coordinator = SubmissionCoordinator(data_dir, approvals)
        self.executor = executor or _EXECUTOR
        self.coordinator.recover(SharedSubmissionJobs(data_dir, self.store))

    def queued_job(
        self,
        *,
        requested_mode: str,
        adapter: str,
        confirmed_zero: bool,
    ) -> SharedJob:
        execution_mode = RequestedMode(requested_mode)
        match execution_mode:
            case RequestedMode.DIRECT:
                job_kind = JobKind.TOPIC_REPORT
            case RequestedMode.CLI:
                job_kind = JobKind.AGENT_BRIDGE
            case unreachable:
                assert_never(unreachable)
        is_direct = execution_mode is RequestedMode.DIRECT
        job = new_shared_job(
            kind=job_kind,
            task_type="topic_report",
            generation_mode="rules" if confirmed_zero or is_direct else "llm_cli",
            adapter="rules" if confirmed_zero or is_direct else adapter,
            requested_mode=execution_mode,
            mode="fallback" if confirmed_zero else "generate",
            attempted_engine="none" if confirmed_zero or is_direct else "cli",
            clock=self.clock,
        )
        if not confirmed_zero:
            return job
        return job.model_copy(
            update={
                "engine": Engine.NONE,
                "finalEngine": Engine.RULES,
                "fallbackReason": FallbackReason.CONFIRMED_ZERO_EVIDENCE,
            }
        )

    def submit(
        self,
        *,
        proof: ApprovalProof,
        job: SharedJob,
        command: ApprovedGenerationInput,
    ) -> SubmittedApprovedJob:
        metadata = JobMetadata(id=job.id, approvalId=proof.id, planHash=proof.planHash)
        jobs = SharedSubmissionJobs(self.data_dir, self.store, job, metadata)
        claimed = self.coordinator.submit(
            SubmissionRequest(proof=proof, jobId=job.id),
            jobs,
        )
        claimed_job = self.store.get(claimed.id)
        if claimed_job is None:
            raise ValueError("approved_job_missing")
        created = claimed.id == job.id
        if created:
            self.lifecycle.set_private(
                job.id,
                {
                    "approvedRequest": command.approved.model_dump(mode="json"),
                    "researchResolution": command.preview.model_dump(mode="json"),
                    "taskPolicy": dict(command.taskPolicy) if isinstance(command.taskPolicy, dict) else None,
                },
            )
            parent = current_context()
            recorder = common_jobs._diagnostic_submission(
                claimed_job,
                current_request_id(),
                parent.run_id if parent is not None else None,
            )
            future = self.executor.submit(self._run, job.id, command, recorder)
            common_jobs.FUTURES[job.id] = future
        return SubmittedApprovedJob(claimed_job, created)

    def _cancelled(self, job_id: str) -> bool:
        current = self.store.get(job_id)
        if current is None or current.status is not JobStatus.CANCEL_REQUESTED:
            return False
        self.lifecycle.terminalize(self.store, job_id, JobStatus.CANCELLED)
        return True

    def _run(self, job_id: str, command: ApprovedGenerationInput, recorder=None) -> None:
        bundle = None
        context = recorder.context if recorder is not None else None
        # Keep the worker seam compatible with the small legacy test/fallback
        # callers that pass an opaque command object.  A task policy is an
        # optional handoff field, so its absence means the existing global
        # generation path rather than an internal worker error.
        task_policy = getattr(command, "taskPolicy", None)
        with bind_context(context) if context is not None else nullcontext():
            with bind_failure_cache():
                try:
                    self.store.transition(job_id, JobStatus.RUNNING)
                    common_jobs._diagnostic_worker_started(recorder)
                    preflight_recorder, preflight_stage = common_jobs.diagnostic_stage_start("preflight")
                    # Confirmation is already durable; this frozen command is
                    # the actual worker-side handoff into generation.
                    _ = getattr(command, "approved", None)
                    common_jobs.diagnostic_stage_end(preflight_recorder, preflight_stage, "preflight")
                    generate_recorder, generate_stage = common_jobs.diagnostic_stage_start("generate")
                    context_recorder, context_stage = common_jobs.diagnostic_stage_start("context")
                    try:
                        with bind_task_policy(task_policy) if isinstance(task_policy, dict) else nullcontext():
                            outcome = build_approved_report(command, job_id=job_id, clock=self.clock)
                    except Exception as exc:
                        common_jobs.diagnostic_stage_failure(
                            context_recorder, exc,
                            stage_id=context_stage,
                            stage_code="context" if context_stage is not None else None,
                            boundary="generic",
                        )
                        common_jobs.diagnostic_stage_end(context_recorder, context_stage, "context")
                        common_jobs.diagnostic_stage_failure(
                            generate_recorder,
                            exc,
                            stage_id=generate_stage,
                            stage_code="generate" if generate_stage is not None else None,
                            boundary="validation" if isinstance(exc, DeepResearchGenerationError) else "generic",
                        )
                        common_jobs.diagnostic_stage_end(generate_recorder, generate_stage, "generate")
                        raise
                    common_jobs.diagnostic_stage_end(context_recorder, context_stage, "context")
                    common_jobs.diagnostic_stage_end(generate_recorder, generate_stage, "generate")
                    initial_report = dict(outcome.report)
                    # A cancellation can be requested by the generator before
                    # it returns a report (including test/fallback seams that
                    # intentionally return an empty placeholder).  Observe it
                    # before deriving report identity so cancellation stays a
                    # terminal cancel instead of becoming internal_error.
                    if self._cancelled(job_id):
                        return
                    initial_provenance = initial_report.get("executionProvenance")
                    initial_plan_hash = str(initial_provenance.get("planHash") or "") if isinstance(initial_provenance, dict) else ""
                    report_id = _stable_topic_id(
                        str(initial_report["date"]),
                        str(initial_report["topicKey"]),
                        str(initial_report["topicLabel"]),
                        discriminator=initial_plan_hash,
                    )
                    if bool(getattr(getattr(command, "approved", None), "deepResearch", False)):
                        self.store.update_runtime(job_id, {"progress": 60})
                        validate_recorder, validate_stage = common_jobs.diagnostic_stage_start("validate")
                        try:
                            with bind_task_policy(task_policy) if isinstance(task_policy, dict) else nullcontext():
                                outcome = run_deep_pipeline(
                                    outcome,
                                    command,
                                    job_id=job_id,
                                    report_id=report_id,
                                    candidate_store=CandidateStore(self.data_dir / "job-context"),
                                )
                        except Exception as exc:
                            common_jobs.diagnostic_stage_failure(
                                validate_recorder, exc,
                                stage_id=validate_stage,
                                stage_code="validate" if validate_stage is not None else None,
                                boundary="validation",
                            )
                            common_jobs.diagnostic_stage_end(validate_recorder, validate_stage, "validate")
                            raise
                        common_jobs.diagnostic_stage_end(validate_recorder, validate_stage, "validate")
                    self.store.update_runtime(
                        job_id,
                        {
                            "generationMode": outcome.generationMode,
                            "engine": outcome.attemptedEngine,
                            "adapter": outcome.adapter,
                            "mode": outcome.mode,
                            "attemptedEngine": outcome.attemptedEngine,
                            "finalEngine": outcome.finalEngine,
                            "fallbackReason": outcome.fallbackReason,
                            "progress": 90,
                        },
                    )
                    common_jobs.diagnostic_execution(
                        attempted_engine=outcome.attemptedEngine,
                        final_engine=outcome.finalEngine,
                        adapter=outcome.adapter,
                        fallback_reason=outcome.fallbackReason,
                    )
                    if self._cancelled(job_id):
                        return
                    report = dict(outcome.report)
                    report["id"] = report_id
                    terminal = {
                        "artifactId": report_id,
                        "reportId": report_id,
                        "date": str(report["date"]),
                        "title": str(report["title"]),
                    }
                    current = self.store.get(job_id)
                    if current is None:
                        raise ValueError("approved_job_missing")
                    producer = JobJsonProducers(self.data_dir, clock=self.clock)
                    bundle = producer.stage_topic(
                        current,
                        ReportJobRequest(report=report, terminal_result=terminal),
                    )
                    staged_job = self.store.get(job_id)
                    if staged_job is not None and staged_job.status is JobStatus.CANCEL_REQUESTED:
                        producer.workspace.discard(bundle)
                        self._cancelled(job_id)
                        return
                    producer.workspace.commit(bundle, self.store, self.lifecycle)
                    _clear_resume(command)
                except Exception as exc:  # noqa: BROAD_EXCEPT_OK -- worker boundary terminalizes every failure.
                    common_jobs._diagnostic_exception(recorder, exc)
                    current = self.store.get(job_id)
                    if current is not None and current.status is JobStatus.CANCEL_REQUESTED:
                        if bundle is not None:
                            JobJsonProducers(self.data_dir, clock=self.clock).workspace.discard(bundle)
                        self.lifecycle.terminalize(self.store, job_id, JobStatus.CANCELLED)
                        return
                    if current is None or current.status in {
                        JobStatus.DONE,
                        JobStatus.CANCELLED,
                        JobStatus.COMMITTING,
                        JobStatus.FAILED,
                        JobStatus.FAILED_COMMIT,
                        JobStatus.FAILED_COMMIT_RECOVERY,
                    }:
                        return
                    if bundle is not None:
                        JobJsonProducers(self.data_dir, clock=self.clock).workspace.discard(bundle)
                    detail = _failure_detail(exc)
                    if detail:
                        try:
                            self.store.update_runtime(job_id, {"failureDetail": detail})
                        except Exception:  # noqa: BLE001 - diagnostics must not block authority.
                            pass
                    self.lifecycle.terminalize(
                        self.store,
                        job_id,
                        JobStatus.FAILED,
                        error_code=_failure_code(exc),
                    )

    def compatibility(self, job: SharedJob) -> dict[str, JsonValue]:
        return compatibility_job(job)


__all__ = ["ApprovedTopicJobs", "SubmittedApprovedJob"]
