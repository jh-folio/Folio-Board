"""Thesis 레지스트리 저장소 — market-memory.sqlite3에 thesis 테이블을 둔다.

지식그래프 데이터(티커별 조회·시계열·교차링크)이므로 별도 파일을 만들지 않고
market-memory.sqlite3를 확장한다(IMPLEMENTATION_PLAN §1·§4).

키 정책: ticker 1개당 thesis 1개(PK=ticker). 같은 ticker 노트가 여러 개면 마지막 동기화가 이긴다.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from features.thesis_tracking import model as M
from features.common.research_schema.checkpoints import checkpoints_from_thesis_delta
from features.common.research_schema.evidence import evidence_items_from_list
from features.common.research_schema.source_ledger import source_ledger_from_items
from features.common.sqlite_receipts import ensure_receipt_table
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = data_dir() / "market-memory.sqlite3"


def connect(db_path=None) -> sqlite3.Connection:
    if db_path == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        path = Path(db_path or DEFAULT_DB)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thesis (
            ticker TEXT PRIMARY KEY,
            company TEXT NOT NULL DEFAULT '',
            core_thesis TEXT NOT NULL DEFAULT '',
            key_assumptions_json TEXT NOT NULL DEFAULT '[]',
            supporting_signals_json TEXT NOT NULL DEFAULT '[]',
            weakening_signals_json TEXT NOT NULL DEFAULT '[]',
            falsification_triggers_json TEXT NOT NULL DEFAULT '[]',
            next_checkpoints_json TEXT NOT NULL DEFAULT '[]',
            key_metrics_json TEXT NOT NULL DEFAULT '[]',
            linked_regimes_json TEXT NOT NULL DEFAULT '[]',
            review_cycle TEXT NOT NULL DEFAULT 'quarterly',
            conviction TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT NOT NULL DEFAULT 'obsidian',
            note_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            last_reviewed_at TEXT NOT NULL DEFAULT '',
            first_seen TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thesis_status ON thesis(status)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS thesis_delta (
            delta_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            company TEXT NOT NULL DEFAULT '',
            generated_at TEXT NOT NULL DEFAULT '',
            period TEXT NOT NULL DEFAULT '90d',
            period_days INTEGER NOT NULL DEFAULT 90,
            verdict TEXT NOT NULL DEFAULT 'insufficient_evidence',
            source TEXT NOT NULL DEFAULT 'local_news_index',
            summary TEXT NOT NULL DEFAULT '',
            analysis_json TEXT NOT NULL DEFAULT '{}',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(ticker) REFERENCES thesis(ticker) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thesis_delta_ticker_time ON thesis_delta(ticker, generated_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_thesis_delta_verdict ON thesis_delta(verdict)")
    ensure_receipt_table(conn)
    from features.thesis_tracking.review_state import ensure_schema as ensure_review_state_schema

    ensure_review_state_schema(conn)
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    """Backward-compatible schema entrypoint."""
    ensure_schema(conn)


_LIST_COLS = {
    "key_assumptions": "key_assumptions_json",
    "supporting_signals": "supporting_signals_json",
    "weakening_signals": "weakening_signals_json",
    "falsification_triggers": "falsification_triggers_json",
    "next_checkpoints": "next_checkpoints_json",
    "key_metrics": "key_metrics_json",
    "linked_regimes": "linked_regimes_json",
}


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def upsert_thesis(conn, thesis: M.Thesis) -> str:
    """Thesis를 ticker 기준으로 upsert. ticker 반환.

    `next_checkpoints`는 통째로 덮지 않는다 — 저장돼 있던 **구조화 체크포인트(dict)는
    보존**하고 들어온 문자열 목록만 갈아끼운다. Thesis 모델은 문자열 리스트라 노트
    재동기화(`get_thesis_bundle`이 읽을 때마다 돈다)가 덮어쓰면 판정 status·이력이
    매 조회마다 증발한다 — `refresh_regime_state`에서 고친 것과 같은 결함의 thesis판.
    """
    from features.common.research_schema.tracked_checkpoints import merge_with_templates

    row = thesis.to_row()
    ticker = row["ticker"]
    if not ticker:
        raise ValueError("thesis.ticker가 비어 있습니다.")
    now = _now()
    existing = conn.execute(
        "SELECT first_seen, next_checkpoints_json FROM thesis WHERE ticker=?", (ticker,)
    ).fetchone()
    first_seen = existing["first_seen"] if existing else now
    try:
        stored_checkpoints = json.loads(existing["next_checkpoints_json"]) if existing else []
    except Exception:
        stored_checkpoints = []
    row["next_checkpoints"] = merge_with_templates(
        stored_checkpoints,
        [x for x in row.get("next_checkpoints") or [] if isinstance(x, str)],
        scope="thesis",
        scope_key=ticker,
    )
    values = {
        "ticker": ticker,
        "company": row["company"],
        "core_thesis": row["core_thesis"],
        "review_cycle": row["review_cycle"],
        "conviction": row["conviction"],
        "status": row["status"],
        "source": row["source"],
        "note_path": row["note_path"],
        "created_at": row["created_at"],
        "last_reviewed_at": row["last_reviewed_at"],
        "first_seen": first_seen,
        "updated_at": now,
    }
    for field_name, col in _LIST_COLS.items():
        values[col] = json.dumps(row[field_name], ensure_ascii=False)
    cols = list(values.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("ticker", "first_seen"))
    conn.execute(
        f"INSERT INTO thesis ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(ticker) DO UPDATE SET {updates}",
        [values[c] for c in cols],
    )
    conn.commit()
    return ticker


def save_thesis_checkpoints(conn, ticker: str, checkpoints: list) -> None:
    """`next_checkpoints_json`만 제자리 교체한다(판정 pass 전용).

    `upsert_thesis`를 쓰지 않는 것은 그쪽이 문자열 목록을 받는 노트 동기화 경로라서다.
    판정은 dict 원소의 `status`·`history`만 바꾸므로 나머지 필드를 건드릴 이유가 없고,
    **`last_reviewed_at`은 절대 바꾸지 않는다** — 기계 판정은 사용자의 검토가 아니다.
    """
    conn.execute(
        "UPDATE thesis SET next_checkpoints_json=?, updated_at=? WHERE ticker=?",
        (json.dumps(checkpoints, ensure_ascii=False), _now(), str(ticker or "").upper()),
    )
    conn.commit()


def _row_to_dict(row) -> dict:
    d = dict(row)
    for field_name, col in _LIST_COLS.items():
        try:
            d[field_name] = json.loads(d.pop(col, "[]"))
        except Exception:
            d.pop(col, None)
            d[field_name] = []
    return d


def list_theses(conn, *, status=None) -> list:
    q = "SELECT * FROM thesis"
    args: list = []
    if status is not None:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY updated_at DESC, ticker ASC"
    return [_row_to_dict(r) for r in conn.execute(q, args).fetchall()]


def get_thesis(conn, ticker: str):
    row = conn.execute("SELECT * FROM thesis WHERE ticker=?", (str(ticker or "").upper(),)).fetchone()
    return _row_to_dict(row) if row else None


def _delta_id(ticker: str, generated_at: str) -> str:
    import hashlib
    raw = f"{ticker}:{generated_at}:{_now()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def save_delta(
    conn,
    ticker: str,
    delta: dict,
    *,
    commit: bool = True,
    created_at: str | None = None,
) -> dict:
    """Persist one Thesis Delta row and return the stored row."""
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        raise ValueError("ticker는 필수입니다.")
    generated_at = str(delta.get("generatedAt") or _now())
    delta_id = str(delta.get("deltaId") or _delta_id(ticker, generated_at))
    analysis = dict(delta or {})
    evidence = analysis.pop("evidence", []) or []
    analysis["deltaId"] = delta_id
    analysis["ticker"] = ticker
    analysis["checkpoints"] = checkpoints_from_thesis_delta({**analysis, "evidence": evidence}, artifact_id=delta_id)
    if not analysis.get("evidenceItems"):
        analysis["evidenceItems"] = evidence_items_from_list(evidence, artifact_type="thesis_delta", artifact_id=delta_id)
    else:
        for item in analysis["evidenceItems"]:
            if isinstance(item, dict) and not item.get("artifactId"):
                item["artifactId"] = delta_id
    if not analysis.get("sourceLedger"):
        analysis["sourceLedger"] = source_ledger_from_items(analysis["evidenceItems"], artifact_type="thesis_delta", artifact_id=delta_id)
    else:
        for item in analysis["sourceLedger"]:
            if isinstance(item, dict) and not item.get("artifactId"):
                item["artifactId"] = delta_id
    conn.execute(
        """
        INSERT INTO thesis_delta (
            delta_id, ticker, company, generated_at, period, period_days, verdict,
            source, summary, analysis_json, evidence_json, created_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            delta_id,
            ticker,
            str(delta.get("company") or ""),
            generated_at,
            str(delta.get("period") or "90d"),
            int(delta.get("periodDays") or 90),
            M.normalize_verdict(delta.get("verdict")),
            str(delta.get("evidenceSource") or "local_news_index"),
            str(delta.get("summary") or ""),
            json.dumps(analysis, ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False),
            created_at or _now(),
        ),
    )
    if commit:
        conn.commit()
    return get_delta(conn, delta_id) or {**analysis, "evidence": evidence}


