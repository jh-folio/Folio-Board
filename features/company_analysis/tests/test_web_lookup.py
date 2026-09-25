"""회사 웹 조회 계약 — 찾기 전용 패스, 원장 등재, 화자 귀속."""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.common.report_prose import speaker_identity, unattributed_speech
from features.company_analysis import web_lookup as W

_PAYLOAD = {
    "facts": [
        {"statement": "2026년 2분기 매출 $8.7B, 전년 대비 +22%", "url": "https://investor.x.com/q2"},
        {"statement": "가이던스를 $9.2B로 상향", "url": "https://investor.x.com/q2"},
        {"statement": "데이터센터 매출 비중 61%", "url": "https://www.sec.gov/10q"},
    ],
    "quotes": [
        {"who": "Colette Kress·CFO", "when": "2026-08-01", "what": "수요가 견조하다", "url": "https://investor.x.com/call"},
    ],
}


def _call(payload):
    return lambda _prompt, _context: json.dumps(payload, ensure_ascii=False)


# ------------------------------------------------------------------ 발동 조건

def test_thin_local_material_triggers_the_lookup():
    # 실측: 로컬 문서가 11 / 5 / 2 / 0건이었고, 0건인 회사는 데이터 갭 6개가 전부
    # "실적발표·컨퍼런스콜·리포트 없음"이었다.
    assert W.needs_web_lookup(document_count=0)
    assert W.needs_web_lookup(document_count=2)
    assert not W.needs_web_lookup(document_count=20)


def test_a_missing_earnings_gap_triggers_it_even_with_many_documents():
    # 자료가 있어도 최근 실적·IR이 통째로 비면 그 회사의 지금을 말할 수 없다.
    gaps = {"gaps": [{"label": "최근 실적·IR 업데이트"}]}
    assert W.needs_web_lookup(document_count=20, data_gaps=gaps)
    assert not W.needs_web_lookup(document_count=20, data_gaps={"gaps": [{"label": "경쟁사 비교"}]})


# ------------------------------------------------------------------ 조회

def test_facts_and_quotes_come_back_with_urls():
    row = W.lookup_company({"name": "NVIDIA", "ticker": "NVDA"}, "허용 목록", _call(_PAYLOAD))
    assert row["status"] == "ok"
    assert len(row["facts"]) == 3 and len(row["quotes"]) == 1


def test_rows_without_a_url_are_dropped():
    # URL 없는 사실은 확인할 방법이 없다.
    row = W.lookup_company(
        {"name": "X"}, "", _call({"facts": [{"statement": "출처 없는 주장"}], "quotes": []}),
    )
    assert row["facts"] == [] and row["status"] == "empty"


def test_engine_failure_does_not_raise():
    def boom(_prompt, _context):
        raise RuntimeError("engine down")

    assert W.lookup_company({"name": "X"}, "", boom)["status"] == "unavailable"
    assert W.lookup_company({}, "", _call(_PAYLOAD))["status"] == "skipped"


# ------------------------------------------------------------------ 원장 등재

def test_one_source_gets_one_id():
    # 사실마다 번호를 매기면 원장의 URL 중복 제거와 어긋나 본문이 인용한 ID가 원장에
    # 없어진다(딥 리서치 실측: 28건 중 10건이 그렇게 무효가 됐다).
    row = W.assign_source_ids(W.lookup_company({"name": "X"}, "", _call(_PAYLOAD)))
    ids = [item["sourceId"] for item in row["facts"]] + [q["sourceId"] for q in row["quotes"]]
    assert ids == ["web_001", "web_001", "web_002", "web_003"]
    assert [item["sourceId"] for item in W.web_source_items(row)] == ["web_001", "web_002", "web_003"]


def test_every_id_the_block_offers_exists_in_the_ledger():
    import re

    row = W.assign_source_ids(W.lookup_company({"name": "X"}, "", _call(_PAYLOAD)))
    offered = set(re.findall(r"\[(web_\d+)\]", W.render_lookup(row)))
    assert offered and offered <= {item["sourceId"] for item in W.web_source_items(row)}


def test_an_empty_lookup_renders_nothing():
    assert W.render_lookup({"facts": [], "quotes": []}) == ""


# ------------------------------------------------------------------ 화자 귀속

def test_a_corporate_speaker_is_matched_by_surname_not_by_cfo():
    # 기업분석 본문에서 `CFO` 세 글자는 대부분 영업현금흐름이다(실측:
    # `CFO/영업이익 92.1%`). 직함으로 세면 재무표만 있어도 귀속이 통과한다.
    assert speaker_identity("Colette Kress·CFO") == {"role": "", "name": "Kress"}
    assert speaker_identity("Tim Archer, CEO")["name"] == "Archer"

    row = W.assign_source_ids(W.lookup_company({"name": "X"}, "", _call(_PAYLOAD)))
    quotes = W.speaker_sources(row)
    assert quotes == [{"sourceId": "web_003", "role": "", "name": "Kress"}]

    tag = "\n<!-- folio-source-ids: web_003 -->"
    assert unattributed_speech("Kress CFO는 수요가 견조하다고 말했다." + tag, quotes) == []
    assert unattributed_speech("경영진은 수요가 견조하다고 말했다." + tag, quotes) == ["web_003"]
    # 재무 지표로서의 CFO는 귀속이 아니다.
    assert unattributed_speech("CFO/영업이익 92.1%." + tag, quotes) == ["web_003"]


