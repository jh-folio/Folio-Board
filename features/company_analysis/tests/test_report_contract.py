"""기업분석 산출물 계약 — 프롬프트에만 있던 약속을 결과에 적용한다."""
from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.company_analysis.depth_policy import build_depth_policy, render_length_contract
from features.company_analysis.report_contract import (
    missing_sections,
    source_required_sections,
    validate_company_report,
)
from features.company_analysis.style import REQUIRED_SECTION_HEADINGS

_FILLER = "이 회사의 매출 구성과 마진 흐름을 자료로 확인한 문장이다. " * 6


def _report(*, drop: tuple[str, ...] = (), tag: bool = True, body: str = _FILLER) -> str:
    blocks = ["# 회사 분석"]
    for name in REQUIRED_SECTION_HEADINGS:
        if name in drop:
            continue
        blocks.append(f"## {name}\n\n{body}")
        if tag and name in source_required_sections():
            blocks.append("<!-- folio-source-ids: ev_001 -->")
    return "\n\n".join(blocks)


def _codes(result: dict) -> list[str]:
    return [row["code"] for row in result["defects"]]


# ------------------------------------------------------------------ 섹션 계약

def test_missing_sections_are_caught_in_the_output_not_just_the_prompt():
    # `REQUIRED_SECTION_HEADINGS`를 쓰는 함수는 프롬프트 파일 검사 하나뿐이었다.
    # 실측: SpaceX·LAM 보고서에 `어떻게 접근할까`와 `자료 한계와 참고자료`가 없었다.
    dropped = ("어떻게 접근할까", "자료 한계와 참고자료")
    assert missing_sections(_report(drop=dropped)) == list(dropped)
    assert _codes(validate_company_report(_report(drop=dropped))).count("section_missing") == 2


def test_a_complete_report_has_no_structural_defect():
    assert missing_sections(_report()) == []
    assert "section_missing" not in _codes(validate_company_report(_report()))


def test_renamed_sections_count_as_missing():
    # 옛 보고서가 `## 섹션 1 — 기업 개요와 사업 구조`를 썼다. 계약과 다른 이름은
    # 계약이 요구한 섹션이 아니다.
    renamed = _report().replace("## 기업 개요와 돈 버는 방식", "## 섹션 1 — 기업 개요와 사업 구조")
    assert "기업 개요와 돈 버는 방식" in missing_sections(renamed)


# ------------------------------------------------------------------ 분량 계약

def test_the_length_target_follows_the_material():
    # 고정 하한을 두면 자료가 0건인 회사에서 모델이 없는 이야기로 칸을 채운다.
    thin = build_depth_policy(document_count=0, sec_facts_ok=True, ranked_filing_ok=True)
    rich = build_depth_policy(document_count=11, sec_facts_ok=True, ranked_filing_ok=True)
    assert thin["targetChars"] < rich["targetChars"]
    # 자료가 하나도 없어도 공식 숫자만으로 쓸 수 있는 만큼은 요구한다.
    bare = build_depth_policy()
    assert bare["targetChars"] >= 11_000


def test_section_budgets_cover_every_required_section():
    budgets = build_depth_policy(document_count=5)["sectionBudgets"]
    assert set(budgets) == set(REQUIRED_SECTION_HEADINGS)
    assert all(value >= 400 for value in budgets.values())


def test_thin_sections_and_short_reports_are_flagged():
    policy = build_depth_policy(document_count=11, sec_facts_ok=True, ranked_filing_ok=True)
    result = validate_company_report(_report(body="짧게 씀."), depth_policy=policy)
    assert "below_recommended_length" in _codes(result)
    assert _codes(result).count("thin_section") >= 5


def test_an_over_long_report_is_flagged():
    policy = build_depth_policy(document_count=11)
    result = validate_company_report(_report(body=_FILLER * 60), depth_policy=policy)
    assert "above_safety_length" in _codes(result)


def test_the_length_contract_gives_numbers_not_encouragement():
    # 원칙은 안 움직이고 숫자로 된 과제만 움직인다(이 세션에서 세 번 확인).
    text = render_length_contract(build_depth_policy(document_count=5))
    assert "자 이상" in text and "실적과 재무 품질" in text
    assert "하한" in text
    assert render_length_contract({}) == ""


# ------------------------------------------------------------------ 근거 연결

def test_sections_without_source_tags_are_flagged():
    # 실측: 저장된 보고서의 숨김 태그가 0개였고 `source_grounding`이 0.08까지 떨어졌다.
    result = validate_company_report(_report(tag=False))
    assert _codes(result).count("unlinked_section") == len(source_required_sections())
    assert "low_source_linkage" in _codes(result)
    assert result["metrics"]["sourceLinkage"] == 0.0


def test_a_tagged_report_links_cleanly():
    result = validate_company_report(_report(), source_ledger=[{"sourceId": "ev_001"}])
    assert "unlinked_section" not in _codes(result)
    assert result["metrics"]["sourceLinkage"] == 1.0


