from features.company_exposure.portfolio import aggregate
from features.company_exposure.store import ExposureStore
from features.company_exposure.extraction import extract
from features.investment_review.review_v2 import build_input_basis, attach_macro_lineage
from features.investment_review.schema import normalize_review
from features.macro_state.store import StateStore
from features.macro_state.tests.test_store import snapshot
from .test_exposure import materials


def test_weight_not_multiplied_by_passages_and_no_target_substitution(tmp_path):
    m = materials(); m['rankedFiling']['paragraphs'].append({'item': '7A', 'text': 'Higher interest rates increase our interest expense.'})
    store = ExposureStore(tmp_path)
    for ticker in ('A', 'B'):
        store.save(extract({'ticker': ticker}, m), materials=m)
    result = aggregate(tmp_path, [{'ticker': 'A', 'weight': .3}, {'ticker': 'B', 'weight': .2}, {'ticker': 'C', 'weight': .5}])
    group = result['groups'][0]
    assert group['combinedWeight'] == .5 and len(group['positions']) == 2
    assert result['dataGaps'] == [{'ticker': 'C', 'reason': 'disclosed_exposure_unavailable'}]
    assert all('magnitudeQuote' not in item for item in group['evidence'])
    assert aggregate(tmp_path, [{'ticker': 'A', 'targetWeight': .9}])['groups'][0]['combinedWeight'] is None
    duplicate_lots = aggregate(tmp_path, [{'ticker': 'A', 'weight': .3}, {'ticker': 'A', 'weight': .2}])['groups'][0]
    assert duplicate_lots['combinedWeight'] == .5 and len(duplicate_lots['positions']) == 1
    assert len(duplicate_lots['evidence']) == len(group['evidence']) // 2


def test_macro_lineage_changes_new_basis_and_preserves_legacy(tmp_path):
    inputs = {'portfolio': {'revision': 1}}
    before = build_input_basis(inputs)
    assert attach_macro_lineage(dict(inputs), tmp_path, before) == inputs
    saved = StateStore(tmp_path/'market-memory.sqlite3').save(snapshot(), reason='fixture')
    current = attach_macro_lineage(dict(inputs), tmp_path, {'macroBasisVersion': 'macro-lineage-1'})
    basis = build_input_basis(current)
    assert basis['macroSnapshots'][0]['snapshotId'] == saved['snapshotId']
    assert basis['macroSnapshots'][0]['inputFingerprint'] == saved['inputFingerprint']
    assert basis['fingerprint'] != before['fingerprint']
    review = normalize_review({'schemaVersion': 2, 'inputBasis': basis})
    assert review['inputBasis']['macroSnapshots'] == basis['macroSnapshots']
