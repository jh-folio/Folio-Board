"""U.2 preset persistence and validation contracts (all providers mocked)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from features.portfolio import service
from features.portfolio.routes import create_portfolio_router


@pytest.fixture
def preset_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("FOLIO_HOME", str(tmp_path))
    path = tmp_path / "portfolio-presets.json"
    monkeypatch.setattr(service, "PORTFOLIO_PRESETS_PATH", path)
    # Saving a preset may enrich metadata, but must never make a test network call.
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker, market="": {
        "ok": False, "ticker": ticker, "symbol": service.portfolio_symbol(ticker, market),
        "market": market or "US", "currency": "USD", "name": ticker,
        "assetClass": "Unknown", "sector": "Unclassified",
    })
    return path


def create_payload(**overrides):
    return {
        "name": "균형",
        "baseCurrency": "USD",
        "positions": [
            {"ticker": "AAPL", "weightPercent": "50"},
            {"ticker": "MSFT", "weightPercent": "50"},
        ],
        **overrides,
    }


def test_legacy_list_projects_revision_zero_without_rewriting(preset_store: Path):
    legacy = [{"id": "legacy", "name": "기존", "positions": [{"ticker": "AAPL", "weight": 1.0}]}]
    original = json.dumps(legacy, ensure_ascii=False).encode("utf-8")
    preset_store.write_bytes(original)

    listed = service.list_portfolio_presets()

    assert listed[0]["revision"] == 0
    assert preset_store.read_bytes() == original


def test_create_update_and_delete_are_per_preset_cas(preset_store: Path):
    created = service.save_portfolio_preset(create_payload())
    assert created["revision"] == 1
    assert created["positions"][0]["weight"] == pytest.approx(0.5)

    updated = service.save_portfolio_preset(create_payload(
        id=created["id"], expectedRevision=1, name="새 균형",
    ))
    assert updated["revision"] == 2
    assert service.list_portfolio_presets()[0]["name"] == "새 균형"

    with pytest.raises(service.PresetRevisionConflict) as stale:
        service.save_portfolio_preset(create_payload(id=created["id"], expectedRevision=1))
    assert stale.value.latest["revision"] == 2

    assert service.delete_portfolio_preset(created["id"], {"expectedRevision": 2}) == {
        "deleted": True, "id": created["id"],
    }
    with pytest.raises(service.PresetRevisionConflict) as removed:
        service.save_portfolio_preset(create_payload(id=created["id"], expectedRevision=2))
    assert removed.value.latest is None


def test_expected_revision_is_an_actual_nonnegative_integer(preset_store: Path):
    created = service.save_portfolio_preset(create_payload())
    for invalid in (None, "1", 1.0, True, -1):
        with pytest.raises(service.PresetRevisionConflict):
            service.save_portfolio_preset(create_payload(id=created["id"], expectedRevision=invalid))


def test_invalid_rows_are_not_filtered_or_clamped(preset_store: Path):
    before = service.save_portfolio_preset(create_payload())
    original = preset_store.read_bytes()
    with pytest.raises(service.PortfolioValidationError) as rejected:
        service.save_portfolio_preset({
            "id": before["id"], "expectedRevision": before["revision"], "name": "",
            "baseCurrency": "EUR",
            "positions": [
                {"ticker": "", "weightPercent": "-1"},
                {"ticker": "AAPL", "weightPercent": "Infinity"},
                {"ticker": "aapl", "weightPercent": "101"},
            ],
        })
    codes = {error["code"] for error in rejected.value.errors}
    assert {"required", "unsupported_currency", "invalid_ticker", "negative_weight", "invalid_weight", "duplicate_ticker"} <= codes
    assert preset_store.read_bytes() == original


def test_non_hundred_total_requires_explicit_normalization(preset_store: Path):
    payload = create_payload(positions=[
        {"ticker": "AAPL", "weightPercent": "60"},
        {"ticker": "MSFT", "weightPercent": "60"},
    ])
    with pytest.raises(service.PortfolioValidationError) as rejected:
        service.save_portfolio_preset(payload)
    assert rejected.value.errors[0]["code"] == "weight_total_not_100"

    normalized = service.save_portfolio_preset({**payload, "normalizeWeights": True})
    assert normalized["normalizedWeights"] is True
    assert [row["weight"] for row in normalized["positions"]] == pytest.approx([0.5, 0.5])


def test_near_hundred_tolerance_does_not_reapply_legacy_percent_heuristic(preset_store: Path):
    saved = service.save_portfolio_preset(create_payload(positions=[
        {"ticker": "AAPL", "weightPercent": "100.00000000001"},
    ]))
    assert saved["positions"][0]["weight"] == pytest.approx(1.0000000000001)


def test_legacy_nonfinite_weight_is_a_validation_error_not_a_decimal_crash(preset_store: Path):
    with pytest.raises(service.PortfolioValidationError) as rejected:
        service.save_portfolio_preset(create_payload(positions=[
            {"ticker": "AAPL", "weight": "NaN"},
        ]))
    assert rejected.value.errors[0]["code"] == "invalid_weight"


def test_post_resolution_duplicate_symbols_reject_the_entire_preset(preset_store: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker, market="": {
        "ok": True, "ticker": ticker, "symbol": "035900.KQ", "name": "JYP Ent.",
        "market": "KR", "currency": "KRW", "assetClass": "Equity", "sector": "Communication Services",
    })
    with pytest.raises(service.PortfolioValidationError) as rejected:
        service.save_portfolio_preset(create_payload(positions=[
            {"ticker": "035900", "weightPercent": "50"},
            {"ticker": "035900.KQ", "weightPercent": "50"},
        ]))
    assert rejected.value.errors == [{
        "row": 1, "field": "ticker", "code": "duplicate_symbol",
        "message": "같은 거래 종목은 한 번만 넣을 수 있습니다.",
    }]
    assert not preset_store.exists()


def test_stale_client_identity_metadata_is_rebuilt_from_ticker(preset_store: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker, market="": {
        "ok": True, "ticker": ticker, "symbol": "MSFT", "name": "Microsoft Corporation",
        "market": "US", "currency": "USD", "assetClass": "Equity", "sector": "Technology",
    })
    saved = service.save_portfolio_preset(create_payload(positions=[
        {"ticker": "MSFT", "symbol": "AAPL", "name": "Apple Inc.", "market": "KR", "currency": "KRW", "weightPercent": "100"},
    ]))
    row = saved["positions"][0]
    assert row["ticker"] == "MSFT"
    assert row["symbol"] == "MSFT"
    assert row["name"] == "Microsoft Corporation"
    assert row["currency"] == "USD"


def test_explicit_exchange_suffix_is_preserved_over_provider_default(preset_store: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda ticker, market="": {
        "ok": True, "ticker": "035900", "symbol": "035900.KS", "name": "JYP Ent.",
        "market": "KR", "currency": "KRW", "assetClass": "Equity", "sector": "Communication Services",
    })
    saved = service.save_portfolio_preset(create_payload(positions=[
        {"ticker": "035900.KQ", "weightPercent": "100"},
    ]))
    assert saved["positions"][0]["symbol"] == "035900.KQ"


def test_existing_fractional_thirds_reopen_without_precision_total_failure(preset_store: Path):
    initial = service.save_portfolio_preset(create_payload(positions=[
        {"ticker": "AAPL", "weight": 1 / 3},
        {"ticker": "MSFT", "weight": 1 / 3},
        {"ticker": "NVDA", "weight": 1 / 3},
    ]))
    reopened = service.list_portfolio_presets()[0]
    saved_again = service.save_portfolio_preset({
        **reopened, "expectedRevision": reopened["revision"],
    })
    assert saved_again["revision"] == initial["revision"] + 1


def test_invalid_existing_file_is_never_overwritten(preset_store: Path):
    preset_store.write_text("{not json", encoding="utf-8")
    before = preset_store.read_bytes()
    with pytest.raises(service.PortfolioValidationError) as rejected:
        service.save_portfolio_preset(create_payload())
    assert rejected.value.errors[0]["code"] == "preset_storage_invalid"
    assert preset_store.read_bytes() == before


def test_from_current_is_unsaved_actual_weight_draft_with_gap_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "portfolio_summary", lambda: {"positions": [
        {"ticker": "AAPL", "weight": 0.4, "targetWeight": 0.9},
        {"ticker": "MSFT", "weight": None, "targetWeight": 0.1},
    ]})
    draft = service.preset_from_current_portfolio("현재")
    assert draft["draft"] is True
    assert "id" not in draft and "revision" not in draft
    assert draft["positions"][0]["ticker"] == "AAPL"
    assert draft["positions"][0]["weight"] == 0.4
    assert draft["weightTotal"] == 0.4
    assert draft["warnings"][0]["ticker"] == "MSFT"


def test_preset_routes_return_the_contract_error_shapes(preset_store: Path):
    router = create_portfolio_router(preset_store.parent)
    endpoints = {route.path + ":" + next(iter(route.methods)): route.endpoint for route in router.routes if route.methods}
    save = endpoints["/api/portfolio/presets:POST"]
    delete = endpoints["/api/portfolio/presets/{preset_id}:DELETE"]

    with pytest.raises(HTTPException) as invalid:
        save(create_payload(positions=[{"ticker": "AAPL", "weightPercent": "90"}]))
    assert invalid.value.status_code == 422
    assert invalid.value.detail["code"] == "preset_validation_failed"

    created = save(create_payload())
    with pytest.raises(HTTPException) as conflict:
        delete(created["id"], {})
    assert conflict.value.status_code == 409
    assert conflict.value.detail == {"code": "preset_revision_conflict", "latest": created}
