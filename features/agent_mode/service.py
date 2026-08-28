from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path

from features.agent_mode import schema as A
from features.agent_mode.hypothesis_context import build_hypothesis_review_context
from features.agent_mode.briefing_contract import (
    briefing_contract_violations,
    briefing_output_contract,
)
from features.common.utils import kst_date, now_iso, read_json, write_json
from features.common.dataframe_ops import top_records
from features.common.research_library.indexing.service import IMPACT_TERMS, build_index, load_index
from features.common.research_library.search.service import group_docs, search_documents
from features.common.market_data.snapshot import fetch_market_snapshot
from features.common.market_data.providers import fetch_korea_market_data
from features.common.market_data.tape import build_market_tape
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.common.research_schema.data_gaps import data_gap_applies_to, data_gaps_from_messages
from features.common.research_schema.evidence import evidence_items_from_list
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.common.company_lookup import infer_requested_company
from features.common.quality_generation.loop import apply_quality_loop
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.preflight_enrichment import build_preflight_evidence_context
from features.common.quality_generation.prompt_hints import render_prompt_hints
from features.common.quality_generation.quality_targets import render_quality_target_context
from features.common.quality_generation.schema import normalize_quality_mode
from features.daily_briefing.limits import (
    ISSUE_COVERAGE_LIMIT,
    source_ref_limit,
)
from features.daily_briefing.source_window import scope_session_documents
from features.daily_briefing.source_integrity import reconcile_source_ledger, source_manifest_prompt
from features.daily_briefing.claim_integrity import enforce_claim_integrity
from features.daily_briefing.style_check import briefing_style_check
from features.daily_briefing.weekly_visuals import collect_weekly_visuals
from features.daily_briefing.weekly import (
    calendar_preview,
    render_calendar_preview,
    weekly_documents,
    weekly_title,
    weekly_window as build_weekly_window,
)
from features.daily_briefing.service import (
    MARKET_LABELS,
    resolve_briefing_by_session,
    append_briefing_sources,
    strip_markdown_sources_section,
    briefing_checkpoint_headings,
    briefing_sources_from_headlines,
    build_llm_context,
    briefing_prompt_path_label,
    extract_prev_checklist,
    group_digest,
    load_prev_briefing,
    news_documents,
    prioritized_source_refs,
    read_briefing_prompt,
    select_briefing_docs,
    source_refs,
)
from features.daily_briefing.selection import (
    derive_market_drivers,
    infer_market_session_date,
    prioritize_briefing_groups,
    session_doc_counts,
)
from features.daily_briefing.issue_selection import (
    build_issue_coverage,
    doc_ref as issue_doc_ref,
    documents_for_scope,
    public_issue_coverage,
    session_modes_from_windows,
)
from features.daily_briefing.concentration.runtime import (
    finalize_concentration,
    prepare_concentration,
    render_concentration_context,
)
from features.daily_briefing.builder import _scope_session_date
from features.daily_briefing.schema import (
    DEFAULT_BRIEFING_KIND,
    briefing_expected_titles,
    briefing_file_name,
    MARKET_TAGS,
    market_keys_for_briefing_scope,
    market_selection_scope,
    normalize_market_selection,
    briefing_scope_view,
    enrich_briefing_sections,
    merge_briefing_report,
    normalize_briefing_kind,
    normalize_briefing_type,
    normalize_market_scope,
    split_market_markdown,
    visual_sidecar_gzip_file_name,
)
from features.daily_briefing.visuals import (
    collect_briefing_visuals,
    leading_company_subjects_from_markdown,
    replace_leading_company_visuals,
    write_visual_sidecar,
)
from features.market_memory.memory import build_memory_from_briefing, list_briefing_memories, upsert_memory
from features.market_memory.market_state_ref import MarketStateRefQuery, resolve_market_state_ref
from features.market_memory.service import (
    build_memory_llm_context,
    normalize_llm_memory_entry,
    read_market_memory_prompt,
)
from features.market_memory.snapshot import (
    MARKET_STATE_SNAPSHOT_PROMPT,
    build_market_state_context,
    save_market_state_snapshot,
    validate_market_state_snapshot,
)
from features.company_analysis.service import (
    ANALYSIS_REPORTS_DIR,
    build_company_analysis_charts,
    build_company_analysis_materials,
    company_analysis_sources,
    company_external_search_context,
    get_analysis_report,
    read_company_analysis_prompt,
    save_analysis_report,
)
from features.company_analysis.data_gap_resolver import resolve_company_analysis_gaps
from features.company_analysis.finalize import finalize_report as finalize_company_report
from features.company_analysis.generation_context import (
    build_generation_inputs,
    draft_artifact as company_draft_artifact,
)
from features.company_analysis.style import (
    REQUIRED_SECTION_HEADINGS as COMPANY_REQUIRED_SECTIONS,
    analysis_prompt_path,
    normalize_analysis_style,
)
from features.topic_report.data_fetcher import fetch_topic_market_data
from features.topic_report.evaluation import evaluate_report
from features.topic_report.evidence import build_evidence_pack, evidence_pack_summary
from features.topic_report.macro_data import fetch_macro_data
from features.topic_report.service import (
    _build_llm_context as build_topic_llm_context,
    _doc_sources as topic_doc_sources,
    _search_docs as topic_search_docs,
    _search_memories as topic_search_memories,
    _read_prompt as read_topic_prompt,
)
from features.topic_report.source_ledger import build_source_ledger
from features.topic_report.templates import compose_prompt
from features.topic_report.topic_config import get_topic_config
from features.topic_report.planner import apply_deep_research_plan, build_topic_plan
from features.topic_report.service import save_topic_report
from features.llm_settings.client import bok_api_key, fred_api_key, use_web_search_for_briefing
from features.common.canonical_identity import split_briefing_id
from features.personal_overlay import schema as overlay_schema
from features.personal_overlay.service import (
    _briefing_overlay_path,
    _build_context as overlay_build_context,
    _gather_hypotheses,
    read_prompt as read_overlay_prompt,
    with_overlay,
)
from features.thesis_tracking import delta as thesis_delta
from features.thesis_tracking import review_state as thesis_review_state
from features.thesis_tracking import store as thesis_store
from features.thesis_tracking.service import get_thesis
from features.common.research_quality.evaluator import evaluate_artifact
from features.common.research_schema.service import load_artifact
from features.investment_review.service import REVIEW_DIR, build_review
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
BRIEFINGS_DIR = DATA_DIR / "briefings"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"


def _items_for_market(items, scope):
    target = str(scope or "").upper()
    return [
        deepcopy(item) for item in (items or [])
        if str(item.get("market") or "").upper() in {target, "BOTH", ""}
    ]


def _sidecar_for_market(sidecar, scope):
    target = str(scope or "").upper()
    out = deepcopy(sidecar or {})
    out["marketScope"] = scope
    out["snapshots"] = {
        key: value for key, value in deepcopy((sidecar or {}).get("snapshots") or {}).items()
        if str(value.get("market") or "").upper() in {target, "BOTH"}
    }
    return out


def _single_market_briefing(briefing, scope):
    scoped = briefing_scope_view(briefing, scope)
    scoped["marketScope"] = scope
    scoped["briefings"] = {}
    scoped["visualRecommendations"] = _items_for_market(briefing.get("visualRecommendations"), scope)
    scoped["visualSnapshots"] = _items_for_market(briefing.get("visualSnapshots"), scope)
    scoped["marketDrivers"] = [
        deepcopy(item) for item in (briefing.get("marketDrivers") or [])
        if str(item.get("market") or "").lower() in {scope, "both", ""}
    ]
    scoped["issueCoverage"] = [
        deepcopy(item) for item in (briefing.get("issueCoverage") or [])
        if str(item.get("market") or "").lower() in {scope, "both", ""}
    ]
    scoped["dataGaps"] = [
        deepcopy(item) for item in (briefing.get("dataGaps") or [])
        if data_gap_applies_to(item, scope)
    ]
    stats = deepcopy(scoped.get("stats") or {})
    stats["marketScope"] = scope
    stats["visualSnapshotCount"] = len(scoped.get("visualSnapshots") or [])
    scoped["stats"] = stats
    return scoped


def _cache_json(path: Path, ttl_seconds: int, fetcher):
    """`ttl_seconds`를 실제로 지킨다.

    예전에는 이 인자를 받고 **한 번도 쓰지 않았다.** 호출부가 3600을 넘기고 있어서 한
    시간 TTL이 있는 것처럼 보였지만, 캐시 파일이 있으면 나이를 보지 않고 그대로 돌려줬다.
    그래서 08-10 08:02(개장 전)에 받은 금요일 종가가 08-10 수치로 영구히 굳었다.
    """
    cached = read_json(path, None)
    if isinstance(cached, dict):
        payload = cached.get("snapshot") or cached.get("marketData") or cached
        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(cached.get("cachedAt", ""))).total_seconds()
            if age < ttl_seconds:
                return payload
        except (TypeError, ValueError):
            # 나이를 알 수 없는 캐시는 신선하다고 볼 근거가 없다. 다시 받는다.
            pass
    value = fetcher()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = "marketData" if "korea-market-data" in path.name else "snapshot"
    write_json(path, {"cachedAt": now_iso(), key: value})
    return value


def cached_market_snapshot():
    return _cache_json(DATA_DIR / "market-snapshot.json", 1200, fetch_market_snapshot)


def cached_korea_market_data(date: str, market_windows=None):
    """규칙 경로와 **같은** 정책을 쓴다. 두 벌이던 캐시가 서로 다르게 동작했다.

    `None`일 수 있다 — 그 세션 수치를 못 받았다는 뜻이며, 직전 세션 값으로 메우지 않는다.
    """
    from features.common.market_data.korea_session import korea_market_data, session_state

    payload, _reason = korea_market_data(date, session_state(market_windows))
    return payload


