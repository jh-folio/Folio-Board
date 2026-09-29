import datetime as dt

from features.macro_state.inputs import Inputs
from features.macro_state.cycle import claims, kr_cycle, us_cycle, diagnostic_available_at
from .test_inputs import row


def test_claims_require_every_week_and_not_current_in_minimum():
    end=dt.date(2025,12,27)
    rows=[row('ICSA',(end-dt.timedelta(weeks=i)).isoformat(),100 if i else 200) for i in range(56)]
    b=Inputs(rows,'2026-01-31T23:59:59Z')
    values=claims(b)
    assert values['current']==125 and values['minimum']==100
    assert values['maximum']==100 and values['before13']==100
    del rows[30]
    assert claims(Inputs(rows,b.as_of))['minimum'] is None


def test_no_vintage_forces_unknown_even_if_other_conditions_exist():
    result=us_cycle(Inputs([],'2008-12-31T23:59:59Z'))
    assert result['cycleSignal']=='unknown'
    assert any(r['reason']=='asOfVintageUnavailable' for r in result['cycleSignalBasis']['unknownReason'])


def test_kr_three_changes_and_zero_breaks_streak():
    rows=[row(k,f'2025-{m:02}-01',100-m) for k in ('KR_LEADING','KR_COINCIDENT') for m in range(1,13)]
    result=kr_cycle(Inputs(rows,'2026-01-31T23:59:59Z'))
    assert result['cycleSignalBasis']['conditions']['K'] is True
    assert result['cycleSignal']=='contraction_confirmed'
    rows[-1]['rawValue']=rows[-2]['rawValue']
    assert kr_cycle(Inputs(rows,'2026-01-31T23:59:59Z'))['cycleSignalBasis']['conditions']['K'] is False


def test_diagnostic_week_saturday_to_next_thursday():
    assert diagnostic_available_at('2001-03-03')=='2001-03-09T05:59:59.999999Z'
    assert diagnostic_available_at('2001-07-07')=='2001-07-13T04:59:59.999999Z'
