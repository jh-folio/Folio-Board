"""Predeclared event and revision-stability counts; no promotion decisions."""
from .rules import shift_months

# Official NBER table rechecked 2026-09-29. Labels only, never calculation inputs.
NBER=[('2001-03','2001-11'),('2007-12','2009-06'),('2020-02','2020-04')]
NBER_SOURCE='https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions'


def month_shift(month,n):return shift_months(month+'-01',n)[:7]


def distance(a,b):
    return (int(b[:4])-int(a[:4]))*12+int(b[5:7])-int(a[5:7])


def episodes(points,active,bridge,*,evaluation_start='2000-08'):
    result=[];current=None;gap=0
    first_valid=next((m for m,s in points if s!='unknown'),None)
    def finish(immature):
        if current:
            current['immature']=immature
            result.append(current)
    for month,state in points:
        if state in active:
            if current is None:
                current={'start':month,'end':month,'months':[],'states':[],
                         'leftCensored':month==first_valid and month<evaluation_start,'prepStarted':month<evaluation_start}
            current['end']=month;current['months'].append(month);current['states'].append(state);gap=0
        elif current and state in bridge and gap==0:
            gap=1
        else:
            finish(False);current=None;gap=0
    finish(True)
    return result


def cycle_events(points):
    warnings=episodes(points,{'contraction_warning'},{'none','unknown'})
    recovery=episodes(points,{'recovery_signal','recovery_confirmed'},{'unknown'})
    for event in warnings:
        event['falseSignal']=not any(month_shift(p,-6)<=event['start']<=t for p,t in NBER)
    for event in recovery:
        event['falseSignal']=not any(month_shift(t,-3)<=event['start']<=month_shift(t,12) for _,t in NBER)
        event['firstConfirmation']=next((m for m,s in zip(event['months'],event['states']) if s=='recovery_confirmed'),None)
        event['downgrades']=sum(a=='recovery_confirmed' and b=='recovery_signal' for a,b in zip(event['states'],event['states'][1:]))
    return {'warnings':warnings,'recoveries':recovery}


def usable(event):return not(event['leftCensored'] or event['prepStarted'] or event['immature'])


def timeliness(events,kind,turning_points):
    result=[]
    for turning in turning_points:
        lo,hi=(-6,2) if kind=='warnings' else (-3,3)
        eligible=[e for e in events[kind] if usable(e) and month_shift(turning,lo)<=e['start']<=month_shift(turning,hi)]
        first=min(eligible,key=lambda e:e['start']) if eligible else None
        result.append({'turningPoint':turning,'eventStart':first['start'] if first else None,
                       'delayMonths':max(0,distance(turning,first['start'])) if first else None,
                       'earlyMonths':max(0,distance(first['start'],turning)) if first else None})
    return result


def false_contractions(points,*,confirmed='contraction'):
    # Entry into an allowed recession window breaks even an already-open false event.
    outside=[]
    for month,state in points:
        inside=any(month_shift(p,-3)<=month<=month_shift(t,3) for p,t in NBER)
        outside.append((month,'boundary' if inside else 'active' if state==confirmed else 'unknown' if state=='unknown' else 'inactive'))
    events=episodes(outside,{'active'},{'inactive'},evaluation_start=points[0][0] if points else '')
    counted=[e for e in events if confirmed!='contraction_confirmed' or not e['immature']]
    return {'months':sum(len(e['months']) for e in events),'events':len(counted),
            'immatureEvents':sum(e['immature'] for e in events),'details':events}


def stability(records,field):
    methods=('proposal','B0','B1')
    common=[];individual={}
    for method in methods:
        valid=[r for r in records if not r.get('immatureReference') and
               r[method].get(field,'unknown')!='unknown' and r[method+'Revised'].get(field,'unknown')!='unknown']
        individual[method]={'count':len(valid),'mismatches':sum(r[method][field]!=r[method+'Revised'][field] for r in valid),
                            'unknown':sum(r[method].get(field,'unknown')=='unknown' for r in records),
                            'unknownTransitions':sum((r[method].get(field,'unknown')=='unknown')!=(r[method+'Revised'].get(field,'unknown')=='unknown') for r in records if not r.get('immatureReference'))}
    for r in records:
        if not r.get('immatureReference') and all(r[m].get(field,'unknown')!='unknown' and r[m+'Revised'].get(field,'unknown')!='unknown' for m in methods):
            common.append(r)
    return {'scheduled':len(records),'immatureReference':sum(bool(r.get('immatureReference')) for r in records),'individual':individual,
            'commonCount':len(common),'commonMismatches':{m:sum(r[m][field]!=r[m+'Revised'][field] for r in common) for m in methods}}


def choose_threshold(candidates,default):
    eligible=[c for c in candidates if all(x['eventStart'] is not None for x in c['timeliness'])]
    if not eligible:return default,True
    best=min(eligible,key=lambda c:(c['falseEvents'],sum(x['delayMonths'] for x in c['timeliness']),abs(c['theta']-default),-c['theta']))
    return best['theta'],False
