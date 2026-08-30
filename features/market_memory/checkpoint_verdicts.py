"""체크포인트 판정 pass — 저장해 둔 "다음 확인"을 새 근거와 대조한다.

자료 수집 뒤(`run_rss_market_memory_update`의 `refresh_all_regimes` 다음)에 돈다.
**LLM을 부르지 않는다.** 판정은 `confirmed | challenged | no_signal` enum이며
자유 텍스트 결론을 만들지 않는다(§5 원칙 4).

같은 날 두 번 돌아도 안전하다 — `lastVerdict.at` 이후의 근거만 보므로 중복 판정이
없고, verdict가 **바뀔 때만** 이력을 남긴다.

**판정은 기록이지 상태 전환이 아니다.** 내러티브의 status/momentum은 기존 규칙이
계속 소유하고, 이 pass는 체크포인트 자신의 status만 바꾼다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from features.common.research_schema.tracked_checkpoints import (
    CHECKPOINT_STATUS_DEFAULT,
    MAX_EVIDENCE_COPIES,
    append_history,
    split_checkpoints,
    squash,
)
from features.market_memory.memory import connect, init_db, parse_json_list

MIN_EVIDENCE_SCORE = 0.5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _opposite(direction: str) -> str:
    return "challenging" if direction == "supporting" else "supporting"


def _haystack(row: dict) -> str:
    parts = [row.get("title"), row.get("summary")] + list(row.get("matchedTerms") or [])
    return squash(" ".join(str(p or "") for p in parts))


def _matched_term_keys(row: dict) -> set:
    return {squash(term) for term in (row.get("matchedTerms") or []) if squash(term)}


def matches_checkpoint(checkpoint: dict, row: dict) -> bool:
    """keyword는 제목+요약+matchedTerms에 공백 제거 부분일치, ticker는 matchedTerms에 있으면 hit.

    ticker를 본문에서 찾지 않는 것은 의도다 — 세 글자 티커가 한국어 본문에 우연히
    걸리면 그 회사와 무관한 기사가 확인 신호가 된다.
    """
    matchers = checkpoint.get("matchers") or {}
    haystack = _haystack(row)
    for keyword in matchers.get("keywords") or []:
        key = squash(keyword)
        if key and key in haystack:
            return True
    terms = _matched_term_keys(row)
    for ticker in matchers.get("tickers") or []:
        key = squash(ticker)
        if key and key in terms:
            return True
    return False


def _watermark(checkpoint: dict) -> str:
    last = checkpoint.get("lastVerdict") or {}
    return str(last.get("at") or checkpoint.get("createdAt") or "")[:10]


def evaluate_checkpoint(checkpoint: dict, evidence_rows: list, *, as_of: str = "") -> dict:
    """한 체크포인트를 근거 행들과 대조해 verdict와 근거 사본을 만든다.

    과잉 판정 방지 4겹:
      ① `neutral` role은 절대 세지 않는다 — 실측 898행 중 364행이 neutral이라
         이걸 세면 매일 confirmed가 된다.
      ② role이 direction과 정합하는 행만 확인 신호로 센다.
      ③ `score >= 0.5`만 센다(실측 실사용 근거는 0.71~1.0).
      ④ 같은 pass에서 양방향이 모두 hit이면 **challenged 우선** — 확증편향 방지는
         반증에 우선권을 준다(§5 원칙 3).
    """
    direction = checkpoint.get("direction")
    watermark = _watermark(checkpoint)
    aligned: list = []
    opposed: list = []
    for row in evidence_rows or []:
        role = str(row.get("role") or "")
        if role == "neutral" or role not in {"supporting", "challenging"}:  # ①
            continue
        try:
            score = float(row.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score < MIN_EVIDENCE_SCORE:  # ③
            continue
        evidence_date = str(row.get("evidenceDate") or "")[:10]
        if watermark and evidence_date <= watermark:
            continue
        if not matches_checkpoint(checkpoint, row):
            continue
        if role == direction:  # ②
            aligned.append(row)
        elif role == _opposite(direction):
            opposed.append(row)

    if aligned and opposed:  # ④
        verdict = "challenged"
        hits = opposed + aligned
    elif aligned:
        verdict = "confirmed" if direction == "supporting" else "challenged"
        hits = aligned
    else:
        return {"verdict": "no_signal", "evidence": [], "at": as_of or _now()}

    hits = sorted(hits, key=lambda row: (str(row.get("evidenceDate") or ""), float(row.get("score") or 0)), reverse=True)
    evidence = [
        {
            # 근거 참조는 evidence_id가 아니라 memory_id 사본이다 — 근거 행은 갱신마다
            # DELETE 후 재삽입이라 evidence_id가 다음 갱신에 사라진다(regime_v2.py 실측).
            "memoryId": str(row.get("memoryId") or ""),
            "date": str(row.get("evidenceDate") or ""),
            "title": str(row.get("title") or "")[:220],
            "role": str(row.get("role") or ""),
        }
        for row in hits[:MAX_EVIDENCE_COPIES]
    ]
    return {"verdict": verdict, "evidence": evidence, "at": as_of or _now()}


def apply_verdict(checkpoint: dict, outcome: dict, *, as_of: str) -> dict:
    """판정 결과를 체크포인트에 반영한다. 무엇이 바뀌었는지 요약을 돌려준다.

    - `no_signal`은 아무것도 바꾸지 않는다(status 불변, watermark도 전진시키지 않는다).
      전진시키면 확인 근거 사본을 잃는데 얻는 것이 없다.
    - `dueBy` 경과 + 판정 없음 → `expired`. 판정이 아니라 상태 전환이며 이력에 남긴다.
    """
    verdict = outcome.get("verdict")
    previous_status = checkpoint.get("status") or CHECKPOINT_STATUS_DEFAULT
    previous_verdict = str((checkpoint.get("lastVerdict") or {}).get("verdict") or "")

    if verdict in {"confirmed", "challenged"}:
        checkpoint["lastVerdict"] = {
            "verdict": verdict,
            "at": outcome.get("at") or as_of,
            "evidence": outcome.get("evidence") or [],
        }
        checkpoint["status"] = verdict
        if previous_verdict != verdict:
            append_history(
                checkpoint,
                at=outcome.get("at") or as_of,
                from_status=previous_status,
                to_status=verdict,
                verdict=verdict,
            )
            return {"changed": True, "from": previous_status, "to": verdict, "verdict": verdict}
        return {"changed": False, "from": previous_status, "to": verdict, "verdict": verdict}

    due_by = checkpoint.get("dueBy")
    if due_by and previous_status == CHECKPOINT_STATUS_DEFAULT and str(due_by) < str(as_of)[:10]:
        checkpoint["status"] = "expired"
        append_history(checkpoint, at=as_of, from_status=previous_status, to_status="expired", verdict="no_signal")
        return {"changed": True, "from": previous_status, "to": "expired", "verdict": "no_signal"}
    return {"changed": False, "from": previous_status, "to": previous_status, "verdict": "no_signal"}


def _change_id(state_id: str, checkpoint_id: str, at: str) -> str:
    return hashlib.sha256(f"{state_id}:checkpoint:{checkpoint_id}:{at}".encode("utf-8")).hexdigest()[:24]


def _evidence_rows(conn, state_id: str) -> list:
    rows = conn.execute(
        """
        SELECT memory_id, evidence_date, role, score, title, summary, matched_terms_json
        FROM market_regime_evidence
        WHERE state_id=?
        ORDER BY evidence_date DESC, score DESC
        """,
        (state_id,),
    ).fetchall()
    return [
        {
            "memoryId": row["memory_id"],
            "evidenceDate": row["evidence_date"],
            "role": row["role"],
            "score": row["score"],
            "title": row["title"],
            "summary": row["summary"],
            "matchedTerms": parse_json_list(row["matched_terms_json"]),
        }
        for row in rows
    ]


def _forbidden_keywords(state_row) -> list:
    return [state_row["state_label"], state_row["state_key"], state_row["story_family"], state_row["story"]]


def run_state_checkpoint_verdicts(conn, state_id: str, *, as_of: str = "") -> dict:
    """한 내러티브 상태의 구조화 체크포인트를 판정한다. 커밋은 호출자가 한다."""
    as_of = as_of or _now()
    row = conn.execute("SELECT * FROM market_narrative_states WHERE state_id=?", (state_id,)).fetchone()
    if not row:
        return {"stateId": state_id, "evaluated": 0, "changes": []}
    stored = parse_json_list(row["next_checkpoints_json"])
    structured, templates = split_checkpoints(
        stored, scope="narrative", forbidden_keywords=_forbidden_keywords(row), now=as_of
    )
    if not structured:
        return {"stateId": state_id, "evaluated": 0, "changes": []}

    evidence_rows = _evidence_rows(conn, state_id)
    changes: list = []
    verdicts: list = []
    for checkpoint in structured:
        outcome = evaluate_checkpoint(checkpoint, evidence_rows, as_of=as_of)
        result = apply_verdict(checkpoint, outcome, as_of=as_of)
        verdicts.append({
            "checkpointId": checkpoint["id"],
            "item": checkpoint["item"],
            "verdict": outcome["verdict"],
            "status": checkpoint["status"],
        })
        if not result["changed"]:
            continue
        changes.append({"checkpointId": checkpoint["id"], **result})
        conn.execute(
            """
            INSERT OR REPLACE INTO market_regime_changes (
                change_id, state_id, changed_at, field, old_value, new_value, reason,
                evidence_ids_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _change_id(state_id, checkpoint["id"], as_of), state_id, as_of,
                f"checkpoint:{checkpoint['id']}", result["from"], result["to"],
                f"{checkpoint['item']} — 규칙 판정 {result['verdict']}",
                # evidence_id가 아니라 memory_id 사본을 남긴다(위 evaluate_checkpoint 주석).
                json.dumps(
                    [item["memoryId"] for item in (outcome.get("evidence") or []) if item.get("memoryId")],
                    ensure_ascii=False,
                ),
                as_of,
            ),
        )

    conn.execute(
        "UPDATE market_narrative_states SET next_checkpoints_json=? WHERE state_id=?",
        (json.dumps(structured + templates, ensure_ascii=False), state_id),
    )
    return {"stateId": state_id, "evaluated": len(structured), "changes": changes, "verdicts": verdicts}


