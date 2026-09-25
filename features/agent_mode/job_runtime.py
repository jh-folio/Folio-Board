from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never
from uuid import uuid4

from features.agent_mode import service as agent_service
from features.common import jobs
from features.common.canonical_identity import BRIEFING_KIND_SUFFIXES, BRIEFING_MARKETS, ReportKind
from features.common.canonical_json import JsonValue
from features.common.job_json_producer_types import (
    BriefingJobRequest,
    InvestmentReviewJobRequest,
    OverlayJobRequest,
    QualityRepairJobRequest,
    ReportJobRequest,
)
from features.common.job_json_producers import JobJsonProducers
from features.common.shared_jobs_projection import utc_z
from features.common.shared_jobs_schema import JobStatus, SharedJob, TaskType
from features.common.sql_job_lifecycle import SqlJobLifecycle
from features.market_memory.attempt_store import AttemptScope, AttemptStore
from features.market_memory.memory import connect as connect_market_memory
from features.market_memory.memory import init_db
from features.market_memory.snapshot import ensure_snapshot_table
from features.market_memory.sql_job_service import (
    CombinedMarketJobRequest,
    MarketMemoryJobRequest,
    MarketSqlJobRuntime,
    MarketStateJobRequest,
    run_combined_market_job,
    run_market_memory_job,
    run_market_state_job,
)
from features.thesis_tracking import store as thesis_store
from features.thesis_tracking import review_state as thesis_review_state
from features.thesis_tracking.sql_job_service import ThesisDeltaJobRequest, run_thesis_delta_job


type SnapshotBuilder = Callable[[object], Mapping[str, JsonValue]]


def _clock() -> datetime:
    return datetime.now(UTC)


def _operation_id() -> str:
    return f"op_{uuid4().hex}"


def shared_job(job_id: str) -> SharedJob | None:
    return jobs.get_shared_job(job_id)


def is_durable_job(job_id: str) -> bool:
    return bool(job_id and shared_job(job_id) is not None)


def _running(job_id: str, task_type: TaskType) -> SharedJob:
    job = shared_job(job_id)
    if job is None or job.status is not JobStatus.RUNNING or job.taskType is not task_type:
        raise RuntimeError("shared job is not running for the requested producer")
    return job


def _report_kind(value: str) -> ReportKind:
    normalized = str(value or "").strip().lower()
    if normalized == "briefing":
        return ReportKind.BRIEFING
    if normalized in {"analysis", "company_analysis"}:
        return ReportKind.COMPANY_ANALYSIS
    if normalized == "topic_report":
        return ReportKind.TOPIC_REPORT
    raise ValueError("unsupported canonical report kind")


def _identity(kind: ReportKind, report_id: str, path: str) -> tuple[str, str | None, str]:
    """Split a briefing target into ``(date, market, kind)``.

    시장 접미사는 `canonical_identity.BRIEFING_MARKETS`에서 읽는다. 여기에 시장을 다시
    적어 두는 동안 유럽장·일본장 브리핑의 overlay·quality repair가 CLI 실행을 다 마친
    **커밋 단계**에서 예외로 버려졌다.

    `quality_repair`의 saveTarget은 `briefing:{id}` 형태다. 접두를 벗기지 않으면
    `briefing:2026-08-14`가 report id가 되어 경로 해석이 거부한다.

    접미사가 없는 옛 브리핑(`2026-06-18.json`)은 scope 없이 돌려준다 — 하류
    `_briefing_identity`가 그 형태를 명시적으로 지원한다.

    **종류는 벗기되 버리지 않고 돌려준다.** 시장을 찾으려면 접미사를 먼저 떼야 하는데,
    떼고 잊으면 주간 대상이 일간 id가 되어 하류 `resolve_exact_report_path`가 그날
    **일간 파일**을 연다 — 주간 품질 개선이 CLI를 다 돌린 뒤 커밋 단계에서 정체성
    검증에 걸려 실패하거나, 최악에는 주간 본문이 일간 보고서를 덮어쓴다.
    """
    if kind is not ReportKind.BRIEFING:
        return report_id, None, ""
    stem = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".json")
    candidates = [value.rsplit(":", 1)[-1] for value in (stem, str(report_id or "")) if value]
    # 종류 접미사를 먼저 벗긴다. 주간 파일(`2026-08-23.us.weekly`)에서 시장을 바로 찾으면
    # 어느 시장으로도 끝나지 않아 접미사 전체가 report id로 남고 경로 해석이 거부한다.
    trimmed = []
    found_kind = ""
    for value in candidates:
        for kind_suffix in BRIEFING_KIND_SUFFIXES:
            if value.endswith(f".{kind_suffix}"):
                value = value[: -len(kind_suffix) - 1]
                found_kind = found_kind or kind_suffix
                break
        trimmed.append(value)
    candidates = trimmed
    for value in candidates:
        for market in BRIEFING_MARKETS:
            if value.endswith(f".{market}"):
                return value[: -len(market) - 1], market, found_kind
    if not candidates:
        raise ValueError("briefing producer requires a report id or path")
    return candidates[0], None, found_kind


