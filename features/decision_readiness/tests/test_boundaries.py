"""Failure, identity, partial exposure and pinned-vintage boundaries on synthetic workspaces."""
import copy
import io
import json
import sqlite3
from decimal import Decimal

import pytest
from features.common.market_data import readonly_quote as provider
from features.common.macro_data.store import MacroStore
from features.common.macro_data.tests.test_ledger import point, write
from features.company_exposure.extraction import extract
from features.company_exposure.store import ExposureStore
from features.company_exposure.tests.test_exposure import materials
from features.decision_readiness import DecisionError
from features.decision_readiness.inputs import Files, database
from features.decision_readiness.portfolio_fit import capture_basis, current_composition, preview
from features.decision_readiness.service import comparison
from .test_capture import seeded, STAMP
from .test_rules import DAY, personal, ready_snapshot
from features.decision_readiness.criteria import evaluate


@pytest.mark.parametrize("irr,irr_range,status", [(None, None, "unavailable"), (None, "above_range", "available"), (None, "below_range", "available"), ("NaN", None, "available"), ("Infinity", None, "available"), (".12", None, "available")])
def test_matching_basis_without_scenario_numbers_is_incomparable(irr, irr_range, status):
    from features.decision_readiness.comparison import DIMENSIONS, cell, comparability
    basis = {"asOf": DAY, "methodVersion": "fixed", "specSha256": "fixed", "currency": "USD", "holdingYears": 10}
    rows = []
    for ticker in ("A", "B"):
        dimensions = {name: cell("available") for name in DIMENSIONS}
        dimensions["scenarioReturn"] = cell("available", basis=basis, value=[{"label": "base", "horizon": 10, "status": status, "irr": irr, "irrRange": irr_range}])
        rows.append({"identity": {"instrumentId": f"US:{ticker}"}, "dimensions": dimensions})
    result = comparability(rows)[0]["dimensions"]["scenarioReturn"]
    expected = {"status": "same_basis", "reasons": []} if irr == ".12" else {"status": "incomparable", "reasons": ["scenario_cells_missing"]}
    assert result == expected


def test_macro_vintage_replay_and_partial_exposure(tmp_path):
    seeded(tmp_path)
    official = materials()
    ExposureStore(tmp_path).save(extract({"ticker": "ACME", "market": "US"}, official), materials=official)
    store = MacroStore(tmp_path / "market-memory.sqlite3")
    metadata = {"unit": "Percent", "frequency": "D", "adjustment": "NSA", "definitionVersion": "v1"}
    write(store, point("2024-12-01", "3", "2024-12-02", series="DFF", metadata=metadata),
          point("2025-03-01", "4", "2025-03-01", series="DFF", metadata=metadata))
    first = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    assert first["candidates"][0]["dimensions"]["macroFit"]["value"]["items"][0]["interpretation"] == "challenging"
    assert first["referenceSet"]["candidates"][0]["macroRows"]
    write(store, point("2025-03-01", "2", "2025-03-01", series="DFF", metadata=metadata))
    assert comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP, reference_set=first["referenceSet"]) == first
    now = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    assert now["candidates"][0]["dimensions"]["macroFit"]["value"]["items"][0]["interpretation"] == "unknown"
    assert "exposure_is_partial" in now["candidates"][0]["readiness"]["warnings"]


def test_optional_basis_weight_is_pinned_without_writes(tmp_path):
    store = seeded(tmp_path)
    store.save_criteria(required_return="10", min_margin_of_safety="20", holding_years=10)
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"positions": [{"ticker": "ACME", "market": "US", "quantity": "2", "industry": "software"}], "cash": [{"currency": "USD", "amount": "10"}]}))
    before = {p.name: p.read_bytes() for p in tmp_path.glob('*') if p.is_file()}
    basis = capture_basis(tmp_path, "US:ACME", quote_reader=lambda _: {"status": "available", "value": "10", "currency": "USD"}, fx_reader=lambda _: {"status": "available", "rateToUsd": "1"})
    result = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP, portfolio_basis=basis, portfolio_basis_id="in-memory")
    weights = result["candidates"][0]["dimensions"]["portfolioOverlap"]["value"]["confirmedWeights"]
    assert Decimal(weights["sameSecurity"]) > Decimal('.66')
    assert Decimal(weights["uninvestigatedHoldingWeight"]) > Decimal('.66')
    assert current_composition(basis)["concentration"]["top3"] == weights["sameSecurity"]
    assert comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP, reference_set=result["referenceSet"], portfolio_basis=basis, portfolio_basis_id="in-memory") == result
    assert {p.name: p.read_bytes() for p in tmp_path.glob('*') if p.is_file()} == before
    basis["dataGaps"] = ["fx_unavailable"]
    assert current_composition(basis) is None


