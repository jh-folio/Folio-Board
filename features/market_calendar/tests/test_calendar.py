

def test_bok_adapter_returns_empty_without_a_key():
    """키 부재는 오류가 아니라 보고되는 공백이다(FRED 어댑터와 같은 계약)."""
    from features.market_calendar.adapters.bok import fetch_bok_macro_events

    assert fetch_bok_macro_events("", start="2026-08-01", end="2026-10-01") == []
    assert fetch_bok_macro_events("   ", start="2026-08-01", end="2026-10-01") == []


def test_bok_projected_dates_are_estimated_not_confirmed():
    """ECOS는 공표 일정을 주지 않는다. 관측 이력에서 투영한 날짜를 confirmed로 쓰면 안 된다."""
    from features.market_calendar.adapters.bok import normalize_bok_events

    rows = normalize_bok_events([{
        "title": "한국 소비자물가지수 (CPI)", "market": "KR", "kind": "macro",
        "startsAt": "2026-10-02", "allDay": True, "timezone": "Asia/Seoul", "status": "estimated",
    }])
    assert rows and rows[0]["status"] == "estimated"
    assert rows[0]["provider"] == "bok"


def test_macro_coverage_gaps_name_the_missing_key_per_market():
    """지표가 비어 있을 때 '이번 주에 없음'과 '수집 불가'를 구분할 수 있어야 한다."""
    from features.market_calendar import service

    original = (service.fred_api_key if hasattr(service, "fred_api_key") else None)
    import features.llm_settings.client as client

    saved_fred, saved_bok = client.fred_api_key, client.bok_api_key
    try:
        client.fred_api_key = lambda: ""
        client.bok_api_key = lambda: ""
        gaps = service.macro_coverage_gaps()
        markets = {g["market"] for g in gaps}
        assert markets == {"US", "KR"}
        for gap in gaps:
            assert gap["requires"] in {"FRED_API_KEY", "BOK_API_KEY"}
            assert gap["message"] and gap["sourceUrl"]

        # 한쪽만 없으면 그 시장만 보고한다.
        client.fred_api_key = lambda: "present"
        assert {g["market"] for g in service.macro_coverage_gaps()} == {"KR"}
    finally:
        client.fred_api_key, client.bok_api_key = saved_fred, saved_bok
        assert original is None or True


def test_yf_economic_skips_us_unless_the_fred_fallback_is_requested():
    """FRED 키가 있으면 미국은 confirmed 경로가 담당하므로 중복을 만들지 않는다."""
    import datetime as dt
    import sys
    import types

    import pandas as pd

    from features.market_calendar.adapters import yf_economic

    stamp = dt.datetime(2026, 8, 13, 12, 30, tzinfo=dt.timezone.utc)
    frame = pd.DataFrame(
        {"Region": ["US", "JP"], "Event Time": [stamp, stamp]},
        index=["PPI Final Demand MM", "CPI, Core Nationwide YY"],
    )

    class _Calendars:
        def __init__(self, *args, **kwargs):
            pass

        def get_economic_events_calendar(self, limit=100, offset=0, **kwargs):
            return frame if offset == 0 else frame.iloc[0:0]

    fake = types.ModuleType("yfinance")
    fake.Calendars = _Calendars
    saved = sys.modules.get("yfinance")
    sys.modules["yfinance"] = fake
    try:
        without_us = yf_economic.fetch_yf_economic_events(
            start="2026-08-01", end="2026-08-31", include_us=False
        )
        with_us = yf_economic.fetch_yf_economic_events(
            start="2026-08-01", end="2026-08-31", include_us=True
        )
    finally:
        if saved is not None:
            sys.modules["yfinance"] = saved
        else:
            sys.modules.pop("yfinance", None)

    assert {e["market"] for e in without_us} == {"JP"}
    assert {e["market"] for e in with_us} == {"US", "JP"}
    # 제3자 집계이므로 폴백도 confirmed로 올리지 않는다.
    assert all(e["status"] == "estimated" for e in with_us)


def test_yf_economic_returns_empty_when_yfinance_is_missing():
    """yfinance가 없어도 캘린더 갱신 전체가 실패하면 안 된다."""
    import sys
    from features.market_calendar.adapters import yf_economic

    saved = sys.modules.get("yfinance")
    sys.modules["yfinance"] = None  # import 시 TypeError를 유발한다
    try:
        assert yf_economic.fetch_yf_economic_events(start="2026-08-01", end="2026-08-31") == []
    finally:
        if saved is not None:
            sys.modules["yfinance"] = saved
        else:
            sys.modules.pop("yfinance", None)