def _briefing_target(date_text: str, scope: str | None, kind_suffix: str) -> tuple[str, str]:
    """`(report id, artifact id)`. 종류는 report id에 싣고 시장은 따로 넘긴다.

    `resolve_exact_report_path`는 `{날짜}[.{시장}][.{종류}]`를 읽으므로 report id에
    종류만 실어 두면 시장과 합쳐 올바른 파일을 연다. artifact id는 저장 파일과 같은
    순서(`{날짜}.{시장}.{종류}`)여야 change 이벤트와 이름이 어긋나지 않는다.
    """
    report_id = f"{date_text}.{kind_suffix}" if kind_suffix else date_text
    artifact_id = ".".join(part for part in (date_text, scope or "", kind_suffix) if part)
    return report_id, artifact_id


def _json_summary(task_type: TaskType, pack: dict, candidate: dict) -> dict[str, str | int | bool | None]:
    artifact_id = str(candidate.get("id") or pack.get("artifactId") or "")
    generated_at = str(candidate.get("generatedAt") or "")
    report_date = str(candidate.get("date") or generated_at[:10] or pack.get("artifactId") or "")
    company = candidate.get("company")
    company_name = company.get("name") if isinstance(company, dict) else ""
    summary: dict[str, str | int | bool | None] = {
        "artifactId": artifact_id,
        "title": str(
            candidate.get("title")
            or candidate.get("headline")
            or pack.get("title")
            or company_name
            or ""
        ),
    }
    if task_type is TaskType.BRIEFING:
        summary["reportId"] = artifact_id
        summary["date"] = report_date
    elif task_type in {TaskType.COMPANY_ANALYSIS, TaskType.TOPIC_REPORT}:
        summary["reportId"] = artifact_id
        summary["date"] = report_date
    elif task_type is TaskType.INVESTMENT_REVIEW:
        summary["reportId"] = artifact_id or report_date
        summary["artifactId"] = artifact_id or report_date
        summary["date"] = report_date
    return summary


def _briefing_fallback_allowed(error: BaseException) -> bool:
    """Keep cancellation/deadline failures from being hidden by a fallback."""
    validation = getattr(error, "validation", None)
    reason_codes = (
        set(validation.get("reasonCodes") or [])
        if isinstance(validation, dict)
        else set()
    )
    error_text = str(error).lower()
    if reason_codes.intersection({"cancelled", "deadline_expired"}):
        return False
    return "cancelled" not in error_text and "deadline_expired" not in error_text


