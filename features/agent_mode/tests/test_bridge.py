import sys
import os
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

from features.agent_mode import bridge
from features.agent_mode import schema
from features.agent_mode.briefing_contract import briefing_contract_violations, briefing_output_contract
from features.common import jobs
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import Adapter, GenerationMode, JobKind, JobMode, JobStatus, TaskType


def _valid_briefing_output():
    contract = briefing_output_contract("both")
    dated_titles = {
        "US Market Briefing": "# US Market Briefing — 2099.12.31",
        "Korea Market Briefing": "# Korea Market Briefing — 2099.12.31",
        "3. 미국장을 주도한 기업 ①": "## 3. 미국장을 주도한 기업 ① — NVIDIA",
        "4. 미국장을 주도한 기업 ②": "## 4. 미국장을 주도한 기업 ② — Alphabet",
        "3. 한국장을 주도한 기업 ①": "## 3. 한국장을 주도한 기업 ① — Samsung Electronics",
        "4. 한국장을 주도한 기업 ②": "## 4. 한국장을 주도한 기업 ② — SK hynix",
    }
    headings = "\n\n".join(
        dated_titles.get(section, f"## {section}")
        for section in contract["requiredSections"]
    )
    conclusions = "\n".join(
        "**한 줄 결론:** 시장의 가격 반응과 내부 구조를 해석합니다."
        for _ in range(contract["minimumOneLineConclusions"])
    )
    bullets = "\n".join(
        "· 핵심 수치와 원인, 다음 확인점을 점검합니다."
        for _ in range(contract["minimumMiddleDotBullets"])
    )
    prose = "시장 흐름과 근거, 반대 신호, 체크포인트를 줄글로 설명합니다. " * 320
    return f"{headings}\n\n{conclusions}\n{bullets}\n\n{prose}"


def test_probe_requires_executable_to_run():
    version = Mock(returncode=0, stdout="codex-cli 1.0\n", stderr="")
    auth = Mock(returncode=0, stdout="Logged in\n", stderr="")
    with (
        patch.object(bridge, "_configured_executable", return_value=sys.executable),
        patch.object(bridge.subprocess, "run", side_effect=[version, auth]),
    ):
        status = bridge._probe_adapter("codex")
    assert status["available"] is True
    assert status["installed"] is True
    assert status["authenticated"] is True
    assert status["version"]


def test_antigravity_opens_only_after_it_is_actually_measured():
    """재본 결과가 있어야 열린다. `--version`만으로는 열지 않는다."""
    version = Mock(returncode=0, stdout="agy 1.1.12\n", stderr="")
    with (
        patch.object(bridge, "_configured_executable", return_value="/usr/local/bin/agy"),
        patch.object(bridge.subprocess, "run", side_effect=[version]) as run,
        patch("features.agent_mode.agy_capability.cached_file_reads", return_value=True),
    ):
        status = bridge._probe_adapter("antigravity")
    assert status["installed"] is True
    assert status["available"] is True
    assert status["bridgeSupported"] is True
    assert run.call_count == 1


def test_antigravity_stays_shut_until_it_is_measured():
    """**안 재본 것을 된다고 가정하지 않는다.**

    예전 게이트는 버전 숫자로 판정했다. 버전 비교는 권한 문제를 구조적으로 볼 수 없어,
    기준을 넘겼다는 이유로 열어 둔 뒤 Agent 잡 두 건이 모두 실패했다(그전까지
    antigravity로 성공한 잡은 한 건도 없다). 플랫폼으로도 가르지 않는다 — 거부를
    실측한 것은 Windows지만 macOS/Linux를 재본 것도 아니다.
    """
    version = Mock(returncode=0, stdout="agy 9.9.9\n", stderr="")
    for platform in ("nt", "posix"):
        with (
            patch.object(bridge.os, "name", platform),
            patch.object(bridge, "_configured_executable", return_value=r"C:\Apps\agy.exe"),
            patch.object(bridge.subprocess, "run", side_effect=[version]),
            patch("features.agent_mode.agy_capability.cached_file_reads", return_value=None),
        ):
            status = bridge._probe_adapter("antigravity")
        assert status["installed"] is True, platform
        assert status["available"] is False, platform
        assert status["bridgeSupported"] is False, platform
        assert "확인하지 않았습니다" in status["error"], platform


def test_antigravity_command_uses_current_long_model_flag_and_print_prompt():
    adapter = {"id": "antigravity", "executable": "agy", "available": True}
    with patch("features.agent_mode.setup.configured_model", return_value="gemini-3.5-pro"):
        command = bridge._adapter_command(adapter, "PROMPT")
    assert command == ["agy", "--model", "gemini-3.5-pro", "--print", "PROMPT"]
    assert "-m" not in command


