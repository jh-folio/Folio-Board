"""주간 시각자료 — 세 그림이 같은 창을 말하는지, 없는 값을 만들지 않는지."""
from __future__ import annotations

import pytest
from copy import deepcopy
import datetime as dt

from features.daily_briefing import weekly_visuals as wv
from features.daily_briefing.weekly import weekly_window

WEEK_SESSIONS = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]


def _full_daily_history():
    end = dt.date(2026, 8, 21)
    days = [end - dt.timedelta(days=n) for n in range(400)]
    days = sorted(day for day in days if day.weekday() < 5)[-255:]
    return {"provider": "test", "sourceByInterval": {"hourly": "test-hourly", "daily": "test-daily"},
            "intraday": {"interval": "5m", "points": [{"time": "unused", "close": 999}]},
            "hourly": {"interval": "1h", "points": [
                {"time": f"2026-08-{17 + (n // 7):02d}T{9 + (n % 7):02d}:00:00-04:00", "close": 100 + n}
                for n in range(35)]},
            "daily": {"interval": "1d", "points": [
                {"time": day.isoformat(), "open": 100 + n, "high": 102 + n,
                 "low": 99 + n, "close": 101 + n, "volume": 100000 + n}
                for n, day in enumerate(days)]}}


@pytest.mark.parametrize("market", ["us", "kr", "europe", "jp"])
def test_weekly_flow_adds_full_daily_history_without_changing_week_fields(market):
    window = weekly_window("2026-08-23")
    history = _full_daily_history()
    original = deepcopy(history)
    calls = []

    def fetch(ticker, date):
        calls.append((ticker, date))
        return history

    result = wv.collect_weekly_visuals(window, "us", markets=[market], documents=[],
        price_history_fetcher=fetch, heatmap_fetchers={market: lambda date: {}})
    flow = result["visualSnapshots"][0]
    assert calls == [(item["ticker"], window.week_end) for item in wv.INDEX_UNIVERSE[market]]
    shorter = deepcopy(history)
    shorter["daily"]["points"] = history["daily"]["points"][-6:]
    legacy = wv._collect_weekly_flow(market, window, lambda *args: shorter, [])
    fields = ("points", "baselineClose", "changePct", "weeklyReturn", "weeklyBaselineClose",
              "weeklyBaselineDate", "weeklyEndDate", "weeklyReturnReason", "expectedSessions", "missingSessions")
    for row, previous in zip(flow["series"], legacy["series"]):
        assert row["daily"] == history["daily"]
        assert row["hourly"] == history["hourly"]
        assert len(row["daily"]["points"]) == 255
        assert all("close" in point for point in row["daily"]["points"])
        assert "intraday" not in row
        assert row["sourceByInterval"] == history["sourceByInterval"]
        assert {key: row[key] for key in fields} == {key: previous[key] for key in fields}
        assert len(row["points"]) == 5
    for key in ("role", "range", "window", "weekLabel", "sessionDates", "coverage", "currencies"):
        assert flow[key] == legacy[key]
    assert flow["granularities"] == ["1h", "1d"]
    assert flow["subject"] == {}
    assert flow["dataSufficiency"]["status"] == "sufficient"
    assert all(counts == {"intraday": 0, "hourly": 35, "daily": 255} for counts in flow["dataSufficiency"]["pointCounts"].values())
    recommendation = result["visualRecommendations"][0]
    assert recommendation["variant"] == "weekly_flow_chart"
    assert recommendation["defaultPeriod"] == "1W"
    assert recommendation["placement"]["sectionRole"] == "weekly_flow"
    flow["series"][0]["daily"]["points"][0]["close"] = -1
    assert history == original  # Saved assembly does not mutate the fetcher's cache.


@pytest.mark.parametrize("market", ["us", "kr", "europe", "jp"])
@pytest.mark.parametrize("points", [None, [], [{"time": "2026-08-21", "close": 100}],
    [{"time": "2026-08-20", "close": None}, {"time": "2026-08-21", "close": 100}]])
