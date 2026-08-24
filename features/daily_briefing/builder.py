"""Daily briefing orchestration.

`app.py` only normalizes HTTP input and calls this module.  Selection,
generation, persistence and scope merging live here.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from copy import deepcopy
import datetime as dt
import time
from pathlib import Path

from features.common.canonical_identity import ReportKind
from features.common.canonical_report_state import load_report
from features.common.canonical_report_types import WriteKind
from features.common.canonical_reports import commit_sync, prepare
from features.common.change_intelligence.service import decorate_candidate, project_committed_report
from features.common.dataframe_ops import top_records
from features.common.market_data.korea_session import korea_market_data as fetch_korea_session_data, session_state
from features.daily_briefing.limits import (
    ISSUE_COVERAGE_LIMIT,
    merged_source_limit,
    source_ref_limit,
)
from features.daily_briefing.source_window import scope_session_documents
from features.daily_briefing.weekly import (
    build_weekly_rules_markdown,
    calendar_preview,
    render_calendar_preview,
    weekly_documents,
    weekly_window as build_weekly_window,
)
from features.common.market_data.snapshot import fetch_market_snapshot
from features.common.market_data.tape import build_market_tape
from features.common.quality_generation.loop import apply_quality_loop
from features.common.quality_generation.preflight import preflight_from_context
from features.common.quality_generation.schema import normalize_quality_mode
from features.common.research_library.indexing.service import IMPACT_TERMS, build_index, load_index
from features.common.research_library.search.service import group_docs
from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.common.research_schema.data_gaps import data_gaps_from_messages
from features.common.utils import kst_date, now_iso, read_json, write_json
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
    record_call,
    render_concentration_context,
)
from features.daily_briefing.schema import (
    AGGREGATE_SCOPES,
    DEFAULT_BRIEFING_KIND,
    briefing_expected_titles,
    briefing_file_name,
    briefing_scope_view,
    enrich_briefing_sections,
    merge_briefing_report,
    normalize_briefing_contract,
    normalize_briefing_kind,
    normalize_briefing_markdown_titles,
    normalize_briefing_type,
    market_keys_for_briefing_scope,
    market_selection_scope,
    normalize_market_scope,
    normalize_market_selection,
    visual_sidecar_gzip_file_name,
)
from features.daily_briefing.selection import (
    derive_market_drivers,
    infer_market_session_date,
    prioritize_briefing_groups,
    session_doc_counts,
)
from features.daily_briefing.service import (
    MARKET_LABELS,
    append_briefing_sources,
    briefing_checkpoint_headings,
    briefing_sources_from_headlines,
    build_prompt_markdown,
    extract_prev_checklist,
    generate_llm_briefing,
    group_digest,
    llm_status_message,
    load_prev_briefing,
    news_documents,
    prioritized_source_refs,
    briefing_prompt_path_label,
    read_briefing_prompt,
    resolve_briefing_by_session,
    select_briefing_docs,
    source_refs,
)
from features.daily_briefing.visuals import (
    collect_briefing_visuals,
    leading_company_subjects_from_markdown,
    write_visual_sidecar,
)
from features.daily_briefing.weekly_visuals import collect_weekly_visuals
from features.llm_settings.client import selected_llm_config
from features.market_memory.memory import build_memory_from_briefing, list_briefing_memories, upsert_memory
from features.market_memory.snapshot import render_market_memory_context
from features.common.workspace import data_dir


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
BRIEFINGS_DIR = DATA_DIR / "briefings"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"
BRIEFING_PROMPT_PATH = ROOT / "features" / "daily_briefing" / "prompt.md"


class _NoWeeklyVisuals(Exception):
    """주간 창을 만들지 못해 주간 그림을 건너뛴다는 표시. 경고가 아니다."""


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)


def cached_market_snapshot(ttl_minutes=20):
    _ensure_dirs()
    cache_path = DATA_DIR / "market-snapshot.json"
    cached = read_json(cache_path, None)
    if cached:
        try:
            fetched = dt.datetime.fromisoformat(cached.get("cachedAt", ""))
            if dt.datetime.now(dt.timezone.utc) - fetched < dt.timedelta(minutes=ttl_minutes):
                return cached.get("snapshot", cached)
        except Exception:
            pass
    snapshot = fetch_market_snapshot()
    write_json(cache_path, {"cachedAt": now_iso(), "snapshot": snapshot})
    return snapshot


def cached_korea_market_data(date, market_windows=None):
    """대상 세션의 한국장 수치. 정책은 `session_cache`가 갖는다.

    돌려주는 값이 `None`일 수 있다 — 그 세션 수치를 못 받았다는 뜻이며, 직전 세션 값으로
    메우지 않는다. 호출부는 이미 `ok`가 아닌 값을 dataGap으로 다룬다.
    """
    payload, _reason = fetch_korea_session_data(date, session_state(market_windows))
    return payload


def _scope_groups_and_drivers(docs, market_windows, scope=None):
    groups = prioritize_briefing_groups(group_docs(docs), market_windows, limit=6, market_scope=scope)
    drivers = derive_market_drivers(docs, market_windows, limit=4)
    return groups, drivers


def _headlines(groups):
    rows = []
    for index, group in enumerate(groups[:4], 1):
        subject = group.get("company") or group.get("sector") or "시장"
        docs_sorted = top_records(group.get("docs", []), ["marketRelevance", "sourceWeight"], 6, descending=True)
        tags = sorted(set(sum([doc.get("sectors", []) + doc.get("impactTags", []) for doc in docs_sorted], [])))[:8]
        variable = ", ".join([tag for tag in tags if tag in IMPACT_TERMS][:3]) or "실적, 수급, 밸류에이션"
        rows.append({
            "id": f"h{index}",
            "title": f"{subject}, {variable} 변수가 시장 기대를 재조정",
            "body": (
                f"{subject} 관련 뉴스는 {', '.join(sorted(set(doc.get('source', '') for doc in docs_sorted))[:4])} 자료에서 확인됩니다. "
                f"{group_digest(group, 2)} 핵심은 {variable}이 투자자 기대를 움직일 수 있다는 점입니다."
            ),
            "tags": tags,
            "sources": [
                {
                    "title": doc.get("title", ""), "source": doc.get("source", ""),
                    "date": doc.get("date", ""), "url": doc.get("url", ""),
                    "path": doc.get("path", ""), "type": doc.get("type", ""),
                }
                for doc in docs_sorted
            ],
        })
    return rows


# 시장 하나가 늦어도 나머지가 끝나야 한다. 순차 실행이면 네 시장은 기준선의 4배가
# 되고, 한 시장의 provider 지연이 나머지 셋을 통째로 막는다.
MARKET_GENERATION_TIMEOUT_SECONDS = 900


def generate_scope_results(scopes, build_one, *, timeout=None):
    """Generate each market concurrently, returning whatever finished in time.

    The work is network-bound (an LLM call per market), so threads overlap the
    waiting. A market that raises or runs past the deadline is dropped and named
    in the warnings rather than failing the whole run — partial coverage is
    already a first-class result, recorded in `includedMarkets`.

    Python cannot kill a running thread, so a straggler keeps going in the
    background and its result is discarded. The pool is shut down without
    waiting; blocking on it would give back exactly the time the timeout saved.
    """
    scopes = list(scopes)
    if len(scopes) <= 1:
        return ({scope: build_one(scope) for scope in scopes}, [])

    deadline = time.monotonic() + (timeout or MARKET_GENERATION_TIMEOUT_SECONDS)
    pool = ThreadPoolExecutor(max_workers=len(scopes), thread_name_prefix="briefing")
    futures = {scope: pool.submit(build_one, scope) for scope in scopes}
    results, warnings = {}, []
    try:
        for scope, future in futures.items():
            try:
                results[scope] = future.result(timeout=max(0.0, deadline - time.monotonic()))
            except FuturesTimeout:
                warnings.append(f"{scope}: 생성 시간이 초과되어 이 시장은 빠졌습니다.")
            except Exception as exc:
                warnings.append(f"{scope}: 생성에 실패해 이 시장은 빠졌습니다({type(exc).__name__}).")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results, warnings


def _scope_session_date(scope, market_windows):
    """The trading date this market's briefing describes.

    US and Korea keep their original window keys because saved reports and every
    current consumer read those. Europe and Japan come from the session
    descriptors — falling through to Korea's keys would have stamped a European
    briefing with the Korean session date.
    """
    windows = market_windows or {}
    if scope == "us":
        return windows.get("usRegularSessionDate")
    if scope == "kr":
        return windows.get("krCurrentSessionDate") or windows.get("krPreviousSessionDate")
    session = (windows.get("marketSessions") or {}).get(scope) or {}
    # 장중이면 진행 중인 세션이 곧 이 브리핑의 세션이다. 창의 `sessionDate`는 직전
    # **완료** 세션이라 그대로 쓰면 일본장 장중 생성분이 전날 세션 파일로 커밋되어
    # 이미 저장된 그 세션의 마감 브리핑을 덮어쓴다. 한국장은 `krCurrentSessionDate`가
    # 이미 이 규칙이며(장중이면 당일), 일본은 한국과 같은 시간대라 같이 흘러야 한다.
    if session.get("phase") == "intraday" and windows.get("briefingDate"):
        return windows.get("briefingDate")
    return session.get("sessionDate") or windows.get("briefingDate")


def _scope_result(
    scope,
    briefing_type,
    date,
    source_date,
    docs,
    market_windows,
    market_snapshot,
    korea_market_data,
    memories,
    prev_checklist,
    quality_preflight,
    web_search_override,
    llm_override,
    kind=DEFAULT_BRIEFING_KIND,
    weekly=None,
):
    kind = normalize_briefing_kind(kind)
    ref_limit = source_ref_limit(kind)
    scoped_docs = documents_for_scope(docs, scope)
    groups, drivers = _scope_groups_and_drivers(scoped_docs, market_windows, scope)
    groups, concentration_control = prepare_concentration(groups, market_scope=scope, kind=kind)
    concentration_context = render_concentration_context(concentration_control)
    issues = build_issue_coverage(
        scoped_docs,
        scope.upper(),
        market_windows,
        limit=ISSUE_COVERAGE_LIMIT,
        coherence_policy=(scope == "kr" and kind == DEFAULT_BRIEFING_KIND),
    )
    headlines = _headlines(groups)
    session_modes = session_modes_from_windows(market_windows)
    window = (weekly or {}).get("window")
    calendar_block = ""
    if kind == "weekly" and window is not None:
        calendar_block = render_calendar_preview(
            calendar_preview(MARKET_MEMORY_DB_PATH, scope, window), window,
        )
    if kind == "weekly" and not scoped_docs:
        # **자료가 0건이면 LLM을 부르지 않는다.** 주간은 창을 넓히지 않으므로 한 주 내내
        # 수집이 없으면 그대로 0건이 된다. 그 상태로 프롬프트를 보내면 근거 없이 한 주의
        # 흐름을 쓰게 되고 참고자료가 빈 보고서가 남는다 — CLI 경로는 `WeeklyWindowEmptyError`로
        # 호출 전에 막고, 규칙 경로는 "자료 0건"을 본문에 적는다. 여기만 그 계약 밖에 있었다.
        llm_result, llm_status = None, "weekly_window_empty"
    else:
        llm_result, llm_status = generate_llm_briefing(
            date,
            source_date,
            scoped_docs,
            groups,
            market_drivers=drivers,
            web_search_override=web_search_override,
            llm_override=llm_override,
            market_snapshot=market_snapshot,
            korea_market_data=korea_market_data,
            memories=memories,
            market_windows=market_windows,
            prev_checklist=prev_checklist,
            quality_preflight=quality_preflight,
            market_scope=scope,
            briefing_type=briefing_type,
            issue_coverage=issues,
            session_modes=session_modes,
            kind=kind,
            weekly_window=window.to_dict() if window is not None else None,
            calendar_block=calendar_block,
            concentration_context=concentration_context,
        )
        if llm_status not in {"disabled", "missing_prompt"} and not llm_status.startswith("missing_"):
            record_call(concentration_control, "generation")
    if llm_result:
        sources = source_refs(llm_result.get("usedDocs", []), limit=ref_limit)
        markdown = append_briefing_sources(llm_result["markdown"], sources, limit=ref_limit, kind=kind)
        generation = {
            "mode": "llm", "status": llm_status, "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""), "responseId": llm_result.get("responseId", ""),
            "sourceCount": len(llm_result.get("usedDocs", [])), "webSearch": bool(llm_result.get("webSearch")),
            "tokenUsage": llm_result.get("tokenUsage") or {},
        }
    else:
        sources = prioritized_source_refs(
            scoped_docs, market_windows, limit=ref_limit, issue_coverage=issues, market_scope=scope,
        )
        if not sources:
            sources = briefing_sources_from_headlines(headlines, limit=ref_limit)
        if kind == "weekly" and window is not None:
            markdown = build_weekly_rules_markdown(
                scope,
                window,
                docs=scoped_docs,
                market_drivers=drivers,
                issue_coverage=issues,
                calendar_block=calendar_block,
                memory_context=render_market_memory_context(MARKET_MEMORY_DB_PATH),
            )
        else:
            markdown = build_prompt_markdown(
                date,
                source_date,
                scoped_docs,
                groups,
                headlines,
                market_drivers=drivers,
                market_windows=market_windows,
                market_snapshot=market_snapshot,
                korea_market_data=korea_market_data,
                market_scope=scope,
                briefing_type=briefing_type,
                issue_coverage=issues,
                session_modes=session_modes,
            )
        generation = {
            "mode": "rules", "status": llm_status, "provider": selected_llm_config().get("provider", ""),
            "model": "", "sourceCount": len(sources),
        }
    if kind != "weekly":
        # 주간 제목은 세션 제목이 아니다. 정규화를 태우면 구간이 세션일로 바뀐다.
        markdown = normalize_briefing_markdown_titles(
            markdown,
            date,
            scope,
            market_windows=market_windows,
            session_modes=session_modes,
        )
    generation["message"] = llm_status_message(generation)
    markdown, concentration_control = finalize_concentration(markdown, concentration_control)
    return {
        "marketScope": scope,
        "kind": kind,
        "markdown": markdown,
        "sessionMode": "" if kind == "weekly" else session_modes.get(scope, ""),
        "marketSessionDate": (
            window.week_end if (kind == "weekly" and window is not None)
            else _scope_session_date(scope, market_windows)
        ),
        "sources": sources,
        "generation": generation,
        "headlines": headlines,
        "marketDrivers": drivers,
        "issueCoverageRaw": issues,
        "issueCoverage": public_issue_coverage(issues),
        "groups": groups,
        "documents": scoped_docs,
        "concentrationControl": concentration_control,
    }


def _merge_sources(results, kind=DEFAULT_BRIEFING_KIND):
    """시장별 참고자료를 하나로 합친다. **상한은 시장 수에서 나온다.**

    고정 28은 이미 잘라먹고 있었다 — 네 시장이면 시장당 상한만 곱해도 그 두 배가
    넘어서, 뒤에 오는 시장의 출처가 통째로 사라졌다.
    """
    rows = []
    seen = set()
    results = list(results)
    for result in results:
        for source in result.get("sources", []):
            key = source.get("url") or source.get("path") or source.get("title")
            if key and key not in seen:
                seen.add(key)
                rows.append(source)
    return rows[:merged_source_limit(len(results), kind)]


def _merge_with_existing(briefing, existing, market_scope):
    return merge_briefing_report(briefing, existing, market_scope)


def _items_for_market(items, scope):
    target = str(scope or "").upper()
    return [
        deepcopy(item) for item in (items or [])
        if str(item.get("market") or "").upper() in {target, "BOTH"}
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


def _single_market_briefing(briefing, scope, checkpoints=None):
    scoped = briefing_scope_view(briefing, scope)
    scoped["marketScope"] = scope
    # 체크포인트는 통합 markdown에서 한 번에 뽑으면 시장을 구분할 수 없다. 그대로
    # 두면 미국 보고서에 한국장 확인 조건이 저장된다 — `/api/research-data/checkpoints`와
    # 도크 대화가 그 값을 그대로 내보낸다.
    if checkpoints is not None:
        scoped["checkpoints"] = deepcopy(checkpoints)
    # Record the original generation scope so the archive can collapse a 종합(both)
    # generation's per-market files into a single combined card. `briefing` still
    # carries the request-level marketScope here (scope_view returns a copy).
    scoped["generationScope"] = normalize_market_scope(briefing.get("marketScope"))
    # 조합에 이름이 없을 수 있으므로 실제 시장 목록도 함께 남긴다. 아카이브는
    # 이름이 아니라 이 목록으로 한 번의 생성을 묶는다.
    generation_markets = briefing.get("generationMarkets")
    scoped["generationMarkets"] = [
        str(key).lower() for key in (generation_markets or market_keys_for_briefing_scope(scoped["generationScope"]))
    ]
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
    control = deepcopy(briefing.get("concentrationControl") or {})
    scoped["concentrationControl"] = {
        "version": int(control.get("version") or 1),
        "mode": str(control.get("mode") or "shadow"),
        "byMarket": {scope: deepcopy((control.get("byMarket") or {}).get(scope) or {})},
    }
    stats = deepcopy(scoped.get("stats") or {})
    stats["marketScope"] = scope
    stats["visualSnapshotCount"] = len(scoped.get("visualSnapshots") or [])
    scoped["stats"] = stats
    return scoped


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
    kind=DEFAULT_BRIEFING_KIND,
):
    generated_at = now_iso()
    today = kst_date()
    date = date or today
    kind = normalize_briefing_kind(kind)
    # 선택은 시장 집합이다. `markets`가 오면 그게 권위이고, 없으면 예전 범위 이름을
    # 집합으로 푼다. 저장·표시용 레이블은 그 집합에서 파생한다.
    requested_markets = normalize_market_selection(
        markets if markets is not None else market_scope
    )
    market_scope = market_selection_scope(requested_markets)
    briefing_type = normalize_briefing_type(briefing_type)
    quality_mode = normalize_quality_mode(quality_mode)
    try:
        build_index(incremental=True)
    except Exception:
        pass
    index = load_index()
    all_documents = news_documents(index)
    docs, source_date, market_windows = select_briefing_docs(
        all_documents, date, strict=bool(strict_date), today=today,
        as_of=generated_at,
    )
    for doc in docs:
        doc["marketSessionDate"] = infer_market_session_date(doc, market_windows)

    market_snapshot = cached_market_snapshot()
    # 발행일이 아니라 **한국장 세션일**로 부른다. 차트는 세션일로 가는데 수치만 발행일로
    # 가면 한 브리핑 안에서 날짜가 갈린다 — 월요일 08:03에 만든 금요일 브리핑에 지수는
    # 금요일 종가가 들어갔는데 환율만 일요일 값이 들어갔다(환율은 24시간 거래라 주말 봉이
    # 잡힌다). 같은 시각에 발행일로 부르면 아직 열지도 않은 월요일 값을 받는다.
    korea_market_data = cached_korea_market_data(_scope_session_date("kr", market_windows) or date, market_windows)
    market_tape = build_market_tape(
        date=date, market_snapshot=market_snapshot, korea_market_data=korea_market_data,
        market_windows=market_windows,
    )
    quality_preflight = preflight_from_context("briefing", {}, {
        "artifactId": date, "sourceCount": len(docs), "marketTape": market_tape,
    })
    memories = list_briefing_memories(MARKET_MEMORY_DB_PATH, limit=12)
    prev_briefing = load_prev_briefing(date)
    prev_checklist = extract_prev_checklist((prev_briefing or {}).get("markdown", ""))

    requested_scopes = list(requested_markets)
    week = build_weekly_window(date) if kind == "weekly" else None
    # 자료 창을 시장별로 나눈다. 예전에는 한 풀을 모두가 공유했는데, 그 창이 발행일
    # 하나에서 나와 미국·한국 세션이 union으로 섞여 있었다. 세션과 세션 사이로 창을
    # 잡으면 주말·휴장 사이 뉴스도 다음 세션 브리핑에 자연히 들어온다.
    #
    # 주간은 세션 창이 아니라 달력 7일이다. 시장마다 창을 다르게 잡을 이유가 없고,
    # 비어도 넓히지 않는다 — "지난주"라는 말이 거짓이 되면 안 된다.
    scope_docs = {}
    # 주간 창은 시장과 무관하므로 한 번만 고른다. 시장마다 다시 고르면 같은 결과를
    # 얻으려고 전체 문서를 시장 수만큼 훑는다.
    weekly_pool = weekly_documents(all_documents, week) if week is not None else None
    for scope in requested_scopes:
        if weekly_pool is not None:
            scope_docs[scope] = weekly_pool
            continue
        selected = scope_session_documents(
            all_documents, scope, market_windows, today=today,
            session_date=_scope_session_date(scope, market_windows),
        )
        # 창이 비면 예전 풀로 되돌아간다. 창을 좁히는 변경이 브리핑을 지우면 안 된다.
        scope_docs[scope] = selected or docs
    for scope_rows in scope_docs.values():
        for doc in scope_rows:
            doc.setdefault("marketSessionDate", infer_market_session_date(doc, market_windows))
    if week is not None:
        source_date = f"{week.week_start}~{week.week_end}"
    results, scope_warnings = generate_scope_results(
        requested_scopes,
        lambda scope: _scope_result(
            scope, briefing_type, date, source_date, scope_docs[scope], market_windows,
            market_snapshot, korea_market_data,
            memories, prev_checklist, quality_preflight, web_search_override, llm_override,
            kind=kind, weekly={"window": week} if week is not None else None,
        ),
    )
    if not results:
        raise RuntimeError("no market briefing could be generated")
    requested_scopes = [scope for scope in requested_scopes if scope in results]
    markdown_parts = [results[scope]["markdown"] for scope in requested_scopes]
    markdown = "\n\n---\n\n".join(part for part in markdown_parts if part)
    sources = _merge_sources(results.values(), kind)
    scope_drivers = []
    issue_coverage = []
    headlines = []
    all_groups = []
    for scope in requested_scopes:
        headlines.extend(results[scope]["headlines"])
        all_groups.extend(results[scope]["groups"])
        issue_coverage.extend(results[scope]["issueCoverage"])
        for driver in results[scope]["marketDrivers"]:
            driver_docs = driver.get("docs", [])
            scope_drivers.append({
                "scope": scope,
                "driver": driver.get("driver", ""),
                "score": round(float(driver.get("score", 0)), 1),
                "markets": driver.get("markets", []),
                "sources": driver.get("sources", []),
                "impactTags": driver.get("impactTags", []),
                "sectors": driver.get("sectors", []),
                "docCount": int(driver.get("docTotal") or len(driver_docs)),
                # 의미 비교와 변화 상세의 입력 재료. 이게 없으면 이 동인이
                # "무슨 내용이었는지"를 나중에 되짚을 방법이 없다.
                "topDocs": [issue_doc_ref(doc) for doc in driver_docs[:3]],
            })

    try:
        if kind == "weekly":
            # **세션 스냅샷은 여전히 싣지 않는다.** 하루 세션의 가격 계열과 그날 등락
            # 히트맵을 한 주 보고서에 붙이면 특정 하루가 그 주를 대표하는 것처럼 읽힌다.
            # 대신 주 단위 계열을 따로 만든다 — 세 그림이 **같은 창 객체**를 받아
            # 주초·주말 경계가 하나다(§12.3).
            if week is None:
                raise _NoWeeklyVisuals
            visual_result = collect_weekly_visuals(
                week, market_scope, documents=weekly_pool if weekly_pool is not None else [],
                markets=requested_markets,
            )
        else:
            leader_subjects = leading_company_subjects_from_markdown(markdown)
            visual_result = collect_briefing_visuals(
                date, market_scope, results, leader_subjects=leader_subjects,
                markets=list(results),
            )
    except _NoWeeklyVisuals:
        visual_result = {
            "visualRecommendations": [], "visualSnapshots": [], "sidecar": {}, "warnings": [],
        }
    except Exception:
        visual_result = {
            "visualRecommendations": [], "visualSnapshots": [], "sidecar": {},
            "warnings": ["visual_snapshot_collection_failed"],
        }

    session_counts = session_doc_counts(docs, market_windows)
    # 시장별 markdown에서 그 시장의 라벨로 따로 뽑는다. 통합 본문에 한 번 부르면
    # 어느 항목이 어느 시장 것인지 남지 않아 시장별 파일이 남의 체크포인트를 갖는다.
    scope_checkpoints = {
        scope: checkpoints_from_markdown(
            results[scope]["markdown"],
            artifact_type="briefing",
            artifact_id=date,
            headings=briefing_checkpoint_headings([scope], kind),
            scope="market",
            topic="Weekly Market Briefing" if kind == "weekly" else "Daily Market Briefing",
        )
        for scope in requested_scopes
    }
    checkpoints = [row for scope in requested_scopes for row in scope_checkpoints[scope]]
    gaps = []
    # 갭도 시장별로 남긴다. 합본 기준으로만 보면 네 시장 중 하나만 섹션이 없을 때
    # 그 사실이 어디에도 남지 않는다 — 저장 파일은 시장별인데 갭은 "전부 비었을 때"만
    # 붙어서, 체크포인트가 0건인 보고서가 아무 표시 없이 나갔다.
    for scope in requested_scopes:
        if not scope_checkpoints[scope]:
            gaps.append(f"{MARKET_LABELS.get(scope, scope)}: 체크포인트 섹션을 찾지 못했습니다.")
    if not checkpoints:
        gaps.append("브리핑에서 구조화 가능한 체크포인트 섹션을 찾지 못했습니다.")
    # 주간은 자기 창의 자료 수를 본다. 일간 세션 풀을 보면 그 주에 한 건도 없어도
    # 세션 풀이 차 있다는 이유로 "자료가 없습니다"가 붙지 않는다.
    if not (weekly_pool if weekly_pool is not None else docs):
        gaps.append("브리핑 입력 뉴스 자료가 없습니다.")
    if not (market_snapshot or {}).get("ok"):
        gaps.append("미국/글로벌 시장 스냅샷을 불러오지 못했습니다.")
    if not (korea_market_data or {}).get("ok"):
        gaps.append("한국장 시장 수치를 불러오지 못했습니다.")
    for issue in issue_coverage:
        if issue.get("marketImpactStatus") == "unavailable":
            gaps.append(f"{issue.get('market', '')} issue {issue.get('issueId', '')}: 시장 반응 데이터가 없습니다.")
    # 시장이 통째로 빠진 것은 시각자료 결함보다 큰 공백이라 먼저 적는다.
    gaps.extend(f"시장 생성: {warning}" for warning in scope_warnings)
    gaps.extend(f"시각자료: {warning}" for warning in visual_result.get("warnings", []))
    for snapshot in visual_result.get("visualSnapshots", []):
        gaps.extend(f"시각자료 {snapshot.get('id', '')}: {warning}" for warning in snapshot.get("warnings", []))
        if (snapshot.get("coverage") or {}).get("status") == "partial":
            gaps.append(f"시각자료 {snapshot.get('id', '')}: 일부 종목만 수집됐습니다.")
        if snapshot.get("freshness") in {"stale", "unavailable"}:
            gaps.append(
                f"시각자료 {snapshot.get('id', '')}: {snapshot.get('freshness')} "
                f"(session {snapshot.get('marketSessionDate', '')}, asOf {snapshot.get('asOf', '')})"
            )
    data_gaps = data_gaps_from_messages(gaps, artifact_type="briefing", artifact_id=date)
    generations = [results[scope]["generation"] for scope in requested_scopes]
    generation = {
        "mode": "llm" if any(item.get("mode") == "llm" for item in generations) else "rules",
        "status": ",".join(sorted({item.get("status", "") for item in generations if item.get("status")})),
        "provider": ",".join(sorted({item.get("provider", "") for item in generations if item.get("provider")})),
        "model": ",".join(sorted({item.get("model", "") for item in generations if item.get("model")})),
        "webSearch": any(bool(item.get("webSearch")) for item in generations),
        "sourceCount": len(sources),
        "byMarket": {scope: results[scope]["generation"] for scope in requested_scopes},
    }
    generation["message"] = llm_status_message(generation)
    report_summary = (
        f"{source_date} 구간의 자료를 시장별로 정리한 주간 요약과 다음주 일정입니다."
        if week is not None
        else f"{source_date} 자료를 시장별 이슈 확산도와 가격 반응으로 선별한 브리핑입니다."
    )
    raw_sections = {
        key: {field: value for field, value in result.items() if field in {
            "markdown", "sessionMode", "marketSessionDate", "sources", "generation", "status",
        }}
        for key, result in results.items()
    }
    briefing_sections = enrich_briefing_sections(
        raw_sections,
        report_date=date,
        report_scope=market_scope,
        briefing_type=briefing_type,
        generated_at=generated_at,
        report_summary=report_summary,
        market_windows=market_windows,
        kind=kind,
        weekly_window=week.to_dict() if week is not None else None,
    )
    briefing = {
        "date": date,
        "generatedAt": generated_at,
        "title": (
            f"Weekly Market Briefing — {week.label}" if week is not None
            else f"Daily Market Briefing — {date.replace('-', '.')}"
        ),
        "summary": report_summary,
        "prompt": read_briefing_prompt(requested_scopes, kind),
        "promptPath": briefing_prompt_path_label(requested_scopes, kind),
        "marketScope": market_scope,
        "kind": kind,
        **(week.to_dict() if week is not None else {}),
        # 시장 집합이 권위다. 레이블(`multi` 등)은 표시용일 뿐이라 각 시장 파일이
        # 이 목록을 물려받아야 아카이브가 한 번의 생성을 정확히 묶는다.
        "generationMarkets": list(requested_scopes),
        "briefingType": briefing_type,
        "markdown": markdown,
        "briefings": briefing_sections,
        "headlines": headlines,
        "sources": sources,
        "generation": generation,
        "marketSnapshot": market_snapshot,
        "koreaMarketData": korea_market_data,
        "marketWindows": market_windows,
        "marketDrivers": scope_drivers,
        "issueCoverage": issue_coverage,
        "concentrationControl": {
            "version": 1,
            "mode": next(
                (
                    str((results[scope].get("concentrationControl") or {}).get("leaderDecision", {}).get("mode") or "shadow")
                    for scope in requested_scopes
                    if results[scope].get("concentrationControl")
                ),
                "off",
            ),
            "byMarket": {
                scope: deepcopy(results[scope].get("concentrationControl") or {})
                for scope in requested_scopes
                if results[scope].get("concentrationControl")
            },
        },
        "visualRecommendations": visual_result.get("visualRecommendations", []),
        "visualSnapshots": visual_result.get("visualSnapshots", []),
        "checkpoints": checkpoints,
        "dataGaps": data_gaps,
        "marketTape": market_tape,
        "stats": {
            "documents": len(docs), "sourceDate": source_date,
            "analysisMode": market_windows.get("analysisMode", ""),
            "marketScope": market_scope, "driverCount": len(scope_drivers),
            "topDrivers": [driver.get("driver", "") for driver in scope_drivers[:4]],
            "sourceCount": len(sources), "issueCount": len(issue_coverage),
            "visualSnapshotCount": len(visual_result.get("visualSnapshots", [])),
            "koreaMarketDataOk": bool(korea_market_data.get("ok")) if isinstance(korea_market_data, dict) else False,
            **session_counts,
        },
    }
    try:
        briefing = apply_quality_loop("briefing", briefing, mode=quality_mode, preflight=quality_preflight)
    except Exception:
        briefing["quality"] = {"status": "warn", "warnings": ["quality_evaluation_failed"]}

    if persist:
        saved_reports = {}
        for scope in requested_scopes:
            scoped_briefing = _single_market_briefing(briefing, scope, scope_checkpoints.get(scope))
            # 저장 키는 그 시장이 다루는 **세션일**이다. 발행일이 아니다 — 발행일로
            # 저장하면 같은 세션이 생성 시각에 따라 다른 이름으로 흩어진다(07:45 예약이
            # 만든 08-10 세션이 08-11로 저장되던 것). `date`도 함께 옮겨야 change
            # event의 artifactId(`report.date`에서 파생)와 파일명이 같은 값을 가리킨다.
            # 주간의 저장 키는 **발행일**이다. 세션일로 옮기면 일요일 실행이 금요일
            # 파일로 떨어져 그 주 금요일 일간 브리핑을 덮어쓴다. 종류 접미사와 발행일이
            # 함께 있어야 두 보고서가 나란히 남는다.
            session_key = date if kind == "weekly" else (_scope_session_date(scope, market_windows) or date)
            scoped_briefing["date"] = session_key
            report_path = BRIEFINGS_DIR / briefing_file_name(session_key, scope, kind)
            existing = read_json(report_path, None)
            if existing is None and kind != "weekly":
                # 옛 키로 저장된 같은 세션이 있으면 그것을 잇는다. personalOverlay처럼
                # 사용자가 붙인 것이 이관 전에 사라지면 안 된다. 주간에는 이을 옛 키가
                # 없다 — 세션 조회를 태우면 같은 날 일간 보고서를 물어 온다.
                existing = resolve_briefing_by_session(session_key, scope)
            if existing is None and kind != "weekly":
                existing = read_json(BRIEFINGS_DIR / briefing_file_name(date), None)
                existing = briefing_scope_view(existing, scope) if isinstance(existing, dict) else None
            scoped_briefing = _merge_with_existing(scoped_briefing, existing, scope)
            scoped_briefing = decorate_candidate(
                "briefing", scoped_briefing, data_dir=DATA_DIR,
                native_context={"generationDocs": docs}, generation_provenance=True,
            )
            try:
                sidecar = _sidecar_for_market(visual_result.get("sidecar") or {}, scope)
                if sidecar.get("snapshots"):
                    write_visual_sidecar(
                        BRIEFINGS_DIR / visual_sidecar_gzip_file_name(session_key, scope, kind),
                        sidecar,
                        scope,
                    )
            except Exception:
                scoped_briefing.setdefault("warnings", []).append("visual_sidecar_write_failed")
            prepared = prepare(
                report_kind=ReportKind.BRIEFING,
                exact_path=report_path,
                write_kind=WriteKind.CANONICAL,
                candidate=scoped_briefing,
            )
            commit_sync(prepared)
            projection = project_committed_report(MARKET_MEMORY_DB_PATH, report_path)
            committed = load_report(report_path)
            if committed is None:
                raise RuntimeError("canonical briefing commit did not persist the report")
            saved_reports[scope] = committed
            saved_reports[scope]["changeIntelligence"] = {
                **(saved_reports[scope].get("changeIntelligence") or {}),
                "projectionStatus": projection.get("status"),
                "invalidationToken": projection.get("invalidationToken") or (saved_reports[scope].get("changeIntelligence") or {}).get("invalidationToken"),
            }
        # 내러티브 누적은 통합 생성에서만 한다. 시장별 생성에서도 하면 같은 이슈가
        # 시장 수만큼 중복 적재된다.
        #
        # **주간은 아예 적재하지 않는다.** 같은 이슈를 일간이 이미 그 주에 넣었고,
        # 주간이 다시 넣으면 한 사건이 두 번 세어져 내러티브의 근거 카운트가 부풀어
        # 오른다 — 그 카운트가 regime 상태 판정에 그대로 쓰인다.
        if kind != "weekly" and market_scope in AGGREGATE_SCOPES:
            for entry in build_memory_from_briefing(briefing, all_groups):
                upsert_memory(MARKET_MEMORY_DB_PATH, entry)
        if len(requested_scopes) == 1:
            briefing = saved_reports.get(requested_scopes[0], briefing)
        else:
            written = [scope for scope in requested_scopes if scope in saved_reports]
            briefing["briefings"] = {scope: saved_reports[scope] for scope in written}
            # 생성 응답도 읽기 경로와 같은 커버리지 계약을 들고 나간다. 생성 직후
            # 화면에 그리는 클라이언트가 어느 시장이 빠졌는지 알 수 없으면 안 된다.
            briefing["includedMarkets"] = [scope.upper() for scope in written]
            # 요청 집합은 생성 실패로 줄어들지 않는다. 줄이면 넷을 요청했는데
            # 셋만 요청했다고 말하게 되고, 빠진 시장이 보이지 않는다.
            briefing["expectedMarkets"] = [scope.upper() for scope in requested_markets]
            if len(written) < len(requested_markets):
                missing = [s.upper() for s in requested_markets if s not in saved_reports]
                briefing["coverageWarnings"] = [
                    f"요청한 {len(requested_markets)}개 시장 중 {', '.join(missing)} 브리핑이 생성되지 않았습니다.",
                    *scope_warnings,
                ]
    return briefing_scope_view(briefing, market_scope)
