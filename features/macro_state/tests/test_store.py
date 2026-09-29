import copy
import sqlite3

import pytest

from features.macro_state.engine import calculate
from features.macro_state.store import StateStore
from .test_inputs import row


def snapshot(value='1'):
    rows=[row('STLFSI4','2025-12-26',value),row('STLFSI4','2025-11-28','.75')]
    return calculate('US','stress_vulnerability',rows,'2026-01-31T23:59:59Z')


def test_read_only_idempotent_immutable_supersession(tmp_path):
    store=StateStore(tmp_path/'market-memory.sqlite3')
    assert store.latest('US','stress_vulnerability') is None
    assert not store.path.exists()
    first=store.save(snapshot(),reason='initial')
    assert store.save(snapshot(),reason='retry')['snapshotId']==first['snapshotId']
    second=store.save(snapshot('2'),reason='source_revision')
    assert second['snapshotId']!=first['snapshotId']
    assert store.get(first['snapshotId'])['level']=='elevated'
    assert store.latest('US','stress_vulnerability')['level']=='high'
    with sqlite3.connect(store.path) as conn:
        assert conn.execute('select count(*) from macro_state_supersessions').fetchone()[0]==1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE macro_state_snapshots SET body='{}'")
    corrupted=snapshot();corrupted['level']='normal'
    with pytest.raises(ValueError,match='non_reproducible'):
        store.save(corrupted,reason='retry')


def test_transaction_failure_preserves_previous_and_promotion_is_projection(tmp_path):
    store=StateStore(tmp_path/'market-memory.sqlite3')
    first=store.save(snapshot(),reason='initial')
    with sqlite3.connect(store.path) as conn:
        conn.execute("CREATE TRIGGER fail_link BEFORE INSERT ON macro_state_supersessions BEGIN SELECT RAISE(ABORT,'failure'); END")
    with pytest.raises(sqlite3.IntegrityError):store.save(snapshot('2'),reason='revision')
    assert store.latest('US','stress_vulnerability')['snapshotId']==first['snapshotId']
    with pytest.raises(ValueError,match='fixed_shadow'):
        store.decide('US','stress_vulnerability','macro-state-1','promotion','primary',evaluation_ref='review',user_confirmed=True)
    with pytest.raises(ValueError,match='confirmation_required'):
        store.decide('US','growth','macro-state-1','promotion','primary',evaluation_ref='review',user_confirmed=False)
    s=copy.deepcopy(snapshot());s['axis']='inflation';s['level']='near_reference'
    saved=store.save(s,reason='fixture')
    store.decide('US','inflation','macro-state-1','promotion','primary',evaluation_ref='review',user_confirmed=True)
    assert store.get(saved['snapshotId'])['promotion']=='primary'
    with sqlite3.connect(store.path) as conn:
        body=conn.execute('SELECT body FROM macro_state_snapshots WHERE id=?',(saved['snapshotId'],)).fetchone()[0]
        assert 'primary' not in body and 'promotion' not in body


def test_backup_restoration_preserves_existing_tables(tmp_path):
    path=tmp_path/'market-memory.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('create table notes(id text)');conn.execute("insert into notes values('keep')")
        before=list(conn.iterdump())
    store=StateStore(path);store.save(snapshot(),reason='initial')
    backup=next((tmp_path/'backups').glob('*.sqlite3'))
    with sqlite3.connect(backup) as source,sqlite3.connect(tmp_path/'restore.sqlite3') as restored:
        source.backup(restored)
        assert list(restored.iterdump())==before
    assert StateStore(path).get(store.latest('US','stress_vulnerability')['snapshotId'])['level']=='elevated'
