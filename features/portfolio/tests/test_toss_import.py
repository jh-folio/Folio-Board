from __future__ import annotations

import json
import threading

import pytest
from fastapi import HTTPException

from features.portfolio import service
from features.portfolio.routes import create_portfolio_router
from features.portfolio.toss_import import TossHoldingsImport, TossImportError, authority_fingerprint, legacy_authority_fingerprint
from features.investment_review.review_v2 import effective_freshness
from features.common.market_data.toss_token_manager import TossProviderError


ACCOUNT = {"accountNo": "123456789012", "accountSeq": 77, "accountType": "BROKERAGE"}
HOLDINGS = {"totalPurchaseAmount": "1", "marketValue": "2", "profitLoss": "1", "dailyProfitLoss": "0", "items": [
    {"symbol": "AAPL", "name": "Apple", "marketCountry": "US", "currency": "USD", "quantity": "2", "lastPrice": "200", "averagePurchasePrice": "150", "marketValue": "400", "profitLoss": "100", "dailyProfitLoss": "3", "cost": "300"},
]}


def importer(tmp_path, *, holdings=None, clock=None, writer=None, state_writer=None):
    return TossHoldingsImport(
        tmp_path,
        accounts_reader=lambda: [ACCOUNT],
        holdings_reader=lambda _seq: holdings if holdings is not None else HOLDINGS,
        monotonic=clock or (lambda: 1.0),
        portfolio_writer=writer or service.write_portfolio_authority,
        state_writer=state_writer or (lambda path, value: __import__("features.common.utils", fromlist=["write_json"]).write_json(path, value)),
    )


def selected(instance):
    account = instance.accounts()["accounts"][0]
    assert account["label"] == "•••• 9012"
    assert "123456789012" not in repr(account)
    return account["selectionId"]


def test_preview_is_redacted_and_has_no_authority_write(tmp_path):
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    assert preview["canConfirm"] is True
    assert preview["buckets"]["additions"] == ["US:USD:AAPL"]
    assert not (tmp_path / "portfolio.json").exists()
    rendered = json.dumps(preview)
    assert "123456789012" not in rendered and "accountSeq" not in rendered and "lastPrice" not in rendered


def test_fractional_preview_preserves_exact_before_after_and_delta(tmp_path):
    service.save_portfolio({"expectedRevision": 0, "positions": [{"ticker": "AAPL", "market": "US", "currency": "USD", "quantity": "1.50", "averagePrice": "15e1"}], "cash": []}, data_dir=tmp_path)
    instance = importer(tmp_path, holdings={**HOLDINGS, "items": [{**HOLDINGS["items"][0], "quantity": "1.25", "averagePurchasePrice": "149.875"}]})
    preview = instance.preview(selected(instance))
    assert preview["canConfirm"] is True
    assert preview["details"] == [{"positionKey": "US:USD:AAPL", "action": "update", "ticker": "AAPL", "currency": "USD", "before": {"quantity": "1.5", "averagePrice": "150"}, "after": {"quantity": "1.25", "averagePrice": "149.875"}, "delta": {"quantity": "-0.25", "averagePrice": "-0.125"}}]
    assert instance.confirm(preview["previewId"], 1)["portfolio"]["positions"][0]["quantity"] == "1.25"


def test_contract_invalid_holdings_stops_preview_before_any_authority_write(tmp_path):
    def invalid_holdings(_seq):
        raise TossProviderError("provider_contract_invalid")
    instance = TossHoldingsImport(
        tmp_path,
        accounts_reader=lambda: [ACCOUNT],
        holdings_reader=invalid_holdings,
        portfolio_writer=service.write_portfolio_authority,
    )
    with pytest.raises(TossImportError) as error:
        instance.preview(selected(instance))
    assert error.value.code == "provider_contract_invalid"
    assert not (tmp_path / "portfolio.json").exists()


