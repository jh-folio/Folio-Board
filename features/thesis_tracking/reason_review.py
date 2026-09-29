"""Explicit review completions tied to an immutable reason revision."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid

from features.thesis_tracking import reason_history as RH
from features.thesis_tracking import store as ST

OUTCOMES = frozenset({"reviewed", "no_material_change", "no_new_material", "evidence_gap",
                      "collection_failed", "unsupported", "deferred"})


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS reason_review_event (
        event_id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        reason_revision_id TEXT NOT NULL,
        source TEXT NOT NULL,
        outcome TEXT NOT NULL,
        checked_scope_json TEXT NOT NULL DEFAULT '[]',
        basis_refs_json TEXT NOT NULL DEFAULT '[]',
        delta_id TEXT NOT NULL DEFAULT '',
        reviewed_at TEXT NOT NULL,
        FOREIGN KEY(reason_revision_id) REFERENCES reason_revision(revision_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS reason_review_ticker_revision ON reason_review_event(ticker,reason_revision_id,reviewed_at DESC)")


def _public(row: sqlite3.Row) -> dict:
    data = dict(row)
    return {"eventId": data["event_id"], "ticker": data["ticker"],
            "reasonRevisionId": data["reason_revision_id"], "source": data["source"],
            "outcome": data["outcome"], "checkedScope": json.loads(data["checked_scope_json"]),
            "basisRefs": json.loads(data["basis_refs_json"]), "deltaId": data["delta_id"],
            "reviewedAt": data["reviewed_at"]}


def recent(conn: sqlite3.Connection, ticker: str, revision_id: str, *, limit: int = 10) -> list[dict]:
    rows = conn.execute("SELECT * FROM reason_review_event WHERE ticker=? AND reason_revision_id=? "
                        "ORDER BY reviewed_at DESC, event_id DESC LIMIT ?", (ticker, revision_id, limit)).fetchall()
    return [_public(row) for row in rows]


def status_for_reason(conn: sqlite3.Connection, ticker: str, revision_id: str | None, has_text: bool) -> tuple[str, list[dict]]:
    if not has_text or not revision_id:
        return "unwritten", []
    events = recent(conn, ticker, revision_id)
    completed = next((event for event in events if event["source"] in {"manual_review", "explicit_delta"}), None)
    if completed is None:
        return "unreviewed", events
    return ("evidence_gap" if completed["outcome"] in {"evidence_gap", "no_new_material", "collection_failed", "unsupported", "deferred"}
            else "reviewed"), events


def record(conn: sqlite3.Connection, ticker: str, revision_id: str, *, source: str,
           outcome: str, checked_scope: list[str], basis_refs: list | None = None,
           delta_id: str = "", event_id: str = "") -> dict:
    if outcome not in OUTCOMES:
        raise ValueError("invalid_review_outcome")
    if not RH.get(conn, revision_id) or RH.get(conn, revision_id)["ticker"] != ticker:
        raise ValueError("invalid_reason_revision")
    ensure_schema(conn)
    identifier = event_id or uuid.uuid4().hex
    checked = [str(value).strip()[:120] for value in checked_scope if str(value).strip()][:10]
    refs = basis_refs if isinstance(basis_refs, list) else []
    conn.execute("""INSERT OR IGNORE INTO reason_review_event
        (event_id,ticker,reason_revision_id,source,outcome,checked_scope_json,basis_refs_json,delta_id,reviewed_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (identifier, ticker, revision_id, source, outcome,
         json.dumps(checked, ensure_ascii=False), json.dumps(refs[:20], ensure_ascii=False),
         delta_id, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")))
    row = conn.execute("SELECT * FROM reason_review_event WHERE event_id=?", (identifier,)).fetchone()
    return _public(row)


def complete_manual_review(ticker: str, body: dict | None = None, *, db_path=None) -> dict:
    request = body if isinstance(body, dict) else {}
    conn = ST.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = ST.get_thesis(conn, ticker)
        if not current:
            raise LookupError("reason_not_found")
        revision = RH.latest(conn, current["ticker"])
        expected = request.get("expectedRevisionId")
        if not isinstance(expected, str) or expected != (revision or {}).get("revisionId"):
            raise RH.ReasonRevisionConflictError(revision)
        if not current.get("core_thesis"):
            raise ValueError("reason_required")
        scope = request.get("checkedScope")
        if not isinstance(scope, list) or not any(str(item).strip() for item in scope) or any(not isinstance(item, str) for item in scope):
            raise ValueError("invalid_checked_scope")
        result = record(conn, current["ticker"], expected, source="manual_review",
                        outcome=str(request.get("outcome") or ""), checked_scope=scope,
                        basis_refs=request.get("basisRefs"))
        from features.thesis_tracking import review_state as RS
        previous = RS.load_review_state(conn, current["ticker"])
        cycle_given = (revision or {}).get("fieldPresence", {}).get("review_cycle") is True
        next_at = RS.derive_next_review_at(result["reviewedAt"], current.get("review_cycle")) if cycle_given else None
        state = RS.ReviewState(
            ticker=RS._ticker(current["ticker"]),
            lastReviewedAt=result["reviewedAt"], nextReviewAt=next_at,
            latestDeltaId=previous.latestDeltaId,
            freshness=RS.derive_freshness(next_at, current.get("review_cycle")),
            checkpoints=previous.checkpoints, revision=previous.revision,
            updatedAt=result["reviewedAt"],
        )
        RS.save_review_state(conn, state, expected_revision=previous.revision, commit=False)
        conn.commit()
        return result
    finally:
        conn.close()
