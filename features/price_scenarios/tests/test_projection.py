import copy
import datetime as dt
import hashlib

import pytest

from features.price_scenarios.projection import project
from features.price_scenarios.returns import scenario_irr
from features.price_scenarios.store import PriceStore

from .snapshot_fixtures import make

TODAY = dt.date(2025, 3, 10)


def snapshot(results_patch=None, **kwargs):
    inputs, results = make(results_patch=results_patch, **kwargs)
    return {"snapshotId": "price-test", "inputs": inputs, "results": results}


def criteria(required=None, margin=None, years=10, revision=1):
    return {"revisionId": revision, "requiredReturn": required, "minMarginOfSafety": margin, "holdingYears": years}


def base_irr(snap, years):
    return float(next(r for r in snap["results"]["scenarios"] if r["label"] == "base" and r["horizon"] == years)["irr"])


def dcf_block(per_share="100", judgement="eligible"):
    return {"status": "available", "marginOfSafetyJudgment": judgement,
            "result": {"scenarios": [{"name": "보수", "perShare": "70"}, {"name": "기준", "perShare": per_share}, {"name": "낙관", "perShare": "130"}]}}


def test_without_criteria_every_judgement_is_unknown_not_met():
    out = project(snapshot(), None, None, (), today=TODAY)
    assert out["verdict"]["return"] == {"state": "unknown", "reason": "criteria_not_set"}
    assert out["verdict"]["marginOfSafety"] == {"state": "unknown", "reason": "criteria_not_set"}
    assert out["requirement"]["status"] == "unavailable" and out["myAssumptions"] is None and out["criteria"] is None
    blank = project(snapshot(), criteria(), None, (), today=TODAY)  # a saved revision with nothing set
    assert blank["verdict"]["return"]["reason"] == "criteria_not_set"


def test_return_judgement_uses_the_base_scenario_of_the_chosen_holding_period():
    snap = snapshot()
    ten, five = base_irr(snap, 10), base_irr(snap, 5)
    below, above = str(round(ten * 100 - 1, 2)), str(round(ten * 100 + 1, 2))
    assert project(snap, criteria(below), None, (), today=TODAY)["verdict"]["return"] == {"state": "met", "horizon": 10, "irr": f"{ten:.4f}"}
    assert project(snap, criteria(above), None, (), today=TODAY)["verdict"]["return"]["state"] == "unmet"
    switched = project(snap, criteria(str(round(five * 100 + 1, 2)), years=5), None, (), today=TODAY)["verdict"]["return"]
    assert (switched["state"], switched["horizon"]) == ("unmet", 5)
    equal = project(snap, criteria(f"{ten * 100:.2f}"), None, (), today=TODAY)["verdict"]["return"]
    assert equal["state"] == "met"  # equal to the stored (rounded) return counts as met


def test_out_of_range_returns_and_unavailable_scenarios():
    snap = snapshot()
    for row in snap["results"]["scenarios"]:
        if row["label"] == "base" and row["horizon"] == 10:
            row.update(irr=None, irrRange="above_range")
    assert project(snap, criteria("100"), None, (), today=TODAY)["verdict"]["return"]["state"] == "met"
    for row in snap["results"]["scenarios"]:
        if row["label"] == "base" and row["horizon"] == 10:
            row.update(irrRange="below_range")
    assert project(snap, criteria("-99"), None, (), today=TODAY)["verdict"]["return"]["state"] == "unmet"
    gone = snapshot()
    gone["results"]["scenarios"] = [dict(row, status="unavailable", reason={"code": "history_too_short"}) if row["horizon"] == 10 else row
                                    for row in gone["results"]["scenarios"]]
    out = project(gone, criteria("6"), None, (), today=TODAY)["verdict"]["return"]
    assert (out["state"], out["reason"]) == ("unknown", "history_too_short")


def test_margin_of_safety_judgement():
    snap = snapshot(results_patch={"dcf": dcf_block("100")})  # price 30 vs intrinsic 100 -> 70%
    assert project(snap, criteria(margin="20"), None, (), today=TODAY)["verdict"]["marginOfSafety"] == {
        "state": "met", "intrinsicValue": "100.00", "margin": "0.7000"}
    assert project(snap, criteria(margin="70"), None, (), today=TODAY)["verdict"]["marginOfSafety"]["state"] == "met"  # equal is met
    assert project(snap, criteria(margin="71"), None, (), today=TODAY)["verdict"]["marginOfSafety"]["state"] == "unmet"
    cases = (({"dcf": dcf_block("100", "unknown")}, "dcf_fallback"), ({"dcf": dcf_block("-5")}, "non_positive_intrinsic_value"),
             ({"dcf": {"status": "unavailable", "reason": {"code": "dcf_not_computable"}}}, "dcf_not_computable"), ({}, "dcf_unavailable"))
    for patch, reason in cases:
        verdict = project(snapshot(results_patch=patch), criteria(margin="10"), None, (), today=TODAY)["verdict"]["marginOfSafety"]
        assert (verdict["state"], verdict["reason"]) == ("unknown", reason), patch


