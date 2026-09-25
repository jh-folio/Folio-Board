from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from features.common.cli_provider_result import observe_execution
from features.common.execution_result import ExecutionResult
from features.common.provider_result import Citation, ContinuationLease, ProviderPayload
from features.agent_mode.bridge import _invoke_agent_cli as invoke_cli


def stream(*events):
    return "\n".join(json.dumps(e) for e in events)


def assistant(text="Claim.", **kwargs):
    return {"type": "assistant", "session_id": "PRIVATE_SESSION", "message": {
        "id": "PRIVATE_RESPONSE", "model": "observed-model", "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text, "citations": [{
            "type": "char_location", "document_index": 0, "document_title": "PRIVATE_TITLE",
            "cited_text": "PRIVATE_SOURCE", "start_char_index": 200, "end_char_index": 220,
        }]}], **kwargs,
    }}


def test_native_citation_source_offsets_differ_from_response_offsets_and_stay_private():
    result = observe_execution("claude", stream(assistant(), {
        "type": "result", "subtype": "success", "result": "Claim.",
        "usage": {"input_tokens": 10, "output_tokens": 2, "cache_read_input_tokens": 3},
    }), returncode=0)
    citation = result.provider.citations[0]
    assert (citation.start, citation.end) == (0, 6)
    assert (citation.source_start, citation.source_end, citation.source_id) == (200, 220, "document:0")
    assert result.provider.model == "observed-model"
    assert result.usage.input_tokens == 10 and result.usage.total_tokens is None
    assert result.usage.cached_tokens == 3
    assert result.completion_status == "completed"
    for text in (repr(result), repr(result.provider), json.dumps(result.safe_projection())):
        assert "PRIVATE" not in text and "Claim." not in text and "observed-model" not in text
    assert set(result.safe_projection()) == {
        "transportStatus", "completionStatus", "stopReason", "usage", "webSearch", "queuedMs", "executionMs", "failure",
    }


@pytest.mark.parametrize("after,expected", [("# Header\nClaim.", 9), ("Changed.", None), ("Claim. Claim.", None)])
def test_edit_remapping_never_guesses(after, expected):
    result = observe_execution("claude", stream(assistant()))
    edited = result.with_text(after)
    assert edited.provider.citations[0].start == expected
    assert edited.provider.citations[0].source_start == 200
    assert result.text == "Claim."


def test_unchanged_duplicate_claim_preserves_exact_position_but_edit_invalidates():
    citation = Citation(0, 0, 2)
    assert citation.remap("xx xx", "xx xx").start == 0
    assert citation.remap("xx xx", "prefix xx xx").start is None
    assert citation.remap("aa", "aaa").start is None


def test_final_result_rewrite_drops_stale_citation_position():
    result = observe_execution("claude", stream(assistant(), {"type": "result", "result": "Rewritten."}))
    assert result.provider.citations[0].start is None


def test_claude_complete_blocks_with_same_message_id_accumulate_and_ignore_subagents():
    child = assistant("Child", id="child-message")
    child["parent_tool_use_id"] = "parent"
    result = observe_execution("claude", stream(assistant("First"), child, assistant("Second"),
        {"type": "result", "subtype": "success", "result": "First\nSecond"}))
    assert len(result.provider.blocks) == 2
    assert [(c.start, c.end) for c in result.provider.citations] == [(0, 5), (6, 12)]
    assert result.response_id == "PRIVATE_RESPONSE"


def test_missing_model_usage_and_citations_are_not_invented():
    result = observe_execution("codex", stream(
        {"type": "thread.started", "thread_id": "PRIVATE_SESSION"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "[link](https://example.org)"}},
        {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 4}},
    ), returncode=0)
    assert result.provider.model is None and result.provider.citations == ()
    assert result.provider.citation_capability == "unknown"
    assert result.usage.input_tokens == 0 and result.usage.total_tokens is None
    assert result.provider.continuation_capability == "unsupported"
    assert result.provider.continuation is None


@pytest.mark.parametrize("stop,status,reason,state", [
    ("pause_turn", "incomplete", "other", "paused"),
    ("tool_use", "incomplete", "other", "tool_pending"),
    ("max_tokens", "incomplete", "limit", "unknown"),
    ("tool_error", "failed", "tool_error", "unknown"),
])
def test_terminal_states(stop, status, reason, state):
    result = observe_execution("claude", stream({"type": "result", "result": "partial", "stop_reason": stop}))
    assert (result.completion_status, result.stop_reason, result.provider.continuation_state) == (status, reason, state)
    assert result.provider.raw_stop_reason == stop


def test_intermediate_tool_use_followed_by_end_is_not_partial():
    result = observe_execution("claude", stream(
        assistant("Thinking", stop_reason="tool_use"), assistant("Done", id="next-message"),
        {"type": "result", "subtype": "success", "result": "Done"},
    ))
    assert result.completion_status == "completed" and result.provider.continuation_state == "none"


def test_new_complete_message_supersedes_previous_limit():
    result = observe_execution("claude", stream(
        assistant("Partial", stop_reason="max_tokens"), assistant("Replacement", id="next-message"),
        {"type": "result", "subtype": "success", "result": "Replacement"},
    ))
    assert result.completion_status == "completed" and result.text == "Replacement"


