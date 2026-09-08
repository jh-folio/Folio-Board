#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run qa_deep_research_execution.py <source-root> <attempt-dir>
# 3. Or make executable and run:
#      chmod +x qa_deep_research_execution.py && ./qa_deep_research_execution.py <source-root> <attempt-dir>
# ──────────────────

from __future__ import annotations

import hashlib
import json
import gc
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from qa_deep_research_fixtures import (
    FakeApi,
    Fixture,
    database_counts,
    prepare_fixture,
    start_fake_api,
    stop_fake_api,
)
from qa_dev_surface_support import (
    HttpResult,
    QaFailure,
    free_port,
    request_json,
    start_real_app,
    stop_server,
    wait_real_app_ready,
)

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class Session:
    fixture: Fixture
    attempt: Path
    baseUrl: str
    environment: dict[str, str]


def _hash(value: JsonValue) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _redact(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: ("<redacted>" if key.lower() in {"token", "authorization", "api_key", "apikey"} else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return value.replace("PRIVATE_", "<private>").replace("CANARY", "<canary>")
    return value


def _trace(session: Session, method: str, path: str, payload: dict[str, JsonValue] | None, result: HttpResult, requests: list[JsonValue], responses: list[JsonValue]) -> HttpResult:
    requests.append({"seq": len(requests) + 1, "method": method, "path": path, "payload": _redact(payload or {})})
    responses.append({"seq": len(responses) + 1, "method": method, "path": path, "status": result.status, "payload": _redact(result.payload)})
    return result


def _call(session: Session, method: str, path: str, payload: dict[str, JsonValue] | None, requests: list[JsonValue], responses: list[JsonValue]) -> HttpResult:
    try:
        result = request_json(session.baseUrl, path, method, payload)
    except (urllib.error.URLError, TimeoutError) as error:
        raise QaFailure(f"http_{method.lower()}_{path.replace('/', '_')}") from error
    return _trace(session, method, path, payload, result, requests, responses)


def _job_id(result: HttpResult) -> str:
    job = result.payload.get("job")
    if not isinstance(job, dict):
        raise QaFailure("job_shape")
    value = str(job.get("id") or "")
    if not value:
        raise QaFailure("job_id_missing")
    return value


def _poll(session: Session, job_id: str, requests: list[JsonValue], responses: list[JsonValue], *, timeout: float = 120.0) -> dict[str, JsonValue]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _call(session, "GET", f"/api/jobs/{job_id}", None, requests, responses)
        if result.status != 200:
            raise QaFailure("job_poll_status")
        status = str(result.payload.get("status") or "")
        if status in {"done", "cancelled", "failed", "failed_cancel", "failed_commit", "failed_restart", "failed_commit_recovery"}:
            return result.payload
        time.sleep(0.1)
    raise QaFailure("job_poll_timeout")


def _plan_body(*, collection_ref: dict[str, JsonValue] | None = None, question: str = "QA deep research execution") -> dict[str, JsonValue]:
    return {
        "question": question,
        "userContext": "QA_HYPOTHESIS_CANARY",
        "deepResearch": True,
        "customTickers": {"QAE": "QA Evidence"},
        "marketStatePolicy": "include_current",
        "marketStateScope": "GLOBAL",
        "collectionRef": collection_ref,
    }


def _execution(envelope: dict[str, JsonValue], mode: str, adapter: str) -> dict[str, JsonValue]:
    approved = envelope.get("approvedRequest")
    grant = envelope.get("approval")
    if not isinstance(approved, dict) or not isinstance(grant, dict):
        raise QaFailure("plan_envelope_shape")
    return {
        "approvedRequest": approved,
        "approval": {"id": grant.get("id"), "token": grant.get("token")},
        "execution": {"mode": mode, "adapter": adapter, "fallbackPolicy": "rules_on_engine_failure"},
    }


def _without_artifact_id(rows: JsonValue) -> JsonValue:
    if not isinstance(rows, list):
        return rows
    return [
        {key: value for key, value in row.items() if key != "artifactId"}
        for row in rows
        if isinstance(row, dict)
    ]


def _provenance(report: dict[str, JsonValue]) -> dict[str, JsonValue]:
    resolution = report.get("researchResolution")
    if isinstance(resolution, dict):
        resolution = dict(resolution)
        resolution.pop("resolvedAt", None)
    market_state = report.get("marketStateResolution")
    if isinstance(market_state, dict):
        market_state = dict(market_state)
        ref = market_state.get("ref")
        if isinstance(ref, dict):
            ref = dict(ref)
            ref.pop("resolvedAt", None)
            market_state["ref"] = ref
    summary = report.get("evidencePackSummary")
    stable_summary: dict[str, JsonValue] = {}
    if isinstance(summary, dict):
        for key in ("axisCoverage", "deepResearch", "roleCounts", "totalDocs", "memoryCount"):
            if key in summary:
                stable_summary[key] = summary[key]
        coverage = summary.get("questionCoverage")
        if isinstance(coverage, dict):
            stable_summary["questionCoverage"] = {
                question_id: {
                    field: question.get(field)
                    for field in ("axisKey", "round", "count", "level")
                    if field in question
                }
                for question_id, question in coverage.items()
                if isinstance(question, dict)
            }
    return {
        "researchResolution": resolution,
        "evidenceItems": _without_artifact_id(report.get("evidenceItems", [])),
        "sourceLedger": _without_artifact_id(report.get("sourceLedger", [])),
        "marketStateResolution": market_state,
        "evidencePackSummary": stable_summary,
    }


def _report_id(job: dict[str, JsonValue]) -> str:
    result = job.get("result")
    if isinstance(result, dict):
        for key in ("reportId", "artifactId"):
            if result.get(key):
                return str(result[key])
        refs = result.get("artifactRefs")
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict) and ref.get("id"):
                    return str(ref["id"])
    raise QaFailure("report_id_missing")


def _assert_no_report(session: Session, report_id: str, requests: list[JsonValue], responses: list[JsonValue]) -> None:
    result = _call(session, "GET", f"/api/topic-reports/{report_id}", None, requests, responses)
    if result.status != 404:
        raise QaFailure("unexpected_report_after_conflict")


def _copy_clean_marker(runtime: Path) -> bool:
    marker = runtime / ".folio-qa-owned"
    return marker.is_file() and marker.read_text(encoding="utf-8") == "folio-board-0-2-0\n"


def _remove_owned(runtime: Path) -> None:
    if not _copy_clean_marker(runtime):
        raise QaFailure("cleanup_marker_missing")
    last_error: OSError | None = None
    for _attempt in range(60):
        try:
            shutil.rmtree(runtime)
            return
        except OSError as error:
            last_error = error
            time.sleep(0.1)
    if last_error is not None:
        raise last_error


def _restart(
    session: Session,
    process: subprocess.Popen[str],
    output,
    port: int,
    environment: Mapping[str, str],
    restarts: list[JsonValue],
    requests: list[JsonValue],
    responses: list[JsonValue],
    spawned: list[subprocess.Popen[str]],
    restore_path: Path | None = None,
) -> subprocess.Popen[str]:
    response = _call(session, "POST", "/api/server/restart", {}, requests, responses)
    if response.status not in {200, 202}:
        raise QaFailure("restart_request_status")
    old_pid = process.pid
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.05)
    if process.poll() is None or process.returncode != 3:
        raise QaFailure("restart_exit_code")
    if restore_path is not None:
        _restore_index_backup(restore_path)
    process = start_real_app(session.fixture.workspace, port, output, environment=environment)
    spawned.append(process)
    wait_real_app_ready(process, session.baseUrl)
    restarts.append({"oldPid": old_pid, "newPid": process.pid, "port": port, "exitCode": 3})
    return process


