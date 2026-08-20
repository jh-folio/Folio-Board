"""참고자료는 그 시장 브리핑의 참고자료여야 한다.

예전에는 티어 표가 시장을 몰랐다. 한국장 키워드 티어(`kr_current_flow`·`korea_market_data`)가
어느 시장 브리핑에서든 걸려서, 유럽장·일본장 참고자료 목록의 **상위 다섯 건이 전부 국내
매체**였다(실측 2026-08-08~14). 프롬프트는 같은 자리에서 "국내 매체 보도는 보조자료로
쓰세요"라고 말하는데 목록은 그 반대로 정렬돼 있었다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from features.daily_briefing.issue_selection import SOURCE_PROFILES, source_profile
from features.daily_briefing.service import (
    _HOME_MARKET_TIERS,
    _publisher_fit_band,
    _reference_sort_key,
    _source_priority_tier,
    _tier_enabled,
)

FIXTURES = Path(__file__).parent / "fixtures"
MARKETS = ("us", "kr", "europe", "jp")


def _doc(**over):
    row = {
        "title": "", "summary": "", "content": "", "source": "Reuters",
        "date": "2026-08-14", "marketSessionDate": "2026-08-14",
        "companies": [], "sectors": [], "impactTags": [], "bodyAvailability": "full",
    }
    row.update(over)
    return row


# ---------------------------------------------------------------- 매체 표


def test_every_market_has_an_expertise_value():
    """`profile.get("europe")`가 없으면 fallback으로 떨어져 권위 점수가 무작동이 된다."""
    for publisher, profile in SOURCE_PROFILES.items():
        for market in MARKETS:
            assert isinstance(profile.get(market), float), f"{publisher}/{market}"
            assert 0.0 < profile[market] <= 10.0, f"{publisher}/{market}"


def test_european_and_japanese_media_are_on_the_table():
    """표에 없으면 그 시장 브리핑의 매체 권위 점수가 사실상 무작동이다."""
    for publisher in ("Handelsblatt", "Het Financieele Dagblad", "The Guardian", "BBC"):
        assert SOURCE_PROFILES[publisher]["europe"] >= 8.0, publisher
    for publisher in ("日本経済新聞", "NHK Business", "Asahi Shimbun Business"):
        assert SOURCE_PROFILES[publisher]["jp"] >= 8.0, publisher


def test_home_media_outrank_foreign_media_on_their_own_market():
    for market, home in (
        ("kr", "연합인포맥스"), ("europe", "Handelsblatt"), ("jp", "日本経済신문".replace("신문", "新聞")),
    ):
        assert SOURCE_PROFILES[home][market] > SOURCE_PROFILES["CNBC"][market], market


def test_new_entries_do_not_change_the_korean_cross_region_verdict():
    """`region: domestic`은 한국장 교차 확인 판정 전용이다.

    유럽·일본 매체에 `domestic`을 주면 KR이 아닌 이슈에서도 교차 확인 보너스가 붙는다.
    """
    domestic = {name for name, row in SOURCE_PROFILES.items() if row["region"] == "domestic"}

    assert domestic == {"연합인포맥스", "연합뉴스", "한국경제", "매일경제"}


# ---------------------------------------------------------------- 티어


_WINDOWS = {"usRegularSessionDate": "2026-08-13", "krCurrentSessionDate": "2026-08-14", "krPreviousSessionDate": "2026-08-13"}


def test_a_korean_flow_article_is_not_a_top_tier_reference_in_a_us_briefing():
    doc = _doc(source="한국경제", title="코스피 외국인 수급과 원달러 환율", content="코스피 거래대금")

    kr_tiers = _HOME_MARKET_TIERS["kr"]

    assert _source_priority_tier(doc, _WINDOWS) in kr_tiers
    assert _source_priority_tier(doc, _WINDOWS, market_scope="us") not in kr_tiers
    assert _source_priority_tier(doc, _WINDOWS, market_scope="europe") not in kr_tiers
    # 한국장 브리핑에서는 그대로다 — 거기서는 그것이 이 시장의 자료다.
    assert _source_priority_tier(doc, _WINDOWS, market_scope="kr") in kr_tiers


def test_a_us_close_article_keeps_its_tier_only_where_it_belongs():
    windows = {"usRegularSessionDate": "2026-08-13"}
    doc = _doc(
        source="연합뉴스", title="뉴욕증시 마감 다우 상승", date="2026-08-14",
        marketSessionDate="2026-08-13", content="뉴욕증시는 상승 마감했다",
    )
    tier_blind = _source_priority_tier(doc, windows)
    if tier_blind == "us_close":  # is_us_market_close_article 판정이 걸린 경우만 의미가 있다
        assert _source_priority_tier(doc, windows, market_scope="us") == "us_close"
        assert _source_priority_tier(doc, windows, market_scope="kr") != "us_close"


def test_an_unknown_scope_keeps_every_tier():
    """범위를 모르거나 종합이면 예전처럼 전부 켠다. 종합 본문은 시장을 모두 담는다."""
    assert _tier_enabled("korea_market_data", "") is True
    assert _tier_enabled("korea_market_data", "both") is True
    assert _tier_enabled("us_close", "all") is True
    assert _tier_enabled("us_close", "kr") is False


def test_shared_tiers_are_never_gated():
    """거시·반도체·동인 티어는 어느 시장에서도 성립한다."""
    for tier in ("semiconductor", "macro_market", "core_driver", "market_flow", "support"):
        for market in MARKETS:
            assert _tier_enabled(tier, market) is True, (tier, market)


def test_every_market_owns_its_home_tiers():
    assert set(_HOME_MARKET_TIERS) == set(MARKETS)
    owned = [tier for tiers in _HOME_MARKET_TIERS.values() for tier in tiers]
    assert len(owned) == len(set(owned)), "한 티어를 두 시장이 소유할 수 없다"


# ---------------------------------------------------------------- 적합도 밴드


@pytest.mark.parametrize(
    ("publisher", "market", "band"),
    [
        ("Reuters", "us", 2),
        ("한국경제", "us", 0),
        ("Handelsblatt", "europe", 2),
        ("한국경제", "europe", 0),
        ("NHK Business", "jp", 2),
        ("CNBC", "jp", 1),
        ("연합인포맥스", "kr", 2),
    ],
)
def test_the_fit_band_reads_market_expertise(publisher, market, band):
    assert _publisher_fit_band(_doc(source=publisher), market) == band


def test_the_fit_band_is_off_without_a_market():
    """범위를 모르면 저울을 걸지 않는다 — 종합 정렬을 조용히 바꾸지 않는다."""
    assert _publisher_fit_band(_doc(source="Reuters"), "") == 0
    assert _publisher_fit_band(_doc(source="Reuters"), "both") == 0


def test_the_tier_still_outranks_the_fit_band():
    """적합도는 **같은 티어 안의 저울**이다. 매체 이름만으로 순서가 정해지면 안 된다."""
    strong_tier = _doc(source="한국경제", briefingDocScore=10.0, refTier="us_close")
    weak_tier = _doc(source="Reuters", briefingDocScore=10.0, refTier="support")

    assert _reference_sort_key(strong_tier, {}, "us") > _reference_sort_key(weak_tier, {}, "us")


def test_the_fit_band_breaks_ties_inside_one_tier():
    korean = _doc(source="한국경제", briefingDocScore=50.0, refTier="macro_market")
    foreign = _doc(source="Reuters", briefingDocScore=50.0, refTier="macro_market")

    assert _reference_sort_key(foreign, {}, "us") > _reference_sort_key(korean, {}, "us")
    # 한국장에서는 반대다.
    assert _reference_sort_key(korean, {}, "kr") > _reference_sort_key(foreign, {}, "kr")


# ---------------------------------------------------------------- 실측 기록


def test_the_measurement_fixture_records_aggregates_only():
    baseline = json.loads((FIXTURES / "source_bias_0_5_4.json").read_text(encoding="utf-8"))
    text = json.dumps(baseline)

    assert "http" not in text and "research-inbox" not in text
    assert set(baseline["after"]["topFiveOrder"]) == set(MARKETS)
    # 유럽·일본 참고자료 상단이 국내 매체로만 차 있던 것이 이 릴리즈가 고친 것이다.
    assert all(name in {"매일경제", "연합뉴스"} for name in baseline["before"]["topFiveOrder"]["europe"][:4])
    assert not any(
        name in {"매일경제", "연합뉴스", "한국경제", "연합인포맥스"}
        for name in baseline["after"]["topFiveOrder"]["europe"][:4]
    )


def test_body_availability_is_why_no_us_feed_was_added():
    """계획의 "US/KR 본문 확보 피드 0개"는 죽은 설정 플래그를 읽은 결과였다.

    실측하면 CNBC와 국내 매체는 본문이 거의 100% 확보되고, 본문이 없는 쪽은 유료벽이
    있는 Bloomberg·WSJ·Reuters다. 유료 본문 우회는 금지이므로 추가할 피드가 없다.
    """
    baseline = json.loads((FIXTURES / "source_bias_0_5_4.json").read_text(encoding="utf-8"))
    body = baseline["bodyAvailability"]

    assert body["CNBC"] >= 0.99 and body["한국경제"] >= 0.99
    assert body["Bloomberg"] < 0.05 and body["WSJ"] < 0.05


def test_the_dead_full_text_flag_is_gone():
    """설정과 실제가 어긋난 신호를 남겨 두면 다음 판단이 그것을 믿는다."""
    import yaml

    from features.common.research_library.rss.feed_config import load_rss_feeds

    raw = yaml.safe_load((Path(__file__).parents[3] / "config" / "rss_feeds.yaml").read_text(encoding="utf-8"))
    assert not any("allow_full_text" in row for row in raw["feeds"])
    feeds = load_rss_feeds(Path(__file__).parents[3] / "config" / "rss_feeds.yaml")
    assert feeds and not any("allow_full_text" in feed for feed in feeds)


def test_profiles_cover_the_publishers_that_actually_arrive():
    """수집되는 매체가 표에 없으면 그 매체의 권위 점수는 `sourceWeight` fallback이다."""
    collected = {
        "Reuters", "WSJ", "Financial Times", "Bloomberg", "CNBC", "MarketWatch", "Barron's",
        "연합인포맥스", "연합뉴스", "한국경제", "매일경제",
        "Handelsblatt", "manager magazin", "Het Financieele Dagblad", "La Tribune",
        "BFM Business", "la Repubblica Economia", "ANSA Economia", "Expansion",
        "NU.nl Economie", "Euronews Business", "The Guardian", "BBC",
        "NHK Business", "Asahi Shimbun Business", "日本経済新聞", "Yahoo Finance",
    }

    assert collected <= set(SOURCE_PROFILES)


def test_an_unknown_publisher_still_gets_a_usable_profile():
    """표에 없는 매체가 예외로 사라지면 안 된다. `sourceWeight`로 떨어진다."""
    profile = source_profile(_doc(source="Some Local Wire", sourceWeight=4), "europe")

    assert profile["publisher"] == "Some Local Wire"
    assert profile["authority"] == 4.0
    assert profile["marketExpertise"] == 4.0
