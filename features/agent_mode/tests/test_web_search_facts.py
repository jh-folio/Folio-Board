"""bridge.py가 웹 검색 찾기 콜에서 실제로 관측한 사실(WebSearchFacts)을 돌려주는지 검사한다.

`_used_web_search()`(→ `run_agent_prompt()`의 `webSearch` 키)는 요청했고 그 어댑터가
정적으로 지원하는지일 뿐 관측이 아니다(plan/BRIEFING_QUALITY_REPAIR_PLAN.md Q4 잔여
세부). 이 파일은 어댑터 자신의 구조화 출력(claude stream-json / codex --json)에서
실제 도구 사용 여부를 읽어내는 새 경로 — `_extract_web_search_observation()`과
`_invoke_agent_cli(..., facts_sink=...)` — 를 검사한다.

이벤트 모양은 2026-09-12 실제 CLI 호출로 확인했다(claude-sonnet-5, codex-cli
0.153.4, 각 1회, WebSearch를 강제하는 프롬프트). 아래 fixture는 그 실측 구조를
그대로 옮긴 것이다 — 지어낸 스키마가 아니다.
"""
from __future__ import annotations

import json
from unittest.mock import Mock, patch

from features.agent_mode import bridge
from features.common.execution_result import WebSearchFacts


def _claude_stream_json(*, used: bool, text: str = "final answer") -> str:
    lines = [{"type": "system", "subtype": "init"}]
    if used:
        lines.append({
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "WebSearch", "input": {"query": "x"}}]},
        })
    lines.append({"type": "result", "subtype": "success", "result": text, "is_error": False})
    return "\n".join(json.dumps(line) for line in lines)


def _codex_jsonl(*, used: bool, text: str = "final answer") -> str:
    lines = [
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "searching..."}},
    ]
    if used:
        lines.append({
            "type": "item.completed",
            "item": {"id": "item_1", "type": "web_search", "query": "x", "action": {"type": "search", "query": "x"}},
        })
    lines.append({"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": text}})
    lines.append({"type": "turn.completed", "usage": {}})
    return "\n".join(json.dumps(line) for line in lines)


class TestAdapterCommandObservabilityFlags:
    def test_claude_lookup_command_switches_to_stream_json(self):
        command = bridge._adapter_command({"id": "claude", "executable": "claude"}, "p", web_search=True)
        assert command[command.index("--output-format") + 1] == "stream-json"
        assert "--verbose" in command

    def test_claude_writer_command_stays_plain_text(self):
        command = bridge._adapter_command({"id": "claude", "executable": "claude"}, "p", web_search=False)
        assert command[command.index("--output-format") + 1] == "text"
        assert "--verbose" not in command

    def test_codex_lookup_command_adds_the_json_event_stream(self):
        command = bridge._adapter_command({"id": "codex", "executable": "codex"}, "p", web_search=True)
        assert "--json" in command
        # The stdin marker must stay last, or codex stops reading the prompt from stdin.
        assert command[-1] == "-"

    def test_codex_writer_command_has_no_json_flag(self):
        command = bridge._adapter_command({"id": "codex", "executable": "codex"}, "p", web_search=False)
        assert "--json" not in command


class TestExtractWebSearchObservation:
    def test_claude_tool_use_block_means_yes(self):
        raw = _claude_stream_json(used=True, text="answer A")
        text, facts = bridge._extract_web_search_observation("claude", raw)
        assert text == "answer A"
        assert facts == WebSearchFacts(enabled=True, used="yes", observation="complete")

    def test_claude_without_a_tool_use_block_means_no_not_unknown(self):
        """관측은 됐다 — 그냥 안 쓴 것이다. '안 씀'과 '못 봄'은 다른 사실이다."""
        raw = _claude_stream_json(used=False, text="answer B")
        text, facts = bridge._extract_web_search_observation("claude", raw)
        assert text == "answer B"
        assert facts == WebSearchFacts(enabled=True, used="no", observation="complete")

    def test_codex_web_search_item_means_yes(self):
        raw = _codex_jsonl(used=True, text="answer C")
        text, facts = bridge._extract_web_search_observation("codex", raw)
        assert text == "answer C"
        assert facts == WebSearchFacts(enabled=True, used="yes", observation="complete")

    def test_codex_takes_the_last_agent_message_not_an_earlier_one(self):
        """중간 '검색 중...' 메시지가 아니라 마지막 답만 본문으로 쓴다."""
        raw = _codex_jsonl(used=True, text="final")
        text, _facts = bridge._extract_web_search_observation("codex", raw)
        assert text == "final"

    def test_codex_without_a_web_search_item_means_no(self):
        raw = _codex_jsonl(used=False, text="answer D")
        text, facts = bridge._extract_web_search_observation("codex", raw)
        assert text == "answer D"
        assert facts == WebSearchFacts(enabled=True, used="no", observation="complete")

    def test_unparseable_output_stays_unknown_and_lets_the_caller_fall_back(self):
        text, facts = bridge._extract_web_search_observation("claude", "not jsonl output")
        assert text is None
        assert facts == WebSearchFacts()

    def test_unsupported_adapter_stays_unknown(self):
        text, facts = bridge._extract_web_search_observation("antigravity", _claude_stream_json(used=True))
        assert text is None
        assert facts == WebSearchFacts()


