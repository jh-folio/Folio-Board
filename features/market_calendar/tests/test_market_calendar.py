from __future__ import annotations

import sqlite3

import pytest

from features.market_calendar.schema import KINDS, normalize_event
from features.market_calendar.service import list_events, upsert_events


def event(**overrides):
    value = {
        "id": "fed-fomc-2026-09",
        "kind": "central_bank",
        "title": "FOMC decision",
        "market": "US",
        "startsAt": "2026-09-16T14:00:00-04:00",
        "timezone": "America/New_York",
        "status": "confirmed",
        "provider": "federal_reserve",
        "source": "Federal Reserve",
    }
    value.update(overrides)
    return value


def test_calendar_only_accepts_six_approved_kinds_and_valid_timezone():
    assert KINDS == {"macro", "central_bank", "holiday", "earnings", "filing", "dividend"}
    assert normalize_event(event())["startsAt"].endswith("-04:00")
    with pytest.raises(ValueError, match="calendar_kind_invalid"):
        normalize_event(event(kind="personal_research"))
    with pytest.raises(ValueError, match="calendar_timezone_invalid"):
        normalize_event(event(timezone="Mars/Olympus"))


def test_update_and_cancellation_keep_provider_identity(tmp_path):
    db = tmp_path / "market-memory.sqlite3"
    assert upsert_events(db, [event()]) == 1
    assert upsert_events(db, [event(startsAt="2026-09-16T14:30:00-04:00", cancelled=True, updatedAt="2026-09-15T12:00:00Z")]) == 1
    result = list_events(db)
    assert result["count"] == 1
    assert result["events"][0]["cancelled"] is True
    assert result["events"][0]["startsAt"].endswith("14:30:00-04:00")


