"""Persistent Agent thread contract.

도크가 대화의 집이고, 주제가 붙은 대화(워치리스트·포트폴리오·보고서)는 그 아래
한 종류다. 화면에서는 전부 "대화"라 부르고 주제는 칩으로 표시한다.

내부 식별자(`sourceLayer: user_consultation` 등)는 저장된 데이터와의 계약이라
그대로 둔다 — 화면 문구와 내부 이름이 다른 것이 데이터를 옮기는 것보다 안전하다.
"""
from __future__ import annotations

import re

SESSION_STATUSES = {"active", "archived"}
# 주제 없는 일반 대화. 도크에서 그냥 시작한 대화가 여기 들어간다.
UNSCOPED_KIND = "general"
SCOPE_KINDS = {UNSCOPED_KIND, "watchlist", "portfolio", "briefing", "company_analysis", "topic_report", "market_memory", "change", "investment_review"}
SCOPE_INTENTS = {"", "challenge"}
NOTE_TYPES = {"company_thesis", "portfolio_decision", "investment_note"}
MAX_MESSAGES = 500
MAX_SESSION_BYTES = 2 * 1024 * 1024
MAX_MESSAGE_CHARS = 12_000
_REVIEW_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_id(value: object) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[A-Za-z0-9_-]{1,96}", text) else ""


def clean_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def normalize_scope(value: dict | None) -> dict:
    value = value if isinstance(value, dict) else {}
    # 알 수 없는 kind를 `portfolio`로 떨어뜨리면 주제 없는 도크 대화가 포트폴리오
    # 대화로 둔갑한다. 모르는 주제는 주제 없음이지 포트폴리오가 아니다.
    kind = clean_text(value.get("kind") or value.get("surface") or UNSCOPED_KIND, 40).lower()
    if kind not in SCOPE_KINDS:
        kind = UNSCOPED_KIND
    tickers = value.get("tickers") if isinstance(value.get("tickers"), list) else []
    intent = clean_text(value.get("intent"), 24).lower()
    if intent not in SCOPE_INTENTS:
        intent = ""
    try:
        revision = max(0, int(value.get("revision") or 0))
    except (TypeError, ValueError):
        revision = 0
    identifier = clean_text(value.get("id") or value.get("reportId"), 160)
    if kind == "investment_review" and _REVIEW_DATE_RE.fullmatch(identifier) is None:
        identifier = ""
    return {
        "kind": kind,
        "id": identifier,
        "marketScope": clean_text(value.get("marketScope"), 16).lower(),
        "tickers": [clean_text(ticker, 24).upper() for ticker in tickers if clean_text(ticker, 24)][:20],
        "intent": intent,
        # Used only by the immutable-at-open investment review challenge.  It
        # is a public revision number, not an internal input fingerprint.
        "revision": revision if kind == "investment_review" else 0,
    }


def public_session(value: dict, *, include_messages: bool = True) -> dict:
    allowed = {
        "id", "title", "scope", "status", "revision", "messages", "messageCount", "memory",
        "continuationOf", "continuedBy", "createdAt", "updatedAt", "layer", "sourceLayer",
        "reuseAsHypothesis", "reuseAsEvidence",
    }
    row = {key: value.get(key) for key in allowed if key in value}
    if not include_messages:
        row.pop("messages", None)
        row.pop("memory", None)
    return row
