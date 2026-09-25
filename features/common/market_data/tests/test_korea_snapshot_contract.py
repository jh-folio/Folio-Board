from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data.providers import YFinanceKoreaMarketProvider, _fetch_usdkrw


class _Series(list):
    def tolist(self):
        return list(self)


class _Frame:
    def __init__(self, rows):
        self.index = [row[0] for row in rows]
        self._close = _Series(row[1] for row in rows)
        self.empty = not rows

    def __contains__(self, key):
        return key == "Close"

    def __getitem__(self, key):
        if key == "Close":
            return self._close
        raise KeyError(key)


def _fake_yfinance(monkeypatch, rows_by_ticker):
    def ticker(symbol):
        return SimpleNamespace(history=lambda **_kwargs: _Frame(rows_by_ticker.get(symbol, [])))

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=ticker))


def test_kospi_missing_exact_previous_kr_session_is_null(monkeypatch):
    _fake_yfinance(monkeypatch, {
        "^KS11": [("2026-08-27", 6912.37), ("2026-08-31", 6820.02)],
    })

    payload = YFinanceKoreaMarketProvider().fetch_korea_market("2026-08-31")
    kospi = payload["indices"]["KOSPI"]

    assert kospi["close"] == 6820.02
    assert kospi["asOfDate"] == "2026-08-31"
    assert kospi["changePct"] is None
    assert kospi["changeComparisonDate"] == "2026-08-28"
    assert kospi["changeReason"] == "prior_session_missing"


def test_kospi_exact_previous_kr_session_uses_08_28_value(monkeypatch):
    _fake_yfinance(monkeypatch, {
        "^KS11": [
            ("2026-08-27", 6912.37),
            ("2026-08-28", 6788.88),
            ("2026-08-31", 6820.02),
        ],
    })

    payload = YFinanceKoreaMarketProvider().fetch_korea_market("2026-08-31")
    kospi = payload["indices"]["KOSPI"]

    assert kospi["changeComparisonDate"] == "2026-08-28"
    assert kospi["changeComparisonValue"] == 6788.88
    assert kospi["changePct"] == pytest.approx((6820.02 / 6788.88 - 1) * 100)
    assert kospi["changeReason"] is None
    assert kospi["priceUnit"] == "points"
    assert kospi["priceBasis"] == "unadjusted_close"


def test_yfinance_fx_retains_exact_as_of_but_has_no_row_offset_change(monkeypatch):
    _fake_yfinance(monkeypatch, {
        "USDKRW=X": [("2026-08-27", 1380.0), ("2026-08-28", 1390.0)],
    })

    fx = _fetch_usdkrw("2026-08-28")["USDKRW"]

    assert fx["asOfDate"] == "2026-08-28"
    assert fx["close"] == 1390.0
    assert fx["changePct"] is None
    assert fx["changeReason"] == "unsupported_comparison_calendar"