def test_additive_table_migration_preserves_existing_rows(tmp_path):
    db = tmp_path / "market-memory.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE market_calendar_events (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, market TEXT NOT NULL,
            country TEXT NOT NULL, tickers_json TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
            timezone TEXT NOT NULL, all_day INTEGER NOT NULL, status TEXT NOT NULL, importance INTEGER NOT NULL,
            source TEXT NOT NULL, source_url TEXT NOT NULL, as_of TEXT NOT NULL, fetched_at TEXT NOT NULL,
            provider TEXT NOT NULL, parser_version TEXT NOT NULL)"""
        )
        conn.execute(
            "INSERT INTO market_calendar_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("old", "macro", "CPI", "US", "US", "[]", "2026-09-01T00:00:00+00:00", "", "UTC", 0, "actual", 3, "FRED", "", "", "", "fred", "0.3"),
        )
        conn.commit()
    upsert_events(db, [event()])
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM market_calendar_events").fetchone()[0] == 2
        columns = {row[1] for row in conn.execute("PRAGMA table_info(market_calendar_events)")}
    assert {"cancelled", "updated_at"} <= columns



def test_official_holidays_are_confirmed_all_day_and_kind_holiday():
    from features.market_calendar.adapters.exchange import official_holiday_events

    events = official_holiday_events([2026])
    # NYSE 10 + KRX 15(제9회 전국동시지방선거 포함, 9/28은 대체휴일이 아니라 제외) + 유럽 5개 venue 32 + JPX 19
    assert len(events) == 76
    assert all(event["kind"] == "holiday" for event in events)
    assert all(event["status"] == "confirmed" for event in events)
    assert all(event["allDay"] for event in events)
    assert all(event["sourceUrl"] for event in events)
    markets = {event["market"] for event in events}
    assert markets == {"US", "KR", "EUROPE", "JP"}


def test_europe_holidays_are_emitted_per_venue_not_per_region():
    """London can be shut while Frankfurt trades; one regional entry would lie."""
    from features.market_calendar.adapters.exchange import overseas_holiday_events

    events = overseas_holiday_events([2026])
    europe = [event for event in events if event["market"] == "EUROPE"]
    assert {event["provider"] for event in europe} == {"lse", "xetra", "euronext", "borsa_italiana", "bme"}
    assert {event["country"] for event in europe} == {"GB", "DE", "FR", "IT", "ES"}

    # 영국 여름 은행휴일은 런던만 닫는다.
    august = [event for event in europe if event["startsAt"].startswith("2026-08-31")]
    assert [event["provider"] for event in august] == ["lse"]


def test_holiday_tables_never_place_a_closure_on_a_weekend():
    """A Saturday closure entry would show up in the calendar as a fake event."""
    import datetime as dt

    from features.market_calendar.adapters.exchange import overseas_holiday_events

    for event in overseas_holiday_events([2026]):
        day = dt.date.fromisoformat(event["startsAt"][:10])
        assert day.weekday() < 5, event["title"]


def test_a_year_without_a_transcribed_table_contributes_nothing():
    from features.market_calendar.adapters.exchange import overseas_holiday_events

    assert overseas_holiday_events([2030]) == []


def test_ecb_boe_and_boj_2026_each_have_eight_decisions():
    from features.market_calendar.adapters.central_banks import official_central_bank_events

    events = official_central_bank_events([2026])
    assert all(event["kind"] == "central_bank" for event in events)
    assert all(event["status"] == "confirmed" for event in events)
    assert all(event["sourceUrl"] for event in events)

    by_provider = {}
    for event in events:
        by_provider.setdefault(event["provider"], []).append(event)
    assert len(by_provider["ecb"]) == 8
    assert len(by_provider["bank_of_england"]) == 8
    # BOJ는 2일 회의라 1일차와 결과 발표가 각각 남는다.
    assert len([e for e in by_provider["bank_of_japan"] if "결과" in e["title"]]) == 8

    assert {e["market"] for e in by_provider["ecb"]} == {"EUROPE"}
    assert {e["market"] for e in by_provider["bank_of_japan"]} == {"JP"}
    # 유럽은 통화정책 주체가 둘이다. ECB는 유로존, BoE는 영국을 각각 가리켜야 한다.
    assert {e["country"] for e in by_provider["ecb"]} == {"EU"}
    assert {e["country"] for e in by_provider["bank_of_england"]} == {"GB"}


def test_central_bank_tables_expire_instead_of_extrapolating():
    from features.market_calendar.adapters.central_banks import official_central_bank_events

    assert official_central_bank_events([2030]) == []


def test_official_fomc_2026_has_eight_statement_events_with_et_time():
    from features.market_calendar.adapters.fed import official_fomc_events

    events = official_fomc_events([2026])
    statements = [event for event in events if "성명서" in event["title"]]
    assert len(statements) == 8
    assert all(event["kind"] == "central_bank" for event in events)
    assert all(event["status"] == "confirmed" for event in events)
    assert all(event["timezone"] == "America/New_York" for event in statements)
    assert all(event["importance"] == 3 for event in statements)


def test_fred_macro_fetch_returns_empty_without_key():
    from features.market_calendar.adapters.fred import fetch_fred_macro_events

    assert fetch_fred_macro_events("", start="2026-08-01", end="2026-09-30") == []


def test_calendar_target_tickers_include_watchlist(tmp_path, monkeypatch):
    import json

    from features.market_calendar import service as calendar_service

    (tmp_path / "portfolio.json").write_text(json.dumps({"positions": [{"ticker": "NVDA", "quantity": 1}], "cash": []}), encoding="utf-8")
    (tmp_path / "watchlist.json").write_text(json.dumps(["AAPL"]), encoding="utf-8")
    monkeypatch.setattr("features.portfolio.service.PORTFOLIO_PATH", tmp_path / "portfolio.json")
    tickers = calendar_service._calendar_target_tickers(tmp_path)
    assert "NVDA" in tickers
    assert "AAPL" in tickers


def test_estimated_events_use_listing_market_not_hardcoded_us():
    """KRX 티커가 US/ET로 저장되면 market=KR 필터에서 사라지고 US에 잘못 뜬다."""
    from features.market_calendar.adapters._ticker_market import market_for_ticker

    assert market_for_ticker("NVDA") == ("US", "America/New_York")
    assert market_for_ticker("BRK-B") == ("US", "America/New_York")
    assert market_for_ticker("005930.KS") == ("KR", "Asia/Seoul")
    assert market_for_ticker("247540.KQ") == ("KR", "Asia/Seoul")
    assert market_for_ticker("005930.ks") == ("KR", "Asia/Seoul")
