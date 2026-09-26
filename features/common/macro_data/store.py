"""Additive tables in market-memory.sqlite3. GET paths never create files or tables."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .schema import canonical, digest, normalize_observation, timestamp

_SCHEMA_LOCK = threading.RLock()
DDL = (
    'CREATE TABLE IF NOT EXISTS macro_schema(version INTEGER PRIMARY KEY)',
    'CREATE TABLE IF NOT EXISTS macro_metadata(id TEXT PRIMARY KEY, series_id TEXT NOT NULL, body TEXT NOT NULL)',
    '''CREATE TABLE IF NOT EXISTS macro_observations(
        id INTEGER PRIMARY KEY,series_id TEXT NOT NULL,period TEXT NOT NULL,vintage TEXT NOT NULL,
        available_at TEXT NOT NULL,basis TEXT NOT NULL,precision TEXT NOT NULL,value TEXT,
        meta_id TEXT NOT NULL REFERENCES macro_metadata(id),fetched_at TEXT NOT NULL,released_at TEXT,
        release_url TEXT,identity TEXT NOT NULL UNIQUE)''',
    'CREATE INDEX IF NOT EXISTS macro_period_idx ON macro_observations(series_id,period,available_at DESC,id DESC)',
    'CREATE INDEX IF NOT EXISTS macro_cutoff_idx ON macro_observations(series_id,available_at,period)',
    '''CREATE TABLE IF NOT EXISTS macro_collection_state(
        series_id TEXT PRIMARY KEY, status TEXT NOT NULL, cursor TEXT NOT NULL, updated_at TEXT NOT NULL,
        last_success TEXT NOT NULL DEFAULT '',error_code TEXT NOT NULL DEFAULT '')''',
)


def backup_database(path: Path, purpose: str) -> Path | None:
    # 운영 DB는 WAL을 쓰므로 파일 복사가 아니라 SQLite backup API로 일관된 사본을 만든다.
    if not path.exists():
        return None
    directory = path.parent / 'backups'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{path.stem}-{purpose}-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.sqlite3'
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(target) as backup:
        source.backup(backup)
        if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('macro_backup_failed')
    return target


class MacroStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    @contextmanager
    def read(self):
        # 읽기는 읽기 전용 연결만 쓴다. 파일이나 테이블이 없으면 만들지 않고 None을 준다.
        if not self.path.exists():
            yield None
            return
        with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='macro_schema'").fetchone():
                yield None
            else:
                yield conn

    def ensure(self):
        # v1 테이블은 기존 DB를 일관되게 백업한 뒤 한 번만 만든다.
        with _SCHEMA_LOCK:
            with self.read() as conn:
                if conn is not None:
                    version = conn.execute('SELECT MAX(version) FROM macro_schema').fetchone()[0]
                    # 더 새로운 앱이 만든 스키마에는 쓰지 않는다.
                    if version is not None and version > 1:
                        raise RuntimeError('macro_schema_newer_than_runtime')
                    if version == 1:
                        return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            backup_database(self.path, 'before-macro-v1')
            with sqlite3.connect(self.path, timeout=30) as conn:
                conn.execute('BEGIN IMMEDIATE')
                for statement in DDL:
                    conn.execute(statement)
                conn.execute('INSERT OR IGNORE INTO macro_schema VALUES(1)')

    def state(self, series_id=None):
        with self.read() as conn:
            if conn is None:
                return {} if series_id else []
            if series_id:
                row = conn.execute('SELECT * FROM macro_collection_state WHERE series_id=?', (series_id,)).fetchone()
                return {**dict(row), 'cursor': json.loads(row['cursor'])} if row else {}
            return [{**dict(r), 'cursor': json.loads(r['cursor'])} for r in conn.execute('SELECT * FROM macro_collection_state')]

    @staticmethod
    def _state(conn, series_id, status, cursor, at, error=''):
        # last_success는 성공한 실행에서만 앞으로 간다. 실패는 마지막 성공 시각을 지우지 않는다.
        conn.execute(
            '''INSERT INTO macro_collection_state(series_id,status,cursor,updated_at,last_success,error_code)
            VALUES(?,?,?,?,?,?) ON CONFLICT(series_id) DO UPDATE SET status=excluded.status,cursor=excluded.cursor,
            updated_at=excluded.updated_at,last_success=CASE WHEN excluded.status='ok' THEN excluded.updated_at ELSE last_success END,error_code=excluded.error_code''',
            (series_id, status, canonical(cursor), at, at if status == 'ok' else '', error),
        )

    def set_state(self, series_id, status, *, cursor=None, at=None, error=''):
        self.ensure()
        previous = self.state(series_id)
        with sqlite3.connect(self.path, timeout=30) as conn:
            self._state(
                conn,
                series_id,
                status,
                previous.get('cursor', {}) if cursor is None else cursor,
                at or dt.datetime.now(dt.timezone.utc).isoformat(),
                error,
            )

    def ingest(self, series_id, rows, *, cursor, status='partial', at=None):
        # 검증한 한 페이지와 재개 지점(cursor)을 같은 transaction에 저장한다.
        points = [normalize_observation(r) for r in rows]
        if any(p['seriesId'] != series_id for p in points):
            raise ValueError('macro_series_mismatch')
        self.ensure()
        inserted = 0
        with sqlite3.connect(self.path, timeout=30) as conn:
            conn.execute('BEGIN IMMEDIATE')
            for p in sorted(points, key=lambda p: (p['availableAt'], p['period'])):
                meta_id = digest({'series': series_id, 'metadata': p['metadata']})
                conn.execute('INSERT OR IGNORE INTO macro_metadata VALUES(?,?,?)', (meta_id, series_id, canonical(p['metadata'])))
                # Consecutive equal snapshots are not revisions; returning to an older value is.
                previous = conn.execute(
                    'SELECT value,meta_id,available_at FROM macro_observations WHERE series_id=? AND period=? AND available_at<=? ORDER BY available_at DESC,id DESC LIMIT 1',
                    (series_id, p['period'], p['availableAt']),
                ).fetchone()
                if previous and previous[0] == p['value'] and previous[1] == meta_id:
                    # 이전 보관판이 충돌 상태라면 뒤의 정상 보관판은 같은 숫자라도 남긴다.
                    # 과거 조회의 충돌은 유지하고 새 시점부터만 값을 확정한다.
                    prior_count = conn.execute(
                        'SELECT COUNT(*) FROM macro_observations WHERE series_id=? AND period=? AND available_at=?',
                        (series_id, p['period'], previous[2]),
                    ).fetchone()[0]
                    if previous[2] == p['availableAt'] or prior_count == 1:
                        continue
                # 같은 요청을 다시 받아도 identity가 같아 중복 행이 생기지 않는다.
                identity = digest([series_id, p['period'], p['vintageDate'] or p['availableAt'], p['availabilityBasis'], p['value'], meta_id])
                result = conn.execute(
                    '''INSERT OR IGNORE INTO macro_observations(series_id,period,vintage,available_at,basis,precision,value,meta_id,fetched_at,released_at,release_url,identity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        series_id, p['period'], p['vintageDate'] or '', p['availableAt'], p['availabilityBasis'],
                        p['precision'], p['value'], meta_id, p['fetchedAt'], p['releasedAt'], p['releaseEvidenceUrl'], identity,
                    ),
                )
                inserted += result.rowcount
            self._state(conn, series_id, status, cursor, at or dt.datetime.now(dt.timezone.utc).isoformat())
        return inserted

    def history(self, series_id, *, cutoff=None, start=None):
        # 관측기간마다 한 행: cutoff(없으면 현재)까지 알려진 가장 늦은 값.
        conditions = ['series_id=?']
        args = [series_id]
        if cutoff:
            conditions.append('available_at<=?')
            args.append(timestamp(cutoff))
        if start:
            conditions.append('period>=?')
            args.append(dt.date.fromisoformat(start).isoformat())
        with self.read() as conn:
            if conn is None:
                return []
            # Aggregate compact indexed columns before joining metadata. A window over
            # metadata-expanded vintage rows made weekly full-history reads expensive.
            # collisions: 같은 관측기간·같은 공개 시점에 값이 둘 이상이면 어느 쪽도 고르지 않는다.
            rows = conn.execute('''WITH picked AS (
                SELECT period,MAX(available_at) AS latest_at,COUNT(*) AS versions,
                       MIN(fetched_at) AS first_seen
                FROM macro_observations WHERE ''' + ' AND '.join(conditions) + ''' GROUP BY period)
                SELECT o.*,m.body AS metadata,p.versions,p.first_seen,
                       (SELECT COUNT(*) FROM macro_observations k
                        WHERE k.series_id=o.series_id AND k.period=o.period
                          AND k.available_at=o.available_at) AS collisions
                FROM picked p JOIN macro_observations o ON o.id=(
                    SELECT id FROM macro_observations z WHERE z.series_id=?
                    AND z.period=p.period AND z.available_at=p.latest_at ORDER BY id DESC LIMIT 1)
                JOIN macro_metadata m ON m.id=o.meta_id ORDER BY o.period''', args + [series_id]).fetchall()
            return [self._public(r) for r in rows]

    def revisions(self, series_id, period, *, cutoff=None):
        dt.date.fromisoformat(period)
        args = [series_id, period]
        where = 'o.series_id=? AND o.period=?'
        if cutoff:
            where += ' AND o.available_at<=?'
            args.append(timestamp(cutoff))
        with self.read() as conn:
            if conn is None:
                return []
            return [
                self._public(r)
                for r in conn.execute(
                    'SELECT o.*,m.body AS metadata FROM macro_observations o JOIN macro_metadata m ON m.id=o.meta_id WHERE ' + where + ' ORDER BY available_at,id',
                    args,
                )
            ]

    def coverage(self, series_id):
        with self.read() as conn:
            if conn is None:
                return {'firstAvailableAt': None, 'firstPeriod': None, 'lastPeriod': None, 'rows': 0}
            row = conn.execute(
                'SELECT MIN(available_at),MIN(period),MAX(period),COUNT(*) FROM macro_observations WHERE series_id=?',
                (series_id,),
            ).fetchone()
            return dict(zip(['firstAvailableAt', 'firstPeriod', 'lastPeriod', 'rows'], row))

    @staticmethod
    def _public(row):
        r = dict(row)
        meta = json.loads(r['metadata'])
        conflict = r.get('collisions', 1) > 1
        return {
            'id': r['id'],
            'seriesId': r['series_id'],
            'period': r['period'],
            # 충돌한 값은 숫자로 내보내지 않는다. 원값은 rawValue에 남는다.
            'value': None if conflict or r['value'] is None else float(r['value']),
            'rawValue': r['value'],
            'metadata': meta,
            'metadataId': r['meta_id'],
            'vintageDate': r['vintage'] or None,
            'availableAt': r['available_at'],
            'availabilityBasis': r['basis'],
            'releasedAt': r['released_at'],
            'releaseEvidenceUrl': r['release_url'],
            'precision': r['precision'],
            'fetchedAt': r['fetched_at'],
            'firstSeenAt': r.get('first_seen', r['fetched_at']) if r['basis'] == 'local_observed' else None,
            'revised': r.get('versions', 1) > 1,
            'conflict': conflict,
        }