def _prepare_rules_briefing_fallback(pack: dict, *, reason: str, rejection_codes: list[str] | None = None) -> dict:
    """Prepare a rules report without bypassing the shared JSON commit path."""
    markdown = agent_service.build_rules_briefing_markdown_from_pack(pack)
    # The fallback must remain deterministic.  Do not spend a quality rewrite
    # or concentration-repair call after the CLI has already failed; the
    # pinned pack still carries the original control metadata for the report.
    fallback_internal = dict(pack.get("internal") or {})
    fallback_internal["qualityMode"] = "diagnose_only"
    fallback_internal["concentrationByMarket"] = {}
    fallback_pack = {**pack, "internal": fallback_internal}
    prepared = agent_service.write_briefing_from_markdown(
        fallback_pack, markdown, persist=False, validate_contract=False
    )
    fallback_status = "rules_fallback_after_cli_validation"
    fallback_message = "CLI 결과가 최종 검증을 통과하지 못해 규칙 기반 브리핑으로 저장했습니다."
    for report in (prepared.get("reports") or {}).values():
        generation = dict(report.get("generation") or {})
        generation.update({
            "mode": "rules",
            "status": fallback_status,
            "fallbackReason": reason,
            "rejectedReasonCodes": rejection_codes or [],
            "message": fallback_message,
        })
        report["generation"] = generation
        warnings = list(report.get("warnings") or [])
        if "rules_fallback_after_cli_validation" not in warnings:
            warnings.append("rules_fallback_after_cli_validation")
        report["warnings"] = warnings
    result = prepared.get("result")
    if isinstance(result, dict):
        generation = dict(result.get("generation") or {})
        generation.update({
            "mode": "rules",
            "status": fallback_status,
            "fallbackReason": reason,
            "message": fallback_message,
        })
        result["generation"] = generation
        result["fallbackReason"] = reason
    prepared["fallbackReason"] = reason
    return prepared