def test_confirm_upserts_and_preserves_cash_and_manual_positions(tmp_path):
    service.save_portfolio({"expectedRevision": 0, "positions": [{"ticker": "AAPL", "market": "US", "currency": "USD", "quantity": 1, "averagePrice": 100}, {"ticker": "005930", "market": "KR", "currency": "KRW", "quantity": 3, "averagePrice": 70000}], "cash": [{"currency": "USD", "amount": 11}]}, data_dir=tmp_path)
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    assert preview["buckets"]["updates"] == ["US:USD:AAPL"]
    assert preview["buckets"]["preservedManual"] == ["KR:KRW:005930"]
    response = instance.confirm(preview["previewId"], 1)
    portfolio = response["portfolio"]
    assert portfolio["revision"] == 2
    assert portfolio["cash"] == [{"currency": "USD", "amount": 11.0}]
    assert {row["ticker"]: row["quantity"] for row in portfolio["positions"]} == {"AAPL": "2", "005930": "3"}
    sidecar = json.loads((tmp_path / "portfolio-import-state.json").read_text(encoding="utf-8"))
    assert sidecar["pendingImport"] is None and sidecar["lastImport"]["portfolioRevision"] == 2
    serialized = json.dumps(sidecar)
    assert "123456789012" not in serialized and "accountSeq" not in serialized and '"quantity"' not in serialized and '"averagePurchasePrice"' not in serialized


@pytest.mark.parametrize("item,code", [
    ({**HOLDINGS["items"][0], "marketCountry": "JP", "currency": "JPY"}, "unsupported_market_or_currency"),
    ({**HOLDINGS["items"][0], "quantity": "0"}, "invalid_quantity"),
])
def test_blocking_preview_never_writes(tmp_path, item, code):
    instance = importer(tmp_path, holdings={**HOLDINGS, "items": [item]})
    preview = instance.preview(selected(instance))
    assert preview["canConfirm"] is False
    assert code in json.dumps(preview)
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "blocking_items"
    assert not (tmp_path / "portfolio.json").exists()


def test_expiry_and_stale_expected_revision_are_safe(tmp_path):
    moment = [0.0]
    instance = importer(tmp_path, clock=lambda: moment[0])
    selection = selected(instance)
    moment[0] = 301
    with pytest.raises(TossImportError) as error:
        instance.preview(selection)
    assert error.value.code == "selection_expired"
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], "0")
    assert error.value.code == "expected_revision_required"
    service.save_portfolio({"expectedRevision": 0, "positions": [], "cash": []}, data_dir=tmp_path)
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "portfolio_revision_conflict"
    assert error.value.latest["revision"] == 1


def test_empty_holdings_is_a_no_write_preview(tmp_path):
    instance = importer(tmp_path, holdings={**HOLDINGS, "items": []})
    preview = instance.preview(selected(instance))
    assert preview["status"] == "empty" and preview["canConfirm"] is False
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "empty_holdings"
    assert not (tmp_path / "portfolio.json").exists()


def test_idempotent_confirm_does_not_increment_revision(tmp_path):
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    first = instance.confirm(preview["previewId"], 0)
    assert first["portfolio"]["revision"] == 1
    # The idempotency record is checked before a broker re-read/write.
    second = instance.confirm(preview["previewId"], 0)
    assert second["idempotent"] is True and second["portfolio"]["revision"] == 1


def test_finalization_failure_recovers_without_second_revision(tmp_path):
    calls = [0]
    def flaky(path, payload):
        calls[0] += 1
        if calls[0] == 2:
            raise OSError("metadata locked")
        from features.common.utils import write_json
        write_json(path, payload)
    instance = importer(tmp_path, state_writer=flaky)
    preview = instance.preview(selected(instance))
    result = instance.confirm(preview["previewId"], 0)
    assert result["metadataStatus"] == "recovery_pending"
    assert result["portfolio"]["revision"] == 1
    recovered = importer(tmp_path)
    assert recovered.accounts()["accounts"]
    state = json.loads((tmp_path / "portfolio-import-state.json").read_text(encoding="utf-8"))
    assert state["pendingImport"] is None and state["lastImport"]["portfolioRevision"] == 1


