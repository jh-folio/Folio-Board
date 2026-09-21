"""LLM-driven market narrative memory context building and execution."""
import json
import os
import re
import sys
import threading
from pathlib import Path

from features.common.markets import PRODUCT_MARKETS
from features.daily_briefing.schema import MARKET_TAGS
from features.common.utils import normalize, now_iso, kst_date, clean_brief_text
from features.common.dataframe_ops import top_records
from features.daily_briefing.service import (
    news_documents,
    select_briefing_docs,
    source_refs,
)
from features.common.research_library.search.service import group_docs
from features.market_memory.memory import (
    REGION_CHOICES,
    list_memory,
    list_states,
    list_story_links,
    list_taxonomy,
    upsert_memory,
)
from features.market_memory.regime_v2 import refresh_all_regimes, refresh_regime_state
from features.market_memory.checkpoint_verdicts import run_checkpoint_verdicts
from features.market_memory.evidence_roles import (
    classify_role_payload,
    rebuild_selected_role_candidates,
    role_candidates_for_context,
    safe_build_role_candidates,
)
from features.market_memory.snapshot import (
    MARKET_STATE_SNAPSHOT_PROMPT,
    build_market_state_context,
    save_market_state_snapshot,
)
from features.llm_settings.client import (
    extract_json_object,
    json_repair_prompt,
    request_cli_text,
    selected_cli_config,
)
from features.common.quality_generation.telemetry import normalize_token_usage
from features.common.workspace import data_dir
from features.common.jobs import current_diagnostic_recorder, diagnostic_stage, diagnostic_stage_failure

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = data_dir()
FEATURES_DIR = ROOT / "features"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"
MARKET_MEMORY_PROMPT_PATH = FEATURES_DIR / "market_memory" / "prompt.md"
_STARTUP_REGIME_REFRESH_STARTED = False


