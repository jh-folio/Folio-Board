"""Memoryless monthly cycle conditions from one selected vintage."""
import datetime as dt
from decimal import Decimal as D

from features.common.macro_data.registry import series
from features.common.macro_data.schema import day_end
from .inputs import month_end, utc
from .rules import shift_months, contraction, kleene_and, kleene_exists, cycle_choice, corroboration


def common_month(book, market='US'):
    keys=('UNRATE','INDPRO') if market=='US' else ('KR_UNRATE','KR_IP')
    shared=set(book.periods(keys[0],valid=True)) & set(book.periods(keys[1],valid=True))
    return book.choose('commonMonth:'+market,max(shared) if shared else None)


def quarter_at(book,key,month):
    if month is None:return None
    eligible=[q for q in book.periods(key) if month_end(shift_months(q,2))<=month_end(month)]
    return book.choose('quarter:'+key+':'+month,max(eligible) if eligible else None)


def growth_components(book, month, market='US'):
    gdp,ip,unrate=('GDPC1','INDPRO','UNRATE') if market=='US' else ('KR_GDP','KR_IP','KR_UNRATE')
    q=quarter_at(book,gdp,month)
    return {'quarter':q,'gdp':book.growth(gdp,q,3),'ip':book.growth(ip,month,12),
            'sahm':book.sahm(unrate,month)}


def contracted_at(book,month,market='US'):
    values=growth_components(book,month,market)
    return contraction(values['gdp'],values['ip'],values['sahm'])


def diagnostic_available_at(week):
    observed=dt.date.fromisoformat(week)
    if observed.weekday()!=5:
        raise ValueError('icsa_week_must_end_saturday')
    return utc(day_end((observed+dt.timedelta(days=5)).isoformat(),'America/Chicago'))


def claims(book):
    latest=book.latest('ICSA')
    if latest is None:
        book.gap('ICSA',None,'claimsWindowIncomplete')
        return dict(current=None,minimum=None,maximum=None,before13=None)
    end=dt.date.fromisoformat(latest)
    raw=book.values('ICSA',[(end-dt.timedelta(weeks=i)).isoformat() for i in range(56)])
    # Retain the latest/13-week comparison even when a different part of the 52-week window is missing.
    def average_at(offset):
        values=book.values('ICSA',[(end-dt.timedelta(weeks=offset+i)).isoformat() for i in range(4)])
        return sum(values)/4 if values is not None else None
    prior=[sum(raw[i:i+4])/4 for i in range(1,53)] if raw is not None else None
    if prior is None:book.gap('ICSA',latest,'claimsWindowIncomplete')
    return {'current':average_at(0),'minimum':min(prior) if prior else None,
            'maximum':max(prior) if prior else None,'before13':average_at(13)}


def compare(a,b,operator):
    return None if a is None or b is None else operator(a,b)


def _result(book,conditions,condition_inputs,*,unavailable=False):
    stale=[condition for condition,keys in condition_inputs.items() if any(book.freshness(k)=='stale' for k in keys)]
    signal,quality,relevant=cycle_choice(conditions,stale)
    if unavailable:
        signal,quality,relevant='unknown','low',list(conditions)
        book.gap('ICSA',None,'asOfVintageUnavailable')
    keys=set(k for condition in relevant for k in condition_inputs[condition])
    freshnesses=[book.freshness(k) for k in keys]
    freshness='stale' if 'stale' in freshnesses else 'current' if freshnesses and all(f=='current' for f in freshnesses) else 'unknown'
    return signal,quality,freshness


def us_cycle(book, *, theta_c=D('.20'),theta_r=D('.15'),diagnostic=False):
    month=common_month(book)
    current=growth_components(book,month)
    k=contraction(current['gdp'],current['ip'],current['sahm'])
    past=[contracted_at(book,shift_months(month,-i)) for i in range(1,13)] if month else [None]*12
    c=claims(book)
    w=kleene_and(compare(c['current'],None if c['minimum'] is None else (1+theta_c)*c['minimum'],lambda a,b:a>=b),
                 compare(c['current'],c['before13'],lambda a,b:a>b))
    r=kleene_and(kleene_exists(past),compare(c['current'],None if c['maximum'] is None else (1-theta_r)*c['maximum'],lambda a,b:a<=b))
    ip_delta=book.change('INDPRO',month,shift_months(month,-3)) if month else None
    q=kleene_and(r,compare(current['gdp'],D(0),lambda a,b:a>b),compare(ip_delta,D(0),lambda a,b:a>b))
    conditions={'W':w,'K':k,'R':r,'Q':q}
    base=['GDPC1','INDPRO','UNRATE']
    inputs={'W':['ICSA'],'K':base,'R':base+['ICSA'],'Q':base+['ICSA']}
    unavailable=not diagnostic and book.as_of<utc(day_end('2009-05-28','America/Chicago'))
    signal,quality,freshness=_result(book,conditions,inputs,unavailable=unavailable)
    cfnai='not_available'
    if book.as_of>=utc('2011-06-01T00:00:00-05:00'):
        latest=book.latest('CFNAIMA3')
        now=book.value('CFNAIMA3',latest)
        past_cfnai=book.values('CFNAIMA3',[shift_months(latest,-i) for i in range(12)]) if latest else []
        cfnai=corroboration(signal,now,past_cfnai if past_cfnai is not None else [None],stale=book.freshness('CFNAIMA3')!='current')
    return {'cycleSignal':signal,'cycleSignalPromotion':'shadow','cycleSignalBasis':{
        'conditions':conditions,'confidence':quality,'freshness':freshness,'unknownReason':book.gaps(),
        'sourceRefs':book.refs(),'evidenceStage':sorted({series(r['seriesId']).stage for r in book.refs()}),
        'cycleCorroboration':cfnai}}


def kr_cycle(book):
    shared=set(book.periods('KR_LEADING',valid=True)) & set(book.periods('KR_COINCIDENT',valid=True))
    month=book.choose('krCycleMonth',max(shared) if shared else None)
    def streak(key,m,up):
        if not m:return None
        values=book.values(key,[shift_months(m,-i) for i in range(4)])
        if values is None:return None
        return all((a>b if up else a<b) for a,b in zip(values,values[1:]))
    w=streak('KR_LEADING',month,False);k=streak('KR_COINCIDENT',month,False)
    past=[streak('KR_COINCIDENT',shift_months(month,-i),False) for i in range(1,13)] if month else [None]*12
    r=kleene_and(kleene_exists(past),streak('KR_LEADING',month,True))
    q=kleene_and(r,streak('KR_COINCIDENT',month,True))
    conditions={'W':w,'K':k,'R':r,'Q':q}
    inputs={'W':['KR_LEADING'],'K':['KR_COINCIDENT'],'R':['KR_LEADING','KR_COINCIDENT'],'Q':['KR_LEADING','KR_COINCIDENT']}
    signal,quality,freshness=_result(book,conditions,inputs)
    return {'cycleSignal':signal,'cycleSignalPromotion':'shadow','cycleSignalBasis':{
        'conditions':conditions,'confidence':quality,'freshness':freshness,'unknownReason':book.gaps(),
        'sourceRefs':book.refs(),'evidenceStage':['coincident','leading'],'cycleCorroboration':'not_available'}}
