import datetime as dt
import json
import sqlite3

import pytest

from features.common.macro_data.schema import digest
from features.common.macro_job_commit import commit, recover
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import JobStatus
from features.common.shared_jobs_store import SharedJobStore
from features.price_scenarios import service
from features.price_scenarios.collect import CollectionError
from features.price_scenarios.decimal_ops import fingerprint
from features.price_scenarios.store import PriceStore, snapshot_id

from .snapshot_fixtures import PRICE, make

TODAY = dt.date(2025, 3, 10)


class FakeCollector:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def collect(self, market, ticker):
        self.calls.append((market, ticker))
        if self.error:
            raise self.error
        return {"market": market, "ticker": ticker}


def built(price=PRICE):
    inputs, results = make(price=price)
    return {"status": "available", "inputs": inputs, "results": results, "meta": {"priceFetchedAt": "2025-03-04T01:00:00+00:00"}}


@pytest.fixture
def assembled(monkeypatch):
    state = {"value": built()}
    monkeypatch.setattr(service, "assemble", lambda raw: state["value"])
    return state


def test_instrument_ids_are_validated():
    assert service.parse_instrument("US:AAPL") == ("US", "AAPL") and service.parse_instrument("KR:005930") == ("KR", "005930")
    for bad in ("AAPL", "us:AAPL", "KR:5930", "KR:ABCDEF", "US:", "US:aapl", "US:A B", None, 5):
        with pytest.raises(ValueError, match="invalid_instrument_id"):
            service.parse_instrument(bad)


def test_calculation_saves_one_snapshot_and_a_repeat_is_idempotent(tmp_path, assembled):
    collector = FakeCollector()
    first = service.calculate(tmp_path, "US:ACME", collector=collector)
    assert first["savedCount"] == 1 and first["created"] is True and collector.calls == [("US", "ACME")]
    inputs = assembled["value"]["inputs"]
    assert first["snapshotId"] == snapshot_id(inputs["instrumentId"], inputs["asOf"], inputs["methodVersion"], fingerprint(inputs))
    again = service.calculate(tmp_path, "US:ACME", collector=collector)
    assert again["snapshotId"] == first["snapshotId"] and again["created"] is False
    view = service.overview(tmp_path, "US:ACME")
    assert view["latest"]["snapshotId"] == first["snapshotId"] and len(view["history"]) == 1
    assert view["lastAttempt"]["status"] == "saved" and view["lastAttempt"]["snapshotId"] == first["snapshotId"]


def test_a_failed_calculation_keeps_the_latest_snapshot_and_records_the_reason(tmp_path, assembled):
    saved = service.calculate(tmp_path, "US:ACME", collector=FakeCollector())
    with pytest.raises(service.CalculationNotStored) as error:
        service.calculate(tmp_path, "US:ACME", collector=FakeCollector(CollectionError("price_unavailable")))
    assert error.value.code == "price_unavailable"
    view = service.overview(tmp_path, "US:ACME")
    assert view["latest"]["snapshotId"] == saved["snapshotId"] and len(view["history"]) == 1
    assert view["lastAttempt"]["status"] == "failed" and view["lastAttempt"]["reason"] == {"code": "price_unavailable"}
    assembled["value"] = {"status": "unavailable", "reason": {"code": "price_stale"}}
    with pytest.raises(service.CalculationNotStored) as error:
        service.calculate(tmp_path, "US:ACME", collector=FakeCollector())
    assert error.value.code == "price_stale"
    assert service.overview(tmp_path, "US:ACME")["lastAttempt"]["reason"] == {"code": "price_stale"}
    assert len(service.overview(tmp_path, "US:ACME")["history"]) == 1


def test_reads_are_empty_before_any_calculation_and_never_create_files(tmp_path):
    view = service.overview(tmp_path, "US:ACME")
    assert view == {"instrumentId": "US:ACME", "latest": None, "history": [], "lastAttempt": None}
    assert service.snapshot_view(tmp_path, "price-x") is None and service.projection_view(tmp_path, "price-x") is None
    assert list(tmp_path.iterdir()) == []


def test_snapshot_view_projection_and_criteria_change_the_judgement_not_the_snapshot(tmp_path, assembled):
    saved = service.calculate(tmp_path, "US:ACME", collector=FakeCollector())
    store = service.store_for(tmp_path)
    summary = service.snapshot_view(tmp_path, saved["snapshotId"])
    assert "inputs" not in summary and summary["inputSummary"]["price"]["value"] == "30" and summary["supportStatus"] == "supported"
    assert "history" in service.snapshot_view(tmp_path, saved["snapshotId"], include_inputs=True)["inputs"]
    store.save_criteria(required_return="1", holding_years=10)
    low = service.projection_view(tmp_path, saved["snapshotId"], today=TODAY)
    store.save_criteria(required_return="99", holding_years=10, expected_revision_id=1)
    high = service.projection_view(tmp_path, saved["snapshotId"], today=TODAY)
    assert (low["verdict"]["return"]["state"], high["verdict"]["return"]["state"]) == ("met", "unmet")
    assert service.projection_view(tmp_path, saved["snapshotId"], criteria_revision_id=1, today=TODAY)["criteria"]["requiredReturn"] == "1"
    with pytest.raises(service.PriceStoreError) as error:
        service.projection_view(tmp_path, saved["snapshotId"], criteria_revision_id=9, today=TODAY)
    assert error.value.code == "revision_not_found"
    assert service.snapshot_view(tmp_path, saved["snapshotId"])["results"] == summary["results"]


