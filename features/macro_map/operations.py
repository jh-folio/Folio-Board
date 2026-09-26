"""Explicit, opt-in collection using the existing SharedJob and scheduler lifecycle."""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

from features.common.atomic_replace import write_bytes_atomic
from features.common.macro_data.collect import collect
from features.common.macro_data.store import MacroStore

_LOCK = threading.RLock()
_SUBMITTED = {}
ACTIVE = {'queued', 'running', 'cancel_requested', 'committing'}


def _read(path):
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise ValueError('macro_settings_unreadable') from None


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


def settings(root: Path):
    # 자동 갱신은 사용자가 켜기 전까지 꺼져 있다(D5-A).
    raw = _read(Path(root) / 'macro-settings.json')
    year = raw.get('startYear', 2000)
    if type(year) is not int or not 2000 <= year <= dt.date.today().year:
        raise ValueError('invalid_macro_start_year')
    return {
        'enabled': raw.get('enabled') is True,
        'startYear': raw.get('startYear', 2000),
        'scheduleTimezone': 'Asia/Seoul',
        'scheduleTimes': ['09:00', '21:00'],
    }


def save_settings(root: Path, body):
    if set(body) - {'enabled', 'startYear'}:
        raise ValueError('invalid_macro_setting')
    if 'enabled' in body and type(body['enabled']) is not bool:
        raise ValueError('invalid_macro_enabled')
    if 'startYear' in body and (type(body['startYear']) is not int or not 2000 <= body['startYear'] <= dt.date.today().year):
        raise ValueError('invalid_macro_start_year')
    with _LOCK:
        current = settings(root)
        current.update(body)
        _save(Path(root) / 'macro-settings.json', current)
        return settings(root)


def run_collection(root: Path, *, start, job_id, progress=None):
    from features.common.jobs import get_shared_job

    def cancel():
        job = get_shared_job(job_id)
        if job is None or job.status.value in {'cancel_requested', 'cancelled', 'failed_restart'}:
            raise RuntimeError('macro_cancelled')

    if progress:
        progress(message='공식 거시 자료를 확인하고 있습니다.')
    result = collect(root, start=start, cancel=cancel)
    if not result['ok']:
        # 이미 저장한 페이지는 남는다. 다만 부분 성공을 완료로 기록하지 않는다.
        connected = [r for r in result['series'] if r.get('status') != 'not_connected']
        raise RuntimeError('macro_collection_incomplete' if connected else 'macro_not_connected')
    return {**result, 'savedCount': sum(r['inserted'] for r in result['series'])}


def source_summary(root: Path):
    # 원천별 마지막 수집 상태를 센다. 작업 오류 코드는 공통 코드로 뭉개지므로,
    # 화면은 이 요약으로 "키가 없어 건너뜀"과 "원천 확인 실패"를 나눠 말한다. 읽기만 한다.
    counts = {'ok': 0, 'notConnected': 0, 'failed': 0}
    for state in MacroStore(Path(root) / 'market-memory.sqlite3').state():
        status = state.get('status')
        if status == 'ok':
            counts['ok'] += 1
        elif status == 'not_connected':
            counts['notConnected'] += 1
        else:
            counts['failed'] += 1
    return counts


def current_job(root: Path):
    from features.common.jobs import get_job
    root = Path(root).resolve()
    job_id = _SUBMITTED.get(str(root)) or _read(root / 'macro-refresh-state.json').get('jobId')
    return get_job(job_id) if job_id else None


def submit_refresh(root: Path, *, slot=None):
    from features.common.jobs import submit_job
    root = Path(root).resolve()
    with _LOCK:
        clock = dt.datetime.now(dt.timezone.utc)
        if slot is None:
            slot = int(clock.timestamp()) // 43200
        # 이미 도는 수집이 있으면 새로 만들지 않고 그 작업을 돌려준다.
        job = current_job(root)
        if job and job.get('status') in ACTIVE:
            _save(root / 'macro-refresh-state.json', {'jobId': job['id'], 'slot': slot, 'submittedAt': clock.isoformat()})
            return job
        config = settings(root)
        job = submit_job(
            'macro_refresh',
            '거시 자료 갱신',
            run_collection,
            root,
            start=f"{config['startYear']}-01-01",
            pass_job_id=True,
            dedicated_thread=True,
        )
        # Keep the identity even if the settings write fails after submission. The
        # in-flight worker remains discoverable and cannot be submitted twice.
        _SUBMITTED[str(root)] = job['id']
        _save(root / 'macro-refresh-state.json', {'jobId': job['id'], 'slot': slot, 'submittedAt': clock.isoformat()})
        return job


def scheduled_refresh(root: Path, now=None):
    root = Path(root)
    if not settings(root)['enabled']:
        return None
    clock = now or dt.datetime.now(dt.timezone.utc)
    # UTC 00:00/12:00 == KST 09:00/21:00. Missed slots coalesce into this one.
    slot = int(clock.timestamp()) // 43200
    with _LOCK:
        state = _read(root / 'macro-refresh-state.json')
        if state.get('slot') == slot:
            return None
        return submit_refresh(root, slot=slot)
