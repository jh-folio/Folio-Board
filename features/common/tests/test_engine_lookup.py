"""`configured_lookup_call()`이 bridge.py의 관측 사실을 그대로 넘기는지 검사한다.

`LookupCall`의 타입(`Callable[[str, str], str]`)은 바꾸지 않는다 — company_analysis와
topic_report는 이 값을 모른 채 그대로 계속 동작해야 한다(§6 규칙 14). 대신 반환된
콜러블 자기 자신에 `web_search_facts` 속성을 additive로 얹는다. 이 파일은 그 통로만
검사한다 — 실제 CLI 실행은 다른 곳(`test_web_search_facts.py`)이 검사한다.
"""
from __future__ import annotations

from features.common.engine_lookup import configured_lookup_call


def test_cli_branch_exposes_the_observed_facts_as_an_attribute(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        "features.common.engine_lookup.selected_llm_config", lambda: {"apiKey": ""}
    )

    def fake_prompt(prompt, **kwargs):
        return {
            "output": "looked-up text",
            "adapter": "claude",
            "webSearch": True,
            "webSearchFacts": {"enabled": True, "used": "yes", "observation": "complete"},
        }

    monkeypatch.setattr("features.agent_mode.bridge.run_agent_prompt", fake_prompt)

    invoke = configured_lookup_call()
    output = invoke("prompt", "context")

    assert output == "looked-up text"
    assert invoke.web_search_facts == {"enabled": True, "used": "yes", "observation": "complete"}


def test_cli_branch_leaves_the_attribute_absent_when_bridge_gives_none(monkeypatch):
    """기존 호출부(company_analysis/topic_report)가 새 필드를 몰라도 그대로 동작한다."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        "features.common.engine_lookup.selected_llm_config", lambda: {"apiKey": ""}
    )
    monkeypatch.setattr(
        "features.agent_mode.bridge.run_agent_prompt",
        lambda prompt, **kwargs: {"output": "plain output", "adapter": "codex", "webSearch": True},
    )

    invoke = configured_lookup_call()
    output = invoke("prompt", "context")

    assert output == "plain output"
    assert invoke.web_search_facts is None


def test_api_branch_never_sets_the_attribute(monkeypatch):
    """API 경로는 이번 작업 범위 밖이다 — 여전히 관측하지 않은 것으로 남는다."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(
        "features.common.engine_lookup.selected_llm_config",
        lambda: {"apiKey": "test-only", "provider": "openai", "model": "test"},
    )
    monkeypatch.setattr("features.common.engine_lookup.use_llm_analysis", lambda: True)
    monkeypatch.setattr(
        "features.common.engine_lookup.request_llm_text",
        lambda *args, **kwargs: ("api output", "response-id"),
    )

    invoke = configured_lookup_call()
    output = invoke("prompt", "context")

    assert output == "api output"
    assert not hasattr(invoke, "web_search_facts")