def _restart_after_fault(
    session: Session,
    process: subprocess.Popen[str],
    output,
    port: int,
    environment: Mapping[str, str],
    restarts: list[JsonValue],
    spawned: list[subprocess.Popen[str]],
) -> subprocess.Popen[str]:
    old_pid = process.pid
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(0.05)
    if process.poll() is None or process.returncode != 91:
        raise QaFailure("after_artifact_fault_exit")
    process = start_real_app(session.fixture.workspace, port, output, environment=environment)
    spawned.append(process)
    wait_real_app_ready(process, session.baseUrl)
    restarts.append({"oldPid": old_pid, "newPid": process.pid, "port": port, "exitCode": 91, "reason": "after_artifact"})
    return process


def _collection(session: Session, requests: list[JsonValue], responses: list[JsonValue]) -> dict[str, JsonValue]:
    body = {"name": "QA Deep Research Collection", "query": "live", "market": "US", "sources": ["Reuters"], "tickers": [], "tags": []}
    created = _call(session, "POST", "/api/smart-collections", body, requests, responses)
    if created.status != 201:
        raise QaFailure("collection_create_status")
    collection = created.payload.get("collection")
    if not isinstance(collection, dict):
        raise QaFailure("collection_shape")
    return collection


def _add_live_rss(fixture: Fixture) -> None:
    path = fixture.inbox / "rss" / "live-qa.md"
    path.write_text(
        "---\ndate: 2026-07-20T00:00:00\ntitle: QA Live RSS 주가 Stock Market\nsource: Reuters\nmarkets: [\"US\"]\ncollector: rss\nsource_type: news\n"
        "collection_status: summary_only\nreliability_tier: 2\nurl: https://qa.example/live\n---\n"
        "# QA Live RSS 주가 Stock Market\n\nalpha live RSS 주가 stock market evidence\n",
        encoding="utf-8",
    )
    stat = path.stat()
    import sqlite3

    with sqlite3.connect(fixture.data / "research-index.sqlite3") as connection:
        connection.execute(
            "INSERT OR REPLACE INTO file_manifest (path, file_signature, market_relevant, doc_id, modified_at) VALUES (?,?,?,?,?)",
            (
                path.relative_to(fixture.workspace).as_posix(),
                f"{stat.st_size}:{stat.st_mtime_ns}",
                0,
                "",
                "2026-07-20T00:00:00Z",
            ),
        )


def _touch_live_rss(fixture: Fixture) -> None:
    path = fixture.inbox / "rss" / "live-qa.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n<!-- explicit-index-once -->\n")