def test_an_anonymous_speaker_is_not_tracked():
    row = W.assign_source_ids({"quotes": [{"who": "시장 참가자", "url": "https://a", "what": "…"}], "facts": []})
    assert W.speaker_sources(row) == []


def test_the_summary_carries_what_the_contract_needs():
    row = W.assign_source_ids(W.lookup_company({"name": "X", "ticker": "X"}, "", _call(_PAYLOAD)))
    summary = W.lookup_summary(row)
    assert summary["factCount"] == 3 and summary["quoteCount"] == 1
    assert summary["speakerSources"] == [{"sourceId": "web_003", "role": "", "name": "Kress"}]
    assert len(summary["urls"]) == 3


def test_the_prompt_asks_for_names_and_forbids_opinions():
    # 찾기 과제다. 전망이나 투자 의견을 가져오면 근거가 아니라 남의 판단이 실린다.
    assert "이름과 직함" in W.PROMPT
    assert "투자 의견은 찾지 마라" in W.PROMPT


# ------------------------------------------------------------------ 필수 묶음 (계획 §12 D)
def test_the_prompt_names_every_required_bundle_and_prefers_the_filed_release():
    for topic in W.FACT_TOPICS:
        assert topic in W.PROMPT
    assert "Exhibit 99.1" in W.PROMPT
    assert "비워 둔다" in W.PROMPT


def test_one_bundle_cannot_use_up_every_slot():
    """예전 전체 8건 상한에서는 실적 문장이 자리를 다 쓰면 배당·자사주가 빠졌다."""
    flood = [{"topic": "results", "statement": f"실적 {i}", "url": f"https://x.com/{i}"} for i in range(10)]
    dividend = {"topic": "capital_return", "statement": "분기 배당 17% 인상", "url": "https://x.com/div"}
    row = W.lookup_company({"name": "X"}, "", _call({"facts": [*flood, dividend], "quotes": []}))
    topics = [fact["topic"] for fact in row["facts"]]
    assert topics.count("results") == 3
    assert "capital_return" in topics


def test_unknown_topics_are_kept_as_other_not_dropped():
    row = W.lookup_company({"name": "X"}, "", _call({"facts": [
        {"statement": "주제 없이 온 사실", "url": "https://x.com/a"},
        {"topic": "weather", "statement": "모르는 주제", "url": "https://x.com/b"},
    ], "quotes": []}))
    assert [fact["topic"] for fact in row["facts"]] == ["other", "other"]


def test_the_block_groups_bundles_and_names_what_was_not_found():
    row = W.assign_source_ids(W.lookup_company({"name": "X"}, "", _call({"facts": [
        {"topic": "segments", "statement": "사업부 A 매출 $1.4B", "url": "https://x.com/q2"},
        {"topic": "guidance", "statement": "연간 매출 가이던스 $10.05B", "url": "https://x.com/q2"},
    ], "quotes": []})))
    block = W.render_lookup(row)
    assert block.index("### 사업부별 매출·이익") < block.index("### 다음 분기·연간 가이던스와 이전 대비 변경 폭")
    missing_line = next(line for line in block.splitlines() if "찾지 못한 묶음" in line)
    assert "전사 실적" in missing_line and "시장(고객 산업)별 성장률·매출 비중" in missing_line
    assert "사업부별" not in missing_line
    assert "공시하지 않았다고 쓰지 말고" in block


def test_a_long_multi_number_fact_is_not_cut_at_the_old_300_characters():
    statement = "사업부 " + " · ".join(f"S{i} 매출 $1,{i:03d}M 조정 EBITDA $5{i:02d}M" for i in range(12))
    assert 300 < len(statement) <= 400
    row = W.lookup_company({"name": "X"}, "", _call({"facts": [
        {"topic": "segments", "statement": statement, "url": "https://x.com/q2"},
    ], "quotes": []}))
    assert row["facts"][0]["statement"] == statement


def test_untagged_facts_keep_the_total_cap_and_do_not_claim_missing_bundles():
    facts = [{"statement": f"사실 {i}", "url": f"https://x.com/{i}"} for i in range(8)]
    row = W.assign_source_ids(W.lookup_company({"name": "X"}, "", _call({"facts": facts, "quotes": []})))
    assert len(row["facts"]) == 8
    assert "찾지 못한 묶음" not in W.render_lookup(row)


def test_topic_spelling_variants_are_normalised():
    row = W.lookup_company({"name": "X"}, "", _call({"facts": [
        {"topic": "Capital-Return", "statement": "배당 인상", "url": "https://x.com/a"},
        {"topic": "end markets", "statement": "시장별 성장", "url": "https://x.com/b"},
    ], "quotes": []}))
    assert [fact["topic"] for fact in row["facts"]] == ["capital_return", "end_markets"]
