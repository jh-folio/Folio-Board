"""CLI-only execution and read-only migration boundaries."""
import json
from pathlib import Path
import pytest
from features.llm_settings import client, task_policy, task_runtime, settings_service
from features.agent_mode.generation_mode import normalize_generation_mode


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setattr(client, "load_dotenv", lambda: None)
    monkeypatch.setattr(settings_service, "load_dotenv", lambda: None)
    monkeypatch.setenv("AI_AGENT_ENABLED", "1")
    monkeypatch.setenv("AI_AGENT_MODE", "cli")


@pytest.mark.parametrize("mode", ["api", "llm_api", "llm-api", "llm"])
def test_legacy_execution_modes_are_rejected(mode):
    with pytest.raises(ValueError, match="llm_api_removed"):
        normalize_generation_mode(mode)


@pytest.mark.parametrize("body", [
    {"agent": {"mode": "api"}}, {"openai": {}},
    {"llm": {"provider": "openai"}}, {"llm": {"providers": {}}},
])
def test_api_settings_rejected_before_any_write(monkeypatch, body):
    monkeypatch.setattr(settings_service, "write_env_values", lambda _: pytest.fail("write"))
    with pytest.raises(task_policy.TaskPolicyError) as error:
        settings_service.save_settings(body)
    assert error.value.code == "llm_api_removed"


def test_legacy_policy_read_preserves_bytes_and_blocks_execution(tmp_path):
    raw = {"schemaVersion": 1, "revision": 7, "tasks": {
        "company_analysis": {"enabled": True, "config": {
            "mode": "api", "provider": "openai", "model": "old-model", "reasoningEffort": "medium"}}}}
    path = task_policy.task_policy_path(tmp_path)
    path.write_text(json.dumps(raw), encoding="utf-8")
    before = path.read_bytes()
    policy = task_policy.load_task_policy(root=tmp_path)
    with pytest.raises(task_policy.TaskPolicyError) as error:
        task_policy.resolve_task_policy("company_analysis", policy=policy, global_enabled=True)
    assert error.value.code == "llm_api_removed"
    assert path.read_bytes() == before
    off = task_policy.save_task_policy({"expectedRevision": 7, "tasks": {
        "company_analysis": {"enabled": False}}}, root=tmp_path)
    assert off["tasks"]["company_analysis"]["config"]["mode"] == "api"
    with pytest.raises(task_policy.TaskPolicyError):
        task_policy.save_task_policy({"expectedRevision": 8, "tasks": {
            "company_analysis": {"enabled": True}}}, root=tmp_path)
    saved = task_policy.save_task_policy({"expectedRevision": 8, "tasks": {
        "company_analysis": {"enabled": True, "config": {
            "mode": "cli", "provider": "codex", "model": "gpt-5.6-sol", "reasoningEffort": "medium"}}}}, root=tmp_path)
    assert saved["revision"] == 9
    assert task_policy.resolve_task_policy("company_analysis", policy=saved, global_enabled=True)["provider"] == "codex"


def test_frozen_api_job_cannot_be_resumed():
    with pytest.raises(task_policy.TaskPolicyError):
        task_runtime.task_snapshot("company_analysis", {
            "taskKey": "company_analysis", "enabled": True, "mode": "api"})


def test_cli_helper_inherits_snapshot_and_never_reads_keys(monkeypatch):
    from features.agent_mode import bridge
    calls = []
    monkeypatch.setattr(bridge, "run_agent_prompt", lambda prompt, **kw: calls.append((prompt, kw)) or {"output": '{"ok":true}'})
    monkeypatch.setattr(client, "_load_secret_value", lambda _: pytest.fail("credential read"))
    with task_runtime.bind_task_policy({"taskKey": "company_analysis", "enabled": True,
            "mode": "cli", "provider": "claude", "model": "claude-sonnet-5", "reasoningEffort": "high"}):
        result = client.request_cli_text(client.selected_cli_config(), "instruction", "evidence", json_mode=True, include_usage=True, web_search=False)
    assert result == ('{"ok":true}', '', {"transport": "cli", "outputTokenCapEnforced": False})
    assert calls[0][1]["adapter"] == "claude"
    assert calls[0][1]["model"] == "claude-sonnet-5"
    assert calls[0][1]["reasoning_effort"] == "high"
    assert calls[0][1]["web_search"] is False


