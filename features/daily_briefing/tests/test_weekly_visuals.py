"""주간 시각자료 — 세 그림이 같은 창을 말하는지, 없는 값을 만들지 않는지."""
from __future__ import annotations

import pytest

from features.daily_briefing import weekly_visuals as wv
from features.daily_briefing.weekly import weekly_window

WEEK_SESSIONS = ["2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21"]


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
