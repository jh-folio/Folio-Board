"""의미 판정은 CLI 구성에서도 돌아야 한다.

예전에는 두 겹으로 막혀 있었다 — `decorate_candidate`가 `generation.mode == "llm"`일 때만
평가를 불렀는데 Agent 산출물의 mode는 `agent`이고, `semantic.py`는 API 키만 보는데
CLI 모드에서는 키가 없는 것이 정상이다. 그래서 CLI로 브리핑을 만드는 구성에서는 모든 변화가
`not_evaluated`로 남았고, 화면은 그것을 "판정하지 못했다"로 읽어 **이미 연결된** Agent를
연결하라고 안내했다.

의미 엔진 자체는 브리핑 저장에서 제거되었지만, 회사·토픽·시장 메모리의 공통 Change
Intelligence 경로와 CLI/API 분기 계약은 계속 유지한다.
"""
from __future__ import annotations

import features.common.change_intelligence.semantic as semantic


def _summary():
    return {
        "artifactKind": "briefing",
        "changedItems": [{
            "id": "u1", "kind": "market_driver", "subject": "금리", "change": "changed",
            "contextDocs": ["연준 인하 기대"], "previousContextDocs": ["연준 동결 전망"],
        }],
    }


def test_bound_cli_does_not_read_unused_api_configuration(monkeypatch):
    from features.llm_settings.task_runtime import bind_task_policy

    def invalid_api():
        raise AssertionError("unused API configuration accessed")

    monkeypatch.setattr("features.llm_settings.client.selected_llm_config", invalid_api)
    calls = []
    monkeypatch.setattr("features.agent_mode.bridge.run_agent_prompt", lambda *args, **kwargs: calls.append(kwargs) or {"output": '{"units": [{"id": "u1", "verdict": "no_new_information"}]}'})
    with bind_task_policy({"taskKey": "daily_briefing", "enabled": True, "mode": "cli", "provider": "codex", "model": "test-model", "reasoningEffort": "high"}):
        result = semantic.evaluate_semantic_changes(_summary())
    assert result["status"] == "evaluated"
    assert calls[0]["adapter"] == "codex"
    assert calls[0]["model"] == "test-model"
    assert calls[0]["reasoning_effort"] == "high"
    assert calls[0]["diagnostic_primary"] is False


def test_invalid_optional_api_configuration_does_not_block_report(monkeypatch):
    def invalid_api():
        raise ValueError("private configuration")

    monkeypatch.setattr("features.llm_settings.client.selected_llm_config", invalid_api)
    result = semantic.evaluate_semantic_changes(_summary())
    assert result == {"status": "not_evaluated", "verdicts": {}, "reason": "llm_configuration_invalid"}


def test_non_object_semantic_response_is_not_evaluated():
    result = semantic.evaluate_semantic_changes(_summary(), llm_call=lambda *_: ["invalid"])
    assert result["status"] == "not_evaluated"
    assert result["reason"] == "no_valid_verdicts"


def test_a_cli_only_install_still_gets_a_verdict(monkeypatch):
    """키가 없다고 판정을 접지 않는다. CLI 모드에서는 키가 없는 것이 정상이다."""
    monkeypatch.setattr(
        "features.llm_settings.client.selected_llm_config", lambda: {"apiKey": "", "provider": "", "model": ""}
    )
    monkeypatch.setattr("features.llm_settings.client.default_generation_mode", lambda: "llm_cli")
    seen = {}

    def fake_prompt(prompt, **kwargs):
        seen["serialize"] = kwargs.get("serialize")
        return {"output": '{"units": [{"id": "u1", "verdict": "new_information", "note": "인하 기대로 전환"}]}' }

    monkeypatch.setattr("features.agent_mode.bridge.run_agent_prompt", fake_prompt)

    result = semantic.evaluate_semantic_changes(_summary())

    assert result["status"] != "not_evaluated"
    assert result["verdicts"]["u1"]["verdict"] == "new_information"
    # **세마포어를 다시 잡지 않는다.** 이 호출은 이미 그것을 쥔 잡 스레드 안에서 일어난다.
    assert seen["serialize"] is False


def test_no_engine_at_all_still_reports_not_evaluated(monkeypatch):
    monkeypatch.setattr(
        "features.llm_settings.client.selected_llm_config", lambda: {"apiKey": "", "provider": "", "model": ""}
    )
    monkeypatch.setattr("features.llm_settings.client.default_generation_mode", lambda: "rules")

    result = semantic.evaluate_semantic_changes(_summary())

    assert result["status"] == "not_evaluated"
    assert result["reason"] == "llm_unavailable"


def test_a_cli_failure_degrades_instead_of_raising(monkeypatch):
    """판정 실패가 브리핑 커밋을 무너뜨리면 안 된다."""
    monkeypatch.setattr(
        "features.llm_settings.client.selected_llm_config", lambda: {"apiKey": "", "provider": "", "model": ""}
    )
    monkeypatch.setattr("features.llm_settings.client.default_generation_mode", lambda: "llm_cli")

    def boom(prompt, **kwargs):
        raise RuntimeError("cli down")

    monkeypatch.setattr("features.agent_mode.bridge.run_agent_prompt", boom)

    result = semantic.evaluate_semantic_changes(_summary())

    assert result["status"] == "not_evaluated"
    assert result["reason"] == "llm_failed"


def test_the_api_path_is_unchanged(monkeypatch):
    """키가 있으면 예전처럼 API를 쓴다. CLI 분기가 그 경로를 가로채지 않는다."""
    monkeypatch.setattr(
        "features.llm_settings.client.selected_llm_config",
        lambda: {"apiKey": "k", "provider": "openai", "model": "gpt"},
    )
    calls = []

    def fake_request(cfg, prompt, context, **kwargs):
        calls.append(cfg["provider"])
        return ('{"units": [{"id": "u1", "verdict": "no_new_information", "note": "같은 이야기"}]}', "r", {})

    monkeypatch.setattr("features.llm_settings.client.request_llm_text", fake_request)

    def explode(*args, **kwargs):
        raise AssertionError("키가 있으면 CLI를 부르지 않는다")

    monkeypatch.setattr("features.agent_mode.bridge.run_agent_prompt", explode)

    result = semantic.evaluate_semantic_changes(_summary())

    assert calls == ["openai"]
    assert result["verdicts"]["u1"]["verdict"] == "no_new_information"


def test_the_bridge_can_run_without_retaking_the_semaphore():
    """`_RUN_SEMAPHORE`는 재진입이 안 되고 acquire에 타임아웃도 없다.

    잡 스레드 안에서 다시 잡으면 그 잡이 영원히 멈춘다 — 브리핑 생성 잡은 커밋까지
    통째로 그 세마포어 안에서 돈다.
    """
    import inspect
    import threading

    from features.agent_mode import bridge

    assert isinstance(bridge._RUN_SEMAPHORE, type(threading.Semaphore(1)))
    source = inspect.getsource(bridge.run_agent_prompt)
    assert "if not serialize:" in source
    # 직렬화를 건너뛰는 분기가 세마포어 acquire보다 앞에 있어야 한다.
    assert source.index("if not serialize:") < source.index("_RUN_SEMAPHORE.acquire")
