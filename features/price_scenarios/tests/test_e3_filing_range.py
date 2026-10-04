"""Eight-source walk, safe amendment skip, format stop versus atomic IO failure."""
from copy import deepcopy
from concurrent.futures import CancelledError
import pytest

from features.price_scenarios import collect, service, history as hm
from features.price_scenarios.class_history import read_class_filing, supplement_class_history
from features.price_scenarios.coverage_history import EPS, row_at
from features.price_scenarios.report import reason_text
from .snapshot_fixtures import make
from .test_coverage_e3 import SECURITY, filing, history


def ten_years():
    template = history()['rows'][0]
    return {'currency': 'USD', 'excludedYears': [], 'rows': [
        {**deepcopy(template), 'fiscalYear': y, 'period': {'start': f'{y}-01-01', 'end': f'{y}-12-31'}}
        for y in range(2016, 2026)]}


def packets():
    return [filing(filed=f'{y+1}-02-01', accession=f'a{y}', years=[y]) for y in range(2025, 2015, -1)]


def empty_amendment():
    return {**filing(filed='2026-03-01', accession='amend'), 'form': '10-K/A',
            'markup': '<html><body>This amendment is solely to provide the information required by Part III. No financial statements are amended.</body></html>'}


def setup_collector(monkeypatch, tmp_path, h=None, ps=None):
    h, ps = h or ten_years(), ps or packets()
    for index, p in enumerate(ps):
        p['accession'] = f'0000000123-{p["filed"][2:4]}-{index:06d}'
    metadata = {'filings': {'recent': {'form': [p['form'] for p in ps], 'filingDate': [p['filed'] for p in ps],
                 'accessionNumber': [p['accession'] for p in ps], 'primaryDocument': [p['accession']+'.htm' for p in ps]}, 'files': []}}
    for p in ps:
        p['url'] = 'https://www.sec.gov/Archives/edgar/data/123/' + p['accession'].replace('-', '') + '/' + p['accession'] + '.htm'
    monkeypatch.setattr(hm, 'sec_history', lambda *a, **k: deepcopy(h))
    monkeypatch.setattr('features.price_scenarios.securities.listed_security', lambda *a, **k: SECURITY)
    calls = []
    def fetch(url, path):
        calls.append(url)
        p = next(p for p in ps if p['url'] == url)
        return p['markup'], ''
    monkeypatch.setattr(collect.sec_filings, 'fetch_text', fetch)
    made = collect.Collector(tmp_path)
    annual = {'form': ps[0]['form'], 'accession': ps[0]['accession'], 'url': ps[0]['url']}
    args = ({}, metadata, annual, ps[0]['markup'], {'price': {'sessionDate': '2026-10-01'}}, '123', 'ABC')
    return made, args, calls


def test_eight_filing_cap_both_collect_and_pure_reader(monkeypatch, tmp_path):
    made, args, calls = setup_collector(monkeypatch, tmp_path)
    got = made._class_filings(*args)
    assert len(got) == 8 and len(calls) == 7  # newest document is already downloaded
    result = supplement_class_history(ten_years(), packets(), SECURITY, cik='123', as_of='2026-10-01')
    assert len(result['classDiagnostics']['filings']) == 8
    assert result['classDiagnostics']['stopReason'] == 'filing_limit'
    assert {r['fiscalYear'] for r in result['rows'] if r['metric'] == EPS} == set(range(2018, 2026))


def test_full_window_stops_before_older_filing_and_archive(monkeypatch, tmp_path):
    ps = [filing(filed='2026-03-01', years=range(2016, 2026)), *packets()]
    made, args, calls = setup_collector(monkeypatch, tmp_path, ps=ps)
    args[1]['filings']['files'] = [{'name': 'CIK0000000123-submissions-001.json', 'filingTo': '2015-12-31'}]
    got = made._class_filings(*args)
    assert len(got) == 1 and calls == []
    out = supplement_class_history(ten_years(), ps, SECURITY, cik='123', as_of='2026-10-01')
    assert out['classDiagnostics']['stopReason'] == 'window_covered'
    assert len(out['classDiagnostics']['filings']) == 1


