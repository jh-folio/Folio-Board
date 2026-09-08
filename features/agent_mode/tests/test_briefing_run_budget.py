import pytest

from features.agent_mode import bridge
from features.common.quality_generation import call_budget
from features.common.quality_generation.call_budget import SharedRepairBudget, bind_briefing_budget, current_briefing_budget
from features.daily_briefing.builder import generate_scope_results


def test_api_market_workers_receive_same_budget_object():
    budget = SharedRepairBudget()
    with bind_briefing_budget(budget):
        results, warnings = generate_scope_results(["us", "kr"], lambda scope: current_briefing_budget())
    assert not warnings
    assert results["us"] is results["kr"] is budget
    assert current_briefing_budget() is None


def test_nested_cli_wait_cannot_exceed_original_deadline(monkeypatch):
    monkeypatch.setattr(call_budget.time, "monotonic", lambda: 10.0)
    timeouts = []
    class BusySemaphore:
        def acquire(self, **kwargs):
            timeouts.append(kwargs["timeout"])
            return False
        def release(self):
            pytest.fail("unowned semaphore release")
    monkeypatch.setattr(bridge, "_RUN_SEMAPHORE", BusySemaphore())
    with bind_briefing_budget(SharedRepairBudget(deadline=20)), pytest.raises(TimeoutError, match="deadline_expired"):
        bridge.run_agent_prompt("synthetic", serialize=True)
    assert timeouts == [10.0]
