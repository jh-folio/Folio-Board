import datetime as dt
from decimal import Decimal
import pytest

from features.company_analysis import risk_free as risk
from features.price_scenarios.history import dart_history, dart_dividend_history, sec_history
from features.price_scenarios.support import dart_classification, classify


def test_fred_asof_selects_price_session_without_latest_cache_or_writes(monkeypatch):
    monkeypatch.setattr(risk, "_fetch_fred_as_of", lambda key, day: [
        {"date": "2026-09-30", "value": "4.070"},
        {"date": "2026-10-02", "value": "5.2"},
        {"date": "2026-10-01", "value": "."},
    ])
    monkeypatch.setattr(risk, "_fetch_tnx_as_of", lambda _: pytest.fail("FRED observation already available"))
    monkeypatch.setattr(risk, "_write_cache", lambda _: pytest.fail("snapshot query must not write legacy cache"))
    row = risk.risk_free_as_of("2026-10-01", api_key="fixture")
    assert row == {"rate": "0.0407", "source": "fred_dgs10", "observedAt": "2026-09-30",
                   "rawObservation": {"value": "4.070", "unit": "percent"}}


def test_stale_fred_moves_to_tnx_with_percent_divided_by_100(monkeypatch):
    monkeypatch.setattr(risk, "_fetch_fred_as_of", lambda *_: [{"date": "2026-09-01", "value": "4.2"}])
    monkeypatch.setattr(risk, "_fetch_tnx_as_of", lambda _: [{"date": "2026-09-30", "value": "4.07"}])
    row = risk.risk_free_as_of("2026-10-01", api_key="fixture")
    assert row["rate"] == "0.0407" and row["source"] == "yfinance_tnx"


def test_stale_or_failed_sources_use_explicit_constant(monkeypatch):
    def failure(*_):
        raise RuntimeError("fixture")
    monkeypatch.setattr(risk, "_fetch_fred_as_of", failure)
    monkeypatch.setattr(risk, "_fetch_tnx_as_of", lambda _: [{"date": "2026-09-01", "value": "4.2"}])
    row = risk.risk_free_as_of("2026-10-01", api_key="fixture")
    assert row["source"] == "constant" and row["observedAt"] is None
    assert Decimal(row["rate"]) == Decimal("0.042")
    assert risk.risk_free_as_of("2026-10-01", "KRW")["rate"] == "0.032"
    with pytest.raises(ValueError):
        risk.risk_free_as_of("2026-10-01", "")


def test_historical_age_boundary_counts_weekdays_and_filters_nonfinite():
    rows = [{"date": "2026-09-17", "value": "4.07"}, {"date": "2026-09-30", "value": "NaN"}]
    assert risk._historical_observation(rows, "2026-10-01", "fred_dgs10") is not None
    assert risk._historical_observation(rows, "2026-10-02", "fred_dgs10") is None


def test_fred_request_has_observation_end_and_timeout(monkeypatch):
    import requests
    captured = {}
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {"observations": [{"date": "2020-01-02", "value": "1.88"}]}
    def get(url, **kwargs):
        captured.update(kwargs)
        return Response()
    monkeypatch.setattr(requests, "get", get)
    assert risk._fetch_fred_as_of("fixture", "2020-01-02")
    assert captured["params"]["observation_end"] == "2020-01-02"
    assert captured["timeout"] == 8.0


def test_measured_dart_capex_tags_and_ofs_profit_are_kept():
    base = {"currency": "KRW", "rcept_no": "20260301000001", "reprt_code": "11011"}
    rows = [{**base, "account_id": "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "thstrm_amount": "15"},
            {**base, "account_id": "ifrs-full_ProfitLoss", "thstrm_amount": "30"}]
    batch = {"basis": "OFS", "periodEnd": "2025-12-31", "rows": rows}
    result = dart_history([batch])
    assert {r["metric"] for r in result["rows"]} == {"Capital Expenditure", "Net Income"}
    assert next(r for r in result["rows"] if r["metric"] == "Capital Expenditure")["value"] == "15"
    assert {r["metric"] for r in dart_history([{**batch, "basis": "CFS"}])["rows"]} == {"Capital Expenditure"}


def test_ifrs_dilution_uses_adjusted_weighted_shares_not_basic_shares():
    fact = {"val": "50", "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-02-01", "form": "20-F"}
    data = {"facts": {"ifrs-full": {"AdjustedWeightedAverageShares": {"units": {"shares": [fact]}},
                                  "WeightedAverageShares": {"units": {"shares": [{**fact, "val": "40"}]}},
                                  "Revenue": {"units": {"USD": [fact]}}}}}
    shares = [row for row in sec_history(data)["rows"] if row["metric"] == "Shares Diluted"]
    assert len(shares) == 1 and shares[0]["value"] == "50"
    assert shares[0]["concept"] == "ifrs-full:AdjustedWeightedAverageShares"


def test_common_dividend_zero_missing_preferred_and_comparative_revision():
    common = {"stock_knd": "보통주", "se": "주당 현금배당금(원)", "rcept_no": "20260301000001",
              "stlm_dt": "2025-03-31", "thstrm": "0", "frmtrm": "101", "lwfr": "-"}
    older = {**common, "rcept_no": "20250301000001", "stlm_dt": "2024-03-31", "thstrm": "100", "frmtrm": "-"}
    result = dart_dividend_history([{"status": "000", "list": [older]},
                                   {"status": "000", "list": [common, {**common, "stock_knd": "우선주", "thstrm": "999"}]}])
    by_year = {row["fiscalYear"]: row for row in result["rows"]}
    assert by_year[2025]["value"] == "0"
    assert by_year[2024]["value"] == "101" and by_year[2024]["priorValues"][0]["value"] == "100"
    assert 2023 not in by_year


def test_holding_exception_is_proven_by_official_income_accounts():
    metadata = {"induty_code": "64992", "stock_code": "105560"}
    insurance = [{"sj_div": "CIS", "ord": "11", "account_id": "dart_OperatingIncomeInsurance"}]
    kb = dart_classification(metadata, insurance, ticker="105560")
    assert kb["financialHolding"] is True
    assert kb["accountEvidence"]["firstFinancialIncome"] == "dart_OperatingIncomeInsurance"
    assert classify({"market": "KR"}, kb, reporting_currency="KRW", quote_currency="KRW", share_unit_status="compatible")["reasons"] == [{"code": "financial_holding"}]
    sk = dart_classification({**metadata, "stock_code": "034730"}, insurance + [
        {"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액"}], ticker="034730")
    assert sk["financialHolding"] is False
    assert dart_classification(metadata, insurance, ticker="105565")["listedSecurity"]["kind"] == "unknown"
