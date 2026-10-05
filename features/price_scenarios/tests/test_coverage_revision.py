from copy import deepcopy
import json
import re
from pathlib import Path
import pytest
from features.price_scenarios import SPEC_SHA256, SPEC4_REVISION0_SHA256, SPEC4_REVISION1_INITIAL_SHA256, SPEC4_REVISION1_FUND_SOURCE_SHA256
from features.price_scenarios import store as sm, service
from features.price_scenarios.store import PriceStoreError
from features.price_scenarios.changes import restated_items, change_reasons
from features.price_scenarios.decimal_ops import fingerprint
from features.price_scenarios.report import scenario_payload, render_section, REASONS
from .snapshot_fixtures import make


def seed(root, inputs, results, monkeypatch):
    # Seed an authentic old-version row using that version's write identity.
    with monkeypatch.context() as m:
        m.setattr(sm, 'SPEC_SHA256', inputs.get('specSha256'))
        m.setattr(sm, 'METHOD_VERSION', inputs['methodVersion'])
        m.setattr(sm, 'SPEC_VERSION', inputs['specVersion'])
        return service.store_for(root).save_snapshot(inputs, results)['snapshotId']


@pytest.mark.parametrize('sha', [None, SPEC4_REVISION0_SHA256, SPEC4_REVISION1_INITIAL_SHA256, SPEC4_REVISION1_FUND_SOURCE_SHA256, 'f' * 64])
def test_old_and_future_sha_reads_do_not_rewrite_and_only_current_can_write(tmp_path, monkeypatch, sha):
    i, r = make()
    i.update(methodVersion='price-scenario-4', specVersion='price-scenario-spec-4')
    if sha is None:
        i.pop('specSha256')
    else:
        i['specSha256'] = sha
    sid = seed(tmp_path, i, r, monkeypatch)
    store = service.store_for(tmp_path)
    saved = deepcopy(store.get(sid))
    view = service.snapshot_view(tmp_path, sid)
    assert view['results']['referenceFacts'] == {'status': 'not_applicable', 'reason': {'code': 'previous_method'}}
    assert view['results']['scenarios'] == r['scenarios']
    assert store.get(sid) == saved
    with pytest.raises(PriceStoreError):
        store.save_snapshot(i, r)
    if sha == 'f' * 64:
        projection = service.projection_view(tmp_path, sid)
        assert projection['noGrowth']['reason']['code'] == 'previous_method'
    else:
        projection = service.projection_view(tmp_path, sid)
        assert projection['noGrowth'].get('reason', {}).get('code') != 'previous_method'


def test_same_sources_different_revision_fingerprint_method_reason_and_report_exclusion(tmp_path, monkeypatch):
    current, results = make(results_patch={'referenceFacts': {'status': 'available', 'sentinel': 'REFERENCE_FACTS_SECRET_SENTINEL'}})
    old = deepcopy(current)
    old['specSha256'] = SPEC4_REVISION0_SHA256
    old.update(methodVersion='price-scenario-4', specVersion='price-scenario-spec-4')
    assert fingerprint(old) != fingerprint(current)
    sid = seed(tmp_path, old, results, monkeypatch)
    store = service.store_for(tmp_path)
    new = store.save_snapshot(current, results)
    reason = store.history('US:ACME')[0]['changeReasons'][0]
    assert reason['code'] == 'method_changed' and reason['fromSpecSha256'] == SPEC4_REVISION0_SHA256 and reason['toSpecSha256'] == SPEC_SHA256
    assert store.reviews(sid) == []
    view = service.snapshot_view(tmp_path, new['snapshotId'])
    assert 'referenceFacts' not in scenario_payload(view)
    assert 'REFERENCE_FACTS_SECRET_SENTINEL' not in render_section(view)
    report = service.snapshot_for_report(tmp_path, {'market': 'US', 'ticker': 'ACME'}, calculator=lambda *a, **k: new)
    assert 'referenceFacts' not in report['view']['results']
    assert 'referenceFacts' in store.get(new['snapshotId'])['results']


