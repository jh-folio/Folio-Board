from copy import deepcopy
from decimal import Decimal

import pytest

from features.price_scenarios import METHOD_VERSION, SPEC_VERSION, SPEC_SHA256
from features.price_scenarios.decimal_ops import canonical, fingerprint
from features.price_scenarios.events import reconcile_korean_shares, reconcile_korean_shares_v1
from features.price_scenarios.korean_shares import dart_observation


def proof(**extra):
    return {"source": "dart_report", "accession": "official", "filed": "2019-04-01",
            "locator": "주식의 총수 등; 보통주", "statement": "confirmed common share denomination", **extra}


def observation(end, shares, cancellation="0", redemption="0", *, unit_date=None):
    return {"periodEnd": end, "shares": shares, "source": {"provider": "dart", "accession": end, "locator": "istc_totqy"},
            "decreases": {key: {"value": value, "unitDate": unit_date or end, "unitProof": proof()}
                          for key, value in (("profitCancellation", cancellation), ("redemption", redemption))}}


def event(day="2018-05-03", ratio="50", **extra):
    return {"eventDate": "2018-05-04", "shareDate": day, "kind": "split", "ratio": ratio, **extra}


def calculate(previous, current, events=None, changes=None, coverage=None):
    return reconcile_korean_shares(previous, current, events or [], changes or [],
                                  coverage=coverage or {"state": "confirmed", "start": "2017-01-01", "end": "2018-12-31"},
                                  as_of="2026-10-01")


def test_samsung_denominations_use_raw_cumulative_values_with_proofs_not_a_raw_difference():
    previous = observation("2017-12-31", "129098494", "26510843")
    current = observation("2018-12-31", "5969782550", "1810684300")
    original = deepcopy((previous, current))
    result = calculate(previous, current, [event()])
    assert result["state"] == "matched" and result["residual"] == "0"
    assert result["decreaseEnd"] == "485142150"
    assert (previous, current) == original
    # The real source's redemption '-' is missing, unlike the synthetic zero.
    current["decreases"]["redemption"]["value"] = None
    assert calculate(previous, current, [event()])["reason"] == "cumulative_unit_unconfirmed"
    old = [{"periodEnd": row["periodEnd"], "shares": row["shares"],
            "decreaseCumulative": row["decreases"]["profitCancellation"]["value"]} for row in original]
    assert reconcile_korean_shares_v1(*old, [event()], [])["state"] == "unknown"


@pytest.mark.parametrize("phase,expected,decrease", [("pre_event", "matched", "20"),
                                                   ("post_event", "unknown", "0"), (None, "unknown", None)])
def test_same_day_cumulative_unit_requires_official_pre_or_post_evidence(phase, expected, decrease):
    previous = observation("2017-12-31", "100", "10")
    current = observation("2018-12-31", "180", "20")
    current["decreases"]["profitCancellation"]["unitDate"] = "2018-05-03"
    if phase:
        current["decreases"]["profitCancellation"]["unitProof"]["sameDayBasis"] = phase
    result = calculate(previous, current, [event(ratio="2")])
    assert result["state"] == expected
    if decrease is not None:
        assert result["decreaseEnd"] == decrease
    else:
        assert result["reason"] == "cumulative_unit_unconfirmed"


def test_cancellations_and_redemptions_keep_independent_denominations():
    previous = observation("2017-12-31", "100", "10", "5")
    current = observation("2018-12-31", "150", "40", "20")
    current["decreases"]["redemption"]["unitDate"] = "2017-12-31"
    result = calculate(previous, current, [event(ratio="2")])
    assert result["state"] == "matched" and result["decreasesEnd"] == {"profitCancellation": "20", "redemption": "30"}


