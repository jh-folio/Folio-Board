"""Direct thesis-delta API observation, separate from HTTP routing."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from features.common.jobs import bound_direct_diagnostic, finish_direct_diagnostic


def run_direct_thesis_delta(
    ticker: str,
    body: dict[str, Any],
    *,
    generate: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    with bound_direct_diagnostic(
        feature_code="personal_judgment", route_code="judgment_sql"
    ) as recorder:
        try:
            result = generate(ticker, body)
        except Exception:
            finish_direct_diagnostic(recorder, "failed")
            raise
        finish_direct_diagnostic(recorder, "succeeded")
        return result


__all__ = ("run_direct_thesis_delta",)