@pytest.mark.parametrize("web_search", [False, True])
def test_claude_authors_without_plan_or_inherited_write_tools(web_search):
    command = bridge._adapter_command(
        {"id": "claude", "executable": "claude"}, model_override="sonnet", web_search=web_search,
    )
    assert command[command.index("--permission-mode") + 1] == "dontAsk"
    expected = {"Read", "Glob", "Grep"} | ({"WebSearch"} if web_search else set())
    assert set(command[command.index("--tools") + 1].split(",")) == expected
    assert set(command[command.index("--allowedTools") + 1].split(",")) == expected
    assert command[command.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert "--strict-mcp-config" in command
    assert "bypassPermissions" not in command and "plan" not in command


def test_inline_briefing_preserves_prepared_writer_input_without_draft_charts():
    pack = {
        "taskType": "briefing", "agentInstructions": "evidence only",
        "prompt": "Korean authoring template", "context": "Exact writer evidence source:test-1\nmarket facts",
        "outputContract": {"format": "markdown", "minimumCharacters": 2500},
        "writeBackContract": {"method": "markdown"},
        "internal": {"privateChartData": "DO_NOT_SEND_INTERNAL_CHARTS"},
        "draftArtifact": {"markdown": "DO_NOT_SEND_DRAFT"},
    }
    prompt = bridge._agent_prompt(Path("private-pack.json"), pack, inline_briefing=True)
    for key in ("agentInstructions", "prompt", "context"):
        assert pack[key] in prompt
    assert '"minimumCharacters": 2500' in prompt
    assert "private-pack.json" not in prompt and "DO_NOT_SEND" not in prompt
    assert "Do not enter plan mode" in prompt


def test_claude_briefing_dispatch_delivers_inline_evidence_to_writer(tmp_path):
    pack = {"taskType": "briefing", "artifactId": "2099-12-31",
            "context": "prepared pinned evidence", "prompt": "report template",
            "outputContract": briefing_output_contract("both")}
    adapter = {"id": "claude", "label": "Claude", "executable": "claude", "available": True}
    with (
        patch.object(bridge, "_select_adapter", return_value=adapter),
        patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, tmp_path / "pack.json")),
        patch.object(bridge, "_invoke_agent_cli", return_value=_valid_briefing_output()) as invoke,
        patch.object(bridge.schema, "update_pack_status"),
        patch.object(bridge.job_runtime, "is_durable_job", return_value=True),
        patch.object(bridge.job_runtime, "commit_json_output", return_value={"artifactId": "2099-12-31"}) as commit,
    ):
        bridge.run_agent_task("briefing", {}, job_id="test-claude-inline")
    assert invoke.call_count == 1
    assert pack["context"] in invoke.call_args.args[1]
    assert pack["prompt"] in invoke.call_args.args[1]
    assert "pack.json" not in invoke.call_args.args[1]
    assert commit.call_args.kwargs["contract_failed"] is False


def test_codex_command_uses_current_exec_flags_without_removed_approval_option():
    adapter = {"id": "codex", "executable": "codex", "available": True}
    with patch("features.agent_mode.setup.configured_model", return_value="gpt-5.4"):
        command = bridge._adapter_command(adapter, "PROMPT")
    assert command == [
        "codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
        "--model", "gpt-5.4", "-",
    ]
    assert "--ask-for-approval" not in command


def test_cli_command_carries_supported_task_reasoning_effort_without_mutating_global_config():
    adapters = (
        ({"id": "codex", "executable": "codex", "available": True}, "high", ["-c", "model_reasoning_effort=high"]),
        ({"id": "claude", "executable": "claude", "available": True}, "max", ["--effort", "max"]),
        ({"id": "antigravity", "executable": "agy", "available": True}, "medium", ["--effort", "medium"]),
    )
    with patch("features.agent_mode.setup.configured_model", return_value="task-model"):
        for adapter, effort, expected in adapters:
            command = bridge._adapter_command(adapter, "PROMPT", reasoning_effort=effort)
            for item in expected:
                assert item in command


def test_cli_command_rejects_effort_unknown_to_selected_adapter():
    adapter = {"id": "antigravity", "executable": "agy", "available": True}
    with pytest.raises(ValueError, match="Unsupported reasoning effort"):
        bridge._adapter_command(adapter, "PROMPT", reasoning_effort="xhigh")


