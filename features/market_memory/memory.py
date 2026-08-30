#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from typing import assert_never

from features.common.markets import MarketCode
from features.common.sqlite_receipts import ensure_receipt_table
from features.common.taxonomy import TAG_ALIASES, INDUSTRY_ALIASES, canonical_tag, canonical_industry

CATEGORY_CHOICES = {"stock_bond", "geopolitics", "emerging"}
REGION_CHOICES = {market.value for market in MarketCode if market is not MarketCode.UNKNOWN}
IMPORTANCE_CHOICES = {"high", "medium", "low"}
ENTRY_MODE_CHOICES = {"issue", "brief"}
STATE_STATUS_CHOICES = {"active", "watch", "resolved", "overridden"}
STATE_BIAS_CHOICES = {"bullish", "bearish", "neutral", "mixed"}
SUBJECT_TYPE_CHOICES = {"person", "politician", "business_leader", "company", "institution", "industry", "market_actor", "other"}
TAXONOMY_TYPES = {
    "category",
    "region",
    "importance",
    "entry_mode",
    "story",
    "story_family",
    "story_relation",
    "tag",
    "industry",
    "ticker",
    "subject",
    "subject_type",
    "event_kind",
    "state_key",
    "net_effect",
}
STORY_RELATIONS = {"evolves_from", "branches_from", "confirms", "conflicts_with", "replaces", "same_family"}
MIN_DERIVED_STATE_SUPPORT = 2


GENERIC_ROUTE_TERMS = {
    "ai",
    "market",
    "stocks",
    "shares",
    "energy",
    "internet",
    "hardware",
    "semiconductors",
    "주식",
    "증시",
    "시장",
}

EARNINGS_HINTS = r"earnings|guidance|eps|revenue|margin|beat|miss|profit warning|실적|어닝|가이던스|매출|영업이익|순이익"
HIGH_IMPACT_EARNINGS_HINTS = r"guidance cut|guidance raise|profit warning|earnings beat|earnings miss|실적 쇼크|실적 서프라이즈|어닝 쇼크|어닝 서프라이즈|가이던스 상향|가이던스 하향"

EVENT_KIND_LABELS = {
    "earnings": "실적",
    "policy": "정책",
    "geopolitics": "지정학",
    "industry_trend": "산업 흐름",
    "market_move": "가격 반응",
    "brief": "관찰 메모",
}

DISPLAY_LABELS = {
    "market": "시장 가격 반응",
    "financials": "금융/금리 경로",
    "nvidia": "NVIDIA AI 반도체",
    "dell_technologies": "Dell Technologies AI 서버",
    "samsung_electro_mechanics": "삼성전기 MLCC/AI 수혜",
    "samsung_electronics": "삼성전자 반도체",
    "sk_hynix": "SK하이닉스 HBM/메모리",
    "energy": "에너지와 금리",
    "semiconductors": "반도체 업종",
    "ai": "AI 인프라",
    "ai_semiconductor_supply_chain": "AI 반도체 공급망",
    "ai_data_center_power_bottleneck": "AI 데이터센터 전력 병목",
    "rates_dollar_liquidity": "금리·달러 유동성",
    "middle_east_energy_risk": "중동 에너지 리스크",
    "korea_semiconductor_exports_fx_sensitivity": "한국 반도체 수출 수혜와 원화·수급 긴장",
    "korea_equity_rally": "한국 증시 랠리",
    "korea_export_cycle": "한국 수출 사이클",
    "us_ai_equity_rally": "미국 AI 주식 랠리",
    "earnings_revision_cycle": "실적 기대 재가격화",
    "policy_regulation_risk": "정책·규제 리스크",
    "broad_market_risk_appetite": "시장 위험선호 변화",
}

CANONICAL_STATE_DEFS = {
    "ai_semiconductor_supply_chain": {
        "label": "AI 반도체 공급망",
        "family": "AI 반도체 공급망",
        "thesis": "AI 투자 사이클이 반도체, 서버, 메모리, 부품 공급망의 실적 기대와 수급으로 전이되는 흐름",
    },
    "ai_data_center_power_bottleneck": {
        "label": "AI 데이터센터 전력 병목",
        "family": "AI 데이터센터 전력 병목",
        "thesis": "AI 인프라 수요가 전력, 유틸리티, 전선·구리 등 물리 인프라 병목으로 확산되는 흐름",
    },
    "rates_dollar_liquidity": {
        "label": "금리·달러 유동성",
        "family": "금리·달러 유동성",
        "thesis": "금리, 국채 수급, 달러 유동성이 위험자산 밸류에이션과 자금 흐름을 좌우하는 흐름",
    },
    "middle_east_energy_risk": {
        "label": "중동 에너지 리스크",
        "family": "에너지 지정학 리스크",
        "thesis": "중동 지정학과 에너지 가격 프리미엄이 물가, 금리, 산업 비용으로 전이되는 흐름",
    },
    "korea_semiconductor_exports_fx_sensitivity": {
        "label": "한국 반도체 수출 수혜와 원화·수급 긴장",
        "family": "한국 수출과 원화 민감도",
        "thesis": "한국 반도체 수출과 AI 메모리 수혜가 원화 안정, 외국인 수급, 해외 레버리지 상품 흐름에 민감하게 반응하는 흐름",
    },
    "korea_equity_rally": {
        "label": "한국 증시 랠리",
        "family": "한국 증시 랠리",
        "thesis": "한국 증시의 지수 상승, 주도 업종, 외국인·기관 수급이 이어지는 흐름",
    },
    "korea_export_cycle": {
        "label": "한국 수출 사이클",
        "family": "한국 수출 사이클",
        "thesis": "반도체와 주력 산업 수출이 원화, 기업이익, 한국 증시 수급에 영향을 주는 흐름",
    },
    "us_ai_equity_rally": {
        "label": "미국 AI 주식 랠리",
        "family": "미국 AI 주식 랠리",
        "thesis": "미국 대형 기술주와 AI 테마가 지수 상승과 밸류에이션 논쟁을 주도하는 흐름",
    },
}

STATE_KEY_ALIASES = {
    "ai_supply_chain": "ai_semiconductor_supply_chain",
    "ai_supply_chain_bottleneck": "ai_semiconductor_supply_chain",
    "ai_leadership_narrows": "ai_semiconductor_supply_chain",
    "ai_leadership_repricing": "ai_semiconductor_supply_chain",
    "ai_semis": "ai_semiconductor_supply_chain",
    "ai_semiconductor": "ai_semiconductor_supply_chain",
    "ai_semiconductors": "ai_semiconductor_supply_chain",
    "korea_semiconductors": "korea_semiconductor_exports_fx_sensitivity",
    "korea_semiconductor_exports": "korea_semiconductor_exports_fx_sensitivity",
    "korea_export_fx_tension": "korea_semiconductor_exports_fx_sensitivity",
    "korea_chip_fx_sensitivity": "korea_semiconductor_exports_fx_sensitivity",
    "energy_geopolitical_risk": "middle_east_energy_risk",
    "geopolitical_premium_eases": "middle_east_energy_risk",
    "middle_east_geopolitical_risk": "middle_east_energy_risk",
    "rates_dollar": "rates_dollar_liquidity",
    "fx_rates": "rates_dollar_liquidity",
}

