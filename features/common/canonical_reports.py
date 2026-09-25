from __future__ import annotations

import os
import json
from collections.abc import Mapping
from pathlib import Path
from typing import assert_never

from features.common.canonical_identity import (
    CanonicalIdentityError,
    CanonicalNotFoundError,
    ReportKind,
    resolve_exact_report_path,
    validate_report_identity,
)
from features.common.canonical_json import JsonValue
from features.common.canonical_report_io import artifact_lock, atomic_write, safe_child_path
from features.common.canonical_report_state import (
    canonical_candidate,
    canonical_content_hash,
    copy_mapping,
    load_report,
    marker,
    matches_target,
    overlay_candidate,
    serialize,
    storage_hash,
    verify_base,
    verify_committed,
)
from features.common.canonical_report_types import (
    CanonicalConflictError,
    CanonicalValidationError,
    PreparedCanonicalWrite,
    WriteKind,
)
from features.common.atomic_replace import replace_with_retry


def _parse_prepare_request(
    request: Mapping[str, JsonValue],
) -> tuple[ReportKind, Path, WriteKind, Mapping[str, JsonValue], str | None, Mapping[str, JsonValue] | None]:
    expected_keys = {"reportKind", "exactPath", "writeKind", "candidate", "operationId", "jobMarker"}
    if set(request) != expected_keys:
        raise CanonicalValidationError("prepare_input_invalid", "prepare input fields are invalid")
    raw_kind = request.get("reportKind")
    raw_path = request.get("exactPath")
    raw_write_kind = request.get("writeKind")
    raw_candidate = request.get("candidate")
    raw_operation = request.get("operationId")
    raw_marker = request.get("jobMarker")
    if not isinstance(raw_kind, str) or not isinstance(raw_path, str) or not isinstance(raw_write_kind, str):
        raise CanonicalValidationError("prepare_input_invalid", "prepare identity fields are invalid")
    if not isinstance(raw_candidate, dict):
        raise CanonicalValidationError("prepare_input_invalid", "prepare candidate must be an object")
    if raw_operation is not None and not isinstance(raw_operation, str):
        raise CanonicalValidationError("prepare_input_invalid", "operationId must be a string or null")
    if raw_marker is not None and not isinstance(raw_marker, dict):
        raise CanonicalValidationError("prepare_input_invalid", "jobMarker must be an object or null")
    try:
        parsed_kind = ReportKind(raw_kind)
        parsed_write_kind = WriteKind(raw_write_kind)
    except ValueError as exc:
        raise CanonicalValidationError("prepare_input_invalid", "prepare enum value is invalid") from exc
    return parsed_kind, Path(raw_path), parsed_write_kind, raw_candidate, raw_operation, raw_marker


def prepare(
    request: Mapping[str, JsonValue] | None = None,
    *,
    report_kind: ReportKind | None = None,
    exact_path: Path | None = None,
    write_kind: WriteKind | None = None,
    candidate: Mapping[str, JsonValue] | None = None,
    operation_id: str | None = None,
    job_marker: Mapping[str, JsonValue] | None = None,
) -> PreparedCanonicalWrite:
    if request is not None:
        if any(value is not None for value in (report_kind, exact_path, write_kind, candidate, operation_id, job_marker)):
            raise CanonicalValidationError("prepare_input_invalid", "prepare object and keyword inputs cannot be mixed")
        report_kind, exact_path, write_kind, candidate, operation_id, job_marker = _parse_prepare_request(request)
    if report_kind is None or exact_path is None or write_kind is None or candidate is None:
        raise CanonicalValidationError("prepare_input_invalid", "prepare input is incomplete")
    path = safe_child_path(exact_path.parent, exact_path.name)
    if path.suffix != ".json":
        raise CanonicalIdentityError("canonical_path_invalid", "canonical path must end in .json")
    with artifact_lock(path):
        current = load_report(path)
        if current is not None:
            validate_report_identity(report_kind, path, current)
        match write_kind:
            case WriteKind.CANONICAL:
                if report_kind is ReportKind.COMPANY_ANALYSIS:
                    from features.company_analysis.recovery import guard_canonical
                    guard_canonical(path.parent, dict(candidate))
                if report_kind is ReportKind.TOPIC_REPORT:
                    from features.topic_report.execution import report_incomplete
                    if report_incomplete(dict(candidate)):
                        raise CanonicalValidationError("topic_report_incomplete", "딥 리서치 실행이 완료되지 않았습니다.")
                target, target_revision, content_hash, changed = canonical_candidate(
                    current,
                    candidate,
                    operation_id,
                )
                validate_report_identity(report_kind, path, target)
            case WriteKind.OVERLAY:
                target, target_revision, content_hash, changed = overlay_candidate(current, candidate)
            case unreachable:
                assert_never(unreachable)
        if job_marker is None:
            target.pop("jobCommit", None)
        else:
            target["jobCommit"] = copy_mapping(job_marker)
            target_marker = marker(target)
            if (
                not isinstance(operation_id, str)
                or not operation_id
                or target_marker is None
                or target_marker.get("operationId") != operation_id
            ):
                raise CanonicalValidationError(
                    "job_marker_operation_mismatch",
                    "job marker operationId must equal the prepared operationId",
                )
        serialized = serialize(target)
        return PreparedCanonicalWrite(
            report_kind=report_kind,
            exact_path=path,
            base_hash=storage_hash(current) if current is not None else None,
            base_marker=marker(current),
            target_hash=storage_hash(target),
            target_revision=target_revision,
            canonical_content_hash=content_hash,
            canonical_changed=changed,
            serialized_bytes=serialized,
            operation_id=operation_id,
            target_marker=marker(target),
        )


