"""Privacy-safe, local-only diagnostics export.

The exporter deliberately does not serialize ``DiagnosticRecord`` directly.
Records are read through :class:`DiagnosticsStore` (which applies the normal
128 KiB bounded reader and source validation) and then rebuilt field by field.
No job/config/result files are opened and no export is written to disk.
"""
from __future__ import annotations

from dataclasses import dataclass
import secrets
import threading
import time
from typing import Any, Callable, Mapping

from features.common.canonical_json import canonical_json_bytes

from .projection import project_record
from .schema import DiagnosticValidationError, valid_id
from .store import DiagnosticsStore, ReadResult, _is_reparse


EXPORT_VERSION = 1
MAX_EXPORT_RUNS = 20
MAX_EXPORT_RUN_BYTES = 128 * 1024
MAX_EXPORT_BYTES = 1024 * 1024
MAX_SCAN_ENTRIES = 5000
SCAN_DEADLINE_SECONDS = 0.250
MAX_PREVIEWS = 32
MAX_EXPORT_ISSUES = 64
_SAFE_ISSUE_CODES = frozenset({
    "missing_unknown", "read_failed", "corrupt", "unsupported_version",
    "scan_limit", "quota_exceeded", "legacy_no_detail", "byte_limit", "run_limit",
})

_OPTION_KEYS = frozenset({"includeParent", "includeChildren"})
_DOWNLOAD_KEYS = frozenset({"previewToken", "includeParent", "includeChildren"})
_TOKEN_PREFIX = "dxp1_"


class ExportError(ValueError):
    """Stable export error code; the caller must not expose exception text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ExportBundle:
    selected_run_id: str
    include_parent: bool
    include_children: bool
    payload: dict[str, Any]
    payload_bytes: bytes
    summary: str

    def preview(self, token: str) -> dict[str, Any]:
        return {
            "version": EXPORT_VERSION,
            "previewToken": token,
            "selectedRunId": self.selected_run_id,
            "includeParent": self.include_parent,
            "includeChildren": self.include_children,
            "runCount": len(self.payload["runs"]),
            "byteCount": len(self.payload_bytes),
            "summary": self.summary,
            "json": self.payload,
        }


@dataclass(frozen=True, slots=True)
class _Preview:
    token: str
    selected_run_id: str
    include_parent: bool
    include_children: bool
    bundle: ExportBundle


def parse_options(body: object, *, download: bool = False) -> tuple[bool, bool, str | None]:
    """Parse the tiny explicit export request without accepting free metadata."""
    if type(body) is not dict:
        raise ExportError("export_options_required")
    allowed = _DOWNLOAD_KEYS if download else _OPTION_KEYS
    unknown = set(body) - allowed
    if unknown:
        raise ExportError("unknown_export_option")
    token = body.get("previewToken")
    if download and token is None:
        raise ExportError("preview_token_required")
    if token is not None:
        if not download or not isinstance(token, str) or not token.startswith(_TOKEN_PREFIX) or len(token) > 80:
            raise ExportError("invalid_preview_token")
    parent = body.get("includeParent", False)
    children = body.get("includeChildren", False)
    if type(parent) is not bool or type(children) is not bool:
        raise ExportError("invalid_export_option")
    return parent, children, token


def _safe_failure(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "errorId", "stageId", "stageCode", "errorCode", "reasonCode",
        "exceptionCode", "frames", "confirmation", "nextActionCode", "fingerprint",
    )
    result: dict[str, Any] = {}
    for key in keys:
        if key == "frames":
            frames = value.get(key)
            if isinstance(frames, list):
                result[key] = [
                    {k: item.get(k) for k in ("moduleCode", "functionCode", "line")}
                    for item in frames if isinstance(item, dict)
                ]
            else:
                result[key] = []
        else:
            result[key] = value.get(key)
    return result


def _safe_event(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("seq", "eventId", "stageId", "stageCode", "eventCode", "producerEpoch", "at", "durationMs", "errorId", "count")
    return {key: value.get(key) for key in keys}


def safe_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the persisted record's allowlist, ignoring any unknown keys."""
    keys = (
        "schemaVersion", "runId", "jobId", "requestId", "parentRunId", "retryOfRunId",
        "processEpoch", "featureCode", "routeCode", "taskType", "authorityKind",
        "appVersion", "buildId", "os", "pythonVersion", "createdAt", "updatedAt",
        "finishedAt", "elapsedMs", "observedStatus", "attemptedEngine", "finalEngine",
        "adapter", "fallbackReason", "droppedEvents", "droppedErrors", "droppedIssues",
        "issueCodes", "requiredProducerCoverage",
    )
    result = {key: record.get(key) for key in keys}
    result["events"] = [
        _safe_event(item) for item in record.get("events", []) if isinstance(item, dict)
    ]
    result["errors"] = [
        _safe_failure(item) for item in record.get("errors", []) if isinstance(item, dict)
    ]
    for key in ("firstFailure", "terminalFailure"):
        value = record.get(key)
        result[key] = _safe_failure(value) if isinstance(value, dict) else None
    observation = record.get("terminalObservation")
    result["terminalObservation"] = (
        {key: observation.get(key) for key in ("observedStatus", "observedAt", "processEpoch")}
        if isinstance(observation, dict) else None
    )
    return result


