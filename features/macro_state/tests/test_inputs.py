import copy
from decimal import Decimal as D

import pytest

from features.macro_state.inputs import Inputs, month_end, utc


def row(series, period, value, **extra):
    return {'seriesId':series,'period':period,'rawValue':str(value) if value is not None else None,
            'value':float(value) if value is not None else None,'id':period,
            'availableAt':'2026-01-01T00:00:00Z','vintageDate':'2025-12-31',
            'metadataId':'v1','metadata':{'unit':'Percent','frequency':'M','adjustment':'SA','definitionVersion':'v1'},
            'availabilityBasis':'provider_vintage','conflict':False,**extra}


def test_exact_dates_metadata_and_cutoff():
    rows=[row('UNRATE','2025-01-01','4'),row('UNRATE','2025-04-01','4.5')]
    book=Inputs(rows,'2026-01-31T23:59:59Z')
    assert book.change('UNRATE','2025-04-01','2025-01-01') == D('.5')
    assert book.change('UNRATE','2025-04-01','2025-02-01') is None
    assert any(g['reason']=='missingObservation' for g in book.gaps())
    broken=copy.deepcopy(rows);broken[1]['metadata']['unit']='different'
    assert Inputs(broken,book.as_of).change('UNRATE','2025-04-01','2025-01-01') is None
    with pytest.raises(ValueError,match='future_input'):
        Inputs(rows,'2025-12-31T23:59:59Z')


def test_sahm_decimal_boundary_and_official_month_skip():
    rows=[row('UNRATE',f'2025-{m:02}-01','4') for m in range(1,13)]
    rows += [row('UNRATE',f'2024-{m:02}-01','4') for m in range(9,13)]
    rows[-1]['rawValue']='4'
    for r in rows:
        if r['period'] >= '2025-10-01': r['rawValue']='4.5'
    book=Inputs(rows,'2026-01-31T23:59:59Z')
    assert book.sahm('UNRATE','2025-12-01') is True
    rows[9]['rawValue']=None;rows[9]['value']=None
    assert Inputs(rows,book.as_of).sahm('UNRATE','2025-12-01') is None
    fact={'rowKind':'fact','seriesId':'UNRATE','observationMonth':'2025-10','sourceUrl':'https://www.bls.gov/example',
          'availableAt':'2025-12-17T05:59:59.999999Z','recordedAt':'2026-09-29T00:00:00Z'}
    b=Inputs(rows,book.as_of,[fact]);assert b.sahm('UNRATE','2025-12-01') is False
    assert len(b.used_facts)==1
    assert b.sahm('UNRATE','2025-10-01') is None
    assert b.average('UNRATE','2025-12-01',3) is None  # direction does not skip


def test_fingerprint_stable_excludes_recorded_at_and_includes_missing():
    rows=[row('UNRATE','2025-01-01','4')]
    a=Inputs(rows,'2026-01-31T23:59:59Z');a.value('UNRATE','2025-01-01')
    b=Inputs(rows,a.as_of);b.value('UNRATE','2025-01-01')
    assert a.fingerprint('US','growth') == b.fingerprint('US','growth')
    b.value('UNRATE','2025-02-01')
    assert a.fingerprint('US','growth') != b.fingerprint('US','growth')
    assert utc('2026-02-01T08:59:59+09:00') == '2026-01-31T23:59:59.000000Z'
    assert month_end('2024-02-01') == '2024-02-29'


def test_trend_minimum_coverage_and_consecutive_gaps():
    rows=[row('INDPRO',f'{year}-{m:02}-01',100 + (year-2020)*12+m) for year in range(2020,2025) for m in range(1,13)]
    b=Inputs(rows,'2026-01-31T23:59:59Z')
    assert b.trend('INDPRO','2024-12-01',12,36) is not None
    assert b.trend('INDPRO','2022-01-01',12,36) is None
    bad=[r for r in rows if r['period'] not in {'2023-04-01','2023-05-01','2023-06-01'}]
    assert Inputs(bad,b.as_of).trend('INDPRO','2024-12-01',12,36) is None