def test_codex_cli_command_keeps_model_specific_effort_levels():
    adapter = {"id": "codex", "executable": "codex", "available": True}

    for model, effort in [
        ("gpt-6-astra", "ultra"),
        ("gpt-5.6-sol", "ultra"),
        ("gpt-5.6-luna", "max"),
    ]:
        command = bridge._adapter_command(
            adapter,
            "PROMPT",
            model_override=model,
            reasoning_effort=effort,
        )
        assert ["-c", f"model_reasoning_effort={effort}"] == command[command.index("-c") : command.index("-c") + 2]

    with pytest.raises(ValueError, match="Unsupported reasoning effort"):
        bridge._adapter_command(
            adapter,
            "PROMPT",
            model_override="gpt-5.6-luna",
            reasoning_effort="ultra",
        )


def test_bridge_parses_fenced_json_object():
    payload = bridge._json_payload('```json\n{"verdict":"maintained"}\n```')
    assert payload["verdict"] == "maintained"


def test_configured_provider_does_not_fall_back_to_another_cli():
    adapters = {
        "codex": {"id": "codex", "label": "Codex CLI", "installed": True, "authenticated": False, "available": False},
        "claude": {"id": "claude", "label": "Claude Code CLI", "installed": True, "authenticated": True, "available": True},
        "antigravity": {"id": "antigravity", "label": "Antigravity CLI", "installed": False, "authenticated": False, "available": False},
    }
    bridge.invalidate_bridge_status()
    with (
        patch.dict(os.environ, {"AGENT_CLI_PROVIDER": "codex"}),
        patch.object(bridge, "_probe_adapter", side_effect=lambda adapter: adapters[adapter]),
    ):
        status = bridge.bridge_status(refresh=True)
    bridge.invalidate_bridge_status()
    assert status["available"] is False
    assert status["selectedAdapter"] == ""


def test_agent_preflight_reports_auth_and_workspace_checks():
    status = {
        "available": False,
        "selectedAdapter": "codex",
        "message": "로그인이 필요합니다.",
        "adapters": [{
            "id": "codex",
            "label": "Codex CLI",
            "installed": True,
            "authenticated": False,
            "available": False,
            "bridgeSupported": True,
            "executable": sys.executable,
            "version": "codex 1.0",
            "error": "로그인이 필요합니다.",
        }],
    }
    with patch.object(bridge, "bridge_status", return_value=status):
        preflight = bridge.agent_preflight("codex")
    checks = {item["id"]: item for item in preflight["checks"]}
    assert preflight["ok"] is False
    assert checks["workspace"]["ok"] is True
    assert checks["adapter_installed"]["ok"] is True
    assert checks["adapter_version"]["message"] == "버전: codex 1.0"
    assert checks["adapter_auth"]["ok"] is False
    assert "로그인" in checks["adapter_auth"]["message"]


def test_agent_preflight_reports_no_selected_adapter():
    status = {
        "available": False,
        "selectedAdapter": "",
        "message": "실행 가능한 Codex/Claude CLI가 없습니다.",
        "adapters": [],
    }
    with patch.object(bridge, "bridge_status", return_value=status):
        preflight = bridge.agent_preflight()
    assert preflight["ok"] is False
    assert preflight["checks"][-1]["id"] == "adapter_selected"
    assert "CLI" in preflight["checks"][-1]["message"]


def test_run_agent_task_captures_output_and_delegates_writeback():
    with TemporaryDirectory() as tmp:
        pack = schema.build_pack(
            task_type="briefing",
            artifact_type="briefing",
            artifact_id="2099-12-31",
            title="Test Briefing",
            prompt="prompt",
            context="context",
            output_contract={"format": "markdown"},
            write_back_contract={"method": "write_markdown"},
            save_target=str(Path(tmp) / "briefing.json"),
            draft_artifact={"date": "2099-12-31"},
        )
        pack_path = Path(tmp) / "pack.json"
        pack_path.write_text("{}", encoding="utf-8")
        adapter = {"id": "codex", "label": "Codex CLI", "executable": sys.executable, "available": True}
        command = [sys.executable, "-c", "print('## Test Briefing\\n\\nAgent output')"]
        with (
            patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset()),
            patch.object(bridge, "_select_adapter", return_value=adapter),
            patch.object(bridge, "_adapter_command", return_value=command),
            patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, pack_path)),
            patch.object(bridge.agent_service, "writeback_pack", return_value={"date": "2099-12-31", "title": "Test Briefing"}) as writeback,
            patch.object(bridge.schema, "update_pack_status"),
        ):
            result = bridge.run_agent_task("briefing", {}, job_id="test-job")
        assert result["generationMode"] == "llm_cli"
        assert result["date"] == "2099-12-31"
        assert "Agent output" in writeback.call_args.kwargs["markdown"]