def _issue(code: str, run_id: str | None = None) -> dict[str, str | None]:
    # Issue codes are export-local and intentionally carry no filesystem path.
    return {"code": code if code in _SAFE_ISSUE_CODES else "read_failed", "runId": run_id}


def _append_issue(issues: list[dict[str, str | None]], code: str, run_id: str | None = None) -> None:
    item = _issue(code, run_id)
    if item not in issues and len(issues) < MAX_EXPORT_ISSUES:
        issues.append(item)


class DiagnosticsExportService:
    """Build bounded exports and retain only bounded in-memory preview snapshots."""

    def __init__(self, *, authority_resolver: Callable[[Any], tuple[bool, str | None]] | None = None) -> None:
        self._authority_resolver = authority_resolver or (lambda _record: (False, None))
        self._lock = threading.RLock()
        self._previews: dict[str, _Preview] = {}

    @staticmethod
    def _read(store: DiagnosticsStore, run_id: str) -> ReadResult:
        return store.read(run_id)

    def _record_projection(self, result: ReadResult) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if result.record is None:
            return None, None
        available, status = self._authority_resolver(result.record)
        projected = project_record(result.record, authority_status=status, authority_available=available)
        value = projected.get("record")
        metadata = {
            "diagnosticQuality": projected.get("diagnosticQuality"),
            "authorityState": projected.get("authorityState"),
            "authorityStatus": projected.get("authorityStatus"),
        }
        return (safe_record(value) if isinstance(value, dict) else None), metadata

    def _children(self, store: DiagnosticsStore, selected: str, issues: list[dict[str, str | None]], *, limit: int) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        root = store.runs_root
        if not root.exists():
            return []
        # The runs directory is an owned path. Reject a pivot before listing
        # it, and verify its resolved location remains below the injected data
        # root. This is a read-only guard; it never repairs or creates paths.
        try:
            if _is_reparse(root):
                _append_issue(issues, "read_failed", selected)
                return []
            root.resolve(strict=False).relative_to(store.data_root.resolve(strict=True))
        except (OSError, RuntimeError, ValueError):
            _append_issue(issues, "read_failed", selected)
            return []
        found: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        entries = 0
        started = time.monotonic()
        try:
            iterator = root.iterdir()
            for item in iterator:
                entries += 1
                if entries > MAX_SCAN_ENTRIES or time.monotonic() - started >= SCAN_DEADLINE_SECONDS:
                    _append_issue(issues, "scan_limit", selected)
                    break
                if _is_reparse(item):
                    _append_issue(issues, "read_failed")
                    continue
                if item.suffix.lower() != ".json":
                    continue
                candidate = item.stem
                try:
                    valid_id(candidate, "run")
                except DiagnosticValidationError:
                    # Non-diagnostic/legacy names are not opened or echoed.
                    continue
                if candidate == selected:
                    continue
                result = self._read(store, candidate)
                if result.record is None:
                    if result.availability_reason not in {"missing_unknown"}:
                        # A corrupt file cannot prove that it is a child. Do
                        # not disclose unrelated run IDs discovered by scan.
                        _append_issue(issues, result.availability_reason)
                    continue
                if result.record.context.parent_run_id != selected:
                    continue
                try:
                    value, metadata = self._record_projection(result)
                except ExportError as error:
                    if error.code == "diagnostic_hidden":
                        _append_issue(issues, "missing_unknown")
                        continue
                    raise
                if value is not None and metadata is not None:
                    if len(found) < max(0, limit):
                        found.append((candidate, value, metadata))
                    else:
                        _append_issue(issues, "run_limit", selected)
        except (OSError, UnicodeError, RuntimeError):
            _append_issue(issues, "read_failed", selected)
        found.sort(key=lambda pair: (str(pair[1].get("createdAt") or ""), pair[0]))
        return found

    @staticmethod
    def _summary(selected_run_id: str, export_records: list[dict[str, Any]], issues: list[dict[str, str | None]]) -> str:
        lines = [
            f"Diagnostics export for {selected_run_id}.",
            f"Included {len(export_records)} bounded run record(s); {len(issues)} issue(s).",
        ]
        for item in export_records:
            record = item["record"]
            failure = record.get("terminalFailure") or record.get("firstFailure")
            reason = failure.get("reasonCode") if isinstance(failure, dict) else None
            stage = failure.get("stageCode") if isinstance(failure, dict) else None
            detail = f" status={record.get('observedStatus')}"
            if stage:
                detail += f" stage={stage}"
            if reason:
                detail += f" reason={reason}"
            lines.append(f"- {item['relation']} {item['runId']}:{detail}")
        if issues:
            lines.append("Some related records were unavailable or bounded; see issues by code.")
        return "\n".join(lines)

    def build(self, store: DiagnosticsStore, selected_run_id: str, *, include_parent: bool, include_children: bool) -> ExportBundle:
        try:
            valid_id(selected_run_id, "run")
        except DiagnosticValidationError as error:
            raise ExportError("invalid_run_id") from error
        result = self._read(store, selected_run_id)
        if result.record is None:
            raise ExportError("diagnostic_not_found" if result.availability_reason == "missing_unknown" else "diagnostic_unavailable")
        selected, selected_metadata = self._record_projection(result)
        if selected is None or selected_metadata is None:
            raise ExportError("diagnostic_unavailable")

        issues: list[dict[str, str | None]] = []
        records: list[tuple[str, dict[str, Any], str, dict[str, Any]]] = [(selected_run_id, selected, "selected", selected_metadata)]
        parent_id = result.record.context.parent_run_id
        if include_parent and parent_id is not None:
            parent_result = self._read(store, parent_id)
            if parent_result.record is None:
                _append_issue(issues, parent_result.availability_reason, parent_id)
            else:
                try:
                    parent, parent_metadata = self._record_projection(parent_result)
                except ExportError as error:
                    if error.code == "diagnostic_hidden":
                        _append_issue(issues, "missing_unknown", parent_id)
                        parent = parent_metadata = None
                    else:
                        raise
                if parent is not None and parent_metadata is not None:
                    records.append((parent_id, parent, "parent", parent_metadata))
                else:
                    _append_issue(issues, "read_failed", parent_id)

        room = MAX_EXPORT_RUNS - len(records)
        children = self._children(store, selected_run_id, issues, limit=room) if include_children else []
        records.extend((run_id, value, "child", metadata) for run_id, value, metadata in children)

        # Build incrementally so a large set of valid 128 KiB records can never
        # produce an over-sized downloadable payload. Selected/parent are kept.
        export_records: list[dict[str, Any]] = []
        omitted = 0
        for run_id, value, relation, metadata in records:
            candidate = {"runId": run_id, "relation": relation, **metadata, "record": value}
            if len(canonical_json_bytes(candidate)) > MAX_EXPORT_RUN_BYTES:
                if relation == "selected":
                    raise ExportError("export_run_too_large")
                _append_issue(issues, "byte_limit", run_id)
                omitted += 1
                continue
            tentative = {
                "schemaVersion": EXPORT_VERSION,
                "exportType": "diagnostics",
                "selectedRunId": selected_run_id,
                "options": {"includeParent": include_parent, "includeChildren": include_children},
                "runs": export_records + [candidate],
                "issues": issues,
            }
            tentative["summary"] = self._summary(selected_run_id, tentative["runs"], issues)
            if len(canonical_json_bytes(tentative)) > MAX_EXPORT_BYTES and export_records:
                omitted += 1
                continue
            export_records.append(candidate)
        if omitted:
            _append_issue(issues, "byte_limit", selected_run_id)
        summary = self._summary(selected_run_id, export_records, issues)

        def make_payload() -> tuple[dict[str, Any], bytes]:
            payload = {
                "schemaVersion": EXPORT_VERSION,
                "exportType": "diagnostics",
                "selectedRunId": selected_run_id,
                "options": {"includeParent": include_parent, "includeChildren": include_children},
                "runs": export_records,
                "issues": issues,
                "summary": summary,
            }
            return payload, canonical_json_bytes(payload)

        payload, payload_bytes = make_payload()
        # Summary is part of the downloaded JSON, so re-check the final bytes
        # after building it. Drop only related children until the one-file
        # bound holds; selected and parent records are retained.
        while len(payload_bytes) > MAX_EXPORT_BYTES and len(export_records) > 1:
            export_records.pop()
            _append_issue(issues, "byte_limit", selected_run_id)
            omitted += 1
            summary = self._summary(selected_run_id, export_records, issues)
            payload, payload_bytes = make_payload()
        if len(payload_bytes) > MAX_EXPORT_BYTES:
            raise ExportError("export_too_large")
        return ExportBundle(selected_run_id, include_parent, include_children, payload, payload_bytes, summary)

    def preview(self, store: DiagnosticsStore, selected_run_id: str, *, include_parent: bool, include_children: bool) -> dict[str, Any]:
        bundle = self.build(store, selected_run_id, include_parent=include_parent, include_children=include_children)
        token = _TOKEN_PREFIX + secrets.token_urlsafe(32)
        with self._lock:
            if len(self._previews) >= MAX_PREVIEWS:
                oldest = next(iter(self._previews))
                self._previews.pop(oldest, None)
            self._previews[token] = _Preview(token, selected_run_id, include_parent, include_children, bundle)
        return bundle.preview(token)

    def download(self, store: DiagnosticsStore, selected_run_id: str, *, include_parent: bool, include_children: bool, token: str) -> bytes:
        if not isinstance(token, str) or not token.startswith(_TOKEN_PREFIX) or len(token) > 80:
            raise ExportError("invalid_preview_token")
        try:
            valid_id(selected_run_id, "run")
        except DiagnosticValidationError as error:
            raise ExportError("invalid_run_id") from error
        with self._lock:
            item = self._previews.get(token)
        if item is None:
            raise ExportError("export_preview_expired")
        if item.selected_run_id != selected_run_id or item.include_parent != include_parent or item.include_children != include_children:
            raise ExportError("export_preview_mismatch")
        return item.bundle.payload_bytes

    def token_options(self, token: str) -> tuple[bool, bool]:
        """Return snapshot options for the conventional token-only download."""
        with self._lock:
            item = self._previews.get(token)
        if item is None:
            raise ExportError("export_preview_expired")
        return item.include_parent, item.include_children