def commit_sync(prepared: PreparedCanonicalWrite) -> PreparedCanonicalWrite:
    # Direct report paths use this common canonical promotion.  The optional
    # recorder is already bound by their API/worker owner; standalone callers
    # remain inert and never acquire a diagnostics writer.
    from features.common.jobs import diagnostic_stage_end, diagnostic_stage_failure, diagnostic_stage_start

    recorder, stage_id = diagnostic_stage_start("commit")
    try:
        with artifact_lock(prepared.exact_path):
            current = load_report(prepared.exact_path)
            if matches_target(current, prepared):
                result = prepared
            else:
                verify_base(current, prepared)
                atomic_write(prepared.exact_path, prepared.serialized_bytes)
                verify_committed(prepared)
                result = prepared
    except Exception as error:
        diagnostic_stage_failure(
            recorder,
            error,
            stage_id=stage_id,
            stage_code="commit" if stage_id is not None else None,
            boundary="save",
        )
        # The caller decides whether a caught direct save failure reaches a
        # terminal observation; preserve the actual open commit gap here.
        raise
    diagnostic_stage_end(recorder, stage_id, "commit")
    return result


def _intent_contains_target(
    commit_intent: Mapping[str, JsonValue],
    prepared: PreparedCanonicalWrite,
) -> bool:
    if set(commit_intent) != {"operationId", "expectedArtifacts", "terminalProjection"}:
        return False
    if commit_intent.get("operationId") != prepared.operation_id:
        return False
    if not isinstance(commit_intent.get("terminalProjection"), dict):
        return False
    target_marker = prepared.target_marker
    if target_marker is None or target_marker.get("operationId") != prepared.operation_id:
        return False
    artifacts = commit_intent.get("expectedArtifacts")
    if not isinstance(artifacts, list):
        return False
    artifact_type, artifact_id = _prepared_artifact_ref(prepared)
    expected = {
        "storage": "json",
        "type": artifact_type,
        "id": artifact_id,
        "baseHash": prepared.base_hash,
        "baseMarker": prepared.base_marker,
        "targetRevision": prepared.target_revision,
        "targetHash": prepared.target_hash,
    }
    return sum(isinstance(item, dict) and item == expected for item in artifacts) == 1


def _prepared_artifact_ref(prepared: PreparedCanonicalWrite) -> tuple[str, str]:
    target = json.loads(prepared.serialized_bytes)
    if not isinstance(target, dict):
        raise CanonicalConflictError("prepared_artifact_invalid", "prepared artifact must be an object")
    match prepared.report_kind:
        case ReportKind.BRIEFING:
            return "briefing_report", prepared.exact_path.stem
        case ReportKind.COMPANY_ANALYSIS:
            artifact_type = "company_analysis_report"
        case ReportKind.TOPIC_REPORT:
            artifact_type = "topic_report"
        case unreachable:
            assert_never(unreachable)
    artifact_id = target.get("id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CanonicalConflictError("prepared_artifact_invalid", "prepared artifact id is invalid")
    return artifact_type, artifact_id


def _stage_is_marker_owned(staged_path: Path, prepared: PreparedCanonicalWrite) -> bool:
    target_marker = prepared.target_marker
    if target_marker is None:
        return False
    job_id = target_marker.get("jobId")
    if not isinstance(job_id, str) or not job_id:
        return False
    parts = staged_path.resolve(strict=False).parts
    return any(
        part.casefold() == "job-staging" and index + 1 < len(parts) and parts[index + 1] == job_id
        for index, part in enumerate(parts)
    )


def promote_job(
    prepared: PreparedCanonicalWrite,
    staged_path: Path,
    commit_intent: Mapping[str, JsonValue],
) -> PreparedCanonicalWrite:
    if not _intent_contains_target(commit_intent, prepared):
        raise CanonicalConflictError("commit_intent_mismatch", "CommitIntent does not bind the prepared target")
    if not _stage_is_marker_owned(staged_path, prepared):
        raise CanonicalConflictError("staged_path_mismatch", "staged path is not owned by the prepared job marker")
    with artifact_lock(prepared.exact_path):
        current = load_report(prepared.exact_path)
        if matches_target(current, prepared):
            return prepared
        try:
            staged_bytes = staged_path.read_bytes()
        except FileNotFoundError as exc:
            raise CanonicalConflictError("staged_artifact_missing", "staged canonical artifact is missing") from exc
        if staged_bytes != prepared.serialized_bytes:
            raise CanonicalConflictError("staged_bytes_mismatch", "staged canonical bytes do not match prepare")
        verify_base(current, prepared)
        prepared.exact_path.parent.mkdir(parents=True, exist_ok=True)
        replace_with_retry(staged_path, prepared.exact_path)
        verify_committed(prepared)
        return prepared


__all__ = [
    "CanonicalConflictError",
    "CanonicalIdentityError",
    "CanonicalNotFoundError",
    "CanonicalValidationError",
    "PreparedCanonicalWrite",
    "ReportKind",
    "WriteKind",
    "canonical_content_hash",
    "commit_sync",
    "prepare",
    "promote_job",
    "resolve_exact_report_path",
    "storage_hash",
]
