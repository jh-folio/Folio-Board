"""Focused task-policy transport tests without paid provider calls."""
from __future__ import annotations

from features.agent_mode import bridge
from features.llm_settings import client
from features.llm_settings import task_runtime


def _api_snapshot(*, effort: str = "medium") -> dict:
    return {
        "taskKey": "company_analysis",
        "runtimeTaskType": "company_analysis",
        "enabled": True,
        "mode": "api",
        "provider": "openai",
        "model": "gpt-6-astra",
        "reasoningEffort": effort,
        "policyRevision": 4,
    }


def _cli_snapshot(*, model: str = "gpt-task", effort: str = "xhigh") -> dict:
    return {
        "taskKey": "topic_report",
        "runtimeTaskType": "topic_report",
        "enabled": True,
        "mode": "cli",
        "provider": "codex",
        "model": model,
        "reasoningEffort": effort,
        "policyRevision": 5,
    }


def test_bound_api_task_snapshot_reaches_selected_model_and_reasoning_request(monkeypatch):
    captured: dict = {}

    monkeypatch.setattr(
        client,
        "openai_config",
        lambda: {
            "provider": "openai",
            "apiKey": "task-test-key",
            "geminiApiKey": "",
            "anthropicApiKey": "",
            "model": "gpt-5.6-sol",
            "geminiModel": "gemini-3.5-flash",
            "anthropicModel": "claude-sonnet-5",
            "enabled": True,
        },
    )
    monkeypatch.setattr(
        client,
        "post_json",
        lambda url, body, headers, timeout: captured.update(
            url=url, body=body, headers=headers, timeout=timeout
        ) or {
            "status": "completed",
            "id": "task-response",
            "output": [{"content": [{"type": "output_text", "text": "ok"}]}],
        },
    )

    with task_runtime.bind_task_policy(_api_snapshot()):
        config = client.selected_llm_config()
        client.request_openai(config, "prompt", "context")

    assert config["provider"] == "openai"
    assert config["model"] == "gpt-6-astra"
    assert config["reasoningEffort"] == "medium"
    assert captured["body"]["model"] == "gpt-6-astra"
    assert captured["body"]["reasoning"] == {"effort": "medium"}


def test_bound_cli_task_snapshot_reaches_adapter_model_and_effort():
    snapshot = _cli_snapshot()
    with task_runtime.bind_task_policy(snapshot):
        kwargs = bridge._task_cli_kwargs(task_runtime.current_task_policy())
        command = bridge._adapter_command(
            {"id": "codex", "executable": "codex", "available": True},
            "PROMPT",
            **kwargs,
        )

    assert kwargs == {"model_override": "gpt-task", "reasoning_effort": "xhigh"}
    assert command[command.index("--model") : command.index("--model") + 2] == ["--model", "gpt-task"]
    assert command[command.index("-c") : command.index("-c") + 2] == ["-c", "model_reasoning_effort=xhigh"]


def test_queued_snapshot_is_defensive_and_global_off_blocks_execution():
    original = _cli_snapshot(model="first-model", effort="high")
    queued = bridge._queued_task_snapshot("topic_report", {"_task_policy_snapshot": original})

    original["model"] = "later-model"
    original["reasoningEffort"] = "low"
    assert queued["model"] == "first-model"
    assert queued["reasoningEffort"] == "high"

    blocked = bridge._bridge_task_gate({**queued, "enabled": False, "mode": "rules"})
    assert blocked["generationMode"] == "rules"
    assert blocked["policy"]["model"] == "first-model"


def test_global_task_policy_inherits_saved_effort_for_unconfigured_tasks(monkeypatch):
    from features.agent_mode import setup
    from features.llm_settings import task_policy

    monkeypatch.setattr(client, "ai_agent_enabled", lambda: True)
    monkeypatch.setattr(client, "ai_agent_mode", lambda: "cli")
    monkeypatch.setattr(client, "configured_global_reasoning_effort", lambda **_: "ultra")
    monkeypatch.setattr(setup, "configured_provider", lambda: "codex")
    monkeypatch.setattr(setup, "configured_model", lambda _provider: "gpt-6-astra")

    policy = {
        "schemaVersion": 1,
        "revision": 1,
        "tasks": {
            key: {"enabled": False, "config": None}
            for key in task_policy.TASK_KEYS
        },
    }
    resolved = task_policy.resolve_task_policy("topic_report", policy=policy, global_enabled=True)

    assert resolved["source"] == "global"
    assert resolved["model"] == "gpt-6-astra"
    assert resolved["reasoningEffort"] == "ultra"
