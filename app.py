#!/usr/bin/env python3
"""Personal Market Research Archive — FastAPI server.

Handles routing and thin orchestration only; feature logic lives in features/.
"""
import datetime as dt
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from features.common.health import health_payload

from features.common.utils import kst_date, now_iso, read_json, write_json
from features.common.jobs import (
    close_diagnostics_runtime,
    diagnostic_job_lookup,
    diagnostics_runtime,
    load_jobs,
    submit_job,
)
from features.common.diagnostics.authority import default_authority_snapshot
from features.common.diagnostics.routes import create_diagnostics_router
from features.common.diagnostics.retention_routes import create_retention_router
from features.common.diagnostics.support import bind_request_id
from features.common.jobs_routes import router as jobs_router
from features.agent_mode.work_log_routes import router as work_log_router
from features.agent_mode.bridge import (
    agent_preflight,
    bridge_status,
    submit_agent_task,
)
from features.agent_mode.chat import (
    ProposalActionError,
    apply_proposal,
    get_proposal,
    recover_proposals,
    reject_proposal,
)
from features.agent_mode.routes import AgentCompanionBoundary
from features.agent_mode.proposal_schema import ProposalAction, ProposalActionRequest
from features.agent_mode.generation_mode import (
    llm_override_for_mode,
)
from features.agent_mode.setup import (
    launch_login as launch_agent_cli_login,
    save_settings as save_agent_cli_settings,
    settings_payload as agent_cli_settings_payload,
    submit_install as submit_agent_cli_install,
)
from features.automation.schema import wants_prerequisites as automation_wants_prerequisites
from features.automation.service import (
    diagnostic_authority_for_run,
    list_runs as list_automation_runs,
    read_settings as read_automation_settings,
    run_briefing_prerequisites,
    run_automation_once,
    schedule_automation_loop,
    save_settings as save_automation_settings,
)
from features.common.company_resolution import resolve_company_query, schedule_sec_exchange_cache
from features.company_analysis.direct_observer import run_direct_analysis
from features.personal_overlay.direct_observer import run_direct_overlay
from features.common.content_revision import content_revisions
from features.common.company_lookup import ensure_company_files
from features.common.dataframe_ops import top_records
from features.common.research_library.indexing.service import (
    IMPACT_TERMS,
    build_index,
    list_indexed_documents,
    load_index,
    warm_index_cache,
)
from features.common.research_library.rss.service import (
    import_rssarchive,
    rss_feed_payload,
    rss_merge_payload,
)
from features.common.research_library.signals.routes import create_signal_router
from features.common.research_library.signals.runtime import start_signal_runtime, stop_signal_runtime
from features.common.research_library.search.service import (
    group_docs,
    index_from_documents,
    list_companies,
    search_documents,
)
from features.llm_settings.settings_service import public_settings, save_settings
from features.llm_settings.task_policy import TaskPolicyError, public_task_policy, save_task_policy
from features.llm_settings.task_policy_check import check_task_policy
from features.llm_settings.task_runtime import (
    bind_task_policy,
    generation_mode as task_generation_mode,
    task_snapshot,
)
from features.llm_settings.provider_status import check_provider as check_llm_api_provider
from features.company_analysis.cache_cleanup import cache_stats, cleanup_cache
from features.market_memory.service import run_llm_market_memory, schedule_startup_regime_refresh
from features.market_memory.direct_observer import run_direct_market_memory
from features.market_memory.verification_view import narrative_verification_payload
from features.market_memory.digest import run_rss_market_memory_update
from features.market_memory.routes import create_market_state_router
from features.market_widgets.service import (
    get_market_widget_settings,
    save_market_widget_settings,
)
from features.investment_notes.service import (
    add_note as add_investment_note,
    get_note as get_investment_note,
    linked_notes_payload as native_linked_notes_payload,
    list_notes as list_investment_notes,
    save_note as save_investment_note,
)
from features.watchlist_notes.service import (
    get_watchlist,
    normalize_watchlist_keyword,
    save_watchlist,
    watchlist_detail,
    watchlist_overview,
)
from features.common.market_data.snapshot import fetch_market_snapshot
from features.common.market_data.providers import fetch_korea_market_data
from features.common.market_data.tape import build_market_tape
from features.common.market_data.routes import create_market_data_router
from features.common.market_data.toss_realtime_hub import TossRealtimeHub
from features.dashboard.routes import create_dashboard_router
from features.market_calendar.routes import create_market_calendar_router
from features.portfolio.routes import create_portfolio_router
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.common.research_schema.data_gaps import data_gaps_from_messages
from features.common.research_schema.service import (
    checkpoints_payload,
    data_gaps_payload,
    evidence_payload,
    market_tape_payload,
    source_ledger_payload,
)
from features.common.data_reliability.service import (
    market_data_files_payload,
    provider_status_payload,
    record_provider_status_payload,
)
from features.market_memory.memory import (
    audit_memory,
    build_memory_from_briefing,
    delete_memory,
    list_briefing_memories,
    list_family_suggestions,
    list_memory,
    list_states,
    list_story_links,
    list_taxonomy,
    memory_report,
    review_family_suggestion,
    story_map,
    update_state,
    upsert_memory,
)
from features.market_memory.regime_v2 import (
    list_regime_changes,
    list_regime_evidence,
    list_regime_thesis_links,
    refresh_all_regimes,
    refresh_regime_state,
    upsert_regime_thesis_link,
)
from features.llm_settings.client import bool_override, default_generation_mode, selected_llm_config, use_web_search_for_analysis
from features.daily_briefing.service import (
    NEWS_INBOX_PREFIXES,
    append_briefing_sources,
    briefing_sources_from_headlines,
    build_prompt_markdown,
    delete_briefing,
    extract_prev_checklist,
    generate_llm_briefing,
    group_digest,
    is_news_document,
    list_briefings,
    llm_status_message,
    load_prev_briefing,
    news_documents,
    prioritized_source_refs,
    read_briefing_prompt,
    resolve_briefing,
    select_briefing_docs,
    source_refs,
)
from features.daily_briefing.selection import derive_market_drivers, infer_market_session_date, prioritize_briefing_groups, session_doc_counts
from features.daily_briefing.builder import (
    build_briefing as build_daily_briefing,
    cached_korea_market_data as feature_cached_korea_market_data,
    cached_market_snapshot as feature_cached_market_snapshot,
)
from features.daily_briefing.archive import query_briefing_archive, refresh_briefing_archive
from features.daily_briefing.schema import (
    briefing_scope_view,
    market_selection_scope,
    normalize_briefing_kind,
    normalize_market_selection,
)
from features.daily_briefing.visuals import load_current_visuals, load_visual_sidecar
from features.company_analysis.report_rules import build_rule_report
from features.company_analysis.generation_service import analyze_company as generate_company_analysis
from features.company_analysis.data_gap_resolver import resolve_company_analysis_gaps
from features.company_analysis.report_contract import apply_report_ceiling as apply_company_report_ceiling
from features.company_analysis.style import analysis_prompt_path, normalize_analysis_style
from features.company_analysis.service import (
    analysis_status_message,
    build_company_analysis_charts,
    build_company_analysis_materials,
    company_analysis_sources,
    delete_analysis_report,
    generate_llm_company_analysis,
    get_analysis_report,
    list_analysis_reports,
    read_company_analysis_prompt,
    save_analysis_report,
)
from features.common.company_lookup import infer_requested_company
from features.notion_export.service import export_briefing, export_analysis, export_topic_report
from features.obsidian.export.service import (
    get_vault_settings,
    save_vault_settings,
    export_briefing_to_obsidian,
    export_analysis_to_obsidian,
    export_topic_report_to_obsidian,
    export_narratives_to_obsidian,
)
from features.obsidian.workflow.service import (
    create_workflow_note,
    linked_notes_payload,
    read_workflow_note,
    validate_workflow_notes,
)
from features.common.canonical_identity import CanonicalIdentityError
from features.common.canonical_reports import CanonicalConflictError, CanonicalValidationError
from features.personal_overlay.service import (
    attach_overlay_to_briefing,
    attach_overlay_to_report,
    strip_overlay,
)
from features.thesis_tracking.workspace_view import thesis_workspace_payload
from features.thesis_tracking.service import (
    list_thesis_payload,
    promote_note_to_thesis,
    run_thesis_delta,
    thesis_detail_payload,
    upsert_manual_thesis,
)
from features.topic_report.service import (
    attach_overlay_to_topic_report,
    delete_topic_report,
    evaluate_topic_report,
    get_topic_report,
    list_topic_reports,
    preset_topics_list,
)
from features.topic_report.routes import ApprovedRequestBoundary
from features.smart_collections.routes import SmartCollectionBoundary, create_smart_collection_service
from features.investment_notes.intelligence_routes import create_intelligence_router
from features.common.research_quality.evaluator import evaluate_artifact as evaluate_research_artifact
from features.common.research_quality.service import (
    evaluate_payload as evaluate_research_quality_payload,
    get_quality as get_research_quality,
    recheck_quality as recheck_research_quality,
)
from features.common.quality_generation.loop import apply_quality_loop
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.service import (
    preflight_payload as quality_generation_preflight_payload,
    repair_payload as quality_generation_repair_payload,
    run_payload as quality_generation_run_payload,
)
from features.common.quality_generation.schema import normalize_quality_mode
from features.investment_review.service import (
    get_review as get_investment_review,
    generate_review as generate_investment_review,
    mark_reviewed as mark_investment_review_reviewed,
    review_history as get_investment_review_history,
    normalize_review_date,
)
from features.investment_review.direct_observer import run_direct_review
from features.thesis_tracking.direct_observer import run_direct_thesis_delta
from features.daily_briefing.direct_observer import run_direct_briefings
from features.investment_review.review_v2 import ReviewRevisionConflict
from features.investment_review.context_routes import create_investment_context_router
from features.common.workspace import config_dir, data_dir, research_inbox_dir