def test_weekly_flow_missing_or_insufficient_history_warns(market, points):
    warnings = []
    history = {} if points is None else {"daily": {"interval": "1d", "points": points}}
    flow = wv._collect_weekly_flow(market, weekly_window("2026-08-23"), lambda *args: history, warnings)
    assert flow["series"] == []
    assert flow["coverage"]["missingSymbols"] == [item["ticker"] for item in wv.INDEX_UNIVERSE[market]]
    assert flow["dataSufficiency"]["status"] == "unavailable"
    assert flow["warnings"] and warnings


def _price_fetcher(closes_by_symbol=None, dates=None):
    dates = dates or WEEK_SESSIONS

    def fetch(symbol, session_date):
        closes = (closes_by_symbol or {}).get(symbol)
        if closes is None:
            closes = [100.0 + index for index in range(len(dates))]
        points = [
            {"time": day, "close": close, "open": close, "high": close, "low": close}
            # 창 밖 하루를 일부러 섞는다. 클리핑이 없으면 주초 기준이 전주 금요일이 된다.
            for day, close in zip(["2026-08-14", *dates], [closes[0] * 0.5, *closes])
        ]
        return {"provider": "test", "intraday": {"interval": "5m", "points": []},
                "daily": {"interval": "1d", "points": points}}

    return fetch


def _heatmap_fetcher(prices_by_date):
    def fetch(session_date):
        rows = [
            {"ticker": ticker, "label": ticker, "sector": "Tech", "close": close,
             "changePct": 0.1, "marketCap": 1e12, "asOf": session_date}
            for ticker, close in (prices_by_date.get(session_date) or {}).items()
        ]
        return {"market": "US", "asOf": session_date, "provider": "test",
                "weightBasis": "market_cap_usd",
                "coverage": {"requested": 2, "returned": len(rows), "ratio": 1.0, "status": "ok"},
                "rows": rows, "warnings": []}

    return fetch


def _docs(pairs):
    return [
        {"path": f"{index}.md", "title": title, "date": date, "markets": ["US"], "text": title}
        for index, (date, title) in enumerate(pairs)
    ]


def test_three_visuals_share_one_window():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us",
        documents=_docs([(day, "AI 반도체 수요") for day in WEEK_SESSIONS]),
        price_history_fetcher=_price_fetcher(),
        heatmap_fetchers={"us": _heatmap_fetcher({
            "2026-08-17": {"AAA": 100.0, "BBB": 50.0},
            "2026-08-21": {"AAA": 110.0, "BBB": 45.0},
        })},
    )
    # `role`은 **슬롯 이름**이라 A와 B가 같은 값을 갖는다(§1 아래 한 자리). 무엇을
    # 그리는지는 `type`이 말한다 — 일간의 `market_summary`도 같은 구조다.
    by_type = {snapshot["type"]: snapshot for snapshot in result["visualSnapshots"]}
    heatmap = list(result["sidecar"]["snapshots"].values())[0]
    assert [snapshot["role"] for snapshot in result["visualSnapshots"]] == [
        "weekly_flow", "weekly_story_share", "weekly_flow",
    ]
    # A·B·C가 모두 같은 주초·주말을 말한다. 그림마다 기간이 다르면 한 보고서 안에서
    # 세 그림이 세 주를 말한다.
    assert by_type["price_series"]["window"] == window.to_dict()
    assert by_type["story_share_series"]["window"] == window.to_dict()
    assert heatmap["window"] == window.to_dict()
    assert heatmap["changeBasis"]["startDate"] == by_type["price_series"]["sessionDates"][0]
    assert heatmap["changeBasis"]["endDate"] == by_type["price_series"]["sessionDates"][-1]


