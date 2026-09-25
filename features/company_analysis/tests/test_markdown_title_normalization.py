"""모델이 `# 제목` 줄을 빠뜨리면 그 줄이 카드 제목 아래 가짜 제목처럼 남았다.

프런트엔드(`CompanyAnalysisRoute.tsx`·`app.js`)는 markdown 첫 내용 줄이 `# `로
시작해야만 그 줄을 카드 제목으로 뽑아 본문에서 지운다(`splitReportTitle`). 규칙
기반 경로(`render_report`)는 `# ✅ 이름 (티커)`를 항상 쓰지만 CLI/LLM 경로는
모델 출력에 그대로 의존한다 — 같은 세션 실측으로 RIVN은 `# Rivian ...`으로
맞았지만 SK하이닉스는 `#` 없이 "SK하이닉스(000660) 기업 분석"으로 시작해,
그 줄이 스타일 없는 문단으로 카드 제목 바로 아래 남아 제목이 두 번 보였다.
"""
from __future__ import annotations

from features.company_analysis.finalize import _ensure_markdown_title, finalize_report


def test_a_missing_hash_title_line_is_replaced_with_the_headline():
    """SK하이닉스 실측 그대로: `#` 없는 제목 줄이 headline으로 교체된다."""
    markdown = "SK하이닉스(000660) 기업 분석\n\n## 0. 핵심 판단\n\n본문."
    result = _ensure_markdown_title(markdown, "SK하이닉스 기업 분석")
    assert result == "# SK하이닉스 기업 분석\n\n## 0. 핵심 판단\n\n본문."


def test_an_already_correct_title_line_is_left_alone():
    """RIVN 실측 그대로: 이미 `# `로 시작하면 손대지 않는다."""
    markdown = "# Rivian Automotive, Inc. / DE (RIVN) 기업 분석\n\n## 0. 핵심 판단\n\n본문."
    assert _ensure_markdown_title(markdown, "Rivian 기업 분석") == markdown


def test_starting_directly_with_a_section_heading_is_left_alone():
    """제목 줄 자체가 없고 바로 `## `로 시작하면(전처리 하네스에서 흔함) 그대로 둔다.

    이 경우 splitReportTitle이 못 찾아도 headline으로 자연스럽게 대체돼(카드
    제목만 나옴) 가짜 문단이 남는 버그가 재현되지 않는다 — 손댈 이유가 없다.
    """
    markdown = "## 0. 핵심 판단\n\n본문."
    assert _ensure_markdown_title(markdown, "아무 회사 기업 분석") == markdown


def test_multiple_bare_preamble_lines_are_all_discarded():
    markdown = "회사명 기업 분석\n\n생성일 2026-09-11\n\n## 0. 핵심 판단\n\n본문."
    result = _ensure_markdown_title(markdown, "회사명 기업 분석")
    assert result == "# 회사명 기업 분석\n\n## 0. 핵심 판단\n\n본문."


def test_a_blank_or_missing_headline_falls_back_to_a_generic_title():
    markdown = "제목 없는 줄\n\n## 0. 핵심 판단\n\n본문."
    assert _ensure_markdown_title(markdown, "").startswith("# 기업 분석\n\n")
    assert _ensure_markdown_title(markdown, None).startswith("# 기업 분석\n\n")


def test_no_heading_anywhere_is_left_alone():
    """헤딩이 하나도 없으면 무엇이 제목 자리인지 판단할 근거가 없다 — 원문을
    지우고 제목만 남기면 "섹션 구조가 아예 없다"는 더 큰 결함을 숨기게 된다.
    이런 문서는 계약 검증(`contractValidation`)이 따로 잡는다."""
    assert _ensure_markdown_title("아무 내용", "회사명 기업 분석") == "아무 내용"


def test_finalize_report_applies_the_same_normalization():
    report = {
        "markdown": "회사명(000000) 기업 분석\n\n## 0. 핵심 판단\n\n본문.",
        "headline": "회사명 기업 분석",
    }
    result = finalize_report(report)
    assert result["markdown"].startswith("# 회사명 기업 분석\n\n## 0. 핵심 판단")


def test_finalize_report_does_not_touch_an_already_titled_report():
    """규칙 기반 경로의 `# ✅ 이름 (티커)`처럼 이미 맞는 형식은 그대로 통과해야 한다."""
    exact = "# ✅ Howmet (HWM)\n\n## 1. 기업 개요\n\n본문."
    result = finalize_report({"markdown": exact, "headline": "Howmet 기업 분석"})
    assert result["markdown"] == exact
