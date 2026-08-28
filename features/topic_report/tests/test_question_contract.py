"""질문이 계약이다 — 사용자가 물은 것이 본문에 남아야 한다."""
from __future__ import annotations

import os
import re
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import planner as P
from features.topic_report.report_contract import (
    question_keywords,
    unanswered_questions,
    validate_deep_report,
)
from features.topic_report.section_sources import parse_section_source_ids
from features.topic_report.topic_schema import (
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
    body_sections,
    compose_sections,
)

_ASKED = """기대 심리는 지표에 어떤 영향을 미치고, 경제 정책에 어떤 어려움을 안기는가?
- 2021~2022 인플레이션 사례
- 2024년 8월 엔캐리 트레이드 청산 사례
- 최근 국채 금리 상승과 향후 금리 정책에 대한 시장 기대 심리의 영향"""


# --------------------------------------------------------- 질문이 든 사례는 축이 된다

def test_listed_cases_are_extracted():
    assert P.question_parts(_ASKED) == [
        "2021~2022 인플레이션 사례",
        "2024년 8월 엔캐리 트레이드 청산 사례",
        "최근 국채 금리 상승과 향후 금리 정책에 대한 시장 기대 심리의 영향",
    ]


def test_a_case_the_axes_missed_becomes_an_axis():
    """실측: 플래머가 표준 거시 축으로 갈아치워 2021~2022 사례가 통째로 사라졌다."""
    plan = {
        "analysisAxes": [
            {"key": "inflation_expectations", "label": "인플레이션 기대와 실제 물가"},
            {"key": "yen_carry_unwind", "label": "엔캐리 청산과 유동성 전이"},
        ],
        "topicLabel": "기대 심리",
    }
    axes = P.ensure_question_axes(plan, _ASKED)["analysisAxes"]
    labels = [axis["label"] for axis in axes]
    assert "2021~2022 인플레이션 사례" in labels
    assert labels[0] == "2021~2022 인플레이션 사례", "사용자가 든 사례를 앞에 둔다"


def test_a_case_already_covered_is_not_duplicated():
    plan = {"analysisAxes": [{"key": "yen", "label": "2024년 8월 엔캐리 청산"}], "topicLabel": "기대 심리"}
    labels = [axis["label"] for axis in P.ensure_question_axes(plan, _ASKED)["analysisAxes"]]
    assert sum(1 for label in labels if "엔캐리" in label) == 1


def test_a_question_without_a_list_is_left_alone():
    plan = {"analysisAxes": [{"key": "a", "label": "축"}], "topicLabel": "주제"}
    assert P.ensure_question_axes(plan, "금리가 오르면 어떻게 되는가?") == plan


# ------------------------------------------------------------ 질문에 답했는지 검사한다

def test_a_year_in_the_question_must_appear_in_the_body():
    question = "2021~2022년 인플레이션 국면에서 기대는 정책에 어떤 영향을 주었는가?"
    assert question_keywords(question) == ["2021", "2022년"]
    body = "인플레이션과 정책 기대는 서로를 움직인다. 물가와 중앙은행 경로가 핵심이다."
    assert unanswered_questions(body, [question]) == [question], "일반어가 겹친다고 답한 것이 아니다"
    assert unanswered_questions("2021년에는 물가가 급등했다.", [question]) == []


def test_a_question_without_years_falls_back_to_its_distinctive_words():
    question = "기간프리미엄은 장기금리에 어떤 영향을 주는가?"
    assert unanswered_questions("기간프리미엄이 확대됐다.", [question]) == []
    assert unanswered_questions("환율과 주가만 다룬다.", [question]) == [question]


def _report(body_headings, extra=""):
    head = "\n\n".join(f"## {name}\n\n내용." for name in REPORT_HEAD_SECTIONS)
    body = "\n\n".join(f"## {name}\n\n내용.{extra}" for name in body_headings)
    tail = "\n\n".join(f"## {name}\n\n내용 4.75% 이상이면 악화." for name in REPORT_TAIL_SECTIONS)
    return f"{head}\n\n{body}\n\n{tail}"


