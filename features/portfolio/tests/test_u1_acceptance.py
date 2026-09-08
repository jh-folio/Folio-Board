"""Independent U.1 acceptance tests using only disposable authority files."""
from __future__ import annotations

import hashlib
import json

import pytest

from features.portfolio import service
from features.portfolio.toss_import import authority_fingerprint


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *a, **k: {})


@pytest.mark.parametrize("quantity", [
    "0.1", "1.25", "0.000000000000000000000000000001",
    "1.1234567890123456789012345678901234567890123456789",
])
def test_exact_manual_authority_roundtrip(tmp_path, quantity):
    average = "123.123456789012345678901234567890123456789"
    saved = service.save_portfolio({"expectedRevision": 0, "positions": [
        {"ticker": "AAPL", "quantity": quantity, "averagePrice": average},
    ], "cash": [{"currency": "USD", "amount": 50}]}, data_dir=tmp_path)
    raw = json.loads((tmp_path / "portfolio.json").read_text(encoding="utf-8"))
    loaded = service.get_portfolio(tmp_path)
    assert saved["schemaVersion"] == raw["schemaVersion"] == loaded["schemaVersion"] == 3
    for value in (saved, raw, loaded):
        assert value["positions"][0]["quantity"] == quantity
        assert value["positions"][0]["averagePrice"] == average
        assert value["cash"] == [{"currency": "USD", "amount": 50}]
    assert authority_fingerprint(saved) == authority_fingerprint(loaded)


def test_legacy_read_has_stable_identity_without_file_mutation(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_bytes(b'{"schemaVersion":2,"revision":7,"updatedAt":"old","positions":[{"ticker":"AAPL","quantity":1.5,"averagePrice":12}],"cash":[]}')
    before = path.read_bytes()
    value = service.get_portfolio(tmp_path)
    assert value["revision"] == 7
    assert value["updatedAt"] == "old"
    assert value["positions"][0]["id"] == hashlib.sha256(b"AAPL:1.5:12.0").hexdigest()[:12]
    assert value["positions"][0]["quantity"] == "1.5"
    assert path.read_bytes() == before


def test_new_fingerprint_uses_numeric_equality_not_decimal_spelling():
    def portfolio(q, p, version):
        return {"schemaVersion": version, "revision": 3, "positions": [
            {"id": "stable", "ticker": "AAPL", "market": "US", "currency": "USD", "quantity": q, "averagePrice": p},
        ], "cash": []}
    assert authority_fingerprint(portfolio("1.50", "12.00", 3)) == authority_fingerprint(portfolio("15e-1", 12, 2))
    assert authority_fingerprint(portfolio("1.50000000000000000000000000001", "12", 3)) != authority_fingerprint(portfolio("1.5", "12", 3))


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "0", True, "1e1001", "9" * 129])
def test_invalid_row_cannot_silently_remove_existing_authority(tmp_path, bad):
    saved = service.save_portfolio({"positions": [{"ticker": "SPY", "quantity": "2", "averagePrice": "100"}], "cash": []}, data_dir=tmp_path)
    path = tmp_path / "portfolio.json"
    before = path.read_bytes()
    with pytest.raises(service.PortfolioValidationError):
        service.save_portfolio({"expectedRevision": saved["revision"], "positions": [
            {"ticker": "SPY", "quantity": "2", "averagePrice": "100"},
            {"ticker": "AAPL", "quantity": bad, "averagePrice": "1"},
        ], "cash": []}, data_dir=tmp_path)
    assert path.read_bytes() == before


def test_manual_route_returns_row_field_error_and_preserves_cash_when_omitted(tmp_path):
    from fastapi import HTTPException
    from features.portfolio.routes import create_portfolio_router
    router = create_portfolio_router(tmp_path)
    write = next(route.endpoint for route in router.routes if route.path == "/api/portfolio" and "POST" in route.methods)
    saved = write({"positions": [{"ticker": "AAPL", "quantity": "0.1", "averagePrice": "1"}], "cash": [{"currency": "USD", "amount": 50}]})
    before = (tmp_path / "portfolio.json").read_bytes()
    with pytest.raises(HTTPException) as rejected:
        write({"expectedRevision": saved["revision"], "positions": [{"ticker": "AAPL", "quantity": "bad", "averagePrice": "1"}]})
    assert rejected.value.status_code == 422
    assert rejected.value.detail == {"code": "portfolio_validation_failed", "errors": [{"row": 0, "field": "quantity", "code": "invalid_decimal"}]}
    assert (tmp_path / "portfolio.json").read_bytes() == before
    accepted = write({"expectedRevision": saved["revision"], "positions": [{"ticker": "AAPL", "quantity": "0.2", "averagePrice": "1"}]})
    assert accepted["cash"] == [{"currency": "USD", "amount": 50}]


