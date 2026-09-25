# Agentic Folio OS Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working foundation for always-available Agent UX, RSS-driven Market Memory, Market State Dashboard v2, and local automation settings.

**Architecture:** Add focused feature modules instead of expanding `app.py`: Agent companion APIs live under `features/agent_mode`, RSS digest and Market State summary live under `features/market_memory`, automation lives under `features/automation`, and `public/` gets the initial dock/dashboard/settings UI. Existing job infrastructure, Agent Mode context packs, RSS cache/indexing, and market-memory SQLite tables are reused.

**Tech Stack:** Python 3, FastAPI, SQLite, JSON settings files, existing vanilla `public/index.html` + `public/app.js` + `public/styles.css`, existing job system in `features/common/jobs.py`.

## Global Constraints

- `app.py` stays thin: endpoints, request normalization, feature service calls, HTTP exception conversion only.
- Canonical report markdown must not be changed by Agent companion answers or Market Memory updates.
- Agent Task Mode writeback requires explicit user approval before saved reports or Market Memory are mutated.
- RSS remains in `research-inbox/rss/`; do not recreate legacy `archive/`.
- Paid content bypass is forbidden; use public RSS, public links, and user-saved materials only.
- User notes and Obsidian imports remain hypothesis, never evidence.
- Market Memory conclusions and roles must use code-normalized enums.
- Automation runs only while the local Folio OS server is running; missed-run behavior must be explicit.
- UI must remain usable on mobile.
- Phase 3 Native Investment Notes and Phase 4 gradual React Shell remain roadmap items, but this plan does not implement them.

---

## File Structure

Create:

- `features/agent_mode/companion.py`  
  Builds current-screen Agent context, classifies Companion vs Task intent, returns safe assistant replies and action cards.
- `features/agent_mode/tests/test_companion.py`  
  Unit tests for context normalization, intent classification, action suggestions, and no-write behavior.
- `features/market_memory/digest.py`  
  Reads RSS/evidence rows, builds short-term digest items, promotes eligible items into normalized Market Memory entries.
- `features/market_memory/state_dashboard.py`  
  Creates one user-facing medium-term market state summary plus 3-5 driver cards from existing states.
- `features/market_memory/tests/test_digest.py`  
  Unit tests for RSS digest clustering and promotion thresholds.
- `features/market_memory/tests/test_state_dashboard.py`  
  Unit tests for concise market state summary and hidden internal fields.
- `features/automation/__init__.py`
- `features/automation/README.md`
- `features/automation/schema.py`  
  Normalizes automation settings, schedules, run records, and missed-run policy.
- `features/automation/service.py`  
  Reads/writes settings, starts/stops scheduler loop, submits jobs, records run summaries.
- `features/automation/tests/test_schema.py`
- `features/automation/tests/test_service.py`

Modify:

- `app.py`  
  Add thin API endpoints for Agent companion, Market Memory digest/dashboard, and automation settings/runs.
- `features/market_memory/README.md`  
  Document RSS short-term memory and Market State Dashboard v2.
- `features/agent_mode/README.md`  
  Document Companion Mode vs Task Mode and current screen context.
- `features/frontend_ui/README.md`  
  Document global Agent Dock and Market State Dashboard v2 UI contracts.
- `public/index.html`  
  Add Agent dock shell, in-reader Ask Agent drawer host, Market State v2 containers, automation settings panel.
- `public/app.js`  
  Add Agent context tracking, dock rendering, API calls, dashboard rendering, automation settings behavior.
- `public/styles.css`  
  Add responsive dock, drawer, dashboard, and automation styles.

---

### Task 1: Agent Companion Backend

**Files:**
- Create: `features/agent_mode/companion.py`
- Create: `features/agent_mode/tests/test_companion.py`
- Modify: `app.py`
- Modify: `features/agent_mode/README.md`

**Interfaces:**
- Consumes: current screen context from frontend as `dict`
- Produces:
  - `normalize_agent_context(raw: dict) -> dict`
  - `classify_agent_intent(message: str) -> str`
  - `agent_companion_reply(message: str, context: dict) -> dict`
  - `POST /api/agent/companion`

- [ ] **Step 1: Write failing tests for context normalization and intent classification**

Create `features/agent_mode/tests/test_companion.py`:

```python
from features.agent_mode.companion import (
    agent_companion_reply,
    classify_agent_intent,
    normalize_agent_context,
)


def test_normalize_agent_context_keeps_safe_fields_only():
    raw = {
        "surface": "briefing_reader",
        "viewId": "briefing",
        "reportKind": "briefing",
        "reportId": "2026-07-02.us",
        "marketScope": "us",
        "selectedText": "AI capex remains central",
        "visibleSection": "leading_companies",
        "apiKey": "sk-proj-secret",
        "token": "secret",
    }
    ctx = normalize_agent_context(raw)
    assert ctx == {
        "surface": "briefing_reader",
        "viewId": "briefing",
        "reportKind": "briefing",
        "reportId": "2026-07-02.us",
        "marketScope": "us",
        "selectedText": "AI capex remains central",
        "visibleSection": "leading_companies",
        "portfolioLinked": False,
    }


def test_classify_agent_intent_starts_as_companion_for_questions():
    assert classify_agent_intent("이 브리핑에서 제일 중요한 게 뭐야?") == "companion"
    assert classify_agent_intent("내 포트폴리오에 어떤 의미야?") == "companion"


def test_classify_agent_intent_switches_to_task_for_mutating_requests():
    assert classify_agent_intent("이 기업분석에 bear case 섹션 추가해줘") == "task"
    assert classify_agent_intent("최신 RSS로 Market Memory 업데이트해줘") == "task"
    assert classify_agent_intent("내일 아침 브리핑 자동화 설정해줘") == "task"


def test_companion_reply_never_writes_state():
    result = agent_companion_reply(
        "이 브리핑에서 반대로 볼 근거는?",
        {"surface": "briefing_reader", "reportKind": "briefing", "reportId": "2026-07-02.us"},
    )
    assert result["mode"] == "companion"
    assert result["requiresApproval"] is False
    assert result["writeback"] is None
    assert any(action["id"] == "create_personal_overlay" for action in result["actions"])
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
py -3 -m pytest features\agent_mode\tests\test_companion.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement minimal companion service**

Create `features/agent_mode/companion.py`:

```python
from __future__ import annotations

from features.agent_mode.schema import scrub_secrets

SAFE_CONTEXT_FIELDS = {
    "surface",
    "viewId",
    "reportKind",
    "reportId",
    "marketScope",
    "selectedText",
    "visibleSection",
    "portfolioLinked",
}

TASK_VERBS = (
    "수정",
    "추가",
    "다시 써",
    "재작성",
    "보강",
    "생성",
    "업데이트",
    "정리해줘",
    "설정",
    "자동화",
    "writeback",
    "rewrite",
    "revise",
    "update",
    "create",
    "schedule",
)