TAG_LABELS = {
    "Semiconductors": "반도체",
    "AI": "AI",
    "Battery": "배터리",
    "Energy": "에너지",
    "Defense": "방산",
    "Financials": "금융/금리",
    "Automobiles": "자동차",
    "Electronic Components": "전자부품",
    "Internet": "인터넷",
    "Hardware": "하드웨어",
    "매출 성장": "매출 성장",
    "마진": "마진",
    "규제": "규제",
    "금리": "금리",
    "환율": "환율",
    "공급망": "공급망",
    "수급": "수급",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_memory (
            memory_id TEXT PRIMARY KEY,
            as_of TEXT NOT NULL,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            story TEXT NOT NULL,
            story_family TEXT NOT NULL DEFAULT '',
            story_thesis TEXT NOT NULL DEFAULT '',
            story_checkpoint TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'stock_bond',
            region TEXT NOT NULL DEFAULT 'GLOBAL',
            importance TEXT NOT NULL DEFAULT 'medium',
            entry_mode TEXT NOT NULL DEFAULT 'issue',
            event_kind TEXT NOT NULL DEFAULT '',
            subjects_json TEXT NOT NULL DEFAULT '[]',
            industries_json TEXT NOT NULL DEFAULT '[]',
            tickers_json TEXT NOT NULL DEFAULT '[]',
            tags_json TEXT NOT NULL DEFAULT '[]',
            sources_json TEXT NOT NULL DEFAULT '[]',
            state_key TEXT NOT NULL DEFAULT '',
            state_label TEXT NOT NULL DEFAULT '',
            parent_story TEXT NOT NULL DEFAULT '',
            story_relation TEXT NOT NULL DEFAULT 'same_family',
            net_effect TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT 'auto',
            dedupe_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    _ensure_columns(
        conn,
        "market_memory",
        {
            "story_family": "TEXT NOT NULL DEFAULT ''",
            "story_thesis": "TEXT NOT NULL DEFAULT ''",
            "story_checkpoint": "TEXT NOT NULL DEFAULT ''",
            "category": "TEXT NOT NULL DEFAULT 'stock_bond'",
            "region": "TEXT NOT NULL DEFAULT 'GLOBAL'",
            "importance": "TEXT NOT NULL DEFAULT 'medium'",
            "entry_mode": "TEXT NOT NULL DEFAULT 'issue'",
            "event_kind": "TEXT NOT NULL DEFAULT ''",
            "subjects_json": "TEXT NOT NULL DEFAULT '[]'",
            "industries_json": "TEXT NOT NULL DEFAULT '[]'",
            "tickers_json": "TEXT NOT NULL DEFAULT '[]'",
            "dedupe_key": "TEXT NOT NULL DEFAULT ''",
            "state_key": "TEXT NOT NULL DEFAULT ''",
            "state_label": "TEXT NOT NULL DEFAULT ''",
            "parent_story": "TEXT NOT NULL DEFAULT ''",
            "story_relation": "TEXT NOT NULL DEFAULT 'same_family'",
            "net_effect": "TEXT NOT NULL DEFAULT ''",
            "source_kind": "TEXT NOT NULL DEFAULT 'auto'",
        },
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_narrative_states (
            state_id TEXT PRIMARY KEY,
            state_key TEXT NOT NULL,
            state_label TEXT NOT NULL,
            story TEXT NOT NULL,
            story_family TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'watch',
            bias TEXT NOT NULL DEFAULT 'neutral',
            category TEXT NOT NULL DEFAULT 'stock_bond',
            region TEXT NOT NULL DEFAULT 'GLOBAL',
            importance TEXT NOT NULL DEFAULT 'medium',
            net_effect TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            rationale TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.55,
            effective_from TEXT NOT NULL,
            effective_to TEXT NOT NULL DEFAULT '',
            source_memory_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    _ensure_columns(
        conn,
        "market_narrative_states",
        {
            "momentum": "TEXT NOT NULL DEFAULT 'stable'",
            "evidence_count_7d": "INTEGER NOT NULL DEFAULT 0",
            "evidence_count_30d": "INTEGER NOT NULL DEFAULT 0",
            "evidence_count_90d": "INTEGER NOT NULL DEFAULT 0",
            "last_confirmed_at": "TEXT NOT NULL DEFAULT ''",
            "last_challenged_at": "TEXT NOT NULL DEFAULT ''",
            "falsification_triggers_json": "TEXT NOT NULL DEFAULT '[]'",
            "next_checkpoints_json": "TEXT NOT NULL DEFAULT '[]'",
        },
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_memory_date ON market_memory(date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_memory_story ON market_memory(story)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_memory_ontology ON market_memory(category, region, importance)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_state_key ON market_narrative_states(state_key, status)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_regime_evidence (
            evidence_id TEXT PRIMARY KEY,
            state_id TEXT NOT NULL,
            memory_id TEXT NOT NULL DEFAULT '',
            evidence_date TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'neutral',
            score REAL NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT '',
            sources_json TEXT NOT NULL DEFAULT '[]',
            matched_terms_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(state_id) REFERENCES market_narrative_states(state_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_regime_changes (
            change_id TEXT PRIMARY KEY,
            state_id TEXT NOT NULL,
            changed_at TEXT NOT NULL DEFAULT '',
            field TEXT NOT NULL DEFAULT '',
            old_value TEXT NOT NULL DEFAULT '',
            new_value TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            evidence_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(state_id) REFERENCES market_narrative_states(state_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_regime_thesis_links (
            link_id TEXT PRIMARY KEY,
            state_id TEXT NOT NULL,
            ticker TEXT NOT NULL DEFAULT '',
            thesis_ticker TEXT NOT NULL DEFAULT '',
            relationship TEXT NOT NULL DEFAULT 'related',
            strength REAL NOT NULL DEFAULT 0.5,
            method TEXT NOT NULL DEFAULT 'auto',
            note_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(state_id) REFERENCES market_narrative_states(state_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_regime_evidence_state ON market_regime_evidence(state_id, evidence_date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_regime_evidence_role ON market_regime_evidence(state_id, role)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_regime_changes_state ON market_regime_changes(state_id, changed_at DESC)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_regime_thesis_state_ticker ON market_regime_thesis_links(state_id, thesis_ticker)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_memory_taxonomy (
            term_type TEXT NOT NULL,
            term_key TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            count INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT NOT NULL DEFAULT '',
            last_seen TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (term_type, term_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_story_links (
            link_id TEXT PRIMARY KEY,
            from_story TEXT NOT NULL,
            to_story TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT 'same_family',
            strength REAL NOT NULL DEFAULT 0.5,
            evidence TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_story_family_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            story TEXT NOT NULL,
            suggested_family TEXT NOT NULL,
            suggested_family_label TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'suggested',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_taxonomy_type ON market_memory_taxonomy(term_type, count DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_story_links_from ON market_story_links(from_story, relation)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_story_family_suggestions ON market_story_family_suggestions(status, updated_at DESC)")
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
    ensure_receipt_table(conn)
    conn.commit()


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def normalize(text: str) -> str:
    return " ".join(str(text or "").split())


def _strip_markup(value: str) -> str:
    output: list[str] = []
    inside_tag = False
    for character in value:
        if character == "<":
            inside_tag = True
            output.append(" ")
        elif character == ">" and inside_tag:
            inside_tag = False
            output.append(" ")
        elif not inside_tag:
            output.append(character)
    return "".join(output)


def _strip_urls(value: str) -> str:
    output: list[str] = []
    index = 0
    lowered = value.lower()
    while index < len(value):
        if lowered.startswith("http://", index) or lowered.startswith("https://", index):
            while index < len(value) and not value[index].isspace():
                index += 1
            output.append(" ")
            continue
        output.append(value[index])
        index += 1
    return "".join(output)


def clean_text(text: str) -> str:
    value = _strip_markup(str(text or ""))
    value = value.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'")
    value = _strip_urls(value.replace("Original link:", " "))
    value = "".join(
        " " if character == "#" and (index == 0 or value[index - 1].isspace()) else character
        for index, character in enumerate(value)
    )
    normalized = normalize(value)
    if normalized.casefold().endswith(" - reuters"):
        normalized = normalized[:-len(" - Reuters")]
    return normalize(normalized)


def slug(text: str) -> str:
    token = normalize(text).lower()
    token = re.sub(r"[^0-9a-z가-힣]+", "_", token)
    return token.strip("_")[:80] or "market"



def canonical_subject_type(value: str) -> str:
    return normalize_choice(value, SUBJECT_TYPE_CHOICES, "other")


def display_label(value: str) -> str:
    raw = normalize(value)
    key = slug(raw)
    if key in DISPLAY_LABELS:
        return DISPLAY_LABELS[key]
    if "_" in raw or raw.islower():
        parts = [p for p in re.split(r"[_\s]+", raw) if p]
        if parts:
            return " ".join(part.upper() if len(part) <= 4 and re.fullmatch(r"[a-z0-9]+", part) else part.capitalize() for part in parts)
    return raw


def _canonical_def(key: str) -> dict | None:
    key = slug(STATE_KEY_ALIASES.get(slug(key), key))
    spec = CANONICAL_STATE_DEFS.get(key)
    if not spec:
        return None
    return {
        "stateKey": key,
        "stateLabel": spec["label"],
        "storyFamily": spec["family"],
        "storyThesis": spec["thesis"],
        "parentStory": key,
    }


def _state_blob(*parts) -> str:
    flat: list[str] = []
    for part in parts:
        if isinstance(part, (list, tuple, set)):
            flat.extend(str(item or "") for item in part)
        else:
            flat.append(str(part or ""))
    return clean_text(" ".join(flat)).lower()


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def canonical_state_for(
    state_key: str = "",
    state_label: str = "",
    story_family: str = "",
    story: str = "",
    text: str = "",
) -> dict | None:
    """Map near-duplicate state labels/keys to one canonical active state."""
    for value in (state_key, state_label, story_family, story):
        direct = _canonical_def(value)
        if direct:
            return direct
    blob = _state_blob(state_key, state_label, story_family, story, text)
    if _contains_any(blob, ("전력", "power", "utility", "utilities", "grid", "data center", "datacenter", "데이터센터", "전선", "구리", "원전")) and _contains_any(blob, ("ai", "인공지능", "데이터센터", "data center", "datacenter")):
        return _canonical_def("ai_data_center_power_bottleneck")
    if _contains_any(blob, ("한국", "korea", "원화", "krw", "외국인", "수급", "etp", "adr", "해외 자본", "레버리지")) and _contains_any(blob, ("반도체", "semiconductor", "semis", "hbm", "memory", "메모리", "sk하이닉스", "삼성전자")):
        return _canonical_def("korea_semiconductor_exports_fx_sensitivity")
    if _contains_any(blob, ("ai", "인공지능", "반도체", "semiconductor", "semis", "hbm", "gpu", "server", "서버", "메모리", "memory", "공급망", "리더십", "broadcom", "nvidia", "sk하이닉스", "삼성전자", "삼성전기")):
        return _canonical_def("ai_semiconductor_supply_chain")
    if _contains_any(blob, ("중동", "iran", "hormuz", "middle east", "유가", "oil", "brent", "wti", "지정학", "geopolitical")):
        return _canonical_def("middle_east_energy_risk")
    if _contains_any(blob, ("금리", "rate", "rates", "yield", "yields", "국채", "채권", "dollar", "달러", "liquidity", "유동성")):
        return _canonical_def("rates_dollar_liquidity")
    if _contains_any(blob, ("코스피", "코스닥", "한국 증시", "kospi", "kosdaq", "외국인", "기관")):
        return _canonical_def("korea_equity_rally")
    if _contains_any(blob, ("수출", "export", "무역", "관세", "tariff")):
        return _canonical_def("korea_export_cycle")
    return None


def apply_canonical_state(memory: dict) -> dict:
    memory = dict(memory or {})
    canonical = canonical_state_for(
        memory.get("stateKey") or memory.get("state_key") or "",
        memory.get("stateLabel") or memory.get("state_label") or "",
        memory.get("storyFamily") or memory.get("story_family") or "",
        memory.get("story") or "",
        _state_blob(
            memory.get("title", ""),
            memory.get("summary", ""),
            memory.get("storyThesis") or memory.get("story_thesis") or "",
            memory.get("tags", []),
            memory.get("industries", []),
            memory.get("tickers", []),
        ),
    )
    if not canonical:
        return memory
    original_state = normalize(memory.get("stateKey") or memory.get("state_key") or memory.get("story") or "")
    story = normalize(memory.get("story", ""))
    memory["stateKey"] = canonical["stateKey"]
    memory["stateLabel"] = canonical["stateLabel"]
    memory["storyFamily"] = canonical["storyFamily"]
    memory["parentStory"] = canonical["parentStory"]
    if not normalize(memory.get("storyThesis") or memory.get("story_thesis") or ""):
        memory["storyThesis"] = canonical["storyThesis"]
    if story and slug(story) != slug(canonical["stateKey"]):
        memory["storyRelation"] = "branches_from"
    elif original_state and slug(original_state) != slug(canonical["stateKey"]):
        memory["storyRelation"] = "branches_from"
    else:
        memory["storyRelation"] = "same_family"
    return memory


def inferred_axis_from_context(subject: str = "", tags: list[str] | None = None, text: str = "") -> dict:
    tags = [canonical_tag(tag) for tag in (tags or []) if canonical_tag(tag)]
    blob = text_blob(subject, " ".join(tags), text).lower()
    if _contains_any(blob, ("ai", "인공지능", "데이터센터", "data center")) and _contains_any(blob, ("전력", "power", "utility", "grid", "electricity", "원전", "전선", "구리")):
        return {"key": "ai_data_center_power_bottleneck", "label": "AI 데이터센터 전력 병목", "thesis": "AI 인프라 수요가 전력, 유틸리티, 전선·구리 등 물리 인프라 병목으로 확산되는 흐름"}
    if _contains_any(blob, ("nvidia", "nvda", "dell", "sk하이닉스", "하이닉스", "samsung", "삼성전자", "삼성전기", "micron", "tsmc", "broadcom", "반도체", "semiconductor", "hbm", "gpu", "ai server", "ai 서버", "mlcc")):
        return {"key": "ai_semiconductor_supply_chain", "label": "AI 반도체 공급망", "thesis": "AI 투자 사이클이 반도체, 서버, 메모리, 부품 공급망의 실적 기대와 수급으로 전이되는 흐름"}
    if _contains_any(blob, ("fed", "fomc", "treasury", "yield", "bond", "rate", "dollar", "fx", "금리", "국채", "채권", "달러", "환율", "유동성", "스와프")):
        return {"key": "rates_dollar_liquidity", "label": "금리·달러 유동성", "thesis": "금리, 국채 수급, 달러 유동성이 위험자산 밸류에이션과 자금 흐름을 좌우하는 흐름"}
    if _contains_any(blob, ("iran", "hormuz", "middle east", "oil", "brent", "wti", "war", "이스라엘", "이란", "호르무즈", "중동", "유가", "원유", "전쟁", "종전")):
        return {"key": "middle_east_energy_risk", "label": "중동 에너지 리스크", "thesis": "중동 지정학과 에너지 가격 프리미엄이 물가, 금리, 산업 비용으로 전이되는 흐름"}
    if _contains_any(blob, ("earnings", "guidance", "revenue", "sales outlook", "beat", "miss", "margin", "eps", "실적", "가이던스", "매출", "영업이익", "마진", "어닝")):
        return {"key": "earnings_revision_cycle", "label": "실적 기대 재가격화", "thesis": "개별 기업의 실적·가이던스 뉴스가 업종 이익 추정과 위험선호로 전이되는 흐름"}
    if _contains_any(blob, ("policy", "regulation", "tariff", "government", "congress", "정책", "규제", "관세", "정부", "국회")):
        return {"key": "policy_regulation_risk", "label": "정책·규제 리스크", "thesis": "정책·규제 변화가 업종 수요, 비용, 밸류에이션에 반영되는 흐름"}
    if _contains_any(blob, ("stock", "shares", "index", "rally", "selloff", "market", "증시", "주가", "지수", "상승", "하락", "위험선호")):
        return {"key": "broad_market_risk_appetite", "label": "시장 위험선호 변화", "thesis": "지수와 업종 수급이 위험선호와 가격 반응을 통해 재분류되는 흐름"}
    return {"key": "market_observation", "label": "시장 관찰 메모", "thesis": "반복되는 시장 재료를 가격 반응과 후속 수급으로 확인하는 흐름"}


def display_memory_axis(row_or_label, tags: list[str] | None = None, text: str = "") -> str:
    if isinstance(row_or_label, sqlite3.Row):
        label = row_or_label["story_family"] or row_or_label["state_label"] or row_or_label["story"]
        key = slug(label)
        if key in GENERIC_ROUTE_TERMS or key in {"market_observation"}:
            row_tags = tags if tags is not None else parse_json_list(row_or_label["tags_json"])
            return inferred_axis_from_context(label, row_tags, text_blob(row_or_label["title"], row_or_label["summary"], row_or_label["story_thesis"])).get("label")
        return display_label(label)
    key = slug(str(row_or_label or ""))
    if key in GENERIC_ROUTE_TERMS or key in {"market_observation"}:
        return inferred_axis_from_context(str(row_or_label or ""), tags or [], text).get("label")
    return display_label(str(row_or_label or ""))


def dedupe_sentences(text: str, limit: int = 700) -> str:
    text = clean_text(text)
    pieces = re.split(r"(?<=[.!?。！？])\s+|(?<=다\.)\s+", text)
    seen = set()
    out = []
    for piece in pieces:
        piece = normalize(piece).strip(" -")
        if len(piece) < 12:
            continue
        key = re.sub(r"[^0-9a-z가-힣]+", "", piece.lower())[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(piece)
        if len(" ".join(out)) >= limit:
            break
    return " ".join(out)[:limit].strip()


def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", str(text or "")))



def compact_memory_text(text: str, limit: int = 520) -> str:
    """Build a reader-facing narrative sentence without leaking tag glossary text."""
    text = dedupe_sentences(text, limit * 2)
    text = re.sub(r"(?:금융/금리|에너지|AI|반도체|인터넷|하드웨어|매출 성장|마진|환율|수급)\s*[:：]\s*", "", text)
    text = re.sub(r"여기서\s+[A-Za-z가-힣/· ]+는\s*", "", text)
    text = re.sub(r"이 내러티브는[^.。！？]*메모입니다[.]?", "", text)
    text = re.sub(r"후속 기사와 거래대금[^.。！？]*높아집니다[.]?", "", text)
    text = re.sub(r"따라서 핵심은 뉴스 자체보다\s*", "핵심은 ", text)
    text = normalize(text)
    return dedupe_sentences(text, limit)


def _text_signature(text: str) -> set[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", str(text or "").lower())
    stop = {"내러티브", "관련", "최근", "자료", "흐름", "확인", "시장", "입니다", "합니다", "the", "and", "for", "with"}
    return {token for token in tokens if token not in stop}


def too_similar_text(left: str, right: str, threshold: float = 0.62) -> bool:
    a = _text_signature(left)
    b = _text_signature(right)
    if not a or not b:
        return False
    return len(a & b) / max(1, min(len(a), len(b))) >= threshold


def state_body_paragraph(label: str, category: str = "", rationale: str = "") -> str:
    name = display_label(label)
    text = f"{name} {rationale}".lower()
    if re.search(r"금리|rates|yield|dollar|달러|liquidity|유동성|국채", text):
        return "이 흐름은 장기금리, 달러, 원자재 가격이 할인율과 외국인 수급에 어떤 압력을 주는지 보는 축입니다. 사용자가 확인할 핵심은 금리 부담이 성장주 밸류에이션을 누르는지, 아니면 유동성 개선과 실적 기대가 이를 상쇄하는지입니다."
    if re.search(r"전력|power|utility|grid|데이터센터|data center|구리|전선", text):
        return "이 흐름은 AI 데이터센터 투자가 전력, 유틸리티, 송전망, 전선·구리 같은 물리 인프라 수요로 번지는지 보는 축입니다. 핵심은 병목이 비용 부담으로 남는지, 아니면 관련 인프라 기업의 수주와 실적 기대를 끌어올리는지입니다."
    if re.search(r"반도체|semiconductor|server|서버|memory|메모리|hbm|gpu|공급망|ai", text):
        return "이 흐름은 AI 투자 사이클이 GPU 한 종목을 넘어 서버, 메모리, 네트워킹, 전자부품 공급망의 실적 기대와 수급으로 확산되는지 보는 축입니다. 핵심은 수요가 실제 주문과 가이던스로 확인되는지, 그리고 수혜 범위가 후방 공급망까지 넓어지는지입니다."
    if re.search(r"oil|energy|유가|에너지|middle east|중동|호르무즈", text):
        return "이 흐름은 유가와 지정학 리스크가 물가, 금리 기대, 산업 비용, 에너지 업종 이익으로 전이되는지 보는 축입니다. 핵심은 단순 가격 급등보다 그 충격이 기업 마진과 금리 경로에 얼마나 오래 남는지입니다."
    if re.search(r"earnings|guidance|revenue|margin|실적|가이던스|매출|마진|이익", text):
        return "이 흐름은 개별 뉴스가 단순 관심 증가에 그치지 않고 실적 추정과 밸류에이션 재평가로 이어지는지 보는 축입니다. 핵심은 매출 성장, 마진, 가이던스가 실제 숫자로 확인되는지입니다."
    if re.search(r"policy|regulation|tariff|정책|규제|관세|정부", text):
        return "이 흐름은 정책과 규제가 업종 수요, 비용 구조, 밸류에이션에 어떤 방향으로 반영되는지 보는 축입니다. 핵심은 발표 자체보다 기업 실적과 수급에 미치는 경로가 분명해지는지입니다."
    return f"{name} 흐름은 반복적으로 등장한 재료가 가격 반응, 실적 기대, 수급 변화 중 어디로 전이되는지 보기 위한 점검 대상입니다. 단기 기사보다 같은 방향의 후속 뉴스와 거래대금, 가이던스 변화를 함께 확인해야 합니다."
def text_blob(*parts) -> str:
    return clean_text(" ".join(str(part or "") for part in parts))


def story_route(subject: str, docs: list[dict], tags: list[str], industries: list[str], tickers: list[str]) -> dict:
    blob = text_blob(
        subject,
        " ".join(tags),
        " ".join(industries),
        " ".join(tickers),
        " ".join(doc.get("title", "") for doc in docs[:6]),
        " ".join(doc.get("summary") or doc.get("content", "")[:400] for doc in docs[:4]),
    ).lower()

    routes = [
        (
            "ai_data_center_power_bottleneck",
            r"(ai|인공지능|데이터센터|data center).*(전력|power|utility|grid|electricity|원전|전선|구리)|(전력|power|utility|grid|전선|구리).*(ai|데이터센터|data center)",
            "AI 데이터센터 전력 병목",
            "AI 인프라 수요가 전력, 유틸리티, 전선·구리 등 물리 인프라 병목으로 확산되는 흐름",
        ),
        (
            "ai_semiconductor_supply_chain",
            r"nvidia|nvda|dell|sk하이닉스|하이닉스|samsung|삼성전자|삼성전기|micron|tsmc|broadcom|반도체|semiconductor|hbm|gpu|ai server|ai 서버|mlcc",
            "AI 반도체 공급망",
            "AI 투자 사이클이 반도체, 서버, 메모리, 부품 공급망의 실적 기대와 수급으로 전이되는 흐름",
        ),
        (
            "rates_dollar_liquidity",
            r"fed|fomc|treasury|yield|bond|rate|dollar|fx|금리|국채|채권|달러|환율|유동성|스와프",
            "금리·달러 유동성",
            "금리, 국채 수급, 달러 유동성이 위험자산 밸류에이션과 자금 흐름을 좌우하는 흐름",
        ),
        (
            "middle_east_energy_risk",
            r"iran|hormuz|middle east|oil|brent|wti|war|이스라엘|이란|호르무즈|중동|유가|원유|전쟁|종전",
            "중동 에너지 리스크",
            "중동 지정학과 에너지 가격 프리미엄이 물가, 금리, 산업 비용으로 전이되는 흐름",
        ),
        (
            "korea_export_cycle",
            r"수출|반도체 수출|무역|관세|원화|환율|한국 수출|export",
            "한국 수출 사이클",
            "반도체와 주력 산업 수출이 원화, 기업이익, 한국 증시 수급에 영향을 주는 흐름",
        ),
        (
            "korea_equity_rally",
            r"코스피|코스닥|외국인|기관|국민연금|한국 증시|kospi|kosdaq",
            "한국 증시 랠리",
            "한국 증시의 지수 상승, 주도 업종, 외국인·기관 수급이 이어지는 흐름",
        ),
        (
            "us_ai_equity_rally",
            r"s&p|nasdaq|월가|미국 증시|us stocks|ai trade|big tech|magnificent",
            "미국 AI 주식 랠리",
            "미국 대형 기술주와 AI 테마가 지수 상승과 밸류에이션 논쟁을 주도하는 흐름",
        ),
    ]
    for key, pattern, label, thesis in routes:
        if re.search(pattern, blob, re.I):
            subject_key = slug(subject)
            branch = subject_key if subject and subject_key != key and subject_key not in GENERIC_ROUTE_TERMS else key
            story = branch if branch != "시장" else key
            return {
                "story": story,
                "storyFamily": label,
                "stateKey": key,
                "stateLabel": label,
                "storyThesis": thesis,
                "relation": "branches_from" if story != key else "same_family",
                "parentStory": key,
            }
    subject_key = slug(subject)
    if not subject or subject_key in GENERIC_ROUTE_TERMS:
        axis = inferred_axis_from_context(subject, tags, blob)
        key = axis["key"]
        label = axis["label"]
        thesis = axis["thesis"]
        return {
            "story": key,
            "storyFamily": label,
            "stateKey": key,
            "stateLabel": label,
            "storyThesis": thesis,
            "relation": "same_family",
            "parentStory": key,
        }
    label = display_label(subject)
    key = slug(subject or "market")
    return {
        "story": key,
        "storyFamily": label,
        "stateKey": key,
        "stateLabel": label,
        "storyThesis": f"{label} 관련 뉴스가 반복되며 중기 점검 대상으로 누적되는 흐름",
        "relation": "same_family",
        "parentStory": key,
    }


def doc_matches_subject(doc: dict, subject: str, tickers: list[str]) -> bool:
    subject_key = slug(subject)
    if not subject or subject_key in {"시장", "market", "ai", "energy", "semiconductors"}:
        return True
    hay = text_blob(doc.get("title", ""), doc.get("summary", ""), doc.get("content", "")[:1200]).lower()
    subject_lower = normalize(subject).lower()
    if subject_lower and subject_lower in hay:
        return True
    for ticker in tickers:
        token = normalize(ticker)
        if token and re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", hay, re.I):
            return True
    for company in doc.get("companies", []) or []:
        if slug(company.get("name", "")) == subject_key or slug(company.get("ticker", "")) == subject_key:
            return True
    return False


def _taxonomy_values(memory: dict) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for term_type, value, label in [
        ("category", memory.get("category", ""), memory.get("category", "")),
        ("region", memory.get("region", ""), memory.get("region", "")),
        ("importance", memory.get("importance", ""), memory.get("importance", "")),
        ("entry_mode", memory.get("entryMode", ""), memory.get("entryMode", "")),
        ("story", memory.get("story", ""), display_label(memory.get("story", ""))),
        ("story_family", memory.get("storyFamily", ""), display_label(memory.get("storyFamily", ""))),
        ("story_relation", memory.get("storyRelation", ""), memory.get("storyRelation", "")),
        ("event_kind", memory.get("eventKind", ""), EVENT_KIND_LABELS.get(memory.get("eventKind", ""), memory.get("eventKind", ""))),
        ("state_key", memory.get("stateKey", "") or memory.get("story", ""), display_label(memory.get("stateLabel", "") or memory.get("stateKey", ""))),
        ("net_effect", memory.get("netEffect", ""), memory.get("netEffect", "")),
    ]:
        key = slug(value)
        if key:
            rows.append((term_type, key, label or value))
    for tag in memory.get("tags", []) or []:
        tag = canonical_tag(tag)
        rows.append(("tag", slug(tag), TAG_LABELS.get(tag, str(tag))))
    for industry in memory.get("industries", []) or []:
        industry = canonical_industry(industry)
        rows.append(("industry", slug(industry), TAG_LABELS.get(industry, str(industry))))
    for ticker in memory.get("tickers", []) or []:
        rows.append(("ticker", slug(ticker), str(ticker).upper()))
    for subject in memory.get("subjects", []) or []:
        name = subject.get("name", "") if isinstance(subject, dict) else str(subject)
        subject_type = canonical_subject_type(subject.get("type", "") if isinstance(subject, dict) else "")
        rows.append(("subject", slug(name), display_label(name)))
        rows.append(("subject_type", slug(subject_type), subject_type))
    return [(a, b, c) for a, b, c in rows if a in TAXONOMY_TYPES and b]


def update_taxonomy(conn: sqlite3.Connection, memory: dict, observed_at: str | None = None) -> None:
    now = observed_at or dt.datetime.now(dt.timezone.utc).isoformat()
    for term_type, term_key, label in _taxonomy_values(memory):
        conn.execute(
            """
            INSERT INTO market_memory_taxonomy (term_type, term_key, label, count, first_seen, last_seen)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(term_type, term_key) DO UPDATE SET
                label=excluded.label,
                count=count + 1,
                last_seen=excluded.last_seen
            """,
            (term_type, term_key, label, now, now),
        )


def upsert_story_link(conn: sqlite3.Connection, from_story: str, to_story: str, relation: str, strength: float, evidence: str, updated_at: str | None = None) -> None:
    import hashlib

    from_key = slug(from_story)
    to_key = slug(to_story)
    if not from_key or not to_key or from_key == to_key:
        return
    relation = normalize_choice(relation, STORY_RELATIONS, "same_family")
    updated_at = updated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    link_id = hashlib.sha256(f"{from_key}:{to_key}:{relation}".encode("utf-8")).hexdigest()[:16]
    conn.execute(
        """
        INSERT INTO market_story_links (link_id, from_story, to_story, relation, strength, evidence, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(link_id) DO UPDATE SET
            strength=excluded.strength,
            evidence=excluded.evidence,
            updated_at=excluded.updated_at
        """,
        (link_id, from_key, to_key, relation, float(strength), clean_text(evidence)[:500], updated_at),
    )


def upsert_family_suggestion(conn: sqlite3.Connection, story: str, suggested_family: str, reason: str, observed_at: str | None = None) -> None:
    import hashlib

    story_key = slug(story)
    family_key = slug(suggested_family)
    if not story_key or not family_key or story_key == family_key:
        return
    now = observed_at or dt.datetime.now(dt.timezone.utc).isoformat()
    suggestion_id = hashlib.sha256(f"{story_key}:{family_key}".encode("utf-8")).hexdigest()[:16]
    conn.execute(
        """
        INSERT INTO market_story_family_suggestions (
            suggestion_id, story, suggested_family, suggested_family_label, reason, status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'suggested', ?, ?)
        ON CONFLICT(suggestion_id) DO UPDATE SET
            suggested_family_label=excluded.suggested_family_label,
            reason=excluded.reason,
            updated_at=excluded.updated_at
        """,
        (suggestion_id, story_key, family_key, display_label(suggested_family), clean_text(reason)[:600], now, now),
    )


# 사용자 화면에 "겹치는 주제"로 보여줄 수 없는 내부/잔여 분류값
_SUGGESTION_TAG_DENYLIST = {"unclassified", "unknown", "other", "etc", "misc", "market", "market_observation"}


def family_suggestion_context(conn: sqlite3.Connection, story: str, suggested_family: str, reason: str) -> dict:
    story_key = slug(story)
    family_key = slug(suggested_family)
    # story 행과 family 행을 따로 조회한다 — 한 쿼리로 합치면 최신 family 행이 LIMIT을 다 차지해
    # 정작 이 제안을 만든 story 행(근거 기사의 출처)이 밀려난다.
    story_rows = conn.execute(
        """
        SELECT story, state_key, title, summary, story_thesis, tags_json, industries_json, sources_json
        FROM market_memory
        WHERE story = ? OR state_key = ?
        ORDER BY date DESC, as_of DESC
        LIMIT 4
        """,
        (story_key, story_key),
    ).fetchall()
    family_rows = conn.execute(
        """
        SELECT story, state_key, title, summary, story_thesis, tags_json, industries_json, sources_json
        FROM market_memory
        WHERE story_family = ? OR story = ? OR state_key = ? OR story_family = ?
        ORDER BY date DESC, as_of DESC
        LIMIT 4
        """,
        (suggested_family, family_key, family_key, family_key),
    ).fetchall()
    rows = list(story_rows) + list(family_rows)
    tags = []
    industries = []
    evidence = []
    story_sources = []
    family_sources = []
    seen_sources = set()
    for row in rows:
        for tag in parse_json_list(row["tags_json"]):
            tag = canonical_tag(tag)
            if tag and tag not in tags:
                tags.append(tag)
        for industry in parse_json_list(row["industries_json"]):
            industry = canonical_industry(industry)
            if industry and industry not in industries:
                industries.append(industry)
        text = dedupe_sentences(f"{row['title']} {row['summary']} {row['story_thesis']}", 240)
        if text:
            evidence.append(text)
        # 근거 기사는 이 제안을 만든 story 쪽 기사를 우선하고, 없으면 family 쪽으로 보충
        is_story_row = slug(row["story"] or "") == story_key or slug(row["state_key"] or "") == story_key
        bucket = story_sources if is_story_row else family_sources
        if is_story_row or len(bucket) < 3:
            for source in parse_json_list(row["sources_json"]):
                if not isinstance(source, dict):
                    continue
                title = clean_text(source.get("title") or "")
                if not title:
                    continue
                dedupe = source.get("url") or f"{source.get('source', '')}:{title}"
                if dedupe in seen_sources:
                    continue
                seen_sources.add(dedupe)
                bucket.append(
                    {
                        "source": clean_text(source.get("source") or ""),
                        "title": title[:160],
                        "url": source.get("url") or "",
                        "date": str(source.get("date") or "")[:10],
                    }
                )
                if not is_story_row and len(bucket) >= 3:
                    break
    # story 행 sources에는 브리핑 일괄 수집 기사가 섞일 수 있으므로, 제목에 story가 언급된 기사를 앞으로
    story_tokens = [token for token in re.split(r"[_\s]+", clean_text(story).lower()) if len(token) >= 3]
    if story_tokens:
        story_sources.sort(key=lambda item: 0 if any(token in item["title"].lower() for token in story_tokens) else 1)
    evidence_sources = (story_sources + family_sources)[:3]
    story_label = display_memory_axis(story, tags, " ".join(evidence))
    family_label = display_memory_axis(suggested_family, tags, " ".join(evidence))
    explanations = tag_scope_explanations(f"{story_label} {family_label}", tags + industries, " ".join(evidence), reason, limit=3)
    shared_tags = []
    for item in tags + industries:
        if slug(item) in _SUGGESTION_TAG_DENYLIST:
            continue
        label = display_label(item)
        if label and label not in shared_tags:
            shared_tags.append(label)
        if len(shared_tags) >= 4:
            break
    detail = (
        f"{story_label} 이슈가 {family_label} 흐름과 같은 원인→영향 고리로 움직이는 것으로 보입니다. "
        f"두 흐름을 하나의 큰 줄기로 합쳐서 추적할까요?"
    )
    return {
        "storyLabel": story_label,
        "familyLabel": family_label,
        "reason": detail,
        "sharedTags": shared_tags,
        "evidenceSources": evidence_sources,
        "tagExplanations": explanations,
    }


def memory_support(conn: sqlite3.Connection, state_key: str, date: str, days: int = 45) -> dict:
    state_key = slug(state_key)
    try:
        end = dt.date.fromisoformat(str(date)[:10])
    except Exception:
        end = dt.datetime.now(dt.timezone.utc).date()
    start = (end - dt.timedelta(days=days)).isoformat()
    rows = conn.execute(
        """
        SELECT memory_id, importance, sources_json, date
        FROM market_memory
        WHERE entry_mode = 'issue'
          AND COALESCE(state_key, story) = ?
          AND date >= ?
        ORDER BY date DESC, as_of DESC
        """,
        (state_key, start),
    ).fetchall()
    sources = set()
    high = 0
    for row in rows:
        if row["importance"] == "high":
            high += 1
        for source in parse_json_list(row["sources_json"]):
            key = source.get("url") or f"{source.get('source', '')}:{source.get('title', '')}"
            if key:
                sources.add(key)
    return {"issues": len(rows), "sources": len(sources), "high": high}


def should_derive_state(conn: sqlite3.Connection, memory: dict) -> bool:
    if normalize_choice(memory.get("entryMode", ""), ENTRY_MODE_CHOICES, "issue") != "issue":
        return False
    if slug(memory.get("stateKey", "") or memory.get("story", "")) in GENERIC_ROUTE_TERMS:
        return False
    if memory.get("stateStatus") in STATE_STATUS_CHOICES:
        return True
    support = memory_support(conn, memory.get("stateKey", "") or memory.get("story", ""), memory.get("date", ""))
    source_count = len(memory.get("sources", []) or [])
    if memory.get("importance") == "high" and source_count >= 2:
        return True
    if support["issues"] >= MIN_DERIVED_STATE_SUPPORT or support["sources"] >= MIN_DERIVED_STATE_SUPPORT:
        return True
    return False


def match_existing_family(conn: sqlite3.Connection, story: str, tags: list[str], industries: list[str], tickers: list[str]) -> dict | None:
    story_key = slug(story)
    if story_key in GENERIC_ROUTE_TERMS:
        return None
    tag_set = {slug(canonical_tag(tag)) for tag in tags if tag}
    industry_set = {slug(canonical_industry(item)) for item in industries if item}
    ticker_set = {slug(ticker) for ticker in tickers if ticker and slug(ticker) not in GENERIC_ROUTE_TERMS}
    if not (tag_set or industry_set or ticker_set):
        return None
    rows = conn.execute(
        """
        SELECT story, story_family, state_key, state_label, tags_json, industries_json, tickers_json, COUNT(*) OVER (PARTITION BY state_key) AS support
        FROM market_memory
        WHERE COALESCE(state_key, '') <> ''
        ORDER BY date DESC, as_of DESC
        LIMIT 80
        """
    ).fetchall()
    best = None
    best_score = 0
    for row in rows:
        candidate_state = row["state_key"]
        if not candidate_state or slug(candidate_state) == story_key:
            continue
        row_tags = {slug(canonical_tag(tag)) for tag in parse_json_list(row["tags_json"]) if tag}
        row_industries = {slug(canonical_industry(item)) for item in parse_json_list(row["industries_json"]) if item}
        row_tickers = {slug(ticker) for ticker in parse_json_list(row["tickers_json"]) if ticker and slug(ticker) not in GENERIC_ROUTE_TERMS}
        score = len(tag_set & row_tags) + len(industry_set & row_industries) * 2 + len(ticker_set & row_tickers) * 3
        if score > best_score:
            best_score = score
            best = row
    if best is not None and best_score >= 3:
        return {
            "stateKey": best["state_key"],
            "stateLabel": best["state_label"] or best["story_family"] or best["state_key"],
            "storyFamily": best["story_family"] or best["state_label"] or best["state_key"],
            "parentStory": best["state_key"],
            "storyRelation": "same_family",
            "score": best_score,
        }
    return None


def join_labels(values: list[str], limit: int = 4) -> str:
    labels = [TAG_LABELS.get(value, value) for value in values[:limit]]
    return ", ".join(dict.fromkeys(label for label in labels if label))


def narrative_summary(subject: str, docs: list[dict], tags: list[str], event_kind: str) -> str:
    label = display_label(subject)
    rows = []
    seen = set()
    for doc in docs[:5]:
        title = clean_text(doc.get("title", ""))
        body = clean_text(doc.get("summary") or doc.get("content") or "")
        source = clean_text(doc.get("source", "자료"))
        key = re.sub(r"[^0-9a-z가-힣]+", "", f"{source}{title}".lower())[:140]
        if not title or key in seen:
            continue
        seen.add(key)
        if body and body.lower().startswith(title.lower()):
            body = body[len(title):].strip(" .:-")
        rows.append((source, title, body[:220]))
    if not rows:
        return f"{label} 관련 자료가 축적되고 있지만, 아직 요약 가능한 본문이 충분하지 않습니다."
    first = rows[0]
    event_label = EVENT_KIND_LABELS.get(event_kind, event_kind or "관찰")
    tag_text = join_labels(tags, 4)
    source_names = ", ".join(dict.fromkeys(source for source, _, _ in rows[:4] if source))
    if has_korean(f"{first[1]} {first[2]}"):
        sentences = [f"{label} 내러티브는 '{first[1]}' 이슈를 중심으로 형성되고 있습니다."]
    else:
        theme = tag_text or event_label
        sentences = [f"{label} 내러티브는 {theme} 관련 보도가 누적되며 형성되고 있습니다."]
    if first[2] and has_korean(first[2]):
        sentences.append(f"{first[0]} 보도는 {first[2]}라는 내용을 전했습니다.")
    elif source_names:
        sentences.append(f"주요 출처는 {source_names}이며, 관련 보도는 가격 반응과 후속 실적 기대를 함께 점검할 필요가 있습니다.")
    for source, title, body in rows[1:3]:
        detail = body or title
        if has_korean(detail):
            sentences.append(f"추가로 {source}는 {detail}라는 흐름을 보강했습니다.")
    if tag_text:
        sentences.append(f"관찰 포인트는 {tag_text} 항목이 실제 실적 기대, 수급, 밸류에이션에 이어지는지입니다.")
    if event_kind:
        sentences.append(f"현재 이 이슈는 {event_label} 성격의 중기 점검 대상으로 분류됩니다.")
    return dedupe_sentences(" ".join(sentences), 900)


def normalize_choice(value: str, allowed: set[str], default: str) -> str:
    token = normalize(value).lower()
    if token in allowed:
        return token
    upper_map = {item.lower(): item for item in allowed}
    return upper_map.get(token, default)


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def json_list(value) -> str:
    return json.dumps(as_list(value), ensure_ascii=False)


def parse_json_list(value: str) -> list:
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def detect_region(sources: list[dict], text: str) -> str:
    blob = f"{text} {' '.join(str(source.get('source', '')) for source in sources)}"
    signals = {
        MarketCode.KR.value: r"한국|코스피|코스닥|삼성|하이닉스|한경|매일경제|연합뉴스|KRW|KOSPI",
        MarketCode.US.value: r"\bUS\b|미국|Fed|S&P|Nasdaq|Dow|Reuters|Bloomberg|WSJ|Financial Times",
        MarketCode.EUROPE.value: r"유럽|영국|독일|프랑스|네덜란드|이탈리아|스페인|ECB|DAX|CAC ?40|AEX|FTSE ?MIB|IBEX|STOXX",
        MarketCode.JP.value: r"일본|日経|東証|TOPIX|Nikkei|Tokyo Stock Exchange|\bBOJ\b|엔화|JPY",
    }
    matched = [market for market, pattern in signals.items() if re.search(pattern, blob, re.I)]
    return matched[0] if len(matched) == 1 else MarketCode.GLOBAL.value


def detect_category(text: str, tags: list[str]) -> str:
    blob = " ".join([text, *[str(tag) for tag in tags]]).lower()
    if re.search(r"earnings|guidance|revenue|margin|stock|shares|semiconductor|ai|실적|가이던스|매출|마진|주가|반도체", blob):
        return "stock_bond"
    if re.search(r"fed|rate|yield|bond|treasury|dollar|fx|oil|금리|환율|유가|국채|채권", blob):
        return "stock_bond"
    if re.search(r"iran|war|tariff|election|policy|regulation|hormuz|이란|전쟁|관세|정책|규제|지정학|호르무즈", blob):
        return "geopolitics"
    return "emerging"


def detect_importance(text: str, tags: list[str], source_count: int) -> str:
    blob = " ".join([text, *[str(tag) for tag in tags]]).lower()
    if re.search(HIGH_IMPACT_EARNINGS_HINTS, blob):
        return "high"
    if re.search(EARNINGS_HINTS, blob) and source_count >= 1:
        return "medium" if source_count < 3 else "high"
    if source_count >= 4 or re.search(r"surge|plunge|record|guidance|earnings|tariff|war|fed|급등|급락|사상|가이던스|실적|관세|전쟁|금리", blob):
        return "high"
    if source_count >= 2:
        return "medium"
    return "low"


def detect_event_kind(text: str) -> str:
    blob = text.lower()
    checks = [
        ("earnings", r"earnings|guidance|revenue|margin|eps|실적|가이던스|매출|영업이익|마진"),
        ("policy", r"fed|rate|tariff|regulation|policy|금리|관세|규제|정책"),
        ("geopolitics", r"iran|war|hormuz|defense|election|전쟁|중동|방산|대선|선거"),
        ("industry_trend", r"ai|semiconductor|data center|supply|chip|반도체|데이터센터|공급망|산업"),
        ("market_move", r"stock|shares|index|rally|selloff|주가|증시|코스피|나스닥|상승|하락"),
    ]
    for label, pattern in checks:
        if re.search(pattern, blob):
            return label
    return "brief"


def infer_bias(text: str) -> str:
    blob = text.lower()
    positive = len(re.findall(r"surge|rally|record|beat|raise|growth|up|급등|상승|호조|성장|상향|최고", blob))
    negative = len(re.findall(r"fall|drop|plunge|miss|cut|risk|down|하락|급락|부진|위험|하향|우려", blob))
    if positive and negative:
        return "mixed"
    if positive:
        return "bullish"
    if negative:
        return "bearish"
    return "neutral"


def infer_net_effect(category: str, bias: str, tags: list[str]) -> str:
    joined = " ".join(str(tag).lower() for tag in tags)
    if "semiconductor" in joined or "ai" in joined:
        return f"ai_semis_{bias}"
    if "energy" in joined or "oil" in joined:
        return f"energy_{bias}"
    if "금리" in joined or "rates" in joined:
        return f"rates_{bias}"
    return f"{category}_{bias}"


def make_checkpoint(event_kind: str, subject: str, tags: list[str], docs: list[dict], bias: str = "neutral") -> str:
    label = display_label(subject)
    tag_blob = " ".join(str(t).lower() for t in tags)
    catalysts = []
    for doc in docs[:4]:
        m = re.search(r"(FOMC|CPI|PCE|NFP|실적\s*발표|어닝|earnings call|guidance|금리\s*결정|기준금리|정책금리)", doc.get("title", ""), re.I)
        if m:
            catalysts.append(m.group(0).strip())
    catalyst_str = f" ({', '.join(dict.fromkeys(catalysts[:2]))})" if catalysts else ""
    direction = {"bullish": "상승 추세 지속", "bearish": "하방 압력 지속", "mixed": "방향성", "neutral": "가격 반응 방향"}.get(bias, "가격 반응 방향")
    templates = {
        "earnings": f"{label} 실적 발표{catalyst_str}, EPS·매출 컨센서스 대비, 가이던스 상향·하향으로 {direction} 확인",
        "policy": f"다음 FOMC·금리 결정{catalyst_str}, CPI/PCE 지표, 정책 발표 후 채권·달러 반응으로 {direction} 추적",
        "geopolitics": f"분쟁 지역 긴장 완화·에스컬레이션{catalyst_str}, 유가·방산주·안전자산 가격 반응으로 {direction} 점검",
        "industry_trend": f"{label} 공급망·수주 변화{catalyst_str}, AI·반도체 수요 사이클 지속성, 다음 실적 가이던스로 {direction} 확인",
        "market_move": f"{label} 가격 반응{catalyst_str}, 외국인·기관 수급, 거래대금으로 {direction} 추적",
        "brief": f"{label} 관련 후속 보도{catalyst_str}, 수급 변화, 정책 발표 방향으로 {direction} 확인",
    }
    base = templates.get(event_kind, templates["brief"])
    extras = []
    if re.search(r"환율|fx|dollar|달러|usd", tag_blob) and "달러" not in base:
        extras.append("달러·환율 방향")
    if re.search(r"공급망|supply chain|logistics", tag_blob) and "공급망" not in base:
        extras.append("공급망 동향")
    if extras:
        base = base.rstrip() + f", {', '.join(extras[:2])} 포함"
    return base


def narrative_thesis(subject: str, event_kind: str, bias: str, tags: list[str]) -> str:
    label = display_label(subject)
    event_label = EVENT_KIND_LABELS.get(event_kind, event_kind or "관찰")
    tag_text = join_labels(tags, 3) or "실적 기대와 수급"
    bias_text = {
        "bullish": "긍정적",
        "bearish": "부정적",
        "mixed": "혼재된",
        "neutral": "중립적",
    }.get(bias, "중립적")
    return f"{label} 이슈는 {event_label} 재료로 분류되며, 현재 시장에는 {bias_text} 신호로 누적되고 있습니다. 핵심은 {tag_text} 항목이 후속 가격 반응과 이익 추정 변화로 이어지는지입니다."


def display_summary(label: str, summary: str, category: str = "", event_kind: str = "", rationale: str = "") -> str:
    cleaned = compact_memory_text(summary, 520)
    generic_or_noisy = (
        not cleaned
        or "태그는" in cleaned
        or "여기서" in cleaned
        or "보기 위한 메모" in cleaned
        or "뉴스 자체보다" in cleaned
        or "판단:" in cleaned
        or cleaned.count("판단") >= 2
        or len(cleaned) > 460
        or "반복적으로 포착되었습니다" in cleaned
        or "후속 가격 반응과 실적 기대" in cleaned
        or "관련 보도가 누적되며 형성" in cleaned
        or len(re.findall(r"\bReuters\b|Bloomberg|Dow Jones|Financial Times|한국경제|연합뉴스|매일경제", cleaned)) >= 2
        or len(re.findall(r"…|\.\.\.", cleaned)) >= 2
        or not has_korean(cleaned)
    )
    if not generic_or_noisy and not too_similar_text(cleaned, rationale, 0.72):
        return cleaned
    fallback = compact_memory_text(rationale, 260)
    body = state_body_paragraph(label, category, fallback or cleaned)
    return body

def display_rationale(label: str, rationale: str, event_kind: str = "") -> str:
    text = compact_memory_text(rationale, 360)
    for key, value in EVENT_KIND_LABELS.items():
        text = re.sub(rf"\b{re.escape(key)}\b", value, text)
    if text and has_korean(text) and not re.search(r"\b[a-z]+_[a-z_]+\b", text) and "태그는" not in text and "여기서" not in text:
        return text
    event_label = EVENT_KIND_LABELS.get(event_kind, event_kind or "시장 이슈")
    return f"{display_label(label)} 이슈는 {event_label} 흐름으로 분류됩니다. 가격 반응, 수급, 실적 가이던스가 같은 방향으로 확인되는지 보세요."
def tag_scope_explanations(label: str, tags: list[str], summary: str = "", rationale: str = "", limit: int = 4) -> list[dict]:
    text = f"{label} {summary} {rationale} {' '.join(str(tag) for tag in tags)}".lower()
    rows = []

    def add(tag: str, explanation: str):
        key = slug(tag)
        if not tag or any(row["key"] == key for row in rows):
            return
        rows.append({"key": key, "label": TAG_LABELS.get(tag, tag), "explanation": explanation})

    tag_set = {canonical_tag(tag) for tag in tags if canonical_tag(tag)}
    if "Financials" in tag_set or re.search(r"financial|금융|금리|rate|yield|credit|liquidity|유동성|달러", text):
        add("Financials", "여기서 Financials는 금융업종 전체보다 금리, 신용, 유동성, 자금조달 비용이 밸류에이션과 투자 여력에 미치는 경로를 뜻합니다.")
    if "Energy" in tag_set or re.search(r"energy|oil|유가|에너지|전력|power|utility|grid", text):
        if re.search(r"전력|power|utility|grid|data center|데이터센터", text):
            add("Energy", "여기서 Energy는 유가보다 AI 데이터센터 증설에 필요한 전력, 유틸리티, 송전망, 전선·구리 투자 병목을 가리킵니다.")
        else:
            add("Energy", "여기서 Energy는 유가와 중동 리스크가 인플레이션 기대, 금리 경로, 에너지 업종 이익에 전이되는 경로를 뜻합니다.")
    if "AI" in tag_set or re.search(r"\bai\b|인공지능|data center|데이터센터", text):
        add("AI", "AI 태그는 단순 기술 뉴스가 아니라 클라우드 CapEx, 서버 수요, 데이터센터 투자, 관련 기업의 실적 기대가 재가격화되는 축입니다.")
    if "Semiconductors" in tag_set or re.search(r"semiconductor|chip|반도체|hbm|memory|메모리|server|서버", text):
        add("Semiconductors", "반도체 태그는 GPU뿐 아니라 HBM/메모리, 서버, 네트워킹, 부품 공급망으로 수요가 확산되는지를 보는 분류입니다.")
    if "Internet" in tag_set or re.search(r"internet|alphabet|google|meta|cloud|클라우드", text):
        add("Internet", "Internet 태그는 검색·광고 기업 자체보다 빅테크의 AI 투자 여력, 클라우드 수요, CapEx 부담과 수익화 속도를 함께 보는 축입니다.")
    if "Hardware" in tag_set or re.search(r"hardware|server|pc|서버|하드웨어", text):
        add("Hardware", "Hardware 태그는 AI 서버·PC·장비 수요가 부품과 완제품 업체의 매출·마진으로 연결되는지를 보는 축입니다.")
    if "매출 성장" in tag_set or re.search(r"revenue|sales|매출|성장", text):
        add("매출 성장", "매출 성장 태그는 뉴스량보다 실제 주문, 가격, 가이던스 상향으로 이익 추정이 올라갈 수 있는지를 확인하는 신호입니다.")
    if "마진" in tag_set or re.search(r"margin|마진|비용|cost", text):
        add("마진", "마진 태그는 수요 증가가 가격 결정력과 영업레버리지로 이어지는지, 반대로 전력·부품·금리 비용이 이익률을 압박하는지를 보는 축입니다.")
    if "환율" in tag_set or re.search(r"fx|환율|달러|원화|dollar", text):
        add("환율", "환율 태그는 달러 강세와 원화 약세가 외국인 수급, 수출주 환산이익, 원가 부담에 어떤 방향으로 작용하는지를 뜻합니다.")
    if "수급" in tag_set or re.search(r"flow|수급|외국인|기관|거래대금", text):
        add("수급", "수급 태그는 뉴스가 실제 매수 주체, 거래대금, 업종 확산으로 이어지는지 확인하기 위한 가격 검증 축입니다.")
    return rows[:limit]


def narrative_context_paragraph(label: str, tags: list[str], category: str = "", event_kind: str = "", summary: str = "", rationale: str = "") -> str:
    name = display_label(label)
    event_label = EVENT_KIND_LABELS.get(event_kind, event_kind or "시장 이슈")
    category_label = {
        "stock_bond": "주식/채권",
        "geopolitics": "정책/지정학",
        "emerging": "신규 이슈",
    }.get(category, category or "시장")
    explanations = tag_scope_explanations(name, tags, summary, rationale, limit=3)
    if explanations:
        scope = " ".join(f"{item['label']}: {item['explanation']}" for item in explanations[:2])
    else:
        scope = f"이 내러티브는 {category_label} 범주의 {event_label} 흐름으로, 단일 기사보다 반복성과 가격 전이를 기준으로 추적합니다."
    return dedupe_sentences(
        f"{name} 내러티브는 최근 자료에서 반복된 재료가 어떤 가격 경로로 이어지는지 보기 위한 메모입니다. "
        f"{scope} 따라서 핵심은 뉴스 자체보다 이 흐름이 실적 기대, 밸류에이션 할인율, 업종 수급, 공급·수요 변화 중 어디로 전이되는지입니다. "
        "후속 기사와 거래대금, 외국인/기관 수급, 기업 가이던스 또는 정책 발표가 같은 방향을 확인해주면 내러티브의 지속성이 높아집니다.",
        900,
    )


def state_conclusion(label: str, bias: str, net_effect: str, summary: str = "", rationale: str = "") -> str:
    name = display_label(label)
    label_text = str(label or "").lower()
    primary_text = f"{label} {net_effect}".lower()
    full_text = f"{primary_text} {summary} {rationale}".lower()
    bias_label = {
        "bullish": "긍정",
        "bearish": "부정",
        "mixed": "혼재",
        "neutral": "중립",
    }.get(bias, "중립")
    if re.search(r"금리|rates?|yield|yields|dollar|달러|liquidity|유동성|국채", label_text):
        if bias == "bullish":
            return "판단: 금리·달러 부담은 완화 쪽 신호가 우세합니다. 주식에는 할인율 부담 축소가 핵심 변수입니다."
        if bias == "bearish":
            return "판단: 금리·달러 부담은 상승·긴축 쪽 리스크가 우세합니다. 성장주와 원화/외국인 수급에는 부담으로 해석합니다."
        if bias == "mixed":
            return "판단: 금리·달러 방향은 혼재되어 있습니다. 위험자산에는 우호적 유동성과 할인율 부담이 동시에 작동하는 국면입니다."
        return "판단: 금리·달러 방향은 아직 중립입니다. 다음 확인 포인트는 장기금리, 달러, 외국인 수급 중 어느 쪽이 먼저 움직이는지입니다."
    is_energy = bool(re.search(r"oil|energy|유가|에너지|middle east|중동|지정학|geopolitical", primary_text))
    is_power = bool(re.search(r"전력|power|electric|utility|utilities|grid|data ?center|데이터센터", primary_text))
    is_korea_fx = bool(
        re.search(r"관세|tariff|trade|무역|export|수출|fx|환율|원화|수급", primary_text)
        and not re.search(r"금리·달러|rates?_dollar|liquidity", primary_text)
    )
    is_ai_semis = bool(re.search(r"반도체|semiconductor|semis|server|서버|memory|메모리|hbm|supply|공급망|ai|리더십", primary_text))
    is_rates = bool(re.search(r"금리|rates?|yield|yields|dollar|달러|liquidity|유동성|국채", primary_text))
    if is_energy:
        if bias == "bullish":
            return "판단: 에너지·지정학 변수는 원자재와 관련 업종에는 우호적일 수 있지만, 인플레이션과 위험 프리미엄을 다시 자극할 수 있습니다."
        if bias == "bearish":
            return "판단: 에너지·지정학 리스크는 완화 쪽으로 기울고 있습니다. 유가와 달러 압력이 낮아지는지, 위험자산 수급 회복으로 이어지는지가 핵심입니다."
        return "판단: 에너지·지정학 변수는 방향보다 변동성 자체가 핵심입니다. 유가와 위험 프리미엄이 시장 할인율과 업종 마진으로 전이되는지 확인해야 합니다."
    if is_power:
        if bias in {"bearish", "mixed"}:
            return "판단: AI 데이터센터 전력 병목은 해소보다 심화·확산 여부를 봐야 하는 단계입니다. 수혜는 전력 인프라로 넓어질 수 있지만 비용 부담도 커질 수 있습니다."
        if bias == "bullish":
            return "판단: AI 전력 수요는 전력설비·유틸리티·전선 업종의 수주 기대를 키우는 방향입니다. 병목 완화보다 투자 확대가 핵심입니다."
        return "판단: AI 전력 병목은 아직 방향이 확정되지 않았습니다. 전력 투자 발표와 데이터센터 증설 속도가 병목 완화 여부를 가를 변수입니다."
    if is_korea_fx:
        if bias == "bullish":
            return "판단: 한국 수출·환율 변수는 수출주와 외국인 수급에 우호적인 쪽으로 기울고 있습니다. 지속성은 원화 안정, 주문 지표, 외국인 순매수가 확인해줘야 합니다."
        if bias == "bearish":
            return "판단: 한국 수출·환율 변수는 수출주와 원화 수급에 부담을 주는 방향입니다. 관세, 달러, 정책 리스크가 동시에 커지는지 봐야 합니다."
        if bias == "mixed":
            return "판단: 한국 수출·환율 변수는 실적 기대와 수급 민감도가 공존합니다. 수출 모멘텀이 원화·외국인 자금 흐름을 이겨내는지가 관건입니다."
        return "판단: 한국 수출·환율 변수는 아직 방향이 확정되지 않았습니다. 수출 회복 기대와 환율/수급 리스크 중 어느 쪽이 가격을 이끄는지 확인해야 합니다."
    if is_ai_semis:
        if bias == "bullish":
            return "판단: AI 반도체 공급망은 수요와 실적 기대가 여전히 우위입니다. 서버, 메모리, 부품으로 수혜가 확산되는지가 핵심입니다."
        if bias == "bearish":
            return "판단: AI 반도체 공급망은 기대보다 공급·마진·밸류에이션 부담이 커지는 쪽입니다. 주문 둔화나 가격 하락 신호를 우선 확인해야 합니다."
        if bias == "mixed":
            return "판단: AI 반도체 공급망은 수요 기대와 밸류에이션 부담이 공존합니다. 강세가 대형주에 머무는지, 후방 공급망으로 확산되는지가 관건입니다."
        return "판단: AI 반도체 공급망은 방향이 아직 중립입니다. 실적 가이던스, 주문 증가, 메모리 가격이 기대를 뒷받침하는지 봐야 합니다."
    if is_rates or (not any([is_energy, is_power, is_korea_fx, is_ai_semis]) and re.search(r"금리|rates?|yield|yields|dollar|달러|liquidity|유동성|국채", full_text)):
        if bias == "bullish":
            return "판단: 금리·달러 부담은 완화 쪽 신호가 우세합니다. 주식에는 할인율 부담 축소가 핵심 변수입니다."
        if bias == "bearish":
            return "판단: 금리·달러 부담은 상승·긴축 쪽 리스크가 우세합니다. 성장주와 원화/외국인 수급에는 부담으로 해석합니다."
        if bias == "mixed":
            return "판단: 금리·달러 방향은 혼재되어 있습니다. 위험자산에는 우호적 유동성과 할인율 부담이 동시에 작동하는 국면입니다."
        return "판단: 금리·달러 방향은 아직 중립입니다. 다음 확인 포인트는 장기금리, 달러, 외국인 수급 중 어느 쪽이 먼저 움직이는지입니다."
    return f"판단: {name} 내러티브는 현재 {bias_label} 신호입니다. 결론은 가격 반응, 실적 기대, 수급 변화 중 어느 축으로 전이되는지에 달려 있습니다."


def upsert_memory(
    db_path: str | Path | sqlite3.Connection,
    entry: dict,
    *,
    prepared_at: str | None = None,
) -> dict:
    import hashlib

    match db_path:
        case sqlite3.Connection() as connection:
            conn = connection
            owns_connection = False
        case str() | Path():
            conn = connect(db_path)
            init_db(conn)
            owns_connection = True
        case unreachable:
            assert_never(unreachable)
    entry = apply_canonical_state(entry or {})
    observed_at = prepared_at or dt.datetime.now(dt.timezone.utc).isoformat()
    date = str(entry.get("date") or observed_at[:10])[:10]
    title = clean_text(entry.get("title", "")) or "시장 내러티브"
    story = normalize(entry.get("story", "")) or slug(title)
    summary = clean_text(entry.get("summary", ""))
    tags = list(dict.fromkeys(canonical_tag(tag) for tag in as_list(entry.get("tags", [])) if canonical_tag(tag)))
    sources = as_list(entry.get("sources", []))
    subjects = as_list(entry.get("subjects", []))
    industries = list(dict.fromkeys(canonical_industry(item) for item in as_list(entry.get("industries", [])) if canonical_industry(item)))
    tickers = as_list(entry.get("tickers", []))
    story_family = normalize(entry.get("storyFamily") or entry.get("story_family") or story)
    story_thesis = clean_text(entry.get("storyThesis") or entry.get("story_thesis") or summary[:220])
    story_checkpoint = clean_text(entry.get("storyCheckpoint") or entry.get("story_checkpoint") or "후속 가격 반응, 실적/정책 확인, 관련 업종 확산 여부")
    state_key = normalize(entry.get("stateKey") or entry.get("state_key") or story)
    state_label = normalize(entry.get("stateLabel") or entry.get("state_label") or story_family or title)
    parent_story = normalize(entry.get("parentStory") or entry.get("parent_story") or state_key)
    story_relation = normalize_choice(entry.get("storyRelation") or entry.get("story_relation") or entry.get("relation", ""), STORY_RELATIONS, "same_family")
    category = normalize_choice(entry.get("category", ""), CATEGORY_CHOICES, detect_category(f"{title} {summary}", tags))
    region = normalize_choice(entry.get("region", ""), REGION_CHOICES, detect_region(sources, f"{title} {summary}"))
    importance = normalize_choice(entry.get("importance", ""), IMPORTANCE_CHOICES, detect_importance(f"{title} {summary}", tags, len(sources)))
    entry_mode = normalize_choice(entry.get("entryMode") or entry.get("entry_mode", ""), ENTRY_MODE_CHOICES, "issue")
    event_kind = normalize(entry.get("eventKind") or entry.get("event_kind") or detect_event_kind(f"{title} {summary}"))
    existing_family = match_existing_family(conn, story, tags, industries, tickers)
    if existing_family and story_relation == "same_family" and slug(state_key) == slug(story):
        story_family = existing_family["storyFamily"]
        state_key = existing_family["stateKey"]
        state_label = existing_family["stateLabel"]
        parent_story = existing_family["parentStory"]
        story_relation = existing_family["storyRelation"]
    net_effect = normalize(entry.get("netEffect") or entry.get("net_effect") or infer_net_effect(category, infer_bias(f"{title} {summary}"), tags))
    source_kind = normalize(entry.get("sourceKind") or entry.get("source_kind") or "auto")
    dedupe_key = normalize(entry.get("dedupeKey") or entry.get("dedupe_key") or f"{entry_mode}:{date}:{story}:{event_kind}")
    memory_id = str(entry.get("id") or hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:16])
    as_of = str(entry.get("asOf") or entry.get("as_of") or observed_at)
    created_at = observed_at
    with nullcontext():
        conn.execute(
            """
            INSERT INTO market_memory (
                memory_id, as_of, date, title, summary, story,
                story_family, story_thesis, story_checkpoint,
                category, region, importance, entry_mode, event_kind,
                subjects_json, industries_json, tickers_json,
                tags_json, sources_json, state_key, state_label, parent_story,
                story_relation, net_effect, source_kind, dedupe_key, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                as_of=excluded.as_of,
                date=excluded.date,
                title=excluded.title,
                summary=excluded.summary,
                story=excluded.story,
                story_family=excluded.story_family,
                story_thesis=excluded.story_thesis,
                story_checkpoint=excluded.story_checkpoint,
                category=excluded.category,
                region=excluded.region,
                importance=excluded.importance,
                entry_mode=excluded.entry_mode,
                event_kind=excluded.event_kind,
                subjects_json=excluded.subjects_json,
                industries_json=excluded.industries_json,
                tickers_json=excluded.tickers_json,
                tags_json=excluded.tags_json,
                sources_json=excluded.sources_json,
                state_key=excluded.state_key,
                state_label=excluded.state_label,
                parent_story=excluded.parent_story,
                story_relation=excluded.story_relation,
                net_effect=excluded.net_effect,
                source_kind=excluded.source_kind,
                dedupe_key=excluded.dedupe_key
            """,
            (
                memory_id,
                as_of,
                date,
                title,
                summary,
                story,
                story_family,
                story_thesis,
                story_checkpoint,
                category,
                region,
                importance,
                entry_mode,
                event_kind,
                json_list(subjects),
                json_list(industries),
                json_list(tickers),
                json_list(tags),
                json_list(sources),
                state_key,
                state_label,
                parent_story,
                story_relation,
                net_effect,
                source_kind,
                dedupe_key,
                created_at,
            ),
        )
        result = {
            "id": memory_id,
            "asOf": as_of,
            "date": date,
            "title": title,
            "summary": summary,
            "story": story,
            "storyFamily": story_family,
            "storyThesis": story_thesis,
            "storyCheckpoint": story_checkpoint,
            "stateKey": state_key,
            "stateLabel": state_label,
            "parentStory": parent_story,
            "storyRelation": story_relation,
            "category": category,
            "region": region,
            "importance": importance,
            "entryMode": entry_mode,
            "eventKind": event_kind,
            "netEffect": net_effect,
            "sourceKind": source_kind,
            "subjects": subjects,
            "industries": industries,
            "tickers": tickers,
            "tags": tags,
            "sources": sources,
            "dedupeKey": dedupe_key,
        }
        update_taxonomy(conn, result, observed_at)
        upsert_story_link(conn, story, parent_story, story_relation, 0.72, story_thesis or summary, observed_at)
        if story_relation == "branches_from":
            story_axis = display_memory_axis(story, tags + industries, f"{title} {summary} {story_thesis} {story_checkpoint}")
            parent_axis = display_memory_axis(parent_story, tags + industries, f"{title} {summary} {story_thesis} {story_checkpoint}")
            shared_items = [
                display_label(item)
                for item in (tags + industries)[:6]
                if item and slug(item) not in _SUGGESTION_TAG_DENYLIST
            ]
            shared_scope = ", ".join(shared_items[:4]) or "가격 반응, 실적 기대, 수급 변화"
            upsert_family_suggestion(
                conn,
                story,
                parent_story,
                (
                    f"{story_axis} 이슈가 {parent_axis} 흐름과 같은 원인→영향 고리로 움직이는 것으로 보입니다 "
                    f"(겹치는 주제: {shared_scope})."
                ),
                observed_at,
            )
    result = {
        "id": memory_id,
        "asOf": as_of,
        "date": date,
        "title": title,
        "summary": summary,
        "story": story,
        "storyFamily": story_family,
        "storyThesis": story_thesis,
        "storyCheckpoint": story_checkpoint,
        "stateKey": state_key,
        "stateLabel": state_label,
        "parentStory": parent_story,
        "storyRelation": story_relation,
        "category": category,
        "region": region,
        "importance": importance,
        "entryMode": entry_mode,
        "eventKind": event_kind,
        "netEffect": net_effect,
        "sourceKind": source_kind,
        "subjects": subjects,
        "industries": industries,
        "tickers": tickers,
        "tags": tags,
        "sources": sources,
        "dedupeKey": dedupe_key,
    }
    try:
        if should_derive_state(conn, result):
            result["state"] = upsert_state_from_memory(conn, result, observed_at)
        if owns_connection:
            conn.commit()
        return result
    except sqlite3.Error:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def upsert_state_from_memory(conn: sqlite3.Connection, memory: dict, observed_at: str | None = None) -> dict:
    import hashlib

    memory = apply_canonical_state(memory)
    story = normalize(memory.get("story", "market"))
    status = normalize_choice(memory.get("stateStatus", ""), STATE_STATUS_CHOICES, "active" if memory.get("importance") == "high" else "watch")
    bias = normalize_choice(memory.get("stateBias", ""), STATE_BIAS_CHOICES, infer_bias(f"{memory.get('title', '')} {memory.get('summary', '')}"))
    state_key = normalize(memory.get("stateKey", "") or story)
    state_id = hashlib.sha256(f"{state_key}:{memory.get('date', '')}".encode("utf-8")).hexdigest()[:16]
    updated_at = observed_at or dt.datetime.now(dt.timezone.utc).isoformat()
    label = display_label(memory.get("stateLabel", "") or memory.get("storyFamily") or memory.get("title") or state_key)
    rationale = dedupe_sentences(memory.get("storyThesis", ""), 700) or dedupe_sentences(memory.get("summary", ""), 280)
    state = {
        "id": state_id,
        "stateKey": state_key,
        "stateLabel": label,
        "story": story,
        "storyFamily": normalize(memory.get("storyFamily", "")),
        "status": status,
        "bias": bias,
        "category": memory.get("category", "stock_bond"),
        "region": memory.get("region", "GLOBAL"),
        "importance": memory.get("importance", "medium"),
        "netEffect": normalize(memory.get("netEffect", "") or infer_net_effect(memory.get("category", "stock_bond"), bias, memory.get("tags", []))),
        "summary": dedupe_sentences(memory.get("summary", ""), 420),
        "rationale": rationale,
        "confidence": float(memory.get("confidence", 0.55) or 0.55),
        "effectiveFrom": memory.get("asOf", updated_at),
        "effectiveTo": normalize(memory.get("effectiveTo", "")),
        "sourceMemoryId": memory.get("id", ""),
        "updatedAt": updated_at,
    }
    with nullcontext():
        inherited_checkpoints = "[]"
        if status in {"active", "watch"}:
            # **체크포인트는 계보(state_key)의 소유물이다.** state_id는 날짜별로 회전해
            # 새 행이 빈 목록으로 태어나는데, 승계 없이 어제 행을 overridden으로 밀면
            # 판정 status·이력이 판정 pass가 다시는 방문하지 않는 행에 고립되고 같은
            # 체크포인트가 매일 open으로 다시 태어난다(2026-08-30 리뷰). 밀려나는 행의
            # 목록을 새 행이 물려받는다 — 템플릿 문장은 refresh가 어차피 다시 만든다.
            prior = conn.execute(
                """
                SELECT next_checkpoints_json FROM market_narrative_states
                WHERE state_key = ? AND status IN ('active', 'watch') AND state_id != ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (state_key, state_id),
            ).fetchone()
            if prior and prior["next_checkpoints_json"]:
                inherited_checkpoints = prior["next_checkpoints_json"]
            conn.execute(
                """
                UPDATE market_narrative_states
                SET status = 'overridden', effective_to = ?, updated_at = ?
                WHERE state_key = ? AND status IN ('active', 'watch') AND state_id != ?
                """,
                (state["effectiveFrom"], updated_at, state_key, state_id),
            )
        # confidence는 ON CONFLICT UPDATE 목록에 넣지 않는다. 이 경로가 넘기는 값은
        # 항상 기본값(0.55)이라, 같은 날 같은 state_key로 다시 저장하면
        # refresh_regime_state()가 근거로 계산해 넣은 값이 기본값으로 되돌아간다.
        # momentum·evidence_count_*·last_confirmed_at을 건드리지 않는 것과 같은 이유다.
        # next_checkpoints_json도 UPDATE 목록에 없다 — 같은 날 재저장이 판정 결과가
        # 실린 목록을 승계본으로 되돌리면 안 된다(INSERT 시에만 승계가 적용된다).
        conn.execute(
            """
            INSERT INTO market_narrative_states (
                state_id, state_key, state_label, story, story_family, status, bias,
                category, region, importance, net_effect, summary, rationale, confidence,
                effective_from, effective_to, source_memory_id, updated_at,
                next_checkpoints_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(state_id) DO UPDATE SET
                state_label=excluded.state_label,
                story=excluded.story,
                story_family=excluded.story_family,
                status=excluded.status,
                bias=excluded.bias,
                category=excluded.category,
                region=excluded.region,
                importance=excluded.importance,
                net_effect=excluded.net_effect,
                summary=excluded.summary,
                rationale=excluded.rationale,
                effective_from=excluded.effective_from,
                effective_to=excluded.effective_to,
                source_memory_id=excluded.source_memory_id,
                updated_at=excluded.updated_at
            """,
            (
                state["id"],
                state["stateKey"],
                state["stateLabel"],
                state["story"],
                state["storyFamily"],
                state["status"],
                state["bias"],
                state["category"],
                state["region"],
                state["importance"],
                state["netEffect"],
                state["summary"],
                state["rationale"],
                state["confidence"],
                state["effectiveFrom"],
                state["effectiveTo"],
                state["sourceMemoryId"],
                state["updatedAt"],
                inherited_checkpoints,
            ),
        )
    return state


def list_memory(db_path: str | Path, limit: int = 50, story: str = "") -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = connect(path)
    init_db(conn)
    params: list = []
    where = ""
    if story:
        where = "WHERE story = ?"
        params.append(story)
    rows = conn.execute(
        f"""
        SELECT * FROM market_memory
        {where}
        ORDER BY date DESC, as_of DESC
        LIMIT ?
        """,
        (*params, int(limit or 50)),
    ).fetchall()
    out = []
    for row in rows:
        tags = parse_json_list(row["tags_json"])
        axis_label = display_memory_axis(row, tags)
        summary = display_summary(axis_label, row["summary"], row["category"], row["event_kind"], row["story_thesis"])
        thesis = display_rationale(axis_label, row["story_thesis"], row["event_kind"])
        out.append({
            "id": row["memory_id"],
            "asOf": row["as_of"],
            "date": row["date"],
            "title": row["title"],
            "summary": summary,
            "story": row["story"],
            "storyFamily": axis_label,
            "storyThesis": thesis,
            "storyCheckpoint": dedupe_sentences(row["story_checkpoint"], 400),
            "stateKey": row["state_key"],
            "stateLabel": display_memory_axis(row["state_label"] or axis_label, tags, f"{row['summary']} {row['story_thesis']}"),
            "parentStory": row["parent_story"],
            "storyRelation": row["story_relation"],
            "category": row["category"],
            "region": row["region"],
            "importance": row["importance"],
            "entryMode": row["entry_mode"],
            "eventKind": row["event_kind"],
            "netEffect": row["net_effect"],
            "sourceKind": row["source_kind"],
            "subjects": parse_json_list(row["subjects_json"]),
            "industries": parse_json_list(row["industries_json"]),
            "tickers": parse_json_list(row["tickers_json"]),
            "tags": tags,
            "tagExplanations": tag_scope_explanations(row["story_family"] or row["story"], tags, summary, thesis),
            "sources": parse_json_list(row["sources_json"]),
            "dedupeKey": row["dedupe_key"],
        })
    return out


def list_briefing_memories(db_path: str | Path, limit: int = 12) -> list[dict]:
    """브리핑 LLM 컨텍스트용 메모리 선택.

    active → watch → 기타 순, 같은 상태 안에서는 high → medium → low 중요도,
    그 안에서는 최신순으로 정렬한다.
    """
    raw = list_memory(db_path, limit=max(limit * 3, 36))
    if not raw:
        return raw
    path = Path(db_path)
    try:
        conn = connect(path)
        status_map: dict[str, str] = {
            row["state_key"]: row["status"]
            for row in conn.execute("SELECT state_key, status FROM market_narrative_states").fetchall()
        }
    except Exception:
        status_map = {}
    _status_rank = {"active": 0, "watch": 1, "resolved": 3, "overridden": 3}
    _imp_rank = {"high": 0, "medium": 1, "low": 2}
    # 먼저 날짜 내림차순으로 안정 정렬한 뒤, (상태, 중요도) 기준으로 재정렬
    raw.sort(key=lambda m: m.get("date", ""), reverse=True)
    raw.sort(key=lambda m: (
        _status_rank.get(status_map.get(m.get("stateKey", ""), ""), 2),
        _imp_rank.get(m.get("importance", ""), 2),
    ))
    return raw[:limit]


def delete_memory(db_path: str | Path, memory_id: str) -> dict:
    path = Path(db_path)
    if not path.exists():
        return {"deleted": False, "error": "Market memory DB not found"}
    memory_id = normalize(memory_id)
    if not memory_id:
        return {"deleted": False, "error": "Invalid memory id"}
    conn = connect(path)
    init_db(conn)
    row = conn.execute("SELECT state_key FROM market_memory WHERE memory_id = ?", (memory_id,)).fetchone()
    if not row:
        return {"deleted": False, "error": "Memory entry not found"}
    state_key = row["state_key"]
    with conn:
        conn.execute("DELETE FROM market_memory WHERE memory_id = ?", (memory_id,))
        conn.execute(
            """
            UPDATE market_narrative_states
            SET status = 'overridden',
                effective_to = ?,
                updated_at = ?
            WHERE source_memory_id = ? AND status IN ('active', 'watch')
            """,
            (dt.datetime.now(dt.timezone.utc).isoformat(), dt.datetime.now(dt.timezone.utc).isoformat(), memory_id),
        )
    return {"deleted": True, "id": memory_id, "stateKey": state_key}


def list_states(db_path: str | Path, limit: int = 50, status: str = "active") -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = connect(path)
    init_db(conn)
    params: list = []
    where = ""
    if status == "current":
        where = "WHERE status IN ('active', 'watch')"
    elif status and status != "all":
        where = "WHERE status = ?"
        params.append(status)
    rows = conn.execute(
        f"""
        SELECT * FROM market_narrative_states
        {where}
        ORDER BY importance = 'high' DESC, effective_from DESC, updated_at DESC
        LIMIT ?
        """,
        (*params, int(limit or 50)),
    ).fetchall()
    out = []
    for row in rows:
        axis_label = display_memory_axis(row["state_label"] or row["story_family"] or row["story"], [], f"{row['summary']} {row['rationale']} {row['net_effect']}")
        summary = display_summary(axis_label, row["summary"], row["category"], "", row["rationale"])
        rationale = display_rationale(axis_label, row["rationale"])
        linked_theses = conn.execute(
            """
            SELECT ticker, thesis_ticker, relationship, strength, method
            FROM market_regime_thesis_links
            WHERE state_id = ?
            ORDER BY strength DESC, ticker ASC
            """,
            (row["state_id"],),
        ).fetchall()
        linked_tickers = sorted({link["ticker"] or link["thesis_ticker"] for link in linked_theses if (link["ticker"] or link["thesis_ticker"])})
        # thesis 링크가 없어도 "연결기업"이 비지 않도록, 이 상태의 근거(evidence)에 등장하는
        # 기업을 빈도순으로 보충한다. memory의 tickers_json은 앞쪽이 주 대상 기업이므로
        # 앞 3개만 집계해 일괄 추출 노이즈 티커를 억제한다.
        ticker_counts: dict[str, int] = {}
        for ev in conn.execute(
            """
            SELECT m.tickers_json
            FROM market_regime_evidence e
            JOIN market_memory m ON m.memory_id = e.memory_id
            WHERE e.state_id = ?
            ORDER BY e.score DESC, e.evidence_date DESC
            LIMIT 40
            """,
            (row["state_id"],),
        ).fetchall():
            for ticker in parse_json_list(ev["tickers_json"])[:3]:
                ticker = str(ticker).strip().upper()
                if ticker:
                    ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        evidence_tickers = [t for t, _ in sorted(ticker_counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        linked_companies = list(dict.fromkeys(linked_tickers + evidence_tickers))[:6]
        out.append({
            "id": row["state_id"],
            "stateKey": row["state_key"],
            "stateLabel": axis_label,
            "story": row["story"],
            "storyFamily": display_memory_axis(row["story_family"] or axis_label, [], f"{row['summary']} {row['rationale']} {row['net_effect']}"),
            "status": row["status"],
            "bias": row["bias"],
            "category": row["category"],
            "region": row["region"],
            "importance": row["importance"],
            "netEffect": row["net_effect"],
            "summary": summary,
            "conclusion": state_conclusion(
                row["state_label"] or row["story_family"] or row["story"],
                row["bias"],
                row["net_effect"],
                row["summary"],
                row["rationale"],
            ),
            "rationale": rationale,
            "tagExplanations": tag_scope_explanations(row["state_label"] or row["story_family"] or row["story"], [], summary, rationale),
            "confidence": row["confidence"],
            "momentum": row["momentum"],
            "evidenceCount7d": row["evidence_count_7d"],
            "evidenceCount30d": row["evidence_count_30d"],
            "evidenceCount90d": row["evidence_count_90d"],
            "lastConfirmedAt": row["last_confirmed_at"],
            "lastChallengedAt": row["last_challenged_at"],
            "falsificationTriggers": parse_json_list(row["falsification_triggers_json"]),
            "nextCheckpoints": parse_json_list(row["next_checkpoints_json"]),
            "linkedCompanies": linked_companies,
            "linkedTheses": [dict(link) for link in linked_theses],
            "effectiveFrom": row["effective_from"],
            "effectiveTo": row["effective_to"],
            "sourceMemoryId": row["source_memory_id"],
            "updatedAt": row["updated_at"],
        })
    conn.close()
    return out


def list_taxonomy(db_path: str | Path, term_type: str = "", limit: int = 50) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = connect(path)
    init_db(conn)
    params: list = []
    where = ""
    if term_type:
        where = "WHERE term_type = ?"
        params.append(term_type)
    rows = conn.execute(
        f"""
        SELECT * FROM market_memory_taxonomy
        {where}
        ORDER BY count DESC, last_seen DESC
        LIMIT ?
        """,
        (*params, int(limit or 50)),
    ).fetchall()
    return [
        {
            "type": row["term_type"],
            "key": row["term_key"],
            "label": display_label(row["label"] or row["term_key"]),
            "count": row["count"],
            "firstSeen": row["first_seen"],
            "lastSeen": row["last_seen"],
        }
        for row in rows
    ]


def list_story_links(db_path: str | Path, story: str = "", limit: int = 50) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = connect(path)
    init_db(conn)
    params: list = []
    where = ""
    if story:
        where = "WHERE from_story = ? OR to_story = ?"
        key = slug(story)
        params.extend([key, key])
    rows = conn.execute(
        f"""
        SELECT * FROM market_story_links
        {where}
        ORDER BY strength DESC, updated_at DESC
        LIMIT ?
        """,
        (*params, int(limit or 50)),
    ).fetchall()
    return [
        {
            "id": row["link_id"],
            "fromStory": row["from_story"],
            "toStory": row["to_story"],
            "fromLabel": display_label(row["from_story"]),
            "toLabel": display_label(row["to_story"]),
            "relation": row["relation"],
            "strength": row["strength"],
            "evidence": display_rationale(row["from_story"], row["evidence"]),
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def list_family_suggestions(db_path: str | Path, status: str = "suggested", limit: int = 50) -> list[dict]:
    path = Path(db_path)
    if not path.exists():
        return []
    conn = connect(path)
    init_db(conn)
    params: list = []
    where = ""
    if status and status != "all":
        where = "WHERE status = ?"
        params.append(status)
    rows = conn.execute(
        f"""
        SELECT * FROM market_story_family_suggestions
        {where}
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (*params, int(limit or 50)),
    ).fetchall()
    suggestions = []
    for row in rows:
        context = family_suggestion_context(conn, row["story"], row["suggested_family"], row["reason"])
        suggestions.append(
            {
                "id": row["suggestion_id"],
                "story": row["story"],
                "storyLabel": context["storyLabel"],
                "suggestedFamily": row["suggested_family"],
                "suggestedFamilyLabel": context["familyLabel"],
                "reason": context["reason"],
                "sharedTags": context["sharedTags"],
                "evidenceSources": context["evidenceSources"],
                "tagExplanations": context["tagExplanations"],
                "status": row["status"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
        )
    return suggestions


def story_map(db_path: str | Path, limit: int = 80) -> dict:
    path = Path(db_path)
    if not path.exists():
        return {"nodes": [], "links": []}
    conn = connect(path)
    init_db(conn)
    memory_counts = {
        row["story"]: row["cnt"]
        for row in conn.execute(
            "SELECT story, COUNT(*) AS cnt FROM market_memory GROUP BY story ORDER BY cnt DESC LIMIT ?",
            (int(limit or 80),),
        ).fetchall()
    }
    links = list_story_links(path, limit=limit)
    node_keys = set(memory_counts)
    for link in links:
        node_keys.add(link["fromStory"])
        node_keys.add(link["toStory"])
    nodes = [
        {
            "key": key,
            "label": display_label(key),
            "count": int(memory_counts.get(key, 0)),
        }
        for key in sorted(node_keys, key=lambda item: (-memory_counts.get(item, 0), display_label(item)))
    ]
    return {"nodes": nodes, "links": links}


def memory_report(db_path: str | Path, limit: int = 8) -> dict:
    states = list_states(db_path, limit=limit, status="current")
    rows = []
    for state in states:
        rows.append(
            {
                "title": state.get("stateLabel", ""),
                "status": state.get("status", ""),
                "bias": state.get("bias", ""),
                "importance": state.get("importance", ""),
                "summary": state.get("summary", ""),
                "checkpoint": state.get("rationale", ""),
            }
        )
    if not rows:
        return {
            "title": "시장 내러티브 리포트",
            "summary": "현재 활성화된 시장 내러티브 상태가 없습니다. 브리핑을 생성하면 반복 이슈가 누적됩니다.",
            "items": [],
        }
    top = ", ".join(item["title"] for item in rows[:3] if item["title"])
    return {
        "title": "시장 내러티브 리포트",
        "summary": f"현재 추적 중인 핵심 내러티브는 {top}입니다. 각 이슈는 단일 기사보다 반복성, 가격 반응, 실적 기대와의 연결성을 기준으로 관리됩니다.",
        "items": rows,
    }


def audit_memory(db_path: str | Path, days: int = 30) -> dict:
    path = Path(db_path)
    if not path.exists():
        return {"status": "warn", "checks": [], "summary": "시장 내러티브 DB가 아직 없습니다."}
    conn = connect(path)
    try:
        init_db(conn)
        today = dt.datetime.now(dt.timezone.utc).date()
        recent_start = (today - dt.timedelta(days=max(1, int(days or 30)))).isoformat()

        def scalar(sql: str, params: tuple = ()) -> int:
            row = conn.execute(sql, params).fetchone()
            return int(row[0] or 0) if row else 0

        total = scalar("SELECT COUNT(*) FROM market_memory")
        recent = scalar("SELECT COUNT(*) FROM market_memory WHERE date >= ?", (recent_start,))
        blank_summary = scalar("SELECT COUNT(*) FROM market_memory WHERE TRIM(summary) = ''")
        blank_story = scalar("SELECT COUNT(*) FROM market_memory WHERE TRIM(story) = '' OR TRIM(story_family) = ''")
        dedupe_missing = scalar("SELECT COUNT(*) FROM market_memory WHERE TRIM(dedupe_key) = ''")
        current_states = scalar("SELECT COUNT(*) FROM market_narrative_states WHERE status IN ('active','watch')")
        stale_states = scalar(
            """
            SELECT COUNT(*)
            FROM market_narrative_states
            WHERE status IN ('active','watch') AND substr(effective_from, 1, 10) < ?
            """,
            ((today - dt.timedelta(days=45)).isoformat(),),
        )
        taxonomy_terms = scalar("SELECT COUNT(*) FROM market_memory_taxonomy")
        story_links_count = scalar("SELECT COUNT(*) FROM market_story_links")
        suggestions = scalar("SELECT COUNT(*) FROM market_story_family_suggestions WHERE status = 'suggested'")

        duplicate_rows = conn.execute(
            """
            SELECT dedupe_key, COUNT(*) AS cnt
            FROM market_memory
            WHERE TRIM(dedupe_key) <> ''
            GROUP BY dedupe_key
            HAVING cnt > 1
            """
        ).fetchall()
        duplicate_count = sum(int(row["cnt"]) - 1 for row in duplicate_rows)

        checks = [
            {"check": "총 메모리", "status": "pass" if total > 0 else "warn", "value": total, "detail": "누적된 시장 내러티브 엔트리 수"},
            {"check": "최근 엔트리", "status": "pass" if recent > 0 else "warn", "value": recent, "detail": f"최근 {days}일 동안 생성된 엔트리"},
            {"check": "빈 요약", "status": "pass" if blank_summary == 0 else "warn", "value": blank_summary, "detail": "summary가 비어 있는 엔트리"},
            {"check": "빈 스토리", "status": "pass" if blank_story == 0 else "warn", "value": blank_story, "detail": "story/story_family가 비어 있는 엔트리"},
            {"check": "Dedupe 누락", "status": "pass" if dedupe_missing == 0 else "warn", "value": dedupe_missing, "detail": "dedupe_key가 없는 엔트리"},
            {"check": "중복 Dedupe", "status": "pass" if duplicate_count == 0 else "warn", "value": duplicate_count, "detail": "같은 dedupe_key로 중복된 엔트리"},
            {"check": "현재 상태", "status": "pass" if current_states <= 12 else "warn", "value": current_states, "detail": "active/watch 상태가 너무 많으면 기억이 흐려집니다"},
            {"check": "오래된 상태", "status": "pass" if stale_states == 0 else "warn", "value": stale_states, "detail": "45일 이상 갱신되지 않은 active/watch 상태"},
            {"check": "Taxonomy", "status": "pass" if taxonomy_terms <= max(40, total * 8) else "warn", "value": taxonomy_terms, "detail": "분류어가 과도하게 늘어나는지 확인"},
            {"check": "Story links", "status": "pass" if story_links_count > 0 or total == 0 else "warn", "value": story_links_count, "detail": "스토리 간 관계 링크 수"},
            {"check": "Family review", "status": "pass" if suggestions <= 20 else "warn", "value": suggestions, "detail": "검토 대기 중인 패밀리 제안"},
        ]
        warn_count = sum(1 for item in checks if item["status"] != "pass")
        return {
            "status": "pass" if warn_count == 0 else "warn",
            "warnCount": warn_count,
            "days": days,
            "summary": "시장 내러티브 DB 상태가 양호합니다." if warn_count == 0 else "시장 내러티브 DB에 점검이 필요한 항목이 있습니다.",
            "checks": checks,
        }
    finally:
        conn.close()


def update_state(db_path: str | Path, state_id: str, updates: dict) -> dict:
    path = Path(db_path)
    conn = connect(path)
    init_db(conn)
    row = conn.execute("SELECT * FROM market_narrative_states WHERE state_id = ?", (state_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "State not found"}
    status = normalize_choice(updates.get("status", row["status"]), STATE_STATUS_CHOICES, row["status"])
    bias = normalize_choice(updates.get("bias", row["bias"]), STATE_BIAS_CHOICES, row["bias"])
    importance = normalize_choice(updates.get("importance", row["importance"]), IMPORTANCE_CHOICES, row["importance"])
    effective_to = normalize(updates.get("effectiveTo") or updates.get("effective_to") or row["effective_to"])
    if status in {"resolved", "overridden"} and not effective_to:
        effective_to = dt.datetime.now(dt.timezone.utc).isoformat()
    updated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            UPDATE market_narrative_states
            SET status = ?, bias = ?, importance = ?, effective_to = ?, updated_at = ?
            WHERE state_id = ?
            """,
            (status, bias, importance, effective_to, updated_at, state_id),
        )
    return {"ok": True, "id": state_id, "status": status, "bias": bias, "importance": importance, "effectiveTo": effective_to}


def reconcile_state_aliases(db_path: str | Path) -> dict:
    """Collapse current active/watch states that are aliases of canonical themes."""
    path = Path(db_path)
    if not path.exists():
        return {"ok": False, "error": "Market memory DB not found"}
    conn = connect(path)
    init_db(conn)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    memory_updates = 0
    state_updates = 0
    overridden = 0
    with conn:
        for row in conn.execute(
            """
            SELECT memory_id, title, summary, story, story_family, state_key, state_label,
                   story_thesis, tags_json, industries_json, tickers_json
            FROM market_memory
            """
        ).fetchall():
            canonical = canonical_state_for(
                row["state_key"],
                row["state_label"],
                row["story_family"],
                row["story"],
                _state_blob(
                    row["title"],
                    row["summary"],
                    row["story_thesis"],
                    parse_json_list(row["tags_json"]),
                    parse_json_list(row["industries_json"]),
                    parse_json_list(row["tickers_json"]),
                ),
            )
            if not canonical or slug(canonical["stateKey"]) == slug(row["state_key"]):
                continue
            relation = "branches_from" if slug(row["story"]) != slug(canonical["stateKey"]) else "same_family"
            conn.execute(
                """
                UPDATE market_memory
                SET state_key=?, state_label=?, story_family=?, parent_story=?, story_relation=?
                WHERE memory_id=?
                """,
                (canonical["stateKey"], canonical["stateLabel"], canonical["storyFamily"], canonical["parentStory"], relation, row["memory_id"]),
            )
            memory_updates += 1

        rows = conn.execute(
            """
            SELECT *
            FROM market_narrative_states
            WHERE status IN ('active','watch')
            ORDER BY importance='high' DESC, status='active' DESC, effective_from DESC, updated_at DESC
            """
        ).fetchall()
        for row in rows:
            canonical = canonical_state_for(
                row["state_key"],
                row["state_label"],
                row["story_family"],
                row["story"],
                _state_blob(row["summary"], row["rationale"], row["net_effect"]),
            )
            if not canonical:
                continue
            if slug(canonical["stateKey"]) != slug(row["state_key"]) or row["state_label"] != canonical["stateLabel"] or row["story_family"] != canonical["storyFamily"]:
                conn.execute(
                    """
                    UPDATE market_narrative_states
                    SET state_key=?, state_label=?, story_family=?, updated_at=?
                    WHERE state_id=?
                    """,
                    (canonical["stateKey"], canonical["stateLabel"], canonical["storyFamily"], now, row["state_id"]),
                )
                state_updates += 1

        rows = conn.execute(
            """
            SELECT state_id, state_key, status, importance, effective_from, updated_at
            FROM market_narrative_states
            WHERE status IN ('active','watch')
            ORDER BY state_key ASC, status='active' DESC, importance='high' DESC, effective_from DESC, updated_at DESC
            """
        ).fetchall()
        keep_by_key: dict[str, str] = {}
        effective_by_id = {row["state_id"]: row["effective_from"] for row in rows}
        for row in rows:
            key = row["state_key"]
            if key not in keep_by_key:
                keep_by_key[key] = row["state_id"]
                continue
            keep_id = keep_by_key[key]
            conn.execute(
                """
                UPDATE market_narrative_states
                SET status='overridden', effective_to=?, updated_at=?
                WHERE state_id=?
                """,
                (effective_by_id.get(keep_id) or now, now, row["state_id"]),
            )
            overridden += 1
    conn.close()
    return {
        "ok": True,
        "memoryUpdates": memory_updates,
        "stateUpdates": state_updates,
        "overridden": overridden,
    }


def review_family_suggestion(db_path: str | Path, suggestion_id: str, action: str) -> dict:
    path = Path(db_path)
    conn = connect(path)
    init_db(conn)
    row = conn.execute("SELECT * FROM market_story_family_suggestions WHERE suggestion_id = ?", (suggestion_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "Suggestion not found"}
    status = "accepted" if action == "accept" else "rejected"
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with conn:
        conn.execute(
            "UPDATE market_story_family_suggestions SET status = ?, updated_at = ? WHERE suggestion_id = ?",
            (status, now, suggestion_id),
        )
        if status == "accepted":
            upsert_story_link(conn, row["story"], row["suggested_family"], "same_family", 0.86, row["reason"])
    return {"ok": True, "id": suggestion_id, "status": status}


def build_memory_from_briefing(briefing: dict, groups: list[dict]) -> list[dict]:
    date = str(briefing.get("date", ""))[:10]
    entries = []
    for group in groups[:4]:
        subject = group.get("company") or group.get("sector") or "시장"
        docs = group.get("docs", [])[:8]
        rough_tickers = []
        for doc in docs:
            for company in doc.get("companies", []) or []:
                ticker = company.get("ticker", "")
                if ticker and ticker not in rough_tickers:
                    rough_tickers.append(ticker)
        relevant_docs = [doc for doc in docs if doc_matches_subject(doc, subject, rough_tickers)]
        if len(relevant_docs) >= 2:
            docs = relevant_docs
        tags = []
        sources = []
        subjects = []
        industries = []
        tickers = []
        for doc in docs[:6]:
            for tag in doc.get("sectors", []) + doc.get("impactTags", []):
                if tag and tag not in tags:
                    tags.append(tag)
            for sector in doc.get("sectors", []):
                if sector and sector not in industries:
                    industries.append(sector)
            for company in doc.get("companies", []):
                name = company.get("name", "")
                ticker = company.get("ticker", "")
                if name and {"name": name, "type": "company"} not in subjects:
                    subjects.append({"name": name, "type": "company"})
                if ticker and ticker not in tickers:
                    tickers.append(ticker)
            sources.append({
                "title": doc.get("title", ""),
                "source": doc.get("source", ""),
                "date": doc.get("date", ""),
                "url": doc.get("url", ""),
            })
        route = story_route(subject, docs, tags, industries, tickers)
        subject_label = route["stateLabel"]
        preliminary_text = f"{subject} {' '.join(doc.get('title', '') for doc in docs[:4])} {' '.join(tags)}"
        event_kind = detect_event_kind(preliminary_text)
        summary = narrative_summary(subject, docs, tags, event_kind)
        if not summary:
            continue
        text = f"{subject} {summary}"
        category = detect_category(text, tags)
        region = detect_region(sources, text)
        importance = detect_importance(text, tags, len(sources))
        event_kind = detect_event_kind(text)
        bias = infer_bias(text)
        thesis = route.get("storyThesis") or narrative_thesis(subject, event_kind, bias, tags)
        subj_display = display_label(subject)
        event_label_short = EVENT_KIND_LABELS.get(event_kind, "관찰")
        title = f"{subj_display} {event_label_short} 이슈"
        entry_mode = "issue" if importance == "high" or (importance == "medium" and len(sources) >= 2) else "brief"
        checkpoint = make_checkpoint(event_kind, subject, tags, docs, bias)
        entries.append({
            "date": date,
            "asOf": briefing.get("generatedAt", ""),
            "title": title,
            "summary": summary,
            "story": route["story"],
            "storyFamily": route["storyFamily"],
            "storyThesis": thesis,
            "storyCheckpoint": checkpoint,
            "stateKey": route["stateKey"],
            "stateLabel": route["stateLabel"],
            "parentStory": route["parentStory"],
            "storyRelation": route["relation"],
            "stateBias": bias,
            "category": category,
            "region": region,
            "importance": importance,
            "entryMode": entry_mode,
            "eventKind": event_kind,
            "subjects": subjects[:8],
            "industries": industries[:8],
            "tickers": tickers[:8],
            "tags": tags[:10],
            "sources": sources,
        })
    return entries