def test_requirement_inversions_round_trip_through_the_scenario_math():
    snap = snapshot()
    out = project(snap, criteria("8"), None, (), today=TODAY)["requirement"]
    row = next(r for r in snap["results"]["scenarios"] if r["label"] == "base" and r["horizon"] == 10)
    eps0, price = snap["results"]["base"]["eps0"], snap["inputs"]["price"]["value"]
    need_pe = out["exitPE"]["10"]
    assert need_pe["state"] == "needed"
    assert float(scenario_irr(price, eps0, row["g"], need_pe["value"], row["payout"], 10)) == pytest.approx(0.08, abs=2e-3)
    need_g = out["growth"]["10"]
    assert float(scenario_irr(price, eps0, need_g["value"], row["exitPE"], row["payout"], 10)) == pytest.approx(0.08, abs=1e-3)
    assert need_g["percentile"] is not None
    margin = out["netMargin"]["10"]
    assert margin["status"] == "available" and "currentMargin" in margin
    zero = project(snap, criteria("0"), None, (), today=TODAY)["requirement"]["exitPE"]["10"]
    stored = snap["results"]["reverse"]["breakEvenPE"]["10"]
    assert (zero["state"], zero.get("value")) == (stored["state"], stored.get("exitPE"))  # 0% matches the stored 0% inversion


def test_my_assumptions_give_returns_and_never_a_judgement():
    snap = snapshot()
    override = {"overrideId": 3, "instrumentId": "US:ACME", "basedOnSnapshotId": "price-test", "growth": "0.2", "exitPE": None, "payout": "0"}
    out = project(snap, criteria("6"), override, (), today=TODAY)["myAssumptions"]
    assert out["basedOnCurrentSnapshot"] is True and "verdict" not in out and "state" not in out
    ten = next(row for row in out["rows"] if row["horizon"] == 10)
    base = next(r for r in snap["results"]["scenarios"] if r["label"] == "base" and r["horizon"] == 10)
    assert (ten["g"], ten["payout"], ten["exitPE"], ten["inherited"]) == ("0.2000", "0.0000", base["exitPE"], {"g": False, "exitPE": True, "payout": False})
    assert float(ten["irr"]) > float(base["irr"])
    old = project(snap, None, {**override, "basedOnSnapshotId": "price-earlier"}, (), today=TODAY)["myAssumptions"]
    assert old["basedOnCurrentSnapshot"] is False and old["basedOnSnapshotId"] == "price-earlier"
    blank = project(snap, None, {**override, "growth": None, "payout": None}, (), today=TODAY)["myAssumptions"]
    assert float(next(r for r in blank["rows"] if r["horizon"] == 10)["irr"]) == pytest.approx(float(base["irr"]), abs=1e-4)


def test_age_notice_review_flags_and_no_mutation():
    snap = snapshot()
    frozen = copy.deepcopy(snap)
    review = [{"reason": "restated", "metric": "EPS Diluted", "fiscalYear": 2024, "detectedBySnapshotId": "price-new"}]
    assert project(snap, None, None, (), today=dt.date(2025, 4, 2))["notices"] == []          # 30 days old
    old = project(snap, None, None, review, today=dt.date(2025, 4, 3))                         # 31 days old
    assert old["notices"] == ["snapshot_old"] and old["ageDays"] == 31 and old["reviewNeeded"] == review
    assert snap == frozen


def test_projection_reads_a_stored_snapshot_without_touching_the_database(tmp_path):
    store = PriceStore(tmp_path / "market-memory.sqlite3")
    inputs, results = make()
    saved = store.save_snapshot(inputs, results)
    store.save_criteria(required_return="6", min_margin_of_safety="10", holding_years=10)
    digest = lambda: hashlib.sha256(store.path.read_bytes()).hexdigest()
    before = digest()
    loaded = store.get(saved["snapshotId"])
    out = project(loaded, store.criteria(), store.override("US:ACME"), store.reviews(saved["snapshotId"]), today=TODAY)
    assert out["verdict"]["return"]["state"] in {"met", "unmet"} and out["criteria"]["revisionId"] == 1
    assert digest() == before
    # a different criteria revision changes the judgement but never the stored snapshot
    store.save_criteria(required_return="99", holding_years=10, expected_revision_id=1)
    assert project(loaded, store.criteria(), None, (), today=TODAY)["verdict"]["return"]["state"] == "unmet"
    assert store.get(saved["snapshotId"]) == loaded


def test_an_assumption_far_beyond_the_search_range_is_a_range_state_not_an_error():
    huge = "9" * 30  # the longest growth the store accepts
    assert scenario_irr("100", "5", huge, "15", "0.3", 10) == "above_range"
    assert scenario_irr("100", "5", "1e99999", "15", "0.3", 10) == "above_range"
