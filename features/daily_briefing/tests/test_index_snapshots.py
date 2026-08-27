"""Task 2.2 — representative index snapshots for Europe and Japan.

The gate is that one index failing degrades coverage instead of failing the
briefing, and that GBP and EUR series are never collapsed into one currency.
"""
from __future__ import annotations

import pytest

from features.common.market_data.price_history import INDEX_UNIVERSE
from features.common.markets import MARKET_REGISTRY, MarketCode
from features.daily_briefing.visuals import collect_briefing_visuals

SESSION = "2026-07-31"


def _rows(count: int = 12) -> list[dict]:
    return [
        {"time": f"2026-07-{day:02d}", "close": 100.0 + day, "provider": "yfinance"}
        for day in range(20, 20 + count)
    ]


def _fetcher(*, failing: tuple[str, ...] = ()):
    def fetch(symbol: str, session_date: str) -> dict:
        points = [] if symbol in failing else _rows()
        return {
            "provider": "yfinance",
            "sourceByInterval": {"daily": "yfinance"},
            "intraday": {"interval": "5m", "points": []},
            "daily": {"interval": "1d", "points": points},
        }
    return fetch


def _collect(scope: str, *, failing: tuple[str, ...] = ()) -> dict:
    result = collect_briefing_visuals(
        "2026-08-05",
        scope,
        {scope: {"marketSessionDate": SESSION}},
        price_history_fetcher=_fetcher(failing=failing),
        # 회사 차트는 이 작업 범위 밖이고, 비워 두면 종목 조회 네트워크 호출도 없다.
        leader_subjects={},
        # 히트맵도 반드시 스텁한다. 기본 fetcher를 타면 실제 yfinance를 부르고 그
        # 결과를 **실제 last-good 캐시에 저장**한다 — 이 테스트가 2026-07-31 스냅샷을
        # 캐시에 심어, provider가 지연된 날 브리핑 두 건이 한 달 전 히트맵을 실었다.
        # fetcher 가드가 이제 네트워크를 막지만, 스텁이 의도를 문서화한다.
        heatmap_fetchers={key: (lambda _d: {}) for key in ("us", "kr", "europe", "jp")},
    )
    return next(row for row in result["visualSnapshots"] if row["type"] == "price_series")


def test_the_registry_is_the_only_place_index_tickers_are_written():
    for market in (MarketCode.US, MarketCode.KR, MarketCode.EUROPE, MarketCode.JP):
        expected = [
            descriptor.ticker
            for descriptor in MARKET_REGISTRY[market].representative_indices
            if descriptor.in_default_chart
        ]
        assert [row["ticker"] for row in INDEX_UNIVERSE[market.value.lower()]] == expected


def test_us_and_kr_charts_are_pinned():
    """KR pairs KOSPI with KOSDAQ: KOSPI 200 redrew the same line, while the
    KOSDAQ shows when the two Korean markets diverge (sidecars fire there first)."""
    assert [row["ticker"] for row in INDEX_UNIVERSE["us"]] == ["^GSPC", "^IXIC", "^DJI"]
    assert [row["ticker"] for row in INDEX_UNIVERSE["kr"]] == ["^KS11", "^KQ11"]
    for scope, currency in (("us", "USD"), ("kr", "KRW")):
        snapshot = _collect(scope)
        assert snapshot["currency"] == currency
        assert snapshot["currencies"] == [currency]


def test_europe_reports_both_currencies_rather_than_one():
    """The gate: GBP and EUR series must not be labeled a single Europe currency."""
    snapshot = _collect("europe")
    assert snapshot["market"] == "EUROPE"
    assert sorted(snapshot["currencies"]) == ["EUR", "GBP"]
    assert snapshot["currency"] == "MIXED"

    by_ticker = {row["ticker"]: row for row in snapshot["series"]}
    assert by_ticker["^FTSE"]["currency"] == "GBP"
    assert by_ticker["^GDAXI"]["currency"] == "EUR"
    assert by_ticker["^FTSE"]["timezone"] == "Europe/London"
    assert by_ticker["^GDAXI"]["timezone"] == "Europe/Berlin"


