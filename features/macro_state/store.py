"""Append-only snapshots and separate user decisions in market-memory.sqlite3."""
import datetime as dt
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from features.common.macro_data.schema import canonical,digest
from features.common.macro_data.store import backup_database,_SCHEMA_LOCK
from .inputs import utc

LEVELS={'growth':{'contraction','weak','moderate','strong','unknown'},
        'inflation':{'high','above_reference','near_reference','below_reference','unknown'},
        'financial_conditions':{'tight','neutral','loose','unknown'},
        'stress_vulnerability':{'high','elevated','normal','unknown'}}
DDL=(
    'CREATE TABLE IF NOT EXISTS macro_state_schema(version INTEGER PRIMARY KEY)',
    '''CREATE TABLE IF NOT EXISTS macro_state_snapshots(
        seq INTEGER PRIMARY KEY,id TEXT NOT NULL UNIQUE,market TEXT NOT NULL,axis TEXT NOT NULL,
        as_of TEXT NOT NULL,method TEXT NOT NULL,fingerprint TEXT NOT NULL,body TEXT NOT NULL,
        created_at TEXT NOT NULL,UNIQUE(market,axis,as_of,method,fingerprint))''',
    'CREATE INDEX IF NOT EXISTS macro_state_lookup ON macro_state_snapshots(market,axis,as_of DESC,seq DESC)',
    '''CREATE TABLE IF NOT EXISTS macro_state_supersessions(
        old_id TEXT NOT NULL,new_id TEXT NOT NULL UNIQUE,reason TEXT NOT NULL,created_at TEXT NOT NULL,
        FOREIGN KEY(old_id) REFERENCES macro_state_snapshots(id),FOREIGN KEY(new_id) REFERENCES macro_state_snapshots(id))''',
    '''CREATE TABLE IF NOT EXISTS macro_state_decisions(
        seq INTEGER PRIMARY KEY,market TEXT NOT NULL,axis TEXT NOT NULL,method TEXT NOT NULL,
        field TEXT NOT NULL,promotion TEXT NOT NULL,evaluation_ref TEXT NOT NULL,created_at TEXT NOT NULL)''',
)