def test_v1_pending_recovery_accepts_original_raw_target_digest(tmp_path):
    raw = {"schemaVersion": 2, "revision": 7, "updatedAt": "old", "positions": [{
        "id": "legacy", "ticker": "AAPL", "symbol": "AAPL", "name": "Apple", "market": "US", "currency": "USD",
        "quantity": 2, "averagePrice": 150.0, "targetWeight": None, "assetClass": "Equity", "sector": "Tech", "industry": "", "country": "", "exchange": "", "quoteType": "",
    }], "cash": []}
    (tmp_path / "portfolio.json").write_text(json.dumps(raw), encoding="utf-8")
    raw_digest = legacy_authority_fingerprint(raw)[0]
    pending = {
        "importId": "legacy-pending", "importedAt": "2026-09-04T00:00:00Z", "mergeMode": "upsert_preserve",
        "portfolioRevision": 7, "authorityFingerprintVersion": 1, "authorityFingerprint": raw_digest,
        "mergeFingerprintVersion": 1, "mergeFingerprint": "0" * 64, "positionKeys": ["US:USD:AAPL"],
        "counts": {"additions": 0, "updates": 1, "preservedManual": 0, "unchanged": 0, "conflicts": 0, "unsupported": 0},
        "openApiVersion": "1.2.14", "basePortfolioRevision": 6, "baseAuthorityFingerprintVersion": 1, "baseAuthorityFingerprint": "1" * 64,
    }
    (tmp_path / "portfolio-import-state.json").write_text(json.dumps({"schemaVersion": 1, "source": "toss_open_api", "lastImport": None, "pendingImport": pending}), encoding="utf-8")
    instance = importer(tmp_path)
    assert instance.recover_portfolio()["revision"] == 7
    state = json.loads(instance.state_path.read_text(encoding="utf-8"))
    assert state["pendingImport"] is None and state["lastImport"]["importId"] == "legacy-pending"


def test_concurrent_same_preview_commits_authority_once(tmp_path):
    writes = [0]
    def counted(document, *, data_dir):
        writes[0] += 1
        return service.write_portfolio_authority(document, data_dir=data_dir)
    instance = importer(tmp_path, writer=counted)
    preview = instance.preview(selected(instance))
    gate = threading.Barrier(3)
    results: list[dict] = []
    def confirm():
        gate.wait()
        results.append(instance.confirm(preview["previewId"], 0))
    threads = [threading.Thread(target=confirm), threading.Thread(target=confirm)]
    for thread in threads: thread.start()
    gate.wait()
    for thread in threads: thread.join()
    assert writes == [1]
    assert sorted(row["idempotent"] for row in results) == [False, True]
    assert service.get_portfolio(tmp_path)["revision"] == 1


def test_unknown_pending_fingerprint_fails_closed_but_manual_read_survives(tmp_path):
    seed = importer(tmp_path)
    preview = seed.preview(selected(seed))
    seed.confirm(preview["previewId"], 0)
    state = json.loads(seed.state_path.read_text(encoding="utf-8"))
    state["lastImport"]["authorityFingerprintVersion"] = 99
    seed.state_path.write_text(json.dumps(state), encoding="utf-8")
    instance = importer(tmp_path)
    # The normal Portfolio route can still show manual data.
    assert instance.recover_portfolio()["revision"] == 1
    with pytest.raises(TossImportError) as error:
        instance.accounts()
    assert error.value.code == "metadata_unavailable"


@pytest.mark.parametrize("holdings", [
    {**HOLDINGS, "items": [HOLDINGS["items"][0], {**HOLDINGS["items"][0], "marketCountry": "KR", "currency": "KRW"}]},
    {**HOLDINGS, "items": [HOLDINGS["items"][0], {**HOLDINGS["items"][0], "quantity": "3"}]},
])
def test_same_ticker_multiplicity_blocks_before_target_assembly(tmp_path, holdings):
    instance = importer(tmp_path, holdings=holdings)
    preview = instance.preview(selected(instance))
    assert preview["canConfirm"] is False
    assert "duplicate_incoming_ticker" in json.dumps(preview)
    cached = next(iter(instance._previews.values())).value
    assert cached["target"] is None and cached["targetDigest"] is None
    assert not (tmp_path / "portfolio.json").exists()


def test_existing_cross_market_same_ticker_is_a_blocker(tmp_path):
    service.save_portfolio({"expectedRevision": 0, "positions": [
        {"ticker": "AAPL", "market": "US", "currency": "USD", "quantity": 1, "averagePrice": 1},
        {"ticker": "AAPL", "market": "KR", "currency": "KRW", "quantity": 1, "averagePrice": 1},
    ], "cash": []}, data_dir=tmp_path)
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    assert preview["canConfirm"] is False
    assert "duplicate_existing_ticker" in json.dumps(preview)
    assert next(iter(instance._previews.values())).value["target"] is None