def normalize_agent_context(raw: dict | None) -> dict:
    raw = scrub_secrets(raw or {})
    out = {}
    for field in SAFE_CONTEXT_FIELDS:
        value = raw.get(field)
        if field == "portfolioLinked":
            out[field] = bool(value)
        else:
            out[field] = str(value or "").strip()[:2000]
    out.setdefault("portfolioLinked", False)
    return {
        "surface": out.get("surface", ""),
        "viewId": out.get("viewId", ""),
        "reportKind": out.get("reportKind", ""),
        "reportId": out.get("reportId", ""),
        "marketScope": out.get("marketScope", ""),
        "selectedText": out.get("selectedText", ""),
        "visibleSection": out.get("visibleSection", ""),
        "portfolioLinked": bool(out.get("portfolioLinked")),
    }


def classify_agent_intent(message: str) -> str:
    text = str(message or "").strip().lower()
    if any(verb in text for verb in TASK_VERBS):
        return "task"
    return "companion"


def _surface_actions(context: dict) -> list[dict]:
    report_kind = context.get("reportKind", "")
    view_id = context.get("viewId", "")
    actions = [
        {"id": "explain_counterpoints", "label": "반대 근거 보기", "requiresApproval": False},
        {"id": "portfolio_impact", "label": "포트폴리오 영향 보기", "requiresApproval": False},
    ]
    if report_kind in {"briefing", "company_analysis", "topic_report"}:
        actions.append({"id": "create_personal_overlay", "label": "Personal Overlay 생성", "requiresApproval": True})
    if view_id in {"memory", "market_memory"}:
        actions.append({"id": "refresh_market_memory_digest", "label": "Market Memory 최신화", "requiresApproval": True})
    return actions


def agent_companion_reply(message: str, context: dict | None = None) -> dict:
    normalized = normalize_agent_context(context)
    mode = classify_agent_intent(message)
    if mode == "task":
        return {
            "ok": True,
            "mode": "task",
            "message": "작업 요청으로 이해했습니다. 실행 전에 계획과 저장될 대상을 먼저 확인해야 합니다.",
            "context": normalized,
            "actions": _surface_actions(normalized),
            "requiresApproval": True,
            "writeback": None,
        }
    return {
        "ok": True,
        "mode": "companion",
        "message": "현재 화면을 기준으로 질문에 답할 준비가 되어 있습니다. 저장된 보고서나 메모리는 사용자가 승인하기 전에는 변경하지 않습니다.",
        "context": normalized,
        "actions": _surface_actions(normalized),
        "requiresApproval": False,
        "writeback": None,
    }
```

- [ ] **Step 4: Add thin API endpoint**

Modify `app.py` imports:

```python
from features.agent_mode.companion import agent_companion_reply
```

Add endpoint near existing Agent Bridge endpoints:

```python
@fastapi_app.post("/api/agent/companion")
def api_agent_companion(body: dict | None = Body(default=None)):
    body = body or {}
    return agent_companion_reply(body.get("message", ""), body.get("context") or {})
```

- [ ] **Step 5: Run tests**

Run:

```powershell
py -3 -m pytest features\agent_mode\tests\test_companion.py -q
py -3 -m py_compile app.py features\agent_mode\companion.py
```

Expected: tests PASS and compile succeeds.

- [ ] **Step 6: Document Companion vs Task Mode**

Append to `features/agent_mode/README.md`:

```markdown
## Global Agent Companion

The global Agent starts in Companion Mode on every screen. Companion Mode can answer questions, summarize visible context, suggest next actions, and explain implications without mutating saved reports or Market Memory.

When the user explicitly asks to revise, create, update, schedule, or write back work, the Agent switches to Task Mode. Task Mode must show the intended operation and require approval before saved JSON, SQLite, or report markdown is changed.
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add app.py features\agent_mode\companion.py features\agent_mode\tests\test_companion.py features\agent_mode\README.md
git commit -m "feat: add agent companion backend"
```

Expected: commit succeeds.

---

### Task 2: Market Memory RSS Digest

**Files:**
- Create: `features/market_memory/digest.py`
- Create: `features/market_memory/tests/test_digest.py`
- Modify: `app.py`
- Modify: `features/market_memory/README.md`

**Interfaces:**
- Consumes: RSS/evidence-like rows with `title`, `description`, `media`, `timestamp`, `url`, `relatedTickers`, `sourceType`
- Produces:
  - `DigestItem` dict shape
  - `build_rss_digest(items: list[dict], *, limit: int = 12) -> list[dict]`
  - `promote_digest_items(digest_items: list[dict], *, date: str = "") -> list[dict]`
  - `run_rss_market_memory_update(date: str = "") -> dict`
  - `POST /api/memory/rss-digest`

- [ ] **Step 1: Write failing digest tests**

Create `features/market_memory/tests/test_digest.py`:

```python
from features.market_memory.digest import build_rss_digest, promote_digest_items


def test_build_rss_digest_clusters_ai_semiconductor_items():
    items = [
        {"title": "Nvidia suppliers rise on AI server demand", "description": "HBM and GPU supply chain", "media": "Reuters", "timestamp": "2026-07-02 08:00:00", "url": "https://a.example/1"},
        {"title": "SK hynix HBM demand strengthens", "description": "AI chips and memory", "media": "Bloomberg", "timestamp": "2026-07-02 08:10:00", "url": "https://a.example/2"},
        {"title": "Oil edges lower", "description": "crude market waits", "media": "Reuters", "timestamp": "2026-07-02 08:20:00", "url": "https://a.example/3"},
    ]
    digest = build_rss_digest(items)
    ai = [item for item in digest if item["stateKey"] == "ai_semiconductor_supply_chain"][0]
    assert ai["sourceCount"] == 2
    assert sorted(ai["publishers"]) == ["Bloomberg", "Reuters"]
    assert ai["promotionCandidate"] is True


def test_promote_digest_items_requires_repeated_signal():
    digest = [
        {
            "stateKey": "ai_semiconductor_supply_chain",
            "stateLabel": "AI 반도체 공급망",
            "summary": "AI 반도체 공급망 관련 신호가 복수 출처에서 반복됐다.",
            "sourceCount": 2,
            "publishers": ["Reuters", "Bloomberg"],
            "sources": [{"title": "A", "source": "Reuters"}, {"title": "B", "source": "Bloomberg"}],
            "promotionCandidate": True,
        },
        {
            "stateKey": "middle_east_energy_risk",
            "stateLabel": "중동 에너지 리스크",
            "summary": "단일 기사성 유가 움직임.",
            "sourceCount": 1,
            "publishers": ["Reuters"],
            "sources": [{"title": "C", "source": "Reuters"}],
            "promotionCandidate": False,
        },
    ]
    promoted = promote_digest_items(digest, date="2026-07-02")
    assert len(promoted) == 1
    assert promoted[0]["stateKey"] == "ai_semiconductor_supply_chain"
    assert promoted[0]["entryMode"] == "issue"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
py -3 -m pytest features\market_memory\tests\test_digest.py -q
```

Expected: FAIL with missing module/functions.

- [ ] **Step 3: Implement rules-first digest**

Create `features/market_memory/digest.py`:

```python
from __future__ import annotations

from collections import defaultdict

from features.common.utils import kst_date, now_iso
from features.market_memory.memory import upsert_memory

MARKET_MEMORY_DB_PATH = "data/market-memory.sqlite3"

