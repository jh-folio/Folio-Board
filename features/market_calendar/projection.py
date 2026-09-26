"""Collapse only proven duplicate readings for display; stored events stay intact."""
from decimal import Decimal, InvalidOperation
import re

_EXACT_CONCEPTS = {
    ('bok', '한국 소비자물가지수 (CPI)'): 'KR_CPI_INDEX',
    ('yfinance_economic', 'KR CPI Index'): 'KR_CPI_INDEX',
    ('yfinance_economic', 'KR Consumer Price Index'): 'KR_CPI_INDEX',
}


def project_events(events):
    output = []
    seen = {}
    for event in events:
        concept = _EXACT_CONCEPTS.get((event.get('provider'), event.get('title')))
        period = str(event.get('observedAt') or '').replace('-', '')
        if re.fullmatch(r'\d{6}01', period):
            period = period[:6]
        unit = event.get('unit')
        try:
            value = Decimal(str(event.get('actualValue') or ''))
        except InvalidOperation:
            value = None
        if not concept or not re.fullmatch(r'\d{6}', period) or not unit or value is None or not value.is_finite():
            output.append(event)
            continue
        # A y/y percentage, a different date, or an unknown period is not a duplicate index.
        key = (concept, period, unit, value, event['startsAt'][:10])
        if key not in seen:
            copy = {**event, 'additionalSources': []}
            seen[key] = copy
            output.append(copy)
        else:
            seen[key]['additionalSources'].append({k: event.get(k) for k in ('id', 'provider', 'source', 'sourceUrl', 'startsAt', 'status')})
    return output