def test_cli_failure_is_not_retried_through_http(monkeypatch):
    from features.agent_mode import bridge
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("HTTP"))
    monkeypatch.setattr(bridge, "run_agent_prompt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("quota")))
    with pytest.raises(RuntimeError, match="quota"):
        client.request_cli_text({"enabled": True, "provider": "codex"}, "p", "c")


def test_retired_secrets_are_not_loaded_or_migrated(tmp_path, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(client, "ROOT", tmp_path)
    monkeypatch.setenv("AI_AGENT_MODE", "cli")
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    before = b"OPENAI_API_KEY=synthetic-test-key\nAI_AGENT_MODE=api\n"
    path.write_bytes(before)
    seen = []
    monkeypatch.setattr(client, "_load_secret_value", lambda key: seen.append(key) or "")
    monkeypatch.setattr(client, "_store_secret_value", lambda *a: pytest.fail("migration"))
    client.load_dotenv()
    assert path.read_bytes() == before
    assert "OPENAI_API_KEY" not in seen


def test_no_runtime_provider_http_endpoints():
    root = Path(__file__).resolve().parents[3]
    forbidden = ("api.openai.com/v1", "api.anthropic.com/v1", "generativelanguage.googleapis.com/v1")
    for path in root.rglob("*.py"):
        if "tests" not in path.parts:
            assert not any(url in path.read_text(encoding="utf-8") for url in forbidden), path


def test_failed_environment_commit_preserves_file_and_process(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(client, "ROOT", tmp_path)
    path = tmp_path / ".env"
    original = b"AI_AGENT_MODE=api\nOPENAI_API_KEY=synthetic-preserved\n"
    path.write_bytes(original)
    monkeypatch.setenv("AI_AGENT_MODE", "api")
    monkeypatch.setattr("features.common.atomic_replace.write_bytes_atomic", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        client.write_env_values({"AI_AGENT_MODE": "cli"})
    assert path.read_bytes() == original
    assert os.environ["AI_AGENT_MODE"] == "api"


def test_nested_cli_inherits_job_and_reenters_lock(monkeypatch):
    from features.agent_mode import bridge
    seen = []
    monkeypatch.setattr(bridge, "get_job", lambda _: {"status": "running"})
    monkeypatch.setattr(bridge, "_select_adapter", lambda _: {"id": "codex"})
    monkeypatch.setattr(bridge, "_invoke_agent_cli", lambda adapter, prompt, timeout, job_id, **kw: seen.append(job_id) or "ok")
    with bridge._RUN_SEMAPHORE, bridge._bind_prompt_job("job-parent"):
        assert client.request_cli_text({"enabled": True, "provider": "codex"}, "p", "c")[0] == "ok"
    assert seen == ["job-parent"]


def test_cancelled_nested_cli_does_not_start(monkeypatch):
    from features.agent_mode import bridge
    monkeypatch.setattr(bridge, "get_job", lambda _: {"status": "cancel_requested"})
    monkeypatch.setattr(bridge, "_select_adapter", lambda _: pytest.fail("CLI started"))
    with bridge._bind_prompt_job("job-parent"), pytest.raises(RuntimeError, match="cancelled"):
        client.request_cli_text({"enabled": True, "provider": "codex"}, "p", "c")


def test_rules_snapshot_cannot_start_auxiliary_cli(monkeypatch):
    from features.agent_mode import bridge
    monkeypatch.setattr(bridge, "_select_adapter", lambda _: pytest.fail("CLI started"))
    with task_runtime.bind_task_policy({"taskKey": "company_analysis", "enabled": False}):
        with pytest.raises(RuntimeError, match="ai_disabled"):
            bridge.run_agent_prompt("never sent")
