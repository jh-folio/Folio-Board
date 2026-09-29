import sqlite3

import pytest

from features.common.macro_data.publication_facts import preview_fact, record_fact, publication_facts
from features.common.macro_data.schema import day_end
from features.common.macro_data.store import MacroStore
from .test_ledger import point, write


def fact():
    return {'seriesId': 'UNRATE', 'observationMonth': '2025-10',
            'sourceUrl': 'https://www.bls.gov/news.release/archives/empsit_12162025.htm',
            'availableAt': day_end('2025-12-16', 'America/Chicago')}


def test_preview_confirmation_and_cutoff_do_not_infer_facts_from_null(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    payload = fact()
    token = preview_fact(payload)['confirmationToken']
    assert not store.path.exists()
    with pytest.raises(ValueError, match='confirmation_required'):
        record_fact(store, payload, confirmation_token='wrong')
    assert not store.path.exists()
    write(store, point(series='UNRATE', value=None, period='2025-10-01', vintage='2025-12-16'))
    assert publication_facts(store, cutoff='2026-01-01T00:00:00Z') == []
    before = store.history('UNRATE')
    saved = record_fact(store, payload, confirmation_token=token)
    assert record_fact(store, payload, confirmation_token=token) == saved
    assert publication_facts(store, cutoff='2025-12-16T23:59:59Z') == []
    assert publication_facts(store, cutoff=payload['availableAt']) == [saved]
    assert MacroStore(store.path).history('UNRATE') == before
    assert saved['rowKind'] == 'fact' and saved['recordedAt']


@pytest.mark.parametrize('field,value', [
    ('seriesId', 'INDPRO'), ('observationMonth', '2025-13'),
    ('sourceUrl', 'https://www.bls.gov.example.com/fake'),
    ('sourceUrl', 'http://www.bls.gov/news'),
    ('availableAt', '2025-12-16'), ('availableAt', '2025-09-01T00:00:00Z'),
])
def test_fact_rejects_unverifiable_shape(field, value):
    with pytest.raises(ValueError):
        preview_fact({**fact(), field: value})


def test_v1_migration_backup_restore_preserves_all_rows(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    write(store, point())
    with sqlite3.connect(store.path) as conn:
        conn.execute('DROP TABLE macro_publication_facts')
        conn.execute('DELETE FROM macro_schema')
        conn.execute('INSERT INTO macro_schema VALUES(1)')
        before = list(conn.iterdump())
    assert publication_facts(store, cutoff='2026-01-01T00:00:00Z') == []
    store.ensure()
    backup = next((tmp_path / 'backups').glob('*.sqlite3'))
    restored = tmp_path / 'restored.sqlite3'
    with sqlite3.connect(backup) as source, sqlite3.connect(restored) as target:
        source.backup(target)
        assert list(target.iterdump()) == before
    assert MacroStore(restored).history('CPIAUCSL') == store.history('CPIAUCSL')
    store.ensure()
    assert len(list((tmp_path / 'backups').glob('*.sqlite3'))) == 1
