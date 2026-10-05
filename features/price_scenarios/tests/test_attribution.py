from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal as D
import json
import urllib.error

import pytest
from fastapi import FastAPI

from features.price_scenarios import METHOD_VERSION, SPEC_VERSION, SPEC_SHA256, SPEC3_SHA256, SPEC4_SHA256
from features.price_scenarios.attribution import capture, historical_attribution, movement
from features.price_scenarios.decimal_ops import canonical
from features.price_scenarios.service import snapshot_view, movement_view, store_for
from features.price_scenarios.routes import create_price_router
from features.price_scenarios.movement_context import normalize_movement, render_movement_context
from features.company_analysis import sec_filings
from features.price_scenarios.collect import Collector, CollectionError
from features.price_scenarios.report import reason_text
from features.market_memory.tests.live_http import LiveHttpClient
from .snapshot_fixtures import make


def comparison_inputs(*, split=False, reflected=True, dividend=True):
    inputs, results = make()
    inputs['asOf'] = inputs['price']['sessionDate'] = '2025-03-03'
    inputs['history']['rows'] = []
    for y in range(2019, 2025):
        inputs['history']['rows'].append({'fiscalYear': y, 'metric': 'EPS Diluted', 'value': '40' if split and y < 2022 else '10' if y < 2024 else '12',
            'filed': f'{y+1}-02-01', 'period': {'start': f'{y}-01-01', 'end': f'{y}-12-31'}})
    rows = []
    day = date(2019, 1, 1)
    while day <= date(2025, 3, 3):
        if day.weekday() < 5:
            close = D(400) if split and not reflected and day < date(2022, 6, 1) else D(100)
            if day >= date(2024, 12, 31): close = D(150)
            amount = (D(20) if split and not reflected else D(5)) if dividend and day == date(2021, 6, 1) else D(0)
            adj = close * D('.95') if dividend and day < date(2021, 6, 1) else close
            rows.append({'date': day.isoformat(), 'close': str(close), 'adjClose': str(adj), 'dividend': str(amount), 'capitalGain': '0'})
        day += timedelta(days=1)
    inputs['price']['value'] = rows[-1]['close']
    events = [{'eventDate': '2022-06-01', 'kind': 'split', 'ratio': '4', 'providerEvent': True}] if split else []
    raw = {'daily': {'closes': [{'date': r['date'], 'close': r['close']} for r in rows], 'rawBars': rows, 'sourceVersion': 'fixture',
        'dividendColumnPresent': True, 'request': {'start': '2019-01-01', 'endExclusive': '2025-03-04'}},
        'benchmarkDaily': {'sourceState': 'received', 'id': 'S&P 500', 'market': 'US', 'kind': 'price', 'currency': 'USD',
            'providerSymbol': '^GSPC', 'exchangeTimezone': 'America/New_York', 'closes': [{'date': r['date'], 'close': '125' if r['date'] >= '2024-12-31' else '100'} for r in rows]}}
    inputs['returnAttributionInputs'] = capture(raw, inputs, results['support'], {'state': 'present' if split else 'none_confirmed', 'events': events})
    return inputs, results


@pytest.mark.parametrize('split,reflected', [(False, True), (True, True), (True, False)])
def test_hand_calculation_split_is_applied_exactly_once(split, reflected):
    inputs, _ = comparison_inputs(split=split, reflected=reflected)
    before = canonical(inputs)
    out = historical_attribution(inputs)
    assert out['startDate'] == '2019-12-31' and out['endDate'] == '2024-12-31'
    assert D(out['earnings']['growth']) == D('.2')
    assert D(out['earnings']['rerating']) == D('.3')
    assert D(out['dividend']['contribution']) == D('.05')
    assert D(out['total']['value']) == D('.55')
    assert sum(D(out['display'][k]) for k in ('growth', 'rerating', 'dividend')) == D(out['display']['total'])
    assert out['benchmark']['display'] == {'stock': '50.0', 'index': '25.0', 'difference': '25.0'}
    assert canonical(inputs) == before