@pytest.mark.parametrize('mutation', ['missing_keys', 'report_hash', 'bool_macro_id', 'wrong_snapshot', 'wrong_revision'])
def test_bad_replay_request_is_validation_error(tmp_path, mutation):
    seeded(tmp_path)
    initial = comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)
    refs = copy.deepcopy(initial['referenceSet'])
    candidates = [{"instrumentId": "US:ACME"}]
    if mutation == 'missing_keys': refs.pop('portfolioHash')
    if mutation == 'report_hash': refs['candidates'][0]['report'] = {'id': 'missing', 'hash': None}
    if mutation == 'bool_macro_id': refs['candidates'][0]['macroMaxId'] = True
    if mutation == 'wrong_snapshot': candidates[0]['snapshotId'] = 'other'
    if mutation == 'wrong_revision': refs['criteriaRevisionId'] = True
    with pytest.raises(DecisionError) as caught:
        comparison(tmp_path, candidates, at=STAMP, reference_set=refs)
    assert caught.value.status == 422


def test_read_fences_reject_concurrent_inputs_and_invalid_json(tmp_path):
    store = seeded(tmp_path)
    with sqlite3.connect(store.path) as setup:
        setup.execute('PRAGMA journal_mode=WAL')
    with pytest.raises(DecisionError, match='comparison_inputs_changed'):
        with database(tmp_path) as conn:
            conn.execute('SELECT COUNT(*) FROM price_snapshots').fetchone()
            with sqlite3.connect(store.path) as other:
                other.execute("INSERT INTO price_snapshot_reviews(snapshot_id,reason,metric,fiscal_year,detected_by_snapshot_id,created_at) VALUES('a','restated','EPS',2024,'b','now')")
    files = Files(tmp_path)
    files.read('portfolio.json')
    (tmp_path / 'portfolio.json').write_text('{}')
    with pytest.raises(DecisionError, match='comparison_inputs_changed'): files.verify()
    (tmp_path / 'portfolio.json').write_text('{ broken')
    with pytest.raises(DecisionError, match='source_file_invalid'): comparison(tmp_path, [{"instrumentId": "US:ACME"}], at=STAMP)


def test_files_never_read_outside_workspace(tmp_path, monkeypatch):
    from pathlib import Path
    root = tmp_path / 'workspace'; root.mkdir()
    outside = tmp_path / 'outside.json'; outside.write_text('{"private":"fixture only"}')
    sibling = tmp_path / 'workspace-other'; sibling.mkdir()
    sibling_file = sibling / 'outside.json'; sibling_file.write_text('{}')
    files = Files(root)
    original = Path.read_bytes
    def guarded_read(path):
        assert path not in (outside, sibling_file), 'outside file must be rejected before reading'
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    for relative in ('../outside.json', str(outside), '../workspace-other/outside.json'):
        with pytest.raises(DecisionError, match='source_path_outside_workspace'): files.read(relative)


def test_file_symlink_escape_is_rejected_before_read_or_verify(tmp_path, monkeypatch):
    from pathlib import Path
    root = tmp_path / 'workspace'; root.mkdir()
    outside = tmp_path / 'outside.json'; outside.write_text('{"private":"fixture only"}')
    files = Files(root)
    original = Path.read_bytes
    def guarded_read(path):
        assert path != outside, 'outside file must be rejected before reading'
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded_read)
    link = root / 'escaped.json'
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('Creating symlinks requires platform permission')
    with pytest.raises(DecisionError, match='source_path_outside_workspace'): files.read('escaped.json')
    files.observed['escaped.json'] = 'recorded-before-retargeting'
    with pytest.raises(DecisionError, match='source_path_outside_workspace'): files.verify()


def test_report_catalog_never_lists_outside_workspace(tmp_path):
    root = tmp_path / 'workspace'; root.mkdir()
    outside = tmp_path / 'outside'; outside.mkdir()
    try:
        (root / 'company-analysis').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Creating symlinks requires platform permission')
    with pytest.raises(DecisionError, match='source_path_outside_workspace'): Files(root).list_reports()


@pytest.mark.parametrize('value', [None, '0', '-1'])
def test_eligible_dcf_without_positive_value_is_incomplete(value):
    snapshot = ready_snapshot()
    snapshot['results']['dcf']['result']['scenarios'][0]['perShare'] = value
    result = evaluate(snapshot, personal(), today=DAY)
    assert result['state'] == 'incomplete' and 'eligible_dcf_missing' in result['blockingReasons']


