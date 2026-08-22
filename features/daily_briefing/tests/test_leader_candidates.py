"""주도 기업 후보의 종합 점수 정렬 — 이야기 × 시장 영향력.

실측(2026-08): 보도량만으로 정렬하던 동안 니치 기업이 미국장 주도 기업 두 자리를
다 차지했다(Nebius·CoreWeave). 절충은 자리 고정이 아니라 점수로 한다 — 시총 상위
구성종목에 배율을 곱하되, 이야기가 충분히 큰 니치는 여전히 이긴다.
"""
from features.daily_briefing.selection import (
    MAJOR_LEADER_MULTIPLIER,
    group_ticker,
    major_ticker_set,
    prioritize_briefing_groups,
)
from features.daily_briefing.service import build_llm_context
from features.common.market_calendar import briefing_market_windows


def _doc(name, ticker, title, weight=0):
    return {
        "title": title, "summary": "요약", "date": "2026-08-20",
        "companies": [{"name": name, "ticker": ticker}],
        "path": f"research-inbox/rss/{ticker}.md", "type": "rss", "markets": ["US"],
        "sourceWeight": weight,
    }


def test_group_ticker_reads_the_tag_not_the_name():
    """이름 매칭이 아니라 문서의 회사 태그(ticker)로 잇는다 — 표기가 다르면 이름은 못 잇는다."""
    group = {"company": "NVIDIA", "docs": [{"companies": [{"name": "NVIDIA", "ticker": "NVDA"}]}]}
    assert group_ticker(group) == "NVDA"
    assert group_ticker({"company": "NVIDIA", "docs": [{"companies": [{"name": "다른회사", "ticker": "X"}]}]}) == ""


def test_major_ticker_set_is_market_scoped_and_fails_open():
    us = major_ticker_set("us")
    assert "NVDA" in us and "AAPL" in us
    assert "005930.KS" in major_ticker_set("kr")
    # 종합 범위는 시장 하나를 못 고르므로 가중이 없을 뿐이다 — 예외가 아니다.
    assert major_ticker_set("both") == frozenset()


def test_leader_score_blends_story_and_market_weight():
    """비슷한 이야기 크기면 시총 상위가 이기고, 이야기가 배율 이상 크면 니치가 이긴다."""
    windows = briefing_market_windows("2026-08-20")
    similar = prioritize_briefing_groups([
        {"company": "Nebius", "sector": "Tech", "docs": [_doc("Nebius", "NBIS", "Nebius update", weight=40)], "score": 1},
        {"company": "NVIDIA", "sector": "Tech", "docs": [_doc("NVIDIA", "NVDA", "NVIDIA update", weight=40)], "score": 1},
    ], windows, market_scope="us")
    assert similar[0]["company"] == "NVIDIA"
    assert similar[0]["isMajor"] is True
    assert similar[0]["leaderScore"] > similar[0]["briefingGroupScore"]

    big_story = prioritize_briefing_groups([
        {"company": "Nebius", "sector": "Tech",
         "docs": [_doc("Nebius", "NBIS", f"Nebius {i}", weight=40) for i in range(5)], "score": 1},
        {"company": "NVIDIA", "sector": "Tech", "docs": [_doc("NVIDIA", "NVDA", "NVIDIA mention")], "score": 1},
    ], windows, market_scope="us")
    assert big_story[0]["company"] == "Nebius"

    # 배율 계약: 이야기 점수는 0 하한(briefing_doc_score)이라 곱 가중이 안전하다.
    # 하한이 사라져 음수가 생기면 곱이 대형주를 거꾸로 끌어내린다 — 그때 이 테스트가
    # 계약 위반을 알린다.
    assert similar[0]["briefingGroupScore"] >= 0
    assert similar[0]["leaderScore"] == similar[0]["briefingGroupScore"] * MAJOR_LEADER_MULTIPLIER


def test_candidate_context_labels_blended_rank_and_majors():
    """후보 묶음 헤더가 종합 점수 순임을 밝히고, 가중 근거(시총 상위)가 줄에 붙는다."""
    windows = briefing_market_windows("2026-08-20")
    doc = _doc("NVIDIA", "NVDA", "NVIDIA earnings")
    groups = prioritize_briefing_groups(
        [{"company": "NVIDIA", "sector": "Tech", "docs": [doc], "score": 1}],
        windows, market_scope="us",
    )
    context, _selected = build_llm_context(
        "2026-08-20", "2026-08-19", [doc], groups, market_scope="us",
    )
    assert "종합 점수 순" in context
    line = next(l for l in context.splitlines() if "NVIDIA | " in l and "관련자료" in l)
    assert "시장 시총 상위" in line