def test_no_dividend_and_loss_keep_independent_price_total_and_index():
    inputs, _ = comparison_inputs(dividend=False)
    out = historical_attribution(inputs)
    assert out['dividend']['amount'] == '0' and out['total']['status'] == 'available'
    inputs['history']['rows'][-1]['value'] = '-1'
    out = historical_attribution(inputs)
    assert out['earnings']['reason']['code'] == 'non_positive_end_eps'
    assert out['priceReturn'] == '0.5000' and out['total']['status'] == out['benchmark']['status'] == 'available'


def test_missing_eps_is_not_missing_price_and_short_record_is_not_shortened():
    inputs, _ = comparison_inputs()
    inputs['history']['rows'][0]['metric'] = 'Revenue'
    out = historical_attribution(inputs)
    assert out['earnings']['reason']['subCode'] == 'missing_endpoint_eps' and out['priceReturn'] == '0.5000'
    inputs['returnAttributionInputs']['annualPeriods'] = inputs['returnAttributionInputs']['annualPeriods'][1:]
    assert historical_attribution(inputs)['reason']['subCode'] == 'years_too_few'
    assert historical_attribution(inputs, 3)['status'] == 'available'


@pytest.mark.parametrize('failure', ['missing', 'double_split', 'tiny', 'same_day', 'ambiguous', 'ads', 'distribution'])
def test_dividend_failure_never_becomes_zero_or_erases_earnings(failure):
    inputs, _ = comparison_inputs(split=True)
    packet = inputs['returnAttributionInputs']; stock = packet['stockDaily']; event = stock['cashDividends'][0]
    if failure == 'missing': stock['dividendCoverage'] = 'unknown'
    if failure == 'double_split': event['rawAmount'] = '20'
    if failure == 'tiny': event['rawAmount'] = '.01'
    if failure == 'same_day': event['exDate'] = '2022-06-01'
    if failure == 'ambiguous':
        packet['shareEvents']['events'][0]['ratio'] = '1.005'
    if failure == 'ads': event['listedUnit'] = 'per_listed_ads_unverified'
    if failure == 'distribution': stock['distributionEvents'] = [{'date': '2021-07-01', 'kind': 'spinoff'}]
    out = historical_attribution(inputs)
    assert out['dividend']['status'] == out['total']['status'] == 'unavailable'
    assert out['earnings']['status'] == out['benchmark']['status'] == 'available'


def test_listed_ads_dividend_does_not_repeat_eps_ads_ratio():
    inputs, _ = comparison_inputs()
    inputs['classificationInputs']['adsRatio'] = {'value': '2'}
    inputs['returnAttributionInputs']['stockDaily']['cashDividends'][0]['listedUnit'] = 'per_listed_ads'
    out = historical_attribution(inputs)
    assert out['earnings']['startEps'] == '20'
    assert out['dividend']['amount'] == '5'


@pytest.mark.parametrize('check', ['unknown', 'assumed_by_provider_event', 'assumed_not_reflected', 'not_needed'])
def test_uncertain_split_price_is_not_a_comparison(check):
    inputs, _ = comparison_inputs(split=True)
    inputs['returnAttributionInputs']['shareEvents']['events'][0]['priceCheck'] = check
    assert historical_attribution(inputs)['reason']['code'] == 'price_event_unverified'
    assert movement(inputs, '2019-12-31', '2024-12-31')['status'] == 'unavailable'


@pytest.mark.parametrize('reason', ['invalid_period', 'share_event_unknown', 'price_event_unverified', 'endpoint_price_missing', 'invalid_number'])
def test_price_failure_preserves_fixed_reason_codes(monkeypatch, reason):
    inputs, _ = comparison_inputs()
    def fail(*args, **kwargs):
        raise ValueError(reason)
    monkeypatch.setattr('features.price_scenarios.attribution._prices', fail)
    for result in (historical_attribution(inputs), movement(inputs, '2019-12-31', '2024-12-31')):
        assert result['reason']['code'] == reason


