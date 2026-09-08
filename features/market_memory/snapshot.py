from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import assert_never

from features.common.markets import MARKET_REGISTRY, PRODUCT_MARKETS, normalize_market_code
from features.common.utils import now_iso
from features.common.market_calendar import infer_doc_markets
from features.market_memory.digest import build_rss_digest
from features.market_memory.market_context import build_market_macro_context
from features.market_memory.market_state_ref import capture_input_watermarks
from features.market_memory.memory import connect, init_db, list_states
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
MARKET_MEMORY_DB_PATH = data_dir() / "market-memory.sqlite3"
MARKET_STATE_SNAPSHOT_PROMPT = """You are writing Folio OS Market Memory v3.

Return one JSON object only. Do not use Markdown fences.

Synthesize the current medium-term market state from:
- shortTermDigest: RSS-derived short-term memory
- existingStates: existing Market Memory states
- marketTape: yfinance/market-data price, index, FX, and commodity context
- macroSnapshot: FRED and BOK/ECOS macro context
- sourceRefs: allowed source references

Required JSON fields:
- headline: one Korean line, 20-40 characters, stating the judgment for the current medium-term market state
- oneLineSummary: one clear paragraph explaining the state, including why the judgment follows from the evidence.
- beginnerSummary: one plain Korean sentence for a beginner investor. Do not list factors; state what the market means for action.
- marketRegime: compact English or Korean regime key
- actionPosture: practical investor posture, not a buy/sell command
- actionGuide: object with headline, action, timing. This is user-facing behavior guidance, not a command to buy/sell.
- keyDrivers: 3-5 items, each with title, summary, directionLabel, marketImpact, nextMemoryCheck, evidenceSummary, whyItMatters, sourceRefs
- watchItems: 3-5 concrete checkpoints
- counterEvidence: 2-5 items that could challenge the view
- uncertainties: optional but recommended
- sourceRefs: source references used, preserving ids from context when possible
- confidence: 0.0 to 1.0
- marketViews: optional object with overall, us, kr, europe, jp. Each view may include headline, marketInterpretation, actionSummary, actionGuide, keyDrivers, watchItems, counterEvidence, uncertainties. marketInterpretation is 3-4 short sentences, about 300 Korean characters and never more than 400.

Rules:
- Use judgment, but keep it source-grounded.
- Write beginnerSummary/actionGuide/keyDrivers in beginner-friendly Korean.
- beginnerSummary and actionGuide are additive display guidance. They must not replace oneLineSummary, driver summaries, whyItMatters, or evidenceSummary.
- Do not repeat a list of factors in beginnerSummary; factors are shown in keyDrivers.
- Every keyDriver must preserve both judgment and reason: summary states the driver's current judgment, whyItMatters explains why it matters, evidenceSummary explains what evidence supports it, and marketImpact explains the effect on investors/markets.
- Write marketViews.overall, marketViews.us, marketViews.kr, marketViews.europe, and marketViews.jp when the evidence supports market-specific views. Keep the same reasoning structure in each view; do not produce disconnected formats.
- marketViews.overall/us/kr/europe/jp keyDrivers are not labels. Each market view driver must include the same rich fields as top-level keyDrivers: title, summary, directionLabel, marketImpact, nextMemoryCheck, evidenceSummary, whyItMatters, sourceRefs.
- If a market-specific view has weak evidence, say that in marketInterpretation/counterEvidence instead of filling it with short factor names.
- Use marketTape and macroSnapshot as structured evidence. They are not conclusions. They help decide whether news flows are confirmed or contradicted by prices and macro data.
- Every headline, top-level and per market view, states a judgment about what happened. A classification is not a headline: do not write a noun phrase that files the state into a category ("...위험을 높임", "...가 병존", "...를 요구하는 국면"), and do not end a market view headline with the market's own name ("...하는 유럽") — the screen already says which market it is.
- A market view headline must compress that same view's marketInterpretation, including whichever cause that body treats as dominant. If the body says two forces drive the market, a headline naming only one is wrong, not shorter.
- Do not headline a market purely by comparison to another market ("미국보다 부진"). If the cause is external, name the mechanism that transmits it.
- Write each marketInterpretation as 3-4 sentences totalling about 300 Korean characters, and never more than 400. Counting sentences alone is not the contract: a sentence that chains four clauses with commas is a paragraph. Keep one idea per sentence, roughly 60-80 characters each.
- Do not enumerate in marketInterpretation. Name at most one or two examples, not every company, official, or index with its own move and reason; keyDrivers already show that list next to this body. Carry a number only when the judgment changes without it.
- Every sentence in marketInterpretation must carry a claim. Reporting what prices did is confirmation, not interpretation: a sentence whose whole content is that indices closed lower by given amounts tells the reader only what the drivers and charts beside it already show. When a move matters, put it inside the claim it supports and keep it to one number — "정책 불확실성이 이익 개선을 눌렀다" is interpretation, "파리가 1.6%, 밀라노가 1.17% 내렸습니다" is not.
- The first sentence of marketInterpretation is this market's judgment: what state it is in and why it is in that state. The screen highlights that sentence. Do not spend it on a session recap, an index level, or a run of percentages.
- Structure the rest as: what cuts against that judgment, and what therefore has to be true for it to hold or break.
- Do not attach source names or reference ids to individual sentences in marketInterpretation. Per-sentence citations make that body unreadable. Put the references in the view's sourceRefs array; inline ids in this field are stripped, not displayed.
- Ground marketInterpretation and oneLineSummary in the news flow in rssCandidates (events, announcements, policy remarks). marketTape and macroSnapshot confirm or contradict that story; they are never the story itself, and a recital of them is not a substitute for judgment.
- marketTape and macroSnapshot are supporting evidence only. If they are unavailable, stale, weak, or hard to match, do not list that as user-facing uncertainties; keep those limitations as internal data diagnostics.
- Treat existingStates as prior hypotheses to re-check, not as conclusions to preserve.
- Do not anchor on past Market Memory. If rssCandidates contradict, weaken, or invalidate an existing state, say so and update the current judgment.
- Prefer "changed / weakened / invalidated / still supported" reasoning over recursively repeating old summaries.
- directionLabel should be one of: 도움, 부담, 부담 완화, 변동성, 혼재, 중립.
- marketImpact must explain whether the driver helps, hurts, or makes the market volatile.
- nextMemoryCheck describes what Folio OS should check in the next Market Memory update, not what the user must manually search.
- Do not treat user notes or hypotheses as evidence.
- Do not invent missing facts or numbers.
- Include counter-evidence even when the main stance is constructive.
"""

