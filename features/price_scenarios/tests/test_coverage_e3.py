from copy import deepcopy
import pytest
from features.price_scenarios.class_history import read_class_filing, supplement_class_history
from features.price_scenarios.coverage_history import row_at, EPS, SHARES

SECURITY = {'kind': 'common_share', 'title': 'Class A Common Stock'}


def history():
    return {'currency': 'USD', 'excludedYears': [], 'rows': [
        {'metric': 'Net Income', 'value': '200', 'fiscalYear': y, 'unit': 'USD', 'precision': 0,
         'period': {'start': f'{y}-01-01', 'end': f'{y}-12-31'}, 'filed': '2026-02-01',
         'accession': 'n', 'concept': 'NetIncomeLoss', 'form': '10-K'} for y in range(2023, 2026)]}


def filing(*, filed='2026-02-01', accession='a', eps='2', member='g:CommonClassAMember', extra='', scale='0', sign='', decimals='2', labels=None, years=range(2023, 2026)):
    contexts, facts = [], []
    for y in years:
        contexts.append(f'<xbrli:context id="c{y}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">123</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="g:StatementClassOfStockAxis">{member}</xbrldi:explicitMember>{extra}</xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>{y}-01-01</xbrli:startDate><xbrli:endDate>{y}-12-31</xbrli:endDate></xbrli:period></xbrli:context>')
        facts.append(f'<ix:nonFraction name="g:EarningsPerShareDiluted" contextRef="c{y}" unitRef="eps" scale="{scale}" decimals="{decimals}" {sign}>{eps}</ix:nonFraction><ix:nonFraction name="g:WeightedAverageNumberOfDilutedSharesOutstanding" contextRef="c{y}" unitRef="shares" decimals="0">100</ix:nonFraction>')
    markup = '<html xmlns:g="http://fasb.org/us-gaap/2025" xmlns:issuer="http://issuer.test/2025" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:xbrli="http://www.xbrl.org/2003/instance">'
    markup += ''.join(contexts) + '<xbrli:unit id="eps"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit><xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>' + ''.join(facts) + '</html>'
    return {'markup': markup, 'filed': filed, 'accession': accession, 'form': '10-K', 'url': 'https://www.sec.gov/test/a.htm', 'labels': labels or {}}


def supplement(h=None, packets=None):
    return supplement_class_history(h or history(), packets or [filing()], SECURITY, cik='123', as_of='2026-10-02')


def test_actual_three_year_class_values_and_complete_validation_sources_replay():
    source = history()
    result = supplement(source)
    assert source == history()
    assert result['listedClass'] == {'id': 'A', 'label': 'Class A'}
    for y in range(2023, 2026):
        e = row_at(result, EPS, y)
        assert e['value'] == '2' and e['source'] == 'filing_class_member' and e['classValidation']['relativeError'] == '0'
        assert e['classValidation']['netIncome']['value'] == '200'
    assert supplement(result) == result


@pytest.mark.parametrize('kwargs,reason', [({'member': 'g:CommonClassBMember'}, 'listed_class_eps_not_found'),
    ({'extra': '<xbrldi:explicitMember dimension="g:OtherAxis">g:OtherMember</xbrldi:explicitMember>'}, 'listed_class_eps_not_found'),
    ({'member': 'issuer:ClassABaitMember'}, 'listed_class_eps_not_found'),
    ({'eps': '3'}, 'listed_class_reconciliation_failed'), ({'decimals': ''}, 'listed_class_source_unavailable')])
def test_missing_member_extra_axis_label_guess_and_reconciliation_are_rejected(kwargs, reason):
    result = supplement(packets=[filing(**kwargs)])
    assert not row_at(result, EPS, 2025)
    assert result['classDiagnostics']['reason'] == reason


def test_official_extension_label_and_ambiguous_members():
    labels = {'issuer:ActualMember': ['Class A Common Stock [Member]']}
    assert supplement(packets=[filing(member='issuer:ActualMember', labels=labels)])['listedClass']['id'] == 'A'
    packet = filing(member='issuer:ActualMember', labels=labels)
    other = filing(member='issuer:OtherMember', labels={'issuer:OtherMember': ['Class A Common Stock']})
    packet['markup'] = packet['markup'].replace('</html>', other['markup'] + '</html>')
    packet['labels'].update(other['labels'])
    # Duplicate context ids are invalid; use distinct ids for the second member.
    packet['markup'] = filing(member='issuer:ActualMember', labels=labels)['markup'].replace('</html>', other['markup'].replace('c202', 'd202') + '</html>')
    assert read_class_filing(packet, SECURITY, cik='123', currency='USD')['reason'] == 'listed_class_eps_ambiguous'


