"""Spec-4 hand calculations, boundaries, immutable compatibility and consumer contracts."""
import datetime as dt
from concurrent.futures import CancelledError, ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal as D
from unittest.mock import patch

import pytest

from features.price_scenarios import crosschecks as cc, report, service, store as store_module
from features.price_scenarios.changes import review_rows
from features.price_scenarios.history import sec_history
from features.price_scenarios.ranges import fiscal_years, margin_range
from features.price_scenarios.scenarios import compute, unavailable_results
from features.price_scenarios.store import PriceStore, PriceStoreError
from .snapshot_fixtures import PRICE, make
from .test_scenario_results import closes, history, steady


SUPPORT = {"status": "supported", "reasons": [], "notices": []}


def cash_history(years=range(2020, 2025), ni="100", ocf="120", capex="-20", sbc="10"):
    return history(years, **{"Net Income": lambda y: ni, "Operating Cash Flow": lambda y: ocf,
        "Capital Expenditure": lambda y: capex, "Stock-Based Compensation": lambda y: sbc})


def cash(data=None, **kwargs):
    return cc.cash_conversion(data or cash_history(), kwargs.get("support", SUPPORT), kwargs.get("market", "US"), kwargs.get("session", "2025-03-03"))


@pytest.mark.parametrize("payout", [D(0), D("0.123456789"), D("0.3")])
def test_a_six_rows_use_full_precision_and_sum_exactly_to_stored_irr(payout):
    data, prices = steady(growth=D("1.073456789"), payout=payout, pe=D("12.3456789"))
    results = compute(data, PRICE, fiscal_prices=closes(prices))
    assert len(results["returnParts"]) == 6
    for part, row in zip(results["returnParts"], results["scenarios"]):
        assert (part["label"], part["horizon"]) == (row["label"], row["horizon"])
        assert part["status"] == "available"
        assert sum(D(part[k]) for k in ("growth", "dividend", "rerating")) == D(row["irr"])
        if payout == 0:
            assert part["growth"] == "0.0735" and part["dividend"] == "0.0000"


def test_a_no_rerating_without_pe_rounding_at_payout_zero():
    data, prices = steady(growth=D("1.073456789"), payout=D(0), pe=D("12.3456789"))
    eps = next(r["value"] for r in data["rows"] if r["metric"] == "EPS Diluted" and r["fiscalYear"] == 2024)
    results = compute(data, {**PRICE, "value": str(D(eps)*D("12.3456789"))}, fiscal_prices=closes(prices))
    assert all(r["rerating"] == "0.0000" for r in results["returnParts"])


@pytest.mark.parametrize("boundary", ["above_range", "below_range"])
def test_a_irr_range_keeps_the_explicit_reason(boundary):
    results = {"scenarios": [{"label": "base", "horizon": 5, "status": "available", "irrRange": boundary}]}
    assert cc.return_parts(results, {}, "1")[0]["reason"]["code"] == "irr_" + boundary


def test_a_flat_solver_range_and_inherited_block_reason():
    data, prices = steady()
    results = compute(data, PRICE, fiscal_prices=closes(prices))
    quartiles = {"growth": {k: D(".1") for k in ("p25", "p50", "p75")}, "payout": {"p50": D(".3")}}
    with patch.object(cc, "scenario_irr", return_value="above_range"):
        assert all(r["reason"]["code"] == "flat_irr_out_of_range" for r in cc.return_parts(results, quartiles, PRICE["value"]))
    blocked = unavailable_results("share_event_unknown")
    assert all(r["reason"]["code"] == "share_event_unknown" for r in blocked["returnParts"])
    assert blocked["noGrowth"]["reason"]["code"] == "share_event_unknown"


def normalized(data, session="2025-03-03"):
    ranges, q = margin_range(data)
    return cc.no_growth(data, {**PRICE, "sessionDate": session}, {"netMargin": ranges}, {"netMargin": q})


def test_b_uses_unrounded_margin_and_latest_rps_even_without_recent_eps():
    data = history(range(2020, 2025), **{"Revenue": lambda y: "7", "Net Income": lambda y: "1", "Shares Diluted": lambda y: "3"})
    result = normalized(data)
    assert result["recentEps"] is None and result["marginP50"] == "0.1429" and result["marginN"] == 5
    assert abs(D(result["normEps"]) - D(1)/3) < D("1e-26")
    assert D(result["normEps"]) != D(result["rps0"])*D(result["marginP50"])


