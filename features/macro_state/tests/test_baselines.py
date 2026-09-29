from features.macro_state.baselines import single_series
from .test_inputs import row


def test_b1_thresholds_are_not_proposal_thresholds():
    rows=[row('NFCI','2025-12-26','.1'),row('NFCI','2025-11-28','0')]
    r=single_series('US','financial_conditions',rows,'2026-01-31T23:59:59Z')
    assert r['level']=='tight' and r['direction']=='rising'
    rows=[row('STLFSI4','2025-12-26','2'),row('STLFSI4','2025-11-28','1.99')]
    r=single_series('US','stress_vulnerability',rows,'2026-01-31T23:59:59Z')
    assert r['level']=='elevated' and r['direction']=='rising'


def test_b1_kr_financial_level_has_no_invented_enum():
    rows=[row('KR_RATE','2025-12-31','3'),row('KR_RATE','2025-09-30','2.99')]
    r=single_series('KR','financial_conditions',rows,'2026-01-31T23:59:59Z')
    assert r['level']=='unknown' and r['direction']=='rising'
