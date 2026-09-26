import datetime as dt
import asyncio
import json
from urllib.parse import urlsplit
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from features.common.macro_data.collect import collect
from features.common.macro_data.providers import OfficialReader,ProviderError
from features.common.macro_data.registry import BY_ID
from features.common.macro_data.store import MacroStore
from features.macro_map import operations
from features.macro_map.routes import create_macro_router
from .test_ledger import point


class ASGIClient:
    """Exercise HTTP routing without adding a test-only HTTP client dependency."""
    def __init__(self,app):self.app=app
    def request(self,method,url,body=None):
        parsed=urlsplit(url);messages=[]
        async def receive():return {'type':'http.request','body':json.dumps(body).encode() if body is not None else b'','more_body':False}
        async def send(message):messages.append(message)
        scope={'type':'http','http_version':'1.1','method':method,'scheme':'http','path':parsed.path,'raw_path':parsed.path.encode(),'query_string':parsed.query.encode(),'headers':[(b'content-type',b'application/json')],'server':('test',80),'client':('test',1),'root_path':''}
        asyncio.run(self.app(scope,receive,send))
        raw=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
        return SimpleNamespace(status_code=next(m['status'] for m in messages if m['type']=='http.response.start'),json=lambda:json.loads(raw))
    def get(self,url):return self.request('GET',url)
    def post(self,url,json):return self.request('POST',url,json)


def test_page_cursor_survives_failure_and_resumes(tmp_path):
    class Reader:
        attempt=0
        def fred_pages(self,spec,start,*,cursor,cancel):
            if not self.attempt:
                self.attempt+=1
                yield [point()],{'phase':'fred','chunk':100,'offset':0},'2026-09-27T01:00:00+00:00'
                raise ProviderError('provider_failed')
            assert cursor['chunk']==100
            yield [point(value='110',vintage='2024-03-01')],{'phase':'fred','chunk':200,'offset':0},'2026-09-27T01:00:00+00:00'
    reader=Reader()
    assert not collect(tmp_path,reader=reader,selected={'CPIAUCSL'})['ok']
    assert collect(tmp_path,reader=reader,selected={'CPIAUCSL'})['ok']
    store=MacroStore(tmp_path/'market-memory.sqlite3')
    assert len(store.revisions('CPIAUCSL','2024-01-01'))==2
    assert store.state('CPIAUCSL')['cursor']['phase']=='complete'


def test_cancel_does_not_advance_a_page(tmp_path):
    class Reader:
        def fred_pages(self,*args,**kwargs):yield [point()],{'phase':'fred','chunk':100},'2026-09-27T01:00:00+00:00'
    checks=0
    def cancel():
        nonlocal checks
        checks+=1
        if checks==2:raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError):collect(tmp_path,reader=Reader(),selected={'CPIAUCSL'},cancel=cancel)
    assert MacroStore(tmp_path/'market-memory.sqlite3').history('CPIAUCSL')==[]


def test_monthly_fred_pages_preserve_metadata_and_pagination():
    reader=OfficialReader(None,fred_key='never-written')
    requested=[]
    def fetch(endpoint,params,required):
        requested.append((endpoint,params))
        if endpoint=='series':return {'seriess':[{'id':'CPIAUCSL','units':'Old index','frequency_short':'M','seasonal_adjustment_short':'SA','realtime_start':'2000-01-01','realtime_end':'2024-02-01'},{'id':'CPIAUCSL','units':'New index','frequency_short':'M','seasonal_adjustment_short':'SA','realtime_start':'2024-02-02','realtime_end':'2026-09-26'}]},'2026-09-27T01:00:00Z'
        if endpoint.endswith('vintagedates'):return {'count':2,'vintage_dates':['2024-02-01','2024-02-02']},'2026-09-27T01:00:00Z'
        if params.get('output_type')==1:return {'count':1,'observations':[{'date':'2024-01-01','value':'200','realtime_start':'2024-02-02'}]},'2026-09-27T01:00:00Z'
        rows=[{'date':'2024-01-01','CPIAUCSL_20240201':'100','CPIAUCSL_20240202':'200'},{'date':'2024-02-01','CPIAUCSL_20240202':'.'}]
        return {'count':2,'observations':[rows[params['offset']]]},'2026-09-27T01:00:00Z'
    reader.fred=fetch
    pages=list(reader.fred_pages(BY_ID['CPIAUCSL'],'2000-01-01',cursor={'end':'2026-09-26'}))
    assert len(pages)==3
    assert [p['metadata']['unit'] for p in pages[0][0]]==['Old index','New index']
    assert pages[1][0][0]['value'] is None
    assert pages[2][1]['phase']=='fred_metadata'
    assert [p['offset'] for endpoint,p in requested if endpoint.endswith('observations')]==[0,1,0]


