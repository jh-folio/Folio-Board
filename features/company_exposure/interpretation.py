"""User-approved spec-4 signed raw direction, never Macro State levels."""
import datetime as dt

from features.macro_state.inputs import Inputs
from features.macro_state.rules import shift_months

TABLE = {
    'benefits_from_rise': {'rising': 'supportive', 'falling': 'challenging'},
    'hurt_by_rise': {'rising': 'challenging', 'falling': 'supportive'},
    'two_sided': {'rising': 'mixed', 'falling': 'mixed'},
    'unclear': {},
}


def raw_direction(rows, as_of, key, *, days=None):
    inputs = Inputs(rows, as_of)
    latest = inputs.latest(key)
    before = ((dt.date.fromisoformat(latest) - dt.timedelta(days=days)).isoformat()
              if days and latest else shift_months(latest, -3) if latest else None)
    delta = inputs.change(key, latest, before) if latest else None
    freshness = inputs.freshness(key, latest)
    value = ('unknown' if delta is None or freshness != 'current' else
             'rising' if delta > 0 else 'falling' if delta < 0 else 'flat')
    return {'seriesId': key, 'direction': value, 'delta': str(delta) if delta is not None else None,
            'period': latest, 'comparisonPeriod': before, 'freshness': freshness,
            'sourceRefs': inputs.refs(), 'dataGaps': inputs.gaps(), 'asOf': inputs.as_of}


def interpret(profile, rows, as_of):
    market = profile['market']
    directions = {'interest_rate': raw_direction(rows, as_of, 'DFF' if market == 'US' else 'KR_RATE')}
    if market == 'KR':
        directions['fx'] = raw_direction(rows, as_of, 'KR_USDKRW')
    contexts = [raw_direction(rows, as_of, 'NFCI', days=28)] if market == 'US' else []
    items = []
    for exposure in profile['items']:
        observation = directions.get(exposure['factor'])
        outcome = TABLE[exposure['direction']].get(observation['direction'], 'unknown') if observation else 'unknown'
        items.append({'exposureId': exposure['id'], 'factor': exposure['factor'],
                      'interpretation': outcome, 'observation': observation,
                      'dataGap': None if observation else 'connected_series_unavailable'})
    known = {item['interpretation'] for item in items} - {'unknown'}
    return {'version': 'exposure-interpretation-1', 'promotion': 'shadow',
            'items': items, 'financialContext': contexts,
            'summary': 'mixed' if len(known) > 1 or 'mixed' in known else next(iter(known), 'unknown'),
            'unknownCount': sum(item['interpretation'] == 'unknown' for item in items),
            'notice': '관측 가능한 노출의 조건부 해석이며 기업 전체의 순효과가 아닙니다. 미확인 노출·헤지·시차는 포함하지 못합니다.'}