@pytest.mark.parametrize("metric", ["Revenue", "Shares Diluted"])
def test_b_missing_latest_input_does_not_fall_back_to_an_earlier_year(metric):
    data, _ = steady()
    data["rows"] = [r for r in data["rows"] if not (r["fiscalYear"] == 2024 and r["metric"] == metric)]
    assert normalized(data)["reason"]["code"] == "non_positive_revenue"


@pytest.mark.parametrize("value", ["0", "-1"])
def test_b_nonpositive_revenue_and_normalized_earnings(value):
    data = history(range(2020, 2025), **{"Revenue": lambda y: "100", "Shares Diluted": lambda y: "10", "Net Income": lambda y: value})
    assert normalized(data)["reason"]["code"] == "non_positive_normalized_earnings"
    for r in data["rows"]:
        if r["metric"] == "Revenue" and r["fiscalYear"] == 2024:
            r["value"] = value
    # A range with enough earlier years reaches the latest-input check.
    data["rows"] += [{**r, "fiscalYear": 2019, "period": {"start": "2019-01-01", "end": "2019-12-31"}} for r in data["rows"] if r["fiscalYear"] == 2020]
    assert normalized(data)["reason"]["code"] == "non_positive_revenue"


def test_b_stale_revenue_has_priority_and_short_margin_samples_block():
    assert normalized(cash_history(), "2026-05-01")["reason"]["code"] == "history_too_short"  # no Revenue row
    data, _ = steady()
    assert normalized(data, "2026-05-01")["reason"]["code"] == "stale_financials"
    short, _ = steady(years=range(2021, 2025))
    assert normalized(short)["reason"]["code"] == "history_too_short"


def test_b_price_event_unverified_still_calculates():
    data, _ = steady()
    result = compute(data, PRICE, fiscal_prices=None)
    assert result["scenarios"][0]["reason"]["code"] == "price_event_unverified"
    assert result["noGrowth"]["status"] == "available"


@pytest.mark.parametrize("required,reason", [(None, "criteria_not_set"), (D(0), "required_return_not_positive"), (D("-.05"), "required_return_not_positive")])
def test_b_projection_criteria_boundaries(required, reason):
    i, r = make(results_patch={"noGrowth": {"status": "available", "normEps": "3"}})
    assert cc.project_no_growth({"inputs": i, "results": r}, required, {"revisionId": 9})["reason"]["code"] == reason


def test_b_projection_fraction_revision_currency_and_unrounded_sentence_branch():
    i, r = make(results_patch={"noGrowth": {"status": "available", "normEps": "3"}})
    result = cc.project_no_growth({"inputs": i, "results": r}, D(".10"), {"revisionId": 9})
    assert result == {"status": "available", "value": "30.00", "growthShare": "0.0000", "priceCoverage": "1.0000", "requiredReturn": "0.1000", "criteriaRevisionId": 9, "hasGrowthShare": False}
    r["noGrowth"]["normEps"] = "2.99999"
    assert cc.project_no_growth({"inputs": i, "results": r}, D(".1"), {"revisionId": 10})["hasGrowthShare"] is True
    i["price"]["currency"] = "KRW"
    r["noGrowth"]["normEps"] = "3.05"
    assert cc.project_no_growth({"inputs": i, "results": r}, D(".1"), {"revisionId": 11})["value"] == "30"  # half even
    r["noGrowth"] = {"status": "unavailable", "reason": {"code": "adr_ratio_unverified"}}
    assert cc.project_no_growth({"inputs": i, "results": r}, None, None)["reason"]["code"] == "adr_ratio_unverified"


def test_c_hand_calculation_preserves_capex_and_negative_sbc_signs():
    result = cash(cash_history(capex="-20", sbc="-10"))
    assert result["years"][0]["capexRaw"] == "-20" and result["years"][0]["capexOut"] == "20"
    assert result["years"][0]["sbc"] == "-10" and result["years"][0]["fcf"] == "110"
    assert result["sumFcf"] == "550" and result["sumNetIncome"] == "500" and result["ratio"] == "1.1000"