def read_market_memory_prompt():
    try:
        return MARKET_MEMORY_PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def schedule_startup_regime_refresh(db_path: str | Path = MARKET_MEMORY_DB_PATH) -> dict:
    """Refresh Regime Tracker metrics once in the background after server startup."""
    global _STARTUP_REGIME_REFRESH_STARTED
    enabled = os.environ.get("STARTUP_REGIME_REFRESH", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return {"scheduled": False, "reason": "disabled"}
    if _STARTUP_REGIME_REFRESH_STARTED:
        return {"scheduled": False, "reason": "already_started"}
    _STARTUP_REGIME_REFRESH_STARTED = True
    status = os.environ.get("STARTUP_REGIME_REFRESH_STATUS", "current").strip() or "current"
    limit = _int_env("STARTUP_REGIME_REFRESH_LIMIT", 30)
    days = _int_env("STARTUP_REGIME_REFRESH_DAYS", 90)

    def worker():
        try:
            result = refresh_all_regimes(db_path, status=status, limit=limit, days=days)
            print(f"Regime Tracker startup refresh complete: {result.get('count', 0)} states")
        except Exception:
            print("Regime Tracker startup refresh failed.", file=sys.stderr)

    thread = threading.Thread(target=worker, name="regime-startup-refresh", daemon=True)
    thread.start()
    return {"scheduled": True, "status": status, "limit": limit, "days": days}


def compact_memory_row(mem):
    return {
        "date": mem.get("date", ""),
        "title": mem.get("title", ""),
        "story": mem.get("story", ""),
        "family": mem.get("storyFamily", ""),
        "stateKey": mem.get("stateKey", ""),
        "status": mem.get("status", ""),
        "bias": mem.get("bias", ""),
        "importance": mem.get("importance", ""),
        "summary": clean_brief_text(mem.get("summary", ""), 420),
        "checkpoint": clean_brief_text(mem.get("storyCheckpoint") or mem.get("rationale") or "", 220),
    }


def build_memory_llm_context(date=None):
    from features.common.research_library.indexing.service import load_index
    date = date or kst_date()
    index = load_index()
    docs, source_date, market_windows = select_briefing_docs(news_documents(index), date, strict=False)
    groups = group_docs(docs)[:4]
    memories = list_memory(MARKET_MEMORY_DB_PATH, limit=8)
    states = list_states(MARKET_MEMORY_DB_PATH, limit=6, status="current")
    taxonomy = list_taxonomy(MARKET_MEMORY_DB_PATH, term_type="story_family", limit=10)
    story_links = list_story_links(MARKET_MEMORY_DB_PATH, limit=10)

    used_docs = []
    seen = set()
    issue_blocks = []
    source_index_by_key = {}
    for i, group in enumerate(groups, 1):
        subject = group.get("company") or group.get("sector") or "시장"
        ranked = top_records(group.get("docs", []), ["marketRelevance", "sourceWeight"], 2, descending=True)
        block_docs = []
        tags = []
        for doc in ranked:
            key = doc.get("url") or doc.get("path") or doc.get("title")
            if key and key not in seen:
                seen.add(key)
                used_docs.append(doc)
                source_index_by_key[key] = len(used_docs)
            source_index = source_index_by_key.get(key, len(used_docs))
            for tag in (doc.get("impactTags", []) + doc.get("sectors", [])):
                if tag and tag not in tags:
                    tags.append(tag)
            block_docs.append({
                "source": doc.get("source", ""),
                "date": doc.get("date", ""),
                "title": clean_brief_text(doc.get("title", ""), 160),
                "summary": clean_brief_text(doc.get("summary") or doc.get("content") or "", 320),
                "companies": [c.get("ticker") or c.get("name") for c in doc.get("companies", [])[:4]],
                "tags": (doc.get("impactTags", []) + doc.get("sectors", []))[:8],
                "url": doc.get("url", ""),
                "sourceIndex": source_index,
                # Evidence Intake provenance: collector/query는 어떤 수집 경로·질의에서
                # 왔는지, narrativeIds는 수집기가 이미 연결한 기존 내러티브 힌트다.
                # (사용자 query intent는 관심 방향일 뿐 evidence가 아니다.)
                "collector": doc.get("collector", ""),
                "query": doc.get("query", ""),
                "narrativeIds": doc.get("narrativeIds", []) or [],
            })
        issue_blocks.append({
            "rank": i,
            "subject": subject,
            "tags": tags[:10],
            "documentCount": len(group.get("docs", [])),
            "docs": block_docs,
        })

    axis_terms = {
        "관세·무역정책": ["tariff", "trade", "관세", "무역", "수출통제", "policy"],
        "금리·달러 유동성": ["fed", "rate", "yield", "bond", "dollar", "fx", "금리", "국채", "채권", "달러", "환율", "스와프"],
        "AI 리더십 재분류": ["ai", "nvidia", "semiconductor", "data center", "gpu", "hbm", "인공지능", "반도체", "데이터센터"],
        "한국 수출과 원화 민감도": ["korea", "kospi", "krw", "export", "semiconductor", "한국", "코스피", "원화", "수출", "반도체"],
        "에너지·지정학 리스크": ["oil", "energy", "iran", "hormuz", "middle east", "war", "유가", "에너지", "이란", "중동", "호르무즈"],
        "신용·금융 스트레스": ["credit", "bank", "loan", "private credit", "debt", "금융", "은행", "신용", "부채"],
    }
    market_axes = []
    for axis, terms in axis_terms.items():
        matches = []
        for doc in docs:
            hay = normalize(" ".join([
                doc.get("title", ""),
                doc.get("summary", ""),
                " ".join(doc.get("impactTags", []) + doc.get("sectors", [])),
                " ".join(c.get("name", "") + " " + c.get("ticker", "") for c in doc.get("companies", [])),
            ])).lower()
            if any(term.lower() in hay for term in terms):
                matches.append({
                    "source": doc.get("source", ""),
                    "date": doc.get("date", ""),
                    "title": clean_brief_text(doc.get("title", ""), 160),
                    "summary": clean_brief_text(doc.get("summary") or doc.get("content") or "", 260),
                })
            if len(matches) >= 3:
                break
        if matches:
            market_axes.append({"axis": axis, "evidenceCount": len(matches), "evidence": matches})

    context = {
        "taskDate": date,
        "sourceDate": source_date,
        "marketTimeRule": market_windows.get("rule", ""),
        "marketClosedNotes": market_windows.get("closedNotes", []),
        "tokenPolicy": {
            "selectedIssueGroups": len(issue_blocks),
            "maxDocsPerGroup": 2,
            "instruction": "Use only the compact evidence below. Do not ask for full articles unless needed later.",
        },
        "existingStates": [compact_memory_row(item) for item in states[:6]],
        "recentMemory": [compact_memory_row(item) for item in memories[:8]],
        "knownStoryFamilies": taxonomy,
        "storyLinks": story_links[:10],
        "marketAxes": market_axes[:6],
        "candidateIssues": issue_blocks,
    }
    return json.dumps(context, ensure_ascii=False, indent=2), used_docs, source_date


def add_role_candidates_to_context(context: str, selection: dict) -> str:
    """Attach the bounded classifier task to the existing market-memory call."""
    try:
        payload = json.loads(context)
    except (TypeError, ValueError):
        payload = {}
    payload["roleCandidates"] = role_candidates_for_context(selection.get("selected") or [])
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _reconcile_role_inputs(selection: dict, payload: dict | None, *, db_path: str | Path) -> tuple[dict, dict | None, set[tuple[str, str]]]:
    """Rebuild after narrative persistence before accepting piggybacked roles.

    The market-memory response can change a state in the same call that
    carried ``roleCandidates``.  Its role label is usable only when our
    pre-call basis hash still equals the freshly rebuilt candidate's internal
    hash.  Only a selected pair whose basis changed is deliberately saved as
    a conservative rule row; a pair first created by this response was never
    given to the model, so it remains untouched for the next primary backlog.
    """
    fresh = rebuild_selected_role_candidates(db_path, selection)
    before = {
        (str(item.get("stateKey") or ""), str(item.get("memoryId") or "")): str(item.get("basisHash") or "")
        for item in (selection.get("selected") or [])
    }
    unchanged: set[tuple[str, str]] = set()
    for item in fresh.get("selected") or []:
        pair = (str(item.get("stateKey") or ""), str(item.get("memoryId") or ""))
        if before.get(pair) and before[pair] == str(item.get("basisHash") or ""):
            unchanged.add(pair)
    forced_rules = {
        (str(item.get("stateKey") or ""), str(item.get("memoryId") or ""))
        for item in (fresh.get("selected") or [])
    } - unchanged
    # Keep the original payload for the shared validator.  It must report
    # unknown/out-of-batch/duplicate/bad-enum items and a stale changed-basis
    # pair as invalid rather than silently erasing those facts here.
    return fresh, payload, forced_rules


def _role_failure_summary(selection: dict) -> dict:
    try:
        candidate_count = max(0, int(selection.get("candidateCount") or 0))
        remaining = max(0, int(selection.get("primaryCount") or 0))
    except (TypeError, ValueError):
        candidate_count = remaining = 0
    return {
        "candidateCount": candidate_count,
        "classifiedCount": 0,
        "ruleFallbackCount": 0,
        "invalidCount": 0,
        "remainingBacklogCount": remaining,
        "failureCode": "role_persistence_failed",
    }


def finalize_role_classification(
    selection: dict,
    payload: dict | None,
    *,
    db_path: str | Path = MARKET_MEMORY_DB_PATH,
    failure_code: str = "",
    budget_exhausted: bool = False,
) -> dict:
    """Persist roles, then run exactly one LLM-free projection/verdict pass.

    The role transaction is independent from narrative/snapshot storage.  A
    failure here returns a bounded code but never rolls those artifacts back.
    """
    if selection.get("roleFailureCode"):
        return _role_failure_summary(selection)
    try:
        fresh_selection, fresh_payload, forced_rules = _reconcile_role_inputs(selection, payload, db_path=db_path)
        summary = classify_role_payload(
            db_path,
            fresh_selection,
            fresh_payload,
            failure_code=failure_code,
            budget_exhausted=budget_exhausted,
            force_rule_pairs=forced_rules,
        )
    except Exception as error:
        # This is intentionally the final role-subsystem boundary.  It covers
        # non-SQLite errors too and must never unwind a successful graph or
        # combined snapshot transaction in an API/CLI parent job.
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="commit", boundary="save",
        )
        return _role_failure_summary(selection)
    try:
        # Refresh exactly the states that this bounded batch touched.  The
        # generic refresh helper is intentionally capped for background work;
        # using it here could skip a selected state ranked beyond its limit.
        affected_state_ids = sorted({
            str(item.get("stateId") or "")
            for item in (fresh_selection.get("selected") or [])
            if str(item.get("stateId") or "")
        })
        for state_id in affected_state_ids:
            refresh_regime_state(db_path, state_id, role_mode="llm")
        run_checkpoint_verdicts(db_path)
    except Exception as error:
        # Projection refresh is reconstructible and must not make the saved
        # role batch or the market-memory update look failed.
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error,
            stage_id=None, stage_code="commit", boundary="save",
        )
        summary.setdefault("failureCode", "projection_refresh_failed")
    return summary


