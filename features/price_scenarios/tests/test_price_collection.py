import datetime as dt
from types import SimpleNamespace
import sys
import pytest

from features.price_scenarios.prices import fetch_daily_history


class Frame:
    empty = False
    columns = ["Close", "Dividends", "Stock Splits"]

    def iterrows(self):
        for date, close, split in [("2026-03-30", 100, 0), ("2026-03-31", 101, 2)]:
            yield dt.datetime.fromisoformat(date), {"Close": close, "Dividends": 0, "Stock Splits": split}


def test_collection_uses_official_kosdaq_daily_unadjusted_close_and_completed_session(monkeypatch):
    captured = {}
    class Stock:
        def history(self, **kwargs):
            captured.update(kwargs)
            return Frame()
        def get_history_metadata(self):
            return {"currency": "KRW"}
    def ticker(symbol):
        captured["symbol"] = symbol
        return Stock()
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=ticker))
    before = dt.datetime(2026, 3, 31, 6, 59, tzinfo=dt.timezone.utc)
    packet = fetch_daily_history("196170", "KR", {"corp_cls": "K"}, now=before)
    assert captured["symbol"] == "196170.KQ"
    assert captured["interval"] == "1d" and captured["auto_adjust"] is False
    assert captured["back_adjust"] is False and captured["repair"] is False
    assert captured["end"] == "2026-04-01" and captured["timeout"] == 8.0
    assert packet["price"]["sessionDate"] == "2026-03-30"
    assert packet["events"] == []  # Incomplete session cannot supply its event.
    assert packet["eventSourceState"] == "received"
    assert "fetchedAt" in packet and "fetchedAt" not in packet["price"]


def test_missing_quote_currency_does_not_use_reporting_currency(monkeypatch):
    class Stock:
        def history(self, **kwargs):
            return Frame()
        def get_history_metadata(self):
            return {}
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _: Stock()))
    with pytest.raises(ValueError, match="currency_unknown"):
        fetch_daily_history("196170", "KR", {"corp_cls": "K", "currency": "KRW"},
                            now=dt.datetime(2026, 3, 31, 8, tzinfo=dt.timezone.utc))
