from copy import deepcopy
import pytest
from features.price_scenarios.reference_facts import reference_facts
from features.price_scenarios.crosschecks import cash_conversion
from .test_scenario_results import steady

SUPPORT = {'status': 'supported', 'reasons': []}
PRICE = {'value': '20', 'currency': 'USD', 'sessionDate': '2026-10-02'}
EVENTS = {'state': 'none_confirmed'}


def data():
    h, _ = steady(range(2021, 2026))
    h['currency'] = 'USD'
    for row in h['rows']:
        row['value'] = {'Revenue': '1000.123456789', 'Net Income': '-100', 'Shares Diluted': '100', 'EPS Diluted': '-1'}.get(row['metric'], row['value'])
    return h


def facts(h=None, adjusted=True, support=SUPPORT, price=PRICE, events=EVENTS, cash=None):
    h = h or data()
    cash = cash or {'status': 'unavailable', 'reason': {'code': 'net_income_sum_not_positive'}, 'sbcBasis': 'deducted', 'notices': [],
                   'years': [{'fiscalYear': y, 'fcf': '0' if y == 2025 else '123.123456789'} for y in range(2021, 2026)]}
    return reference_facts(h, h if adjusted else None, price, support, events, cash)


@pytest.mark.parametrize('eps,state,value', [('-1', 'loss', None), ('0', 'zero', None), ('2', 'multiple', '10.0000')])
def test_per_zero_loss_positive_and_precise_company_amounts(eps, state, value):
    h = data()
    for row in h['rows']:
        if row['metric'] == 'EPS Diluted' and row['fiscalYear'] == 2025:
            row['value'] = eps
    out = facts(h)
    assert out['peNow'] == {'status': 'available', 'state': state, 'value': value}
    assert out['psNow']['value'] == '1.9998'
    assert out['years'][-1]['revenue'] == '1000.123456789'
    assert out['years'][-1]['fcf'] == '0' and out['years'][-1]['fcfMargin'] == '0.0000'
    assert out['years'][0]['revenueGrowth'] is None and out['years'][0]['reasons']['revenueGrowth']['code'] == 'missing_value'


def test_gap_does_not_compare_last_observed_year_and_recent_missing_never_falls_back():
    h = data()
    h['rows'] = [r for r in h['rows'] if not (r['metric'] == 'Revenue' and r['fiscalYear'] == 2024)]
    out = facts(h)
    assert out['years'][-1]['revenueGrowth'] is None
    h['rows'] = [r for r in h['rows'] if not (r['metric'] == 'EPS Diluted' and r['fiscalYear'] == 2025)]
    assert facts(h)['peNow']['reason']['code'] == 'base_eps_missing'
    cash = {'status': 'unavailable', 'reason': {'code': 'history_too_short'}, 'years': [{'fiscalYear': 2024, 'fcf': '20'}]}
    latest = facts(h, cash=cash)['years'][-1]
    assert latest['fcf'] is None and latest['fcfMargin'] is None and latest['reasons']['fcf']['code'] == 'history_too_short'


def test_zero_revenue_null_ratios_and_missing_cash_keep_revenue_and_income_records():
    h = data()
    for row in h['rows']:
        if row['metric'] == 'Revenue' and row['fiscalYear'] == 2025:
            row['value'] = '0'
    out = facts(h)
    assert out['psNow']['reason']['code'] == 'non_positive_revenue'
    latest = out['years'][-1]
    assert latest['revenue'] == '0' and latest['revenueGrowth'] == '-1.0000'
    assert latest['netMargin'] is None and latest['reasons']['netMargin']['code'] == 'non_positive_revenue'


@pytest.mark.parametrize('kwargs,reason', [({'events': {'state': 'unknown', 'reason': 'event_source_unavailable'}}, 'share_event_unknown'),
    ({'price': {**PRICE, 'currency': 'KRW'}}, 'currency_mismatch'),
    ({'price': {**PRICE, 'currency': None}}, 'currency_unknown'),
    ({'adjusted': False, 'support': {'status': 'limited', 'reasons': [{'code': 'currency_mismatch'}]}}, 'currency_mismatch')])
def test_per_share_guards_do_not_block_whole_company_history(kwargs, reason):
    out = facts(**kwargs)
    assert out['status'] == 'available' and out['peNow']['reason']['code'] == out['psNow']['reason']['code'] == reason
    assert out['years'][-1]['netMargin'] == '-0.1000'


def test_unsupported_units_currency_and_stale():
    assert facts(support={'status': 'unsupported', 'reasons': [{'code': 'fund_not_supported'}]})['reason']['code'] == 'fund_not_supported'
    assert facts(support={'status': 'limited', 'reasons': [{'code': 'share_unit_unknown'}]})['reason']['code'] == 'share_unit_unknown'
    h = data()
    h['currency'] = None
    assert facts(h)['reason']['code'] == 'currency_unknown'
    assert facts(price={**PRICE, 'sessionDate': '2028-10-02'})['peNow']['reason']['code'] == 'stale_financials'


def test_cash_years_amounts_and_sbc_basis_are_exactly_c():
    h = data()
    for year in range(2021, 2026):
        exemplar = next(r for r in h['rows'] if r['fiscalYear'] == year)
        for metric, value in [('Operating Cash Flow', '300.123456789'), ('Capital Expenditure', '-100'), ('Stock-Based Compensation', '50')]:
            h['rows'].append({**deepcopy(exemplar), 'metric': metric, 'value': value})
    c = cash_conversion(h, SUPPORT, 'US', PRICE['sessionDate'])
    out = facts(h, cash=c)
    assert out['sbcBasis'] == c['sbcBasis'] == 'deducted' and out['notices'] == c['notices']
    assert [(r['fiscalYear'], r['fcf']) for r in out['years']] == [(r['fiscalYear'], r['fcf']) for r in c['years']]
    h['rows'] = [r for r in h['rows'] if not (r['metric'] == 'Stock-Based Compensation' and r['fiscalYear'] == 2023)]
    c = cash_conversion(h, SUPPORT, 'US', PRICE['sessionDate'])
    assert facts(h, cash=c)['sbcBasis'] == 'not_deducted'
