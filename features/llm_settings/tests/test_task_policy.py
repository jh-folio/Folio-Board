from __future__ import annotations

import json
from pathlib import Path

import pytest

from features.llm_settings import task_policy


def api_config(model: str = "gpt-6-astra", effort: str = "high") -> dict:
    return {"mode": "api", "provider": "openai", "model": model, "reasoningEffort": effort}


def test_missing_policy_is_all_off_and_does_not_create_file(tmp_path: Path) -> None:
    policy = task_policy.load_task_policy(root=tmp_path)

    assert policy["schemaVersion"] == 1
    assert policy["revision"] == 0
    assert set(policy["tasks"]) == set(task_policy.TASK_KEYS)
    assert all(row == {"enabled": False, "config": None} for row in policy["tasks"].values())
    assert not task_policy.task_policy_path(tmp_path).exists()


def test_first_save_and_off_to_on_restores_previous_config(tmp_path: Path) -> None:
    saved = task_policy.save_task_policy({
        "expectedRevision": 0,
        "tasks": {"company_analysis": {"enabled": True, "config": api_config()}},
    }, root=tmp_path)
    assert saved["revision"] == 1
    assert saved["tasks"]["company_analysis"]["config"] == api_config()

    disabled = task_policy.save_task_policy({
        "expectedRevision": 1,
        "tasks": {"company_analysis": {"enabled": False}},
    }, root=tmp_path)
    assert disabled["tasks"]["company_analysis"]["enabled"] is False
    assert disabled["tasks"]["company_analysis"]["config"] == api_config()

    restored = task_policy.save_task_policy({
        "expectedRevision": 2,
        "tasks": {"company_analysis": {"enabled": True}},
    }, root=tmp_path)
    assert restored["tasks"]["company_analysis"]["config"] == api_config()


def test_stale_revision_returns_latest_without_overwriting(tmp_path: Path) -> None:
    task_policy.save_task_policy({
        "expectedRevision": 0,
        "tasks": {"daily_briefing": {"enabled": True, "config": api_config("gpt-5.6-sol", "provider_default")}},
    }, root=tmp_path)
    with pytest.raises(task_policy.TaskPolicyConflict) as caught:
        task_policy.save_task_policy({
            "expectedRevision": 0,
            "tasks": {"daily_briefing": {"enabled": True, "config": api_config()}},
        }, root=tmp_path)
    assert caught.value.code == "task_policy_revision_conflict"
    assert caught.value.latest["revision"] == 1
    assert task_policy.load_task_policy(root=tmp_path)["tasks"]["daily_briefing"]["config"]["model"] == "gpt-5.6-sol"


@pytest.mark.parametrize("config", [
    {"mode": "api", "provider": "gemini", "model": "gemini-3.5-flash", "reasoningEffort": "high"},
    {"mode": "api", "provider": "openai", "model": "gpt-5.6-sol", "reasoningEffort": "high"},
    {"mode": "cli", "provider": "codex", "model": "gpt-5.5", "reasoningEffort": "max"},
])
def test_unsupported_reasoning_is_rejected_before_write(tmp_path: Path, config: dict) -> None:
    with pytest.raises(task_policy.TaskPolicyError) as caught:
        task_policy.save_task_policy({
            "expectedRevision": 0,
            "tasks": {"topic_report": {"enabled": True, "config": config}},
        }, root=tmp_path)
    assert caught.value.code == "task_policy_unsupported_reasoning"
    assert not task_policy.task_policy_path(tmp_path).exists()


@pytest.mark.parametrize(
    ("provider", "effort"),
    [
        ("codex", "low"),
        ("codex", "xhigh"),
        ("claude", "max"),
        ("antigravity", "medium"),
    ],
)
def test_supported_cli_reasoning_is_normalized_and_saved(tmp_path: Path, provider: str, effort: str) -> None:
    saved = task_policy.save_task_policy({
        "expectedRevision": 0,
        "tasks": {
            "topic_report": {
                "enabled": True,
                "config": {"mode": "cli", "provider": provider, "model": "task-model", "reasoningEffort": effort},
            },
        },
    }, root=tmp_path)
    assert saved["tasks"]["topic_report"]["config"]["reasoningEffort"] == effort


def test_corrupt_and_unsupported_schema_are_explicit_errors(tmp_path: Path) -> None:
    path = task_policy.task_policy_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(task_policy.TaskPolicyError) as corrupt:
        task_policy.load_task_policy(root=tmp_path)
    assert corrupt.value.code == "task_policy_corrupt"
    path.write_text(json.dumps({"schemaVersion": 99, "revision": 0, "tasks": {}}), encoding="utf-8")
    with pytest.raises(task_policy.TaskPolicyError) as schema:
        task_policy.load_task_policy(root=tmp_path)
    assert schema.value.code == "task_policy_schema_unsupported"


def test_explicit_override_does_not_require_unrelated_global_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    from features.llm_settings import client
    from features.agent_mode import setup
    from features.agent_mode import bridge

    monkeypatch.setattr(client, "ai_agent_enabled", lambda: True)
    monkeypatch.setattr(client, "ai_agent_mode", lambda: "cli")
    monkeypatch.setattr(setup, "configured_provider", lambda: "auto")
    monkeypatch.setattr(bridge, "bridge_status", lambda **_: {"selectedAdapter": ""})
    resolved = task_policy.resolve_task_policy("company_analysis", policy={
        "schemaVersion": 1,
        "revision": 7,
        "tasks": {
            **{key: {"enabled": False, "config": None} for key in task_policy.TASK_KEYS},
            "company_analysis": {"enabled": True, "config": api_config()},
        },
    })
    assert resolved["source"] == "task"
    assert resolved["mode"] == "api"
    assert resolved["provider"] == "openai"
    assert resolved["policyRevision"] == 7


def test_global_off_remains_execution_gate_and_aliases_are_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    from features.llm_settings import client

    monkeypatch.setattr(client, "ai_agent_enabled", lambda: False)
    resolved = task_policy.resolve_task_policy("thesis_delta", policy={
        "schemaVersion": 1,
        "revision": 2,
        "tasks": {key: {"enabled": False, "config": None} for key in task_policy.TASK_KEYS},
    })
    assert resolved["taskKey"] == "thesis_review"
    assert resolved["mode"] == "rules"
    assert resolved["enabled"] is False
