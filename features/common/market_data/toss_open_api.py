from __future__ import annotations

import os

"""Toss Securities Open API market-data client.

Official docs: https://developers.tossinvest.com/docs
Pinned contract: REST OpenAPI 1.2.14 and realtime AsyncAPI 1.2.2.

The API uses OAuth2 Client Credentials:
POST /oauth2/token with client_id/client_secret, then
Authorization: Bearer {access_token} for market data endpoints.
"""

import datetime as dt
from decimal import Decimal, InvalidOperation
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from features.llm_settings.client import (
    TOSS_OPEN_API_DEFAULT_BASE_URL,
    toss_open_api_base_url,
    toss_open_api_client_id,
    toss_open_api_client_secret,
    toss_open_api_enabled,
)
from features.common.workspace import data_dir
from features.common.market_data.toss_token_manager import TokenLease, TossProviderError, TossTokenError, TossTokenManager


Transport = Callable[..., dict]
_TOKEN_MANAGER: TossTokenManager | None = None
_TOKEN_MANAGER_INIT_LOCK = threading.Lock()
TOSS_REST_OPENAPI_VERSION = "1.2.14"
TOSS_REALTIME_ASYNCAPI_VERSION = "1.2.2"

# Extracted from the pinned OpenAPI 1.2.14 fixture. Keep this explicit schema
# beside the adapter: importing must never infer wire types from mutable docs.
_ACCOUNT_REQUIRED_FIELDS = {
    "accountNo": "nonempty_string",
    "accountSeq": "int64",
    "accountType": "nonempty_string",
}
_HOLDINGS_OVERVIEW_OBJECT_FIELDS = (
    "totalPurchaseAmount", "marketValue", "profitLoss", "dailyProfitLoss",
)
_HOLDINGS_ITEM_STRING_FIELDS = ("symbol", "name", "marketCountry", "currency")
_HOLDINGS_ITEM_DECIMAL_FIELDS = (
    "quantity", "lastPrice", "averagePurchasePrice",
)
_HOLDINGS_ITEM_OBJECT_FIELDS = ("marketValue", "profitLoss", "dailyProfitLoss", "cost")
_TOSS_MARKET_INDICATORS = {
    "^KS11": "KOSPI",
    "KOSPI": "KOSPI",
    "^KQ11": "KOSDAQ",
    "KOSDAQ": "KOSDAQ",
}
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


class _LegacyTokenCache(dict):
    """Compatibility reset hook for existing focused tests and internal tools."""

    def clear(self) -> None:  # type: ignore[override]
        super().clear()
        if _TOKEN_MANAGER is not None:
            _TOKEN_MANAGER.clear_cached_token_for_tests()


_TOKEN_CACHE: dict[str, Any] = _LegacyTokenCache()


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


def toss_market_indicator_for(symbol: str) -> str:
    """Map Folio/yfinance index symbols to Toss market-indicator symbols."""
    return _TOSS_MARKET_INDICATORS.get(str(symbol or "").strip().upper(), "")


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
    # ``toss_open_api_base_url`` is the one settings boundary that normalizes
    # a missing or whitespace-only configured origin to this pinned default.
    return toss_open_api_base_url().rstrip("/") or TOSS_OPEN_API_DEFAULT_BASE_URL


def token_manager() -> TossTokenManager:
    """The sole process-local token owner, shared by REST and future WebSocket."""
    global _TOKEN_MANAGER
    manager = _TOKEN_MANAGER
    if manager is not None:
        return manager
    with _TOKEN_MANAGER_INIT_LOCK:
        if _TOKEN_MANAGER is None:
            _TOKEN_MANAGER = TossTokenManager(
                workspace_dir=data_dir(),
                enabled=toss_open_api_enabled,
                client_id=toss_open_api_client_id,
                client_secret=toss_open_api_client_secret,
            )
        return _TOKEN_MANAGER


def _set_token_manager_for_tests(manager: TossTokenManager | None) -> None:
    """Focused-test seam; production code always uses :func:`token_manager`."""
    global _TOKEN_MANAGER
    _TOKEN_MANAGER = manager
    _TOKEN_CACHE.clear()


def toss_provider_health() -> dict:
    """Safe health only; it never issues a token or attempts a process lock."""
    return token_manager().health_snapshot()


def _token_payload(*, transport: Transport | None = None) -> tuple[str, int]:
    fetch = transport or _default_transport
    payload = fetch(
        "POST",
        f"{_base_url()}/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_id": toss_open_api_client_id(),
            "client_secret": toss_open_api_client_secret(),
        },
        timeout=10,
    )
    return str(payload.get("access_token") or "").strip(), int(payload.get("expires_in") or 3600)


def issue_access_token(*, transport: Transport | None = None) -> str:
    try:
        lease = token_manager().get_token(lambda: _token_payload(transport=transport))
    except TossTokenError as exc:
        if exc.code == "disabled":
            raise ValueError("Toss Open API is disabled for this release") from exc
        if exc.code == "credentials_missing":
            raise ValueError("Toss Open API client_id/client_secret is not configured") from exc
        raise RuntimeError(exc.code) from exc
    # Legacy private cache is not an authority.  Keep it process-memory-only so
    # existing focused tests/tools that clear it still reset the new manager.
    _TOKEN_CACHE.update({"access_token": lease.token, "generation": lease.generation})
    return lease.token


