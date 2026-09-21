"""Bounded Agent adjudication for conflicting KR leader candidates."""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from features.daily_briefing.concentration.leader_selection import apply_agent_decision


def adjudicate_conflict(
    base_decision: dict,
    signatures: list[dict],
    *,
    invoke: Callable[[str], str],
) -> dict:
    candidate_ids = {str(row.get("candidateId") or "") for row in signatures}
    payload = {
        "task": "Choose whether the original KR briefing leader pair is causally distinct.",
        "allowedDecisions": ["allow_pair", "replace", "uncertain"],
        "candidateWhitelist": sorted(candidate_ids),
        "baseDecision": base_decision,
        "candidates": signatures[:5],
        "output": {"decision": "allow_pair|replace|uncertain", "replacementCandidateId": "whitelist id or empty"},
    }
    try:
        raw = invoke(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        parsed = json.loads(str(raw or ""))
        if not isinstance(parsed, dict):
            raise ValueError("agent_object_required")
        return apply_agent_decision(base_decision, parsed, candidate_ids)
    except TimeoutError:
        return {**base_decision, "decisionSource": "fallback", "agentStatus": "timeout"}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {**base_decision, "decisionSource": "fallback", "agentStatus": "invalid"}
    except (OSError, RuntimeError):
        return {**base_decision, "decisionSource": "fallback", "agentStatus": "unavailable"}


def configured_adjudication(base_decision: dict, signatures: list[dict], *, serialize: bool = True) -> dict:
    from features.llm_settings.client import (
        ai_agent_enabled,
        ai_agent_mode,
        request_cli_text,
        selected_cli_config,
    )

    # Unit/integration tests must never launch a real external CLI or paid API call.
    if os.environ.get("PYTEST_CURRENT_TEST") or not ai_agent_enabled():
        return {**base_decision, "decisionSource": "fallback", "agentStatus": "unavailable"}
    from features.agent_mode.bridge import run_agent_prompt

    def invoke(prompt: str) -> str:
        result = run_agent_prompt(
            prompt,
            timeout=max(30, int(os.environ.get("KR_CONCENTRATION_ADJUDICATION_TIMEOUT_SECONDS", "120"))),
            serialize=serialize,
        )
        return str(result.get("output") or "")
    return adjudicate_conflict(base_decision, signatures, invoke=invoke)


__all__ = ["adjudicate_conflict", "configured_adjudication"]