def test_one_failing_index_degrades_coverage_instead_of_failing_the_briefing():
    snapshot = _collect("europe", failing=("^GDAXI",))
    assert snapshot["coverage"]["status"] == "partial"
    assert snapshot["coverage"]["missingSymbols"] == ["^GDAXI"]
    assert [row["ticker"] for row in snapshot["series"]]  # 나머지 지수는 그대로 남는다
    assert any("missing symbols" in text for text in snapshot["warnings"])


def test_a_missing_series_stops_claiming_its_currency():
    """No GBP line means no GBP axis — the label has to follow the data."""
    snapshot = _collect("europe", failing=("^FTSE",))
    assert snapshot["currencies"] == ["EUR"]
    assert snapshot["currency"] == "EUR"


def test_a_two_currency_market_reports_unknown_rather_than_guessing():
    snapshot = _collect("europe", failing=tuple(row["ticker"] for row in INDEX_UNIVERSE["europe"]))
    assert snapshot["coverage"]["status"] == "unavailable"
    # 요청 목록에서 통화를 읽되, 어느 하나를 고르지 않는다.
    assert snapshot["currency"] == "MIXED"


def test_a_proxy_series_says_so_instead_of_posing_as_the_index():
    """yfinance has no TOPIX symbol, so an ETF stands in — and must be labeled."""
    snapshot = _collect("jp")
    proxy = next(row for row in snapshot["series"] if row["ticker"] == "1475.T")
    assert proxy["proxyFor"] == "TOPIX"
    assert "TOPIX" in proxy["label"]
    assert any("proxy for TOPIX" in text for text in snapshot["warnings"])

    nikkei = next(row for row in snapshot["series"] if row["ticker"] == "^N225")
    assert "proxyFor" not in nikkei


def test_a_heatmap_records_the_currency_its_boxes_are_sized_in():
    """Europe caps are restated into EUR at build time.

    Labeling the boxes with the market's first currency (GBP) would say the
    sizes mean something they do not.
    """
    result = collect_briefing_visuals(
        "2026-08-05", "europe", {"europe": {"marketSessionDate": SESSION}},
        price_history_fetcher=_fetcher(), leader_subjects={},
        heatmap_fetchers={"europe": lambda _: {"weightBasis": "market_cap_eur", "rows": [], "asOf": SESSION}},
    )
    heatmap = next(row for row in result["visualSnapshots"] if row["type"] == "market_heatmap")
    assert heatmap["weightBasis"] == "market_cap_eur"
    assert heatmap["currency"] == "EUR"


def test_a_market_without_a_weight_basis_does_not_invent_a_currency():
    result = collect_briefing_visuals(
        "2026-08-05", "europe", {"europe": {"marketSessionDate": SESSION}},
        price_history_fetcher=_fetcher(), leader_subjects={},
        heatmap_fetchers={"europe": lambda _: {"rows": [], "asOf": SESSION}},
    )
    heatmap = next(row for row in result["visualSnapshots"] if row["type"] == "market_heatmap")
    assert heatmap["weightBasis"] == "market_cap"
    assert heatmap["currency"] == ""  # 유럽은 통화가 둘이라 하나를 고를 수 없다


@pytest.mark.parametrize("scope,expected", [("both", ["US", "KR"]), ("all", ["US", "KR", "EUROPE", "JP"])])
def test_saved_scope_both_stays_us_kr_while_all_covers_four_markets(scope, expected):
    result = collect_briefing_visuals(
        "2026-08-05", scope,
        {key: {"marketSessionDate": SESSION} for key in ("us", "kr", "europe", "jp")},
        price_history_fetcher=_fetcher(), leader_subjects={},
        heatmap_fetchers={"us": lambda _: {}, "kr": lambda _: {}},
    )
    markets = [row["market"] for row in result["visualSnapshots"] if row["type"] == "price_series"]
    assert markets == expected