def _llm_budget_exhausted(error: RuntimeError) -> bool:
    """Map only provider budget/quota signals from this existing LLM call."""
    detail = f"{error} {getattr(error, 'body', '')}".lower()
    return any(token in detail for token in (
        "insufficient_quota", "quota exceeded", "quota_exceeded", "budget exhausted",
        "budget_exhausted", "credit balance", "billing hard limit",
    ))


def llm_story_key(value):
    token = normalize(value).lower()
    replacements = {
        "관세": "tariff",
        "무역": "trade",
        "정책": "policy",
        "금리": "rates",
        "달러": "dollar",
        "유동성": "liquidity",
        "한국": "korea",
        "수출": "export",
        "원화": "krw",
        "환율": "fx",
        "반도체": "semiconductors",
        "에너지": "energy",
        "유가": "oil",
        "지정학": "geopolitics",
        "리더십": "leadership",
        "재분류": "reclassification",
    }
    for source, target in replacements.items():
        token = token.replace(source, f" {target} ")
    token = re.sub(r"[^0-9a-z]+", "_", token)
    return token.strip("_")[:80] or "market_narrative"


MAX_ENTRY_CHECKPOINTS = 3


def llm_checkpoint_inputs(value, limit: int = MAX_ENTRY_CHECKPOINTS) -> list:
    """LLM 엔트리의 `nextCheckpoints`를 생성 입력 모양으로만 정리한다.

    LLM이 낼 수 있는 키는 `item`·`direction`·`matchers`·`dueBy` 넷뿐이다.
    `status`·`createdAt`·`lastVerdict`·`history`는 서버가 찍는 값이라 들이지 않는다 —
    받으면 "이미 확인됨"으로 태어나는 체크포인트가 생긴다(validator의 `trusted=False`가
    한 번 더 벗긴다).

    값 검증은 하지 않는다 — enum·길이·keyword 규칙은
    `tracked_checkpoints.normalize_tracked_checkpoint`가 병합 시점에 집행한다.
    여기서 또 검증하면 같은 규칙이 두 곳에 살게 된다.
    """
    out: list = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        matchers = raw.get("matchers") if isinstance(raw.get("matchers"), dict) else {}
        out.append({
            "item": raw.get("item"),
            "direction": raw.get("direction"),
            "matchers": {"tickers": matchers.get("tickers") or [], "keywords": matchers.get("keywords") or []},
            "dueBy": raw.get("dueBy"),
        })
        if len(out) >= limit:
            break
    return out


