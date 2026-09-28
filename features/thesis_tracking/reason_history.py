"""Immutable user-reason revisions alongside the current thesis row.

The thesis row remains the single current authority. This module records its
user-authored fields without copying machine checkpoint results into history.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import tempfile
import threading
import uuid
from contextlib import closing
from pathlib import Path


_MIGRATION_LOCK = threading.RLock()
_FIELDS = (
    "ticker", "company", "core_thesis", "key_assumptions", "supporting_signals",
    "weakening_signals", "falsification_triggers", "next_checkpoints",
    "key_metrics", "linked_regimes", "review_cycle", "conviction", "status",
    "source", "note_path",
)
_LIST_COLUMNS = {
    "key_assumptions": "key_assumptions_json",
    "supporting_signals": "supporting_signals_json",
    "weakening_signals": "weakening_signals_json",
    "falsification_triggers": "falsification_triggers_json",
    "next_checkpoints": "next_checkpoints_json",
    "key_metrics": "key_metrics_json",
    "linked_regimes": "linked_regimes_json",
}
CONDITION_STATES = frozenset({"unanswered", "unknown", "skipped", "written", "legacy_unknown"})
EDIT_SOURCES = frozenset({"manual", "native_note", "obsidian", "agent_approved", "legacy_import"})


class ReasonRevisionConflictError(Exception):
    def __init__(self, current: dict | None):
        super().__init__("reason_revision_conflict")
        self.current = current


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_refs(values: list) -> list[dict]:
    if len(values) > 20:
        raise ValueError("too_many_reason_refs")
    result = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("invalid_reason_ref")
        ref = {key: str(value.get(key) or "").strip()[:limit]
               for key, limit in (("id", 200), ("revision", 120), ("title", 220), ("url", 1000))}
        if not ref["id"] and not ref["url"]:
            raise ValueError("invalid_reason_ref")
        if ref["url"] and not ref["url"].startswith(("https://", "http://")):
            raise ValueError("invalid_reason_ref_url")
        result.append({key: text for key, text in ref.items() if text})
    return result


def _snapshot(row: dict | sqlite3.Row) -> dict:
    data = dict(row)
    result = {}
    for field in _FIELDS:
        if field in _LIST_COLUMNS:
            raw = data.get(field)
            if raw is None:
                raw = data.get(_LIST_COLUMNS[field]) or "[]"
            try:
                items = json.loads(raw) if isinstance(raw, str) else list(raw or [])
            except (TypeError, ValueError):
                items = []
            # A checkpoint's machine status/history is not a change to the
            # user's reason. Keep only the strings authored as conditions.
            result[field] = [item for item in items if isinstance(item, str)] if field == "next_checkpoints" else items
        else:
            result[field] = data.get(field) or ""
    return result


def _kind_at_write(connection: sqlite3.Connection, ticker: str) -> str:
    db_file = connection.execute("PRAGMA database_list").fetchone()[2]
    if not db_file:
        return "unknown"
    try:
        from features.portfolio.service import get_portfolio
        from features.thesis_tracking.model import normalize_ticker

        holdings = get_portfolio(Path(db_file).parent).get("positions") or []
        key = normalize_ticker(ticker)
        for position in holdings:
            if normalize_ticker(position.get("ticker") or position.get("symbol") or "") == key:
                return "investment"
    except Exception:
        # An invalid or temporarily unreadable portfolio must not block a
        # user's reason write; the snapshot records that classification is unknown.
        return "unknown"
    return "interest"


def backup_before_migration(path: Path) -> Path | None:
    """Back up a legacy DB and prove it can be reopened elsewhere before DDL."""
    path = Path(path).resolve()
    if not path.exists() or path.stat().st_size == 0:
        return None
    with _MIGRATION_LOCK:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "thesis" not in tables or "reason_revision" in tables:
                return None
            prior_count = source.execute("SELECT COUNT(*) FROM thesis").fetchone()[0]
            directory = path.parent / "backups"
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / f"{path.stem}-before-reason-v1-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.sqlite3"
            with closing(sqlite3.connect(target)) as backup:
                source.backup(backup)
        with tempfile.TemporaryDirectory(prefix="folio-reason-restore-") as temp:
            restored_path = Path(temp) / "restored.sqlite3"
            with closing(sqlite3.connect(target)) as backup, closing(sqlite3.connect(restored_path)) as restored:
                backup.backup(restored)
                if restored.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise RuntimeError("reason_backup_restore_failed")
                if restored.execute("SELECT COUNT(*) FROM thesis").fetchone()[0] != prior_count:
                    raise RuntimeError("reason_backup_restore_mismatch")
                # These existing owner tables must remain readable after restore.
                for table in ("thesis_delta", "thesis_review_state"):
                    if table in tables:
                        restored.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
        return target


def verify_legacy_import(backup_path: Path, connection: sqlite3.Connection) -> None:
    """Prove every legacy current row and its first immutable snapshot survived."""
    with closing(sqlite3.connect(backup_path)) as backup:
        backup.row_factory = sqlite3.Row
        rows = backup.execute("SELECT * FROM thesis").fetchall()
        for original in rows:
            current = connection.execute("SELECT * FROM thesis WHERE ticker=?", (original["ticker"],)).fetchone()
            first = connection.execute("SELECT * FROM reason_revision WHERE ticker=? ORDER BY revision LIMIT 1",
                                       (original["ticker"],)).fetchone()
            if current is None or dict(current) != dict(original) or first is None:
                raise RuntimeError("reason_legacy_import_mismatch")
            imported = _public(first)
            if imported["content"] != _snapshot(original) or imported["editSource"] != "legacy_import":
                raise RuntimeError("reason_legacy_import_mismatch")
        for table in ("thesis_delta", "thesis_review_state"):
            if backup.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                before = [tuple(row) for row in backup.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                after = [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                if before != after:
                    raise RuntimeError("reason_legacy_import_mismatch")


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS reason_revision (
        revision_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        revision INTEGER NOT NULL,
        previous_revision_id TEXT NOT NULL DEFAULT '',
        content_hash TEXT NOT NULL,
        content_json TEXT NOT NULL,
        condition_state TEXT NOT NULL,
        field_presence_json TEXT NOT NULL DEFAULT '{}',
        edit_source TEXT NOT NULL,
        kind_at_write TEXT NOT NULL,
        change_reason TEXT NOT NULL DEFAULT '',
        user_stated_at TEXT NOT NULL DEFAULT '',
        basis_refs_json TEXT NOT NULL DEFAULT '[]',
        recorded_at TEXT NOT NULL,
        UNIQUE(ticker, revision),
        FOREIGN KEY(ticker) REFERENCES thesis(ticker) ON DELETE CASCADE
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS reason_revision_ticker_order ON reason_revision(ticker, revision DESC)")
    # Existing rows have no provable authoring time or explicit condition state.
    for row in connection.execute("SELECT * FROM thesis WHERE ticker NOT IN (SELECT ticker FROM reason_revision)").fetchall():
        record_revision(
            connection, row, edit_source="legacy_import", condition_state="legacy_unknown",
            field_presence={"conviction": "unknown", "review_cycle": "unknown"},
            kind_at_write="legacy_unknown",
        )


def latest(connection: sqlite3.Connection, ticker: str) -> dict | None:
    row = connection.execute(
        "SELECT * FROM reason_revision WHERE ticker=? ORDER BY revision DESC LIMIT 1", (ticker,)
    ).fetchone()
    return _public(row) if row else None


def get(connection: sqlite3.Connection, revision_id: str) -> dict | None:
    row = connection.execute("SELECT * FROM reason_revision WHERE revision_id=?", (revision_id,)).fetchone()
    return _public(row) if row else None


def list_for_ticker(connection: sqlite3.Connection, ticker: str, *, limit: int = 20) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM reason_revision WHERE ticker=? ORDER BY revision DESC LIMIT ?",
        (ticker, max(1, min(int(limit), 100))),
    ).fetchall()
    return [_public(row) for row in rows]


def _public(row: sqlite3.Row) -> dict:
    data = dict(row)
    return {
        "revisionId": data["revision_id"], "ticker": data["ticker"],
        "revision": data["revision"], "previousRevisionId": data["previous_revision_id"],
        "contentHash": data["content_hash"], "content": json.loads(data["content_json"]),
        "conditionResponse": data["condition_state"],
        "fieldPresence": json.loads(data["field_presence_json"]),
        "editSource": data["edit_source"],
        "kindAtWrite": data["kind_at_write"], "changeReason": data["change_reason"],
        "userStatedAt": data["user_stated_at"], "basisRefs": json.loads(data["basis_refs_json"]),
        "recordedAt": data["recorded_at"],
    }


def record_revision(
    connection: sqlite3.Connection,
    row: dict | sqlite3.Row,
    *,
    edit_source: str,
    condition_state: str | None = None,
    field_presence: dict | None = None,
    kind_at_write: str | None = None,
    change_reason: str = "",
    user_stated_at: str | None = None,
    basis_refs: list | None = None,
) -> dict:
    content = _snapshot(row)
    if edit_source not in EDIT_SOURCES:
        raise ValueError("invalid_reason_edit_source")
    ticker = content["ticker"]
    previous = latest(connection, ticker)
    # Vault edits have no explicit response enum. A removed condition is an
    # unanswered condition, not the previous revision's written answer.
    previous_triggers = (previous or {}).get("content", {}).get("falsification_triggers") or []
    inferred_state = (previous["conditionResponse"] if previous and previous_triggers == content["falsification_triggers"]
                      else "written" if content["falsification_triggers"] else "unanswered")
    state = condition_state or inferred_state
    if state not in CONDITION_STATES:
        raise ValueError("invalid_condition_response")
    if state == "written" and not content["falsification_triggers"]:
        raise ValueError("written_condition_requires_text")
    if state != "written" and content["falsification_triggers"] and state != "legacy_unknown":
        # Existing triggers must never be silently relabeled as unknown/skipped.
        state = "written"
    presence = field_presence if field_presence is not None else (previous["fieldPresence"] if previous else {})
    refs = _normalize_refs(basis_refs) if basis_refs is not None else (previous["basisRefs"] if previous else [])
    stated_at = user_stated_at if user_stated_at is not None else (previous["userStatedAt"] if previous else "")
    digest = hashlib.sha256(_canonical({"content": content, "conditionResponse": state, "fieldPresence": presence,
                                        "basisRefs": refs, "userStatedAt": stated_at}).encode("utf-8")).hexdigest()
    if previous and previous["contentHash"] == digest:
        return previous
    revision_id = uuid.uuid4().hex
    connection.execute(
        """INSERT INTO reason_revision(revision_id,ticker,revision,previous_revision_id,content_hash,
            content_json,condition_state,field_presence_json,edit_source,kind_at_write,change_reason,user_stated_at,
            basis_refs_json,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            revision_id, ticker, (previous["revision"] + 1) if previous else 1,
            previous["revisionId"] if previous else "", digest, _canonical(content), state,
            _canonical(presence),
            edit_source, kind_at_write or _kind_at_write(connection, ticker),
            str(change_reason or "")[:500], str(stated_at or "")[:40],
            _canonical(refs), _now(),
        ),
    )
    return latest(connection, ticker) or {}