def test_c_one_missing_sbc_year_means_none_of_the_years_deduct_it():
    data = cash_history()
    data["rows"] = [r for r in data["rows"] if not (r["metric"] == "Stock-Based Compensation" and r["fiscalYear"] == 2021)]
    result = cash(data)
    assert result["sbcBasis"] == "not_deducted" and result["ratio"] == "1.0000"
    assert all("sbc" not in r for r in result["years"])
    assert result["notices"] == [{"code": "sbc_missing_years", "years": [2021]}]


@pytest.mark.parametrize("ratio,classification", [(".79999", "cash_below_earnings"), (".8", "cash_in_line"), ("1.5", "cash_in_line"), ("1.50001", "cash_above_earnings"), ("-.2", "cash_below_earnings")])
def test_c_classifies_before_rounding(ratio, classification):
    result = cash(cash_history(ocf=str(D(ratio)*100), capex="0", sbc="0"))
    assert result["class"] == classification
    assert result["ratio"] == str(D(ratio).quantize(D(".0001")))


@pytest.mark.parametrize("reason", ["currency_mismatch", "currency_unknown", "share_event_unknown", "price_event_unverified"])
def test_c_limited_per_share_support_does_not_block_raw_reporting_currency(reason):
    data = cash_history()
    data["currency"] = "TWD"
    result = cash(data, support={"status": "limited", "reasons": [{"code": reason}]})
    assert result["status"] == "available" and result["currency"] == "TWD"
    data["currency"] = ""
    assert cash(data)["reason"]["code"] == "currency_unknown"


def test_c_korea_short_history_nonpositive_ni_and_stale_keep_values():
    assert cash(market="KR")["sbcBasis"] == "not_applicable_kr"
    assert cash(market="KR")["ratio"] == "1.0000"
    short = cash(cash_history(years=range(2020, 2024)), session="2026-05-01")
    assert short["reason"]["code"] == "history_too_short" and len(short["years"]) == 4 and short["sumFcf"] == "360"
    assert {"code": "stale_financials"} in short["notices"]
    zero = cash(cash_history(ni="0"))
    assert zero["reason"]["code"] == "net_income_sum_not_positive" and len(zero["years"]) == 5
    assert cash(cash_history(ni="-1"))["reason"]["code"] == "net_income_sum_not_positive"


def test_c_max_ten_matching_years_exclusions_and_latest_ni_stale():
    data = cash_history(years=range(2009, 2025))
    data["excludedYears"] = [{"fiscalYear": 2022, "reason": "non_annual_period"}]
    result = cash(data, session="2026-05-01")
    assert len(result["years"]) == 10 and result["years"][0]["fiscalYear"] == 2014
    assert 2022 not in [r["fiscalYear"] for r in result["years"]]
    assert {"code": "stale_financials"} in result["notices"]
    assert "10개 회계연도" in " ".join(report.cash_lines(result))
    assert cash(support={"status": "unsupported", "reasons": [{"code": "financial_holding"}]})["reason"]["code"] == "financial_holding"


@pytest.mark.parametrize("version", [1, 2, 3])
def test_old_records_read_with_previous_method_and_remain_immutable(tmp_path, monkeypatch, version):
    store = PriceStore(tmp_path / "market-memory.sqlite3")
    i, r = make()
    i.update(methodVersion=f"price-scenario-{version}", specVersion=f"price-scenario-spec-{version}")
    for key in ("returnParts", "noGrowth", "cashConversion"):
        r.pop(key, None)
    with monkeypatch.context() as m:
        m.setattr(store_module, "METHOD_VERSION", i["methodVersion"])
        m.setattr(store_module, "SPEC_VERSION", i["specVersion"])
        saved = store.save_snapshot(i, r)
    before = store.get(saved["snapshotId"])
    content = store.path.read_bytes()
    view = service.snapshot_view(tmp_path, saved["snapshotId"])
    previous = {"status": "not_applicable", "reason": {"code": "previous_method"}}
    assert view["results"]["returnParts"] == view["results"]["cashConversion"] == previous
    assert service.projection_view(tmp_path, saved["snapshotId"])["noGrowth"] == previous
    assert store.get(saved["snapshotId"]) == before and store.path.read_bytes() == content
    with pytest.raises(PriceStoreError, match="method_version_not_writable"):
        store.save_snapshot(i, r)