def normalize_llm_memory_entry(entry, date, used_docs):
    if not isinstance(entry, dict):
        return None, "entry_not_object"
    title = normalize(entry.get("title") or entry.get("stateLabel") or entry.get("storyFamily") or "")
    summary = normalize(entry.get("summary") or entry.get("storyThesis") or entry.get("thesis") or "")
    state_conclusion = normalize(entry.get("stateConclusion") or entry.get("conclusion") or "")
    if state_conclusion and not summary.startswith(state_conclusion):
        summary = f"{state_conclusion} {summary}".strip()
    story = normalize(entry.get("story") or entry.get("stateKey") or entry.get("story_key") or entry.get("storyFamily") or title)
    story_family = normalize(entry.get("storyFamily") or entry.get("story_family") or entry.get("stateLabel") or title or story)
    state_key = normalize(entry.get("stateKey") or entry.get("state_key") or entry.get("story") or story_family or title)
    if not title or not summary:
        missing = [name for name, value in [("title", title), ("summary", summary)] if not value]
        return None, "missing_" + "_".join(missing)
    if not story:
        story = state_key or title
    if not state_key:
        state_key = story
    story = llm_story_key(story)
    state_key = llm_story_key(state_key)
    source_ids = entry.get("sourceIndexes", [])
    selected_sources = []
    if isinstance(source_ids, list):
        for idx in source_ids[:8]:
            try:
                doc = used_docs[int(idx) - 1]
            except Exception:
                continue
            selected_sources.append({
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
                "date": doc.get("date", ""),
                "url": doc.get("url", ""),
                "path": doc.get("path", ""),
                "type": doc.get("type", ""),
            })
    if not selected_sources:
        selected_sources = source_refs(used_docs, limit=5)
    allowed_category = {"stock_bond", "geopolitics", "emerging"}
    # 시장 계약에서 파생한다. 하드코딩된 {US, KR, GLOBAL}이 남아 있어서 LLM이
    # `EUROPE`/`JP`로 분류한 내러티브가 저장 직전에 전부 GLOBAL로 강등됐다 —
    # 4시장으로 넓힌 뒤에도 유럽·일본 내러티브가 하나도 등록되지 않은 원인이다.
    allowed_region = REGION_CHOICES
    allowed_importance = {"high", "medium", "low"}
    allowed_event = {"earnings", "policy", "geopolitics", "industry_trend", "market_move", "brief"}
    allowed_bias = {"bullish", "bearish", "neutral", "mixed"}
    allowed_relation = {"evolves_from", "branches_from", "confirms", "conflicts_with", "replaces", "same_family"}
    return {
        "date": date,
        "asOf": now_iso(),
        "title": title[:180],
        "summary": summary[:900],
        "story": story[:80],
        "storyFamily": story_family[:120] or story,
        "storyThesis": normalize(entry.get("storyThesis", ""))[:700] or summary[:300],
        "storyCheckpoint": normalize(entry.get("storyCheckpoint", ""))[:500] or "후속 가격 반응, 수급, 실적 가이던스, 정책 발표를 확인",
        "stateKey": state_key[:80] or story,
        "stateLabel": normalize(entry.get("stateLabel", ""))[:120] or story_family or title,
        "parentStory": normalize(entry.get("parentStory", ""))[:80] or state_key or story,
        "storyRelation": normalize(entry.get("storyRelation", "")) if normalize(entry.get("storyRelation", "")) in allowed_relation else "same_family",
        "stateBias": normalize(entry.get("stateBias", "")) if normalize(entry.get("stateBias", "")) in allowed_bias else "neutral",
        "category": normalize(entry.get("category", "")) if normalize(entry.get("category", "")) in allowed_category else "stock_bond",
        "region": normalize(entry.get("region", "")) if normalize(entry.get("region", "")) in allowed_region else "GLOBAL",
        "importance": normalize(entry.get("importance", "")) if normalize(entry.get("importance", "")) in allowed_importance else "medium",
        "entryMode": "issue",
        "eventKind": normalize(entry.get("eventKind", "")) if normalize(entry.get("eventKind", "")) in allowed_event else "brief",
        "netEffect": normalize(entry.get("netEffect", ""))[:80],
        "sourceKind": "llm",
        "subjects": entry.get("subjects", []) if isinstance(entry.get("subjects", []), list) else [],
        "industries": entry.get("industries", []) if isinstance(entry.get("industries", []), list) else [],
        "tickers": entry.get("tickers", []) if isinstance(entry.get("tickers", []), list) else [],
        "tags": entry.get("tags", []) if isinstance(entry.get("tags", []), list) else [],
        "sources": selected_sources,
        "dedupeKey": normalize(entry.get("dedupeKey", ""))[:160] or f"llm:{date}:{story}",
        # 구조화 체크포인트. `upsert_memory`는 이 키를 무시하고, 엔트리가 상태를
        # 만들거나 갱신할 때 `save_memory_entries`가 그 상태에 병합한다.
        "nextCheckpoints": llm_checkpoint_inputs(entry.get("nextCheckpoints")),
    }, ""


