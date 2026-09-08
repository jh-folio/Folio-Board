#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import calendar as pycalendar
import math
import re
from zoneinfo import ZoneInfo

from features.common.market_calendar import market_open_status, previous_trading_day


try:
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = dt.timezone(dt.timedelta(hours=9))

MARKET_TICKERS = {
    "SPY": "S&P 500 ETF",
    "QQQ": "Nasdaq 100 ETF",
    "IWM": "Russell 2000 ETF",
    "RSP": "S&P 500 Equal Weight",
    "^VIX": "VIX",
    "^TNX": "US 10Y Yield",
    "TLT": "Long Treasury ETF",
    "HYG": "High Yield Credit",
    "LQD": "Investment Grade Credit",
    "DX-Y.NYB": "DXY",
    "CL=F": "WTI Crude",
    "GC=F": "Gold",
    "BTC-USD": "Bitcoin",
}

# These are the instruments for which a one-day/5-day comparison is a market
# session comparison.  FX, futures, rates and crypto can print on dates when a
# stock exchange is closed, so applying the NYSE calendar to them would turn an
# observed interval into a made-up trading-session interval.
US_EQUITY_CALENDAR_TICKERS = frozenset({
    "SPY", "QQQ", "IWM", "RSP", "^VIX", "TLT", "HYG", "LQD",
})
CRYPTO_24_7_TICKERS = frozenset({"BTC-USD"})
RATE_TICKERS = frozenset({"^TNX", "^IRX", "^FVX", "^TYX"})
KNOWN_INDEX_TICKERS = frozenset({"^GSPC", "^IXIC", "^DJI", "^KS11", "^KQ11", "^KS200"})
INDEX_LEVEL_TICKERS = frozenset({"^GSPC", "^IXIC", "^DJI", "^KS11", "^KQ11", "^KS200", "^VIX"})


def _infer_asset_kind(ticker: str) -> str:
    symbol = str(ticker or "").strip().upper()
    if symbol in RATE_TICKERS:
        return "rate"
    if symbol.endswith("=X"):
        return "fx"
    if symbol.endswith("=F"):
        return "future"
    if symbol.endswith("-USD"):
        return "crypto"
    if symbol in US_EQUITY_CALENDAR_TICKERS or symbol in KNOWN_INDEX_TICKERS:
        return "equity"
    # A bare US symbol is the only ambiguous case accepted by the default
    # classifier (e.g. NVDA). Exchange-style suffixes are never guessed as
    # stock instruments here.
    if re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", symbol):
        return "equity"
    return "unknown"


def snapshot_price_metadata(ticker: str, *, market: str = "US", asset_kind: str | None = None) -> dict:
    """Describe the known yfinance price basis without guessing custom feeds."""
    symbol = str(ticker or "").strip().upper()
    kind = str(asset_kind or _infer_asset_kind(symbol)).lower()
    if kind == "index" or symbol in INDEX_LEVEL_TICKERS:
        unit = "points"
    elif kind == "rate":
        unit = "percent"
    elif kind == "fx":
        unit = "quote"
    elif kind == "crypto":
        unit = "USD"
    elif str(market).upper() == "KR":
        unit = "KRW"
    elif kind == "equity":
        unit = "USD"
    else:
        unit = "unknown"
    metadata = {
        "comparisonSource": "yfinance",
        "priceUnit": unit,
        "comparisonUnit": unit,
        "priceBasis": "unadjusted_close",
        "comparisonBasis": "unadjusted_close",
    }
    for prefix in ("oneDay", "fiveDay"):
        metadata.update({
            f"{prefix}ComparisonSource": "yfinance",
            f"{prefix}ComparisonUnit": unit,
            f"{prefix}ComparisonBasis": "unadjusted_close",
        })
    return metadata


def pct_change(first: float | None, last: float | None) -> float | None:
    if first is None or last is None or first == 0:
        return None
    try:
        result = (last / first - 1.0) * 100.0
    except (OverflowError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) else None


def safe_float(value) -> float | None:
    try:
        if value != value or not math.isfinite(float(value)):
            return None
        return float(value)
    except Exception:
        return None


def _parse_bar_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except (TypeError, ValueError):
        return None


def snapshot_cache_suffix(as_of_date=None) -> str:
    """Return a stable cache suffix so historical cutoffs never reuse current data."""
    day = _parse_bar_date(as_of_date)
    return f".{day.isoformat()}" if day else ""


