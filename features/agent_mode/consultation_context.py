"""Server-authoritative, bounded consultation context assembly."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path

from features.agent_mode.consultation_store import get_session
from features.common.change_intelligence.projection import list_change_events
from features.common.research_library.signals.service import default_db_path, query_signals
from features.common.utils import read_json
from features.market_memory.verification_view import narrative_verification_payload
from features.portfolio.service import get_portfolio
from features.thesis_tracking.workspace_view import thesis_workspace_payload
from features.watchlist_notes.service import get_watchlist

MAX_CONTEXT_CHARS = 32_000
CHALLENGE_MAX_CHECKPOINTS = 8
CHALLENGE_MAX_EVIDENCE = 6
CHALLENGE_MAX_TIMELINE = 8
CHALLENGE_MAX_ALERTS = 6
CHALLENGE_TEXT_LIMIT = 420
CHALLENGE_EVIDENCE_WINDOW_DAYS = 90


def _clip(value: object, limit: int = CHALLENGE_TEXT_LIMIT) -> str:
    return str(value or "").strip()[:limit]


def _gap(scope: str, identifier: str, reason: str) -> dict:
    """선택 항목을 못 읽으면 전체 맥락으로 넓히지 않는 정직한 data gap."""
    return {
        "dataGaps": [{"scope": scope, "id": _clip(identifier, 120), "reason": reason}],
        "evidenceWindow": {"days": CHALLENGE_EVIDENCE_WINDOW_DAYS, "maxItems": CHALLENGE_MAX_EVIDENCE},
        "layer": "source-grounded",
    }


def _evidence_anchor(value: object = "") -> date:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return datetime.now(timezone.utc).date()


def _inside_evidence_window(value: object, anchor: date) -> bool:
    try:
        observed = date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return False
    return anchor.fromordinal(anchor.toordinal() - (CHALLENGE_EVIDENCE_WINDOW_DAYS - 1)) <= observed <= anchor


def _challenge_checkpoint(item: dict, *, anchor: date) -> tuple[dict, int]:
    last = item.get("lastVerdict") or {}
    evidence = []
    excluded = 0
    for row in (last.get("evidence") or [])[:CHALLENGE_MAX_EVIDENCE * 4]:
        if not isinstance(row, dict) or not _inside_evidence_window(row.get("date"), anchor):
            excluded += 1
            continue
        if len(evidence) < CHALLENGE_MAX_EVIDENCE:
            evidence.append({"date": _clip(row.get("date"), 20), "title": _clip(row.get("title"), 220), "role": _clip(row.get("role"), 32)})
    return {
        "id": _clip(item.get("id"), 120), "item": _clip(item.get("item")),
        "direction": _clip(item.get("direction"), 32), "status": _clip(item.get("status"), 32),
        "dueBy": _clip(item.get("dueBy"), 20), "lastVerdict": {"verdict": _clip(last.get("verdict"), 32), "at": _clip(last.get("at"), 32), "evidence": evidence} if last else None,
    }, excluded


def _challenge_evidence(values, *, anchor: date) -> tuple[list, int]:
    out = []
    excluded = 0
    for row in (values or [])[:CHALLENGE_MAX_EVIDENCE * 4]:
        if not isinstance(row, dict) or not _inside_evidence_window(row.get("date"), anchor):
            excluded += 1
            continue
        if len(out) < CHALLENGE_MAX_EVIDENCE:
            out.append({
                "title": _clip(row.get("title"), 220), "source": _clip(row.get("source"), 80),
                "date": _clip(row.get("date"), 20), "reason": _clip(row.get("reason")),
            })
    return out, excluded


def _challenge_alerts(values) -> list:
    out = []
    for row in (values or [])[:CHALLENGE_MAX_ALERTS]:
        if not isinstance(row, dict):
            continue
        out.append({
            "stateId": _clip(row.get("stateId"), 120), "label": _clip(row.get("label")),
            "status": _clip(row.get("status"), 32), "momentum": _clip(row.get("momentum"), 32),
            "reasons": [{"kind": _clip(reason.get("kind"), 40), "detail": _clip(reason.get("detail"))}
                        for reason in (row.get("reasons") or [])[:CHALLENGE_MAX_EVIDENCE] if isinstance(reason, dict)],
        })
    return out


def _narrative_challenge_context(data_dir: Path, scope: dict) -> dict:
    state_id = str(scope.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", state_id):
        return _gap("market_memory", state_id, "선택한 내러티브 식별자가 없거나 형식이 맞지 않습니다.")
    payload = narrative_verification_payload(
        Path(data_dir) / "market-memory.sqlite3",
        limit=1,
        state_id=state_id,
    )
    selected = next((row for row in payload.get("states") or [] if str(row.get("stateId") or "") == state_id), None)
    if not isinstance(selected, dict):
        return _gap("market_memory", state_id, "선택한 내러티브가 없거나 더 이상 활성·관찰 상태가 아닙니다.")
    anchor = _evidence_anchor(payload.get("asOf"))
    checkpoints = []
    excluded_evidence = 0
    for row in (selected.get("checkpoints") or [])[:CHALLENGE_MAX_CHECKPOINTS]:
        if not isinstance(row, dict):
            continue
        checkpoint, excluded = _challenge_checkpoint(row, anchor=anchor)
        checkpoints.append(checkpoint)
        excluded_evidence += excluded
    counter = [checkpoint for checkpoint in checkpoints if checkpoint.get("direction") == "challenging"][:CHALLENGE_MAX_EVIDENCE]
    timeline = [
        {"at": _clip(row.get("at"), 32), "kind": _clip(row.get("kind"), 32), "from": _clip(row.get("from"), 80), "to": _clip(row.get("to"), 80), "reason": _clip(row.get("reason"))}
        for row in (selected.get("timeline") or [])[:CHALLENGE_MAX_TIMELINE] if isinstance(row, dict)
    ]
    return {
        "selectedNarrative": {
            "stateId": state_id, "label": _clip(selected.get("label")), "status": _clip(selected.get("status"), 32),
            "momentum": _clip(selected.get("momentum"), 32), "evidenceCounts": dict(selected.get("evidenceCounts") or {}),
            "lastEvidenceAt": _clip(selected.get("lastEvidenceAt"), 20), "silence": selected.get("silence") or {},
            "checkpoints": checkpoints, "counterEvidence": counter, "timeline": timeline, "layer": "source-grounded",
        },
        "evidenceWindow": {"days": CHALLENGE_EVIDENCE_WINDOW_DAYS, "maxItems": CHALLENGE_MAX_EVIDENCE},
        "dataGaps": ([{"scope": "market_memory", "id": state_id,
                       "reason": f"90일 근거 창에서 날짜가 없거나 범위를 벗어난 근거 {excluded_evidence}건을 제외했습니다."}]
                     if excluded_evidence else []),
    }


def _thesis_challenge_context(data_dir: Path, scope: dict) -> dict:
    ticker = str(scope.get("id") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9._-]{1,24}", ticker):
        return _gap("watchlist", ticker, "선택한 Thesis 티커가 없거나 형식이 맞지 않습니다.")
    payload = thesis_workspace_payload(ticker, Path(data_dir) / "market-memory.sqlite3")
    thesis = payload.get("thesis") if isinstance(payload, dict) else None
    if not payload.get("hasThesis") or not isinstance(thesis, dict):
        return _gap("watchlist", ticker, "선택한 종목에 저장된 Thesis가 없습니다.")
    latest = payload.get("latestDelta") if isinstance(payload.get("latestDelta"), dict) else None
    anchor = _evidence_anchor((latest or {}).get("generatedAt"))
    supporting, excluded_supporting = _challenge_evidence((latest or {}).get("supportingEvidence"), anchor=anchor)
    counter, excluded_counter = _challenge_evidence((latest or {}).get("counterEvidence"), anchor=anchor)
    checkpoints = []
    excluded_checkpoints = 0
    for row in ((payload.get("checkpoints") or {}).get("structured") or [])[:CHALLENGE_MAX_CHECKPOINTS]:
        if not isinstance(row, dict):
            continue
        checkpoint, excluded = _challenge_checkpoint(row, anchor=anchor)
        checkpoints.append(checkpoint)
        excluded_checkpoints += excluded
    verification = {
        "layer": "source-grounded",
        "latestDelta": {
            "verdict": _clip(latest.get("verdict"), 32), "generatedAt": _clip(latest.get("generatedAt"), 32),
            "summary": _clip(latest.get("summary")),
            "supportingEvidence": supporting,
            "counterEvidence": counter,
            "contradictions": [_clip(row) for row in (latest.get("contradictions") or [])[:CHALLENGE_MAX_EVIDENCE]],
            "uncertainties": [_clip(row) for row in (latest.get("uncertainties") or [])[:CHALLENGE_MAX_EVIDENCE]],
        } if latest else None,
        "checkpoints": checkpoints,
        "linkedAlerts": _challenge_alerts(payload.get("regimeAlerts")),
    }
    gaps = [] if latest else [{"scope": "watchlist", "id": ticker, "reason": "최신 Thesis 검증 결과가 아직 없습니다."}]
    excluded_evidence = excluded_supporting + excluded_counter + excluded_checkpoints
    if excluded_evidence:
        gaps.append({"scope": "watchlist", "id": ticker,
                     "reason": f"90일 근거 창에서 날짜가 없거나 범위를 벗어난 근거 {excluded_evidence}건을 제외했습니다."})
    return {
        "selectedThesis": {
            "ticker": ticker,
            "hypothesis": {
                "layer": "hypothesis", "reuseAsEvidence": False,
                "coreThesis": _clip(thesis.get("coreThesis"), 1200),
                "keyAssumptions": [_clip(row) for row in (thesis.get("keyAssumptions") or [])[:CHALLENGE_MAX_CHECKPOINTS]],
                "falsificationTriggers": [_clip(row) for row in (thesis.get("falsificationTriggers") or [])[:CHALLENGE_MAX_CHECKPOINTS]],
            },
            "verification": verification,
        },
        "evidenceWindow": {"days": CHALLENGE_EVIDENCE_WINDOW_DAYS, "maxItems": CHALLENGE_MAX_EVIDENCE},
        "dataGaps": gaps,
    }


def _report(data_dir: Path, scope: dict) -> dict:
    kind = scope.get("kind")
    report_id = str(scope.get("id") or "")
    directory = {"briefing": "briefings", "company_analysis": "company-analysis", "topic_report": "topic-reports"}.get(kind)
    if not directory or not re.fullmatch(r"[A-Za-z0-9가-힣._:-]{1,160}", report_id) or ".." in report_id:
        return {}
    root = Path(data_dir) / directory
    candidates = [root / f"{report_id}.json"] + list(root.glob(f"{report_id}.*.json"))
    for path in candidates:
        value = read_json(path, {})
        if isinstance(value, dict) and value:
            return {
                "kind": kind,
                "id": value.get("id") or report_id,
                "title": value.get("title") or value.get("headline") or "",
                "generatedAt": value.get("generatedAt") or value.get("date") or "",
                "changeSummary": value.get("changeSummary") or {},
                "checkpoints": (value.get("checkpoints") or [])[:20],
                "dataGaps": (value.get("dataGaps") or [])[:12],
                "markdownExcerpt": str(value.get("markdown") or "")[:12_000],
                "layer": "source-grounded",
            }
    return {}


def _market_state(data_dir: Path) -> dict:
    path = Path(data_dir) / "market-memory.sqlite3"
    if not path.exists():
        return {}
    try:
        with sqlite3.connect(str(path)) as connection:
            row = connection.execute("SELECT payload_json FROM market_state_snapshots ORDER BY as_of DESC LIMIT 1").fetchone()
        payload = json.loads(row[0]) if row else {}
    except (sqlite3.Error, json.JSONDecodeError):
        return {}
    return {
        "id": payload.get("id") or payload.get("stateId") or "",
        "asOf": payload.get("asOf") or payload.get("createdAt") or "",
        "marketRegime": payload.get("marketRegime") or payload.get("regime") or "",
        "keyDrivers": (payload.get("keyDrivers") or [])[:12],
        "counterEvidence": (payload.get("counterEvidence") or [])[:12],
        "uncertainties": (payload.get("uncertainties") or [])[:12],
        "layer": "source-grounded",
    }


def _scope_context(data_dir: Path, session: dict) -> dict:
    scope = session.get("scope") or {}
    tickers = [str(ticker).upper() for ticker in scope.get("tickers") or []]
    if scope.get("kind") == "market_memory" and scope.get("intent") == "challenge":
        return _narrative_challenge_context(data_dir, scope)
    if scope.get("kind") == "watchlist" and scope.get("intent") == "challenge":
        return _thesis_challenge_context(data_dir, scope)
    if scope.get("kind") == "investment_review" and scope.get("intent") == "challenge":
        # Re-read this exact dated snapshot for every Agent turn.  A revision
        # mismatch is deliberately a narrow gap, not a generic Portfolio
        # fallback that could make the challenge silently change its target.
        from features.investment_review.review_v2 import challenge_context
        from features.investment_review.service import REVIEW_DIR
        return challenge_context(data_dir, REVIEW_DIR, str(scope.get("id") or ""), scope.get("revision"))
    if scope.get("kind") == "portfolio":
        portfolio = get_portfolio(data_dir)
        if not tickers:
            tickers = [str(row.get("ticker") or row.get("symbol") or "").upper() for row in portfolio.get("positions") or []]
        primary = {"portfolio": {"revision": portfolio.get("revision"), "positions": (portfolio.get("positions") or [])[:40], "cash": (portfolio.get("cash") or [])[:10], "layer": "hypothesis_input"}}
    elif scope.get("kind") == "watchlist":
        watchlist = get_watchlist(data_dir)
        if not tickers:
            tickers = [str(item).upper() for item in watchlist[:30]]
        primary = {"watchlist": watchlist[:40], "layer": "hypothesis_input"}
    else:
        report = _report(data_dir, scope)
        primary = {"report": report} if report else {}
    # 실사용 확인(2026-09-16): 종목·보고서·주제가 전혀 없는 순수 시장 질문("요즘
    # 시장 어때" 류)도 여전히 marketState/recentChanges를 근거로 삼을 수 있다 —
    # 둘 다 티커와 무관하게 이미 상한(최대 12~20개)이 걸린 요약값이라 붙여도
    # 프롬프트 부담이 크지 않다. 이전에는 이 둘까지 완전히 비워 답이 얕아졌다.
    # fastSignals는 티커별 조회라 정말로 아무 티커도 없으면 낼 것이 없다.
    changes = list_change_events(Path(data_dir) / "market-memory.sqlite3", limit=20)
    result = {
        **primary,
        "marketState": _market_state(data_dir),
        "recentChanges": changes[:20],
    }
    if tickers:
        signals = []
        for ticker in tickers[:8]:
            signals.extend(query_signals(default_db_path(data_dir), ticker=ticker, limit=5).get("items") or [])
        result["fastSignals"] = signals[:20]
        result["signalNotice"] = "fastSignals are unconfirmed metadata-only leads and are not evidence"
    return result


def assemble_consultation_context(data_dir: Path, session_id: str, *, current_message_id: str = "") -> dict:
    started = time.perf_counter()
    session = get_session(data_dir, session_id)
    if not session:
        raise KeyError("consultation_not_found")
    messages = session.get("messages") or []
    if current_message_id:
        # The caller's own question is already the newest saved message (the
        # route persists it before the job runs) and is passed to the prompt
        # separately — including it here too would repeat it verbatim.
        messages = [row for row in messages if row.get("id") != current_message_id]
    # `_update_memory()` (consultation_store.py) only ever summarizes
    # `messages[:-12]` once it fires, so once that summary exists the last 12
    # is exactly the window it does *not* cover. Without a summary yet, keep
    # the older wider window — nothing has been condensed away to duplicate.
    recent_window = 12 if str((session.get("memory") or {}).get("summary") or "").strip() else 20
    scope = session.get("scope") or {}
    rules = {
        "canonicalWriteback": False, "proposalIntent": False, "noteActionOnly": True, "consultationIsEvidence": False,
    }
    review_challenge = scope.get("kind") == "investment_review" and scope.get("intent") == "challenge"
    if scope.get("intent") == "challenge":
        rules["challenge"] = {
            "mustAddress": ["counterEvidence", "contradictions", "uncertainties", "source reliability", "materiality"],
            "noRecommendation": True, "noWriteback": True,
        }
        if review_challenge:
            # Unlike Thesis/Narrative challenge, this scope deliberately
            # re-reads one immutable saved review and does not refresh a 90d
            # evidence window. Do not imply that it did.
            rules["challenge"]["savedSnapshotOnly"] = True
        else:
            rules["challenge"].update({"evidenceWindowDays": CHALLENGE_EVIDENCE_WINDOW_DAYS,
                                       "maxEvidenceItems": CHALLENGE_MAX_EVIDENCE})
    pack = {
        "schemaVersion": 1,
        "session": {"id": session["id"], "scope": session.get("scope") or {}, "title": session.get("title") or ""},
        "consultationMemory": {**(session.get("memory") or {}), "layer": "hypothesis", "sourceLayer": "user_consultation", "reuseAsEvidence": False},
        "recentMessages": [{"role": row.get("role"), "content": str(row.get("content") or "")[:6000], "sourceLayer": row.get("sourceLayer"), "reuseAsEvidence": False} for row in messages[-recent_window:]],
        "sourceContext": _scope_context(Path(data_dir), session),
        "rules": rules,
    }
    serialized = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    if review_challenge and len(serialized) > MAX_CONTEXT_CHARS:
        # The roster/date/revision/coverage are the exact-scope contract.
        # Sacrifice conversational memory and optional detail first; never
        # replace sourceContext with the generic over-budget notice.
        pack["consultationMemory"]["summary"] = str(pack["consultationMemory"].get("summary") or "")[-500:]
        pack["recentMessages"] = [{**row, "content": str(row.get("content") or "")[:1000]}
                                  for row in pack["recentMessages"][-4:]]
        review = (pack.get("sourceContext") or {}).get("investmentReview") or {}
        if isinstance(review, dict):
            review["positionReviews"] = list(review.get("positionReviews") or [])[:8]
            review["sharedExposures"] = list(review.get("sharedExposures") or [])[:6]
            review["portfolioRisks"] = list(review.get("portfolioRisks") or [])[:6]
            review["counterEvidence"] = list(review.get("counterEvidence") or [])[:6]
            pack.setdefault("sourceContext", {}).setdefault("dataGaps", []).append({
                "code": "context_detail_truncated", "reason": "정확한 저장 리뷰의 전체 roster와 revision을 보존하기 위해 대화·상세 일부를 줄였습니다.",
            })
        serialized = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    if review_challenge and len(serialized) > MAX_CONTEXT_CHARS:
        # Last exact-scope reduction: preserve only immutable identity,
        # coverage, roster and core counter-evidence.  This must never use the
        # generic sourceContext replacement below, which would silently erase
        # the target of the user's challenge.
        review = (pack.get("sourceContext") or {}).get("investmentReview") or {}
        protected = {
            "date": review.get("date"), "reviewRevision": review.get("reviewRevision"),
            "reviewState": review.get("reviewState"), "coverage": review.get("coverage") or {},
            "positionRoster": list(review.get("positionRoster") or [])[:100],
            "counterEvidence": list(review.get("counterEvidence") or [])[:6],
        }
        pack["sourceContext"] = {"investmentReview": protected,
                                 "dataGaps": [{"code": "context_detail_truncated", "reason": "정확한 저장 리뷰의 최소 roster와 핵심 반증만 유지했습니다."}]}
        pack["consultationMemory"]["summary"] = ""
        pack["recentMessages"] = []
        serialized = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_CONTEXT_CHARS and not review_challenge:
        report = (pack.get("sourceContext") or {}).get("report") or {}
        if isinstance(report, dict):
            report["markdownExcerpt"] = str(report.get("markdownExcerpt") or "")[:3000]
        pack["recentMessages"] = pack["recentMessages"][-10:]
        serialized = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_CONTEXT_CHARS and not review_challenge:
        pack["sourceContext"]["fastSignals"] = []
        pack["sourceContext"]["recentChanges"] = (pack["sourceContext"].get("recentChanges") or [])[:5]
        pack["consultationMemory"]["summary"] = str(pack["consultationMemory"].get("summary") or "")[-1500:]
        pack["recentMessages"] = pack["recentMessages"][-5:]
        serialized = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_CONTEXT_CHARS and not review_challenge:
        pack["sourceContext"] = {"notice": "source context exceeded bound; ask a narrower follow-up", "signalNotice": "fast signals are not evidence"}
        pack["consultationMemory"]["summary"] = str(pack["consultationMemory"].get("summary") or "")[-500:]
        pack["recentMessages"] = [{**row, "content": str(row.get("content") or "")[:2000]} for row in pack["recentMessages"][-4:]]
        serialized = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    return {
        "pack": pack,
        "serialized": serialized,
        "telemetry": {"assemblyMs": round((time.perf_counter() - started) * 1000, 2), "serializedChars": len(serialized)},
    }
