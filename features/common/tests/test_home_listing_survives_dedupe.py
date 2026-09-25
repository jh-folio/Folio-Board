"""자국 상장 신호는 중복 제거에서 살아남아야 한다.

`_listing_rank`는 자국 상장을 `source == "constituents"`로 판정한다. 그런데 `_dedupe`가
같은 `(시장, 티커)`를 **점수로 먼저 접기** 때문에, 그 티커가 여러 출처로 들어오면
`home`을 들고 있던 행이 조용히 밀려났다.

실측: `SK hynix`로 물으면 000660이 curated(98) · constituents(96) · dart(96) 셋으로
들어오는데 점수 최고인 curated만 남고, 그건 `home=0`이라 미국 OTC ADR `SKHY`(cik 있음,
104점)가 대표가 됐다. `prefer_home=True`인 한국장 브리핑에서도 그랬고, 그 뒤
`_resolve_leading_company`가 `market_mismatch`로 걷어내 주도 기업 차트 자리가 비었다
(2026-08-14 세션 한국장 브리핑의 `unresolved-2`).

Toyota가 멀쩡했던 건 수동 사전에 도요타가 없어서 JP 행이 constituents 하나뿐이었기
때문이다 — 출처가 겹치는 종목만 걸리는 결함이었다.
"""
from __future__ import annotations

import pytest

from features.common.tests.company_listing_fixtures import company_listing_cache

from features.common.company_resolution import resolve_company_query


def _match(query, *, prefer_home):
    return (resolve_company_query(query, prefer_home=prefer_home).get("match") or {})


@pytest.mark.parametrize("query", ["SK hynix", "SK Hynix"])
def test_a_latin_query_reaches_the_home_listing_when_home_is_preferred(query):
    match = _match(query, prefer_home=True)

    assert match.get("ticker") == "000660"
    assert match.get("market") == "KR"


@pytest.mark.parametrize("query", ["SK hynix", "SK Hynix"])
def test_the_sec_listing_still_wins_by_default(query):
    """기업분석은 SEC companyfacts가 붙는 쪽이라야 보고서가 채워진다."""
    assert _match(query, prefer_home=False).get("ticker") == "SKHY"


def test_the_korean_name_reaches_the_home_listing_either_way():
    for prefer_home in (True, False):
        assert _match("SK하이닉스", prefer_home=prefer_home).get("ticker") == "000660"


def test_toyota_still_splits_the_two_listings():
    """이 계약이 원래 지키던 것. 고치면서 깨뜨리지 않는다."""
    assert _match("Toyota", prefer_home=True).get("ticker") == "7203.T"
    assert _match("Toyota", prefer_home=False).get("ticker") == "TM"


@pytest.mark.parametrize(
    ("query", "ticker"),
    [("Micron", "MU"), ("Intel", "INTC"), ("Samsung Electronics", "005930")],
)
def test_single_listing_companies_are_unaffected(query, ticker):
    for prefer_home in (True, False):
        assert _match(query, prefer_home=prefer_home).get("ticker") == ticker, query


def test_the_internal_hint_does_not_leak_into_the_response():
    """`listingFlags`는 순위용 내부 힌트다. 응답 계약에 새면 안 된다."""
    resolution = resolve_company_query("SK hynix", prefer_home=True)

    assert "listingFlags" not in (resolution.get("match") or {})
    assert all("listingFlags" not in row for row in resolution.get("candidates") or [])


def test_the_briefing_chart_path_no_longer_drops_the_second_leader():
    """실제로 빈자리가 났던 경로."""
    from features.daily_briefing.visuals import leading_company_subjects_from_markdown

    markdown = (
        "# Korea Market Briefing — 2026.08.14 마감\n"
        "## 3. 한국장을 주도한 기업 ① — Samsung Electronics\n"
        "## 4. 한국장을 주도한 기업 ② — SK hynix\n"
    )

    result = leading_company_subjects_from_markdown(markdown)

    assert [row["ticker"] for row in result["kr"]] == ["005930", "000660"]
    assert result["unresolvedByMarket"]["kr"] == []
