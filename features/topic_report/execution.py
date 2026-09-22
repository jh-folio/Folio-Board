"""Deep Research consumers of E0; private payloads never enter report JSON."""
from concurrent.futures import CancelledError

from features.common.execution_result import ExecutionResult
from features.common.jobs import get_job


class IncompleteExecutionError(RuntimeError):
    pass


def ensure_active(job_id: str) -> None:
    if job_id and (get_job(job_id) or {}).get("status") in {"cancelled", "cancel_requested"}:
        raise CancelledError("cancelled")


def propagate_interruption(error: Exception) -> None:
    if isinstance(error, (CancelledError, TimeoutError)):
        raise error
    if isinstance(error, RuntimeError) and str(error) == "deadline_expired":
        raise TimeoutError("deadline_expired") from error
    if isinstance(error, RuntimeError) and str(error) == "cancelled":
        raise CancelledError("cancelled") from error


def incomplete(result: ExecutionResult | None) -> bool:
    return result is not None and (result.completion_status in {"incomplete", "failed"}
                                  or result.transport_status in {"failed", "cancelled"})


def require_complete(sink: dict) -> None:
    result = sink.get("result")
    if result is not None and result.transport_status == "cancelled":
        raise CancelledError("cancelled")
    if incomplete(sink.get("result")):
        raise IncompleteExecutionError("deep_cli_incomplete")


def report_incomplete(report: dict) -> bool:
    facts = report.get("executionFacts") or {}
    return facts.get("completionStatus") in {"incomplete", "failed"} or facts.get("transportStatus") in {"failed", "cancelled"}
