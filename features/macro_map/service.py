from __future__ import annotations

import datetime as dt
import calendar
from pathlib import Path
from zoneinfo import ZoneInfo

from features.common.macro_data.registry import AXES,indicators
from features.common.macro_data.schema import day_end
from features.common.macro_data.store import MacroStore
from features.common.macro_data.transforms import compatible,spread,transform
from .calendar import next_releases


def observation_end(period,frequency):
    day=dt.date.fromisoformat(period)
    month=((day.month-1)//3+1)*3 if frequency=='Q' else day.month
    if frequency in {'M','Q'}:return dt.date(day.year,month,calendar.monthrange(day.year,month)[1])
    return day


def map_snapshot(data_root:Path,*,market='US',mode='latest_revised',date=None,series_id=None,period=None,years=5,now=None):
    specs=indicators(market)
    if mode not in {'latest_revised','as_of'}:raise ValueError('invalid_macro_mode')
    if market=='KR' and mode=='as_of':raise ValueError('korean_historical_replay_unsupported')
    clock=now or dt.datetime.now(dt.timezone.utc)
    timezone='America/Chicago' if market=='US' else 'Asia/Seoul'
    today=clock.astimezone(ZoneInfo(timezone)).date()
    selected=dt.date.fromisoformat(date) if date else today
    if selected>today:raise ValueError('future_macro_cutoff')
    if mode=='latest_revised':selected=today
    cutoff=day_end(selected.isoformat(),timezone) if mode=='as_of' else None
    if period:
        dt.date.fromisoformat(period)
        if not series_id:raise ValueError('revision_series_required')
    if series_id:
        specs=[s for s in specs if s['id']==series_id]
        if not specs:raise ValueError('unknown_macro_indicator')
    store=MacroStore(Path(data_root)/'market-memory.sqlite3')
    schedules=next_releases(store.path,selected.isoformat(),cutoff=cutoff)
    items=[]
    for spec in specs:
        ids=spec.get('inputs') or [spec['id']]
        histories=[store.history(s,cutoff=cutoff) for s in ids]
        points=spread(*histories) if spec['id']=='KR_SPREAD' else transform(histories[0],spec)
        latest=points[-1] if points else None
        states=[store.state(s) for s in ids]
        coverages=[store.coverage(s) for s in ids]
        quality=[]
        if latest is None or latest['displayValue'] is None:quality.append('missing')
        if any(s.get('status')=='provider_failed' for s in states):quality.append('provider_failed')
        if any(s.get('status')=='partial' or s.get('cursor',{}).get('phase') in {'fred','fred_metadata','ecos'} for s in states):quality.append('partial')
        if latest:
            if (selected-observation_end(latest['period'],spec['frequency'])).days>spec['max_age_days']:quality.append('stale')
            if latest.get('revised'):quality.append('revised')
            if latest.get('conflict'):quality.append('vintage_conflict')
            if latest.get('calculationGap')=='method_changed':quality.append('method_changed')
        direction='unavailable'
        if len(points)>1 and all(p['displayValue'] is not None for p in points[-2:]) and compatible(points[-1]['metadata'],points[-2]['metadata']):
            delta=round(points[-1]['displayValue'],2)-round(points[-2]['displayValue'],2)
            direction='up' if delta>0 else 'down' if delta<0 else 'same'
        first=max((c['firstAvailableAt'] or '' for c in coverages),default='') or None
        start=dt.date(max(1,selected.year-years),selected.month,min(selected.day,28)).isoformat()
        visible=[p for p in points if p['period']>=start]
        latest_compare=[]
        if mode=='as_of' and series_id:
            latest_compare=transform(store.history(ids[0]),spec)
            latest_compare=[p for p in latest_compare if start<=p['period']<=selected.isoformat()]
        revisions=[]
        if latest and series_id and spec['id']!='KR_SPREAD':
            revisions=store.revisions(ids[0],period or latest['period'],cutoff=cutoff)
        items.append({'series':spec,'latest':latest,'history':visible,'direction':direction,'quality':quality,
                      'coverage':{'firstAvailableAt':first,'sources':coverages},'providerStates':states,
                      'releaseDateStatus':'unknown','nextRelease':schedules.get(spec['id']),'comparisonStatus':'no_comparison_source',
                      'revisionPeriod':period or (latest['period'] if latest else None),
                      'latestRevisedComparison':latest_compare,'revisions':revisions})
    return {'market':market,'mode':mode,'date':selected.isoformat(),'timezone':timezone,'cutoff':cutoff,
            'axes':AXES,'items':items,'agentCalled':False,'replaySupported':market=='US',
            'notes':['한국은 현재 수정치 추이와 수집 이후 확인한 이력을 제공합니다. 과거 당시 값 재현은 지원하지 않습니다.'] if market=='KR' else ['NFCI와 금융스트레스 지수는 공통 입력이 있어 함께 움직일 수 있습니다. 독립된 두 신호로 합산하지 않습니다.'],
            'fetchedAt':clock.isoformat()}