def test_shared_job_uses_owned_pack_and_atomic_json_producer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Given: a real running SharedJob, an unrelated manual pack, and a fake CLI result.
    monkeypatch.setattr(jobs, "JOBS_PATH", tmp_path / "jobs.json")
    jobs._LIFECYCLES.clear()
    job = new_shared_job(
        kind=JobKind.AGENT_BRIDGE,
        task_type=TaskType.INVESTMENT_REVIEW,
        generation_mode=GenerationMode.LLM_CLI,
        adapter=Adapter.CODEX,
        requested_mode="cli",
        mode=JobMode.GENERATE,
        attempted_engine="cli",
        clock=jobs._clock,
    )
    jobs._store().add(job)
    jobs._store().transition(job.id, JobStatus.RUNNING)
    jobs._lifecycle().set_private(job.id, {"canary": "PRIVATE_CANARY"})
    manual = tmp_path / "agent-context" / "manual-sentinel.json"
    manual.parent.mkdir(parents=True)
    manual.write_bytes(b"MANUAL_SENTINEL")
    pack = schema.build_pack(
        task_type="investment_review",
        artifact_type="investment_review",
        artifact_id="2099-12-31",
        title="Investment Review",
        prompt="prompt",
        context="PRIVATE_CONTEXT_CANARY",
        output_contract={"format": "markdown"},
        write_back_contract={"method": "write_markdown"},
        save_target=str(tmp_path / "investment-review" / "2099-12-31.json"),
        draft_artifact={"date": "2099-12-31", "title": "Investment Review"},
    )

    def prepare_pack(_task_type: str, **kwargs):
        assert kwargs["owner_job_id"] == job.id
        owned = jobs.write_job_pack(job.id, f"review_{pack['packId']}", pack)
        return pack, owned

    adapter = {"id": "codex", "label": "Codex CLI", "executable": "codex", "available": True}
    with (
        patch.object(bridge, "_select_adapter", return_value=adapter),
        patch.object(bridge.agent_service, "prepare_pack", side_effect=prepare_pack),
        patch.object(bridge, "_invoke_agent_cli", return_value="# Review\n\nSafe result"),
        patch.object(bridge.agent_service, "writeback_pack", side_effect=AssertionError("direct writeback forbidden")),
    ):
        # When: the live bridge finishes the SharedJob.
        result = bridge.run_agent_task("investment_review", {}, job_id=job.id)

    # Then: one atomic producer commit is durable and all job-private state is gone.
    durable = jobs._store().get(job.id)
    report_path = tmp_path / "investment-review" / "2099-12-31.json"
    assert result["artifactId"] == "2099-12-31"
    assert durable is not None and durable.status is JobStatus.DONE
    assert durable.artifactRefs[0].type == "investment_review"
    assert report_path.is_file()
    assert '"jobCommit"' in report_path.read_text(encoding="utf-8")
    assert not (tmp_path / "job-context" / job.id).exists()
    assert not jobs._lifecycle().has_private(job.id)
    assert manual.read_bytes() == b"MANUAL_SENTINEL"