def test_price_failure_does_not_expose_exception_text_in_http(monkeypatch, tmp_path):
    inputs, results = comparison_inputs()
    store = store_for(tmp_path)
    saved = store.save_snapshot(inputs, results)
    before = store.path.read_bytes()
    def fail(*args, **kwargs):
        raise ValueError('private provider message: /private/internal/file.sqlite')
    monkeypatch.setattr('features.price_scenarios.attribution._prices', fail)
    app = FastAPI()
    app.include_router(create_price_router(tmp_path))
    with LiveHttpClient(app) as client:
        snapshot = client.get('/api/price-snapshots/' + saved['snapshotId'])
        movement_response = client.get('/api/price-movement', params={
            'instrumentId': 'US:ACME', 'snapshotId': saved['snapshotId'],
            'startDate': '2019-12-31', 'endDate': '2024-12-31'})
        for response in (snapshot, movement_response):
            assert response.status_code == 200
            body = json.dumps(response.json(), ensure_ascii=False)
            assert 'private provider' not in body
            assert '/private/internal' not in body
        assert snapshot.json()['historicalReturnAttribution']['reason']['code'] == 'invalid_number'
        assert movement_response.json()['reason']['code'] == 'invalid_number'
    assert store.path.read_bytes() == before


def test_index_holiday_and_failure_keep_stock_values():
    inputs, _ = comparison_inputs()
    benchmark = inputs['returnAttributionInputs']['benchmarkDaily']
    benchmark['closes'] = [r for r in benchmark['closes'] if r['date'] != '2024-12-31']
    out = historical_attribution(inputs)
    assert out['benchmark']['reason']['code'] == 'benchmark_date_missing'
    assert out['total']['status'] == 'available'
    benchmark['sourceState'] = 'unavailable'
    assert historical_attribution(inputs)['benchmark']['reason']['code'] == 'benchmark_unavailable'


def test_weekend_requested_dates_are_visible_and_snapshot_end_is_not_silently_shortened():
    inputs, _ = comparison_inputs()
    out = movement(inputs, '2020-01-04', '2025-03-02')
    assert out['requestedStartDate'] == '2020-01-04' and out['startDate'] == '2020-01-03'
    assert out['endDate'] == '2025-02-28'
    assert movement(inputs, '2020-01-04', '2025-03-04')['status'] == 'unavailable'


def test_round_trip_replay_and_live_http_reads_do_not_write(tmp_path):
    inputs, results = comparison_inputs()
    store = store_for(tmp_path); saved = store.save_snapshot(inputs, results)
    before = store.path.read_bytes()
    app = FastAPI(); app.include_router(create_price_router(tmp_path))
    with LiveHttpClient(app) as client:
        view = client.get('/api/price-snapshots/'+saved['snapshotId']).json()
        assert view['historicalReturnAttribution'] == historical_attribution(inputs)
        assert client.get('/api/price-snapshots/'+saved['snapshotId']+'?attributionYears=2').status_code == 422
        assert client.get('/api/price-movement', params={'instrumentId':'US:ACME','startDate':'20191231','endDate':'2024-12-31'}).status_code == 422
        facts = client.get('/api/price-movement', params={'instrumentId': 'US:ACME', 'startDate': '2019-12-31', 'endDate': '2024-12-31'}).json()
        assert facts['snapshotId'] == saved['snapshotId']
    assert store.path.read_bytes() == before
    selection = {'instrumentId': 'US:ACME', 'snapshotId': saved['snapshotId'], 'startDate': '2019-12-31', 'endDate': '2024-12-31', 'stockReturn': '999'}
    assert '999' not in render_movement_context(tmp_path, selection)
    assert '50.0' in render_movement_context(tmp_path, selection)
    assert normalize_movement({**selection, 'startDate': '2024-02-31'}) is None
    assert 'comparison_inputs_missing' in render_movement_context(tmp_path, {**selection, 'snapshotId': None})
    assert store.path.read_bytes() == before


@pytest.mark.parametrize('status,code', [(404,'source_not_found'),(410,'source_not_found'),(401,'source_access_denied'),(403,'source_access_denied'),(408,'provider_error'),(429,'provider_error'),(503,'provider_error'),(400,'source_request_failed')])
def test_actual_http_status_survives_legacy_tuple_and_never_uses_stale_text(monkeypatch, tmp_path, status, code):
    cache = tmp_path/'public.json'
    cache.write_text(json.dumps({'text':'cached public filing','fetchedAt':'2020-01-01T00:00:00+00:00'}),encoding='utf-8')
    def fail(*args, **kwargs): raise urllib.error.HTTPError('https://www.sec.gov/public',status,'private exception not exposed',{},None)
    monkeypatch.setattr(sec_filings.urllib.request,'urlopen',fail)
    text, error = sec_filings.fetch_text('https://www.sec.gov/public',cache)
    assert text == 'cached public filing' and isinstance(error,str) and error.code == code and error.http_status == status
    collector = Collector(tmp_path)
    with pytest.raises(CollectionError) as thrown: collector._class_source('https://www.sec.gov/public',cache)
    assert thrown.value.sub_code == code
    msg = reason_text({'code':'financial_history_unavailable','subCode':code,**thrown.value.source_diagnostic})
    assert 'private' not in msg
    if status in {404,410,401,403}: assert '일시적으로' not in msg
    if status in {408,429,503}: assert '일시적으로' in msg