def test_existing_duplicate_ticker_never_leaks_into_success_buckets_or_operations(tmp_path):
    service.save_portfolio({"expectedRevision": 0, "positions": [
        {"ticker": "AAPL", "market": "US", "currency": "USD", "quantity": 1, "averagePrice": 1},
        {"ticker": "AAPL", "market": "KR", "currency": "KRW", "quantity": 1, "averagePrice": 1},
        {"ticker": "MSFT", "market": "US", "currency": "USD", "quantity": 1, "averagePrice": 1},
    ], "cash": []}, data_dir=tmp_path)
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    cached = instance._previews[preview["previewId"]].value
    assert preview["canConfirm"] is False
    assert preview["buckets"]["additions"] == []
    assert preview["buckets"]["updates"] == []
    assert preview["buckets"]["unchanged"] == []
    assert preview["buckets"]["preservedManual"] == ["US:USD:MSFT"]
    assert {issue["positionKey"] for issue in preview["buckets"]["conflicts"]} == {
        "US:USD:AAPL", "KR:KRW:AAPL",
    }
    assert cached["incoming"][0]["issueCodes"] == ["duplicate_existing_ticker"]
    assert cached["target"] is None


@pytest.mark.parametrize("raw", ["{", "{}", '{"schemaVersion":2,"source":"toss_open_api","lastImport":null,"pendingImport":null}'])
def test_existing_corrupt_sidecar_blocks_new_import_but_not_manual_read(tmp_path, raw):
    (tmp_path / "portfolio-import-state.json").write_text(raw, encoding="utf-8")
    instance = importer(tmp_path)
    assert instance.recover_portfolio()["revision"] == 0
    with pytest.raises(TossImportError) as error:
        instance.accounts()
    assert error.value.code == "metadata_unavailable"


def test_absent_sidecar_is_the_only_initial_metadata_state(tmp_path):
    instance = importer(tmp_path)
    assert not instance.state_path.exists()
    assert instance.accounts()["accounts"]


def test_ttl_sweep_removes_selection_and_preview_sensitive_values(tmp_path):
    moment = [0.0]
    instance = importer(tmp_path, clock=lambda: moment[0])
    selection = selected(instance)
    preview = instance.preview(selection)
    assert instance._selections and instance._previews
    moment[0] = 301
    instance.accounts()
    assert selection not in instance._selections and instance._selections and not instance._previews  # accounts makes only fresh selections
    with pytest.raises(TossImportError) as error:
        instance.preview(selection)
    assert error.value.code == "selection_expired"


@pytest.mark.parametrize("item", [
    {**HOLDINGS["items"][0], "quantity": "1" * 129},
    {**HOLDINGS["items"][0], "averagePurchasePrice": "0." + ("1" * 129)},
])
def test_precision_unsupported_is_blocking_and_never_written(tmp_path, item):
    instance = importer(tmp_path, holdings={**HOLDINGS, "items": [item]})
    preview = instance.preview(selected(instance))
    assert preview["canConfirm"] is False and "precision_unsupported" in json.dumps(preview)
    assert not (tmp_path / "portfolio.json").exists()


def test_authority_projection_excludes_extras_and_caches_target_bytes(tmp_path):
    base = {"schemaVersion": 2, "revision": 2, "positions": [{"id": "a", "ticker": "AAPL", "symbol": "AAPL", "name": "Apple", "market": "US", "quantity": 1, "averagePrice": 1, "targetWeight": None, "currency": "USD", "assetClass": "Unknown", "sector": "Unclassified", "industry": "", "country": "", "exchange": "", "quoteType": "", "resolved": {"ok": False}, "providerPrivate": "ignore"}], "cash": [], "updatedAt": "old"}
    changed = {**base, "positions": [{**base["positions"][0], "providerPrivate": "other"}], "updatedAt": "new"}
    assert authority_fingerprint(base) == authority_fingerprint(changed)
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    cached = instance._previews[preview["previewId"]].value
    assert cached["authorityVersion"] == 2 and cached["targetBytes"]
    cached["targetBytes"] = b"wrong"
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "preview_stale"


def test_cached_fingerprint_version_mismatch_fails_closed(tmp_path):
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    instance._previews[preview["previewId"]].value["mergeVersion"] = 99
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "preview_stale"


def test_negative_expected_revision_is_validation_error(tmp_path):
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], -1)
    assert error.value.code == "expected_revision_invalid" and error.value.status == 400