@pytest.mark.parametrize("adapter", ["claude", "codex", "antigravity", "unsupported"])
def test_malformed_events_and_unobserved_counts_are_safe(adapter):
    result = observe_execution(adapter, 'bad json\n' + stream([], {"type": "assistant", "message": []},
        {"type": "item.completed", "item": "wrong"}, {"type": "result", "usage": {"input_tokens": True, "output_tokens": -1}}))
    assert result.completion_status == "unknown" and result.usage.source == "unavailable"


def test_continuation_owner_single_use_and_concurrent_claims():
    lease = ContinuationLease("PRIVATE_TOKEN", owner="job:revision", ttl_seconds=10)
    with pytest.raises(ValueError):
        lease.claim(owner="different")
    def claim():
        try:
            return lease.claim(owner="job:revision")
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: claim(), range(2))).count("PRIVATE_TOKEN") == 1
    assert lease.state == "consumed" and "PRIVATE_TOKEN" not in repr(lease)


def test_continuation_expiry_cancel_and_capability_guard():
    now = [10]
    lease = ContinuationLease("PRIVATE_TOKEN", owner="job", ttl_seconds=5, clock=lambda: now[0])
    now[0] = 15
    assert lease.state == "expired"
    with pytest.raises(ValueError):
        lease.claim(owner="job")
    other = ContinuationLease("PRIVATE_TOKEN", owner="job", ttl_seconds=10)
    other.cancel()
    with pytest.raises(ValueError):
        other.claim(owner="job")
    assert other.state == "cancelled"
    with pytest.raises(ValueError):
        ProviderPayload(continuation=other)


def test_cli_bridge_private_sink_and_legacy_string(monkeypatch):
    from features.agent_mode import bridge
    stdout = stream(assistant("```markdown\nClaim.\n```"), {"type": "result", "subtype": "success", "result": "```markdown\nClaim.\n```"})
    monkeypatch.setattr(bridge, "_adapter_command", lambda *a, **k: ["claude", "--output-format", "text"])
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: SimpleNamespace(returncode=0, communicate=lambda *a, **k: (stdout, "")))
    sink, facts = {}, {}
    output = invoke_cli({"id": "claude"}, "prompt", 30, result_sink=sink, facts_sink=facts)
    assert output == "Claim." and isinstance(sink["result"], ExecutionResult)
    assert sink["result"].text == output
    assert "PRIVATE" not in json.dumps(facts["executionFacts"])


@pytest.mark.parametrize("serialize", [True, False])
def test_prompt_never_serializes_private_sink(monkeypatch, serialize):
    from features.agent_mode import bridge
    monkeypatch.setattr(bridge, "_select_adapter", lambda *a: {"id": "claude"})
    monkeypatch.setattr(bridge, "current_task_policy", lambda: None)
    monkeypatch.setattr(bridge, "current_briefing_budget", lambda: None)
    def invoke(*a, **kwargs):
        kwargs["result_sink"]["result"] = observe_execution("claude", stream(assistant()))
        return "Claim."
    monkeypatch.setattr(bridge, "_invoke_agent_cli", invoke)
    sink = {}
    response = bridge.run_agent_prompt("prompt", result_sink=sink, serialize=serialize)
    assert response["output"] == "Claim." and sink["result"].provider.model == "observed-model"
    assert "PRIVATE" not in json.dumps(response)


def test_cancelled_prompt_overrides_stale_result_without_private_payload(monkeypatch):
    from features.agent_mode import bridge
    monkeypatch.setattr(bridge, "get_job", lambda _: {"status": "cancelled"})
    sink = {"result": observe_execution("claude", stream(assistant()))}
    with pytest.raises(RuntimeError, match="cancelled"):
        bridge.run_agent_prompt("prompt", job_id="cancelled", result_sink=sink)
    assert sink["result"].stop_reason == "cancelled" and sink["result"].provider is None


def test_cli_timeout_keeps_exception_contract_and_clears_private_state(monkeypatch):
    from features.agent_mode import bridge
    import subprocess
    calls = []
    def communicate(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("cli", 30)
        return "", ""
    monkeypatch.setattr(bridge, "_adapter_command", lambda *a, **k: ["claude", "--output-format", "text"])
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: SimpleNamespace(
        communicate=communicate, kill=lambda: None))
    sink = {}
    with pytest.raises(TimeoutError):
        invoke_cli({"id": "claude"}, "prompt", 30, result_sink=sink)
    assert sink["result"].provider.raw_stop_reason == "deadline_expired"
    assert sink["result"].completion_status == "incomplete"


def test_client_tuple_compatibility_and_private_result_transfer(monkeypatch):
    from features.agent_mode import bridge
    from features.llm_settings import client
    monkeypatch.setattr(client, "ai_agent_enabled", lambda: True)
    def prompt(*a, **k):
        k["result_sink"]["result"] = observe_execution("claude", stream(assistant()))
        return {"output": "Claim.", "executionFacts": {"completionStatus": "unknown"}}
    monkeypatch.setattr(bridge, "run_agent_prompt", prompt)
    sink, facts = {}, {}
    response = client.request_cli_text({"enabled": True}, "prompt", "context", result_sink=sink, facts_sink=facts, include_usage=True)
    assert len(response) == 3 and response[0] == "Claim." and response[1] == ""
    assert sink["result"].provider.model == "observed-model"
    assert "PRIVATE" not in json.dumps(response) and "PRIVATE" not in json.dumps(facts)
