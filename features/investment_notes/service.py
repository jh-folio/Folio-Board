"""Native investment note storage.

Native notes are user hypothesis. They can be linked to reports, tickers, and
topics, but they must never be promoted to evidence.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import uuid
from pathlib import Path

from features.common.utils import now_iso, read_json, write_json
from features.investment_notes.checkpoints import (
    checkpoint_projection,
    normalize_checkpoint_fields,
)
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
NOTES_DIR = DATA_DIR / "investment-notes"
MARKET_MEMORY_DB_PATH = DATA_DIR / "market-memory.sqlite3"

NOTE_TYPES = {
    "investment_note",
    "company_thesis",
    "market_memo",
    "topic_review",
    "portfolio_decision",
    "checkpoint",
}


def _clean_text(value) -> str:
    return str(value or "").strip()


def _clean_ticker(value) -> str:
    # 규칙 소유자는 thesis 모델이다 — 노트 색인과 thesis PK가 join 키라 두 곳이 각자
    # 정규화하면 같은 회사가 두 행으로 갈라진다(0.6 Stage B 리뷰).
    from features.thesis_tracking.model import normalize_ticker

    return normalize_ticker(_clean_text(value))


def _clean_note_id(value) -> str:
    raw = _clean_text(value)
    return raw if re.fullmatch(r"[A-Za-z0-9_-]{1,96}", raw) else ""


def _clean_tags(values) -> list[str]:
    if isinstance(values, str):
        values = [x.strip() for x in values.split(",")]
    if not isinstance(values, list):
        return []
    tags: list[str] = []
    seen = set()
    for item in values:
        tag = _clean_text(item)
        key = tag.lower()
        if tag and key not in seen:
            tags.append(tag[:48])
            seen.add(key)
    return tags[:12]


def _clean_list(values) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    rows: list[str] = []
    seen = set()
    for item in values:
        text = _clean_text(item)
        key = text.lower()
        if text and key not in seen:
            rows.append(text[:160])
            seen.add(key)
    return rows[:20]


def _clean_note_events(values) -> list[dict]:
    if not isinstance(values, list):
        return []
    events: list[dict] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        role = _clean_text(item.get("role"))[:24] or "user"
        body = _clean_text(item.get("body"))
        if not body:
            continue
        event = {
            "role": role,
            "body": body[:8000],
            "createdAt": _clean_text(item.get("createdAt"))[:48] or now_iso(),
        }
        summary = _clean_text(item.get("summary"))
        if summary:
            event["summary"] = summary[:240]
        events.append(event)
    return events[-80:]


def _note_path(note_id: str, notes_dir: Path | None = None) -> Path:
    return (notes_dir or NOTES_DIR) / f"{note_id}.json"


def _note_id() -> str:
    return f"note-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or MARKET_MEMORY_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS native_note_index (
            note_id TEXT PRIMARY KEY,
            note_type TEXT NOT NULL,
            title TEXT NOT NULL,
            ticker TEXT NOT NULL DEFAULT '',
            company TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            layer TEXT NOT NULL DEFAULT 'hypothesis',
            source_layer TEXT NOT NULL DEFAULT 'user_synthesis',
            reuse_as_hypothesis INTEGER NOT NULL DEFAULT 1,
            reuse_as_evidence INTEGER NOT NULL DEFAULT 0,
            tags_json TEXT NOT NULL DEFAULT '[]',
            linked_reports_json TEXT NOT NULL DEFAULT '[]',
            path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_native_note_ticker ON native_note_index(ticker)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_native_note_topic ON native_note_index(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_native_note_type ON native_note_index(note_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_native_note_updated ON native_note_index(updated_at)")
    conn.commit()


def normalize_note(payload: dict | None, existing: dict | None = None) -> dict:
    payload = payload or {}
    existing = existing or {}
    now = now_iso()
    note_type = _clean_text(payload.get("noteType") or payload.get("note_type") or existing.get("noteType"))
    if note_type not in NOTE_TYPES:
        note_type = "investment_note"
    note_id = _clean_note_id(payload.get("id") or payload.get("noteId") or existing.get("id")) or _note_id()
    body = _clean_text(payload.get("body") if "body" in payload else existing.get("body"))
    title = _clean_text(payload.get("title") or existing.get("title"))
    ticker = _clean_ticker(payload.get("ticker") if "ticker" in payload else existing.get("ticker"))
    company = _clean_text(payload.get("company") if "company" in payload else existing.get("company"))
    topic = _clean_text(payload.get("topic") if "topic" in payload else existing.get("topic"))
    label = _clean_text(payload.get("label") or company or ticker or topic)
    if not title:
        title = label or "투자 노트"
    linked_reports = _clean_list(payload.get("linkedReports") or payload.get("linked_reports") or existing.get("linkedReports"))
    report_kind = _clean_text(payload.get("reportKind") or existing.get("reportKind"))
    report_id = _clean_text(payload.get("reportId") or existing.get("reportId"))
    consultation_ref = _clean_text(payload.get("consultationRef") or existing.get("consultationRef"))[:96]
    if report_id and report_id not in linked_reports:
        linked_reports.append(report_id)
    note = {
        "id": note_id,
        "noteType": note_type,
        "title": title[:160],
        "body": body,
        "rawThoughts": _clean_note_events(payload.get("rawThoughts") if "rawThoughts" in payload else existing.get("rawThoughts")),
        "interactionLog": _clean_note_events(payload.get("interactionLog") if "interactionLog" in payload else existing.get("interactionLog")),
        "ticker": ticker,
        "company": company[:120],
        "topic": topic[:160],
        "label": label[:160],
        "tags": _clean_tags(payload.get("tags") if "tags" in payload else existing.get("tags")),
        "linkedReports": linked_reports,
        "reportKind": report_kind,
        "reportId": report_id,
        "status": _clean_text(payload.get("status") or existing.get("status") or "active")[:32],
        "layer": "hypothesis",
        "sourceLayer": "user_consultation" if consultation_ref else "user_synthesis",
        "reuseAsHypothesis": True,
        "reuseAsEvidence": False,
        "consultationRef": consultation_ref,
        "createdAt": existing.get("createdAt") or now,
        "updatedAt": now,
    }
    if note_type == "checkpoint":
        note.update(normalize_checkpoint_fields(payload, existing))
    return note


def public_note(note: dict, *, include_body: bool = True, clock=None) -> dict:
    row = dict(note)
    if row.get("noteType") == "checkpoint":
        clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        row = checkpoint_projection(row, clock=clock)
    if not include_body:
        body = row.pop("body", "") or ""
        row["summary"] = body.replace("\n", " ").strip()[:180]
    return row


def _upsert_index(conn: sqlite3.Connection, note: dict, path: Path) -> None:
    conn.execute(
        """
        INSERT INTO native_note_index
          (note_id, note_type, title, ticker, company, topic, status, layer, source_layer,
           reuse_as_hypothesis, reuse_as_evidence, tags_json, linked_reports_json, path,
           created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(note_id) DO UPDATE SET
          note_type=excluded.note_type,
          title=excluded.title,
          ticker=excluded.ticker,
          company=excluded.company,
          topic=excluded.topic,
          status=excluded.status,
          layer=excluded.layer,
          source_layer=excluded.source_layer,
          reuse_as_hypothesis=excluded.reuse_as_hypothesis,
          reuse_as_evidence=excluded.reuse_as_evidence,
          tags_json=excluded.tags_json,
          linked_reports_json=excluded.linked_reports_json,
          path=excluded.path,
          updated_at=excluded.updated_at
        """,
        (
            note["id"],
            note["noteType"],
            note["title"],
            note["ticker"],
            note["company"],
            note["topic"],
            note["status"],
            note["layer"],
            note["sourceLayer"],
            1,
            0,
            json.dumps(note["tags"], ensure_ascii=False),
            json.dumps(note["linkedReports"], ensure_ascii=False),
            str(path),
            note["createdAt"],
            note["updatedAt"],
        ),
    )
    conn.commit()


def save_note(payload: dict | None, *, db_path: Path | None = None) -> dict:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    raw_id = _clean_note_id((payload or {}).get("id") or (payload or {}).get("noteId"))
    if raw_id and _note_path(raw_id).exists():
        existing = read_json(_note_path(raw_id), {})
    note = normalize_note(payload, existing)
    path = _note_path(note["id"])
    write_json(path, note)
    conn = connect(db_path)
    try:
        _upsert_index(conn, note, path)
    finally:
        conn.close()
    # company_thesis 노트는 thesis 레지스트리의 빈자리를 자동으로 채운다(0.6 §8.2).
    # 이미 thesis가 있으면 덮지 않는다 — 갱신은 명시적 action뿐이다. 실패해도
    # 노트 저장을 되돌리지 않는다(등록은 노트의 부가물이다).
    if note.get("noteType") == "company_thesis" and note.get("ticker"):
        from features.thesis_tracking.native_notes import link_note_on_save

        # thesis 레지스트리는 이 노트 색인과 **같은 DB**에 있다 — 호출자가 준 경로를
        # 그대로 넘긴다. 레지스트리 기본 경로를 따로 열면 임시 DB로 격리한 호출자
        # (테스트 포함)가 실제 워크스페이스에 쓰게 된다.
        link_note_on_save(note, db_path=db_path or MARKET_MEMORY_DB_PATH)
    return public_note(note)


def get_note(note_id: str, *, notes_dir: Path | None = None, clock=None) -> dict:
    # Same rule as the write path: an ID is one file name inside the notes folder.
    note_id = _clean_note_id(note_id)
    if not note_id:
        return {}
    note = read_json(_note_path(note_id, notes_dir), {})
    return public_note(note, clock=clock) if isinstance(note, dict) and note else {}


def _row_to_note(row: sqlite3.Row, *, include_body: bool = False, clock=None) -> dict:
    saved = read_json(Path(row["path"]), {})
    note = {
        "id": row["note_id"],
        "noteType": row["note_type"],
        "title": row["title"],
        "ticker": row["ticker"],
        "company": row["company"],
        "topic": row["topic"],
        "status": row["status"],
        "layer": row["layer"],
        "sourceLayer": row["source_layer"],
        "reuseAsHypothesis": bool(row["reuse_as_hypothesis"]),
        "reuseAsEvidence": bool(row["reuse_as_evidence"]),
        "tags": json.loads(row["tags_json"] or "[]"),
        "linkedReports": json.loads(row["linked_reports_json"] or "[]"),
        "path": row["path"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    if include_body:
        note.update({k: saved.get(k, note.get(k, "")) for k in ("body", "label", "reportKind", "reportId", "consultationRef")})
    else:
        note["summary"] = str(saved.get("body") or "").replace("\n", " ").strip()[:180]
    if note["noteType"] == "checkpoint":
        note.update(normalize_checkpoint_fields(saved))
        note = checkpoint_projection(
            note,
            clock=clock or (lambda: dt.datetime.now(dt.timezone.utc)),
        )
    return note


def _sync_files_to_index(conn: sqlite3.Connection) -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    for path in NOTES_DIR.glob("*.json"):
        note = read_json(path, {})
        if isinstance(note, dict) and note.get("id"):
            row = normalize_note(note, note)
            # 목록 조회는 읽기 경로다. `normalize_note`는 updatedAt에 언제나 현재 시각을
            # 박으므로 파일에 남은 값을 되돌린다 — 안 그러면 목록을 여는 것만으로 전 노트의
            # 수정 시각이 조회 시각으로 덮이고 `ORDER BY updated_at`이 glob 순서(파일명순)로
            # 격하돼 방금 수정한 노트가 위로 오지 않는다.
            saved_updated = _clean_text(note.get("updatedAt"))
            if saved_updated:
                row["updatedAt"] = saved_updated
            _upsert_index(conn, row, path)


def list_notes(
    *,
    ticker: str = "",
    topic: str = "",
    note_type: str = "",
    q: str = "",
    limit: int = 50,
    include_body: bool = False,
    db_path: Path | None = None,
    clock=None,
) -> list[dict]:
    conn = connect(db_path)
    try:
        _sync_files_to_index(conn)
        sql = "SELECT * FROM native_note_index WHERE reuse_as_evidence=0"
        args: list = []
        if ticker:
            sql += " AND ticker=?"
            args.append(_clean_ticker(ticker))
        if topic:
            sql += " AND lower(topic)=lower(?)"
            args.append(_clean_text(topic))
        if note_type:
            sql += " AND note_type=?"
            args.append(_clean_text(note_type))
        if q:
            sql += " AND (lower(title) LIKE ? OR lower(company) LIKE ? OR lower(topic) LIKE ? OR lower(ticker) LIKE ?)"
            needle = f"%{_clean_text(q).lower()}%"
            args.extend([needle, needle, needle, needle])
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(max(1, min(int(limit or 50), 200)))
        return [
            _row_to_note(row, include_body=include_body, clock=clock)
            for row in conn.execute(sql, args).fetchall()
        ]
    finally:
        conn.close()


def linked_notes_payload(*, ticker: str = "", topic: str = "", report_id: str = "") -> dict:
    notes = list_notes(ticker=ticker, topic=topic, limit=100)
    if report_id:
        rid = _clean_text(report_id)
        notes = [n for n in notes if rid in (n.get("linkedReports") or []) or not n.get("linkedReports")]
    return {"ok": True, "count": len(notes), "notes": notes[:20]}


def add_note(payload: dict | None) -> dict:
    payload = payload or {}
    note = {
        **payload,
        "noteType": payload.get("noteType") or "investment_note",
        "company": payload.get("company") or payload.get("label") or "",
        "title": payload.get("title") or "투자 메모",
    }
    return save_note(note)
