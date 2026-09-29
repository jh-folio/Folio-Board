import copy
import sqlite3
import datetime as dt

import pytest
from features.common.macro_data.schema import canonical
from features.company_exposure.extraction import extract, validate_item
from features.company_exposure.interpretation import interpret, raw_direction, TABLE
from features.company_exposure.store import ExposureStore
from features.company_exposure.service import read
from features.macro_state.tests.test_inputs import row


def materials(text='Higher interest rates would increase our borrowing costs.'):
    return {'rankedFiling': {'ok': True, 'form': '10-K',
        'metadata': {'url': 'https://www.sec.gov/Archives/example', 'filingDate': '2026-01-01'},
        'paragraphs': [{'item': '7A', 'text': text}]}}


def test_canonical_independent_of_reason_and_exact_quote():
    company = {'ticker': 'TEST', 'market': 'US'}
    results = [extract(company, materials(), personal_reason=r) for r in ('', '금리에 민감', '사용자 가설 '*500)]
    assert len({canonical(p) for p in results}) == 1
    item = results[0]['items'][0]
    assert item['direction'] == 'hurt_by_rise'
    assert item['quote'] == materials()['rankedFiling']['paragraphs'][0]['text']
    invalid = dict(item, magnitudeBasis='company_quantified', magnitudeQuote='12% profit decline')
    with pytest.raises(ValueError, match='quantification'):
        validate_item(invalid, item['quote'])
    with pytest.raises(ValueError, match='quote_not_in_source'):
        validate_item(dict(item, quote='Invented sensitivity 40%'), item['quote'])


@pytest.mark.parametrize('quote', ['Higher interest rates would not increase our borrowing costs.',
    'Higher interest rates and exchange rates may increase our borrowing costs.',
    'Our interest rates are hedged; the net impact is uncertain.'])
def test_ambiguous_or_negated_effect_not_inferred(quote):
    assert all(item['direction'] == 'unclear' for item in extract({'ticker': 'T'}, materials(quote))['items'])


def test_wrong_sections_absent_source_and_news_not_used():
    m = materials(); m['rankedFiling']['paragraphs'][0]['item'] = '1'
    assert extract({'ticker': 'T'}, m)['items'] == []
    m = materials(); m['rankedFiling']['metadata'] = {}
    assert extract({'ticker': 'T'}, m)['items'] == []
    assert extract({'ticker': 'T'}, {'supportDocs': [materials()]})['items'] == []


def test_signed_change_exact_missing_day_stale_and_separate_nfci():
    as_of = '2026-03-31T23:00:00Z'
    rows = [row('DFF', '2026-03-30', '4'), row('DFF', '2025-12-30', '3'),
            row('NFCI', '2026-03-27', '-1'), row('NFCI', '2026-02-27', '0')]
    for r in rows: r['availableAt'] = '2026-03-31T10:00:00Z'
    profile = extract({'ticker': 'T'}, materials())
    result = interpret(profile, rows, as_of)
    assert result['summary'] == 'challenging'
    assert result['financialContext'][0]['direction'] == 'falling'
    assert interpret(profile, rows, '2026-05-31T23:00:00Z')['summary'] == 'unknown'
    assert raw_direction(rows[:1], as_of, 'DFF')['direction'] == 'unknown'
    assert raw_direction(rows, as_of, 'DFF')['comparisonPeriod'] == '2025-12-30'
    assert TABLE['two_sided'].get('flat', 'unknown') == 'unknown'
    assert TABLE['two_sided']['falling'] == 'mixed'
    assert TABLE['benefits_from_rise']['falling'] == 'challenging'


def test_storage_read_only_restart_and_history(tmp_path):
    assert read(tmp_path, 'T')['status'] == 'not_collected'
    assert not (tmp_path/'market-memory.sqlite3').exists()
    store = ExposureStore(tmp_path)
    first = extract({'ticker': 'T'}, materials())
    store.save(first, materials=materials()); store.save(first, materials=materials())
    second = extract({'ticker': 'T'}, materials('Higher interest rates would increase our net interest income.'))
    store.save(second, materials=materials("Higher interest rates would increase our net interest income."))
    assert ExposureStore(tmp_path).get('T') == second
    assert store.get('T', first['profileId']) == first
    with sqlite3.connect(store.path) as c:
        assert c.execute('select count(*) from company_macro_exposures').fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError):
            c.execute('delete from company_macro_exposures')


