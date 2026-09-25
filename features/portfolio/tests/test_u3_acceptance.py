"""Independent U.3 mathematical and non-mutating acceptance fixtures."""
import json
import math

import pytest
from fastapi import HTTPException

from features.portfolio import service
from features.portfolio import backtest_analysis


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "BACKTESTS_DIR", tmp_path / "backtests")
    monkeypatch.setattr(service, "PORTFOLIO_PRESETS_PATH", tmp_path / "presets.json")
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker: {"ticker": ticker, "symbol": ticker, "currency": "USD", "name": ticker})
    monkeypatch.setattr(service, "_fx_series_for_currencies", lambda *a, **k: {})
    preset = {"id": "core", "name": "Core", "baseCurrency": "USD", "positions": [{"ticker": "AAPL", "symbol": "AAPL", "currency": "USD", "weight": 1}]}
    monkeypatch.setattr(service, "get_portfolio_preset", lambda identifier: preset if identifier == "core" else None)
    prices = {"2024-01-30": 100., "2024-01-31": 110., "2024-02-01": 99., "2024-02-02": 120.}
    monkeypatch.setattr(service, "_download_adjusted_close", lambda *a, **k: (dict(prices), {"provider": "fixture"}))
    return tmp_path


def test_rebalance_does_not_erase_boundary_day_profit():
    rows = [{"date": "2024-01-31", "A": 100}, {"date": "2024-02-01", "A": 110}, {"date": "2024-02-02", "A": 121}]
    result = service._run_weight_backtest(rows, {"A": 1}, 1000, "monthly")
    assert [r["value"] for r in result] == pytest.approx([1000, 1100, 1210])


def test_two_asset_rebalance_marks_both_holdings_before_reallocating():
    rows = [{"date": "2024-01-31", "A": 100, "B": 100}, {"date": "2024-02-01", "A": 200, "B": 100}, {"date": "2024-02-02", "A": 100, "B": 100}]
    result = service._run_weight_backtest(rows, {"A": .5, "B": .5}, 1000, "monthly")
    assert [r["value"] for r in result] == pytest.approx([1000, 1500, 1125])


@pytest.mark.parametrize("frequency", ["none", "monthly", "quarterly", "yearly"])
def test_single_asset_result_is_rebalance_invariant(frequency):
    rows = [{"date": "2023-12-29", "A": 100}, {"date": "2024-01-02", "A": 80}, {"date": "2024-04-01", "A": 120}]
    result = service._run_weight_backtest(rows, {"A": 1}, 1234.5, frequency)
    assert result[-1]["value"] == pytest.approx(1481.4)


@pytest.mark.parametrize("period", ["month", "year"])
def test_period_boundary_compounds_to_total_return(period):
    values = [{"date": "2023-12-28", "value": 100}, {"date": "2023-12-29", "value": 110}, {"date": "2024-01-02", "value": 99}, {"date": "2024-02-01", "value": 120}]
    rows = service._period_returns(values, period)
    assert math.prod(1 + row["return"] for row in rows) == pytest.approx(1.2)
    if period == "month":
        assert rows[1]["return"] == pytest.approx(-.1)
        assert rows[2]["return"] == pytest.approx(120 / 99 - 1)


def test_return_pairs_do_not_mix_one_and_two_day_intervals():
    portfolio = [{"date": "2024-01-01", "value": 100}, {"date": "2024-01-02", "value": 110}, {"date": "2024-01-03", "value": 121}, {"date": "2024-01-04", "value": 133.1}]
    benchmark = [{"date": "2024-01-01", "value": 100}, {"date": "2024-01-03", "value": 121}, {"date": "2024-01-04", "value": 133.1}]
    pairs = service._aligned_return_pairs(portfolio, benchmark)
    assert pairs
    assert all(p == pytest.approx(b) for p, b in pairs)


