"""Headless v1 diagnostic detail routes; no UI or authority mutation."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response, status

from .authority import AuthoritySnapshotUnavailable, default_authority_snapshot
from .listing import (
    DiagnosticsListService,
    ListCursorError,
    ListQueryError,
    ListUnavailable,
    parse_list_query,
)
from .projection import project_read
from .export import DiagnosticsExportService, ExportError, parse_options
from .schema import DiagnosticValidationError, run_id_for_job, valid_id
from .store import ReadResult


def create_diagnostics_router(
    *,
    runtime_provider: Callable[[], Any],
    job_lookup: Callable[[str], Any],
    run_lookup: Callable[[str], Any] | None = None,
    authority_provider: Callable[[], Any] | None = None,
    list_service: DiagnosticsListService | None = None,
) -> APIRouter:
    """Build an injectable router so tests need no application lifespan."""
    router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])
    runs_list = list_service or DiagnosticsListService(
        authority_provider=authority_provider or default_authority_snapshot,
    )

    def _export_authority(record: Any) -> tuple[bool, str | None]:
        """Resolve only the status used by the normal safe projection."""
        job_id = getattr(record.context, "job_id", None)
        if job_id is not None:
            if authority_provider is not None:
                try:
                    authority = authority_provider()
                except AuthoritySnapshotUnavailable as error:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "authority_unavailable"}) from error
                hidden = getattr(authority, "hidden_job_ids", frozenset())
                if job_id in hidden:
                    # Do not let a direct run-id export bypass Work Log visibility.
                    raise ExportError("diagnostic_hidden")
            job = _lookup(job_id)
            return job is not None, _status_of(job) if job is not None else None
        if run_lookup is not None:
            try:
                authority = run_lookup(record.run_id)
            except Exception as error:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "authority_unavailable"}) from error
            return authority is not None, _status_of(authority) if authority is not None else None
        return False, None

    exporter = DiagnosticsExportService(authority_resolver=_export_authority)

    def _status_of(job: Any) -> str | None:
        if isinstance(job, dict):
            value = job.get("status")
        else:
            value = getattr(job, "status", None)
            value = getattr(value, "value", value)
        return value if isinstance(value, str) else None

    def _lookup(job_id: str) -> Any:
        try:
            return job_lookup(job_id)
        except Exception as error:
            # Existing private cleanup / jobs-store unavailability remains the
            # authority boundary; diagnostic detail cannot bypass it.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "jobs_store_unavailable"}) from error

    def _runtime() -> Any:
        try:
            return runtime_provider()
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "diagnostics_unavailable"}) from error

    def detail(run_id: str) -> dict[str, Any]:
        try:
            valid_id(run_id, "run")
        except DiagnosticValidationError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "invalid_run_id"}) from error
        runtime = _runtime()
        try:
            result = runtime.store.read(run_id)
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "diagnostics_unavailable"}) from error
        if result.availability_reason == "missing_unknown":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "diagnostic_not_found"})
        authority_status: str | None = None
        authority_available = False
        if result.record is not None and result.record.context.job_id is not None:
            job = _lookup(result.record.context.job_id)
            authority_available = job is not None
            authority_status = _status_of(job) if job is not None else None
        elif result.record is not None and run_lookup is not None:
            try:
                authority = run_lookup(run_id)
            except Exception as error:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "authority_unavailable"}) from error
            authority_available = authority is not None
            authority_status = _status_of(authority) if authority is not None else None
        envelope = project_read(
            result,
            run_id=run_id,
            authority_status=authority_status,
            authority_available=authority_available,
            warnings=runtime.store.warning_projection(run_id),
        )
        return envelope

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return detail(run_id)

    def _export_error(error: ExportError) -> HTTPException:
        if error.code == "invalid_run_id":
            return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code})
        if error.code in {"export_options_required", "unknown_export_option", "invalid_export_option", "invalid_preview_token", "preview_token_required"}:
            return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code})
        if error.code == "diagnostic_not_found":
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": error.code})
        if error.code == "diagnostic_hidden":
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "diagnostic_not_found"})
        if error.code in {"export_preview_expired", "export_preview_mismatch"}:
            return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": error.code})
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": error.code})

    def _export_body(body: object, *, download: bool) -> tuple[bool, bool, str | None]:
        try:
            return parse_options(body, download=download)
        except ExportError as error:
            raise _export_error(error) from error

    @router.post("/runs/{run_id}/export-preview")
    @router.post("/runs/{run_id}/export/preview")
    def export_preview(run_id: str, body: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        include_parent, include_children, _ = _export_body(body, download=False)
        try:
            return exporter.preview(
                _runtime().store,
                run_id,
                include_parent=include_parent,
                include_children=include_children,
            )
        except HTTPException:
            raise
        except ExportError as error:
            raise _export_error(error) from error
        except Exception as error:
            # A read/authority failure must not become an empty successful export.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "diagnostics_unavailable"}) from error

    @router.post("/runs/{run_id}/export")
    @router.post("/runs/{run_id}/export/download")
    def export_download(run_id: str, body: dict[str, Any] | None = Body(default=None)) -> Response:
        # Validate before token lookup and before using the id in a filename.
        try:
            valid_id(run_id, "run")
        except DiagnosticValidationError as error:
            raise _export_error(ExportError("invalid_run_id")) from error
        include_parent, include_children, token = _export_body(body, download=True)
        try:
            if token is not None and isinstance(body, dict) and "includeParent" not in body and "includeChildren" not in body:
                include_parent, include_children = exporter.token_options(token)
            payload = exporter.download(
                _runtime().store,
                run_id,
                include_parent=include_parent,
                include_children=include_children,
                token=token,
            )
        except HTTPException:
            raise
        except ExportError as error:
            raise _export_error(error) from error
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "diagnostics_unavailable"}) from error
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="diagnostics-{run_id}.json"'},
        )

    @router.get("/runs")
    def list_runs(request: Request) -> dict[str, Any]:
        # FastAPI's normal query binding ignores unknown keys and keeps the
        # first value of duplicates.  This endpoint is intentionally stricter:
        # a cursor must bind exactly one immutable query shape.
        params = request.query_params
        try:
            if hasattr(params, "multi_items"):
                seen: set[str] = set()
                for key, _value in params.multi_items():
                    if key not in {"version", "limit", "cursor", "feature", "outcome", "fallback", "from", "to"}:
                        raise ListQueryError("unknown_query_parameter")
                    if key in seen:
                        raise ListQueryError("duplicate_query_parameter")
                    seen.add(key)
            query, cursor = parse_list_query(params)
        except ListCursorError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": error.code}) from error
        except ListQueryError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": error.code}) from error

        runtime = _runtime()
        try:
            return runs_list.list(runtime.store, query, cursor)
        except ListCursorError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": error.code}) from error
        except (AuthoritySnapshotUnavailable, ListUnavailable) as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": getattr(error, "code", "diagnostics_unavailable")}) from error
        except Exception as error:
            # A list read must never turn an authority/filesystem failure into
            # an indistinguishable successful empty array.
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "diagnostics_unavailable"}) from error

    @router.get("/jobs/{job_id}")
    def get_job_run(job_id: str) -> dict[str, Any]:
        job = _lookup(job_id)
        if job is None:
            try:
                valid_id(job_id, "job")
            except DiagnosticValidationError as error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "invalid_job_id"}) from error
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "job_not_found"})
        try:
            parsed_id = job.get("id") if isinstance(job, dict) else getattr(job, "id", None)
            run_id = run_id_for_job(parsed_id)
        except (DiagnosticValidationError, AttributeError, ValueError, TypeError):
            return project_read(ReadResult(None, "legacy_no_detail"), run_id=None)
        # A known current job with no diagnostic is a truthful 200 distinction,
        # unlike a caller guessing an arbitrary run ID.
        runtime = _runtime()
        try:
            result = runtime.store.read(run_id)
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "diagnostics_unavailable"}) from error
        return project_read(
            result,
            run_id=run_id,
            authority_status=_status_of(job),
            authority_available=True,
            warnings=runtime.store.warning_projection(run_id),
        )

    return router