def commit_json_output(
    job_id: str,
    task_type: TaskType,
    pack: dict,
    *,
    markdown: str | None,
    payload: dict | None,
    contract_failed: bool = False,
) -> dict[str, str | int | bool | None]:
    job = _running(job_id, task_type)
    root = jobs.data_root()
    lifecycle = jobs.private_lifecycle()
    producer = JobJsonProducers(root, clock=_clock)
    match task_type:
        case TaskType.BRIEFING:
            from features.daily_briefing.finalize import BriefingFinalizationError
            from features.agent_mode.briefing_contract import (
                BriefingOutputContractError, briefing_contract_violations, contract_reason_codes,
            )

            fallback_reason = "cli_output_contract_failed"
            if contract_failed:
                # 계약을 어긴 본문은 파싱해 볼 것도 없다.  같은 사유로 바로 규칙
                # 대체를 만든다 — 예전에는 이 경우 잡이 예외로 죽어 산출물이
                # 하나도 남지 않았다.
                prepared = _prepare_rules_briefing_fallback(
                    pack, reason=fallback_reason,
                    rejection_codes=contract_reason_codes(briefing_contract_violations(markdown or "", pack.get("outputContract") or {})),
                )
            else:
                try:
                    prepared = agent_service.write_briefing_from_markdown(pack, markdown or "", persist=False)
                except BriefingOutputContractError as error:
                    prepared = _prepare_rules_briefing_fallback(pack, reason=fallback_reason, rejection_codes=error.reason_codes)
            reports = prepared["reports"]
            result = prepared["result"]
            summary = _json_summary(task_type, pack, result)
            if prepared.get("fallbackReason"):
                summary.update({
                    "generationMode": "rules",
                    "fallbackReason": prepared["fallbackReason"],
                })

            def stage_prepared(current: dict) -> object:
                current_reports = current["reports"]
                current_result = current["result"]
                current_summary = _json_summary(task_type, pack, current_result)
                if current.get("fallbackReason"):
                    current_summary.update({
                        "generationMode": "rules",
                        "fallbackReason": current["fallbackReason"],
                    })
                return producer.stage_briefing(
                    job,
                    BriefingJobRequest(
                        date=str(current_result.get("date") or pack.get("artifactId") or ""),
                        scopes=tuple(current_reports),
                        reports=current_reports,
                        visuals=current["visuals"],
                        terminal_result=current_summary,
                        kind=str(current_result.get("kind") or "daily"),
                    ),
                )

            try:
                bundle = stage_prepared(prepared)
            except BriefingFinalizationError as error:
                if not _briefing_fallback_allowed(error):
                    raise
                prepared = _prepare_rules_briefing_fallback(
                    pack,
                    reason="cli_final_validation_failed",
                    rejection_codes=sorted(set(error.validation.get("reasonCodes") or []).intersection({
                        "value_mismatch", "unit_mismatch", "date_mismatch",
                        "direction_mismatch", "relative_strength_mismatch",
                        "required_omission", "source_outside_whitelist",
                    })),
                )
                bundle = stage_prepared(prepared)
                summary = dict(bundle.terminal_result)
        case TaskType.COMPANY_ANALYSIS:
            candidate = agent_service.write_company_analysis_from_markdown(pack, markdown or "", persist=False)
            from features.company_analysis.service import analysis_report_id

            candidate["id"] = candidate.get("id") or analysis_report_id(candidate.get("company", {}), candidate.get("generatedAt", ""))
            summary = _json_summary(task_type, pack, candidate)
            bundle = producer.stage_company(job, ReportJobRequest(candidate, summary))
        case TaskType.TOPIC_REPORT:
            candidate = agent_service.write_topic_report_from_markdown(pack, markdown or "", persist=False)
            from features.topic_report.service import _stable_topic_id

            candidate["id"] = candidate.get("id") or _stable_topic_id(
                str(candidate.get("date") or ""),
                str(candidate.get("topicKey") or ""),
                str(candidate.get("topicLabel") or ""),
            )
            summary = _json_summary(task_type, pack, candidate)
            bundle = producer.stage_topic(job, ReportJobRequest(candidate, summary))
        case TaskType.PERSONAL_OVERLAY:
            result = agent_service.write_personal_overlay_from_json(pack, payload or {}, persist=False)
            internal = pack.get("internal") or {}
            draft = pack.get("draftArtifact") or {}
            canonical = draft.get("canonical") or {}
            kind = _report_kind(str(internal.get("reportKind") or canonical.get("kind") or ""))
            date_text, scope, kind_suffix = _identity(kind, str(canonical.get("id") or ""), str(internal.get("reportPath") or ""))
            report_id, artifact_id = _briefing_target(date_text, scope, kind_suffix)
            summary = {"artifactId": artifact_id, "reportId": report_id}
            bundle = producer.stage_overlay(
                job,
                OverlayJobRequest(kind, report_id, scope, result["personalOverlay"], summary),
            )
        case TaskType.QUALITY_REPAIR:
            candidate = agent_service.write_quality_repair_from_markdown(pack, markdown or "", persist=False)
            internal = pack.get("internal") or {}
            kind = _report_kind(str(internal.get("targetArtifactType") or ""))
            date_text, scope, kind_suffix = _identity(
                kind,
                str(internal.get("targetArtifactId") or ""),
                str(pack.get("saveTarget") or ""),
            )
            report_id, artifact_id = _briefing_target(date_text, scope, kind_suffix)
            summary = {"artifactId": artifact_id, "reportId": report_id}
            bundle = producer.stage_quality_repair(
                job,
                QualityRepairJobRequest(kind, report_id, scope, candidate, summary),
            )
        case TaskType.INVESTMENT_REVIEW:
            candidate = agent_service.write_investment_review_from_markdown(pack, markdown or "", persist=False)
            # CLI Markdown is allowed to change only the derived field.  The
            # JobArtifactWorkspace runs the shared CAS/fingerprint finalizer
            # under its artifact lock and owns the sole durable promotion.
            summary = _json_summary(task_type, pack, candidate)
            producer = JobJsonProducers(root, clock=_clock, review_builder=lambda _body: candidate)
            bundle = producer.stage_investment_review(job, InvestmentReviewJobRequest({}, summary))
        case (
            TaskType.INDEX
            | TaskType.RSS
            | TaskType.SETUP
            | TaskType.COMPANION
            | TaskType.THESIS_DELTA
            | TaskType.MARKET_MEMORY_LLM
            | TaskType.MARKET_STATE_SNAPSHOT
            | TaskType.MARKET_MEMORY_UPDATE
        ):
            raise ValueError("task is not a JSON producer")
        case unreachable:
            assert_never(unreachable)
    if task_type == TaskType.BRIEFING:
        from features.common.quality_generation.call_budget import current_briefing_budget
        budget = current_briefing_budget()
        if budget:
            budget.check_active()
        summary = dict(bundle.terminal_result)
        if summary.get("fallbackReason"):
            jobs.shared_store().update_runtime(job_id, {
                "generationMode": "rules", "finalEngine": "rules",
                "fallbackReason": "engine_failed",
            })
            jobs.diagnostic_execution(final_engine="rules", fallback_reason="engine_failed")
    producer.workspace.commit(bundle, jobs.shared_store(), lifecycle)
    return summary