def _clear_index_database(path: Path) -> None:
    with sqlite3.connect(path, timeout=30) as connection:
        for table in ("chunks_fts", "chunks", "documents", "file_manifest", "rss_feed_items"):
            connection.execute(f"DELETE FROM {table}")


def _restore_index_backup(path: Path) -> None:
    backup = path.with_suffix(".qa-backup")
    if not backup.is_file():
        return
    last_error: OSError | None = None
    for _attempt in range(60):
        try:
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{path}{suffix}")
                if sidecar.exists():
                    sidecar.unlink()
            if path.exists():
                path.unlink()
            backup.replace(path)
            return
        except OSError as error:
            last_error = error
            gc.collect()
            time.sleep(0.1)
    if last_error is not None:
        raise last_error


def _index_once(session: Session, requests: list[JsonValue], responses: list[JsonValue]) -> dict[str, JsonValue]:
    result = _call(session, "POST", "/api/index", {"incremental": True}, requests, responses)
    if result.status not in {200, 202}:
        raise QaFailure("index_submit_status")
    if result.status == 202 or (result.status == 200 and result.payload.get("job")):
        job_id = _job_id(result)
        return _poll(session, job_id, requests, responses)
    if result.status == 200 and result.payload.get("kind") == "index" and result.payload.get("id"):
        return _poll(session, str(result.payload["id"]), requests, responses)
    return result.payload


def _import_rss(session: Session, requests: list[JsonValue], responses: list[JsonValue]) -> dict[str, JsonValue]:
    result = _call(session, "POST", "/api/rssarchive/import", {}, requests, responses)
    if result.status not in {200, 202}:
        raise QaFailure("rss_submit_status")
    if result.status == 202 or (result.status == 200 and result.payload.get("job")):
        return _poll(session, _job_id(result), requests, responses)
    if result.status == 200 and result.payload.get("kind") == "rss" and result.payload.get("id"):
        return _poll(session, str(result.payload["id"]), requests, responses)
    return result.payload