def _delta_row_to_dict(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    try:
        analysis = json.loads(d.get("analysis_json") or "{}")
    except Exception:
        analysis = {}
    try:
        evidence = json.loads(d.get("evidence_json") or "[]")
    except Exception:
        evidence = []
    analysis.update({
        "deltaId": d.get("delta_id", ""),
        "ticker": d.get("ticker", ""),
        "company": d.get("company", ""),
        "generatedAt": d.get("generated_at", ""),
        "period": d.get("period", ""),
        "periodDays": d.get("period_days", 0),
        "verdict": M.normalize_verdict(d.get("verdict")),
        "verdictLabel": M.VERDICT_LABELS.get(M.normalize_verdict(d.get("verdict")), M.VERDICT_LABELS[M.VERDICT_DEFAULT]),
        "evidenceSource": d.get("source", ""),
        "summary": d.get("summary", ""),
        "evidence": evidence,
        "createdAt": d.get("created_at", ""),
    })
    return analysis


def get_delta(conn, delta_id: str):
    row = conn.execute("SELECT * FROM thesis_delta WHERE delta_id=?", (str(delta_id or ""),)).fetchone()
    return _delta_row_to_dict(row) if row else None


def latest_delta(conn, ticker: str):
    row = conn.execute(
        "SELECT * FROM thesis_delta WHERE ticker=? ORDER BY generated_at DESC, created_at DESC LIMIT 1",
        (str(ticker or "").upper(),),
    ).fetchone()
    return _delta_row_to_dict(row) if row else None


def list_deltas(conn, ticker: str, limit: int = 10) -> list:
    rows = conn.execute(
        "SELECT * FROM thesis_delta WHERE ticker=? ORDER BY generated_at DESC, created_at DESC LIMIT ?",
        (str(ticker or "").upper(), int(limit or 10)),
    ).fetchall()
    return [_delta_row_to_dict(row) for row in rows]