MAX_DRIVERS = 5
MAX_WATCH_ITEMS = 5
MAX_COUNTER_EVIDENCE = 5
MAX_SOURCE_REFS = 60
# 시장별 뷰 키. 시장 계약에서 파생해 새 시장이 자동으로 포함된다.
MARKET_VIEW_KEYS = tuple(market.value.lower() for market in PRODUCT_MARKETS)
RSS_CONTEXT_LIMIT = 120
# 이 아래로는 시장 판단을 뒷받침할 근거가 부족하다고 보고 컨텍스트에 경고를 남긴다.
RSS_CANDIDATE_MIN = 8


def _text(value, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit]


def _body_text(value, limit: int) -> str:
    """본문 길이 필드는 문장 경계에서 자른다.

    _text()는 value[:limit]이라 상한에 걸리면 단어 중간에서 끊긴다. 짧은 라벨은
    그래도 되지만 시장 해석처럼 화면의 큰 본문으로 읽히는 값은 잘린 티가 나지
    않는 채로 문장이 끊긴다. 상한을 넘으면 마지막 온전한 문장까지만 남긴다.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(mark) for mark in (".", "!", "?", "。"))
    return head[: cut + 1].strip() if cut > limit // 3 else head.strip()


_REF_ID = r"(?:rss:item:\d+|driver:\d+|state:[A-Za-z0-9_:-]+)"
_INLINE_REF_GROUP = re.compile(r"\s*[\(\[]\s*(" + _REF_ID + r"(?:\s*[,;/]\s*" + _REF_ID + r")*)\s*[\)\]]")
_INLINE_REF_BARE = re.compile(r"\s*" + _REF_ID)
_REF_ONLY = re.compile(_REF_ID)
# 본문에 내부 id가 들어가면 안 되는 필드만 훑는다. sourceRefs와 id는 id가 값이다.
_REF_SAFE_KEYS = {"id", "sourceRefs", "sources", "sourceLookup", "inputWatermarks"}
# 인용을 매체명으로 살리지 않고 지우는 필드. 화면의 큰 본문이라 문장마다 출처가
# 붙으면 읽을 수 없다. 출처는 그 뷰의 sourceRefs가 이미 갖고 있다.
_REF_DROP_KEYS = {"marketInterpretation"}


def _resolve_ref_label(source_id: str, lookup: dict[str, dict] | None) -> str:
    entry = (lookup or {}).get(source_id) or {}
    return _text(entry.get("source") or entry.get("title"), 60)


def scrub_inline_refs(value, lookup: dict[str, dict] | None = None):
    """모델이 본문에 써넣은 내부 참조 id를 읽을 수 있는 출처명으로 바꾸거나 지운다.

    `rss:item:13`은 context 항목에 코드가 붙인 내부 id다. 프롬프트는 이 id를
    sourceRefs 배열에 담으라고 하지만 모델은 문장 안에도 인용처럼 써넣는다.
    구조화된 sourceRefs는 이미 `_display_source_refs()`가 해석 불가능한 id를
    걸러내는데, 본문에 박힌 것은 그 관문을 지나지 않고 화면까지 나온다.

    아는 출처면 매체명으로 바꾸고, 모르면 지운다. 사용자에게 `rss:item:13`은
    출처가 아니라 새는 내부 구현이다.

    단 `_REF_DROP_KEYS`의 필드는 아는 id도 지운다. 매체명으로 살려 주면 문장마다
    `(Bloomberg, 연합뉴스)`가 붙어 화면의 큰 본문이 읽히지 않는다(실측 한 해석에
    9곳). 그 필드의 출처는 sourceRefs 배열이 이미 갖고 있으므로 잃는 것이 없다.
    """
    if isinstance(value, str):
        def replace_group(match):
            labels = []
            for source_id in _REF_ONLY.findall(match.group(1)):
                label = _resolve_ref_label(source_id, lookup)
                if label and label not in labels:
                    labels.append(label)
            return f" ({', '.join(labels)})" if labels else ""

        text = _INLINE_REF_GROUP.sub(replace_group, value)
        text = _INLINE_REF_BARE.sub("", text)
        text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
        text = re.sub(r"\(\s*\)", "", text)
        return re.sub(r"\s{2,}", " ", text).strip()
    if isinstance(value, list):
        return [scrub_inline_refs(item, lookup) for item in value]
    if isinstance(value, dict):
        return {
            key: item
            if key in _REF_SAFE_KEYS
            else scrub_inline_refs(item, None if key in _REF_DROP_KEYS else lookup)
            for key, item in value.items()
        }
    return value


def _confidence(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.5
    return max(0.0, min(1.0, round(score, 3)))


def _list(value, *, limit: int) -> list:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _source_ref_from_context_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    title = _text(item.get("title"), 220)
    source = _text(item.get("source") or item.get("media"), 100)
    url = _text(item.get("url"), 500)
    source_id = _text(item.get("id"), 80)
    if not (source_id or title or source or url):
        return None
    return {
        "id": source_id,
        "title": title,
        "source": source,
        "date": _text(item.get("date") or item.get("timestamp"), 40),
        "url": url,
    }


def _source_ref_lookup(context: dict | None) -> dict[str, dict]:
    if not isinstance(context, dict):
        return {}
    lookup: dict[str, dict] = {}
    for collection_name in ("sourceRefs", "rssCandidates"):
        for item in _list(context.get(collection_name), limit=RSS_CONTEXT_LIMIT):
            ref = _source_ref_from_context_item(item)
            if ref and ref.get("id"):
                lookup[ref["id"]] = ref
    return lookup


def _resolve_source_ref(ref, lookup: dict[str, dict]) -> dict | None:
    if isinstance(ref, str):
        source_id = _text(ref, 80)
        if not source_id:
            return None
        if source_id in lookup:
            return dict(lookup[source_id])
        return {"id": source_id, "title": source_id, "source": "", "date": "", "url": ""}
    if not isinstance(ref, dict):
        return None
    source_id = _text(ref.get("id"), 80)
    if source_id in lookup:
        resolved = dict(lookup[source_id])
        for key in ("title", "source", "date", "url"):
            override = _text(ref.get(key), 500 if key == "url" else 220)
            if override:
                resolved[key] = override
        return resolved
    return _source_ref_from_context_item(ref)


def _source_refs(value, lookup: dict[str, dict] | None = None) -> list[dict]:
    refs = []
    lookup = lookup or {}
    for index, item in enumerate(_list(value, limit=MAX_SOURCE_REFS), 1):
        ref = _resolve_source_ref(item, lookup)
        if not ref:
            continue
        ref["id"] = ref.get("id") or f"source:{index}"
        refs.append(ref)
    return refs


def _rss_candidate(item: dict, index: int) -> dict:
    markets = item.get("markets")
    if not isinstance(markets, list) or not markets:
        markets = infer_doc_markets({
            "title": item.get("title"),
            "summary": item.get("summary") or item.get("description") or item.get("content"),
            "content": item.get("content"),
            "url": item.get("url"),
            "source": item.get("media") or item.get("source"),
        })
    return {
        "id": f"rss:item:{index}",
        "title": _text(item.get("title"), 220),
        "source": _text(item.get("media") or item.get("source"), 80),
        "date": _text(item.get("timestamp") or item.get("date"), 40),
        "summary": _text(item.get("summary") or item.get("description") or item.get("content"), 360),
        "url": _text(item.get("url"), 500),
        "markets": markets,
    }


def _driver(value, index: int, lookup: dict[str, dict] | None = None) -> dict | None:
    if isinstance(value, str):
        title = _text(value, 120)
        return {"id": f"driver:{index}", "title": title, "summary": title, "sourceRefs": []} if title else None
    if not isinstance(value, dict):
        return None
    title = _text(value.get("title") or value.get("name") or value.get("stateLabel"), 140)
    summary = _text(value.get("summary") or value.get("interpretation") or value.get("rationale"), 700)
    if not title or not summary:
        return None
    source_refs = []
    raw_refs = value.get("sourceRefs") or value.get("sources") or []
    if isinstance(raw_refs, list):
        for ref in raw_refs[:8]:
            resolved = _resolve_source_ref(ref, lookup or {})
            source_id = _text((resolved or {}).get("id"), 80)
            if source_id:
                source_refs.append(source_id)
    return {
        "id": _text(value.get("id"), 80) or f"driver:{index}",
        "title": title,
        "summary": summary,
        "directionLabel": _text(value.get("directionLabel"), 40),
        "directionTone": _text(value.get("directionTone"), 40),
        "marketImpact": _text(value.get("marketImpact"), 700),
        "nextMemoryCheck": _text(value.get("nextMemoryCheck"), 300),
        "evidenceSummary": _text(value.get("evidenceSummary"), 500),
        "whyItMatters": _text(value.get("whyItMatters") or value.get("impact"), 500),
        "sourceRefs": source_refs,
    }


def _action_guide(value) -> dict:
    raw_action = value if isinstance(value, dict) else {}
    return {
        "headline": _text(raw_action.get("headline"), 120),
        "action": _text(raw_action.get("action"), 300),
        "timing": _text(raw_action.get("timing"), 300),
    }


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NUMBER_TOKEN = re.compile(r"\d+(?:[.,]\d+)*\s*%?")


def _interpretation_audit(text: str) -> dict:
    """시장 해석이 계약을 지켰는지 재서 남긴다. 되돌리지는 않는다.

    같은 규칙(`퍼센트 나열로 열지 말 것`)이 프롬프트에 있는 채로 두 번 깨졌다.
    프롬프트는 부탁이라 지켜졌는지 아무도 모르면 다음 판단이 눈대중이 된다.
    자르거나 실패시키지 않는 이유는 마지막 문장이 결론이고 재생성이 수십 초짜리
    CLI 호출이기 때문이다 — 재는 것과 되돌리는 것은 다른 결정이다.
    """
    sentences = [part for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    lead = sentences[0] if sentences else ""
    return {
        "chars": len(text),
        "sentences": len(sentences),
        "numbers": len(_NUMBER_TOKEN.findall(text)),
        "leadNumbers": len(_NUMBER_TOKEN.findall(lead)),
    }


def _view_label(key: str) -> str:
    """헤드라인이 비었을 때 쓰는 마지막 라벨.

    `key.upper()`는 화면에 `EUROPE`를 내보낸다. 나머지 문장이 전부 한국어인
    자리에 영문 코드가 앉으면 값이 빠진 티가 아니라 고장으로 읽힌다.
    """
    if key == "overall":
        return "종합"
    code = normalize_market_code(key)
    definition = MARKET_REGISTRY.get(code) if code in PRODUCT_MARKETS else None
    return definition.label_ko if definition else key.upper()


def _market_view(value, key: str, fallback: dict, lookup: dict[str, dict] | None = None) -> dict | None:
    if not isinstance(value, dict):
        return None
    headline = _text(value.get("headline") or value.get("title"), 160)
    # 시장 해석은 화면 상단의 큰 본문이다. 짧은 라벨과 같은 상한을 두면 모델이
    # 근거를 덧붙일수록 뒤가 잘린다. 상한은 폭주 방지용으로만 남긴다 — 계약은
    # 400자이고 이 값은 그 두 배다. 계약을 지킨 본문은 여기에 닿지 않는다.
    interpretation = _body_text(
        value.get("marketInterpretation")
        or value.get("oneLineSummary")
        or value.get("reasonSummary")
        or value.get("summary"),
        800,
    )
    action_summary = _text(value.get("actionSummary") or value.get("beginnerSummary") or value.get("actionPosture"), 420)
    drivers = [
        driver
        for index, raw in enumerate(_list(value.get("keyDrivers") or value.get("drivers"), limit=MAX_DRIVERS), 1)
        if (driver := _driver(raw, index, lookup))
    ]
    watch_items = [_text(item, 160) for item in _list(value.get("watchItems"), limit=MAX_WATCH_ITEMS)]
    watch_items = [item for item in watch_items if item]
    counter = [_text(item, 300) for item in _list(value.get("counterEvidence"), limit=MAX_COUNTER_EVIDENCE)]
    counter = [item for item in counter if item]
    uncertainties = [_text(item, 300) for item in _list(value.get("uncertainties"), limit=MAX_COUNTER_EVIDENCE)]
    uncertainties = [item for item in uncertainties if item]
    source_refs = _source_refs(value.get("sourceRefs") or value.get("sources") or [], lookup)
    action_guide = _action_guide(value.get("actionGuide"))
    if not headline and not interpretation and not action_summary and not drivers:
        return None
    return {
        "id": key,
        "headline": headline or fallback.get("headline") or _view_label(key),
        "marketInterpretation": interpretation or fallback.get("oneLineSummary") or "",
        "interpretationAudit": _interpretation_audit(interpretation or fallback.get("oneLineSummary") or ""),
        "actionSummary": action_summary or fallback.get("beginnerSummary") or fallback.get("actionPosture") or "",
        "actionGuide": action_guide if any(action_guide.values()) else fallback.get("actionGuide", {}),
        "keyDrivers": _enrich_market_view_drivers(
            drivers,
            fallback=fallback,
            interpretation=interpretation or fallback.get("oneLineSummary") or "",
            action_summary=action_summary or fallback.get("beginnerSummary") or fallback.get("actionPosture") or "",
        ) or fallback.get("keyDrivers", [])[:MAX_DRIVERS],
        "watchItems": watch_items or fallback.get("watchItems", [])[:MAX_WATCH_ITEMS],
        "counterEvidence": counter or fallback.get("counterEvidence", [])[:MAX_COUNTER_EVIDENCE],
        "uncertainties": uncertainties or fallback.get("uncertainties", [])[:MAX_COUNTER_EVIDENCE],
        "sourceRefs": source_refs or fallback.get("sourceRefs", [])[:MAX_SOURCE_REFS],
    }


def _enrich_market_view_drivers(
    drivers: list[dict],
    *,
    fallback: dict,
    interpretation: str,
    action_summary: str,
) -> list[dict]:
    if not drivers:
        return []
    enriched = []
    for driver in drivers:
        if not isinstance(driver, dict):
            continue
        next_driver = dict(driver)
        if not next_driver.get("whyItMatters"):
            next_driver["whyItMatters"] = interpretation or fallback.get("oneLineSummary") or next_driver.get("summary") or ""
        if not next_driver.get("evidenceSummary"):
            next_driver["evidenceSummary"] = interpretation or fallback.get("oneLineSummary") or next_driver.get("summary") or ""
        if not next_driver.get("marketImpact"):
            next_driver["marketImpact"] = action_summary or fallback.get("actionPosture") or next_driver.get("summary") or ""
        # 시장별 view의 드라이버는 자기 nextMemoryCheck/sourceRefs만 말한다.
        # 페이지 수준 watchItems나 다른 드라이버의 단어 유사도로 보완하면, 화면이
        # 존재하지 않는 연결·출처를 사실처럼 표시하게 된다.
        enriched.append(next_driver)
    return enriched


def _market_views(payload: dict, fallback: dict, lookup: dict[str, dict] | None = None) -> dict:
    raw_views = payload.get("marketViews") if isinstance(payload.get("marketViews"), dict) else {}
    views: dict[str, dict] = {}
    overall = _market_view(raw_views.get("overall") or {}, "overall", fallback, lookup)
    if not overall:
        overall = {
            "id": "overall",
            "headline": fallback.get("headline", ""),
            "marketInterpretation": fallback.get("oneLineSummary", ""),
            "actionSummary": fallback.get("beginnerSummary") or fallback.get("actionPosture", ""),
            "actionGuide": fallback.get("actionGuide", {}),
            "keyDrivers": fallback.get("keyDrivers", [])[:MAX_DRIVERS],
            "watchItems": fallback.get("watchItems", [])[:MAX_WATCH_ITEMS],
            "counterEvidence": fallback.get("counterEvidence", [])[:MAX_COUNTER_EVIDENCE],
            "uncertainties": fallback.get("uncertainties", [])[:MAX_COUNTER_EVIDENCE],
        }
    views["overall"] = overall
    for key in MARKET_VIEW_KEYS:
        view = _market_view(raw_views.get(key), key, fallback, lookup)
        if view:
            views[key] = view
    return views


def validate_market_state_snapshot(payload: dict, context: dict | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("MarketStateSnapshot payload must be an object")
    source_lookup = _source_ref_lookup(context)
    headline = _text(payload.get("headline") or payload.get("title"), 160)
    one_line = _text(payload.get("oneLineSummary") or payload.get("summary"), 600)
    beginner_summary = _text(payload.get("beginnerSummary") or payload.get("plainConclusion"), 360)
    posture = _text(payload.get("actionPosture") or payload.get("stance"), 400)
    action_guide = _action_guide(payload.get("actionGuide"))
    drivers = [
        driver
        for index, raw in enumerate(_list(payload.get("keyDrivers") or payload.get("drivers"), limit=MAX_DRIVERS), 1)
        if (driver := _driver(raw, index, source_lookup))
    ]
    watch_items = [_text(item, 160) for item in _list(payload.get("watchItems"), limit=MAX_WATCH_ITEMS)]
    watch_items = [item for item in watch_items if item]
    counter = [_text(item, 300) for item in _list(payload.get("counterEvidence"), limit=MAX_COUNTER_EVIDENCE)]
    counter = [item for item in counter if item]
    uncertainties = [_text(item, 300) for item in _list(payload.get("uncertainties"), limit=MAX_COUNTER_EVIDENCE)]
    uncertainties = [item for item in uncertainties if item]
    source_refs = _source_refs(payload.get("sourceRefs") or payload.get("sources") or [], source_lookup)
    missing = []
    if not headline:
        missing.append("headline")
    if not one_line:
        missing.append("oneLineSummary")
    if not posture:
        missing.append("actionPosture")
    if not drivers:
        missing.append("keyDrivers")
    if not watch_items:
        missing.append("watchItems")
    if not counter:
        missing.append("counterEvidence")
    if not source_refs:
        missing.append("sourceRefs")
    if missing:
        raise ValueError("MarketStateSnapshot missing required fields: " + ", ".join(missing))
    as_of = _text(payload.get("asOf"), 40) or now_iso()
    snapshot = {
        "id": _text(payload.get("id"), 80),
        "asOf": as_of,
        "horizon": _text(payload.get("horizon"), 40) or "medium_term",
        "status": _text(payload.get("status"), 40) or "agent_authored",
        "headline": headline,
        "oneLineSummary": one_line,
        "beginnerSummary": beginner_summary,
        "marketRegime": _text(payload.get("marketRegime") or payload.get("regime"), 80) or "mixed",
        "actionPosture": posture,
        "actionGuide": action_guide,
        "keyDrivers": drivers,
        "watchItems": watch_items,
        "counterEvidence": counter,
        "uncertainties": uncertainties,
        "sourceRefs": source_refs,
        "confidence": _confidence(payload.get("confidence")),
        "freshness": _text(payload.get("freshness"), 120) or "latest_available",
    }
    snapshot.update({
        key: payload[key] if key in payload else context[key]
        for key in ("inputWatermarks", "updateAttemptRef", "inputGraphBaseHash", "inputGraphTargetHash")
        if key in payload or isinstance(context, dict) and key in context
    })
    snapshot["marketViews"] = _market_views(payload, snapshot, source_lookup)
    snapshot = scrub_inline_refs(snapshot, source_lookup)
    for key in ("changeBasis", "changeSummary", "changeIntelligence"):
        if isinstance(payload.get(key), dict):
            snapshot[key] = payload[key]
    return snapshot


def ensure_snapshot_table(conn: sqlite3.Connection, *, initialize_graph: bool = True) -> None:
    if initialize_graph:
        init_db(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_state_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            as_of TEXT NOT NULL,
            horizon TEXT NOT NULL,
            status TEXT NOT NULL,
            headline TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_state_snapshots_as_of ON market_state_snapshots(as_of DESC)")


def save_market_state_snapshot(
    db_path: str | Path | sqlite3.Connection,
    payload: dict,
    context: dict | None = None,
) -> dict:
    match db_path:
        case sqlite3.Connection() as connection:
            conn = connection
            owns_connection = False
        case str() | Path():
            conn = connect(db_path)
            owns_connection = True
        case unreachable:
            assert_never(unreachable)
    try:
        ensure_snapshot_table(conn, initialize_graph=owns_connection)
        candidate = dict(payload or {})
        tentative_id = candidate.get("id") or "mss_" + re.sub(r"[^0-9A-Za-z]+", "", str(candidate.get("asOf") or now_iso()))[:24]
        candidate["id"] = tentative_id
        if not isinstance(candidate.get("changeBasis"), dict):
            from features.common.change_intelligence.adapters.market_memory import build_market_memory_basis
            from features.common.change_intelligence.baseline import select_market_memory_baseline
            from features.common.change_intelligence.basis import content_hash
            from features.common.change_intelligence.comparator import compare_basis
            from features.common.change_intelligence.projection import invalidation_token

            basis = build_market_memory_basis(candidate)
            previous, baseline_ref = select_market_memory_baseline(conn, basis)
            current_ref = {"storageKind": "market_state_snapshot", "id": tentative_id, "revision": None, "contentHash": content_hash(basis)}
            summary = compare_basis(basis, previous, current_ref=current_ref, baseline_ref=baseline_ref)
            candidate["changeBasis"] = basis
            candidate["changeSummary"] = summary
            candidate["changeIntelligence"] = {"status": summary["status"], "authorityKind": "market_state_snapshot", "projectionStatus": "pending", "invalidationToken": invalidation_token(summary)}
        snapshot = validate_market_state_snapshot(candidate, context=context)
        snapshot_id = snapshot.get("id") or tentative_id
        snapshot["id"] = snapshot_id
        conn.execute(
            """
            INSERT OR REPLACE INTO market_state_snapshots
            (snapshot_id, as_of, horizon, status, headline, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                snapshot["asOf"],
                snapshot["horizon"],
                snapshot["status"],
                snapshot["headline"],
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        if owns_connection and isinstance(snapshot.get("changeSummary"), dict):
            from features.common.change_intelligence.projection import upsert_change_projection

            upsert_change_projection(conn, snapshot["changeSummary"], authority_kind="market_state_snapshot", authority_id=snapshot_id)
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()
    return snapshot


def current_market_state_snapshot(
    db_path: str | Path | sqlite3.Connection = MARKET_MEMORY_DB_PATH,
) -> dict | None:
    match db_path:
        case sqlite3.Connection() as connection:
            conn = connection
            owns_connection = False
        case str() | Path():
            conn = connect(db_path)
            owns_connection = True
        case unreachable:
            assert_never(unreachable)
    try:
        ensure_snapshot_table(conn, initialize_graph=owns_connection)
        row = conn.execute(
            """
            SELECT snapshot_id, payload_json
            FROM market_state_snapshots
            WHERE status != 'archived'
            ORDER BY as_of DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        if owns_connection:
            conn.close()
    if not row:
        return None
    try:
        payload = json.loads(row["payload_json"])
        snapshot = validate_market_state_snapshot(payload)
        if not snapshot.get("id"):
            snapshot["id"] = row["snapshot_id"]
        return snapshot
    except Exception:
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return None


def latest_market_state_snapshot_as_of(
    db_path: str | Path = MARKET_MEMORY_DB_PATH,
) -> str | None:
    """가장 최근 화면 스냅샷이 만들어진 시각.

    payload를 열지 않고 `as_of` 열만 읽는다. 사전작업이 스냅샷 신선도를 메모리 갱신
    신선도와 **따로** 보기 위한 값이라, 브리핑 앞에서 매번 도는 경로다.
    """
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        conn = connect(path)
    except sqlite3.Error:
        return None
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_state_snapshots'"
        ).fetchone()
        if not table:
            return None
        row = conn.execute(
            """
            SELECT as_of
            FROM market_state_snapshots
            WHERE status != 'archived'
            ORDER BY as_of DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if not row:
        return None
    text = str(row["as_of"] or "").strip()
    return text or None


def _compact_state(state: dict) -> dict:
    return {
        "id": state.get("id") or state.get("memoryId") or "",
        "stateLabel": state.get("stateLabel") or state.get("story") or "",
        "momentum": state.get("momentum") or "stable",
        "confidence": state.get("confidence") or 0,
        "summary": _text(state.get("conclusion") or state.get("summary") or state.get("rationale"), 500),
        "evidenceCounts": {
            "d7": int(state.get("evidenceCount7d") or 0),
            "d30": int(state.get("evidenceCount30d") or 0),
            "d90": int(state.get("evidenceCount90d") or 0),
        },
    }


def build_market_state_context(
    *,
    rss_items: list[dict] | None = None,
    states: list[dict] | None = None,
    market_tape: dict | None = None,
    macro_snapshot: dict | None = None,
    include_market_macro: bool = True,
    market_scope: str = "overall",
    db_path: str | Path = MARKET_MEMORY_DB_PATH,
) -> dict:
    market_scope = str(market_scope or "overall").strip().lower()
    if market_scope not in {"overall", *MARKET_VIEW_KEYS}:
        market_scope = "overall"
    if rss_items is None:
        rss_items = _fetch_scoped_rss_items(market_scope)
    if states is None:
        states = list_states(db_path, status="current", limit=12)
    all_candidates = [
        candidate
        for index, item in enumerate((rss_items or [])[:RSS_CONTEXT_LIMIT], 1)
        if (candidate := _rss_candidate(item, index)).get("title")
    ]
    rss_candidates = _filter_candidates_for_scope(all_candidates, market_scope)
    digest_items = _filter_raw_rss_items_for_scope(rss_items or [], market_scope)
    digest = build_rss_digest(digest_items, limit=12)
    source_refs = []
    for item in rss_candidates[:MAX_SOURCE_REFS]:
        source_refs.append({
            "id": item["id"],
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "date": item.get("date", ""),
            "url": item.get("url", ""),
        })
    macro_context = build_market_macro_context(
        market_tape=market_tape,
        macro_snapshot=macro_snapshot,
        fetch_live=include_market_macro and market_tape is None and macro_snapshot is None,
    ) if include_market_macro else {"marketTape": {}, "macroSnapshot": {}}
    evidence_coverage = _evidence_coverage(rss_candidates, market_scope)
    # 경고는 컨텍스트 어딘가가 아니라 instruction 안에 있어야 모델이 먼저 읽는다.
    sparse_note = (" " + " ".join(evidence_coverage["warnings"])) if evidence_coverage["warnings"] else ""
    return {
        "instruction": (
            "Synthesize one medium-term MarketStateSnapshot for Folio OS. "
            f"This request is for marketScope={market_scope}. "
            "Use the broad rssCandidates list as the primary short-term evidence pool; it is lightly compacted but not scored or preselected by importance. "
            "shortTermDigest is only a navigation aid, not a selection result. "
            "existingStates are prior hypotheses to re-check, not conclusions to preserve. "
            "marketTape and macroSnapshot provide structured price, index, FX, rates, and macro context from yfinance/FRED/BOK when available; use them to confirm, weaken, or qualify news-driven narratives, not as prewritten conclusions. "
            "Financial market data is supporting evidence only; if marketTape or macroSnapshot is missing, stale, sparse, or hard to match, do not turn that into user-facing uncertainties. "
            "Each rssCandidate has markets tags (US/KR/GLOBAL/UNKNOWN). The list is already filtered for this marketScope, except overall keeps the broad pool. "
            "LLM should choose the important drivers from rssCandidates, marketTape, macroSnapshot, and existingStates, invalidate existingStates when new evidence contradicts them, then return judgment with evidence, counter-evidence, uncertainty, watch items, and marketViews for overall/us/kr/europe/jp when supported."
            + sparse_note
        ),
        "marketScope": market_scope,
        "evidenceCoverage": evidence_coverage,
        "marketDataPolicy": {
            "role": "supporting evidence only",
            "use": "Use marketTape and macroSnapshot to confirm, weaken, or qualify news-driven market interpretation.",
            "missingDataPolicy": "Do not include missing, stale, sparse, or weakly matched marketTape/macroSnapshot data in user-facing uncertainties.",
        },
        "priorUsePolicy": {
            "role": "hypothesis_to_recheck",
            "instruction": (
                "Do not anchor on existingStates or recursively repeat old Market Memory summaries. "
                "Use them as medium-term priors, then decide whether each is still supported, weakened, changed, or invalidated by rssCandidates."
            ),
        },
        "schema": {
            "required": [
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
            "marketViews": {
                "overall": "same structure as the top-level judgment, but focused on the combined market view",
                "us": "US market-specific judgment; keyDrivers must include title, summary, whyItMatters, evidenceSummary, marketImpact, nextMemoryCheck, sourceRefs",
                "kr": "Korea market-specific judgment; keyDrivers must include title, summary, whyItMatters, evidenceSummary, marketImpact, nextMemoryCheck, sourceRefs",
            },
        },
        "rssCandidates": rss_candidates,
        "shortTermDigest": digest,
        "marketTape": macro_context.get("marketTape") or {},
        "macroSnapshot": macro_context.get("macroSnapshot") or {},
        "existingStates": [_compact_state(state) for state in (states or [])[:12]],
        "sourceRefs": source_refs,
        "inputWatermarks": capture_input_watermarks(Path(db_path).parent / "research-index.sqlite3"),
    }


def _rss_item_key(item: dict) -> str:
    """같은 기사를 두 창에서 한 번씩 받으므로 합칠 때 쓸 열쇠."""
    for field in ("filename", "normalizedUrl", "url"):
        value = str(item.get(field) or "").strip().lower()
        if value:
            return f"{field}:{value}"
    title = _text(item.get("title"), 220).lower()
    source = _text(item.get("media") or item.get("source"), 80).lower()
    return f"title:{title}|{source}"


def _fetch_scoped_rss_items(market_scope: str) -> list[dict]:
    """시장별 스냅샷은 그 시장의 근거 창을 따로 받는다.

    시장 무관 최신 120건을 받아 뒤에서 거르면 남는 것은 피드 분포다. JP 피드는 3개뿐이라
    EUROPE/JP는 GLOBAL만 남아 근거 없는 시장 판단이 조용히 나갔다.
    `rss_feed_payload`의 market 필터(`_normalize_market_filter`)는 US/KR/EUROPE/JP/
    GLOBAL/UNKNOWN 중 **하나**만 받으므로 두 태그를 한 질의로 OR 할 수 없다. 시장 창과
    GLOBAL 창을 따로 받아 합치며, 이 합집합은 `_candidate_matches_scope`(시장 태그 또는
    GLOBAL)와 같은 범위다.
    """
    from features.common.research_library.rss.service import rss_feed_payload

    if market_scope == "overall":
        payload = rss_feed_payload({"limit": [str(RSS_CONTEXT_LIMIT)], "offset": ["0"]})
        return list(payload.get("items") or [])
    merged: list[dict] = []
    seen: set[str] = set()
    for market in (market_scope.upper(), "GLOBAL"):
        payload = rss_feed_payload({
            "limit": [str(RSS_CONTEXT_LIMIT)],
            "offset": ["0"],
            "market": [market],
        })
        for item in payload.get("items") or []:
            key = _rss_item_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    # 두 창을 이어 붙이면 GLOBAL이 통째로 뒤로 밀린다. 목록 계약(최신순)을 유지한다.
    merged.sort(key=lambda item: str(item.get("timestampSort") or item.get("timestamp") or ""), reverse=True)
    return merged[:RSS_CONTEXT_LIMIT]


def _evidence_coverage(candidates: list[dict], market_scope: str) -> dict:
    """근거가 얼마나 얇은지 프롬프트가 알게 한다.

    풀이 비어도 모델은 그 사실을 모른 채 시장 판단을 쓴다. 부족하면 컨텍스트에
    남겨 "근거가 얇다"가 판단의 일부가 되게 한다.
    """
    count = len(candidates)
    sparse = count < RSS_CANDIDATE_MIN
    coverage = {
        "marketScope": market_scope,
        "rssCandidateCount": count,
        "minimumExpected": RSS_CANDIDATE_MIN,
        "status": "sparse" if sparse else "sufficient",
        "warnings": [],
    }
    if sparse:
        coverage["warnings"].append(
            f"marketScope={market_scope}: rssCandidates {count} items "
            f"(below {RSS_CANDIDATE_MIN}). Evidence for this market is thin; "
            "state that limitation instead of writing a confident market judgment."
        )
    return coverage


def _candidate_matches_scope(candidate: dict, market_scope: str) -> bool:
    markets = {str(item or "").upper() for item in (candidate.get("markets") or [])}
    if market_scope == "overall":
        return True
    # 시장 키(MARKET_VIEW_KEYS)는 PRODUCT_MARKETS 파생이므로 비교도 파생으로 한다.
    # 리터럴 분기로 두면 새로 열린 시장(europe/jp)이 조용히 전부 통과해,
    # "이 목록은 이 marketScope로 이미 걸러졌다"는 instruction이 거짓이 된다.
    return market_scope.upper() in markets or "GLOBAL" in markets


def _filter_candidates_for_scope(candidates: list[dict], market_scope: str) -> list[dict]:
    return [candidate for candidate in candidates if _candidate_matches_scope(candidate, market_scope)]


def _filter_raw_rss_items_for_scope(items: list[dict], market_scope: str) -> list[dict]:
    if market_scope == "overall":
        return list(items)
    scoped = []
    for index, item in enumerate(items[:RSS_CONTEXT_LIMIT], 1):
        candidate = _rss_candidate(item, index)
        if _candidate_matches_scope(candidate, market_scope):
            scoped.append(item)
    return scoped


def market_memory_context_pack(db_path: str | Path = MARKET_MEMORY_DB_PATH) -> dict:
    snapshot = current_market_state_snapshot(db_path)
    if not snapshot:
        states = list_states(db_path, status="current", limit=5)
        if not states:
            return {"available": False, "source": "empty"}
        return {
            "available": True,
            "source": "state_fallback",
            "headline": "현재 중기 시장 상황",
            "summary": "저장된 Agent 스냅샷이 없어 기존 Market Memory 상태를 압축한 fallback입니다.",
            "actionPosture": "",
            "keyDrivers": [_compact_state(state) for state in states[:5]],
            "watchItems": [],
            "counterEvidence": [],
            "uncertainties": [],
            "sourceRefs": [],
            "confidence": 0.5,
        }
    return {
        "available": True,
        "source": "market_state_snapshot",
        "headline": snapshot.get("headline", ""),
        "summary": snapshot.get("oneLineSummary", ""),
        "marketRegime": snapshot.get("marketRegime", ""),
        "actionPosture": snapshot.get("actionPosture", ""),
        "keyDrivers": snapshot.get("keyDrivers", [])[:MAX_DRIVERS],
        "watchItems": snapshot.get("watchItems", [])[:MAX_WATCH_ITEMS],
        "counterEvidence": snapshot.get("counterEvidence", [])[:MAX_COUNTER_EVIDENCE],
        "uncertainties": snapshot.get("uncertainties", [])[:MAX_COUNTER_EVIDENCE],
        "sourceRefs": snapshot.get("sourceRefs", [])[:MAX_SOURCE_REFS],
        "marketViews": snapshot.get("marketViews") or {},
        "confidence": snapshot.get("confidence", 0.5),
        "asOf": snapshot.get("asOf", ""),
        "freshness": snapshot.get("freshness", ""),
    }


def render_market_memory_context(db_path: str | Path = MARKET_MEMORY_DB_PATH, *, max_sources: int = 6) -> str:
    pack = market_memory_context_pack(db_path)
    if not pack.get("available"):
        return ""
    lines = [
        "## Market Memory Context",
        "이 블록은 Folio OS의 중기 시장 배경입니다. 기업 고유 사실의 evidence가 아니라 시장 배경/context로만 사용하세요.",
        f"- source: {pack.get('source', '')}",
        f"- headline: {pack.get('headline', '')}",
        f"- summary: {pack.get('summary', '')}",
    ]
    if pack.get("marketRegime"):
        lines.append(f"- marketRegime: {pack.get('marketRegime')}")
    if pack.get("actionPosture"):
        lines.append(f"- actionPosture: {pack.get('actionPosture')}")
    if pack.get("watchItems"):
        lines.extend(["", "### Watch Items", *[f"- {item}" for item in pack.get("watchItems", [])[:MAX_WATCH_ITEMS]]])
    views = pack.get("marketViews") or {}
    if isinstance(views, dict) and views:
        lines.append("")
        lines.append("### Market Views")
        for key in ("overall", *MARKET_VIEW_KEYS):
            view = views.get(key)
            if not isinstance(view, dict):
                continue
            lines.append(f"- {key}: {view.get('headline', '')} | {view.get('marketInterpretation', '')} | {view.get('actionSummary', '')}".strip())
    drivers = pack.get("keyDrivers") or []
    if drivers:
        lines.append("")
        lines.append("### Key Drivers")
        for driver in drivers[:MAX_DRIVERS]:
            if not isinstance(driver, dict):
                continue
            title = driver.get("title") or driver.get("stateLabel") or ""
            summary = driver.get("summary") or ""
            if title or summary:
                lines.append(f"- {title}: {summary}".strip())
    if pack.get("counterEvidence"):
        lines.extend(["", "### Counter Evidence", *[f"- {item}" for item in pack.get("counterEvidence", [])[:MAX_COUNTER_EVIDENCE]]])
    if pack.get("uncertainties"):
        lines.extend(["", "### Uncertainties", *[f"- {item}" for item in pack.get("uncertainties", [])[:MAX_COUNTER_EVIDENCE]]])
    sources = pack.get("sourceRefs") or []
    if sources:
        lines.append("")
        lines.append("### Source Refs")
        for source in sources[: int(max_sources or 6)]:
            if not isinstance(source, dict):
                continue
            label = " | ".join(part for part in [
                source.get("id", ""),
                source.get("source", ""),
                source.get("title", ""),
                source.get("date", ""),
            ] if part)
            if label:
                lines.append(f"- {label}")
    return "\n".join(lines).strip()