def test_cancel_agent_task_marks_shared_job_before_terminating_registered_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Given: a running SharedJob whose registered CLI process makes its worker
    # observe a non-zero exit immediately when terminate() is called.
    monkeypatch.setattr(jobs, "JOBS_PATH", tmp_path / "jobs.json")
    jobs._LIFECYCLES.clear()
    job = new_shared_job(
        kind=JobKind.AGENT_BRIDGE,
        task_type=TaskType.COMPANION,
        generation_mode=GenerationMode.LLM_CLI,
        adapter=Adapter.CODEX,
        requested_mode="cli",
        mode=JobMode.ANSWER,
        attempted_engine="cli",
        clock=jobs._clock,
    )
    jobs._store().add(job)
    lifecycle = jobs._lifecycle()
    lifecycle.set_private(job.id, {"canary": "PRIVATE_CANCEL_CANARY"})

    terminalized = threading.Event()
    communicating = threading.Event()
    release_process = threading.Event()
    worker_finished = threading.Event()
    real_terminalize = lifecycle.terminalize

    def terminalize(*args, **kwargs):
        try:
            return real_terminalize(*args, **kwargs)
        finally:
            terminalized.set()

    monkeypatch.setattr(lifecycle, "terminalize", terminalize)

    class ControlledProcess:
        returncode = None
        terminated = False
        terminate_calls = 0

        def communicate(self, _input=None, timeout=None):
            communicating.set()
            assert release_process.wait(timeout=2), "test process was not released"
            self.returncode = -15
            return "", "terminated by cancellation"

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.terminate_calls += 1
            release_process.set()
            # Make the ordering deterministic: termination does not return to
            # cancel_agent_task until the worker has terminalized the job.
            assert terminalized.wait(timeout=2), "worker did not terminalize"

    process = ControlledProcess()
    adapter = {"id": "codex", "executable": "codex", "available": True}

    def worker(*, progress):
        del progress
        try:
            return bridge._invoke_agent_cli(adapter, "PROMPT", timeout=30, job_id=job.id)
        finally:
            worker_finished.set()

    monkeypatch.setattr(bridge, "_adapter_command", lambda *_args, **_kwargs: ["codex", "exec", "-"])
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *_args, **_kwargs: process)
    thread = threading.Thread(target=jobs.run_job, args=(job.id, worker), daemon=True)
    thread.start()

    try:
        assert communicating.wait(timeout=2), "worker did not register its process"
        assert jobs._store().get(job.id).status is JobStatus.RUNNING

        # When: the public cancellation path is invoked.
        result = bridge.cancel_agent_task(job.id)

        # Then: cancellation wins the process-exit race and private state is cleaned.
        assert worker_finished.wait(timeout=2)
        thread.join(timeout=2)
        durable = jobs._store().get(job.id)
        assert result["cancelled"] is True
        assert durable is not None and durable.status is JobStatus.CANCELLED
        assert process.terminated is True
        assert process.terminate_calls == 1
        assert job.id not in bridge._RUNNING_PROCESSES
        assert not lifecycle.has_private(job.id)
        assert b"PRIVATE_CANCEL_CANARY" not in (tmp_path / "jobs-v2.json").read_bytes()

        repeated = bridge.cancel_agent_task(job.id)
        assert repeated["cancelled"] is False
        assert process.terminate_calls == 1
    finally:
        release_process.set()
        thread.join(timeout=2)
        with bridge._PROCESS_LOCK:
            bridge._RUNNING_PROCESSES.pop(job.id, None)
        jobs._LIFECYCLES.clear()


@pytest.mark.parametrize("status", ["committing", "cancelled"])
def test_cancel_agent_task_does_not_terminate_when_shared_job_rejects_cancel(status: str):
    process = Mock()
    process.poll.return_value = None
    with bridge._PROCESS_LOCK:
        bridge._RUNNING_PROCESSES["job-rejected"] = process
    try:
        with patch.object(
            bridge,
            "cancel_job",
            return_value={"cancelled": False, "job": {"status": status}},
        ):
            result = bridge.cancel_agent_task("job-rejected")
        assert result["cancelled"] is False
        process.poll.assert_not_called()
        process.terminate.assert_not_called()
    finally:
        with bridge._PROCESS_LOCK:
            bridge._RUNNING_PROCESSES.pop("job-rejected", None)


def test_cancel_agent_task_accepts_process_exit_between_poll_and_terminate():
    process = Mock()
    process.poll.return_value = None
    process.terminate.side_effect = ProcessLookupError
    with bridge._PROCESS_LOCK:
        bridge._RUNNING_PROCESSES["job-exited"] = process
    try:
        with patch.object(bridge, "cancel_job", return_value={"cancelled": True}) as cancel:
            result = bridge.cancel_agent_task("job-exited")
        assert result == {"cancelled": True}
        cancel.assert_called_once_with("job-exited")
        process.terminate.assert_called_once_with()
    finally:
        with bridge._PROCESS_LOCK:
            bridge._RUNNING_PROCESSES.pop("job-exited", None)