def snapshot_cutoff_date(date, market_windows=None, kind="daily", weekly_window=None) -> str:
    """Resolve the one cutoff shared by API and Agent snapshot consumers."""
    if kind == "weekly" and weekly_window is not None:
        return str(weekly_window.week_end or "")[:10]
    return str((market_windows or {}).get("usRegularSessionDate") or date or "")[:10]


def _subtract_months(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 - months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return day.replace(year=year, month=month, day=min(day.day, pycalendar.monthrange(year, month)[1]))


def _period_start_date(cutoff: dt.date, period: str) -> dt.date | None:
    """Resolve yfinance period labels at calendar boundaries, not day estimates."""
    text = str(period or "1mo").strip().lower()
    if text == "ytd":
        return dt.date(cutoff.year, 1, 1)
    if text == "max":
        # Explicit full-history query; never describe an arbitrary bounded
        # lookback as ``max``.
        return dt.date(1970, 1, 1)
    match = re.fullmatch(r"(\d+)(mo|d|w|y)", text)
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2)
    if unit == "d":
        return cutoff - dt.timedelta(days=amount)
    if unit == "w":
        return cutoff - dt.timedelta(days=amount * 7)
    if unit == "mo":
        return _subtract_months(cutoff, amount)
    return _subtract_months(cutoff, amount * 12)


def _normalize_close_pairs(pairs, *, as_of_date: dt.date | None = None) -> tuple[list[tuple[dt.date, float]], list[str]]:
    """Normalize daily closes without treating row position as a session.

    yfinance normally returns sorted, unique dates, but this boundary is also
    used with fixtures and other providers. Identical duplicate dates collapse;
    conflicting or invalid duplicates are discarded as ambiguous. Future and
    malformed bars are ignored.
    """
    cutoff = _parse_bar_date(as_of_date) or dt.datetime.now(tz=KST).date()
    by_date: dict[dt.date, float] = {}
    seen_dates: set[dt.date] = set()
    invalid_duplicate_dates: set[dt.date] = set()
    reasons: list[str] = []
    for raw_date, raw_close in pairs or []:
        day = _parse_bar_date(raw_date)
        close = safe_float(raw_close)
        if day is None:
            if "invalid_bar_date" not in reasons:
                reasons.append("invalid_bar_date")
            continue
        if day > cutoff:
            if "future_bar_ignored" not in reasons:
                reasons.append("future_bar_ignored")
            continue
        if day in seen_dates:
            if "duplicate_bar_date" not in reasons:
                reasons.append("duplicate_bar_date")
            if close is None and "nonfinite_close_ignored" not in reasons:
                reasons.append("nonfinite_close_ignored")
            previous = by_date.get(day)
            # Identical duplicates are harmless. A conflicting or invalid
            # duplicate makes the date ambiguous; a later valid row must not
            # resurrect an unusable comparison anchor.
            if close is None or previous is None or close != previous:
                invalid_duplicate_dates.add(day)
                if "conflicting_duplicate_bar" not in reasons:
                    reasons.append("conflicting_duplicate_bar")
            continue
        seen_dates.add(day)
        if close is None:
            if "nonfinite_close_ignored" not in reasons:
                reasons.append("nonfinite_close_ignored")
            continue
        by_date[day] = close
    for day in invalid_duplicate_dates:
        by_date.pop(day, None)
    return sorted(by_date.items()), reasons


def _calendar_is_known(status: dict | None) -> bool:
    return isinstance(status, dict) and status.get("source") in {"static", "exchange_api"}


def _equity_rows_for_sessions(rows: list[tuple[dt.date, float]], market: str, calendar_fetcher) -> tuple[list[tuple[dt.date, float]], list[str]]:
    """Drop known stock-market holidays and report an unknown calendar.

    A missing calendar does not make the observed latest close disappear, but
    it prevents session-relative comparisons.  In particular, there is no
    weekday fallback here.
    """
    kept: list[tuple[dt.date, float]] = []
    reasons: list[str] = []
    for day, close in rows:
        status = market_open_status(day, market, calendar_fetcher)
        if not _calendar_is_known(status):
            if "calendar_unavailable" not in reasons:
                reasons.append("calendar_unavailable")
            kept.append((day, close))
            continue
        if status.get("isOpen"):
            kept.append((day, close))
        elif "holiday_bar_ignored" not in reasons:
            reasons.append("holiday_bar_ignored")
    return kept, reasons


