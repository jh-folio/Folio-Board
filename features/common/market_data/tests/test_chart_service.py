from __future__ import annotations

import pytest

from features.common.data_reliability.fetch_runtime import ProviderFetchRuntime
from features.common.market_data import chart_service


def test_chart_request_enum_and_intraday_guard():
    assert chart_service.normalize_chart_request("nvda", "3m", "1d") == ("NVDA", "3m", "1d")
    with pytest.raises(ValueError, match="chart_symbol_invalid"):
        chart_service.normalize_chart_request("<bad>", "3m", "1d")
    with pytest.raises(ValueError, match="chart_intraday_range_invalid"):
        chart_service.normalize_chart_request("NVDA", "1y", "5m")


class _Stamp:
    """yfinance 인덱스 흉내 — `.date()`와 `.isoformat()`만 쓴다."""

    def __init__(self, day, text):
        self._day, self._text = day, text

    def date(self):
        return self._day

    def isoformat(self):
        return self._text


class _Frame:
    def __init__(self, rows):
        self._rows = rows

    @property
    def empty(self):
        return not self._rows

    @property
    def index(self):
        return [stamp for stamp, _ in self._rows]

    def __getitem__(self, mask):
        return _Frame([row for row, keep in zip(self._rows, mask) if keep])

    def tail(self, _n):
        return self

    def iterrows(self):
        return iter(self._rows)


