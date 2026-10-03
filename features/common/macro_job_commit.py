"""SharedJob commit fence and durable receipt for immutable macro artifacts.

Collection may retain partial raw pages; a completed derived-artifact job needs
every expected immutable body and its receipt. Recovery never recollects data.
"""
import json
import sqlite3
from pathlib import Path

from features.common.macro_data.schema import canonical, digest
from features.common.macro_data.store import backup_database, _SCHEMA_LOCK
from features.common.shared_jobs_completion import ArtifactCompletionSource, _mint_artifact_completion_proof
from features.common.shared_jobs_schema import CommitIntent, ExpectedArtifact, StorageKind, JobStatus, MacroProjection, ErrorCode, TaskType

TASKS = {TaskType.MACRO_REFRESH, TaskType.MACRO_EXPOSURE, TaskType.PRICE_SCENARIO}
TABLES = {'macro_snapshot': 'macro_state_snapshots', 'company_exposure': 'company_macro_exposures',
          'price_snapshot': 'price_snapshots'}


def _ensure(path):
    with _SCHEMA_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with sqlite3.connect(path) as conn:
                if conn.execute("SELECT 1 FROM sqlite_master WHERE name='macro_job_receipts'").fetchone():
                    return
        backup_database(path, 'before-macro-job-receipts-v1')
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE macro_job_receipts(job_id TEXT PRIMARY KEY, intent_hash TEXT NOT NULL)')
            for action in ('UPDATE', 'DELETE'):
                conn.execute(f"CREATE TRIGGER macro_receipt_no_{action.lower()} BEFORE {action} ON macro_job_receipts BEGIN SELECT RAISE(ABORT,'immutable_macro_receipt'); END")


def _verify(conn, intent):
    for artifact in intent.expectedArtifacts:
        table = TABLES.get(artifact.type)
        if table is None:
            raise ValueError('macro_artifact_type_invalid')
        row = conn.execute(f'SELECT body FROM {table} WHERE id=?', (artifact.id,)).fetchone()
        if row is None or digest(json.loads(row[0])) != artifact.targetHash:
            raise ValueError('macro_artifact_hash_mismatch')


def commit(root, job_id, expected, write, *, saved_count, store=None, lifecycle=None):
    from features.common import jobs
    store = store or jobs._store()
    lifecycle = lifecycle or jobs._lifecycle()
    job = store.get(job_id)
    if job is None or job.taskType not in TASKS:
        raise ValueError('macro_job_invalid')
    intent = CommitIntent(operationId='macro-' + job_id,
                          expectedArtifacts=[ExpectedArtifact(storage=StorageKind.SQLITE, type=a['type'], id=a['id'],
                              targetHash=a['hash'], baseHash=None, baseMarker=None, targetRevision=None) for a in expected],
                          terminalProjection=MacroProjection(savedCount=saved_count))
    # claim_committing atomically refuses a previously accepted cancellation.
    store.claim_committing(job_id, intent)
    path = Path(root).resolve() / 'market-memory.sqlite3'
    receipt_written = False
    try:
        _ensure(path)
        result = write()
        with sqlite3.connect(path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            _verify(conn, intent)
            conn.execute('INSERT INTO macro_job_receipts VALUES(?,?)', (job_id, digest(intent.model_dump(mode='json'))))
        receipt_written = True
        if not recover(root, job_id, store=store, lifecycle=lifecycle):
            raise ValueError('macro_completion_verification_failed')
        return result
    except Exception:
        current = store.get(job_id)
        if not receipt_written and current and current.status is JobStatus.COMMITTING:
            lifecycle.terminalize(store, job_id, JobStatus.FAILED_COMMIT, error_code=ErrorCode.SAVE_FAILED)
        raise


def recover(root, job_id, *, store, lifecycle):
    job = store.get(job_id)
    if job is None or job.status is not JobStatus.COMMITTING or job.taskType not in TASKS or job.commitIntent is None:
        raise ValueError('macro_committing_job_required')
    path = Path(root).resolve() / 'market-memory.sqlite3'
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            receipt = conn.execute('SELECT intent_hash FROM macro_job_receipts WHERE job_id=?', (job_id,)).fetchone()
            if receipt is None or receipt[0] != digest(job.commitIntent.model_dump(mode='json')):
                raise ValueError('macro_receipt_mismatch')
            _verify(conn, job.commitIntent)
    except (OSError, sqlite3.Error, ValueError):
        lifecycle.terminalize_recovery(store, job_id, JobStatus.FAILED_COMMIT_RECOVERY)
        return False
    proof = _mint_artifact_completion_proof(job, ArtifactCompletionSource.SQLITE)
    lifecycle.complete_artifact(store, job_id, proof)
    return True