def _briefing_headlines(groups):
    headlines = []
    for i, g in enumerate(groups[:4], 1):
        subject = g["company"] or g["sector"]
        docs_sorted = top_records(g["docs"], ["marketRelevance", "sourceWeight"], 6, descending=True)
        tags = sorted(set(sum([d.get("sectors", []) + d.get("impactTags", []) for d in docs_sorted], [])))[:8]
        variable = ", ".join([t for t in tags if t in IMPACT_TERMS][:3]) or "실적, 수급, 밸류에이션"
        title = f"{subject}, {variable} 변수가 시장 기대를 재조정"
        body = (
            f"{subject} 관련 뉴스는 {', '.join(sorted(set(d['source'] for d in docs_sorted))[:4])} 자료에서 확인됩니다. "
            f"{group_digest(g, 2)} 핵심은 {variable}이 투자자 기대를 움직일 수 있다는 점입니다. "
            "후속 공시, 컨퍼런스콜 발언, 거래대금, 외국인·기관 수급이 함께 따라오는지 확인해야 합니다."
        )
        headlines.append({
            "id": f"h{i}",
            "title": title,
            "body": body,
            "tags": tags,
            "sources": [
                {
                    "title": d["title"],
                    "source": d["source"],
                    "date": d["date"],
                    "url": d.get("url", ""),
                    "path": d["path"],
                    "type": d["type"],
                }
                for d in docs_sorted
            ],
        })
    return headlines


class WeeklyWindowEmptyError(ValueError):
    """주간 창에 자료가 하나도 없다. CLI를 부르기 전에 멈춘다."""


def _write_pack(pack: dict, owner_job_id: str | None) -> Path:
    if owner_job_id is None:
        return A.write_pack(pack)
    return A.write_pack(pack, owner_job_id=owner_job_id)


