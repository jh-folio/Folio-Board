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
from features.common.self_reference import GENERATED_BY_MARKER
from features.thesis_tracking import delta as D
from features.thesis_tracking import model as M
from features.thesis_tracking import review_state as RS
from features.thesis_tracking import store as ST
from features.common.jobs import (
    diagnostic_execution,
    diagnostic_stage,
    diagnostic_stage_end,
    diagnostic_stage_failure,
    diagnostic_stage_start,
)


def sync_theses_from_vault(db_path=None) -> dict:
    """Vault를 스캔해 company_thesis 노트를 thesis 레지스트리에 동기화한다."""
    summary = {"scanned_notes": 0, "theses_upserted": 0, "skipped_no_ticker": 0, "skipped_not_owned": 0}
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
            # **Vault는 자기가 만든 thesis만 덮는다.** 이 동기화는 thesis를 열 때마다
            # 도는 경로라(`thesis_detail_payload(sync=True)`), 소유자를 보지 않으면
            # 앱 안에서 만든 thesis가 같은 티커의 옛 Vault 노트로 조용히 되돌아간다.
            # 빈자리는 예전처럼 자동으로 채운다(§8.2와 같은 규칙).
            existing = ST.get_thesis(conn, thesis.ticker)
            if existing and str(existing.get("source") or "") not in ST.VAULT_OWNED_SOURCES:
                summary["skipped_not_owned"] += 1
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


_MANUAL_FIELD_ALIASES = {
    "company": ("company",),
    "core_thesis": ("core_thesis", "coreThesis"),
    "key_assumptions": ("key_assumptions", "keyAssumptions"),
    "supporting_signals": ("supporting_signals", "supportingSignals"),
    "weakening_signals": ("weakening_signals", "weakeningSignals"),
    "falsification_triggers": ("falsification_triggers", "falsificationTriggers"),
    "next_checkpoints": ("next_checkpoints", "nextCheckpoints"),
    "key_metrics": ("key_metrics", "keyMetrics"),
    "linked_regimes": ("linked_regimes", "linkedRegimes"),
    "review_cycle": ("review_cycle", "reviewCycle"),
    "conviction": ("conviction",),
    "status": ("status",),
}


def _manual_field(data: dict, field: str, existing: dict):
    """보낸 키만 덮는다(부분 갱신).

    전체 폼을 통째로 받는 API로 두면 한 칸만 고치는 화면·호출자가 나머지를 빈 값으로
    지운다 — 명시적 action이 곧 손실 없는 action은 아니다.
    """
    for key in _MANUAL_FIELD_ALIASES[field]:
        if key in data:
            return data[key], True
    return existing.get(field), False


def upsert_manual_thesis(data: dict, db_path=None) -> dict:
    """UI 직접 입력 thesis 저장(Obsidian 의존 없음).

    `source="manual"`로 기록되며, 이후 Vault 동기화는 이 행을 덮지 않는다
    (`store.VAULT_OWNED_SOURCES`).
    """
    data = data or {}
    ticker = M.normalize_ticker(data.get("ticker"))
    if not ticker:
        raise ValueError("ticker는 필수이며 형식이 올바라야 합니다.")
    conn = ST.connect(db_path)
    try:
        existing = ST.get_thesis(conn, ticker) or {}
        raw_checkpoints, _ = _manual_field(data, "next_checkpoints", existing)
        thesis = M.Thesis(
            ticker=ticker,
            company=str(_manual_field(data, "company", existing)[0] or "").strip()[:120],
            core_thesis=str(_manual_field(data, "core_thesis", existing)[0] or "").strip()[:4000],
            key_assumptions=M._as_list(_manual_field(data, "key_assumptions", existing)[0]),
            supporting_signals=M._as_list(_manual_field(data, "supporting_signals", existing)[0]),
            weakening_signals=M._as_list(_manual_field(data, "weakening_signals", existing)[0]),
            falsification_triggers=M._as_list(_manual_field(data, "falsification_triggers", existing)[0]),
            # dict(구조화 체크포인트)는 이 경로로 오면 안 된다 — `_as_list`가 repr 문자열로
            # 바꿔 영구 템플릿으로 굳는다. 구조화 생성·갱신은 전용 병합 경로가 맡고,
            # 저장된 dict는 store.upsert_thesis의 보존 병합이 지킨다.
            next_checkpoints=M._as_list(
                [x for x in (raw_checkpoints or []) if not isinstance(x, dict)]
                if isinstance(raw_checkpoints, (list, tuple)) else raw_checkpoints
            ),
            key_metrics=M._as_list(_manual_field(data, "key_metrics", existing)[0]),
            linked_regimes=M._as_list(_manual_field(data, "linked_regimes", existing)[0]),
            review_cycle=M.normalize_review_cycle(_manual_field(data, "review_cycle", existing)[0]),
            conviction=M.normalize_conviction(_manual_field(data, "conviction", existing)[0]),
            status=M.normalize_status(_manual_field(data, "status", existing)[0]),
            # **부분 갱신은 소유권을 옮기지 않는다.** source는 VAULT_OWNED_SOURCES의
            # 판정 키라, 여기서 무조건 "manual"로 덮으면 Obsidian 소유 thesis의 확신도
            # 한 칸을 고친 것만으로 Vault 동기화가 영구히 끊긴다(되돌리는 UI도 없다).
            # 소유권 이전은 명시적 승격(`이 노트로 Thesis 갱신`)만 한다.
            source=str(existing.get("source") or "manual"),
            # 원본 노트 참조는 잃지 않는다 — 노트에서 승격된 thesis를 화면에서 한 칸
            # 고쳤다고 출처가 사라지면 안 된다.
            note_path=str(existing.get("note_path") or ""),
            created_at=str(existing.get("created_at") or ""),
            last_reviewed_at=str(existing.get("last_reviewed_at") or ""),
        )
        ST.upsert_thesis(conn, thesis)
        return ST.get_thesis(conn, thesis.ticker)
    finally:
        conn.close()