def test_tags_outside_the_ledger_are_flagged():
    doc = _report().replace("<!-- folio-source-ids: ev_001 -->", "<!-- folio-source-ids: ev_999 -->", 1)
    result = validate_company_report(doc, source_ledger=[{"sourceId": "ev_001"}])
    assert "unknown_source_tag" in _codes(result)


def test_unmeasurable_linkage_is_not_reported_as_perfect():
    # 계약이 자기 섹션을 하나도 못 찾았는데 1.0으로 두면, 못 잰 것을 만점으로 보고한다
    # (실측: 옛 제목을 쓴 보고서 3건이 그랬다).
    result = validate_company_report("## 아무 제목\n\n본문")
    assert result["metrics"]["sourceLinkage"] is None
    assert "low_source_linkage" not in _codes(result)


def test_narrative_sections_are_exempt_from_source_tags():
    # 판단을 적는 자리와 데이터 메모는 근거를 인용하는 자리가 아니다.
    assert "어떻게 접근할까" not in source_required_sections()
    assert "자료 한계와 참고자료" not in source_required_sections()


# ------------------------------------------------------------------ 문체

def test_hedge_density_ignores_the_data_notes_section():
    doc = _report(body="회사의 마진은 개선됐다. " * 10).replace(
        "## 자료 한계와 참고자료\n\n회사의 마진은 개선됐다. " * 1,
        "## 자료 한계와 참고자료\n\n" + "확인하기 어렵다. 단정하기 어렵다. " * 10,
    )
    assert "hedge_overuse" not in _codes(validate_company_report(doc))


def test_hedge_overuse_points_at_a_section():
    doc = _report(body="그럴 수 있다. 가능성이 있다. " * 10)
    defects = {row["code"]: row["section"] for row in validate_company_report(doc)["defects"]}
    assert defects.get("hedge_overuse")  # 보수가 손댈 자리를 가리킨다


def test_speech_without_a_named_speaker_is_flagged():
    doc = _report().replace(
        "<!-- folio-source-ids: ev_001 -->",
        "<!-- folio-source-ids: ev_001, web_007 -->", 1,
    )
    quotes = [{"sourceId": "web_007", "role": "CEO"}]
    assert "speech_unattributed" in _codes(validate_company_report(doc, quote_sources=quotes))


# ------------------------------------------------------------------ 경계

def test_no_defect_blocks_the_report():
    # 기업분석에는 후보·재시도 구조가 없다. 차단하면 사용자가 아무것도 받지 못한다.
    result = validate_company_report(_report(drop=tuple(REQUIRED_SECTION_HEADINGS[:4]), tag=False))
    assert all(row["category"] != "blocking" for row in result["defects"])


def test_an_empty_body_is_the_one_blocking_case():
    assert _codes(validate_company_report("")) == ["empty_body"]


# ------------------------------------------------------------------ 점수 상한

def test_contract_defects_cap_the_quality_score():
    # 지금까지는 섹션이 통째로 빠져도 66점이 나왔다. 계약이 잡은 것을 점수가 읽지
    # 않으면 사용자는 무엇이 비었는지 모른 채 등급만 본다.
    from features.company_analysis.report_contract import apply_report_ceiling

    report = {
        "quality": {"score": 88, "grade": "B+", "status": "pass"},
        "contractValidation": validate_company_report(
            _report(drop=("어떻게 접근할까", "자료 한계와 참고자료"), tag=False),
        ),
    }
    out = apply_report_ceiling(report)["quality"]
    assert out["score"] < 88
    assert out["contractCeiling"]["applied"] is True


def test_a_clean_report_keeps_its_score():
    from features.company_analysis.report_contract import apply_report_ceiling

    report = {
        "quality": {"score": 88, "grade": "B+", "status": "pass"},
        "contractValidation": validate_company_report(
            _report(), source_ledger=[{"sourceId": "ev_001"}],
        ),
    }
    assert apply_report_ceiling(report)["quality"]["score"] == 88


def test_the_ceiling_is_inert_without_a_validation():
    from features.company_analysis.report_contract import apply_report_ceiling

    assert apply_report_ceiling({"quality": {"score": 90}})["quality"] == {"score": 90}
    assert apply_report_ceiling({}) == {}


# ------------------------------------------------------------- 근거 인용 계약

def test_the_source_block_lists_the_ids_and_the_sections_that_need_them():
    from features.company_analysis.report_contract import render_source_contract

    text = render_source_contract([
        {"sourceId": "ev_001", "title": "10-K Item 1A", "source": "SEC", "date": "2026-02-20"},
    ])
    assert "[ev_001]" in text and "folio-source-ids" in text
    assert "실적과 재무 품질" in text  # 어느 섹션에 달아야 하는지 함께 말한다
    assert render_source_contract([]) == ""  # 인용할 것이 없으면 지시하지 않는다