@pytest.mark.parametrize("old_version,metric,expected", [(3,"EPS Diluted",True),(2,"EPS Diluted",False),(3,"Stock-Based Compensation",False),(4,"Stock-Based Compensation",True)])
def test_cross_version_review_compares_spec3_onward_and_skips_only_sbc(old_version, metric, expected):
    i, r = make()
    i["history"]["rows"].append({"fiscalYear": 2024, "metric": "Stock-Based Compensation", "value": "10", "filed": "2025-02-01", "precision": 0})
    old = {"snapshotId": "old", "inputs": deepcopy(i), "results": r}
    old["inputs"].update(methodVersion=f"price-scenario-{old_version}", specVersion=f"price-scenario-spec-{old_version}")
    new = {"snapshotId": "new", "inputs": deepcopy(i), "results": r}
    for row in new["inputs"]["history"]["rows"]:
        if row["metric"] == metric and row["fiscalYear"] == 2024:
            row["value"] = "100"
    rows = review_rows([old], new)
    assert bool(rows) == expected
    if expected:
        assert rows[0]["snapshotId"] == "old" and rows[0]["metric"] == metric


def test_ifrs_sbc_tag_precedence_cannot_expand_years_periods_exclusions_or_common_candidates():
    from features.company_analysis import sec_companyfacts as sec
    before = deepcopy(sec.IFRS_METRIC_CANDIDATES)
    def fact(year, val, start=None, end=None):
        return {"val": val, "start": start or f"{year}-01-01", "end": end or f"{year}-12-31", "filed": "2026-03-01", "form": "20-F", "accn": str(year)}
    facts = {"Revenue": {"units": {"USD": [fact(y,"100") for y in range(2015,2025)]}},
             "ShareBasedPayments": {"units": {"USD": [fact(2024,"4")]}},
             "AdjustmentsForSharebasedPayments": {"units": {"USD": [fact(y,"10") for y in range(2014,2026)] + [fact(2024,"10",end="2024-11-30"), fact(2026,"1",start="2026-01-01",end="2026-06-30")]}}}
    packet = {"facts": {"ifrs-full": facts}}
    old, new = sec_history(packet, _spec4_sbc=False), sec_history(packet)
    assert sec.IFRS_METRIC_CANDIDATES == before
    assert fiscal_years(old) == fiscal_years(new) and old["excludedYears"] == new["excludedYears"]
    assert [r for r in old["rows"] if r["metric"] != "Stock-Based Compensation"] == [r for r in new["rows"] if r["metric"] != "Stock-Based Compensation"]
    sbc = [r for r in new["rows"] if r["metric"] == "Stock-Based Compensation"]
    assert len(sbc) == 10 and sbc[-1]["value"] == "10" and all(r["fiscalYear"] < 2025 for r in sbc)


def test_a_and_c_are_report_and_cli_only_b_never_enters_either(tmp_path):
    data, prices = steady()
    i, r = make(results_patch={"cashConversion": cash()})
    saved = PriceStore(tmp_path / "market-memory.sqlite3").save_snapshot(i, r)
    view = service.snapshot_view(tmp_path, saved["snapshotId"])
    payload = report.scenario_payload(view)
    assert [(p["label"], p["horizon"]) for p in payload["returnParts"]] == [("base",5),("base",10)]
    assert "noGrowth" not in payload
    for text in (report.render_section(view), report.render_context(view)):
        assert "기본 5년: 이익 성장" in text and "기본 10년: 이익 성장" in text and "순이익 100당" in text
        assert "성장이 없다면" not in text and "성장 없는" not in text and "normEps" not in text
    view["results"]["support"] = {"status": "limited", "reasons": [{"code": "currency_mismatch"}], "notices": []}
    assert "순이익 100당" in report.render_section(view)