def test_flow_baseline_is_the_first_session_inside_the_window():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us", documents=[],
        price_history_fetcher=_price_fetcher({"^GSPC": [100.0, 101.0, 102.0, 103.0, 104.0]}),
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    flow = next(row for row in result["visualSnapshots"] if row["role"] == "weekly_flow")
    series = next(row for row in flow["series"] if row["ticker"] == "^GSPC")
    # 창 밖 8월 14일(반값)이 기준이 되면 첫 점이 0%가 아니라 +100%가 된다.
    assert series["points"][0] == {"time": "2026-08-17", "close": 100.0, "changePct": 0.0}
    assert series["baselineClose"] == 100.0
    assert series["changePct"] == pytest.approx(4.0)
    assert flow["sessionDates"] == WEEK_SESSIONS
    assert flow["unit"] == "percent_change_from_week_start"
    assert flow["range"] == "week"


def test_flow_exposes_prior_week_close_return_separately_from_normalized_curve():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us", documents=[],
        price_history_fetcher=_price_fetcher({"^GSPC": [100.0, 101.0, 102.0, 103.0, 104.0]}),
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    series = next(row for row in result["visualSnapshots"][0]["series"] if row["ticker"] == "^GSPC")
    # The curve remains first-in-window (100 -> 104), while the headline
    # weekly return uses the preceding close (50 -> 104).
    assert series["baselineClose"] == 100.0
    assert series["points"][0]["changePct"] == 0.0
    assert series["weeklyBaselineDate"] == "2026-08-14"
    assert series["weeklyBaselineClose"] == 50.0
    assert series["weeklyReturn"] == pytest.approx(108.0)
    assert series["weeklyEndDate"] == "2026-08-21"


