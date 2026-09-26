import datetime as dt
import sqlite3

import pytest

from features.common.macro_data.store import MacroStore
from features.common.macro_data.schema import day_end
from features.common.macro_data.providers import parse_fred_vintages
from features.macro_map.service import map_snapshot


def point(period='2024-01-01',value='100',vintage='2024-02-01',*,series='CPIAUCSL',unit='Index',fetched='2026-09-27T01:00:00+00:00',**extra):
    return {'seriesId':series,'period':period,'value':value,'vintageDate':vintage,'availabilityBasis':'provider_vintage','fetchedAt':fetched,
            'metadata':{'unit':unit,'frequency':'M','adjustment':'SA','definitionVersion':'v1'},**extra}


def write(store,*rows):return store.ingest(rows[0]['seriesId'],rows,cursor={'page':2},status='ok')


def test_empty_reads_create_nothing(tmp_path):
    assert map_snapshot(tmp_path)['items'][0]['latest'] is None
    assert list(tmp_path.iterdir())==[]


def test_backup_additive_migration_and_reopen(tmp_path):
    path=tmp_path/'market-memory.sqlite3'
    with sqlite3.connect(path) as conn:conn.execute('CREATE TABLE notes(id TEXT)');conn.execute("INSERT INTO notes VALUES('keep')")
    store=MacroStore(path);write(store,point());store.ensure()
    with sqlite3.connect(path) as conn:assert conn.execute('SELECT * FROM notes').fetchall()==[('keep',)]
    backups=list((tmp_path/'backups').glob('*.sqlite3'));assert len(backups)==1
    with sqlite3.connect(backups[0]) as conn:assert conn.execute('SELECT * FROM notes').fetchall()==[('keep',)]
    assert MacroStore(path).history('CPIAUCSL')[0]['value']==100


def test_vintage_replay_excludes_later_revisions_and_does_not_require_early_download(tmp_path):
    store=MacroStore(tmp_path/'market-memory.sqlite3')
    write(store,point(),point(value='110',vintage='2024-03-01'))
    assert store.history('CPIAUCSL',cutoff=day_end('2024-02-15','America/Chicago'))[0]['value']==100
    assert store.history('CPIAUCSL')[0]['value']==110
    assert store.history('CPIAUCSL',cutoff='2024-02-01T12:00:00+00:00')==[]
    assert len(store.revisions('CPIAUCSL','2024-01-01'))==2


def test_newer_schema_cannot_be_written_by_older_runtime(tmp_path):
    store=MacroStore(tmp_path/'market-memory.sqlite3');write(store,point())
    with sqlite3.connect(store.path) as conn:conn.execute('INSERT INTO macro_schema VALUES(2)')
    before=store.path.read_bytes()
    with pytest.raises(RuntimeError,match='newer_than_runtime'):write(store,point(value='101'))
    assert store.path.read_bytes()==before


def test_quarterly_staleness_counts_from_end_of_observed_quarter(tmp_path):
    store=MacroStore(tmp_path/'market-memory.sqlite3')
    write(store,point('2026-01-01',series='GDPC1',vintage='2026-07-01',metadata={'unit':'Dollars','frequency':'Q','adjustment':'SA','definitionVersion':'v1'}),
          point('2026-04-01','101',series='GDPC1',vintage='2026-08-01',metadata={'unit':'Dollars','frequency':'Q','adjustment':'SA','definitionVersion':'v1'}))
    item=map_snapshot(tmp_path,series_id='GDPC1',now=dt.datetime(2026,9,27,tzinfo=dt.timezone.utc))['items'][0]
    assert 'stale' not in item['quality']
    item=map_snapshot(tmp_path,series_id='GDPC1',now=dt.datetime(2026,12,1,tzinfo=dt.timezone.utc))['items'][0]
    assert 'stale' in item['quality']


def test_idempotent_and_equal_snapshots_are_not_revisions_but_returning_values_are(tmp_path):
    store=MacroStore(tmp_path/'m.sqlite3')
    assert write(store,point())==1
    assert write(store,point())==0
    assert write(store,point(vintage='2024-02-02'))==0
    assert write(store,point(value='101',vintage='2024-03-01'),point(value='100',vintage='2024-04-01'))==2
    assert len(store.revisions('CPIAUCSL','2024-01-01'))==3


