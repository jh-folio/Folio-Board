"""LLM이 쓴 계획도 검색어 위생은 코드가 정한다.

프롬프트에 "짧은 구문으로 쓰세요"라고 적는 것은 부탁이지 제한이 아니다.
여기서 새는 질의는 그대로 근거 검색을 돌리므로 보고서 품질이 된다(§5 원칙 4).
"""
from __future__ import annotations

import json

from features.topic_report import planner


def _llm_returning(payload: dict, monkeypatch):
    monkeypatch.setattr(planner, "topic_subject", planner.topic_subject)
    import features.llm_settings.client as client

    monkeypatch.setattr(client, "use_llm_analysis", lambda: True)
    monkeypatch.setattr(client, "selected_cli_config", lambda: {"enabled": True, "apiKey": "test-key", "provider": "test"})
    monkeypatch.setattr(client, "request_cli_text", lambda *a, **k: (json.dumps(payload, ensure_ascii=False), "rid"))
    monkeypatch.setattr(client, "extract_json_object", lambda text: json.loads(text))


LONG = "메모리 반도체의 방향성: 피크 아웃인가 - " + "배경 설명이 길게 이어집니다. " * 6


def test_a_full_question_returned_as_a_query_is_dropped(monkeypatch):
    _llm_returning({
        "topic": LONG,
        "reportType": "industry_theme",
        "searchQueries": [LONG, "메모리 반도체 가격", "피크"],
        "analysisAxes": [
            {"key": "demand", "label": "수요", "questions": ["수요는 어떤가?"], "searchQueries": [LONG]},
        ],
    }, monkeypatch)

    plan, mode = planner.refine_plan_with_llm(planner.build_rule_plan(LONG), LONG)

    assert mode == "llm"
    assert plan["searchQueries"] == ["메모리 반도체 가격"]
    for axis in plan["analysisAxes"]:
        for query in axis["searchQueries"]:
            assert len(query) <= 40


def test_an_llm_plan_with_no_usable_query_falls_back_to_the_rules(monkeypatch):
    rule_plan = planner.build_rule_plan(LONG)
    _llm_returning({
        "topic": LONG,
        "reportType": "industry_theme",
        "searchQueries": ["피크", "메모리"],
        "analysisAxes": [{"key": "demand", "label": "수요", "questions": ["수요는?"], "searchQueries": []}],
    }, monkeypatch)

    plan, _mode = planner.refine_plan_with_llm(rule_plan, LONG)

    assert plan["searchQueries"]
    assert plan["searchQueries"] == rule_plan["searchQueries"][:4]


def test_an_llm_title_is_cut_to_the_subject_by_code(monkeypatch):
    """제목에도 게이트가 필요하다.

    검색어에는 `_clean_queries()`가 있는데 topicLabel은 200자 절단뿐이라, LLM이
    배경 문단을 통째로 넣으면 그 문단이 보고서 제목이자 저장 라벨이 됐다.
    """
    long_label = "메모리 반도체의 방향성: " + "배경이 아주 길게 이어지는 문장입니다. " * 8
    _llm_returning({
        "topic": LONG,
        "topicLabel": long_label,
        "reportType": "industry_theme",
        "searchQueries": ["메모리 반도체 가격"],
        "analysisAxes": [{"key": "demand", "label": "수요", "questions": ["수요는?"], "searchQueries": ["메모리 수요"]}],
    }, monkeypatch)

    plan, mode = planner.refine_plan_with_llm(planner.build_rule_plan(LONG), LONG)

    assert mode == "llm"
    assert len(plan["topicLabel"]) <= 40
    assert plan["topicLabel"] == "메모리 반도체의 방향성"
    # 원문 질문은 `topic`에 그대로 남는다. 짧은 이름은 표시용이지 기록의 대체가 아니다.
    assert plan["topic"].startswith("메모리 반도체의 방향성: 피크 아웃인가 - 배경 설명이")
    assert len(plan["topic"]) > 40


