"""한국 지표는 **관측월이 끝난 뒤** 발표된다.

예전 어댑터는 관측월의 15일 08:00을 발표 시각으로 만들었다. 실측(2026-09-27) DB에는
7월 CPI가 "7월 15일 발표됨"으로, 기준금리 "결정"이 매달 15일(광복절 포함)로 있었다.
PPI는 ECOS에 없는 통계표 코드를 물어 한 번도 들어오지 않았다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3

import pytest

from features.market_calendar.adapters import bok


def _ecos_payload(stat_code: str, months: list[tuple[str, str]]) -> bytes:
    return json.dumps({"StatisticSearch": {"row": [
        {"STAT_CODE": stat_code, "TIME": time, "DATA_VALUE": value, "UNIT_NAME": "2020=100"}
        for time, value in months
    ]}}).encode("utf-8")


@pytest.fixture
def ecos(monkeypatch):
    """ECOS 응답을 통계표별로 흉내 내고, 실제로 물어본 통계표를 기록한다."""
    asked: list[str] = []
    responses = {
        "901Y009": _ecos_payload("901Y009", [("202606", "119.50"), ("202607", "119.77"), ("202608", "120.05")]),
        "404Y014": _ecos_payload("404Y014", [("202607", "129.38"), ("202608", "129.64")]),
    }

    def fake_urlopen(url, timeout=0):
        # .../StatisticSearch/KEY/json/kr/1/20/<통계표>/<주기>/...
        stat_code = url.split("/json/kr/1/20/", 1)[1].split("/", 1)[0]
        asked.append(stat_code)
        if stat_code not in responses:
            raise OSError("unknown table")
        return io.BytesIO(responses[stat_code])

    monkeypatch.setattr(bok.urllib.request, "urlopen", fake_urlopen)
    return asked


def test_release_date_is_always_in_the_following_month():
    for month in range(1, 13):
        observed = dt.date(2026, month, 1)
        released = bok.release_date(observed, 2)
        assert released > dt.date(2026, month, 28), "관측월이 끝나기 전에 발표될 수 없다"
    assert bok.release_date(dt.date(2026, 12, 1), 2) == dt.date(2027, 1, 2)


def test_observed_values_land_after_their_month_as_all_day_rows(ecos):
    rows = bok.fetch_bok_macro_events("KEY", start="2026-07-01", end="2026-10-31")
    actual = [r for r in rows if r["status"] == "actual"]
    assert actual, "관측값이 결과로 실려야 한다"
    for row in actual:
        observed = dt.date(int(row["observedAt"][:4]), int(row["observedAt"][4:]), 1)
        assert dt.date.fromisoformat(row["startsAt"]) > bok._add_months(observed, 1) - dt.timedelta(days=1)
        # 공식 발표 시각 근거가 없으므로 시각을 지어내지 않는다.
        assert row["allDay"] is True

    cpi = {r["observedAt"]: r for r in actual if "CPI" in r["title"]}
    assert cpi["202607"]["startsAt"] == "2026-08-02"
    assert cpi["202608"]["startsAt"] == "2026-09-02"
    assert cpi["202608"]["previousValue"] == "119.77"


def test_projected_releases_are_estimated_and_follow_the_last_observation(ecos):
    rows = bok.fetch_bok_macro_events("KEY", start="2026-07-01", end="2026-10-31")
    projected = sorted(r["startsAt"] for r in rows if r["status"] == "estimated" and "CPI" in r["title"])
    # 8월까지 관측됐으니 다음은 9월분(10/2)이다. 9/15 같은 관측월 중순 날짜는 없다.
    assert projected == ["2026-10-02"]
    assert all(r["actualValue"] == "" for r in rows if r["status"] == "estimated")


def test_ppi_uses_the_ecos_table_that_exists(ecos):
    rows = bok.fetch_bok_macro_events("KEY", start="2026-07-01", end="2026-10-31")
    assert "404Y014" in ecos
    assert "901Y014" not in ecos
    ppi = [r for r in rows if "PPI" in r["title"] and r["status"] == "actual"]
    assert [r["startsAt"] for r in ppi] == ["2026-08-18", "2026-09-18"]


def test_ecos_no_longer_invents_base_rate_decisions(ecos):
    rows = bok.fetch_bok_macro_events("KEY", start="2026-01-01", end="2026-12-31")
    assert "722Y001" not in ecos
    assert all(r["kind"] == "macro" for r in rows)
    assert not any("기준금리" in r["title"] for r in rows)


def test_bok_rate_decisions_come_from_the_published_schedule():
    from features.market_calendar.adapters.central_banks import official_central_bank_events

    events = [e for e in official_central_bank_events([2026]) if e["provider"] == "bank_of_korea"]
    assert len(events) == 8, "금통위 통화정책방향 결정회의는 연 8회다"
    assert all(e["status"] == "confirmed" and e["allDay"] for e in events)
    assert {e["market"] for e in events} == {"KR"}
    assert all("bok.or.kr" in e["sourceUrl"] for e in events)
    assert "2026-08-15" not in {e["startsAt"] for e in events}
    assert official_central_bank_events([2030]) == []


def test_legacy_mid_month_rows_are_pruned_but_others_stay(tmp_path):
    from features.market_calendar.service import prune_legacy_bok_rows, upsert_events

    db = tmp_path / "market-memory.sqlite3"
    legacy = bok.normalize_bok_events([
        {"title": "한국 소비자물가지수 (CPI)", "market": "KR", "kind": "macro", "status": "actual",
         "startsAt": "2026-07-15T08:00:00", "timezone": "Asia/Seoul", "observedAt": "202607"},
        {"title": "한국은행 기준금리 결정", "market": "KR", "kind": "central_bank", "status": "estimated",
         "startsAt": "2026-10-15T08:00:00", "timezone": "Asia/Seoul"},
    ])
    current = bok.normalize_bok_events([
        {"title": "한국 소비자물가지수 (CPI)", "market": "KR", "kind": "macro", "status": "actual",
         "startsAt": "2026-08-02", "allDay": True, "timezone": "Asia/Seoul", "observedAt": "202607"},
    ])
    other = [{"kind": "central_bank", "provider": "ecb", "title": "ECB", "status": "confirmed",
              "startsAt": "2026-09-10T14:15:00", "timezone": "Europe/Berlin"}]
    upsert_events(db, [*legacy, *current, *other])

    assert prune_legacy_bok_rows(db) == 2
    with sqlite3.connect(str(db)) as conn:
        left = conn.execute("SELECT provider, starts_at FROM market_calendar_events ORDER BY provider").fetchall()
    assert left == [("bok", "2026-08-02"), ("ecb", "2026-09-10T14:15:00+02:00")]
    # 두 번째 수집에서는 지울 것이 없다.
    assert prune_legacy_bok_rows(db) == 0
