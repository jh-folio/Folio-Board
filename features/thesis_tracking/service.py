"""Thesis Tracking 서비스 — Obsidian company_thesis 노트 동기화 + 조회 + Delta.

- Vault의 `company_thesis` 노트를 읽어 thesis 레지스트리에 적재한다(Obsidian importer 재사용).
- thesis는 사용자 가설이다. self_generated 노트는 Obsidian importer 분류에서 이미 제외된다.
- Delta는 로컬 뉴스 인덱스 evidence와 thesis를 대조해 별도 시계열로 저장한다.
"""
from __future__ import annotations

from pathlib import Path
import re

from features.obsidian.importer.service import scan_vault, list_hypotheses
from features.obsidian.export.formatter import build_frontmatter, preserve_user_notes
from features.obsidian.export.service import get_vault_settings
from features.llm_settings.client import bool_override
from features.common.utils import now_iso
from features.thesis_tracking import delta as D
from features.thesis_tracking import model as M
from features.thesis_tracking import review_state as RS
from features.thesis_tracking import store as ST


def sync_theses_from_vault(db_path=None) -> dict:
    """Vault를 스캔해 company_thesis 노트를 thesis 레지스트리에 동기화한다."""
    summary = {"scanned_notes": 0, "theses_upserted": 0, "skipped_no_ticker": 0}
    try:
        scan_vault(db_path=db_path)
    except Exception:
        pass
    try:
        notes = list_hypotheses(db_path=db_path)
    except Exception:
        notes = []
    conn = ST.connect(db_path)
    try:
        for note in notes:
            if note.get("note_type") != "company_thesis":
                continue
            summary["scanned_notes"] += 1
            path = note.get("path")
            if not path:
                summary["skipped_no_ticker"] += 1
                continue
            try:
                text = Path(path).read_text(encoding="utf-8")
            except Exception:
                continue
            thesis = M.parse_thesis_text(text, note_path=path, source="obsidian")
            if not thesis.ticker:
                summary["skipped_no_ticker"] += 1
                continue
            ST.upsert_thesis(conn, thesis)
            summary["theses_upserted"] += 1
        return summary
    finally:
        conn.close()


def list_theses(db_path=None, status=None) -> list:
    conn = ST.connect(db_path)
    try:
        return ST.list_theses(conn, status=status)
    finally:
        conn.close()


def get_thesis(ticker: str, db_path=None):
    conn = ST.connect(db_path)
    try:
        return ST.get_thesis(conn, ticker)
    finally:
        conn.close()


def get_thesis_review_state(ticker: str, db_path=None, *, now=None) -> dict:
    """Return stored review state or a non-persisted legacy-safe projection."""
    conn = ST.connect(db_path)
    try:
        thesis = ST.get_thesis(conn, ticker)
        if not thesis:
            return RS.empty_review_state(ticker).model_dump(mode="json")
        stored = RS.load_review_state(conn, thesis["ticker"])
        if stored.revision > 0:
            return stored.model_dump(mode="json")
        return RS.state_from_thesis(thesis, now=now).model_dump(mode="json")
    finally:
        conn.close()


def list_thesis_payload(db_path=None, status=None, *, sync: bool = True) -> dict:
    """API payload for thesis registry list."""
    if sync:
        try:
            sync_theses_from_vault(db_path=db_path)
        except Exception:
            pass
    rows = list_theses(db_path=db_path, status=status)
    return {"theses": rows, "count": len(rows)}


def thesis_detail_payload(ticker: str, db_path=None, *, sync: bool = True, history_limit: int = 8) -> dict:
    """API payload for one thesis plus recent Delta history."""
    if sync:
        try:
            sync_theses_from_vault(db_path=db_path)
        except Exception:
            pass
    conn = ST.connect(db_path)
    try:
        thesis = ST.get_thesis(conn, ticker)
        if not thesis:
            return {"ticker": str(ticker or "").upper(), "thesis": None, "latestDelta": None, "history": []}
        history = ST.list_deltas(conn, thesis["ticker"], limit=history_limit)
        latest = history[0] if history else None
        return {"ticker": thesis["ticker"], "thesis": thesis, "latestDelta": latest, "history": history}
    finally:
        conn.close()


