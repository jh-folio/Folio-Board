"""Report Type Template / prompt / rule fallback v2 테스트.

    py -3 features/topic_report/tests/test_report_templates.py
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import planner as P
from features.topic_report import templates as T
from features.topic_report.report_rules import build_rule_report
from features.topic_report.topic_config import get_topic_config
from features.topic_report.topic_schema import REPORT_TYPE_CHOICES


def test_every_report_type_resolves_to_template():
    for rtype in sorted(REPORT_TYPE_CHOICES):
        text = T.load_type_template(rtype)
        assert text, f"{rtype} 템플릿이 비어 있음"
        assert text.startswith("# 유형별 지침"), f"{rtype} 템플릿 헤더 형식"


def test_unknown_type_falls_back_to_generic():
    assert T.load_type_template("없는유형") == T.load_type_template("custom_research")


def test_compose_prompt_appends_template():
    base = "BASE PROMPT"
    composed = T.compose_prompt(base, "macro_analysis")
    assert composed.startswith("BASE PROMPT")
    assert "거시 분석" in composed
    # 빈 base여도 죽지 않음
    assert T.compose_prompt("", "macro_analysis")


def test_prompt_md_declares_the_fixed_head_and_tail():
    """프롬프트가 강제하는 건 **머리·꼬리**다.

    본문 섹션은 계획이 정하므로 프롬프트에 이름이 박혀 있으면 안 된다 — 박혀 있던 시절
    12개 보고서 유형이 전부 같은 골격을 썼고, 주제와 안 맞는 섹션은 건너뛸 수 없어
    얇게 채워졌다.
    """
    from features.topic_report.topic_schema import REPORT_HEAD_SECTIONS, REPORT_TAIL_SECTIONS

    path = os.path.join(_ROOT, "features", "topic_report", "prompt.md")
    with open(path, encoding="utf-8") as fh:
        prompt = fh.read()
    for required in (*REPORT_HEAD_SECTIONS, *REPORT_TAIL_SECTIONS):
        assert required in prompt, f"prompt.md에 필수 섹션 '{required}' 누락"
    assert "[본문 섹션]" in prompt, "본문 섹션을 입력에서 받는다는 지시 누락"
    assert "사실로 간주하지" in prompt, "userContext 비사실 원칙 누락"


def test_rule_fallback_v2_sections():
    plan = P.build_rule_plan("일본 금리 인상이 원화와 한국 금융주에 미치는 영향")
    topic = get_topic_config("custom", custom_label="일본 금리 인상이 원화와 한국 금융주에 미치는 영향")
    md = build_rule_report(
        topic, {"tickers": {}}, {}, [], [],
        user_context="개인 메모",
        topic_plan=plan,
        data_gaps=["수급 데이터 부족"],
    )
    assert "## 리서치 계획 요약" in md
    assert "## 데이터 부족 경고" in md
    assert "## 앞으로 확인할 체크포인트" in md
    assert "## Source & Data Notes" in md
    assert "사실/근거 아님" in md, "userContext는 근거가 아님을 표기"


def test_deep_rule_fallback_includes_subquestions_and_falsification():
    plan = P.apply_deep_research_plan(P.build_rule_plan("AI 데이터센터 전력 병목이 전력기기 기업에 주는 영향"))
    topic = get_topic_config("custom", custom_label="AI 데이터센터 전력 병목이 전력기기 기업에 주는 영향")
    md = build_rule_report(
        topic, {"tickers": {}}, {}, [], [],
        topic_plan=plan,
        data_gaps=["심층 질문 일부 근거 부족"],
    )

    assert "## 심층 리서치 커버리지" in md
    assert "## 시나리오" in md
    assert "## 반증 조건" in md
    assert "## 정량 근거표" in md
    assert "심층 질문 일부 근거 부족" in md


def test_rule_report_title_uses_the_report_date_not_the_run_clock():
    """자정을 넘겨 끝난 생성에서 본문 H1만 하루 어긋났다.

    JSON `date`/`title`은 호출자가 정한 기준일인데 H1만 실행 시각을 다시 읽었다.
    """
    topic = get_topic_config("weekly_market")
    md = build_rule_report(topic, {"tickers": {}}, {}, [], [], as_of="2026-07-16")
    assert md.splitlines()[0].endswith("— 2026-07-16")


def test_rule_fallback_backward_compatible_without_plan():
    topic = get_topic_config("weekly_market")
    md = build_rule_report(topic, {"tickers": {}}, {}, [], [])
    assert md.startswith("# ")
    assert "## Source & Data Notes" in md
    assert "리서치 계획 요약" not in md, "plan 없으면 v2 섹션은 생략"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)


def test_prompt_does_not_tell_the_model_to_be_brief():
    """분량 계약과 정면으로 충돌하던 문구를 되살리지 않는다.

    프롬프트가 12,000~16,000자를 요구하면서 같은 문서에서 "각 섹션을 간결하게라도 모두
    완성하는 것이 우선"이라고 적고 있었다. 실측으로 모든 섹션이 예산의 20~60%만 채웠다.
    """
    path = os.path.join(_ROOT, "features", "topic_report", "prompt.md")
    with open(path, encoding="utf-8") as fh:
        prompt = fh.read()
    assert "간결하게라도" not in prompt
    assert "길이보다" not in prompt
    assert "최소 70%" in prompt, "섹션 예산이 하한이라는 지시가 있어야 한다"
