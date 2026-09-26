"""Replace only identified legacy CPI/PPI rows, with recoverable evidence and atomicity."""
import datetime as dt
import json
import sqlite3
from pathlib import Path

from features.common.macro_data.store import backup_database
from .adapters.bok import BOK_RELEASES,release_date
from .schema import normalize_event


def replacement_pairs(conn,events):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='market_calendar_events'").fetchone():return []
    columns={row[1] for row in conn.execute('PRAGMA table_info(market_calendar_events)')}
    if not {'observed_at','actual_value','unit','parser_version'}<=columns:return []
    replacements={}
    for event in events:
        try:row=normalize_event(event)
        except (TypeError,ValueError):continue
        if row['provider']=='bok' and row['kind']=='macro' and row['allDay'] and row['actualValue'] and row['status']=='estimated':
            replacements[(row['title'],row['observedAt'])]=row
    allowed={v[0]:v[-1] for v in BOK_RELEASES.values()}
    result=[]
    for old in conn.execute("SELECT * FROM market_calendar_events WHERE provider='bok' AND all_day=0"):
        old=dict(old);title=old['title'];observed=old['observed_at']
        replacement=replacements.get((title,observed))
        if not replacement or title not in allowed or old['parser_version']!='0.4.0' or old['kind']!='macro' or old['market']!='KR' or old['timezone']!='Asia/Seoul':continue
        try:month=dt.datetime.strptime(observed,'%Y%m').date()
        except ValueError:continue
        legacy_start=month.replace(day=15).isoformat()+'T08:00:00+09:00'
        expected=normalize_event({'kind':'macro','provider':'bok','title':title,'startsAt':legacy_start,'timezone':'Asia/Seoul'})['id']
        if old['starts_at']!=legacy_start or old['id']!=expected:continue
        if replacement['startsAt']!=release_date(month,allowed[title]).isoformat():continue
        if old['actual_value']!=replacement['actualValue'] or old['unit']!=replacement['unit']:continue
        result.append((old,replacement))
    return result


def store_calendar_refresh(path:Path,events):
    from .service import upsert_events,ensure_calendar_table
    path=Path(path).resolve();path.parent.mkdir(parents=True,exist_ok=True)
    backup=None;candidates=[]
    if path.exists():
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
            conn.row_factory=sqlite3.Row
            candidates=replacement_pairs(conn,events)
        if candidates:backup=backup_database(path,'before-calendar-repair')
    with sqlite3.connect(path,timeout=30) as conn:
        conn.row_factory=sqlite3.Row;conn.execute('BEGIN IMMEDIATE');ensure_calendar_table(conn)
        count=upsert_events(path,events,connection=conn)
        covered={old['id']:old for old,_ in candidates}
        pairs=[(old,new) for old,new in replacement_pairs(conn,events) if covered.get(old['id'])==old] if backup else []
        if pairs:
            conn.execute('CREATE TABLE IF NOT EXISTS market_calendar_repairs(old_id TEXT PRIMARY KEY,replacement_id TEXT NOT NULL,old_row_json TEXT NOT NULL,backup_name TEXT NOT NULL,repaired_at TEXT NOT NULL)')
        for old,new in pairs:
            saved=conn.execute('SELECT actual_value,observed_at,unit FROM market_calendar_events WHERE id=?',(new['id'],)).fetchone()
            if not saved or tuple(saved)!=(new['actualValue'],new['observedAt'],new['unit']):raise RuntimeError('calendar_replacement_not_saved')
            conn.execute('INSERT INTO market_calendar_repairs VALUES(?,?,?,?,?)',(old['id'],new['id'],json.dumps(old,ensure_ascii=False),backup.name,dt.datetime.now(dt.timezone.utc).isoformat()))
            conn.execute('DELETE FROM market_calendar_events WHERE id=?',(old['id'],))
    return count,len(pairs)