def test_empty_amendment_skips_counts_cap_and_keeps_source_proof(monkeypatch, tmp_path):
    ps = [empty_amendment(), *packets()]
    made, args, calls = setup_collector(monkeypatch, tmp_path, ps=ps)
    got = made._class_filings(*args)
    assert len(got) == 8 and len(calls) == 7
    out = supplement_class_history(ten_years(), got, SECURITY, cik='123', as_of='2026-10-01')
    proof = out['classDiagnostics']['filings'][0]
    assert proof['action'] == 'skip' and proof['reason'] == 'amendment_without_financials' and len(proof['sourceSha256']) == 64
    assert row_at(out, EPS, 2025) and row_at(out, EPS, 2018) is None  # skip consumes one of eight
    dei = empty_amendment()
    dei['markup'] = dei['markup'].replace('<html>', '<html xmlns:dei="http://xbrl.sec.gov/dei/2025">').replace('<body>', '<body><ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">123</ix:nonFraction>')
    assert read_class_filing(dei, SECURITY, cik='123', currency='USD')['skip']
    dei['markup'] = dei['markup'].replace('<ix:nonFraction', '<table><tr><td><ix:nonFraction').replace('</ix:nonFraction>', '</ix:nonFraction></td></tr></table>')
    assert read_class_filing(dei, SECURITY, cik='123', currency='USD')['skip']


@pytest.mark.parametrize('kind', ['original', 'financial_amendment', 'unknown_amendment', 'inline_financial_amendment', 'earnings_table', 'unknown_inline', 'plain_numbers', 'dei_plain_financials'])
def test_noninline_or_financial_unknown_amendment_does_not_skip(kind):
    p = empty_amendment()
    if kind == 'original': p['form'] = '10-K'
    if kind == 'financial_amendment':
        p['markup'] = p['markup'].replace('</body>', '<h2>Consolidated Statements of Income</h2><table><tr><td>100</td></tr></table></body>')
    if kind == 'unknown_amendment': p['markup'] = '<html><body>Amendment text</body></html>'
    if kind == 'inline_financial_amendment':
        p = {**filing(member='g:CommonClassBMember'), 'form': '10-K/A'}
    if kind == 'earnings_table':
        p['markup'] = p['markup'].replace('</body>', '<h2>Consolidated Statements of Earnings</h2><table><td>Net earnings 100</td></table></body>')
    if kind == 'unknown_inline':
        p['markup'] = p['markup'].replace('</body>', '<ix:nonFraction name="g:EarningsPerShareDiluted">bad</ix:nonFraction></body>')
    if kind == 'plain_numbers':
        p['markup'] = p['markup'].replace('</body>', '<table><td>100</td></table></body>')
    if kind == 'dei_plain_financials':
        p['markup'] = p['markup'].replace('<html>', '<html xmlns:dei="http://xbrl.sec.gov/dei/2025">').replace('</body>', '<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding">123</ix:nonFraction><h2>Results</h2><table><td>Diluted EPS 2.00</td><td>Weighted average diluted shares 100</td></table></body>')
    parsed = read_class_filing(p, SECURITY, cik='123', currency='USD')
    assert not parsed.get('skip') and parsed['reason']


def test_middle_format_stop_keeps_newer_three_and_never_reads_older(monkeypatch, tmp_path):
    ps = packets()
    ps[3]['markup'] = '<html><body>Non-inline financial annual report</body></html>'
    made, args, calls = setup_collector(monkeypatch, tmp_path, ps=ps)
    got = made._class_filings(*args)
    assert len(got) == 4 and len(calls) == 3
    out = supplement_class_history(ten_years(), got, SECURITY, cik='123', as_of='2026-10-01')
    assert row_at(out, EPS, 2025) and not row_at(out, EPS, 2022)
    assert out['classDiagnostics']['stopReason'] == 'format_stop'


def test_middle_malformed_financial_amendment_stops(monkeypatch, tmp_path):
    ps = packets()
    ps[3]['form'] = '10-K/A'
    ps[3]['markup'] = ps[3]['markup'].replace('>2</ix:nonFraction>', '>bad</ix:nonFraction>')
    made, args, calls = setup_collector(monkeypatch, tmp_path, ps=ps)
    got = made._class_filings(*args)
    assert len(got) == 4 and len(calls) == 3
    out = supplement_class_history(ten_years(), got, SECURITY, cik='123', as_of='2026-10-01')
    assert out['classDiagnostics']['stopReason'] == 'format_stop'
    assert {r['fiscalYear'] for r in out['rows'] if r['metric'] == EPS} == {2023, 2024, 2025}


