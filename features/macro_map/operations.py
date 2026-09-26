"""Explicit, opt-in collection using the existing SharedJob and scheduler lifecycle."""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

from features.common.atomic_replace import write_bytes_atomic
from features.common.macro_data.collect import collect

_LOCK=threading.RLock()
_SUBMITTED={}
ACTIVE={'queued','running','cancel_requested','committing'}


def _read(path):
    if not path.exists():return {}
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,OSError):raise ValueError('macro_settings_unreadable') from None


def _save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    write_bytes_atomic(path,json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8'))


def settings(root:Path):
    raw=_read(Path(root)/'macro-settings.json')
    year=raw.get('startYear',2000)
    if type(year) is not int or not 2000<=year<=dt.date.today().year:raise ValueError('invalid_macro_start_year')
    return {'enabled':raw.get('enabled') is True,'startYear':raw.get('startYear',2000),'scheduleTimezone':'Asia/Seoul','scheduleTimes':['09:00','21:00']}


def save_settings(root:Path,body):
    if set(body)-{'enabled','startYear'}:raise ValueError('invalid_macro_setting')
    if 'enabled' in body and type(body['enabled']) is not bool:raise ValueError('invalid_macro_enabled')
    if 'startYear' in body and (type(body['startYear']) is not int or not 2000<=body['startYear']<=dt.date.today().year):raise ValueError('invalid_macro_start_year')
    with _LOCK:
        current=settings(root);current.update(body)
        _save(Path(root)/'macro-settings.json',current)
        return settings(root)


def run_collection(root:Path,*,start,job_id,progress=None):
    from features.common.jobs import get_shared_job
    def cancel():
        job=get_shared_job(job_id)
        if job is None or job.status.value in {'cancel_requested','cancelled','failed_restart'}:raise RuntimeError('macro_cancelled')
    if progress:progress(message='공식 거시 자료를 확인하고 있습니다.')
    result=collect(root,start=start,cancel=cancel)
    if not result['ok']:raise RuntimeError('macro_collection_incomplete')
    return {**result,'savedCount':sum(r['inserted'] for r in result['series'])}


def current_job(root:Path):
    from features.common.jobs import get_job
    root=Path(root).resolve()
    job_id=_SUBMITTED.get(str(root)) or _read(root/'macro-refresh-state.json').get('jobId')
    return get_job(job_id) if job_id else None


def submit_refresh(root:Path,*,slot=None):
    from features.common.jobs import submit_job
    root=Path(root).resolve()
    with _LOCK:
        clock=dt.datetime.now(dt.timezone.utc)
        if slot is None:slot=int(clock.timestamp())//43200
        job=current_job(root)
        if job and job.get('status') in ACTIVE:
            _save(root/'macro-refresh-state.json',{'jobId':job['id'],'slot':slot,'submittedAt':clock.isoformat()})
            return job
        config=settings(root)
        job=submit_job('macro_refresh','거시 자료 갱신',run_collection,root,start=f"{config['startYear']}-01-01",pass_job_id=True,dedicated_thread=True)
        # Keep the identity even if the settings write fails after submission. The
        # in-flight worker remains discoverable and cannot be submitted twice.
        _SUBMITTED[str(root)]=job['id']
        _save(root/'macro-refresh-state.json',{'jobId':job['id'],'slot':slot,'submittedAt':clock.isoformat()})
        return job


def scheduled_refresh(root:Path,now=None):
    root=Path(root)
    if not settings(root)['enabled']:return None
    clock=now or dt.datetime.now(dt.timezone.utc)
    # UTC 00:00/12:00 == KST 09:00/21:00. Missed slots coalesce into this one.
    slot=int(clock.timestamp())//43200
    with _LOCK:
        state=_read(root/'macro-refresh-state.json')
        if state.get('slot')==slot:return None
        return submit_refresh(root,slot=slot)
