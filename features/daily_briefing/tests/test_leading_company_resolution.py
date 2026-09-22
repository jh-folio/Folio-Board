"""본문이 이름을 부른 주도 기업의 차트가 조용히 사라지면 안 된다.

발행된 2026-08-10 미국장 브리핑에서 "4. 미국장을 주도한 기업 ② — Intel" 자리가 빈 채로
나갔다. 원인이 셋 겹쳐 있었다.

1. 해석기가 둘이었다. 이 경로만 옛 `find_companies`를 썼는데, 그쪽 SEC 이름 색인은 첫
   단어 하나로 만들어지고 그 단어가 7자 미만이거나 흔하면 통째로 버려진다. Intel(5자)·
   Ford·Visa·Nike가 안 잡히고, Western Digital은 `western`·`digital`이 둘 다 generic
   목록에 있어 대안이 없었다. 한국 종목은 수동 사전 8곳 밖이면 전부 실패했다.
2. 폴백 조건이 `not leaders`였다. ①이 풀리고 ②만 실패하면 목록이 비어 있지 않다는
   이유로 폴백을 건너뛰었다.
3. 실패가 조용했다. 스냅샷을 안 만들면 프런트가 그 슬롯을 그냥 지나가서, 경고는 보고서
   JSON에만 남고 화면에는 아무 표시도 없었다.
"""
from __future__ import annotations

import pytest

from features.common.tests.company_listing_fixtures import company_listing_cache

from features.daily_briefing.visuals import (
    collect_briefing_visuals,
    leading_company_subjects_from_markdown,
)


def _heading(market_label, ordinal, name):
    return f"## {3 if ordinal == '①' else 4}. {market_label}을 주도한 기업 {ordinal} — {name}"


@pytest.mark.parametrize(
    ("name", "ticker"),
    [
        ("Intel", "INTC"),
        ("Intel Corporation", "INTC"),
        ("Western Digital", "WDC"),
        ("Ford", "F"),
        ("Visa", "V"),
        ("Nike", "NKE"),
        ("Berkshire Hathaway", "BRK-B"),
    ],
)
def test_short_and_generic_us_names_resolve(name, ticker):
    """첫 단어가 짧거나 흔하다는 이유로 회사가 사라지지 않는다."""
    parsed = leading_company_subjects_from_markdown(_heading("미국장", "①", name))

    assert [row["ticker"] for row in parsed["us"]] == [ticker]
    assert parsed["warnings"] == []


def test_a_korean_name_outside_the_manual_dictionary_resolves(monkeypatch):
    """알테오젠은 수동 사전에도 KOSPI200 구성종목에도 없다. DART 상장 목록에는 있다.

    **상장 목록을 stub한다.** 예전에는 `data/dart-cache/corp_codes.json`을 그대로 읽어,
    캐시를 받아 둔 기계에서만 통과하고 CI에서는 빈 목록이라 실패했다 — 내려받아 둔
    적이 있다는 사실이 테스트 통과의 조건이 되면 안 된다. 여기서 검사하는 것은
    해석기가 상장 목록의 이름을 종목 코드로 잇는가이지, 캐시가 있는가가 아니다.
    """
    import features.common.company_resolution as resolution

    monkeypatch.setattr(
        resolution, "_dart_listed_rows",
        lambda: [
            {"ticker": "196170", "name": "알테오젠", "englishName": "Alteogen",
             "market": "KR", "cik": "", "source": "dart"},
        ],
    )
    # 색인은 프로세스 캐시라 stub만으로는 안 바뀐다. 이 테스트 안에서만 비우고 되돌린다.
    monkeypatch.setattr(resolution, "_INDEX_CACHE", None, raising=False)
    monkeypatch.setattr(resolution, "_INDEX_STAMP", None, raising=False)

    parsed = leading_company_subjects_from_markdown(_heading("한국장", "②", "알테오젠"))

    assert [row["ticker"] for row in parsed["kr"]] == ["196170"]


def test_the_heading_market_decides_which_listing_is_charted():
    """자국 원주와 미국 ADR은 통화도 시간대도 다른 증권이다."""
    us = leading_company_subjects_from_markdown(_heading("미국장", "①", "Toyota"))
    jp = leading_company_subjects_from_markdown(_heading("일본장", "①", "Toyota"))

    assert [row["ticker"] for row in us["us"]] == ["TM"]
    assert [row["ticker"] for row in jp["jp"]] == ["7203.T"]


def test_an_unresolvable_name_keeps_its_slot_and_says_why():
    """차트 대상에는 안 들어가되 자리와 이유는 남는다."""
    parsed = leading_company_subjects_from_markdown(
        _heading("미국장", "①", "없는회사이름입니다")
    )

    assert parsed["us"] == []
    assert [(row["ordinal"], row["label"], row["unresolved"])
            for row in parsed["unresolvedByMarket"]["us"]] == [(1, "없는회사이름입니다", True)]
    assert any("could not be resolved" in w for w in parsed["warnings"])


