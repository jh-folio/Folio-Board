"""Feature-owned diagnostics for the direct briefing API path."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from features.common.jobs import (
    bound_direct_diagnostic,
    diagnostic_stage_end,
    diagnostic_stage_failure,
    diagnostic_stage_start,
    finish_direct_diagnostic,
)


def run_direct_briefings(
    *,
    wants_prerequisites: bool,
    run_prerequisites: Callable[[], dict[str, Any]],
    build: Callable[..., dict[str, Any]],
    build_requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build direct reports while preserving their existing return authority."""
    with bound_direct_diagnostic(
        feature_code="briefing", route_code="report_api"
    ) as recorder:
        prerequisites: dict[str, Any] = {}
        if wants_prerequisites:
            stage_recorder, stage_id = diagnostic_stage_start("preflight")
            try:
                prerequisites = run_prerequisites()
            except Exception as error:
                diagnostic_stage_failure(
                    stage_recorder,
                    error,
                    stage_id=stage_id,
                    stage_code="preflight" if stage_id is not None else None,
                    boundary="generic",
                )
                # Prerequisite collection is historically best-effort.  Keep
                # building, and let the returned report remain authoritative.
                prerequisites = {}
            diagnostic_stage_end(stage_recorder, stage_id, "preflight")
        try:
            reports = [build(**request) for request in build_requests]
        except Exception as error:
            diagnostic_stage_failure(
                None if recorder is None else recorder,
                error,
                stage_id=None,
                stage_code="generate",
                boundary="generic",
                terminal=True,
            )
            finish_direct_diagnostic(recorder, "failed")
            raise
        finish_direct_diagnostic(recorder, "succeeded")
        return reports, prerequisites


__all__ = ("run_direct_briefings",)
