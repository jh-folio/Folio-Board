import datetime as dt
import io
import json
import sqlite3
import urllib.error
from types import SimpleNamespace

import pytest

from features.common.macro_data import providers, store as store_module
from features.common.macro_data.collect import collect
from features.common.macro_data.registry import BY_ID
from features.common.macro_data.store import MacroStore
from features.common.macro_data.transforms import spread
from features.macro_map import operations
from features.macro_map.service import map_snapshot
from features.market_calendar.service import upsert_events
from .test_ledger import point, write


def test_equivalent_numeric_forms_and_negative_zero_are_idempotent(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    assert write(store, point(value='-0.20')) == 1
    assert write(store, point(value='-0.2')) == 0
    assert write(store, point(value='-0', vintage='2024-03-01')) == 1
    assert write(store, point(value='0', vintage='2024-03-01')) == 0
    assert not store.history('CPIAUCSL')[0]['conflict']


def test_schema_ddl_failure_rolls_back_and_existing_data_is_backed_up(tmp_path, monkeypatch):
    path = tmp_path / 'market-memory.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE notes(id TEXT)')
        c.execute("INSERT INTO notes VALUES('keep')")
    monkeypatch.setattr(store_module, 'DDL', store_module.DDL + ('INVALID SQL',))
    with pytest.raises(sqlite3.OperationalError):
        MacroStore(path).ensure()
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT * FROM notes').fetchall() == [('keep',)]
        assert c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'macro_%'").fetchall() == []
    assert len(list((tmp_path / 'backups').glob('*.sqlite3'))) == 1