def save_memory_entries(entries, *, db_path=MARKET_MEMORY_DB_PATH) -> dict:
    """엔트리를 저장하고 구조화 체크포인트를 그 엔트리가 만든 상태에 병합한다.

    **생성 경로가 둘이라 여기 하나로 모은다** — `/api/memory/llm`(API 키)과 Agent CLI
    writeback이 각자 저장하면 계약이 한쪽에만 붙는다(§6 규칙 14). 어느 경로로 만든
    내러티브든 체크포인트가 같은 규칙으로 붙어야 한다.

    체크포인트는 **상태의 소유물**이다. 엔트리가 active/watch 상태를 만들거나 갱신할
    때만 병합하고, 상태로 승격되지 않은 issue 메모의 체크포인트는 버린 개수만 남긴다 —
    "모든 이슈를 바로 상태로 올리지 않는다"는 기존 보수 원칙이 여기에도 적용된다.
    """
    from features.market_memory.checkpoint_verdicts import (
        current_state_id_for_key,
        merge_state_checkpoints,
    )

    saved: list = []
    merged = 0
    dropped = 0
    errors = 0
    first_error = ""
    for entry in entries or []:
        checkpoints = (entry or {}).get("nextCheckpoints") or []
        result = upsert_memory(db_path, entry)
        saved.append(result)
        if not checkpoints:
            continue
        state = result.get("state") or {}
        state_id = str(state.get("id") or "")
        if not state_id or state.get("status") not in {"active", "watch"}:
            # 새 상태를 파생하지 않아도 **기존 살아 있는 상태를 갱신하는 엔트리**면
            # 체크포인트는 그 상태의 소유물이다(계약: 귀속은 stateKey를 따른다).
            # 중요도 미달로 상태 파생이 안 됐다고 드롭하면, 살아 있는 내러티브의
            # 후속 확인이 전부 버려진다(2026-08-30 리뷰).
            state_id = current_state_id_for_key(db_path, result.get("stateKey"))
        if not state_id:
            dropped += len(checkpoints)  # 상태로 승격되지 않은 issue 메모 — 계약대로 버린다
            continue
        try:
            outcome = merge_state_checkpoints(db_path, state_id, checkpoints)
        except Exception as exc:  # noqa: BLE001 - 병합 실패가 내러티브 저장을 되돌리지 않는다
            outcome = {"error": type(exc).__name__}
        if outcome.get("ok"):
            merged += int(outcome.get("accepted") or 0)
            dropped += int(outcome.get("rejected") or 0)
        else:
            # 실패를 dropped에 섞으면 기능 전체가 죽어도 "LLM이 나쁜 체크포인트를
            # 냈다"와 구분되지 않는다. 오류는 따로 세고 코드 식별자만 남긴다.
            errors += len(checkpoints)
            first_error = first_error or str(outcome.get("error") or "merge_failed")
    summary = {"saved": saved, "checkpointsMerged": merged, "checkpointsDropped": dropped}
    if errors:
        summary["checkpointErrors"] = errors
        summary["checkpointErrorCode"] = first_error
    return summary