def _market_runtime() -> MarketSqlJobRuntime:
    return MarketSqlJobRuntime(
        lifecycle=SqlJobLifecycle(jobs.shared_store(), jobs.private_lifecycle()),
        attempts=AttemptStore(jobs.data_root() / "market-state-update-attempts.json"),
        clock=_clock,
    )


def _market_connection():
    connection = connect_market_memory(jobs.data_root() / "market-memory.sqlite3")
    init_db(connection)
    ensure_snapshot_table(connection, initialize_graph=False)
    connection.commit()
    return connection


def run_consultation_job(data_dir: Path, session_id: str, user_message_id: str, *, progress=None, job_id: str = "",
                         screen_context: dict | None = None, options: dict | None = None) -> dict[str, str]:
    """Answer one saved turn and persist the reply outside job telemetry.

    생성은 도크와 같은 경로(`run_agent_chat`)가 맡는다. 저장 경로만 따로 두면 같은
    대화가 두 길로 다니게 되고, 제안을 승인·거절한 사실이 대화 기록에 남지 않아
    다음 세션의 Agent가 같은 제안을 다시 하게 된다. 여기는 맥락 조립과 저장만 한다.
    """
    progress = progress or (lambda *_args, **_kwargs: None)
    started_monotonic = time.monotonic()
    from features.agent_mode.chat import run_agent_chat
    from features.agent_mode.consultation_context import assemble_consultation_context
    from features.agent_mode.consultation_prompt import rules_fallback
    from features.agent_mode.consultation_store import append_assistant_message, get_session
    from features.smart_collections.routes import create_smart_collection_service

    context_recorder, context_stage = jobs.diagnostic_stage_start("context")
    try:
        session = get_session(data_dir, session_id)
        user_message = next((row for row in session.get("messages") or [] if row.get("id") == user_message_id and row.get("role") == "user"), None)
        if not user_message:
            raise ValueError("consultation_user_message_not_found")
        question = str(user_message.get("content") or "")
        progress("대화 맥락을 조립하고 있습니다.", 20, phaseCode="context")
        context = assemble_consultation_context(data_dir, session_id, current_message_id=user_message_id)
    except Exception as error:
        jobs.diagnostic_stage_failure(
            context_recorder,
            error,
            stage_id=context_stage,
            stage_code="context" if context_stage is not None else None,
            boundary="generic",
        )
        jobs.diagnostic_stage_end(context_recorder, context_stage, "context")
        raise
    jobs.diagnostic_stage_end(context_recorder, context_stage, "context")

    # 화면 맥락은 요청이 준 것을 쓰고, 없으면 대화 주제에서 만든다.
    scope = session.get("scope") or {}
    exact_review_challenge = scope.get("kind") == "investment_review" and scope.get("intent") == "challenge"
    # An exact review challenge is immutable-at-open.  Client screen context
    # may contain report/collection selectors from a different surface, so it
    # cannot be merged into this turn or it would reintroduce generic data.
    screen = ({"surface": "agent_dock", "viewId": "investment_review", "exactReviewChallenge": True}
              if exact_review_challenge else dict(screen_context or {}))
    screen.setdefault("surface", "agent_dock")
    if scope.get("kind") and scope["kind"] != "general":
        screen.setdefault("viewId", str(scope["kind"]))

    engine = "rules"
    reply = rules_fallback(question)
    proposal_id = ""
    search = None
    try:
        progress("Agent가 답변을 작성하고 있습니다.", 50)
        jobs.diagnostic_execution(attempted_engine="cli")
        # 컬렉션 서비스를 넘기지 않으면 `prepare_agent_context()`가 화면이 실어 보낸
        # `collectionId`를 풀지 못해 예외를 던지고, 아래 광범위 except가 그것을 삼켜
        # 대화 전체가 규칙 fallback으로 떨어진다 — CLI는 한 번도 불리지 않는다.
        # Deep Research에서 컬렉션을 고른 상태의 도크 질문이 전부 그랬다.
        result = run_agent_chat(
            question, screen, options or {},
            progress=progress, job_id=job_id, conversation=context["serialized"],
            collection_service=None if exact_review_challenge else create_smart_collection_service(data_dir),
            exact_review_challenge=exact_review_challenge,
        )
        postprocess_recorder, postprocess_stage = jobs.diagnostic_stage_start("postprocess")
        progress(None, None, phaseCode="postprocess")
        search = result.get("search") if isinstance(result.get("search"), dict) else None
        answer = str(result.get("reply") or "").strip()
        if answer:
            reply = answer
            engine = str(result.get("adapter") or result.get("engine") or "cli")[:30]
        notice = str(result.get("notice") or "").strip()
        if notice:
            reply = "\n\n".join([reply, notice])
        # 제안을 만들었다는 사실은 대화 기록에 남아야 한다. diff 본문은 제안 저장소가 갖는다.
        proposal_id = str(((result.get("proposal") or {}) or {}).get("id") or "")
        if proposal_id:
            reply = "\n\n".join([reply, f"(수정 제안 {proposal_id} 을 만들었습니다. 승인해야 보고서가 바뀝니다.)"])
        jobs.diagnostic_stage_end(postprocess_recorder, postprocess_stage, "postprocess")
    except Exception as error:
        # Transcript and private provider errors never enter job result or telemetry.
        jobs.diagnostic_stage_failure(
            jobs.current_diagnostic_recorder(),
            error,
            stage_id=None,
            stage_code="generate",
            boundary="adapter",
        )
        engine = "rules"
    # The bridge already records a concrete CLI failure before its legacy
    # fallback returns.  Here we only publish the closed final engine fact.
    final_engine = "rules" if engine == "rules" else "cli"
    fallback_reason = "engine_failed" if engine == "rules" else None
    jobs.diagnostic_execution(final_engine=final_engine, fallback_reason=fallback_reason)
    # Job-facing attribution and timing: nothing wrote these for chat jobs
    # before, so `GET /api/jobs/{id}` always showed the untouched defaults
    # (`adapter: auto`, `finalEngine: null`) even after a real CLI failure.
    # `stage_timing_summary` reads the diagnostics stages this function and
    # the bridge already measured — it does not start a second clock.
    progress(
        None, None,
        adapter="rules" if engine == "rules" else engine,
        finalEngine=final_engine,
        fallbackReason=fallback_reason,
        **jobs.stage_timing_summary(jobs.current_diagnostic_recorder()),
        totalMs=int((time.monotonic() - started_monotonic) * 1000),
    )
    commit_recorder, commit_stage = jobs.diagnostic_stage_start("commit")
    progress(None, None, phaseCode="commit")
    try:
        assistant = append_assistant_message(data_dir, session_id, user_message_id, reply, engine=engine, search=search)
    except Exception as error:
        jobs.diagnostic_stage_failure(
            commit_recorder,
            error,
            stage_id=commit_stage,
            stage_code="commit" if commit_stage is not None else None,
            boundary="save",
        )
        jobs.diagnostic_stage_end(commit_recorder, commit_stage, "commit")
        raise
    jobs.diagnostic_stage_end(commit_recorder, commit_stage, "commit")
    return {
        "sessionId": session_id, "messageId": user_message_id, "status": "answered", "proposalId": proposal_id,
        "assistantMessageId": assistant.get("id", ""),
    }


