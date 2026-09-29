from features.macro_state.engine import calculate
from .test_inputs import row


def test_finance_exact_date_gap_does_not_hide_valid_level():
    rows=[row('NFCI','2026-05-29','0.3'),row('NFCI','2026-05-01','0.2'),
          row('DFF','2026-05-31','4'),row('DFF','2026-02-27','3.5')]
    out=calculate('US','financial_conditions',rows,'2026-06-01T04:59:59.999999Z')
    assert out['level']=='tight' and out['direction']=='unknown'
    assert out['confidence']=='low'
    rows.append(row('DFF','2026-02-28','3.5'))
    out=calculate('US','financial_conditions',rows,'2026-06-01T04:59:59.999999Z')
    assert out['direction']=='rising'
    assert out['promotion']=='shadow'


def test_stale_values_still_calculate_and_are_reproducible():
    rows=[row('STLFSI4','2025-12-26','1'),row('STLFSI4','2025-11-28','.75')]
    out=calculate('US','stress_vulnerability',rows,'2026-02-01T05:59:59.999999Z')
    assert (out['level'],out['direction'],out['freshness'],out['confidence'])==('elevated','flat','stale','low')
    assert calculate('US','stress_vulnerability',list(reversed(rows)),out['asOf'])==out


def test_growth_contraction_and_cycle_input_do_not_contaminate_axis_stage():
    rows=[row('UNRATE',f'2025-{m:02}-01','4' if m<10 else '5') for m in range(1,13)]
    rows += [row('UNRATE',f'2024-{m:02}-01','4') for m in (10,11,12)]
    rows += [row('INDPRO','2025-12-01','100'),row('INDPRO','2024-12-01','101')]
    rows += [row('ICSA','2025-12-27','200000')]
    out=calculate('US','growth',rows,'2026-01-31T23:59:59Z')
    assert out['level']=='contraction' and out['confidence']=='low'
    assert out['cycleSignal']=='contraction_confirmed'
    assert 'leading' not in out['evidenceStage']
    assert out['cycleSignalPromotion']=='shadow'


def test_no_claims_vintage_remains_unknown_even_after_first_provider_date():
    rows=[row('UNRATE',f'2025-{m:02}-01','4' if m<10 else '5') for m in range(1,13)]
    rows += [row('UNRATE',f'2024-{m:02}-01','4') for m in (10,11,12)]
    rows += [row('INDPRO','2025-12-01','100'),row('INDPRO','2024-12-01','101')]
    out=calculate('US','growth',rows,'2026-01-31T23:59:59Z')
    assert out['level']=='contraction'
    assert out['cycleSignal']=='unknown'


def test_kr_target_reference_uses_observation_month_not_evaluation_date():
    rows=[row('KR_CPI','2015-12-01','102'),row('KR_CPI','2014-12-01','100'),
          row('KR_CPI','2015-09-01','102'),row('KR_CPI','2014-09-01','100')]
    out=calculate('KR','inflation',rows,'2026-01-31T23:59:59Z')
    assert out['level']=='below_reference'
    assert out['direction']=='flat'


def test_conflict_is_never_used_as_valid_numeric_input():
    rows=[row('NFCI','2025-12-26','1',conflict=True),row('NFCI','2025-11-28','.5'),
          row('DFF','2025-12-31','4'),row('DFF','2025-09-30','3')]
    out=calculate('US','financial_conditions',rows,'2026-01-31T23:59:59Z')
    assert out['level']==out['direction']=='unknown'
    assert any(g['reason']=='integrityConflict' for g in out['unknownReason'])


def test_revision_retains_original_observation_dates():
    rows=[row('STLFSI4','2025-12-26','1'),row('STLFSI4','2025-11-28','.75')]
    at='2026-01-31T23:59:59Z'
    original=calculate('US','stress_vulnerability',rows,at)
    revised=rows+[row('STLFSI4','2026-02-27','10',availableAt='2026-03-01T00:00:00Z')]
    out=calculate('US','stress_vulnerability',revised,at,selection=original['observationSelection'],selection_cutoff='2026-04-30T23:59:59Z')
    assert out['level']==original['level'] and out['direction']==original['direction']
    assert out['inputFingerprint']==original['inputFingerprint']
    assert all(r['period']<'2026' for r in out['sourceRefs'])