ROOT = Path(__file__).resolve().parent
APP_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
DATA_DIR = data_dir()
CONFIG_DIR = config_dir()
INBOX_DIR = research_inbox_dir()
RSS_INBOX_DIR = INBOX_DIR / "rss"
PUBLIC_DIR = ROOT / "public"
BRIEFINGS_DIR = DATA_DIR / "briefings"
NOTES_DIR = DATA_DIR / "notes"
ANALYSIS_REPORTS_DIR = DATA_DIR / "company-analysis"
TOPIC_REPORTS_DIR = DATA_DIR / "topic-reports"
SEC_CACHE_DIR = DATA_DIR / "sec-cache"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"
FEATURES_DIR = ROOT / "features"
BRIEFING_PROMPT_PATH = FEATURES_DIR / "daily_briefing" / "prompt.md"
COMPANY_ANALYSIS_PROMPT_PATH = FEATURES_DIR / "company_analysis" / "prompt.md"


def ensure_dirs():
    for p in [
        DATA_DIR, CONFIG_DIR, INBOX_DIR, RSS_INBOX_DIR, BRIEFINGS_DIR,
        SEC_CACHE_DIR, NOTES_DIR, ANALYSIS_REPORTS_DIR, TOPIC_REPORTS_DIR,
        FEATURES_DIR / "daily_briefing", FEATURES_DIR / "company_analysis",
        INBOX_DIR / "filings", INBOX_DIR / "reports",
        INBOX_DIR / "articles", INBOX_DIR / "links",
    ]:
        p.mkdir(parents=True, exist_ok=True)
    from features.agent_mode.report_delete import recover_report_deletes

    recover_report_deletes(BRIEFINGS_DIR, refresh=refresh_briefing_archive)
    recover_report_deletes(ANALYSIS_REPORTS_DIR)
    recover_report_deletes(TOPIC_REPORTS_DIR)
    recover_proposals()
    ensure_company_files()


def cached_market_snapshot(ttl_minutes=20):
    return feature_cached_market_snapshot(ttl_minutes=ttl_minutes)


def cached_korea_market_data(date, ttl_minutes=60):
    return feature_cached_korea_market_data(date, ttl_minutes=ttl_minutes)


def build_briefing(
    date=None,
    strict_date=False,
    web_search_override=None,
    llm_override=None,
    persist=True,
    quality_mode="diagnose_only",
    market_scope="both",
    briefing_type="default",
    markets=None,
    kind="daily",
    task_policy_snapshot=None,
):
    if isinstance(task_policy_snapshot, dict):
        with bind_task_policy(task_policy_snapshot):
            return build_daily_briefing(
                date=date,
                strict_date=strict_date,
                web_search_override=web_search_override,
                llm_override=llm_override,
                persist=persist,
                quality_mode=quality_mode,
                market_scope=market_scope,
                briefing_type=briefing_type,
                markets=markets,
                kind=kind,
            )
    return build_daily_briefing(
        date=date,
        strict_date=strict_date,
        web_search_override=web_search_override,
        llm_override=llm_override,
        persist=persist,
        quality_mode=quality_mode,
        market_scope=market_scope,
        briefing_type=briefing_type,
        markets=markets,
        kind=kind,
    )