def _submit_and_read(
    session: Session,
    envelope: dict[str, JsonValue],
    mode: str,
    adapter: str,
    requests: list[JsonValue],
    responses: list[JsonValue],
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    submitted = _call(session, "POST", "/api/topic-reports", _execution(envelope, mode, adapter), requests, responses)
    if submitted.status == 501:
        raise QaFailure("RED_topic_execution_501")
    if submitted.status != 202:
        raise QaFailure(f"execution_submit_{submitted.status}")
    job_id = _job_id(submitted)
    job = _poll(session, job_id, requests, responses)
    if str(job.get("status")) != "done":
        raise QaFailure(f"execution_terminal_{job.get('status')}")
    report_id = _report_id(job)
    report = _call(session, "GET", f"/api/topic-reports/{report_id}", None, requests, responses)
    if report.status != 200 or not isinstance(report.payload, dict):
        raise QaFailure("report_reopen_status")
    return job, report.payload


def _run_full(session: Session, process: subprocess.Popen[str], output, port: int, environment: Mapping[str, str], fake: FakeApi, requests: list[JsonValue], responses: list[JsonValue], restarts: list[JsonValue], spawned: list[subprocess.Popen[str]]) -> tuple[subprocess.Popen[str], list[JsonValue]]:
    checks: list[JsonValue] = []
    first = _call(session, "POST", "/api/topic-reports/plan", _plan_body(), requests, responses)
    if first.status != 200:
        raise QaFailure("plan_direct_status")
    direct_job, direct_report = _submit_and_read(session, first.payload, "direct", "auto", requests, responses)
    checks.append({"step": "direct_done", "jobId": direct_job.get("id"), "reportId": _report_id(direct_job)})
    process = _restart(session, process, output, port, environment, restarts, requests, responses, spawned)
    reopened = _call(session, "GET", f"/api/topic-reports/{_report_id(direct_job)}", None, requests, responses)
    if reopened.status != 200:
        raise QaFailure("restart_reopen_report")
    second = _call(session, "POST", "/api/topic-reports/plan", _plan_body(question="QA CLI deep research execution"), requests, responses)
    if second.status != 200:
        raise QaFailure("plan_cli_status")
    cli_job, cli_report = _submit_and_read(session, second.payload, "cli", "codex", requests, responses)
    direct_provenance = _provenance(direct_report)
    cli_provenance = _provenance(cli_report)
    if _hash(direct_provenance) != _hash(cli_provenance):
        raise QaFailure("direct_cli_provenance_mismatch")
    checks.append({"step": "direct_cli_parity", "directJob": direct_job.get("id"), "cliJob": cli_job.get("id"), "provenanceHash": _hash(direct_provenance)})
    _add_live_rss(session.fixture)
    _import_rss(session, requests, responses)
    collection = _collection(session, requests, responses)
    collection_ref = {"id": collection.get("id"), "revision": collection.get("revision")}
    constrained = _call(session, "POST", "/api/topic-reports/plan", _plan_body(collection_ref=collection_ref, question="zzzzunique"), requests, responses)
    if constrained.status != 200:
        raise QaFailure("collection_plan_status")
    preview = constrained.payload.get("preview")
    if not isinstance(preview, dict):
        raise QaFailure("collection_preview_shape")
    resolution = preview.get("resolution")
    if not isinstance(resolution, dict):
        raise QaFailure("collection_resolution_shape")
    unusable = resolution.get("unusableCandidates")
    if not isinstance(unusable, list) or len(unusable) != 1:
        raise QaFailure("unindexed_rss_not_visible")
    before_submit = _call(session, "POST", "/api/topic-reports", _execution(constrained.payload, "direct", "auto"), requests, responses)
    if before_submit.status != 409 or before_submit.payload.get("error") != "evidence_confirmation_required":
        raise QaFailure("unindexed_rss_entered_pack")
    _touch_live_rss(session.fixture)
    _index_once(session, requests, responses)
    resolved = _call(session, "POST", f"/api/smart-collections/{collection.get('id')}/resolve", {"expectedRevision": collection.get("revision"), "limit": 120}, requests, responses)
    if resolved.status != 200:
        raise QaFailure("collection_resolve_after_index")
    execution_universe = resolved.payload.get("executionUniverseIds")
    resolved_items = resolved.payload.get("items")
    if not isinstance(execution_universe, list) or not isinstance(resolved_items, list):
        raise QaFailure("rss_not_mapped_once")
    live_index_ids = [
        str(provider.get("id"))
        for item in resolved_items
        if isinstance(item, dict)
        and any(str(provider.get("provider")) == "rss" and str(provider.get("id")) == "live-qa.md" for provider in item.get("providerIds", []) if isinstance(provider, dict))
        for provider in item.get("providerIds", [])
        if isinstance(provider, dict) and str(provider.get("provider")) == "index" and provider.get("id")
    ]
    if len(live_index_ids) != 1:
        raise QaFailure("rss_not_mapped_once")
    live_index_id = live_index_ids[0]
    if execution_universe.count(live_index_id) != 1 or execution_universe.count("doc-allowed") != 1:
        raise QaFailure("rss_not_mapped_once")
    checks.append({"step": "rss_unindexed_then_indexed", "unusableBefore": unusable, "executionUniverseAfter": execution_universe, "eligibleTotal": resolved.payload.get("total"), "liveIndexId": live_index_id})
    zero_db = session.fixture.data / "research-index.sqlite3"
    backup = zero_db.with_suffix(".qa-backup")
    shutil.copy2(zero_db, backup)
    _clear_index_database(zero_db)
    zero = _call(session, "POST", "/api/topic-reports/plan", _plan_body(question="QA confirmed zero"), requests, responses)
    if zero.status != 200:
        raise QaFailure("zero_plan_status")
    zero_preview = zero.payload.get("preview")
    zero_evidence = zero_preview.get("zeroEvidence") if isinstance(zero_preview, dict) else None
    if not isinstance(zero_evidence, dict) or zero_evidence.get("reasonCode") != "zero_matches":
        raise QaFailure("zero_reason")
    zero_reason = str(zero_evidence.get("reasonCode"))
    zero_grant = zero.payload.get("approval")
    if not isinstance(zero_grant, dict):
        raise QaFailure("zero_approval_shape")
    confirmed = _call(session, "POST", "/api/topic-reports/confirm-degraded", {"approvedRequest": zero.payload.get("approvedRequest"), "approval": {"id": zero_grant.get("id"), "token": zero_grant.get("token")}, "reasonCode": zero_reason, "resolutionFingerprint": zero_evidence.get("resolutionFingerprint"), "confirmed": True}, requests, responses)
    if confirmed.status != 200:
        raise QaFailure("zero_confirm_status")
    zero_job, zero_report = _submit_and_read(session, confirmed.payload, "cli", "codex", requests, responses)
    if zero_job.get("finalEngine") != "rules" or zero_job.get("fallbackReason") != "confirmed_zero_evidence":
        raise QaFailure("zero_rules_provenance")
    checks.append({"step": "confirmed_zero_rules", "jobId": zero_job.get("id"), "reportId": _report_id(zero_job), "reportKeys": sorted(zero_report)})
    process = _restart(
        session,
        process,
        output,
        port,
        environment,
        restarts,
        requests,
        responses,
        spawned,
        restore_path=zero_db,
    )
    indexed = _call(session, "POST", "/api/topic-reports/plan", _plan_body(collection_ref=collection_ref, question="live"), requests, responses)
    if indexed.status != 200:
        raise QaFailure("indexed_collection_plan_status")
    indexed_preview = indexed.payload.get("preview")
    indexed_resolution = indexed_preview.get("resolution") if isinstance(indexed_preview, dict) else None
    if not isinstance(indexed_resolution, dict):
        raise QaFailure("indexed_collection_resolution_shape")
    indexed_unusable = indexed_resolution.get("unusableCandidates")
    indexed_universe = indexed_resolution.get("executionUniverseIds")
    if indexed_unusable != [] or not isinstance(indexed_universe, list) or indexed_universe.count(live_index_id) != 1 or indexed_universe.count("doc-allowed") != 1:
        raise QaFailure("indexed_collection_resolution_mismatch")
    indexed_job, indexed_report = _submit_and_read(session, indexed.payload, "direct", "auto", requests, responses)
    persisted_research = indexed_report.get("researchResolution")
    if not isinstance(persisted_research, dict):
        raise QaFailure("research_resolution_missing")
    persisted_resolution = persisted_research.get("resolution")
    if not isinstance(persisted_resolution, dict):
        raise QaFailure("research_resolution_shape")
    for key in ("collectionId", "collectionRevision", "collectionDefinitionHash", "eligibleTotal", "candidateCap", "truncated", "resolvedCandidateIds", "executionUniverseIds", "unusableCandidates", "providerGenerations", "inputWatermark"):
        if persisted_resolution.get(key) != indexed_resolution.get(key):
            raise QaFailure("research_resolution_not_persisted_exact")
    selected_ids = persisted_resolution.get("selectedEvidenceIds")
    evidence_items = indexed_report.get("evidenceItems")
    source_ledger = indexed_report.get("sourceLedger")
    if not isinstance(selected_ids, list) or not isinstance(evidence_items, list) or not isinstance(source_ledger, list):
        raise QaFailure("indexed_evidence_shape")
    evidence_ids = [str(item.get("documentId")) for item in evidence_items if isinstance(item, dict) and item.get("documentId")]
    ledger_keys = [
        str(item.get("path") or item.get("url") or item.get("normalizedUrl"))
        for item in source_ledger
        if isinstance(item, dict) and (item.get("path") or item.get("url") or item.get("normalizedUrl"))
    ]
    if selected_ids.count(live_index_id) != 1 or evidence_ids.count(live_index_id) != 1:
        raise QaFailure("indexed_live_not_admitted_once")
    forbidden_ids = {"doc-off-999", *(f"doc-off-{index:03d}" for index in range(120))}
    if forbidden_ids.intersection({str(item) for item in selected_ids + evidence_ids}):
        raise QaFailure("indexed_off_filter_admitted")
    allowed_ids = {live_index_id, "doc-allowed"}
    if not set(evidence_ids).issubset(allowed_ids) or len(source_ledger) != len(evidence_items) or len(ledger_keys) != len(evidence_ids) or any("/off/" in key or "doc-off-" in key for key in ledger_keys):
        raise QaFailure("indexed_universe_breach")
    evidence_summary = indexed_report.get("evidencePackSummary")
    if not isinstance(evidence_summary, dict):
        raise QaFailure("indexed_coverage_missing")
    total_docs = evidence_summary.get("totalDocs")
    role_counts = evidence_summary.get("roleCounts")
    if total_docs != len(evidence_ids) or not isinstance(role_counts, dict) or sum(int(value) for value in role_counts.values() if isinstance(value, (int, float))) != len(evidence_ids):
        raise QaFailure("indexed_coverage_mismatch")
    quality = indexed_report.get("quality")
    quality_detail = quality.get("sourceGroundingDetail") if isinstance(quality, dict) else None
    quality_preflight = indexed_report.get("qualityPreflight")
    quality_inputs = quality_preflight.get("requiredInputs") if isinstance(quality_preflight, dict) else None
    source_count = quality_detail.get("sourceCount") if isinstance(quality_detail, dict) else None
    evidence_count = quality_detail.get("evidenceCount") if isinstance(quality_detail, dict) else None
    preflight_source_count = quality_inputs.get("sourceCount") if isinstance(quality_inputs, dict) else None
    if source_count != len(evidence_ids) or evidence_count != len(evidence_ids) or preflight_source_count != len(evidence_ids):
        raise QaFailure("indexed_quality_coverage_mismatch")
    checks.append({"step": "collection_constrained_report", "jobId": indexed_job.get("id"), "reportId": _report_id(indexed_job), "liveIndexId": live_index_id, "selectedEvidenceIds": selected_ids, "evidenceDocumentIds": evidence_ids, "sourceLedgerKeys": ledger_keys, "coverageTotalDocs": total_docs, "coverageRoleCounts": role_counts, "qualityEvidenceCount": evidence_count, "qualitySourceCount": source_count, "qualityPreflightSourceCount": preflight_source_count, "researchResolution": persisted_research})
    fault_arm = session.fixture.adapters / "fault-arm.txt"
    fault_consumed = Path(f"{fault_arm}.consumed")
    fault_consumed.unlink(missing_ok=True)
    fault_arm.write_text("armed\n", encoding="utf-8")
    fault_plan = _call(session, "POST", "/api/topic-reports/plan", _plan_body(collection_ref=collection_ref, question="QA crash after artifact"), requests, responses)
    if fault_plan.status != 200:
        raise QaFailure("fault_plan_status")
    fault_submit = _call(session, "POST", "/api/topic-reports", _execution(fault_plan.payload, "direct", "auto"), requests, responses)
    if fault_submit.status != 202:
        raise QaFailure("fault_submit_status")
    fault_job_id = _job_id(fault_submit)
    process = _restart_after_fault(session, process, output, port, environment, restarts, spawned)
    fault_arm.write_text("disarmed\n", encoding="utf-8")
    fault_terminal = _poll(session, fault_job_id, requests, responses)
    if str(fault_terminal.get("status")) != "done":
        raise QaFailure("fault_recovery_terminal")
    fault_report_id = _report_id(fault_terminal)
    fault_report_response = _call(session, "GET", f"/api/topic-reports/{fault_report_id}", None, requests, responses)
    if fault_report_response.status != 200 or not isinstance(fault_report_response.payload, dict):
        raise QaFailure("fault_recovery_report")
    if not fault_consumed.is_file():
        raise QaFailure("fault_not_triggered")
    residue: dict[str, JsonValue] = {}
    for root_name in ("job-commits", "job-staging", "job-context"):
        root = session.fixture.data / root_name
        residue[root_name] = [path.relative_to(root).as_posix() for path in sorted(root.rglob("*")) if path.is_file()] if root.exists() else []
    if any(residue.values()):
        raise QaFailure("fault_recovery_residue")
    checks.append({"step": "crash_after_artifact_recovery", "jobId": fault_job_id, "reportId": fault_report_id, "faultExitCode": 91, "terminalStatus": fault_terminal.get("status"), "jobCommit": fault_report_response.payload.get("jobCommit"), "residue": residue})
    stale = _call(session, "POST", "/api/topic-reports/plan", _plan_body(question="QA stale approval"), requests, responses)
    if stale.status != 200:
        raise QaFailure("stale_plan_status")
    stale_exec = _execution(stale.payload, "direct", "auto")
    stale_approved = stale_exec["approvedRequest"]
    if isinstance(stale_approved, dict):
        stale_approved["question"] = "QA stale changed"
    conflict = _call(session, "POST", "/api/topic-reports", stale_exec, requests, responses)
    if conflict.status != 409:
        raise QaFailure("stale_approval_not_rejected")
    checks.append({"step": "stale_approval", "status": conflict.status, "error": conflict.payload.get("error")})
    mode_path = fake.modePath
    mode_path.write_text("ok", encoding="utf-8")
    (session.fixture.adapters / "cli-mode.txt").write_text("slow", encoding="utf-8")
    session.environment["QA_FAKE_CLI_MODE_FILE"] = str(session.fixture.adapters / "cli-mode.txt")
    report_count_before_cancel = _report_file_count(session.fixture)
    cancel_plan = _call(session, "POST", "/api/topic-reports/plan", _plan_body(question="QA cancel before commit"), requests, responses)
    if cancel_plan.status != 200:
        raise QaFailure("cancel_plan_status")
    cancel_submit = _call(session, "POST", "/api/topic-reports", _execution(cancel_plan.payload, "cli", "codex"), requests, responses)
    if cancel_submit.status != 202:
        raise QaFailure("cancel_submit_status")
    cancel_id = _job_id(cancel_submit)
    cancelled = _call(session, "POST", f"/api/jobs/{cancel_id}/cancel", {}, requests, responses)
    cancel_terminal = _poll(session, cancel_id, requests, responses, timeout=30)
    if cancelled.status != 200 or str(cancel_terminal.get("status")) not in {"cancelled", "failed_cancel"}:
        raise QaFailure("cancel_before_commit")
    cancel_result = cancel_terminal.get("result")
    if isinstance(cancel_result, dict) and any(cancel_result.get(key) for key in ("reportId", "artifactId")):
        raise QaFailure("cancel_created_artifact")
    report_count_after_cancel = _report_file_count(session.fixture)
    if report_count_after_cancel != report_count_before_cancel:
        raise QaFailure("cancel_created_report")
    checks.append({"step": "cancel_before_commit", "jobId": cancel_id, "status": cancel_terminal.get("status"), "artifact": cancel_result, "reportCountBefore": report_count_before_cancel, "reportCountAfter": report_count_after_cancel})
    (session.fixture.adapters / "cli-mode.txt").write_text("normal", encoding="utf-8")
    return process, checks


def _write(path: Path, payload: JsonValue) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_lines(path: Path, rows: list[JsonValue]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _inventory(fixture: Fixture, runtime: Path) -> dict[str, JsonValue]:
    private_markers = ("PRIVATE_", "QA_HYPOTHESIS_CANARY")
    private_surfaces = (
        "workspace/data/jobs-v2.json",
        "workspace/data/jobs.json",
        "workspace/data/job-context/",
        "workspace/data/job-staging/",
        "workspace/data/job-commits/",
        "workspace/data/topic-plan-submissions/",
    )
    files: list[JsonValue] = []
    forbidden: list[JsonValue] = []
    for path in sorted(runtime.rglob("*")):
        if not path.is_file() or path.name == ".folio-qa-owned":
            continue
        relative = path.relative_to(runtime).as_posix()
        if any(token in relative for token in ("job-staging", "job-context", "job-commits", "topic-plan-submissions")):
            forbidden.append(relative)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = ""
        if any(marker in text for marker in private_markers) and (
            relative in private_surfaces or any(relative.startswith(prefix) for prefix in private_surfaces if prefix.endswith("/"))
        ):
            forbidden.append(f"private:{relative}")
        files.append({"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
    return {
        "database": database_counts(fixture.data / "research-index.sqlite3"),
        "files": files,
        "forbiddenLeftovers": forbidden,
        "reportFiles": [path.relative_to(fixture.data).as_posix() for path in sorted((fixture.data / "topic-reports").glob("*.json"))] if (fixture.data / "topic-reports").exists() else [],
    }


def _report_file_count(fixture: Fixture) -> int:
    reports = fixture.data / "topic-reports"
    return len(list(reports.glob("*.json"))) if reports.exists() else 0


def _artifact_inventory(path: Path) -> dict[str, JsonValue]:
    artifacts = {item.name for item in path.iterdir() if item.is_file()} if path.exists() else set()
    if path.exists():
        artifacts.add("result.json")
    return {
        "attempt": str(path),
        "result": str(path / "result.json"),
        "artifacts": sorted(artifacts),
    }


def _red_green_inventory(attempt: Path) -> dict[str, JsonValue]:
    return {
        "red": _artifact_inventory(attempt.parent / "red-final-2"),
        "green": _artifact_inventory(attempt),
    }


def _adversarial_classes(attempt: Path) -> list[JsonValue]:
    result_path = str(attempt / "result.json")
    return [
        {"class": "direct_http_execution", "check": "direct_done", "evidence": result_path},
        {"class": "cli_http_execution_and_parity", "check": "direct_cli_parity", "evidence": result_path},
        {"class": "unindexed_rss_confirmation_gate", "check": "rss_unindexed_then_indexed", "evidence": result_path},
        {"class": "indexed_rss_representative_admission", "check": "collection_constrained_report", "evidence": result_path},
        {"class": "duplicate_url_and_off_filter_exclusion", "check": "collection_constrained_report", "evidence": result_path},
        {"class": "confirmed_zero_rules_only", "check": "confirmed_zero_rules", "evidence": result_path},
        {"class": "stale_approval_conflict", "check": "stale_approval", "evidence": result_path},
        {"class": "cancel_before_commit", "check": "cancel_before_commit", "evidence": result_path},
        {"class": "crash_after_artifact_recovery", "check": "crash_after_artifact_recovery", "evidence": result_path},
    ]


def _protected_ok(protected: dict[str, str]) -> bool:
    return all(Path(path).is_file() and hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest for path, digest in protected.items())


def _claim(attempt: Path, passed: bool, failure: str | None, checks: list[JsonValue]) -> None:
    path = Path(r"D:\Project\Personal\FolioOS_Public\.omo\evidence\folio-os-0-2-0\task-7\harness\done-claim.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(
        path,
        {
            "task": "Todo 7 deep-research-execution real HTTP harness",
            "status": "confirmed" if passed else "working",
            "changedFiles": ["scripts/qa_dev_surface.py", "scripts/qa_dev_surface_support.py", "scripts/qa_deep_research_execution.py", "scripts/qa_deep_research_fixtures.py"],
            "tests": ["py -3 -m py_compile scripts/qa_dev_surface.py scripts/qa_dev_surface_support.py scripts/qa_deep_research_execution.py scripts/qa_deep_research_fixtures.py"],
            "manualQa": [str(attempt / "result.json")],
            "cleanup": [str(attempt / "cleanup-receipt.json")],
            "redGreen": _red_green_inventory(attempt),
            "adversarialClasses": _adversarial_classes(attempt),
            "checks": checks,
            "failure": failure,
        },
    )


def run(source_root: Path, attempt_dir: Path) -> int:
    attempt = attempt_dir.resolve()
    attempt.mkdir(parents=True, exist_ok=True)
    runtime = attempt / ".runtime"
    requests: list[JsonValue] = []
    responses: list[JsonValue] = []
    checks: list[JsonValue] = []
    restarts: list[JsonValue] = []
    spawned: list[subprocess.Popen[str]] = []
    process: subprocess.Popen[str] | None = None
    fake: FakeApi | None = None
    fixture: Fixture | None = None
    failure: str | None = None
    passed = False
    stop_receipt: dict[str, JsonValue] = {"serverStopped": False}
    cleanup_receipt: dict[str, JsonValue] = {"runtimeRemoved": False, "protectedRootsUnchanged": False}
    server_log = attempt / "server.log"
    port = free_port()
    environment: dict[str, str] = {}
    try:
        if runtime.exists() or not attempt.is_dir():
            raise QaFailure("ownership_runtime_exists")
        fixture = prepare_fixture(source_root, runtime)
        fake = start_fake_api(runtime / "fake-api-mode.txt")
        (fake.modePath).write_text("ok", encoding="utf-8")
        environment.update(
            {
                "PYTHONPATH": os.pathsep.join((str(runtime), str(fixture.workspace), os.environ.get("PYTHONPATH", ""))),
                "QA_FAKE_API_URL": fake.url,
                "OPENAI_RESPONSES_URL": fake.url,
                "FOLIO_OPENAI_BASE_URL": fake.url,
                "OPENAI_API_BASE_URL": fake.url,
                "OPENAI_API_KEY": "qa-fake-api-key",
                "LLM_PROVIDER": "openai",
                "AI_AGENT_ENABLED": "1",
                "AI_AGENT_MODE": "api",
                "STARTUP_REGIME_REFRESH": "0",
                "FOLIO_AGENT_CODEX_COMMAND": str(fixture.adapters / "qa_fake_cli.cmd"),
                "AGENT_CLI_PROVIDER": "codex",
                "QA_FAKE_CLI_MODE_FILE": str(fixture.adapters / "cli-mode.txt"),
                "FOLIO_QA_FAULT_STAGE": "after_artifact",
                "QA_FAULT_ARM_PATH": str(fixture.adapters / "fault-arm.txt"),
                "QA_RSS_TRACE_PATH": str(runtime / "rss-trace.jsonl"),
            }
        )
        manifest: dict[str, JsonValue] = {
            "scenario": "deep-research-execution",
            "sourceRoot": str(source_root.resolve()),
            "attemptDir": str(attempt),
            "runtime": str(runtime),
            "marker": ".folio-qa-owned",
            "port": port,
            "protectedRoots": fixture.protected,
            "fakeAdapters": {"api": fake.url, "cli": str(fixture.adapters / "qa_fake_cli.cmd")},
            "requiredArtifacts": ["manifest.json", "requests.jsonl", "responses.jsonl", "rss-trace.jsonl", "stores.json", "server.json", "restart.json", "stop.json", "cleanup-receipt.json", "result.json"],
        }
        _write(attempt / "manifest.json", manifest)
        with server_log.open("a", encoding="utf-8") as output:
            process = start_real_app(fixture.workspace, port, output, environment=environment)
            spawned.append(process)
            wait_real_app_ready(process, f"http://127.0.0.1:{port}")
            session = Session(fixture, attempt, f"http://127.0.0.1:{port}", environment)
            process, checks = _run_full(session, process, output, port, environment, fake, requests, responses, restarts, spawned)
        passed = True
    except (QaFailure, OSError, ValueError, json.JSONDecodeError, urllib.error.URLError) as error:
        failure = str(error)
        if failure == "RED_topic_execution_501":
            _write(attempt / "red-current.json", {"status": "red", "observable": "POST /api/topic-reports returned HTTP 501 topic_execution_deferred", "scenario": "deep-research-execution"})
    finally:
        if spawned:
            exit_codes: list[JsonValue] = []
            for child in reversed(spawned):
                exit_codes.append(stop_server(child))
            latest = spawned[-1]
            stop_receipt = {
                "serverStopped": all(child.poll() is not None for child in spawned),
                "pid": latest.pid,
                "pids": [child.pid for child in spawned],
                "exitCode": exit_codes[0] if exit_codes else 0,
            }
        if fixture is not None:
            _restore_index_backup(fixture.data / "research-index.sqlite3")
        if fake is not None:
            stop_fake_api(fake)
        if fixture is not None:
            cleanup_receipt["protectedRootsUnchanged"] = _protected_ok(fixture.protected)
            cleanup_receipt["markerOwned"] = _copy_clean_marker(runtime)
            stores = _inventory(fixture, runtime) if runtime.exists() else {"database": {"exists": False}, "files": [], "forbiddenLeftovers": []}
        else:
            stores = {"database": {"exists": False}, "files": [], "forbiddenLeftovers": []}
        if stores.get("forbiddenLeftovers"):
            failure = failure or "private_runtime_residue"
            passed = False
        _write_lines(attempt / "requests.jsonl", requests)
        _write_lines(attempt / "responses.jsonl", responses)
        trace_source = runtime / "rss-trace.jsonl"
        if trace_source.is_file():
            shutil.copy2(trace_source, attempt / "rss-trace.jsonl")
        else:
            (attempt / "rss-trace.jsonl").write_text("", encoding="utf-8")
        _write(attempt / "stores.json", stores)
        _write(attempt / "server.json", {"supervisorPid": os.getpid(), "port": port, "childPid": process.pid if process is not None else None, "state": "stopped"})
        _write(attempt / "restart.json", restarts)
        _write(attempt / "stop.json", stop_receipt)
        try:
            if runtime.exists():
                gc.collect()
                time.sleep(10.0)
                _remove_owned(runtime)
            cleanup_receipt["runtimeRemoved"] = not runtime.exists()
        except (OSError, QaFailure) as error:
            cleanup_receipt["error"] = str(error)
            failure = failure or str(error)
        _write(attempt / "cleanup-receipt.json", cleanup_receipt)
        _write(
            attempt / "result.json",
            {
                "scenario": "deep-research-execution",
                "passed": passed and bool(cleanup_receipt.get("runtimeRemoved")),
                "failure": failure,
                "checks": checks,
                "redGreen": _red_green_inventory(attempt),
                "adversarialClasses": _adversarial_classes(attempt),
                "evidence": ["manifest.json", "requests.jsonl", "responses.jsonl", "rss-trace.jsonl", "stores.json", "server.json", "restart.json", "stop.json", "cleanup-receipt.json", "result.json", "server.log"],
            },
        )
        _claim(attempt, passed and bool(cleanup_receipt.get("runtimeRemoved")), failure, checks)
    return 0 if passed and bool(cleanup_receipt.get("runtimeRemoved")) else 4


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    return run(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    raise SystemExit(main())
