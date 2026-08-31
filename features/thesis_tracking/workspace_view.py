"""종목 Thesis workspace projection — Watchlist 상세가 읽는 개인 판단 층.

**읽기 전용이다.** Thesis·Delta·체크포인트 판정은 각자의 소유자가 쓰고, 여기서는
저장된 것을 화면 순서(계획 C.2)대로 모으기만 한다.

    내 Thesis → 최신 검증 → 근거/반대근거 → 다음 확인 → 검토 이력

세 가지 경계를 payload가 직접 나른다.

- **판정 enum은 두 층이고 섞지 않는다**(§3.2): Delta verdict는 6값, 체크포인트 판정은
  3값이다. 한 배지로 합치지 않도록 서로 다른 키에 담고 라벨도 따로 준다.
- **소유권**(Stage B 리뷰 확정 1): thesis가 앱 소유(manual/native_note)인데 같은
  티커의 Vault `company_thesis` 노트가 있으면 Vault 동기화가 더 이상 이 행을 덮지
  않는다. 그 사실이 조용하면 사용자는 노트를 고쳐도 반영되지 않는 이유를 찾을 수 없다.
- **linked_regimes 전파**(A.3): thesis가 기대는 내러티브에 반증 신호가 있으면 알린다.
  **표시일 뿐 verdict를 바꾸지 않는다.**
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from features.common.research_schema.tracked_checkpoints import partition_checkpoints, squash
from features.thesis_tracking import model as M
from features.thesis_tracking import store as ST

CHECKPOINT_STATUS_LABELS = {
    "open": "확인 대기",
    "confirmed": "확인됨",
    "challenged": "반증 신호",
    "expired": "기한 경과",
}
VERDICT_LABELS = {
    "confirmed": "확인됨",
    "challenged": "반증",
    "no_signal": "신호 없음",
}
# 내러티브 반증 신호를 살아 있다고 볼 창. 계획 §4의 중기 본체(30일)와 같은 눈금이다.
REGIME_ALERT_WINDOW_DAYS = 30
MIN_EVIDENCE_SCORE = 0.5
HISTORY_LIMIT = 12
VAULT_OWNED_SOURCES = ST.VAULT_OWNED_SOURCES


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _date(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _checkpoint_projection(checkpoint: dict) -> dict:
    last = checkpoint.get("lastVerdict") or {}
    status = str(checkpoint.get("status") or "open")
    return {
        "id": checkpoint.get("id", ""),
        "item": checkpoint.get("item", ""),
        "direction": checkpoint.get("direction", ""),
        "status": status,
        "statusLabel": CHECKPOINT_STATUS_LABELS.get(status, status),
        "dueBy": checkpoint.get("dueBy"),
        "lastVerdict": {
            "verdict": last.get("verdict", ""),
            "verdictLabel": VERDICT_LABELS.get(str(last.get("verdict") or ""), ""),
            "at": last.get("at", ""),
            # thesis 근거 풀은 연구 인덱스 문서라 사본 키가 docId이고 role이 없다.
            "evidence": [
                {"date": str(item.get("date") or ""), "title": str(item.get("title") or "")}
                for item in (last.get("evidence") or [])[:3]
                if isinstance(item, dict)
            ],
        } if last else None,
        "history": [
            {
                "at": str(item.get("at") or ""),
                "from": str(item.get("from") or ""),
                "to": str(item.get("to") or ""),
                "verdict": str(item.get("verdict") or ""),
                "verdictLabel": VERDICT_LABELS.get(str(item.get("verdict") or ""), ""),
            }
            for item in (checkpoint.get("history") or [])
            if isinstance(item, dict)
        ],
    }


def _vault_note(conn, ticker: str) -> dict:
    """같은 티커의 Vault company_thesis 노트. 없으면 빈 dict."""
    try:
        row = conn.execute(
            """
            SELECT title, rel_path FROM obsidian_note_index
            WHERE note_type = 'company_thesis' AND UPPER(ticker) = ?
            ORDER BY last_seen DESC LIMIT 1
            """,
            (ticker,),
        ).fetchone()
    except Exception:
        return {}
    if not row:
        return {}
    return {"title": str(row["title"] or ""), "relPath": str(row["rel_path"] or "")}


def _ownership(thesis: dict, vault_note: dict) -> dict:
    source = str(thesis.get("source") or "")
    app_owned = source not in VAULT_OWNED_SOURCES
    sync_paused = bool(app_owned and vault_note)
    return {
        "source": source,
        "appOwned": app_owned,
        "vaultNote": vault_note or None,
        "syncPaused": sync_paused,
        "message": (
            "이 Thesis는 Vault에서 더 이상 갱신되지 않습니다. 앱에서 만든 내용이 우선이며, "
            "Vault 노트를 반영하려면 그 노트를 Thesis로 다시 등록하세요."
            if sync_paused else ""
        ),
    }


def _delta_projection(delta: dict | None) -> dict | None:
    if not delta:
        return None
    verdict = M.normalize_verdict(delta.get("verdict"))
    return {
        "deltaId": str(delta.get("deltaId") or ""),
        # 6값 enum이다. 체크포인트 판정(3값)과 한 배지로 합치지 않는다(§3.2).
        "verdict": verdict,
        "verdictLabel": M.VERDICT_LABELS.get(verdict, verdict),
        "generatedAt": str(delta.get("generatedAt") or ""),
        "period": str(delta.get("period") or ""),
        "summary": str(delta.get("summary") or ""),
        "supportingEvidence": _evidence_list(delta.get("supportingEvidence")),
        "counterEvidence": _evidence_list(delta.get("counterEvidence")),
        "contradictions": [str(x) for x in (delta.get("contradictions") or [])[:5]],
        "uncertainties": [str(x) for x in (delta.get("uncertainties") or [])[:5]],
    }


def _evidence_list(values) -> list:
    out = []
    for item in (values or [])[:5]:
        if isinstance(item, dict):
            out.append({
                "title": str(item.get("title") or "")[:220],
                "source": str(item.get("source") or "")[:80],
                "date": str(item.get("date") or "")[:10],
                "reason": str(item.get("reason") or "")[:400],
            })
        elif str(item).strip():
            out.append({"title": str(item)[:220], "source": "", "date": "", "reason": ""})
    return out


def _linked_state_ids(conn, thesis: dict, ticker: str) -> set:
    """thesis가 **선언한** 내러티브만 본다.

    자동 추론 링크(ticker 겹침 등)까지 끌어오면 사용자가 연결한 적 없는 내러티브의
    반증이 경고로 뜬다 — A.3은 "thesis가 기대는 내러티브"에 대한 전파다.
    """
    declared = {squash(x) for x in (thesis.get("linked_regimes") or []) if squash(x)}
    ids: set = set()
    try:
        rows = conn.execute(
            "SELECT state_id, state_key, state_label FROM market_narrative_states WHERE status IN ('active','watch')"
        ).fetchall()
    except Exception:
        return ids
    for row in rows:
        if squash(row["state_key"]) in declared or squash(row["state_label"]) in declared:
            ids.add(row["state_id"])
    try:
        links = conn.execute(
            """
            SELECT state_id FROM market_regime_thesis_links
            WHERE UPPER(thesis_ticker) = ? AND (relationship = 'linked_regimes' OR method = 'manual')
            """,
            (ticker,),
        ).fetchall()
        ids.update(row["state_id"] for row in links)
    except Exception:
        pass
    return ids


def _regime_alerts(conn, thesis: dict, ticker: str, *, today: dt.date) -> list:
    """연결된 내러티브의 반증 신호를 thesis 화면으로 전파한다(A.3).

    **표시일 뿐이다** — thesis verdict도 체크포인트 status도 이 함수가 바꾸지 않는다.
    """
    state_ids = _linked_state_ids(conn, thesis, ticker)
    if not state_ids:
        return []
    alerts = []
    for state_id in sorted(state_ids):
        row = conn.execute(
            "SELECT state_id, state_key, state_label, status, momentum FROM market_narrative_states WHERE state_id = ?",
            (state_id,),
        ).fetchone()
        if not row:
            continue
        reasons = []
        checkpoints = conn.execute(
            "SELECT next_checkpoints_json FROM market_narrative_states WHERE state_id = ?",
            (state_id,),
        ).fetchone()
        from features.market_memory.memory import parse_json_list

        structured, _invalid, _templates = partition_checkpoints(
            parse_json_list(checkpoints["next_checkpoints_json"]) if checkpoints else [],
            scope="narrative",
            scope_key=str(row["state_key"] or state_id),
            forbidden_keywords=[row["state_label"], row["state_key"]],
        )
        for checkpoint in structured:
            if checkpoint.get("status") == "challenged":
                reasons.append({"kind": "challenged_checkpoint", "detail": checkpoint.get("item", "")})
        challenging = conn.execute(
            """
            SELECT title, evidence_date FROM market_regime_evidence
            WHERE state_id = ? AND role = 'challenging' AND score >= ?
            ORDER BY evidence_date DESC LIMIT 3
            """,
            (state_id, MIN_EVIDENCE_SCORE),
        ).fetchall()
        for evidence in challenging:
            day = _date(evidence["evidence_date"])
            if day and (today - day).days <= REGIME_ALERT_WINDOW_DAYS:
                reasons.append({"kind": "challenging_evidence", "detail": str(evidence["title"] or "")})
        if not reasons:
            continue
        alerts.append({
            "stateId": row["state_id"],
            "stateKey": str(row["state_key"] or ""),
            "label": str(row["state_label"] or row["state_key"] or ""),
            "status": str(row["status"] or ""),
            "momentum": str(row["momentum"] or ""),
            "reasons": reasons[:4],
        })
    return alerts


def thesis_workspace_payload(ticker: str, db_path: str | Path | None = None, *, as_of: str = "") -> dict:
    """Watchlist 상세의 Personal 영역이 읽는 하나의 payload.

    Agent를 부르지 않고 저장된 projection만 읽는다(계획 C.2).
    """
    ticker = M.normalize_ticker(ticker)
    today = _date(as_of) or _now().date()
    empty = {
        "ticker": ticker,
        "hasThesis": False,
        "thesis": None,
        "ownership": None,
        "latestDelta": None,
        "checkpoints": {"structured": [], "templates": [], "unverifiableCount": 0, "counts": {}},
        "regimeAlerts": [],
        "deltaHistory": [],
        "layer": "hypothesis",
        "reuseAsEvidence": False,
    }
    if not ticker:
        return empty
    conn = ST.connect(db_path)
    try:
        thesis = ST.get_thesis(conn, ticker)
        if not thesis:
            # thesis가 없어도 Vault 노트 유무는 알려준다 — 만드는 경로 안내가 달라진다.
            empty["ownership"] = {"source": "", "appOwned": False, "vaultNote": _vault_note(conn, ticker) or None,
                                  "syncPaused": False, "message": ""}
            return empty
        structured, invalid, templates = partition_checkpoints(
            thesis.get("next_checkpoints"),
            scope="thesis",
            scope_key=ticker,
            forbidden_keywords=[ticker, thesis.get("company")],
        )
        checkpoints = [_checkpoint_projection(item) for item in structured]
        counts = {key: 0 for key in CHECKPOINT_STATUS_LABELS}
        for item in checkpoints:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        deltas = ST.list_deltas(conn, ticker, limit=HISTORY_LIMIT)
        return {
            "ticker": ticker,
            "hasThesis": True,
            "thesis": {
                "ticker": thesis["ticker"],
                "company": str(thesis.get("company") or ""),
                "coreThesis": str(thesis.get("core_thesis") or ""),
                "keyAssumptions": [str(x) for x in (thesis.get("key_assumptions") or [])[:8]],
                "supportingSignals": [str(x) for x in (thesis.get("supporting_signals") or [])[:8]],
                "weakeningSignals": [str(x) for x in (thesis.get("weakening_signals") or [])[:8]],
                "falsificationTriggers": [str(x) for x in (thesis.get("falsification_triggers") or [])[:8]],
                "keyMetrics": [str(x) for x in (thesis.get("key_metrics") or [])[:8]],
                "linkedRegimes": [str(x) for x in (thesis.get("linked_regimes") or [])[:8]],
                "reviewCycle": str(thesis.get("review_cycle") or ""),
                "conviction": str(thesis.get("conviction") or ""),
                "status": str(thesis.get("status") or ""),
                "lastReviewedAt": str(thesis.get("last_reviewed_at") or ""),
                "notePath": str(thesis.get("note_path") or ""),
            },
            "ownership": _ownership(thesis, _vault_note(conn, ticker)),
            "latestDelta": _delta_projection(deltas[0] if deltas else None),
            "checkpoints": {
                "structured": checkpoints,
                "templates": [str(x) for x in templates[:5]],
                "unverifiableCount": len(invalid),
                "counts": counts,
            },
            "regimeAlerts": _regime_alerts(conn, thesis, ticker, today=today),
            "deltaHistory": [
                {
                    "deltaId": str(item.get("deltaId") or ""),
                    "verdict": M.normalize_verdict(item.get("verdict")),
                    "verdictLabel": M.VERDICT_LABELS.get(M.normalize_verdict(item.get("verdict")), ""),
                    "generatedAt": str(item.get("generatedAt") or ""),
                    "summary": str(item.get("summary") or "")[:200],
                }
                for item in deltas
            ],
            "layer": "hypothesis",
            "reuseAsEvidence": False,
        }
    finally:
        conn.close()