def upsert_manual_thesis(data: dict, db_path=None) -> dict:
    """UI 직접 입력 thesis 저장(Obsidian 의존 없음)."""
    thesis = M.Thesis(
        ticker=str(data.get("ticker", "") or "").strip().upper(),
        company=str(data.get("company", "") or "").strip(),
        core_thesis=str(data.get("core_thesis", "") or "").strip(),
        key_assumptions=M._as_list(data.get("key_assumptions")),
        supporting_signals=M._as_list(data.get("supporting_signals")),
        weakening_signals=M._as_list(data.get("weakening_signals")),
        falsification_triggers=M._as_list(data.get("falsification_triggers")),
        # dict(구조화 체크포인트)는 이 경로로 오면 안 된다 — `_as_list`가 repr 문자열로
        # 바꿔 영구 템플릿으로 굳는다. 구조화 생성·갱신은 전용 병합 경로(Stage B)가
        # 맡고, 저장된 dict는 store.upsert_thesis의 보존 병합이 지킨다.
        next_checkpoints=M._as_list(
            [x for x in (data.get("next_checkpoints") or []) if not isinstance(x, dict)]
            if isinstance(data.get("next_checkpoints"), (list, tuple)) else data.get("next_checkpoints")
        ),
        key_metrics=M._as_list(data.get("key_metrics")),
        linked_regimes=M._as_list(data.get("linked_regimes")),
        review_cycle=M.normalize_review_cycle(data.get("review_cycle")),
        conviction=M.normalize_conviction(data.get("conviction")),
        status=M.normalize_status(data.get("status")),
        source="manual",
    )
    if not thesis.ticker:
        raise ValueError("ticker는 필수입니다.")
    conn = ST.connect(db_path)
    try:
        ST.upsert_thesis(conn, thesis)
        return ST.get_thesis(conn, thesis.ticker)
    finally:
        conn.close()


def run_thesis_delta(ticker: str, body: dict | None = None, db_path=None) -> dict:
    """Generate or export a Thesis Delta for one ticker.

    body:
      period: 30d | 90d | since_last_review | since_last_note | last_earnings
      useLlm: optional bool-ish override
      exportObsidian: optional bool; when true, writes the resulting/latest delta note
      reuseLatest: optional bool; when true and exportObsidian is true, does not regenerate
    """
    body = body or {}
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        raise ValueError("ticker는 필수입니다.")
    conn = ST.connect(db_path)
    try:
        thesis = ST.get_thesis(conn, ticker)
        if not thesis:
            raise LookupError(f"Thesis not found: {ticker}")
        export_obsidian = bool(body.get("exportObsidian"))
        if export_obsidian and body.get("reuseLatest"):
            latest = ST.latest_delta(conn, ticker)
            if not latest:
                raise LookupError(f"Thesis Delta not found: {ticker}")
            exported = export_thesis_delta_to_obsidian(thesis, latest)
            return {"ok": True, "status": "exported", "thesis": thesis, "delta": latest, "export": exported}

        delta, status = D.generate_delta(
            thesis,
            period=D.normalize_period(body.get("period")),
            llm_override=bool_override(body.get("useLlm")),
            evidence_limit=int(body.get("limit") or 12),
        )
        delta["company"] = thesis.get("company", "")
        saved = ST.save_delta(conn, ticker, delta)
        RS.record_completed_review(conn, thesis, saved)
        exported = None
        if export_obsidian:
            exported = export_thesis_delta_to_obsidian(thesis, saved)
        return {"ok": True, "status": status, "thesis": thesis, "delta": saved, "export": exported}
    finally:
        conn.close()


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|#^[\]]', "", name).strip()


def _require_vault_path() -> Path:
    settings = get_vault_settings()
    vault_path = str(settings.get("vaultPath", "") or "").strip()
    if not vault_path:
        raise ValueError("Obsidian vault 경로가 설정되지 않았습니다.")
    path = Path(vault_path)
    if not path.exists():
        raise ValueError(f"Vault 경로가 존재하지 않습니다: {vault_path}")
    return path


def export_thesis_delta_to_obsidian(thesis: dict, delta: dict) -> dict:
    """Write a self-generated thesis_delta note to the configured Vault."""
    vault = _require_vault_path()
    folder = vault / "Thesis Delta"
    folder.mkdir(parents=True, exist_ok=True)
    ticker = thesis.get("ticker") or delta.get("ticker") or "UNKNOWN"
    generated = str(delta.get("generatedAt") or now_iso())[:10]
    verdict = delta.get("verdict", M.VERDICT_DEFAULT)
    meta = {
        "type": "thesis_delta",
        "generated_by": "Folio OS",
        "source_layer": "primary_processed",
        "reuse_as_evidence": False,
        "ticker": ticker,
        "company": thesis.get("company") or None,
        "date": generated,
        "verdict": verdict,
        "period": delta.get("period") or "90d",
        "delta_id": delta.get("deltaId") or None,
    }
    title = f"# {ticker} Thesis Delta — {generated}"
    body = delta.get("markdown") or D.build_markdown(thesis, delta, delta.get("evidence") or [], delta)
    new_body = f"{build_frontmatter(meta)}\n\n{title}\n\n{body}"
    filename = _safe_filename(f"{ticker} Thesis Delta {generated}") + ".md"
    note_path = folder / filename
    existing = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    note_path.write_text(preserve_user_notes(existing, new_body), encoding="utf-8")
    return {"ok": True, "path": str(note_path), "filename": filename}