def test_market_state_snapshot_progress_does_not_conflict_with_message_key():
    with TemporaryDirectory() as tmp:
        pack = schema.build_pack(
            task_type="market_state_snapshot",
            artifact_type="market_state_snapshot",
            artifact_id="2099-12-31",
            title="Market State",
            prompt="prompt",
            context="context",
            output_contract={"format": "json"},
            write_back_contract={"method": "write_json"},
            save_target=str(Path(tmp) / "snapshot.json"),
        )
        pack_path = Path(tmp) / "pack.json"
        pack_path.write_text("{}", encoding="utf-8")
        adapter = {"id": "codex", "label": "Codex CLI", "executable": "codex", "available": True}
        progress_calls = []

        def progress(message, progress=None, **extra):
            progress_calls.append({"message": message, "progress": progress, **extra})

        with (
            patch.object(bridge, "_select_adapter", return_value=adapter),
            patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, pack_path)),
            patch.object(bridge, "_invoke_agent_cli", return_value='{"headline":"AI 반도체 장"}'),
            patch.object(bridge.agent_service, "writeback_pack", return_value={"snapshot": {"id": "snap_1", "headline": "AI 반도체 장"}}),
            patch.object(bridge.schema, "update_pack_status"),
        ):
            result = bridge.run_agent_task("market_state_snapshot", {}, progress=progress, job_id="snapshot-job")
        assert result["snapshotId"] == "snap_1"
        assert result["statusMessage"] == "AI Agent 시장 상태 스냅샷을 저장했습니다."
        assert progress_calls[-1]["message"] == "Agent 결과 저장을 완료했습니다."
        assert "message" not in {key for key in progress_calls[-1] if key != "message"}


def test_market_memory_update_task_runs_memory_then_snapshot():
    calls = []
    progress_calls = []

    def fake_run_agent_task(task_type, params, *, adapter="", progress=None, job_id=""):
        calls.append((task_type, params, adapter, job_id))
        if progress:
            progress(f"{task_type} 진행", 50, artifactType=task_type)
        if task_type == "market_memory_llm":
            return {"artifactType": "market_memory", "savedCount": 3, "date": params["date"]}
        if task_type == "market_state_snapshot":
            return {"artifactType": "market_state_snapshot", "snapshotId": "snap_1", "title": "최신 시장 상태", "date": params["date"]}
        raise AssertionError(task_type)

    def progress(message, progress=None, **extra):
        progress_calls.append({"message": message, "progress": progress, **extra})

    with patch.object(bridge, "run_agent_task", side_effect=fake_run_agent_task):
        result = bridge.run_market_memory_update_task(
            {"date": "2026-07-07"},
            adapter="codex",
            progress=progress,
            job_id="update-job",
        )

    assert [call[0] for call in calls] == ["market_memory_llm", "market_state_snapshot"]
    assert all(call[1] == {"date": "2026-07-07"} for call in calls)
    assert all(call[2] == "codex" for call in calls)
    assert all(call[3] == "update-job" for call in calls)
    assert result["artifactType"] == "market_memory_update"
    assert result["savedCount"] == 3
    assert result["snapshotId"] == "snap_1"
    assert result["title"] == "최신 시장 상태"
    assert result["memory"]["artifactType"] == "market_memory"
    assert result["snapshot"]["artifactType"] == "market_state_snapshot"
    assert progress_calls[0]["message"].startswith("1/2")
    assert progress_calls[-1]["message"].startswith("2/2")
    assert progress_calls[0]["progress"] < progress_calls[-1]["progress"]


def test_briefing_agent_prompt_embeds_full_output_contract():
    contract = briefing_output_contract(
        "both",
        expected_titles={
            "us": "US Market Briefing — 2026.08.03 마감",
            "kr": "Korea Market Briefing — 2026.08.04 장중",
        },
    )
    prompt = bridge._agent_prompt(Path("pack.json"), {"outputContract": contract})
    assert "0. 오늘의 미국장 성격" in prompt
    assert "6. 다음 한국장 체크포인트" in prompt
    assert "10000" in prompt
    assert "축약" in prompt
    assert "# US Market Briefing — 2026.08.03 마감" in prompt
    assert "# Korea Market Briefing — 2026.08.04 장중" in prompt
    assert "기업명" in prompt


def test_briefing_contract_rejects_missing_title_date_and_company_names():
    contract = briefing_output_contract("us")
    markdown = (
        "# US Market Briefing\n\n"
        "## 0. 오늘의 미국장 성격\n\n"
        "## 1. 미국장 시장 흐름\n\n"
        "## 2. 미국장을 움직인 핵심 변수\n\n"
        "## 3. 미국장을 주도한 기업 ① — [기업명]\n\n"
        "## 4. 미국장을 주도한 기업 ②\n\n"
        "## 5. 일반 투자자 관점\n\n"
        "## 6. 다음 미국장 체크포인트\n\n"
        "## 오늘의 결론\n\n"
        "## Source & Data Notes\n"
        + ("**한 줄 결론:** 요약\n" * 7)
        + ("· 요약 항목\n" * 18)
        + ("본문 " * 3000)
    )
    violations = briefing_contract_violations(markdown, contract)
    assert any("시장별 제목 날짜 누락" in item for item in violations)
    assert any("주도 기업명 누락" in item for item in violations)


