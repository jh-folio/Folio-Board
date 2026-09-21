"""Direct market-memory API observation."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from features.common.jobs import (
    bound_direct_diagnostic,
    diagnostic_execution,
    diagnostic_stage_end,
    diagnostic_stage_failure,
    diagnostic_stage_start,
    finish_direct_diagnostic,
)


def run_direct_market_memory(date: str, *, generate: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    with bound_direct_diagnostic(
        feature_code="personal_judgment", route_code="judgment_sql"
    ) as recorder:
        stage_recorder, stage_id = diagnostic_stage_start("generate")
        try:
            result = generate(date)
        except Exception as error:
            diagnostic_stage_failure(
                stage_recorder, error, stage_id=stage_id,
                stage_code="generate" if stage_id is not None else None,
                boundary="generic", terminal=True,
            )
            diagnostic_stage_end(stage_recorder, stage_id, "generate")
            finish_direct_diagnostic(recorder, "failed")
            raise
        diagnostic_stage_end(stage_recorder, stage_id, "generate")
        if result.get("ok") is True:
            diagnostic_execution(attempted_engine="cli", final_engine="cli")
            finish_direct_diagnostic(recorder, "succeeded")
        else:
            status = str(result.get("status") or "")
            # Missing configuration/prompt performed no provider attempt and
            # did not manufacture a rules artifact.  A returned generation
            # failure, by contrast, is the existing CLI-to-rules fallback.
            if status.startswith("missing_") or status == "cli_disabled":
                diagnostic_execution(final_engine="none")
            else:
                diagnostic_execution(
                    attempted_engine="cli", final_engine="rules", fallback_reason="engine_failed"
                )
            finish_direct_diagnostic(recorder, "unknown")
        return result


__all__ = ("run_direct_market_memory",)
