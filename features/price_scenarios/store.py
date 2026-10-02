"""Append-only price snapshots and the person's criteria/assumptions in market-memory.sqlite3.

Reading never creates a file or table. Snapshots, links, review rows, criteria
revisions and assumption overrides are never updated or deleted (triggers). A
snapshot, its supersession link and the review rows it triggers commit in one
SQLite transaction, so a failure leaves earlier rows exactly as they were.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from decimal import Decimal
from pathlib import Path

from features.common.macro_data.store import _SCHEMA_LOCK, backup_database

from . import METHOD_VERSION, SPEC_VERSION
from .changes import change_reasons, review_rows
from .decimal_ops import canonical, fingerprint, number

SCHEMA_VERSION = 1
HOLDING_YEARS = {5, 10}
DDL = (
    "CREATE TABLE IF NOT EXISTS price_scenario_schema(version INTEGER PRIMARY KEY)",
    """CREATE TABLE IF NOT EXISTS price_snapshots(
        seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, instrument_id TEXT NOT NULL, as_of TEXT NOT NULL,
        method TEXT NOT NULL, fingerprint TEXT NOT NULL, body TEXT NOT NULL, meta TEXT NOT NULL,
        computed_at TEXT NOT NULL, UNIQUE(instrument_id, as_of, method, fingerprint))""",
    "CREATE INDEX IF NOT EXISTS price_snapshot_latest ON price_snapshots(instrument_id, as_of DESC, computed_at DESC, seq DESC)",
    """CREATE TABLE IF NOT EXISTS price_snapshot_links(
        snapshot_id TEXT NOT NULL UNIQUE REFERENCES price_snapshots(id),
        supersedes_snapshot_id TEXT NOT NULL REFERENCES price_snapshots(id),
        change_reasons TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS price_snapshot_reviews(
        seq INTEGER PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES price_snapshots(id), reason TEXT NOT NULL,
        metric TEXT NOT NULL, fiscal_year INTEGER NOT NULL,
        detected_by_snapshot_id TEXT NOT NULL REFERENCES price_snapshots(id), created_at TEXT NOT NULL,
        UNIQUE(snapshot_id, reason, metric, fiscal_year, detected_by_snapshot_id))""",
    """CREATE TABLE IF NOT EXISTS valuation_user_criteria(
        revision_id INTEGER PRIMARY KEY, required_return TEXT, min_margin_of_safety TEXT,
        holding_years INTEGER, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS valuation_assumption_overrides(
        override_id INTEGER PRIMARY KEY, instrument_id TEXT NOT NULL,
        based_on_snapshot_id TEXT NOT NULL REFERENCES price_snapshots(id),
        growth TEXT, exit_pe TEXT, payout TEXT, supersedes_override_id INTEGER, created_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS valuation_override_lookup ON valuation_assumption_overrides(instrument_id, override_id DESC)",
)
TABLES = ("price_snapshots", "price_snapshot_links", "price_snapshot_reviews",
          "valuation_user_criteria", "valuation_assumption_overrides")


class PriceStoreError(ValueError):
    """`.code` is a stable enum for HTTP mapping; the message never carries paths."""

    def __init__(self, code: str, field: str | None = None):
        super().__init__(code)
        self.code, self.field = code, field


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_id(instrument_id: str, as_of: str, method: str, input_fingerprint: str) -> str:
    return "price-" + hashlib.sha256(canonical([instrument_id, as_of, method, input_fingerprint]).encode()).hexdigest()


PLAIN_DECIMAL = re.compile(r"-?[0-9]{1,30}(\.[0-9]{1,30})?")


def decimal_text(value, *, field: str, low=None, high=None, low_open=False) -> str:
    """Finite Decimal text with a closed range; never repaired or clamped."""
    if isinstance(value, (float, bool)):
        raise PriceStoreError("invalid_number", field)
    try:
        parsed = number(value)
        text = value if isinstance(value, str) else format(parsed, "f")
    except (ValueError, TypeError) as exc:
        raise PriceStoreError("invalid_number", field) from exc
    if not PLAIN_DECIMAL.fullmatch(text.strip()):  # exponent notation would be read at a different scale by the person and the screen
        raise PriceStoreError("invalid_number", field)
    if (low is not None and (parsed < low or (low_open and parsed == low))) or (high is not None and parsed > high):
        raise PriceStoreError("out_of_range", field)
    return str(parsed)


class PriceStore:
    def __init__(self, path):
        self.path = Path(path).resolve()

    # --- connection and schema -------------------------------------------------

    @contextmanager
    def read(self):
        if not self.path.exists():
            yield None
            return
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
            conn.row_factory = sqlite3.Row
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='price_scenario_schema'").fetchone():
                yield None
            else:
                yield conn

    def ensure(self):
        with _SCHEMA_LOCK:
            with self.read() as conn:
                if conn is not None:
                    version = conn.execute("SELECT MAX(version) FROM price_scenario_schema").fetchone()[0]
                    if version and version > SCHEMA_VERSION:
                        raise RuntimeError("price_scenario_schema_newer_than_runtime")
                    if version == SCHEMA_VERSION:
                        return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            backup_database(self.path, "before-price-scenarios-v1")
            with closing(sqlite3.connect(self.path, timeout=30)) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                for statement in DDL:
                    conn.execute(statement)
                for table in TABLES:
                    for operation in ("UPDATE", "DELETE"):
                        conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                                     "BEGIN SELECT RAISE(ABORT,'immutable_price_scenario'); END")
                conn.execute("INSERT INTO price_scenario_schema VALUES(?)", (SCHEMA_VERSION,))

    @contextmanager
    def _write(self):
        """A write connection: commits on success, rolls back on error and is always closed."""
        self.ensure()
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            with conn:
                yield conn
        finally:
            conn.close()

    # --- snapshots -------------------------------------------------------------

    @staticmethod
    def _load(row) -> dict:
        body = json.loads(row["body"])
        return {"snapshotId": row["id"], "instrumentId": row["instrument_id"], "asOf": row["as_of"],
                "inputFingerprint": row["fingerprint"], "computedAt": row["computed_at"],
                "inputs": body["inputs"], "results": body["results"], "meta": json.loads(row["meta"])}

    def save_snapshot(self, inputs: dict, results: dict, *, meta: dict | None = None, computed_at: str | None = None) -> dict:
        """Idempotent for identical results; a different result under one fingerprint is refused."""
        for key in ("instrumentId", "asOf", "methodVersion", "specVersion"):
            if not isinstance(inputs.get(key), str) or not inputs[key]:
                raise PriceStoreError("invalid_snapshot_identity", key)
        dt.date.fromisoformat(inputs["asOf"])
        if inputs["methodVersion"] != METHOD_VERSION or inputs["specVersion"] != SPEC_VERSION:
            raise PriceStoreError("method_version_not_writable")
        digest = fingerprint(inputs)  # also rejects float numbers in inputs
        identity = (inputs["instrumentId"], inputs["asOf"], inputs["methodVersion"], digest)
        new_id = snapshot_id(*identity)
        results_text = canonical(results)
        body = canonical({"inputs": inputs, "results": results})
        stamp = computed_at or _now()
        with self._write() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT body FROM price_snapshots WHERE id=?", (new_id,)).fetchone()
            if existing:
                if canonical(json.loads(existing["body"])["results"]) != results_text:
                    raise PriceStoreError("non_reproducible")
                return {"snapshotId": new_id, "created": False}
            rows = conn.execute("SELECT * FROM price_snapshots WHERE instrument_id=? ORDER BY as_of DESC, computed_at DESC, seq DESC",
                                (inputs["instrumentId"],)).fetchall()
            conn.execute("INSERT INTO price_snapshots(id,instrument_id,as_of,method,fingerprint,body,meta,computed_at) VALUES(?,?,?,?,?,?,?,?)",
                         (new_id, *identity[:3], digest, body, canonical(meta or {}), stamp))
            if rows:
                earlier = [self._load(row) for row in rows]
                new = {"snapshotId": new_id, "inputs": inputs, "results": results}
                conn.execute("INSERT INTO price_snapshot_links VALUES(?,?,?,?)",
                             (new_id, earlier[0]["snapshotId"], canonical(change_reasons(earlier[0], new)), stamp))
                for row in review_rows(earlier, new):
                    conn.execute("INSERT OR IGNORE INTO price_snapshot_reviews(snapshot_id,reason,metric,fiscal_year,detected_by_snapshot_id,created_at) "
                                 "VALUES(?,?,?,?,?,?)", (row["snapshotId"], row["reason"], row["metric"], row["fiscalYear"],
                                                         row["detectedBySnapshotId"], stamp))
        return {"snapshotId": new_id, "created": True}

    def get(self, snapshot_id_: str) -> dict | None:
        with self.read() as conn:
            row = conn.execute("SELECT * FROM price_snapshots WHERE id=?", (snapshot_id_,)).fetchone() if conn else None
            return self._load(row) if row else None

    def latest(self, instrument_id: str) -> dict | None:
        with self.read() as conn:
            row = conn.execute("SELECT * FROM price_snapshots WHERE instrument_id=? ORDER BY as_of DESC, computed_at DESC, seq DESC LIMIT 1",
                               (instrument_id,)).fetchone() if conn else None
            return self._load(row) if row else None

    def history(self, instrument_id: str) -> list[dict]:
        """Newest first, with each snapshot's link (what it superseded and why)."""
        with self.read() as conn:
            if conn is None:
                return []
            rows = conn.execute("""SELECT s.id, s.as_of, s.computed_at, s.method, l.supersedes_snapshot_id, l.change_reasons,
                                          (SELECT COUNT(*) FROM price_snapshot_reviews r WHERE r.snapshot_id = s.id) AS review_count
                                   FROM price_snapshots s LEFT JOIN price_snapshot_links l ON l.snapshot_id = s.id
                                   WHERE s.instrument_id=? ORDER BY s.as_of DESC, s.computed_at DESC, s.seq DESC""",
                                (instrument_id,)).fetchall()
            return [{"snapshotId": row["id"], "asOf": row["as_of"], "computedAt": row["computed_at"], "method": row["method"],
                     "supersedes": row["supersedes_snapshot_id"], "reviewCount": row["review_count"],
                     "changeReasons": json.loads(row["change_reasons"]) if row["change_reasons"] else []} for row in rows]

    def reviews(self, snapshot_id_: str) -> list[dict]:
        with self.read() as conn:
            rows = conn.execute("SELECT * FROM price_snapshot_reviews WHERE snapshot_id=? ORDER BY seq", (snapshot_id_,)).fetchall() if conn else []
            return [{"reason": row["reason"], "metric": row["metric"], "fiscalYear": row["fiscal_year"],
                     "detectedBySnapshotId": row["detected_by_snapshot_id"], "createdAt": row["created_at"]} for row in rows]

    # --- the person's criteria (global) ---------------------------------------

    def criteria(self, revision_id: int | None = None) -> dict | None:
        with self.read() as conn:
            if conn is None:
                return None
            row = (conn.execute("SELECT * FROM valuation_user_criteria WHERE revision_id=?", (revision_id,)).fetchone()
                   if revision_id is not None else
                   conn.execute("SELECT * FROM valuation_user_criteria ORDER BY revision_id DESC LIMIT 1").fetchone())
            return None if row is None else {"revisionId": row["revision_id"], "requiredReturn": row["required_return"],
                                              "minMarginOfSafety": row["min_margin_of_safety"],
                                              "holdingYears": row["holding_years"], "createdAt": row["created_at"]}

    def save_criteria(self, *, required_return=None, min_margin_of_safety=None, holding_years=None,
                      expected_revision_id: int | None = None) -> dict:
        """A new revision. Blank means not set (never 0). A stale expected revision is a conflict."""
        required = None if required_return in (None, "") else decimal_text(
            required_return, field="requiredReturn", low=Decimal(-99), high=Decimal(100))
        margin = None if min_margin_of_safety in (None, "") else decimal_text(
            min_margin_of_safety, field="minMarginOfSafety", low=Decimal(0), high=Decimal(100))
        if holding_years is not None and (isinstance(holding_years, bool) or holding_years not in HOLDING_YEARS):
            raise PriceStoreError("invalid_holding_years", "holdingYears")
        if (required is not None or margin is not None) and holding_years is None:
            raise PriceStoreError("holding_years_required", "holdingYears")
        with self._write() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT MAX(revision_id) FROM valuation_user_criteria").fetchone()[0]
            if current != expected_revision_id:
                raise PriceStoreError("revision_conflict")
            cursor = conn.execute("INSERT INTO valuation_user_criteria(required_return,min_margin_of_safety,holding_years,created_at) "
                                  "VALUES(?,?,?,?)", (required, margin, holding_years, _now()))
            revision = cursor.lastrowid
        return self.criteria(revision)

    # --- the person's assumptions per instrument ------------------------------

    def override(self, instrument_id: str, override_id: int | None = None) -> dict | None:
        with self.read() as conn:
            if conn is None:
                return None
            row = (conn.execute("SELECT * FROM valuation_assumption_overrides WHERE override_id=? AND instrument_id=?",
                                (override_id, instrument_id)).fetchone() if override_id is not None else
                   conn.execute("SELECT * FROM valuation_assumption_overrides WHERE instrument_id=? ORDER BY override_id DESC LIMIT 1",
                                (instrument_id,)).fetchone())
            return None if row is None else {"overrideId": row["override_id"], "instrumentId": row["instrument_id"],
                                              "basedOnSnapshotId": row["based_on_snapshot_id"], "growth": row["growth"],
                                              "exitPE": row["exit_pe"], "payout": row["payout"],
                                              "supersedesOverrideId": row["supersedes_override_id"], "createdAt": row["created_at"]}

    def save_override(self, instrument_id: str, based_on_snapshot_id: str, *, growth=None, exit_pe=None, payout=None,
                      expected_override_id: int | None = None) -> dict:
        """A new override revision; blank fields inherit the snapshot's median. Clearing is a revision of all-blank."""
        values = {
            "growth": None if growth in (None, "") else decimal_text(growth, field="growth", low=Decimal(-1), low_open=True),
            "exit_pe": None if exit_pe in (None, "") else decimal_text(exit_pe, field="exitPE", low=Decimal(0), low_open=True),
            "payout": None if payout in (None, "") else decimal_text(payout, field="payout", low=Decimal(0), high=Decimal(1)),
        }
        with self._write() as conn:
            conn.execute("BEGIN IMMEDIATE")
            snapshot = conn.execute("SELECT instrument_id FROM price_snapshots WHERE id=?", (based_on_snapshot_id,)).fetchone()
            if snapshot is None:
                raise PriceStoreError("snapshot_not_found")
            if snapshot["instrument_id"] != instrument_id:
                raise PriceStoreError("snapshot_instrument_mismatch")
            current = conn.execute("SELECT MAX(override_id) FROM valuation_assumption_overrides WHERE instrument_id=?",
                                   (instrument_id,)).fetchone()[0]
            if current != expected_override_id:
                raise PriceStoreError("revision_conflict")
            cursor = conn.execute("INSERT INTO valuation_assumption_overrides(instrument_id,based_on_snapshot_id,growth,exit_pe,payout,"
                                  "supersedes_override_id,created_at) VALUES(?,?,?,?,?,?,?)",
                                  (instrument_id, based_on_snapshot_id, values["growth"], values["exit_pe"], values["payout"],
                                   current, _now()))
            override_id = cursor.lastrowid
        return self.override(instrument_id, override_id)
