from __future__ import annotations

import pytest

from features.common.market_data import fundamentals_service


class _Runtime:
    """fetch를 그대로 실행하는 러너 — 캐시 정책은 fetch_runtime 테스트가 맡는다."""

    def __init__(self):
        self.calls = []

    def fetch(self, provider, operation, params, fetcher, *, policy=None, background_refresh=True):
        self.calls.append((provider, operation, dict(params)))
        return {"value": fetcher(), "status": "fetched", "fetchedAt": "2026-08-21T10:00:00", "fallbackReason": ""}


def test_fundamentals_keep_missing_fields_as_none(monkeypatch, tmp_path):
    """결측을 숨기지 않는다 — 삼성전자의 PER처럼 provider가 실제로 비워 두는 칸이 있다."""

    class _Ticker:
        info = {"marketCap": 2.5e12, "trailingPE": None, "returnOnEquity": 0.31, "dividendYield": 0.55, "currency": "KRW", "beta": "not-a-number"}

    monkeypatch.setattr(fundamentals_service, "_download", lambda symbol: {
        "symbol": symbol,
        **{f: None for f in fundamentals_service.FUNDAMENTAL_FIELDS},
        "marketCap": 2.5e12, "returnOnEquity": 0.31, "dividendYield": 0.55, "currency": "KRW",
    })
    runtime = _Runtime()

    payload = fundamentals_service.get_fundamentals(tmp_path, symbol="005930.ks", runtime=runtime)

    assert runtime.calls == [("yfinance", "fundamentals", {"symbol": "005930.KS"})]
    assert payload["marketCap"] == 2.5e12
    assert payload["trailingPE"] is None
    assert payload["currency"] == "KRW"
    assert payload["provider"] == "yfinance"
    assert payload["freshness"] == "fetched"


def test_fundamentals_reject_invalid_symbols(tmp_path):
    """차트와 같은 심볼 규칙이다 — 두 패널이 같은 티커 문자열을 받는다."""
    with pytest.raises(ValueError, match="chart_symbol_invalid"):
        fundamentals_service.get_fundamentals(tmp_path, symbol="<bad>", runtime=_Runtime())


def test_download_coerces_non_numbers_to_none(monkeypatch):
    class _Ticker:
        info = {"marketCap": "not-a-number", "beta": float("nan"), "trailingPE": 12.5, "currency": None}

    import sys, types

    fake = types.ModuleType("yfinance")
    fake.Ticker = lambda symbol: _Ticker()
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    row = fundamentals_service._download("AMD")

    assert row["marketCap"] is None
    assert row["beta"] is None
    assert row["trailingPE"] == 12.5
    assert row["currency"] == ""