def run_llm_market_memory(date=None):
    cfg = selected_cli_config()
    if not cfg["enabled"]:
        return {"ok": False, "status": "cli_disabled", "saved": [], "message": "AI가 꺼져 있습니다."}
    prompt = read_market_memory_prompt()
    if not prompt:
        return {"ok": False, "status": "missing_prompt", "saved": [], "message": "시장 내러티브 LLM 프롬프트가 없습니다."}
    with diagnostic_stage("context"):
        context, used_docs, source_date = build_memory_llm_context(date)
        role_selection = safe_build_role_candidates(MARKET_MEMORY_DB_PATH)
        context = add_role_candidates_to_context(context, role_selection)
    max_tokens = int(os.environ.get("LLM_MEMORY_MAX_OUTPUT_TOKENS", "2600"))
    try:
        text, response_id, usage = request_cli_text(cfg, prompt, context, web_search=False, max_output_tokens=max_tokens, json_mode=True, include_usage=True)
        with diagnostic_stage("validate", boundary="validation"):
            try:
                payload = extract_json_object(text)
            except Exception:
                repair_context = (
                    "Original output:\n"
                    + clean_brief_text(text, 5000)
                    + "\n\nRequired schema: {\"entries\": [...]}"
                )
                repaired, repair_id, repair_usage = request_cli_text(
                    cfg, json_repair_prompt(), repair_context,
                    web_search=False, max_output_tokens=min(max_tokens, 1800), json_mode=True, include_usage=True,
                )
                response_id = response_id or repair_id
                payload = extract_json_object(repaired)
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            prepared = []
            dropped = []
            for raw_entry in entries[:3]:
                entry, reason = normalize_llm_memory_entry(raw_entry, date or kst_date(), used_docs)
                if not entry:
                    dropped.append(reason or "invalid_entry")
                    continue
                prepared.append(entry)
        with diagnostic_stage("commit", boundary="save"):
            stored = save_memory_entries(prepared)
            role_classification = finalize_role_classification(role_selection, payload)
        saved = stored["saved"]
        if not saved and not entries:
            detail = "LLM이 중기 내러티브로 저장할 만큼 충분한 후보가 없다고 판단했습니다."
        elif not saved:
            detail = f"LLM 응답 {len(entries)}건 중 저장 가능한 형식이 없었습니다: {', '.join(dropped[:3])}"
        else:
            detail = f"LLM 시장 내러티브 {len(saved)}건을 저장했습니다."
        return {
            "ok": True,
            "status": "ok_local_only",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "responseId": response_id,
            "sourceDate": source_date,
            "usedSourceCount": len(used_docs),
            "estimatedInputTokens": max(1, len(context) // 4),
            "maxOutputTokens": max_tokens,
            "tokenUsage": normalize_token_usage(usage, prompt=prompt, context=context, output=text, max_output_tokens=max_tokens),
            "repairTokenUsage": normalize_token_usage(repair_usage, prompt=json_repair_prompt(), context=repair_context, output=repaired, max_output_tokens=min(max_tokens, 1800)) if "repair_usage" in locals() else {},
            "rawEntryCount": len(entries),
            "droppedCount": len(dropped),
            "droppedReasons": dropped[:6],
            "checkpointsMerged": stored["checkpointsMerged"],
            "checkpointsDropped": stored["checkpointsDropped"],
            "roleClassification": role_classification,
            "saved": saved,
            "message": detail,
        }
    except (RuntimeError, OSError) as exc:
        diagnostic_stage_failure(
            current_diagnostic_recorder(), exc, stage_id=None,
            stage_code="generate", boundary="generic",
        )
        budget_exhausted = _llm_budget_exhausted(exc)
        with diagnostic_stage("commit", boundary="save"):
            role_classification = finalize_role_classification(
                role_selection,
                None,
                failure_code="role_budget_exhausted" if budget_exhausted else "llm_request_failed",
                budget_exhausted=budget_exhausted,
            )
        return {
            "ok": False,
            "status": "generation_failed",
            "saved": [],
            "roleClassification": role_classification,
            "message": "LLM 시장 내러티브 생성에 실패해 기존 근거 역할은 보수 규칙으로 처리했습니다.",
        }
    except Exception as error:
        diagnostic_stage_failure(
            current_diagnostic_recorder(), error, stage_id=None,
            stage_code="generate", boundary="generic",
        )
        with diagnostic_stage("commit", boundary="save"):
            role_classification = finalize_role_classification(
                role_selection, None, failure_code="llm_request_failed"
            )
        return {
            "ok": False,
            "status": "generation_failed",
            "saved": [],
            "roleClassification": role_classification,
            "message": "LLM 시장 내러티브 생성에 실패해 기존 근거 역할은 보수 규칙으로 처리했습니다.",
        }


# 시장 목록은 계약에서 파생한다. 여기에 다시 적으면 새 시장이 늘었을 때
# 시장 상태 화면만 조용히 두 시장에 머문다.
MARKET_STATE_SCOPES = ("overall", *(market.value.lower() for market in PRODUCT_MARKETS))


def _market_state_scope_prompt(scope: str) -> str:
    labels = {"overall": "종합", **{key: MARKET_TAGS[key] for key in MARKET_STATE_SCOPES[1:]}}
    label = labels.get(scope, scope)
    return (
        MARKET_STATE_SNAPSHOT_PROMPT
        + "\n\n"
        + f"Current task: generate the {label} MarketStateSnapshot only.\n"
        + "Return the same top-level JSON shape. Do not rely on another market view to fill keyDrivers or sourceRefs.\n"
        + "Use only the rssCandidates/sourceRefs supplied in this context for cited sourceRefs.\n"
        + "marketTape and macroSnapshot are supporting evidence only; missing or weak market data must not be listed as user-facing uncertainties.\n"
    )


def _payload_to_market_view(payload: dict, scope: str) -> dict:
    return {
        "id": scope,
        "headline": payload.get("headline", ""),
        "marketInterpretation": payload.get("oneLineSummary", ""),
        "actionSummary": payload.get("beginnerSummary") or payload.get("actionPosture", ""),
        "actionGuide": payload.get("actionGuide") or {},
        "keyDrivers": payload.get("keyDrivers") or [],
        "watchItems": payload.get("watchItems") or [],
        "counterEvidence": payload.get("counterEvidence") or [],
        "uncertainties": payload.get("uncertainties") or [],
        "sourceRefs": payload.get("sourceRefs") or payload.get("sources") or [],
    }


def _merge_context_refs(contexts: dict[str, dict]) -> dict:
    merged = dict(contexts.get("overall") or {})
    for key in ("rssCandidates", "sourceRefs"):
        seen = set()
        items = []
        for context in contexts.values():
            for item in context.get(key) or []:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "")
                dedupe_key = item_id or str(item)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(item)
        merged[key] = items
    merged["marketViewContexts"] = {
        scope: {
            "marketScope": context.get("marketScope"),
            "sourceRefs": context.get("sourceRefs") or [],
            "rssCandidateCount": len(context.get("rssCandidates") or []),
        }
        for scope, context in contexts.items()
    }
    return merged


