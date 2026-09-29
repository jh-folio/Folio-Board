import pytest
from datetime import datetime, timezone
from features.common.shared_jobs_store import SharedJobStore
from features.common.shared_jobs_private import JobPrivateLifecycle
from features.common.shared_jobs_projection import new_shared_job
from features.common.shared_jobs_schema import JobStatus
from features.common.macro_data.schema import digest
from features.common.macro_job_commit import commit, recover
from features.company_exposure.extraction import extract
from features.company_exposure.store import ExposureStore
from .test_exposure import materials


def setup(root):
    clock = lambda: datetime.now(timezone.utc)
    store = SharedJobStore(root/'jobs-v2.json', root/'jobs.json', clock=clock)
    private = JobPrivateLifecycle(root/'job-context', clock=clock)
    job = new_shared_job(kind='macro_exposure', task_type='macro_exposure', generation_mode='none', adapter='none', requested_mode=None, mode='collect', attempted_engine=None, clock=clock)
    store.add(job); store.transition(job.id, JobStatus.RUNNING)
    profile = extract({'ticker': 'T'}, materials())
    expected = [{'type': 'company_exposure', 'id': profile['profileId'], 'hash': digest(profile)}]
    return store, private, job, profile, expected


def test_cancel_before_claim_never_writes(tmp_path):
    store, private, job, profile, expected = setup(tmp_path)
    store.transition(job.id, JobStatus.CANCEL_REQUESTED)
    called = []
    with pytest.raises(Exception):
        commit(tmp_path, job.id, expected, lambda: called.append(True), saved_count=1, store=store, lifecycle=private)
    assert called == [] and not (tmp_path/'market-memory.sqlite3').exists()


def test_save_fence_and_recovery_after_receipt(tmp_path, monkeypatch):
    store, private, job, profile, expected = setup(tmp_path)
    original = private.complete_artifact
    def crash(*args, **kwargs):
        raise SystemExit('simulated process stop after receipt')
    monkeypatch.setattr(private, 'complete_artifact', crash)
    def write():
        assert store.get(job.id).status is JobStatus.COMMITTING
        with pytest.raises(Exception):
            store.transition(job.id, JobStatus.CANCEL_REQUESTED)
        return ExposureStore(tmp_path).save(profile, materials=materials())
    with pytest.raises(SystemExit):
        commit(tmp_path, job.id, expected, write, saved_count=1, store=store, lifecycle=private)
    assert store.get(job.id).status is JobStatus.COMMITTING
    monkeypatch.setattr(private, 'complete_artifact', original)
    assert recover(tmp_path, job.id, store=store, lifecycle=private)
    assert store.get(job.id).status is JobStatus.DONE


def test_partial_save_without_receipt_never_recovers_done(tmp_path):
    store, private, job, profile, expected = setup(tmp_path)
    def crash():
        ExposureStore(tmp_path).save(profile, materials=materials())
        raise SystemExit('simulated crash before receipt')
    with pytest.raises(SystemExit):
        commit(tmp_path, job.id, expected, crash, saved_count=1, store=store, lifecycle=private)
    assert not recover(tmp_path, job.id, store=store, lifecycle=private)
    assert store.get(job.id).status is JobStatus.FAILED_COMMIT_RECOVERY
    assert ExposureStore(tmp_path).get('T') == profile
