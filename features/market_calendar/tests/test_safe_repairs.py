import json
import sqlite3

import pytest

from features.market_calendar.schema import normalize_event
from features.market_calendar.service import upsert_events
from features.market_calendar.repairs import store_calendar_refresh


def legacy(**extra):
    return normalize_event({'title':'한국 소비자물가지수 (CPI)','kind':'macro','market':'KR','provider':'bok','timezone':'Asia/Seoul','startsAt':'2026-07-15T08:00:00','observedAt':'202607','actualValue':'119.77','unit':'2020=100','status':'actual',**extra})


def replacement(**extra):return legacy(startsAt='2026-08-02',allDay=True,status='estimated',**extra)


def ids(db):
    with sqlite3.connect(db) as conn:return {r[0] for r in conn.execute('SELECT id FROM market_calendar_events')}


def test_success_keeps_backup_evidence_and_untouched_rows(tmp_path):
    db=tmp_path/'market-memory.sqlite3';old=legacy();outside=legacy(startsAt='2006-07-15T08:00:00',observedAt='200607')
    other_time=legacy(startsAt='2026-07-15T09:00:00');rate=legacy(kind='central_bank',title='한국은행 기준금리 결정')
    upsert_events(db,[old,outside,other_time,rate])
    assert store_calendar_refresh(db,[replacement()])==(1,1)
    assert ids(db)=={outside['id'],other_time['id'],rate['id'],replacement()['id']}
    with sqlite3.connect(db) as conn:
        saved=conn.execute('SELECT old_row_json,backup_name FROM market_calendar_repairs').fetchone()
        assert json.loads(saved[0])['actual_value']=='119.77'
    backup=tmp_path/'backups'/saved[1]
    assert old['id'] in ids(backup)
    assert store_calendar_refresh(db,[replacement()])==(1,0)


@pytest.mark.parametrize('fresh',[[],[replacement(actualValue='')],[replacement(actualValue='120')],[replacement(unit='other')]])
def test_missing_failed_or_unmatched_replacement_keeps_old_row(tmp_path,fresh):
    db=tmp_path/'market-memory.sqlite3';upsert_events(db,[legacy()])
    store_calendar_refresh(db,fresh)
    assert legacy()['id'] in ids(db)
    assert not (tmp_path/'backups').exists()


def test_failure_rolls_back_replacement_and_deletion(tmp_path):
    db=tmp_path/'market-memory.sqlite3';upsert_events(db,[legacy()])
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER refuse_delete BEFORE DELETE ON market_calendar_events BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError):store_calendar_refresh(db,[replacement()])
    assert ids(db)=={legacy()['id']}
    assert len(list((tmp_path/'backups').glob('*.sqlite3')))==1


def test_unknown_parser_and_noncanonical_id_are_preserved(tmp_path):
    db=tmp_path/'market-memory.sqlite3'
    rows=[legacy(parserVersion='new-parser'),legacy(id='user-row')]
    upsert_events(db,rows);store_calendar_refresh(db,[replacement()])
    assert {r['id'] for r in rows}<=ids(db)


def test_backup_failure_preserves_original_database(tmp_path,monkeypatch):
    import features.market_calendar.repairs as repairs
    db=tmp_path/'market-memory.sqlite3';upsert_events(db,[legacy()])
    monkeypatch.setattr(repairs,'backup_database',lambda *a:(_ for _ in ()).throw(OSError('locked')))
    with pytest.raises(OSError):store_calendar_refresh(db,[replacement()])
    assert ids(db)=={legacy()['id']}


def test_display_projection_only_collapses_exact_numeric_readings(tmp_path):
    from features.market_calendar.service import list_events
    exact=replacement(provider='yfinance_economic',title='KR CPI Index',observedAt='2026-07-01')
    different=replacement(provider='yfinance_economic',title='KR CPI Index',unit='%',actualValue='2.3')
    unknown=replacement(provider='yfinance_economic',title='KR Consumer Price Index',observedAt='')
    db=tmp_path/'market-memory.sqlite3';upsert_events(db,[replacement(),exact,different,unknown])
    # exact and different share provider/title/date, so assign independent provider IDs.
    different['id']='different-unit';upsert_events(db,[exact,different])
    before=ids(db);events=list_events(db)['events']
    assert len(events)==3 and len(before)==4 and ids(db)==before
    assert sum(len(e.get('additionalSources',[])) for e in events)==1


@pytest.mark.parametrize('case',['no_key','timeout','empty','partial'])
def test_refresh_integration_preserves_unmatched_rows(tmp_path,monkeypatch,case):
    import features.market_calendar.service as service
    import features.llm_settings.client as settings
    db=tmp_path/'market-memory.sqlite3'
    old=legacy();outside=legacy(startsAt='2006-07-15T08:00:00',observedAt='200607')
    upsert_events(db,[old,outside])
    monkeypatch.setattr(service,'_calendar_target_tickers',lambda _:[])
    for name in ('local_filing_events','official_holiday_events','official_fomc_events','official_central_bank_events'):
        monkeypatch.setattr(service,name,lambda *a,**k:[])
    monkeypatch.setattr(service,'fetch_yf_economic_events',lambda **k:[])
    monkeypatch.setattr(settings,'fred_api_key',lambda:'')
    monkeypatch.setattr(settings,'bok_api_key',lambda:'' if case=='no_key' else 'test')
    if case=='timeout':
        # Real BOK transport failure is converted to an empty source result by its adapter.
        import features.market_calendar.adapters.bok as bok
        monkeypatch.setattr(bok.urllib.request,'urlopen',lambda *a,**k:(_ for _ in ()).throw(TimeoutError()))
    else:monkeypatch.setattr(service,'fetch_bok_macro_events',lambda *a,**k:[replacement()] if case=='partial' else [])
    result=service.refresh_calendar(tmp_path,include_estimates=False)
    assert outside['id'] in ids(db) and result['agentCalled'] is False
    assert (old['id'] not in ids(db))==(case=='partial')
