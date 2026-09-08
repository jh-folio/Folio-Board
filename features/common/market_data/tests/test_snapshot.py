"""Pure market snapshot return contracts."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data.snapshot import (
    _period_start_date,
    calculate_price_returns,
    fetch_market_snapshot,
    snapshot_cutoff_date,
)


AS_OF = dt.date(2026, 8, 28)


def test_returns_normalize_sort_dedupe_and_ignore_nonfinite_or_future_rows():
    result = calculate_price_returns(
        [
            ("2026-08-28", 104),
            ("2026-08-27", 103),
            ("2026-08-26", 102),
            ("2026-08-25", 101),
            ("2026-08-25", 101),  # identical duplicate collapses
            ("2026-08-26", float("nan")),
            ("2026-09-01", 999),
        ],
        "BTC-USD",
        as_of_date=AS_OF,
    )

    assert result["last"] == 104.0
    assert result["asOfDate"] == "2026-08-28"
    assert result["periodStartDate"] == "2026-08-25"
    assert result["oneDayComparisonDate"] == "2026-08-27"
    assert result["oneDayComparisonValue"] == 103.0
    assert result["oneDayPct"] == pytest.approx((104 / 103 - 1) * 100)
    assert result["dataQualityReasons"] == [
        "duplicate_bar_date",
        "nonfinite_close_ignored",
        "conflicting_duplicate_bar",
        "future_bar_ignored",
    ]


def test_conflicting_duplicate_comparison_date_is_invalid():
    result = calculate_price_returns(
        [("2026-08-27", 103), ("2026-08-27", 999), ("2026-08-28", 104)],
        "BTC-USD",
        as_of_date=AS_OF,
    )

    assert result["oneDayComparisonDate"] == "2026-08-27"
    assert result["oneDayPct"] is None
    assert result["oneDayReason"] == "prior_observation_missing"
    assert "conflicting_duplicate_bar" in result["dataQualityReasons"]


def test_equity_returns_use_exact_us_sessions_not_row_positions():
    result = calculate_price_returns(
        [(day.isoformat(), 100 + i) for i, day in enumerate(
            [
                dt.date(2026, 8, 17),
                dt.date(2026, 8, 18),
                dt.date(2026, 8, 19),
                dt.date(2026, 8, 20),
                dt.date(2026, 8, 21),
                dt.date(2026, 8, 24),
            ]
        )],
        "SPY",
        as_of_date=AS_OF,
    )

    assert result["oneDayComparisonDate"] == "2026-08-21"
    assert result["fiveDayComparisonDate"] == "2026-08-17"
    assert result["fiveDayComparisonValue"] == 100.0
    assert result["oneDayPct"] == (105 / 104 - 1) * 100
    assert result["fiveDayPct"] == (105 / 100 - 1) * 100


def test_arbitrary_us_stock_uses_shared_session_calculation():
    result = calculate_price_returns(
        [("2026-08-27", 227.98), ("2026-08-28", 217.55), ("2026-08-31", 220.78)],
        "NVDA",
        as_of_date=dt.date(2026, 8, 31),
    )

    assert result["oneDayComparisonDate"] == "2026-08-28"
    assert result["oneDayPct"] == pytest.approx((220.78 / 217.55 - 1) * 100)
    assert result["oneDayComparisonValue"] == 217.55


def test_missing_exact_prior_session_is_null_with_reason():
    result = calculate_price_returns(
        [(day.isoformat(), 100 + i) for i, day in enumerate(
            [
                dt.date(2026, 8, 17),
                dt.date(2026, 8, 18),
                dt.date(2026, 8, 19),
                dt.date(2026, 8, 20),
                # 2026-08-21 is intentionally missing
                dt.date(2026, 8, 24),
            ]
        )],
        "SPY",
        as_of_date=AS_OF,
    )

    assert result["oneDayComparisonDate"] == "2026-08-21"
    assert result["oneDayPct"] is None
    assert result["oneDayReason"] == "prior_session_missing"
    assert result["fiveDayPct"] is None
    assert result["fiveDayReason"] == "session_bar_missing"


def test_holiday_rows_do_not_become_a_stock_session():
    result = calculate_price_returns(
        [("2026-07-02", 100), ("2026-07-03", 101), ("2026-07-06", 102)],
        "SPY",
        as_of_date=dt.date(2026, 7, 6),
    )

    assert result["oneDayComparisonDate"] == "2026-07-02"
    assert result["oneDayPct"] == pytest.approx(2.0)
    assert "holiday_bar_ignored" in result["dataQualityReasons"]


def test_unknown_calendar_does_not_weekday_fallback(monkeypatch):
    def unknown_calendar(_day, _market, _fetcher=None):
        return {"source": "unavailable", "isOpen": False}

    monkeypatch.setattr(
        "features.common.market_data.snapshot.market_open_status",
        unknown_calendar,
    )

    result = calculate_price_returns(
        [("2026-08-27", 100), ("2026-08-28", 101)],
        "SPY",
        as_of_date=AS_OF,
    )

    assert result["oneDayPct"] is None
    assert result["fiveDayPct"] is None
    assert result["oneDayReason"] == "calendar_unavailable"
    assert result["fiveDayReason"] == "calendar_unavailable"


def test_five_session_calendar_failure_does_not_erase_valid_one_day(monkeypatch):
    def partial_calendar(day, _market, _fetcher=None):
        if day <= dt.date(2026, 8, 17):
            return {"source": "unavailable", "isOpen": False}
        return {"source": "static", "isOpen": True}

    monkeypatch.setattr(
        "features.common.market_data.snapshot.market_open_status",
        partial_calendar,
    )
    result = calculate_price_returns(
        [(day.isoformat(), 100 + i) for i, day in enumerate(
            [
                dt.date(2026, 8, 17),
                dt.date(2026, 8, 18),
                dt.date(2026, 8, 19),
                dt.date(2026, 8, 20),
                dt.date(2026, 8, 21),
                dt.date(2026, 8, 24),
            ]
        )],
        "SPY",
        as_of_date=AS_OF,
    )

    assert result["oneDayPct"] == pytest.approx((105 / 104 - 1) * 100)
    assert result["oneDayReason"] is None
    assert result["fiveDayPct"] is None
    assert result["fiveDayReason"] == "calendar_unavailable"


def test_non_equity_assets_do_not_call_stock_calendar(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("stock calendar must not be used for crypto")

    monkeypatch.setattr("features.common.market_data.snapshot.market_open_status", fail_if_called)
    result = calculate_price_returns(
        [(f"2026-08-{day:02d}", day) for day in range(23, 29)],
        "BTC-USD",
        as_of_date=AS_OF,
    )

    assert result["oneDayPct"] == pytest.approx((28 / 27 - 1) * 100)
    assert result["fiveDayPct"] == pytest.approx((28 / 23 - 1) * 100)


def test_arbitrary_fx_suffix_is_not_classified_as_us_stock(monkeypatch):
    monkeypatch.setattr(
        "features.common.market_data.snapshot.market_open_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no stock calendar")),
    )
    result = calculate_price_returns(
        [("2026-08-27", 100), ("2026-08-28", 101)],
        "EURUSD=X",
        as_of_date=AS_OF,
    )
    assert result["oneDayPct"] is None
    assert result["fiveDayPct"] is None
    assert result["oneDayReason"] == "unsupported_comparison_calendar"


def test_arbitrary_future_suffix_is_not_classified_as_us_stock(monkeypatch):
    monkeypatch.setattr(
        "features.common.market_data.snapshot.market_open_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no stock calendar")),
    )
    result = calculate_price_returns(
        [("2026-08-27", 100), ("2026-08-28", 101)],
        "NG=F",
        as_of_date=AS_OF,
    )
    assert result["oneDayPct"] is None
    assert result["fiveDayPct"] is None
    assert result["fiveDayReason"] == "unsupported_comparison_calendar"


def test_arbitrary_crypto_suffix_uses_exact_calendar_dates_without_stock_calendar(monkeypatch):
    monkeypatch.setattr(
        "features.common.market_data.snapshot.market_open_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no stock calendar")),
    )
    result = calculate_price_returns(
        [(f"2026-08-{day:02d}", day) for day in range(23, 29)],
        "ETH-USD",
        as_of_date=AS_OF,
    )
    assert result["oneDayPct"] == pytest.approx((28 / 27 - 1) * 100)
    assert result["fiveDayPct"] == pytest.approx((28 / 23 - 1) * 100)


def test_unknown_market_does_not_guess_a_stock_calendar(monkeypatch):
    monkeypatch.setattr(
        "features.common.market_data.snapshot.market_open_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("no stock calendar")),
    )
    result = calculate_price_returns(
        [("2026-08-27", 100), ("2026-08-28", 101)],
        "NVDA",
        market="UNKNOWN",
        as_of_date=AS_OF,
    )
    assert result["oneDayPct"] is None
    assert result["oneDayReason"] == "unsupported_comparison_calendar"


def test_sparse_bitcoin_requires_exact_calendar_dates():
    result = calculate_price_returns(
        [("2026-08-23", 100), ("2026-08-25", 102), ("2026-08-28", 105)],
        "BTC-USD",
        as_of_date=AS_OF,
    )

    assert result["oneDayComparisonDate"] == "2026-08-27"
    assert result["oneDayPct"] is None
    assert result["oneDayReason"] == "prior_observation_missing"
    assert result["fiveDayComparisonDate"] == "2026-08-23"
    assert result["fiveDayPct"] == pytest.approx(5.0)


def test_fx_keeps_period_but_makes_no_row_offset_claim():
    result = calculate_price_returns(
        [("2026-08-27", 100), ("2026-08-28", 101)],
        "DX-Y.NYB",
        as_of_date=AS_OF,
    )

    assert result["periodPct"] == pytest.approx(1.0)
    assert result["oneDayPct"] is None
    assert result["fiveDayPct"] is None
    assert result["oneDayReason"] == "unsupported_comparison_calendar"


def test_pct_change_overflow_is_null():
    result = calculate_price_returns(
        [("2026-08-27", 1e-300), ("2026-08-28", 1e308)],
        "BTC-USD",
        as_of_date=AS_OF,
    )

    assert result["periodPct"] is None
    assert result["oneDayPct"] is None


def test_historical_snapshot_requests_a_cutoff_range_and_discards_future_rows(monkeypatch):
    calls = []

    class Frame:
        empty = False
        index = [
            dt.datetime(2026, 8, 28),
            dt.datetime(2026, 9, 4),
        ]

        def __contains__(self, key):
            return key == "Close"

        def __getitem__(self, key):
            class Column(list):
                def tolist(self):
                    return list(self)
            return Column([100.0, 999.0]) if key == "Close" else Column()

    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            calls.append((self.symbol, kwargs))
            return Frame()

    class YF:
        @staticmethod
        def Ticker(symbol):
            return Ticker(symbol)

    monkeypatch.setitem(sys.modules, "yfinance", YF)
    result = fetch_market_snapshot(as_of_date=AS_OF)
    assert result["ok"] is True
    assert calls
    assert all("period" not in kwargs for _, kwargs in calls)
    assert all(kwargs["start"] == "2026-07-18" and kwargs["end"] == "2026-08-29" for _, kwargs in calls)
    assert all(row.get("asOfDate") == "2026-08-28" for row in result["tickers"].values() if not row.get("error"))
    assert result["tickers"]["SPY"]["oneDayComparisonValue"] is None
    assert result["tickers"]["SPY"]["comparisonSource"] == "yfinance"
    assert result["tickers"]["SPY"]["priceUnit"] == "USD"
    assert result["tickers"]["SPY"]["priceBasis"] == "unadjusted_close"


def test_period_return_ignores_comparison_warmup_rows():
    result = calculate_price_returns(
        [("2026-07-20", 50), ("2026-07-28", 100), ("2026-08-28", 110)],
        "BTC-USD",
        as_of_date=AS_OF,
        period_start_date="2026-07-28",
    )
    assert result["periodStartDate"] == "2026-07-28"
    assert result["periodPct"] == pytest.approx(10.0)


def test_period_boundaries_use_calendar_month_year_and_ytd_semantics():
    cutoff = dt.date(2026, 8, 31)
    assert _period_start_date(cutoff, "1mo") == dt.date(2026, 7, 31)
    assert _period_start_date(cutoff, "3mo") == dt.date(2026, 5, 31)
    assert _period_start_date(cutoff, "1y") == dt.date(2025, 8, 31)
    assert _period_start_date(cutoff, "ytd") == dt.date(2026, 1, 1)
    assert _period_start_date(cutoff, "max") == dt.date(1970, 1, 1)
    assert _period_start_date(cutoff, "bogus") is None


def test_snapshot_cutoff_is_shared_for_daily_and_weekly_consumers():
    class Window:
        week_end = "2026-08-30"

    assert snapshot_cutoff_date("2026-09-04", {"usRegularSessionDate": "2026-09-04"}) == "2026-09-04"
    assert snapshot_cutoff_date("2026-09-04", {"usRegularSessionDate": "2026-09-04"}, "weekly", Window()) == "2026-08-30"