def test_briefing_contract_rejects_preamble_between_title_and_section_zero():
    contract = briefing_output_contract("us")
    markdown = _valid_briefing_output().split("# Korea Market Briefing", 1)[0].strip()
    markdown = markdown.replace(
        "# US Market Briefing — 2099.12.31\n\n## 0. 오늘의 미국장 성격",
        "# US Market Briefing — 2099.12.31\n\n> 시장 범위: us\n\n## 0. 오늘의 미국장 성격",
    )
    violations = briefing_contract_violations(markdown, contract)
    assert any("제목 다음 프리앰블 금지" in item for item in violations)


def test_briefing_contract_rejects_title_that_uses_publication_date_instead_of_session_date():
    contract = briefing_output_contract(
        "us",
        expected_titles={"us": "US Market Briefing — 2026.08.03 마감"},
    )
    markdown = _valid_briefing_output().split("# Korea Market Briefing", 1)[0].strip()
    markdown = markdown.replace(
        "# US Market Briefing — 2099.12.31",
        "# US Market Briefing — 2026.08.04 마감",
    )

    violations = briefing_contract_violations(markdown, contract)

    assert any("US Market Briefing — 2026.08.03 마감" in item for item in violations)


def test_run_agent_task_does_not_retry_invalid_briefing_or_writeback():
    with TemporaryDirectory() as tmp:
        pack = {
            "taskType": "briefing",
            "artifactType": "briefing",
            "artifactId": "2099-12-31",
            "title": "Test Briefing",
            "outputContract": briefing_output_contract("both"),
            "draftArtifact": {"date": "2099-12-31"},
        }
        pack_path = Path(tmp) / "pack.json"
        pack_path.write_text("{}", encoding="utf-8")
        adapter = {"id": "codex", "label": "Codex CLI", "executable": "codex", "available": True}
        invalid = "# Daily Market Briefing\n\n## US Market Briefing\n짧은 요약"
        with (
            patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset()),
            patch.object(bridge, "_select_adapter", return_value=adapter),
            patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, pack_path)),
            patch.object(bridge, "_invoke_agent_cli", return_value=invalid) as invoke,
            patch.object(bridge.agent_service, "writeback_pack", return_value={"date": "2099-12-31", "title": "Test Briefing"}) as writeback,
            patch.object(bridge.schema, "update_pack_status"),
        ):
            with pytest.raises(RuntimeError, match="출력 계약을 충족하지 못했습니다"):
                bridge.run_agent_task("briefing", {}, job_id="retry-job")
        assert invoke.call_count == 1
        writeback.assert_not_called()


def test_run_agent_task_never_writes_briefing_after_invalid_output():
    with TemporaryDirectory() as tmp:
        pack = {
            "taskType": "briefing",
            "artifactType": "briefing",
            "artifactId": "2099-12-31",
            "title": "Test Briefing",
            "outputContract": briefing_output_contract("both"),
            "draftArtifact": {"date": "2099-12-31"},
        }
        pack_path = Path(tmp) / "pack.json"
        pack_path.write_text("{}", encoding="utf-8")
        adapter = {"id": "codex", "label": "Codex CLI", "executable": "codex", "available": True}
        invalid = "# Daily Market Briefing\n\n## US Market Briefing\n짧은 요약"
        with (
            patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset()),
            patch.object(bridge, "_select_adapter", return_value=adapter),
            patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, pack_path)),
            patch.object(bridge, "_invoke_agent_cli", side_effect=[invalid, invalid]) as invoke,
            patch.object(bridge.agent_service, "writeback_pack") as writeback,
            patch.object(bridge.schema, "update_pack_status"),
        ):
            with pytest.raises(RuntimeError, match="출력 계약을 충족하지 못했습니다"):
                bridge.run_agent_task("briefing", {}, job_id="retry-fail-job")
        assert invoke.call_count == 1
        writeback.assert_not_called()


def test_antigravity_invoke_does_not_send_prompt_to_stdin_on_non_windows():
    # macOS/Linux: 프롬프트는 --print 인자로 전달하므로 stdin으로 중복 전달하지 않는다.
    selected = {"id": "antigravity", "executable": "agy", "available": True}
    proc = Mock()
    proc.communicate.return_value = ("RESULT", "")
    proc.returncode = 0
    with patch.object(bridge.os, "name", "posix"), \
         patch.object(bridge, "_adapter_command", return_value=["agy", "--print"]), \
         patch("subprocess.Popen", return_value=proc):
        out = bridge._invoke_agent_cli(selected, "PROMPT", timeout=30)
    assert out == "RESULT"
    sent = proc.communicate.call_args
    assert (sent.args[0] if sent.args else sent.kwargs.get("input")) is None


