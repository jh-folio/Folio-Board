from __future__ import annotations

import json

import pytest

from features.common.execution_result import ExecutionResult, UsageFacts, WebSearchFacts
from features.common.diagnostics.schema import SafeFrame, safe_failure


def test_private_text_and_response_id_never_enter_safe_projection_or_repr() -> None:
    result = ExecutionResult(
        text="private_prompt_canary",
        response_id="private_response_id",
        transport_status="succeeded",
        completion_status="unknown",
    )
    assert "private_prompt_canary" not in repr(result)
    assert "private_response_id" not in repr(result)
    assert "private_prompt_canary" not in json.dumps(result.safe_projection())
    assert "private_response_id" not in json.dumps(result.safe_projection())
    assert result.completion_status == "unknown"


def test_structured_execution_facts_are_closed_and_do_not_infer_completion() -> None:
    result = ExecutionResult(
        text="nonempty legacy output",
        transport_status="succeeded",
        completion_status="incomplete",
        usage=UsageFacts(input_tokens=1, source="provider"),
        web_search=WebSearchFacts(enabled=True, used="unknown", observation="partial"),
    )
    projection = result.safe_projection()
    assert projection["completionStatus"] == "incomplete"
    assert projection["webSearch"] == {"enabled": True, "used": "unknown", "observation": "partial"}
    with pytest.raises(ValueError):
        UsageFacts(input_tokens=True)
    with pytest.raises(ValueError):
        WebSearchFacts(enabled="true")
    with pytest.raises(ValueError):
        UsageFacts(input_tokens=1, source="unavailable")
    with pytest.raises(ValueError):
        WebSearchFacts(used="no", observation="partial")


def test_execution_failure_projection_drops_unverified_source_hints() -> None:
    failure = safe_failure(frames=(SafeFrame("features.private_canary", "hidden", 1),))
    projection = ExecutionResult(failure=failure).safe_projection()
    assert projection["failure"]["frames"] == []
    assert "private_canary" not in json.dumps(projection)