def _issue_lease(*, transport: Transport | None = None) -> TokenLease:
    try:
        return token_manager().get_token(lambda: _token_payload(transport=transport))
    except TossTokenError as exc:
        if exc.code == "disabled":
            raise ValueError("Toss Open API is disabled for this release") from exc
        if exc.code == "credentials_missing":
            raise ValueError("Toss Open API client_id/client_secret is not configured") from exc
        raise RuntimeError(exc.code) from exc


def issue_access_token_lease() -> TokenLease:
    """Safe realtime seam: shares the REST manager and its generation."""
    return _issue_lease()


def active_token_generation() -> int:
    """Read-only generation marker for the realtime owner; never issues a token."""
    return int(getattr(token_manager(), "_generation", 0))


def _explicit_token_error_code(payload: dict) -> str | None:
    error = payload.get("error") if isinstance(payload, dict) else None
    code = payload.get("code") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code") or code
    elif isinstance(error, str) and not code:
        code = error
    normalized = str(code or "").strip().lower().replace("-", "_")
    if normalized in {"invalid_token", "invalid_access_token"}:
        return "invalid_token"
    if normalized in {"access_token_expired", "token_expired"}:
        return "token_expired"
    return None


def _retry_authorization_failure(lease: TokenLease, *, code: str, retried: bool, headers: object | None = None) -> bool:
    """Return whether this request may make its one safe auth retry."""
    manager = token_manager()
    manager.record_http_error(401, headers, error_code=code)
    manager.invalidate_if_generation(lease.generation, error_code=code)
    if retried:
        raise TossProviderError(code)
    # A stale request must not clear a newer token, but its first GET still
    # failed.  It receives one retry even while the matching request is issuing
    # the next generation; `_issue_lease()` waits on that single-flight issuer.
    return True


