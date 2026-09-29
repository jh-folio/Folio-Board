"""Pure macro state calculation. Callers select the vintage; this module rejects leakage."""
import datetime as dt
from decimal import Decimal as D

from features.common.macro_data.registry import AXES,series
from features.common.macro_data.transforms import compatible
from .inputs import Inputs
from .rules import (shift_months,direction,inflation_level,financial_level,financial_direction,
                    stress_level,growth_level,growth_direction,contraction,confidence)
from .cycle import common_month,growth_components,us_cycle,kr_cycle


def _delta(a,b):
    return None if a is None or b is None else a-b


def _daily_change(book,key,*,ratio=False):
    latest=book.latest(key)
    if latest is None:book.gap(key,None,'missingObservation')
    return book.change(key,latest,shift_months(latest,-3),ratio=ratio) if latest else None


def _weekly_change(book,key):
    latest=book.latest(key)
    if latest is None:book.gap(key,None,'missingObservation')
    return book.change(key,latest,(dt.date.fromisoformat(latest)-dt.timedelta(days=28)).isoformat()) if latest else None


def _growth(book,market):
    gdp,ip,unrate=('GDPC1','INDPRO','UNRATE') if market=='US' else ('KR_GDP','KR_IP','KR_UNRATE')
    month=common_month(book,market)
    values=growth_components(book,month,market)
    # Freeze both branches' periods before a later vintage can change contraction.
    trends=(book.trend(gdp,values['quarter'],3,12) if values['quarter'] else None,
            book.trend(ip,month,12,36) if month else None)
    level=growth_level(values['gdp'],values['ip'],values['sahm'],*trends)
    gd=book.latest(gdp);im=book.latest(ip);um=book.latest(unrate)
    deltas=[_delta(book.growth(gdp,gd,3),book.growth(gdp,shift_months(gd,-3),3)) if gd else None,
            _delta(book.growth(ip,im,12),book.growth(ip,shift_months(im,-3),12)) if im else None,
            _delta(book.sum_months(unrate,shift_months(um,-3),3),book.sum_months(unrate,um,3)) if um else None]
    signals=[direction(v,t) for v,t in zip(deltas,(D('.25'),D('.5'),D('.3')))]
    conflicts=[]
    if len(set(signals)-{'unknown'})>1:
        conflicts.append({'kind':'growthDirectionDisagreement','signals':dict(zip((gdp,ip,unrate),signals))})
    if all(t is not None for t in trends) and values['gdp'] is not None and values['ip'] is not None:
        sides=['strong' if value>=threshold else 'weak' if value < -threshold else 'moderate'
               for value,threshold in ((values['gdp']-trends[0],D('.25')),(values['ip']-trends[1],D(1)))]
        if len(set(sides))>1:conflicts.append({'kind':'growthLevelDisagreement','signals':dict(zip((gdp,ip),sides))})
    missing=any(values[k] is None for k in ('gdp','ip','sahm')) or any(v is None for v in deltas)
    return level,growth_direction(deltas,unemployment_sum=True),[gdp,ip,unrate],conflicts,missing,False


def _inflation(book,market):
    key='PCEPILFE' if market=='US' else 'KR_CPI'
    month=book.latest(key)
    current=book.growth(key,month,12)
    previous=book.growth(key,shift_months(month,-3),12) if month else None
    level=inflation_level(market,month,current)
    if level=='unknown' and current is not None:
        book.gap(key,month,'referenceNotApplicable' if market=='US' else 'targetIndexMismatch')
    conflicts=[]
    if market=='US':
        cp=book.latest('CPIAUCSL');cv=book.growth('CPIAUCSL',cp,12)
        cl=inflation_level('US',cp,cv)
        if cl!='unknown' and level!='unknown' and cl!=level:
            conflicts.append({'kind':'auxiliaryInflationDisagreement','signals':{key:level,'CPIAUCSL':cl}})
        if any(g['seriesId']=='CPIAUCSL' and g['reason']=='integrityConflict' for g in book.gaps()):
            conflicts.append({'kind':'auxiliaryIntegrityConflict','seriesId':'CPIAUCSL'})
    return level,direction(_delta(current,previous),D('.3')),[key],conflicts,current is None or previous is None,bool(conflicts)


def _finance(book,market):
    conflicts=[]
    if market=='US':
        value=book.value('NFCI',book.latest('NFCI'))
        rate,nfci=_daily_change(book,'DFF'),_weekly_change(book,'NFCI')
        signals={'DFF':direction(rate,D('.25'),inclusive=True),'NFCI':direction(nfci,D('.1'))}
        if 'unknown' not in signals.values() and len(set(signals.values()))>1:
            conflicts.append({'kind':'financialDirectionDisagreement','signals':signals})
        return financial_level(market,value),financial_direction(rate,nfci),['NFCI','DFF'],conflicts,any(v is None for v in (value,rate,nfci)),False
    rate=book.value('KR_RATE',book.latest('KR_RATE'))
    inflation=book.growth('KR_CPI',book.latest('KR_CPI'),12)
    change=_daily_change(book,'KR_RATE');fx=_daily_change(book,'KR_USDKRW',ratio=True)
    if fx is not None and abs(fx)>=5:
        conflicts.append({'kind':'fxContext','seriesId':'KR_USDKRW','changePercent':str(fx)})
    if any(g['seriesId']=='KR_USDKRW' and g['reason']=='integrityConflict' for g in book.gaps()):
        conflicts.append({'kind':'auxiliaryIntegrityConflict','seriesId':'KR_USDKRW'})
    return financial_level(market,_delta(rate,inflation)),direction(change,D('.25'),inclusive=True),['KR_RATE','KR_CPI'],conflicts,any(v is None for v in (rate,inflation,change)),bool(conflicts)


