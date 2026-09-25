"""기업분석의 조건·범위 검사가 **맞는 자리**를 읽는지 (계획 §12 C, HWM 2026-09 실측).

- 평가기는 첫 '시나리오' 헤딩을 잡아 PER 배수 표만 읽고, 뒤의 성장 체크포인트 조건을
  놓쳤다(Codex 저장본).
- 계약·평가는 '분석 범위' 낱말을 찾는데 프롬프트는 그 낱말을 쓰라고 한 적이 없었다. 범위를
  밝히고도 감점된 저장본이 있었다(Opus 저장본). 이제 프롬프트가 `분석 범위:` 라벨을 지시한다.

낱말 검사는 조건·범위의 **자리와 형식**을 볼 뿐 사실성이나 논리의 타당성을 검증하지 않는다.
"""
from __future__ import annotations

from features.common.research_quality.evaluator import evaluate_report
from features.company_analysis.report_contract import render_quality_requirements, validate_company_report
from features.company_analysis.style import REQUIRED_SECTION_HEADINGS, read_analysis_prompt

_FILLER = "이 회사의 매출 구성과 마진 흐름을 자료로 확인한 문장이다. " * 6


def _report(overrides: dict[str, str] | None = None, *, numbered: bool = True) -> str:
    overrides = overrides or {}
    blocks = ["# 회사 분석"]
    for index, name in enumerate(REQUIRED_SECTION_HEADINGS):
        title = f"{index}. {name}" if numbered else name
        blocks.append(f"## {title}\n\n{overrides.get(name, _FILLER)}")
    return "\n\n".join(blocks)


_PER_TABLE = (
    "### PER 조건별 시나리오\n\n| 시나리오 | PER |\n|---|---:|\n| 나쁜 경우 | 39배 |\n| 좋은 경우 | 72배 |\n\n"
    "### 현금흐름할인모형\n\n가정을 설명한다."
)


def _scenario(markdown: str) -> tuple[float, list[str]]:
    result = evaluate_report(markdown, artifact_type="company_analysis")
    return result["checks"]["scenario_quality"], result["warnings"]


def _defects(markdown: str) -> list[str]:
    return [row["code"] for row in validate_company_report(markdown)["defects"]]


class TestEvaluatorReadsTheCheckpointSection:
    def test_per_table_first_does_not_hide_later_conditions(self):
        markdown = _report({
            "밸류에이션": _PER_TABLE,
            "성장 전망과 체크포인트": "분기 매출원가율이 66%를 넘으면 가격 효과가 약해진 것으로 봅니다.",
        })
        score, warnings = _scenario(markdown)
        assert score > 0.5
        assert not any("시나리오가 조건 기반" in w for w in warnings)

    def test_per_table_alone_is_not_a_conditional_scenario(self):
        score, warnings = _scenario(_report({"밸류에이션": _PER_TABLE}))
        assert score == 0.5 and any("시나리오가 조건 기반" in w for w in warnings)

    def test_numbers_without_a_condition_are_not_conditions(self):
        score, _ = _scenario(_report({"성장 전망과 체크포인트": "2분기 원가율은 62.7%, 유기적 성장률은 21%였다."}))
        assert score == 0.5

    def test_a_vague_optimistic_sentence_is_not_a_condition(self):
        score, _ = _scenario(_report({"성장 전망과 체크포인트": "업황 개선이 기대되며 성장이 이어질 전망이다."}))
        assert score == 0.5

    def test_conditions_under_a_sub_heading_count(self):
        body = "회사 전망을 정리한다.\n\n### 확인할 체크포인트\n\n유기적 성장률이 한 자릿수가 되면 판단을 낮춥니다."
        score, _ = _scenario(_report({"성장 전망과 체크포인트": body}, numbered=False))
        assert score > 0.5

    def test_conditions_in_the_next_section_do_not_leak_in(self):
        score, _ = _scenario(_report({
            "성장 전망과 체크포인트": "회사 전망을 정리한다.",
            "어떻게 접근할까": "원가율이 66%를 넘으면 다시 봅니다.",
        }))
        assert score == 0.5

    def test_a_missing_checkpoint_section_is_not_treated_as_fine(self):
        markdown = _report().replace("## 6. 성장 전망과 체크포인트", "## 6. 전망")
        score, _ = _scenario(markdown)
        assert score == 0.2

    def test_other_report_types_keep_reading_the_scenario_heading(self):
        topic = "# 테마\n\n## 시나리오\n\n금리가 5%를 넘으면 수요가 줄어든다.\n\n## 결론\n\n정리."
        result = evaluate_report(topic, artifact_type="topic_report")
        assert result["checks"]["scenario_quality"] > 0.5


class TestScopeLabel:
    def test_both_style_prompts_ask_for_the_label(self):
        for style in ("beginner", "advanced"):
            assert "`분석 범위:`" in read_analysis_prompt(style), style

    def test_the_requirements_example_itself_passes_the_check(self):
        """예시 문장에 검사 낱말이 없으면 예시대로 쓴 보고서가 감점된다."""
        assert "\"분석 범위: " in render_quality_requirements()

    def test_a_labelled_scope_paragraph_passes(self):
        markdown = _report({"핵심 판단": "분석 범위: 이 보고서는 SEC 재무와 10-Q를 다루며 단기 수급은 다루지 않습니다.\n\n" + _FILLER})
        assert "scope_undefined" not in _defects(markdown)

    def test_an_unlabelled_scope_paragraph_is_still_flagged(self):
        """검사 낱말은 넓히지 않는다 — 평가기를 공유하는 다른 보고서 점수가 함께 바뀐다."""
        markdown = _report({"핵심 판단": "이 보고서는 SEC 재무와 10-Q를 다룹니다. 단기 수급은 다루지 않습니다.\n\n" + _FILLER})
        assert "scope_undefined" in _defects(markdown)


class TestTableConditions:
    def test_direction_only_cells_are_flagged(self):
        table = (
            "| 관찰 변수 | 긍정 신호 | 부정 신호 |\n|---|---|---|\n"
            "| 매출원가율 | 62~63% 유지 | 전년 수준으로 복귀 |\n| 유기적 성장률 | 두 자릿수 유지 | 한 자릿수로 둔화 |"
        )
        assert "scenario_not_conditional" in _defects(_report({"성장 전망과 체크포인트": table}))

    def test_cells_written_as_conditions_pass(self):
        table = (
            "| 관찰 변수 | 판단을 낮출 조건 |\n|---|---|\n"
            "| 매출원가율 | 전년 수준(66.5%) 위로 올라가면 |\n| 유기적 성장률 | 한 자릿수가 되면 |"
        )
        assert "scenario_not_conditional" not in _defects(_report({"성장 전망과 체크포인트": table}))

    def test_the_requirements_block_shows_how_to_write_table_cells(self):
        block = render_quality_requirements()
        assert "체크포인트 표의 칸" in block and "한 자릿수가 되면" in block