def analyze_company(q, web_search_override=None, llm_override=None, analysis_style="beginner", task_policy_snapshot=None):
    context = bind_task_policy(task_policy_snapshot) if isinstance(task_policy_snapshot, dict) else nullcontext()
    with context:
        return generate_company_analysis(
        q,
        web_search_override=web_search_override,
        llm_override=llm_override,
        analysis_style=analysis_style,
        runtime={
            "load_index": load_index,
            "search_documents": search_documents,
            "infer_requested_company": infer_requested_company,
            "build_company_analysis_materials": build_company_analysis_materials,
            "build_company_analysis_charts": build_company_analysis_charts,
            "generate_llm_company_analysis": generate_llm_company_analysis,
            "build_rule_report": build_rule_report,
            "company_analysis_sources": company_analysis_sources,
            "selected_llm_config": selected_llm_config,
        },
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    # 거래소가 붙은 SEC 목록을 한 번 받아 둔다. 없으면 dual-listed 유럽·일본 기업이
    # 상장 라인과 원주 OTC 라인으로 갈려 전부 "애매"로 떨어진다.
    schedule_sec_exchange_cache()
    # 인덱스를 미리 읽어 둔다. 첫 사용자가 6초를 기다리는 대신 시작 직후 조용히 치른다 —
    # 대시보드 이야기 비중이 앱을 켜고 처음 열 때 13.9초 걸리던 것이 이 때문이었다.
    warm_index_cache()
    schedule_startup_regime_refresh(MARKET_MEMORY_DB_PATH)
    schedule_automation_loop()
    start_signal_runtime(DATA_DIR, CONFIG_DIR / "evidence_sources.yaml")
    await TOSS_REALTIME_HUB.start()
    try:
        yield
    finally:
        await TOSS_REALTIME_HUB.stop()
        stop_signal_runtime()
        close_diagnostics_runtime()


fastapi_app = FastAPI(title="Folio OS", version=APP_VERSION, lifespan=lifespan)
TOSS_REALTIME_HUB = TossRealtimeHub()
SMART_COLLECTION_SERVICE = create_smart_collection_service(DATA_DIR)
TOPIC_APPROVAL_BOUNDARY = ApprovedRequestBoundary(
    DATA_DIR,
    collection_service=SMART_COLLECTION_SERVICE,
)
fastapi_app.include_router(TOPIC_APPROVAL_BOUNDARY.router(include_preflight=False))
fastapi_app.include_router(SmartCollectionBoundary(SMART_COLLECTION_SERVICE).router())
fastapi_app.include_router(
    AgentCompanionBoundary(
        SMART_COLLECTION_SERVICE,
        data_dir=DATA_DIR,
    ).router()
)
fastapi_app.include_router(create_market_state_router(DATA_DIR))
fastapi_app.include_router(create_intelligence_router(DATA_DIR))
fastapi_app.include_router(
    create_investment_context_router(
        DATA_DIR,
        collection_service=SMART_COLLECTION_SERVICE,
    )
)
fastapi_app.include_router(jobs_router)
fastapi_app.include_router(
    create_diagnostics_router(
        runtime_provider=diagnostics_runtime,
        job_lookup=diagnostic_job_lookup,
        run_lookup=diagnostic_authority_for_run,
        authority_provider=default_authority_snapshot,
        )
)
fastapi_app.include_router(work_log_router)
fastapi_app.include_router(
    create_retention_router(
        runtime_provider=diagnostics_runtime,
        authority_provider=default_authority_snapshot,
    )
)
fastapi_app.include_router(create_signal_router(DATA_DIR))
fastapi_app.include_router(create_dashboard_router(DATA_DIR))
fastapi_app.include_router(create_market_calendar_router(DATA_DIR))
fastapi_app.include_router(create_market_data_router(DATA_DIR, realtime_hub=TOSS_REALTIME_HUB))
fastapi_app.include_router(create_portfolio_router(DATA_DIR))


@fastapi_app.get("/api/health")
def api_health():
    return health_payload(ROOT)


@fastapi_app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    # ``request`` is present in FastAPI, but keeping this boundary defensive
    # also preserves the existing direct-handler regression harness.
    request_id = getattr(getattr(request, "state", None), "folio_request_id", None)
    headers: dict[str, str] = {}
    if isinstance(request_id, str):
        headers["X-Folio-Request-Id"] = request_id
        try:
            run_id = diagnostics_runtime().observe_unhandled_http(request_id, exc)
        except Exception:
            run_id = None
        if isinstance(run_id, str):
            headers["X-Folio-Run-Id"] = run_id
    return JSONResponse({"error": "internal_server_error"}, status_code=500, headers=headers)


@fastapi_app.middleware("http")
async def no_store_for_local_app(request: Request, call_next):
    request_id = "req_" + str(uuid.uuid4())
    request.state.folio_request_id = request_id
    with bind_request_id(request_id):
        response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Folio-Request-Id", request_id)
    return response


def query_lists(request: Request):
    return {key: request.query_params.getlist(key) for key in request.query_params.keys()}


def _task_request_context(payload: dict | None, task_key: str) -> tuple[dict, str]:
    """Resolve a fresh policy for a public HTTP request.

    ``_task_policy_snapshot`` is an internal handoff field used only after a
    job has been accepted.  Treating a request body value as an already
    trusted snapshot would turn it into an undocumented one-run override and
    let a caller select an unsaved model or bypass the global gate.  Queued
    and continuation workers pass their snapshot directly to the feature or
    bridge boundary instead.
    """
    snapshot = task_snapshot(task_key)
    # Keep the one-argument request_generation_mode seam used by older callers
    # and source tests while carrying the immutable snapshot through it.
    mode = request_generation_mode({"_task_policy_snapshot": snapshot})
    return snapshot, mode


def request_generation_mode(_payload: dict | None) -> str:
    payload = _payload if isinstance(_payload, dict) else {}
    frozen = payload.get("_task_policy_snapshot")
    if isinstance(frozen, dict):
        return task_generation_mode(frozen)
    return default_generation_mode()


def _run_task_thesis_delta(task_policy: dict, ticker: str, payload: dict) -> dict:
    with bind_task_policy(task_policy):
        return run_thesis_delta(ticker, payload)


def canonical_write_http_error(exc: Exception) -> HTTPException:
    """Canonical 커밋 예외를 HTTP로 옮긴다.

    동시 커밋(제안 승인·예약 생성)이나 정체성 불일치는 서버 고장이 아니라 충돌이다.
    500으로 나가면 화면이 "다시 시도"밖에 말할 수 없다. 포트폴리오 409와 같은 모양으로
    `{"code": ...}`를 실어 화면이 무엇이 어긋났는지 말할 수 있게 한다.
    """
    return HTTPException(
        status_code=409,
        detail={"code": getattr(exc, "code", "canonical_write_failed"), "message": str(exc)},
    )


_RESTART_REQUESTED = False

# 재시작 신호. **3을 쓰지 않는다** — `uvicorn.config.STARTUP_FAILURE`가 3이라
# 포트 충돌을 비롯한 모든 uvicorn 시작 실패가 같은 코드로 끝난다. 런처는 그것을
# 재시작 신호로 읽어 무한히 다시 띄웠다: 시작 → 바인드 실패(exit 3) → "Restarting..."
# → 시작 → … (실측으로 이미 서버가 떠 있을 때 `py -3 app.py`가 exit 3을 냈다).
RESTART_EXIT_CODE = 7


def schedule_server_restart(delay: float = 0.5):
    """Exit with RESTART_EXIT_CODE so start.ps1 / start.sh can restart the process.

    A guard prevents multiple simultaneous restart requests.
    """
    global _RESTART_REQUESTED
    if _RESTART_REQUESTED:
        return
    _RESTART_REQUESTED = True

    def _exit():
        time.sleep(delay)
        os._exit(RESTART_EXIT_CODE)

    threading.Thread(target=_exit, daemon=True).start()


@fastapi_app.get("/api/rss/items")
def api_rss_items(request: Request):
    return rss_feed_payload(query_lists(request))


@fastapi_app.get("/api/rss/merge")
def api_rss_merge(request: Request):
    filename, merged = rss_merge_payload(query_lists(request))
    return Response(
        content=merged,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@fastapi_app.post("/api/server/restart")
def api_restart_server():
    schedule_server_restart()
    return {"ok": True, "message": "서버 재시작을 시작했습니다. 잠시 후 페이지를 다시 불러오세요."}


@fastapi_app.get("/api/dashboard")
def api_dashboard():
    idx = load_index()
    news_docs = news_documents(idx)
    news_idx = index_from_documents(idx, news_docs)
    return {
        "index": {
            "generatedAt": idx["generatedAt"],
            "count": idx["count"],
            "newsCount": len(news_docs),
            "inbox": idx["inbox"],
        },
        "companies": list_companies(news_idx)[:20],
        "briefings": list_briefings()[:20],
        "watchlist": get_watchlist(),
        "notes": list_investment_notes(limit=10, include_body=True),
        "recent": news_docs[:12],
    }


@fastapi_app.get("/api/market-widgets/settings")
def api_get_market_widget_settings():
    return get_market_widget_settings()


@fastapi_app.post("/api/market-widgets/settings")
def api_save_market_widget_settings(body: dict | None = Body(default=None)):
    return save_market_widget_settings(body or {})


@fastapi_app.get("/api/search")
def api_search(request: Request):
    qs = query_lists(request)
    idx = load_index()
    return search_documents(
        idx,
        query=qs.get("query", [""])[0],
        company=qs.get("company", [""])[0],
        limit=int(qs.get("limit", [50])[0] or 50),
        scope=qs.get("scope", ["news"])[0],
    )


@fastapi_app.get("/api/briefings")
def api_list_briefings():
    return list_briefings()


@fastapi_app.get("/api/briefings/index")
def api_briefing_archive_index(
    q: str = "",
    marketScope: str = "all",
    briefingType: str = "all",
    kind: str = "all",
    dateFrom: str = "",
    dateTo: str = "",
    offset: int = 0,
    limit: int = 20,
):
    try:
        return query_briefing_archive(
            q=q,
            market_scope=marketScope,
            briefing_type=briefingType,
            kind=kind,
            date_from=dateFrom,
            date_to=dateTo,
            offset=offset,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid briefing query") from exc


@fastapi_app.post("/api/briefings")
def api_create_briefing(body: dict | None = Body(default=None)):
    body = body or {}
    automation_settings = read_automation_settings()
    prerequisites = {}
    # 손으로 만드는 브리핑은 어느 스케줄에도 속하지 않는다. 켜 둔 스케줄 중
    # 하나라도 수집을 원하면 수집한다(싱글톤이던 시절 동작과 같다).
    task_policy, generation_mode = _task_request_context(body, "daily_briefing")
    # CLI submission keeps its pre-existing eager prerequisite collection.
    # Direct generation moves it inside the feature-owned diagnostic context.
    # 시장 다중 선택. 없으면 예전 단일 범위로 해석한다. 날짜 변환은 선택된
    # 시장 집합에 달려 있으므로 여기서 먼저 확정한다.
    requested_markets = list(
        normalize_market_selection(body.get("markets") or body.get("marketScope", "both"))
    )
    # 무엇에 대한 브리핑인지를 **먼저** 정한다. 화면의 날짜는 발행일이 아니라 그 시장의
    # 세션일이며, 성립하지 않는 요청은 여기서 거부한다 — 08-10 08:02에 08-10 한국장을
    # 요청하면 아직 열리지도 않은 장이고, 그것을 금요일 종가로 메운 것이 지난 사고였다.
    from features.common.market_calendar import publication_date_groups
    from features.daily_briefing.target import resolve_targets, resolve_weekly_targets

    requested_date = str(body.get("date") or "").strip()
    briefing_kind = normalize_briefing_kind(body.get("kind"))
    if briefing_kind == "weekly":
        # 주간은 세션 판정을 태우지 않는다. 주말 발행이 정상인 산출물을 "그날은 거래일이
        # 아니다"로 막으면 주간 브리핑을 손으로 만들 길이 아예 없다.
        targets, target_errors = resolve_weekly_targets(
            requested_markets, publication_date=requested_date
        )
    else:
        targets, target_errors = resolve_targets(requested_markets, session_date=requested_date)
    accepted = [target.market for target in targets]
    if not accepted:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_valid_briefing_target",
                "markets": [
                    {"market": err.market, "reason": err.reason, "message": str(err)}
                    for err in target_errors
                ],
            },
        )
    skipped = [
        {"market": err.market, "reason": err.reason, "message": str(err)}
        for err in target_errors
    ]
    # 앵커는 **아직** 발행일이다. 자료 창과 분석 모드가 발행일에 걸려 있어서(Phase 4가
    # 옮긴다) 여기서 세션일을 앵커로 바꾸면 내용이 조용히 달라진다 — 특히 주말 생성은
    # 직전 세션으로 앵커가 내려가 off-session 뉴스 창을 잃는다. target은 지금은 판정과
    # 거부만 소유하고, 앵커 계산은 기존 경로를 그대로 쓴다.
    if briefing_kind == "weekly":
        # 주간의 발행일은 하나다. 시장마다 세션 마감 시각이 달라 갈리는 것은 일간 얘기이고,
        # 주간 창은 달력 7일이라 네 시장이 같은 발행일을 쓴다.
        date_groups = [(targets[0].publication_date, accepted)]
    else:
        date_groups = (
            publication_date_groups(requested_date, accepted)
            if requested_date else [(kst_date(), accepted)]
        )
    from features.daily_briefing.news_selection_runtime import pin_selection_context
    selection_contexts = {date: pin_selection_context(date, markets, briefing_kind) for date, markets in date_groups}
    if generation_mode == "llm_cli" and automation_wants_prerequisites(automation_settings):
        prerequisites = run_briefing_prerequisites()
    if generation_mode == "llm_cli":
        jobs = [
            submit_agent_task("briefing", {
                "date": date,
                "strict_date": body.get("strictDate", False),
                "quality_mode": body.get("qualityMode", "diagnose_only"),
                "market_scope": market_selection_scope(markets),
                "markets": markets,
                "briefing_type": body.get("briefingType", "default"),
                "kind": briefing_kind,
                # 규칙 경로의 web_search_override와 **같은 값**이 도착해야 한다(§6 규칙 14).
                # `is True`로 접지 않는다 — None은 pack 빌더가 설정으로 푼다.
                "web_search": bool_override(body.get("webSearch")),
                "selection_context": selection_contexts[date],
                "_task_policy_snapshot": task_policy,
            }, adapter=body.get("agentAdapter", ""))
            for date, markets in date_groups
        ]
        if len(jobs) == 1:
            if prerequisites and isinstance(jobs[0], dict):
                jobs[0]["prerequisites"] = prerequisites
            if skipped and isinstance(jobs[0], dict):
                jobs[0]["skippedMarkets"] = skipped
            return jobs[0]
        # 발행일이 갈렸다. 작업이 둘이라는 사실을 숨기지 않는다 — 하나만 돌려주면
        # 화면이 그것만 기다리다 나머지가 끝나기 전에 다 됐다고 말한다.
        payload = {"jobs": jobs}
        if prerequisites:
            payload["prerequisites"] = prerequisites
        if skipped:
            payload["skippedMarkets"] = skipped
        return payload
    reports, prerequisites = run_direct_briefings(
        wants_prerequisites=automation_wants_prerequisites(automation_settings),
        run_prerequisites=run_briefing_prerequisites,
        build=build_briefing,
        build_requests=[
            {
                "date": date,
                "strict_date": body.get("strictDate", False),
                "web_search_override": bool_override(body.get("webSearch")),
                "selection_context": selection_contexts[date],
                "llm_override": llm_override_for_mode(generation_mode),
                "quality_mode": body.get("qualityMode", "diagnose_only"),
                "market_scope": market_selection_scope(markets),
                "markets": markets,
                "briefing_type": body.get("briefingType", "default"),
                "kind": briefing_kind,
                "task_policy_snapshot": task_policy,
            }
            for date, markets in date_groups
        ],
    )
    if len(reports) == 1:
        if prerequisites and isinstance(reports[0], dict):
            reports[0]["prerequisites"] = prerequisites
        if skipped and isinstance(reports[0], dict):
            reports[0]["skippedMarkets"] = skipped
        return reports[0]
    payload = {"reports": reports}
    if prerequisites:
        payload["prerequisites"] = prerequisites
    if skipped:
        payload["skippedMarkets"] = skipped
    return payload


@fastapi_app.get("/api/briefings/{date}")
def api_get_briefing(date: str, includePersonal: bool = False, marketScope: str = "both", kind: str = "daily"):
    try:
        briefing = resolve_briefing(date, marketScope, kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid briefing identifier or market scope") from exc
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return strip_overlay(briefing_scope_view(briefing, marketScope), includePersonal)


@fastapi_app.delete("/api/briefings/{date}")
def api_delete_briefing(date: str, market: str = "", kind: str = "daily"):
    try:
        result = delete_briefing(date, market=market or None, kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid briefing identifier or market scope") from exc
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return result


@fastapi_app.get("/api/briefings/{date}/visuals")
def api_get_briefing_visuals(date: str, market: str = "", marketScope: str = "", kind: str = ""):
    payload = load_visual_sidecar(date, BRIEFINGS_DIR, market_scope=market or marketScope, kind=kind)
    if payload is None:
        raise HTTPException(status_code=404, detail="Briefing visuals not found")
    return payload


@fastapi_app.get("/api/briefings/{date}/visuals/current")
def api_get_briefing_current_visuals(date: str, market: str = "", snapshotId: str = ""):
    payload = load_current_visuals(
        date,
        BRIEFINGS_DIR,
        market=market,
        snapshot_id=snapshotId,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return payload


@fastapi_app.post("/api/briefings/{date}/personal-overlay")
def api_briefing_personal_overlay(date: str, marketScope: str = "both", kind: str = "daily", body: dict | None = Body(default=None)):
    body = body or {}
    requested_scope = body.get("marketScope") or marketScope
    # **종류를 받지 않으면 주간 보고서의 개인 해석이 그날 일간 보고서에 얹힌다.**
    # 주간의 저장 키는 발행일이라 같은 날 일간과 날짜가 겹친다.
    requested_kind = normalize_briefing_kind(body.get("kind") or kind)
    task_policy, generation_mode = _task_request_context(body, "personal_overlay")
    if generation_mode == "llm_cli":
        return submit_agent_task("personal_overlay", {
            "report_kind": "briefing",
            # CLI 경로는 report id로 파일을 되짚으므로 종류 접미사를 id에 실어 보낸다
            # (`canonical_identity.BRIEFING_KIND_SUFFIXES`가 그 형태를 안다).
            "report_id": date if requested_kind == "daily" else f"{date}.{requested_kind}",
            "market_scope": requested_scope,
            "_task_policy_snapshot": task_policy,
        }, adapter=body.get("agentAdapter", ""))
    try:
        def _generate_overlay():
            with bind_task_policy(task_policy):
                return attach_overlay_to_briefing(
                    date, market_scope=requested_scope, kind=requested_kind,
                    llm_override=llm_override_for_mode(generation_mode),
                    web_search_override=bool_override(body.get("webSearch")),
                )
        return run_direct_overlay(_generate_overlay)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Briefing not found")
    except (CanonicalConflictError, CanonicalValidationError, CanonicalIdentityError) as exc:
        raise canonical_write_http_error(exc) from exc


@fastapi_app.get("/api/content-revisions")
def api_content_revisions():
    """저장소별 마지막 변경 시각. 화면이 목록을 다시 읽을 시점을 판단한다.

    파일 mtime만 읽으므로 몇 초 간격 폴링에도 부담이 없다.
    """
    return {"revisions": content_revisions(DATA_DIR)}


@fastapi_app.get("/api/company/resolve")
def api_company_resolve(request: Request):
    """입력이 어느 기업인지 판단한다. 규칙과 로컬 색인만 쓰며 LLM을 호출하지 않는다."""
    qs = query_lists(request)
    query = qs.get("q", qs.get("query", [""]))[0]
    try:
        limit = max(1, min(12, int(qs.get("limit", ["6"])[0])))
    except ValueError:
        limit = 6
    # `prefer=home`은 원주와 ADR이 갈릴 때 자국 상장을 대표로 세운다. 워치리스트가
    # 쓴다 — 기업분석은 SEC 등록분이라야 companyfacts와 10-K가 붙는다.
    prefer_home = qs.get("prefer", [""])[0].strip().lower() == "home"
    return resolve_company_query(query, limit=limit, prefer_home=prefer_home)


@fastapi_app.get("/api/analyze")
def api_analyze(request: Request):
    qs = query_lists(request)
    quality_mode = normalize_quality_mode(qs.get("qualityMode", ["diagnose_only"])[0])
    task_policy, generation_mode = _task_request_context({}, "company_analysis")
    query = qs.get("q", [""])[0]
    analysis_style = normalize_analysis_style(qs.get("analysisStyle", qs.get("analysis_style", ["beginner"]))[0])
    # **두 경로가 웹 검색을 같은 방법으로 정한다.** 예전에는 CLI만 `is True`로 접어서
    # 파라미터가 없으면(화면은 보내지 않는다) 하드 오프였고, 바로 아래 API 경로는
    # 같은 `None`을 설정값으로 풀어 켜졌다 — 같은 요청이 경로에 따라 정반대가 된다.
    # 실측으로 로컬 문서 0건인 회사의 CLI 보고서에 `webLookup`이 없고 `sourceLedger`가
    # 0건이었다. 자료 공백을 메우는 유일한 경로가 그 설치에서 죽어 있었다(§6 규칙 14).
    web_search = bool_override(qs.get("webSearch", [None])[0])
    if generation_mode == "llm_cli":
        return submit_agent_task("company_analysis", {
            "query": query,
            "quality_mode": quality_mode,
            "analysis_style": analysis_style,
            "web_search": use_web_search_for_analysis() if web_search is None else web_search,
            "_task_policy_snapshot": task_policy,
        }, adapter=qs.get("agentAdapter", [""])[0])
    return run_direct_analysis(
        query=query,
        web_search_override=web_search,
        llm_override=llm_override_for_mode(generation_mode),
        analysis_style=analysis_style,
        quality_mode=quality_mode,
        generate=lambda *args, **kwargs: analyze_company(
            *args, task_policy_snapshot=task_policy, **kwargs
        ),
        apply_quality=apply_quality_loop,
        apply_ceiling=apply_company_report_ceiling,
        save=save_analysis_report,
    )


@fastapi_app.get("/api/analysis-reports")
def api_list_analysis_reports():
    return list_analysis_reports()


@fastapi_app.post("/api/analysis-reports")
def api_save_analysis_report(body: dict | None = Body(default=None)):
    report = body or {}
    if not report.get("quality"):
        try:
            report["quality"] = evaluate_research_quality_payload({"artifactType": "company_analysis", "artifact": report})["quality"]
        except Exception:
            pass
    return save_analysis_report(report)


@fastapi_app.get("/api/analysis-reports/{report_id}")
def api_get_analysis_report(report_id: str, includePersonal: bool = False):
    report = get_analysis_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    if not report.get("quality") or "sourceGrounding" not in report.get("quality", {}):
        # 열람은 저장물을 바꾸지 않는다 — 배지는 응답에만 계산해 싣는다. 예전에는 여기서
        # recheck가 파일을 직접 덮어써 canonicalRevision 지문을 깨뜨렸다. 영구 backfill은
        # POST /api/research-quality/recheck(정식 커밋 배관)만 한다.
        try:
            report["quality"] = evaluate_research_artifact("company_analysis", report)
        except Exception:
            report["quality"] = {"status": "warn", "warnings": ["quality evaluation failed"]}
    return strip_overlay(report, includePersonal)


@fastapi_app.post("/api/analysis-reports/{report_id}/personal-overlay")
def api_analysis_personal_overlay(report_id: str, body: dict | None = Body(default=None)):
    body = body or {}
    task_policy, generation_mode = _task_request_context(body, "personal_overlay")
    if generation_mode == "llm_cli":
        return submit_agent_task("personal_overlay", {
            "report_kind": "company_analysis",
            "report_id": report_id,
            "_task_policy_snapshot": task_policy,
        }, adapter=body.get("agentAdapter", ""))
    try:
        def _generate_overlay():
            with bind_task_policy(task_policy):
                return attach_overlay_to_report(
                    report_id, llm_override=llm_override_for_mode(generation_mode),
                    web_search_override=bool_override(body.get("webSearch")),
                )
        return run_direct_overlay(_generate_overlay)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Analysis report not found")
    except (CanonicalConflictError, CanonicalValidationError, CanonicalIdentityError) as exc:
        raise canonical_write_http_error(exc) from exc


@fastapi_app.get("/api/theses")
def api_list_theses(status: str = ""):
    return list_thesis_payload(status=status or None)


@fastapi_app.get("/api/memory/verification")
def api_memory_verification(status: str = "current", limit: int = 20):
    """내러티브 검증 상태(구조화 체크포인트 판정·무소식·판정 이력) 읽기 전용 projection."""
    return narrative_verification_payload(status=status or "current", limit=max(1, min(int(limit or 20), 50)))


@fastapi_app.get("/api/theses/{ticker}/workspace")
def api_thesis_workspace(ticker: str):
    """Watchlist 상세의 종목 Thesis workspace payload(저장된 projection만 읽는다)."""
    return thesis_workspace_payload(ticker)


@fastapi_app.post("/api/theses")
def api_upsert_thesis(body: dict | None = Body(default=None)):
    """Obsidian 없이 앱 안에서 Thesis를 만들고 고친다. 보낸 키만 덮는다(부분 갱신)."""
    try:
        return {"ok": True, "thesis": upsert_manual_thesis(body or {})}
    except (ValueError, TypeError) as e:
        # 리스트 필드에 스칼라가 오는 것 같은 형식 오류도 400이다 — 500은 호출자에게
        # 고칠 단서를 주지 않는다.
        raise HTTPException(status_code=400, detail=str(e)) from e


@fastapi_app.get("/api/theses/{ticker}")
def api_get_thesis(ticker: str):
    return thesis_detail_payload(ticker)


@fastapi_app.post("/api/investment-notes/{note_id}/thesis")
def api_promote_note_to_thesis(note_id: str, body: dict | None = Body(default=None)):
    """이 노트로 Thesis 만들기/갱신 — 명시적 action만 기존 Thesis를 덮는다(§8.2).

    덮겠다는 의사는 요청의 `overwrite`가 싣는다. 서버 기본이 덮기면 화면 캐시가
    낡았을 때 남의 thesis가 확인 없이 덮인다.
    """
    try:
        return promote_note_to_thesis(note_id, overwrite=bool((body or {}).get("overwrite")))
    except LookupError as e:
        raise HTTPException(status_code=404, detail="Note not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@fastapi_app.post("/api/theses/{ticker}/delta")
def api_run_thesis_delta(ticker: str, body: dict | None = Body(default=None)):
    body = body or {}
    task_policy, generation_mode = _task_request_context(body, "thesis_review")
    if generation_mode == "llm_cli":
        return submit_agent_task("thesis_delta", {
            "ticker": ticker,
            "period": body.get("period", "90d"),
            "limit": body.get("evidenceLimit", body.get("limit", 12)),
            "_task_policy_snapshot": task_policy,
        }, adapter=body.get("agentAdapter", ""))
    body["useLlm"] = llm_override_for_mode(generation_mode)
    try:
        return run_direct_thesis_delta(
            ticker,
            body,
            generate=lambda symbol, payload: _run_task_thesis_delta(
                task_policy, symbol, payload
            ),
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail="Thesis not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid thesis request") from e


@fastapi_app.delete("/api/analysis-reports/{report_id}")
def api_delete_analysis_report(report_id: str):
    try:
        result = delete_analysis_report(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid company analysis identifier") from exc
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Analysis report not found")
    return result


@fastapi_app.post("/api/briefings/{date}/export-notion")
def api_export_briefing_notion(date: str, marketScope: str = "both", kind: str = "daily", body: dict | None = Body(default=None)):
    body = body or {}
    requested_scope = body.get("marketScope") or marketScope
    try:
        briefing = resolve_briefing(date, requested_scope, body.get("kind") or kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid briefing identifier or market scope") from exc
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    chart_images = body.get("chartImages") or None
    try:
        return export_briefing(date, briefing_scope_view(briefing, requested_scope), chart_images=chart_images)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Notion export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Notion 내보내기에 실패했습니다.") from e


@fastapi_app.post("/api/export-notion/analysis")
def api_export_analysis_notion(body: dict | None = Body(default=None)):
    body = body or {}
    report = {k: v for k, v in body.items() if k != "chartImages"}
    if not report.get("markdown") and not report.get("headline"):
        raise HTTPException(status_code=400, detail="분석 보고서 내용이 없습니다.")
    try:
        return export_analysis(report, chart_images=body.get("chartImages") or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Notion export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Notion 내보내기에 실패했습니다.") from e


@fastapi_app.post("/api/export-notion/topic-report")
def api_export_topic_report_notion(body: dict | None = Body(default=None)):
    body = body or {}
    report = {k: v for k, v in body.items() if k != "chartImages"}
    if not report.get("markdown") and not report.get("topicLabel"):
        raise HTTPException(status_code=400, detail="테마분석 보고서 내용이 없습니다.")
    try:
        return export_topic_report(report, chart_images=body.get("chartImages") or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Notion export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Notion 내보내기에 실패했습니다.") from e


@fastapi_app.get("/api/obsidian/settings")
def api_get_obsidian_settings():
    return get_vault_settings()


@fastapi_app.post("/api/obsidian/settings")
def api_save_obsidian_settings(body: dict | None = Body(default=None)):
    vault_path = (body or {}).get("vaultPath", "")
    return save_vault_settings(vault_path)


@fastapi_app.post("/api/obsidian-workflow/create-note")
def api_obsidian_workflow_create_note(body: dict | None = Body(default=None)):
    body = body or {}
    try:
        return create_workflow_note(
            str(body.get("templateType") or ""),
            body.get("context") if isinstance(body.get("context"), dict) else {},
            overwrite=bool(body.get("overwrite")),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian workflow request") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 노트 생성에 실패했습니다.") from e


@fastapi_app.get("/api/obsidian-workflow/note")
def api_obsidian_workflow_read_note(templateType: str = "", ticker: str = "", topic: str = "", label: str = ""):
    try:
        return read_workflow_note(templateType, {"ticker": ticker, "topic": topic, "label": label})
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian workflow request") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 노트 조회에 실패했습니다.") from e


@fastapi_app.get("/api/obsidian-workflow/linked-notes")
def api_obsidian_workflow_linked_notes(ticker: str = "", topic: str = ""):
    try:
        return linked_notes_payload(ticker=ticker, topic=topic)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian workflow request") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 연결 노트 조회에 실패했습니다.") from e


@fastapi_app.get("/api/obsidian-workflow/validate")
def api_obsidian_workflow_validate():
    try:
        return validate_workflow_notes()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian workflow request") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian frontmatter 검사에 실패했습니다.") from e


@fastapi_app.post("/api/briefings/{date}/export-obsidian")
def api_export_briefing_obsidian(date: str, marketScope: str = "both", kind: str = "daily", body: dict | None = Body(default=None)):
    body = body or {}
    requested_scope = body.get("marketScope") or marketScope
    try:
        briefing = resolve_briefing(date, requested_scope, body.get("kind") or kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid briefing identifier or market scope") from exc
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    try:
        return export_briefing_to_obsidian(
            date,
            briefing_scope_view(briefing, requested_scope),
            chart_images=body.get("chartImages") or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 내보내기에 실패했습니다.") from e


@fastapi_app.post("/api/export-obsidian/analysis")
def api_export_analysis_obsidian(body: dict | None = Body(default=None)):
    report = body or {}
    if not report.get("markdown") and not report.get("headline"):
        raise HTTPException(status_code=400, detail="분석 보고서 내용이 없습니다.")
    try:
        return export_analysis_to_obsidian(report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 내보내기에 실패했습니다.") from e


@fastapi_app.post("/api/export-obsidian/topic-report")
def api_export_topic_report_obsidian(body: dict | None = Body(default=None)):
    report = body or {}
    if not report.get("markdown"):
        raise HTTPException(status_code=400, detail="테마 보고서 내용이 없습니다.")
    try:
        return export_topic_report_to_obsidian(report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 내보내기에 실패했습니다.") from e


@fastapi_app.post("/api/export-obsidian/narratives")
def api_export_narratives_obsidian():
    try:
        return export_narratives_to_obsidian()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid Obsidian export settings") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Obsidian 내보내기에 실패했습니다.") from e


@fastapi_app.get("/api/watchlist")
def api_get_watchlist():
    return get_watchlist()


@fastapi_app.post("/api/watchlist")
def api_save_watchlist(body: dict | None = Body(default=None)):
    body = body or {}
    return save_watchlist(body.get("items", []))


@fastapi_app.get("/api/watchlist/resolve")
def api_resolve_watchlist_keyword(request: Request):
    qs = query_lists(request)
    keyword = normalize_watchlist_keyword(qs.get("keyword", [""])[0])
    return {"keyword": keyword or ""}


@fastapi_app.get("/api/watchlist/overview")
def api_watchlist_overview():
    return watchlist_overview()


@fastapi_app.get("/api/watchlist/detail")
def api_watchlist_detail(request: Request):
    qs = query_lists(request)
    item = qs.get("item", [""])[0]
    limit = int(qs.get("limit", ["12"])[0] or 12)
    return watchlist_detail(item, limit=min(max(limit, 1), 50))


@fastapi_app.get("/api/notes")
def api_get_notes():
    return list_investment_notes(limit=100, include_body=True)


@fastapi_app.post("/api/notes")
def api_add_note(body: dict | None = Body(default=None)):
    return add_investment_note(body or {})


@fastapi_app.get("/api/investment-notes")
def api_list_investment_notes(
    ticker: str = "",
    topic: str = "",
    noteType: str = "",
    q: str = "",
    limit: int = 50,
    includeBody: bool = False,
):
    return list_investment_notes(
        ticker=ticker,
        topic=topic,
        note_type=noteType,
        q=q,
        limit=limit,
        include_body=includeBody,
    )


@fastapi_app.get("/api/investment-notes/linked")
def api_linked_investment_notes(ticker: str = "", topic: str = "", reportId: str = ""):
    return native_linked_notes_payload(ticker=ticker, topic=topic, report_id=reportId)


@fastapi_app.get("/api/investment-notes/{note_id}")
def api_get_investment_note(note_id: str):
    note = get_investment_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Investment note not found")
    return note


@fastapi_app.post("/api/investment-notes")
def api_save_investment_note(body: dict | None = Body(default=None)):
    return save_investment_note(body or {})


@fastapi_app.get("/api/settings")
def api_get_settings(refresh: bool = False):
    try:
        return public_settings(refresh=refresh)
    except TaskPolicyError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)}) from exc


@fastapi_app.post("/api/settings")
def api_save_settings(body: dict | None = Body(default=None)):
    try:
        return save_settings(body or {})
    except TaskPolicyError as exc:
        detail = {"code": exc.code, "message": str(exc)}
        if exc.latest is not None:
            detail["latest"] = exc.latest
        raise HTTPException(status_code=exc.status, detail=detail) from exc


@fastapi_app.get("/api/settings/task-policies")
def api_get_task_policies():
    try:
        return public_task_policy()
    except TaskPolicyError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)}) from exc


@fastapi_app.post("/api/settings/task-policies")
def api_save_task_policies(body: dict | None = Body(default=None)):
    try:
        return save_task_policy(body or {})
    except TaskPolicyError as exc:
        detail = {"code": exc.code, "message": str(exc)}
        if exc.latest is not None:
            detail["latest"] = exc.latest
        raise HTTPException(status_code=exc.status, detail=detail) from exc


@fastapi_app.post("/api/settings/task-policies/check")
def api_check_task_policy(body: dict | None = Body(default=None)):
    try:
        config = (body or {}).get("config") if isinstance(body, dict) else None
        return check_task_policy(config)
    except TaskPolicyError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": str(exc)}) from exc


@fastapi_app.get("/api/automation/settings")
def api_automation_settings():
    return read_automation_settings()


@fastapi_app.post("/api/automation/settings")
def api_save_automation_settings(body: dict | None = Body(default=None)):
    return save_automation_settings(body or {})


@fastapi_app.get("/api/automation/runs")
def api_automation_runs(limit: int = 20):
    return {"items": list_automation_runs(limit)}


@fastapi_app.post("/api/automation/run/{kind}")
def api_run_automation(kind: str):
    return run_automation_once(kind)


@fastapi_app.post("/api/settings/llm/test/{provider}")
def api_test_llm_provider(provider: str):
    try:
        return check_llm_api_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid LLM provider") from exc


@fastapi_app.get("/api/cache/stats")
def api_cache_stats():
    return cache_stats()


@fastapi_app.post("/api/cache/cleanup")
def api_cache_cleanup():
    return cleanup_cache()


@fastapi_app.get("/api/market/snapshot")
def api_market_snapshot():
    return fetch_market_snapshot()


@fastapi_app.get("/api/research-data/checkpoints")
def api_research_data_checkpoints(artifactType: str = "", artifactId: str = ""):
    return checkpoints_payload(artifactType, artifactId)


@fastapi_app.get("/api/research-data/evidence")
def api_research_data_evidence(artifactType: str = "", artifactId: str = ""):
    return evidence_payload(artifactType, artifactId)


@fastapi_app.get("/api/research-data/source-ledger")
def api_research_data_source_ledger(artifactType: str = "", artifactId: str = ""):
    return source_ledger_payload(artifactType, artifactId)


@fastapi_app.get("/api/research-data/data-gaps")
def api_research_data_data_gaps(artifactType: str = "", artifactId: str = ""):
    return data_gaps_payload(artifactType, artifactId)


@fastapi_app.get("/api/research-data/market-tape")
def api_research_data_market_tape(artifactType: str = "", artifactId: str = "", date: str = ""):
    if artifactType and artifactId:
        return market_tape_payload(artifactType, artifactId, date=date)
    target_date = date or kst_date()
    from features.common.market_calendar import briefing_market_windows
    return {
        "artifactType": artifactType,
        "artifactId": artifactId,
        "marketTape": build_market_tape(
            date=target_date,
            market_snapshot=cached_market_snapshot(),
            korea_market_data=cached_korea_market_data(target_date),
            market_windows=briefing_market_windows(target_date),
        ),
    }


@fastapi_app.get("/api/data-reliability/provider-status")
def api_data_reliability_provider_status():
    return provider_status_payload()


@fastapi_app.post("/api/data-reliability/provider-status")
def api_data_reliability_record_provider_status(body: dict | None = Body(default=None)):
    return record_provider_status_payload((body or {}).get("records") or [])


@fastapi_app.get("/api/data-reliability/market-data-files")
def api_data_reliability_market_data_files():
    return market_data_files_payload()


@fastapi_app.post("/api/research-quality/evaluate")
def api_research_quality_evaluate(body: dict | None = Body(default=None)):
    return evaluate_research_quality_payload(body or {})


@fastapi_app.get("/api/research-quality/{artifact_type}/{artifact_id}")
def api_research_quality_get(artifact_type: str, artifact_id: str):
    try:
        return get_research_quality(artifact_type, artifact_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")


@fastapi_app.post("/api/research-quality/recheck/{artifact_type}/{artifact_id}")
def api_research_quality_recheck(artifact_type: str, artifact_id: str):
    try:
        return recheck_research_quality(artifact_type, artifact_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Artifact not found")
    except (CanonicalConflictError, CanonicalValidationError, CanonicalIdentityError) as exc:
        raise canonical_write_http_error(exc) from exc


@fastapi_app.post("/api/quality-generation/preflight")
def api_quality_generation_preflight(body: dict | None = Body(default=None)):
    return quality_generation_preflight_payload(body or {})


@fastapi_app.post("/api/quality-generation/repair")
def api_quality_generation_repair(body: dict | None = Body(default=None)):
    body = body or {}
    generation_mode = request_generation_mode(body)
    if generation_mode == "llm_cli":
        return submit_agent_task("quality_repair", {
            "artifact_type": body.get("artifactType") or body.get("artifact_type"),
            "artifact_id": body.get("artifactId") or body.get("artifact_id"),
        }, adapter=body.get("agentAdapter", ""))
    if generation_mode == "rules":
        return quality_generation_run_payload({**body, "qualityMode": "diagnose_only"})
    return quality_generation_repair_payload(body)


@fastapi_app.post("/api/quality-generation/run")
def api_quality_generation_run(body: dict | None = Body(default=None)):
    return quality_generation_run_payload(body or {})


@fastapi_app.get("/api/investment-review")
def api_investment_review():
    return get_investment_review()


@fastapi_app.post("/api/investment-review/generate")
def api_investment_review_generate(body: dict | None = Body(default=None)):
    body = body or {}
    try:
        # date는 캐시 파일 경로가 되므로 두 분기(CLI/규칙) 모두 여기서 먼저 형식을 막는다.
        body["date"] = normalize_review_date(body.get("date"))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_review_date")
    # The Portfolio's "오늘 리뷰 갱신" is an explicit local rules action.
    # Do not let a global CLI default silently turn it into a background job.
    task_policy, generation_mode = _task_request_context(body, "investment_review")
    # The explicit rules action remains deterministic.  The persisted task
    # policy controls the AI producer route when the caller did not request
    # that local action explicitly.
    if body.get("generationMode") == "rules":
        generation_mode = "rules"
    if generation_mode == "llm_cli":
        return submit_agent_task("investment_review", {
            "date": body.get("date"),
            "include_portfolio": body.get("includePortfolio", True),
            "include_watchlist": body.get("includeWatchlist", True),
            "include_obsidian": body.get("includeObsidian", True),
            "_task_policy_snapshot": task_policy,
        }, adapter=body.get("agentAdapter", ""))
    body["useLlm"] = llm_override_for_mode(generation_mode)
    try:
        return run_direct_review(body, generate=generate_investment_review)
    except ReviewRevisionConflict as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "latest": exc.latest})


@fastapi_app.get("/api/investment-review/history")
def api_investment_review_history():
    return get_investment_review_history()


@fastapi_app.get("/api/investment-review/{date}")
def api_investment_review_by_date(date: str):
    try:
        return get_investment_review(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_review_date")


@fastapi_app.post("/api/investment-review/{date}/reviewed")
def api_investment_review_reviewed(date: str, body: dict | None = Body(default=None)):
    try:
        return mark_investment_review_reviewed(date, (body or {}).get("expectedReviewRevision"))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_review_date")
    except ReviewRevisionConflict as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "latest": exc.latest})


@fastapi_app.get("/api/agent-bridge/status")
def api_agent_bridge_status(refresh: bool = False):
    return bridge_status(refresh=refresh)


@fastapi_app.get("/api/agent-bridge/preflight")
def api_agent_bridge_preflight(adapter: str = ""):
    try:
        return agent_preflight(adapter=adapter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsupported agent adapter") from exc


@fastapi_app.get("/api/agent/proposals/{proposal_id}")
def api_agent_proposal(proposal_id: str):
    try:
        proposal = get_proposal(proposal_id)
    except ProposalActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "proposal_read_failed"}) from exc
    if proposal is None:
        raise HTTPException(status_code=404, detail={"code": "proposal_not_found"})
    return proposal


@fastapi_app.post("/api/agent/proposals/{proposal_id}")
def api_agent_proposal_action(proposal_id: str, body: ProposalActionRequest):
    try:
        if body.action == ProposalAction.APPROVE:
            return apply_proposal(proposal_id)
        return reject_proposal(proposal_id)
    except ProposalActionError as exc:
        if exc.status_code >= 500:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "proposal_apply_failed"}) from exc


