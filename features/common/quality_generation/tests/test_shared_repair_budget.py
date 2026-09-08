from concurrent.futures import ThreadPoolExecutor

import pytest

from features.common.quality_generation import call_budget as module
from features.common.quality_generation.call_budget import SharedRepairBudget
from features.common.quality_generation.llm_section_rewrite import _parse_rewrite_response
from features.common.quality_generation.repair_grounding import preserves_briefing_input


def test_parallel_stages_share_one_slot():
    budget = SharedRepairBudget(9)
    def claim(stage):
        try:
            budget.claim(stage)
            return True
        except RuntimeError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(claim, ["quality", "structure", "concentration", "briefing_finalization"]))
    assert sum(accepted) == 1
    assert budget.snapshot()["used"] == 1


def test_repairs_cannot_add_new_assertions_or_numbers():
    original = "# Report\n\nNVDA fell 2%.\nInvestors watched yields."
    assert preserves_briefing_input(original, "# Report\nNVDA fell 2%.")
    assert not preserves_briefing_input(original, "NVDA rose 2%.")
    assert not preserves_briefing_input(original, "NVDA fell 20%.")
    assert not preserves_briefing_input(original, "NVDA fell 2% because liquidity vanished.")


def test_original_deadline_is_not_reset_after_claim(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    budget = SharedRepairBudget(deadline=20)
    budget.claim("quality")
    assert budget.remaining_seconds() == 10
    now[0] = 21
    with pytest.raises(TimeoutError, match="deadline_expired"):
        budget.check_active()


@pytest.mark.parametrize("deadline", [float("nan"), float("inf")])
def test_invalid_deadline_rejected(deadline):
    with pytest.raises(ValueError):
        SharedRepairBudget(deadline=deadline)


def test_cancellation_observed_after_repair():
    state = [False]
    budget = SharedRepairBudget(cancelled=lambda: state[0])
    budget.claim("quality")
    state[0] = True
    with pytest.raises(RuntimeError, match="cancelled"):
        budget.check_active()


def test_unreadable_cancellation_does_not_authorize_repair():
    budget = SharedRepairBudget(cancelled=object())
    with pytest.raises(RuntimeError, match="cancelled"):
        budget.claim("quality")


def test_private_stage_name_is_not_recorded():
    budget = SharedRepairBudget()
    budget.claim("secret prompt https://private.invalid")
    assert budget.snapshot()["claims"] == ["briefing_finalization"]


def test_briefing_parse_failure_cannot_spend_another_model_call(monkeypatch):
    from features.common.quality_generation import llm_section_rewrite as rewrite
    def forbidden(*args, **kwargs):
        pytest.fail("second repair call")
    monkeypatch.setattr(rewrite, "request_llm_text", forbidden)
    with pytest.raises(ValueError, match="rewrite_json_invalid"):
        _parse_rewrite_response({}, "invalid response", max_tokens=100, allow_repair=False)


def test_quality_rewrite_uses_shared_deadline_and_no_nested_retry(monkeypatch):
    from features.common.quality_generation import llm_section_rewrite as rewrite
    now = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(rewrite, "selected_llm_config", lambda: {"enabled": True, "apiKey": "test", "provider": "test"})
    monkeypatch.setattr(rewrite, "_rewrite_context", lambda *args: "synthetic")
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs)
        return "invalid response", "", {}
    monkeypatch.setattr(rewrite, "request_llm_text", request)
    budget = SharedRepairBudget(deadline=20)
    artifact = {"markdown": "original", "generation": {"mode": "llm"}}
    out = rewrite.improve_sections_with_llm("briefing", artifact, {}, {}, [], mode="strict", repair_budget=budget)
    assert out["artifact"] == artifact
    assert not out["repairApplied"]
    assert len(calls) == 1 and calls[0]["timeout_seconds"] == 10
    out = rewrite.improve_sections_with_llm("briefing", artifact, {}, {}, [], mode="strict", repair_budget=budget)
    assert out["repairReason"] == "shared_repair_budget_exhausted"
    assert len(calls) == 1


def test_expired_rewrite_result_cannot_be_accepted(monkeypatch):
    from features.common.quality_generation import llm_section_rewrite as rewrite
    now = [10.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(rewrite, "selected_llm_config", lambda: {"enabled": True, "apiKey": "test", "provider": "test"})
    monkeypatch.setattr(rewrite, "_rewrite_context", lambda *args: "synthetic")
    def request(*args, **kwargs):
        now[0] = 21
        return '{"markdown":"valid"}', "", {}
    monkeypatch.setattr(rewrite, "request_llm_text", request)
    with pytest.raises(TimeoutError, match="deadline_expired"):
        rewrite.improve_sections_with_llm("briefing", {"generation": {"mode": "llm"}}, {}, {}, [], mode="strict", repair_budget=SharedRepairBudget(deadline=20))