def test_summary_does_not_overwrite_exact_authority_strings(tmp_path, monkeypatch):
    quantity = "0.1000000000000000000000000000001"
    service.save_portfolio({"positions": [{"ticker": "AAPL", "quantity": quantity, "averagePrice": "1.25"}]}, data_dir=tmp_path)
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda p: {"ok": True, "price": 10.0, "currency": "USD", "previousClose": 9.0})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda c: (1.0, "fixture"))
    value = service.portfolio_summary()
    assert value["positions"][0]["quantity"] == quantity
    assert value["positions"][0]["marketValueUsd"] == pytest.approx(1.0)
    assert service.get_portfolio(tmp_path)["positions"][0]["quantity"] == quantity


@pytest.mark.parametrize("quantity", ["1e-1000", "1e127", "1e128", "1e255", "1e256", "1e1000"])
def test_valid_exponent_extremes_can_be_resubmitted_without_precision_loss(tmp_path, quantity):
    from decimal import Decimal
    first = service.save_portfolio({"positions": [{"ticker": "AAPL", "quantity": quantity, "averagePrice": "1"}]}, data_dir=tmp_path)
    loaded = service.get_portfolio(tmp_path)
    assert Decimal(loaded["positions"][0]["quantity"]) == Decimal(quantity)
    second = service.save_portfolio({"expectedRevision": first["revision"], "positions": loaded["positions"], "cash": loaded["cash"]}, data_dir=tmp_path)
    assert Decimal(second["positions"][0]["quantity"]) == Decimal(quantity)


def test_canonical_output_is_closed_under_reinput_across_supported_exponents():
    from decimal import Decimal
    from features.portfolio.decimal_values import canonical_decimal
    for exponent in range(-1000, 1001):
        for coefficient in ("1", "1." + "2" * 127):
            raw = f"{coefficient}e{exponent}"
            rendered = canonical_decimal(raw)
            assert Decimal(rendered) == Decimal(raw)
            assert canonical_decimal(rendered) == rendered, raw


def test_review_basis_changes_on_explicit_save_not_legacy_read(tmp_path):
    from features.investment_review.review_v2 import build_input_basis
    legacy = {"schemaVersion": 2, "revision": 7, "updatedAt": "2026-09-01T00:00:00Z", "positions": [
        {"ticker": "AAPL", "quantity": 1.5, "averagePrice": 12},
    ], "cash": []}
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")
    before = path.read_bytes()
    original_basis = build_input_basis({"portfolio": legacy})["fingerprint"]
    loaded = service.get_portfolio(tmp_path)
    assert build_input_basis({"portfolio": loaded})["fingerprint"] == original_basis
    assert path.read_bytes() == before
    saved = service.save_portfolio({"expectedRevision": 7, "positions": loaded["positions"], "cash": []}, data_dir=tmp_path)
    assert build_input_basis({"portfolio": saved})["fingerprint"] != original_basis


@pytest.mark.parametrize("quantity", ["1e1000", "1e-1000"])
@pytest.mark.parametrize("with_normal_row", [False, True])
def test_arithmetic_unavailable_cannot_become_a_complete_subset_total(tmp_path, monkeypatch, quantity, with_normal_row):
    positions = [{"ticker": "AAPL", "quantity": quantity, "averagePrice": "1", "targetWeight": 0.5}]
    if with_normal_row:
        positions.append({"ticker": "MSFT", "quantity": "1", "averagePrice": "1", "targetWeight": 0.5})
    service.save_portfolio({"positions": positions}, data_dir=tmp_path)
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "fetch_portfolio_quote", lambda p: {"ok": True, "price": 1.0, "currency": "USD", "previousClose": 1.0})
    monkeypatch.setattr(service, "_portfolio_fx_to_usd", lambda c: (1.0, "fixture"))
    monkeypatch.setattr(service, "get_portfolio_preset", lambda _: {"id": "fixture", "positions": [{"ticker": "AAPL", "weight": 0.5}, {"ticker": "MSFT", "weight": 0.5}]})
    result = service.portfolio_analytics("fixture")
    json.dumps(result, allow_nan=False)
    assert result["analytics"]["totalMarketValue"] is None
    assert result["analytics"]["concentration"]["top1"] is None
    assert all(row["marketValue"] is None and row["calculationUnavailable"] for row in result["summary"])
    assert all(row["weight"] is None for row in result["positions"])
    assert all(row["currentWeight"] is None and row["diffWeight"] is None for row in result["analytics"]["targetWeights"]["items"])
    assert next(row for row in result["analytics"]["targetWeights"]["items"] if row["ticker"] == "AAPL")["marketValueUsd"] is None
    assert not any(comment["title"] == "단일 종목 집중" for comment in result["analytics"]["comments"])
