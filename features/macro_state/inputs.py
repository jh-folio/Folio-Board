"""Pure as-of input access with exact windows, provenance and canonical fingerprint."""
from __future__ import annotations

import calendar
import datetime as dt
from decimal import Decimal as D
from statistics import median
from zoneinfo import ZoneInfo

from features.common.macro_data.registry import series
from features.common.macro_data.schema import digest
from features.common.macro_data.transforms import compatible
from .rules import shift_months


def utc(value):
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('macro_timestamp_requires_timezone')
    return parsed.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def month_end(day):
    d=dt.date.fromisoformat(day)
    return d.replace(day=calendar.monthrange(d.year,d.month)[1]).isoformat()


class Inputs:
    def __init__(self, rows, as_of, facts=(), *, selection=None, selection_cutoff=None):
        self.as_of=utc(as_of)
        self.selection_cutoff=utc(selection_cutoff or as_of)
        self.frozen_selection=selection
        self.selection={}
        self.rows={}
        for row in rows:
            if utc(row['availableAt']) > self.selection_cutoff:
                raise ValueError('future_input')
            key=(row['seriesId'],row['period'])
            if key in self.rows:
                raise ValueError('duplicate_selected_period')
            self.rows[key]=row
        self.facts={(f['seriesId'],f['observationMonth']+'-01'):f for f in facts if utc(f['availableAt'])<=self.as_of}
        self.used={}
        self.used_facts={}
        self.unknown=set()

    def choose(self,key,value):
        if self.frozen_selection is not None:
            if key not in self.frozen_selection:raise ValueError('unfrozen_observation_selection:'+key)
            value=self.frozen_selection[key]
        self.selection[key]=value
        return value

    def gap(self, key, period, reason):
        self.unknown.add((key,period or '',reason))

    def gaps(self):
        return [{'seriesId':k,'period':p,'reason':r} for k,p,r in sorted(self.unknown)]

    def periods(self,key,*,valid=False):
        return sorted(p for (k,p),r in self.rows.items() if k==key and
                      (not valid or (r['rawValue'] is not None and not r.get('conflict'))))

    def latest(self,key):
        periods=self.periods(key)
        return self.choose('latest:'+key,periods[-1] if periods else None)

    def value(self,key,period):
        r=self.rows.get((key,period))
        if r is None:
            self.gap(key,period,'missingObservation')
            return None
        self.used[(key,period)]=r
        if r.get('conflict') or r['rawValue'] is None:
            self.gap(key,period,'integrityConflict' if r.get('conflict') else 'missingValue')
            return None
        return D(r['rawValue'])

    def values(self,key,periods):
        values=[self.value(key,p) for p in periods]
        metadata=[self.rows[(key,p)]['metadata'] for p in periods if (key,p) in self.rows]
        if metadata and not all(compatible(metadata[0],m) for m in metadata[1:]):
            self.gap(key,periods[0],'methodChanged')
            return None
        return None if any(v is None for v in values) else values

    def change(self,key,now,before,*,ratio=False):
        values=self.values(key,[now,before])
        if values is None:
            return None
        a,b=values
        if ratio and b==0:
            self.gap(key,before,'zeroDenominator')
            return None
        return (a/b-1)*100 if ratio else a-b

    def growth(self,key,period,months):
        if period is None:
            self.gap(key,None,'missingObservation')
            return None
        return self.change(key,period,shift_months(period,-months),ratio=True)

    def average(self,key,period,n):
        if period is None:
            self.gap(key,None,'missingObservation')
            return None
        values=self.values(key,[shift_months(period,-i) for i in range(n)])
        return sum(values)/n if values is not None else None

    def sum_months(self,key,period,n):
        if period is None:return None
        values=self.values(key,[shift_months(period,-i) for i in range(n)])
        return sum(values) if values is not None else None

    def sahm(self,key,period,threshold=D('.5')):
        if period is None:
            self.gap(key,None,'missingObservation')
            return None
        chosen=[]
        cursor=period
        # Only explicit UNRATE facts expand the published-month windows.
        while len(chosen)<15:
            fact=self.facts.get((key,cursor)) if key=='UNRATE' else None
            if fact:
                self.used_facts[(key,cursor)]=fact
                if cursor==period:
                    self.gap(key,cursor,'officiallyNotPublished')
                    return None
            else:
                chosen.append(cursor)
            cursor=shift_months(cursor,-1)
        chosen=self.choose('sahm:'+key+':'+period,chosen)
        values=self.values(key,chosen)
        if values is None:
            return None
        # Compare sums, avoiding division/rounding exactly at 0.50 pp.
        return sum(values[:3])-min(sum(values[i:i+3]) for i in range(1,13)) >= 3*threshold

    def trend(self,key,period,transform_months,minimum):
        step=3 if series(key).frequency=='Q' else 1
        end=shift_months(period,-step)
        start=shift_months(end,-120)
        candidate=[p for p in self.periods(key) if start<=p<=end]
        transformed={p:self.growth(key,p,transform_months) for p in candidate}
        valid=[p for p in candidate if transformed[p] is not None]
        first=self.choose('trend:'+key+':'+period,valid[0] if valid else None)
        if len(valid)<minimum or first is None:
            self.gap(key,period,'trendUnavailable')
            return None
        cursor=first;count=0;missing=0;run=0;longest=0;values=[]
        while cursor<=end:
            count+=1
            value=transformed.get(cursor)
            if value is None:
                self.gap(key,cursor,'missingTrendObservation')
                missing+=1;run+=1;longest=max(longest,run)
            else:
                values.append(value);run=0
            cursor=shift_months(cursor,step)
        if len(values)<minimum or len(values)*10<count*9 or longest>2:
            self.gap(key,period,'trendUnavailable')
            return None
        return median(values)

    def freshness(self,key,period=None):
        used_periods=[p for k,p in self.used if k==key]
        period=period or (max(used_periods) if used_periods else None)
        if period is None or (key,period) not in self.rows:
            return 'unknown'
        spec=series(key);end=period
        if spec.frequency=='M':end=month_end(period)
        if spec.frequency=='Q':end=month_end(shift_months(period,2))
        local=dt.datetime.fromisoformat(self.as_of.replace('Z','+00:00')).astimezone(ZoneInfo(spec.timezone)).date()
        return 'stale' if (local-dt.date.fromisoformat(end)).days>spec.max_age_days else 'current'

    def refs(self):
        result=[]
        for (key,period),r in sorted(self.used.items()):
            result.append({'rowKind':'observation','seriesId':key,'period':period,'id':r['id'],
                           'value':r['rawValue'],'metadataId':r['metadataId'],'availabilityBasis':r['availabilityBasis'],
                           'availableAt':utc(r['availableAt']),'vintageDate':r.get('vintageDate'),
                           'firstSeenAt':utc(r['firstSeenAt']) if r.get('firstSeenAt') else None,
                           'conflict':bool(r.get('conflict'))})
            if r.get('diagnosticAvailability'):
                result[-1].update(diagnosticAvailability=True, actualSourceAvailableAt=utc(r['actualSourceAvailableAt']))
        for (key,period),f in sorted(self.used_facts.items()):
            result.append({'rowKind':'fact','seriesId':key,'period':period,'observationMonth':f['observationMonth'],
                           'availableAt':utc(f['availableAt']),'sourceUrl':f['sourceUrl']})
        return sorted(result,key=lambda r:(r['seriesId'],r['period'],r['availableAt'],str(r.get('id',''))))

    def fingerprint(self,market,axis,method='macro-state-1',parameters=None):
        return digest({'fingerprintVersion':'macro-input-1','market':market,'axis':axis,'asOf':self.as_of,
                       'methodVersion':method,'ruleParameters':parameters or {},'transformVersion':'macro-2','rows':self.refs(),'unknownReason':self.gaps()})