def test_a_broken_llm_reply_keeps_the_rule_plan(monkeypatch):
    import features.llm_settings.client as client

    monkeypatch.setattr(client, "use_llm_analysis", lambda: True)
    monkeypatch.setattr(client, "selected_cli_config", lambda: {"enabled": True, "apiKey": "k"})
    monkeypatch.setattr(client, "request_cli_text", lambda *a, **k: ("not json", "rid"))
    monkeypatch.setattr(client, "extract_json_object", lambda _text: None)

    rule_plan = planner.build_rule_plan(LONG)
    plan, mode = planner.refine_plan_with_llm(rule_plan, LONG)

    assert mode == "parse_failed"
    assert plan is rule_plan


def test_without_a_key_the_planner_asks_the_agent_cli(monkeypatch):
    """이 설치의 Agent는 API 키가 아니라 CLI로 돈다.

    플래너만 직접 API 경로를 보고 있어서, 보고서를 쓰는 엔진이 멀쩡히 있는데도
    계획은 늘 규칙으로 떨어졌다. 켤 설정이 없었던 게 아니라 플래너가 몰랐다.
    """
    import features.llm_settings.client as client
    from features.agent_mode import bridge

    monkeypatch.setattr(client, "use_llm_analysis", lambda: True)
    monkeypatch.setattr(client, "selected_cli_config", lambda: {"enabled": True, "apiKey": ""})
    monkeypatch.setattr(bridge, "bridge_status", lambda *a, **k: {"available": True})
    asked = {}

    def fake_prompt(prompt, **kwargs):
        asked["prompt"] = prompt
        return {"output": json.dumps({
            "topic": LONG,
            "reportType": "industry_theme",
            "searchQueries": ["메모리 반도체 가격"],
            "analysisAxes": [{"key": "demand", "label": "수요", "questions": ["수요는?"], "searchQueries": ["메모리 수요 전망"]}],
        }, ensure_ascii=False)}

    monkeypatch.setattr(bridge, "run_agent_prompt", fake_prompt)

    plan, mode = planner.refine_plan_with_llm(planner.build_rule_plan(LONG), LONG)

    assert mode == "llm"
    assert "리서치 주제" in asked["prompt"]
    assert plan["searchQueries"] == ["메모리 반도체 가격"]


def test_with_no_key_and_no_cli_it_stays_on_rules(monkeypatch):
    import features.llm_settings.client as client
    from features.agent_mode import bridge

    monkeypatch.setattr(client, "use_llm_analysis", lambda: True)
    monkeypatch.setattr(client, "selected_cli_config", lambda: {"enabled": True, "apiKey": ""})
    monkeypatch.setattr(bridge, "bridge_status", lambda *a, **k: {"available": False})

    plan = planner.build_topic_plan("custom", custom_label=LONG)

    assert plan["plannerMode"] == "rules"
    assert plan["analysisAxes"]


def test_the_preview_uses_the_engine_by_default(monkeypatch):
    """엔진을 설정해 둔 사용자는 그 순간부터 Agent 사용을 허락한 것으로 본다.

    계획을 보려고 버튼을 두 번 누르게 하는 것은 확인이 아니라 절차다.
    """
    import features.llm_settings.client as client
    from features.agent_mode import bridge

    monkeypatch.setattr(client, "use_llm_analysis", lambda: True)
    monkeypatch.setattr(client, "selected_cli_config", lambda: {"enabled": True, "apiKey": ""})
    monkeypatch.setattr(bridge, "bridge_status", lambda *a, **k: {"available": True})
    monkeypatch.setattr(bridge, "run_agent_prompt", lambda *a, **k: {"output": json.dumps({
        "topic": LONG,
        "reportType": "industry_theme",
        "searchQueries": ["메모리 반도체 가격"],
        "analysisAxes": [{"key": "demand", "label": "수요", "questions": ["수요는?"], "searchQueries": ["메모리 수요 전망"]}],
    }, ensure_ascii=False)})

    plan = planner.build_topic_plan("custom", custom_label=LONG)

    assert plan["plannerMode"] == "llm"


def test_the_rules_choice_skips_the_engine(monkeypatch):
    """빠른 계획이 필요할 때가 있다. 그때만 규칙으로 내려간다."""
    from features.agent_mode import bridge

    def explode(*_args, **_kwargs):
        raise AssertionError("규칙 계획을 골랐는데 Agent CLI를 호출했다")

    monkeypatch.setattr(bridge, "run_agent_prompt", explode)

    plan = planner.build_topic_plan("custom", custom_label=LONG, llm_override=False)

    assert plan["plannerMode"] == "rules"
