import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data.price_history import INDEX_UNIVERSE, _clip_rows, build_price_history


def test_regular_report_provider_requests_exact_intervals_without_extended_hours(monkeypatch):
    from types import SimpleNamespace
    from features.common.market_data.price_history import _download_yfinance_rows

    calls = []

    def history(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(empty=True)

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _: SimpleNamespace(history=history)))
    for interval in ("5m", "1h", "1d"):
        assert _download_yfinance_rows("005930.KS", start="2026-09-07", end="2026-09-08", interval=interval) == []
    assert [call["interval"] for call in calls] == ["5m", "1h", "1d"]
    assert all(call["prepost"] is False and call["auto_adjust"] is False for call in calls)
    assert all(call["start"] == "2026-09-07" and call["end"] == "2026-09-08" for call in calls)


def test_build_price_history_separates_intraday_and_daily_and_clips_session():
    calls = []

    def downloader(symbol, *, start, end, interval):
        calls.append((symbol, start, end, interval))
        if interval == "5m":
            return [
                {"time": "2026-06-19T15:55:00-04:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
                {"time": "2026-06-22T09:30:00-04:00", "open": 103, "high": 104, "low": 102, "close": 103, "volume": 12},
            ]
        if interval == "1h":
            return [
                {"time": "2026-06-18T10:30:00-04:00", "close": 98},
                {"time": "2026-06-19T15:00:00-04:00", "close": 101},
                {"time": "2026-06-20T10:00:00-04:00", "close": 999},
            ]
        return [
            {"time": "2025-06-20", "open": 80, "high": 82, "low": 79, "close": 81, "volume": 20},
            {"time": "2026-06-19", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 30},
            {"time": "2026-06-22", "open": 102, "high": 104, "low": 101, "close": 103, "volume": 40},
        ]

    result = build_price_history("^GSPC", "2026-06-19", downloader=downloader)

    assert result["intraday"]["interval"] == "5m"
    assert [row["time"] for row in result["intraday"]["points"]] == ["2026-06-19T15:55:00-04:00"]
    assert result["daily"]["interval"] == "1d"
    assert result["daily"]["points"][-1]["time"] == "2026-06-19"
    assert result["hourly"]["interval"] == "1h"
    assert [row["time"] for row in result["hourly"]["points"]] == [
        "2026-06-18T10:30:00-04:00",
        "2026-06-19T15:00:00-04:00",
    ]
    assert calls[1] == ("^GSPC", "2026-06-13", "2026-06-20", "1h")
    assert [call[-1] for call in calls] == ["5m", "1h", "1d"]


def test_build_price_history_reports_actual_provider_from_rows():
    def downloader(symbol, *, start, end, interval):
        time = "2026-06-19T15:55:00-04:00" if interval in {"5m", "1h"} else "2026-06-19"
        return [{
            "time": time,
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 10,
            "provider": "toss_open_api",
        }]

    result = build_price_history("AAPL", "2026-06-19", downloader=downloader)

    assert result["provider"] == "toss_open_api"
    assert result["sourceByInterval"] == {
        "intraday": "toss_open_api",
        "hourly": "toss_open_api",
        "daily": "toss_open_api",
    }


def test_build_price_history_appends_target_daily_bar_when_daily_feed_lags():
    def downloader(_symbol, *, start, end, interval):
        if interval == "5m":
            return [
                {"time": "2026-08-03T09:00:00+09:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10, "provider": "yfinance"},
                {"time": "2026-08-03T09:05:00+09:00", "open": 101, "high": 104, "low": 100, "close": 103, "volume": 20, "provider": "yfinance"},
            ]
        if interval == "1h":
            return []
        return [
            {"time": "2026-07-31", "open": 98, "high": 101, "low": 97, "close": 100, "volume": 50, "provider": "yfinance"},
        ]

    result = build_price_history("^KS11", "2026-08-03", downloader=downloader)

    assert result["daily"]["points"][-1] == {
        "time": "2026-08-03",
        "open": 100.0,
        "high": 104.0,
        "low": 99.0,
        "close": 103.0,
        "volume": 30.0,
        "provider": "intraday_aggregate:yfinance",
    }
    assert result["sourceByInterval"]["daily"] == "yfinance+intraday_aggregate:yfinance"
    assert result["hourly"]["points"] == []
    assert result["warnings"] == ["hourly_history_empty"]


def test_build_price_history_skips_toss_without_release_flag(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "0")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_calls = []

    def fake_toss_rows(symbol, *, start, end, interval):
        toss_calls.append((symbol, interval))
        return [{
            "time": "2026-06-19T15:55:00-04:00" if interval == "5m" else "2026-06-19",
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 10,
            "provider": "toss_open_api",
        }]

    def fake_yfinance_rows(symbol, *, start, end, interval):
        return [{
            "time": "2026-06-19T15:55:00-04:00" if interval == "5m" else "2026-06-19",
            "open": 100,
            "high": 102,
            "low": 99,
            "close": 101,
            "volume": 10,
            "provider": "yfinance",
        }]

    monkeypatch.setattr("features.common.market_data.toss_open_api.download_toss_candle_rows", fake_toss_rows)
    monkeypatch.setattr("features.common.market_data.price_history._download_yfinance_rows", fake_yfinance_rows)

    result = build_price_history("AAPL", "2026-06-19")

    assert toss_calls == []
    assert result["provider"] == "yfinance"


def test_saved_history_keeps_all_intervals_on_regular_yfinance_when_toss_is_enabled(monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "client-secret")
    toss_calls = []

    def fake_toss_rows(symbol, *, start, end, interval):
        toss_calls.append(interval)
        return [{"time": "2026-06-19T15:55:00-04:00" if interval == "5m" else "2026-06-19",
                 "close": 101, "provider": "toss_open_api"}]

    def fake_yfinance_rows(symbol, *, start, end, interval):
        time = "2026-06-19T15:00:00-04:00" if interval in {"5m", "1h"} else "2026-06-19"
        return [{"time": time, "close": 101, "provider": "yfinance"}]

    monkeypatch.setattr("features.common.market_data.toss_open_api.download_toss_candle_rows", fake_toss_rows)
    monkeypatch.setattr("features.common.market_data.price_history._download_yfinance_rows", fake_yfinance_rows)

    result = build_price_history("AAPL", "2026-06-19")

    assert toss_calls == []
    assert result["hourly"]["points"][0]["provider"] == "yfinance"
    assert result["sourceByInterval"] == {key: "yfinance" for key in ("intraday", "hourly", "daily")}
    assert result["intraday"]["points"][0]["time"] == "2026-06-19T15:00:00-04:00"


def test_build_price_history_warns_and_keeps_empty_hourly_on_failure():
    def downloader(_symbol, *, start, end, interval):
        if interval == "1h":
            raise RuntimeError("hourly provider unavailable")
        if interval == "5m":
            return [{"time": "2026-06-19T15:55:00-04:00", "close": 101}]
        return [{"time": "2026-06-19", "close": 101}]

    result = build_price_history("AAPL", "2026-06-19", downloader=downloader)

    assert result["hourly"] == {"interval": "1h", "points": []}
    assert result["warnings"] == ["hourly_history_unavailable"]


def test_index_universe_uses_exact_requested_indices():
    assert [row["ticker"] for row in INDEX_UNIVERSE["us"]] == ["^GSPC", "^IXIC", "^DJI"]
    assert [row["label"] for row in INDEX_UNIVERSE["us"]] == ["S&P 500", "Nasdaq", "Dow Jones"]
    assert [row["ticker"] for row in INDEX_UNIVERSE["kr"]] == ["^KS11", "^KQ11"]


def test_price_history_rejects_future_nonfinite_and_conflicting_daily_duplicates():
    rows = _clip_rows([
        {"time": "2026-08-27", "close": 100.0},
        {"time": "2026-08-27", "close": 101.0},  # conflicting date is invalid
        {"time": "2026-08-27", "close": 102.0},  # cannot resurrect it
        {"time": "2026-08-28", "close": float("nan")},
        {"time": "2026-08-28", "close": 103.0},  # malformed duplicate cannot resurrect
        {"time": "2026-09-01", "close": 110.0},  # future relative to target
        {"time": "malformed", "close": 90.0},
    ], __import__("datetime").date(2026, 8, 28), intraday=False)
    assert rows == []


def test_intraday_aggregate_remains_distinct_from_raw_daily_price_basis():
    def downloader(_symbol, *, start, end, interval):
        if interval == "5m":
            return [{"time": "2026-08-03T09:00:00+09:00", "close": 101.0}]
        return []

    result = build_price_history("^KS11", "2026-08-03", downloader=downloader)
    assert result["daily"]["points"][0]["provider"] == "intraday_aggregate:custom"
    assert result["intraday"]["points"][0].get("provider") != "intraday_aggregate:custom"


def test_intraday_rejects_date_only_and_duplicate_adjustment_basis_conflict():
    import datetime as dt

    rows = _clip_rows([
        {"time": "2026-08-03", "close": 100.0},  # no intraday time
        {"time": "2026-08-03T09:00:00+09:00", "close": 101.0, "priceBasis": "raw"},
        {"time": "2026-08-03T09:00:00+09:00", "close": 101.0, "priceBasis": "adjusted"},
    ], dt.date(2026, 8, 3), intraday=True)
    assert rows == []
