"""Predeclared single-series B1. B0 is evaluated from the previous scheduled input set."""
from decimal import Decimal as D

from .inputs import Inputs
from .rules import shift_months,direction,inflation_level,kleene_and,kleene_exists,contraction
from .cycle import common_month,growth_components,contracted_at,compare
from .engine import _weekly_change,_daily_change,_spread


def single_series(market,axis,rows,as_of,*,facts=(),selection=None,selection_cutoff=None):
    b=Inputs(rows,as_of,facts,selection=selection,selection_cutoff=selection_cutoff)
    level=trend='unknown';cycle=None
    if axis=='growth':
        key='GDPC1' if market=='US' else 'KR_GDP'
        q=b.latest(key);value=b.growth(key,q,3)
        prior=b.growth(key,shift_months(q,-3),3) if q else None
        central=b.trend(key,q,3,12) if q else None
        if value is not None:
            level=('contraction' if value<0 else 'unknown' if central is None else
                   'strong' if value>=central+D('.25') else 'weak' if value<central-D('.25') else 'moderate')
        trend=direction(value-prior if value is not None and prior is not None else None,D('.25'))
        if market=='US':
            m=common_month(b);c=growth_components(b,m)
            k=contraction(c['gdp'],c['ip'],c['sahm'])
            past=kleene_exists([contracted_at(b,shift_months(m,-i)) for i in range(1,13)]) if m else None
            delta=b.change('INDPRO',m,shift_months(m,-3)) if m else None
            qprime=kleene_and(past,compare(c['gdp'],D(0),lambda a,b:a>b),compare(delta,D(0),lambda a,b:a>b))
            cycle='recovery_confirmed' if qprime is True else 'contraction_confirmed' if k is True else 'none' if k is False and qprime is False else 'unknown'
    elif axis=='inflation':
        key='CPIAUCSL' if market=='US' else 'KR_CPI'
        m=b.latest(key);value=b.growth(key,m,12)
        before=b.growth(key,shift_months(m,-3),12) if m else None
        level=inflation_level(market,m,value)
        trend=direction(value-before if value is not None and before is not None else None,D('.3'))
    elif axis=='financial_conditions':
        if market=='US':
            value=b.value('NFCI',b.latest('NFCI'))
            level='unknown' if value is None else 'tight' if value>0 else 'loose' if value<0 else 'neutral'
            trend=direction(_weekly_change(b,'NFCI'),D(0))
        else:trend=direction(_daily_change(b,'KR_RATE'),D(0))
    elif axis=='stress_vulnerability':
        if market=='US':
            value=b.value('STLFSI4',b.latest('STLFSI4'))
            level='unknown' if value is None else 'elevated' if value>0 else 'normal'
            trend=direction(_weekly_change(b,'STLFSI4'),D(0))
        else:
            periods=b.choose('spreadPeriods',sorted(set(b.periods('KR_CORP'))|set(b.periods('KR_GOV'))))
            values=[_spread(b,p) for p in periods[-21:]]
            trend=direction(values[-1]-values[0] if len(values)==21 and all(v is not None for v in values) else None,D(0))
    result={'level':level,'direction':trend,'observationSelection':b.selection,'sourceRefs':b.refs(),'unknownReason':b.gaps()}
    if cycle is not None:result['cycleSignal']=cycle
    return result
