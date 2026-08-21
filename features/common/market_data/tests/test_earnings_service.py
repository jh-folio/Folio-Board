"""실적 패널이 없는 값을 만들어내지 않는지 확인한다.

실측(2026-08-21)으로 확인한 provider 한계가 그대로 테스트가 된다 — `earnings_history`에
매출 열이 없고, 지난 분기 매출 컨센서스는 어느 종목에도 없으며, 일부 종목(6501.T)은
분기 손익계산서에 `Total Revenue` 행 자체가 없다.
"""
from __future__ import annotations

import datetime as dt

import pytest

from features.common.market_data import earnings_service


def test_ticker_gate_matches_the_chart_api():
    assert earnings_service.normalize_ticker("lrcx") == "LRCX"
    assert earnings_service.normalize_ticker("005930.KS") == "005930.KS"
    with pytest.raises(ValueError, match="earnings_ticker_invalid"):
        earnings_service.normalize_ticker("<bad>")


def test_quarter_label_names_the_end_month_not_a_fiscal_quarter_number():
    # LRCX는 6월 결산이라 6월 분기가 회계 4분기다. 종료월만 말하면 어느 회사에서나 사실이다.
    assert earnings_service.quarter_label("2026-06-30") == "2026.06 종료 분기"
    assert earnings_service.quarter_label(dt.date(2026, 3, 31)) == "2026.03 종료 분기"
    assert earnings_service.quarter_label("없음") == ""


def test_year_ago_key_matches_by_month_not_by_index():
    # `earnings_history`가 4개만 주므로 인덱스로 4칸 뒤를 보면 최신 분기의 작년 동기가
    # 늘 비어 있다. 손익계산서는 더 뒤까지 주므로 종료월로 찾는다.
    available = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-06-30"]
    assert earnings_service.year_ago_key("2026-06-30", available) == "2025-06-30"
    # 분기 말일이 며칠 달라도 걸린다.
    assert earnings_service.year_ago_key("2026-06-28", ["2025-06-30"]) == "2025-06-30"
    assert earnings_service.year_ago_key("2026-06-30", ["2025-03-31"]) == ""
    assert earnings_service.year_ago_key("", available) == ""


class _Runtime:
    """`ProviderFetchRuntime` 자리에 끼우는 대역. 캐시 없이 곧장 부른다."""

    def __init__(self, value=None, status="fresh"):
        self._value, self._status = value, status

    def fetch(self, provider, kind, key, loader, policy=None, background_refresh=False):
        return {"value": self._value if self._value is not None else loader(), "status": self._status, "fetchedAt": "2026-08-21T00:00:00Z"}


def test_missing_revenue_and_consensus_are_named_not_hidden(tmp_path):
    # 실측 6501.T: EPS 컨센서스가 없고 `Total Revenue` 행도 없다.
    runtime = _Runtime({
        "ticker": "6501.T", "currency": "JPY",
        "next": {"date": "2026-10-29", "epsEstimate": None, "revenueEstimate": None, "status": "estimated"},
        "history": [{"quarter": "2026-06-30", "epsActual": 12.0, "revenueActual": None}],
        "provider": "yfinance", "hasRevenue": False,
    })
    payload = earnings_service.get_earnings(tmp_path, ticker="6501.T", runtime=runtime)
    assert "revenue_unavailable" in payload["warnings"]
    # 매출 컨센서스는 종목 문제가 아니라 provider 한계다. 항상 남긴다.
    assert "revenue_consensus_unavailable" in payload["warnings"]
    assert payload["next"]["status"] == "estimated"


def test_healthy_ticker_still_reports_the_missing_revenue_consensus(tmp_path):
    runtime = _Runtime({
        "ticker": "LRCX", "currency": "USD",
        "next": {"date": "2026-10-22", "epsEstimate": 2.17, "revenueEstimate": 8.1e9, "status": "estimated"},
        "history": [{"quarter": "2026-06-30", "epsActual": 1.33, "revenueActual": 5.6e9}],
        "provider": "yfinance", "hasRevenue": True,
    })
    payload = earnings_service.get_earnings(tmp_path, ticker="LRCX", runtime=runtime)
    assert payload["warnings"] == ["revenue_consensus_unavailable"]
    assert payload["freshness"] == "fresh"


def test_empty_provider_result_does_not_crash_the_panel(tmp_path):
    payload = earnings_service.get_earnings(tmp_path, ticker="ZZZZ", runtime=_Runtime({}, status="failed"))
    assert payload["history"] == []
    assert "earnings_history_unavailable" in payload["warnings"]
    assert payload["ticker"] == "ZZZZ"
