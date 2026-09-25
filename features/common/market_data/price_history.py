from __future__ import annotations

import datetime as dt
import math
from typing import Any, Callable

from features.common.markets import MARKET_REGISTRY, PRODUCT_MARKETS


def _index_entry(descriptor) -> dict:
    entry = {
        "ticker": descriptor.ticker,
        "label": descriptor.label,
        # 시리즈마다 통화를 들고 다닌다. 유럽은 GBP와 EUR이 한 차트에 섞이므로
        # 스냅샷 하나에 통화 하나를 붙이면 축의 숫자에 대해 거짓을 말하게 된다.
        "currency": descriptor.currency,
        "timezone": descriptor.timezone,
        "country": descriptor.country,
    }
    if descriptor.proxy_for:
        entry["proxyFor"] = descriptor.proxy_for
    return entry


# 시장 레지스트리가 대표 지수의 단일 출처다. 여기서 다시 티커를 적지 않는다.
INDEX_UNIVERSE = {
    market.value.lower(): tuple(
        _index_entry(descriptor)
        for descriptor in MARKET_REGISTRY[market].representative_indices
        if descriptor.in_default_chart
    )
    for market in PRODUCT_MARKETS
}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value != value:
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _download_yfinance_rows(symbol: str, *, start: str, end: str, interval: str) -> list[dict]:
    import yfinance as yf

    frame = yf.Ticker(symbol).history(
        start=start,
        end=end,
        interval=interval,
        auto_adjust=False,
        prepost=False,
    )
    if frame is None or frame.empty:
        return []
    rows = []
    for index, row in frame.iterrows():
        close = _safe_float(row.get("Close"))
        if close is None:
            continue
        try:
            time = index.isoformat() if interval in {"5m", "1h"} else index.date().isoformat()
        except Exception:
            time = str(index)
        rows.append({
            "time": time,
            "open": _safe_float(row.get("Open")),
            "high": _safe_float(row.get("High")),
            "low": _safe_float(row.get("Low")),
            "close": close,
            "volume": _safe_float(row.get("Volume")),
            "provider": "yfinance",
        })
    return rows


