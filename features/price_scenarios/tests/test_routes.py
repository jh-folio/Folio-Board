import pytest
from fastapi import FastAPI

from features.market_memory.tests.live_http import LiveHttpClient
from features.price_scenarios import routes
from features.price_scenarios.store import PriceStore

from .snapshot_fixtures import make


@pytest.fixture
def server(tmp_path):
    app = FastAPI()
    app.include_router(routes.create_price_router(tmp_path))
    with LiveHttpClient(app) as client:
        yield client, tmp_path


def seeded(root):
    store = PriceStore(root / "market-memory.sqlite3")
    return store, store.save_snapshot(*make())["snapshotId"]


def test_reads_on_an_empty_workspace_return_empty_states_and_write_nothing(server):
    client, root = server
    assert client.get("/api/valuation/criteria").json() == {"criteria": None}
    assert client.get("/api/valuation/assumptions", params={"instrumentId": "US:ACME"}).json() == {"override": None}
    assert client.get("/api/price-snapshots", params={"instrumentId": "US:ACME"}).json() == {
        "instrumentId": "US:ACME", "latest": None, "history": [], "lastAttempt": None}
    assert client.get("/api/price-snapshots/price-none").status_code == 404
    assert client.get("/api/price-snapshots/price-none/projection").status_code == 404
    assert list(root.iterdir()) == []


def test_snapshot_reads_and_projection_follow_the_saved_criteria(server):
    client, root = server
    store, snapshot_id = seeded(root)
    overview = client.get("/api/price-snapshots", params={"instrumentId": "US:ACME"}).json()
    assert overview["latest"]["snapshotId"] == snapshot_id and overview["history"][0]["supersedes"] is None
    view = client.get(f"/api/price-snapshots/{snapshot_id}").json()
    assert "inputs" not in view and view["results"]["scenarios"] and view["supportStatus"] == "supported"
    assert "history" in client.get(f"/api/price-snapshots/{snapshot_id}", params={"include": "inputs"}).json()["inputs"]
    before = client.get(f"/api/price-snapshots/{snapshot_id}/projection").json()
    assert before["verdict"]["return"] == {"state": "unknown", "reason": "criteria_not_set"}
    saved = client.post("/api/valuation/criteria", json={"requiredReturn": "1", "holdingYears": 10}).json()["criteria"]
    assert saved["revisionId"] == 1
    after = client.get(f"/api/price-snapshots/{snapshot_id}/projection").json()
    assert after["verdict"]["return"]["state"] == "met" and after["criteria"]["revisionId"] == 1
    assert client.get(f"/api/price-snapshots/{snapshot_id}/projection", params={"criteriaRevisionId": 7}).status_code == 404
    assert client.get(f"/api/price-snapshots/{snapshot_id}").json()["results"] == view["results"]


def test_criteria_writes_map_errors_to_stable_codes(server):
    client, _ = server
    cases = [({"requiredReturn": "6", "holdingYears": 7}, 422, "invalid_holding_years"),
             ({"requiredReturn": "6"}, 422, "holding_years_required"),
             ({"requiredReturn": "150", "holdingYears": 5}, 422, "out_of_range"),
             ({"requiredReturn": "abc", "holdingYears": 5}, 422, "invalid_number")]
    for body, status, code in cases:
        response = client.post("/api/valuation/criteria", json=body)
        assert response.status_code == status and response.json()["detail"]["code"] == code, body
    assert client.post("/api/valuation/criteria", json={"requiredReturn": 6.5, "holdingYears": 5}).status_code == 422  # numbers are text
    assert client.post("/api/valuation/criteria", json={"requiredReturn": "6", "holdingYears": 5, "other": 1}).status_code == 422
    assert client.get("/api/valuation/criteria").json() == {"criteria": None}  # nothing was repaired or saved
    ok = client.post("/api/valuation/criteria", json={"requiredReturn": "6", "minMarginOfSafety": "20", "holdingYears": 10})
    assert ok.status_code == 200
    stale = client.post("/api/valuation/criteria", json={"requiredReturn": "7", "holdingYears": 10})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "revision_conflict"
    cleared = client.post("/api/valuation/criteria", json={"holdingYears": 10, "expectedRevisionId": 1}).json()["criteria"]
    assert (cleared["requiredReturn"], cleared["minMarginOfSafety"], cleared["holdingYears"]) == (None, None, 10)


def test_assumptions_need_a_matching_snapshot_and_report_conflicts(server):
    client, root = server
    _, snapshot_id = seeded(root)
    body = {"instrumentId": "US:ACME", "basedOnSnapshotId": snapshot_id, "growth": "0.12", "payout": "0"}
    saved = client.post("/api/valuation/assumptions", json=body).json()["override"]
    assert (saved["growth"], saved["exitPE"], saved["payout"], saved["basedOnSnapshotId"]) == ("0.12", None, "0", snapshot_id)
    assert client.get("/api/valuation/assumptions", params={"instrumentId": "US:ACME"}).json()["override"]["overrideId"] == saved["overrideId"]
    conflict = client.post("/api/valuation/assumptions", json=body)
    assert conflict.status_code == 409 and conflict.json()["detail"]["code"] == "revision_conflict"
    missing = client.post("/api/valuation/assumptions", json={**body, "basedOnSnapshotId": "price-missing", "expectedOverrideId": saved["overrideId"]})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "snapshot_not_found"
    other = client.post("/api/valuation/assumptions", json={**body, "instrumentId": "US:OTHR", "expectedOverrideId": None})
    assert other.status_code == 422 and other.json()["detail"]["code"] == "snapshot_instrument_mismatch"
    bad = client.post("/api/valuation/assumptions", json={**body, "growth": "-1", "expectedOverrideId": saved["overrideId"]})
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "out_of_range", "field": "growth"}


def test_bad_instrument_ids_are_rejected_before_any_work(server):
    client, root = server
    assert client.get("/api/price-snapshots", params={"instrumentId": "AAPL"}).status_code == 400
    assert client.get("/api/valuation/assumptions", params={"instrumentId": "kr:5930"}).status_code == 400
    assert client.post("/api/price-snapshots/calculate", json={"instrumentId": "AAPL"}).status_code == 400
    assert list(root.iterdir()) == []


def test_calculate_reuses_the_active_job_and_starts_a_new_one_after_it_finishes(server, monkeypatch):
    client, root = server
    from features.common import jobs
    started, states = [], {"status": "running"}
    monkeypatch.setattr(jobs, "submit_job", lambda *args, **kwargs: started.append((args[0], args[4])) or {"id": f"job-{len(started)}", "status": "queued"})
    monkeypatch.setattr(jobs, "get_job", lambda job_id: {"id": job_id, "status": states["status"]})
    first = client.post("/api/price-snapshots/calculate", json={"instrumentId": "US:ACME"}).json()
    second = client.post("/api/price-snapshots/calculate", json={"instrumentId": "US:ACME"}).json()
    assert first["id"] == "job-1" and second["id"] == "job-1" and started == [("price_scenario", "US:ACME")]
    other = client.post("/api/price-snapshots/calculate", json={"instrumentId": "KR:005930"}).json()
    assert other["id"] == "job-2"
    states["status"] = "done"
    assert client.post("/api/price-snapshots/calculate", json={"instrumentId": "US:ACME"}).json()["id"] == "job-3"