def _expected_prior_sessions(anchor: dt.date, count: int, market: str, calendar_fetcher) -> tuple[list[dt.date] | None, str | None]:
    """Return exactly ``count`` prior sessions, or a non-guessing reason."""
    dates: list[dt.date] = []
    cursor = anchor
    for _ in range(count):
        status = market_open_status(cursor, market, calendar_fetcher)
        if not _calendar_is_known(status):
            return None, "calendar_unavailable"
        prior = previous_trading_day(cursor, market, calendar_fetcher)
        if not isinstance(prior, dt.date) or prior >= cursor:
            return None, "calendar_unavailable"
        prior_status = market_open_status(prior, market, calendar_fetcher)
        if not _calendar_is_known(prior_status):
            return None, "calendar_unavailable"
        if not prior_status.get("isOpen"):
            return None, "calendar_unavailable"
        dates.append(prior)
        cursor = prior
    return dates, None


def calculate_price_returns(
    rows: list[tuple[object, object]],
    ticker: str,
    *,
    as_of_date: dt.date | None = None,
    calendar_fetcher=None,
    market: str = "US",
    asset_kind: str | None = None,
    period_start_date=None,
) -> dict:
    """Calculate compatible snapshot fields from dated close observations.

    ``periodPct`` remains first-observation-to-last-observation.  ``oneDayPct``
    and ``fiveDayPct`` are session-relative for equity instruments and become
    null when their exact comparison observation is absent.
    """
    normalized, quality_reasons = _normalize_close_pairs(rows, as_of_date=as_of_date)
    # Passing an explicit empty fetcher forces the static calendar fallback and
    # keeps this pure calculation path from making a connected-provider call.
    calendar_fetcher = calendar_fetcher or (lambda _day, _market: None)
    normalized_market = str(market).upper()
    kind = str(asset_kind or _infer_asset_kind(ticker)).strip().lower()
    if kind == "index":
        kind = "equity"
    uses_calendar = normalized_market in {"US", "KR"} and kind == "equity"
    is_crypto = kind == "crypto"
    if uses_calendar:
        normalized, calendar_reasons = _equity_rows_for_sessions(normalized, str(market).upper(), calendar_fetcher)
        for reason in calendar_reasons:
            if reason not in quality_reasons:
                quality_reasons.append(reason)
    if not normalized:
        return {
            "last": None,
            "asOfDate": None,
            "oneDayPct": None,
            "fiveDayPct": None,
            "oneDayComparisonValue": None,
            "fiveDayComparisonValue": None,
            "periodPct": None,
            "oneDayComparisonDate": None,
            "fiveDayComparisonDate": None,
            "oneDayReason": "no_valid_close",
            "fiveDayReason": "no_valid_close",
            "periodStartDate": None,
            "periodEndDate": None,
            "dataQualityReasons": quality_reasons,
        }

    values = dict(normalized)
    current_date, current = normalized[-1]
    period_rows = normalized
    requested_period_start = _parse_bar_date(period_start_date)
    if requested_period_start is not None:
        period_rows = [row for row in normalized if row[0] >= requested_period_start]
        if not period_rows:
            period_rows = normalized
    result = {
        "last": current,
        "asOfDate": current_date.isoformat(),
        "oneDayPct": None,
        "fiveDayPct": None,
        "oneDayComparisonValue": None,
        "fiveDayComparisonValue": None,
        "periodPct": pct_change(period_rows[0][1], current),
        "oneDayComparisonDate": None,
        "fiveDayComparisonDate": None,
        "oneDayReason": None,
        "fiveDayReason": None,
        "periodStartDate": period_rows[0][0].isoformat(),
        "periodEndDate": current_date.isoformat(),
        "dataQualityReasons": quality_reasons,
    }

    if uses_calendar:
        one_day_dates, one_day_calendar_reason = _expected_prior_sessions(current_date, 1, str(market).upper(), calendar_fetcher)
        if one_day_dates is None:
            result["oneDayReason"] = one_day_calendar_reason
        else:
            prior_date = one_day_dates[0]
            result["oneDayComparisonDate"] = prior_date.isoformat()
            if prior_date in values:
                result["oneDayComparisonValue"] = values[prior_date]
                if values[prior_date] == 0:
                    result["oneDayReason"] = "zero_comparison_value"
                else:
                    result["oneDayPct"] = pct_change(values[prior_date], current)
            else:
                result["oneDayReason"] = "prior_session_missing"

        five_day_dates, five_day_calendar_reason = _expected_prior_sessions(current_date, 5, str(market).upper(), calendar_fetcher)
        if five_day_dates is None:
            result["fiveDayReason"] = five_day_calendar_reason
        else:
            prior_dates = five_day_dates
            five_date = prior_dates[-1]
            result["fiveDayComparisonDate"] = five_date.isoformat()
            missing = [day for day in prior_dates if day not in values]
            if missing:
                result["fiveDayReason"] = "session_bar_missing"
            elif values[five_date] == 0:
                result["fiveDayComparisonValue"] = values[five_date]
                result["fiveDayReason"] = "zero_comparison_value"
            else:
                result["fiveDayComparisonValue"] = values[five_date]
                result["fiveDayPct"] = pct_change(values[five_date], current)
    elif is_crypto:
        # Bitcoin is a known 24/7 series: compare exact calendar dates rather
        # than treating an arbitrary row offset as a five-day interval.
        one_day_date = current_date - dt.timedelta(days=1)
        result["oneDayComparisonDate"] = one_day_date.isoformat()
        if one_day_date not in values:
            result["oneDayReason"] = "prior_observation_missing"
        elif values[one_day_date] == 0:
            result["oneDayComparisonValue"] = values[one_day_date]
            result["oneDayReason"] = "zero_comparison_value"
        else:
            result["oneDayComparisonValue"] = values[one_day_date]
            result["oneDayPct"] = pct_change(values[one_day_date], current)
        five_day_date = current_date - dt.timedelta(days=5)
        result["fiveDayComparisonDate"] = five_day_date.isoformat()
        if five_day_date not in values:
            result["fiveDayReason"] = "prior_observation_missing"
        elif values[five_day_date] == 0:
            result["fiveDayComparisonValue"] = values[five_day_date]
            result["fiveDayReason"] = "zero_comparison_value"
        else:
            result["fiveDayComparisonValue"] = values[five_day_date]
            result["fiveDayPct"] = pct_change(values[five_day_date], current)
    else:
        # FX, futures and rates have no calendar contract here. Keep the
        # period interval but do not publish row-offset daily claims.
        result["oneDayReason"] = "unsupported_comparison_calendar"
        result["fiveDayReason"] = "unsupported_comparison_calendar"
    return result


