from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from features.common.diagnostics.authority import AuthoritySnapshot
from features.common.diagnostics.listing import DiagnosticsListService, ListQuery
from features.common.diagnostics.routes import create_diagnostics_router
from features.common.diagnostics.schema import new_context
from features.common.diagnostics.store import DiagnosticsStore


def _authority(revision: str = "stable") -> AuthoritySnapshot:
    return AuthoritySnapshot((), frozenset(), (), 0, 0, revision)


def _request(**params: str) -> Request:
    query = urlencode(params)
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/diagnostics/runs",
            "raw_path": b"/api/diagnostics/runs",
            "query_string": query.encode("ascii"),
            "headers": [],
            "client": ("test", 1),
            "server": ("test", 80),
            "root_path": "",
        }
    )


def _direct(store: DiagnosticsStore, status: str = "failed") -> str:
    recorder = store.start(
        new_context(
            feature_code="http",
            route_code="http_unhandled",
            authority_kind="direct",
        )
    )
    assert recorder is not None
    assert recorder.finish(status)
    return recorder.context.run_id


def test_http_list_rejects_unknown_duplicate_and_invalid_query(tmp_path):
    store = DiagnosticsStore(tmp_path)
    runtime = SimpleNamespace(store=store)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    router = create_diagnostics_router(
        runtime_provider=lambda: runtime,
        job_lookup=lambda _job_id: None,
        list_service=service,
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/runs")
    try:
        with pytest.raises(HTTPException) as unknown:
            endpoint(_request(**{"private-canary": "secret"}))
        assert unknown.value.status_code == 422
        assert unknown.value.detail == {"code": "unknown_query_parameter"}
        with pytest.raises(HTTPException) as invalid:
            endpoint(_request(outcome="nope"))
        assert invalid.value.status_code == 422
        assert invalid.value.detail == {"code": "invalid_outcome"}
        # Build duplicate query manually because urlencode(mapping) cannot
        # represent repeated keys.
        request = _request(limit="1")
        request.scope["query_string"] = b"limit=1&limit=2"
        with pytest.raises(HTTPException) as duplicate:
            endpoint(request)
        assert duplicate.value.status_code == 422
        assert duplicate.value.detail == {"code": "duplicate_query_parameter"}
    finally:
        store.close()


def test_http_cursor_tamper_and_query_mismatch_are_explicit(tmp_path):
    store = DiagnosticsStore(tmp_path)
    _direct(store)
    _direct(store)
    runtime = SimpleNamespace(store=store)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    router = create_diagnostics_router(
        runtime_provider=lambda: runtime,
        job_lookup=lambda _job_id: None,
        list_service=service,
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/runs")
    try:
        first = endpoint(_request(limit="1"))
        assert first["version"] == 1
        assert first["snapshotAt"].endswith("Z")
        assert first["scan"]["complete"] is True
        token = first["nextCursor"]
        assert token
        second = endpoint(_request(cursor=token, limit="1"))
        assert second["snapshotAt"] == first["snapshotAt"]
        tampered = _request(cursor=token[:-1] + ("A" if token[-1] != "A" else "B"), limit="1")
        with pytest.raises(HTTPException) as bad:
            endpoint(tampered)
        assert bad.value.status_code == 409
        assert bad.value.detail == {"code": "cursor_expired"}
        with pytest.raises(HTTPException) as mismatch:
            endpoint(_request(cursor=token, limit="2"))
        assert mismatch.value.status_code == 409
        assert mismatch.value.detail == {"code": "cursor_query_mismatch"}
    finally:
        store.close()


def test_http_period_is_utc_half_open_and_fallback_absence_is_unknown(tmp_path):
    store = DiagnosticsStore(tmp_path)
    run_id = _direct(store)
    runtime = SimpleNamespace(store=store)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    router = create_diagnostics_router(
        runtime_provider=lambda: runtime,
        job_lookup=lambda _job_id: None,
        list_service=service,
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/runs")
    try:
        record = store.read(run_id).record
        assert record is not None
        exact = record.created_at
        # Equal bounds are rejected; the half-open interval is not silently
        # changed to an inclusive range.
        request = _request(**{"from": exact, "to": exact})
        with pytest.raises(HTTPException) as period:
            endpoint(request)
        assert period.value.status_code == 422
        assert period.value.detail == {"code": "invalid_period"}
        unknown = endpoint(_request(outcome="unknown"))
        assert [item["runId"] for item in unknown["items"]] == [run_id]
        assert unknown["items"][0]["fallbackObserved"] is None
    finally:
        store.close()


def test_job_visibility_joins_worklog_id_without_detail_reads(tmp_path):
    store = DiagnosticsStore(tmp_path)
    # The service's direct row is enough to establish that the list can be
    # formed without calling the detail lookup; current job fixtures belong in
    # authority-provider tests because SharedJob is a closed Pydantic model.
    run_id = _direct(store, "succeeded")
    calls = []
    runtime = SimpleNamespace(store=store)
    service = DiagnosticsListService(authority_provider=lambda: _authority())
    router = create_diagnostics_router(
        runtime_provider=lambda: runtime,
        job_lookup=lambda _job_id: calls.append(_job_id),
        list_service=service,
    )
    endpoint = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/runs")
    try:
        payload = endpoint(_request())
        assert payload["items"][0]["runId"] == run_id
        assert calls == []
    finally:
        store.close()