def _validate(markdown, **kwargs):
    return validate_deep_report(
        markdown,
        source_ledger=[],
        depth_policy={"recommendedMinChars": 0, "safetyMaxChars": 99_999, "sections": compose_sections(["축1", "축2"])},
        material_resolution={},
        internal_score=90,
        **kwargs,
    )


def test_unanswered_question_is_a_defect_pointing_at_a_body_section():
    result = _validate(
        _report(["축1", "축2"]),
        research_questions=["2021~2022년 긴축에서 무엇이 확인되는가?"],
    )
    rows = [row for row in result["defects"] if row["code"] == "question_unanswered"]
    assert rows and rows[0]["section"] in {"축1", "축2"}, "보수가 고칠 섹션을 가리켜야 한다"
    assert result["metrics"]["unansweredQuestionCount"] == 1
    assert result["valid"] is True, "차단하지 않는다 — 결과물을 버리지 않고 결함으로 남긴다"


# --------------------------------------------------------------------- 태그와 서식

def test_variant_source_tag_names_are_read():
    """모델이 `<!-- sources: -->`를 스스로 만들어 22개 썼고 연결이 0.38로 떨어졌다."""
    usage, malformed = parse_section_source_ids("## 1. 결론\n\n본문\n\n<!-- sources: ev_015, ev_017 -->\n")
    assert usage["결론"] == ["ev_015", "ev_017"]
    assert malformed == []


def test_an_unrecognized_comment_is_a_defect():
    codes = {row["code"] for row in _validate(_report(["축1", "축2"], extra="\n\n<!-- note: 메모 -->"))["defects"]}
    assert "unknown_comment_tag" in codes


def test_repeated_step_headings_are_a_defect():
    templated = _report(["축1", "축2"], extra="\n\n### 개념\n\n설명.\n\n### 작동 원리\n\n설명.")
    codes = {row["code"] for row in _validate(templated)["defects"]}
    assert "templated_step_headings" in codes


def test_normal_prose_is_not_flagged_as_templated():
    codes = {row["code"] for row in _validate(_report(["축1", "축2"]))["defects"]}
    assert "templated_step_headings" not in codes


def test_type_templates_do_not_name_fixed_sections():
    """골격을 푼 뒤에도 템플릿이 `"5. 작동 경로"`를 지시해 모델이 옛 골격을 되살렸다."""
    root = os.path.join(_ROOT, "features", "topic_report", "templates")
    for name in os.listdir(root):
        if not name.endswith(".md"):
            continue
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            text = fh.read()
        assert not re.search(r'"\d+\.\s', text), f"{name}에 옛 섹션 번호 참조가 남아 있다"


def test_matching_ignores_korean_spacing():
    """한국어 복합어 띄어쓰기는 글쓴이마다 다르다.

    실측으로 질문의 "기간프리미엄"이 본문의 "기간 프리미엄"과 맞지 않아, 8번이나 다룬
    주제를 다루지 않았다고 잡았다. 오탐이 쌓이면 진짜 결함이 묻힌다.
    """
    question = "기간프리미엄은 장기금리에 어떤 영향을 주는가?"
    assert unanswered_questions("기간 프리미엄이 확대됐다.", [question]) == []


def test_inline_source_ids_are_read_as_citations():
    """숨김 주석을 막았더니 모델이 본문에 `[macro_DGS10]`으로 썼다(실측 18곳).

    형식이 달라도 인용은 인용이다 — 세지 않으면 근거 연결이 실제보다 낮게 나온다.
    """
    usage, malformed = parse_section_source_ids(
        "## 1. 결론\n\n금리는 4.10%가 됐다. [macro_DGS10, ev_019]\n"
    )
    assert usage["결론"] == ["macro_DGS10", "ev_019"]
    assert malformed == []


