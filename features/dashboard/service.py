from __future__ import annotations

import json
import time
from pathlib import Path

from features.common.change_intelligence.projection import lineage_matches_ticker, list_change_events
from features.common.research_library.signals.service import provider_health
from features.common.utils import read_json, write_json
from features.dashboard.schema import native_symbol, normalize_dashboard_settings
from features.market_widgets.service import get_market_widget_settings
from features.portfolio.service import get_portfolio
from features.watchlist_notes.service import get_watchlist, sec_ticker_for_name, tradingview_symbol_for_query


def settings_path(data_dir: Path) -> Path:
    return Path(data_dir) / "dashboard-settings.json"


def get_dashboard_settings(data_dir: Path) -> dict:
    return normalize_dashboard_settings(read_json(settings_path(data_dir), {}))


def save_dashboard_settings(data_dir: Path, payload: dict) -> dict:
    current = read_json(settings_path(data_dir), {})
    merged = {**(current if isinstance(current, dict) else {}), **(payload or {})}
    normalized = normalize_dashboard_settings(merged)
    write_json(settings_path(data_dir), normalized)
    return normalized


def focus_symbols(data_dir: Path) -> list[dict]:
    rows = []
    legacy_settings = get_market_widget_settings(data_dir)
    widgets = ((legacy_settings.get("dashboard") or {}).get("widgets") or []) if (Path(data_dir) / "market-widget-settings.json").exists() else []
    for widget in widgets:
        if widget.get("type") not in {"advanced_chart", "symbol_overview", "ticker_tag", "single_ticker"}:
            continue
        symbol = native_symbol(widget.get("symbol"))
        if symbol and symbol not in [row["symbol"] for row in rows]:
            rows.append({"symbol": symbol, "label": widget.get("title") or symbol, "source": "legacy_setting"})
    for item in get_watchlist(data_dir):
        symbol = native_symbol(tradingview_symbol_for_query(item)) or sec_ticker_for_name(item)
        if symbol and symbol not in [row["symbol"] for row in rows]:
            rows.append({"symbol": symbol, "label": item, "source": "watchlist"})
    if not rows:
        rows = [{"symbol": "SPY", "label": "S&P 500", "source": "fallback"}, {"symbol": "^KS11", "label": "KOSPI", "source": "fallback"}]
    return rows[:12]


def _calendar_refs(db_path: Path, limit: int = 12) -> list[dict]:
    if not db_path.exists():
        return []
    import sqlite3

    from features.market_calendar.service import LEGACY_BOK_ROW_SQL

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            # 캘린더 화면과 같은 기준으로 날짜가 틀린 옛 한국 지표 행을 뺀다.
            rows = conn.execute(
                "SELECT id,kind,title,market,starts_at,status,importance,provider FROM market_calendar_events "
                f"WHERE starts_at>=datetime('now','-1 day') AND NOT ({LEGACY_BOK_ROW_SQL}) ORDER BY starts_at LIMIT ?", (limit,),
            ).fetchall()
        except sqlite3.Error:
            return []
    return [dict(row) for row in rows]


VISIBLE_CHANGE_STATUSES = ("major_change", "developing_signal", "conflicting_uncertain")
# 변화 피드는 "무엇이 달라졌나"다. 기한 없는 목록은 새 브리핑이 없는 주에 지난
# 카드를 계속 변화처럼 보여주므로, 이 일수보다 오래된 이벤트는 피드에서 뺀다.
# 권위 저장소(보고서 JSON/스냅샷)와 index 행은 그대로 남는다.
CHANGE_FEED_WINDOW_DAYS = 14


def _current_change_events(events: list[dict], *, now: str = "") -> list[dict]:
    """Drop stale and superseded rows from the visible feed.

    A briefing date used to commit one aggregate row (`2026-08-05`); the four-
    market split commits per-market rows (`2026-08-05.us`, ...). The aggregate id
    is never overwritten by those commits, so without this both generations of
    the same date sit in the feed side by side and the date looks duplicated.
    """
    import datetime as dt

    def _parse(value: str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None

    reference = (_parse(now) if now else None) or dt.datetime.now(dt.timezone.utc)
    cutoff = reference - dt.timedelta(days=CHANGE_FEED_WINDOW_DAYS)
    dates_with_market_rows = {
        str(row.get("artifactId") or "").split(".")[0]
        for row in events
        if row.get("artifactKind") == "briefing" and "." in str(row.get("artifactId") or "")
    }
    kept = []
    for row in events:
        generated = _parse(str(row.get("generatedAt") or ""))
        # 시각을 못 읽는 행은 오래됐다고 단정할 수 없으므로 남긴다.
        if generated and generated < cutoff:
            continue
        artifact_id = str(row.get("artifactId") or "")
        if row.get("artifactKind") == "briefing" and "." not in artifact_id and artifact_id in dates_with_market_rows:
            continue
        kept.append(row)
    return kept


def build_cockpit_payload(data_dir: Path) -> dict:
    started = time.perf_counter()
    data_dir = Path(data_dir)
    db_path = data_dir / "market-memory.sqlite3"
    # Keep the legacy change projection fields in this API response for older
    # clients.  The current Research Cockpit does not render them; new briefing
    # saves also stop creating briefing rows.
    events = _current_change_events(list_change_events(db_path, limit=24))
    changes = [row for row in events if row.get("status") in VISIBLE_CHANGE_STATUSES]
    quiet = [row for row in events if row.get("status") not in VISIBLE_CHANGE_STATUSES]
    portfolio = get_portfolio(data_dir)
    portfolio_tickers = {str(row.get("ticker") or "").upper() for row in portfolio.get("positions") or []}
    watchlist_tickers = {native_symbol(tradingview_symbol_for_query(item)) or sec_ticker_for_name(item) for item in get_watchlist(data_dir)}
    watchlist_tickers = {t for t in watchlist_tickers if t} - portfolio_tickers
    implications = []
    for event in changes:
        lineage = event.get("lineageId")
        matched_portfolio = sorted(t for t in portfolio_tickers if lineage_matches_ticker(lineage, t))
        matched_watchlist = sorted(t for t in watchlist_tickers if lineage_matches_ticker(lineage, t))
        if matched_portfolio or matched_watchlist:
            implications.append({
                "tickers": matched_portfolio + matched_watchlist,
                "source": "portfolio" if matched_portfolio else "watchlist",
                "status": event.get("status"), "artifactId": event.get("artifactId"), "generatedAt": event.get("generatedAt"),
            })
    payload = {
        "schemaVersion": 1, "mode": get_dashboard_settings(data_dir)["dashboardMode"],
        "changes": changes[:12], "quietChanges": quiet[:8],
        "changeCounts": {
            "majorChange": sum(1 for row in changes if row.get("status") == "major_change"),
            "developingSignal": sum(1 for row in changes if row.get("status") == "developing_signal"),
            "conflictingUncertain": sum(1 for row in changes if row.get("status") == "conflicting_uncertain"),
            "quiet": len(quiet),
        },
        "calendarRefs": _calendar_refs(db_path), "focusSymbols": focus_symbols(data_dir),
        "implications": implications[:8],
        "providerHealth": list(provider_health(data_dir).values()),
        "invalidationToken": events[0].get("invalidationToken") if events else "",
        "portfolioState": "available" if portfolio.get("positions") else "empty",
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload["telemetry"] = {"assemblyMs": round((time.perf_counter() - started) * 1000, 2), "payloadBytes": len(encoded), "upstreamRequests": 0}
    return payload