@fastapi_app.get("/api/agent-bridge/settings")
def api_agent_bridge_settings(refresh: bool = False):
    return agent_cli_settings_payload(refresh=refresh)


@fastapi_app.post("/api/agent-bridge/settings")
def api_save_agent_bridge_settings(body: dict | None = Body(default=None)):
    try:
        return save_agent_cli_settings(body or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Agent settings") from exc


@fastapi_app.post("/api/agent-bridge/install/{adapter}")
def api_install_agent_cli(adapter: str):
    try:
        return submit_agent_cli_install(adapter)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Agent CLI installation request failed") from exc


@fastapi_app.post("/api/agent-bridge/login/{adapter}")
def api_login_agent_cli(adapter: str):
    try:
        return launch_agent_cli_login(adapter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Agent CLI login request") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Agent CLI login could not be started") from exc


@fastapi_app.get("/api/index/documents")
def api_index_documents(company: str = "", limit: int = 50, offset: int = 0):
    return list_indexed_documents(company=company, limit=min(limit, 200), offset=offset)


@fastapi_app.post("/api/index")
def api_build_index(body: dict | None = Body(default=None)):
    body = body or {}
    return submit_job(
        "index",
        "자료 폴더 다시 읽기",
        build_index,
        incremental=body.get("incremental", True),
    )


@fastapi_app.post("/api/rssarchive/import")
def api_import_rssarchive():
    return submit_job(
        "rss",
        "RSS 수집/가져오기",
        import_rssarchive,
        run_collection=True,
    )


@fastapi_app.get("/api/rss/retention")
def api_rss_retention(days: str = ""):
    """`days`를 주면 그 기간으로 세어 본다 — 저장하기 전에 무엇이 지워지는지 보여준다."""
    from features.common.research_library.rss.retention import (
        RETENTION_CHOICES,
        preview,
        reclaimable_bytes,
    )
    from features.common.research_library.rss.service import rss_retention_days

    chosen = days.strip()
    return {
        "choices": list(RETENTION_CHOICES),
        "saved": rss_retention_days(),
        # 지울 자료가 없어도 돌려받을 공간은 있을 수 있다. 버튼이 무엇을 할지 말해야 한다.
        "reclaimableBytes": reclaimable_bytes(),
        **preview(chosen if chosen else rss_retention_days()),
    }


@fastapi_app.post("/api/rss/retention/run")
def api_run_rss_retention():
    from features.common.research_library.rss.service import run_retention_now

    return submit_job("rss", "오래된 RSS 자료 정리", run_retention_now)


@fastapi_app.get("/api/market-scope")
def api_get_market_scope():
    from features.common.market_scope import MARKET_LABELS, MARKETS, load_market_scope

    scope = load_market_scope()
    return {**scope, "markets": [{"id": m, "label": MARKET_LABELS[m]} for m in MARKETS]}


@fastapi_app.put("/api/market-scope")
def api_put_market_scope(body: dict = Body(default={})):
    from features.common.market_scope import MARKET_LABELS, MARKETS, save_market_scope
    from features.common.research_library.rss.service import collect_markets_now

    scope, newly_enabled = save_market_scope((body or {}).get("selected") or [])
    payload = {**scope, "markets": [{"id": m, "label": MARKET_LABELS[m]} for m in MARKETS], "newlyEnabled": newly_enabled}
    if newly_enabled:
        # 방금 켠 시장은 즉시 수집한다. RSS는 피드가 내어주는 최근 항목까지만
        # 받을 수 있으므로, 꺼져 있던 기간의 공백이 남을 수 있다.
        payload["collectionJob"] = submit_job(
            "rss",
            f"{'·'.join(MARKET_LABELS[m] for m in newly_enabled)} 시장 자료 수집",
            collect_markets_now,
            markets=newly_enabled,
        )
    return payload


@fastapi_app.get("/api/onboarding")
def api_get_onboarding():
    from features.onboarding.service import onboarding_status

    return onboarding_status()


@fastapi_app.post("/api/onboarding/complete")
def api_complete_onboarding(body: dict = Body(default={})):
    from features.onboarding.service import complete_onboarding

    return complete_onboarding(skipped=bool((body or {}).get("skipped")))


@fastapi_app.get("/api/workspace")
def api_get_workspace():
    from features.common.workspace_service import workspace_payload

    return workspace_payload()


@fastapi_app.post("/api/workspace/move")
def api_move_workspace(body: dict = Body(default={})):
    from features.common.workspace_service import WorkspaceMoveError, move_workspace

    try:
        return move_workspace(
            str((body or {}).get("destination") or ""),
            merge=bool((body or {}).get("merge")),
        )
    except WorkspaceMoveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@fastapi_app.post("/api/workspace/reveal")
def api_reveal_workspace():
    from features.common.workspace_service import WorkspaceMoveError, reveal_workspace

    try:
        return reveal_workspace()
    except WorkspaceMoveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@fastapi_app.get("/api/memory")
def api_list_memory(request: Request):
    qs = query_lists(request)
    return list_memory(
        MARKET_MEMORY_DB_PATH,
        limit=int(qs.get("limit", [50])[0] or 50),
        story=qs.get("story", [""])[0],
    )


@fastapi_app.post("/api/memory")
def api_upsert_memory(body: dict | None = Body(default=None)):
    return upsert_memory(MARKET_MEMORY_DB_PATH, body or {})


@fastapi_app.delete("/api/memory/{memory_id}")
def api_delete_memory(memory_id: str):
    result = delete_memory(MARKET_MEMORY_DB_PATH, memory_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return result


@fastapi_app.post("/api/memory/llm")
def api_run_llm_market_memory(body: dict | None = Body(default=None)):
    body = body or {}
    task_policy, generation_mode = _task_request_context(body, "market_memory")
    if generation_mode == "llm_cli":
        return submit_agent_task("market_memory_llm", {
            "date": body.get("date") or kst_date(),
            "_task_policy_snapshot": task_policy,
        }, adapter=body.get("agentAdapter", ""))
    if generation_mode == "rules":
        return {
            "ok": True,
            "status": "rules",
            "saved": [],
            "message": "규칙 기반 내러티브 후보는 브리핑 생성 시 자동으로 누적됩니다.",
        }
    def _generate_market_memory(date):
        with bind_task_policy(task_policy):
            return run_llm_market_memory(date)
    return run_direct_market_memory(
        body.get("date") or kst_date(), generate=_generate_market_memory
    )


@fastapi_app.post("/api/memory/rss-digest")
def api_memory_rss_digest(body: dict | None = Body(default=None)):
    body = body or {}
    return run_rss_market_memory_update(date=body.get("date", ""))


@fastapi_app.get("/api/memory/states")
def api_list_memory_states(request: Request):
    qs = query_lists(request)
    return list_states(
        MARKET_MEMORY_DB_PATH,
        limit=int(qs.get("limit", [50])[0] or 50),
        status=qs.get("status", ["current"])[0],
    )


@fastapi_app.post("/api/memory/states/{state_id}")
def api_update_memory_state(state_id: str, body: dict | None = Body(default=None)):
    return update_state(MARKET_MEMORY_DB_PATH, state_id, body or {})


@fastapi_app.post("/api/memory/regime/refresh")
def api_refresh_memory_regimes(body: dict | None = Body(default=None)):
    body = body or {}
    state_id = body.get("stateId") or body.get("state_id") or ""
    days = int(body.get("days") or 90)
    if state_id:
        result = refresh_regime_state(MARKET_MEMORY_DB_PATH, state_id, days=days)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("error") or "State not found")
        return result
    return refresh_all_regimes(
        MARKET_MEMORY_DB_PATH,
        status=body.get("status") or "current",
        limit=int(body.get("limit") or 30),
        days=days,
    )


@fastapi_app.get("/api/memory/states/{state_id}/evidence")
def api_memory_regime_evidence(state_id: str, limit: int = 50):
    return list_regime_evidence(MARKET_MEMORY_DB_PATH, state_id, limit=min(int(limit or 50), 200))


@fastapi_app.get("/api/memory/states/{state_id}/changes")
def api_memory_regime_changes(state_id: str, limit: int = 30):
    return list_regime_changes(MARKET_MEMORY_DB_PATH, state_id, limit=min(int(limit or 30), 100))


@fastapi_app.get("/api/memory/states/{state_id}/thesis-links")
def api_memory_regime_thesis_links(state_id: str):
    return list_regime_thesis_links(MARKET_MEMORY_DB_PATH, state_id)


@fastapi_app.post("/api/memory/states/{state_id}/thesis-links")
def api_upsert_memory_regime_thesis_link(state_id: str, body: dict | None = Body(default=None)):
    try:
        return upsert_regime_thesis_link(MARKET_MEMORY_DB_PATH, state_id, body or {})
    except LookupError as e:
        raise HTTPException(status_code=404, detail="Market state not found") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid market-state request") from e


@fastapi_app.get("/api/memory/taxonomy")
def api_memory_taxonomy(request: Request):
    qs = query_lists(request)
    return list_taxonomy(
        MARKET_MEMORY_DB_PATH,
        term_type=qs.get("type", [""])[0],
        limit=int(qs.get("limit", [50])[0] or 50),
    )


@fastapi_app.get("/api/memory/story-links")
def api_memory_story_links(request: Request):
    qs = query_lists(request)
    return list_story_links(
        MARKET_MEMORY_DB_PATH,
        story=qs.get("story", [""])[0],
        limit=int(qs.get("limit", [50])[0] or 50),
    )


@fastapi_app.get("/api/memory/story-map")
def api_memory_story_map(request: Request):
    qs = query_lists(request)
    return story_map(MARKET_MEMORY_DB_PATH, limit=int(qs.get("limit", [80])[0] or 80))


@fastapi_app.get("/api/memory/suggestions")
def api_memory_suggestions(request: Request):
    qs = query_lists(request)
    return list_family_suggestions(
        MARKET_MEMORY_DB_PATH,
        status=qs.get("status", ["suggested"])[0],
        limit=int(qs.get("limit", [50])[0] or 50),
    )


@fastapi_app.post("/api/memory/suggestions/{suggestion_id}")
def api_review_memory_suggestion(suggestion_id: str, body: dict | None = Body(default=None)):
    body = body or {}
    return review_family_suggestion(
        MARKET_MEMORY_DB_PATH,
        suggestion_id,
        body.get("action", "reject"),
    )


@fastapi_app.get("/api/memory/audit")
def api_memory_audit(request: Request):
    qs = query_lists(request)
    return audit_memory(MARKET_MEMORY_DB_PATH, days=int(qs.get("days", [30])[0] or 30))


@fastapi_app.get("/api/memory/report")
def api_memory_report(request: Request):
    qs = query_lists(request)
    return memory_report(MARKET_MEMORY_DB_PATH, limit=int(qs.get("limit", [8])[0] or 8))


@fastapi_app.get("/api/topic-reports/presets")
def api_topic_report_presets():
    return preset_topics_list()


@fastapi_app.get("/api/topic-reports")
def api_list_topic_reports():
    return list_topic_reports()


@fastapi_app.post("/api/topic-reports")
def api_generate_topic_report(body: dict | None = Body(default=None)):
    return TOPIC_APPROVAL_BOUNDARY.preflight(body or {})


@fastapi_app.get("/api/topic-reports/{report_id}")
def api_get_topic_report(report_id: str, includePersonal: bool = False):
    report = get_topic_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Topic report not found")
    if not report.get("quality") or "sourceGrounding" not in report.get("quality", {}):
        # 열람은 저장물을 바꾸지 않는다 — 배지는 응답에만 계산해 싣는다(위 기업분석 GET과 동일).
        try:
            report["quality"] = evaluate_research_artifact("topic_report", report)
        except Exception:
            report["quality"] = {"status": "warn", "warnings": ["quality evaluation failed"]}
    return strip_overlay(report, includePersonal)


@fastapi_app.post("/api/topic-reports/{report_id}/evaluate")
def api_evaluate_topic_report(report_id: str):
    try:
        return evaluate_topic_report(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Topic report not found")


@fastapi_app.post("/api/topic-reports/{report_id}/personal-overlay")
def api_topic_report_personal_overlay(report_id: str, body: dict | None = Body(default=None)):
    body = body or {}
    task_policy, generation_mode = _task_request_context(body, "personal_overlay")
    if generation_mode == "llm_cli":
        return submit_agent_task("personal_overlay", {
            "report_kind": "topic_report",
            "report_id": report_id,
            "_task_policy_snapshot": task_policy,
        }, adapter=body.get("agentAdapter", ""))
    try:
        def _generate_overlay():
            with bind_task_policy(task_policy):
                return attach_overlay_to_topic_report(
                    report_id, llm_override=llm_override_for_mode(generation_mode),
                    web_search_override=bool_override(body.get("webSearch")),
                )
        return run_direct_overlay(_generate_overlay)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Topic report not found")


@fastapi_app.delete("/api/topic-reports/{report_id}")
def api_delete_topic_report(report_id: str):
    try:
        result = delete_topic_report(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid topic report identifier") from exc
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Topic report not found")
    return result


fastapi_app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")


def _port_owner_message(host: str, port: int) -> str:
    """포트가 이미 쓰이고 있으면 사람이 읽을 문장을, 비어 있으면 빈 문자열을 돌려준다.

    같은 Folio OS가 이미 떠 있는 경우가 대부분이라 그 사실을 먼저 확인한다. 두 번
    켜는 것은 실수가 아니라 흔한 일이고(창을 닫지 않고 .cmd를 다시 누른다), 그때
    필요한 답은 "이미 켜져 있으니 그 주소를 여세요"다.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError:
        pass
    else:
        return ""
    finally:
        probe.close()

    address = f"http://127.0.0.1:{port}"
    mine = False
    try:
        import urllib.request

        with urllib.request.urlopen(f"{address}/api/onboarding", timeout=3) as response:
            mine = 200 <= response.status < 300
    except Exception:
        mine = False

    if mine:
        return (
            f"Folio OS is already running. Open {address} in your browser.\n"
            "Close the other Folio OS window first if you want to restart it."
        )
    return (
        f"Port {port} is already in use by another program, so Folio OS cannot start.\n"
        "Close that program, or start Folio OS on another port: set PORT=8788 before running."
    )


def main():
    ensure_dirs()
    load_jobs()
    if os.environ.get("STARTUP_REINDEX", "0").strip().lower() in {"1", "true", "yes", "on"}:
        build_index()
    else:
        load_index()
    port = int(os.environ.get("PORT", "8787"))
    host = os.environ.get("FOLIO_HOST", "127.0.0.1").strip() or "127.0.0.1"

    print("Folio OS starting...")
    # `localhost`가 아니라 127.0.0.1을 안내한다. Windows에서 localhost는 ::1을 먼저
    # 시도하는데 서버는 IPv4 루프백만 열어 두므로, 새 연결마다 폴백까지 약 2초를
    # 기다린다(실측: localhost 2.02초 / 127.0.0.1 0.01초). 화면 전환이 느리다고
    # 느껴지던 주된 이유가 이것이다 — 모든 요청이 그 2초를 냈다.
    print(f"Open this address on this PC: http://127.0.0.1:{port}")

    if host == "0.0.0.0":
        print(f"LAN access enabled. Open from your phone: http://<PC_LOCAL_IP>:{port}")
    else:
        print("LAN access disabled. Set FOLIO_HOST=0.0.0.0 to access from another device.")

    print("RSS collection is embedded in this Python app.")

    # 포트를 먼저 잡아 본다. **uvicorn이 실패하면 종료 코드가 3인데 그것은 예전
    # 재시작 신호와 같은 값이었다** — 런처가 무한히 다시 띄웠다. 코드를 갈랐어도
    # 여기서 미리 확인하는 편이 낫다: 이미 켜져 있다는 사실을 말할 수 있고,
    # uvicorn의 영어 소켓 오류 대신 무엇을 해야 하는지 알려줄 수 있다.
    already = _port_owner_message(host, port)
    if already:
        print(already)
        raise SystemExit(1)

    import uvicorn
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
