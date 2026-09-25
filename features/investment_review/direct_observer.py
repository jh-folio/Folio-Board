"""Direct investment-review API observation."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from features.common.jobs import bound_direct_diagnostic, diagnostic_execution, finish_direct_diagnostic


def run_direct_review(body: dict[str, Any], *, generate: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    with bound_direct_diagnostic(
        feature_code="personal_judgment", route_code="judgment_json"
    ) as recorder:
        try:
            result = generate(body)
        except Exception:
            finish_direct_diagnostic(recorder, "failed")
            raise
        # Investment Review v2 is deterministic; this direct route performs
        # no provider call even when its authoritative JSON candidate saves.
        diagnostic_execution(final_engine="rules")
        finish_direct_diagnostic(recorder, "succeeded")
        return result


__all__ = ("run_direct_review",)
