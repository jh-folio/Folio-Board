"""Operational integration of the frozen engine; no historical evaluation runs."""
import calendar
import datetime as dt
import json
from pathlib import Path
from decimal import Decimal
from zoneinfo import ZoneInfo

from features.common.macro_data.registry import SERIES
from features.common.macro_data.schema import day_end
from features.common.macro_data.store import MacroStore
from features.macro_map.calendar import next_releases
from .engine import calculate
from .inputs import utc
from .replay import Replay
from .store import StateStore, LEVELS

METHOD = json.loads(Path(__file__).with_name('method_version.json').read_text(encoding='utf-8'))


def refresh_snapshots(root, *, now=None, job_id=None, saved_count=0):
    clock = now or dt.datetime.now(dt.timezone.utc)
    cutoff = utc(clock.isoformat())
    path = Path(root) / 'market-memory.sqlite3'
    with MacroStore(path).read() as conn:
        if conn is None:
            raise ValueError('macro_ledger_unavailable')
    replay = Replay(path, [s.id for s in SERIES])
    store = StateStore(path)
    snapshots = []
    for market in ('US', 'KR'):
        zone = 'America/Chicago' if market == 'US' else 'Asia/Seoul'
        local_day = clock.astimezone(ZoneInfo(zone)).date()
        rows = replay.select(cutoff, observation_end=local_day.isoformat())
        for axis in LEVELS:
            # Defaults are development starters. Production always uses the
            # independently reviewed and evaluated frozen parameter values.
            result = calculate(market, axis, rows, cutoff, facts=replay.facts_at(cutoff),
                               theta_c=Decimal(METHOD['parameters']['thetaC']), theta_r=Decimal(METHOD['parameters']['thetaR']))
            snapshots.append(result)
    def write():
        return [store.save(result, reason='explicit_macro_refresh') for result in snapshots]
    if not job_id:
        return write()
    from features.common.macro_job_commit import commit
    from features.common.macro_data.schema import digest
    expected = []
    for result in snapshots:
        body = dict(result)
        body['asOf'] = utc(body['asOf'])
        body.pop('promotion', None); body.pop('cycleSignalPromotion', None)
        identity = tuple(body[key] for key in ('market', 'axis', 'asOf', 'methodVersion', 'inputFingerprint'))
        expected.append({'type': 'macro_snapshot', 'id': 'macro-' + digest(identity), 'hash': digest(body)})
    return commit(root, job_id, expected, write, saved_count=saved_count)


def previous_month_snapshot(store, market, axis, date):
    """Only actually stored local month-end snapshots before the selected day."""
    zone = ZoneInfo('America/Chicago' if market == 'US' else 'Asia/Seoul')
    with store.read() as conn:
        if conn is None:
            return None
        for row in conn.execute('SELECT * FROM macro_state_snapshots WHERE market=? AND axis=? AND method=? ORDER BY as_of DESC,seq DESC',
                                (market, axis, METHOD['methodVersion'])):
            local = dt.datetime.fromisoformat(row['as_of'].replace('Z', '+00:00')).astimezone(zone)
            if (local.date() < date and local.day == calendar.monthrange(local.year, local.month)[1]
                    and utc(row['as_of']) == utc(day_end(local.date().isoformat(), str(zone)))):
                return store._project(conn, row)
    return None


def summary(root, *, market='US', date=None, now=None):
    if market not in {'US', 'KR'}:
        raise ValueError('invalid_macro_market')
    clock = now or dt.datetime.now(dt.timezone.utc)
    timezone = 'America/Chicago' if market == 'US' else 'Asia/Seoul'
    today = clock.astimezone(ZoneInfo(timezone)).date()
    selected = dt.date.fromisoformat(date) if date else today
    if selected > today:
        raise ValueError('future_macro_date')
    store = StateStore(Path(root) / 'market-memory.sqlite3')
    cutoff = day_end(selected.isoformat(), timezone)
    cards = []
    for axis in LEVELS:
        # latest() has an exclusive upper bound; include the selected day's
        # stored end-of-day snapshot without changing the frozen store API.
        before = (dt.datetime.fromisoformat(cutoff.replace('Z', '+00:00')) + dt.timedelta(microseconds=1)).isoformat()
        current = store.latest(market, axis, before=before)
        previous = previous_month_snapshot(store, market, axis, selected)
        cards.append({'axis': axis, 'snapshot': current, 'previous': previous,
                      'comparisonStatus': 'available' if current and previous else 'stored_comparison_unavailable'})
    return {'market': market, 'date': selected.isoformat(), 'cards': cards,
            'methodVersion': METHOD['methodVersion'], 'specVersion': METHOD['specVersion'],
            'nextCheckpoints': {key: value for key, value in next_releases(store.path, selected.isoformat(), cutoff=cutoff).items()
                                if key.startswith('KR_') == (market == 'KR')},
            'notice': '이미 나타난 신호의 확인이지 예측이 아닙니다. 과거 전환점 표본이 적습니다.',
            'inflationLimitation': '검증 구간 B1 대비 이탈 차이 4.76%p로 한도 5%p에 가깝습니다(1개월 여유 미만). 공식 물가 목표 달성이나 투자 지침을 뜻하지 않습니다.'}


def lineage(root):
    store = StateStore(Path(root) / 'market-memory.sqlite3')
    result = []
    for market in ('US', 'KR'):
        for axis in LEVELS:
            snapshot = store.latest(market, axis)
            if snapshot:
                result.append({key: snapshot[key] for key in ('snapshotId', 'inputFingerprint', 'market', 'axis', 'asOf', 'methodVersion')})
    return result


def history(root):
    store = StateStore(Path(root) / 'market-memory.sqlite3')
    with store.read() as conn:
        if conn is None:
            return {'snapshots': [], 'decisions': []}
        snapshots = [dict(r) for r in conn.execute('SELECT id,market,axis,as_of,method,created_at FROM macro_state_snapshots ORDER BY seq DESC LIMIT 80')]
        decisions = [dict(r) for r in conn.execute('SELECT seq,market,axis,method,field,promotion,created_at FROM macro_state_decisions ORDER BY seq DESC LIMIT 40')]
    return {'snapshots': snapshots, 'decisions': decisions}
