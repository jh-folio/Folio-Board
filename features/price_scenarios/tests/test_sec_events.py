from copy import deepcopy

import pytest

from features.price_scenarios.sec_events import reconcile_sec_events


def history(*facts):
    """Actual filing observations, packaged as latest plus priorValues."""
    rows = []
    for metric, index in (("Shares Diluted", 1), ("EPS Diluted", 2)):
        latest = facts[-1]
        rows.append({"metric": metric, "period": {"start": "2019-01-01", "end": "2019-12-31"},
                     "filed": latest[0], "accession": latest[0], "value": latest[index],
                     "priorValues": [{"filed": fact[0], "accession": fact[0], "value": fact[index]}
                                     for fact in facts[:-1]]})
    return {"rows": rows}


def event(day, ratio, **extra):
    return {"eventDate": day, "ratio": ratio, "kind": "unspecified", "providerEvent": True, **extra}


def reconcile(source, events, **extra):
    return reconcile_sec_events(source, events, source_state="received", session_date="2026-09-30",
                                security_kind=extra.pop("security_kind", "common_share"), **extra)


def test_multiple_events_match_every_filing_pair_without_double_adjustment():
    source = history(("2020-03-01", "100", "12"), ("2021-03-01", "200", "6"),
                     ("2022-03-01", "600", "2"))
    events = [event("2020-08-01", "2"), event("2021-08-01", "3")]
    result = reconcile(source, events)
    assert result["state"] == "present"
    assert len(result["filingPairChecks"]) == 3
    assert {row["eventProduct"] for row in result["filingPairChecks"]} == {"2", "3", "6"}
    assert all(row["matched"] for row in result["filingPairChecks"])
    assert reconcile(source, events[:1])["reason"] == "unmatched_common_share_trace"
    assert reconcile(source, [event("2020-08-01", "3"), *events[1:]])["state"] == "unknown"


def test_normal_restatement_is_history_but_empty_collection_is_not_proof_alone():
    source = history(("2020-03-01", "100", "12"), ("2021-03-01", "100", "11"))
    original = deepcopy(source)
    result = reconcile(source, [])
    assert result["state"] == "none_confirmed"
    assert result["filingPairChecks"][0]["trace"] is False
    assert source == original
    assert reconcile({"rows": []}, [])["state"] == "unknown"
    assert reconcile_sec_events(source, [], source_state="unknown", session_date="2026-09-30",
                                security_kind="common_share")["reason"] == "event_source_unavailable"


def test_false_provider_split_with_expected_trace_is_rejected_but_recent_split_is_allowed():
    source = history(("2020-03-01", "100", "12"), ("2021-03-01", "100", "12"))
    assert reconcile(source, [event("2020-08-01", "2")])["reason"] == "expected_share_trace_missing"
    assert reconcile(source, [event("2022-08-01", "2")])["state"] == "present"
    # A >5% share change without inverse EPS movement is not a split trace.
    changed = history(("2020-03-01", "100", "12"), ("2021-03-01", "200", "12"))
    assert reconcile(changed, [])["state"] == "none_confirmed"


def test_adr_provider_event_without_common_trace_is_ads_ratio_change():
    source = history(("2020-03-01", "100", "12"), ("2021-03-01", "100", "12"))
    events = [event("2020-08-01", "1.116")]
    result = reconcile(source, events, security_kind="ads", latest_annual_filed="2021-03-01")
    assert result["state"] == "present" and result["events"][0]["kind"] == "ads_ratio_change"
    assert events[0]["kind"] == "unspecified"
    assert reconcile(source, [event("2022-08-01", "2")], security_kind="ads",
                     latest_annual_filed="2021-03-01")["reason"] == "ads_event_after_latest_annual"
    assert reconcile(source, [], security_kind="ads")["state"] == "unknown"


def test_verified_adr_common_split_is_retained_and_inverse_eps_tolerance_is_relative():
    source = history(("2020-03-01", "100", "12"), ("2021-03-01", "200", "6.05"))
    result = reconcile(source, [event("2020-08-01", "2")], security_kind="ads",
                       latest_annual_filed="2021-03-01")
    assert result["state"] == "present" and result["events"][0]["kind"] == "unspecified"
    outside = history(("2020-03-01", "100", "12"), ("2021-03-01", "200", "6.07"))
    assert reconcile(outside, [event("2020-08-01", "2")])["state"] == "unknown"


@pytest.mark.parametrize("events", [[event("2027-01-01", "2")], [event("2020-08-01", "0")],
                                   [event("2020-08-01", "2"), event("2020-08-01", "2")]])
def test_invalid_or_future_events_do_not_confirm_evidence(events):
    assert reconcile(history(("2020-03-01", "100", "12")), events)["state"] == "unknown"
