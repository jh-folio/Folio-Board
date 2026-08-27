from __future__ import annotations

import os

"""Toss Securities Open API market-data client.

Official docs: https://developers.tossinvest.com/docs
Machine-readable source of truth: https://openapi.tossinvest.com/openapi-docs/latest/openapi.json

The API uses OAuth2 Client Credentials:
POST /oauth2/token with client_id/client_secret, then
Authorization: Bearer {access_token} for market data endpoints.
"""

import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from features.llm_settings.client import (
    toss_open_api_base_url,
    toss_open_api_client_id,
    toss_open_api_client_secret,
    toss_open_api_enabled,
)


Transport = Callable[..., dict]
_TOKEN_CACHE: dict[str, Any] = {}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def toss_symbol_for(symbol: str) -> str:
    """Return Toss-compatible stock/ETF symbol, or empty string if unsupported."""
    raw = str(symbol or "").strip().upper()
    if raw.endswith(".KS") or raw.endswith(".KQ"):
        raw = raw.split(".", 1)[0]
    if raw.startswith("^") or "=" in raw:
        return ""
    # Avoid treating crypto/FX/futures pseudo tickers as securities.
    if raw in {"BTC-USD", "USDKRW=X"}:
        return ""
    return raw if re.fullmatch(r"[A-Z0-9.\-]+", raw) else ""


def toss_credentials_available() -> bool:
    return bool(toss_open_api_enabled() and toss_open_api_client_id() and toss_open_api_client_secret())


def _default_transport(method: str, url: str, *, headers=None, data=None, timeout=10) -> dict:
    body = data
    if isinstance(data, dict):
        body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _base_url() -> str:
    return toss_open_api_base_url().rstrip("/") or "https://openapi.tossinvest.com"


