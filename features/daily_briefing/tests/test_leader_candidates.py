"""주도 기업 후보 힌트 — 보도량 순위가 시장 영향력으로 읽히지 않게.

실측(2026-08): 4시장 분리 때 선정 기준이 legacy prompt.md에만 남아 시장별
프롬프트에서 사라졌고, 기준 없는 모델이 보도량 상위의 니치 기업(Nebius·CoreWeave)을
미국장 주도 기업으로, SK hynix ADR을 ②로 올렸다.
"""
from features.daily_briefing.service import _group_ticker, _major_ticker_set, build_llm_context


def test_group_ticker_reads_the_tag_not_the_name():
    """이름 매칭이 아니라 문서의 회사 태그(ticker)로 잇는다 — 표기가 다르면 이름은 못 잇는다."""
    group = {"company": "NVIDIA", "docs": [{"companies": [{"name": "NVIDIA", "ticker": "NVDA"}]}]}
    assert _group_ticker(group) == "NVDA"
    assert _group_ticker({"company": "NVIDIA", "docs": [{"companies": [{"name": "다른회사", "ticker": "X"}]}]}) == ""
    assert _group_ticker({"company": "", "docs": []}) == ""


def test_major_ticker_set_is_market_scoped_and_fails_open():
    us = _major_ticker_set("us")
    assert "NVDA" in us and "AAPL" in us
    assert "005930.KS" in _major_ticker_set("kr")
    # 종합 범위는 시장 하나를 못 고르므로 힌트가 없을 뿐이다 — 예외가 아니다.
    assert _major_ticker_set("both") == frozenset()
    assert _major_ticker_set("nonsense") == frozenset()


def test_candidate_context_labels_coverage_rank_and_majors():
    """후보 묶음 헤더가 '보도량 순'임을 밝히고, 시총 상위 구성종목에 힌트가 붙는다."""
    doc = {
        "title": "NVIDIA earnings", "summary": "요약", "date": "2026-08-20",
        "companies": [{"name": "NVIDIA", "ticker": "NVDA"}],
        "path": "research-inbox/rss/x.md", "type": "rss", "markets": ["US"],
    }
    niche = {
        "title": "Nebius surges", "summary": "요약", "date": "2026-08-20",
        "companies": [{"name": "Nebius", "ticker": "NBIS"}],
        "path": "research-inbox/rss/y.md", "type": "rss", "markets": ["US"],
    }
    groups = [
        {"company": "Nebius", "sector": "Tech", "docs": [niche], "score": 99},
        {"company": "NVIDIA", "sector": "Tech", "docs": [doc], "score": 10},
    ]
    context, _selected = build_llm_context(
        "2026-08-20", "2026-08-19", [doc, niche], groups, market_scope="us",
    )
    assert "보도량 기준" in context
    lines = context.splitlines()
    nvda_line = next(line for line in lines if line.strip().startswith(("1.", "2.")) and "NVIDIA" in line)
    nebius_line = next(line for line in lines if line.strip().startswith(("1.", "2.")) and "Nebius" in line)
    assert "시장 시총 상위" in nvda_line
    assert "시장 시총 상위" not in nebius_line