def test_ordinary_brackets_are_not_citations():
    usage, _ = parse_section_source_ids("## 1. 결론\n\n각주[1]와 [일반 대괄호]는 인용이 아니다.\n")
    assert usage["결론"] == []


def test_visible_source_ids_are_a_defect():
    """정본은 숨김 주석이다. 독자에게 `macro_T5YIE`는 뜻 없는 식별자다."""
    codes = {row["code"] for row in _validate(_report(["축1", "축2"], extra=" [macro_DGS10]"))["defects"]}
    assert "visible_source_id" in codes


# ------------------------------------- 두 글자 내용어를 버리지 않는다

def test_two_character_korean_words_survive_as_keywords():
    # 한국어 내용어는 대부분 두 글자다. 세 글자 하한을 두면 남는 것이 동사 활용형과
    # 의문사뿐이라, 잘 쓴 글일수록(질문의 활용형을 반복하지 않으므로) 벌을 받는다.
    keywords = question_keywords("기대 심리는 어떤 경로로 실제 물가·금리·환율 지표에 반영되는가?")
    for word in ("기대", "심리", "경로", "물가", "금리", "환율"):
        assert word in keywords, word


def test_a_report_that_answers_the_question_is_not_flagged():
    # 실측: 질문을 다루는 3,333자짜리 섹션이 있는데도 미응답으로 잡혀 심각도 70
    # 결함이 되어 품질이 69점으로 눌렸다.
    question = "기대 심리는 어떤 경로로 실제 물가·금리·환율 지표에 반영되는가?"
    body = "## 기대 심리가 지표로 옮겨가는 경로\n\n기대가 임금과 물가 설정에 반영되면 금리와 환율이 함께 움직인다."
    assert unanswered_questions(body, [question]) == []


def test_an_ignored_question_is_still_flagged():
    # 느슨해졌다고 무용해지면 안 된다. 흔적이 하나도 없으면 여전히 잡는다.
    question = "반도체 재고 순환은 어떤 국면인가?"
    assert unanswered_questions("## 금리\n\n장기금리와 환율을 다룬다.", [question]) == [question]


def test_interrogative_tails_are_not_the_only_keyword():
    # `무엇인` 하나가 키워드로 남으면 본문이 그 활용형을 쓰지 않는 한 언제나 미응답이다.
    keywords = question_keywords("기대 심리 중심의 해석이 틀릴 수 있는 반대 근거는 무엇인가?")
    assert "무엇인" not in keywords
    assert "근거" in keywords and "해석" in keywords


def test_a_term_that_merely_contains_digits_does_not_erase_the_content_words():
    """`10년물`·`P500` 같은 용어가 걸리면 내용어를 전부 버리고 그 한 토큰만 요구했다.

    "미국 10년물 금리…" 질문은 본문이 "10년 만기 국채 금리"라고 제대로 답해도 미답으로
    잡혀 `question_unanswered`(심각도 70)가 붙고 품질이 69점으로 눌렸다.
    """
    from features.topic_report.report_contract import question_keywords, unanswered_questions

    question = "미국 10년물 금리 상승이 한국 증시에 미치는 영향은 무엇인가?"
    assert len(question_keywords(question)) > 1
    body = "미국 10년 만기 국채 금리가 오르면 한국 증시의 밸류에이션이 눌린다."
    assert unanswered_questions(body, [question]) == []


def test_a_year_in_the_question_is_still_required_in_the_body():
    """연도가 든 질문은 그 연도가 답의 대상이다. 일반어가 겹친다고 답한 것이 아니다."""
    from features.topic_report.report_contract import question_keywords, unanswered_questions

    question = "2021~2022년 인플레이션 국면에서 무엇이 확인되는가?"
    assert question_keywords(question) == ["2021", "2022년"]
    body = "인플레이션과 정책 대응을 다룬다."
    assert unanswered_questions(body, [question]) == [question]