def test_run_is_unsaved_and_keeps_authority_bytes(isolated):
    authority = isolated / "portfolio.json"
    authority.write_bytes(b'{"revision":7,"positions":[],"cash":[]}')
    result = service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-02-03", "initialValue": 1000, "benchmark": "SPY", "rebalance": "monthly"})
    assert result["series"][-1]["value"] == pytest.approx(1200)
    assert result["metrics"]["totalReturn"] == pytest.approx(.2)
    assert result["analysisVersion"] == "u3-v1"
    assert not service.BACKTESTS_DIR.exists()
    assert authority.read_bytes() == b'{"revision":7,"positions":[],"cash":[]}'
    json.dumps(result, allow_nan=False)
    assert {"bestYear", "worstYear", "positiveYearRatio", "worstMonth", "var95", "cvar95", "alpha", "beta"} <= result["metrics"].keys()
    assert "return" in result["assetContributions"][0]


def test_legacy_saved_read_is_byte_immutable(isolated):
    service.BACKTESTS_DIR.mkdir()
    path = service.BACKTESTS_DIR / "legacy.json"
    raw = b'{"id":"legacy","name":"old","metrics":{"totalReturn":0.1},"series":[],"custom":"keep"}'
    path.write_bytes(raw)
    assert service.get_portfolio_backtest("legacy")["custom"] == "keep"
    service.list_portfolio_backtests()
    assert path.read_bytes() == raw


def test_missing_asset_cannot_silently_become_a_partial_portfolio(isolated, monkeypatch):
    monkeypatch.setattr(service, "_download_adjusted_close", lambda *a, **k: ({}, {"provider": "fixture"}))
    with pytest.raises(HTTPException):
        service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-02-03"})
    assert not service.BACKTESTS_DIR.exists()


@pytest.mark.parametrize("initial", [0, -1, "NaN", "Infinity"])
def test_invalid_initial_value_rejected_before_price_requests(isolated, monkeypatch, initial):
    def forbidden(*a, **k):
        pytest.fail("invalid initial value reached provider")
    monkeypatch.setattr(service, "_download_adjusted_close", forbidden)
    with pytest.raises(HTTPException):
        service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-02-03", "initialValue": initial})


def test_fx_asof_uses_intervening_observation_without_future_lookahead():
    prices = {"2024-01-02": 100, "2024-01-06": 100}
    rates = {"JPY": {"2024-01-02": 100, "2024-01-03": 125, "2024-01-07": 200}}
    converted = service._convert_price_series(prices, "JPY", "USD", rates)
    assert converted == pytest.approx({"2024-01-02": 1., "2024-01-06": .8})


def test_one_return_is_insufficient_for_sample_volatility():
    metrics = service._portfolio_metrics([{"date": "2024-01-01", "value": 100}, {"date": "2024-01-02", "value": 110}])
    assert metrics["volatility"] is None
    assert metrics["sharpe"] is None


def test_paired_alpha_ignores_earlier_unpaired_portfolio_gain():
    portfolio = [{"date": "2024-01-01", "value": 50}, {"date": "2024-01-02", "value": 100}, {"date": "2024-01-03", "value": 110}, {"date": "2024-01-04", "value": 99}]
    metrics = service._portfolio_metrics(portfolio, portfolio[1:])
    assert metrics["beta"] == pytest.approx(1)
    assert metrics["alpha"] == pytest.approx(0, abs=1e-10)
    assert metrics["excessReturn"] is None or metrics["excessReturn"] == pytest.approx(0, abs=1e-10)


def test_drawdown_distinguishes_recovered_and_open_episodes():
    values = [{"date": date, "value": value} for date, value in [("2024-01-01", 100), ("2024-01-02", 80), ("2024-01-05", 90), ("2024-01-08", 100), ("2024-01-09", 110), ("2024-01-10", 99)]]
    points, episodes = backtest_analysis.drawdown_analysis(values)
    assert [r["drawdown"] for r in points] == pytest.approx([0, -.2, -.1, 0, 0, -.1])
    assert len(episodes) == 2
    assert episodes[0]["peakDate"] == "2024-01-01"
    assert episodes[0]["troughDate"] == "2024-01-02"
    assert episodes[0]["recoveryDate"] == "2024-01-08"
    assert episodes[0]["calendarDaysToRecovery"] == 7
    assert episodes[0]["underwaterTradingDays"] == 2
    assert episodes[1]["status"] == "unrecovered"
    assert episodes[1]["recoveryDate"] is None


