"""Derived EPS eligibility, split basis, source round-trip and exact thresholds."""
from copy import deepcopy
from decimal import Decimal
import pytest

from features.price_scenarios.coverage_history import derive_missing_eps, same_filing_pair
from features.price_scenarios.events import adjust_history
from features.price_scenarios.sec_events import _observations
from .test_scenario_results import steady


def raw_history():
    h, _ = steady(range(2016, 2026), growth=Decimal(1))
    for row in h["rows"]:
        row.update(form="10-K", filed=f"{row['fiscalYear'] + 1}-02-01", accession=f"acc-{row['fiscalYear']}",
                   concept="us-gaap:"+row["metric"], unit="shares" if row["metric"] == "Shares Diluted" else
                   "USD/shares" if row["metric"] in {"EPS Diluted", "DPS"} else "USD", precision=2, priorValues=[])
    return h


def missing(h, *years):
    h["rows"] = [r for r in h["rows"] if not (r["metric"] == "EPS Diluted" and r["fiscalYear"] in years)]
    return h


def derived(h):
    return [r for r in h["rows"] if r.get("derived")]


def test_explicit_income_scope_or_share_class_mismatch_is_not_derived():
    for metric, field, value in [('Net Income', 'scope', 'parent_only'), ('Shares Diluted', 'classBasis', 'B')]:
        h = missing(raw_history(), 2020)
        for row in h['rows']:
            if row['metric'] == metric:
                row[field] = value
        assert derived(derive_missing_eps(h)) == []


@pytest.mark.parametrize("gaps,expected", [((2020,), [2020]), ((2019, 2020), [2019, 2020]),
                                          ((2018, 2019, 2020), []), ((2025,), [])])
def test_maximum_two_past_gaps_and_base_exclusion(gaps, expected):
    original = missing(raw_history(), *gaps)
    saved = deepcopy(original)
    out = derive_missing_eps(original)
    assert [r["fiscalYear"] for r in derived(out)] == expected
    assert original == saved
    assert derive_missing_eps(out) == out


@pytest.mark.parametrize("income,expected", [("102.9", True), ("103", True), ("103.1", False), ("103.000001", False)])
def test_three_percent_boundary_before_rounding(income, expected):
    h = missing(raw_history(), 2020)
    for r in h["rows"]:
        if r["metric"] == "Net Income" and r["fiscalYear"] == 2025:
            r["value"] = income
    assert bool(derived(derive_missing_eps(h))) is expected


def test_minimum_three_recent_positive_same_filing_pairs():
    h = missing(raw_history(), 2020)
    for r in h["rows"]:
        if r["metric"] == "Shares Diluted" and r["fiscalYear"] < 2024:
            r["accession"] = "other"
    assert not derived(derive_missing_eps(h))
    for r in h["rows"]:
        if r["metric"] == "Shares Diluted" and r["fiscalYear"] == 2023:
            r["accession"] = "acc-2023"
    out = derive_missing_eps(h)
    assert len(derived(out)) == 1 and len(derived(out)[0]["validation"]["years"]) == 3


def test_period_and_units_are_required_and_latest_matching_prior_pair_is_used():
    h = missing(raw_history(), 2020)
    for r in h["rows"]:
        if r["metric"] == "Shares Diluted" and r["fiscalYear"] == 2020:
            r["period"]["start"] = "2020-02-01"
    assert not derived(derive_missing_eps(h))
    h = raw_history()
    e = next(r for r in h["rows"] if r["metric"] == "EPS Diluted")
    s = next(r for r in h["rows"] if r["metric"] == "Shares Diluted")
    e["priorValues"] = [{"filed": s["filed"], "accession": s["accession"], "value": "1", "form": "10-K"}]
    e.update(filed="2025-02-01", accession="new", value="0.1")
    assert same_filing_pair(e, s)[0]["value"] == "1"


def test_derived_value_uses_shares_filing_split_basis_but_is_not_split_evidence():
    h = missing(raw_history(), 2020)
    out = derive_missing_eps(h)
    row = derived(out)[0]
    assert row["filed"] == "2021-02-01" and row["accession"] == "acc-2020"
    assert row["precision"] == 2 and row["value"] == "1.00"
    assert {r["metric"] for r in row["sourceRows"]} == {"Shares Diluted", "Net Income"}
    assert _observations(out) == _observations(h)
    adjusted = adjust_history(out, [{"eventDate": "2021-06-01", "ratio": "10", "kind": "split"}],
                              state="present", session_date="2026-10-01")
    assert derived(adjusted)[0]["value"] == "0.10"
    assert not derived(derive_missing_eps(h, listed_class_pending=True))
