from __future__ import annotations

import pytest

from features.common.quality_generation.call_budget import deep_research_budget, kr_briefing_budget


def test_deep_budget_has_one_initial_and_two_repairs() -> None:
    budget = deep_research_budget()
    budget.claim("initial")
    budget.claim("repair")
    budget.claim("repair")
    with pytest.raises(RuntimeError, match="call_budget_exhausted:repair"):
        budget.claim("repair")


def test_kr_budget_has_three_distinct_non_retrying_slots() -> None:
    budget = kr_briefing_budget()
    for slot in ("adjudication", "generation", "repair"):
        budget.claim(slot)
        with pytest.raises(RuntimeError):
            budget.claim(slot)