def prepare_briefing_pack(date: str | None = None, *, strict_date=False, quality_mode="diagnose_only", market_scope="both", briefing_type="default", markets=None, kind=DEFAULT_BRIEFING_KIND, web_search=None, owner_job_id: str | None = None) -> tuple[dict, Path]:
    generated_at = now_iso()
    date = date or kst_date()
    kind = normalize_briefing_kind(kind)
    ref_limit = source_ref_limit(kind)
    week = build_weekly_window(date) if kind == "weekly" else None
    quality_mode = normalize_quality_mode(quality_mode)
    requested_markets = normalize_market_selection(
        markets if markets is not None else market_scope
    )
    market_scope = market_selection_scope(requested_markets)
    briefing_type = normalize_briefing_type(briefing_type)
    try:
        build_index(incremental=True)
    except Exception:
        pass
    today = kst_date()
    index = load_index()
    all_documents = news_documents(index)
    docs, source_date, market_windows = select_briefing_docs(
        all_documents, date, strict=bool(strict_date), today=today,
        as_of=generated_at,
    )
    # 자료 창을 시장별 세션에서 파생한다. 예전에는 발행일 하나에서 나온 union을 모든
    # 시장이 공유했다. 한 pack이 여러 시장을 담을 수 있으므로(같은 발행일 그룹) 풀은
    # 시장별 창의 합집합이고, 시장 태그 필터가 그다음을 좁힌다.
    scope_docs = {
        target: (
            weekly_documents(all_documents, week) if week is not None
            else scope_session_documents(
                all_documents, target, market_windows, today=today,
                session_date=_scope_session_date(target, market_windows),
            )
        )
        for target in requested_markets
    }
    session_pool = []
    seen_keys = set()
    for rows in scope_docs.values():
        for row in rows:
            key = row.get("path") or row.get("url") or (row.get("title"), row.get("date"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            session_pool.append(row)
    # 창이 비면 예전 풀로 되돌아간다. 창을 좁히는 변경이 브리핑을 지우면 안 된다.
    # 주간은 되돌아가지 않는다 — 창을 넓히면 "지난주"라는 말이 거짓이 된다.
    docs = session_pool if week is not None else (session_pool or docs)
    if week is not None:
        source_date = f"{week.week_start}~{week.week_end}"
        if not docs:
            # **자료가 없으면 CLI를 부르지 않는다.** 주간은 창이 비어도 넓히지 않으므로
            # 수집이 한 주 내내 꺼져 있었으면 여기가 0건이다. 그대로 pack을 만들면 CLI가
            # 근거 없이 쓰고, 출력 계약의 최소 분량에 걸려 재작성 1회 뒤 실패한다 —
            # 한 번에 수십 초가 걸리는 CLI를 두 번 돌리고 아무것도 남기지 못한다
            # (2026-08-12에 같은 모양으로 45분을 버린 기록이 이 모듈에 남아 있다).
            raise WeeklyWindowEmptyError(
                f"{week.week_start}~{week.week_end} 구간에 수집된 자료가 없습니다. "
                "RSS 수집 상태를 확인한 뒤 다시 만드세요."
            )
    for doc in docs:
        doc["marketSessionDate"] = infer_market_session_date(doc, market_windows)
    scoped_docs = documents_for_scope(docs, market_scope)
    groups = prioritize_briefing_groups(group_docs(scoped_docs), market_windows, limit=6, market_scope=market_scope)
    session_modes = session_modes_from_windows(market_windows)
    # 시장별 문서를 한 번만 고른다. 아래 동인·참고자료·시각자료가 모두 이것을 쓴다.
    market_docs = {
        target: documents_for_scope(scope_docs.get(target) or docs, target)
        for target in requested_markets
    }
    concentration_by_market = {}
    effective_groups_by_market = {}
    for target in requested_markets:
        target_groups = prioritize_briefing_groups(
            group_docs(market_docs[target]), market_windows, limit=6, market_scope=target,
        )
        effective_groups, control = prepare_concentration(
            target_groups,
            market_scope=target,
            kind=kind,
            report_date=date,
            reports_dir=BRIEFINGS_DIR,
            # Agent pack preparation normally runs while bridge._RUN_SEMAPHORE is held.
            agent_serialize=False,
        )
        effective_groups_by_market[target] = effective_groups
        if control:
            concentration_by_market[target] = control
    if requested_markets == ["kr"]:
        groups = effective_groups_by_market["kr"]
    # **동인과 참고자료는 시장마다 다르다.** 예전에는 합쳐진 풀로 한 번만 만들어 네 시장
    # 보고서가 같은 동인과 같은 참고자료를 실었다. 동인에는 시장을 붙여야 저장 시
    # `_single_market_briefing`의 필터가 그 시장 것만 남긴다 — 시장이 비어 있으면
    # 모든 시장을 통과한다.
    market_drivers = []
    issue_coverage_raw = []
    sources_by_market = {}
    for target in requested_markets:
        target_docs = market_docs[target]
        # builder와 같은 계약 — KR 일간만 응집 분해를 켠다. 한쪽만 켜면 같은 날
        # 두 생성 경로가 다른 이슈 클러스터를 먹는다.
        target_issues = build_issue_coverage(
            target_docs, target.upper(), market_windows, limit=ISSUE_COVERAGE_LIMIT,
            coherence_policy=(target == "kr" and week is None),
        )
        issue_coverage_raw.extend(target_issues)
        for driver in derive_market_drivers(target_docs, market_windows, limit=4):
            market_drivers.append({**driver, "market": target})
        target_sources = prioritized_source_refs(
            target_docs, market_windows, limit=ref_limit, issue_coverage=target_issues, market_scope=target,
        ) or briefing_sources_from_headlines(
            _briefing_headlines(prioritize_briefing_groups(group_docs(target_docs), market_windows, limit=6, market_scope=target)),
            limit=ref_limit,
        )
        sources_by_market[target] = source_refs(target_sources, limit=ref_limit)
    visual_scope_results = {}
    for target in requested_markets:
        target_docs = market_docs[target]
        visual_scope_results[target] = {
            # 세션 기준일은 빌더와 같은 규칙을 쓴다. 여기서 따로 고르면 Agent 경로만
            # 유럽·일본에 한국 세션일을 찍는다.
            "marketSessionDate": _scope_session_date(target, market_windows),
            "groups": effective_groups_by_market[target],
        }
    try:
        if week is not None:
            # 세션 스냅샷은 싣지 않고(§builder와 같은 규칙) 주 단위 계열을 만든다.
            # **pack 단계에서 만든다** — A·B·C는 본문 내용이 아니라 창·지수·자료 풀에서
            # 나오므로 CLI 답을 기다릴 이유가 없고, 규칙 경로와 같은 계약이 된다.
            # 문서 풀은 **중복 제거된 것**을 넘긴다. 시장별 리스트를 이어 붙이면 주간
            # 풀이 시장 수만큼 복제돼 이야기 비중의 표본 수가 N배로 부풀고, 표본 부족
            # 경고(MIN_CONFIDENT_SAMPLE)가 조용히 사라진다 — 규칙 경로는 한 번만 넘긴다.
            visual_result = collect_weekly_visuals(
                week, market_scope,
                documents=docs,
                markets=requested_markets,
            )
        else:
            visual_result = collect_briefing_visuals(date, market_scope, visual_scope_results, markets=list(visual_scope_results))
    except Exception:
        visual_result = {
            "visualRecommendations": [], "visualSnapshots": [], "sidecar": {},
            "warnings": ["visual_snapshot_collection_failed"],
        }
    market_snapshot = cached_market_snapshot()
    # 규칙 생성과 같은 기준이다 — 발행일이 아니라 한국장 세션일로 부른다.
    korea_market_data = cached_korea_market_data(_scope_session_date("kr", market_windows) or date, market_windows)
    market_tape = build_market_tape(
        date=date,
        market_snapshot=market_snapshot,
        korea_market_data=korea_market_data,
        market_windows=market_windows,
    )
    quality_preflight = preflight_from_context("briefing", {}, {
        "artifactId": date,
        "sourceCount": len(docs),
        "marketTape": market_tape,
    })
    memories = list_briefing_memories(MARKET_MEMORY_DB_PATH, limit=12)
    prev_briefing = load_prev_briefing(date)
    prev_checklist = extract_prev_checklist((prev_briefing or {}).get("markdown", ""))
    calendar_block = ""
    if week is not None:
        # 여러 시장이 한 pack에 실릴 수 있으므로 시장별 표를 이어 붙인다. 시장 라벨을
        # 함께 적지 않으면 어느 표가 어느 시장 것인지 모델이 알 수 없다.
        blocks = []
        for target in requested_markets:
            preview = calendar_preview(MARKET_MEMORY_DB_PATH, target, week)
            blocks.append(f"### {MARKET_TAGS[target]}\n\n{render_calendar_preview(preview, week)}")
        calendar_block = "\n\n".join(blocks)
    # 결측(None)은 설정을 따른다 — API 경로(generate_llm_briefing)와 같은 규칙이다.
    # 한쪽만 `is True`로 접으면 화면이 값을 안 보낼 때 CLI만 꺼진다(기업분석 실측).
    web_search = use_web_search_for_briefing() if web_search is None else bool(web_search)
    web_lookup_sink: dict = {}
    context, used_docs = build_llm_context(
        date,
        source_date,
        scoped_docs,
        groups,
        market_drivers=market_drivers,
        market_snapshot=market_snapshot,
        memories=memories,
        market_windows=market_windows,
        prev_checklist=prev_checklist,
        korea_market_data=korea_market_data,
        market_scope=market_scope,
        briefing_type=briefing_type,
        issue_coverage=issue_coverage_raw,
        session_modes=session_modes,
        kind=kind,
        weekly_window=week.to_dict() if week is not None else None,
        calendar_block=calendar_block,
        web_search=web_search,
        web_lookup_sink=web_lookup_sink,
        # shadow는 관측 전용이다(README 계약) — 프롬프트 권위 주입은 active만.
        concentration_context="\n\n".join(
            render_concentration_context(control)
            for control in concentration_by_market.values()
            if control and control.get("mode") == "active"
        ),
    )
    target_block = render_quality_target_context(
        "briefing",
        preflight=quality_preflight,
        context={"extraRoutes": [
            "브리핑 입력은 articles/rss만 사용한다. filings/reports는 브리핑 근거로 쓰지 않는다.",
            "한국장 종가·수급이 없으면 KRX/CSV/yfinance provider 한계를 Source & Data Notes에 남긴다.",
        ]},
    )
    context = "\n\n".join([context, target_block])
    context = "\n\n".join([context, build_preflight_evidence_context(
        "briefing",
        preflight=quality_preflight,
        artifact={"sources": used_docs, "stats": {"sourceCount": len(used_docs)}, "dataGaps": []},
    )])
    hint_block = render_prompt_hints(quality_preflight)
    if hint_block:
        context = "\n\n".join([context, hint_block])
    sources = prioritized_source_refs(
        scoped_docs, market_windows, limit=ref_limit, issue_coverage=issue_coverage_raw, market_scope=market_scope,
    ) or briefing_sources_from_headlines(_briefing_headlines(groups), limit=ref_limit)
    sources = source_refs(sources, limit=ref_limit)
    context = "\n\n".join([context, source_manifest_prompt(sources)])
    session_counts = session_doc_counts(scoped_docs, market_windows)
    draft = {
        "date": date,
        "generatedAt": generated_at,
        # 웹 보완 요약(시장별). write_briefing_from_markdown이 {**draft, ...}로 저장하므로
        # 여기 실으면 저장 JSON까지 간다 — API 경로의 llm_result["webLookup"]과 같은 계약.
        "webLookup": web_lookup_sink,
        "title": (
            f"Weekly Market Briefing — {week.label}" if week is not None
            else f"Daily Market Briefing — {date.replace('-', '.')}"
        ),
        "summary": (
            (
                f"{source_date} 구간의 자료를 바탕으로 "
                f"{', '.join(MARKET_TAGS[key] for key in requested_markets)}의 "
                "지난주 흐름과 다음주 일정을 정리했습니다."
            ) if week is not None else (
                f"{source_date}에 수집된 최신 자료를 바탕으로 "
                f"{', '.join(MARKET_TAGS[key] for key in requested_markets)}의 "
                "시장 반응, 핵심 이슈, 주도 기업을 정리했습니다."
            )
        ),
        "marketScope": market_scope,
        "kind": kind,
        **(week.to_dict() if week is not None else {}),
        "generationMarkets": list(requested_markets),
        "briefingType": briefing_type,
        "prompt": read_briefing_prompt(requested_markets, kind),
        "promptPath": briefing_prompt_path_label(requested_markets, kind),
        "headlines": _briefing_headlines(groups),
        "sources": sources,
        "marketSnapshot": market_snapshot,
        "koreaMarketData": korea_market_data,
        "marketWindows": market_windows,
        # 생성 시점의 세션 판정을 남긴다. 저장하지 않으면 읽을 때마다 다시
        # 추측하게 되고, 추측이 틀리면 브리핑이 스스로 어느 세션을 다뤘는지
        # 잘못 말하게 된다.
        "sessionModes": dict(session_modes),
        "marketDrivers": [
            {
                "driver": d.get("driver", ""),
                # 이 동인이 어느 시장 보고서 것인지. 저장 시 `_single_market_briefing`이
                # 이 값으로 거른다 — 비어 있으면 모든 시장을 통과해 네 보고서가 같은
                # 동인을 싣는다. `markets`는 그 동인이 건드리는 시장 목록이라 다른 값이다.
                "market": str(d.get("market") or ""),
                "score": round(float(d.get("score", 0)), 1),
                "markets": d.get("markets", []),
                "sources": d.get("sources", []),
                "impactTags": d.get("impactTags", []),
                "sectors": d.get("sectors", []),
                "docCount": len(d.get("docs", [])),
                # 규칙 생성(`builder.py`)과 같은 계약이다. 이게 없으면 그 동인이
                # 무슨 내용이었는지 되짚을 방법이 없고, 변화의 의미 비교가
                # 대조할 재료를 못 받아 이슈 목록만 판정하게 된다 — 이슈는 매일
                # 통째로 갈리는 집합이라 판정이 언제나 "새 정보"로 나온다.
                "topDocs": [issue_doc_ref(doc) for doc in (d.get("docs") or [])[:3]],
            }
            for d in market_drivers
        ],
        "issueCoverage": public_issue_coverage(issue_coverage_raw),
        "concentrationControl": {
            "version": 1,
            "mode": next(
                (str((row.get("leaderDecision") or {}).get("mode") or "shadow") for row in concentration_by_market.values()),
                "off",
            ),
            "byMarket": deepcopy(concentration_by_market),
        },
        "briefings": {},
        "visualRecommendations": visual_result.get("visualRecommendations", []),
        "visualSnapshots": visual_result.get("visualSnapshots", []),
        "visualWarnings": visual_result.get("warnings", []),
        "stats": {
            "documents": len(scoped_docs),
            "sourceDate": source_date,
            "analysisMode": market_windows.get("analysisMode", ""),
            "driverCount": len(market_drivers),
            "topDrivers": [d.get("driver", "") for d in market_drivers],
            "sourceCount": len(sources),
            "marketScope": market_scope,
            "issueCount": len(issue_coverage_raw),
            "koreaMarketDataOk": bool(korea_market_data.get("ok")) if isinstance(korea_market_data, dict) else False,
            **session_counts,
        },
    }
    pack = A.build_pack(
        task_type="briefing",
        artifact_type="briefing",
        artifact_id=f"{date}.weekly" if week is not None else date,
        title=draft["title"],
        prompt=read_briefing_prompt(requested_markets, kind),
        context=context,
        output_contract=briefing_output_contract(
            market_scope,
            briefing_type,
            # 계약 대상은 실제 시장 목록이다. 범위 이름만 넘기면 `multi` 같은 조합에서
            # 프롬프트와 검사가 서로 다른 시장을 본다.
            markets=requested_markets,
            expected_titles=(
                {target: weekly_title(target, week) for target in requested_markets}
                if week is not None
                else briefing_expected_titles(
                    date,
                    market_scope,
                    market_windows=market_windows,
                    session_modes=session_modes,
                )
            ),
            kind=kind,
            # shadow는 관측 전용 — 이름 강제는 active만. shadow에서 강제하면 규칙
            # 선별과 모델 판단이 갈릴 때마다 재작성 1회 + 잡 실패가 된다.
            expected_leading_companies={
                target: [
                    str(signature.get("subject") or "")
                    for candidate in (control.get("leaderDecision") or {}).get("finalPair") or []
                    for signature in control.get("signatures") or []
                    if signature.get("candidateId") == candidate
                ]
                for target, control in concentration_by_market.items()
                if control.get("mode") == "active"
            },
            leader_section_modes={
                target: "qualified_zero_to_two"
                for target, control in concentration_by_market.items()
                if control.get("mode") == "active"
            },
        ),
        # 실제 저장 경로는 여기서 정하지 않는다 — 시장별 **세션 키**가 파일명을 정하고
        # (`write_briefing_from_markdown`/`job_briefing_producer`), 그 키는 쓰기 시점의
        # 보고서 `date`다. 예전에는 이 라벨이 발행일 합본 경로를 박아 둬서, 이 문자열을
        # 계약으로 읽은 작성자가 발행일 키 저장 경로를 만들었다. 라벨은 템플릿으로만 남긴다.
        write_back_contract={"method": "write_markdown", "target": str(BRIEFINGS_DIR / f"{{sessionDate}}.{{market}}{'.weekly' if week is not None else ''}.json")},
        save_target=str(BRIEFINGS_DIR / f"{{sessionDate}}.{{market}}{'.weekly' if week is not None else ''}.json"),
        draft_artifact=draft,
        sources=sources,
        market_tape=market_tape,
        internal={
            "groups": groups, "qualityMode": quality_mode, "qualityPreflight": quality_preflight,
            "marketScope": market_scope, "visualSidecar": visual_result.get("sidecar", {}),
            "visualScopeResults": visual_scope_results,
            # 시장별 참고자료. 저장할 때 각 시장 섹션에 붙는다 — 하나로 합치면 네 시장
            # 보고서가 같은 참고자료를 싣는다.
            "sourcesByMarket": sources_by_market,
            "concentrationByMarket": deepcopy(concentration_by_market),
        },
    )
    return pack, _write_pack(pack, owner_job_id)


def write_briefing_from_markdown(pack: dict, markdown: str, *, persist: bool = True) -> dict:
    draft = dict(pack.get("draftArtifact") or {})
    date = draft.get("date") or str(pack.get("artifactId") or "").removesuffix(".weekly") or kst_date()
    market_scope = normalize_market_scope(draft.get("marketScope", "both"))
    draft["marketScope"] = market_scope
    kind = normalize_briefing_kind(draft.get("kind"))
    ref_limit = source_ref_limit(kind)
    contract = pack.get("outputContract") or briefing_output_contract(
        market_scope, draft.get("briefingType", "default"), kind=kind
    )
    violations = briefing_contract_violations(markdown, contract)
    if violations:
        raise ValueError(f"CLI 브리핑 출력 계약 위반: {'; '.join(violations)}")
    leader_subjects = leading_company_subjects_from_markdown(markdown)
    visual_scope_results = (pack.get("internal") or {}).get("visualScopeResults") or {}
    aligned_visuals = {
        "visualRecommendations": [],
        "visualSnapshots": [],
        "warnings": list(leader_subjects.get("warnings") or []),
    }
    if kind == "weekly":
        # 주간 그림(A·B·C)은 pack 단계에서 이미 만들어 draft에 실려 있고, 본문에서
        # 기업을 다시 읽어 맞출 세션 차트가 없다. `replace_leading_company_visuals`는
        # `leading_company` 행만 갈아끼우므로 주간 스냅샷은 그대로 남는다.
        aligned_visuals["warnings"] = []
        visual_scope_results = {}
    if visual_scope_results:
        try:
            aligned_visuals = collect_briefing_visuals(
                date,
                market_scope,
                visual_scope_results,
                leader_subjects=leader_subjects,
                include_market_visuals=False,
            )
        except Exception:
            aligned_visuals["warnings"].append(
                "leading_company_visual_alignment_failed"
            )
    draft = replace_leading_company_visuals(draft, aligned_visuals)
    candidate_sources = source_refs(pack.get("sources") or draft.get("sources") or [], limit=ref_limit)
    markdown, sources, generation_evidence, claim_ledger = reconcile_source_ledger(
        str(markdown or "").strip(), candidate_sources, limit=ref_limit,
    )
    # 저장된 pack의 시장 목록이 권위다(아래 requested_scopes와 같은 규칙).
    generation_scopes = list(
        normalize_market_selection(draft.get("generationMarkets") or market_scope)
    )
    resolved_sources_by_market = {}
    if len(generation_scopes) <= 1:
        markdown, claim_ledger = enforce_claim_integrity(markdown, sources, claim_ledger)
        markdown = append_briefing_sources(markdown, sources, limit=ref_limit, kind=kind)
        if generation_scopes:
            resolved_sources_by_market[generation_scopes[0]] = sources
    else:
        # 다시장 합본에는 여기서 붙이지 않는다 — 합본에 목록이 하나라도 있으면
        # has_sources가 참이 되어 시장별 본문이 참고자료를 영영 못 받고, 분리가
        # 그 하나를 마지막 시장 파일에 준다(2026-08-24 kr+jp 실측). 시장별 처리는
        # 아래 집중 종목 마무리 뒤에 한다.
        markdown = str(markdown or "").strip()
    generation = A.agent_generation(
        len(sources),
        message="LLM CLI 브리핑 생성 완료: Agent CLI / context pack 기반",
        model=str(pack.get("executedAdapter") or ""),
    )
    # 시장별 markdown에서 그 시장 라벨로 따로 뽑는다(§builder와 같은 규칙). 예전의
    # 일반 라벨 목록("내일 확인할 체크포인트" 등)은 네 시장 프롬프트 어디에도 없어
    # Agent 생성 브리핑은 체크포인트가 항상 0건이었고, 통합 본문에 한 번 부르면
    # 시장별 파일이 남의 체크포인트를 갖는다.
    checkpoint_scopes = generation_scopes
    market_markdowns = split_market_markdown(markdown, market_scope)
    concentration_by_market = deepcopy((pack.get("internal") or {}).get("concentrationByMarket") or {})
    for scope, control in list(concentration_by_market.items()):
        scoped_markdown = str((market_markdowns.get(scope) or {}).get("markdown") or "")
        repaired_markdown, concentration_by_market[scope] = finalize_concentration(
            scoped_markdown,
            control,
            agent_serialize=False,
        )
        if repaired_markdown != scoped_markdown:
            markdown = markdown.replace(scoped_markdown, repaired_markdown, 1)
    if concentration_by_market:
        market_markdowns = split_market_markdown(markdown, market_scope)
    if len(generation_scopes) > 1 and market_markdowns:
        # **시장별 본문이 각자 참고자료·Notes를 소유한다.** 모델이 쓴 목록은 시장을
        # 구분하지 않으므로 떼어내고, 일간은 그 시장의 선별 목록(sourcesByMarket)을
        # 붙인다(규칙 생성과 같은 계약). 주간은 본문에 목록을 두지 않는다(§10).
        scoped_sources = (pack.get("internal") or {}).get("sourcesByMarket") or {}
        global_external = [row for row in sources if row.get("external")]
        parts = []
        for scope_key, section in market_markdowns.items():
            scoped_markdown = strip_markdown_sources_section(str(section.get("markdown") or ""))
            scoped_markdown, market_sources, market_evidence, market_claims = reconcile_source_ledger(
                scoped_markdown,
                [*(scoped_sources.get(scope_key) or []), *global_external],
                limit=ref_limit,
            )
            resolved_sources_by_market[scope_key] = market_sources
            generation_evidence.setdefault("byMarket", {})[scope_key] = market_evidence
            scoped_markdown, market_claims = enforce_claim_integrity(
                scoped_markdown, market_sources, market_claims,
            )
            claim_ledger.setdefault("byMarket", {})[scope_key] = market_claims
            if kind != "weekly":
                scoped_markdown = append_briefing_sources(
                    scoped_markdown, market_sources, limit=ref_limit, kind=kind,
                )
            parts.append(scoped_markdown)
        markdown = "\n\n".join(part for part in parts if part).strip()
        market_markdowns = split_market_markdown(markdown, market_scope)
    if concentration_by_market:
        draft["concentrationControl"] = {
            "version": 1,
            "mode": str((draft.get("concentrationControl") or {}).get("mode") or "shadow"),
            "byMarket": concentration_by_market,
        }
    scope_checkpoints = {
        scope: checkpoints_from_markdown(
            (market_markdowns.get(scope) or {}).get("markdown", ""),
            artifact_type="briefing",
            artifact_id=date,
            headings=briefing_checkpoint_headings([scope], kind),
            scope="market",
            topic="Weekly Market Briefing" if kind == "weekly" else "Daily Market Briefing",
        )
        for scope in checkpoint_scopes
    }
    checkpoints = [row for scope in checkpoint_scopes for row in scope_checkpoints[scope]]
    gaps = []
    # 갭도 시장별로 남긴다(§builder와 같은 규칙). 합본 기준으로만 보면 네 시장 중
    # 하나만 섹션이 없을 때 그 사실이 어디에도 남지 않는다.
    for scope in checkpoint_scopes:
        if not scope_checkpoints[scope]:
            gaps.append({"market": scope, "category": "checkpoint", "message": f"{MARKET_LABELS.get(scope, scope)}: 체크포인트 섹션을 찾지 못했습니다."})
    if not checkpoints:
        gaps.append({"market": "both", "category": "checkpoint", "message": "브리핑에서 구조화 가능한 체크포인트 섹션을 찾지 못했습니다."})
    if not draft.get("stats", {}).get("documents"):
        gaps.append({"market": "both", "message": "브리핑 입력 뉴스 자료가 없습니다."})
    if not (draft.get("marketSnapshot") or {}).get("ok"):
        gaps.append({"market": "both", "category": "market_data", "message": "미국/글로벌 시장 스냅샷을 불러오지 못했습니다."})
    if not (draft.get("koreaMarketData") or {}).get("ok"):
        gaps.append({"market": "kr", "category": "market_data", "message": "한국장 시장 수치를 불러오지 못했습니다."})
    gaps.extend({"market": "both", "category": "market_data", "message": f"시각자료: {warning}"} for warning in draft.get("visualWarnings", []))
    for snapshot in draft.get("visualSnapshots", []):
        snapshot_market = str(snapshot.get("market") or "both").lower()
        gaps.extend({"market": snapshot_market, "category": "market_data", "message": f"시각자료 {snapshot.get('id', '')}: {warning}"} for warning in snapshot.get("warnings", []))
        if (snapshot.get("coverage") or {}).get("status") == "partial":
            gaps.append({"market": snapshot_market, "category": "market_data", "message": f"시각자료 {snapshot.get('id', '')}: 일부 종목만 수집됐습니다."})
        if snapshot.get("freshness") in {"stale", "unavailable"}:
            gaps.append({
                "market": snapshot_market,
                "category": "market_data",
                "message": (
                    f"시각자료 {snapshot.get('id', '')}: {snapshot.get('freshness')} "
                    f"(session {snapshot.get('marketSessionDate', '')}, asOf {snapshot.get('asOf', '')})"
                ),
            })
    sections = enrich_briefing_sections(
        split_market_markdown(markdown, market_scope),
        report_date=date,
        report_scope=market_scope,
        briefing_type=draft.get("briefingType", "default"),
        generated_at=draft.get("generatedAt", ""),
        report_summary=draft.get("summary", ""),
        market_windows=draft.get("marketWindows"),
        kind=kind,
        weekly_window={
            "weekStart": draft.get("weekStart", ""),
            "weekEnd": draft.get("weekEnd", ""),
            "previewStart": draft.get("previewStart", ""),
            "previewEnd": draft.get("previewEnd", ""),
        } if kind == "weekly" else None,
    )
    # 시장별 참고자료를 그 시장 섹션에 붙인다. `briefing_scope_view`가 섹션의 것을
    # 먼저 읽으므로, 없으면 합본 목록으로 떨어져 네 시장이 같은 자료를 싣게 된다.
    sources_by_market = resolved_sources_by_market or (pack.get("internal") or {}).get("sourcesByMarket") or {}
    for scope_key, rows in sources_by_market.items():
        if rows and isinstance(sections.get(scope_key), dict):
            sections[scope_key]["sources"] = rows
    for scope_key, section in sections.items():
        if not isinstance(section, dict):
            continue
        section["generationEvidence"] = deepcopy(
            (generation_evidence.get("byMarket") or {}).get(scope_key) or generation_evidence
        )
        section["claimLedger"] = deepcopy(
            (claim_ledger.get("byMarket") or {}).get(scope_key) or claim_ledger
        )
    briefing = {
        **draft,
        "markdown": markdown,
        "briefings": sections,
        "sources": sources,
        "generation": generation,
        "generationEvidence": generation_evidence,
        "claimLedger": claim_ledger,
        "checkpoints": checkpoints,
        "dataGaps": data_gaps_from_messages(gaps, artifact_type="briefing", artifact_id=date),
        "marketTape": pack.get("marketTape") or {},
    }
    try:
        generation_preflight = (pack.get("internal") or {}).get("qualityPreflight")
        postflight = preflight_from_context("briefing", briefing, {"artifactId": date})
        briefing = apply_quality_loop(
            "briefing",
            briefing,
            mode=(pack.get("internal") or {}).get("qualityMode", "diagnose_only"),
            preflight=postflight,
        )
        briefing.setdefault("qualityGeneration", {})["generationPreflight"] = generation_preflight
    except Exception:
        briefing["quality"] = {"status": "warn", "warnings": ["quality_evaluation_failed"]}
    # 주간은 내러티브에 적재하지 않는다(§builder와 같은 규칙). 같은 이슈를 일간이 이미
    # 그 주에 넣었고, 다시 넣으면 한 사건이 두 번 세어져 regime 근거 카운트가 부푼다.
    if persist and kind != "weekly" and market_scope == "both":
        try:
            for entry in build_memory_from_briefing(briefing, (pack.get("internal") or {}).get("groups") or []):
                upsert_memory(MARKET_MEMORY_DB_PATH, entry)
        except Exception:
            briefing.setdefault("warnings", []).append("agent writeback skipped market memory update")

    if persist:
        BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    # 저장된 pack의 시장 목록이 권위다. 레이블에서 되짚으면 이름 없는 조합이
    # 네 시장으로 넓어진다.
    requested_scopes = list(
        normalize_market_selection(briefing.get("generationMarkets") or market_scope)
    )
    saved_reports = {}
    visuals = {}
    sidecar = (pack.get("internal") or {}).get("visualSidecar") or {}
    for scope in requested_scopes:
        scoped_briefing = _single_market_briefing(briefing, scope)
        # 체크포인트는 시장별 추출본으로 교체한다. 합본을 그대로 두면 시장별 파일이
        # 남의 시장 체크포인트를 갖는다(§builder와 같은 규칙).
        scoped_briefing["checkpoints"] = scope_checkpoints.get(scope, [])
        # 저장 키는 그 시장의 세션일이다(§builder와 같은 규칙). 두 경로가 다른 키를 쓰면
        # 같은 세션이 생성 엔진에 따라 다른 파일이 된다.
        # 주간의 저장 키는 발행일이다(§builder와 같은 규칙). 세션일로 옮기면 일요일
        # 실행이 금요일 파일로 떨어져 그 주 금요일 일간 브리핑을 덮어쓴다.
        session_key = date if kind == "weekly" else (_scope_session_date(scope, draft.get("marketWindows")) or date)
        scoped_briefing["date"] = session_key
        save_path = BRIEFINGS_DIR / briefing_file_name(session_key, scope, kind)
        existing = read_json(save_path, None)
        if existing is None and kind != "weekly":
            # 옛 키로 저장된 같은 세션을 잇는다. personalOverlay가 사라지면 안 된다.
            existing = resolve_briefing_by_session(session_key, scope)
        if existing is None and kind != "weekly":
            legacy = read_json(BRIEFINGS_DIR / briefing_file_name(date), None)
            existing = briefing_scope_view(legacy, scope) if isinstance(legacy, dict) else None
        scoped_briefing = merge_briefing_report(scoped_briefing, existing, scope)
        # 이 시장 본문의 문체 실측(§builder와 같은 계약). 검사만 하고 되돌리지 않는다 —
        # 예약 발행물이 문체 때문에 막히면 안 된다.
        scoped_briefing["styleCheck"] = briefing_style_check(
            str((market_markdowns.get(scope) or {}).get("markdown") or scoped_briefing.get("markdown") or "")
        )
        scoped_briefing["webLookup"] = deepcopy((draft.get("webLookup") or {}).get(scope) or {})
        if persist:
            write_json(save_path, scoped_briefing)
        try:
            scoped_sidecar = _sidecar_for_market(sidecar, scope)
            if scoped_sidecar.get("snapshots"):
                visuals[scope] = scoped_sidecar
                if persist:
                    write_visual_sidecar(
                        BRIEFINGS_DIR / visual_sidecar_gzip_file_name(session_key, scope, kind),
                        scoped_sidecar,
                        scope,
                    )
        except Exception:
            scoped_briefing.setdefault("warnings", []).append("visual_sidecar_write_failed")
            if persist:
                write_json(save_path, scoped_briefing)
        saved_reports[scope] = scoped_briefing

    if len(requested_scopes) == 1:
        result = saved_reports.get(requested_scopes[0], briefing)
    else:
        briefing["briefings"] = {
            scope: saved_reports[scope] for scope in requested_scopes if scope in saved_reports
        }
        result = briefing_scope_view(briefing, market_scope)
    if persist:
        return result
    return {"result": result, "reports": saved_reports, "visuals": visuals}


def prepare_company_analysis_pack(query: str, *, quality_mode="diagnose_only", web_search=False, analysis_style="beginner", owner_job_id: str | None = None) -> tuple[dict, Path]:
    """CLI용 컨텍스트 팩. 자료 수집과 계약 블록은 **API 경로와 같은 조립기**가 만든다.

    예전에는 이 함수가 자료 수집과 컨텍스트 조립을 따로 했고, 그래서 두 경로가 갈렸다 —
    산출물 계약이 API 경로에만 붙었고, 자료 검색도 CLI만 사용자가 친 문자열 하나로
    찾아 실측 NVDA 문서 겹침이 8/30이었다(CLI 상위 3건에 엔비디아 기사 0건).
    """
    analysis_style = normalize_analysis_style(analysis_style)
    inputs = build_generation_inputs(
        query, analysis_style=analysis_style, web_search=bool(web_search),
    )
    prompt = read_company_analysis_prompt(analysis_style)
    draft = {
        **company_draft_artifact(inputs, query, analysis_style=analysis_style),
        "generatedAt": now_iso(),
        "headline": f"{(inputs.materials.get('company') or inputs.company).get('name', query)} 기업 분석",
        "prompt": prompt,
        "promptPath": str(analysis_prompt_path(analysis_style)),
    }
    context = inputs.context
    data_gaps = inputs.dataGaps
    quality_preflight = inputs.preflight

    pack = A.build_pack(
        task_type="company_analysis",
        artifact_type="company_analysis",
        artifact_id=f"{(draft['company'].get('ticker') or query)}_{str(draft['generatedAt'])[:10]}",
        title=draft["headline"],
        prompt=prompt,
        context=context,
        # 계약이 요구하는 아홉 개 전부다. 손으로 여섯 개만 적어 두면 나머지 셋은
        # 빠져도 아무도 모른다(실측: 경쟁우위·성장 전망·어떻게 접근할까가 빠져 있었다).
        output_contract={
            "format": "markdown",
            "analysisStyle": analysis_style,
            "requiredSections": list(COMPANY_REQUIRED_SECTIONS),
        },
        write_back_contract={"method": "write_markdown", "target": "data/company-analysis/{stable-id}.json"},
        save_target=str(ANALYSIS_REPORTS_DIR),
        metadata={"analysisStyle": analysis_style},
        draft_artifact=draft,
        sources=draft["sources"],
        data_gaps=data_gaps.get("gaps", []),
        internal={"qualityMode": normalize_quality_mode(quality_mode), "qualityPreflight": quality_preflight, "analysisStyle": analysis_style},
    )
    return pack, _write_pack(pack, owner_job_id)


def write_company_analysis_from_markdown(pack: dict, markdown: str, *, persist: bool = True) -> dict:
    report = dict(pack.get("draftArtifact") or {})
    report["markdown"] = str(markdown or "").strip()
    report["generation"] = A.agent_generation(len(report.get("sources") or []))
    try:
        report = apply_quality_loop(
            "company_analysis",
            report,
            mode=(pack.get("internal") or {}).get("qualityMode", "diagnose_only"),
            preflight=(pack.get("internal") or {}).get("qualityPreflight"),
        )
    except Exception:
        report["quality"] = {"status": "warn", "warnings": ["quality_evaluation_failed"]}
    # 계약 검증과 점수 상한은 **API 경로와 같은 것**을 쓴다. 한쪽에만 붙이면 다른 쪽에서
    # 조용히 빠진다 — 실제로 CLI 보고서에는 `contractValidation`이 아예 없었다.
    report = finalize_company_report(
        report, quote_sources=(report.get("webLookup") or {}).get("speakerSources") or [],
    )
    return save_analysis_report(report) if persist else report


def prepare_topic_report_pack(
    topic_key: str,
    *,
    custom_label: str = "",
    user_context: str = "",
    date: str | None = None,
    use_planner: bool = True,
    custom_tickers: dict | None = None,
    deep_research: bool = False,
    quality_mode: str = "diagnose_only",
    owner_job_id: str | None = None,
) -> tuple[dict, Path]:
    date = date or kst_date()
    topic = get_topic_config(topic_key, custom_label=custom_label or None, custom_tickers=custom_tickers)
    topic_plan = None
    if use_planner:
        try:
            topic_plan = build_topic_plan(
                topic_key,
                custom_label=custom_label,
                user_context=user_context,
                llm_override=False,
                preset_config=topic if topic_key != "custom" else None,
            )
        except Exception:
            topic_plan = None
    if topic_plan and topic_key == "custom":
        if topic_plan.get("searchQueries"):
            topic["search_keywords"] = topic_plan["searchQueries"]
        if topic_plan.get("memoryQueries"):
            topic["memory_keywords"] = topic_plan["memoryQueries"]
        if topic_plan.get("analysisAxes"):
            topic["theme_axes"] = [axis["label"] for axis in topic_plan["analysisAxes"]]
        if topic_plan.get("reportType"):
            topic["report_type"] = topic_plan["reportType"]
        if not custom_tickers and topic_plan.get("candidateTickers"):
            merged = dict(topic_plan["candidateTickers"])
            for ticker, name in topic["tickers"].items():
                if ticker not in merged and len(merged) < 12:
                    merged[ticker] = name
            topic["tickers"] = merged
    if topic_plan and deep_research:
        topic_plan = apply_deep_research_plan(topic_plan)
    market_data = fetch_topic_market_data(topic["tickers"], history_period=topic.get("history_period", "1y"))
    macro_data = fetch_macro_data(
        fred_series=topic.get("fred_series", []),
        bok_series=topic.get("bok_series", []),
        fred_key=fred_api_key(),
        bok_key=bok_api_key(),
    )
    evidence_pack = None
    source_ledger = []
    if topic_plan:
        evidence_pack = build_evidence_pack(
            topic_plan,
            search_docs=lambda queries, limit=12: topic_search_docs(list(queries), limit=limit),
            search_memories=lambda keywords, limit=20: topic_search_memories(list(keywords), limit=limit),
            date=date,
            deep_research=deep_research,
        )
        docs = evidence_pack["items"]
        memories = evidence_pack["marketMemory"]
        source_ledger = build_source_ledger(docs)
    else:
        docs = topic_search_docs(topic["search_keywords"])
        memories = topic_search_memories(topic["memory_keywords"])
    quality_preflight = preflight_from_context("topic_report", {}, {
        "artifactId": f"{date}:{topic['key']}",
        "sourceCount": len(docs),
        "sourceLedger": source_ledger,
        "evidenceItems": docs,
        "dataGaps": (evidence_pack or {}).get("dataGaps") or [],
    })
    prompt = read_topic_prompt()
    report_type = (topic_plan or {}).get("reportType") or topic.get("report_type", "")
    if prompt:
        prompt = compose_prompt(prompt, report_type)
    context = build_topic_llm_context(
        topic,
        market_data,
        macro_data,
        docs,
        memories,
        user_context,
        date,
        data_gaps=evidence_pack["dataGaps"] if evidence_pack else None,
    )
    context = "\n\n".join([context, render_quality_target_context(
        "topic_report",
        preflight=quality_preflight,
        context={"extraRoutes": [
            "Evidence Pack의 analysisAxes별 빈 축은 dataGap으로 처리하고 본문에서 한계로 명시한다.",
            "marketData/FRED/BOK가 없으면 해당 수치를 만들지 말고 Source & Data Notes에 남긴다.",
        ]},
    )])
    context = "\n\n".join([context, build_preflight_evidence_context(
        "topic_report",
        preflight=quality_preflight,
        artifact={
            "sourceLedger": source_ledger,
            "evidenceItems": docs,
            "dataGaps": (evidence_pack or {}).get("dataGaps") or [],
        },
    )])
    hint_block = render_prompt_hints(quality_preflight)
    if hint_block:
        context = "\n\n".join([context, hint_block])
    draft = {
        "saved": False,
        "generatedAt": now_iso(),
        "date": date,
        "topicKey": topic["key"],
        "topicLabel": topic["label"],
        "title": f"{topic['label']} 분석 리포트 — {date}",
        "topicPlan": topic_plan,
        "marketData": market_data,
        "macroAvailable": macro_data.get("ok", False),
        "sources": topic_doc_sources(docs),
        "memoryCount": len(memories),
        "docCount": len(docs),
        "userContext": bool(user_context and user_context.strip()),
        "personalOverlay": None,
    }
    pack = A.build_pack(
        task_type="topic_report",
        artifact_type="topic_report",
        artifact_id=f"{date}_{topic['key']}_{topic['label']}",
        title=draft["title"],
        prompt=prompt,
        context=context,
        output_contract={"format": "markdown", "requiredSections": ["Executive Summary", "반론과 리스크", "앞으로 확인할 체크포인트", "결론", "Source & Data Notes"]},
        write_back_contract={"method": "write_markdown", "target": "data/topic-reports/{stable-id}.json"},
        save_target=str(DATA_DIR / "topic-reports"),
        draft_artifact=draft,
        sources=draft["sources"],
        source_ledger=source_ledger,
        data_gaps=(evidence_pack or {}).get("dataGaps") or [],
        market_tape=build_market_tape(date=date, topic_market_data=market_data),
        internal={
            "topic": topic,
            "docs": docs,
            "memories": memories,
            "evidencePack": evidence_pack,
            "macroData": macro_data,
            "qualityMode": normalize_quality_mode(quality_mode),
            "qualityPreflight": quality_preflight,
        },
    )
    return pack, _write_pack(pack, owner_job_id)


def write_topic_report_from_markdown(pack: dict, markdown: str, *, persist: bool = True) -> dict:
    draft = dict(pack.get("draftArtifact") or {})
    internal = pack.get("internal") or {}
    docs = internal.get("docs") or []
    evidence_pack = internal.get("evidencePack")
    evidence_summary = evidence_pack_summary(evidence_pack) if evidence_pack else None
    data_gaps = data_gaps_from_messages(
        (evidence_pack or {}).get("dataGaps") or [],
        artifact_type="topic_report",
        category="evidence",
        source_section="Evidence Pack",
    )
    evidence_items = evidence_items_from_list(docs, artifact_type="topic_report", default_type="news")
    source_ledger = source_ledger_from_items(pack.get("sourceLedger") or docs, artifact_type="topic_report")
    checkpoints = checkpoints_from_markdown(
        markdown,
        artifact_type="topic_report",
        scope="market",
        topic=draft.get("topicLabel", ""),
        headings=["앞으로 확인할 체크포인트", "체크포인트", "다음 체크포인트"],
    )
    market_tape = pack.get("marketTape") or {}
    quality = evaluate_report(
        markdown,
        evidence_summary=evidence_summary,
        topic_plan=draft.get("topicPlan"),
        user_context_present=bool(draft.get("userContext")),
        checkpoints=checkpoints,
        source_ledger=source_ledger,
        evidence_items=evidence_items,
        data_gaps=data_gaps,
        market_tape=market_tape,
        artifact_type="topic_report",
    )
    report = {
        **draft,
        "markdown": str(markdown or "").strip(),
        "evidencePackSummary": evidence_summary,
        "evidenceItems": evidence_items,
        "sourceLedger": source_ledger,
        "checkpoints": checkpoints,
        "dataGaps": data_gaps,
        "marketTape": market_tape,
        "quality": quality,
        "qualityPreflight": internal.get("qualityPreflight"),
        "generation": A.agent_generation(len(docs)),
    }
    try:
        report = apply_quality_loop(
            "topic_report",
            report,
            mode=internal.get("qualityMode", "diagnose_only"),
            preflight=internal.get("qualityPreflight"),
        )
    except Exception:
        pass
    return save_topic_report(report) if persist else report


def _load_canonical_for_overlay(report_kind: str, report_id: str, market_scope: str = "both") -> tuple[dict, Path, str]:
    kind = str(report_kind or "").strip().lower()
    if kind == "briefing":
        # 규칙 경로와 **같은 해석기**로 파일을 찾는다. 예전에는 여기서 report id에
        # `.json`만 붙였는데, 주간 id(`{발행일}.weekly`)는 시장이 빠져 있어 저장된 적이
        # 없는 이름이 된다 — 주간 보고서는 시장별로만 저장된다. 그래서 CLI 모드의 주간
        # 개인 해석이 언제나 FileNotFoundError로 끝났다.
        date_text, scope_from_id, kind_from_id = split_briefing_id(report_id)
        path = _briefing_overlay_path(date_text, scope_from_id or market_scope, kind_from_id)
        canonical = read_json(path, None)
        return canonical, path, "briefing"
    if kind in {"analysis", "company_analysis"}:
        canonical = get_analysis_report(report_id)
        path = ANALYSIS_REPORTS_DIR / f"{(canonical or {}).get('id') or report_id}.json"
        return canonical, path, "analysis"
    if kind == "topic_report":
        from features.topic_report.service import get_topic_report
        canonical = get_topic_report(report_id)
        filename = (canonical or {}).get("filename") or f"{report_id}.json"
        path = DATA_DIR / "topic-reports" / filename
        return canonical, path, "topic_report"
    raise ValueError("report_kind must be briefing, analysis, or topic_report")


def prepare_personal_overlay_pack(report_kind: str, report_id: str, *, market_scope: str = "both", owner_job_id: str | None = None) -> tuple[dict, Path]:
    canonical, path, kind = _load_canonical_for_overlay(report_kind, report_id, market_scope)
    if not canonical:
        raise FileNotFoundError(f"Report not found: {report_kind}/{report_id}")
    hypotheses = _gather_hypotheses(kind, canonical)
    context = overlay_build_context(canonical, hypotheses, kind)
    pack = A.build_pack(
        task_type="personal_overlay",
        artifact_type=f"{kind}_personal_overlay",
        artifact_id=f"{kind}_{report_id}",
        title=f"Personal Overlay — {canonical.get('title') or canonical.get('headline') or report_id}",
        prompt=read_overlay_prompt(),
        context=context,
        output_contract={
            "format": "json",
            "requiredFields": ["linkedNotes", "supportingEvidence", "counterEvidence", "contradictions", "uncertainties", "personalQuestions", "stance", "markdown"],
            "stanceEnum": ["supportive", "mixed", "contradictory", "insufficient"],
        },
        write_back_contract={"method": "write_json", "target": str(path), "field": "personalOverlay"},
        save_target=str(path),
        draft_artifact={"canonical": {"id": report_id, "kind": kind, "title": canonical.get("title") or canonical.get("headline", "")}},
        internal={"reportKind": kind, "reportPath": str(path), "hypotheses": hypotheses},
    )
    return pack, _write_pack(pack, owner_job_id)


def write_personal_overlay_from_json(pack: dict, overlay_payload: dict, *, persist: bool = True) -> dict:
    if not isinstance(overlay_payload, dict):
        raise ValueError("personal_overlay writeback payload must be a JSON object")
    path = Path((pack.get("internal") or {}).get("reportPath") or pack.get("saveTarget"))
    if not path.is_absolute():
        path = ROOT / path
    canonical = read_json(path, None)
    if not canonical:
        raise FileNotFoundError(f"Report not found: {path}")
    hypotheses = (pack.get("internal") or {}).get("hypotheses") or []
    linked_notes = [
        {"noteId": h.get("note_id", ""), "title": h.get("title") or h.get("rel_path", ""), "type": h.get("note_type", ""), "ticker": h.get("ticker", "")}
        for h in hypotheses
    ]
    overlay = overlay_schema.normalize_overlay(overlay_payload, linked_notes=linked_notes, markdown=str(overlay_payload.get("markdown") or ""))
    overlay["generation"] = A.agent_generation(len(pack.get("sources") or []))
    updated = with_overlay(canonical, overlay, status="ok_agent_authored")
    if persist:
        write_json(path, updated)
    return {"ok": True, "personalOverlay": updated["personalOverlay"], "path": str(path)}


def prepare_thesis_delta_pack(ticker: str, *, period="90d", evidence_limit=12, owner_job_id: str | None = None) -> tuple[dict, Path]:
    thesis = get_thesis(ticker)
    if not thesis:
        raise FileNotFoundError(f"Thesis not found: {ticker}")
    period = thesis_delta.normalize_period(period)
    evidence_limit = max(1, min(int(evidence_limit or 12), 12))
    evidence, meta = thesis_delta.gather_local_evidence(thesis, period=period, limit=evidence_limit)
    connection = thesis_store.connect(MARKET_MEMORY_DB_PATH)
    try:
        prior_delta = thesis_store.latest_delta(connection, thesis["ticker"])
        review_state = thesis_review_state.load_review_state(connection, thesis["ticker"]).model_dump(mode="json")
    finally:
        connection.close()
    market_state_ref = resolve_market_state_ref(
        MarketStateRefQuery(
            market_db_path=MARKET_MEMORY_DB_PATH,
            research_db_path=DATA_DIR / "research-index.sqlite3",
            scope="GLOBAL",
            now=datetime.now(UTC),
        )
    )
    context = json.dumps(
        build_hypothesis_review_context(
            thesis=thesis,
            evidence=evidence,
            meta=meta,
            market_state_ref=market_state_ref,
            prior_delta=prior_delta,
            review_state=review_state,
        ),
        ensure_ascii=False,
        indent=2,
    )
    pack = A.build_pack(
        task_type="thesis_delta",
        artifact_type="thesis_delta",
        artifact_id=f"{thesis.get('ticker')}_{period}",
        title=f"Thesis Delta — {thesis.get('ticker')}",
        prompt=thesis_delta.read_prompt(),
        context=context,
        output_contract={
            "format": "json",
            "requiredFields": ["verdict", "summary", "supportingEvidence", "counterEvidence", "contradictions", "uncertainties", "nextCheckpoints", "markdown"],
            "verdictEnum": ["strengthened", "maintained", "weakened", "at_risk", "broken", "insufficient_evidence"],
        },
        write_back_contract={"method": "write_json", "target": "market-memory.sqlite3::thesis_delta"},
        save_target=str(MARKET_MEMORY_DB_PATH),
        draft_artifact={"thesis": thesis, "meta": meta},
        sources=evidence,
        internal={"thesis": thesis, "meta": meta, "evidence": evidence},
    )
    return pack, _write_pack(pack, owner_job_id)


def prepare_thesis_delta_writeback(pack: dict, delta_payload: dict) -> tuple[str, dict]:
    if not isinstance(delta_payload, dict):
        raise ValueError("thesis_delta writeback payload must be a JSON object")
    thesis = (pack.get("internal") or {}).get("thesis") or (pack.get("draftArtifact") or {}).get("thesis")
    meta = (pack.get("internal") or {}).get("meta") or (pack.get("draftArtifact") or {}).get("meta") or {}
    evidence = (pack.get("internal") or {}).get("evidence") or pack.get("sources") or []
    if not thesis:
        raise ValueError("Pack does not contain thesis data")
    delta = thesis_delta.normalize_delta(delta_payload, thesis=thesis, evidence=evidence, meta=meta)
    delta["generation"] = A.agent_generation(len(evidence))
    delta["company"] = thesis.get("company", "")
    return str(thesis.get("ticker") or ""), delta


def write_thesis_delta_from_json(pack: dict, delta_payload: dict) -> dict:
    ticker, delta = prepare_thesis_delta_writeback(pack, delta_payload)
    conn = thesis_store.connect()
    try:
        saved = thesis_store.save_delta(conn, ticker, delta)
        thesis = thesis_store.get_thesis(conn, ticker)
        if thesis:
            thesis_review_state.record_completed_review(conn, thesis, saved)
    finally:
        conn.close()
    return {"ok": True, "delta": saved}


def prepare_market_memory_pack(date: str | None = None, *, owner_job_id: str | None = None) -> tuple[dict, Path]:
    date = date or kst_date()
    context, used_docs, source_date = build_memory_llm_context(date)
    pack = A.build_pack(
        task_type="market_memory_llm",
        artifact_type="market_memory",
        artifact_id=date,
        title=f"Market Memory Update — {date}",
        prompt=read_market_memory_prompt(),
        context=context,
        output_contract={
            "format": "json",
            "requiredFields": ["entries"],
            "maxEntries": 3,
        },
        write_back_contract={"method": "write_json", "target": "market-memory.sqlite3::market_memory"},
        save_target=str(MARKET_MEMORY_DB_PATH),
        sources=source_refs(used_docs, limit=12),
        internal={"date": date, "sourceDate": source_date, "usedDocs": used_docs},
    )
    return pack, _write_pack(pack, owner_job_id)


def prepare_market_memory_writeback(pack: dict, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("market_memory_llm writeback payload must be a JSON object")
    internal = pack.get("internal") or {}
    date = internal.get("date") or pack.get("artifactId") or kst_date()
    used_docs = internal.get("usedDocs") or []
    entries = payload.get("entries") or []
    if not isinstance(entries, list):
        raise ValueError("market_memory_llm entries must be a list")
    prepared = []
    dropped = []
    for raw_entry in entries[:3]:
        entry, reason = normalize_llm_memory_entry(raw_entry, date, used_docs)
        if not entry:
            dropped.append(reason or "invalid_entry")
            continue
        entry["sourceKind"] = "agent"
        entry["generation"] = A.agent_generation(len(entry.get("sources") or []))
        prepared.append(entry)
    return {
        "ok": True,
        "status": "ok_agent_authored",
        "sourceDate": internal.get("sourceDate", ""),
        "rawEntryCount": len(entries),
        "droppedCount": len(dropped),
        "droppedReasons": dropped,
        "entries": prepared,
        "message": f"AI 에이전트 시장 내러티브 {len(prepared)}건을 준비했습니다.",
        "generation": A.agent_generation(len(used_docs)),
    }


def write_market_memory_from_json(pack: dict, payload: dict) -> dict:
    prepared = prepare_market_memory_writeback(pack, payload)
    saved = [upsert_memory(MARKET_MEMORY_DB_PATH, entry) for entry in prepared.pop("entries")]
    return {
        **prepared,
        "saved": saved,
        "message": f"AI 에이전트 시장 내러티브 {len(saved)}건을 저장했습니다.",
    }


def prepare_market_state_snapshot_pack(date: str | None = None, *, owner_job_id: str | None = None, context_payload: dict | None = None) -> tuple[dict, Path]:
    date = date or kst_date()
    context_payload = context_payload or build_market_state_context(db_path=MARKET_MEMORY_DB_PATH)
    context = json.dumps(context_payload, ensure_ascii=False, indent=2)
    pack = A.build_pack(
        task_type="market_state_snapshot",
        artifact_type="market_state_snapshot",
        artifact_id=date,
        title=f"Market State Snapshot — {date}",
        prompt=MARKET_STATE_SNAPSHOT_PROMPT,
        context=context,
        output_contract={
            "format": "json",
            "requiredFields": [
                "headline",
                "oneLineSummary",
                "beginnerSummary",
                "marketRegime",
                "actionPosture",
                "actionGuide",
                "keyDrivers",
                "watchItems",
                "counterEvidence",
                "sourceRefs",
                "confidence",
            ],
        },
        write_back_contract={"method": "write_json", "target": "market-memory.sqlite3::market_state_snapshots"},
        save_target=str(MARKET_MEMORY_DB_PATH),
        sources=context_payload.get("sourceRefs") or [],
        internal={"date": date, "sourceRefs": context_payload.get("sourceRefs") or []},
    )
    return pack, _write_pack(pack, owner_job_id)


def prepare_market_state_snapshot_writeback(pack: dict, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("market_state_snapshot writeback payload must be a JSON object")
    snapshot_payload = dict(payload)
    try:
        context_payload = json.loads(pack.get("context") or "{}")
    except Exception:
        context_payload = {"sourceRefs": (pack.get("internal") or {}).get("sourceRefs") or []}
    return validate_market_state_snapshot(snapshot_payload, context=context_payload)


def write_market_state_snapshot_from_json(pack: dict, payload: dict) -> dict:
    snapshot_payload = prepare_market_state_snapshot_writeback(pack, payload)
    snapshot = save_market_state_snapshot(MARKET_MEMORY_DB_PATH, snapshot_payload)
    generation = A.agent_generation(len((pack.get("internal") or {}).get("sourceRefs") or snapshot.get("sourceRefs") or []))
    return {
        "ok": True,
        "status": "ok_agent_authored",
        "snapshot": snapshot,
        "generation": generation,
        "message": "AI Agent 시장 상태 스냅샷을 저장했습니다.",
    }


def prepare_quality_repair_pack(artifact_type: str, artifact_id: str, *, owner_job_id: str | None = None) -> tuple[dict, Path]:
    artifact_type = str(artifact_type or "").strip()
    artifact_id = str(artifact_id or "").strip()
    if artifact_type not in {"briefing", "company_analysis", "topic_report"}:
        raise ValueError("quality_repair supports briefing, company_analysis, and topic_report")
    artifact = load_artifact(artifact_type, artifact_id)
    if not artifact:
        raise FileNotFoundError(f"Artifact not found: {artifact_type}/{artifact_id}")
    context = json.dumps({
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "instruction": "Repair weak sections using only the existing evidence. Preserve correct sections and the report's overall structure.",
        "quality": artifact.get("quality") or {},
        "qualityGeneration": artifact.get("qualityGeneration") or {},
        "sourceLedger": artifact.get("sourceLedger") or [],
        "evidenceItems": artifact.get("evidenceItems") or [],
        "dataGaps": artifact.get("dataGaps") or [],
        "markdown": artifact.get("markdown") or "",
    }, ensure_ascii=False, indent=2)
    prompt = """Improve only weak sections of the stored Folio OS report. Use no facts outside the supplied evidence and source ledger. Preserve the report type, headings, supported numbers, counter-evidence, uncertainties, checkpoints, and Source & Data Notes. Return the complete repaired Markdown only."""
    pack = A.build_pack(
        task_type="quality_repair",
        artifact_type="quality_repair",
        artifact_id=f"{artifact_type}_{artifact_id}",
        title=f"Quality Repair — {artifact.get('title') or artifact.get('headline') or artifact_id}",
        prompt=prompt,
        context=context,
        output_contract={"format": "markdown", "preserveCanonicalStructure": True},
        write_back_contract={"method": "write_markdown", "targetArtifactType": artifact_type, "targetArtifactId": artifact_id},
        save_target=f"{artifact_type}:{artifact_id}",
        draft_artifact=artifact,
        sources=artifact.get("sources") or [],
        source_ledger=artifact.get("sourceLedger") or [],
        evidence_items=artifact.get("evidenceItems") or [],
        data_gaps=artifact.get("dataGaps") or [],
        market_tape=artifact.get("marketTape") or {},
        internal={"targetArtifactType": artifact_type, "targetArtifactId": artifact_id},
    )
    return pack, _write_pack(pack, owner_job_id)


def write_quality_repair_from_markdown(pack: dict, markdown: str, *, persist: bool = True) -> dict:
    internal = pack.get("internal") or {}
    artifact_type = internal.get("targetArtifactType")
    artifact_id = internal.get("targetArtifactId")
    artifact = dict(pack.get("draftArtifact") or {})
    if not artifact or not artifact_type or not artifact_id:
        raise ValueError("quality_repair pack is missing target artifact data")
    previous_quality = artifact.get("quality") or {}
    artifact["markdown"] = str(markdown or "").strip()
    artifact["quality"] = evaluate_artifact(artifact_type, artifact)
    artifact["qualityGeneration"] = {
        **(artifact.get("qualityGeneration") or {}),
        "mode": "agent_cli_repair",
        "repairApplied": True,
        "repairCount": 1,
        "repairType": "agent",
        "qualityBefore": previous_quality,
        "qualityAfter": artifact["quality"],
        "generation": A.agent_generation(len(artifact.get("sources") or [])),
    }
    if not persist:
        return artifact
    if artifact_type == "briefing":
        write_json(BRIEFINGS_DIR / f"{artifact_id}.json", artifact)
        return artifact
    if artifact_type == "company_analysis":
        return save_analysis_report(artifact)
    return save_topic_report(artifact)


def prepare_investment_review_pack(
    date: str | None = None,
    *,
    include_portfolio: bool = True,
    include_watchlist: bool = True,
    include_obsidian: bool = True,
    owner_job_id: str | None = None,
) -> tuple[dict, Path]:
    review = build_review(
        date=date,
        include_portfolio=include_portfolio,
        include_watchlist=include_watchlist,
        include_obsidian=include_obsidian,
        use_llm=False,
        force_refresh=True,
        persist=owner_job_id is None,
    )
    date = review.get("date") or date or kst_date()
    context = json.dumps({
        "layer": "Personal Overlay",
        "instruction": "Synthesize the structured review without turning hypotheses into evidence or giving trade instructions.",
        "review": review,
    }, ensure_ascii=False, indent=2)
    prompt = """Write a concise Korean investment review Markdown from the supplied structured review. Separate source-grounded market state from user thesis and notes. Include challenging evidence, uncertainties, portfolio/watchlist implications, and concrete checkpoints. Do not add buy/sell instructions or unsupported facts."""
    pack = A.build_pack(
        task_type="investment_review",
        artifact_type="investment_review",
        artifact_id=date,
        title=f"Investment Review — {date}",
        prompt=prompt,
        context=context,
        output_contract={"format": "markdown", "layer": "personal_overlay"},
        write_back_contract={"method": "write_markdown", "target": str(REVIEW_DIR / f"{date}.json")},
        save_target=str(REVIEW_DIR / f"{date}.json"),
        draft_artifact=review,
        checkpoints=review.get("keyCheckpoints") or [],
        market_tape=review.get("marketTape") or {},
    )
    return pack, _write_pack(pack, owner_job_id)


def write_investment_review_from_markdown(pack: dict, markdown: str, *, persist: bool = True) -> dict:
    review = dict(pack.get("draftArtifact") or {})
    date = review.get("date") or pack.get("artifactId") or kst_date()
    review["markdown"] = str(markdown or "").strip()
    review["mode"] = "agent"
    review["generation"] = A.agent_generation(0)
    if persist:
        from features.common.canonical_report_io import safe_child_path

        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        # date는 저장된 pack에서도 올 수 있어 경로 조립 전에 봉쇄한다(리뷰 캐시 경로 조작 방지).
        write_json(safe_child_path(REVIEW_DIR, f"{date}.json"), review)
    return review


def prepare_investment_explanation_pack(tickers, context_service, evidence_loader) -> dict:
    """Public service seam for the read-only investment explanation context pack."""
    from features.agent_mode.investment_context import prepare_investment_context_pack

    return prepare_investment_context_pack(
        tickers,
        context_service,
        evidence_loader=evidence_loader,
    )


def submit_investment_explanation(tickers, context_service, evidence_loader) -> dict:
    """Submit the explanation through the existing metadata-only Agent job lane."""
    from features.agent_mode.investment_context import (
        submit_investment_context_explanation,
    )

    return submit_investment_context_explanation(
        tickers,
        context_service=context_service,
        evidence_loader=evidence_loader,
    )


def prepare_pack(task_type: str, **kwargs) -> tuple[dict, Path]:
    task_type = A.normalize_task_type(task_type)
    owner_job_id = kwargs.get("owner_job_id")
    if task_type == "briefing":
        return prepare_briefing_pack(
            kwargs.get("date"),
            strict_date=kwargs.get("strict_date", False),
            quality_mode=kwargs.get("quality_mode", "diagnose_only"),
            market_scope=kwargs.get("market_scope", "both"),
            briefing_type=kwargs.get("briefing_type", "default"),
            # **시장 목록을 그대로 넘긴다.** 여기서 버리면 `prepare_briefing_pack`이
            # 범위 이름으로 되짚는데, 임의 조합은 그 이름으로 표현되지 않는다 —
            # `market_selection_scope(["kr","jp"])`는 `multi`이고 `multi`는 네 시장
            # 전부로 풀린다. 그래서 한국·일본 예약이 미국장·유럽장까지 만들었다
            # (실측 2026-08-13 18:18에 파일 넷이 한꺼번에 쓰였다).
            markets=kwargs.get("markets"),
            # 브리핑 종류. 없으면 일간이라 기존 호출부가 그대로 동작한다.
            kind=kwargs.get("kind", DEFAULT_BRIEFING_KIND),
            # 결측(None)은 pack 빌더가 설정으로 푼다. 여기서 bool로 접으면 값을 안 준
            # 호출자(자동화 스케줄러)에게 웹 보완이 조용히 꺼진다(기업분석에서 실측).
            web_search=kwargs.get("web_search"),
            owner_job_id=owner_job_id,
        )
    if task_type == "company_analysis":
        return prepare_company_analysis_pack(
            kwargs.get("query") or "",
            quality_mode=kwargs.get("quality_mode", "diagnose_only"),
            web_search=bool(kwargs.get("web_search")),
            analysis_style=kwargs.get("analysis_style", "beginner"),
            owner_job_id=owner_job_id,
        )
    if task_type == "topic_report":
        return prepare_topic_report_pack(
            kwargs.get("topic_key") or "custom",
            custom_label=kwargs.get("custom_label") or "",
            user_context=kwargs.get("user_context") or "",
            date=kwargs.get("date"),
            use_planner=kwargs.get("use_planner", True),
            custom_tickers=kwargs.get("custom_tickers"),
            deep_research=kwargs.get("deep_research", False),
            quality_mode=kwargs.get("quality_mode", "diagnose_only"),
            owner_job_id=owner_job_id,
        )
    if task_type == "personal_overlay":
        return prepare_personal_overlay_pack(
            kwargs.get("report_kind") or "",
            kwargs.get("report_id") or "",
            # 시장을 버리면 주간 보고서를 찾을 수 없다 — 저장 키에 시장이 들어 있다.
            market_scope=kwargs.get("market_scope") or "both",
            owner_job_id=owner_job_id,
        )
    if task_type == "thesis_delta":
        return prepare_thesis_delta_pack(kwargs.get("ticker") or "", period=kwargs.get("period") or "90d", evidence_limit=kwargs.get("limit") or 12, owner_job_id=owner_job_id)
    if task_type == "market_memory_llm":
        return prepare_market_memory_pack(kwargs.get("date"), owner_job_id=owner_job_id)
    if task_type == "market_state_snapshot":
        return prepare_market_state_snapshot_pack(kwargs.get("date"), owner_job_id=owner_job_id)
    if task_type == "quality_repair":
        return prepare_quality_repair_pack(kwargs.get("artifact_type") or "", kwargs.get("artifact_id") or "", owner_job_id=owner_job_id)
    if task_type == "investment_review":
        return prepare_investment_review_pack(
            kwargs.get("date"),
            include_portfolio=kwargs.get("include_portfolio", True),
            include_watchlist=kwargs.get("include_watchlist", True),
            include_obsidian=kwargs.get("include_obsidian", True),
            owner_job_id=owner_job_id,
        )
    raise NotImplementedError(f"Prepare is not implemented for task type: {task_type}")


def writeback_pack(pack: dict, *, markdown: str | None = None, payload: dict | None = None) -> dict:
    task_type = A.normalize_task_type(pack.get("taskType"))
    if task_type == "briefing":
        return write_briefing_from_markdown(pack, markdown or "")
    if task_type == "company_analysis":
        return write_company_analysis_from_markdown(pack, markdown or "")
    if task_type == "topic_report":
        return write_topic_report_from_markdown(pack, markdown or "")
    if task_type == "personal_overlay":
        return write_personal_overlay_from_json(pack, payload or {})
    if task_type == "thesis_delta":
        return write_thesis_delta_from_json(pack, payload or {})
    if task_type == "market_memory_llm":
        return write_market_memory_from_json(pack, payload or {})
    if task_type == "market_state_snapshot":
        return write_market_state_snapshot_from_json(pack, payload or {})
    if task_type == "quality_repair":
        return write_quality_repair_from_markdown(pack, markdown or "")
    if task_type == "investment_review":
        return write_investment_review_from_markdown(pack, markdown or "")
    raise NotImplementedError(f"Writeback is not implemented for task type: {task_type}")