def test_single_run_contributions_reconcile_after_rebalance(isolated, monkeypatch):
    preset = {"id": "core", "name": "Core", "baseCurrency": "USD", "positions": [{"ticker": symbol, "symbol": symbol, "currency": "USD", "weight": .5} for symbol in ["AAPL", "MSFT"]]}
    monkeypatch.setattr(service, "get_portfolio_preset", lambda _: preset)
    series = {"AAPL": {"2024-01-31": 100, "2024-02-01": 200, "2024-02-02": 100}, "MSFT": {"2024-01-31": 100, "2024-02-01": 100, "2024-02-02": 100}, "SPY": {"2024-01-31": 100, "2024-02-01": 100, "2024-02-02": 100}}
    monkeypatch.setattr(service, "_download_adjusted_close", lambda symbol, *a, **k: (series[symbol], {}))
    result = service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-02-03", "initialValue": 1000, "rebalance": "monthly"})
    assert result["series"][-1]["value"] == pytest.approx(1125)
    assert sum(r["contributionAmount"] for r in result["assetContributions"]) == pytest.approx(125)
    assert sum(r["contribution"] for r in result["assetContributions"]) == pytest.approx(.125)


def test_coverage_counts_carry_from_before_simulation_start():
    coverage = service._series_coverage({"2024-01-01": 100, "2024-01-04": 110}, ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    assert coverage["observedDays"] == 1
    assert coverage["forwardFilledDays"] == 3
    assert coverage["trailingForwardFilledDays"] == 1
    assert coverage["coverage"] == pytest.approx(.25)


def test_benchmark_asof_uses_prior_and_intervening_dates():
    rows = service._series_on_dates({"2024-01-01": 100, "2024-01-03": 120, "2024-01-05": 130}, ["2024-01-02", "2024-01-04", "2024-01-05"])
    assert [row["date"] for row in rows] == ["2024-01-02", "2024-01-04", "2024-01-05"]
    assert [row["value"] for row in rows] == pytest.approx([100, 120, 130])


def test_mixed_market_holiday_still_marks_foreign_exchange(isolated, monkeypatch):
    positions = [{"ticker": "7203.T", "symbol": "7203.T", "currency": "JPY", "weight": .5}, {"ticker": "AAPL", "symbol": "AAPL", "currency": "USD", "weight": .5}]
    monkeypatch.setattr(service, "get_portfolio_preset", lambda _: {"id": "core", "name": "Mixed", "baseCurrency": "USD", "positions": positions})
    fx = {"JPY": {"2024-01-02": 100, "2024-01-03": 200, "2024-01-04": 200}}
    monkeypatch.setattr(service, "_fx_series_for_currencies", lambda *a, **k: fx)
    series = {"7203.T": {"2024-01-02": 100, "2024-01-04": 100}, "AAPL": {"2024-01-02": 100, "2024-01-03": 100, "2024-01-04": 100}, "SPY": {"2024-01-02": 100, "2024-01-03": 100, "2024-01-04": 100}}
    monkeypatch.setattr(service, "_download_adjusted_close", lambda symbol, *a, **k: (series[symbol], "fixture"))
    result = service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-01-05", "initialValue": 1000, "rebalance": "none"})
    assert [r["value"] for r in result["series"]] == pytest.approx([1000, 750, 750])
    foreign = next(row for row in result["dataCoverage"]["positions"] if row["ticker"] == "7203.T")
    assert foreign["price"]["observedDays"] == 2
    assert foreign["price"]["forwardFilledDays"] == 1


def test_run_benchmark_uses_prior_observations_on_asset_calendar(isolated, monkeypatch):
    series = {
        "AAPL": {"2024-01-02": 100, "2024-01-04": 100, "2024-01-05": 100},
        "SPY": {"2024-01-01": 100, "2024-01-03": 120, "2024-01-05": 130},
    }
    monkeypatch.setattr(service, "_download_adjusted_close", lambda symbol, *a, **k: (series[symbol], "fixture"))
    result = service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-01-06", "initialValue": 1000, "benchmark": "SPY"})
    assert result["benchmarkComparison"]["status"] == "comparable"
    assert [row["date"] for row in result["benchmarkSeries"]] == ["2024-01-02", "2024-01-04", "2024-01-05"]
    assert [row["value"] for row in result["benchmarkSeries"]] == pytest.approx([1000, 1200, 1300])


def test_run_comparable_benchmark_risk_is_not_portfolio_risk(isolated, monkeypatch):
    dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    series = {"AAPL": dict(zip(dates, [100, 105, 110, 120])), "SPY": dict(zip(dates, [100, 80, 90, 95]))}
    monkeypatch.setattr(service, "_download_adjusted_close", lambda symbol, *a, **k: (series[symbol], "fixture"))
    result = service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-01-06", "initialValue": 1000, "benchmark": "SPY"})
    expected = service._portfolio_metrics(result["benchmarkSeries"])
    for metric in ["Volatility", "MaxDrawdown", "Sharpe"]:
        assert result["metrics"]["benchmarkComparable" + metric] == pytest.approx(expected[metric[0].lower() + metric[1:]])
    assert result["metrics"]["benchmarkComparableMaxDrawdown"] == pytest.approx(-.2)
    assert result["metrics"]["maxDrawdown"] == pytest.approx(0)
    coverage = result["dataCoverage"]["benchmark"]
    assert coverage["ticker"] == "SPY"
    assert coverage["price"]["observedDays"] == 4
    assert coverage["fx"]["required"] is False


def test_metrics_wrapper_extreme_growth_never_crashes_or_serializes_infinity():
    values = [{"date": "2024-01-02", "value": 100}, {"date": "2024-01-03", "value": 1e20}]
    metrics = service._portfolio_metrics(values)
    assert metrics["cagr"] is None
    assert metrics["metricUnavailableReasons"].get("cagr")
    json.dumps(metrics, allow_nan=False)


def test_explicit_saved_summary_retains_all_identifying_conditions(isolated):
    result = service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-02-03", "initialValue": 1234, "benchmark": "SPY", "rebalance": "quarterly"})
    service.save_portfolio_backtest_result(result)
    saved_path = service.BACKTESTS_DIR / (result["id"] + ".json")
    before = saved_path.read_bytes()
    summary = service.list_portfolio_backtests()[0]
    assert summary["initialValue"] == 1234
    assert summary["rebalance"] == "quarterly"
    assert summary["benchmark"]["ticker"] == "SPY"
    assert summary["baseCurrency"] == "USD"
    assert saved_path.read_bytes() == before


@pytest.mark.parametrize("initial,price", [(1e-323, 100), (1e308, .001)])
def test_unrepresentable_initial_shares_fail_without_fabricated_result(isolated, monkeypatch, initial, price):
    series = {"2024-01-02": price, "2024-01-03": price, "2024-01-04": price}
    monkeypatch.setattr(service, "_download_adjusted_close", lambda *a, **k: (series, "fixture"))
    with pytest.raises(HTTPException) as failure:
        service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-01-05", "initialValue": initial})
    assert failure.value.status_code in (400, 422)
    assert not service.BACKTESTS_DIR.exists()


@pytest.mark.parametrize("initial,prices", [(1., [1., 1e200, 1e200]), (1e-200, [1e-200, 1e200, 1e200])])
def test_unrepresentable_downstream_analysis_fails_explicitly(isolated, monkeypatch, initial, prices):
    series = dict(zip(["2024-01-02", "2024-01-03", "2024-01-04"], prices))
    monkeypatch.setattr(service, "_download_adjusted_close", lambda *a, **k: (series, "fixture"))
    with pytest.raises(HTTPException) as failure:
        service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-01-05", "initialValue": initial})
    assert failure.value.status_code == 422
    assert not service.BACKTESTS_DIR.exists()


@pytest.mark.parametrize("helper", ["_actual_asset_contributions", "_asset_risk_contributions", "_rolling_metrics"])
def test_each_analysis_branch_translates_arithmetic_failure_to_422(isolated, monkeypatch, helper):
    def overflow(*args, **kwargs):
        raise OverflowError("fixture derived arithmetic overflow")
    monkeypatch.setattr(service, helper, overflow)
    with pytest.raises(HTTPException) as failure:
        service.run_portfolio_backtest({"presetId": "core", "start": "2024-01-01", "end": "2024-02-03", "initialValue": 1000})
    assert failure.value.status_code == 422
    assert failure.value.detail["code"] == "backtest_calculation_limit"
    assert not service.BACKTESTS_DIR.exists()
