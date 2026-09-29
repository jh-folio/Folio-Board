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


def test_explicit_exposure_link_and_stale_profile(tmp_path):
    from features.company_exposure.tests.test_exposure import materials
    from features.company_exposure.extraction import extract
    from features.company_exposure.store import ExposureStore
    profile = extract({'ticker': 'T'}, materials())
    ExposureStore(tmp_path).save(profile, materials=materials())
    body = draft()
    body['channels'] = [{'channel': 'financing_cost', 'explanation': '금리 상승으로 자금조달 비용 증가 가능',
                         'sourceRef': body['sourceRef'], 'companyLink': {'ticker': 'T',
                         'profileId': profile['profileId'], 'exposureId': profile['items'][0]['id']}}]
    store = PolicyStore(tmp_path); p = store.preview(body)
    assert p['resolvedLinks'][0]['quote'] == profile['items'][0]['quote']
    saved = store.confirm(p['draft'], preview_id=p['previewId'], user_confirmed=True, official_source_confirmed=True)
    assert saved['channels'][0]['resolvedCompanyLink']['sourceRef'] == profile['items'][0]['sourceRef']
    changed = materials('Higher interest rates would increase our net interest income.')
    ExposureStore(tmp_path).save(extract({'ticker': 'T'}, changed), materials=changed)
    with pytest.raises(ValueError, match='stale_exposure'):
        store.preview(body)
    assert len(store.list()) == 1


def test_condition_requires_current_revision_and_exact_overlap(tmp_path, monkeypatch):
    from features.macro_policy import links
    profile = {'profileId': 'p', 'items': [{'id': 'e', 'quote': 'Our borrowing cost risk.', 'sourceRef': {'url': 'https://official.example/a'}}]}
    monkeypatch.setattr(links, 'targets', lambda *a: {'profile': profile, 'reason': {'revisionId': 'r', 'conditions': ['금리 상승으로 비용이 늘면 다시 본다.']}})
    link = {'ticker': 'T', 'profileId': 'p', 'exposureId': 'e', 'condition': {'revisionId': 'r', 'index': 0, 'overlapQuote': '금리 상승'}}
    assert links.resolve(tmp_path, link, '금리 상승 경로')['condition']['layer'] == 'hypothesis'
    with pytest.raises(ValueError, match='overlapping'):
        links.resolve(tmp_path, link, '수요 감소 경로')
    link['condition']['revisionId'] = 'old'
    with pytest.raises(ValueError, match='stale_reason'):
        links.resolve(tmp_path, link, '금리 상승 경로')
