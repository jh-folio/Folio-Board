"""찾기와 쓰기를 분리한다 — 웹 조회 전용 패스."""
from __future__ import annotations

import re

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import web_lookup as W
from features.topic_report.web_lookup import (
    historical_years,
    lookup_axis,
    lookup_summary,
    needs_web_lookup,
    render_lookup,
)

_ANSWER = (
    '{"facts": [{"statement": "닛케이225 -12.4% (2024-08-05)", "url": "https://www.reuters.com/x"},'
    ' {"statement": "URL 없는 사실"}],'
    ' "quotes": [{"who": "우에다 총재", "when": "2024-08", "what": "인상에 신중", "url": "https://www.boj.or.jp/y"}]}'
)


def test_past_years_trigger_a_lookup_even_when_evidence_looks_sufficient():
    """개수만 보면 안 된다.

    실측: "2021~2022 인플레이션" 축이 로컬 근거 4건을 받았지만 전부 2021년을 스쳐
    언급한 2026년 기사였다. 로컬 색인은 보관 기간상 약 3개월이라 그 창 밖 국면은
    근거가 몇 건 잡히든 답할 수 없다.
    """
    assert needs_web_lookup({"label": "2021~2022 인플레이션"}, [], 5, as_of="2026-08-25") is True
    assert needs_web_lookup({"label": "최근 국채금리"}, [], 5, as_of="2026-08-25") is False
    assert needs_web_lookup({"label": "최근 국채금리"}, [], 1, as_of="2026-08-25") is True


def test_current_year_is_not_historical():
    assert historical_years("2026년 금리 전망", as_of="2026-08-25") == []
    assert historical_years("2021~2022 인플레이션", as_of="2026-08-25") == ["2021", "2022"]


def test_a_fact_without_a_url_is_dropped():
    """URL이 없으면 검증할 수 없고 감사도 대조할 것이 없다."""
    row = lookup_axis({"key": "a", "label": "엔캐리"}, ["무슨 일이"], "질문", "허용 목록", lambda p, c: _ANSWER)
    assert [fact["statement"] for fact in row["facts"]] == ["닛케이225 -12.4% (2024-08-05)"]
    assert row["quotes"][0]["who"] == "우에다 총재"
    assert row["status"] == "ok"


def test_lookup_failure_does_not_raise():
    def boom(prompt, context):
        raise RuntimeError("engine down")

    row = lookup_axis({"key": "a", "label": "엔캐리"}, [], "질문", "목록", boom)
    assert row["status"] == "unavailable" and row["facts"] == []


def test_the_lookup_prompt_is_a_search_task_not_a_writing_task():
    """브리프 호출에 검색을 얹는 방식은 네 번 실패했다 — 일의 모양이 달라야 한다."""
    from features.topic_report.web_lookup import _PROMPT

    assert "웹에서 사실을 찾아" in _PROMPT
    assert "글을 쓰지 말고" in _PROMPT
    assert "출처 URL을 반드시" in _PROMPT


def test_rendered_block_carries_urls_for_citation():
    row = lookup_axis({"key": "a", "label": "엔캐리"}, [], "질문", "목록", lambda p, c: _ANSWER)
    text = render_lookup([row])
    assert "https://www.reuters.com/x" in text
    assert "https://www.boj.or.jp/y" in text
    assert lookup_summary([row])["factCount"] == 1
    assert len(lookup_summary([row])["urls"]) == 2


def test_empty_lookup_renders_nothing():
    assert render_lookup([{"axisKey": "a", "facts": [], "quotes": []}]) == ""


def test_web_facts_become_citable_ledger_items():
    """계약이 "제공된 source ID만 쓰라"고 한다 — 등재하지 않으면 인용할 자격이 없다.

    실측: 전용 조회가 사실 12건·발언 6건(FOMC 녹취·BLS·BOJ)을 찾아 왔는데 본문이 쓴
    것은 1건이었다.
    """
    from features.topic_report.web_lookup import assign_source_ids, web_source_items

    rows = assign_source_ids([
        {
            "label": "엔캐리",
            "facts": [{"statement": "닛케이 -12.4%", "url": "https://www.reuters.com/x"}],
            "quotes": [{"who": "우에다", "when": "2024-08", "what": "신중", "url": "https://www.boj.or.jp/y"}],
        }
    ])
    items = web_source_items(rows)
    assert [item["sourceId"] for item in items] == ["web_001", "web_002"]
    assert items[0]["source"] == "reuters.com" and items[1]["source"] == "boj.or.jp"
    assert all(item["type"] == "web_reference" and item["url"].startswith("http") for item in items)


def test_render_and_ledger_share_the_same_ids():
    """렌더가 보여 주는 ID와 원장의 ID가 다르면 태그가 맞지 않는다."""
    from features.topic_report.web_lookup import assign_source_ids, render_lookup, web_source_items

    rows = assign_source_ids([
        {"label": "축", "facts": [{"statement": "f", "url": "https://a.test/1"}], "quotes": []}
    ])
    assert "[web_001]" in render_lookup(rows)
    assert web_source_items(rows)[0]["sourceId"] == "web_001"

# ------------------------------------------- 조회 블록과 원장이 같은 ID를 쓴다

def test_facts_from_one_page_share_one_source_id():
    # 사실마다 새 번호를 매기면 원장이 URL로 중복을 제거하는 순간 인용하라고 알려 준
    # ID의 일부가 원장에 없게 된다. 실측: 28건 중 10건이 모르는 ID가 되어 계약이
    # unknown_source_tag(심각도 60)로 잡았고 품질 상한이 89로 묶였다.
    rows = W.assign_source_ids([{
        "label": "축",
        "facts": [
            {"statement": "사실1", "url": "https://fed.gov/minutes"},
            {"statement": "사실2", "url": "https://fed.gov/minutes"},
            {"statement": "사실3", "url": "https://bls.gov/cpi"},
        ],
        "quotes": [{"who": "파월 의장", "when": "2022", "what": "발언", "url": "https://fed.gov/minutes"}],
    }])
    ids = [item["sourceId"] for item in rows[0]["facts"]] + [q["sourceId"] for q in rows[0]["quotes"]]
    assert ids == ["web_001", "web_001", "web_002", "web_001"]
    # 원장은 출처당 한 줄이다.
    assert [row["sourceId"] for row in W.web_source_items(rows)] == ["web_001", "web_002"]


def test_every_id_the_block_offers_exists_in_the_ledger():
    # 조회 블록이 "이 ID로 인용하라"고 알려 준 것은 반드시 원장에 있어야 한다.
    rows = W.assign_source_ids([{
        "label": "축",
        "facts": [{"statement": f"사실{n}", "url": f"https://site/{n % 3}"} for n in range(9)],
        "quotes": [{"who": "총재", "when": "2024", "what": "발언", "url": "https://site/0"}],
    }])
    offered = set(re.findall(r"\[(web_\d+)\]", W.render_lookup(rows)))
    in_ledger = {row["sourceId"] for row in W.web_source_items(rows)}
    assert offered and offered <= in_ledger