def _clip_rows(
    rows: list[dict] | None,
    target: dt.date,
    *,
    intraday: bool,
    intraday_start: dt.date | None = None,
) -> list[dict]:
    """Keep valid observations at or before ``target`` without hiding gaps.

    Daily data is keyed by session date and intraday data by timestamp.  A
    repeated key is safe to collapse only when its close agrees; conflicting
    (or malformed) duplicates invalidate that key so a later row cannot
    silently resurrect an arbitrary anchor.  This is deliberately a clipping
    and validation step, not an adjustment step: callers' raw/adjusted price
    basis and the explicit intraday aggregate remain distinct.
    """
    start_date = intraday_start or target
    by_key: dict[str, dict] = {}
    invalid: set[str] = set()
    nonfinite_keys: set[str] = set()
    for row in rows or []:
        time = str(row.get("time") or "")
        row_date = time[:10]
        try:
            parsed_date = dt.date.fromisoformat(row_date)
        except (TypeError, ValueError):
            continue
        if intraday and ("T" not in time and " " not in time):
            continue
        if intraday:
            try:
                dt.datetime.fromisoformat(time.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
        if intraday and not (start_date <= parsed_date <= target):
            continue
        if not intraday and parsed_date > target:
            continue
        # Intraday timestamps must contain a time component; daily points use
        # the session date.  Keep the original timestamp spelling for charts.
        key = time if intraday else row_date
        close = _safe_float(row.get("close"))
        if close is None:
            nonfinite_keys.add(key)
            if key in by_key:
                invalid.add(key)
                by_key.pop(key, None)
            continue
        candidate = dict(row)
        candidate["close"] = close
        for field in ("open", "high", "low", "volume"):
            if field in candidate:
                candidate[field] = _safe_float(candidate.get(field))
        if key in invalid or key in nonfinite_keys:
            invalid.add(key)
            by_key.pop(key, None)
            continue
        prior = by_key.get(key)
        if prior is None:
            by_key[key] = candidate
            continue
        prior_basis = _adjustment_basis(prior)
        candidate_basis = _adjustment_basis(candidate)
        basis_conflict = bool(prior_basis and candidate_basis and prior_basis != candidate_basis)
        if _safe_float(prior.get("close")) != close or basis_conflict:
            invalid.add(key)
            by_key.pop(key, None)
    return sorted(by_key.values(), key=lambda row: str(row.get("time") or ""))


def _provider_from_rows(rows: list[dict] | None, default: str = "custom") -> str:
    providers = []
    for row in rows or []:
        provider = str(row.get("provider") or "").strip()
        if provider and provider not in providers:
            providers.append(provider)
    return "+".join(providers) if providers else default


def _adjustment_basis(row: dict) -> tuple:
    """Return declared adjustment/basis fields for duplicate validation."""
    fields = ("priceBasis", "adjustment", "adjusted", "auto_adjust")
    return tuple((field, str(row.get(field))) for field in fields if field in row)


def _combined_provider(*providers: str) -> str:
    parts = []
    for provider in providers:
        for part in str(provider or "").split("+"):
            part = part.strip()
            if part and part not in parts:
                parts.append(part)
    return "+".join(parts) if parts else "custom"


def _append_intraday_session_bar(daily: list[dict], intraday: list[dict], target: dt.date) -> list[dict]:
    """Fill a delayed daily feed's target bar from the same session's 5m bars."""
    if not intraday or any(str(row.get("time") or "")[:10] == target.isoformat() for row in daily):
        return daily
    opens = [_safe_float(row.get("open")) for row in intraday]
    highs = [_safe_float(row.get("high")) for row in intraday]
    lows = [_safe_float(row.get("low")) for row in intraday]
    closes = [_safe_float(row.get("close")) for row in intraday]
    volumes = [_safe_float(row.get("volume")) for row in intraday]
    valid_closes = [value for value in closes if value is not None]
    if not valid_closes:
        return daily
    first_open = next((value for value in opens if value is not None), valid_closes[0])
    valid_highs = [value for value in highs if value is not None]
    valid_lows = [value for value in lows if value is not None]
    provider = _provider_from_rows(intraday)
    return [*daily, {
        "time": target.isoformat(),
        "open": first_open,
        "high": max(valid_highs) if valid_highs else max(valid_closes),
        "low": min(valid_lows) if valid_lows else min(valid_closes),
        "close": valid_closes[-1],
        "volume": sum(value for value in volumes if value is not None) if any(value is not None for value in volumes) else None,
        "provider": f"intraday_aggregate:{provider}",
    }]


def build_price_history(
    symbol: str,
    session_date: str,
    downloader: Callable[..., list[dict]] | None = None,
) -> dict:
    """Saved briefing candles on one regular-session, unadjusted price basis.

    The legacy Toss downloader returns the latest 200 *one-minute* candles,
    including extended hours, and integrated daily closes. Those are neither
    a requested historical 5m session nor the same basis as regular-session
    hourly candles. Do not combine them in an immutable report. Live Toss
    charts remain owned by chart_service and are unaffected by this choice.
    """
    fetch = downloader if downloader is not None else _download_yfinance_rows
    target = dt.date.fromisoformat(str(session_date)[:10])
    intraday_raw = fetch(
        symbol,
        start=target.isoformat(),
        end=(target + dt.timedelta(days=1)).isoformat(),
        interval="5m",
    )
    hourly_warnings = []
    try:
        hourly_raw = fetch(
            symbol,
            start=(target - dt.timedelta(days=6)).isoformat(),
            end=(target + dt.timedelta(days=1)).isoformat(),
            interval="1h",
        )
    except Exception:
        hourly_raw = []
        hourly_warnings.append("hourly_history_unavailable")
    daily_raw = fetch(
        symbol,
        start=(target - dt.timedelta(days=370)).isoformat(),
        end=(target + dt.timedelta(days=1)).isoformat(),
        interval="1d",
    )
    intraday = _clip_rows(intraday_raw, target, intraday=True)
    hourly = _clip_rows(
        hourly_raw,
        target,
        intraday=True,
        intraday_start=target - dt.timedelta(days=6),
    )
    if not hourly and "hourly_history_unavailable" not in hourly_warnings:
        hourly_warnings.append("hourly_history_empty")
    daily = _clip_rows(daily_raw, target, intraday=False)
    daily = _append_intraday_session_bar(daily, intraday, target)
    intraday_provider = _provider_from_rows(intraday_raw)
    hourly_provider = _provider_from_rows(
        hourly_raw,
        default="yfinance" if downloader is None else "custom",
    )
    daily_provider = _provider_from_rows(daily)
    return {
        "provider": _combined_provider(intraday_provider, hourly_provider, daily_provider),
        "sourceByInterval": {
            "intraday": intraday_provider,
            "hourly": hourly_provider,
            "daily": daily_provider,
        },
        "intraday": {"interval": "5m", "points": intraday},
        "hourly": {"interval": "1h", "points": hourly},
        "daily": {"interval": "1d", "points": daily},
        "warnings": hourly_warnings,
    }
