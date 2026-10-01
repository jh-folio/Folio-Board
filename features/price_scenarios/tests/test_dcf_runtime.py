from copy import deepcopy
from decimal import Decimal

import pytest

from features.company_analysis import dcf
from features.price_scenarios.dcf_runtime import capture_dcf_inputs, replay_dcf
from features.price_scenarios.decimal_ops import canonical, fingerprint


def fixture():
    rows = []
    for year in range(2016, 2026):
        for metric, value in {"Revenue": str(100*1.1**(year-2020)), "Operating Cash Flow": "30", "Capital Expenditure": "10",
                              "Shares Diluted": "100", "Long-Term Debt": "100", "Income Tax": "4", "Pretax Income": "20",
                              "Interest Expense": "3", "Net Income": "16"}.items():
            instant = metric == "Long-Term Debt"
            rows.append({"metric": metric, "value": value, "fiscalYear": year,
                         "period": {"start": None if instant else f"{year}-01-01", "end": f"{year}-12-31"},
                         "filed": f"{year+1}-02-01", "accession": str(year), "concept": metric,
                         "form": "10-K", "unit": "shares" if metric == "Shares Diluted" else "USD", "precision": 0})
    return {"history": {"currency": "USD", "basis": "us-gaap", "rows": rows},
            "price": {"value": "10", "sessionDate": "2026-09-30", "currency": "USD"},
            "support": {"status": "supported", "reasons": []}, "share_event_state": "none_confirmed",
            "debt_inputs": {"ok": True, "position": {"ok": True, "asOf": "2025-12-31", "complete": True,
                "netDebt": "70", "totalDebt": "100", "cash": "30", "basis": "total_debt", "sources": []}, "observations": []},
            "beta": {"value": "1.2", "source": "yfinance"},
            "risk_free": {"rate": "0.0407", "source": "fred_dgs10", "observedAt": "2026-09-29",
                          "rawObservation": {"value": "4.07", "unit": "percent"}, "fetchedAt": "now"}}


def test_capture_contains_every_used_value_and_replay_ignores_legacy_derivation(monkeypatch):
    source = fixture()
    original = deepcopy(source)
    capture = capture_dcf_inputs(**source)
    assert capture["status"] == "available"
    inputs = capture["inputs"]
    assert inputs["marketCap"] == "1000" and inputs["shares"] == "100"
    assert inputs["financialRates"] == {"taxRate": "0.2", "debtCost": "0.03"}
    assert inputs["growthWindow"]["periodYears"] == 3
    assert inputs["discount"]["method"] == "wacc" and inputs["beta"]["value"] == "1.2"
    assert "fetchedAt" not in inputs["riskFree"]
    assert all(len(row["annual"]) == 10 for row in inputs["summary"]["rows"])
    assert len(fingerprint(inputs)) == 64 and source == original
    monkeypatch.setattr(dcf, "normalized_base_fcf", lambda *a: pytest.fail("must replay captured base"))
    monkeypatch.setattr(dcf, "growth_driver", lambda *a: pytest.fail("must replay captured growth"))
    monkeypatch.setattr(dcf, "net_debt_from", lambda *a: pytest.fail("must replay captured position"))
    monkeypatch.setattr(dcf.financial_engine, "derived_financials", lambda *a: pytest.fail("must replay captured rates"))
    output = replay_dcf(inputs)
    assert output["status"] == "available" and output["marginOfSafetyJudgment"] == "eligible"
    assert output["derivedAssumptions"]["discountRate"] == inputs["discount"]["rate"]
    assert output["result"]["netDebt"]["asOf"] == "2025-12-31"
    assert canonical(replay_dcf(inputs)) == canonical(output)
    assert capture["inputs"] == inputs


def test_same_period_and_current_tax_interest_do_not_use_older_accounts():
    source = fixture()
    source["history"]["rows"] = [r for r in source["history"]["rows"] if not (r["fiscalYear"] == 2025 and r["metric"] in {"Income Tax", "Interest Expense"})]
    inputs = capture_dcf_inputs(**source)["inputs"]
    assert inputs["financialRates"] == {"taxRate": None, "debtCost": None}
    assert inputs["rateSources"]["Income Tax"] is None
    # Same year but different accounting period also cannot form a tax rate.
    tax = next(r for r in source["history"]["rows"] if r["metric"] == "Income Tax")
    source["history"]["rows"].append({**tax, "fiscalYear": 2025, "filed": "2026-02-01",
                                      "period": {"start": "2025-07-01", "end": "2025-12-31"}})
    assert capture_dcf_inputs(**source)["inputs"]["financialRates"]["taxRate"] is None


