from __future__ import annotations

import json

import pytest

from features.portfolio import service


def test_missing_portfolio_is_revision_zero(tmp_path):
    assert service.get_portfolio(tmp_path) == {
        "schemaVersion": 3,
        "sourceSchemaVersion": 1,
        "revision": 0,
        "positions": [],
        "cash": [],
        "updatedAt": "",
    }


def test_revision_safe_save_and_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "normalize_portfolio_position", lambda row, resolve=False: {**row, "ticker": row.get("ticker", ""), "quantity": float(row.get("quantity", 0))})
    first = service.save_portfolio({"expectedRevision": 0, "positions": [{"ticker": "NVDA", "quantity": 2}], "cash": []}, data_dir=tmp_path)
    assert first["revision"] == 1
    with pytest.raises(service.PortfolioRevisionConflict) as error:
        service.save_portfolio({"expectedRevision": 0, "positions": [], "cash": []}, data_dir=tmp_path)
    assert error.value.latest["revision"] == 1
    assert service.get_portfolio(tmp_path)["positions"][0]["ticker"] == "NVDA"


def test_legacy_list_is_read_without_mutation(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text('[{"ticker":"SPY","quantity":1}]', encoding="utf-8")
    value = service.get_portfolio(tmp_path)
    assert value["revision"] == 0
    assert value["positions"][0]["ticker"] == "SPY"
    assert path.read_text(encoding="utf-8").startswith("[")


def test_summary_nulls_overflowing_aggregate_and_ratio_without_nonfinite_json(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda _position: {"ok": True, "price": 1.0, "currency": "USD", "previousClose": 1.0})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda _currency: (1.0, "fixture"))
    service.save_portfolio({"positions": [
        {"ticker": "AAPL", "quantity": "1e308", "averagePrice": "0"},
        {"ticker": "MSFT", "quantity": "1e308", "averagePrice": "0"},
    ], "cash": []})
    value = service.portfolio_summary()
    assert value["summary"][0]["marketValue"] is None
    assert "market_value_total_unavailable" in value["summary"][0]["calculationUnavailable"]
    assert value["summary"][0]["pnl"] is None
    assert value["positions"][0]["weight"] is None
    assert "portfolio_total_unavailable" in value["positions"][0]["calculationUnavailable"]
    json.dumps(value, allow_nan=False)


def test_summary_keeps_exact_cost_before_display_float_projection(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda _position: {"ok": True, "price": 1.0, "currency": "USD", "previousClose": 1.0})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda _currency: (1.0, "fixture"))
    service.save_portfolio({"positions": [{"ticker": "AAPL", "quantity": "1e-300", "averagePrice": "1e400"}], "cash": []})
    row = service.portfolio_summary()["positions"][0]
    assert row["cost"] == pytest.approx(1e100)
    assert "cost_unavailable" not in row["calculationUnavailable"]


def test_summary_nulls_overflowing_pnl_ratio(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda _position: {"ok": True, "price": 1e308, "currency": "USD", "previousClose": 1e308})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda _currency: (1.0, "fixture"))
    service.save_portfolio({"positions": [{"ticker": "AAPL", "quantity": "1", "averagePrice": "1e-308"}], "cash": []})
    row = service.portfolio_summary()["positions"][0]
    assert row["pnlPct"] is None
    assert "pnl_pct_unavailable" in row["calculationUnavailable"]
    json.dumps(row, allow_nan=False)


def test_arithmetic_unavailability_invalidates_totals_weights_and_concentration(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "PORTFOLIO_PRESETS_PATH", tmp_path / "portfolio-presets.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda _position: {"ok": True, "price": 1.0, "currency": "USD", "previousClose": 1.0})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda _currency: (1.0, "fixture"))
    service.save_portfolio({"positions": [
        {"ticker": "AAPL", "quantity": "1e1000", "averagePrice": "1"},
        {"ticker": "MSFT", "quantity": "1", "averagePrice": "1"},
    ], "cash": []})
    summary = service.portfolio_summary()
    assert summary["summary"][0]["marketValue"] is None
    assert "market_value_total_unavailable" in summary["summary"][0]["calculationUnavailable"]
    assert summary["summary"][1]["marketValue"] is None
    assert all(row["weight"] is None for row in summary["positions"])
    preset = service.save_portfolio_preset({"name": "Half", "positions": [
        {"ticker": "AAPL", "weight": 50}, {"ticker": "MSFT", "weight": 50},
    ]})
    analytics = service.portfolio_analytics(preset["id"])
    assert analytics["analytics"]["totalMarketValue"] is None
    assert analytics["analytics"]["concentration"]["top1"] is None
    target_items = {row["ticker"]: row for row in analytics["analytics"]["targetWeights"]["items"]}
    assert target_items["AAPL"]["marketValueUsd"] is None
    assert target_items["AAPL"]["currentWeight"] is None
    assert target_items["AAPL"]["diffWeight"] is None
    assert target_items["MSFT"]["currentWeight"] is None
    assert target_items["MSFT"]["diffWeight"] is None
    assert analytics["analytics"]["marketWeights"][0]["weight"] is None
    json.dumps(analytics, allow_nan=False)


def test_missing_quote_keeps_existing_partial_total_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda position: {"ok": False, "error": "missing"} if position["ticker"] == "AAPL" else {"ok": True, "price": 1.0, "currency": "USD", "previousClose": 1.0})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda _currency: (1.0, "fixture"))
    service.save_portfolio({"positions": [
        {"ticker": "AAPL", "quantity": "1", "averagePrice": "1"},
        {"ticker": "MSFT", "quantity": "1", "averagePrice": "1"},
    ], "cash": []})
    summary = service.portfolio_summary()
    assert summary["summary"][0]["marketValue"] == pytest.approx(1.0)
    assert "market_value_total_unavailable" not in summary["summary"][0]["calculationUnavailable"]
    assert summary["positions"][1]["weight"] == pytest.approx(1.0)
