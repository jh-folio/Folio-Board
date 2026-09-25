from copy import deepcopy

import pytest

from features.daily_briefing.saved_chart_repair import repair_saved_kr_company_charts


def _report():
    return {"date": "2026-09-07", "sessionDate": "2026-09-07", "marketScope": "kr", "kind": "daily",
            "markdown": "정상 분석.\n- Toss Open API가 설정돼 있으나 yfinance를 사용한다는 provider 경고가 있었다.\n",
            "generation": {"mode": "agent", "model": "claude"},
            "koreaMarketData": {"warnings": ["internal provider warning"]},
            "visualSnapshots": [
                {"id": "index", "role": "market_summary", "series": []},
                {"id": "company", "role": "leading_company", "market": "KR", "marketSessionDate": "2026-09-07",
                 "subject": {"ticker": "005930", "label": "Samsung", "ordinal": 1},
                 "series": [{"ticker": "005930", "providerSymbol": "005930.KS", "label": "Samsung",
                             "intraday": {"interval": "5m", "points": [{"time": "2026-09-07T20:00:00+09:00", "close": 100}]}}]},
            ]}


def _history(symbol, session):
    assert symbol == "005930.KS" and session == "2026-09-07"
    return {"provider": "yfinance", "sourceByInterval": {"intraday": "yfinance", "hourly": "yfinance", "daily": "yfinance"},
            "intraday": {"interval": "5m", "points": [{"time": "2026-09-07T09:00:00+09:00", "close": 101}]},
            "hourly": {"interval": "1h", "points": []},
            "daily": {"interval": "1d", "points": [{"time": "2026-09-04", "close": 100}, {"time": "2026-09-07", "close": 102}]}}


def test_explicit_repair_preserves_unrelated_report_content_and_snapshot_identity():
    report = _report()
    original = deepcopy(report)
    result = repair_saved_kr_company_charts(report, price_fetcher=_history)
    assert report == original
    assert result["visualSnapshots"][0] == report["visualSnapshots"][0]
    company = result["visualSnapshots"][1]
    assert company["id"] == "company" and company["subject"] == report["visualSnapshots"][1]["subject"]
    assert company["series"][0]["intraday"]["points"][0]["time"].endswith("09:00:00+09:00")
    assert company["dataSufficiency"]["pointCounts"]["005930"]["intraday"] == 1
    assert result["markdown"] == "정상 분석.\n\n"
    assert result["generation"] == report["generation"]
    assert result["koreaMarketData"] == report["koreaMarketData"]


@pytest.mark.parametrize("stamp", ["2026-09-07T19:00:00+09:00", "2026-09-08T09:00:00+09:00", "2026-09-07T09:01:00+09:00", "2026-09-07T09:00:00"])
def test_repair_does_not_accept_wrong_session_or_fake_5m_candles(stamp):
    report = _report()
    original = deepcopy(report)

    def bad_history(symbol, session):
        result = _history(symbol, session)
        result["intraday"]["points"][0]["time"] = stamp
        return result

    with pytest.raises(ValueError):
        repair_saved_kr_company_charts(report, price_fetcher=bad_history)
    assert report == original


def test_missing_regular_history_never_erases_a_saved_chart():
    report = _report()
    with pytest.raises(ValueError, match="history_unavailable"):
        repair_saved_kr_company_charts(report, price_fetcher=lambda *_: {})