def test_ifrs_preexisting_sbc_only_latest_year_cannot_disappear():
    def fact(year, value):
        return {"val": value, "start":f"{year}-01-01", "end":f"{year}-12-31", "filed":"2026-03-01", "form":"20-F", "accn":str(year)}
    packet = {"facts":{"ifrs-full":{
        "Revenue":{"units":{"USD":[fact(y,"100") for y in range(2015,2025)]}},
        "ShareBasedPayments":{"units":{"USD":[fact(2025,"4")]}},
        "AdjustmentsForSharebasedPayments":{"units":{"USD":[fact(2024,"10")]}}
    }}}
    old, new = sec_history(packet,_spec4_sbc=False), sec_history(packet)
    assert fiscal_years(old) == fiscal_years(new) == list(range(2016,2026))
    assert old["excludedYears"] == new["excludedYears"]
    assert next(r for r in new["rows"] if r["fiscalYear"] == 2025)["value"] == "4"


def test_attempt_writes_for_different_instruments_are_atomic_as_one_map(tmp_path):
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda n: service._write_attempt(tmp_path, f"US:A{n}", {"status": "saved", "snapshotId": str(n)}), range(40)))
    assert all(service.read_attempt(tmp_path, f"US:A{n}")["snapshotId"] == str(n) for n in range(40))


@pytest.mark.parametrize("error", [RuntimeError("cancelled"), CancelledError()])
def test_caller_report_cancellation_leaves_no_snapshot_or_failed_attempt(tmp_path, error):
    def cancel():
        raise error
    with pytest.raises((RuntimeError, CancelledError)):
        service.calculate(tmp_path, "US:ACME", cancel_check=cancel)
    assert service.overview(tmp_path,"US:ACME")["latest"] is None
    assert service.read_attempt(tmp_path,"US:ACME") is None


def test_report_adapter_passes_cancellation_into_actual_calculator(tmp_path):
    seen = {}
    def cancel():
        pass
    def calculator(root, instrument, **kwargs):
        seen.update(kwargs)
        raise CancelledError()
    with pytest.raises(CancelledError):
        service.snapshot_for_report(tmp_path, {"market":"US", "ticker":"ACME"}, calculator=calculator, cancel=cancel)
    assert seen["cancel_check"] is cancel


@pytest.mark.parametrize("ticker", ["005930", "0123A0"])
def test_korean_alphanumeric_codes_remain_explicitly_korean(ticker):
    assert service.parse_instrument(f"KR:{ticker}") == ("KR", ticker)
    from features.price_scenarios.prices import provider_symbol
    assert provider_symbol(ticker, "KR", {"corp_cls": "Y"})[0] == ticker + ".KS"


def test_cross_version_review_reaches_old_report_marker_without_mutating_body(tmp_path, monkeypatch):
    store = PriceStore(tmp_path / "market-memory.sqlite3")
    i, r = make()
    old_i, old_r = deepcopy(i), deepcopy(r)
    old_i.update(methodVersion="price-scenario-3", specVersion="price-scenario-spec-3")
    for key in ("returnParts", "noGrowth", "cashConversion"):
        old_r.pop(key, None)
    with monkeypatch.context() as m:
        m.setattr(store_module,"METHOD_VERSION","price-scenario-3")
        m.setattr(store_module,"SPEC_VERSION","price-scenario-spec-3")
        old = store.save_snapshot(old_i,old_r)
    before = deepcopy(store.get(old["snapshotId"]))
    for row in i["history"]["rows"]:
        if row["metric"] == "EPS Diluted" and row["fiscalYear"] == 2024:
            row["value"] = "10"
    saved = store.save_snapshot(i,r)
    marker = service.review_marker(tmp_path,old["snapshotId"])
    assert marker["reviewNeeded"][0]["detectedBySnapshotId"] == saved["snapshotId"]
    assert marker["reviewNeeded"][0]["metric"] == "EPS Diluted"
    assert store.get(old["snapshotId"]) == before


def test_actual_cli_context_assembler_does_not_swallow_price_cancellation():
    from contextlib import ExitStack
    from features.company_analysis import generation_context as context
    from features.company_analysis.tests.test_generation_paths import _stubbed
    def provider(company, *, cancel):
        cancel()
        raise RuntimeError("price_calculation_cancelled")
    with ExitStack() as stack:
        for stub in _stubbed():
            stack.enter_context(stub)
        with pytest.raises(RuntimeError, match="price_calculation_cancelled"):
            context.build_generation_inputs("ACME", runtime={"price_snapshot_for_report": provider}, cancel=lambda: None)
