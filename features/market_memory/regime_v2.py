"""Regime tracking v2 for market narrative states.

This module extends the existing market-memory knowledge graph without changing
canonical briefing/report markdown. It classifies existing narrative memories as
supporting/challenging/neutral evidence for a state, computes rolling evidence
windows, and updates code-validated market-phase momentum.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

from features.common.research_schema.tracked_checkpoints import merge_with_templates
from features.common.taxonomy import canonical_tag
from features.market_memory.memory import connect, init_db, normalize, parse_json_list

MOMENTUM_CHOICES = {"strengthening", "stable", "fading", "turning", "conflicted"}
MOMENTUM_DEFAULT = "stable"
EVIDENCE_ROLE_CHOICES = {"supporting", "challenging", "neutral"}
EVIDENCE_ROLE_DEFAULT = "neutral"

POSITIVE_TERMS = {
    "accelerate", "beat", "boost", "expand", "gain", "growth", "improve", "increase",
    "raise", "recover", "resilient", "strong", "surge", "upside",
    "강세", "개선", "반등", "상승", "상향", "서프라이즈", "성장", "수혜", "증가", "호조", "회복", "확대",
}
NEGATIVE_TERMS = {
    "concern", "cut", "decline", "delay", "disappoint", "downside", "drop", "fall",
    "miss", "pressure", "risk", "slow", "slowdown", "weak", "weaken",
    "감소", "둔화", "리스크", "부담", "악화", "약세", "우려", "위험", "하락", "하향", "훼손",
}
STOPWORDS = {
    "and", "the", "for", "with", "from", "this", "that", "market", "markets", "stock",
    "stocks", "share", "shares", "news", "report", "brief", "시장", "증시", "주식", "관련", "자료",
}
SOURCE_QUALITY = {
    "filings": 0.95,
    "filing": 0.95,
    "sec": 0.95,
    "reports": 0.85,
    "report": 0.85,
    "articles": 0.72,
    "article": 0.72,
    "rss": 0.68,
    "briefing": 0.58,
    "llm": 0.45,
    "auto": 0.45,
}


def normalize_momentum(value, default: str = MOMENTUM_DEFAULT) -> str:
    value = str(value or "").strip().lower()
    return value if value in MOMENTUM_CHOICES else default


def normalize_evidence_role(value, default: str = EVIDENCE_ROLE_DEFAULT) -> str:
    value = str(value or "").strip().lower()
    return value if value in EVIDENCE_ROLE_CHOICES else default


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _parse_date(value) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc)
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _age_days(value, as_of=None) -> int:
    event_at = _parse_date(value)
    anchor = _parse_date(as_of) or dt.datetime.now(dt.timezone.utc)
    if not event_at:
        return 9999
    return max(0, int((anchor - event_at).total_seconds() // 86400))


def stale_penalty(age_days: int) -> float:
    if age_days <= 30:
        return 0.0
    if age_days <= 90:
        return 0.12
    if age_days <= 180:
        return 0.24
    return 0.35


def _tokens(value: str) -> set[str]:
    out = set()
    for token in re.findall(r"[A-Za-z0-9가-힣]{2,}", str(value or "").lower()):
        if token not in STOPWORDS and len(token) >= 2:
            out.add(token)
    return out


def _json_list(value) -> list:
    if isinstance(value, str):
        return parse_json_list(value)
    return value if isinstance(value, list) else []


def classify_evidence(text: str, state: dict) -> str:
    """Classify text as supporting/challenging/neutral for the state.

    A bearish state is supported by negative evidence; a bullish state is
    supported by positive evidence. Mixed/neutral states require one side to be
    clearly dominant, otherwise remain neutral.
    """
    lower = str(text or "").lower()
    positive = sum(1 for term in POSITIVE_TERMS if term.lower() in lower)
    negative = sum(1 for term in NEGATIVE_TERMS if term.lower() in lower)
    bias = str(state.get("bias") or "").lower()
    net_effect = str(state.get("net_effect") or state.get("netEffect") or "").lower()
    if bias == "bearish" or any(word in net_effect for word in ("risk", "tighten", "pressure", "부담", "위험")):
        support, challenge = negative, positive
    elif bias == "bullish" or any(word in net_effect for word in ("benefit", "tailwind", "수혜", "완화")):
        support, challenge = positive, negative
    else:
        support, challenge = max(positive, negative), min(positive, negative)
    if support == 0 and challenge == 0:
        return "neutral"
    if support >= challenge + 1:
        return "supporting"
    if challenge >= support + 1:
        return "challenging"
    return "neutral"


def evidence_score(memory: dict, role: str, *, as_of=None, matched_terms=None) -> float:
    role = normalize_evidence_role(role)
    age = _age_days(memory.get("date") or memory.get("as_of"), as_of=as_of)
    source_kind = str(memory.get("source_kind") or memory.get("sourceKind") or "").lower()
    sources = _json_list(memory.get("sources_json") or memory.get("sources"))
    source_quality = SOURCE_QUALITY.get(source_kind, 0.62)
    if sources:
        source_quality = max(source_quality, min(0.9, 0.55 + len(sources) * 0.08))
    importance_boost = {"high": 0.12, "medium": 0.05, "low": 0.0}.get(str(memory.get("importance") or ""), 0.03)
    cross_confirm = min(0.16, max(0, len(sources) - 1) * 0.04)
    match_boost = min(0.12, len(matched_terms or []) * 0.03)
    role_penalty = 0.08 if role == "neutral" else 0.0
    score = source_quality + importance_boost + cross_confirm + match_boost - stale_penalty(age) - role_penalty
    return round(max(0.05, min(1.0, score)), 3)


def evidence_windows(evidence_rows: list[dict], *, as_of=None) -> dict:
    windows = {
        "evidenceCount7d": 0,
        "evidenceCount30d": 0,
        "evidenceCount90d": 0,
        "supporting30d": 0,
        "challenging30d": 0,
        "neutral30d": 0,
    }
    for item in evidence_rows:
        age = _age_days(item.get("evidenceDate") or item.get("evidence_date"), as_of=as_of)
        role = normalize_evidence_role(item.get("role"))
        if age <= 7:
            windows["evidenceCount7d"] += 1
        if age <= 30:
            windows["evidenceCount30d"] += 1
            windows[f"{role}30d"] += 1
        if age <= 90:
            windows["evidenceCount90d"] += 1
    return windows


def determine_momentum(evidence_rows: list[dict], *, as_of=None) -> str:
    recent = [row for row in evidence_rows if _age_days(row.get("evidenceDate") or row.get("evidence_date"), as_of=as_of) <= 30]
    support = sum(float(row.get("score") or 0) for row in recent if normalize_evidence_role(row.get("role")) == "supporting")
    challenge = sum(float(row.get("score") or 0) for row in recent if normalize_evidence_role(row.get("role")) == "challenging")
    neutral = sum(float(row.get("score") or 0) for row in recent if normalize_evidence_role(row.get("role")) == "neutral")
    total = support + challenge + neutral
    if total <= 0:
        has_old = any(_age_days(row.get("evidenceDate") or row.get("evidence_date"), as_of=as_of) <= 90 for row in evidence_rows)
        return "fading" if has_old else "stable"
    if support > 0 and challenge > 0 and min(support, challenge) / max(support, challenge) >= 0.45:
        return "conflicted"
    if support >= max(0.65, challenge * 1.4):
        return "strengthening"
    if challenge >= max(0.65, support * 1.4):
        old_support = sum(float(row.get("score") or 0) for row in evidence_rows if normalize_evidence_role(row.get("role")) == "supporting")
        return "turning" if old_support > challenge else "fading"
    return "stable"


def confidence_from_evidence(evidence_rows: list[dict], *, as_of=None) -> float:
    recent = [row for row in evidence_rows if _age_days(row.get("evidenceDate") or row.get("evidence_date"), as_of=as_of) <= 90]
    if not recent:
        return 0.35
    support = sum(float(row.get("score") or 0) for row in recent if normalize_evidence_role(row.get("role")) == "supporting")
    challenge = sum(float(row.get("score") or 0) for row in recent if normalize_evidence_role(row.get("role")) == "challenging")
    total = sum(float(row.get("score") or 0) for row in recent)
    # supporting/challenging 한쪽 쏠림 정도를 연속값으로 반영 (-0.14 ~ +0.14)
    # — 이진(+0.1/-0.05)으로 하면 근거가 많은 상태들이 전부 같은 confidence로 포화된다
    # 소표본 감쇠: 근거 2~3건의 쏠림이 수십 건짜리 상태보다 확신도가 높게 나오지 않도록
    consistency = ((max(support, challenge) / total) - 0.5) * 0.28 * min(1.0, len(recent) / 6) if total else 0.0
    freshness = 0.08 if any(_age_days(row.get("evidenceDate") or row.get("evidence_date"), as_of=as_of) <= 14 for row in recent) else -0.04
    value = 0.42 + min(0.32, math.sqrt(total) / 6) + consistency + freshness
    return round(max(0.15, min(0.95, value)), 2)


def regime_checkpoints(state: dict, evidence_rows: list[dict], momentum: str) -> list[str]:
    """Build concrete next checkpoints for a regime state.

    These are not evidence. They are monitoring prompts derived from the state
    label and recent supporting/challenging evidence balance.
    """
    label = state.get("state_label") or state.get("story_family") or state.get("story") or "시장 내러티브"
    top_support = next((r for r in evidence_rows if normalize_evidence_role(r.get("role")) == "supporting"), None)
    top_challenge = next((r for r in evidence_rows if normalize_evidence_role(r.get("role")) == "challenging"), None)
    points = [
        f"{label} 관련 가격 반응과 거래대금이 다음 자료 창에서도 같은 방향으로 이어지는지 확인",
        f"{label} 내러티브가 포트폴리오/관심 기업의 실적 기대 또는 수급으로 실제 전이되는지 확인",
    ]
    if top_support:
        points.append(f"강화 근거 '{top_support.get('title', '')}' 이후 같은 방향의 후속 뉴스가 반복되는지 확인")
    if top_challenge:
        points.append(f"반대 근거 '{top_challenge.get('title', '')}'가 일회성인지 추세 전환 신호인지 확인")
    if momentum in {"conflicted", "turning", "fading"}:
        points.append(f"momentum={momentum} 상태가 지속되면 기존 thesis 연결을 재검토")
    return [p for p in points if p][:5]


def regime_falsification_triggers(state: dict, momentum: str) -> list[str]:
    label = state.get("state_label") or state.get("story_family") or state.get("story") or "시장 내러티브"
    return [
        f"{label} 관련 supporting evidence가 30일 창에서 사라지고 challenging evidence가 우세해지는 경우",
        f"{label}가 설명하던 가격·수급 반응이 주요 지표와 반대로 움직이는 경우",
        f"momentum이 strengthening/stable에서 turning/fading으로 2회 이상 이동하는 경우",
    ][:3]


# 토픽 매칭에서 제외할 토큰 — 감성/방향 단어는 어느 내러티브에나 나와서
# "토큰 2개 겹침" 기준을 무의미하게 만든다 (모든 상태가 같은 근거를 갖게 되는 원인)
_MATCH_TOKEN_EXCLUDE = (
    STOPWORDS
    | {term.lower() for term in POSITIVE_TERMS}
    | {term.lower() for term in NEGATIVE_TERMS}
    | {"이슈", "흐름", "전망", "global", "kr", "us", "글로벌", "한국", "미국"}
)


def _state_tokens(state: dict) -> set[str]:
    raw = " ".join(str(state.get(k, "") or "") for k in ("state_key", "state_label", "story", "story_family", "summary", "rationale", "net_effect"))
    return _tokens(raw)


def _state_identity_tokens(state: dict) -> set[str]:
    """상태의 '주제'를 나타내는 토큰만 — state_key와 state_label로 한정한다.

    summary/rationale/net_effect는 LLM 생성 문구가 상태 간 중복되는 경우가 많고,
    story/story_family는 상태를 만든 memory에서 복사돼 다른 주제의 값이 섞일 수 있다
    (실데이터에서 금리 상태의 story에 ai_semiconductor_supply_chain이 들어간 사례).
    이런 필드를 매칭 기준으로 쓰면 모든 상태가 같은 근거를 공유하게 된다."""
    raw = " ".join(str(state.get(k, "") or "") for k in ("state_key", "state_label"))
    return _tokens(raw) - _MATCH_TOKEN_EXCLUDE


def _memory_tokens(memory: dict) -> set[str]:
    raw = " ".join(str(memory.get(k, "") or "") for k in ("state_key", "state_label", "story", "story_family", "title", "summary", "story_thesis", "net_effect"))
    raw += " " + " ".join(_json_list(memory.get("tags_json")) + _json_list(memory.get("tickers_json")) + _json_list(memory.get("industries_json")))
    return _tokens(raw)


def _memory_matches_state(memory: dict, state: dict) -> tuple[bool, list[str]]:
    for key in ("state_key", "story", "story_family"):
        if normalize(memory.get(key)) and normalize(memory.get(key)) == normalize(state.get(key)):
            return True, [normalize(memory.get(key))]
    overlap = sorted(_state_identity_tokens(state) & _memory_tokens(memory))
    # 영/한 동의 토큰(semiconductor↔반도체 등)이 "2개 겹침"을 채우지 못하도록
    # canonical 개념 단위로 센다 — 서로 다른 주제 토큰 2개가 겹쳐야 매칭
    concepts = {str(canonical_tag(token) or token).lower() for token in overlap}
    return len(concepts) >= 2, overlap[:8]


def _evidence_id(state_id: str, memory_id: str) -> str:
    return hashlib.sha256(f"{state_id}:{memory_id}".encode("utf-8")).hexdigest()[:24]


def _change_id(state_id: str, field: str, now: str) -> str:
    return hashlib.sha256(f"{state_id}:{field}:{now}".encode("utf-8")).hexdigest()[:24]


def _state_row(conn: sqlite3.Connection, state_id: str):
    return conn.execute("SELECT * FROM market_narrative_states WHERE state_id=?", (state_id,)).fetchone()


def refresh_regime_state(db_path: str | Path, state_id: str, *, days: int = 90) -> dict:
    path = Path(db_path)
    conn = connect(path)
    init_db(conn)
    row = _state_row(conn, state_id)
    if not row:
        conn.close()
        return {"ok": False, "error": "State not found", "stateId": state_id}
    state = dict(row)
    as_of = _now()
    anchor = _parse_date(as_of) or dt.datetime.now(dt.timezone.utc)
    min_date = (anchor - dt.timedelta(days=max(7, int(days or 90)))).date().isoformat()
    candidates = conn.execute(
        """
        SELECT * FROM market_memory
        WHERE date >= ?
        ORDER BY date DESC, as_of DESC
        LIMIT 400
        """,
        (min_date,),
    ).fetchall()
    evidence_rows = []
    for candidate in candidates:
        memory = dict(candidate)
        matches, matched_terms = _memory_matches_state(memory, state)
        if not matches:
            continue
        text = " ".join(str(memory.get(k, "") or "") for k in ("title", "summary", "story_thesis", "story_checkpoint", "net_effect"))
        role = classify_evidence(text, state)
        score = evidence_score(memory, role, as_of=as_of, matched_terms=matched_terms)
        item = {
            "evidenceId": _evidence_id(state_id, memory.get("memory_id", "")),
            "stateId": state_id,
            "memoryId": memory.get("memory_id", ""),
            "evidenceDate": memory.get("date", ""),
            "role": role,
            "score": score,
            "title": memory.get("title", ""),
            "summary": memory.get("summary", ""),
            "sourceKind": memory.get("source_kind", ""),
            "sources": _json_list(memory.get("sources_json")),
            "matchedTerms": matched_terms,
        }
        evidence_rows.append(item)

    evidence_rows.sort(key=lambda item: (item.get("evidenceDate", ""), item.get("score", 0)), reverse=True)
    windows = evidence_windows(evidence_rows, as_of=as_of)
    momentum = determine_momentum(evidence_rows, as_of=as_of)
    confidence = confidence_from_evidence(evidence_rows, as_of=as_of)
    # 구조화 체크포인트는 보존하고 템플릿 문장만 오늘 것으로 갈아끼운다.
    # 예전에는 목록을 통째로 덮어써서, 이 갱신이 도는 순간(서버 시작·RSS 수집마다)
    # 판정 pass가 기록한 status가 초기화됐다.
    next_checkpoints = merge_with_templates(
        parse_json_list(state.get("next_checkpoints_json")),
        regime_checkpoints(state, evidence_rows, momentum),
        scope="narrative",
        forbidden_keywords=[
            state.get("state_label"), state.get("state_key"),
            state.get("story_family"), state.get("story"),
        ],
        now=as_of,
    )
    falsification_triggers = regime_falsification_triggers(state, momentum)
    last_confirmed = next((r["evidenceDate"] for r in evidence_rows if r["role"] == "supporting"), "")
    last_challenged = next((r["evidenceDate"] for r in evidence_rows if r["role"] == "challenging"), "")
    now = _now()
    with conn:
        conn.execute("DELETE FROM market_regime_evidence WHERE state_id=?", (state_id,))
        for item in evidence_rows:
            conn.execute(
                """
                INSERT INTO market_regime_evidence (
                    evidence_id, state_id, memory_id, evidence_date, role, score,
                    title, summary, source_kind, sources_json, matched_terms_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["evidenceId"], state_id, item["memoryId"], item["evidenceDate"], item["role"],
                    item["score"], item["title"], item["summary"], item["sourceKind"],
                    json.dumps(item["sources"], ensure_ascii=False),
                    json.dumps(item["matchedTerms"], ensure_ascii=False),
                    now,
                ),
            )
        old_momentum = normalize_momentum(state.get("momentum"))
        old_confidence = float(state.get("confidence") or 0)
        if old_momentum != momentum:
            conn.execute(
                """
                INSERT INTO market_regime_changes (
                    change_id, state_id, changed_at, field, old_value, new_value, reason,
                    evidence_ids_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _change_id(state_id, "momentum", now), state_id, now, "momentum",
                    old_momentum, momentum,
                    f"30일 supporting/challenging 근거 비중으로 {momentum} 판정",
                    json.dumps([r["evidenceId"] for r in evidence_rows[:6]], ensure_ascii=False),
                    now,
                ),
            )
        if abs(old_confidence - confidence) >= 0.08:
            conn.execute(
                """
                INSERT INTO market_regime_changes (
                    change_id, state_id, changed_at, field, old_value, new_value, reason,
                    evidence_ids_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _change_id(state_id, "confidence", now), state_id, now, "confidence",
                    str(round(old_confidence, 2)), str(confidence),
                    "최근 90일 근거 품질·신선도·일관성으로 confidence 재계산",
                    json.dumps([r["evidenceId"] for r in evidence_rows[:6]], ensure_ascii=False),
                    now,
                ),
            )
        conn.execute(
            """
            UPDATE market_narrative_states
            SET momentum=?, confidence=?, evidence_count_7d=?, evidence_count_30d=?,
                evidence_count_90d=?, last_confirmed_at=?, last_challenged_at=?,
                falsification_triggers_json=?, next_checkpoints_json=?, updated_at=?
            WHERE state_id=?
            """,
            (
                momentum, confidence, windows["evidenceCount7d"], windows["evidenceCount30d"],
                windows["evidenceCount90d"], last_confirmed, last_challenged,
                json.dumps(falsification_triggers, ensure_ascii=False),
                json.dumps(next_checkpoints, ensure_ascii=False),
                now, state_id,
            ),
        )
    link_summary = refresh_thesis_links(conn, state_id)
    conn.close()
    return {
        "ok": True,
        "stateId": state_id,
        "momentum": momentum,
        "confidence": confidence,
        **windows,
        "lastConfirmedAt": last_confirmed,
        "lastChallengedAt": last_challenged,
        "nextCheckpoints": next_checkpoints,
        "falsificationTriggers": falsification_triggers,
        "evidence": evidence_rows[:50],
        "thesisLinks": link_summary,
    }