def test_flow_marks_missing_middle_session_as_partial_temporal_coverage():
    window = weekly_window("2026-08-23")

    def sparse(symbol, session_date):
        points = [
            {"time": "2026-08-17", "close": 100.0},
            # 08-18 is intentionally absent for every symbol.
            {"time": "2026-08-19", "close": 101.0},
            {"time": "2026-08-20", "close": 102.0},
            {"time": "2026-08-21", "close": 103.0},
        ]
        return {"provider": "test", "daily": {"interval": "1d", "points": points}}

    result = wv.collect_weekly_visuals(
        window, "us", documents=[], price_history_fetcher=sparse,
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    flow = next(row for row in result["visualSnapshots"] if row["role"] == "weekly_flow")
    series = next(row for row in flow["series"] if row["ticker"] == "^GSPC")
    assert flow["coverage"]["status"] == "partial"
    assert "2026-08-18" in series["missingSessions"]
    assert "2026-08-18" in flow["coverage"]["missingSessionsBySymbol"]["^GSPC"]


def test_weekly_return_keeps_missing_prior_baseline_null():
    window = weekly_window("2026-08-23")

    def no_prior(symbol, session_date):
        return {"provider": "test", "daily": {"interval": "1d", "points": [
            {"time": "2026-08-17", "close": 100.0},
            {"time": "2026-08-18", "close": 101.0},
            {"time": "2026-08-19", "close": 102.0},
            {"time": "2026-08-20", "close": 103.0},
            {"time": "2026-08-21", "close": 104.0},
        ]}}

    result = wv.collect_weekly_visuals(
        window, "us", documents=[], price_history_fetcher=no_prior,
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    series = next(row for row in result["visualSnapshots"][0]["series"] if row["ticker"] == "^GSPC")
    assert series["weeklyReturn"] is None
    assert series["weeklyBaselineDate"] is None
    assert series["weeklyReturnReason"] == "prior_week_close_missing"


def test_weekly_return_requires_exact_prior_and_final_calendar_sessions():
    window = weekly_window("2026-08-23")

    def stale_or_missing_end(symbol, session_date):
        return {"provider": "test", "daily": {"interval": "1d", "points": [
            # 08-13 is not the exact prior session to this window; 08-14 is missing.
            {"time": "2026-08-13", "close": 50.0},
            {"time": "2026-08-17", "close": 100.0},
            {"time": "2026-08-18", "close": 101.0},
            {"time": "2026-08-19", "close": 102.0},
            {"time": "2026-08-20", "close": 103.0},
        ]}}

    result = wv.collect_weekly_visuals(
        window, "us", documents=[], price_history_fetcher=stale_or_missing_end,
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    series = next(row for row in result["visualSnapshots"][0]["series"] if row["ticker"] == "^GSPC")
    assert series["weeklyReturn"] is None
    assert series["weeklyBaselineDate"] is None
    assert series["weeklyReturnReason"] == "prior_week_close_missing"

    def missing_friday(symbol, session_date):
        return {"provider": "test", "daily": {"interval": "1d", "points": [
            {"time": "2026-08-14", "close": 50.0},
            {"time": "2026-08-17", "close": 100.0},
            {"time": "2026-08-18", "close": 101.0},
            {"time": "2026-08-19", "close": 102.0},
            {"time": "2026-08-20", "close": 103.0},
        ]}}

    result = wv.collect_weekly_visuals(
        window, "us", documents=[], price_history_fetcher=missing_friday,
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    series = next(row for row in result["visualSnapshots"][0]["series"] if row["ticker"] == "^GSPC")
    assert series["weeklyReturn"] is None
    assert series["weeklyBaselineDate"] == "2026-08-14"
    assert series["weeklyReturnReason"] == "week_end_session_missing"


def test_heatmap_recomputes_week_over_week_and_drops_constituents_without_a_week_start():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us", documents=[],
        price_history_fetcher=_price_fetcher(),
        heatmap_fetchers={"us": _heatmap_fetcher({
            "2026-08-17": {"AAA": 100.0},
            "2026-08-21": {"AAA": 110.0, "NEW": 20.0},
        })},
    )
    heatmap = list(result["sidecar"]["snapshots"].values())[0]
    rows = {row["ticker"]: row for row in heatmap["rows"]}
    assert rows["AAA"]["changePct"] == pytest.approx(10.0)
    # 주초 종가가 없는 종목은 그리지 않는다. 0%로 두면 "안 움직였다"가 되어 결측이
    # 사실로 둔갑한다.
    assert "NEW" not in rows
    assert any("no week-start close" in warning for warning in heatmap["warnings"])
    # 상자 크기·분류는 주말 스냅샷을 쓴다.
    assert rows["AAA"]["marketCap"] == 1e12
    assert heatmap["weightBasis"] == "market_cap_usd"


def test_story_share_counts_each_document_on_its_own_day():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us",
        documents=_docs([
            ("2026-08-17", "AI 반도체 수요"),
            ("2026-08-18", "AI 반도체 수요"),
            ("2026-08-18", "연준 금리 인하"),
            # 창 밖 문서는 어느 막대에도 들어가지 않는다.
            ("2026-08-10", "AI 반도체 수요"),
        ]),
        price_history_fetcher=_price_fetcher(),
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    story = next(row for row in result["visualSnapshots"] if row["role"] == "weekly_story_share")
    days = {row["date"]: row for row in story["days"]}
    assert set(days) == {"2026-08-17", "2026-08-18"}
    assert days["2026-08-17"]["docCount"] == 1
    assert days["2026-08-18"]["docCount"] == 2
    # 색과 순서는 그 주 전체 기준으로 한 번 정한다 — 날마다 다시 고르면 같은 색이
    # 막대마다 다른 이야기를 가리킨다.
    assert story["drivers"] == sorted(story["drivers"], key=lambda label: story["drivers"].index(label))
    assert all(set(row["shares"]) == set(story["drivers"]) for row in story["days"])
    assert story["basis"] == "collected_news_volume"
    assert story["driverBasis"]["kind"] == "fixed_vocabulary"


def test_story_share_marks_small_samples():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us",
        documents=_docs([("2026-08-18", "AI 반도체 수요")]),
        price_history_fetcher=_price_fetcher(),
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    story = next(row for row in result["visualSnapshots"] if row["role"] == "weekly_story_share")
    # 하루 한 건이면 기사 하나가 비중을 100%p 움직인다. 그 사실을 함께 내보낸다.
    assert story["smallSample"] is True
    assert any("small sample" in warning for warning in story["warnings"])


def test_heatmap_is_skipped_when_no_week_over_week_row_survives():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us", documents=[],
        price_history_fetcher=_price_fetcher(),
        # 주말 종가만 있고 주초가 통째로 비면 비교할 것이 없다.
        heatmap_fetchers={"us": _heatmap_fetcher({"2026-08-21": {"AAA": 2.0}})},
    )
    assert result["sidecar"]["snapshots"] == {}
    assert not [row for row in result["visualSnapshots"] if row["type"] == "market_heatmap"]
    assert [row["role"] for row in result["visualSnapshots"]] == ["weekly_flow", "weekly_story_share"]
    assert any("no week-over-week rows" in warning for warning in result["warnings"])


def test_every_product_market_can_get_a_weekly_heatmap():
    window = weekly_window("2026-08-23")
    prices = {"2026-08-17": {"AAA": 1.0}, "2026-08-21": {"AAA": 2.0}}
    for market in ("us", "kr", "europe", "jp"):
        result = wv.collect_weekly_visuals(
            window, market, documents=[],
            price_history_fetcher=_price_fetcher(),
            heatmap_fetchers={market: _heatmap_fetcher(prices)},
        )
        # 히트맵 지원은 시장 계약이 정한다. 네 시장 모두 구성종목 universe를 갖는다.
        assert list(result["sidecar"]["snapshots"]) == [f"weekly-heatmap:{market}:2026-08-23"], market


def test_price_failure_leaves_a_gap_rather_than_an_empty_chart():
    window = weekly_window("2026-08-23")

    def broken(symbol, session_date):
        raise RuntimeError("provider down")

    result = wv.collect_weekly_visuals(
        window, "us", documents=[], price_history_fetcher=broken,
        heatmap_fetchers={"us": _heatmap_fetcher({})},
    )
    flow = next(row for row in result["visualSnapshots"] if row["role"] == "weekly_flow")
    assert flow["freshness"] == "unavailable"
    assert flow["coverage"]["status"] == "unavailable"
    assert any("weekly_price_history_unavailable" in warning for warning in result["warnings"])


def test_sidecar_reference_carries_the_weekly_file_name():
    window = weekly_window("2026-08-23")
    result = wv.collect_weekly_visuals(
        window, "us", documents=[],
        price_history_fetcher=_price_fetcher(),
        heatmap_fetchers={"us": _heatmap_fetcher({
            "2026-08-17": {"AAA": 100.0}, "2026-08-21": {"AAA": 110.0},
        })},
    )
    inline = next(row for row in result["visualSnapshots"] if row["type"] == "market_heatmap")
    # 종류가 빠지면 같은 날 일간 사이드카를 가리켜 하루 등락이 주간 카드에 그려진다.
    assert inline["sidecarRef"]["file"] == "data/briefings/2026-08-23.us.weekly.visuals.json.gz"
    assert result["sidecar"]["kind"] == "weekly"


def test_collect_weekly_visuals_uses_market_list_over_label():
    """kr+jp 예약의 라벨은 `multi`다 — 라벨 정규화는 BOTH(미국+한국)로 떨어지므로
    명시된 시장 목록이 이겨야 일본 주간에 시각자료가 실린다."""
    from features.daily_briefing.weekly import WeeklyWindow
    from features.daily_briefing.weekly_visuals import collect_weekly_visuals

    window = WeeklyWindow(
        publication_date="2026-08-23", week_start="2026-08-17", week_end="2026-08-23",
        preview_start="2026-08-24", preview_end="2026-08-30",
    )
    asked = []

    def fake_fetch(symbol, session_date):
        asked.append(symbol)
        return {"intraday": {"interval": "5m", "points": []}, "daily": {"interval": "1d", "points": []}}

    result = collect_weekly_visuals(
        window, "multi", documents=[], markets=["kr", "jp"],
        price_history_fetcher=fake_fetch,
        heatmap_fetchers={key: (lambda session_date: {}) for key in ("us", "kr", "europe", "jp")},
    )
    markets = {snap.get("market") for snap in result["visualSnapshots"]}
    assert "JP" in markets and "US" not in markets, markets
