"""Independent U.2 authority acceptance; all files/providers are isolated."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException

from features.portfolio import service


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "PORTFOLIO_PRESETS_PATH", tmp_path / "portfolio-presets.json")
    monkeypatch.setattr(service, "PORTFOLIO_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr(service, "resolve_portfolio_ticker", lambda *a, **k: {})
    return tmp_path


def body(name="Core", **extra):
    return {"name": name, "baseCurrency": "USD", "positions": [
        {"ticker": "AAPL", "weightPercent": "0.5"},
        {"ticker": "MSFT", "weightPercent": "99.5"},
    ], **extra}


def test_legacy_read_then_revision_zero_update_preserves_portfolio_and_sibling(isolated):
    presets = isolated / "portfolio-presets.json"
    legacy = {"id": "legacy", "name": "Old", "positions": [{"ticker": "SPY", "weight": 1}], "updatedAt": "old"}
    sibling = {"id": "other", "name": "Other", "positions": [], "custom": {"keep": True}}
    presets.write_text(json.dumps([legacy, sibling]), encoding="utf-8")
    authority = isolated / "portfolio.json"
    authority.write_bytes(b'{"revision":19,"positions":[],"updatedAt":"unchanged"}')
    before = presets.read_bytes()
    assert service.list_portfolio_presets()[0]["revision"] == 0
    assert presets.read_bytes() == before
    saved = service.save_portfolio_preset(body(id="legacy", expectedRevision=0))
    assert saved["id"] == "legacy" and saved["revision"] == 1
    raw = json.loads(presets.read_text(encoding="utf-8"))
    assert next(p for p in raw if p["id"] == "other") == sibling
    assert authority.read_bytes() == b'{"revision":19,"positions":[],"updatedAt":"unchanged"}'
    assert saved["positions"][0]["weight"] == pytest.approx(0.005)


def test_distinct_ids_concurrent_updates_preserve_every_save(isolated):
    saved = [service.save_portfolio_preset(body(str(i))) for i in range(12)]
    gate = Barrier(len(saved))
    def update(p):
        gate.wait()
        return service.save_portfolio_preset(body("edited-" + p["name"], id=p["id"], expectedRevision=p["revision"]))
    with ThreadPoolExecutor(max_workers=len(saved)) as pool:
        results = list(pool.map(update, saved))
    actual = {p["id"]: p for p in service.list_portfolio_presets()}
    assert len(actual) == len(saved)
    for result in results:
        assert actual[result["id"]]["name"] == result["name"]
        assert actual[result["id"]]["revision"] == 2


def test_same_id_concurrent_cas_has_exactly_one_winner(isolated):
    saved = service.save_portfolio_preset(body())
    gate = Barrier(8)
    def update(i):
        gate.wait()
        try:
            return service.save_portfolio_preset(body(str(i), id=saved["id"], expectedRevision=1))
        except service.PresetRevisionConflict:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(update, range(8)))
    assert sum(r is not None for r in results) == 1
    assert service.get_portfolio_preset(saved["id"])["revision"] == 2


def test_new_ids_do_not_depend_on_name_or_clock(isolated, monkeypatch):
    monkeypatch.setattr(service, "now_iso", lambda: "frozen")
    results = [service.save_portfolio_preset(body()) for _ in range(25)]
    assert len({p["id"] for p in results}) == 25
    assert len(service.list_portfolio_presets()) == 25


@pytest.mark.parametrize("extra", [{}, {"expectedRevision": 0}, {"expectedRevision": True}, {"expectedRevision": "1"}])
def test_update_rejects_missing_stale_or_noninteger_revision_without_write(isolated, extra):
    saved = service.save_portfolio_preset(body())
    before = (isolated / "portfolio-presets.json").read_bytes()
    with pytest.raises(service.PresetRevisionConflict) as exc:
        service.save_portfolio_preset(body("changed", id=saved["id"], **extra))
    assert exc.value.latest["revision"] == 1
    assert (isolated / "portfolio-presets.json").read_bytes() == before


@pytest.mark.parametrize("rows", [
    [{"ticker": "AAPL", "weightPercent": "100"}, {"ticker": "MSFT", "weightPercent": "-1"}],
    [{"ticker": "AAPL", "weightPercent": "NaN"}],
    [{"ticker": "AAPL", "weightPercent": True}],
    [{"ticker": "AAPL", "weightPercent": "50"}, {"ticker": "aapl", "weightPercent": "50"}],
    [{"ticker": "<script>", "weightPercent": "100"}],
])
def test_invalid_rows_never_partially_replace_preset(isolated, rows):
    saved = service.save_portfolio_preset(body())
    before = (isolated / "portfolio-presets.json").read_bytes()
    with pytest.raises(service.PortfolioValidationError) as exc:
        service.save_portfolio_preset(body(id=saved["id"], expectedRevision=1, positions=rows))
    assert exc.value.errors
    assert (isolated / "portfolio-presets.json").read_bytes() == before


def test_underallocated_input_needs_explicit_normalization(isolated):
    request = body(positions=[{"ticker": "AAPL", "weightPercent": "20"}, {"ticker": "MSFT", "weightPercent": "30"}])
    with pytest.raises(service.PortfolioValidationError):
        service.save_portfolio_preset(request)
    assert not (isolated / "portfolio-presets.json").exists()
    saved = service.save_portfolio_preset({**request, "normalizeWeights": True})
    assert [p["weight"] for p in saved["positions"]] == pytest.approx([0.4, 0.6])


def test_delete_stale_then_update_after_delete_cannot_resurrect(isolated):
    from features.portfolio.routes import create_portfolio_router
    router = create_portfolio_router(isolated)
    save = next(r.endpoint for r in router.routes if r.path == "/api/portfolio/presets" and "POST" in r.methods)
    delete = next(r.endpoint for r in router.routes if r.path == "/api/portfolio/presets/{preset_id}" and "DELETE" in r.methods)
    saved = save(body())
    updated = save(body("Edited", id=saved["id"], expectedRevision=1))
    before = (isolated / "portfolio-presets.json").read_bytes()
    with pytest.raises(HTTPException) as exc:
        delete(saved["id"], {"expectedRevision": 1})
    assert exc.value.status_code == 409
    assert exc.value.detail["latest"]["name"] == "Edited"
    assert (isolated / "portfolio-presets.json").read_bytes() == before
    assert delete(saved["id"], {"expectedRevision": updated["revision"]})["deleted"] is True
    with pytest.raises(HTTPException) as exc:
        save(body("Resurrect", id=saved["id"], expectedRevision=updated["revision"]))
    assert exc.value.status_code == 409
    assert exc.value.detail["latest"] is None
    assert service.list_portfolio_presets() == []


def test_route_422_and_from_current_have_no_authority_writes(isolated, monkeypatch):
    from features.portfolio.routes import create_portfolio_router
    router = create_portfolio_router(isolated)
    save = next(r.endpoint for r in router.routes if r.path == "/api/portfolio/presets" and "POST" in r.methods)
    draft = next(r.endpoint for r in router.routes if r.path == "/api/portfolio/presets/from-current")
    with pytest.raises(HTTPException) as exc:
        save(body(positions=[{"ticker": "AAPL", "weightPercent": "bad"}]))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "preset_validation_failed"
    assert exc.value.detail["errors"][0]["row"] == 0
    monkeypatch.setattr(service, "portfolio_summary", lambda: {"positions": [
        {"ticker": "AAPL", "weight": 0.2, "targetWeight": 0.9},
        {"ticker": "MSFT", "weight": None},
    ]})
    result = draft({"name": "Current"})
    assert "id" not in result and "revision" not in result
    assert result["positions"][0]["weight"] == 0.2
    assert result["warnings"]
    assert not (isolated / "portfolio-presets.json").exists()


def test_thirds_reopen_save_and_near_hundred_do_not_change_units(isolated):
    saved = service.save_portfolio_preset(body(positions=[
        {"ticker": ticker, "weightPercent": "1"} for ticker in ["AAPL", "MSFT", "SPY"]
    ], normalizeWeights=True))
    reopened = service.save_portfolio_preset(body(id=saved["id"], expectedRevision=1, positions=[
        {"ticker": row["ticker"], "weightPercent": str(row["weight"] * 100)} for row in saved["positions"]
    ]))
    assert sum(row["weight"] for row in reopened["positions"]) == pytest.approx(1)
    tolerance = service.save_portfolio_preset(body(positions=[{"ticker": "AAPL", "weightPercent": "100.00000000001"}]))
    assert tolerance["positions"][0]["weight"] == pytest.approx(1)


@pytest.mark.parametrize("raw", [b"{broken", b"{}", b'[null,{"id":"keep"}]'])
def test_malformed_storage_is_not_replaced_by_create(isolated, raw):
    path = isolated / "portfolio-presets.json"
    path.write_bytes(raw)
    with pytest.raises(service.PortfolioValidationError):
        service.save_portfolio_preset(body())
    assert path.read_bytes() == raw
