"""Private, additive execution facts for future provider adapters.

`WebSearchFacts` is wired: `features/agent_mode/bridge.py` constructs it from
the CLI adapter's own structured output for web-search lookup calls (claude
`stream-json`, codex `--json`; 2026-09-12) and threads it through
`run_agent_prompt()` -> `features/common/engine_lookup.py` ->
`features/daily_briefing/web_lookup.py`. `ExecutionResult` and `UsageFacts`
still have no persistence adapter. Existing tuple/string provider APIs keep
their return values and exception behavior; callers opt in only when a trusted
adapter can supply structured facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from features.common.diagnostics.schema import Failure, failure_fingerprint

TransportStatus = Literal["succeeded", "failed", "cancelled", "unknown"]
CompletionStatus = Literal["completed", "incomplete", "failed", "unknown"]
StopReason = Literal["end", "limit", "tool_error", "cancelled", "other", "unknown"]
WebSearchUsed = Literal["yes", "no", "unknown"]
Observation = Literal["complete", "partial", "unavailable"]


def _optional_count(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 1_000_000_000_000:
        raise ValueError(f"invalid_{field_name}")
    return value


@dataclass(frozen=True, slots=True)
class UsageFacts:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    source: Literal["provider", "unavailable"] = "unavailable"

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cached_tokens"):
            _optional_count(getattr(self, name), name)
        if self.source not in {"provider", "unavailable"}:
            raise ValueError("invalid_usage_source")
        if self.source == "unavailable" and any(
            getattr(self, name) is not None
            for name in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "cached_tokens")
        ):
            raise ValueError("unavailable_usage_values")

    def safe_projection(self) -> dict[str, int | str | None]:
        return {
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "totalTokens": self.total_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "cachedTokens": self.cached_tokens,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class WebSearchFacts:
    enabled: bool | None = None
    used: WebSearchUsed = "unknown"
    observation: Observation = "unavailable"

    def __post_init__(self) -> None:
        if self.enabled is not None and type(self.enabled) is not bool:
            raise ValueError("invalid_web_search_enabled")
        if self.used not in {"yes", "no", "unknown"} or self.observation not in {"complete", "partial", "unavailable"}:
            raise ValueError("invalid_web_search")
        if self.used == "yes" and self.observation == "unavailable":
            raise ValueError("unobserved_web_search_yes")
        if self.used == "no" and self.observation != "complete":
            raise ValueError("unobserved_web_search_no")

    def safe_projection(self) -> dict[str, bool | str | None]:
        return {"enabled": self.enabled, "used": self.used, "observation": self.observation}


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Memory-only result; private text and response IDs never serialize/repr."""

    text: str | None = field(default=None, repr=False)
    response_id: str | None = field(default=None, repr=False)
    transport_status: TransportStatus = "unknown"
    completion_status: CompletionStatus = "unknown"
    stop_reason: StopReason = "unknown"
    usage: UsageFacts = field(default_factory=UsageFacts)
    web_search: WebSearchFacts = field(default_factory=WebSearchFacts)
    queued_ms: int | None = None
    execution_ms: int | None = None
    failure: Failure | None = None

    def __post_init__(self) -> None:
        if self.text is not None and not isinstance(self.text, str):
            raise ValueError("invalid_execution_text")
        if self.response_id is not None and not isinstance(self.response_id, str):
            raise ValueError("invalid_response_id")
        if self.transport_status not in {"succeeded", "failed", "cancelled", "unknown"}:
            raise ValueError("invalid_transport_status")
        if self.completion_status not in {"completed", "incomplete", "failed", "unknown"}:
            raise ValueError("invalid_completion_status")
        if self.stop_reason not in {"end", "limit", "tool_error", "cancelled", "other", "unknown"}:
            raise ValueError("invalid_stop_reason")
        _optional_count(self.queued_ms, "queued_ms")
        _optional_count(self.execution_ms, "execution_ms")
        if not isinstance(self.usage, UsageFacts) or not isinstance(self.web_search, WebSearchFacts):
            raise ValueError("invalid_execution_facts")
        if self.failure is not None and not isinstance(self.failure, Failure):
            raise ValueError("invalid_execution_failure")

    def safe_projection(self) -> dict[str, object]:
        """Return only approved facts; intentionally omit text and response ID."""
        return {
            "transportStatus": self.transport_status,
            "completionStatus": self.completion_status,
            "stopReason": self.stop_reason,
            "usage": self.usage.safe_projection(),
            "webSearch": self.web_search.safe_projection(),
            "queuedMs": self.queued_ms,
            "executionMs": self.execution_ms,
            "failure": _project_failure(self.failure),
        }


def _project_failure(failure: Failure | None) -> dict[str, object] | None:
    """Execution results lack a shipped source registry, so never expose frames."""
    if failure is None:
        return None
    safe = replace(
        failure,
        frames=(),
        fingerprint=failure_fingerprint(
            stage_code=failure.stage_code,
            reason_code=failure.reason_code,
            exception_code=failure.exception_code,
            frames=(),
        ),
    )
    return safe.to_dict()
