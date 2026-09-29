import json
import sqlite3
from pathlib import Path

from features.common.macro_data.schema import canonical
from features.common.macro_data.store import backup_database, _SCHEMA_LOCK
from .extraction import extract


class ExposureStore:
    def __init__(self, data_root):
        self.path = Path(data_root).resolve() / 'market-memory.sqlite3'

    def get(self, ticker, profile_id=None):
        if not self.path.exists():
            return None
        with sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='company_macro_exposures'").fetchone():
                return None
            query = 'SELECT body FROM company_macro_exposures WHERE ticker=?'
            args = [ticker]
            if profile_id:
                query += ' AND id=?'; args.append(profile_id)
            row = conn.execute(query + ' ORDER BY seq DESC LIMIT 1', args).fetchone()
            return json.loads(row[0]) if row else None

    def save(self, profile, *, materials):
        expected = extract({'ticker': profile['ticker'], 'market': profile['market']}, materials)
        if canonical(expected) != canonical(profile):
            raise ValueError('exposure_profile_not_grounded_in_materials')
        with _SCHEMA_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path) as conn:
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='company_macro_exposures'").fetchone()
            if not exists:
                backup_database(self.path, 'before-company-exposure-v1')
                with sqlite3.connect(self.path) as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    conn.execute('CREATE TABLE company_macro_exposures(seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,ticker TEXT NOT NULL,body TEXT NOT NULL)')
                    conn.execute('CREATE INDEX company_exposure_lookup ON company_macro_exposures(ticker,seq DESC)')
                    for operation in ('UPDATE', 'DELETE'):
                        conn.execute(f"CREATE TRIGGER company_exposure_no_{operation.lower()} BEFORE {operation} ON company_macro_exposures BEGIN SELECT RAISE(ABORT,'immutable_exposure'); END")
            with sqlite3.connect(self.path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                old = conn.execute('SELECT body FROM company_macro_exposures WHERE id=?', (profile['profileId'],)).fetchone()
                body = canonical(profile)
                if old and old[0] != body:
                    raise ValueError('exposure_identity_collision')
                if not old:
                    conn.execute('INSERT INTO company_macro_exposures(id,ticker,body) VALUES(?,?,?)', (profile['profileId'],profile['ticker'],body))
        return profile