def test_one_day_keeps_only_the_latest_session(monkeypatch):
    """`1D`는 시초가에서 종가까지 한 세션이다.

    이틀치를 요청하는 건 개장 직후 빈 차트를 피하려는 것이지 이틀을 이어
    붙이려는 게 아니다. 이어 붙이면 밤 사이 갭이 세션 안 급락으로 보인다.
    """
    import datetime as dt

    def bar(day, hhmm, close):
        return (_Stamp(day, f"{day}T{hhmm}:00-04:00"), {"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1})

    yesterday, today = dt.date(2026, 8, 5), dt.date(2026, 8, 6)
    frame = _Frame([bar(yesterday, "09:30", 100), bar(yesterday, "15:55", 101), bar(today, "09:30", 90), bar(today, "15:55", 95)])
    monkeypatch.setitem(
        __import__("sys").modules, "yfinance",
        type("M", (), {"Ticker": staticmethod(lambda _s: type("T", (), {"history": staticmethod(lambda **_k: frame)})())})(),
    )
    payload = chart_service._download("NVDA", "1d", "5m")
    assert [row["close"] for row in payload["series"]] == [90, 95]


def test_chart_uses_semantic_cache_and_explicit_delay(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        chart_service,
        "_download",
        lambda symbol, range_key, interval: calls.append((symbol, range_key, interval)) or {
            "symbol": symbol,
            "range": range_key,
            "interval": interval,
            "series": [{"time": "2026-08-01", "close": 100}],
            "asOf": "2026-08-01",
            "provider": "fixture",
        },
    )
    runtime = ProviderFetchRuntime(tmp_path / "cache")
    first = chart_service.get_chart(tmp_path, symbol="NVDA", runtime=runtime)
    second = chart_service.get_chart(tmp_path, symbol="NVDA", runtime=runtime)
    assert first["delayed"] is True
    assert second["freshness"] == "cached"
    assert calls == [("NVDA", "3m", "1d")]


def test_daily_moving_averages_are_computed_with_warmup(monkeypatch):
    """이동평균은 서버가 워밍업 구간까지 받아 계산한다.

    화면이 받은 구간만으로 계산하면 1M(21봉) 차트에서 20일선이 끝 한두 점만 남는다.
    워밍업 봉은 계산에만 쓰고 응답 구간은 요청대로다.
    """
    import datetime as dt

    import pandas as pd

    dates = pd.bdate_range(end=dt.date.today(), periods=240)
    closes = [float(i + 1) for i in range(len(dates))]
    frame = pd.DataFrame(
        {"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": [1.0] * len(dates)},
        index=dates,
    )
    monkeypatch.setitem(
        __import__("sys").modules, "yfinance",
        type("M", (), {"Ticker": staticmethod(lambda _s: type("T", (), {"history": staticmethod(lambda **_k: frame)})())})(),
    )

    payload = chart_service._download("NVDA", "1m", "1d")
    rows = payload["series"]

    # 구간은 요청(달력 35일)대로 — 워밍업 90봉이 통째로 나오면 안 된다.
    assert 0 < len(rows) < 40
    last = rows[-1]
    assert last["ma20"] == sum(closes[-20:]) / 20
    assert last["ma60"] == sum(closes[-60:]) / 60
    assert last["ma120"] == sum(closes[-120:]) / 120
    # 240봉으로는 200일선도 창을 채운다. 못 채우는 창은 키 자체가 없다(None 아님).
    assert last["ma200"] == sum(closes[-200:]) / 200
    # 응답 첫 봉에도 이동평균이 있다 — 워밍업 덕에 구간 안에서 선이 끊기지 않는다.
    assert rows[0]["ma20"] is not None


def test_intraday_bars_have_no_moving_averages(monkeypatch):
    """5분봉에는 이동평균을 붙이지 않는다 — 일 단위 창을 분봉에 걸면 다른 지표가 된다."""
    import datetime as dt

    def bar(day, hhmm, close):
        return (_Stamp(day, f"{day}T{hhmm}:00-04:00"), {"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1})

    today = dt.date(2026, 8, 6)
    frame = _Frame([bar(today, "09:30", 90), bar(today, "15:55", 95)])
    monkeypatch.setitem(
        __import__("sys").modules, "yfinance",
        type("M", (), {"Ticker": staticmethod(lambda _s: type("T", (), {"history": staticmethod(lambda **_k: frame)})())})(),
    )

    payload = chart_service._download("NVDA", "1d", "5m")

    assert all("ma20" not in row for row in payload["series"])


def test_toss_1m_bootstrap_aggregates_exchange_local_five_minute_bars_with_rest_snapshot_volume():
    rows = chart_service.aggregate_toss_1m_to_5m([
        {"timestamp": "2026-09-01T09:30:00-04:00", "openPrice": "10", "highPrice": "11", "lowPrice": "9", "closePrice": "10.5", "volume": "50"},
        {"timestamp": "2026-09-01T09:34:00-04:00", "openPrice": "10.5", "highPrice": "12", "lowPrice": "10", "closePrice": "11.5", "volume": "60"},
        {"timestamp": "2026-09-01T09:35:00-04:00", "openPrice": "11.5", "highPrice": "13", "lowPrice": "11", "closePrice": "12", "volume": "70"},
        # Prior session and pre-market are not joined into today's chart.
        {"timestamp": "2026-08-29T15:55:00-04:00", "openPrice": "8", "highPrice": "8", "lowPrice": "8", "closePrice": "8"},
        {"timestamp": "2026-09-01T09:00:00-04:00", "openPrice": "8", "highPrice": "8", "lowPrice": "8", "closePrice": "8"},
    ], market="US")
    assert rows == [
        {"time": "2026-09-01T09:30:00-04:00", "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.5, "volume": 110.0},
        {"time": "2026-09-01T09:35:00-04:00", "open": 11.5, "high": 13.0, "low": 11.0, "close": 12.0, "volume": 70.0},
    ]


def test_one_day_chart_uses_toss_bootstrap_only_when_injected_and_keeps_safe_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_service, "_download", lambda symbol, range_key, interval: {
        "symbol": symbol, "range": range_key, "interval": interval,
        "series": [{"time": "2026-09-01T09:30:00-04:00", "close": 100}], "asOf": "2026-09-01T09:30:00-04:00", "provider": "yfinance",
    })
    payload = chart_service.get_chart(
        tmp_path, symbol="NVDA", range_key="1d", interval="5m", runtime=ProviderFetchRuntime(tmp_path / "cache"),
        toss_candle_loader=lambda _symbol: [
            {"timestamp": "2026-09-01T09:30:00-04:00", "openPrice": "100", "highPrice": "102", "lowPrice": "99", "closePrice": "101"},
        ],
    )
    assert payload["provider"] == "toss_open_api"
    assert payload["liveStatus"] == "available"
    assert payload["delayed"] is False
    assert payload["series"][0]["volume"] is None

    requested = []
    index = chart_service.get_chart(
        tmp_path, symbol="^KS11", range_key="1d", interval="5m", runtime=ProviderFetchRuntime(tmp_path / "index"),
        toss_candle_loader=lambda target: requested.append(target) or [
            {"timestamp": "2026-09-01T09:00:00+09:00", "openPrice": "2800", "highPrice": "2810", "lowPrice": "2795", "closePrice": "2805"},
        ],
    )
    assert requested == ["KOSPI"]
    assert index["provider"] == "toss_open_api"
    assert index["liveEligible"] is True
    assert index["realtimeEligible"] is False
    assert index["liveStatus"] == "available"

    unsupported = chart_service.get_chart(tmp_path, symbol="^GSPC", range_key="1d", interval="5m", runtime=ProviderFetchRuntime(tmp_path / "other"))
    assert unsupported["provider"] == "yfinance"
    assert unsupported["liveEligible"] is False
    assert unsupported["fallbackReason"] == "unsupported"


def test_us_timestamp_is_converted_from_kst_and_full_regular_session_has_78_bars():
    import datetime as dt

    # Official-shaped AAPL instant is 10:30 EDT, despite its +09:00 text.
    first = chart_service.aggregate_toss_1m_to_5m([
        {"timestamp": "2026-06-18T23:30:00+09:00", "openPrice": "1", "highPrice": "1", "lowPrice": "1", "closePrice": "1"},
    ], market="US")
    assert first[0]["time"] == "2026-06-18T10:30:00-04:00"
    base = dt.datetime(2026, 6, 18, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
    candles = []
    for minute in range(390):
        stamp = base + dt.timedelta(minutes=minute)
        candles.append({"timestamp": stamp.isoformat(), "openPrice": minute, "highPrice": minute + 1, "lowPrice": minute, "closePrice": minute + 0.5, "volume": 1})
    rows = chart_service.aggregate_toss_1m_to_5m(candles, market="US")
    assert len(rows) == 78
    assert rows[0]["time"] == "2026-06-18T09:30:00-04:00"
    assert rows[-1]["time"] == "2026-06-18T15:55:00-04:00"


def test_next_before_loader_deduplicates_and_stops_on_no_progress(monkeypatch):
    pages = [
        {"candles": [{"timestamp": "2026-06-18T10:00:00-04:00"}, {"timestamp": "2026-06-18T09:59:00-04:00"}], "nextBefore": "one"},
        {"candles": [{"timestamp": "2026-06-18T09:59:00-04:00"}, {"timestamp": "2026-06-18T09:58:00-04:00"}], "nextBefore": "one"},
    ]
    monkeypatch.setattr("features.common.market_data.toss_open_api.fetch_toss_candle_page", lambda *_args, **_kwargs: pages.pop(0))
    rows = chart_service.load_toss_session_pages("AAPL")
    assert [row["timestamp"] for row in rows] == ["2026-06-18T10:00:00-04:00", "2026-06-18T09:59:00-04:00", "2026-06-18T09:58:00-04:00"]
