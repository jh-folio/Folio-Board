"""Case/index metadata in the existing graph DB; journal bodies stay in JSON."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager

from features.common.macro_data.store import backup_database
from features.decision_readiness.inputs import has
from . import CaseError, SCHEMA_VERSION
from .paths import canonical, database, safe_path

DDL = (
    "CREATE TABLE IF NOT EXISTS investment_case_schema(version INTEGER PRIMARY KEY)",
    """CREATE TABLE IF NOT EXISTS investment_cases(
        case_id TEXT PRIMARY KEY, instrument_id TEXT NOT NULL UNIQUE, revision INTEGER NOT NULL,
        lifecycle TEXT NOT NULL CHECK(lifecycle IN ('researching','considering','owned','archived')),
        episode_id TEXT NOT NULL, refs_json TEXT NOT NULL, fingerprint TEXT NOT NULL, method TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS investment_case_events(
        event_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, case_revision INTEGER NOT NULL,
        kind TEXT NOT NULL, from_stage TEXT, to_stage TEXT, episode_id TEXT NOT NULL,
        previous_episode_id TEXT, related_journal_id TEXT, recorded_at TEXT NOT NULL,
        UNIQUE(case_id,case_revision))""",
    """CREATE TABLE IF NOT EXISTS decision_journal_index(
        journal_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, episode_id TEXT NOT NULL,
        operation_id TEXT NOT NULL UNIQUE, recorded_at TEXT NOT NULL, file_hash TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ready','deletion_pending')))""",
    """CREATE TABLE IF NOT EXISTS decision_journal_links(
        journal_id TEXT NOT NULL, slot TEXT NOT NULL, source_kind TEXT NOT NULL,
        source_id TEXT NOT NULL, source_hash TEXT,
        PRIMARY KEY(journal_id,slot,source_kind,source_id))""",
    "CREATE INDEX IF NOT EXISTS journal_source_links ON decision_journal_links(source_kind,source_id)",
    """CREATE TABLE IF NOT EXISTS investment_case_operations(
        operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, case_id TEXT,
        expected_revision INTEGER NOT NULL, kind TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('preparing','ready','failed','deleting')),
        metadata_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS decision_journal_corrections(
        link_id TEXT PRIMARY KEY, journal_id TEXT NOT NULL, slot TEXT NOT NULL,
        old_ref_json TEXT NOT NULL, new_ref_json TEXT NOT NULL, noted_at TEXT NOT NULL)""",
)


def decode(row):
    return dict(row) if row else None


def case(conn, case_id):
    return decode(conn.execute("SELECT * FROM investment_cases WHERE case_id=?", (case_id,)).fetchone()) if has(conn, "investment_cases") else None


def operation(conn, operation_id):
    row = decode(conn.execute("SELECT * FROM investment_case_operations WHERE operation_id=?", (operation_id,)).fetchone()) if has(conn, "investment_case_operations") else None
    if row:
        row["metadata"] = json.loads(row.pop("metadata_json"))
    return row


def index(conn, journal_id):
    return decode(conn.execute("SELECT * FROM decision_journal_index WHERE journal_id=?", (journal_id,)).fetchone()) if has(conn, "decision_journal_index") else None


def journals(conn, case_id):
    return [dict(r) for r in conn.execute("SELECT * FROM decision_journal_index WHERE case_id=? ORDER BY recorded_at DESC,journal_id", (case_id,))] if has(conn, "decision_journal_index") else []


def pending(conn):
    return [operation(conn, r[0]) for r in conn.execute("SELECT operation_id FROM investment_case_operations WHERE status IN ('preparing','deleting') ORDER BY created_at")] if has(conn, "investment_case_operations") else []


def assert_revision(conn, case_id, expected):
    value = case(conn, case_id)
    if (value["revision"] if value else 0) != expected:
        raise CaseError("case_revision_changed", 409)
    return value


class Store:
    def __init__(self, root):
        self.root = root
        self.path = safe_path(root, "market-memory.sqlite3")

    def ensure(self):
        with database(self.root) as conn:
            version = conn.execute("SELECT MAX(version) FROM investment_case_schema").fetchone()[0] if has(conn, "investment_case_schema") else None
            if version and version > SCHEMA_VERSION:
                raise CaseError("case_schema_newer_than_runtime", 409)
            if version == SCHEMA_VERSION:
                return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        safe_path(self.root, "backups")  # reject a redirected backup destination before invoking the shared helper
        backup_database(self.path, "before-investment-case-v1")
        with closing(sqlite3.connect(self.path, timeout=30)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for statement in DDL:
                conn.execute(statement)
            conn.execute("INSERT OR IGNORE INTO investment_case_schema VALUES(?)", (SCHEMA_VERSION,))

    @contextmanager
    def write(self):
        self.ensure()
        with closing(sqlite3.connect(self.path, timeout=30)) as conn, conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            yield conn


def set_operation(conn, operation_id, status, metadata):
    conn.execute("UPDATE investment_case_operations SET status=?,metadata_json=? WHERE operation_id=?",
                 (status, canonical(metadata).decode(), operation_id))


def add_operation(conn, operation_id, request_hash, case_id, expected, kind, status, metadata, stamp):
    conn.execute("INSERT INTO investment_case_operations VALUES(?,?,?,?,?,?,?,?)",
                 (operation_id, request_hash, case_id, expected, kind, status, canonical(metadata).decode(), stamp))


def source_links(conn, kind, source_id):
    return [dict(r) for r in conn.execute("SELECT l.*,i.case_id,i.file_hash,i.status FROM decision_journal_links l JOIN decision_journal_index i ON l.journal_id=i.journal_id WHERE source_kind=? AND source_id=? ORDER BY l.journal_id,l.slot", (kind, source_id))] if has(conn, "decision_journal_links") else []
