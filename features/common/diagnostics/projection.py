"""Safe read projections; no authority writes or private-result access."""
from __future__ import annotations

from typing import Any

from .record import DiagnosticRecord
from .schema import DiagnosticValidationError, ISSUE_CODES, OBSERVED_STATUSES, valid_id
from .store import ReadResult

_REASONS = frozenset({"present", "disabled", "writer_conflict", "quota_exceeded", "read_failed", "corrupt", "unsupported_version", "missing_unknown", "legacy_no_detail", "expired"})


def _authority(record: DiagnosticRecord, authority_status: str | None, authority_available: bool) -> str:
    if record.context.authority_kind == "direct":
        return "not_applicable"
    if not authority_available or authority_status not in OBSERVED_STATUSES:
        return "unavailable"
    return "matched" if authority_status == record.observed_status else "changed"


def _next_action(record: DiagnosticRecord, authority_state: str, authority_status: str | None) -> str:
    if authority_state == "unavailable":
        return "inspect_result"
    if authority_status in {"queued", "running", "cancel_requested", "committing"}:
        return "wait"
    failure = record.terminal_failure or record.first_failure
    if failure is not None and failure.reason_code == "commit_unknown":
        return "inspect_result"
    # L1a has no verified retry authority/revision flow, so it never exposes
    # the stored candidate as an actionable explicit retry.
    return "contact_support" if failure is not None else "none"


def project_record(record: DiagnosticRecord, *, authority_status: str | None = None, authority_available: bool = False) -> dict[str, Any]:
    authority_state = _authority(record, authority_status, authority_available)
    payload = record.to_dict()
    action = _next_action(record, authority_state, authority_status)
    for key in ("firstFailure", "terminalFailure"):
        failure = payload.get(key)
        if isinstance(failure, dict):
            failure["nextActionCode"] = action
    errors = payload.get("errors")
    if isinstance(errors, list):
        for failure in errors:
            if isinstance(failure, dict):
                failure["nextActionCode"] = action
    quality = (
        "complete"
        if record.required_producer_coverage == "complete" and authority_state == "matched"
        else "partial"
    )
    return {"version": 1, "runId": record.run_id, "diagnosticQuality": quality, "availabilityReason": "present", "authorityState": authority_state, "authorityStatus": authority_status if authority_state in {"matched", "changed"} else None, "record": payload}


def _safe_warnings(raw: object) -> list[dict[str, str]]:
    if type(raw) is not list:
        return []
    safe: list[dict[str, str]] = []
    for item in raw[:100]:
        if type(item) is not dict or set(item) != {"code", "runId"}:
            continue
        code, run_id = item.get("code"), item.get("runId")
        if not isinstance(code, str) or code not in ISSUE_CODES:
            continue
        try:
            safe.append({"code": code, "runId": valid_id(run_id, "run")})
        except (DiagnosticValidationError, ValueError):
            continue
    return safe


def project_read(result: ReadResult, *, run_id: str | None = None, authority_status: str | None = None, authority_available: bool = False, warnings: list[dict[str, str]] | None = None) -> dict[str, Any]:
    if result.record is not None:
        envelope = project_record(result.record, authority_status=authority_status, authority_available=authority_available)
        envelope["warnings"] = _safe_warnings(warnings)
        return envelope
    reason = result.availability_reason if result.availability_reason in _REASONS else "read_failed"
    quality = "legacy_unavailable" if reason == "legacy_no_detail" else "unavailable"
    return {"version": 1, "runId": run_id, "diagnosticQuality": quality, "availabilityReason": reason, "authorityState": "unavailable", "authorityStatus": None, "record": None, "warnings": _safe_warnings(warnings)}