def test_same_vintage_conflict_retains_both_and_does_not_pick_one(tmp_path):
    store=MacroStore(tmp_path/'m.sqlite3');write(store,point(),point(value='101'))
    p=store.history('CPIAUCSL')[0]
    assert p['value'] is None and p['conflict']
    assert {p['value'] for p in store.revisions('CPIAUCSL','2024-01-01')}=={100,101}


def test_local_observation_is_not_backdated_to_measurement_period(tmp_path):
    store=MacroStore(tmp_path/'m.sqlite3')
    p=point(series='KR_CPI',availabilityBasis='local_observed',vintageDate=None)
    write(store,p)
    assert store.history('KR_CPI',cutoff='2025-01-01T00:00:00+00:00')==[]
    with pytest.raises(ValueError,match='korean_historical'):map_snapshot(tmp_path,market='KR',mode='as_of',date='2024-02-01')


def test_page_validation_is_atomic_and_preserves_cursor(tmp_path):
    store=MacroStore(tmp_path/'m.sqlite3');write(store,point())
    with pytest.raises(ValueError):store.ingest('CPIAUCSL',[point(value='102',vintage='2024-04-01'),point(value='nan')],cursor={'page':3})
    assert len(store.revisions('CPIAUCSL','2024-01-01'))==1
    assert store.state('CPIAUCSL')['cursor']=={'page':2}


def test_database_failure_rolls_back_rows_and_cursor(tmp_path):
    store=MacroStore(tmp_path/'m.sqlite3');write(store,point())
    with sqlite3.connect(store.path) as conn:
        conn.execute("CREATE TRIGGER fail_state BEFORE UPDATE ON macro_collection_state BEGIN SELECT RAISE(ABORT,'test failure'); END")
    with pytest.raises(sqlite3.IntegrityError):store.ingest('CPIAUCSL',[point(value='102',vintage='2024-04-01')],cursor={'page':3})
    assert len(store.revisions('CPIAUCSL','2024-01-01'))==1
    assert store.state('CPIAUCSL')['cursor']=={'page':2}


@pytest.mark.parametrize('scenario,base,current',[('normal','100','102'),('inflation_shock','100','115'),('tightening','110','113'),('recession_transition','110','105')])
def test_transform_denominator_uses_the_same_cutoff(tmp_path,scenario,base,current):
    store=MacroStore(tmp_path/'market-memory.sqlite3')
    write(store,point('2023-01-01',base,'2023-02-01'),point('2024-01-01',current,'2024-02-01'),point('2023-01-01','150','2025-01-01'))
    snapshot=map_snapshot(tmp_path,mode='as_of',date='2024-02-15',series_id='CPIAUCSL')
    assert snapshot['items'][0]['latest']['displayValue']==pytest.approx((float(current)/float(base)-1)*100)
    assert snapshot['items'][0]['latestRevisedComparison'][-1]['displayValue']!=snapshot['items'][0]['latest']['displayValue']
    assert all(p['availableAt']<=snapshot['cutoff'] for p in snapshot['items'][0]['history'])


def test_method_change_and_missing_period_do_not_produce_growth(tmp_path):
    store=MacroStore(tmp_path/'market-memory.sqlite3')
    write(store,point('2023-01-01'),point('2024-01-01',unit='New base',vintage='2024-02-01'))
    latest=map_snapshot(tmp_path,series_id='CPIAUCSL')['items'][0]['latest']
    assert latest['displayValue'] is None and latest['calculationGap']=='method_changed'


def test_parser_retains_all_periods_and_zero_and_withdrawal():
    data={'observations':[{'date':'2024-01-01','DFF_20240201':'0','DFF_20240301':'.'},{'date':'2023-12-01','DFF_20240201':'2'}]}
    rows=list(parse_fred_vintages(data,'DFF'))
    assert len(rows)==3 and rows[0]['value']=='0' and rows[1]['value'] is None


def test_provider_failure_preserves_last_known_value_and_marks_it(tmp_path):
    store=MacroStore(tmp_path/'market-memory.sqlite3');write(store,point())
    store.set_state('CPIAUCSL','provider_failed',error='provider_failed')
    item=map_snapshot(tmp_path,series_id='CPIAUCSL')['items'][0]
    assert item['latest']['value']==100 and 'provider_failed' in item['quality'] and 'stale' in item['quality']


def test_sixteen_indicators_no_invented_score(tmp_path):
    items=[p for market in ('US','KR') for p in map_snapshot(tmp_path,market=market)['items']]
    assert len(items)==16
    assert not any('verdict' in p or 'score' in p for p in items)
