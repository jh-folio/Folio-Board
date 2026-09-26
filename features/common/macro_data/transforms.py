"""Transforms use only observations selected at the same cutoff."""
import datetime as dt
from .schema import digest


def shifted(period,months):
    date=dt.date.fromisoformat(period)
    total=date.year*12+date.month-1-months
    return dt.date(total//12,total%12+1,1).isoformat()


def compatible(a,b):
    return all(a.get(k)==b.get(k) for k in ('unit','frequency','adjustment','definitionVersion'))


def transform(points,spec):
    by_period={p['period']:p for p in points}
    result=[];previous=None
    for p in points:
        raw=p['value'];kind=spec['transform'];base=None;reason=None
        if kind in {'yoy','mom','qoq'}:
            base=by_period.get(shifted(p['period'],12 if kind=='yoy' else 3 if kind=='qoq' else 1))
        elif kind=='difference':base=previous
        value=raw
        if kind in {'yoy','mom','qoq','difference'}:
            value=None
            if raw is None or base is None or base['value'] is None:reason='comparison_missing'
            elif not compatible(p['metadata'],base['metadata']):reason='method_changed'
            elif kind=='difference':value=raw-base['value']
            elif base['value']==0:reason='zero_denominator'
            else:value=(raw/base['value']-1)*100
        unit=('%p' if kind=='difference' else '%') if kind in {'yoy','mom','qoq','difference'} else p['metadata']['unit']
        result.append({**p,'displayValue':value,'displayUnit':unit,'transform':kind,'calculationGap':reason})
        previous=p
    return result


def spread(corporate,government):
    corp={p['period']:p for p in corporate};gov={p['period']:p for p in government};result=[]
    for period in sorted(corp.keys()|gov.keys()):
        left=corp.get(period);right=gov.get(period);present=[p for p in (left,right) if p]
        p=present[0]
        valid=left and right and left['value'] is not None and right['value'] is not None and compatible(left['metadata'],right['metadata'])
        value=left['value']-right['value'] if valid else None
        metadata={**p['metadata'],'unit':'%p','definitionVersion':digest([v['metadata'] for v in present])}
        result.append({**p,'seriesId':'KR_SPREAD','value':value,'rawValue':str(value) if value is not None else None,
                       'metadata':metadata,'metadataId':digest(metadata),
                       'displayValue':value,'displayUnit':'%p','transform':'spread',
                       'calculationGap':None if valid else 'comparison_missing','inputs':[left,right],
                       'revised':any(v.get('revised') for v in present),'conflict':any(v.get('conflict') for v in present),
                       'fetchedAt':max(v['fetchedAt'] for v in present),
                       'firstSeenAt':max(v.get('firstSeenAt') or v['fetchedAt'] for v in present),
                       'availableAt':max(v['availableAt'] for v in present)})
    return result
