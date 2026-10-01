from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pytest

from features.price_scenarios.decimal_ops import fingerprint, load_source_json, number, source_number
from features.price_scenarios.history import dart_history, sec_history
from features.price_scenarios.prices import completed_closes, fiscal_year_prices, provider_symbol, reference_price
from features.price_scenarios.securities import listed_security, verify_ads_basis
from features.price_scenarios.support import classify


def fact(value, end="2025-12-31", *, start="2025-01-01", filed="2026-02-01", acc="latest", form="10-K"):
    return {"val": value, "end": end, "start": start, "filed": filed, "accn": acc, "form": form}


def packet(concepts):
    return {"facts": {"us-gaap": concepts}}


def by_metric(history, metric):
    return [row for row in history["rows"] if row["metric"] == metric]


def test_source_precision_zero_missing_nonfinite_and_fingerprint():
    decoded = load_source_json('{"value":1.2300}')
    assert str(decoded["value"]) == "1.2300"
    assert source_number("0") == "0"
    assert source_number("(1,230.00)") == "-1230.00"
    assert source_number("-") is None
    assert source_number("NaN") is None
    with pytest.raises(ValueError):
        number(True)
    assert fingerprint({"value":"1.2300","date":"2025-01-01"}) == fingerprint({"date":"2025-01-01","value":"1.2300"})
    assert fingerprint({"value":"1.2300"}) != fingerprint({"value":"1.23"})
    with pytest.raises(ValueError):
        fingerprint({"rate":0.12})


def test_sec_ten_year_history_tag_selection_per_period_and_revisions():
    old=[fact(str(100+y),f"{y}-12-31",start=f"{y}-01-01",filed=f"{y+1}-02-01",acc=f"old-{y}") for y in range(2012,2026)]
    modern=[fact("220.00","2024-12-31",start="2024-01-01",filed="2025-02-01",acc="m1"),
            fact("221.00","2024-12-31",start="2024-01-01",filed="2026-02-01",acc="m2")]
    data=packet({"Revenues":{"units":{"USD":modern}},"SalesRevenueNet":{"units":{"USD":old}}})
    rows=by_metric(sec_history(data),"Revenue")
    assert len(rows)==10
    assert {r["fiscalYear"] for r in rows}==set(range(2016,2026))
    current=next(r for r in rows if r["fiscalYear"]==2024)
    assert current["value"]=="221.00" and current["precision"]==2
    assert current["priorValues"][0]["value"]=="220.00"
    assert next(r for r in rows if r["fiscalYear"]==2025)["concept"].endswith("SalesRevenueNet")
    historical=next(r for r in by_metric(sec_history(data,as_of="2025-03-01"),"Revenue") if r["fiscalYear"]==2024)
    assert historical["value"]=="220.00"


def test_53_week_year_and_short_transition_never_become_annual_growth_input():
    rows=[fact("100","2025-02-01",start="2024-01-28"),fact("20","2024-01-27",start="2023-10-01")]
    result=sec_history(packet({"Revenues":{"units":{"USD":rows}}}))
    assert [r["fiscalYear"] for r in result["rows"]]==[2025]
    assert result["rows"][0]["period"]["end"]=="2025-02-01"
    assert result["excludedYears"]==[{"fiscalYear":2024,"reason":"non_annual_period"}]


def test_quarterly_facts_inside_annual_filing_do_not_exclude_the_full_fiscal_year():
    rows=[fact("100"),fact("20",start="2025-10-01")]
    result=sec_history(packet({"Revenues":{"units":{"USD":rows}}}))
    assert result["rows"][0]["value"]=="100"
    assert result["excludedYears"]==[]