def test_missing_merge_field_is_unsupported_not_conflict(tmp_path):
    instance = importer(tmp_path, holdings={**HOLDINGS, "items": [{**HOLDINGS["items"][0], "name": ""}]})
    preview = instance.preview(selected(instance))
    assert preview["buckets"]["unsupported"] and not preview["buckets"]["conflicts"]
    assert "missing_required_field" in json.dumps(preview)


def test_pending_and_base_write_failures_never_increment_authority(tmp_path):
    def fail_pending(_path, _payload): raise OSError("locked")
    instance = importer(tmp_path, state_writer=fail_pending)
    preview = instance.preview(selected(instance))
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "pending_write_failed" and not (tmp_path / "portfolio.json").exists()

    def fail_write(_document, *, data_dir): raise OSError("disk")
    instance = importer(tmp_path, writer=fail_write)
    preview = instance.preview(selected(instance))
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.code == "portfolio_write_failed" and not (tmp_path / "portfolio.json").exists()


def test_ambiguous_authority_write_clears_pending_as_stale_without_overwrite(tmp_path):
    def ambiguous(_document, *, data_dir):
        service.write_portfolio_authority({"schemaVersion": 2, "revision": 9, "positions": [], "cash": [], "updatedAt": ""}, data_dir=data_dir)
        raise OSError("unknown")
    instance = importer(tmp_path, writer=ambiguous)
    preview = instance.preview(selected(instance))
    with pytest.raises(TossImportError) as error:
        instance.confirm(preview["previewId"], 0)
    assert error.value.metadata_status == "stale"
    assert service.get_portfolio(tmp_path)["revision"] == 9
    state = json.loads(instance.state_path.read_text(encoding="utf-8"))
    assert state["source"] == "toss_open_api" and state["pendingImport"] is None


def test_legacy_list_becomes_v3_only_after_explicit_confirm(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text('[{"ticker":"MSFT","quantity":1}]', encoding="utf-8")
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    assert path.read_text(encoding="utf-8").startswith("[")
    instance.confirm(preview["previewId"], 0)
    assert json.loads(path.read_text(encoding="utf-8"))["schemaVersion"] == 3


def test_import_revision_makes_prior_investment_review_basis_stale(tmp_path):
    instance = importer(tmp_path)
    preview = instance.preview(selected(instance))
    committed = instance.confirm(preview["previewId"], 0)["portfolio"]
    prior = {"inputBasis": {"fingerprint": "before", "status": "partial", "portfolio": {"revision": 0}}, "reviewState": "reviewed", "generatedAt": "2026-09-01T00:00:00Z", "positionReviews": []}
    current = {"fingerprint": "after", "status": "partial", "portfolio": {"revision": committed["revision"]}}
    state, freshness, reasons = effective_freshness(prior, current)
    assert committed["revision"] == 1 and state == "stale" and freshness["status"] == "stale" and reasons[0]["code"] == "input_fingerprint_changed"


def test_router_masks_and_redacts_safe_errors(tmp_path):
    instance = importer(tmp_path)
    router = create_portfolio_router(tmp_path, instance)
    endpoints = {route.path: route.endpoint for route in router.routes}
    accounts = endpoints["/api/portfolio/toss/accounts"]()
    assert "123456789012" not in json.dumps(accounts) and "accountSeq" not in json.dumps(accounts)
    preview = endpoints["/api/portfolio/toss/preview"]({"selectionId": accounts["accounts"][0]["selectionId"]})
    with pytest.raises(HTTPException) as error:
        endpoints["/api/portfolio/toss/confirm"]({"previewId": preview["previewId"], "expectedRevision": 2})
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "portfolio_revision_conflict"


def test_authority_fingerprint_excludes_updated_at_and_normalizes_decimal(tmp_path):
    one = {"schemaVersion": 2, "revision": 3, "positions": [{"id": "x", "ticker": "AAPL", "symbol": "AAPL", "name": "Cafe\u0301", "market": "US", "quantity": 2.0, "averagePrice": 10.00, "targetWeight": None, "currency": "USD", "assetClass": "Unknown", "sector": "Unclassified", "industry": "", "country": "", "exchange": "", "quoteType": "", "resolved": {}}], "cash": [], "updatedAt": "old"}
    two = {**one, "updatedAt": "new"}
    assert authority_fingerprint(one)[0] == authority_fingerprint(two)[0]