def test_quote_currency_symbol_and_timestamp_are_verified(monkeypatch, tmp_path):
    meta = {'symbol': 'ABC.L', 'regularMarketPrice': '123.45', 'currency': 'GBp', 'regularMarketTime': 1740960000, 'instrumentType': 'EQUITY'}
    def network(*args, **kwargs):
        return io.BytesIO(json.dumps({'chart': {'result': [{'meta': meta}]}}).encode())
    monkeypatch.setattr(provider, 'urlopen', network)
    quote = provider.read_quote('ABC.L')
    assert quote['value'] == '1.2345' and quote['currency'] == 'GBP' and quote['observedAt']
    meta['currency'] = None
    assert provider.read_quote('ABC.L')['status'] == 'unavailable'
    meta['currency'] = 'GBP'; meta['symbol'] = 'OTHER.L'
    assert provider.read_quote('ABC.L')['status'] == 'unavailable'
    assert list(tmp_path.iterdir()) == []


def test_fx_wrong_provider_currency_has_no_fallback(monkeypatch):
    monkeypatch.setattr(provider, 'read_quote', lambda _: {'status': 'available', 'value': '2', 'currency': 'JPY'})
    assert provider.read_fx('EUR')['status'] == 'unavailable'
    assert provider.read_fx(None)['status'] == 'unavailable'


@pytest.mark.parametrize('market,ticker,symbol', [('US', 'SAP', 'AAPL'), ('KR', '005930', '000660.KS'), ('US', 'SAP', 'SAP.DE')])
def test_other_security_quote_is_not_a_denominator(tmp_path, market, ticker, symbol):
    path = tmp_path / 'portfolio.json'
    path.write_text(json.dumps({'positions': [{'market': market, 'ticker': ticker, 'symbol': symbol, 'quantity': '2'}], 'cash': [{'currency': 'USD', 'amount': '10'}]}))
    before = path.read_bytes(); calls = []
    def quote(value):
        calls.append(value)
        return {'status': 'available', 'value': '10', 'currency': 'USD'}
    basis = capture_basis(tmp_path, 'US:C', quote_reader=quote, fx_reader=lambda _: {'status': 'available', 'rateToUsd': '1'})
    assert 'holding_quote_identity_unverified' in basis['dataGaps'] and calls == []
    assert preview(basis, 'US:C', '20')['status'] == 'unavailable'
    assert path.read_bytes() == before


def test_duplicate_lot_identity_and_foreign_venues(tmp_path):
    path = tmp_path / 'portfolio.json'
    path.write_text(json.dumps({'positions': [{'market': 'US', 'ticker': 'SAP', 'symbol': symbol, 'quantity': '1'} for symbol in ['SAP', 'AAPL']]}))
    basis = capture_basis(tmp_path, 'US:C', quote_reader=lambda _: {'status': 'available', 'value': '10', 'currency': 'USD'}, fx_reader=lambda _: {'status': 'available', 'rateToUsd': '1'})
    assert preview(basis, 'US:C', '20')['status'] == 'unavailable'
    path.write_text(json.dumps({'positions': [{'market': 'EUROPE', 'ticker': 'SAP', 'symbol': symbol, 'quantity': '1'} for symbol in ['SAP.DE', 'SAP.L']]}))
    basis = capture_basis(tmp_path, 'US:C', quote_reader=lambda _: {'status': 'available', 'value': '10', 'currency': 'EUR'}, fx_reader=lambda _: {'status': 'available', 'rateToUsd': '1'})
    assert [row['instrumentId'] for row in basis['entries']] == ['EUROPE:SAP.DE', 'EUROPE:SAP.L']


def test_comparison_holding_and_weight_share_venue_identity(tmp_path):
    path = tmp_path / 'portfolio.json'
    path.write_text(json.dumps({'positions': [{'market': 'EUROPE', 'ticker': 'SAP', 'symbol': 'SAP.DE', 'quantity': '1'}]}))
    basis = capture_basis(tmp_path, 'EUROPE:SAP.DE', quote_reader=lambda _: {'status': 'available', 'value': '10', 'currency': 'EUR'}, fx_reader=lambda _: {'status': 'available', 'rateToUsd': '1'})
    result = comparison(tmp_path, [{'instrumentId': 'EUROPE:SAP.DE'}, {'instrumentId': 'EUROPE:SAP'}, {'instrumentId': 'EUROPE:SAP.L'}], at=STAMP, portfolio_basis=basis)
    overlaps = [row['dimensions']['portfolioOverlap']['value'] for row in result['candidates']]
    assert overlaps[0]['heldSameSecurity'] is True and overlaps[0]['confirmedWeights']['sameSecurity'] == '1'
    assert overlaps[1]['heldSameSecurity'] is None and overlaps[1]['confirmedWeights']['sameSecurity'] is None
    assert overlaps[2]['heldSameSecurity'] is False and overlaps[2]['confirmedWeights']['sameSecurity'] == '0'


