"""날짜가 틀린 옛 한국 지표 행은 **지우지 않고 읽을 때 뺀다**.

옛 ECOS 어댑터는 관측월 15일 08:00 KST에 행을 만들었다. 실측(2026-09-27) 사용자 DB에는
그런 행이 8개 있었다. 대체 행이 생길 수 없는 기준금리 "결정"·옛 예정일·45일 창 밖의 과거 값이
섞여 있어서, 대체 행이 확인된 경우에만 지우는 방식으로는 8개 중 7개가 화면에 남았다.
"""
from __future__ import annotations

import sqlite3

import pytest

from features.market_calendar.adapters.bok import normalize_bok_events
from features.market_calendar.schema import normalize_event
from features.market_calendar.service import list_events, upsert_events

# 실제 사용자 DB에 있던 옛 행 8개(제목·시각·상태·관측월).
REAL_LEGACY = [
    ("central_bank", "한국은행 기준금리 결정", "2026-07-15T08:00:00", "actual", "202607", "2.75"),
    ("macro", "한국 소비자물가지수 (CPI)", "2026-07-15T08:00:00", "actual", "202607", "119.77"),
    ("central_bank", "한국은행 기준금리 결정", "2026-08-15T08:00:00", "actual", "202608", "3"),
    ("macro", "한국 소비자물가지수 (CPI)", "2026-08-15T08:00:00", "actual", "202608", "120.05"),
    ("central_bank", "한국은행 기준금리 결정", "2026-09-15T08:00:00", "estimated", "", ""),
    ("macro", "한국 소비자물가지수 (CPI)", "2026-09-15T08:00:00", "estimated", "", ""),
    ("central_bank", "한국은행 기준금리 결정", "2026-10-15T08:00:00", "estimated", "", ""),
    ("macro", "한국 소비자물가지수 (CPI)", "2026-10-15T08:00:00", "estimated", "", ""),
]


def legacy_rows():
    return normalize_bok_events([
        {"kind": kind, "title": title, "market": "KR", "startsAt": starts, "timezone": "Asia/Seoul",
         "status": status, "observedAt": observed, "actualValue": value}
        for kind, title, starts, status, observed, value in REAL_LEGACY
    ])


def current_cpi(**extra):
    return normalize_bok_events([{
        "kind": "macro", "title": "한국 소비자물가지수 (CPI)", "market": "KR", "startsAt": "2026-09-02",
        "allDay": True, "timezone": "Asia/Seoul", "status": "estimated", "observedAt": "202608",
        "actualValue": "120.05", "unit": "2020=100", **extra,
    }])[0]


def stored_ids(db):
    with sqlite3.connect(db) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM market_calendar_events")}


def test_all_eight_real_legacy_rows_are_hidden_but_kept(tmp_path):
    db = tmp_path / "market-memory.sqlite3"
    legacy = legacy_rows()
    upsert_events(db, [*legacy, current_cpi()])

    shown = {event["id"] for event in list_events(db)["events"]}
    assert shown == {current_cpi()["id"]}
    # 저장소에는 그대로 남는다. 되돌리려면 조건만 바꾸면 된다.
    assert {row["id"] for row in legacy} <= stored_ids(db)


def test_rows_that_only_resemble_the_legacy_format_stay_visible(tmp_path):
    db = tmp_path / "market-memory.sqlite3"
    lookalikes = [
        # 시각이 다르다.
        *normalize_bok_events([{"kind": "macro", "title": "한국 소비자물가지수 (CPI)", "market": "KR",
                                "startsAt": "2026-07-15T09:00:00", "timezone": "Asia/Seoul", "status": "actual"}]),
        # 다른 parser가 만든 행이다.
        *normalize_bok_events([{"kind": "macro", "title": "한국 소비자물가지수 (CPI)", "market": "KR",
                                "startsAt": "2026-06-15T08:00:00", "timezone": "Asia/Seoul", "status": "actual",
                                "parserVersion": "0.7.0"}]),
        # 같은 시각이지만 다른 provider다.
        normalize_event({"kind": "macro", "provider": "yfinance_economic", "title": "KR CPI Growth YY", "market": "KR",
                         "startsAt": "2026-07-15T08:00:00", "timezone": "Asia/Seoul", "status": "estimated"}),
        # 한은 공시 회의 일정은 종일 행이다.
        normalize_event({"kind": "central_bank", "provider": "bank_of_korea", "title": "한국은행 기준금리 결정 (통화정책방향 결정회의)",
                         "market": "KR", "startsAt": "2026-10-22", "allDay": True, "timezone": "Asia/Seoul", "status": "confirmed"}),
        current_cpi(),
    ]
    upsert_events(db, lookalikes)
    assert {event["id"] for event in list_events(db)["events"]} == {row["id"] for row in lookalikes}