def test_fallback_growth_or_discount_allows_display_but_never_safety_judgment():
    source = fixture()
    source["beta"] = {"value": None, "source": "unavailable"}
    captured = capture_dcf_inputs(**source)
    output = replay_dcf(captured["inputs"])
    assert output["status"] == "available" and output["marginOfSafetyJudgment"] == "unknown"
    assert output["notices"] == ["dcf_fallback"]
    assert captured["inputs"]["discount"]["method"] == "fallback_fixed"
    source = fixture()
    source["history"]["rows"] = [r for r in source["history"]["rows"]
                                 if r["metric"] not in {"Revenue", "Operating Cash Flow"} or r["fiscalYear"] == 2025]
    output = replay_dcf(capture_dcf_inputs(**source)["inputs"])
    assert output["notices"] == ["dcf_fallback"] and output["derivedAssumptions"]["growthBasis"] == "fallback"


@pytest.mark.parametrize("field,value,reason", [
    ("support", {"status": "limited", "reasons": [{"code": "share_unit_unknown", "subCode": "listed_security_unknown"}]}, "share_unit_unknown"),
    ("support", {"status": "unsupported", "reasons": [{"code": "industry_not_supported"}]}, "industry_not_supported"),
    ("share_event_state", "unknown", "share_event_unknown"),
    ("debt_inputs", {"ok": False, "reason": "same_period_debt_unavailable"}, "dcf_not_computable"),
    ("price", {"value": "10", "sessionDate": "2026-09-30", "currency": "TWD"}, "currency_mismatch"),
])
def test_support_and_input_guards_run_before_any_valuation(field, value, reason, monkeypatch):
    source = fixture()
    source[field] = value
    monkeypatch.setattr(dcf, "normalized_base_fcf", lambda *a: pytest.fail("ineligible inputs reached DCF"))
    assert capture_dcf_inputs(**source)["reason"]["code"] == reason


def test_price_shares_market_cap_and_risk_free_units_are_not_provider_replaced():
    source = fixture()
    source["price"]["value"] = "12"
    source["history"]["rows"] = [{**r, "value": "5000", "rawValue": "100", "adjustment": {"eventProduct": "50"}}
                                 if r["metric"] == "Shares Diluted" else r for r in source["history"]["rows"]]
    inputs = capture_dcf_inputs(**source)["inputs"]
    assert inputs["marketCap"] == "60000" and inputs["shares"] == "5000"
    assert inputs["shareSource"]["rawValue"] == "100"
    source["risk_free"]["rate"] = "0.407"
    assert capture_dcf_inputs(**source)["reason"]["subCode"] == "risk_free_unit_mismatch"


def test_constant_risk_free_remains_an_assumption_without_forcing_fallback():
    source = fixture()
    source["risk_free"] = {"rate": "0.032", "source": "constant", "observedAt": None}
    assert replay_dcf(capture_dcf_inputs(**source)["inputs"])["marginOfSafetyJudgment"] == "eligible"
    for risk in [dict(source["risk_free"], source="latest_cache"),
                 {"rate": "0.04", "source": "fred_dgs10", "observedAt": "2026-10-01"},
                 {"rate": "0.04", "source": "fred_dgs10", "observedAt": "2026-08-01"}]:
        source["risk_free"] = risk
        assert capture_dcf_inputs(**source)["status"] == "unavailable"


@pytest.mark.parametrize("risk", [
    {"source": "constant"},
    {"rate": "NaN", "source": "constant"},
    {"rate": "0.04", "source": "fred_dgs10", "observedAt": "2026-09-29"},
    {"rate": "0.04", "source": "fred_dgs10", "observedAt": "2026-09-xx"},
])
def test_incomplete_risk_free_observations_return_unavailable(risk):
    source = fixture()
    source["risk_free"] = risk
    assert capture_dcf_inputs(**source)["status"] == "unavailable"


def test_future_beta_and_changed_projection_are_rejected():
    source = fixture()
    source["beta"]["observedAt"] = "2026-10-01"
    assert capture_dcf_inputs(**source)["reason"]["subCode"] == "future_beta_observation"
    source["beta"].pop("observedAt")
    inputs = capture_dcf_inputs(**source)["inputs"]
    inputs["projectionYears"] = 5
    assert replay_dcf(inputs)["reason"]["subCode"] == "projection_years_mismatch"
