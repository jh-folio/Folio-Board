from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from features.agent_mode import bridge


CODEX = {"id": "codex", "label": "Codex CLI", "executable": "codex", "available": True}
CLAUDE = {"id": "claude", "label": "Claude Code CLI", "executable": "claude", "available": True}


def _command(*, web_search: bool = False) -> list[str]:
    with patch("features.agent_mode.setup.configured_model", return_value="gpt-5.6-terra"):
        return bridge._adapter_command(CODEX, "PROMPT", web_search=web_search)


def _assert_briefing_restrictions(command: list[str], *, node_repl: bool = True) -> None:
    for feature in bridge._BRIEFING_DISABLED_CODEX_FEATURES:
        assert f"features.{feature}=false" in command
    assert (bridge._BRIEFING_DISABLED_NODE_REPL in command) is node_repl


def test_mcp_discovery_accepts_an_empty_native_list_without_legacy_override():
    result = Mock(returncode=0, stdout="[]", stderr="")
    with patch.object(bridge.subprocess, "run", return_value=result) as run:
        names = bridge._briefing_mcp_server_names(CODEX)

    assert names == frozenset()
    assert run.call_args.args[0] == ["codex", "mcp", "list", "--json", "-c", "features.plugins=false"]
    assert run.call_args.kwargs["cwd"] == bridge.ROOT
    assert run.call_args.kwargs["timeout"] == bridge._BRIEFING_MCP_DISCOVERY_TIMEOUT_SECONDS


def test_mcp_discovery_preserves_url_config_by_using_only_the_server_name():
    result = Mock(returncode=0, stdout='[{"name":"node_repl","url":"https://example.invalid/mcp"}]', stderr="")
    with patch.object(bridge.subprocess, "run", return_value=result):
        names = bridge._briefing_mcp_server_names(CODEX)

    assert names == frozenset({"node_repl"})


@pytest.mark.parametrize("result", [
    Mock(returncode=1, stdout="private details", stderr="private details"),
    Mock(returncode=0, stdout="not json", stderr=""),
    Mock(returncode=0, stdout='[{"name":null}]', stderr=""),
])
def test_mcp_discovery_fails_closed_without_exposing_cli_output(result):
    with patch.object(bridge.subprocess, "run", return_value=result):
        with pytest.raises(RuntimeError, match="MCP 구성을 확인") as error:
            bridge._briefing_mcp_server_names(CODEX)

    assert "private details" not in str(error.value)


def test_briefing_codex_command_disables_only_known_ui_channels_and_keeps_native_web_search():
    ordinary = _command(web_search=True)
    assert "tools.web_search=true" in ordinary
    assert bridge._BRIEFING_DISABLED_NODE_REPL not in ordinary
    assert not any(item.startswith("features.browser_use=") for item in ordinary)

    with patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset({"node_repl"})):
        with bridge._briefing_codex_tool_policy("briefing", CODEX):
            briefing = _command(web_search=True)

    _assert_briefing_restrictions(briefing)
    assert "tools.web_search=true" in briefing
    assert "--model" in briefing and "gpt-5.6-terra" in briefing
    assert bridge._BRIEFING_DISABLED_NODE_REPL not in _command()


def test_briefing_prompt_instructs_the_child_to_stay_with_local_context_and_out_of_ui():
    prompt = bridge._agent_prompt(Path("C:/context.json"), {"taskType": "briefing"})

    assert "local Context Pack" in prompt
    assert "must not open or control a browser" in prompt


def test_nonbriefing_and_non_codex_contexts_never_probe_or_apply_the_policy():
    with patch.object(bridge, "_briefing_mcp_server_names") as discover:
        with bridge._briefing_codex_tool_policy("company_analysis", CODEX):
            assert bridge._briefing_codex_tool_policy_args() == []
        with bridge._briefing_codex_tool_policy("briefing", CLAUDE):
            assert bridge._briefing_codex_tool_policy_args() == []

    discover.assert_not_called()