AXES = {
    "ai_semiconductor_supply_chain": {
        "label": "AI 반도체 공급망",
        "terms": ("ai", "nvidia", "hbm", "gpu", "semiconductor", "chip", "반도체", "하이닉스", "삼성전자"),
        "tags": ["AI", "Semiconductors"],
    },
    "ai_data_center_power_bottleneck": {
        "label": "AI 데이터센터 전력 병목",
        "terms": ("power", "grid", "data center", "utility", "전력", "데이터센터", "전선", "구리"),
        "tags": ["AI", "Energy"],
    },
    "rates_dollar_liquidity": {
        "label": "금리·달러 유동성",
        "terms": ("fed", "rate", "yield", "bond", "dollar", "금리", "국채", "달러", "환율"),
        "tags": ["금리", "환율"],
    },
    "middle_east_energy_risk": {
        "label": "중동 에너지 리스크",
        "terms": ("oil", "iran", "hormuz", "middle east", "crude", "유가", "중동", "이란", "호르무즈"),
        "tags": ["Energy"],
    },
    "korea_semiconductor_exports_fx_sensitivity": {
        "label": "한국 반도체 수출 수혜와 원화·수급 긴장",
        "terms": ("korea", "kospi", "krw", "export", "한국", "코스피", "원화", "수출", "반도체"),
        "tags": ["Semiconductors", "환율"],
    },
}


def _text(item: dict) -> str:
    return " ".join(str(item.get(key, "")) for key in ("title", "description", "summary", "media")).lower()


def _source(item: dict) -> dict:
    return {
        "title": str(item.get("title", ""))[:220],
        "source": str(item.get("media") or item.get("source") or "")[:80],
        "date": str(item.get("timestamp") or item.get("date") or "")[:30],
        "url": str(item.get("url", ""))[:500],
    }


def build_rss_digest(items: list[dict], *, limit: int = 12) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in items or []:
        hay = _text(item)
        for key, spec in AXES.items():
            if any(term.lower() in hay for term in spec["terms"]):
                buckets[key].append(item)
                break
    digest = []
    for key, rows in buckets.items():
        spec = AXES[key]
        publishers = sorted({str(row.get("media") or row.get("source") or "").strip() for row in rows if str(row.get("media") or row.get("source") or "").strip()})
        sources = [_source(row) for row in rows[:6]]
        promotion = len(sources) >= 2 and len(publishers) >= 2
        digest.append({
            "stateKey": key,
            "stateLabel": spec["label"],
            "summary": f"{spec['label']} 관련 신호가 {len(sources)}개 자료에서 관찰됐다.",
            "sourceCount": len(sources),
            "publishers": publishers,
            "sources": sources,
            "tags": spec["tags"],
            "promotionCandidate": promotion,
        })
    digest.sort(key=lambda row: (row["promotionCandidate"], row["sourceCount"], len(row["publishers"])), reverse=True)
    return digest[: int(limit or 12)]


def promote_digest_items(digest_items: list[dict], *, date: str = "") -> list[dict]:
    date = date or kst_date()
    promoted = []
    for item in digest_items or []:
        if not item.get("promotionCandidate"):
            continue
        promoted.append({
            "date": date,
            "asOf": now_iso(),
            "title": f"{item['stateLabel']} RSS 단기 신호",
            "summary": item["summary"],
            "story": item["stateKey"],
            "storyFamily": item["stateLabel"],
            "storyThesis": item["summary"],
            "storyCheckpoint": "후속 가격 반응, 거래대금, 수급, 기업 가이던스 변화를 확인",
            "stateKey": item["stateKey"],
            "stateLabel": item["stateLabel"],
            "parentStory": item["stateKey"],
            "storyRelation": "same_family",
            "stateBias": "neutral",
            "category": "stock_bond",
            "region": "GLOBAL",
            "importance": "medium",
            "entryMode": "issue",
            "eventKind": "industry_trend",
            "sourceKind": "rss_digest",
            "tags": item.get("tags", []),
            "sources": item.get("sources", []),
            "dedupeKey": f"rss_digest:{date}:{item['stateKey']}",
        })
    return promoted


def run_rss_market_memory_update(date: str = "", items: list[dict] | None = None) -> dict:
    if items is None:
        from features.common.research_library.rss.service import rss_feed_payload
        payload = rss_feed_payload({"limit": ["200"], "offset": ["0"]})
        items = payload.get("items", [])
    digest = build_rss_digest(items or [])
    promoted = promote_digest_items(digest, date=date or kst_date())
    saved = [upsert_memory(MARKET_MEMORY_DB_PATH, entry) for entry in promoted]
    return {
        "ok": True,
        "digestCount": len(digest),
        "promotedCount": len(promoted),
        "saved": saved,
        "digest": digest,
    }
```

- [ ] **Step 4: Add endpoint**

Modify `app.py` imports:

```python
from features.market_memory.digest import run_rss_market_memory_update
```

Add endpoint near memory endpoints:

```python
@fastapi_app.post("/api/memory/rss-digest")
def api_memory_rss_digest(body: dict | None = Body(default=None)):
    body = body or {}
    return run_rss_market_memory_update(date=body.get("date", ""))
```

- [ ] **Step 5: Run tests**

Run:

```powershell
py -3 -m pytest features\market_memory\tests\test_digest.py -q
py -3 -m py_compile app.py features\market_memory\digest.py
```

Expected: tests PASS and compile succeeds.

- [ ] **Step 6: Document RSS short-term memory**

Append to `features/market_memory/README.md`:

```markdown
## RSS Short-Term Memory Intake

Market Memory can be updated from RSS/evidence before a briefing is generated. RSS items are first grouped into short-term digest items. Only repeated, source-diverse, market-relevant digest items are promoted into medium-term Market Memory entries.

This keeps the hierarchy explicit: RSS/evidence is short-term memory, Market Memory is medium-term memory, and reports consume both.
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add app.py features\market_memory\digest.py features\market_memory\tests\test_digest.py features\market_memory\README.md
git commit -m "feat: update market memory from rss digest"
```

Expected: commit succeeds.

---

### Task 3: Market State Dashboard Backend

**Files:**
- Create: `features/market_memory/state_dashboard.py`
- Create: `features/market_memory/tests/test_state_dashboard.py`
- Modify: `app.py`
- Modify: `features/market_memory/README.md`

**Interfaces:**
- Consumes: `features.market_memory.memory.list_states`
- Produces:
  - `market_state_dashboard_payload(db_path=MARKET_MEMORY_DB_PATH, limit=5) -> dict`
  - `GET /api/memory/state-dashboard`

- [ ] **Step 1: Write failing tests**

Create `features/market_memory/tests/test_state_dashboard.py`:

```python
from features.market_memory.state_dashboard import summarize_market_state


