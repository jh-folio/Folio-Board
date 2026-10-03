"""Spec-4 explanatory blocks. Decimal calculations, no personal verdicts or writes."""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from .blocks import not_applicable, unavailable
from .decimal_ops import number, rounded
from .ranges import fiscal_years
from .returns import IRR_HIGH, IRR_LOW, scenario_irr


def return_parts(results, quartiles, reference):
    """Use the same unrounded assumptions and solver as each canonical scenario."""
    parts = []
    for row in results['scenarios']:
        head = {'label': row['label'], 'horizon': row['horizon']}
        if row['status'] != 'available':
            parts.append({**head, **unavailable(row['reason']['code'], row['reason'].get('subCode'))})
            continue
        if row.get('irrRange'):
            parts.append({**head, **unavailable('irr_'+row['irrRange'])})
            continue
        with localcontext() as context:
            context.prec, context.rounding = 28, ROUND_HALF_EVEN
            pe_now = number(reference) / number(results['base']['eps0'])
            name = {'conservative': 'p25', 'base': 'p50', 'optimistic': 'p75'}[row['label']]
            growth, payout = quartiles['growth'][name], quartiles['payout']['p50']
            flat = growth if payout == 0 else scenario_irr(reference, results['base']['eps0'], growth, pe_now, payout, row['horizon'])
            if not isinstance(flat, Decimal) or not IRR_LOW <= flat <= IRR_HIGH:
                parts.append({**head, **unavailable('flat_irr_out_of_range')})
                continue
            flat_stored, growth_stored = number(rounded(flat, 4)), number(rounded(growth, 4))
            parts.append({**head, 'status': 'available', 'peNow': rounded(pe_now, 2), 'exitPE': row['exitPE'],
                          'growth': rounded(growth_stored, 4), 'dividend': rounded(flat_stored-growth_stored, 4),
                          'rerating': rounded(number(row['irr'])-flat_stored, 4), 'irrFlat': rounded(flat_stored, 4)})
    return parts


def _row(history, metric, year):
    matches = [r for r in history['rows'] if r['metric'] == metric and int(r['fiscalYear']) == year]
    return matches[0] if len(matches) == 1 else None


def no_growth(history, price, ranges, quartiles):
    """Store normalized earnings, never the person's required-return-dependent value."""
    from .scenarios import _stale
    years = fiscal_years(history)
    year = years[-1] if years else None
    revenue, shares, eps = (_row(history, m, year) for m in ('Revenue', 'Shares Diluted', 'EPS Diluted'))
    if revenue and _stale(revenue, price['sessionDate']):
        return unavailable('stale_financials')
    if ranges['netMargin']['status'] != 'available':
        return unavailable(ranges['netMargin']['reason']['code'])
    if not revenue or not shares or number(revenue['value']) <= 0 or number(shares['value']) <= 0:
        return unavailable('non_positive_revenue')
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        rps = number(revenue['value']) / number(shares['value'])
        norm = rps * quartiles['netMargin']['p50']
        if norm <= 0:
            return unavailable('non_positive_normalized_earnings')
        return {'status': 'available', 'rps0': str(rps), 'marginP50': ranges['netMargin']['p50'],
                'marginN': ranges['netMargin']['n'], 'normEps': str(norm), 'recentEps': eps['value'] if eps else None}


def project_no_growth(snapshot, required, criteria):
    from . import method_at_least
    if not method_at_least(snapshot['inputs']['methodVersion'], 4):
        return not_applicable('previous_method')
    block = snapshot['results'].get('noGrowth') or unavailable('non_positive_normalized_earnings')
    if block['status'] != 'available':
        return dict(block)
    if required is None:
        return unavailable('criteria_not_set')
    if required <= 0:
        return unavailable('required_return_not_positive')
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        price = snapshot['inputs']['price']
        value = number(block['normEps']) / required
        coverage = value / number(price['value'])
        return {'status': 'available', 'value': rounded(value, 0 if price['currency'] == 'KRW' else 2),
                'growthShare': rounded(1-coverage, 4), 'priceCoverage': rounded(coverage, 4),
                'requiredReturn': rounded(required, 4), 'criteriaRevisionId': criteria['revisionId'],
                # The sentence must branch on the unrounded value (§3.2), even when growthShare rounds to zero.
                'hasGrowthShare': coverage < 1}


def cash_conversion(history, support, market, session_date):
    """Whole-company raw amounts, independent of per-share support and quote currency."""
    from .scenarios import _stale
    if support['status'] not in {'supported', 'limited'}:
        reason = support['reasons'][0]
        return unavailable(reason['code'], reason.get('subCode'))
    currency = history.get('currency')
    if not currency:
        return unavailable('currency_unknown')
    excluded = {int(r['fiscalYear']) for r in history.get('excludedYears', [])}
    years = [y for y in fiscal_years(history) if y not in excluded and all(_row(history,m,y) for m in ('Net Income','Operating Cash Flow','Capital Expenditure'))][-10:]
    missing_sbc = [y for y in years if not _row(history,'Stock-Based Compensation',y)]
    basis = 'not_applicable_kr' if market == 'KR' else 'not_deducted' if missing_sbc else 'deducted'
    notices = ([{'code': 'sbc_not_deducted_kr'}] if market == 'KR' else
               [{'code': 'sbc_missing_years', 'years': missing_sbc}] if missing_sbc else [])
    if years and _stale(_row(history, 'Net Income', years[-1]), session_date):
        notices.append({'code': 'stale_financials'})
    rows = []
    with localcontext() as context:
        context.prec, context.rounding = 28, ROUND_HALF_EVEN
        for year in years:
            ni, ocf, capex = (_row(history,m,year)['value'] for m in ('Net Income','Operating Cash Flow','Capital Expenditure'))
            capex_out = abs(number(capex))
            sbc = _row(history,'Stock-Based Compensation',year)['value'] if basis == 'deducted' else None
            fcf = number(ocf)-capex_out-(number(sbc) if sbc is not None else 0)
            rows.append({'fiscalYear': year, 'netIncome': ni, 'ocf': ocf, 'capexRaw': capex, 'capexOut': str(capex_out),
                         **({'sbc': sbc} if sbc is not None else {}), 'fcf': str(fcf)})
        ni_sum = sum((number(r['netIncome']) for r in rows), Decimal(0))
        fcf_sum = sum((number(r['fcf']) for r in rows), Decimal(0))
        common = {'years': rows, 'currency': currency, 'sumNetIncome': str(ni_sum), 'sumFcf': str(fcf_sum), 'sbcBasis': basis, 'notices': notices}
        if len(years) < 5:
            return {**common, **unavailable('history_too_short')}
        if ni_sum <= 0:
            return {**common, **unavailable('net_income_sum_not_positive')}
        ratio = fcf_sum/ni_sum
        classification = 'cash_below_earnings' if ratio < Decimal('0.80') else 'cash_above_earnings' if ratio > Decimal('1.50') else 'cash_in_line'
        return {**common, 'status': 'available', 'ratio': rounded(ratio, 4), 'class': classification}