def test_scheduler_off_is_read_only_and_missed_runs_coalesce(tmp_path,monkeypatch):
    assert operations.scheduled_refresh(tmp_path) is None
    assert list(tmp_path.iterdir())==[]
    operations.save_settings(tmp_path,{'enabled':True})
    import features.common.jobs as jobs
    submissions=[]
    monkeypatch.setattr(jobs,'get_job',lambda _id:{'id':_id,'status':'done'})
    def submit(*args,**kwargs):submissions.append(args);return {'id':f'test-{len(submissions)}','status':'queued'}
    monkeypatch.setattr(jobs,'submit_job',submit)
    now=dt.datetime(2026,9,27,0,0,tzinfo=dt.timezone.utc)
    assert operations.scheduled_refresh(tmp_path,now)
    assert operations.scheduled_refresh(tmp_path,now) is None
    assert operations.scheduled_refresh(tmp_path,now+dt.timedelta(days=7))
    assert len(submissions)==2


def test_active_manual_and_scheduled_collection_share_one_job(tmp_path,monkeypatch):
    import features.common.jobs as jobs
    operations._save(tmp_path/'macro-refresh-state.json',{'jobId':'active'})
    monkeypatch.setattr(jobs,'get_job',lambda _id:{'id':_id,'status':'running'})
    monkeypatch.setattr(jobs,'submit_job',lambda *a,**k:pytest.fail('duplicate job'))
    assert operations.submit_refresh(tmp_path)['id']=='active'


def test_worker_failure_is_not_completed_and_cancellation_is_checked(tmp_path,monkeypatch):
    import features.common.jobs as jobs
    monkeypatch.setattr(jobs,'get_shared_job',lambda _id:SimpleNamespace(status=SimpleNamespace(value='running')))
    monkeypatch.setattr(operations,'collect',lambda *a,**k:{'ok':False,'series':[]})
    with pytest.raises(RuntimeError,match='incomplete'):operations.run_collection(tmp_path,start='2000-01-01',job_id='x')
    monkeypatch.setattr(jobs,'get_shared_job',lambda _id:SimpleNamespace(status=SimpleNamespace(value='cancel_requested')))
    def collecting(*a,**kwargs):kwargs['cancel']()
    monkeypatch.setattr(operations,'collect',collecting)
    with pytest.raises(RuntimeError,match='cancelled'):operations.run_collection(tmp_path,start='2000-01-01',job_id='x')


def test_api_validates_market_cutoff_settings_and_preserves_roundtrip(tmp_path):
    app=FastAPI();app.include_router(create_macro_router(tmp_path));client=ASGIClient(app)
    assert client.get('/api/macro').status_code==200
    assert len(client.get('/api/macro?market=KR').json()['items'])==8
    assert client.get('/api/macro?market=JP').status_code==400
    assert client.get('/api/macro?market=KR&mode=as_of').status_code==400
    assert client.get('/api/macro?date=2099-01-01').status_code==400
    assert client.post('/api/macro/settings',json={'enabled':'false'}).status_code==400
    assert client.post('/api/macro/settings',json={'enabled':True,'startYear':2000}).status_code==200
    assert client.get('/api/macro/settings').json()['enabled'] is True
    assert not (tmp_path/'market-memory.sqlite3').exists()


def test_shared_job_contract_supports_macro_without_ai_or_artifact():
    from features.common.shared_jobs_projection import new_shared_job,project_terminal_result
    from features.common.shared_jobs_schema import JobKind,TaskType,JobMode
    job=new_shared_job(kind=JobKind.MACRO_REFRESH,task_type=TaskType.MACRO_REFRESH,mode=JobMode.COLLECT,generation_mode='none',adapter='none',requested_mode=None,attempted_engine=None,clock=lambda:dt.datetime.now(dt.timezone.utc))
    assert job.labelCode.value=='macro_refresh'
    assert job.generationMode.value=='none'
    result=project_terminal_result(job,'done',{'savedCount':4})
    assert result.savedCount==4