def test_legacy_and_unknown_methods_are_read_only_for_new_attribution():
    inputs, _ = comparison_inputs()
    inputs['specSha256'] = 'f'*64
    assert historical_attribution(inputs)['status'] == 'not_applicable'
    inputs.update(methodVersion='price-scenario-4',specVersion='price-scenario-spec-4',specSha256=SPEC4_SHA256)
    assert historical_attribution(inputs)['status'] == 'not_applicable'


def _recapture(inputs):
    packet = inputs['returnAttributionInputs']; stock = packet['stockDaily']
    raw = {'daily': {'closes': stock['closes'], 'rawBars': stock['rawBars'], 'dividendColumnPresent': True,
                     'request': stock['request'], 'sourceVersion': stock['sourceVersion']}, 'benchmarkDaily': packet['benchmarkDaily']}
    inputs['returnAttributionInputs'] = capture(raw, inputs, packet['support'], packet['shareEvents'])


def test_missing_close_on_cash_event_cannot_turn_dividend_into_zero():
    inputs, _ = comparison_inputs()
    stock = inputs['returnAttributionInputs']['stockDaily']
    stock['closes'] = [r for r in stock['closes'] if r['date'] != '2021-06-01']
    next(r for r in stock['rawBars'] if r['date'] == '2021-06-01')['close'] = None
    _recapture(inputs)
    cash = inputs['returnAttributionInputs']['stockDaily']['cashDividends']
    assert cash[0]['rawAmount'] == '5' and cash[0]['unitValidation']['status'] == 'unavailable'
    out = historical_attribution(inputs)
    assert out['dividend']['reason']['code'] == 'dividend_unit_unverified'
    assert out['total']['status'] == 'unavailable' and out['priceReturn'] == '0.5000'


def test_dividend_coverage_is_specific_to_selected_period_and_unit_proof_is_saved():
    inputs, _ = comparison_inputs()
    cash = inputs['returnAttributionInputs']['stockDaily']['cashDividends'][0]
    assert cash['basisEvidence'] == 'provider_price_unit_consistent' and cash['normalizationFactor'] == '1'
    next(r for r in inputs['returnAttributionInputs']['stockDaily']['rawBars'] if r['date'] == '2019-01-01')['dividend'] = None
    _recapture(inputs)
    assert historical_attribution(inputs, 1)['total']['status'] == 'available'
    next(r for r in inputs['returnAttributionInputs']['stockDaily']['rawBars'] if r['date'] == '2024-06-03')['dividend'] = None
    _recapture(inputs)
    assert historical_attribution(inputs, 1)['dividend']['reason']['code'] == 'dividend_history_unavailable'


def test_reverse_split_and_cash_amount_are_normalized_once():
    inputs, _ = comparison_inputs(split=True, reflected=False)
    packet = inputs['returnAttributionInputs']; stock = packet['stockDaily']
    packet['shareEvents']['events'][0]['ratio'] = '.1'
    for row in stock['rawBars']:
        if row['date'] < '2022-06-01':
            row['close'] = '10'; row['adjClose'] = '9.5' if row['date'] < '2021-06-01' else '10'
        if row['date'] == '2021-06-01': row['dividend'] = '.5'
    stock['closes'] = [{'date': r['date'], 'close': r['close']} for r in stock['rawBars']]
    for row in inputs['history']['rows']:
        if row['fiscalYear'] < 2022: row['value'] = '1'
    _recapture(inputs)
    out = historical_attribution(inputs)
    assert D(out['startClose']) == D(100) and D(out['earnings']['growth']) == D('.2')
    assert D(out['dividend']['amount']) == D(5) and D(out['total']['value']) == D('.55')