def test_summarize_market_state_returns_one_summary_and_five_drivers():
    states = [
        {"stateLabel": "AI 반도체 공급망", "momentum": "strengthening", "confidence": 0.82, "summary": "AI 공급망 실적 기대가 강화됐다.", "rationale": "HBM 수요 확인"},
        {"stateLabel": "AI 데이터센터 전력 병목", "momentum": "strengthening", "confidence": 0.7, "summary": "전력 병목이 수혜 범위를 넓힌다.", "rationale": "전력기기 수주 확인"},
        {"stateLabel": "금리·달러 유동성", "momentum": "conflicted", "confidence": 0.58, "summary": "금리와 달러는 성장주 상단을 제한한다.", "rationale": "국채금리 확인"},
        {"stateLabel": "중동 에너지 리스크", "momentum": "stable", "confidence": 0.52, "summary": "유가 리스크는 관망 상태다.", "rationale": "유가 반응 확인"},
        {"stateLabel": "한국 반도체 수출", "momentum": "stable", "confidence": 0.61, "summary": "한국 반도체 수출 기대가 유지된다.", "rationale": "수출 데이터 확인"},
        {"stateLabel": "잡음", "momentum": "stable", "confidence": 0.1, "summary": "숨겨야 한다.", "rationale": ""},
    ]
    payload = summarize_market_state(states, limit=5)
    assert payload["title"] == "현재 중기 시장 상황"
    assert len(payload["drivers"]) == 5
    assert "AI 반도체 공급망" in payload["summary"]
    assert "rawEvidence" not in payload["drivers"][0]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
py -3 -m pytest features\market_memory\tests\test_state_dashboard.py -q
```

Expected: FAIL with missing module/functions.

- [ ] **Step 3: Implement dashboard summary**

Create `features/market_memory/state_dashboard.py`:

```python
from __future__ import annotations

from pathlib import Path

from features.market_memory.memory import list_states

ROOT = Path(__file__).resolve().parents[2]
MARKET_MEMORY_DB_PATH = ROOT / "data" / "market-memory.sqlite3"

MOMENTUM_LABELS = {
    "strengthening": "강화",
    "stable": "유지",
    "fading": "약화",
    "turning": "전환",
    "conflicted": "혼재",
}


def confidence_label(value) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def summarize_market_state(states: list[dict], *, limit: int = 5) -> dict:
    ranked = sorted(
        states or [],
        key=lambda row: (float(row.get("confidence") or 0), row.get("momentum") == "strengthening"),
        reverse=True,
    )[: int(limit or 5)]
    drivers = []
    for state in ranked:
        drivers.append({
            "title": state.get("stateLabel") or state.get("story") or "시장 내러티브",
            "momentum": state.get("momentum") or "stable",
            "momentumLabel": MOMENTUM_LABELS.get(state.get("momentum"), "유지"),
            "confidence": confidence_label(state.get("confidence")),
            "interpretation": state.get("summary") or state.get("rationale") or "",
            "nextCheckpoint": state.get("rationale") or "",
            "askAgentPrompt": f"{state.get('stateLabel') or '이 내러티브'}가 내 포트폴리오에 주는 의미를 설명해줘",
        })
    if not drivers:
        summary = "아직 정리된 중기 시장 상황이 없습니다. RSS 수집과 Market Memory 정리를 먼저 실행하세요."
    else:
        lead = drivers[0]["title"]
        rest = ", ".join(item["title"] for item in drivers[1:3])
        summary = f"{lead}이 현재 시장 이해의 중심축이며, {rest} 흐름이 함께 시장의 폭과 리스크를 결정하고 있습니다.".strip()
    return {
        "title": "현재 중기 시장 상황",
        "summary": summary,
        "drivers": drivers,
        "hiddenInternals": ["taxonomy", "storyMap", "audit", "familySuggestions", "rawEvidence"],
    }


def market_state_dashboard_payload(db_path: str | Path = MARKET_MEMORY_DB_PATH, *, limit: int = 5) -> dict:
    states = list_states(db_path, status="current", limit=30)
    return summarize_market_state(states, limit=limit)
```

- [ ] **Step 4: Add endpoint**

Modify `app.py` imports:

```python
from features.market_memory.state_dashboard import market_state_dashboard_payload
```

Add endpoint:

```python
@fastapi_app.get("/api/memory/state-dashboard")
def api_market_state_dashboard(limit: int = 5):
    return market_state_dashboard_payload(MARKET_MEMORY_DB_PATH, limit=limit)
```

- [ ] **Step 5: Run tests**

Run:

```powershell
py -3 -m pytest features\market_memory\tests\test_state_dashboard.py -q
py -3 -m py_compile app.py features\market_memory\state_dashboard.py
```

Expected: tests PASS and compile succeeds.

- [ ] **Step 6: Commit**

Run:

```powershell
git add app.py features\market_memory\state_dashboard.py features\market_memory\tests\test_state_dashboard.py features\market_memory\README.md
git commit -m "feat: add market state dashboard payload"
```

Expected: commit succeeds.

---

### Task 4: Automation Settings and Runner Backend

**Files:**
- Create: `features/automation/__init__.py`
- Create: `features/automation/schema.py`
- Create: `features/automation/service.py`
- Create: `features/automation/tests/test_schema.py`
- Create: `features/automation/tests/test_service.py`
- Create: `features/automation/README.md`
- Modify: `app.py`

**Interfaces:**
- Produces:
  - `default_settings() -> dict`
  - `normalize_settings(raw: dict | None) -> dict`
  - `read_settings() -> dict`
  - `save_settings(raw: dict) -> dict`
  - `run_automation_once(kind: str) -> dict`
  - `GET /api/automation/settings`
  - `POST /api/automation/settings`
  - `POST /api/automation/run/{kind}`

- [ ] **Step 1: Write failing schema tests**

Create `features/automation/tests/test_schema.py`:

```python
from features.automation.schema import normalize_settings


def test_normalize_settings_defaults_to_disabled():
    settings = normalize_settings({})
    assert settings["rss"]["enabled"] is False
    assert settings["marketMemory"]["enabled"] is False
    assert settings["briefing"]["enabled"] is False
    assert settings["briefing"]["marketScope"] == "both"


def test_normalize_settings_clamps_bad_values():
    settings = normalize_settings({
        "rss": {"enabled": True, "intervalMinutes": -5},
        "briefing": {"enabled": True, "time": "99:99", "marketScope": "bad", "generationMode": "bad"},
    })
    assert settings["rss"]["intervalMinutes"] == 60
    assert settings["briefing"]["time"] == "08:00"
    assert settings["briefing"]["marketScope"] == "both"
    assert settings["briefing"]["generationMode"] == "rules"
```

- [ ] **Step 2: Write failing service tests**

Create `features/automation/tests/test_service.py`:

```python
from pathlib import Path

from features.automation import service


def test_save_and_read_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "SETTINGS_PATH", tmp_path / "automation-settings.json")
    saved = service.save_settings({"rss": {"enabled": True, "intervalMinutes": 120}})
    loaded = service.read_settings()
    assert saved["rss"]["enabled"] is True
    assert loaded["rss"]["intervalMinutes"] == 120


def test_run_unknown_automation_returns_error():
    result = service.run_automation_once("unknown")
    assert result["ok"] is False
    assert "Unsupported automation" in result["error"]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
py -3 -m pytest features\automation\tests -q
```

Expected: FAIL with missing module/functions.

- [ ] **Step 4: Implement schema**

Create `features/automation/__init__.py`:

```python
"""Local Folio OS automation settings and runners."""
```

Create `features/automation/schema.py`:

```python
from __future__ import annotations

