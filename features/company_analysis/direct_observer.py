"""Feature-owned observation for the direct company-analysis API path.

The API keeps its historic report-return behaviour: diagnostics describe what
happened but are never proof that a report was durably saved.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError
from typing import Any

from features.common.jobs import (
    bound_direct_diagnostic,
    diagnostic_stage_end,
    diagnostic_stage_failure,
    diagnostic_execution,
    diagnostic_stage_start,
    finish_direct_diagnostic,
)
from features.company_analysis.finalize import preserve_unassessed_warning


def run_direct_analysis(
    *,
    query: str,
    web_search_override: bool | None,
    llm_override: Callable[..., Any] | None,
    analysis_style: str,
    quality_mode: str,
    generate: Callable[..., dict[str, Any]],
    apply_quality: Callable[..., dict[str, Any]],
    apply_ceiling: Callable[[dict[str, Any]], dict[str, Any]],
    save: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Run the established direct path with bounded diagnostic observation."""
    with bound_direct_diagnostic(
        feature_code="company_analysis", route_code="report_api"
    ) as recorder:
        generate_recorder, generate_stage = diagnostic_stage_start("generate")
        try:
            report = generate(
                query,
                web_search_override=web_search_override,
                llm_override=llm_override,
                analysis_style=analysis_style,
            )
        except (KeyboardInterrupt, SystemExit, CancelledError) as error:
            diagnostic_stage_failure(
                generate_recorder,
                error,
                stage_id=generate_stage,
                stage_code="generate" if generate_stage is not None else None,
                boundary="generic",
                terminal=True,
            )
            diagnostic_stage_end(generate_recorder, generate_stage, "generate")
            finish_direct_diagnostic(recorder, "failed")
            raise
        except Exception as error:
            diagnostic_stage_failure(
                generate_recorder,
                error,
                stage_id=generate_stage,
                stage_code="generate" if generate_stage is not None else None,
                boundary="generic",
                terminal=True,
            )
            diagnostic_stage_end(generate_recorder, generate_stage, "generate")
            finish_direct_diagnostic(recorder, "failed")
            raise
        diagnostic_stage_end(generate_recorder, generate_stage, "generate")
        generation = report.get("generation") if isinstance(report, dict) else None
        if isinstance(generation, dict):
            mode = generation.get("mode")
            status = generation.get("status")
            if mode == "llm":
                diagnostic_execution(attempted_engine="api", final_engine="api")
            elif mode == "rules":
                diagnostic_execution(
                    attempted_engine="api" if status == "generation_failed" else None,
                    final_engine="rules",
                    fallback_reason="engine_failed" if status == "generation_failed" else None,
                )

        validate_recorder, validate_stage = diagnostic_stage_start("validate")
        try:
            preflight = report.pop("qualityPreflight", None)
            report = apply_quality(
                "company_analysis", report, mode=quality_mode, preflight=preflight
            )
            report = apply_ceiling(report)
            report = preserve_unassessed_warning(report)
        except (KeyboardInterrupt, SystemExit, CancelledError) as error:
            diagnostic_stage_failure(
                validate_recorder,
                error,
                stage_id=validate_stage,
                stage_code="validate" if validate_stage is not None else None,
                boundary="validation",
                terminal=True,
            )
            diagnostic_stage_end(validate_recorder, validate_stage, "validate")
            finish_direct_diagnostic(recorder, "failed")
            raise
        except Exception as error:
            # Historic direct behaviour is a generated report with a warning.
            diagnostic_stage_failure(
                validate_recorder,
                error,
                stage_id=validate_stage,
                stage_code="validate" if validate_stage is not None else None,
                boundary="validation",
            )
            report["quality"] = {
                "status": "warn",
                "warnings": ["quality evaluation failed"],
            }
            report = preserve_unassessed_warning(report)
        diagnostic_stage_end(validate_recorder, validate_stage, "validate")

        commit_recorder, commit_stage = diagnostic_stage_start("commit")
        try:
            saved = save(report)
            persisted = isinstance(saved, dict) and saved.get("saved") is True
            if isinstance(saved, dict):
                # The storage boundary owns the durable truth.  A test seam or
                # legacy writer that omits `saved` is not evidence of a commit;
                # the reader can still display the returned candidate.
                saved = dict(saved)
                if not persisted:
                    saved["saved"] = False
        except (KeyboardInterrupt, SystemExit, CancelledError) as error:
            diagnostic_stage_failure(
                commit_recorder,
                error,
                stage_id=commit_stage,
                stage_code="commit" if commit_stage is not None else None,
                boundary="save",
                terminal=True,
            )
            diagnostic_stage_end(commit_recorder, commit_stage, "commit")
            finish_direct_diagnostic(recorder, "unknown")
            raise
        except Exception as error:
            # Returning the unsaved report is the legacy contract; terminal
            # diagnostics deliberately remain non-successful.
            diagnostic_stage_failure(
                commit_recorder,
                error,
                stage_id=commit_stage,
                stage_code="commit" if commit_stage is not None else None,
                boundary="save",
                terminal=True,
            )
            diagnostic_stage_end(commit_recorder, commit_stage, "commit")
            finish_direct_diagnostic(recorder, "unknown")
            unsaved = dict(report)
            unsaved["saved"] = False
            unsaved["saveError"] = {
                "code": "save_failed",
                "message": "보고서를 저장하지 못했습니다.",
            }
            return unsaved
        diagnostic_stage_end(commit_recorder, commit_stage, "commit")
        finish_direct_diagnostic(recorder, "succeeded" if persisted else "unknown")
        return saved


__all__ = ("run_direct_analysis",)