class StateStore:
    def __init__(self,path):
        self.path=Path(path).resolve()

    @contextmanager
    def read(self):
        if not self.path.exists():
            yield None;return
        with sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=30) as conn:
            conn.row_factory=sqlite3.Row
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='macro_state_schema'").fetchone():
                yield None
            else:yield conn

    def ensure(self):
        with _SCHEMA_LOCK:
            with self.read() as conn:
                if conn is not None:
                    version=conn.execute('SELECT MAX(version) FROM macro_state_schema').fetchone()[0]
                    if version and version>1:raise RuntimeError('macro_state_schema_newer_than_runtime')
                    if version==1:return
            self.path.parent.mkdir(parents=True,exist_ok=True)
            backup_database(self.path,'before-macro-state-v1')
            with sqlite3.connect(self.path,timeout=30) as conn:
                conn.execute('BEGIN IMMEDIATE')
                for statement in DDL:conn.execute(statement)
                for table in ('macro_state_snapshots','macro_state_supersessions','macro_state_decisions'):
                    for operation in ('UPDATE','DELETE'):
                        conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable_macro_state'); END")
                conn.execute('INSERT INTO macro_state_schema VALUES(1)')

    def save(self,result,*,reason):
        body=dict(result)
        if body.get('diagnosticOnly'):raise ValueError('diagnostic_snapshot_not_storable')
        market,axis=body.get('market'),body.get('axis')
        if market not in {'US','KR'} or axis not in LEVELS or body.get('level') not in LEVELS[axis]:
            raise ValueError('invalid_macro_state_enum')
        if body.get('direction') not in {'rising','falling','flat','mixed','unknown'}:raise ValueError('invalid_macro_state_enum')
        if body.get('confidence') not in {'high','medium','low'} or body.get('freshness') not in {'current','stale','unknown'}:
            raise ValueError('invalid_macro_state_enum')
        if axis=='growth':
            if body.get('cycleSignal') not in {'none','contraction_warning','contraction_confirmed','recovery_signal','recovery_confirmed','unknown'}:
                raise ValueError('invalid_macro_cycle_enum')
            cycle=body.get('cycleSignalBasis',{})
            if set(cycle.get('conditions',{}))!={'W','K','R','Q'} or any(v is not None and type(v) is not bool for v in cycle['conditions'].values()):
                raise ValueError('invalid_macro_cycle_conditions')
            if cycle.get('confidence') not in {'high','medium','low'} or cycle.get('freshness') not in {'current','stale','unknown'} or cycle.get('cycleCorroboration') not in {'agrees','strongly_agrees','disagrees','not_available'}:
                raise ValueError('invalid_macro_cycle_enum')
        if not re.fullmatch('[a-f0-9]{64}',body.get('inputFingerprint','')) or not body.get('methodVersion'):
            raise ValueError('invalid_macro_state_identity')
        if not isinstance(reason,str) or not reason.strip():raise ValueError('snapshot_reason_required')
        body['asOf']=utc(body['asOf'])
        body.pop('promotion',None);body.pop('cycleSignalPromotion',None)
        identity=(market,axis,body['asOf'],body['methodVersion'],body['inputFingerprint'])
        snapshot_id='macro-'+digest(identity)
        serialized=canonical(body)
        now=utc(dt.datetime.now(dt.timezone.utc).isoformat())
        self.ensure()
        with sqlite3.connect(self.path,timeout=30) as conn:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE')
            previous=conn.execute('SELECT body FROM macro_state_snapshots WHERE id=?',(snapshot_id,)).fetchone()
            if previous:
                if previous[0]!=serialized:raise ValueError('macro_snapshot_non_reproducible')
            else:
                old=conn.execute('SELECT id FROM macro_state_snapshots WHERE market=? AND axis=? AND as_of=? AND method=? ORDER BY seq DESC LIMIT 1',identity[:4]).fetchone()
                conn.execute('INSERT INTO macro_state_snapshots(id,market,axis,as_of,method,fingerprint,body,created_at) VALUES(?,?,?,?,?,?,?,?)',
                             (snapshot_id,*identity,serialized,now))
                if old:conn.execute('INSERT INTO macro_state_supersessions VALUES(?,?,?,?)',(old[0],snapshot_id,reason.strip(),now))
        return self.get(snapshot_id)

    @staticmethod
    def _project(conn,row):
        body=json.loads(row['body'])
        body.update(snapshotId=row['id'],promotion='shadow')
        if body['axis']=='growth':body['cycleSignalPromotion']='shadow'
        for field in ('promotion','cycleSignalPromotion'):
            if field=='cycleSignalPromotion' and body['axis']!='growth':continue
            decision=conn.execute('SELECT promotion,seq FROM macro_state_decisions WHERE market=? AND axis=? AND method=? AND field=? ORDER BY seq DESC LIMIT 1',
                                  (body['market'],body['axis'],body['methodVersion'],field)).fetchone()
            if decision:body[field]=decision[0];body[field+'DecisionId']=decision[1]
        return body

    def get(self,snapshot_id):
        with self.read() as conn:
            if conn is None:return None
            row=conn.execute('SELECT * FROM macro_state_snapshots WHERE id=?',(snapshot_id,)).fetchone()
            return self._project(conn,row) if row else None

    def latest(self,market,axis,*,before=None,method='macro-state-1'):
        with self.read() as conn:
            if conn is None:return None
            query='SELECT * FROM macro_state_snapshots WHERE market=? AND axis=? AND method=?'
            args=[market,axis,method]
            if before:query+=' AND as_of<?';args.append(utc(before))
            row=conn.execute(query+' ORDER BY as_of DESC,seq DESC LIMIT 1',args).fetchone()
            return self._project(conn,row) if row else None

    def decide(self,market,axis,method,field,promotion,*,evaluation_ref,user_confirmed):
        if user_confirmed is not True or not evaluation_ref:raise ValueError('promotion_confirmation_required')
        if market not in {'US','KR'} or axis not in LEVELS or field not in {'promotion','cycleSignalPromotion'} or promotion not in {'shadow','primary'}:
            raise ValueError('invalid_promotion')
        if field=='cycleSignalPromotion' and axis!='growth':raise ValueError('invalid_promotion')
        if promotion=='primary' and (market=='KR' or axis=='stress_vulnerability'):raise ValueError('macro_fixed_shadow')
        self.ensure()
        with sqlite3.connect(self.path,timeout=30) as conn:
            cursor=conn.execute('INSERT INTO macro_state_decisions(market,axis,method,field,promotion,evaluation_ref,created_at) VALUES(?,?,?,?,?,?,?)',
                               (market,axis,method,field,promotion,evaluation_ref,utc(dt.datetime.now(dt.timezone.utc).isoformat())))
            return cursor.lastrowid