def test_scale_sign_decimals_unit_period_entity_cutoff():
    packet = filing(eps='0.2', scale='1', sign='sign="-"', decimals='-6')
    parsed = read_class_filing(packet, SECURITY, cik='123', currency='USD')
    e = next(r for r in parsed['rows'] if r['metric'] == EPS)
    assert e['value'] == '-2.0' and e['precision'] == -6 and e['displayedValue'] == '0.2'
    assert read_class_filing(packet, SECURITY, cik='456', currency='USD')['rows'] == []
    assert all(r.get('error') for r in read_class_filing(packet, SECURITY, cik='123', currency='EUR')['rows'] if r['metric'] == EPS)
    bad = filing()
    bad['markup'] = bad['markup'].replace('-01-01', '-10-01')
    assert read_class_filing(bad, SECURITY, cik='123', currency='USD')['rows'] == []
    assert not row_at(supplement(packets=[filing(filed='2027-02-01')]), EPS, 2025)


def test_latest_bad_values_do_not_fall_back_and_read_prior_values_are_preserved():
    old = filing(filed='2026-01-01', accession='old')
    bad = filing(eps='3')
    assert not row_at(supplement(packets=[old, bad]), EPS, 2025)
    packets = [filing(filed=f'2026-0{m}-01', accession=str(m), eps='3') for m in range(2, 6)] + [old]
    assert not row_at(supplement(packets=packets), EPS, 2025)
    # Read an older source only while the ten-year fiscal domain is uncovered.
    h = history()
    h['rows'].append({**deepcopy(h['rows'][0]), 'fiscalYear': 2022, 'period': {'start': '2022-01-01', 'end': '2022-12-31'}})
    result = supplement(h, packets=[old, filing()])
    assert row_at(result, EPS, 2025)['priorValues'][0]['accession'] == 'old'


def test_zero_exact_validation_latest_failure_and_fewer_than_three():
    h = history()
    for row in h['rows']:
        row['value'] = '0'
    assert row_at(supplement(h, [filing(eps='0')]), EPS, 2025)['value'] == '0'
    h['rows'][-1]['value'] = '1'
    assert not row_at(supplement(h, [filing(eps='0')]), EPS, 2025)
    h = history()
    h['rows'][0]['value'] = '1'
    assert not row_at(supplement(h), EPS, 2025)


def test_dimensionless_overlap_needs_same_class_and_same_filing_pair():
    actual = supplement()
    h = history()
    for metric in (EPS, SHARES):
        old = deepcopy(row_at(actual, metric, 2023))
        old.pop('classBasis')
        h['rows'].append(old)
    assert not row_at(supplement(h), EPS, 2025)  # only two validated years
    for row in h['rows']:
        if row['metric'] in {EPS, SHARES}:
            row['classBasis'] = 'A'
    assert row_at(supplement(h), EPS, 2025)
    row_at(h, EPS, 2023)['value'] = '9'
    assert not row_at(supplement(h), EPS, 2025)


def test_rejected_past_values_are_missing_after_three_other_years_pass():
    h = history()
    prior = {**deepcopy(h['rows'][0]), 'fiscalYear': 2022, 'period': {'start': '2022-01-01', 'end': '2022-12-31'}}
    h['rows'].append(prior)
    h['rows'].append({**deepcopy(prior), 'metric': EPS, 'unit': 'USD/shares', 'value': '9'})
    out = supplement(h, [filing(years=range(2022, 2026))])
    assert out['listedClass']['id'] == 'A'
    assert row_at(out, EPS, 2022) is None
    assert any(r['metric'] == EPS and r['fiscalYear'] == 2022 and r['value'] == '9' for r in out['existingSourceRows'])


def test_same_day_newer_accession_pair_has_its_own_validation():
    h = history()
    original = supplement()
    for metric in (EPS, SHARES):
        r = deepcopy(row_at(original, metric, 2023))
        r.update(accession='z', source='companyfacts', value='2.02' if metric == EPS else '100')
        h['rows'].append(r)
    out = supplement(h)
    e = row_at(out, EPS, 2023)
    assert e['value'] == '2.02' and e['accession'] == 'z'
    assert e['classValidation']['eps']['value'] == '2.02' and e['classValidation']['eps']['accession'] == 'z'
    assert e['classValidation']['relativeError'] != '0'


def test_old_unreadable_or_missing_member_does_not_cancel_three_verified_latest_years():
    for old in (filing(filed='2025-01-01', member='g:CommonClassBMember'), {**filing(filed='2025-01-01'), 'markup': ''}):
        out = supplement(packets=[filing(), old])
        assert row_at(out, EPS, 2025)['value'] == '2'
        assert out['classDiagnostics']['filings']