def _spread(book,p):
    left,right=book.value('KR_CORP',p),book.value('KR_GOV',p)
    a,b=book.rows.get(('KR_CORP',p)),book.rows.get(('KR_GOV',p))
    if a and b and not compatible(a['metadata'],b['metadata']):
        book.gap('KR_CORP',p,'spreadMetadataMismatch');book.gap('KR_GOV',p,'spreadMetadataMismatch')
        return None
    return _delta(left,right)


def _stress(book,market):
    if market=='US':
        current=book.value('STLFSI4',book.latest('STLFSI4'))
        change=_weekly_change(book,'STLFSI4')
        return stress_level(current),direction(change,D('.25')),['STLFSI4'],[],current is None or change is None,False
    periods=book.choose('spreadPeriods',sorted(set(book.periods('KR_CORP'))|set(book.periods('KR_GOV'))))
    if not periods:
        book.gap('KR_CORP',None,'missingObservation');book.gap('KR_GOV',None,'missingObservation')
        return 'unknown','unknown',['KR_CORP','KR_GOV'],[],True,False
    latest=periods[-1];current=_spread(book,latest)
    start=shift_months(book.as_of[:10],-60)
    window=[_spread(book,p) for p in periods if start<=p<=book.as_of[:10]]
    complete=[v for v in window if v is not None]
    level='unknown'
    if current is not None and len(complete)>=600 and len(complete)==len(window):
        rank=D(sum(v<=current for v in complete))*100/len(complete)
        level='high' if rank>=90 else 'elevated' if rank>=70 else 'normal'
    else:book.gap('KR_CORP',latest,'spreadWindowIncomplete')
    recent=[_spread(book,p) for p in periods[-21:]]
    change=_delta(current,recent[0]) if len(recent)==21 and all(v is not None for v in recent) else None
    return level,direction(change,D('.1')),['KR_CORP','KR_GOV'],[],current is None or change is None or len(window)!=len(complete),False


def calculate(market,axis,rows,as_of,*,facts=(),theta_c=D('.20'),theta_r=D('.15'),diagnostic=False,
              selection=None,selection_cutoff=None,basis=None):
    if market not in {'US','KR'} or axis not in AXES:raise ValueError('invalid_macro_axis')
    if basis is None:basis='as_of_replay' if market=='US' else 'local_observed'
    if basis not in {'as_of_replay','local_observed','current_revised'} or (basis=='current_revised' and market!='KR'):
        raise ValueError('invalid_macro_basis')
    if selection_cutoff and selection is None and basis!='current_revised':raise ValueError('revision_requires_frozen_selection')
    book=Inputs(rows,as_of,facts,selection=selection,selection_cutoff=selection_cutoff)
    level,trend,required,conflicts,missing,aux=({'growth':_growth,'inflation':_inflation,
        'financial_conditions':_finance,'stress_vulnerability':_stress}[axis])(book,market)
    freshnesses=[book.freshness(key) for key in required]
    stale=freshnesses.count('stale')
    result={'market':market,'axis':axis,'asOf':book.as_of,'level':level,'direction':trend,
            'confidence':confidence(level,trend,stale,len(required),missing,bool(conflicts) and not aux,aux),
            'freshness':'stale' if stale else 'unknown' if 'unknown' in freshnesses else 'current',
            'horizon':'quarterly' if axis=='growth' else 'monthly' if axis=='inflation' else 'fast',
            'evidenceStage':sorted({series(k).stage for k in required}),
            'conflicts':conflicts,'sourceRefs':book.refs(),'unknownReason':book.gaps(),
            'nextCheckpoints':[],'basis':basis,
            'methodVersion':'macro-state-1','promotion':'shadow'}
    if axis=='growth':
        cycle_book=Inputs(rows,as_of,facts,selection=selection,selection_cutoff=selection_cutoff)
        result.update(us_cycle(cycle_book,theta_c=theta_c,theta_r=theta_r,diagnostic=diagnostic) if market=='US' else kr_cycle(cycle_book))
        book.used.update(cycle_book.used);book.used_facts.update(cycle_book.used_facts);book.unknown.update(cycle_book.unknown)
        book.selection.update(cycle_book.selection)
        # Official non-publication facts also belong in the growth axis provenance.
        result['sourceRefs']=book.refs()
    if axis=='stress_vulnerability':
        structural={'status':'not_available','yearOverYear':None,'previousYearOverYear':None}
        if market=='KR':
            quarter=book.latest('KR_CREDIT')
            current=book.growth('KR_CREDIT',quarter,12)
            previous=book.growth('KR_CREDIT',shift_months(quarter,-3),12) if quarter else None
            structural={'status':'available' if current is not None else 'unknown','period':quarter,
                        'yearOverYear':str(current) if current is not None else None,
                        'previousYearOverYear':str(previous) if previous is not None else None,
                        'changePercentagePoints':str(current-previous) if current is not None and previous is not None else None,
                        'freshness':book.freshness('KR_CREDIT')}
            result['sourceRefs']=book.refs()
        result['structuralVulnerability']=structural
    parameters={'basis':basis,'diagnosticOnly':diagnostic}
    if axis=='growth':parameters.update(thetaC=str(theta_c),thetaR=str(theta_r))
    result['ruleParameters']=parameters
    result['inputFingerprint']=book.fingerprint(market,axis,parameters=parameters)
    result['observationSelection']=book.selection
    if diagnostic:result['diagnosticOnly']=True
    return result