def test_missing_or_unsupported_does_not_fabricate_effect():
    profile = extract({'ticker': 'T'}, materials('Raw material prices and tariffs could adversely affect our business.'))
    result = interpret(profile, [], '2026-03-31T23:00:00Z')
    assert result['summary'] == 'unknown'
    assert all(item['dataGap'] == 'connected_series_unavailable' for item in result['items'])


def test_counter_channels_controls_abbreviations_and_save_tampering(tmp_path):
    from features.company_exposure.extraction import direction, sentences
    quote = 'Higher interest rates would increase our borrowing costs and increase our net interest income.'
    assert direction(quote, 'interest_rate') == 'two_sided'
    regulation = 'Our operations are subject to foreign exchange controls and cash repatriation restrictions and export controls.'
    assert {r['factor'] for r in extract({'ticker': 'T'}, materials(regulation))['items']} == {'policy_specific'}
    assert list(sentences('Non-U.S. dollar FX risk affects our assets. Our liabilities also change.')) == ['Non-U.S. dollar FX risk affects our assets.', 'Our liabilities also change.']
    profile = extract({'ticker': 'T'}, materials())
    profile['items'][0]['quote'] = 'An invented 999% sensitivity.'
    with pytest.raises(ValueError, match='not_grounded'):
        ExposureStore(tmp_path).save(profile, materials=materials())
    assert not (tmp_path/'market-memory.sqlite3').exists()


def test_utility_tariff_is_not_trade_policy():
    profile = extract({'ticker': 'T'}, materials('Our published tariffs govern the cost of electricity services.'))
    assert profile['items'] == []


def test_tax_regulation_mention_is_not_fx_exposure():
    quote = "The Company's effective tax rate increased due to foreign currency loss regulations."
    assert extract({'ticker': 'T'}, materials(quote))['items'] == []
    quote = "The Company's effective tax rate reflects the impact of foreign currency loss regulations and foreign currency revaluations related to a tax decision."
    assert extract({'ticker': 'T'}, materials(quote))['items'] == []
    quote = "Our exposure to fluctuations in foreign currency exchange rates affects our revenue."
    assert {i['factor'] for i in extract({'ticker': 'T'}, materials(quote))['items']} == {'fx'}


def test_issuer_names_are_not_special_cased():
    for issuer in ['NEE', 'FPL', 'Duke Energy', 'Unseen Issuer']:
        quote = f'Higher interest rates would increase {issuer} borrowing costs.'
        assert extract({'ticker': 'T'}, materials(quote))['items'] == []
    quote = "Higher interest rates would increase the Company's borrowing costs."
    assert extract({'ticker': 'T'}, materials(quote))['items'][0]['direction'] == 'hurt_by_rise'


def test_identical_sentence_merges_sources_and_preserves_roundtrip(tmp_path):
    m = materials()
    m['rankedQuarterlyFiling'] = copy.deepcopy(m['rankedFiling'])
    m['rankedQuarterlyFiling']['form'] = '10-Q'
    m['rankedQuarterlyFiling']['metadata']['url'] = 'https://www.sec.gov/Archives/quarterly'
    m['rankedQuarterlyFiling']['paragraphs'] *= 2
    result = extract({'ticker': 'T'}, m)
    assert len(result['items']) == 1
    item = result['items'][0]
    assert [r['form'] for r in item['sourceRefs']] == ['10-K', '10-Q']
    assert item['sourceRef'] == item['sourceRefs'][0]
    store = ExposureStore(tmp_path)
    store.save(result, materials=m)
    assert store.get('T') == result
    m['rankedQuarterlyFiling']['paragraphs'] = [{'item': '7A', 'text': 'Higher interest rates could increase our borrowing costs.'}]
    assert len(extract({'ticker': 'T'}, m)['items']) == 2


def test_explicit_fx_cost_exposure_is_retained_without_resolving_direction_basis():
    quote = 'Higher exchange rates would increase our borrowing costs.'
    assert {i['factor'] for i in extract({'ticker': 'T'}, materials(quote))['items']} == {'fx'}