class TestInvokeAgentCliFactsSink:
    """`facts_sink`는 순수 additive 통로다 — 넘기지 않는 기존 호출자는 그대로 동작한다."""

    def test_lookup_call_populates_facts_sink_from_real_shaped_stdout(self):
        proc = Mock()
        proc.communicate.return_value = (_claude_stream_json(used=True, text="answer"), "")
        proc.returncode = 0
        selected = {"id": "claude", "executable": "claude"}
        sink: dict = {}
        with (
            patch.object(bridge, "_adapter_command", return_value=["claude", "--print"]),
            patch("subprocess.Popen", return_value=proc),
        ):
            output = bridge._invoke_agent_cli(selected, "PROMPT", 30, web_search=True, facts_sink=sink)
        assert output == "answer"
        assert sink["webSearchFacts"] == WebSearchFacts(enabled=True, used="yes", observation="complete")

    def test_omitting_facts_sink_behaves_exactly_as_before(self):
        proc = Mock()
        proc.communicate.return_value = ("plain text result", "")
        proc.returncode = 0
        selected = {"id": "codex", "executable": "codex"}
        with (
            patch.object(bridge, "_adapter_command", return_value=["codex", "exec", "-"]),
            patch("subprocess.Popen", return_value=proc),
        ):
            output = bridge._invoke_agent_cli(selected, "PROMPT", 30)
        assert output == "plain text result"

    def test_non_web_search_call_fills_facts_sink_with_the_default(self):
        """검색을 안 켰으면 관측할 것도 없다 — 기본값(unknown/unavailable)을 그대로 채운다."""
        proc = Mock()
        proc.communicate.return_value = ("plain text result", "")
        proc.returncode = 0
        selected = {"id": "codex", "executable": "codex"}
        sink: dict = {}
        with (
            patch.object(bridge, "_adapter_command", return_value=["codex", "exec", "-"]),
            patch("subprocess.Popen", return_value=proc),
        ):
            output = bridge._invoke_agent_cli(selected, "PROMPT", 30, web_search=False, facts_sink=sink)
        assert output == "plain text result"
        assert sink["webSearchFacts"] == WebSearchFacts()

    def test_antigravity_never_switches_format_even_if_web_search_is_requested(self):
        """antigravity는 검색을 지원하지 않는다 — 요청해도 관측 시도 자체를 하지 않는다."""
        proc = Mock()
        proc.communicate.return_value = ("PONG", "")
        proc.returncode = 0
        selected = {"id": "antigravity", "executable": "agy", "version": "1.1.12"}
        sink: dict = {}
        with (
            patch.object(bridge, "_adapter_command", return_value=["agy", "--print"]) as command,
            patch("subprocess.Popen", return_value=proc),
        ):
            output = bridge._invoke_agent_cli(selected, "PROMPT", 30, web_search=True, facts_sink=sink)
        assert output == "PONG"
        assert command.call_args.kwargs["web_search"] is False
        assert sink["webSearchFacts"] == WebSearchFacts()


class TestRunAgentPromptReturnsWebSearchFacts:
    _ADAPTER = {"id": "claude", "label": "Claude Code CLI", "executable": "claude", "available": True}

    def test_serialize_false_branch_carries_the_observed_facts(self):
        def fake_invoke(selected, prompt, timeout, job_id="", model_override="", *, web_search=False,
                         reasoning_effort="", facts_sink=None, **_kwargs):
            if facts_sink is not None:
                facts_sink["webSearchFacts"] = WebSearchFacts(enabled=True, used="yes", observation="complete")
            return "looked-up text"

        with (
            patch.object(bridge, "_select_adapter", return_value=self._ADAPTER),
            patch.object(bridge, "_invoke_agent_cli", side_effect=fake_invoke),
        ):
            result = bridge.run_agent_prompt("q", serialize=False, web_search=True)

        assert result["output"] == "looked-up text"
        assert result["webSearchFacts"] == {"enabled": True, "used": "yes", "observation": "complete"}

    def test_serialize_true_branch_carries_the_observed_facts(self):
        def fake_invoke(selected, prompt, timeout, job_id="", model_override="", *, web_search=False,
                         reasoning_effort="", facts_sink=None, **_kwargs):
            if facts_sink is not None:
                facts_sink["webSearchFacts"] = WebSearchFacts(enabled=True, used="no", observation="complete")
            return "looked-up text"

        with (
            patch.object(bridge, "_select_adapter", return_value=self._ADAPTER),
            patch.object(bridge, "_invoke_agent_cli", side_effect=fake_invoke),
        ):
            result = bridge.run_agent_prompt("q", serialize=True, web_search=True)

        assert result["webSearchFacts"] == {"enabled": True, "used": "no", "observation": "complete"}

    def test_existing_callers_that_never_request_web_search_get_the_unknown_default(self):
        with (
            patch.object(bridge, "_select_adapter", return_value=self._ADAPTER),
            patch.object(bridge, "_invoke_agent_cli", return_value="plain output"),
        ):
            result = bridge.run_agent_prompt("q", serialize=False)

        assert result["webSearchFacts"] == {"enabled": None, "used": "unknown", "observation": "unavailable"}
        assert result["output"] == "plain output"
        assert result["webSearch"] is False