def issue_access_token(*, transport: Transport | None = None) -> str:
    if not toss_open_api_enabled():
        raise ValueError("Toss Open API is disabled for this release")
    client_id = toss_open_api_client_id()
    client_secret = toss_open_api_client_secret()
    if not client_id or not client_secret:
        raise ValueError("Toss Open API client_id/client_secret is not configured")
    now = time.time()
    cached = _TOKEN_CACHE.get("access_token")
    if cached and float(_TOKEN_CACHE.get("expires_at") or 0) > now + 60:
        return str(cached)
    fetch = transport or _default_transport
    payload = fetch(
        "POST",
        f"{_base_url()}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Toss Open API token response did not include access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    _TOKEN_CACHE.update({"access_token": token, "expires_at": now + max(60, expires_in)})
    return token


def request_json(path: str, params: dict[str, Any] | None = None, *, transport: Transport | None = None) -> dict:
    fetch = transport or _default_transport
    token = issue_access_token(transport=fetch)
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{_base_url()}{path}" + (f"?{query}" if query else "")
    return fetch("GET", url, headers={"Authorization": f"Bearer {token}"}, timeout=10)


def _calendar_day_date(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    text = str(value.get("date") or "").strip()
    try:
        return dt.date.fromisoformat(text[:10]).isoformat()
    except (TypeError, ValueError):
        return ""


def fetch_toss_market_calendar(
    market: str,
    *,
    date: str,
    transport: Transport | None = None,
) -> dict:
    """Return the exchange calendar status for one KR/US local market date.

    A valid response is authoritative for the requested date. Callers fall back
    to the bundled static calendar when credentials are unavailable, the request
    fails, or the response cannot be validated.
    """
    normalized_market = str(market or "").strip().upper()
    if normalized_market not in {"KR", "US"}:
        raise ValueError("Toss market calendar supports only KR or US")
    requested_date = dt.date.fromisoformat(str(date or "")[:10]).isoformat()
    payload = request_json(
        f"/api/v1/market-calendar/{normalized_market}",
        {"date": requested_date},
        transport=transport,
    )
    result = payload.get("result") or {}
    today = result.get("today") or {}
    response_date = _calendar_day_date(today)
    if response_date != requested_date:
        return {}

    if normalized_market == "KR":
        regular_market = (today.get("integrated") or {}).get("regularMarket")
    else:
        regular_market = today.get("regularMarket")
    previous_day = _calendar_day_date(result.get("previousBusinessDay"))
    next_day = _calendar_day_date(result.get("nextBusinessDay"))
    return {
        "provider": "toss_open_api",
        "market": normalized_market,
        "date": response_date,
        "isOpen": isinstance(regular_market, dict) and bool(regular_market),
        "regularMarket": regular_market if isinstance(regular_market, dict) else None,
        "previousBusinessDay": previous_day,
        "nextBusinessDay": next_day,
    }


def fetch_toss_prices(symbols: list[str], *, transport: Transport | None = None) -> list[dict]:
    # 테스트에서는 실제 API를 부르지 않는다(market_universe의 yfinance 가드와 같은
    # 계약). transport를 주입한 호출은 테스트가 의도적으로 응답을 제어하는 것이므로
    # 허용한다.
    if transport is None and os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("market_data_network_disabled_in_tests")
    normalized = [toss_symbol_for(symbol) for symbol in symbols]
    normalized = [symbol for symbol in dict.fromkeys(normalized) if symbol]
    if not normalized:
        return []
    payload = request_json("/api/v1/prices", {"symbols": ",".join(normalized[:200])}, transport=transport)
    rows = []
    for row in payload.get("result") or []:
        rows.append({
            "symbol": row.get("symbol"),
            "timestamp": row.get("timestamp"),
            "lastPrice": _safe_float(row.get("lastPrice")),
            "currency": row.get("currency"),
            "provider": "toss_open_api",
        })
    return rows


def fetch_toss_candles(
    symbol: str,
    *,
    interval: str = "1d",
    count: int = 200,
    before: str | None = None,
    adjusted: bool = True,
    transport: Transport | None = None,
) -> list[dict]:
    toss_symbol = toss_symbol_for(symbol)
    if not toss_symbol:
        return []
    api_interval = "1m" if interval in {"1m", "5m"} else "1d"
    payload = request_json(
        "/api/v1/candles",
        {
            "symbol": toss_symbol,
            "interval": api_interval,
            "count": max(1, min(int(count or 200), 200)),
            "before": before,
            "adjusted": str(bool(adjusted)).lower(),
        },
        transport=transport,
    )
    result = payload.get("result") or {}
    return result.get("candles") or []


def _row_date(timestamp: str) -> str:
    return str(timestamp or "")[:10]


def download_toss_candle_rows(
    symbol: str,
    *,
    start: str,
    end: str,
    interval: str,
    transport: Transport | None = None,
) -> list[dict]:
    if not toss_credentials_available():
        return []
    api_interval = "1m" if interval in {"1m", "5m"} else "1d"
    count = 200
    candles = fetch_toss_candles(
        symbol,
        interval=api_interval,
        count=count,
        adjusted=True,
        transport=transport,
    )
    start_text = str(start or "")[:10]
    end_text = str(end or "")[:10]
    rows = []
    for candle in candles:
        timestamp = str(candle.get("timestamp") or "")
        day = _row_date(timestamp)
        if start_text and day < start_text:
            continue
        if end_text and day >= end_text:
            continue
        rows.append({
            "time": timestamp if api_interval == "1m" else day,
            "open": _safe_float(candle.get("openPrice")),
            "high": _safe_float(candle.get("highPrice")),
            "low": _safe_float(candle.get("lowPrice")),
            "close": _safe_float(candle.get("closePrice")),
            "volume": _safe_float(candle.get("volume")),
            "provider": "toss_open_api",
        })
    rows = [row for row in rows if row["close"] is not None]
    return sorted(rows, key=lambda row: str(row.get("time") or ""))


def fetch_usdkrw_exchange_rate(*, date_time: str | None = None, transport: Transport | None = None) -> dict:
    if not toss_credentials_available():
        return {}
    payload = request_json(
        "/api/v1/exchange-rate",
        {"baseCurrency": "USD", "quoteCurrency": "KRW", "dateTime": date_time},
        transport=transport,
    )
    result = payload.get("result") or {}
    rate = _safe_float(result.get("midRate")) or _safe_float(result.get("rate"))
    if rate is None:
        return {}
    return {
        "USDKRW": {
            "label": "원·달러 환율",
            "asOfDate": str(result.get("validFrom") or "")[:10],
            "close": rate,
            "changePct": None,
            "source": "toss_open_api",
        }
    }
