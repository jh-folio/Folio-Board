"""Reference facts only. Never an input to scenarios, reports or personal criteria."""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from copy import deepcopy

from .blocks import unavailable
from .coverage_history import row_at
from .decimal_ops import number, rounded
from .ranges import fiscal_years
from .scenarios import base_year, _stale


def reference_facts(history, adjusted, price, support, share_events, cash):
    if support['status'] not in {'supported', 'limited'}:
        return unavailable(support['reasons'][0])
    classification_reason = next((r for r in support.get('reasons', []) if r['code'] == 'share_unit_unknown'), None)
    if classification_reason:
        return unavailable(classification_reason)
    currency = history.get('currency')
    if not currency:
        return unavailable('currency_unknown')
    years = fiscal_years(history)
    latest = years[-1] if years else None
    shares = row_at(history, 'Shares Diluted', latest) if latest else None
    if not shares or number(shares['value']) <= 0:
        return unavailable('share_unit_unknown')
    guard = None
    if share_events['state'] not in {'present', 'none_confirmed'}:
        guard = unavailable('share_event_unknown', share_events.get('reason'))
    elif not price.get('currency'):
        guard = unavailable('currency_unknown')
    elif price['currency'] != currency:
        guard = unavailable('currency_mismatch')
    elif not adjusted:
        guard = unavailable(support.get('reasons', [{'code': 'share_unit_unknown'}])[0])
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        pe = deepcopy(guard)
        ps = deepcopy(guard)
        if not guard:
            base = base_year(adjusted, price['sessionDate'])
            if base['status'] != 'available':
                pe = unavailable(base['reason'])
            else:
                eps = number(base['eps0'])
                pe = {'status': 'available', 'state': 'multiple' if eps > 0 else 'loss' if eps < 0 else 'zero',
                      'value': rounded(number(price['value']) / eps, 4) if eps > 0 else None}
            revenue = row_at(adjusted, 'Revenue', latest)
            count = row_at(adjusted, 'Shares Diluted', latest)
            if not revenue or not count or number(revenue['value']) <= 0 or number(count['value']) <= 0:
                ps = unavailable('non_positive_revenue')
            elif _stale(revenue, price['sessionDate']):
                ps = unavailable('stale_financials')
            else:
                ps = {'status': 'available', 'value': rounded(number(price['value']) * number(count['value']) / number(revenue['value']), 4)}
        cash_years = {r['fiscalYear']: r for r in cash.get('years', [])}
        rows = []
        for year in years:
            revenue, income, prior = (row_at(history, m, y) for m, y in [('Revenue', year), ('Net Income', year), ('Revenue', year - 1)])
            r = number(revenue['value']) if revenue else None
            ni = number(income['value']) if income else None
            fcf = cash_years.get(year, {}).get('fcf')
            item = {'fiscalYear': year, 'revenue': revenue['value'] if revenue else None,
                    'revenueGrowth': rounded(r / number(prior['value']) - 1, 4) if r is not None and prior and number(prior['value']) > 0 else None,
                    'netMargin': rounded(ni / r, 4) if ni is not None and r is not None and r > 0 else None,
                    'fcf': fcf, 'fcfMargin': rounded(number(fcf) / r, 4) if fcf is not None and r is not None and r > 0 else None,
                    'reasons': {}}
            for field in ('revenue', 'revenueGrowth', 'netMargin', 'fcf', 'fcfMargin'):
                if item[field] is not None:
                    continue
                if field in {'fcf', 'fcfMargin'} and fcf is None:
                    reason = cash.get('reason') or {'code': 'missing_value'}
                elif r is not None and r <= 0 and field in {'netMargin', 'fcfMargin'}:
                    reason = {'code': 'non_positive_revenue'}
                elif field == 'revenueGrowth' and prior and number(prior['value']) <= 0:
                    reason = {'code': 'non_positive_revenue'}
                else:
                    reason = {'code': 'missing_value'}
                item['reasons'][field] = deepcopy(reason)
            rows.append(item)
    return {'status': 'available', 'currency': currency, 'peNow': pe, 'psNow': ps, 'years': rows,
            'sbcBasis': cash.get('sbcBasis'), 'notices': deepcopy(cash.get('notices', []))}