@pytest.mark.parametrize('price,eps,total,growth,rerating', [('120.05','12','20.0','20.0','0.0'),
    ('120.15','12','20.2','20.0','0.2'), ('79.95','8','-20.0','-20.0','0.0'),
    ('79.85','8','-20.2','-20.0','-0.2'), ('1500','20','1400.0','100.0','1300.0')])
def test_half_even_signed_and_large_returns_have_exact_visible_sum(price,eps,total,growth,rerating):
    inputs, _ = comparison_inputs(dividend=False)
    packet = inputs['returnAttributionInputs']
    for rows in (packet['stockDaily']['closes'], packet['stockDaily']['rawBars']):
        for row in rows:
            if row['date'] >= '2024-12-31': row['close'] = price
    inputs['price']['value'] = price; inputs['history']['rows'][-1]['value'] = eps
    out = historical_attribution(inputs)
    assert out['display']['total'] == total and out['display']['growth'] == growth and out['display']['rerating'] == rerating
    assert sum(D(out['display'][k]) for k in ('growth','rerating','dividend')) == D(total)
    assert sum(D(out['calculation']['response'][k]) for k in ('growth','rerating','dividend')) == D(out['total']['value'])


def test_chat_prompt_recomputes_fixed_selection_and_does_not_touch_report_or_storage(monkeypatch,tmp_path):
    from features.agent_mode import chat
    from features.agent_mode.companion import normalize_agent_context
    inputs, results = comparison_inputs(); saved = store_for(tmp_path).save_snapshot(inputs, results)
    before = store_for(tmp_path).path.read_bytes()
    monkeypatch.setattr(chat, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(chat, 'project_market_state', lambda *_: {})
    monkeypatch.setattr(chat, 'render_market_state_projection', lambda *_: '')
    context = normalize_agent_context({'surface': 'watchlist', 'chartMovement': {'instrumentId':'US:ACME','snapshotId':saved['snapshotId'],
                                      'startDate':'2019-12-31','endDate':'2024-12-31','stockReturn':'999'}})
    prompt = chat.build_chat_prompt('계산된 사실을 설명해 주세요',context,{})
    assert '999' not in prompt and '50.0' in prompt and 'hypothesis' in prompt and 'reuseAsEvidence=false' in prompt
    assert store_for(tmp_path).get(saved['snapshotId'])['inputFingerprint'] in prompt
    assert store_for(tmp_path).path.read_bytes() == before


def test_internal_missing_year_is_not_a_successful_zero_dividend_record():
    inputs, _ = comparison_inputs(dividend=False)
    stock = inputs['returnAttributionInputs']['stockDaily']
    for key in ('closes','rawBars'): stock[key] = [r for r in stock[key] if not r['date'].startswith('2022-')]
    _recapture(inputs)
    out = historical_attribution(inputs)
    assert out['dividend']['reason']['subCode'] == 'internal_coverage_gap' and out['total']['status'] == 'unavailable'
    assert out['priceReturn'] == '0.5000' and out['earnings']['status'] == out['benchmark']['status'] == 'available'
    assert historical_attribution(inputs, 1)['total']['status'] == 'available'


def test_report_boundary_omits_historical_section_and_preserves_http_diagnostic(tmp_path):
    from features.price_scenarios.service import snapshot_for_report, CalculationNotStored
    inputs, results = comparison_inputs(); saved = store_for(tmp_path).save_snapshot(inputs, results)
    report = snapshot_for_report(tmp_path, {'market':'US','ticker':'ACME'}, calculator=lambda *_args,**_kwargs: saved)
    assert report['status'] == 'saved' and 'historicalReturnAttribution' not in report['view']
    assert canonical(report['view']['results']['scenarios']) == canonical(results['scenarios'])
    def missing(*_args,**_kwargs):
        raise CalculationNotStored('financial_history_unavailable','source_not_found',{'httpStatus':404,'sourceFailureVerified':True})
    failure = snapshot_for_report(tmp_path, {'market':'US','ticker':'ACME'}, calculator=missing)
    assert failure['reason']['httpStatus'] == 404 and 'HTTP 404' in reason_text(failure['reason'])