def test_mentions_are_counted_per_market():
    """전체 언급 수 하나로는 US가 다 풀려도 모자란 것처럼 보인다."""
    markdown = "\n".join([
        _heading("미국장", "①", "Berkshire Hathaway"),
        _heading("미국장", "②", "Intel"),
        _heading("한국장", "①", "SK하이닉스"),
    ])

    parsed = leading_company_subjects_from_markdown(markdown)

    assert parsed["headingMentionsByMarket"]["us"] == 2
    assert parsed["headingMentionsByMarket"]["kr"] == 1
    assert parsed["headingMentionsByMarket"]["jp"] == 0


def _scope_results():
    return {
        "us": {
            "marketSessionDate": "2026-08-10",
            "groups": [{
                "sector": "Semiconductors",
                "docs": [{
                    "companies": [
                        {"ticker": "NVDA", "name": "NVIDIA", "market": "US", "sector": "Semiconductors"},
                        {"ticker": "AMD", "name": "AMD", "market": "US", "sector": "Semiconductors"},
                    ],
                }],
            }],
        },
    }


def _history(symbol, session_date):
    return {
        "provider": "test",
        "sourceByInterval": {},
        "intraday": {"interval": "5m", "points": []},
        "daily": {"interval": "1d", "points": [{"date": session_date, "close": 1.0}] * 9},
    }


def _collect(markdown, *, history=_history):
    return collect_briefing_visuals(
        "2026-08-10", "us", _scope_results(),
        leader_subjects=leading_company_subjects_from_markdown(markdown),
        price_history_fetcher=history,
        include_market_visuals=False,
    )


def _company_snapshots(result):
    return [s for s in result["visualSnapshots"] if s.get("role") == "leading_company"]


def test_a_partly_resolved_pair_keeps_the_failed_slot_visible():
    """①만 풀리던 실제 실패 형태. 예전에는 ② 자리가 통째로 없어졌다.

    ② 자리를 ranked group의 다른 회사로 **채우지 않는다.** 본문이 그 자리에 특정 회사를
    지목했으므로, 다른 기업 차트를 걸면 이름과 그림이 어긋난다. 빈 차트보다 나쁜 것이
    틀린 차트다(`test_unknown_leading_company_is_not_replaced_with_another_ticker`).
    """
    markdown = "\n".join([
        _heading("미국장", "①", "Berkshire Hathaway"),
        _heading("미국장", "②", "없는회사이름입니다"),
    ])

    result = _collect(markdown)
    snapshots = _company_snapshots(result)

    assert [s["subject"]["ordinal"] for s in snapshots] == [1, 2]
    assert snapshots[0]["subject"]["ticker"] == "BRK-B"
    assert snapshots[1]["subject"]["unresolved"] is True
    assert snapshots[1]["freshness"] == "unavailable"
    assert not any("charted ranked-group companies instead" in str(w) for w in result["warnings"])


def test_an_unparsed_heading_still_falls_back_to_ranked_groups():
    """자리를 아무도 차지하지 않았을 때만 ranked group이 채운다."""
    result = _collect("### 주도한 기업: 엔비디아와 AMD가 이끌었다")
    snapshots = _company_snapshots(result)

    assert [s["subject"]["ticker"] for s in snapshots] == ["NVDA", "AMD"]
    assert any("charted ranked-group companies instead" in str(w) for w in result["warnings"])


def test_an_unresolvable_slot_renders_an_unavailable_snapshot_when_nothing_can_fill_it():
    """폴백 후보까지 없으면 자리를 비우지 말고 unavailable로 남긴다."""
    empty_scope = {"us": {"marketSessionDate": "2026-08-10", "groups": []}}
    result = collect_briefing_visuals(
        "2026-08-10", "us", empty_scope,
        leader_subjects=leading_company_subjects_from_markdown(
            _heading("미국장", "①", "없는회사이름입니다")
        ),
        price_history_fetcher=_history,
        include_market_visuals=False,
    )

    snapshots = _company_snapshots(result)
    assert len(snapshots) == 1
    assert snapshots[0]["freshness"] == "unavailable"
    assert snapshots[0]["subject"]["unresolved"] is True
    assert snapshots[0]["subject"]["label"] == "없는회사이름입니다"


def test_a_resolved_company_without_price_history_is_also_unavailable_not_absent():
    def no_history(symbol, session_date):
        return {
            "provider": "test",
            "sourceByInterval": {},
            "intraday": {"interval": "5m", "points": []},
            "daily": {"interval": "1d", "points": []},
        }

    result = _collect(_heading("미국장", "①", "Intel"), history=no_history)
    snapshots = _company_snapshots(result)

    assert len(snapshots) == 1
    assert snapshots[0]["freshness"] == "unavailable"
    assert snapshots[0]["subject"]["ticker"] == "INTC"


def test_every_charted_slot_has_a_matching_recommendation():
    """프런트는 추천으로 슬롯을 찾는다. 스냅샷만 있고 추천이 없으면 화면에서 사라진다."""
    markdown = "\n".join([
        _heading("미국장", "①", "Berkshire Hathaway"),
        _heading("미국장", "②", "없는회사이름입니다"),
    ])

    result = _collect(markdown)
    charted = {s["id"] for s in _company_snapshots(result)}
    recommended = {r.get("snapshotId") or r.get("id") for r in result["visualRecommendations"]}

    assert charted <= recommended
