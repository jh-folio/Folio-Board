"""Completed daily closes, separate from intraday briefing/chart providers."""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from .decimal_ops import source_number, number


def provider_symbol(ticker: str, market: str, metadata: dict) -> tuple[str, str]:
    if market == "KR":
        suffix = {"Y": ".KS", "K": ".KQ"}.get(metadata.get("corp_cls"))
        if not suffix or not re.fullmatch(r"[0-9][A-Z0-9]{5}", ticker):
            raise ValueError("exchange_not_supported")
        return ticker + suffix, "dart_corp_cls"
    if market == "US" and metadata.get("exchanges"):
        if metadata.get("tickers") and ticker not in metadata["tickers"]:
            raise ValueError("instrument_not_in_submissions")
        return ticker, "sec_submissions"
    raise ValueError("exchange_unknown")


def completed_closes(bars: list[dict], market: str, *, now: dt.datetime) -> list[dict]:
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    zones = {"US": ("America/New_York", 16, 30), "KR": ("Asia/Seoul", 16, 0)}
    if market not in zones:
        raise ValueError("market_not_supported")
    zone, hour, minute = zones[market]
    local = now.astimezone(ZoneInfo(zone))
    output = []
    seen = set()
    for bar in sorted(bars, key=lambda row: row["date"]):
        day = dt.date.fromisoformat(bar["date"])
        value = source_number(bar.get("close"))
        if day.weekday() >= 5 or day > local.date() or value is None or number(value) <= 0:
            continue
        if day == local.date() and (local.hour, local.minute) < (hour, minute):
            continue
        if day.isoformat() in seen:
            raise ValueError("duplicate_daily_bar")
        seen.add(day.isoformat())
        output.append({"date": day.isoformat(), "close": value})
    return output


def reference_price(bars: list[dict], market: str, *, now: dt.datetime, currency: str, symbol: str) -> dict:
    closes = completed_closes(bars, market, now=now)
    if not closes:
        raise ValueError("price_unavailable")
    zone = ZoneInfo("America/New_York" if market == "US" else "Asia/Seoul")
    today, recent = now.astimezone(zone).date(), dt.date.fromisoformat(closes[-1]["date"])
    weekdays = sum((recent + dt.timedelta(days=i)).weekday() < 5 for i in range(1, (today-recent).days+1))
    if weekdays >= 10:
        raise ValueError("price_stale")
    if not currency:
        raise ValueError("currency_unknown")
    if currency not in {"USD", "KRW"}:
        raise ValueError("quote_currency_not_supported")
    return {"value": closes[-1]["close"], "sessionDate": recent.isoformat(), "currency": currency,
            "provider": "yfinance", "providerSymbol": symbol}


def fiscal_year_prices(closes: list[dict], periods: list[dict]) -> list[dict]:
    output = []
    for period in periods:
        end = dt.date.fromisoformat(period["periodEnd"])
        eligible = [row for row in closes if dt.date.fromisoformat(row["date"]) <= end]
        if eligible:
            row = max(eligible, key=lambda r: r["date"])
            output.append({"fiscalYear": period["fiscalYear"], "periodEnd": end.isoformat(), "priceDate": row["date"], "close": row["close"]})
    return output


def fetch_daily_history(ticker: str, market: str, metadata: dict, *, now: dt.datetime, timeout=8.0) -> dict:
    """Explicit daily-only collection. No app price/cache or workspace writes.

    A successful empty split column is a source observation, not confirmation
    that there were no events; official traces still have to be reconciled.
    """
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    symbol, exchange_source = provider_symbol(ticker, market, metadata)
    zone = ZoneInfo("America/New_York" if market == "US" else "Asia/Seoul")
    end = now.astimezone(zone).date()
    start = end.replace(year=end.year - 11, day=min(end.day, 28)) if end.month == 2 else end.replace(year=end.year - 11)
    import yfinance as yf

    stock = yf.Ticker(symbol)
    frame = stock.history(start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat(),
                          interval="1d", auto_adjust=False, back_adjust=False, actions=True,
                          repair=False, rounding=False, timeout=timeout, raise_errors=True)
    if frame is None or getattr(frame, "empty", True) or "Close" not in frame.columns:
        raise ValueError("price_unavailable")
    raw_bars, events = [], []
    event_source_complete = "Stock Splits" in frame.columns
    for index, row in frame.iterrows():
        day = index.date().isoformat()
        raw_bars.append({"date": day, "close": source_number(row.get("Close")),
                         "dividend": source_number(row.get("Dividends"))})
        ratio = source_number(row.get("Stock Splits"))
        if ratio is None or number(ratio) < 0:
            event_source_complete = False
        if ratio is not None and number(ratio) > 0:
            events.append({"eventDate": day, "shareDate": day, "ratio": ratio, "kind": "unspecified",
                           "exDateBasis": "provider", "sources": [{"provider": "yfinance", "symbol": symbol}]})
    closes = completed_closes(raw_bars, market, now=now)
    # Currency comes from quote metadata, never the ticker or reporting currency.
    quote_metadata = stock.get_history_metadata() or {}
    currency = str(quote_metadata.get("currency") or "")
    price = reference_price(raw_bars, market, now=now, currency=currency, symbol=symbol)
    events = [event for event in events if event["eventDate"] <= price["sessionDate"]]
    return {"price": price, "closes": closes, "rawBars": raw_bars, "events": events,
            "eventSourceState": "received" if event_source_complete else "unknown",
            "exchangeSource": exchange_source,
            "request": {"provider": "yfinance", "providerSymbol": symbol, "start": start.isoformat(),
                        "endExclusive": (end + dt.timedelta(days=1)).isoformat(), "interval": "1d", "autoAdjust": False},
            "fetchedAt": now.isoformat()}
