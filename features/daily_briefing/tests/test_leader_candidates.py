"""주도 기업 후보의 종합 점수 정렬 — 이야기 + 시장 영향력.

실측(2026-08): 보도량만으로 정렬하던 동안 니치 기업이 미국장 주도 기업 두 자리를
다 차지했다(Nebius·CoreWeave). 절충은 자리 고정이 아니라 점수이고, 종합은 곱이
아니라 **합**이다 — 곱은 이야기 점수가 0인 대형주를 통째로 소멸시킨다.
"""
from features.common.market_calendar import briefing_market_windows
from features.daily_briefing.selection import (
    MAJOR_IMPACT_WEIGHT,
    group_ticker,
    major_ticker_set,
    prioritize_briefing_groups,
)
from features.daily_briefing.service import build_llm_context


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
    # 종합 범위는 선택 시장들의 **합집합**이다 — 예약 기본값이 미국+한국(both)이라
    # 여기서 빈 집합을 주면 가장 흔한 구성에서 가중이 사라진다(Agent pack 경로).
    both = major_ticker_set("both")
    assert us <= both and "005930.KS" in both


def test_leader_score_adds_impact_to_story():
    """비슷한 이야기면 시총 상위가 이기고, 이야기 격차가 충분히 크면 니치가 이긴다."""
    windows = briefing_market_windows("2026-08-20")
    similar = prioritize_briefing_groups([
        {"company": "Nebius", "sector": "Tech", "docs": [_doc("Nebius", "NBIS", "Nebius update", weight=40)], "score": 1},
        {"company": "NVIDIA", "sector": "Tech", "docs": [_doc("NVIDIA", "NVDA", "NVIDIA update", weight=40)], "score": 1},
    ], windows, market_scope="us")
    assert similar[0]["company"] == "NVIDIA"
    assert similar[0]["isMajor"] is True

    # 종합 계약: 영향력 점수는 그날 최고 이야기 점수 × 비중이고, **더해진다**.
    top = max(row["briefingGroupScore"] for row in similar)
    assert similar[0]["leaderScore"] == similar[0]["briefingGroupScore"] + MAJOR_IMPACT_WEIGHT * top

    big_story = prioritize_briefing_groups([
        {"company": "Nebius", "sector": "Tech",
         "docs": [_doc("Nebius", "NBIS", f"Nebius {i}", weight=40) for i in range(5)], "score": 1},
        {"company": "NVIDIA", "sector": "Tech", "docs": [_doc("NVIDIA", "NVDA", "NVIDIA mention")], "score": 1},
    ], windows, market_scope="us")
    assert big_story[0]["company"] == "Nebius"


def test_zero_story_major_does_not_vanish():
    """이야기 점수 0인 대형주가 소멸하지 않는다 — 곱이었다면 leaderScore도 0이다."""
    windows = briefing_market_windows("2026-08-20")
    rows = prioritize_briefing_groups([
        {"company": "Nebius", "sector": "Tech", "docs": [_doc("Nebius", "NBIS", "Nebius update", weight=40)], "score": 1},
        # weight 없는 한 글자 제목 — 이야기 점수 0으로 떨어지는 최소 문서.
        {"company": "NVIDIA", "sector": "Tech", "docs": [_doc("NVIDIA", "NVDA", "V", weight=-40)], "score": 1},
    ], windows, market_scope="us")
    nvda = next(row for row in rows if row["company"] == "NVIDIA")
    assert nvda["briefingGroupScore"] == 0
    assert nvda["leaderScore"] > 0
    # 이야기가 있는 니치가 그래도 앞선다 — 영향력 점수는 보정이지 대체가 아니다.
    assert rows[0]["company"] == "Nebius"


def test_candidate_context_labels_blended_rank_and_majors():
    """후보 묶음 헤더가 종합 점수 순임을 밝히고, 가중 근거(시총 상위)가 줄에 붙는다."""
    windows = briefing_market_windows("2026-08-20")
    doc = _doc("NVIDIA", "NVDA", "NVIDIA update", weight=40)
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


def test_major_ticker_set_carries_bare_forms(monkeypatch):
    """대형주 목록은 provider 심볼(005930.KS)인데 기사 태그는 bare 코드(005930)다.

    접미사를 떼지 않으면 isMajor가 미국 밖에서 한 번도 참이 되지 않는다.
    """
    import features.common.market_data.major_companies as majors
    from features.daily_briefing import selection

    monkeypatch.setattr(majors, "major_company_symbols", lambda codes: ["005930.KS", "7203.T", "AAPL"])
    out = selection.major_ticker_set("kr")
    assert {"005930.KS", "005930", "7203.T", "7203", "AAPL"} <= out


def test_major_ticker_set_aggregate_scope_is_union(monkeypatch):
    """종합 범위(both/multi/all)는 빈 집합이 아니라 선택 시장들의 합집합이다.

    예약 기본값이 미국+한국(both)인데 종합이라고 가중을 끄면, 가장 흔한 구성에서
    주도 기업 절충(0.5.4)이 무작동이다 — 컨텍스트 헤더는 가산했다고 말하면서.
    """
    import features.common.market_data.major_companies as majors
    from features.daily_briefing import selection

    seen = []

    def fake_symbols(codes):
        seen.extend(code.value for code in codes)
        return ["AAPL", "005930.KS"]

    monkeypatch.setattr(majors, "major_company_symbols", fake_symbols)
    out = selection.major_ticker_set("both")
    assert out, "종합 범위에서 빈 집합이면 가중이 사라진다"
    assert {"US", "KR"} <= set(seen)
