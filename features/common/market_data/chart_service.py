"""Native chart series service with semantic cache and explicit freshness."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from features.common.data_reliability.fetch_runtime import FetchPolicy, ProviderFetchRuntime

# `1d`는 장중 흐름이라 5분봉으로 받는다. 창을 넉넉히 잡는 이유는 휴장 다음 날이나
# 개장 직후에 당일 봉이 없어 빈 차트가 되기 때문이다. 어차피 `_download`가 마지막
# 세션만 남기므로 길게 잡아도 그리는 양은 같다.
#
# 이틀로는 모자랐다. 월요일 UTC 기준 `오늘-2일`은 토요일이라 금요일 세션이 창 밖으로
# 빠지고, 미국장이 열리는 13:30 UTC까지 한국 근무시간 내내 1D 탭이 비어 있었다.
# 월요일 공휴일 다음 화요일에도 같다.
RANGES = {"1d": 6, "5d": 7, "1m": 35, "3m": 100, "6m": 190, "1y": 370, "5y": 1830}
INTERVALS = {"5m", "1d", "1wk"}


def normalize_chart_request(symbol: str, range_key: str, interval: str) -> tuple[str, str, str]:
    symbol = str(symbol or "").strip().upper()
    if not re.fullmatch(r"(?:\^|[0-9A-Z])[0-9A-Z.^=-]{0,23}", symbol):
        raise ValueError("chart_symbol_invalid")
    range_key = str(range_key or "3m").lower()
    interval = str(interval or "1d").lower()
    if range_key not in RANGES or interval not in INTERVALS:
        raise ValueError("chart_range_or_interval_invalid")
    if interval == "5m" and range_key not in {"1d", "5d"}:
        raise ValueError("chart_intraday_range_invalid")
    return symbol, range_key, interval


# 이동평균 창(거래일). 계산은 서버가 한다 — 화면이 받은 구간만으로 계산하면 1M(21봉)
# 차트에서 20일선이 끝 한두 점만 남는다. 워밍업만큼 과거를 더 받아 계산하고 구간은
# 요청대로 돌려준다.
MA_WINDOWS = (20, 60)
# 거래일 60개 ≈ 달력 88일. 휴장 몰림을 감안해 넉넉히 잡는다 — 어차피 잘라서 돌려준다.
_MA_WARMUP_CALENDAR_DAYS = 130


def _download(symbol: str, range_key: str, interval: str) -> dict:
    import yfinance as yf

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=RANGES[range_key])
    fetch_start = start - dt.timedelta(days=_MA_WARMUP_CALENDAR_DAYS) if interval == "1d" else start
    frame = yf.Ticker(symbol).history(start=fetch_start.date().isoformat(), end=(end + dt.timedelta(days=1)).date().isoformat(), interval=interval, auto_adjust=False, prepost=False)
    ma_by_time: dict[str, dict[str, float]] = {}
    if interval == "1d" and frame is not None and not frame.empty:
        closes = frame["Close"]
        for window in MA_WINDOWS:
            series = closes.rolling(window).mean()
            for index, value in series.items():
                number = float(value)
                if number != number:
                    continue
                ma_by_time.setdefault(index.date().isoformat(), {})[f"ma{window}"] = number
        # 워밍업 구간은 계산에만 쓰고 응답에서는 자른다 — 구간 계약은 그대로다.
        cutoff = start.date().isoformat()
        frame = frame[[stamp.date().isoformat() >= cutoff for stamp in frame.index]]
    if frame is not None and not frame.empty and range_key == "1d":
        # `1D`는 하루치 장중 흐름이다 — 시초가에서 종가까지 한 세션만 그린다.
        # 이틀을 요청하는 건 휴장 다음 날이나 개장 직후에 당일 봉이 없어 빈
        # 차트가 되지 않게 하기 위해서지, 이틀을 이어 붙이려는 게 아니다.
        # 이어 붙이면 밤 사이 갭이 세션 안의 급락처럼 보인다.
        last_session = frame.index[-1].date()
        frame = frame[[stamp.date() == last_session for stamp in frame.index]]
    rows = []
    if frame is not None and not frame.empty:
        for index, row in frame.tail(2000).iterrows():
            try:
                close = float(row.get("Close"))
            except (TypeError, ValueError):
                continue
            if close != close:
                continue
            time_value = index.isoformat() if interval == "5m" else index.date().isoformat()
            def number(key):
                try:
                    value = float(row.get(key))
                    return None if value != value else value
                except (TypeError, ValueError):
                    return None
            rows.append({
                "time": time_value, "open": number("Open"), "high": number("High"),
                "low": number("Low"), "close": close, "volume": number("Volume"),
                **ma_by_time.get(time_value, {}),
            })
    return {"symbol": symbol, "range": range_key, "interval": interval, "series": rows, "asOf": rows[-1]["time"] if rows else "", "provider": "yfinance"}


def get_chart(data_dir: Path, *, symbol: str, range_key: str = "3m", interval: str = "1d", runtime: ProviderFetchRuntime | None = None) -> dict:
    symbol, range_key, interval = normalize_chart_request(symbol, range_key, interval)
    runtime = runtime or ProviderFetchRuntime(Path(data_dir) / "provider-cache" / "charts", max_workers=3)
    ttl = 60 if interval == "5m" else 900
    result = runtime.fetch(
        "yfinance", "chart_series", {"symbol": symbol, "range": range_key, "interval": interval, "schema": 2},
        lambda: _download(symbol, range_key, interval),
        policy=FetchPolicy(ttl_seconds=ttl, timeout_seconds=20, stale_while_revalidate_seconds=86400),
        background_refresh=True,
    )
    value = result.get("value") if isinstance(result.get("value"), dict) else {"symbol": symbol, "range": range_key, "interval": interval, "series": [], "asOf": "", "provider": "yfinance"}
    return {
        **value, "freshness": result.get("status"), "fetchedAt": result.get("fetchedAt") or "",
        "fallbackReason": result.get("fallbackReason") or "", "delayed": True,
        "notice": "yfinance 일봉/분봉은 실시간 체결가가 아닙니다.",
    }