def test_weekly_and_market_filters_use_the_same_rule(tmp_path):
    db = tmp_path / "market-memory.sqlite3"
    upsert_events(db, [*legacy_rows(), current_cpi()])
    kr = list_events(db, start="2026-07-01", end="2026-10-31T23:59:59+09:00", market="KR", kinds=["macro", "central_bank"])
    assert [event["startsAt"] for event in kr["events"]] == ["2026-09-02"]


def test_dashboard_preview_hides_legacy_rows(tmp_path):
    from features.dashboard.service import _calendar_refs

    db = tmp_path / "market-memory.sqlite3"
    future_legacy = normalize_bok_events([{"kind": "central_bank", "title": "한국은행 기준금리 결정", "market": "KR",
                                           "startsAt": "2099-10-15T08:00:00", "timezone": "Asia/Seoul", "status": "estimated"}])
    upsert_events(db, [*future_legacy, current_cpi(startsAt="2099-10-02")])
    assert [row["starts_at"] for row in _calendar_refs(db)] == ["2099-10-02"]


@pytest.mark.parametrize("case", ["no_key", "timeout", "fresh_rows"])
def test_refresh_never_deletes_legacy_rows(tmp_path, monkeypatch, case):
    import features.llm_settings.client as settings
    import features.market_calendar.service as service

    db = tmp_path / "market-memory.sqlite3"
    legacy = legacy_rows()
    upsert_events(db, legacy)
    monkeypatch.setattr(service, "_calendar_target_tickers", lambda _: [])
    for name in ("local_filing_events", "official_holiday_events", "official_fomc_events", "official_central_bank_events"):
        monkeypatch.setattr(service, name, lambda *a, **k: [])
    monkeypatch.setattr(service, "fetch_yf_economic_events", lambda **k: [])
    monkeypatch.setattr(settings, "fred_api_key", lambda: "")
    monkeypatch.setattr(settings, "bok_api_key", lambda: "" if case == "no_key" else "test")
    if case == "timeout":
        import features.market_calendar.adapters.bok as bok
        monkeypatch.setattr(bok.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    else:
        monkeypatch.setattr(service, "fetch_bok_macro_events", lambda *a, **k: [current_cpi()] if case == "fresh_rows" else [])

    result = service.refresh_calendar(tmp_path, include_estimates=False)
    assert result["agentCalled"] is False
    assert {row["id"] for row in legacy} <= stored_ids(db)
    # 지우지 않으므로 백업도 만들지 않는다.
    assert not (tmp_path / "backups").exists()


def test_display_projection_only_collapses_exact_numeric_readings(tmp_path):
    exact = current_cpi(provider="yfinance_economic", title="KR CPI Index", observedAt="2026-08-01")
    exact = normalize_event({**exact, "provider": "yfinance_economic", "id": ""})
    different = normalize_event({**exact, "unit": "%", "actualValue": "2.3", "id": "different-unit"})
    unknown = normalize_event({**exact, "title": "KR Consumer Price Index", "observedAt": "", "id": ""})
    db = tmp_path / "market-memory.sqlite3"
    upsert_events(db, [current_cpi(), exact, different, unknown])
    before = stored_ids(db)
    events = list_events(db)["events"]
    # 같은 개념·기간·단위·값·날짜인 한 쌍만 접는다. 저장된 행은 그대로다.
    assert len(before) == 4 and len(events) == 3 and stored_ids(db) == before
    assert sum(len(event.get("additionalSources", [])) for event in events) == 1
