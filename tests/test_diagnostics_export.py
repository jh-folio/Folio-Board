from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi import HTTPException

import features.common.diagnostics.export as export_module
from features.common.diagnostics.export import MAX_EXPORT_BYTES, MAX_EXPORT_RUNS, safe_record
from features.common.diagnostics.routes import create_diagnostics_router
from features.common.diagnostics.runtime import DiagnosticsRuntime
from features.common.diagnostics.schema import new_context


def _runtime_run(runtime: DiagnosticsRuntime, *, parent: str | None = None, job_id: str | None = None) -> str:
    context = new_context(
        feature_code="jobs",
        route_code="shared_worker",
        authority_kind="shared_job" if job_id else "direct",
        parent_run_id=parent,
        job_id=job_id,
        app_version="0.6.0",
        build_id="abcdef1",
    )
    recorder = runtime.store.start(context)
    assert recorder is not None
    stage = recorder.start_stage("generate")
    assert stage is not None
    assert recorder.end_stage(stage, "generate", duration_ms=1)
    assert recorder.finish("failed")
    return context.run_id


def _endpoint(router, suffix: str):
    return next(route.endpoint for route in router.routes if route.path.endswith(suffix))


def test_export_preview_and_download_are_the_same_bounded_json(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    parent = _runtime_run(runtime)
    child = _runtime_run(runtime, parent=parent)
    router = create_diagnostics_router(runtime_provider=lambda: runtime, job_lookup=lambda _value: None)
    preview = _endpoint(router, "/export-preview")
    download = _endpoint(router, "/export")

    envelope = preview(child, {"includeParent": True, "includeChildren": False})
    assert envelope["runCount"] == 2
    assert envelope["json"]["selectedRunId"] == child
    assert envelope["json"]["summary"] == envelope["summary"]
    assert {item["relation"] for item in envelope["json"]["runs"]} == {"selected", "parent"}
    response = download(
        child,
        {"previewToken": envelope["previewToken"]},
    )
    assert response.headers["content-disposition"].endswith(f'"diagnostics-{child}.json"')
    assert json.loads(response.body) == envelope["json"]
    assert len(response.body) == envelope["byteCount"] <= MAX_EXPORT_BYTES
    token_only = download(child, {"previewToken": envelope["previewToken"]})
    assert token_only.body == response.body
    assert json.loads(response.body)["summary"] == envelope["summary"]
    try:
        download(child, {"includeParent": False, "includeChildren": False})
    except HTTPException as error:
        assert error.status_code == 422
        assert error.detail == {"code": "preview_token_required"}
    else:
        raise AssertionError("download must require a preview token")
    try:
        download(child, {"previewToken": "not-a-preview-token"})
    except HTTPException as error:
        assert error.status_code == 422
        assert error.detail == {"code": "invalid_preview_token"}
    else:
        raise AssertionError("download must reject malformed preview tokens")
    runtime.close()


def test_export_children_are_direct_and_capped(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    root = _runtime_run(runtime)
    direct = [_runtime_run(runtime, parent=root) for _ in range(MAX_EXPORT_RUNS + 2)]
    _runtime_run(runtime, parent=direct[0])
    router = create_diagnostics_router(runtime_provider=lambda: runtime, job_lookup=lambda _value: None)
    preview = _endpoint(router, "/export-preview")
    envelope = preview(root, {"includeParent": False, "includeChildren": True})
    assert envelope["runCount"] == MAX_EXPORT_RUNS
    assert all(item["relation"] in {"selected", "child"} for item in envelope["json"]["runs"])
    assert any(issue["code"] == "run_limit" for issue in envelope["json"]["issues"])
    # The cap keeps the earliest children by (createdAt, runId), not whatever the
    # filesystem lists first — NTFS lists alphabetically, macOS APFS did not, and
    # the kept set differed per OS. Children created in the same millisecond tie
    # on createdAt, so compare against the stored order rather than creation order.
    runs_dir = tmp_path / "diagnostics" / "runs"
    created = {
        run_id: json.loads((runs_dir / f"{run_id}.json").read_text(encoding="utf-8"))["createdAt"]
        for run_id in direct
    }
    earliest = sorted(direct, key=lambda run_id: (created[run_id], run_id))[: MAX_EXPORT_RUNS - 1]
    exported = [item["runId"] for item in envelope["json"]["runs"] if item["relation"] == "child"]
    assert exported == earliest
    assert len(json.dumps(envelope["json"], ensure_ascii=False).encode()) <= MAX_EXPORT_BYTES
    runtime.close()


def test_export_rejects_invalid_id_and_does_not_expose_arbitrary_fields(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    run_id = _runtime_run(runtime)
    router = create_diagnostics_router(runtime_provider=lambda: runtime, job_lookup=lambda _value: None)
    preview = _endpoint(router, "/export-preview")
    try:
        preview("../../secrets", {"includeParent": False, "includeChildren": False})
    except HTTPException as error:
        assert error.status_code == 422
        assert error.detail == {"code": "invalid_run_id"}
    else:
        raise AssertionError("path traversal must be rejected")

    safe = safe_record({"runId": run_id, "events": [], "errors": [], "firstFailure": None, "terminalFailure": None, "terminalObservation": None, "canary": "secret"})
    assert "canary" not in safe
    raw = json.loads((runtime.store.runs_root / f"{run_id}.json").read_text(encoding="utf-8"))
    raw["canary"] = "SECRET_CANARY"
    (runtime.store.runs_root / f"{run_id}.json").write_text(json.dumps(raw), encoding="utf-8")
    try:
        preview(run_id, {"includeParent": False, "includeChildren": False})
    except HTTPException as error:
        assert error.status_code == 503
        assert "SECRET_CANARY" not in str(error.detail)
    else:
        raise AssertionError("unknown persisted fields must fail closed")
    runtime.close()


def test_hidden_job_cannot_be_exported_by_run_id(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    job_id = "job_00000000-0000-4000-8000-000000000001"
    run_id = _runtime_run(runtime, job_id=job_id)
    job = {"id": job_id, "status": "failed"}
    authority = SimpleNamespace(hidden_job_ids=frozenset({job_id}))
    router = create_diagnostics_router(
        runtime_provider=lambda: runtime,
        job_lookup=lambda value: job if value == job_id else None,
        authority_provider=lambda: authority,
    )
    preview = _endpoint(router, "/export-preview")
    try:
        preview(run_id, {"includeParent": False, "includeChildren": False})
    except HTTPException as error:
        assert error.status_code == 404
        assert error.detail == {"code": "diagnostic_not_found"}
    else:
        raise AssertionError("hidden job must not be exportable")
    runtime.close()


def test_corrupt_related_record_is_reported_as_partial_without_raw_content(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    root = _runtime_run(runtime)
    child = _runtime_run(runtime, parent=root)
    child_path = runtime.store.runs_root / f"{child}.json"
    child_path.write_text('{"runId":"' + child + '","canary":"PRIVATE"}', encoding="utf-8")
    router = create_diagnostics_router(runtime_provider=lambda: runtime, job_lookup=lambda _value: None)
    preview = _endpoint(router, "/export-preview")
    envelope = preview(root, {"includeParent": False, "includeChildren": True})
    assert envelope["runCount"] == 1
    assert {item["code"] for item in envelope["json"]["issues"]} == {"corrupt"}
    assert "PRIVATE" not in json.dumps(envelope)
    runtime.close()


def test_children_scan_has_cooperative_deadline_and_bounded_candidates(tmp_path, monkeypatch):
    runtime = DiagnosticsRuntime(tmp_path)
    root = _runtime_run(runtime)
    for _ in range(3):
        _runtime_run(runtime, parent=root)
    # The service uses the existing diagnostics 250ms cooperative slice; this
    # fixture proves a slow scan reports partial metadata instead of looping.
    values = iter((0.0, 0.3))
    monkeypatch.setattr(export_module.time, "monotonic", lambda: next(values, 0.3))
    issues: list[dict[str, str | None]] = []
    exporter = export_module.DiagnosticsExportService()
    found = exporter._children(runtime.store, root, issues, limit=2)
    assert found == []
    assert any(issue["code"] == "scan_limit" for issue in issues)
    runtime.close()
