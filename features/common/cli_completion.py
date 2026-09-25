"""Backward-compatible completion-only view of the shared E0 parser."""
from features.common.cli_provider_result import observe_execution


def observe_completion(adapter: str, stdout: str) -> tuple[str | None, dict]:
    result = observe_execution(adapter, stdout)
    return result.text, {"completionStatus": result.completion_status, "stopReason": result.stop_reason}