VALID_MARKET_SCOPES = {"us", "kr", "both"}
VALID_BRIEFING_TYPES = {"default", "market_focused", "concise"}
VALID_GENERATION_MODES = {"rules", "llm_cli"}
VALID_QUALITY_MODES = {"diagnose_only", "llm_section_improve", "strict"}


def _bool(value) -> bool:
    return bool(value)


def _int(value, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _time(value: str, default: str = "08:00") -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        return default
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return default
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return f"{hour:02d}:{minute:02d}"


def default_settings() -> dict:
    return {
        "rss": {"enabled": False, "intervalMinutes": 60},
        "marketMemory": {"enabled": False, "intervalMinutes": 240, "runAfterRss": True},
        "briefing": {
            "enabled": False,
            "time": "08:00",
            "marketScope": "both",
            "briefingType": "default",
            "generationMode": "rules",
            "qualityMode": "diagnose_only",
            "runPrerequisites": True,
        },
        "missedRuns": {"onStartup": "skip"},
    }


def _choice(value, choices: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in choices else default


def normalize_settings(raw: dict | None) -> dict:
    raw = raw or {}
    defaults = default_settings()
    rss = raw.get("rss") or {}
    memory = raw.get("marketMemory") or {}
    briefing = raw.get("briefing") or {}
    missed = raw.get("missedRuns") or {}
    return {
        "rss": {
            "enabled": _bool(rss.get("enabled", defaults["rss"]["enabled"])),
            "intervalMinutes": _int(rss.get("intervalMinutes"), defaults["rss"]["intervalMinutes"], 15),
        },
        "marketMemory": {
            "enabled": _bool(memory.get("enabled", defaults["marketMemory"]["enabled"])),
            "intervalMinutes": _int(memory.get("intervalMinutes"), defaults["marketMemory"]["intervalMinutes"], 30),
            "runAfterRss": _bool(memory.get("runAfterRss", defaults["marketMemory"]["runAfterRss"])),
        },
        "briefing": {
            "enabled": _bool(briefing.get("enabled", defaults["briefing"]["enabled"])),
            "time": _time(briefing.get("time"), defaults["briefing"]["time"]),
            "marketScope": _choice(briefing.get("marketScope"), VALID_MARKET_SCOPES, "both"),
            "briefingType": _choice(briefing.get("briefingType"), VALID_BRIEFING_TYPES, "default"),
            "generationMode": _choice(briefing.get("generationMode"), VALID_GENERATION_MODES, "rules"),
            "qualityMode": _choice(briefing.get("qualityMode"), VALID_QUALITY_MODES, "diagnose_only"),
            "runPrerequisites": _bool(briefing.get("runPrerequisites", defaults["briefing"]["runPrerequisites"])),
        },
        "missedRuns": {
            "onStartup": _choice(missed.get("onStartup"), {"skip", "catch_up"}, "skip"),
        },
    }
```

- [ ] **Step 5: Implement service**

Create `features/automation/service.py`:

```python
from __future__ import annotations

from pathlib import Path

from features.automation.schema import normalize_settings
from features.common.utils import now_iso, read_json, write_json
from features.common.research_library.rss.service import import_rssarchive
from features.market_memory.digest import run_rss_market_memory_update

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SETTINGS_PATH = DATA_DIR / "automation-settings.json"
RUNS_PATH = DATA_DIR / "automation-runs.json"


def read_settings() -> dict:
    return normalize_settings(read_json(SETTINGS_PATH, {}))


def save_settings(raw: dict) -> dict:
    settings = normalize_settings(raw)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(SETTINGS_PATH, settings)
    return settings


def _append_run(row: dict) -> None:
    runs = read_json(RUNS_PATH, [])
    if not isinstance(runs, list):
        runs = []
    runs.insert(0, row)
    write_json(RUNS_PATH, runs[:50])


def list_runs(limit: int = 20) -> list[dict]:
    runs = read_json(RUNS_PATH, [])
    return runs[: int(limit or 20)] if isinstance(runs, list) else []


def run_automation_once(kind: str) -> dict:
    kind = str(kind or "").strip()
    started = now_iso()
    try:
        if kind == "rss":
            result = import_rssarchive(run_collection=True)
        elif kind == "marketMemory":
            result = run_rss_market_memory_update()
        elif kind == "briefingPrerequisites":
            rss = import_rssarchive(run_collection=True)
            memory = run_rss_market_memory_update()
            result = {"rss": rss, "marketMemory": memory}
        else:
            return {"ok": False, "error": f"Unsupported automation: {kind}"}
        row = {"kind": kind, "status": "done", "startedAt": started, "finishedAt": now_iso(), "result": result}
        _append_run(row)
        return {"ok": True, **row}
    except Exception as exc:
        row = {"kind": kind, "status": "failed", "startedAt": started, "finishedAt": now_iso(), "error": str(exc)}
        _append_run(row)
        return {"ok": False, **row}
```

- [ ] **Step 6: Add endpoints**

Modify `app.py` imports:

```python
from features.automation.service import read_settings as read_automation_settings, save_settings as save_automation_settings, list_runs as list_automation_runs, run_automation_once
```

Add endpoints:

```python
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
```

- [ ] **Step 7: Run tests**

Run:

```powershell
py -3 -m pytest features\automation\tests -q
py -3 -m py_compile app.py features\automation\schema.py features\automation\service.py
```

Expected: tests PASS and compile succeeds.

- [ ] **Step 8: Document automation**

Create `features/automation/README.md`:

```markdown
# Automation

Automation stores local settings for RSS collection, Market Memory digest updates, and briefing prerequisites.

Automation is local-only: it runs while the Folio OS server is running. If the PC is asleep, shut down, or the server is stopped, scheduled work may be skipped according to the missed-run setting.

Settings live in `data/automation-settings.json`. Recent run summaries live in `data/automation-runs.json`.

The first implementation exposes manual run endpoints and normalized settings. A scheduler loop can call the same service functions without adding logic to `app.py`.
```

- [ ] **Step 9: Commit**

Run:

```powershell
git add app.py features\automation features\market_memory\digest.py
git commit -m "feat: add local automation settings"
```

Expected: commit succeeds.

---

### Task 5: Agent Dock and Reader Drawer UI

**Files:**
- Modify: `public/index.html`
- Modify: `public/app.js`
- Modify: `public/styles.css`
- Modify: `features/frontend_ui/README.md`

**Interfaces:**
- Consumes: `POST /api/agent/companion`
- Produces:
  - `window.FolioAgent.currentContext`
  - `openAgentDock(contextOverride)`
  - `renderAgentDock()`
  - in-reader `Ask Agent` drawer host

- [ ] **Step 1: Add HTML shell**

Add near the end of `public/index.html` body:

```html
<button id="agentFab" class="agent-fab" type="button" aria-label="AI Agent 열기">
  <span class="agent-fab-dot" aria-hidden="true"></span>
  <span>AI</span>
</button>

<aside id="agentDock" class="agent-dock" aria-label="AI Agent" hidden>
  <header class="agent-dock-header">
    <div>
      <p class="agent-dock-eyebrow" id="agentConnectionStatus">Agent</p>
      <h2>Folio Agent</h2>
    </div>
    <button id="agentDockClose" class="icon-btn" type="button" aria-label="AI Agent 닫기">×</button>
  </header>
  <div id="agentMessages" class="agent-messages"></div>
  <form id="agentForm" class="agent-form">
    <textarea id="agentInput" rows="2" placeholder="현재 화면에 대해 물어보세요"></textarea>
    <button type="submit">보내기</button>
  </form>
</aside>
```

- [ ] **Step 2: Add frontend state and API call**

Add to `public/app.js` near other global UI state:

```javascript
const FolioAgent = {
  currentContext: {
    surface: "",
    viewId: "",
    reportKind: "",
    reportId: "",
    marketScope: "",
    selectedText: "",
    visibleSection: "",
    portfolioLinked: false,
  },
  messages: [],
};
window.FolioAgent = FolioAgent;

function updateAgentContext(patch = {}) {
  FolioAgent.currentContext = { ...FolioAgent.currentContext, ...patch };
}

async function sendAgentMessage(message) {
  const response = await fetch("/api/agent/companion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context: FolioAgent.currentContext }),
  });
  if (!response.ok) throw new Error(`Agent request failed: ${response.status}`);
  return response.json();
}
```

- [ ] **Step 3: Add dock rendering**

Add to `public/app.js`:

```javascript
function renderAgentDock() {
  const dock = document.getElementById("agentDock");
  const list = document.getElementById("agentMessages");
  if (!dock || !list) return;
  list.innerHTML = FolioAgent.messages.map((msg) => `
    <article class="agent-message ${msg.role}">
      <p>${escapeHtml(msg.text || "")}</p>
      ${(msg.actions || []).length ? `<div class="agent-actions">${msg.actions.map((action) => `
        <button type="button" class="agent-action" data-agent-action="${escapeHtml(action.id)}">${escapeHtml(action.label)}</button>
      `).join("")}</div>` : ""}
    </article>
  `).join("");
}

function openAgentDock(contextOverride = {}) {
  updateAgentContext(contextOverride);
  const dock = document.getElementById("agentDock");
  if (dock) dock.hidden = false;
  renderAgentDock();
}

function closeAgentDock() {
  const dock = document.getElementById("agentDock");
  if (dock) dock.hidden = true;
}

function bindAgentDock() {
  document.getElementById("agentFab")?.addEventListener("click", () => openAgentDock());
  document.getElementById("agentDockClose")?.addEventListener("click", closeAgentDock);
  document.getElementById("agentForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("agentInput");
    const message = input?.value?.trim();
    if (!message) return;
    input.value = "";
    FolioAgent.messages.push({ role: "user", text: message });
    renderAgentDock();
    try {
      const result = await sendAgentMessage(message);
      FolioAgent.messages.push({ role: "assistant", text: result.message || "", actions: result.actions || [] });
    } catch (error) {
      FolioAgent.messages.push({ role: "assistant", text: error.message || "Agent 요청에 실패했습니다." });
    }
    renderAgentDock();
  });
}
```

Call `bindAgentDock()` inside the existing startup/bootstrap block.

- [ ] **Step 4: Update context on view/report changes**

In `switchViewById(viewId)`, add:

```javascript
updateAgentContext({ surface: "view", viewId, reportKind: "", reportId: "", marketScope: "" });
```

In briefing reader open logic after report metadata is known, add:

```javascript
updateAgentContext({
  surface: "briefing_reader",
  viewId: "briefing",
  reportKind: "briefing",
  reportId: date,
  marketScope: marketScope || "both",
});
```

In company/topic report render functions, add equivalent context updates with `reportKind: "company_analysis"` or `reportKind: "topic_report"`.

- [ ] **Step 5: Add styles**

Append to `public/styles.css`:

```css
.agent-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 1200;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 56px;
  height: 44px;
  border: 1px solid var(--folio-border, #d8d3c7);
  background: var(--folio-surface-clean, #fffdfa);
  color: var(--folio-ink, #1d1b18);
  box-shadow: var(--elev-2, 0 10px 28px rgba(0,0,0,.12));
}

.agent-fab-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #2fa66a;
}

.agent-dock {
  position: fixed;
  top: 0;
  right: 0;
  z-index: 1300;
  width: min(420px, 100vw);
  height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr auto;
  border-left: 1px solid var(--folio-border, #d8d3c7);
  background: var(--folio-surface-clean, #fffdfa);
}

.agent-dock[hidden] {
  display: none;
}

.agent-dock-header,
.agent-form {
  padding: 16px;
  border-bottom: 1px solid var(--folio-border, #d8d3c7);
}

.agent-form {
  border-top: 1px solid var(--folio-border, #d8d3c7);
  border-bottom: 0;
  display: grid;
  gap: 10px;
}

.agent-messages {
  overflow: auto;
  padding: 16px;
}

.agent-message {
  margin: 0 0 12px;
  padding: 12px;
  border: 1px solid var(--folio-border, #d8d3c7);
  background: var(--folio-surface-2, #f8f5ef);
}

.agent-message.user {
  background: var(--folio-surface-muted, #efebe2);
}

.agent-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
```

- [ ] **Step 6: Run frontend syntax check**

Run:

```powershell
node --check public\app.js
```

Expected: no syntax errors.

- [ ] **Step 7: Document UI contract**

Append to `features/frontend_ui/README.md`:

```markdown
## Global Agent Dock

The Agent Dock is a persistent global layer. It starts collapsed, opens as a right dock on desktop, and should become a bottom sheet on narrow mobile layouts. Report reader modals should update `FolioAgent.currentContext` so Agent requests know the active report without changing Canonical markdown.
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add public\index.html public\app.js public\styles.css features\frontend_ui\README.md
git commit -m "feat: add global agent dock"
```

Expected: commit succeeds.

---

### Task 6: Market State Dashboard v2 UI

**Files:**
- Modify: `public/index.html`
- Modify: `public/app.js`
- Modify: `public/styles.css`
- Modify: `features/frontend_ui/README.md`

**Interfaces:**
- Consumes: `GET /api/memory/state-dashboard`
- Produces: concise market state card plus 3-5 driver cards

- [ ] **Step 1: Add dashboard containers**

In the existing Market Memory view in `public/index.html`, add:

```html
<section id="marketStateDashboard" class="market-state-dashboard">
  <div class="market-state-head">
    <p class="section-kicker">Market State</p>
    <h2 id="marketStateTitle">현재 중기 시장 상황</h2>
    <button id="refreshMarketStateBtn" type="button">새로고침</button>
  </div>
  <p id="marketStateSummary" class="market-state-summary"></p>
  <div id="marketStateDrivers" class="market-state-drivers"></div>
</section>
```

- [ ] **Step 2: Add dashboard loader**

Add to `public/app.js`:

```javascript
async function loadMarketStateDashboard() {
  const response = await fetch("/api/memory/state-dashboard?limit=5");
  if (!response.ok) throw new Error(`Market State request failed: ${response.status}`);
  const payload = await response.json();
  renderMarketStateDashboard(payload);
  updateAgentContext({ surface: "market_state", viewId: "memory", reportKind: "", reportId: "" });
}

function renderMarketStateDashboard(payload) {
  const title = document.getElementById("marketStateTitle");
  const summary = document.getElementById("marketStateSummary");
  const drivers = document.getElementById("marketStateDrivers");
  if (!title || !summary || !drivers) return;
  title.textContent = payload.title || "현재 중기 시장 상황";
  summary.textContent = payload.summary || "";
  drivers.innerHTML = (payload.drivers || []).map((driver) => `
    <article class="market-driver-card">
      <div class="market-driver-top">
        <h3>${escapeHtml(driver.title || "")}</h3>
        <span>${escapeHtml(driver.momentumLabel || driver.momentum || "")}</span>
      </div>
      <p>${escapeHtml(driver.interpretation || "")}</p>
      <footer>
        <small>확신도 ${escapeHtml(driver.confidence || "medium")}</small>
        <button type="button" class="agent-action" data-agent-prompt="${escapeHtml(driver.askAgentPrompt || "")}">Agent에게 묻기</button>
      </footer>
    </article>
  `).join("");
}
```

Bind refresh:

```javascript
document.getElementById("refreshMarketStateBtn")?.addEventListener("click", () => {
  loadMarketStateDashboard().catch((error) => setStatus(error.message || "Market State 로딩 실패"));
});
```

Call `loadMarketStateDashboard()` when switching into the Market Memory view.

- [ ] **Step 3: Wire Agent prompt buttons**

Add delegated click handler:

```javascript
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-agent-prompt]");
  if (!button) return;
  openAgentDock({ surface: "market_state", viewId: "memory" });
  const input = document.getElementById("agentInput");
  if (input) {
    input.value = button.dataset.agentPrompt || "";
    input.focus();
  }
});
```

- [ ] **Step 4: Add styles**

Append to `public/styles.css`:

```css
.market-state-dashboard {
  display: grid;
  gap: 16px;
}

.market-state-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.market-state-summary {
  max-width: 880px;
  font-size: 20px;
  line-height: 1.6;
  color: var(--folio-ink, #1d1b18);
}

.market-state-drivers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.market-driver-card {
  border: 1px solid var(--folio-border, #d8d3c7);
  background: var(--folio-surface-clean, #fffdfa);
  padding: 16px;
}

.market-driver-top {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
}
```

- [ ] **Step 5: Run frontend syntax check**

Run:

```powershell
node --check public\app.js
```

Expected: no syntax errors.

- [ ] **Step 6: Commit**

Run:

```powershell
git add public\index.html public\app.js public\styles.css features\frontend_ui\README.md
git commit -m "feat: add market state dashboard ui"
```

Expected: commit succeeds.

---

### Task 7: Automation Settings UI

**Files:**
- Modify: `public/index.html`
- Modify: `public/app.js`
- Modify: `public/styles.css`
- Modify: `features/frontend_ui/README.md`

**Interfaces:**
- Consumes:
  - `GET /api/automation/settings`
  - `POST /api/automation/settings`
  - `GET /api/automation/runs`
  - `POST /api/automation/run/{kind}`
- Produces: settings form for RSS interval, Market Memory interval, briefing time, and prerequisites.

- [ ] **Step 1: Add settings markup**

In the Settings view in `public/index.html`, add:

```html
<section class="settings-panel" id="automationSettingsPanel">
  <h2>자동화</h2>
  <label>
    <input id="autoRssEnabled" type="checkbox">
    RSS 자동 수집
  </label>
  <input id="autoRssInterval" type="number" min="15" step="15" value="60">

  <label>
    <input id="autoMemoryEnabled" type="checkbox">
    Market Memory 자동 정리
  </label>
  <input id="autoMemoryInterval" type="number" min="30" step="30" value="240">

  <label>
    <input id="autoBriefingEnabled" type="checkbox">
    브리핑 자동 생성
  </label>
  <input id="autoBriefingTime" type="time" value="08:00">
  <select id="autoBriefingMarket">
    <option value="both">종합</option>
    <option value="us">미국장</option>
    <option value="kr">한국장</option>
  </select>
  <label>
    <input id="autoBriefingPrereq" type="checkbox">
    생성 전 RSS 수집과 Market Memory 정리 실행
  </label>

  <div class="settings-actions">
    <button id="saveAutomationSettingsBtn" type="button">자동화 저장</button>
    <button id="runAutomationPrereqBtn" type="button">지금 준비 작업 실행</button>
  </div>
  <div id="automationRunList" class="automation-run-list"></div>
</section>
```

- [ ] **Step 2: Add JS load/save**

Add to `public/app.js`:

```javascript
async function loadAutomationSettings() {
  const response = await fetch("/api/automation/settings");
  if (!response.ok) throw new Error(`Automation settings failed: ${response.status}`);
  const settings = await response.json();
  document.getElementById("autoRssEnabled").checked = !!settings.rss?.enabled;
  document.getElementById("autoRssInterval").value = settings.rss?.intervalMinutes || 60;
  document.getElementById("autoMemoryEnabled").checked = !!settings.marketMemory?.enabled;
  document.getElementById("autoMemoryInterval").value = settings.marketMemory?.intervalMinutes || 240;
  document.getElementById("autoBriefingEnabled").checked = !!settings.briefing?.enabled;
  document.getElementById("autoBriefingTime").value = settings.briefing?.time || "08:00";
  document.getElementById("autoBriefingMarket").value = settings.briefing?.marketScope || "both";
  document.getElementById("autoBriefingPrereq").checked = settings.briefing?.runPrerequisites !== false;
}

function automationSettingsFromForm() {
  return {
    rss: {
      enabled: document.getElementById("autoRssEnabled").checked,
      intervalMinutes: Number(document.getElementById("autoRssInterval").value || 60),
    },
    marketMemory: {
      enabled: document.getElementById("autoMemoryEnabled").checked,
      intervalMinutes: Number(document.getElementById("autoMemoryInterval").value || 240),
      runAfterRss: true,
    },
    briefing: {
      enabled: document.getElementById("autoBriefingEnabled").checked,
      time: document.getElementById("autoBriefingTime").value || "08:00",
      marketScope: document.getElementById("autoBriefingMarket").value || "both",
      briefingType: "default",
      generationMode: "rules",
      qualityMode: "diagnose_only",
      runPrerequisites: document.getElementById("autoBriefingPrereq").checked,
    },
    missedRuns: { onStartup: "skip" },
  };
}

async function saveAutomationSettings() {
  const response = await fetch("/api/automation/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(automationSettingsFromForm()),
  });
  if (!response.ok) throw new Error(`Automation save failed: ${response.status}`);
  await loadAutomationSettings();
}
```

- [ ] **Step 3: Add manual run and run list**

Add to `public/app.js`:

```javascript
async function runAutomation(kind) {
  const response = await fetch(`/api/automation/run/${encodeURIComponent(kind)}`, { method: "POST" });
  if (!response.ok) throw new Error(`Automation run failed: ${response.status}`);
  await loadAutomationRuns();
}

async function loadAutomationRuns() {
  const response = await fetch("/api/automation/runs?limit=10");
  if (!response.ok) return;
  const payload = await response.json();
  const target = document.getElementById("automationRunList");
  if (!target) return;
  target.innerHTML = (payload.items || []).map((run) => `
    <article class="automation-run ${escapeHtml(run.status || "")}">
      <strong>${escapeHtml(run.kind || "")}</strong>
      <span>${escapeHtml(run.status || "")}</span>
      <small>${escapeHtml(run.finishedAt || run.startedAt || "")}</small>
    </article>
  `).join("");
}
```

Bind buttons:

```javascript
document.getElementById("saveAutomationSettingsBtn")?.addEventListener("click", () => {
  saveAutomationSettings().catch((error) => setStatus(error.message || "자동화 저장 실패"));
});

document.getElementById("runAutomationPrereqBtn")?.addEventListener("click", () => {
  runAutomation("briefingPrerequisites").catch((error) => setStatus(error.message || "자동화 실행 실패"));
});
```

Call `loadAutomationSettings()` and `loadAutomationRuns()` when rendering Settings.

- [ ] **Step 4: Add styles**

Append to `public/styles.css`:

```css
.automation-run-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.automation-run {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 12px;
  padding: 10px 0;
  border-top: 1px solid var(--folio-border, #d8d3c7);
}

.automation-run small {
  grid-column: 1 / -1;
  color: var(--folio-ink-muted, #746f66);
}
```

- [ ] **Step 5: Run frontend syntax check**

Run:

```powershell
node --check public\app.js
```

Expected: no syntax errors.

- [ ] **Step 6: Commit**

Run:

```powershell
git add public\index.html public\app.js public\styles.css features\frontend_ui\README.md
git commit -m "feat: add automation settings ui"
```

Expected: commit succeeds.

---

### Task 8: Scheduler Loop and Startup Integration

**Files:**
- Modify: `features/automation/service.py`
- Create: `features/automation/tests/test_scheduler.py`
- Modify: `app.py`
- Modify: `features/automation/README.md`

**Interfaces:**
- Produces:
  - `automation_due(now, last_run, interval_minutes) -> bool`
  - `run_due_automations(now=None) -> dict`
  - `schedule_automation_loop() -> dict`

- [ ] **Step 1: Write scheduler tests**

Create `features/automation/tests/test_scheduler.py`:

```python
import datetime as dt

from features.automation.service import automation_due


def test_automation_due_when_never_run():
    now = dt.datetime(2026, 7, 2, 8, 0)
    assert automation_due(now, "", 60) is True


def test_automation_due_after_interval():
    now = dt.datetime(2026, 7, 2, 8, 0)
    last = "2026-07-02T06:59:00"
    assert automation_due(now, last, 60) is True


def test_automation_not_due_before_interval():
    now = dt.datetime(2026, 7, 2, 8, 0)
    last = "2026-07-02T07:30:00"
    assert automation_due(now, last, 60) is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
py -3 -m pytest features\automation\tests\test_scheduler.py -q
```

Expected: FAIL with missing `automation_due`.

- [ ] **Step 3: Implement due checks and scheduler loop**

Append to `features/automation/service.py`:

```python
import datetime as dt
import threading
import time

_AUTOMATION_LOOP_STARTED = False


def automation_due(now: dt.datetime, last_run: str, interval_minutes: int) -> bool:
    if not last_run:
        return True
    try:
        parsed = dt.datetime.fromisoformat(last_run)
    except ValueError:
        return True
    return (now - parsed).total_seconds() >= int(interval_minutes or 60) * 60


def _last_run_for(kind: str) -> str:
    for row in list_runs(limit=50):
        if row.get("kind") == kind and row.get("status") == "done":
            return row.get("finishedAt") or row.get("startedAt") or ""
    return ""


def run_due_automations(now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now()
    settings = read_settings()
    ran = []
    if settings["rss"]["enabled"] and automation_due(now, _last_run_for("rss"), settings["rss"]["intervalMinutes"]):
        ran.append(run_automation_once("rss"))
        if settings["marketMemory"]["enabled"] and settings["marketMemory"]["runAfterRss"]:
            ran.append(run_automation_once("marketMemory"))
    if settings["marketMemory"]["enabled"] and automation_due(now, _last_run_for("marketMemory"), settings["marketMemory"]["intervalMinutes"]):
        ran.append(run_automation_once("marketMemory"))
    return {"ok": True, "ran": ran}


def schedule_automation_loop() -> dict:
    global _AUTOMATION_LOOP_STARTED
    if _AUTOMATION_LOOP_STARTED:
        return {"scheduled": False, "reason": "already_started"}
    _AUTOMATION_LOOP_STARTED = True

    def worker():
        while True:
            try:
                run_due_automations()
            except Exception:
                pass
            time.sleep(60)

    thread = threading.Thread(target=worker, name="folio-automation-loop", daemon=True)
    thread.start()
    return {"scheduled": True}
```

- [ ] **Step 4: Call scheduler on startup**

Modify `app.py` imports:

```python
from features.automation.service import schedule_automation_loop
```

Inside the existing startup event after `load_jobs()` and market memory startup scheduling:

```python
schedule_automation_loop()
```

- [ ] **Step 5: Run tests**

Run:

```powershell
py -3 -m pytest features\automation\tests -q
py -3 -m py_compile app.py features\automation\service.py
```

Expected: tests PASS and compile succeeds.

- [ ] **Step 6: Commit**

Run:

```powershell
git add app.py features\automation\service.py features\automation\tests\test_scheduler.py features\automation\README.md
git commit -m "feat: run due local automations"
```

Expected: commit succeeds.

---

## Final Verification

- [ ] Run Python tests for touched modules:

```powershell
py -3 -m pytest features\agent_mode\tests\test_companion.py features\market_memory\tests\test_digest.py features\market_memory\tests\test_state_dashboard.py features\automation\tests -q
```

Expected: all tests PASS.

- [ ] Run Python compile check:

```powershell
py -3 -m py_compile app.py features\agent_mode\companion.py features\market_memory\digest.py features\market_memory\state_dashboard.py features\automation\schema.py features\automation\service.py
```

Expected: no output and exit code 0.

- [ ] Run frontend syntax check:

```powershell
node --check public\app.js
```

Expected: no syntax errors.

- [ ] Manual smoke test:

```powershell
py -3 app.py
```

Expected:

- `GET /api/agent/companion` is not allowed because endpoint is POST.
- `POST /api/agent/companion` returns Companion Mode for ordinary questions.
- `POST /api/memory/rss-digest` returns `digestCount` and `promotedCount`.
- `GET /api/memory/state-dashboard` returns `title`, `summary`, and `drivers`.
- `GET /api/automation/settings` returns normalized defaults.
- `POST /api/automation/settings` persists settings.
- `POST /api/automation/run/briefingPrerequisites` runs RSS collection and Market Memory update without crashing the server.

---

## Deferred Follow-Up Plans

Create separate plans after this foundation lands:

1. `Native Investment Notes`  
   Folio-owned note editor and `market-memory.sqlite3` native note index.
2. `React Shell Gradual Adoption`  
   Vite/React island setup for Agent Dock, Market State Dashboard, Automation, and future Notes surfaces.
3. `Agent Task Mode Writeback`  
   Preview/diff/approval flows for company analysis and topic report revisions.

