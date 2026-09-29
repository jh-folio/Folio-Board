import copy
import sqlite3

import pytest
from fastapi import FastAPI
from features.market_memory.tests.live_http import LiveHttpClient
from features.macro_policy.routes import create_policy_router
from features.macro_policy.service import PolicyStore, preview


def draft():
    return {'title': '공식 정책 발표 fixture', 'policyType': 'central_bank_rate',
            'jurisdiction': 'US', 'status': 'proposed',
            'sourceRef': {'url': 'https://www.federalreserve.gov/example', 'title': '가상 공식 원문',
                          'kind': 'central_bank', 'quote': 'Fixture proposal; not an enacted policy.'},
            'counterConditions': '제안이 철회되면 적용되지 않음', 'nextCheckpoint': '공식 결정문 발표 확인'}


def test_preview_no_write_confirmation_retry_restart_and_backup(tmp_path):
    store = PolicyStore(tmp_path)
    assert store.list() == [] and not store.path.exists()
    p = preview(draft())
    with pytest.raises(ValueError, match='confirmation'):
        store.confirm(p['draft'], preview_id=p['previewId'], user_confirmed=True, official_source_confirmed=False)
    changed = copy.deepcopy(p['draft']); changed['status'] = 'effective'
    with pytest.raises(ValueError, match='preview_changed'):
        store.confirm(changed, preview_id=p['previewId'], user_confirmed=True, official_source_confirmed=True)
    with sqlite3.connect(store.path) as c:
        c.execute('create table personal_notes(body text)')
        c.execute("insert into personal_notes values('preserve')")
    saved = store.confirm(p['draft'], preview_id=p['previewId'], user_confirmed=True, official_source_confirmed=True)
    assert saved['status'] == 'proposed'
    assert store.confirm(p['draft'], preview_id=p['previewId'], user_confirmed=True, official_source_confirmed=True) == saved
    assert PolicyStore(tmp_path).list() == [saved]
    with sqlite3.connect(store.path) as c:
        assert c.execute('select body from personal_notes').fetchone()[0] == 'preserve'
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('delete from macro_policy_events')
    backup = next((tmp_path/'backups').glob('*.sqlite3'))
    with sqlite3.connect(backup) as c:
        assert c.execute('select body from personal_notes').fetchone()[0] == 'preserve'


@pytest.mark.parametrize('field,value', [('status', 'predicted'), ('policyType', 'election'),
    ('counterConditions', ''), ('nextCheckpoint', ''), ('announcedAt', '2026-02-30'),
    ('probability', .8), ('sourceRef', {'url': 'https://news.example.com'})])
def test_invalid_drafts(field, value):
    body = draft(); body[field] = value
    with pytest.raises(ValueError):
        preview(body)


def test_routes_and_link_source_boundary(tmp_path):
    app = FastAPI(); app.include_router(create_policy_router(tmp_path))
    with LiveHttpClient(app) as client:
        assert client.get('/api/macro/policies').json() == {'items': []}
        body = draft(); body['channels'] = [{'channel': 'financing_cost', 'explanation': '자금조달 비용 경로', 'sourceRef': body['sourceRef']}]
        p = client.post('/api/macro/policies/preview', json=body).json()
        payload = {'draft': p['draft'], 'previewId': p['previewId'], 'userConfirmed': True, 'officialSourceConfirmed': True}
        assert client.post('/api/macro/policies/confirm', json=payload).status_code == 200
        body['channels'][0]['ticker'] = 'AAPL'
        assert client.post('/api/macro/policies/preview', json=body).status_code == 400