def submit_consultation_job(data_dir: Path, session_id: str, user_message_id: str,
                            *, screen_context: dict | None = None, options: dict | None = None) -> dict:
    job = jobs.submit_job(
        "agent_bridge",
        "Agent 대화",
        run_consultation_job,
        Path(data_dir),
        session_id,
        user_message_id,
        screen_context=screen_context,
        options=options,
        pass_job_id=True,
        dedicated_thread=True,
    )
    job["generationMode"] = "llm_cli"
    return job


def commit_thesis_output(job_id: str, pack: dict, payload: dict) -> dict[str, str | int | bool | None]:
    _running(job_id, TaskType.THESIS_DELTA)
    ticker, delta = agent_service.prepare_thesis_delta_writeback(pack, payload)
    generated_at = str(delta.get("generatedAt") or utc_z(_clock()))
    operation_id = _operation_id()
    connection = thesis_store.connect(jobs.data_root() / "market-memory.sqlite3")
    lifecycle = SqlJobLifecycle(jobs.shared_store(), jobs.private_lifecycle())
    try:
        result = run_thesis_delta_job(
            connection,
            lifecycle,
            ThesisDeltaJobRequest(job_id, operation_id, ticker, generated_at, delta, utc_z(_clock())),
        )
        thesis = thesis_store.get_thesis(connection, ticker)
        saved_delta = thesis_store.get_delta(connection, result.delta_id)
        if thesis and saved_delta:
            thesis_review_state.record_completed_review(connection, thesis, saved_delta)
    finally:
        connection.close()
    return {"artifactId": result.delta_id, "reportId": result.delta_id}


