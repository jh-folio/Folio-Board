"""Topic Planner 단위 테스트.

    py -3 features/topic_report/tests/test_planner.py
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.topic_report import planner as P
from features.topic_report import topic_schema as S
from features.topic_report.topic_config import PRESET_TOPICS, get_topic_config


def test_report_type_enum_guard():
    assert S.normalize_report_type("macro_analysis") == "macro_analysis"
    assert S.normalize_report_type("이상한 값") == "custom_research"
    assert S.normalize_report_type("") == "custom_research"
    # legacy 매핑
    assert S.normalize_report_type("earnings_analysis") == "earnings_theme"
    assert S.normalize_report_type("industry_analysis") == "industry_theme"


def test_custom_plan_cross_asset():
    plan = P.build_rule_plan("일본 금리 인상이 원화와 한국 금융주에 미치는 영향")
    assert plan["reportType"] == "cross_asset_analysis"
    assert "Japan" in plan["regions"] and "Korea" in plan["regions"]
    assert "FX" in plan["assetClasses"]
    assert plan["analysisAxes"], "분석 축이 생성되어야 함"
    assert all(set(a) >= {"key", "label", "questions", "searchQueries"} for a in plan["analysisAxes"])
    assert "USDJPY=X" in plan["candidateTickers"]
    assert "USDKRW=X" in plan["candidateTickers"]
    assert plan["dataGapsLikely"], "데이터 부족 가능성이 채워져야 함"


def test_custom_plan_supply_chain_with_explicit_tickers():
    plan = P.build_rule_plan("AI 데이터센터 전력 병목이 GEV, ETN, VRT에 주는 투자 함의")
    assert plan["reportType"] == "supply_chain_theme"
    for ticker in ("GEV", "ETN", "VRT"):
        assert ticker in plan["candidateTickers"], f"명시 티커 {ticker} 추출 실패"


def test_search_queries_not_label_split():
    label = "원화 약세가 한국 반도체 수출주에 정말 긍정적인가"
    plan = P.build_rule_plan(label)
    assert plan["searchQueries"], "searchQueries 생성"
    # 단순 split 단어 나열이 아니라 라벨 전체/조합 쿼리가 포함되어야 함
    assert label in plan["searchQueries"]
    assert len(plan["searchQueries"]) >= 3
    assert plan["memoryQueries"], "memoryQueries 생성"


def test_user_context_not_treated_as_fact():
    """userContext는 분류 힌트일 뿐 — 계획 텍스트(질문/축)에 그대로 새어들지 않는다."""
    secret = "내 생각엔 무조건 오른다"
    plan = P.build_rule_plan("미국 장기금리 전망", user_context=secret)
    dumped = str(plan)
    assert secret not in dumped


def test_preset_backward_compatible():
    for key, config in PRESET_TOPICS.items():
        plan = P.build_topic_plan(key, preset_config=config)
        assert plan["plannerMode"] == "preset"
        assert plan["reportType"] in S.REPORT_TYPE_CHOICES
        assert plan["searchQueries"] == config["search_keywords"][:12]
        assert plan["candidateTickers"] == config["tickers"]
    # 프리셋 설정 자체는 planner가 변형하지 않는다
    assert get_topic_config("exchange_rate")["search_keywords"][0] == "환율"


def test_normalize_topic_plan_forces_schema():
    plan = S.normalize_topic_plan({
        "reportType": "factor_style",
        "analysisAxes": [{"label": "축1"}, {"no_label": True}, "garbage"],
        "candidateTickers": {"SPY": ""},
        "searchQueries": ["a", "a", "b"],
    }, topic="테스트")
    assert plan["reportType"] == "factor_style"
    assert len(plan["analysisAxes"]) == 1 and plan["analysisAxes"][0]["key"] == "axis_1"
    assert plan["candidateTickers"] == {"SPY": "SPY"}
    assert plan["searchQueries"] == ["a", "b"]  # 중복 제거
    assert plan["expectedSections"] == S.EXPECTED_SECTIONS_V2


def test_build_topic_plan_custom_without_llm():
    plan = P.build_topic_plan("custom", custom_label="중국 경기 둔화가 일본 종합상사에 미치는 영향", llm_override=False)
    assert plan["plannerMode"] == "rules"
    assert plan["reportType"] in S.REPORT_TYPE_CHOICES
    assert "China" in plan["regions"] and "Japan" in plan["regions"]


def test_deep_research_plan_adds_bounded_subquestions():
    base = P.build_rule_plan("AI 데이터센터 전력 병목이 전력기기 기업에 주는 영향")
    plan = P.apply_deep_research_plan(base)
    deep = plan["deepResearch"]

    assert deep["enabled"] is True
    assert deep["maxRounds"] == 2
    assert 3 <= len(deep["subQuestions"]) <= 12
    assert all({"id", "question", "axisKey", "round", "searchQueries"} <= set(q) for q in deep["subQuestions"])
    assert {q["round"] for q in deep["subQuestions"]} <= {1, 2}
    assert deep["falsificationTriggers"], "심층 모드는 반증 조건을 계획 단계에서 만든다"


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