def transitioned(correct_income=False):
    old_i, old_r = make()
    new_i, new_r = deepcopy(old_i), deepcopy(old_r)
    old_i['history']['rows'] = [r for r in old_i['history']['rows'] if not (r['metric'] == 'EPS Diluted' and r['fiscalYear'] == 2020)]
    new_i['history']['rows'] = deepcopy(old_i['history']['rows'])
    ni = next(r for r in new_i['history']['rows'] if r['metric'] == 'Net Income' and r['fiscalYear'] == 2020)
    if correct_income:
        ni['value'] = '500'
    eps = next(r for r in make()[0]['history']['rows'] if r['metric'] == 'EPS Diluted' and r['fiscalYear'] == 2020)
    new_i['history']['rows'].append({**eps, 'derived': 'net_income_over_diluted_shares', 'sourceRows': [deepcopy(ni)]})
    old = {'inputs': old_i, 'results': old_r, 'snapshotId': 'old'}
    new = {'inputs': new_i, 'results': new_r, 'snapshotId': 'new'}
    return old, new


def test_source_addition_is_not_false_restatement_and_real_source_correction_links_reports(tmp_path):
    old, new = transitioned()
    assert restated_items(old, new) == []
    assert change_reasons(old, new) == [{'code': 'input_changed', 'path': 'history'}]
    old, new = transitioned(correct_income=True)
    store = service.store_for(tmp_path)
    first = store.save_snapshot(old['inputs'], old['results'])
    # Every earlier snapshot remains linked, even if the input supplement changes.
    second_i = deepcopy(old['inputs'])
    second_i['price']['value'] = '31'
    second = store.save_snapshot(second_i, old['results'])
    store.save_snapshot(new['inputs'], new['results'])
    for earlier in (first, second):
        marker = service.review_marker(tmp_path, earlier['snapshotId'])
        assert [(r['metric'], r['fiscalYear']) for r in marker['reviewNeeded']] == [('Net Income', 2020)]


def test_source_transition_with_split_does_not_mark_source_values_restated():
    old, new = transitioned()
    for r in new['inputs']['history']['rows']:
        if r['metric'] == 'Shares Diluted':
            r['value'] = str(float(r['value']) * 2)
            r['filed'] = '2025-03-10'
        if r['metric'] in {'EPS Diluted', 'DPS'}:
            r['value'] = str(float(r['value']) / 2)
            r['filed'] = '2025-03-10'
    new['inputs']['asOf'] = '2025-03-11'
    new['results']['shareEvents'] = {'state': 'present', 'events': [{'kind': 'split', 'date': '2025-03-05', 'ratio': '2'}]}
    assert restated_items(old, new) == []


def test_negative_disclosed_precision_and_scope_class_period_are_comparison_guards():
    i, r = make()
    old = {'inputs': i, 'results': r}
    new = deepcopy(old)
    a = next(x for x in old['inputs']['history']['rows'] if x['metric'] == 'EPS Diluted' and x['fiscalYear'] == 2024)
    b = next(x for x in new['inputs']['history']['rows'] if x['metric'] == 'EPS Diluted' and x['fiscalYear'] == 2024)
    a.update(value='1000000', precision=-6)
    b.update(value='1400000', precision=-6)
    assert restated_items(old, new) == []
    b['value'] = '1600000'
    assert restated_items(old, new)
    for field, value in [('classBasis', 'A'), ('scope', 'attributable_class_a'), ('unit', 'EUR/shares')]:
        b[field] = value
        assert restated_items(old, new) == []
        b.pop(field)
    b['period'] = {**b['period'], 'start': '2024-02-01'}
    assert restated_items(old, new) == []


def test_report_and_ui_static_reason_texts_are_identical():
    repo = Path(__file__).resolve().parents[3]
    source = (repo / 'web/src/app/price/format.ts').read_text(encoding='utf-8')
    text = source.split('export const REASON_TEXT')[1].split('};')[0]
    ui = {code: json.loads('"' + value + '"') for code, value in re.findall(r'"([a-z_]+)": "([^"\n]+)"', text)}
    # Personal comparison wording exists only in the UI; every report reason
    # must still have exactly the same text on that screen.
    assert ui == {**REASONS, 'criteria_not_set': '내 기준이 정해지지 않았습니다',
                  'dcf_fallback': '내재가치 계산에 자료 부족으로 채운 값이 있어 판정하지 않았습니다'}


def test_failed_report_and_cli_preserve_provider_sub_reason():
    from features.price_scenarios import report_link
    state = {'status': 'unavailable', 'reason': {'code': 'price_unavailable', 'subCode': 'provider_error'}}
    expected = '가격 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요'
    assert expected in report_link.rule_section(state)
    assert expected in report_link.apply_price_snapshot({}, {}, state)[2]