def test_annual_filing_quarterly_and_opening_balances_are_not_fiscal_year_ends():
    data = packet({"Revenues": {"units": {"USD": [fact("100")] }},
        "Assets": {"units": {"USD": [fact("50", "2025-03-31", start=None),
            fact("60", "2025-06-30", start=None), fact("70", "2025-09-30", start=None),
            fact("80", "2025-12-31", start=None), fact("40", "2025-01-01", start=None)]}}})
    history = sec_history(data)
    assert [(r["period"]["end"], r["value"]) for r in by_metric(history, "Total Assets")] == [("2025-12-31", "80")]
    assert history["excludedYears"] == []  # Only observations were excluded.
    # A 53-week fiscal year ends in February, without inventing December data.
    data["facts"]["us-gaap"]["Revenues"]["units"]["USD"] = [fact("100", "2025-02-01", start="2024-01-28")]
    data["facts"]["us-gaap"]["Assets"]["units"]["USD"].append(fact("81", "2025-02-01", start=None))
    assert by_metric(sec_history(data), "Total Assets")[0]["period"]["end"] == "2025-02-01"


def test_measured_ifrs_cash_capex_does_not_substitute_non_cash_ppe_additions():
    concepts = {
        "Revenue": {"units": {"USD": [fact("100", form="20-F")] }},
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": {
            "units": {"USD": [fact("15", form="20-F")] }},
        "AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment": {
            "units": {"USD": [fact("99", form="20-F")] }},
    }
    data = {"facts": {"ifrs-full": concepts}}
    row = by_metric(sec_history(data), "Capital Expenditure")[0]
    assert row["value"] == "15" and row["concept"].endswith("ClassifiedAsInvestingActivities")
    del concepts["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]
    assert by_metric(sec_history(data), "Capital Expenditure") == []


def dart_row(account, current, prior="10", previous="9", *, accession="20260310002820", currency="KRW"):
    return {"account_id":account,"currency":currency,"rcept_no":accession,"reprt_code":"11011",
            "thstrm_amount":current,"frmtrm_amount":prior,"bfefrmtrm_amount":previous}


def test_dart_comparatives_revisions_march_end_and_single_statement_basis():
    old=dart_row("ifrs-full_Revenue","100","90","80",accession="20250301000001")
    new=dart_row("ifrs-full_Revenue","120","101","90")
    batches=[{"basis":"CFS","periodEnd":"2024-03-31","rows":[old]},
             {"basis":"CFS","periodEnd":"2025-03-31","periodEndSource":"stockTotqySttus.stlm_dt","rows":[new]},
             {"basis":"OFS","periodEnd":"2025-03-31","rows":[dart_row("ifrs-full_Revenue","999")]}]
    result=dart_history(batches)
    assert result["basis"]=="CFS"
    rows=by_metric(result,"Revenue")
    assert next(r for r in rows if r["fiscalYear"]==2024)["value"]=="101"
    assert next(r for r in rows if r["fiscalYear"]==2025)["period"]=={"start":"2024-04-01","end":"2025-03-31"}
    assert next(r for r in rows if r["fiscalYear"]==2024)["priorValues"][0]["value"]=="100"
    with pytest.raises(ValueError,match="requires_source"):
        dart_history([{"basis":"CFS","rows":[new]}])


def test_dart_implied_common_shares_missing_and_foreign_currency():
    rows=[dart_row("ifrs-full_ProfitLossAttributableToOwnersOfParent","100","-50","0"),
          dart_row("ifrs-full_DilutedEarningsLossPerShare","2","-1","0"),
          dart_row("ifrs-full_Revenue","999",currency="USD")]
    result=dart_history([{"basis":"CFS","periodEnd":"2025-12-31","rows":rows}])
    shares=by_metric(result,"Shares Diluted")
    assert len(shares)==2 and all(Decimal(r["value"])==50 for r in shares)
    assert by_metric(result,"Revenue")==[]


def cover(ticker,title,*,extra=""):
    return f'<html><body><ix:nonNumeric name="dei:Security12bTitle" contextRef="c1">{title}</ix:nonNumeric><ix:nonNumeric name="dei:TradingSymbol" contextRef="c1">{ticker}</ix:nonNumeric>{extra}</body></html>'


def test_20f_common_share_official_title_wins_and_ticker_context_is_exact():
    result=listed_security(cover("MNDY","Ordinary shares"),"MNDY",accession="annual",provider_kind="ads")
    assert result["kind"]=="common_share" and "adsRatio" not in result
    assert listed_security(cover("OTHER","American Depositary Shares, each representing two Ordinary Shares"),"MNDY",accession="annual")["kind"]=="unknown"


def test_ads_ratio_footnote_and_bonds_using_same_symbol():
    bond='<ix:nonNumeric name="dei:Security12bTitle" contextRef="bond">3.125% Notes due 2028</ix:nonNumeric><ix:nonNumeric name="dei:TradingSymbol" contextRef="bond">MSFT</ix:nonNumeric>'
    assert listed_security(cover("MSFT","Common stock",extra=bond),"MSFT",accession="a")["kind"]=="common_share"
    ads=listed_security(cover("TEVA","American Depositary Shares, each representing one Ordinary Share"),"TEVA",accession="a")
    assert ads["kind"]=="ads" and ads["adsRatio"]["value"]=="1"
    nvs=listed_security(cover("NVS","American Depositary Shares each representing 1 share"),"NVS",accession="n")
    assert nvs["adsRatio"]["value"]=="1"
    tsm=listed_security(cover("TSM","Common Shares",extra="Not for trading, but only in connection with the listing of American Depositary Shares representing such Common Shares."),"TSM",accession="a")
    assert tsm["kind"]=="ads" and "adsRatio" not in tsm


def test_missing_listing_precedes_compatible_and_verified_ads_basis():
    result=classify({"market":"US"},{"code":"3571","listedSecurity":{"kind":"unknown"}},reporting_currency="USD",quote_currency="USD",share_unit_status="compatible")
    assert result["status"]=="limited"
    assert result["reasons"]==[{"code":"share_unit_unknown","subCode":"listed_security_unknown"}]
    history={"rows":[{"fiscalYear":2025,"metric":name,"value":value,"period":{"start":"2025-01-01","end":"2025-12-31"}} for name,value in [("Net Income","100"),("Shares Diluted","50"),("EPS Diluted","2")]]}
    assert verify_ads_basis(history,{"value":"5"})
    history["rows"][-1]["value"]="10"
    assert not verify_ads_basis(history,{"value":"5"})


@pytest.mark.parametrize("market,code,expected",[("US","6020","unsupported"),("US","6719","supported"),("US","6799","supported"),("KR","64992","supported"),("KR","66201","unsupported"),("KR","26410","supported")])
def test_frozen_industry_boundaries(market,code,expected):
    result=classify({"market":market},{"code":code,"listedSecurity":{"kind":"common_share"}},reporting_currency="USD",quote_currency="USD",share_unit_status="compatible")
    assert result["status"]==expected


def test_march_fiscal_price_daily_close_session_cutoff_weekend_and_stale():
    bars=[{"date":"2026-03-27","close":"100"},{"date":"2026-03-30","close":"110"},{"date":"2026-03-31","close":"120"}]
    before=dt.datetime(2026,3,31,6,59,tzinfo=dt.timezone.utc)
    assert reference_price(bars,"KR",now=before,currency="KRW",symbol="092440.KS")["value"]=="110"
    after=dt.datetime(2026,3,31,7,0,tzinfo=dt.timezone.utc)
    closes=completed_closes(bars,"KR",now=after)
    assert fiscal_year_prices(closes,[{"fiscalYear":2026,"periodEnd":"2026-03-31"}])[0]["close"]=="120"
    with pytest.raises(ValueError,match="price_stale"):
        reference_price(bars,"KR",now=dt.datetime(2026,4,16,8,tzinfo=dt.timezone.utc),currency="KRW",symbol="x")
    assert provider_symbol("035900","KR",{"corp_cls":"K"})==("035900.KQ","dart_corp_cls")
    with pytest.raises(ValueError,match="exchange"):
        provider_symbol("035900","KR",{})
