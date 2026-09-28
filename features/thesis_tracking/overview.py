"""Watchlist reason projection, including currently held companies.

This is a read model. It never registers holdings in watchlist.json or writes a
thesis when a position changes.
"""
from __future__ import annotations

from pathlib import Path

from features.common.workspace import data_dir
from features.portfolio.service import get_portfolio
from features.thesis_tracking import model, reason_history, store
from features.thesis_tracking import reason_review
from features.watchlist_notes.service import watchlist_overview


def reason_watchlist_overview(*, db_path=None, data_path: Path | None = None) -> dict:
    base = watchlist_overview()
    cards = list(base.get("items") or [])
    directory = Path(data_path or data_dir())
    holdings = get_portfolio(directory).get("positions") or []
    held: dict[str, dict] = {}
    for row in holdings:
        ticker = model.normalize_ticker(row.get("ticker") or row.get("symbol") or "")
        try:
            has_position = float(row.get("quantity") or 0) != 0
        except (TypeError, ValueError):
            has_position = False
        if ticker and has_position:
            held[ticker] = row
    known = {model.normalize_ticker(row.get("ticker")): row for row in cards if row.get("ticker")}
    for ticker, position in held.items():
        if ticker not in known:
            cards.append({"item": ticker, "ticker": ticker,
                          "companyName": position.get("name") or ticker,
                          "sector": "", "count": 0, "latestDate": "",
                          "portfolioOnly": True})
    conn = store.connect(db_path)
    try:
        for card in cards:
            ticker = model.normalize_ticker(card.get("ticker"))
            current = store.get_thesis(conn, ticker) if ticker else None
            revision = reason_history.latest(conn, current["ticker"]) if current else None
            card["reasonKind"] = "investment" if ticker in held else "interest"
            card["reasonRevisionId"] = revision["revisionId"] if revision else ""
            card["reasonPreview"] = str(current.get("core_thesis") or "")[:120] if current else ""
            card["reasonStatus"] = reason_review.status_for_reason(
                conn, current["ticker"] if current else ticker,
                revision["revisionId"] if revision else None,
                bool(current and current.get("core_thesis")),
            )[0]
    finally:
        conn.close()
    return {**base, "items": cards}
