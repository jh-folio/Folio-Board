"""Pure fixed-decimal rules; None means unknown, never zero or yesterday's verdict."""
from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal as D


def shift_months(day: str, months: int) -> str:
    date = dt.date.fromisoformat(day)
    index = date.year * 12 + date.month - 1 + months
    year, month = index // 12, index % 12 + 1
    return dt.date(year, month, min(date.day, calendar.monthrange(year, month)[1])).isoformat()


def direction(delta, threshold, *, inclusive=False):
    if delta is None:
        return 'unknown'
    if delta > threshold or (inclusive and delta == threshold):
        return 'rising'
    if delta < -threshold or (inclusive and delta == -threshold):
        return 'falling'
    return 'flat'


def inflation_level(market, observation_month, value):
    if value is None or observation_month is None:
        return 'unknown'
    year = int(observation_month[:4])
    if market == 'US':
        if year < 2012:
            return 'unknown'
        lower, upper = D('1.5'), D('2.5')
        high = D(4)
    elif market == 'KR':
        if year < 2007:
            return 'unknown'
        if year <= 2015:
            lower, upper = (D(2), D(4)) if 2010 <= year <= 2012 else (D('2.5'), D('3.5'))
            high = upper + 2
        else:
            lower, upper, high = D('1.5'), D('2.5'), D(4)
    else:
        raise ValueError('unsupported_macro_market')
    return ('below_reference' if value < lower else 'near_reference' if value <= upper
            else 'above_reference' if value <= high else 'high')


def financial_level(market, value):
    if value is None:
        return 'unknown'
    threshold = D('.25') if market == 'US' else D(1)
    return 'tight' if value > threshold else 'loose' if value < -threshold else 'neutral'


def financial_direction(rate_delta, nfci_delta):
    rate = direction(rate_delta, D('.25'), inclusive=True)
    nfci = direction(nfci_delta, D('.10'))
    if 'unknown' in {rate, nfci}:
        return 'unknown'
    return 'mixed' if {rate, nfci} == {'rising', 'falling'} else rate


def stress_level(value):
    return 'unknown' if value is None else 'high' if value > 1 else 'elevated' if value > 0 else 'normal'


def contraction(gdp, ip, sahm):
    if (gdp is not None and ip is not None and gdp < 0 and ip < 0) or sahm is True:
        return True
    if gdp is None or ip is None or sahm is None:
        return None
    return False


def growth_level(gdp, ip, sahm, gdp_trend, ip_trend, *, gdp_margin=D('.25'), ip_margin=D(1)):
    contracted = contraction(gdp, ip, sahm)
    if contracted is True:
        return 'contraction'
    if contracted is None or gdp_trend is None or ip_trend is None:
        return 'unknown'
    if gdp >= gdp_trend + gdp_margin and ip >= ip_trend + ip_margin:
        return 'strong'
    if gdp < gdp_trend - gdp_margin and ip < ip_trend - ip_margin:
        return 'weak'
    return 'moderate'


def growth_direction(deltas, *, unemployment_sum=False):
    # Caller supplies the unemployment change with its sign already inverted.
    signals = [direction(v,t) for v,t in zip(deltas, (D('.25'),D('.5'),D('.3') if unemployment_sum else D('.1')))]
    present = [v for v in signals if v != 'unknown']
    if len(present) < 2:
        return 'unknown'
    return next((v for v in ('rising','falling','flat') if present.count(v) >= 2), 'mixed')


def confidence(level, direction_value, stale_count, required_count, missing=False, conflict=False, auxiliary_conflict=False):
    if level == 'unknown' or direction_value == 'unknown' or missing or conflict or (required_count and stale_count * 2 >= required_count):
        return 'low'
    return 'medium' if stale_count or auxiliary_conflict else 'high'


def kleene_and(*values):
    return False if any(v is False for v in values) else True if all(v is True for v in values) else None


def kleene_exists(values):
    return True if any(v is True for v in values) else False if all(v is False for v in values) else None


def cycle_choice(conditions, stale_conditions=()):
    names = {'Q':'recovery_confirmed','R':'recovery_signal','K':'contraction_confirmed','W':'contraction_warning'}
    relevant = []
    for key, name in names.items():
        relevant.append(key)
        if conditions[key] is True:
            break
    else:
        name = 'none' if all(v is False for v in conditions.values()) else 'unknown'
    quality = ('low' if any(conditions[k] is None for k in relevant)
               else 'medium' if set(relevant) & set(stale_conditions) else 'high')
    return name, quality, relevant


def corroboration(signal, current, previous_months, *, stale=False):
    if stale or current is None or signal in {'none','unknown'}:
        return 'not_available'
    if signal in {'contraction_warning','contraction_confirmed'}:
        return 'agrees' if current <= D('-.70') else 'disagrees'
    if any(v is None for v in previous_months):
        return 'not_available'
    prerequisite = any(v <= D('-.70') for v in previous_months)
    return ('strongly_agrees' if prerequisite and current > D('.20') else
            'agrees' if prerequisite and current > D('-.70') else 'disagrees')
