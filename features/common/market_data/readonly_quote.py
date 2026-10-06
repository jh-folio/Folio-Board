"""Explicit preview quote read using the existing Yahoo chart provider; no caches or fallback currency."""
import datetime as dt
import json
import re
from decimal import Decimal
from urllib.parse import quote
from urllib.request import Request, urlopen

from features.common.instruments.registry import quote_currency


def read_quote(symbol: str) -> dict:
    if not isinstance(symbol, str) or not re.fullmatch(r"\^?[A-Z0-9][A-Z0-9.^=\-]{0,24}", symbol):
        return {"status": "unavailable", "reason": "quote_identity_unknown"}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}?range=10d&interval=1d"
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=8) as response:
            packet = json.loads(response.read(2_000_000), parse_float=str)
        meta = packet["chart"]["result"][0]["meta"]
        if str(meta.get("symbol") or "").upper() != symbol.upper():
            raise ValueError()
        raw_currency = meta.get("currency")
        if not isinstance(raw_currency, str) or not re.fullmatch(r"[A-Za-z]{3}", raw_currency):
            raise ValueError()
        currency, scale = quote_currency(raw_currency)
        value = Decimal(str(meta["regularMarketPrice"]))
        if not value.is_finite() or value <= 0:
            raise ValueError()
        timestamp = meta.get("regularMarketTime")
        observed = dt.datetime.fromtimestamp(int(timestamp), dt.timezone.utc).isoformat().replace("+00:00", "Z") if timestamp is not None else None
        return {"status": "available", "symbol": symbol, "value": str(value * Decimal(str(scale))),
                "rawValue": str(value), "rawCurrency": raw_currency, "currency": currency,
                "observedAt": observed, "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": "yahoo_chart_regularMarketPrice", "availabilityBasis": "provider_timestamp" if observed else "fetched_only",
                "freshness": "unknown", "assetClass": meta.get("instrumentType")}
    except Exception:
        return {"status": "unavailable", "reason": "quote_unavailable", "symbol": symbol}


def read_fx(currency: str) -> dict:
    if currency == "USD":
        return {"status": "available", "rateToUsd": "1", "source": "USD_identity", "currency": "USD"}
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        return {"status": "unavailable", "reason": "fx_currency_unknown"}
    direct = read_quote(f"{currency}USD=X")
    if direct.get("status") == "available" and direct.get("currency") == "USD":
        return {**direct, "rateToUsd": direct["value"], "currency": currency}
    inverse = read_quote("KRW=X" if currency == "KRW" else f"{currency}=X")
    if inverse.get("status") == "available" and inverse.get("currency") == currency:
        return {**inverse, "rateToUsd": str(Decimal(1) / Decimal(inverse["value"])), "currency": currency}
    return {"status": "unavailable", "reason": "fx_unavailable", "currency": currency}