def fetch_market_snapshot(period: str = "1mo", as_of_date=None) -> dict:
    try:
        import yfinance as yf
    except Exception:
        return {
            "ok": False,
            "error": "market_data_provider_unavailable",
            "asOfKst": dt.datetime.now(tz=KST).isoformat(),
            "tickers": {},
            "signals": [],
        }

    cutoff = _parse_bar_date(as_of_date)
    tickers = {}
    for ticker, label in MARKET_TICKERS.items():
        try:
            if cutoff is None:
                hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
            else:
                # Historical briefings must query a range ending at the
                # requested cutoff; a current ``period`` cache is not past data.
                # Keep a small comparison warmup, but calculate periodPct from
                # the requested period boundary so the warmup does not silently
                # turn a 1mo request into a 3mo return.
                period_start = _period_start_date(cutoff, period)
                if period_start is None:
                    tickers[ticker] = {"label": label, "error": "historical_period_unsupported"}
                    continue
                start = (period_start - dt.timedelta(days=10)).isoformat()
                end = (cutoff + dt.timedelta(days=1)).isoformat()
                hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
        except Exception:
            tickers[ticker] = {"label": label, "error": "market_data_unavailable"}
            continue
        if hist is None or hist.empty or "Close" not in hist:
            tickers[ticker] = {"label": label, "error": "no price data"}
            continue
        # 종가와 해당 일봉 날짜를 함께 보관한 뒤 NaN을 버린다. 이렇게 해야
        # last(최근값)가 실제로 며칠 종가인지(asOfDate)를 알 수 있다. yfinance가
        # 당일 EOD 일봉을 아직 안 주면 그 날짜는 NaN으로 빠지고, last는 그 전
        # 거래일 종가가 된다 — 이 경우 asOfDate로 그 사실이 드러난다.
        def _bar_date(idx_value):
            try:
                return idx_value.date().isoformat()
            except Exception:
                return str(idx_value)[:10]
        pairs = [
            (_bar_date(idx), x)
            for idx, x in zip(hist.index, hist["Close"].tolist())
        ]
        if not pairs:
            tickers[ticker] = {"label": label, "error": "no close data"}
            continue
        period_start = _period_start_date(cutoff, period) if cutoff else None
        calculated = calculate_price_returns(
            pairs, ticker, as_of_date=cutoff, period_start_date=period_start,
        )
        if calculated.get("last") is None:
            tickers[ticker] = {"label": label, "error": "no close data"}
            continue
        tickers[ticker] = {
            "label": label,
            **calculated,
            **snapshot_price_metadata(ticker),
        }

    def val(ticker: str, key: str) -> float | None:
        value = tickers.get(ticker, {}).get(key)
        return value if isinstance(value, (int, float)) else None

    spy_1d = val("SPY", "oneDayPct")
    qqq_1d = val("QQQ", "oneDayPct")
    vix_1d = val("^VIX", "oneDayPct")
    hyg_5d = val("HYG", "fiveDayPct")
    lqd_5d = val("LQD", "fiveDayPct")
    tlt_5d = val("TLT", "fiveDayPct")
    oil_5d = val("CL=F", "fiveDayPct")
    signals = []
    if spy_1d is not None and vix_1d is not None:
        if spy_1d >= 0 and vix_1d <= 0:
            signals.append("주식 상승과 변동성 하락이 동시에 나타난 리스크온 신호")
        if spy_1d < 0 and vix_1d > 0:
            signals.append("주식 하락과 변동성 상승이 동시에 나타난 리스크오프 신호")
    if hyg_5d is not None and lqd_5d is not None and (hyg_5d - lqd_5d) < 0:
        signals.append("하이일드가 IG 대비 약해 크레딧 내부는 방어적으로 움직임")
    if tlt_5d is not None and tlt_5d > 1:
        signals.append("장기채 강세가 동반되어 금리/성장 기대 변화 확인 필요")
    if oil_5d is not None and abs(oil_5d) >= 4:
        signals.append("유가 변동성이 커져 에너지·인플레이션 경로 점검 필요")
    if qqq_1d is not None and spy_1d is not None and qqq_1d > spy_1d:
        signals.append("나스닥/성장주가 S&P 500 대비 우위")

    # 미국 정규장 데이터가 며칠 종가까지 반영됐는지 — 24시간 거래되는 선물/암호화폐가
    # 아니라 미국 주식 ETF/지수 기준으로 판단한다(스냅샷 stale 여부 판정용).
    us_equity_dates = [
        tickers.get(t, {}).get("asOfDate")
        for t in ("SPY", "QQQ", "IWM", "RSP", "^TNX")
    ]
    us_equity_dates = [d for d in us_equity_dates if d]
    latest_us_equity_date = max(us_equity_dates) if us_equity_dates else None

    return {
        "ok": True,
        "asOfKst": dt.datetime.now(tz=KST).isoformat(),
        "requestedPeriod": period,
        "dataNote": "yfinance daily data; delayed/end-of-day data may be mixed.",
        "latestUsEquityDate": latest_us_equity_date,
        "tickers": tickers,
        "signals": signals,
    }


