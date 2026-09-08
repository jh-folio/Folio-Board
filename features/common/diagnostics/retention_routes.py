"""Closed HTTP boundary for diagnostic retention settings and cleanup.

The router is intentionally separate from the normal diagnostic read/list
router.  Retention is the only diagnostic surface that can mutate a file, so
all mutating calls require a short-lived preview token and an explicit
``confirm: true`` value.  The route translates only stable retention error
codes; filesystem/provider details never cross the HTTP boundary.
"""
from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status

from .retention import (
    DiagnosticsRetentionService,
    RetentionConflict,
    RetentionError,
    RetentionUnavailable,
    RetentionValidationError,
)


def create_retention_router(
    *,
    runtime_provider: Callable[[], Any],
    authority_provider: Callable[[], Any] | None = None,
    service_provider: Callable[[Any], DiagnosticsRetentionService] | None = None,
) -> APIRouter:
    """Build the injectable ``/api/diagnostics/retention`` router.

    Services are cached per runtime store so a preview token survives the
    separate HTTP request used for confirmation, while a changed data root
    receives a fresh token registry.  ``service_provider`` exists for tests
    and hosts that already own a retention service; production may use the
    default constructor.
    """

    router = APIRouter(prefix="/api/diagnostics/retention", tags=["diagnostics-retention"])
    cache_lock = threading.RLock()
    cached_store: Any = None
    cached_service: DiagnosticsRetentionService | None = None

    def _runtime() -> Any:
        try:
            return runtime_provider()
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "diagnostics_unavailable"},
            ) from error

    def _service() -> DiagnosticsRetentionService:
        nonlocal cached_store, cached_service
        runtime = _runtime()
        store = getattr(runtime, "store", None)
        if store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "diagnostics_unavailable"},
            )
        with cache_lock:
            if cached_store is not store or cached_service is None:
                try:
                    cached_service = (
                        service_provider(runtime)
                        if service_provider is not None
                        else DiagnosticsRetentionService(
                            store,
                            authority_provider=authority_provider,
                        )
                    )
                except RetentionError as error:
                    raise _retention_error(error) from error
                cached_store = store
            return cached_service

    def _retention_error(error: RetentionError) -> HTTPException:
        if isinstance(error, RetentionValidationError):
            code = error.code
            code_status = status.HTTP_422_UNPROCESSABLE_CONTENT
        elif isinstance(error, RetentionConflict):
            code = error.code
            code_status = status.HTTP_409_CONFLICT
        elif isinstance(error, RetentionUnavailable):
            code = error.code
            code_status = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            code = error.code
            code_status = status.HTTP_503_SERVICE_UNAVAILABLE
        return HTTPException(status_code=code_status, detail={"code": code})

    def _call(function: Callable[[], dict[str, object]]) -> dict[str, object]:
        try:
            return function()
        except HTTPException:
            raise
        except RetentionError as error:
            raise _retention_error(error) from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "diagnostics_unavailable"},
            ) from error

    def _object_body(body: object, keys: set[str]) -> dict[str, object]:
        if type(body) is not dict or set(body) != keys:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_retention_request"},
            )
        return body

    @router.get("")
    def get_status() -> dict[str, object]:
        return _call(lambda: _service().usage_status())

    @router.post("/preview")
    def preview(body: object = Body(default=None)) -> dict[str, object]:
        payload = _object_body(body, {"retentionDays"})
        return _call(lambda: _service().preview(payload["retentionDays"]))

    @router.post("/confirm")
    def confirm(body: object = Body(default=None)) -> dict[str, object]:
        payload = _object_body(body, {"previewToken", "confirm"})
        return _call(
            lambda: _service().confirm(
                payload["previewToken"],
                confirm=payload["confirm"] is True,
            )
        )

    @router.post("/settings/preview")
    def settings_preview(body: object = Body(default=None)) -> dict[str, object]:
        payload = _object_body(body, {"retentionDays", "autoDelete"})
        return _call(
            lambda: _service().settings_preview(
                payload["retentionDays"],
                payload["autoDelete"],
            )
        )

    @router.post("/settings/confirm")
    def settings_confirm(body: object = Body(default=None)) -> dict[str, object]:
        payload = _object_body(body, {"previewToken", "confirm"})
        return _call(
            lambda: _service().settings_confirm(
                payload["previewToken"],
                confirm=payload["confirm"] is True,
            )
        )

    return router


__all__ = ["create_retention_router"]
