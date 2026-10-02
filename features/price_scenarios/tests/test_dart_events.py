from copy import deepcopy

import pytest

from features.price_scenarios.dart_events import bonus_decisions, dart_date, dated_share_changes
from features.price_scenarios.events import merge_events, reconcile_korean_shares_v1 as reconcile_korean_shares


def decision(**extra):
    return {"corp_code": "00989619", "rcept_no": "20200707000078", "nstk_asstd": "2020년 07월 24일",
            "nstk_lstprd": "2020년 08월 13일", "nstk_ascnt_ps_ostk": "1", **extra}


def bonus(row):
    return bonus_decisions({"status": "000", "list": [row]}, corp_code="00989619",
                          trading_dates=["2020-07-22", "2020-07-23", "2020-07-24"], as_of="2026-10-01")


def test_measured_bonus_fields_use_one_plus_allocation_and_distinct_effective_dates():
    row = decision()
    original = deepcopy(row)
    result = bonus(row)
    event = result["events"][0]
    assert event["ratio"] == "2" and event["eventDate"] == "2020-07-23"
    assert event["shareDate"] == "2020-08-13" and event["exDateBasis"] == "record_date_minus_1"
    assert event["sources"][0]["newSharesPerOldShare"] == "1"
    assert row == original
    merged = merge_events([{**event, "kind": "unspecified", "sources": [{"provider": "yfinance"}]}], [event])
    assert len(merged["events"]) == 1 and merged["events"][0]["ratio"] == "2"


@pytest.mark.parametrize("extra", [{"nstk_ascnt_ps_ostk": "-"}, {"nstk_lstprd": "-"},
                                   {"corp_code": "different"}, {"nstk_asstd": "2020년 02월 30일"}])
def test_missing_or_wrong_bonus_fields_do_not_get_provider_guesses(extra):
    assert bonus(decision(**extra))["state"] == "unknown"


def test_empty_bonus_collection_is_only_one_source_not_none_confirmed():
    result = bonus_decisions({"status": "013"}, corp_code="00989619", trading_dates=[], as_of="2026-10-01")
    assert result["state"] == "received" and result["events"] == []
    assert bonus_decisions({"status": "020"}, corp_code="00989619", trading_dates=[], as_of="2026-10-01")["state"] == "unknown"


def change(kind, day="2020.06.10", shares="10", security="보통주"):
    return {"corp_code": "00989619", "rcept_no": "20210325000001", "isu_dcrs_de": day,
            "isu_dcrs_stle": kind, "isu_dcrs_stock_knd": security, "isu_dcrs_qy": shares}


def test_capital_changes_exclude_bonus_and_split_and_keep_dated_units():
    rows = [change("전환권행사"), change("감자", "2020.09.01", "5"),
            change("무상증자", shares="100"), change("주식분할", shares="100"),
            change("유상증자(제3자배정)", shares="200", security="전환우선주")]
    result = dated_share_changes({"status": "000", "list": rows}, corp_code="00989619", as_of="2021-01-01")
    assert result["state"] == "received" and [r["delta"] for r in result["changes"]] == ["10", "-5"]
    event = bonus(decision())["events"][0]
    previous = {"periodEnd": "2019-12-31", "shares": "100", "decreaseCumulative": "0"}
    current = {"periodEnd": "2020-12-31", "shares": "215", "decreaseCumulative": "0"}
    assert reconcile_korean_shares(previous, current, [event], result["changes"])["state"] == "matched"


def test_blank_placeholder_and_source_failure_remain_distinct():
    blank = change("-", day="-", shares="-", security="-")
    assert dated_share_changes({"status": "000", "list": [blank]}, corp_code="00989619", as_of="2021-01-01")["state"] == "received"
    assert dated_share_changes({"status": "013"}, corp_code="00989619", as_of="2021-01-01")["state"] == "unknown"
    for rows in ([change("미확인")], [change("전환권행사"), change("전환권행사")], [blank, change("전환권행사")]):
        assert dated_share_changes({"status": "000", "list": rows}, corp_code="00989619", as_of="2021-01-01")["state"] == "unknown"


def test_dates_are_exact_formats_and_calendar_validated():
    assert dart_date("2020.07.24") == dart_date("2020년 07월 24일") == dart_date("2020-07-24")
    assert dart_date("2020-02-30") is None and dart_date("예정 2020-07-24") is None


def test_truncated_trading_history_cannot_supply_a_previous_trading_day():
    result = bonus_decisions({"status": "000", "list": [decision()]}, corp_code="00989619",
                            trading_dates=["2020-07-10"], as_of="2026-10-01")
    assert result["state"] == "unknown"


def test_a_dated_increase_with_a_blank_reason_explains_nothing_but_does_not_stop_the_ledger():
    rows = [change("-", day="2021.12.09", shares="3,789,032"), change("전환권행사", "2021.03.01", "10")]
    result = dated_share_changes({"status": "000", "list": rows}, corp_code="00989619", as_of="2026-10-01")
    assert result["state"] == "received" and [r["delta"] for r in result["changes"]] == ["10"]
    for broken in (change("-", day="-", shares="5"), change("-", shares="-")):
        assert dated_share_changes({"status": "000", "list": [broken]}, corp_code="00989619", as_of="2026-10-01")["state"] == "unknown"