# --- the SharedJob commit fence --------------------------------------------------

def job_setup(tmp_path, monkeypatch):
    from features.common import jobs
    clock = lambda: dt.datetime.now(dt.timezone.utc)
    store = SharedJobStore(tmp_path / "jobs-v2.json", tmp_path / "jobs.json", clock=clock)
    private = JobPrivateLifecycle(tmp_path / "job-context", clock=clock)
    job = new_shared_job(kind="price_scenario", task_type="price_scenario", generation_mode="none", adapter="none",
                         requested_mode=None, mode="generate", attempted_engine=None, clock=clock)
    store.add(job)
    store.transition(job.id, JobStatus.RUNNING)
    monkeypatch.setattr(jobs, "_store", lambda: store)
    monkeypatch.setattr(jobs, "_lifecycle", lambda: private)
    return store, private, job


def test_a_job_commits_with_a_receipt_and_completes(tmp_path, monkeypatch, assembled):
    store, private, job = job_setup(tmp_path, monkeypatch)
    out = service.calculate(tmp_path, "US:ACME", job_id=job.id, collector=FakeCollector())
    assert out["snapshotId"] and store.get(job.id).status is JobStatus.DONE
    assert store.get(job.id).resultProjection.model_dump(mode="json") == {"status": "done", "savedCount": 1}
    assert service.overview(tmp_path, "US:ACME")["latest"]["snapshotId"] == out["snapshotId"]
    with sqlite3.connect(tmp_path / "market-memory.sqlite3") as conn:
        assert conn.execute("select count(*) from macro_job_receipts").fetchone()[0] == 1


def test_a_cancelled_job_collects_and_saves_nothing(tmp_path, monkeypatch, assembled):
    store, private, job = job_setup(tmp_path, monkeypatch)
    store.transition(job.id, JobStatus.CANCEL_REQUESTED)
    collector = FakeCollector()
    with pytest.raises(RuntimeError, match="price_calculation_cancelled"):
        service.calculate(tmp_path, "US:ACME", job_id=job.id, collector=collector)
    assert collector.calls == [] and not (tmp_path / "market-memory.sqlite3").exists()


def test_receipt_recovery_and_partial_save_without_receipt(tmp_path, monkeypatch, assembled):
    store, private, job = job_setup(tmp_path, monkeypatch)
    inputs, results = assembled["value"]["inputs"], assembled["value"]["results"]
    new_id = snapshot_id(inputs["instrumentId"], inputs["asOf"], inputs["methodVersion"], fingerprint(inputs))
    expected = [{"type": "price_snapshot", "id": new_id, "hash": digest({"inputs": inputs, "results": results})}]

    def crash():
        PriceStore(tmp_path / "market-memory.sqlite3").save_snapshot(inputs, results)
        raise SystemExit("simulated stop before the receipt")

    with pytest.raises(SystemExit):
        commit(tmp_path, job.id, expected, crash, saved_count=1, store=store, lifecycle=private)
    assert not recover(tmp_path, job.id, store=store, lifecycle=private)  # saved rows without a receipt never become done
    assert store.get(job.id).status is not JobStatus.DONE


def test_a_tampered_artifact_hash_is_not_completed(tmp_path, monkeypatch, assembled):
    store, private, job = job_setup(tmp_path, monkeypatch)
    inputs, results = assembled["value"]["inputs"], assembled["value"]["results"]
    new_id = snapshot_id(inputs["instrumentId"], inputs["asOf"], inputs["methodVersion"], fingerprint(inputs))
    wrong = [{"type": "price_snapshot", "id": new_id, "hash": digest({"inputs": inputs, "results": {**results, "x": 1}})}]
    with pytest.raises(Exception):
        commit(tmp_path, job.id, wrong, lambda: PriceStore(tmp_path / "market-memory.sqlite3").save_snapshot(inputs, results),
               saved_count=1, store=store, lifecycle=private)
    assert store.get(job.id).status is not JobStatus.DONE


def test_calculations_for_one_instrument_never_interleave(tmp_path, assembled):
    import threading
    import time

    state = {"running": 0, "peak": 0}
    guard = threading.Lock()

    class SlowCollector(FakeCollector):
        def collect(self, market, ticker):
            with guard:
                state["running"] += 1
                state["peak"] = max(state["peak"], state["running"])
            time.sleep(0.05)
            with guard:
                state["running"] -= 1
            return super().collect(market, ticker)

    results = []
    threads = [threading.Thread(target=lambda: results.append(service.calculate(tmp_path, "US:ACME", collector=SlowCollector())))
               for _ in range(4)]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    assert state["peak"] == 1 and len(results) == 4
    assert len({row["snapshotId"] for row in results}) == 1 and sum(row["created"] for row in results) == 1
    assert len(service.overview(tmp_path, "US:ACME")["history"]) == 1
