import copy
import datetime as dt
from decimal import Decimal as D
import pytest

from features.decision_readiness.criteria import evaluate, high_premise
from features.price_scenarios.tests.snapshot_fixtures import make

DAY = dt.date(2025, 3, 3)


def ready_snapshot():
    inputs, results = make()
    results["dcf"] = {"status": "available", "marginOfSafetyJudgment": "eligible", "result": {"scenarios": [{"name": "기준", "perShare": "100"}]}}
    for row in results["scenarios"]:
        if row["label"] == "base":
            row["irr"] = ".12"
    return {"snapshotId": "hand-snapshot", "inputs": inputs, "results": results}


def personal(**kwargs):
    return {"revisionId": 1, "requiredReturn": "10", "minMarginOfSafety": "20", "holdingYears": 10, "allowAboveHistoricalRange": None, **kwargs}


def test_unset_partial_and_exact_boundaries():
    snap = ready_snapshot()
    out = evaluate(snap, None, today=DAY)
    assert out["state"] == "unknown"
    assert all(row["state"] == "unknown" for row in out["criteria"].values())
    partial = evaluate(snap, personal(minMarginOfSafety=None), today=DAY)
    assert partial["state"] == "unknown"
    assert partial["criteria"]["requiredReturn"]["state"] == "met"
    snap["inputs"]["price"]["value"] = "80"
    for row in snap["results"]["scenarios"]:
        if row["label"] == "base": row["irr"] = ".10"
    exact = evaluate(snap, personal(), today=DAY)
    assert exact["state"] == "ready_for_review"
    assert exact["criteria"]["minMarginOfSafety"]["margin"] == "0.2000"
    assert exact["scope"] == "price_and_personal_criteria"


def test_unmet_stale_unknown_priority_preserves_all_causes():
    snap = ready_snapshot()
    for row in snap["results"]["scenarios"]:
        if row["label"] == "base": row["irr"] = ".09"
    value = personal(allowAboveHistoricalRange=False, minMarginOfSafety=None)
    out = evaluate(snap, value, today=DAY)
    assert out["state"] == "criteria_unmet"
    assert "minMarginOfSafety_unknown" in out["blockingReasons"]
    assert evaluate(snap, value, today=DAY + dt.timedelta(days=30))["state"] == "criteria_unmet"
    old = evaluate(snap, value, today=DAY + dt.timedelta(days=31))
    assert old["state"] == "stale" and "requiredReturn_unmet" in old["blockingReasons"]
    assert evaluate(snap, value, [{"reason": "restated"}], today=DAY)["state"] == "stale"
    snap["inputs"]["specSha256"] = "not-known"
    assert evaluate(snap, value, today=DAY + dt.timedelta(days=31))["state"] == "unknown"


@pytest.mark.parametrize("status", ["unsupported", "unknown"])
def test_unsupported_never_ready(status):
    snap = ready_snapshot()
    snap["results"]["support"]["status"] = status
    assert evaluate(snap, personal(), today=DAY)["state"] == "unknown"


def test_core_missing_and_no_snapshot_support():
    snap = ready_snapshot()
    snap["results"]["dcf"]["marginOfSafetyJudgment"] = "unknown"
    assert evaluate(snap, personal(), today=DAY)["state"] == "incomplete"
    assert evaluate(None, personal(), today=DAY, support_status="supported")["state"] == "incomplete"
    assert evaluate(None, personal(), today=DAY)["state"] == "unknown"
    assert evaluate(None, personal(), today=DAY, attempt={"reason": {"code": "fund_not_supported"}})["state"] == "unknown"


def range_inputs():
    results = {"ranges": {}}
    for key, values in (("growth", [".02", ".04", ".06", ".08", ".10"]), ("pe", ["10", "15", "20", "25", "30"]), ("netMargin", [".10", ".15", ".20", ".25", ".30"])):
        results["ranges"][key] = {"status": "available", "p75": values[3], "values": [{"value": value} for value in values]}
    needed = {key: {"10": {"status": "available", "value": value}} for key, value in (("growth", ".09"), ("exitPE", "25"), ("netMargin", ".22"))}
    return results, needed


@pytest.mark.parametrize("growth,policy,state", [(".09", False, "met"), (".10", False, "met"), (".11", False, "unmet"), (".11", True, "met"), (".11", None, "unknown")])
def test_maximum_not_p75(growth, policy, state):
    results, needed = range_inputs()
    needed["growth"]["10"]["value"] = growth
    out = high_premise(results, needed, 10, policy)
    assert out["state"] == state
    assert out["axes"]["growth"]["p75"] == ".08"
    assert out["axes"]["growth"]["state"] == ("above_sample" if D(growth) > D(".10") else "within_sample")


def test_partial_unknown_search_bounds_and_not_needed():
    results, needed = range_inputs()
    needed["exitPE"]["10"] = {"status": "available", "state": "not_needed"}
    assert high_premise(results, needed, 10, False)["axes"]["exitPE"]["state"] == "not_needed"
    needed["growth"]["10"] = {"status": "available", "range": "above_range"}
    assert high_premise(results, needed, 10, False)["state"] == "unknown"
    needed["growth"]["10"] = {"status": "available", "value": ".11"}
    results["ranges"]["pe"]["values"] = []
    assert high_premise(results, needed, 10, False)["state"] == "unmet"
    assert high_premise(results, needed, 10, True)["state"] == "unknown"
    before = copy.deepcopy((results, needed))
    high_premise(results, needed, 10, None)
    assert before == (results, needed)


def test_financial_stale_and_rules_inputs_exclude_reason():
    snap = ready_snapshot()
    snap["results"]["dcf"] = {"status": "unavailable", "reason": {"code": "stale_financials"}}
    assert evaluate(snap, personal(), today=DAY)["state"] == "stale"
    import inspect
    parameters = inspect.signature(evaluate).parameters
    assert not {"reason", "reasonStatus", "hasThesis", "reviewedAt", "holdings"} & set(parameters)
