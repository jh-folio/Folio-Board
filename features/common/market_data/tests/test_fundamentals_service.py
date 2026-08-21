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

    assert runtime.calls == [("yfinance", "fundamentals", {"symbol": "005930.KS", "schema": 4})]
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
    assert row["sector"] == ""


def test_quarterly_earnings_align_series_by_quarter():
    """세 계열을 분기 키로 정렬해 묶고, 없는 행은 그 계열만 빈다(6501.T의 매출처럼)."""

    class _Frame:
        empty = False
        index = ["Total Revenue", "Operating Income", "Net Income"]
        columns = ["2026-06-30", "2026-03-31"]

        class _Loc:
            _values = {
                ("Total Revenue", "2026-06-30"): 119.8, ("Total Revenue", "2026-03-31"): 109.9,
                ("Operating Income", "2026-06-30"): 40.8, ("Operating Income", "2026-03-31"): 39.7,
                ("Net Income", "2026-06-30"): 112.2, ("Net Income", "2026-03-31"): 62.6,
            }

            def __getitem__(self, key):
                return self._values[key]

        loc = _Loc()

    class _Ticker:
        quarterly_income_stmt = _Frame()

    rows = fundamentals_service._quarterly_earnings(_Ticker())

    assert [row["quarter"] for row in rows] == ["2026-03-31", "2026-06-30"]
    latest = rows[-1]
    assert (latest["revenue"], latest["operatingIncome"], latest["netIncome"]) == (119.8, 40.8, 112.2)
    # 재무·현금흐름 계열은 이 픽스처에 없다 — 없는 계열은 그 분기에서 None이다.
    assert latest["totalDebt"] is None and latest["freeCashFlow"] is None


def test_quarterly_earnings_survive_missing_statement():
    class _Ticker:
        @property
        def quarterly_income_stmt(self):
            raise RuntimeError("no statement")

    assert fundamentals_service._quarterly_earnings(_Ticker()) == []


def test_summary_translation_caches_by_text_hash(monkeypatch, tmp_path):
    """같은 원문은 한 번만 번역한다 — provider 캐시 주기에 묶으면 매일 다시 번역한다."""
    from features.common.market_data import summary_translation as st

    calls = []
    monkeypatch.setattr("features.llm_settings.client.selected_llm_config", lambda: {"enabled": True, "apiKey": "k"})
    monkeypatch.setattr(
        "features.llm_settings.client.request_llm_text",
        lambda cfg, prompt, context, **kw: calls.append(context) or "램리서치는 반도체 장비 회사다.",
    )

    first = st.translated_summary(tmp_path, "Lam Research designs equipment.")
    second = st.translated_summary(tmp_path, "Lam Research designs equipment.")

    assert first == second == "램리서치는 반도체 장비 회사다."
    assert len(calls) == 1


def test_summary_translation_falls_back_to_original(monkeypatch, tmp_path):
    from features.common.market_data import summary_translation as st

    # 키 없음 → 원문
    monkeypatch.setattr("features.llm_settings.client.selected_llm_config", lambda: {"enabled": True, "apiKey": ""})
    assert st.translated_summary(tmp_path, "Original text.") == "Original text."

    # 모델이 한국어가 아닌 답을 내면 원문을 지킨다
    monkeypatch.setattr("features.llm_settings.client.selected_llm_config", lambda: {"enabled": True, "apiKey": "k"})
    monkeypatch.setattr("features.llm_settings.client.request_llm_text", lambda *a, **kw: "I cannot translate this.")
    assert st.translated_summary(tmp_path, "Original text.") == "Original text."
