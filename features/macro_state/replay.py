"""Read-only vintage selection. No evaluation or collection is triggered by construction."""
import bisect
import datetime as dt
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

from features.common.macro_data.schema import day_end
from .inputs import utc,month_end
from .rules import shift_months


def revision_cutoff(as_of,market='US',*,weekly=False):
    timezone='America/Chicago' if market=='US' else 'Asia/Seoul'
    local=dt.datetime.fromisoformat(utc(as_of).replace('Z','+00:00')).astimezone(ZoneInfo(timezone))
    target=shift_months(local.date().isoformat(),3)
    return utc(day_end(target if weekly else month_end(target),timezone))


def evaluation_cutoffs(start_month,end_month,market='US',*,weekly=False):
    timezone='America/Chicago' if market=='US' else 'Asia/Seoul'
    first=dt.date.fromisoformat(start_month+'-01')
    last=dt.date.fromisoformat(month_end(end_month+'-01'))
    if weekly:
        cursor=first+dt.timedelta(days=(4-first.weekday())%7)
        while cursor<=last:
            yield utc(day_end(cursor.isoformat(),timezone))
            cursor+=dt.timedelta(days=7)
    else:
        cursor=first.isoformat()
        while cursor<=last.isoformat():
            yield utc(day_end(month_end(cursor),timezone))
            cursor=shift_months(cursor,1)


class Replay:
    def __init__(self,path:Path,series_ids):
        self.history={}
        self.metadata={}
        self.facts=[]
        with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as conn:
            for id,body in conn.execute('SELECT id,body FROM macro_metadata'):
                self.metadata[id]=json.loads(body)
            for key in series_ids:
                for row in conn.execute('SELECT id,period,available_at,value,meta_id,basis,vintage,fetched_at FROM macro_observations WHERE series_id=? ORDER BY period,available_at,id',(key,)):
                    self.history.setdefault((key,row[1]),[]).append(row)
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='macro_publication_facts'").fetchone():
                self.facts=[json.loads(r[0]) for r in conn.execute('SELECT body FROM macro_publication_facts')]
        self.times={key:[utc(r[2]) for r in rows] for key,rows in self.history.items()}

    def select(self,cutoff,*,observation_end=None,allowed=None):
        cutoff=utc(cutoff);result=[]
        for (key,period),versions in self.history.items():
            if observation_end and period>observation_end:continue
            if allowed is not None and (key,period) not in allowed:continue
            dates=self.times[(key,period)]
            index=bisect.bisect_right(dates,cutoff)-1
            if index<0:continue
            id,_,available,value,meta,basis,vintage,fetched=versions[index]
            conflict=index>0 and dates[index-1]==dates[index]
            result.append({'seriesId':key,'period':period,'id':id,'availableAt':available,'rawValue':value,
                           'value':None if conflict or value is None else float(value),'metadataId':meta,
                           'metadata':self.metadata[meta],'availabilityBasis':basis,'vintageDate':vintage or None,
                           'fetchedAt':fetched,'firstSeenAt':versions[0][-1] if basis=='local_observed' else None,
                           'conflict':conflict})
        return result

    def facts_at(self,cutoff):
        return [f for f in self.facts if utc(f['availableAt'])<=utc(cutoff)]
