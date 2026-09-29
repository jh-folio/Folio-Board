"""Shared disclosed exposures and descriptive current holding weights."""
from decimal import Decimal, InvalidOperation

from .store import ExposureStore


def aggregate(root, positions):
    store = ExposureStore(root)
    groups = {}
    gaps = []
    lots = {}
    for position in positions:
        ticker = str(position.get('ticker') or position.get('symbol') or '').upper()
        try:
            weight = Decimal(str(position['weight']))
            if not weight.is_finite() or weight < 0 or weight > 1:
                weight = None
        except (KeyError, TypeError, InvalidOperation):
            weight = None
        if ticker in lots:
            lots[ticker] = lots[ticker] + weight if lots[ticker] is not None and weight is not None else None
        else:
            lots[ticker] = weight
    for ticker, weight in lots.items():
        profile = store.get(ticker)
        if not profile or not profile['items']:
            gaps.append({'ticker': ticker, 'reason': 'disclosed_exposure_unavailable'})
            continue
        for item in profile['items']:
            key = (item['factor'], item['direction'])
            group = groups.setdefault(key, {'factor': key[0], 'direction': key[1], 'positions': {}, 'evidence': []})
            # Several passages for one holding do not multiply its weight.
            group['positions'][ticker] = {'ticker': ticker, 'weight': float(weight) if weight is not None else None}
            evidence = {'ticker': ticker, 'profileId': profile['profileId'], 'exposureId': item['id'],
                        'quote': item['quote'], 'sourceRef': item['sourceRef'],
                        'sourceRefs': item.get('sourceRefs') or [item['sourceRef']], 'magnitudeBasis': item['magnitudeBasis']}
            if item['magnitudeBasis'] == 'company_quantified':
                evidence['magnitudeQuote'] = item['magnitudeQuote']
            group['evidence'].append(evidence)
    result = []
    for key, group in sorted(groups.items()):
        holdings = sorted(group['positions'].values(), key=lambda p: p['ticker'])
        weights = [p['weight'] for p in holdings]
        result.append({**group, 'positions': holdings,
                       'combinedWeight': float(sum(Decimal(str(w)) for w in weights)) if all(w is not None for w in weights) else None,
                       'scenario': '이 요인이 상승한다면, 아래 공시 노출의 조건과 반대 경로를 확인합니다.'})
    return {'promotion': 'shadow', 'groups': result, 'dataGaps': gaps,
            'weightBasis': '기존 포트폴리오 평가금액 기준 현재 보유 비중',
            'notice': '합산 비중은 해당 노출이 확인된 보유의 비중입니다. 실적 손실률이나 전체 위험 비율이 아닙니다. 미조사 노출·헤지·시차를 포함하지 못합니다.'}
