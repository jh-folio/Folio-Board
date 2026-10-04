"""Coverage revision: failure reasons, boundaries and restricted provider calls."""
from concurrent.futures import CancelledError
from copy import deepcopy
import pytest

from features.price_scenarios import ranges
from features.price_scenarios.collect import Collector, CollectionError
from features.price_scenarios.prices import provider_failure
from features.price_scenarios.report import reason_text
from features.price_scenarios.scenarios import compute
from features.price_scenarios.support import classify
from .test_scenario_results import steady, closes
from .test_collect import collector, sec, NOW


def calculation(data, prices, *, prices_reason=None):
    return compute(data, {"sessionDate": "2026-10-01", "value": "20"},
                   fiscal_prices=closes(prices) if prices_reason is None else None, prices_reason=prices_reason)


@pytest.mark.parametrize("eps", ["0", "-1"])
def test_nonpositive_base_precedes_short_history_and_price_range(eps):
    data, prices = steady(range(2024, 2026))
    for row in data["rows"]:
        if row["metric"] == "EPS Diluted" and row["fiscalYear"] == 2025:
            row["value"] = eps
    out = calculation(data, prices, prices_reason={"code": "price_event_unverified"})
    assert {r["reason"]["code"] for r in out["scenarios"]} == {"negative_base_eps"}
    assert out["reverse"]["breakEvenPE"]["5"]["reason"] == {"code": "negative_base_eps"}
    assert out["reverse"]["sensitivity"]["reason"] == {"code": "negative_base_eps"}
    assert all(r["reason"] == {"code": "negative_base_eps"} for r in out["returnParts"])
    # The revenue-based reverse path keeps the earlier price-range guard.
    assert out["reverse"]["breakEvenMargin"]["5"]["reason"]["code"] == "price_event_unverified"


def test_short_span_counts_and_all_reason_consumers():
    data, prices = steady(range(2023, 2026))
    out = calculation(data, prices)
    expected = {"code": "history_too_short", "subCode": "years_too_few", "range": "growth",
                "n": 0, "required": 3, "historyYears": 3}
    assert out["ranges"]["growth"]["reason"] == expected
    assert all(r["reason"] == expected for r in out["scenarios"] + out["returnParts"])
    assert out["reverse"]["sensitivity"]["reason"] == expected
    assert reason_text(expected) == "재무 기록이 3년뿐이라 비교할 5년 구간이 0개입니다(필요 3개). 연속 기록이라면 최소 8년이 필요합니다"


def test_eight_year_span_with_loss_is_not_seven_years():
    data, prices = steady(range(2018, 2026))
    for row in data["rows"]:
        if row["metric"] == "EPS Diluted" and row["fiscalYear"] == 2018:
            row["value"] = "-1"
    out = calculation(data, prices)
    assert out["scenarios"][0]["reason"] == {"code": "history_too_short", "subCode": "loss_years",
        "range": "growth", "n": 2, "required": 3, "historyYears": 8}


def test_five_year_span_with_metric_gap_and_other_dominant_cause():
    data, prices = steady(range(2021, 2026))
    data["rows"] = [r for r in data["rows"] if not (r["metric"] == "EPS Diluted" and r["fiscalYear"] == 2022)]
    pe = ranges.explain_short_history(ranges.pe_range(data, closes(prices))[0], "pe", data)
    assert pe["reason"]["subCode"] == "missing_years"
    assert pe["reason"]["n"] == 4 and pe["reason"]["required"] == 5
    block = {"reason": {"code": "history_too_short"}, "n": 2, "required": 5,
             "excluded": [{"reason": r} for r in ["missing_value", "non_positive_eps", "payout_out_of_range"]]}
    assert "subCode" not in ranges.explain_short_history(block, "payout", data)["reason"]
    block["excluded"].pop()
    assert ranges.explain_short_history(block, "payout", data)["reason"]["subCode"] == "loss_years"


def test_base_missing_and_stale_are_preserved_before_negative_eps():
    data, prices = steady(range(2018, 2026))
    data["rows"] = [r for r in data["rows"] if not (r["metric"] == "EPS Diluted" and r["fiscalYear"] == 2025)]
    assert calculation(data, prices)["scenarios"][0]["reason"]["code"] == "base_eps_missing"
    data, prices = steady(range(2015, 2024))
    data["rows"] = [dict(r, value="-1") if r["metric"] == "EPS Diluted" else r for r in data["rows"]]
    assert calculation(data, prices)["scenarios"][0]["reason"]["code"] == "stale_financials"


def test_fund_wins_over_financial_holding():
    out = classify({"market": "US"}, {"code": "6719", "financialHolding": True, "quoteType": "ETF"},
                   reporting_currency="USD", quote_currency="USD")
    assert out == {"status": "unsupported", "reasons": [{"code": "fund_not_supported"}], "notices": []}


@pytest.mark.parametrize("kind,code", [("ETF", "fund_not_supported"), (None, "company_not_found"), ("EQUITY", "company_not_found")])
def test_kind_probe_only_on_missing_cik(tmp_path, sec, monkeypatch, kind, code):
    from features.price_scenarios import collect
    seen = []
    made, _ = collector(tmp_path)
    made.instrument_type = lambda symbol: seen.append(symbol) or kind
    made.collect("US", "AAPL")
    assert seen == []
    monkeypatch.setattr(collect.sec_companyfacts, "resolve_cik", lambda *args: "")
    with pytest.raises(CollectionError) as error:
        made.collect("US", "SGOV")
    assert error.value.code == code and seen == ["SGOV"]


def test_transport_failure_and_internal_error_differ_and_cancel_survives(tmp_path, sec):
    for failure, sub in [(TimeoutError(), "provider_error"), (TypeError(), None), (ValueError("price_unavailable"), "price_unavailable")]:
        def broken(*args, **kwargs):
            raise failure
        made = Collector(tmp_path, now=NOW, sec_bytes=lambda url: b"{}", fetch_daily=broken)
        with pytest.raises(CollectionError) as error:
            made.collect("US", "AAPL")
        assert error.value.sub_code == sub
    made.fetch_daily = lambda *args, **kwargs: (_ for _ in ()).throw(CancelledError())
    with pytest.raises(CancelledError):
        made.collect("US", "AAPL")
    assert not provider_failure(TypeError())
    assert reason_text({"code": "price_unavailable", "subCode": "provider_error"}) == "가격 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요"