def test_multiple_splits_and_reverse_split_and_cumulative_unit_only_change():
    events = [event("2018-03-01", "4"), event("2018-06-01", "2"), event("2018-09-01", "0.5", kind="reverse_split")]
    previous = observation("2017-12-31", "100", "5")
    current = observation("2018-12-31", "380", "40")
    result = calculate(previous, current, events)
    assert result["eventProduct"] == "4.0" and result["decreaseEnd"] == "20.0" and result["state"] == "matched"
    assert canonical(calculate(previous, current, list(reversed(events)))) == canonical(result)
    current = observation("2018-12-31", "400", "20")
    assert calculate(previous, current, events)["decreaseEnd"] == "0.0"


def test_dated_changes_and_actual_share_membership_keep_distinct_price_dates():
    previous = observation("2017-12-31", "100")
    current = observation("2018-12-31", "220")
    split = event(ratio="2")
    changes = [{"date": "2018-05-02", "delta": "10"}]
    assert calculate(previous, current, [split], changes)["state"] == "matched"
    # May 3 is the actual share date; price resumes May 4. Same-day delta is
    # after the split only when the source says so, never implicitly guessed.
    changes = [{"date": "2018-05-03", "delta": "20"}]
    assert calculate(previous, current, [split], changes)["reason"] == "dated_change_unit_unconfirmed"
    changes[0]["sameDayBasis"] = "post_event"
    assert calculate(previous, current, [split], changes)["state"] == "matched"


@pytest.mark.parametrize("edit,reason", [
    (lambda p,c: c["decreases"]["profitCancellation"].update(value=None), "cumulative_unit_unconfirmed"),
    (lambda p,c: c["decreases"]["profitCancellation"].update(value="-1"), "cumulative_unit_unconfirmed"),
    (lambda p,c: c["decreases"]["profitCancellation"].update(unitDate="2019-01-01"), "cumulative_unit_unconfirmed"),
    (lambda p,c: c["decreases"]["profitCancellation"]["unitProof"].update(source="provider_guess"), "cumulative_unit_unconfirmed"),
    (lambda p,c: c["decreases"]["profitCancellation"]["unitProof"].update(filed="2027-01-01"), "cumulative_unit_unconfirmed"),
    (lambda p,c: c.update(restated=True), "cumulative_revision_unconfirmed"),
])
def test_missing_negative_future_or_unconfirmed_sources_do_not_reach_residual(edit, reason):
    previous = observation("2017-12-31", "100")
    current = observation("2018-12-31", "100")
    edit(previous, current)
    assert calculate(previous, current)["reason"] == reason


def test_event_coverage_and_negative_cumulative_difference_are_never_guessed():
    previous = observation("2017-12-31", "100", "10")
    current = observation("2018-12-31", "100", "10")
    for coverage in ({"state": "unknown"}, {"state": "confirmed", "start": "2018-01-01", "end": "2018-12-31"},
                     {"state": "confirmed", "start": "2017-01-01", "end": "2018-11-01"}):
        assert calculate(previous, current, coverage=coverage)["reason"] == "event_coverage_unconfirmed"
    current["decreases"]["profitCancellation"]["value"] = "5"
    assert calculate(previous, current)["reason"] == "cumulative_decrease_unconfirmed"


def test_ads_events_are_excluded_and_revisions_require_both_official_proofs():
    previous = observation("2017-12-31", "100", "10")
    current = observation("2018-12-31", "100", "10")
    assert calculate(previous, current, [event(kind="ads_ratio_change")])["state"] == "matched"
    for row in (previous, current):
        row.update(restated=True, revisionBasis="consistent restated common share ledger", revisionProof=proof())
    assert calculate(previous, current)["state"] == "matched"
    current["revisionBasis"] = "different"
    assert calculate(previous, current)["reason"] == "cumulative_revision_unconfirmed"


def test_version_and_unit_proofs_are_input_fingerprint_owned_but_results_are_not():
    inputs = {"methodVersion": METHOD_VERSION, "specVersion": SPEC_VERSION, "specSha256": SPEC_SHA256,
              "previous": observation("2017-12-31", "100"), "current": observation("2018-12-31", "100")}
    original = fingerprint(inputs)
    result = calculate(inputs["previous"], inputs["current"])
    result["residual"] = "changed"
    assert fingerprint(inputs) == original
    inputs["current"]["decreases"]["profitCancellation"]["unitProof"]["locator"] += " revised"
    assert fingerprint(inputs) != original