def test_ticker_only_reason_does_not_cross_market_and_suffix_uses_owner_convention(tmp_path):
    from features.thesis_tracking import store as ST
    from features.thesis_tracking.model import Thesis
    store = seeded(tmp_path, 'SAP')
    with ST.connect(store.path) as conn:
        ST.upsert_thesis(conn, Thesis(ticker='SAP', core_thesis='미국 상장선 이유'), edit_source='manual')
        ST.upsert_thesis(conn, Thesis(ticker='7203-T', core_thesis='일본 상장선 이유'), edit_source='manual')
        conn.commit()
    result = comparison(tmp_path, [{'instrumentId': 'US:SAP'}, {'instrumentId': 'EUROPE:SAP'}, {'instrumentId': 'JP:7203.T'}], at=STAMP)
    reasons = [row['dimensions']['reasonState']['value'] for row in result['candidates']]
    assert reasons[0]['text'] == '미국 상장선 이유'
    assert reasons[1]['status'] == 'unknown' and reasons[1]['text'] == '' and reasons[1]['events'] == []
    assert reasons[2]['text'] == '일본 상장선 이유'
    assert comparison(tmp_path, [{'instrumentId': 'US:SAP'}, {'instrumentId': 'EUROPE:SAP'}, {'instrumentId': 'JP:7203.T'}], at=STAMP, reference_set=result['referenceSet']) == result


def test_unreadable_report_is_unknown_context_and_pinned(tmp_path):
    store = seeded(tmp_path)
    store.save_criteria(required_return='10', min_margin_of_safety='20', holding_years=10)
    path = tmp_path / 'company-analysis' / 'broken.json'; path.parent.mkdir()
    path.write_bytes(b'{ broken')
    first = comparison(tmp_path, [{'instrumentId': 'US:ACME'}], at=STAMP)
    quality = first['candidates'][0]['dimensions']['companyQuality']
    assert quality['status'] == 'unknown' and quality['dataGaps'] == ['company_report_unreadable']
    assert first['candidates'][0]['readiness']['state'] == 'ready_for_review'
    assert first['referenceSet']['candidates'][0]['reportReadErrors']
    assert comparison(tmp_path, [{'instrumentId': 'US:ACME'}], at=STAMP, reference_set=first['referenceSet']) == first
    path.write_bytes(b'{}')
    with pytest.raises(DecisionError, match='comparison_inputs_changed'):
        comparison(tmp_path, [{'instrumentId': 'US:ACME'}], at=STAMP, reference_set=first['referenceSet'])


def test_exposure_source_quote_date_and_magnitude_are_preserved(tmp_path):
    official = materials()
    ExposureStore(tmp_path).save(extract({'ticker': 'ACME', 'market': 'US'}, official), materials=official)
    (tmp_path / 'portfolio.json').write_text(json.dumps({'positions': [{'ticker': 'ACME', 'market': 'US', 'quantity': '1'}]}))
    basis = capture_basis(tmp_path, 'US:ACME', quote_reader=lambda _: {'status': 'available', 'value': '10', 'currency': 'USD'}, fx_reader=lambda _: {'status': 'available', 'rateToUsd': '1'})
    coverage = preview(basis, 'US:ACME', '100')['after']['coverage'][0]
    item = coverage['items'][0]
    assert coverage['profileId'] and item['quote'] == official['rankedFiling']['paragraphs'][0]['text']
    assert item['sourceRefs'][0]['date'] == '2026-01-01' and item['magnitudeBasis'] == 'qualitative_only'


def test_schema_migration_failure_is_rolled_back_and_backup_kept(tmp_path, monkeypatch):
    from features.price_scenarios import store as module
    path = tmp_path / 'market-memory.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE price_scenario_schema(version INTEGER PRIMARY KEY)'); conn.execute('INSERT INTO price_scenario_schema VALUES(1)')
        conn.execute('CREATE TABLE valuation_user_criteria(revision_id INTEGER PRIMARY KEY, required_return TEXT, min_margin_of_safety TEXT, holding_years INTEGER, created_at TEXT)')
        conn.execute("INSERT INTO valuation_user_criteria VALUES(1,'10','20',10,'before')")
    before = path.read_bytes()
    monkeypatch.setattr(module, 'DDL', (*module.DDL, 'THIS IS INVALID SQL'))
    with pytest.raises(sqlite3.Error): module.PriceStore(path).ensure()
    assert path.read_bytes() == before
    assert list(tmp_path.glob('*.bak')) or list(tmp_path.rglob('*before-price-scenarios-v2*'))
