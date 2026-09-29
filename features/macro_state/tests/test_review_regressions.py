import datetime as dt
from decimal import Decimal as D

from features.macro_state.engine import calculate
from features.macro_state.inputs import Inputs
from features.macro_state.rules import growth_direction
from features.macro_state.rules import shift_months
from .test_inputs import row


def test_parameters_and_diagnostic_mode_are_part_of_reproducible_identity():
    at='2026-01-31T23:59:59Z'
    a=calculate('US','growth',[],at)
    b=calculate('US','growth',[],at,theta_c=D('.10'))
    c=calculate('US','growth',[],at,diagnostic=True)
    assert len({r['inputFingerprint'] for r in (a,b,c)})==3


def test_unemployment_direction_compares_exact_sums():
    values=[('2026-05-01','9.9'),('2026-04-01','10'),('2026-03-01','10'),
            ('2026-02-01','10'),('2026-01-01','10.1'),('2025-12-01','10.1')]
    b=Inputs([row('UNRATE',p,v) for p,v in values],'2026-06-30T23:59:59Z')
    delta=b.sum_months('UNRATE','2026-02-01',3)-b.sum_months('UNRATE','2026-05-01',3)
    assert delta==D('.3')
    assert growth_direction([D(0),D(2),delta],unemployment_sum=True)=='flat'


def test_auxiliary_cpi_conflict_lowers_confidence_without_overriding_level():
    rows=[row('PCEPILFE',p,v) for p,v in [('2025-12-01','102'),('2024-12-01','100'),
            ('2025-09-01','102'),('2024-09-01','100')]]
    rows += [row('CPIAUCSL','2025-12-01','103',conflict=True),row('CPIAUCSL','2024-12-01','100')]
    out=calculate('US','inflation',rows,'2026-01-31T23:59:59Z')
    assert out['level']=='near_reference' and out['direction']=='flat'
    assert out['confidence']=='medium'


def spreads():
    return [row(key,(dt.date(2025,12,31)-dt.timedelta(days=i)).isoformat(),4 if key=='KR_CORP' else 3)
            for i in range(601) for key in ('KR_CORP','KR_GOV')]


def test_spread_missing_pair_is_not_dropped_from_rank_or_direction():
    rows=spreads();del rows[11]
    result=calculate('KR','stress_vulnerability',rows,'2026-01-01T00:00:00Z')
    assert result['level']==result['direction']=='unknown'


def test_spread_revision_uses_original_observation_set():
    rows=spreads();at='2026-01-01T00:00:00Z'
    first=calculate('KR','stress_vulnerability',rows,at)
    rows += [row('KR_CORP','2026-03-31','2',availableAt='2026-04-01T00:00:00Z'),
             row('KR_GOV','2026-03-31','3',availableAt='2026-04-01T00:00:00Z')]
    later=calculate('KR','stress_vulnerability',rows,at,selection=first['observationSelection'],selection_cutoff='2026-04-01T00:00:00Z')
    assert first==later


def test_spread_units_cannot_be_subtracted_without_compatibility():
    rows=spreads()
    for r in rows:
        if r['seriesId']=='KR_GOV':
            r['rawValue']='300';r['metadata']={**r['metadata'],'unit':'basis points'}
    out=calculate('KR','stress_vulnerability',rows,'2026-01-01T00:00:00Z')
    assert out['level']==out['direction']=='unknown'
    assert any(g['reason']=='spreadMetadataMismatch' for g in out['unknownReason'])


def test_inclusive_growth_level_conflict_lowers_confidence():
    rows=[]
    for i in range(70):
        p=shift_months('2026-05-01',-i)
        rows.extend([row('UNRATE',p,4),row('INDPRO',p,100)])
    rows += [row('GDPC1',shift_months('2026-01-01',-3*i),'100.25' if i==0 else '100') for i in range(17)]
    out=calculate('US','growth',rows,'2026-07-01T04:59:59.999999Z')
    assert out['level']=='moderate' and out['confidence']=='low'
    assert any(c['kind']=='growthLevelDisagreement' for c in out['conflicts'])


def test_fx_integrity_conflict_and_missing_spread_provenance():
    rows=[row('KR_RATE','2026-06-30','4'),row('KR_RATE','2026-03-30','4'),
          row('KR_CPI','2026-05-01','102'),row('KR_CPI','2025-05-01','100'),
          row('KR_USDKRW','2026-06-30','1400',conflict=True),row('KR_USDKRW','2026-03-30','1400')]
    out=calculate('KR','financial_conditions',rows,'2026-06-30T14:59:59.999999Z')
    assert out['level']=='tight' and out['direction']=='flat' and out['confidence']=='medium'
    missing=calculate('KR','stress_vulnerability',[],'2026-06-30T14:59:59.999999Z')
    assert {'KR_CORP','KR_GOV'}<={g['seriesId'] for g in missing['unknownReason']}