@pytest.mark.parametrize('stage', ['submissions_empty', 'annual_empty', 'cover_empty', 'cover_cached_unidentified'])
def test_initial_transport_failure_is_retryable_before_class_identification(monkeypatch, tmp_path, stage):
    made, args, _ = setup_collector(monkeypatch, tmp_path)
    monkeypatch.setattr(collect.sec_companyfacts, 'resolve_cik', lambda *a: '123')
    made.sec_bytes = lambda *a: b'{}'
    monkeypatch.setattr(collect.sec_filings, 'get_company_submissions', lambda *a: ({} if stage == 'submissions_empty' else args[1], 'SEC request failed' if stage == 'submissions_empty' else ''))
    monkeypatch.setattr(collect.sec_filings, 'latest_annual_report_metadata', lambda *a: {'ok': stage != 'annual_empty', **args[2], 'error': 'SEC request failed' if stage == 'annual_empty' else ''})
    monkeypatch.setattr(collect.sec_filings, 'fetch_text', lambda *a: ('' if stage == 'cover_empty' else '<html>stale cover</html>', 'SEC request failed'))
    monkeypatch.setattr('features.price_scenarios.securities.listed_security', lambda *a, **k: {'kind': 'unknown'})
    with pytest.raises(collect.CollectionError) as e:
        made._collect_us('ABC')
    assert (e.value.code, e.value.sub_code) == ('financial_history_unavailable', 'source_request_failed')


@pytest.mark.parametrize('error_text', ['SEC request failed', 'using cached SEC filing after fetch error'])
def test_middle_transport_failure_fails_whole_calculation_and_preserves_previous(monkeypatch, tmp_path, error_text):
    made, args, calls = setup_collector(monkeypatch, tmp_path)
    original = collect.sec_filings.fetch_text
    def fetch(url, path):
        if url == packets_url(args, 3): return '<html>stale cached document</html>', error_text
        return original(url, path)
    monkeypatch.setattr(collect.sec_filings, 'fetch_text', fetch)
    class ReplayCollector:
        def collect(self, *a):
            made._class_filings(*args)
            pytest.fail('partial raw data must never leave the collector')
    inputs, results = make()
    saved = service.store_for(tmp_path).save_snapshot(inputs, results)
    previous = deepcopy(service.store_for(tmp_path).get(saved['snapshotId']))
    with pytest.raises(service.CalculationNotStored) as error:
        service.calculate(tmp_path, inputs['instrumentId'], collector=ReplayCollector())
    assert (error.value.code, error.value.sub_code) == ('financial_history_unavailable', 'source_request_failed')
    assert service.store_for(tmp_path).latest(inputs['instrumentId']) == previous
    assert len(service.store_for(tmp_path).history(inputs['instrumentId'])) == 1
    assert service.read_attempt(tmp_path, inputs['instrumentId'])['reason'] == {'code': 'financial_history_unavailable', 'subCode': 'source_request_failed', 'httpStatus': None, 'sourceFailureVerified': False}
    assert '오류가 일시적인지는 확인하지 못했습니다' in reason_text(service.read_attempt(tmp_path, inputs['instrumentId'])['reason'])


def packets_url(args, index):
    recent = args[1]['filings']['recent']; acc = recent['accessionNumber'][index]
    return 'https://www.sec.gov/Archives/edgar/data/123/' + acc.replace('-', '') + '/' + acc + '.htm'


def test_required_source_archive_schema_label_and_cancel(monkeypatch, tmp_path):
    made, args, _ = setup_collector(monkeypatch, tmp_path)
    for error in ('SEC request failed', 'using cached SEC filing after fetch error'):
        monkeypatch.setattr(collect.sec_filings, 'fetch_text', lambda *a: ('cached', error))
        for name in ('submissions.json', 'report.htm', 'schema.xsd', 'labels.xml'):
            with pytest.raises(collect.CollectionError) as e:
                made._class_source('https://www.sec.gov/' + name, tmp_path/name)
            assert e.value.sub_code == 'source_request_failed'
    for errors in [('cached submissions error',), ('cached latest cover error',)]:
        with pytest.raises(collect.CollectionError): made._class_filings(*args, source_errors=errors)
    def cancel(*a): raise CancelledError()
    monkeypatch.setattr(collect.sec_filings, 'fetch_text', cancel)
    with pytest.raises(CancelledError): made._class_source('https://www.sec.gov/test', tmp_path/'test')


def test_dimensionless_latest_eps_has_zero_additional_collection(monkeypatch, tmp_path):
    h = ten_years()
    h['rows'].append({**deepcopy(h['rows'][-1]), 'metric': EPS, 'unit': 'USD/shares', 'value': '2'})
    made, args, calls = setup_collector(monkeypatch, tmp_path, h=h)
    assert made._class_filings(*args) is None and calls == []
