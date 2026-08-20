from __future__ import annotations

import json
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


def _identity(kind: ReportKind, report_id: str, path: str) -> tuple[str, str | None]:
    """Split a briefing target into ``(date, market)``.

    시장 접미사는 `canonical_identity.BRIEFING_MARKETS`에서 읽는다. 여기에 시장을 다시
    적어 두는 동안 유럽장·일본장 브리핑의 overlay·quality repair가 CLI 실행을 다 마친
    **커밋 단계**에서 예외로 버려졌다.

    `quality_repair`의 saveTarget은 `briefing:{id}` 형태다. 접두를 벗기지 않으면
    `briefing:2026-08-14`가 report id가 되어 경로 해석이 거부한다.

    접미사가 없는 옛 브리핑(`2026-06-18.json`)은 scope 없이 돌려준다 — 하류
    `_briefing_identity`가 그 형태를 명시적으로 지원한다.
    """
    if kind is not ReportKind.BRIEFING:
        return report_id, None
    stem = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".json")
    candidates = [value.rsplit(":", 1)[-1] for value in (stem, str(report_id or "")) if value]
    # 종류 접미사를 먼저 벗긴다. 주간 파일(`2026-08-23.us.weekly`)에서 시장을 바로 찾으면
    # 어느 시장으로도 끝나지 않아 접미사 전체가 report id로 남고 경로 해석이 거부한다.
    trimmed = []
    for value in candidates:
        for kind_suffix in BRIEFING_KIND_SUFFIXES:
            if value.endswith(f".{kind_suffix}"):
                value = value[: -len(kind_suffix) - 1]
                break
        trimmed.append(value)
    candidates = trimmed
    for value in candidates:
        for market in BRIEFING_MARKETS:
            if value.endswith(f".{market}"):
                return value[: -len(market) - 1], market
    if not candidates:
        raise ValueError("briefing producer requires a report id or path")
    return candidates[0], None


def _json_summary(task_type: TaskType, pack: dict, candidate: dict) -> dict[str, str | int | bool | None]:
    artifact_id = str(candidate.get("id") or pack.get("artifactId") or "")
    generated_at = str(candidate.get("generatedAt") or "")
    report_date = str(candidate.get("date") or generated_at[:10] or pack.get("artifactId") or "")
    summary: dict[str, str | int | bool | None] = {
        "artifactId": artifact_id,
        "title": str(candidate.get("title") or candidate.get("headline") or pack.get("title") or ""),
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


def commit_json_output(
    job_id: str,
    task_type: TaskType,
    pack: dict,
    *,
    markdown: str | None,
    payload: dict | None,
) -> dict[str, str | int | bool | None]:
    job = _running(job_id, task_type)
    root = jobs.data_root()
    lifecycle = jobs.private_lifecycle()
    producer = JobJsonProducers(root, clock=_clock)
    match task_type:
        case TaskType.BRIEFING:
            prepared = agent_service.write_briefing_from_markdown(pack, markdown or "", persist=False)
            reports = prepared["reports"]
            result = prepared["result"]
            summary = _json_summary(task_type, pack, result)
            bundle = producer.stage_briefing(
                job,
                BriefingJobRequest(
                    date=str(result.get("date") or pack.get("artifactId") or ""),
                    scopes=tuple(reports),
                    reports=reports,
                    visuals=prepared["visuals"],
                    terminal_result=summary,
                    kind=str(result.get("kind") or "daily"),
                ),
            )
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
            report_id, scope = _identity(kind, str(canonical.get("id") or ""), str(internal.get("reportPath") or ""))
            summary = {"artifactId": f"{report_id}.{scope}" if scope else report_id, "reportId": report_id}
            bundle = producer.stage_overlay(
                job,
                OverlayJobRequest(kind, report_id, scope, result["personalOverlay"], summary),
            )
        case TaskType.QUALITY_REPAIR:
            candidate = agent_service.write_quality_repair_from_markdown(pack, markdown or "", persist=False)
            internal = pack.get("internal") or {}
            kind = _report_kind(str(internal.get("targetArtifactType") or ""))
            report_id, scope = _identity(
                kind,
                str(internal.get("targetArtifactId") or ""),
                str(pack.get("saveTarget") or ""),
            )
            summary = {"artifactId": f"{report_id}.{scope}" if scope else report_id, "reportId": report_id}
            bundle = producer.stage_quality_repair(
                job,
                QualityRepairJobRequest(kind, report_id, scope, candidate, summary),
            )
        case TaskType.INVESTMENT_REVIEW:
            candidate = agent_service.write_investment_review_from_markdown(pack, markdown or "", persist=False)
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
    from features.agent_mode.chat import run_agent_chat
    from features.agent_mode.consultation_context import assemble_consultation_context
    from features.agent_mode.consultation_prompt import rules_fallback
    from features.agent_mode.consultation_store import append_assistant_message, get_session
    from features.smart_collections.routes import create_smart_collection_service

    session = get_session(data_dir, session_id)
    user_message = next((row for row in session.get("messages") or [] if row.get("id") == user_message_id and row.get("role") == "user"), None)
    if not user_message:
        raise ValueError("consultation_user_message_not_found")
    question = str(user_message.get("content") or "")
    progress("대화 맥락을 조립하고 있습니다.", 20)
    context = assemble_consultation_context(data_dir, session_id)

    # 화면 맥락은 요청이 준 것을 쓰고, 없으면 대화 주제에서 만든다.
    scope = session.get("scope") or {}
    screen = dict(screen_context or {})
    screen.setdefault("surface", "agent_dock")
    if scope.get("kind") and scope["kind"] != "general":
        screen.setdefault("viewId", str(scope["kind"]))

    engine = "rules"
    reply = rules_fallback(question)
    proposal_id = ""
    try:
        progress("Agent가 답변을 작성하고 있습니다.", 50)
        # 컬렉션 서비스를 넘기지 않으면 `prepare_agent_context()`가 화면이 실어 보낸
        # `collectionId`를 풀지 못해 예외를 던지고, 아래 광범위 except가 그것을 삼켜
        # 대화 전체가 규칙 fallback으로 떨어진다 — CLI는 한 번도 불리지 않는다.
        # Deep Research에서 컬렉션을 고른 상태의 도크 질문이 전부 그랬다.
        result = run_agent_chat(
            question, screen, options or {},
            progress=progress, job_id=job_id, conversation=context["serialized"],
            collection_service=create_smart_collection_service(data_dir),
        )
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
    except Exception:
        # Transcript and private provider errors never enter job result or telemetry.
        engine = "rules"
    append_assistant_message(data_dir, session_id, user_message_id, reply, engine=engine)
    return {"sessionId": session_id, "messageId": user_message_id, "status": "answered", "proposalId": proposal_id}


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
    return {"artifactId": job_id, "savedCount": result.saved_count, "date": str(pack.get("artifactId") or "")}


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
