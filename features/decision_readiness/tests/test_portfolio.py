import copy
import datetime as dt
import json
from decimal import Decimal as D
import pytest

from features.decision_readiness import DecisionError
from features.decision_readiness.portfolio_fit import BasisCache, capture_basis, preview


def fixture_basis():
    entries = [
        {"instrumentId": "US:A", "kind": "holding", "valueUsd": "60", "industry": "same", "currency": "USD", "exposure": None},
        {"instrumentId": "KR:000001", "kind": "holding", "valueUsd": "30", "industry": "other", "currency": "KRW", "exposure": None},
        {"instrumentId": "cash:0", "kind": "cash", "valueUsd": "10", "industry": "현금", "currency": "USD", "exposure": None},
    ]
    return {"candidate": {"instrumentId": "US:C", "industry": "same", "currency": "USD", "exposure": None}, "entries": entries,
            "basisFingerprint": "fixed", "portfolioRevision": 1, "notice": "final weight and proportional adjustment", "dataGaps": [], "fx": {}}


def test_manual_p01_p02_and_purity():
    basis = fixture_basis(); original = copy.deepcopy(basis)
    out = preview(basis, "US:C", "20")
    assert {key: D(value) for key, value in out["after"]["security"].items()} == {"US:A": D(".48"), "KR:000001": D(".24"), "cash:0": D(".08"), "US:C": D(".20")}
    assert D(out["after"]["industry"]["same"]) == D(".68")
    assert D(out["delta"]["industry"]["same"]) == D(".08")
    assert D(out["after"]["currency"]["USD"]) == D(".76")
    assert D(out["delta"]["currency"]["KRW"]) == D("-.06")
    assert D(out["after"]["concentration"]["maxHolding"]) == D(".48")
    assert D(out["after"]["concentration"]["top3"]) == D(".92")
    assert preview(basis, "US:C", "20") == out and basis == original
    basis["candidate"]["instrumentId"] = "US:A"
    second = preview(basis, "US:A", "20")
    assert {key: D(value) for key, value in second["after"]["security"].items()} == {"US:A": D(".20"), "KR:000001": D(".60"), "cash:0": D(".20")}


@pytest.mark.parametrize("weight", ["0", "100"])
def test_zero_and_full_weight(weight):
    out = preview(fixture_basis(), "US:C", weight)
    assert sum(D(value) for value in out["after"]["security"].values()) == 1
    assert D(out["after"]["security"]["US:C"]) == D(weight) / 100


@pytest.mark.parametrize("weight", ["", "-1", "101", "NaN", "Infinity", "1e1", "0x10", True, 20.0])
def test_invalid_weight_not_default(weight):
    with pytest.raises(DecisionError, match="invalid_candidate_weight"):
        preview(fixture_basis(), "US:C", weight)


def test_sole_holding_empty_and_incomplete_denominator():
    basis = fixture_basis(); basis["entries"] = basis["entries"][:1]; basis["candidate"]["instrumentId"] = "US:A"
    assert preview(basis, "US:A", "20")["reason"] == "no_other_assets"
    assert preview(basis, "US:A", "100")["status"] == "available"
    basis["entries"] = []
    assert preview(basis, "US:A", "20")["after"] is None
    basis = fixture_basis(); basis["dataGaps"] = ["fx_unavailable"]
    assert preview(basis, "US:C", "20")["before"] is None


def test_partial_etf_never_double_counts_direct_security():
    basis = fixture_basis()
    basis["candidate"].update(assetClass="ETF", components={"verified": True, "asOf": "2025-03-01", "sourceRefs": [{"id": "fixture-official"}],
        "items": [{"instrumentId": "US:A", "weight": ".3"}, {"instrumentId": "KR:000001", "weight": ".2"}]})
    out = preview(basis, "US:C", "20")
    looked = out["after"]["etfLookThrough"][0]
    assert [D(row["weight"]) for row in looked["items"]] == [D(".06"), D(".04")]
    assert D(looked["unknownWeight"]) == D(".10")
    assert D(out["after"]["security"]["US:A"]) == D(".48")
    assert out["backtest"]["status"] == "unavailable"


def test_capture_duplicate_lots_cash_and_byte_invariance(tmp_path):
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"schemaVersion": 3, "revision": 4, "positions": [{"market": "US", "ticker": "A", "symbol": "A", "quantity": "2", "industry": "same"},
        {"market": "US", "ticker": "A", "symbol": "A", "quantity": "3", "industry": "same"}], "cash": [{"currency": "USD", "amount": "10"}]}), encoding="utf-8")
    before = path.read_bytes(); calls = []
    def quote(symbol):
        calls.append(symbol)
        return {"status": "available", "value": "10", "currency": "USD", "source": "fixture", "observedAt": "2025-03-03T00:00:00Z"}
    basis = capture_basis(tmp_path, "US:A", quote_reader=quote, fx_reader=lambda c: {"status": "available", "rateToUsd": "1"})
    assert calls == ["A"] and basis["entries"][0]["quantity"] == "5"
    for _ in range(3): preview(basis, "US:A", "20")
    with pytest.raises(DecisionError): preview(basis, "US:B", "20")
    assert path.read_bytes() == before and sorted(p.name for p in tmp_path.iterdir()) == ["portfolio.json"]
    cache = BasisCache(); captured = cache.put(tmp_path, basis)
    assert cache.get(tmp_path, captured["basisId"]) == basis
    assert path.read_bytes() == before
    path.write_text(path.read_text().replace('"revision": 4', '"revision": 5'))
    with pytest.raises(DecisionError, match="comparison_inputs_changed"): cache.get(tmp_path, captured["basisId"])


def test_basis_expiry_workspace_and_missing_quotes(tmp_path):
    now = [dt.datetime(2025, 3, 3, tzinfo=dt.timezone.utc)]
    cache = BasisCache(lambda: now[0]); basis = {**fixture_basis(), "portfolioHash": None}
    result = cache.put(tmp_path, basis)
    with pytest.raises(DecisionError): cache.get(tmp_path / "other", result["basisId"])
    now[0] += dt.timedelta(minutes=30)
    with pytest.raises(DecisionError, match="portfolio_basis_expired"): cache.get(tmp_path, result["basisId"])
    (tmp_path / "portfolio.json").write_text(json.dumps({"positions": [{"market": "US", "ticker": "A", "quantity": "1"}], "cash": []}))
    missing = capture_basis(tmp_path, "US:C", quote_reader=lambda s: {"status": "unavailable"}, fx_reader=lambda c: {"status": "unavailable"})
    assert preview(missing, "US:C", "20")["before"] is None
