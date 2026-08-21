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

    dates = pd.bdate_range(end=dt.date.today(), periods=90)
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
