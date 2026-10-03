from copy import deepcopy

import pytest

from features.company_analysis import dcf, financial_engine
from features.price_scenarios.dcf_history import dcf_summary
from features.price_scenarios.decimal_ops import fingerprint


def row(year, metric, value, *, month="03", **extra):
    return {"fiscalYear": year, "metric": metric, "value": value,
            "period": {"start": f"{year-1}-04-01", "end": f"{year}-{month}-31"},
            "form": "DART_11011", "filed": f"{year}-06-25", "accession": f"{year}0625000001",
            "concept": metric, "unit": "KRW", "precision": 0, "priorValues": [], **extra}


def test_ten_year_adapter_keeps_march_ends_missing_years_and_source_ids():
    years = [2016, 2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025]
    history = {"currency": "KRW", "basis": "CFS", "sharesBasis": "implied_from_eps", "rows": [
        row(year, metric, str(value)) for year in years
        for metric, value in (("Revenue", 100 * 1.1**(year-2020)),
                              ("Operating Cash Flow", 30), ("Capital Expenditure", 10))]}
    original = deepcopy(history)
    summary = dcf_summary(history)
    assert len(summary["rows"][0]["annual"]) == 9
    assert sorted(financial_engine.annual_year_values(summary, "Revenue")) == [str(year) for year in years]
    growth = dcf.growth_driver(summary)
    assert growth["rate"] == pytest.approx(0.1)
    assert growth["growthWindow"]["periodYears"] == 4
    observation = growth["growthWindow"]["start"]["sources"][0]
    assert observation["end"] == "2021-03-31" and observation["accn"] == "20210625000001"
    assert history == original
    assert len(fingerprint(summary)) == 64


def test_adapter_does_not_align_different_fcf_years_or_fill_missing_observations():
    source = {"currency": "USD", "rows": [row(2025, "Operating Cash Flow", "100"),
                                           row(2024, "Capital Expenditure", "20")]}
    assert dcf.normalized_base_fcf(dcf_summary(source)) == {}


def test_zero_negative_and_share_adjustment_remain_distinct_from_absence():
    history = {"currency": "KRW", "rows": [row(2025, "Income Tax", "0"),
        row(2025, "Net Income", "-100"), row(2025, "Shares Diluted", "5000",
        rawValue="100", formula="parent_common_profit/diluted_common_eps", sourceAccessions=["profit", "eps"],
        adjustment={"eventProduct": "50", "adsRatio": "1", "events": ["2025-05-04"]})]}
    summary = dcf_summary(history)
    assert financial_engine.latest_value(summary, "Income Tax") == 0
    assert financial_engine.latest_value(summary, "Net Income") == -100
    assert financial_engine.latest_value(summary, "Interest Expense") is None
    shares = next(row for row in summary["rows"] if row["metric"] == "Shares Diluted")["annual"][0]
    assert shares["rawValue"] == "100" and shares["adjustment"]["eventProduct"] == "50"
    assert shares["val"] == "5000"
    assert shares["sourceAccessions"] == ["profit", "eps"] and shares["formula"] == "parent_common_profit/diluted_common_eps"


def test_source_correction_changes_input_fingerprint_without_mutating_history():
    history = {"rows": [row(2025, "Revenue", "100")]}
    before = fingerprint(dcf_summary(history))
    corrected = deepcopy(history)
    corrected["rows"][0]["value"] = "101"
    corrected["rows"][0]["priorValues"] = [{"value": "100", "filed": "2025-06-25", "accession": "old"}]
    assert fingerprint(dcf_summary(corrected)) != before
    assert history["rows"][0]["value"] == "100"


def test_ambiguous_year_is_rejected_instead_of_order_dependent_selection():
    with pytest.raises(ValueError, match="ambiguous_dcf_fiscal_year"):
        dcf_summary({"rows": [row(2025, "Revenue", "100"), row(2025, "Revenue", "200", month="12")]})
    wrong = row(2025, "Revenue", "100")
    wrong["fiscalYear"] = 2024
    with pytest.raises(ValueError, match="dcf_fiscal_year_end_mismatch"):
        dcf_summary({"rows": [wrong]})