def snapshot_to_markdown(snapshot: dict) -> str:
    if not snapshot.get("ok"):
        return f"시장 스냅샷을 불러오지 못했습니다: {snapshot.get('error', 'unknown error')}"
    rows = [
        "| 지표 | 기준일 | 최근값 | 1D | 5D | 기간 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for ticker, data in snapshot.get("tickers", {}).items():
        if data.get("error"):
            continue
        def fmt(value):
            if value is None:
                return "-"
            return f"{value:.2f}"
        def pct(value):
            if value is None:
                return "-"
            return f"{value:+.2f}%"
        rows.append(
            f"| {ticker} {data.get('label', '')} | {data.get('asOfDate', '-')} | {fmt(data.get('last'))} | {pct(data.get('oneDayPct'))} | {pct(data.get('fiveDayPct'))} | {pct(data.get('periodPct'))} |"
        )
    signals = "\n".join(f"- {item}" for item in snapshot.get("signals", [])) or "- 뚜렷한 규칙 기반 신호 없음"
    latest_us = snapshot.get("latestUsEquityDate")
    return "\n".join([
        f"as of KST: {snapshot.get('asOfKst', '')}",
        f"data note: {snapshot.get('dataNote', '')}",
        (f"미국 주가 데이터 기준일: {latest_us} 종가까지 반영" if latest_us else ""),
        "",
        *rows,
        "",
        "규칙 기반 신호:",
        signals,
    ])