def run_llm_market_state_snapshot(date=None):
    cfg = selected_cli_config()
    if not cfg["enabled"]:
        return {"ok": False, "status": "cli_disabled", "message": "AI가 꺼져 있습니다."}
    max_tokens = int(os.environ.get("LLM_MARKET_STATE_MAX_OUTPUT_TOKENS", "2200"))
    try:
        payloads = {}
        contexts = {}
        response_ids = {}
        token_usage = {}
        estimated_input_tokens = 0
        for scope in MARKET_STATE_SCOPES:
            context_payload = build_market_state_context(market_scope=scope)
            context = json.dumps(context_payload, ensure_ascii=False, indent=2)
            prompt = _market_state_scope_prompt(scope)
            text, response_id, usage = request_cli_text(
                cfg,
                prompt,
                context,
                web_search=False,
                max_output_tokens=max_tokens,
                json_mode=True,
                include_usage=True,
            )
            payloads[scope] = extract_json_object(text)
            contexts[scope] = context_payload
            response_ids[scope] = response_id
            estimated_input_tokens += max(1, len(context) // 4)
            token_usage[scope] = normalize_token_usage(
                usage,
                prompt=prompt,
                context=context,
                output=text,
                max_output_tokens=max_tokens,
            )
        payload = dict(payloads["overall"])
        payload["marketViews"] = {
            scope: _payload_to_market_view(payloads[scope], scope)
            for scope in MARKET_STATE_SCOPES
        }
        merged_context = _merge_context_refs(contexts)
        snapshot = save_market_state_snapshot(MARKET_MEMORY_DB_PATH, payload, context=merged_context)
        return {
            "ok": True,
            "status": "ok_llm_authored",
            "provider": cfg["provider"],
            "model": cfg["model"],
            "responseId": response_ids.get("overall", ""),
            "responseIds": response_ids,
            "snapshot": snapshot,
            "message": "LLM 시장 상태 스냅샷을 저장했습니다.",
            "tokenUsage": token_usage,
            "estimatedInputTokens": estimated_input_tokens,
        }
    except Exception:
        return {"ok": False, "status": "generation_failed", "message": "LLM 시장 상태 스냅샷 생성에 실패했습니다."}