def test_explicit_zero_proof_cannot_confirm_a_positive_cumulative_cell():
    previous = observation("2017-12-31", "100")
    current = observation("2018-12-31", "190", "10")
    current["decreases"]["profitCancellation"]["unitProof"]["statement"] = "explicit_zero"
    assert calculate(previous, current, [event(ratio="2")])["reason"] == "cumulative_unit_unconfirmed"
    packet = {"status": "000", "list": [{"corp_code": "00126380", "se": "보통주",
              "stlm_dt": "2018-12-31", "rcept_no": "20190401004781", "istc_totqy": "190",
              "profit_incnr": "10", "rdmstk_repy": "0"}]}
    adapted = dart_observation(packet, corp_code="00126380", as_of="2026-10-01", unit_bases={
        "profitCancellation": {"unitDate": "2018-12-31", "unitProof": proof(statement="explicit_zero")}})
    assert calculate(previous, adapted["observation"], [event(ratio="2")])["reason"] == "cumulative_unit_unconfirmed"


@pytest.mark.parametrize("events,changes", [(None, []), ([None], []), ([], [None]), ({}, [])])
def test_malformed_event_and_change_shapes_return_unknown(events, changes):
    result = reconcile_korean_shares(observation("2017-12-31", "100"), observation("2018-12-31", "100"),
                                    events, changes, coverage={}, as_of="2026-10-01")
    assert result == {"state": "unknown", "reason": "invalid_share_input"}


@pytest.mark.parametrize("packet", [None, [], {"status": "000", "list": [None]}, {"status": "000", "list": None}])
def test_malformed_dart_packets_return_unknown(packet):
    assert dart_observation(packet, corp_code="00126380", as_of="2026-10-01")["state"] == "unknown"


def test_malformed_cumulative_basis_returns_unknown():
    packet = {"status": "000", "list": [{"corp_code": "00126380", "se": "보통주",
              "stlm_dt": "2018-12-31", "rcept_no": "20190401004781", "istc_totqy": "100"}]}
    for basis in ({"profitCancellation": "bad"}, "bad"):
        assert dart_observation(packet, corp_code="00126380", as_of="2026-10-01", unit_bases=basis)["state"] == "unknown"


def test_official_share_cells_keep_missing_preferred_and_explicit_zero_distinct():
    row = {"corp_code": "00126380", "se": "보통주", "stlm_dt": "2018-12-31", "rcept_no": "20190401004781",
           "istc_totqy": "5,969,782,550", "profit_incnr": "1,810,684,300", "rdmstk_repy": "-"}
    packet = {"status": "000", "list": [row, {**row, "se": "우선주", "istc_totqy": "822,886,700"}]}
    bases = {"profitCancellation": {"unitDate": "2018-12-31", "unitProof": proof()}}
    original = deepcopy(packet)
    output = dart_observation(packet, corp_code="00126380", as_of="2026-10-01", unit_bases=bases)
    observation = output["observation"]
    assert observation["shares"] == "5969782550"
    assert observation["decreases"]["redemption"]["value"] is None
    assert observation["decreases"]["redemption"]["rawCell"] == "-"
    assert observation["decreases"]["profitCancellation"]["unitProof"] == proof()
    assert packet == original
    row["rdmstk_repy"] = "0"
    zero = dart_observation(packet, corp_code="00126380", as_of="2026-10-01")["observation"]["decreases"]["redemption"]
    assert zero["value"] == "0" and zero["unitProof"]["statement"] == "explicit_zero"
    assert dart_observation(packet, corp_code="different", as_of="2026-10-01")["state"] == "unknown"
    assert dart_observation(packet, corp_code="00126380", as_of="2018-12-31")["reason"] == "future_share_count_source"