def test_antigravity_invoke_fails_fast_once_file_reads_are_known_blocked():
    """이미 거부당한 것을 알고 있으면 팩을 만들고 수 분을 버리지 않는다(실측 8분 30초).

    예전에는 여기서 버전을 봤다. 버전 게이트는 지웠다 — 재본 결과만 믿는다.
    """
    selected = {"id": "antigravity", "executable": "agy", "available": True, "version": "1.1.12"}
    bridge.reset_agy_permission_state()
    try:
        with patch.object(bridge, "_AGY_FILE_READS_BLOCKED", True), patch("subprocess.Popen") as popen:
            with pytest.raises(RuntimeError, match="권한"):
                bridge._invoke_agent_cli(selected, "Read the UTF-8 Agent Context Pack at: C:/x.json", timeout=30)
        popen.assert_not_called()  # agy를 실행조차 하지 않는다
    finally:
        bridge.reset_agy_permission_state()


def test_codex_invoke_sends_prompt_to_stdin():
    selected = {"id": "codex", "executable": "codex", "available": True}
    proc = Mock()
    proc.communicate.return_value = ("RESULT", "")
    proc.returncode = 0
    with patch.object(bridge, "_adapter_command", return_value=["codex", "exec", "-"]), \
         patch("subprocess.Popen", return_value=proc):
        bridge._invoke_agent_cli(selected, "PROMPT", timeout=30)
    sent = proc.communicate.call_args
    assert (sent.args[0] if sent.args else sent.kwargs.get("input")) == "PROMPT"


if __name__ == "__main__":
    test_probe_requires_executable_to_run()
    test_antigravity_probe_available_on_non_windows()
    test_antigravity_probe_unavailable_on_windows()
    test_antigravity_command_uses_current_long_model_flag_and_print_prompt()
    test_antigravity_invoke_does_not_send_prompt_to_stdin_on_non_windows()
    test_antigravity_invoke_fails_fast_on_windows()
    test_codex_invoke_sends_prompt_to_stdin()
    test_bridge_parses_fenced_json_object()
    test_configured_provider_does_not_fall_back_to_another_cli()
    test_run_agent_task_captures_output_and_delegates_writeback()


def test_durable_briefing_contract_violation_falls_back_to_rules_instead_of_failing():
    """토큰을 쓴 실행을 계약 위반 하나로 버리지 않는다 — 규칙 대체로 커밋한다.

    비-durable 경로는 규칙 대체를 태울 커밋 경로가 없어 그대로 거절한다(위 두 테스트).
    """
    with TemporaryDirectory() as tmp:
        pack = {
            "taskType": "briefing",
            "artifactType": "briefing",
            "artifactId": "2099-12-31",
            "title": "Test Briefing",
            "outputContract": briefing_output_contract("both"),
            "draftArtifact": {"date": "2099-12-31"},
        }
        pack_path = Path(tmp) / "pack.json"
        pack_path.write_text("{}", encoding="utf-8")
        adapter = {"id": "codex", "label": "Codex CLI", "executable": "codex", "available": True}
        invalid = "# Daily Market Briefing\n\n## US Market Briefing\n짧은 요약"
        seen = {}

        def _commit(job_id, task_type, pack, *, markdown, payload, contract_failed=False):
            seen["contractFailed"] = contract_failed
            seen["markdown"] = markdown
            return {"artifactId": "2099-12-31"}

        with (
            patch.object(bridge, "_briefing_mcp_server_names", return_value=frozenset()),
            patch.object(bridge, "_select_adapter", return_value=adapter),
            patch.object(bridge.agent_service, "prepare_pack", return_value=(pack, pack_path)),
            patch.object(bridge, "_invoke_agent_cli", return_value=invalid) as invoke,
            patch.object(bridge.agent_service, "writeback_pack") as writeback,
            patch.object(bridge.schema, "update_pack_status"),
            patch.object(bridge.job_runtime, "is_durable_job", return_value=True),
            patch.object(bridge.job_runtime, "commit_json_output", side_effect=_commit),
        ):
            summary = bridge.run_agent_task("briefing", {}, job_id="durable-contract-job")
        assert seen["contractFailed"] is True
        assert invoke.call_count == 1
        writeback.assert_not_called()
        assert summary["artifactId"] == "2099-12-31"