def refresh_all_regimes(db_path: str | Path, *, status: str = "current", limit: int = 30, days: int = 90) -> dict:
    conn = connect(db_path)
    init_db(conn)
    where = "WHERE status IN ('active','watch')" if status == "current" else ""
    rows = conn.execute(
        f"SELECT state_id FROM market_narrative_states {where} ORDER BY updated_at DESC LIMIT ?",
        (int(limit or 30),),
    ).fetchall()
    conn.close()
    results = [refresh_regime_state(db_path, row["state_id"], days=days) for row in rows]
    return {"ok": True, "count": len(results), "results": results}


def _evidence_row(row) -> dict:
    return {
        "evidenceId": row["evidence_id"],
        "stateId": row["state_id"],
        "memoryId": row["memory_id"],
        "evidenceDate": row["evidence_date"],
        "role": normalize_evidence_role(row["role"]),
        "score": row["score"],
        "title": row["title"],
        "summary": row["summary"],
        "sourceKind": row["source_kind"],
        "sources": parse_json_list(row["sources_json"]),
        "matchedTerms": parse_json_list(row["matched_terms_json"]),
        "createdAt": row["created_at"],
    }


def list_regime_evidence(db_path: str | Path, state_id: str, *, limit: int = 50) -> list[dict]:
    conn = connect(db_path)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT * FROM market_regime_evidence
        WHERE state_id=?
        ORDER BY evidence_date DESC, score DESC
        LIMIT ?
        """,
        (state_id, int(limit or 50)),
    ).fetchall()
    conn.close()
    return [_evidence_row(row) for row in rows]


def list_regime_changes(db_path: str | Path, state_id: str, *, limit: int = 30) -> list[dict]:
    conn = connect(db_path)
    init_db(conn)
    rows = conn.execute(
        """
        SELECT * FROM market_regime_changes
        WHERE state_id=?
        ORDER BY changed_at DESC
        LIMIT ?
        """,
        (state_id, int(limit or 30)),
    ).fetchall()
    conn.close()
    return [
        {
            "changeId": row["change_id"],
            "stateId": row["state_id"],
            "changedAt": row["changed_at"],
            "field": row["field"],
            "oldValue": row["old_value"],
            "newValue": row["new_value"],
            "reason": row["reason"],
            "evidenceIds": parse_json_list(row["evidence_ids_json"]),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def _link_row(row) -> dict:
    return {
        "linkId": row["link_id"],
        "stateId": row["state_id"],
        "ticker": row["ticker"],
        "thesisTicker": row["thesis_ticker"],
        "relationship": row["relationship"],
        "strength": row["strength"],
        "method": row["method"],
        "notePath": row["note_path"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def list_regime_thesis_links(db_path: str | Path, state_id: str) -> list[dict]:
    conn = connect(db_path)
    init_db(conn)
    rows = conn.execute(
        "SELECT * FROM market_regime_thesis_links WHERE state_id=? ORDER BY strength DESC, ticker ASC",
        (state_id,),
    ).fetchall()
    conn.close()
    return [_link_row(row) for row in rows]


def upsert_regime_thesis_link(db_path: str | Path, state_id: str, data: dict) -> dict:
    ticker = str(data.get("ticker") or data.get("thesisTicker") or "").strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    relationship = normalize(data.get("relationship") or "related") or "related"
    strength = max(0.0, min(1.0, float(data.get("strength") or 0.65)))
    note_path = normalize(data.get("notePath") or data.get("note_path") or "")
    now = _now()
    link_id = hashlib.sha256(f"{state_id}:{ticker}".encode("utf-8")).hexdigest()[:24]
    conn = connect(db_path)
    init_db(conn)
    if not _state_row(conn, state_id):
        conn.close()
        raise LookupError("State not found")
    with conn:
        conn.execute(
            """
            INSERT INTO market_regime_thesis_links (
                link_id, state_id, ticker, thesis_ticker, relationship, strength, method,
                note_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?)
            ON CONFLICT(state_id, thesis_ticker) DO UPDATE SET
                ticker=excluded.ticker,
                relationship=excluded.relationship,
                strength=excluded.strength,
                method='manual',
                note_path=excluded.note_path,
                updated_at=excluded.updated_at
            """,
            (link_id, state_id, ticker, ticker, relationship, strength, note_path, now, now),
        )
    row = conn.execute("SELECT * FROM market_regime_thesis_links WHERE link_id=?", (link_id,)).fetchone()
    conn.close()
    return _link_row(row)


def refresh_thesis_links(conn: sqlite3.Connection, state_id: str) -> dict:
    """Infer automatic links from thesis.linked_regimes and Obsidian note hints."""
    try:
        from features.thesis_tracking import store as thesis_store
        thesis_store.init_db(conn)
        theses = thesis_store.list_theses(conn, status="active")
    except Exception:
        theses = []
    state = _state_row(conn, state_id)
    if not state:
        return {"count": 0, "links": []}
    state_text = " ".join(str(state[k] or "") for k in ("state_key", "state_label", "story", "story_family", "summary", "rationale")).lower()
    evidence = conn.execute(
        "SELECT matched_terms_json, summary FROM market_regime_evidence WHERE state_id=? ORDER BY score DESC LIMIT 30",
        (state_id,),
    ).fetchall()
    evidence_text = " ".join([state_text] + [row["summary"] or "" for row in evidence]).lower()
    links = []
    now = _now()
    for thesis in theses:
        ticker = str(thesis.get("ticker") or "").upper()
        regimes = [str(v).lower() for v in thesis.get("linked_regimes", [])]
        strength = 0.0
        reason = ""
        if any(regime and (regime in state_text or regime in evidence_text) for regime in regimes):
            strength = 0.82
            reason = "linked_regimes"
        elif ticker and re.search(rf"\b{re.escape(ticker.lower())}\b", evidence_text):
            strength = 0.62
            reason = "ticker_overlap"
        if strength <= 0:
            continue
        link_id = hashlib.sha256(f"{state_id}:{ticker}".encode("utf-8")).hexdigest()[:24]
        conn.execute(
            """
            INSERT INTO market_regime_thesis_links (
                link_id, state_id, ticker, thesis_ticker, relationship, strength, method,
                note_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, ?, ?)
            ON CONFLICT(state_id, thesis_ticker) DO UPDATE SET
                ticker=excluded.ticker,
                relationship=CASE WHEN market_regime_thesis_links.method='manual' THEN market_regime_thesis_links.relationship ELSE excluded.relationship END,
                strength=MAX(market_regime_thesis_links.strength, excluded.strength),
                note_path=CASE WHEN market_regime_thesis_links.note_path='' THEN excluded.note_path ELSE market_regime_thesis_links.note_path END,
                updated_at=excluded.updated_at
            """,
            (link_id, state_id, ticker, ticker, reason, strength, thesis.get("note_path", ""), now, now),
        )
        links.append({"ticker": ticker, "relationship": reason, "strength": strength})
    try:
        note_rows = conn.execute(
            """
            SELECT rel_path, path, note_type, ticker, title, tags_json
            FROM obsidian_note_index
            WHERE importable = 1 AND layer = 'hypothesis'
            """
        ).fetchall()
    except Exception:
        note_rows = []
    state_tokens = _state_tokens(dict(state))
    for note in note_rows:
        ticker = str(note["ticker"] or "").upper()
        if not ticker:
            continue
        note_tags = parse_json_list(note["tags_json"])
        note_text = " ".join([note["title"] or "", ticker, " ".join(note_tags), note["rel_path"] or ""])
        overlap = state_tokens & _tokens(note_text)
        ticker_hit = re.search(rf"\b{re.escape(ticker.lower())}\b", evidence_text)
        if not overlap and not ticker_hit:
            continue
        strength = 0.58 + min(0.18, len(overlap) * 0.04)
        relationship = "obsidian_note_tags" if overlap else "obsidian_note_ticker"
        link_id = hashlib.sha256(f"{state_id}:{ticker}".encode("utf-8")).hexdigest()[:24]
        conn.execute(
            """
            INSERT INTO market_regime_thesis_links (
                link_id, state_id, ticker, thesis_ticker, relationship, strength, method,
                note_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'auto_note', ?, ?, ?)
            ON CONFLICT(state_id, thesis_ticker) DO UPDATE SET
                ticker=excluded.ticker,
                relationship=CASE WHEN market_regime_thesis_links.method='manual' THEN market_regime_thesis_links.relationship ELSE excluded.relationship END,
                strength=MAX(market_regime_thesis_links.strength, excluded.strength),
                note_path=CASE WHEN market_regime_thesis_links.note_path='' THEN excluded.note_path ELSE market_regime_thesis_links.note_path END,
                updated_at=excluded.updated_at
            """,
            (link_id, state_id, ticker, ticker, relationship, strength, note["path"] or note["rel_path"] or "", now, now),
        )
        links.append({"ticker": ticker, "relationship": relationship, "strength": strength})
    conn.commit()
    return {"count": len(links), "links": links}