def commit_market_memory_output(job_id: str, pack: dict, payload: dict) -> dict[str, str | int | bool | None]:
    _running(job_id, TaskType.MARKET_MEMORY_LLM)
    prepared = agent_service.prepare_market_memory_writeback(pack, payload)
    entries = tuple(prepared["entries"])
    connection = _market_connection()
    try:
        result = run_market_memory_job(
            connection,
            _market_runtime(),
            MarketMemoryJobRequest(job_id, _operation_id(), entries, utc_z(_clock())),
        )
    finally:
        connection.close()
    # Graph persistence above is intentionally independent from role
    # persistence.  A stale/failed role batch must never invalidate the
    # durable market-memory job receipt.
    from features.market_memory.service import finalize_role_classification

    role_classification = finalize_role_classification(
        prepared.get("roleSelection") or {}, payload, db_path=jobs.data_root() / "market-memory.sqlite3"
    )
    return {
        "artifactId": job_id,
        "savedCount": result.saved_count,
        "date": str(pack.get("artifactId") or ""),
        "roleClassification": role_classification,
    }


def commit_market_state_output(job_id: str, pack: dict, payload: dict) -> dict[str, str | int | bool | None]:
    _running(job_id, TaskType.MARKET_STATE_SNAPSHOT)
    snapshot = agent_service.prepare_market_state_snapshot_writeback(pack, payload)
    now = _clock()
    now_text = utc_z(now)
    context = json.loads(str(pack.get("context") or "{}"))
    watermarks = context.get("inputWatermarks") if isinstance(context, dict) else None
    watermark = watermarks.get("GLOBAL") if isinstance(watermarks, dict) else None
    connection = _market_connection()
    try:
        result = run_market_state_job(
            connection,
            _market_runtime(),
            MarketStateJobRequest(
                job_id,
                _operation_id(),
                snapshot,
                AttemptScope.GLOBAL,
                str(watermark or now_text),
                now,
                now_text,
            ),
        )
    finally:
        connection.close()
    return {
        "artifactId": result.snapshot_id,
        "snapshotId": result.snapshot_id,
        "date": str(pack.get("artifactId") or ""),
        "title": str(snapshot.get("headline") or pack.get("title") or ""),
    }


def commit_combined_market_output(
    job_id: str,
    entries: tuple[Mapping[str, JsonValue], ...],
    snapshot_builder: SnapshotBuilder,
) -> dict[str, str | int | bool | None]:
    _running(job_id, TaskType.MARKET_MEMORY_UPDATE)
    now = _clock()
    now_text = utc_z(now)
    connection = _market_connection()
    try:
        result = run_combined_market_job(
            connection,
            _market_runtime(),
            CombinedMarketJobRequest(
                job_id,
                _operation_id(),
                entries,
                snapshot_builder,
                AttemptScope.GLOBAL,
                now_text,
                now,
                now_text,
            ),
        )
    finally:
        connection.close()
    return {
        "artifactId": job_id,
        "savedCount": result.saved_count,
        "snapshotId": result.snapshot_id,
    }


__all__ = [
    "commit_combined_market_output",
    "commit_json_output",
    "commit_market_memory_output",
    "commit_market_state_output",
    "commit_thesis_output",
    "is_durable_job",
    "shared_job",
]
