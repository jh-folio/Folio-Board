from decimal import Decimal
import pytest

from features.price_scenarios.events import (merge_events, price_check, event_price_checks, reconcile_korean_shares_v1 as reconcile_korean_shares,
                                            adjust_history, adjust_fiscal_prices)


def event(date, ratio, kind="unspecified", **extra):
    return {"eventDate": date, "shareDate": date, "ratio": ratio, "kind": kind, "sources": [], **extra}


def test_two_sources_merge_once_and_distant_dates_do_not_double_adjust():
    provider = [event("2020-07-23", "2")]
    official = [event("2020-07-24", "2", "bonus_issue", sources=[{"accession": "official"}])]
    result = merge_events(provider, official)
    assert result["state"] == "merged" and len(result["events"]) == 1
    assert result["events"][0]["eventDate"] == "2020-07-24"
    assert result["events"][0]["providerEvent"] is True
    assert merge_events(provider, [event("2020-08-15", "2", "bonus_issue")])["state"] == "unknown"
    assert merge_events(provider, [event("2020-07-24", "3", "bonus_issue")])["state"] == "unknown"
    assert merge_events([*provider, *provider], official)["state"] == "unknown"
    assert merge_events([], [event("2020-07-24", "0")])["state"] == "unknown"
    assert merge_events([], [])["state"] == "merged"  # No none_confirmed promotion.


@pytest.mark.parametrize("ratio,before,after,provider,expected", [
    ("10", "1000", "100", True, "not_reflected"),
    ("10", "101", "100", True, "reflected"),
    ("0.1", "10", "100", True, "not_reflected"),
    ("0.1", "101", "100", True, "reflected"),
    ("1.1", "100", "100", True, "assumed_by_provider_event"),
    ("1.1", "100", "100", False, "assumed_not_reflected"),
    ("10", "500", "100", True, "unknown"),
    ("10", None, "100", True, "unknown"),
])
def test_log_price_distance_is_symmetric_for_splits_and_reverse_splits(ratio, before, after, provider, expected):
    assert price_check(ratio, before, after, provider_event=provider) == expected


def test_price_check_retains_actual_raw_closes_and_window_boundary():
    events = [event("2010-01-04", "2"), event("2020-07-24", "2", providerEvent=True)]
    closes = [{"date": "2020-07-23", "close": "202"}, {"date": "2020-07-24", "close": "100"}]
    prices = [{"fiscalYear": 2019, "priceDate": "2019-12-31", "close": "150"}]
    checked, raw = event_price_checks(events, closes, prices)
    assert checked[0]["priceCheck"] == "not_needed"
    assert checked[1]["priceCheck"] == "not_reflected"
    assert raw[0] == {"eventDate": "2020-07-24", "beforeDate": "2020-07-23", "beforeClose": "202", "afterDate": "2020-07-24", "afterClose": "100"}
    assert adjust_fiscal_prices(prices, checked)[0]["close"] == "75"


def test_50_split_and_cancellation_both_cumulative_units_are_allowed():
    split = event("2018-05-04", "50", "split")
    previous = {"periodEnd": "2017-12-31", "shares": "100", "decreaseCumulative": "0"}
    for decrease in ("10", "500"):
        current = {"periodEnd": "2018-12-31", "shares": "4500", "decreaseCumulative": decrease}
        assert reconcile_korean_shares(previous, current, [split], [])["state"] == "matched"
    mismatch = {"periodEnd": "2018-12-31", "shares": "100", "decreaseCumulative": "0"}
    assert reconcile_korean_shares(previous, mismatch, [split], [])["state"] == "unknown"


def test_measured_cumulative_unit_change_stays_unknown_until_proven():
    # Samsung 2017/2018 raw cumulative figures change denomination. Applying
    # the frozen two-unit residual to their raw difference does not reconcile;
    # do not silently rescale a cumulative source value to obtain a pass.
    previous = {"periodEnd": "2017-12-31", "shares": "129098494", "decreaseCumulative": "26510843"}
    current = {"periodEnd": "2018-12-31", "shares": "5969782550", "decreaseCumulative": "1810684300"}
    assert reconcile_korean_shares(previous, current, [event("2018-05-04", "50", "split")], [])["state"] == "unknown"


def test_dated_equity_issuance_is_converted_only_by_later_events():
    previous = {"periodEnd": "2017-12-31", "shares": "100", "decreaseCumulative": "0"}
    current = {"periodEnd": "2018-12-31", "shares": "5700", "decreaseCumulative": "0"}
    result = reconcile_korean_shares(previous, current, [event("2018-05-04", "50")], [
        {"date": "2018-01-10", "delta": "10"}, {"date": "2018-10-01", "delta": "200"}])
    assert result["state"] == "matched" and Decimal(result["datedDeltaAdjusted"]) == 700


def test_share_membership_uses_listing_date_not_the_bonus_price_effective_date():
    previous = {"periodEnd": "2020-06-30", "shares": "100", "decreaseCumulative": "0"}
    current = {"periodEnd": "2020-12-31", "shares": "200", "decreaseCumulative": "0"}
    bonus = event("2020-06-29", "2", "bonus_issue", shareDate="2020-07-10")
    assert reconcile_korean_shares(previous, current, [bonus], [])["state"] == "matched"


def test_filing_dates_prevent_double_adjustment_and_ads_ratio_changes_are_excluded():
    history = {"rows": [{"metric": metric, "value": value, "filed": filed} for metric, value, filed in [
        ("EPS Diluted", "10", "2019-03-01"), ("EPS Diluted", "5", "2021-03-01"),
        ("Shares Diluted", "100", "2019-03-01"), ("Revenue", "1000", "2019-03-01")]]}
    events = [event("2020-07-24", "2", "bonus_issue"), event("2022-01-03", "2", "ads_ratio_change")]
    result = adjust_history(history, events, session_date="2026-10-01", state="present", ads_ratio="5")
    assert [r["value"] for r in result["rows"]] == ["25", "25", "40", "1000"]
    assert history["rows"][0]["value"] == "10"
    with pytest.raises(ValueError, match="share_event_unknown"):
        adjust_history(history, events, session_date="2026-10-01", state="unknown")