def request_json(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    transport: Transport | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    fetch = transport or _default_transport
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    url = f"{_base_url()}{path}" + (f"?{query}" if query else "")
    retried = False
    while True:
        lease = _issue_lease(transport=fetch)
        try:
            request_headers = {"Authorization": f"Bearer {lease.token}"}
            request_headers.update(headers or {})
            payload = fetch("GET", url, headers=request_headers, timeout=10)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                # Record exactly once per failed GET; the manager's invalidate
                # operation only clears a matching generation.
                try:
                    retry = _retry_authorization_failure(lease, code="invalid_token", retried=retried, headers=exc.headers)
                except TossProviderError as terminal:
                    # Do not retain provider reason/body through exception
                    # chaining after the one permitted auth retry is spent.
                    raise terminal from None
                if retry:
                    retried = True
                    continue
            token_manager().record_http_error(exc.code, exc.headers)
            raise
        token_error = _explicit_token_error_code(payload)
        if token_error:
            retry = _retry_authorization_failure(lease, code=token_error, retried=retried)
            if retry:
                retried = True
                continue
        return payload


def fetch_toss_accounts(*, transport: Transport | None = None) -> list[dict]:
    """Read the pinned 1.2.14 account envelope for the import feature.

    This adapter intentionally returns the wire values only to the server-side
    caller.  Routes must use :mod:`features.portfolio.toss_import` to mask the
    account number and keep the sequence in its short-lived process store.
    """
    try:
        payload = request_json("/api/v1/accounts", transport=transport)
    except Exception as exc:
        # Never attach a provider response/body to the public error surface.
        status = getattr(exc, "code", None)
        code = {401: "invalid_token", 403: "ip_allowlist_or_permission_denied", 429: "rate_limited"}.get(status, getattr(exc, "code", "provider_error"))
        raise TossProviderError(code) from None
    rows = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise TossProviderError("provider_contract_invalid")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise TossProviderError("provider_contract_invalid")
        number, sequence, account_type = row.get("accountNo"), row.get("accountSeq"), row.get("accountType")
        if (
            not isinstance(number, str) or not number.strip()
            or isinstance(sequence, bool) or not isinstance(sequence, int)
            or not _INT64_MIN <= sequence <= _INT64_MAX
            or not isinstance(account_type, str) or not account_type.strip()
        ):
            raise TossProviderError("provider_contract_invalid")
        normalized.append(dict(row))
    return normalized


def fetch_toss_holdings(account_seq: int, *, transport: Transport | None = None) -> dict:
    """Read one account's pinned holdings overview without optional queries."""
    try:
        sequence = int(account_seq)
        payload = request_json(
            "/api/v1/holdings",
            transport=transport,
            headers={"X-Tossinvest-Account": str(sequence)},
        )
    except Exception as exc:
        status = getattr(exc, "code", None)
        code = {401: "invalid_token", 403: "ip_allowlist_or_permission_denied", 429: "rate_limited"}.get(status, getattr(exc, "code", "provider_error"))
        raise TossProviderError(code) from None
    result = payload.get("result") if isinstance(payload, dict) else None
    if (
        not isinstance(result, dict)
        or any(key not in result for key in (*_HOLDINGS_OVERVIEW_OBJECT_FIELDS, "items"))
        or not isinstance(result.get("items"), list)
        or not _valid_holdings_overview(result)
    ):
        raise TossProviderError("provider_contract_invalid")
    for item in result["items"]:
        if (
            not isinstance(item, dict)
            or any(key not in item for key in (*_HOLDINGS_ITEM_STRING_FIELDS, *_HOLDINGS_ITEM_DECIMAL_FIELDS, *_HOLDINGS_ITEM_OBJECT_FIELDS))
            or any(not isinstance(item.get(key), str) or not item.get(key).strip() for key in _HOLDINGS_ITEM_STRING_FIELDS)
            or any(not _finite_decimal_string(item.get(key)) for key in _HOLDINGS_ITEM_DECIMAL_FIELDS)
            or not _valid_holding_item_objects(item)
        ):
            raise TossProviderError("provider_contract_invalid")
    return dict(result)


def _finite_decimal_string(value: object) -> bool:
    """OpenAPI 1.2.14 monetary values are finite decimal strings, not JSON numbers."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        return Decimal(value).is_finite()
    except (InvalidOperation, ValueError):
        return False


def _decimal_fields(value: object, required: tuple[str, ...], *, nullable: tuple[str, ...] = ()) -> bool:
    if not isinstance(value, dict) or any(key not in value for key in required):
        return False
    for key in required:
        field = value.get(key)
        if key in nullable and field is None:
            continue
        if not _finite_decimal_string(field):
            return False
    return True


def _price(value: object) -> bool:
    """Official Price requires KRW; USD may be absent or null."""
    if not _decimal_fields(value, ("krw",)):
        return False
    return not isinstance(value, dict) or "usd" not in value or value.get("usd") is None or _finite_decimal_string(value.get("usd"))


def _valid_holdings_overview(value: dict) -> bool:
    market_value = value.get("marketValue")
    profit_loss = value.get("profitLoss")
    daily = value.get("dailyProfitLoss")
    return (
        _price(value.get("totalPurchaseAmount"))
        and isinstance(market_value, dict)
        and _price(market_value.get("amount"))
        and _price(market_value.get("amountAfterCost"))
        and isinstance(profit_loss, dict)
        and _price(profit_loss.get("amount"))
        and _price(profit_loss.get("amountAfterCost"))
        and _decimal_fields(profit_loss, ("rate", "rateAfterCost"))
        and isinstance(daily, dict)
        and _price(daily.get("amount"))
        and _decimal_fields(daily, ("rate",))
    )


def _valid_holding_item_objects(value: dict) -> bool:
    return (
        _decimal_fields(value.get("marketValue"), ("purchaseAmount", "amount", "amountAfterCost"))
        and _decimal_fields(value.get("profitLoss"), ("amount", "amountAfterCost", "rate", "rateAfterCost"))
        and _decimal_fields(value.get("dailyProfitLoss"), ("amount", "rate"))
        and _decimal_fields(value.get("cost"), ("commission",))
        and (
            not isinstance(value.get("cost"), dict)
            or "tax" not in value["cost"]
            or value["cost"].get("tax") is None
            or _finite_decimal_string(value["cost"].get("tax"))
        )
    )


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
    return fetch_toss_candle_page(symbol, interval=interval, count=count, before=before, adjusted=adjusted, transport=transport)["candles"]


def fetch_toss_candle_page(
    symbol: str,
    *,
    interval: str = "1d",
    count: int = 200,
    before: str | None = None,
    adjusted: bool = True,
    transport: Transport | None = None,
) -> dict[str, object]:
    """Pinned REST 1.2.14 page shape; no mutable specification fetches."""
    # The REST adapter has no hourly candle contract.  Returning an empty page
    # is safer than issuing a daily request and letting callers mislabel it as
    # 1h data.
    if interval == "1h":
        return {"candles": [], "nextBefore": ""}
    indicator = toss_market_indicator_for(symbol)
    toss_symbol = toss_symbol_for(symbol) if not indicator else ""
    if not indicator and not toss_symbol:
        return {"candles": [], "nextBefore": ""}
    api_interval = "1m" if interval in {"1m", "5m"} else "1d"
    path = f"/api/v1/market-indicators/{indicator}/candles" if indicator else "/api/v1/candles"
    params = {
        "interval": api_interval,
        "count": max(1, min(int(count or 200), 200)),
        "before": before,
    }
    if not indicator:
        params.update({"symbol": toss_symbol, "adjusted": str(bool(adjusted)).lower()})
    payload = request_json(
        path,
        params,
        transport=transport,
    )
    result = payload.get("result") or {}
    return {"candles": result.get("candles") or [], "nextBefore": str(result.get("nextBefore") or "")}


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
    if interval == "1h":
        return []
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
