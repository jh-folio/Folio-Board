"""발췌에 매체 페이지의 장식 텍스트가 실리지 않는다."""
from features.common.utils import clean_brief_text, doc_brief_text
from features.daily_briefing.selection import briefing_doc_excerpt
from features.daily_briefing.service import doc_sentence

# 실측 사례. 2026-08-11 규칙 기반 US 브리핑 본문에 이 덩어리가 그대로 실렸다 —
# 기사 요약 대신 매일경제 페이지의 공유 버튼과 글자 크기 위젯이 근거로 인용됐다.
POLLUTED = (
    "# Summary\n"
    "증권가, 미국 빅테크 영향에 주목 “AI 데이터센터 수요 견조함 확인”\n"
    "# Full Text\n"
    "공유 이메일에 공유하기 카카오톡에 공유하기 페이스북에 공유하기 트위터에 공유하기 "
    "링크 복사하기 닫기 글자 크기 가 가 가 가 가 닫기 번역 ENG JPN CHN 닫기 편의기능"
)
CLEAN = "증권가, 미국 빅테크 영향에 주목 “AI 데이터센터 수요 견조함 확인”"


def test_the_old_cleaner_alone_lets_the_page_chrome_through():
    """왜 정리 함수를 하나 더 거치는지 남긴다.

    `clean_brief_text()`는 URL과 공백만 정리한다. body 섹션 마커를 모르므로 `Full Text`
    아래의 페이지 장식이 그대로 통과한다.
    """
    leaked = clean_brief_text(POLLUTED, 280)

    assert "공유하기" in leaked
    assert "글자 크기" in leaked


def test_a_document_excerpt_keeps_only_the_summary_body():
    excerpt = doc_brief_text({"summary": POLLUTED}, 280)

    assert excerpt == CLEAN
    assert "공유하기" not in excerpt
    assert "Full Text" not in excerpt


def test_the_rule_based_sentence_quotes_the_summary_not_the_page():
    sentence = doc_sentence({"title": "반도체 사이클", "summary": POLLUTED, "source": "매일경제"})

    assert "공유하기" not in sentence
    assert "글자 크기" not in sentence
    assert CLEAN in sentence


def test_the_llm_excerpt_path_is_cleaned_too():
    """규칙 본문만 고치면 같은 덩어리가 프롬프트로 들어간다."""
    excerpt = briefing_doc_excerpt({"summary": POLLUTED}, clean_brief_text, "support")

    assert "공유하기" not in excerpt
    assert CLEAN in excerpt


def test_plain_documents_are_left_alone():
    """섹션 마커가 없는 문서는 원문 그대로다. 대부분이 이쪽이다."""
    assert doc_brief_text({"summary": "평범한 요약 문장입니다."}, 280) == "평범한 요약 문장입니다."
    assert doc_brief_text({"content": "요약이 없으면 본문을 쓴다."}, 280) == "요약이 없으면 본문을 쓴다."
    assert doc_brief_text({}, 280) == ""


def test_a_document_with_only_full_text_still_says_something():
    """Summary 섹션이 없다고 빈 발췌를 내면 근거가 통째로 사라진다."""
    excerpt = doc_brief_text({"summary": "# Full Text\n실제 기사 본문이 여기 있습니다."}, 280)

    assert "실제 기사 본문" in excerpt


def test_briefing_excerpt_keeps_relevant_full_text_after_short_summary():
    doc = {
        "summary": "시장은 혼조세를 보였다.",
        "content": (
            "# Full Text\n"
            "현대차 주가는 5.62% 급락했다. 외국인은 5034억원 순매도했다. "
            "기관은 1조6690억원 순매수로 전환했다. 공유하기 추천기사 많이 본 기사"
        ),
    }

    excerpt = briefing_doc_excerpt(doc, clean_brief_text, "driver")

    assert "시장은 혼조세를 보였다" in excerpt
    assert "5.62%" in excerpt
    assert "5034억원" in excerpt
    assert "1조6690억원" in excerpt
    assert "공유하기" not in excerpt
    assert "추천기사" not in excerpt


def test_combined_summary_preserves_six_day_flow_and_newline_menu_noise():
    doc = {
        "summary": (
            "# Summary\n09-04 KR 지수는 +1.64% 상승했다.\n"
            "# Full Text\n09-02 현대차는 -5.62% 하락했다.\n"
            "09-03 외국인은 5034억원 순매도했다.\n"
            "09-04 기관은 1조6690억원 순매수로 전환했다.\n"
            "09-05 외국인 순매수로 다시 전환했다.\n"
            "09-06 지수는 +2.95% 반등했다.\n"
            "09-07 시장은 상승으로 마감했다.\n"
            "추천기사\n다른 회사 메뉴"
        ),
        "content": "",
    }

    excerpt = briefing_doc_excerpt(doc, clean_brief_text, "driver")

    for fact in ("+1.64%", "-5.62%", "5034억원", "1조6690억원", "+2.95%"):
        assert fact in excerpt
    assert "추천기사" not in excerpt
    assert "다른 회사 메뉴" not in excerpt