def test_expanding_history_does_not_use_incremental_cursor(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    store.set_state('CPIAUCSL', 'ok', cursor={'phase': 'complete', 'start': '2010-01-01'})

    class Reader:
        def fred_pages(self, spec, start, *, cursor, cancel):
            assert start == '2000-01-01' and not cursor
            yield [point()], {'phase': 'fred'}, '2026-09-27T00:00:00Z'

    assert collect(tmp_path, start='2000-01-01', reader=Reader(), selected={'CPIAUCSL'})['ok']


def test_invalid_provider_page_retains_earlier_page_and_failure_state(tmp_path):
    class Reader:
        def fred_pages(self, *a, **k):
            yield [point()], {'phase': 'fred', 'chunk': 100}, '2026-09-27T00:00:00Z'
            yield [point(value='nan')], {'phase': 'fred', 'chunk': 200}, '2026-09-27T00:00:00Z'

    assert not collect(tmp_path, reader=Reader(), selected={'CPIAUCSL'})['ok']
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    assert store.state('CPIAUCSL')['cursor']['chunk'] == 100
    assert store.state('CPIAUCSL')['status'] == 'provider_failed'
    assert store.history('CPIAUCSL')[0]['value'] == 100


def test_no_keys_is_explicit_without_calling_network(tmp_path):
    reader = providers.OfficialReader(None, transport=lambda _: pytest.fail('network'))
    result = collect(tmp_path, reader=reader, selected={'CPIAUCSL', 'KR_CPI'})
    assert not result['ok'] and {r['status'] for r in result['series']} == {'not_connected'}


def test_429_retries_and_timeout_does_not_expose_url(monkeypatch):
    calls = []

    def request(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError('https://example.test?api_key=secret', 429, 'limited', {}, None)
        return io.BytesIO(b'{"ok":true}')

    monkeypatch.setattr(providers.urllib.request, 'urlopen', request)
    monkeypatch.setattr(providers.time, 'sleep', lambda _: None)
    assert providers.get_json('never-output') == {'ok': True} and len(calls) == 3

    def timeout(*a, **k):
        raise TimeoutError('https://example.test?api_key=secret')

    monkeypatch.setattr(providers.urllib.request, 'urlopen', timeout)
    with pytest.raises(providers.ProviderError) as caught:
        providers.get_json('never-output')
    assert str(caught.value) == 'provider_unavailable'


def test_stale_cache_is_not_accepted_as_a_successful_fetch():
    runtime = SimpleNamespace(fetch=lambda *a, **k: {'status': 'stale', 'value': {}, 'fetchedAt': '2020-01-01T00:00:00Z'})
    reader = providers.OfficialReader(runtime, fred_key='test')
    with pytest.raises(providers.ProviderError):
        reader.fred('series', {}, 'seriess')


def test_daily_long_form_resumes_offset_and_keeps_withdrawal():
    reader = providers.OfficialReader(None, fred_key='test')
    requests = []

    def fetch(endpoint, params, required):
        requests.append(params)
        if endpoint == 'series':
            return {'seriess': [{'id': 'DFF', 'units': 'Percent', 'frequency_short': 'D', 'seasonal_adjustment_short': 'NSA', 'realtime_start': '2000-01-01', 'realtime_end': '2026-09-26'}]}, '2026-09-27T00:00:00Z'
        if endpoint.endswith('vintagedates'):
            return {'count': 1, 'vintage_dates': ['2024-01-02']}, '2026-09-27T00:00:00Z'
        assert params['output_type'] == 1 and params['offset'] == 1
        return {'count': 2, 'observations': [{'date': '2024-01-01', 'value': '.', 'realtime_start': '2024-01-02'}]}, '2026-09-27T00:00:00Z'

    reader.fred = fetch
    pages = list(reader.fred_pages(BY_ID['DFF'], '2000-01-01', cursor={'end': '2024-12-31', 'window': '2024-01-01', 'offset': 1}))
    assert len(pages) == 1 and pages[0][0][0]['value'] == '.'
    assert pages[0][1]['window'] == '2025-01-01'


def test_ecos_refuses_wrong_or_extra_dimension():
    reader = providers.OfficialReader(None, ecos_key='test')
    reader._fetch = lambda *a, **k: (
        {'StatisticSearch': {'list_total_count': 1, 'row': [{'STAT_CODE': '901Y009', 'ITEM_CODE1': '0', 'ITEM_CODE2': 'different', 'TIME': '202408', 'UNIT_NAME': 'Index', 'DATA_VALUE': '1'}]}},
        '2026-09-27T00:00:00Z',
    )
    with pytest.raises(providers.ProviderError, match='dimension'):
        list(reader.ecos_pages(BY_ID['KR_CPI'], '2000-01-01'))


def test_scheduling_deduplicates_active_job_across_slot_and_write_failure(tmp_path, monkeypatch):
    import features.common.jobs as jobs
    monkeypatch.setattr(jobs, 'get_job', lambda id: {'id': id, 'status': 'running'})
    count = []
    monkeypatch.setattr(jobs, 'submit_job', lambda *a, **k: (count.append(1) or {'id': 'running', 'status': 'queued'}))
    save = operations._save
    monkeypatch.setattr(operations, '_save', lambda *a: (_ for _ in ()).throw(OSError('locked')))
    with pytest.raises(OSError):
        operations.submit_refresh(tmp_path)
    assert operations.current_job(tmp_path)['id'] == 'running'
    monkeypatch.setattr(operations, '_save', save)
    operations.save_settings(tmp_path, {'enabled': True})
    now = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
    assert operations.scheduled_refresh(tmp_path, now)['id'] == 'running'
    assert operations.scheduled_refresh(tmp_path, now) is None
    assert len(count) == 1


def test_calendar_day_link_cannot_set_official_release_or_leak_future_schedule(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    write(store, point())
    upsert_events(store.path, [{
        'kind': 'macro',
        'provider': 'fred',
        'title': '미국 CPI',
        'market': 'US',
        'status': 'confirmed',
        'startsAt': '2024-03-01T08:30:00-05:00',
        'sourceUrl': 'https://fred.stlouisfed.org/release?rid=10',
        'fetchedAt': '2024-02-02T12:00:00Z',
    }])
    before = map_snapshot(tmp_path, mode='as_of', date='2024-02-01', series_id='CPIAUCSL')['items'][0]
    after = map_snapshot(tmp_path, mode='as_of', date='2024-02-03', series_id='CPIAUCSL')['items'][0]
    assert before['nextRelease'] is None
    assert after['nextRelease']['date'] == '2024-03-01' and after['nextRelease']['precision'] == 'date'
    assert after['latest']['releasedAt'] is None and after['latest']['availabilityBasis'] == 'provider_vintage'


def test_revision_period_selection_and_spread_missing_leg(tmp_path):
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    write(store, point(), point('2024-02-01', '102', '2024-03-01'))
    item = map_snapshot(tmp_path, series_id='CPIAUCSL', period='2024-01-01')['items'][0]
    assert item['revisionPeriod'] == '2024-01-01' and len(item['revisions']) == 1
    p = store.history('CPIAUCSL')[0]
    assert spread([], [p])[0]['displayValue'] is None
    result = spread([{**p, 'value': 4}], [{**p, 'value': 3}])[0]
    assert result['value'] == 1 and result['metadata']['unit'] == '%p'


@pytest.mark.parametrize('outcome', ['done', 'failed', 'cancelled'])
def test_real_shared_job_lifecycle_uses_macro_result_and_cancel_boundary(tmp_path, monkeypatch, outcome):
    from features.common import jobs
    monkeypatch.setattr(jobs, 'JOBS_PATH', tmp_path / 'jobs.json')
    jobs._LIFECYCLES.clear()
    job = jobs.new_shared_job(kind='macro_refresh', task_type='macro_refresh', generation_mode='none', adapter='none', requested_mode=None, mode='collect', attempted_engine=None, clock=jobs._clock)
    jobs.shared_store().add(job)
    jobs.private_lifecycle().set_private(job.id, {})

    def worker(root, *, start, cancel):
        if outcome == 'cancelled':
            jobs.cancel_job(job.id)
            cancel()
        return {'ok': outcome == 'done', 'series': [{'inserted': 2}], 'agentCalled': False}

    monkeypatch.setattr(operations, 'collect', worker)
    jobs.run_job(job.id, operations.run_collection, tmp_path, start='2000-01-01', _folio_job_id=job.id)
    saved = jobs.get_job(job.id)
    assert saved['status'] == outcome
    if outcome == 'done':
        assert saved['result']['savedCount'] == 2


def test_restart_terminates_orphan_and_keeps_committed_page(tmp_path, monkeypatch):
    from features.common import jobs
    monkeypatch.setattr(jobs, 'JOBS_PATH', tmp_path / 'jobs.json')
    jobs._LIFECYCLES.clear()
    job = jobs.new_shared_job(kind='macro_refresh', task_type='macro_refresh', generation_mode='none', adapter='none', requested_mode=None, mode='collect', attempted_engine=None, clock=jobs._clock)
    jobs.shared_store().add(job)
    jobs.private_lifecycle().set_private(job.id, {})
    store = MacroStore(tmp_path / 'market-memory.sqlite3')
    write(store, point())
    operations._save(tmp_path / 'macro-refresh-state.json', {'jobId': job.id})
    jobs.load_jobs()
    assert operations.current_job(tmp_path)['status'] == 'failed_restart'
    assert store.history('CPIAUCSL')[0]['value'] == 100 and store.state('CPIAUCSL')['cursor'] == {'page': 2}


def test_cache_budget_preserves_fresh_and_unowned_files(tmp_path):
    import os
    from features.common.macro_data.cache_policy import prune_owned_cache
    old = tmp_path / ('fred_macro_series_' + ('a' * 24) + '.json')
    fresh = tmp_path / ('ecos_macro_observations_' + ('b' * 24) + '.json')
    unrelated = tmp_path / 'user.json'
    for path in (old, fresh, unrelated):
        path.write_text('x' * 80)
    os.utime(old, (0, 0))
    os.utime(fresh, (10000, 10000))
    os.utime(unrelated, (0, 0))
    assert prune_owned_cache(tmp_path, budget_bytes=100, now=10001) == 1
    assert fresh.exists() and unrelated.exists() and not old.exists()


def test_unreadable_cache_cleanup_does_not_fail_a_collection(tmp_path, monkeypatch):
    from pathlib import Path
    from features.common.macro_data.cache_policy import prune_owned_cache

    def denied(_):
        raise PermissionError('locked cache directory')

    monkeypatch.setattr(Path, 'iterdir', denied)
    assert prune_owned_cache(tmp_path) == 0


class _OneKeyReader:
    """FRED 키만 있는 사용자. 한국 원천은 키가 없어 연결되지 않는다."""

    def __init__(self, fred_fails=False):
        self.fred_fails = fred_fails

    def fred_pages(self, spec, start, *, cursor, cancel):
        if self.fred_fails:
            raise providers.ProviderError('provider_failed')
        yield [point()], {'phase': 'fred'}, '2026-09-27T00:00:00Z'

    def ecos_pages(self, spec, start, *, cursor, cancel):
        raise providers.ProviderError('not_connected')
        yield


def test_missing_key_is_skipped_not_failed_when_connected_sources_succeed(tmp_path):
    result = collect(tmp_path, reader=_OneKeyReader(), selected={'CPIAUCSL', 'KR_CPI'})
    assert result['ok']
    assert result['notConnected'] == ['KR_CPI']
    assert operations.source_summary(tmp_path) == {'ok': 1, 'notConnected': 1, 'failed': 0}


def test_connected_source_failure_is_still_incomplete(tmp_path):
    result = collect(tmp_path, reader=_OneKeyReader(fred_fails=True), selected={'CPIAUCSL', 'KR_CPI'})
    assert not result['ok']
    assert operations.source_summary(tmp_path) == {'ok': 0, 'notConnected': 1, 'failed': 1}


def test_worker_completes_with_one_key_and_names_the_no_key_failure(tmp_path, monkeypatch):
    import features.common.jobs as jobs
    monkeypatch.setattr(jobs, 'get_shared_job', lambda _id: SimpleNamespace(status=SimpleNamespace(value='running')))
    monkeypatch.setattr(operations, 'collect', lambda root, **k: collect(root, reader=_OneKeyReader(), selected={'CPIAUCSL', 'KR_CPI'}, cancel=k['cancel']))
    done = operations.run_collection(tmp_path, start='2000-01-01', job_id='x')
    assert done['savedCount'] == 1 and done['notConnected'] == ['KR_CPI']

    no_keys = {'ok': False, 'series': [{'seriesId': 'CPIAUCSL', 'status': 'not_connected', 'inserted': 0}]}
    monkeypatch.setattr(operations, 'collect', lambda *a, **k: no_keys)
    with pytest.raises(RuntimeError, match='macro_not_connected'):
        operations.run_collection(tmp_path, start='2000-01-01', job_id='x')


def test_refresh_status_reports_source_summary_without_writing(tmp_path):
    from fastapi import FastAPI
    from features.macro_map.routes import create_macro_router
    from .test_collection import ASGIClient

    app = FastAPI()
    app.include_router(create_macro_router(tmp_path))
    body = ASGIClient(app).get('/api/macro/refresh').json()
    assert body == {'job': None, 'sources': {'ok': 0, 'notConnected': 0, 'failed': 0}}
    assert not (tmp_path / 'market-memory.sqlite3').exists()
