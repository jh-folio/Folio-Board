"""Run-level regressions owned by the U.3 backend implementation."""
from __future__ import annotations

import json

import pytest

from features.portfolio import service


def _install_run(monkeypatch, prices):
    preset = {
        "id": "u3", "name": "U3", "baseCurrency": "USD",
        "positions": [{"ticker": "ASSET", "symbol": "ASSET", "currency": "USD", "weight": 1.0}],
    }
    monkeypatch.setattr(service, "get_portfolio_preset", lambda identifier: preset if identifier == "u3" else None)
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker: {"ticker": ticker, "symbol": ticker, "currency": "USD", "name": ticker})
    monkeypatch.setattr(service, "_fx_series_for_currencies", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_download_adjusted_close", lambda symbol, *args, **kwargs: (prices[symbol], "fixture"))


def test_run_benchmark_carries_sparse_native_prices_as_of_simulation_dates(monkeypatch):
    _install_run(monkeypatch, {
        "ASSET": {"2024-01-02": 100.0, "2024-01-04": 100.0, "2024-01-05": 100.0},
        "SPY": {"2024-01-01": 100.0, "2024-01-03": 120.0, "2024-01-05": 130.0},
    })
    result = service.run_portfolio_backtest({"presetId": "u3", "start": "2024-01-01", "end": "2024-01-06", "initialValue": 1000, "benchmark": "SPY"})
    assert [row["value"] for row in result["benchmarkSeries"]] == pytest.approx([1000, 1200, 1300])
    assert result["benchmarkComparison"]["status"] == "comparable"


def test_run_keeps_benchmark_risk_statistics_separate_from_portfolio(monkeypatch):
    _install_run(monkeypatch, {
        "ASSET": {"2024-01-02": 100.0, "2024-01-03": 120.0, "2024-01-04": 100.0},
        "SPY": {"2024-01-02": 100.0, "2024-01-03": 100.0, "2024-01-04": 100.0},
    })
    result = service.run_portfolio_backtest({"presetId": "u3", "start": "2024-01-01", "end": "2024-01-05", "initialValue": 1000, "benchmark": "SPY"})
    assert result["metrics"]["benchmarkComparableVolatility"] == 0.0
    assert result["metrics"]["benchmarkComparableMaxDrawdown"] == 0.0
    assert result["metrics"]["volatility"] > 0.0


def test_benchmark_only_fx_failure_does_not_abort_a_usd_portfolio_run(monkeypatch):
    _install_run(monkeypatch, {
        "ASSET": {"2024-01-02": 100.0, "2024-01-03": 110.0, "2024-01-04": 120.0},
        "7203.T": {"2024-01-02": 100.0, "2024-01-03": 110.0, "2024-01-04": 120.0},
    })
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker: {
        "ticker": ticker, "symbol": ticker, "currency": "JPY" if ticker == "7203.T" else "USD", "name": ticker,
    })
    def fx(currencies, *args, **kwargs):
        if "JPY" in currencies:
            raise RuntimeError("benchmark FX unavailable")
        return {}
    monkeypatch.setattr(service, "_fx_series_for_currencies", fx)
    result = service.run_portfolio_backtest({"presetId": "u3", "start": "2024-01-01", "end": "2024-01-05", "initialValue": 1000, "benchmark": "7203.T"})
    assert result["series"][-1]["value"] == pytest.approx(1200)
    assert result["benchmarkComparison"]["status"] == "unavailable"
    assert result["benchmarkComparison"]["reason"] == "benchmark_data_unavailable"


def test_saved_list_projects_backtest_conditions_without_rewriting_legacy_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "BACKTESTS_DIR", tmp_path / "backtests")
    service.BACKTESTS_DIR.mkdir()
    path = service.BACKTESTS_DIR / "saved.json"
    raw = json.dumps({
        "id": "saved", "name": "Saved", "initialValue": 25000, "rebalance": "quarterly",
        "benchmark": {"ticker": "SPY", "symbol": "SPY"}, "metrics": {}, "series": [],
    }, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    row = service.list_portfolio_backtests()[0]
    assert row["initialValue"] == 25000
    assert row["rebalance"] == "quarterly"
    assert row["benchmark"] == {"ticker": "SPY", "symbol": "SPY"}
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    ("initial_value", "price"),
    [(1e-323, 100.0), (1e308, 0.001)],
)
def test_unrepresentable_derived_shares_fail_explicitly(monkeypatch, initial_value, price):
    _install_run(monkeypatch, {
        "ASSET": {"2024-01-02": price, "2024-01-03": price, "2024-01-04": price},
        "SPY": {"2024-01-02": 100.0, "2024-01-03": 100.0, "2024-01-04": 100.0},
    })
    with pytest.raises(Exception) as error:
        service.run_portfolio_backtest({"presetId": "u3", "start": "2024-01-01", "end": "2024-01-05", "initialValue": initial_value})
    assert getattr(error.value, "status_code", None) == 422
    assert error.value.detail["code"] == "backtest_calculation_limit"


@pytest.mark.parametrize(
    ("initial_value", "prices"),
    [
        (1.0, [1.0, 1e200, 1e200]),
        (1e-200, [1e-200, 1e200, 1e200]),
    ],
)
def test_nonfinite_return_or_variance_is_explicit_calculation_limit(monkeypatch, initial_value, prices):
    _install_run(monkeypatch, {
        "ASSET": dict(zip(["2024-01-02", "2024-01-03", "2024-01-04"], prices)),
        "SPY": {"2024-01-02": 100.0, "2024-01-03": 100.0, "2024-01-04": 100.0},
    })
    with pytest.raises(Exception) as error:
        service.run_portfolio_backtest({"presetId": "u3", "start": "2024-01-01", "end": "2024-01-05", "initialValue": initial_value})
    assert getattr(error.value, "status_code", None) == 422
    assert error.value.detail["code"] == "backtest_calculation_limit"