def promote_note_to_thesis(note_id: str, *, overwrite: bool = False, db_path=None) -> dict:
    """네이티브 노트를 Thesis로 등록하거나 갱신한다(명시적 action, §8.2).

    노트 저장 훅은 빈자리만 채운다. 이미 있는 thesis를 노트 내용으로 덮는 것은
    사용자가 여기를 눌렀을 때뿐이다 — 그리고 **덮겠다는 의사는 요청이 실어야 한다**
    (`overwrite`, 기본 False). 기본을 덮기로 두면 화면이 마지막으로 읽은 캐시가
    "thesis 없음"인 채로 다른 탭·Vault 동기화가 만든 thesis를 확인 없이 덮는다
    (2026-08-30 리뷰). overwrite 없이 기존 행을 만나면 `skipped_existing`으로
    돌아가고, 화면이 그때 확인을 받아 다시 부른다.
    """
    from features.investment_notes import service as note_service
    from features.thesis_tracking import native_notes as NN

    note = note_service.get_note(str(note_id or ""))
    if not note:
        raise LookupError(f"Note not found: {note_id}")
    if str(note.get("noteType") or "") != NN.NOTE_TYPE:
        raise ValueError("company_thesis 노트만 Thesis로 등록할 수 있습니다.")
    if not str(note.get("ticker") or "").strip():
        raise ValueError("노트에 종목 코드가 없어 Thesis로 등록할 수 없습니다.")
    result = NN.register_thesis_from_note(note, db_path=db_path, overwrite=overwrite)
    return {"ok": True, "noteId": note.get("id", ""), **result}


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
    export_obsidian = bool(body.get("exportObsidian"))
    reuse_latest = export_obsidian and bool(body.get("reuseLatest"))
    conn = None
    try:
        with diagnostic_stage("context"):
            conn = ST.connect(db_path)
            thesis = ST.get_thesis(conn, ticker)
            if not thesis:
                raise LookupError(f"Thesis not found: {ticker}")
            if reuse_latest:
                latest = ST.latest_delta(conn, ticker)
                if not latest:
                    raise LookupError(f"Thesis Delta not found: {ticker}")
            else:
                period = D.normalize_period(body.get("period"))
                evidence, evidence_meta = D.gather_local_evidence(
                    thesis, period=period, limit=int(body.get("limit") or 12),
                )

        if reuse_latest:
            # Re-exporting a durable delta writes a Vault artifact but invokes
            # no generation engine.  Keep the authority reads above separate
            # from this real persistence boundary.
            diagnostic_execution(final_engine="none")
            commit_recorder, commit_stage = diagnostic_stage_start("commit")
            try:
                exported = export_thesis_delta_to_obsidian(thesis, latest)
            except Exception as error:
                diagnostic_stage_failure(
                    commit_recorder, error, stage_id=commit_stage,
                    stage_code="commit" if commit_stage is not None else None,
                    boundary="save",
                )
                diagnostic_stage_end(commit_recorder, commit_stage, "commit")
                raise
            diagnostic_stage_end(commit_recorder, commit_stage, "commit")
            return {"ok": True, "status": "exported", "thesis": thesis, "delta": latest, "export": exported}

        generate_recorder, generate_stage = diagnostic_stage_start("generate")
        try:
            delta, status = D.generate_delta(
                thesis,
                period=period,
                llm_override=bool_override(body.get("useLlm")),
                evidence_limit=int(body.get("limit") or 12),
                prepared_evidence=evidence,
                prepared_meta=evidence_meta,
            )
        except Exception as error:
            diagnostic_stage_failure(
                generate_recorder, error, stage_id=generate_stage,
                stage_code="generate" if generate_stage is not None else None,
                boundary="generic",
            )
            diagnostic_stage_end(generate_recorder, generate_stage, "generate")
            raise
        diagnostic_stage_end(generate_recorder, generate_stage, "generate")
        delta["company"] = thesis.get("company", "")
        commit_recorder, commit_stage = diagnostic_stage_start("commit")
        try:
            saved = ST.save_delta(conn, ticker, delta)
            RS.record_completed_review(conn, thesis, saved)
            exported = None
            if export_obsidian:
                exported = export_thesis_delta_to_obsidian(thesis, saved)
        except Exception as error:
            diagnostic_stage_failure(
                commit_recorder, error, stage_id=commit_stage,
                stage_code="commit" if commit_stage is not None else None,
                boundary="save",
            )
            diagnostic_stage_end(commit_recorder, commit_stage, "commit")
            raise
        diagnostic_stage_end(commit_recorder, commit_stage, "commit")
        return {"ok": True, "status": status, "thesis": thesis, "delta": saved, "export": exported}
    finally:
        if conn is not None:
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
        "generated_by": GENERATED_BY_MARKER,
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
