"""개요 화면의 한 줄 요약. 전체 이력 대신 머리 숫자·직전 비교·짧은 추이만 보낸다.

머리 숫자는 사람이 먼저 묻는 값이다. 실업률·금리처럼 변화폭(difference)을 계산하는 지표도
"실업률 4.1%"처럼 **수준**을 머리 숫자로 쓰고, 변화는 직전 값과 함께 옆에 적는다.
방향(tone)은 좋고 나쁨이 아니라 늘었다·줄었다만 말한다.
"""
from __future__ import annotations

import datetime as dt

# 수준을 머리 숫자로 읽는 변환. 나머지(전년비·전분기비·전월비)는 변화율이 머리 숫자다.
LEVEL_TRANSFORMS = {'difference', 'level', 'spread'}
# 변화율 중 한 기간 변화(막대로 그린다). 전년비는 흐름이라 선으로 그린다.
PERIOD_CHANGE_TRANSFORMS = {'qoq', 'mom'}
MEASURE = {
    'qoq': '전분기 대비', 'mom': '전월 대비', 'yoy': '전년 대비',
    'difference': '수준', 'level': '수준', 'spread': '금리 차',
}
# 화면에 쓰는 수준 단위와 표기 자릿수. 원천 단위(Percent, 연%)를 그대로 쓰지 않는다.
LEVEL_UNIT = {
    'UNRATE': '%', 'DFF': '%', 'NFCI': '지수', 'STLFSI4': '지수',
    'KR_UNRATE': '%', 'KR_RATE': '%', 'KR_USDKRW': '원', 'KR_SPREAD': '%p',
}
LEVEL_DIGITS = {
    'UNRATE': 1, 'KR_UNRATE': 1, 'DFF': 2, 'KR_RATE': 2, 'NFCI': 2, 'STLFSI4': 2,
    'KR_USDKRW': 0, 'KR_SPREAD': 2,
}
SPARK_MONTHS = 36
SPARK_QUARTERS = 20


def _sample(points, frequency):
    # 일간·주간은 월말 값만 남긴다. 추이선이 톱니가 아니라 흐름을 보이게 한다.
    if frequency not in ('D', 'W'):
        return points
    by_month = {}
    for period, value in points:
        if value is not None:
            by_month[period[:7]] = (period, value)
    return list(by_month.values())


def headline(item: dict) -> dict | None:
    series = item['series']
    transform = series['transform']
    level = transform in LEVEL_TRANSFORMS
    key = 'value' if level else 'displayValue'
    points = [(p['period'], p[key]) for p in item['history']]
    known = [(period, value) for period, value in points if value is not None]
    if not known:
        return None
    unit = LEVEL_UNIT.get(series['id'], series['unit']) if level else '%'
    digits = LEVEL_DIGITS.get(series['id'], 2) if level else 2
    period, value = known[-1]
    previous = known[-2][1] if len(known) > 1 else None
    delta = None
    tone = 'flat'
    if previous is not None:
        # 표시 자릿수에서 같으면 변화 없음이다. 원값은 그대로 둔다.
        delta = round(round(value, digits) - round(previous, digits), digits)
        tone = 'up' if delta > 0 else 'down' if delta < 0 else 'flat'
    sampled = _sample(points, series['frequency'])
    spark = sampled[-(SPARK_QUARTERS if series['frequency'] == 'Q' else SPARK_MONTHS):]
    return {
        'value': value,
        'previous': previous,
        'delta': delta,
        'tone': tone,
        'unit': unit,
        'deltaUnit': '%p' if unit in ('%', '%p') else unit,
        'digits': digits,
        'measure': MEASURE[transform],
        'period': period,
        'shape': 'bars' if transform in PERIOD_CHANGE_TRANSFORMS else 'line',
        'spark': [[p, v] for p, v in spark],
    }


def _observation_end(period: str, frequency: str) -> dt.date:
    day = dt.date.fromisoformat(period)
    if frequency == 'Q':
        month = ((day.month - 1) // 3 + 1) * 3
        return dt.date(day.year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    if frequency == 'M':
        return dt.date(day.year + (day.month == 12), day.month % 12 + 1, 1) - dt.timedelta(days=1)
    return day


def overview(items: list[dict], *, recent_count: int = 3, upcoming_dates: int = 2) -> dict:
    """요약 카드(최근 자료·다음 발표)와 맨 아래 수집 상태 줄에 쓰는 값."""
    monthly = [i for i in items if i['latest'] and i['series']['frequency'] in ('M', 'Q')]
    # 최근 자료는 관측기간이 가장 늦게 끝난 월·분기 지표다. 한국은 공표일을 모르므로
    # 공표 순서가 아니라 관측기간 순서로 고른다.
    monthly.sort(key=lambda i: (_observation_end(i['latest']['period'], i['series']['frequency']), i['latest'].get('availableAt') or ''), reverse=True)
    recent = [{'seriesId': i['series']['id'], 'period': i['latest']['period'], 'frequency': i['series']['frequency']} for i in monthly[:recent_count]]
    by_date: dict[str, list[dict]] = {}
    for item in items:
        release = item.get('nextRelease')
        if release:
            by_date.setdefault(release['date'], []).append({'seriesId': item['series']['id'], 'basis': release['basis']})
    upcoming = [{'date': day, 'series': by_date[day]} for day in sorted(by_date)[:upcoming_dates]]
    states = [s for i in items for s in i['providerStates'] if s]
    last = max((s.get('last_success') or '' for s in states), default='') or None
    return {
        'recent': recent,
        'upcoming': upcoming,
        'collection': {
            'total': len(items),
            'collected': sum('missing' not in i['quality'] for i in items),
            'revised': sum('revised' in i['quality'] for i in items),
            'lastCollectedAt': last,
        },
    }