def test_briefing_policy_covers_prepare_initial_correction_and_nested_commit_calls():
    """Nested CLI calls inherit only this briefing's ContextVar policy."""
    captured: list[tuple[str, list[str]]] = []
    pack = {
        "taskType": "briefing",
        "artifactType": "briefing",
        "artifactId": "2099-12-31",
        "title": "Test Briefing",
        "outputContract": {"format": "markdown", "retryOnViolation": 1},
        "draftArtifact": {"date": "2099-12-31"},
    }
    pack_path = Path("C:/unused-pack.json")

    def fake_invoke(selected, prompt, timeout, job_id="", model_override="", *, web_search=False, **_kwargs):
        with patch("features.agent_mode.setup.configured_model", return_value="gpt-5.6-terra"):
            captured.append((prompt, bridge._adapter_command(
                selected, prompt, model_override=model_override, web_search=web_search
            )))
        return "draft"

    def fake_prepare(task_type, **_kwargs):
        assert task_type == "briefing"
        bridge.run_agent_prompt("nested lookup", serialize=False, web_search=True)
        bridge.run_agent_prompt("nested semantic comparison", serialize=False)
        return pack, pack_path

    def fake_writeback(_pack, **_kwargs):
        bridge.run_agent_prompt("nested concentration repair", serialize=False, web_search=True)
        return {"date": "2099-12-31", "title": "Test Briefing"}

    with (
        patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset({"node_repl"})) as discover,
        patch.object(bridge, "_select_adapter", return_value=CODEX),
        patch.object(bridge, "_invoke_agent_cli", side_effect=fake_invoke),
        patch.object(bridge.agent_service, "prepare_pack", side_effect=fake_prepare),
        patch.object(bridge.agent_service, "writeback_pack", side_effect=fake_writeback),
        patch.object(bridge.schema, "update_pack_status"),
        patch.object(bridge, "briefing_contract_violations", side_effect=[["missing heading"], []]),
    ):
        bridge.run_agent_task("briefing")

    discover.assert_called_once_with(CODEX)
    assert len(captured) == 5
    assert captured[0][0] == "nested lookup"
    assert captured[1][0] == "nested semantic comparison"
    assert "Agent Context Pack" in captured[2][0]  # initial briefing generation
    assert "previous briefing output violated" in captured[3][0]  # correction
    assert captured[4][0] == "nested concentration repair"
    for _prompt, command in captured:
        _assert_briefing_restrictions(command)
    assert "tools.web_search=true" in captured[0][1]
    assert "tools.web_search=true" in captured[4][1]
    assert bridge._BRIEFING_DISABLED_NODE_REPL not in _command()


def test_briefing_policy_covers_the_durable_commit_path():
    pack = {
        "taskType": "briefing",
        "artifactType": "briefing",
        "artifactId": "2099-12-31",
        "title": "Test Briefing",
        "outputContract": {"format": "markdown"},
        "draftArtifact": {"date": "2099-12-31"},
    }
    captured: list[list[str]] = []

    def fake_invoke(selected, prompt, timeout, job_id="", model_override="", *, web_search=False, **_kwargs):
        captured.append(_command(web_search=web_search))
        return "durable draft"

    with (
        patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset()),
        patch.object(bridge, "_select_adapter", return_value=CODEX),
        patch.object(bridge.job_runtime, "is_durable_job", return_value=True),
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, Path("C:/unused-pack.json"))),
        patch.object(bridge, "_invoke_agent_cli", side_effect=fake_invoke),
        patch.object(bridge.schema, "update_pack_status"),
        patch.object(bridge.job_runtime, "commit_json_output", return_value={"artifactId": "2099-12-31"}) as commit,
    ):
        result = bridge.run_agent_task("briefing", job_id="durable-job")

    commit.assert_called_once()
    assert result["artifactId"] == "2099-12-31"
    _assert_briefing_restrictions(captured[0], node_repl=False)
    assert bridge._briefing_codex_tool_policy_args() == []


@pytest.mark.parametrize("failure_phase", ["prepare", "commit"])
def test_briefing_policy_resets_after_prepare_or_commit_failure(failure_phase):
    pack = {
        "taskType": "briefing",
        "artifactType": "briefing",
        "artifactId": "2099-12-31",
        "title": "Test Briefing",
        "outputContract": {"format": "markdown"},
        "draftArtifact": {"date": "2099-12-31"},
    }
    prepare = Mock(return_value=(pack, Path("C:/unused-pack.json")))
    if failure_phase == "prepare":
        prepare.side_effect = RuntimeError("prepare failed")

    with (
        patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset({"node_repl"})),
        patch.object(bridge, "_select_adapter", return_value=CODEX),
        patch.object(bridge.job_runtime, "is_durable_job", return_value=failure_phase == "commit"),
        patch.object(bridge.agent_service, "prepare_pack", prepare),
        patch.object(bridge, "_invoke_agent_cli", return_value="draft"),
        patch.object(bridge.schema, "update_pack_status"),
        patch.object(bridge.job_runtime, "commit_json_output", side_effect=RuntimeError("commit failed")),
    ):
        with pytest.raises(RuntimeError, match=f"{failure_phase} failed"):
            bridge.run_agent_task("briefing", job_id="durable-job")

    assert bridge._briefing_codex_tool_policy_args() == []
    assert bridge._BRIEFING_DISABLED_NODE_REPL not in _command()


def test_briefing_policy_resets_after_failure_and_does_not_leak_to_another_thread():
    with patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset({"node_repl"})):
        with pytest.raises(RuntimeError, match="boom"):
            with bridge._briefing_codex_tool_policy("briefing", CODEX):
                raise RuntimeError("boom")
    assert bridge._BRIEFING_DISABLED_NODE_REPL not in _command()

    entered = threading.Event()
    release = threading.Event()
    worker_commands: list[list[str]] = []

    def briefing_worker():
        with bridge._briefing_codex_tool_policy("briefing", CODEX):
            entered.set()
            assert release.wait(timeout=2)
            worker_commands.append(_command())

    with patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset({"node_repl"})):
        worker = threading.Thread(target=briefing_worker)
        worker.start()
        assert entered.wait(timeout=2)
        concurrent_ordinary = _command()
        release.set()
        worker.join(timeout=2)

    assert not worker.is_alive()
    _assert_briefing_restrictions(worker_commands[0])
    assert bridge._BRIEFING_DISABLED_NODE_REPL not in concurrent_ordinary