def run_checkpoint_verdicts(db_path, *, status: str = "current", limit: int = 30, as_of: str = "") -> dict:
    """활성/관찰 상태의 구조화 체크포인트를 한 번에 판정한다."""
    as_of = as_of or _now()
    conn = connect(db_path)
    init_db(conn)
    where = "WHERE status IN ('active','watch')" if status == "current" else ""
    rows = conn.execute(
        f"SELECT state_id FROM market_narrative_states {where} ORDER BY updated_at DESC LIMIT ?",
        (int(limit or 30),),
    ).fetchall()
    results: list = []
    try:
        with conn:
            for row in rows:
                results.append(run_state_checkpoint_verdicts(conn, row["state_id"], as_of=as_of))
    finally:
        conn.close()
    return {
        "ok": True,
        "asOf": as_of,
        "stateCount": len(results),
        "checkpointCount": sum(item["evaluated"] for item in results),
        "changeCount": sum(len(item["changes"]) for item in results),
        "results": results,
    }


def merge_state_checkpoints(db_path, state_id: str, incoming, *, as_of: str = "") -> dict:
    """구조화 체크포인트를 생성·교체한다(LLM 시장 메모리 업데이트·수동 편집 경로).

    규칙 갱신(`refresh_regime_state`)은 이 목록을 만들지 않는다 — 그쪽은 템플릿
    문장만 다시 쓰고 구조화 원소는 보존한다.
    """
    from features.common.research_schema.tracked_checkpoints import merge_checkpoint_lists

    as_of = as_of or _now()
    conn = connect(db_path)
    init_db(conn)
    try:
        row = conn.execute("SELECT * FROM market_narrative_states WHERE state_id=?", (state_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "State not found", "stateId": state_id}
        stored = parse_json_list(row["next_checkpoints_json"])
        forbidden = _forbidden_keywords(row)
        merged = merge_checkpoint_lists(
            stored, incoming, scope="narrative", forbidden_keywords=forbidden, now=as_of
        )
        _, templates = split_checkpoints(stored, scope="narrative", forbidden_keywords=forbidden, now=as_of)
        with conn:
            conn.execute(
                "UPDATE market_narrative_states SET next_checkpoints_json=?, updated_at=? WHERE state_id=?",
                (json.dumps(merged + templates, ensure_ascii=False), as_of, state_id),
            )
    finally:
        conn.close()
    return {"ok": True, "stateId": state_id, "checkpoints": merged}
