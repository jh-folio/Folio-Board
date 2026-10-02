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


def test_a_pre_split_filing_without_share_counts_is_neither_a_trace_nor_an_expected_trace():
    """GOOGL type: the old 10-K carries the year's EPS (112.2) but companyfacts has no diluted shares for it."""
    period = {"start": "2021-01-01", "end": "2021-12-31"}
    rows = [{"metric": "EPS Diluted", "period": period, "filed": "2023-02-02", "accession": "new", "value": "5.61",
             "priorValues": [{"filed": "2022-02-02", "accession": "old", "value": "112.2"}]},
            {"metric": "Shares Diluted", "period": period, "filed": "2023-02-02", "accession": "new", "value": "13000", "priorValues": []}]
    result = reconcile({"rows": rows}, [event("2022-07-18", "20")])
    assert result["state"] == "present" and result["filingPairChecks"] == []   # the user-approved reading; see the spec-3 clarification


def test_googl_shape_neither_filing_carries_the_year_s_share_count():
    old_year = {"start": "2021-01-01", "end": "2021-12-31"}
    later = {"start": "2023-01-01", "end": "2023-12-31"}
    later_rows = [{"metric": metric, "period": later, "filed": "2025-02-05", "accession": "later", "value": value,
                   "priorValues": [{"filed": "2024-01-31", "accession": "prev", "value": value}]}
                  for metric, value in (("EPS Diluted", "5.8"), ("Shares Diluted", "12722"))]   # later years carry both, so evidence exists
    year_2021 = {"metric": "EPS Diluted", "period": old_year, "filed": "2024-01-31", "accession": "newest", "value": "5.61",
                 "priorValues": [{"filed": "2022-02-02", "accession": "old", "value": "112.2"},
                                 {"filed": "2023-02-03", "accession": "mid", "value": "5.61"}]}
    result = reconcile({"rows": [year_2021, *later_rows]}, [event("2022-07-18", "20")])
    assert result["state"] == "present" and all(pair["after"]["period"] != old_year for pair in result["filingPairChecks"])
    # the same year with a share count in both filings and nothing moving is a false split: the expected trace is missing
    shares = {"metric": "Shares Diluted", "period": old_year, "filed": "2024-01-31", "accession": "newest", "value": "650",
              "priorValues": [{"filed": "2022-02-02", "accession": "old", "value": "650"}, {"filed": "2023-02-03", "accession": "mid", "value": "650"}]}
    flat_eps = dict(year_2021, priorValues=[{"filed": "2022-02-02", "accession": "old", "value": "5.61"}, {"filed": "2023-02-03", "accession": "mid", "value": "5.61"}])
    assert reconcile({"rows": [flat_eps, shares, *later_rows]}, [event("2022-07-18", "20")])["state"] == "unknown"
