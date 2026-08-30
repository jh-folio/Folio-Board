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
    merge_checkpoint_lists,
    normalize_tracked_checkpoint,
    partition_checkpoints,
    rewrite_checkpoints,
    squash,
)
from features.market_memory.memory import connect, init_db, parse_json_list

MIN_EVIDENCE_SCORE = 0.5
# dueBy 없는 open 체크포인트의 수명. §4 사다리의 구조 판정 창(90일)과 같은 눈금 —
# 이 창을 한 번도 신호 없이 넘긴 "다음 확인"은 더는 확인이 아니다.
OPEN_MAX_AGE_DAYS = 90


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _prepared(row: dict) -> dict:
    """매칭용 파생값을 행에 한 번만 계산해 붙인다 — 체크포인트 수만큼 재계산하지 않는다."""
    if "_haystack" not in row:
        parts = [row.get("title"), row.get("summary")] + list(row.get("matchedTerms") or [])
        row["_haystack"] = squash(" ".join(str(p or "") for p in parts))
        row["_termKeys"] = {squash(term) for term in (row.get("matchedTerms") or []) if squash(term)}
    return row


def matches_checkpoint(checkpoint: dict, row: dict, *, use_tickers: bool = True) -> bool:
    """keyword는 제목+요약+matchedTerms에 공백 제거 부분일치, ticker는 matchedTerms에 있으면 hit.

    ticker를 본문에서 찾지 않는 것은 의도다 — 세 글자 티커가 한국어 본문에 우연히
    걸리면 그 회사와 무관한 기사가 확인 신호가 된다.

    `use_tickers=False`는 **풀 자체가 이미 그 회사로 걸러진 경우**(thesis — 종목
    태그 문서)다. 거기서는 ticker matcher가 모든 행에 걸려 "그 회사 뉴스가 있다"가
    곧 확인이 된다. 계획 A.2가 "티커 태그 문서 중 **keyword hit**이 전부다"라고
    적은 이유이고, A.1이 thesis 체크포인트에 keyword를 필수로 건 이유다.
    """
    matchers = checkpoint.get("matchers") or {}
    row = _prepared(row)
    haystack = row["_haystack"]
    for keyword in matchers.get("keywords") or []:
        key = squash(keyword)
        if key and key in haystack:
            return True
    if not use_tickers:
        return False
    terms = row["_termKeys"]
    for ticker in matchers.get("tickers") or []:
        key = squash(ticker)
        if key and key in terms:
            return True
    return False


def _cutoff(checkpoint: dict) -> tuple[str, bool]:
    """(기준일, 그 날짜 포함 제외 여부).

    - 판정 이력이 있으면 기준은 마지막 verdict 날짜이고 **그 날짜는 다시 본다**
      (strict `<` skip). 오전 판정 후 오후에 들어온 같은 날짜의 반증이 영구 스킵되면
      confirmed가 하루 종일 눌러앉는다 — 확증편향 방지 취지와 정반대다. 같은 행을
      다시 봐도 판정은 결정적이고 이력은 verdict가 바뀔 때만 남으므로 멱등하다.
    - 첫 판정(이력 없음)은 기준이 `createdAt` 날짜이고 **그 날짜를 제외한다**
      (`<=` skip). 체크포인트는 대개 그날의 근거에서 태어나므로, 낳아 준 근거로
      즉시 확인되는 것은 자기확인이다 — "다음 확인"은 앞을 본다.
    """
    last = checkpoint.get("lastVerdict") or {}
    last_at = str(last.get("at") or "")[:10]
    if last_at:
        return last_at, False
    return str(checkpoint.get("createdAt") or "")[:10], True


def evaluate_checkpoint(checkpoint: dict, evidence_rows: list, *, as_of: str = "", role_pool: bool = True) -> dict:
    """한 체크포인트를 근거 행들과 대조해 verdict와 근거 사본을 만든다.

    `role_pool=False`는 **role 분류가 없는 풀**(thesis — 연구 인덱스 문서)이다.
    거기서는 아래 ①②④가 성립하지 않으므로 **direction이 판정 방향을 정한다**
    (계획 A.2: "티커 태그 문서 중 keyword hit이 전부다"). score 게이트도 걸지
    않는다 — 문서에는 `market_regime_evidence`의 근거 점수에 대응하는 값이 없고,
    없는 눈금을 지어내면 판정이 그 발명 위에 선다.

    과잉 판정 방지와 판정 규칙(role 풀):
      ① `neutral` role은 절대 세지 않는다 — 실측 898행 중 364행이 neutral이라
         이걸 세면 매일 confirmed가 된다.
      ② **role이 판정을 정한다**: 매칭된 supporting행은 확인 신호, challenging행은
         반증 신호다 — 체크포인트 direction과 무관하다. direction으로 거르면 반증
         단독(supporting 체크포인트에 challenging행만 hit)이 무시되는데, 반증+지지
         혼합보다 반증 단독이 약할 이유가 없다(2026-08-30 리뷰). direction은
         체크포인트가 무엇을 기다리는지의 메타데이터이고, role이 없는 풀(thesis)
         에서만 판정 방향을 정한다.
      ③ `score >= 0.5`만 센다(실측 실사용 근거는 0.71~1.0).
      ④ 반증이 하나라도 있으면 `challenged` — 확증편향 방지는 반증에 우선권을
         준다(§5 원칙 3). ②의 자연 귀결이다.
    """
    cutoff, exclusive = _cutoff(checkpoint)
    confirming: list = []
    refuting: list = []
    for row in evidence_rows or []:
        role = str(row.get("role") or "")
        if role_pool:
            if role not in {"supporting", "challenging"}:  # ① — neutral과 미지 role 제외
                continue
            try:
                score = float(row.get("score") or 0)
            except (TypeError, ValueError):
                score = 0.0
            if score < MIN_EVIDENCE_SCORE:  # ③
                continue
        evidence_date = str(row.get("evidenceDate") or "")[:10]
        if cutoff and (evidence_date < cutoff or (exclusive and evidence_date == cutoff)):
            continue
        # 문서 풀은 이미 그 종목으로 걸러져 있어 ticker matcher가 모든 행에 걸린다.
        if not matches_checkpoint(checkpoint, row, use_tickers=role_pool):
            continue
        if role_pool:
            (confirming if role == "supporting" else refuting).append(row)  # ②
        elif checkpoint.get("direction") == "supporting":
            confirming.append(row)
        elif checkpoint.get("direction") == "challenging":
            refuting.append(row)
        else:
            # direction이 enum 밖이면 판정하지 않는다 — 정규화 안 된 dict가 흘러들었을
            # 때 기본이 challenged면, 지지 기사가 가설을 약화시켰다고 기록된다.
            continue

    if not confirming and not refuting:
        return {"verdict": "no_signal", "evidence": [], "at": as_of or _now()}
    verdict = "challenged" if refuting else "confirmed"  # ④

    def _sorted(rows: list) -> list:
        return sorted(
            rows,
            key=lambda row: (str(row.get("evidenceDate") or ""), float(row.get("score") or 0)),
            reverse=True,
        )

    # 반증 행이 사본에서 잘리면 안 된다 — challenged 배지 아래 확인 기사만 보이면
    # 사용자는 판정을 눈으로 검증할 수 없다. 반증 먼저 싣고 남은 칸을 지지로 채운다.
    hits = (_sorted(refuting) + _sorted(confirming))[:MAX_EVIDENCE_COPIES]
    if role_pool:
        evidence = [
            {
                # 근거 참조는 evidence_id가 아니라 memory_id 사본이다 — 근거 행은 갱신마다
                # DELETE 후 재삽입이라 evidence_id가 다음 갱신에 사라진다(regime_v2.py 실측).
                "memoryId": str(row.get("memoryId") or ""),
                "date": str(row.get("evidenceDate") or ""),
                "title": str(row.get("title") or "")[:220],
                "role": str(row.get("role") or ""),
            }
            for row in hits
        ]
    else:
        # 문서 풀에는 role 분류가 없다 — 없는 분류를 빈 값으로 흉내 내지 않는다.
        evidence = [
            {
                "docId": str(row.get("docId") or "")[:400],
                "date": str(row.get("evidenceDate") or ""),
                "title": str(row.get("title") or "")[:220],
            }
            for row in hits
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
    # dueBy 없는 open도 영원히 살지 않는다 — LLM이 매일 문구를 조금씩 바꿔 내면
    # open이 무한히 쌓인다(병합은 open을 자르지 않는다). 사다리의 구조 판정 창(90일,
    # §4)을 한 번도 신호 없이 넘긴 항목은 만료가 맞다. 상태 전환이라 이력에 남는다.
    if (
        previous_status == CHECKPOINT_STATUS_DEFAULT
        and not checkpoint.get("lastVerdict")
        and _age_days(checkpoint.get("createdAt"), as_of) > OPEN_MAX_AGE_DAYS
    ):
        checkpoint["status"] = "expired"
        append_history(checkpoint, at=as_of, from_status=previous_status, to_status="expired", verdict="no_signal")
        return {"changed": True, "from": previous_status, "to": "expired", "verdict": "no_signal"}
    return {"changed": False, "from": previous_status, "to": previous_status, "verdict": "no_signal"}


def _age_days(created_at, as_of: str) -> int:
    try:
        created = dt.date.fromisoformat(str(created_at or "")[:10])
        today = dt.date.fromisoformat(str(as_of or "")[:10])
    except ValueError:
        return 0
    return (today - created).days


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
    """한 내러티브 상태의 구조화 체크포인트를 판정한다. 커밋은 호출자가 한다.

    **읽기 우선 경로다** — 판정이 실제로 무언가를 바꿨을 때만, 그것도 바뀐 원소만
    바꿔 쓴다. 예전에는 매 실행이 재검증된 목록을 통째로 되썼는데, 그러면 검증
    실패 원소가 판정 pass에 의해 **삭제**되고(라벨 개명 한 번에 이력까지 증발),
    변화가 없어도 목록이 재정렬됐다.
    """
    as_of = as_of or _now()
    row = conn.execute("SELECT * FROM market_narrative_states WHERE state_id=?", (state_id,)).fetchone()
    if not row:
        return {"stateId": state_id, "evaluated": 0, "changes": []}
    stored = parse_json_list(row["next_checkpoints_json"])
    forbidden = _forbidden_keywords(row)
    scope_key = str(row["state_key"] or state_id)
    structured, _invalid, _templates = partition_checkpoints(
        stored, scope="narrative", scope_key=scope_key, forbidden_keywords=forbidden, now=as_of
    )
    if not structured:
        return {"stateId": state_id, "evaluated": 0, "changes": []}

    evidence_rows = _evidence_rows(conn, state_id)
    changes: list = []
    verdicts: list = []
    updated: dict = {}
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
        updated[checkpoint["id"]] = checkpoint
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
                # evidence_id가 아니라 memory_id 사본이며, 이 컬럼의 다른 생산자
                # (momentum/confidence 변경)는 진짜 evidence_id를 쓰므로 `memory:`
                # 접두로 이름공간을 가른다 — 없으면 join하는 소비자가 0행을 얻는다.
                json.dumps(
                    ["memory:" + item["memoryId"] for item in (outcome.get("evidence") or []) if item.get("memoryId")],
                    ensure_ascii=False,
                ),
                as_of,
            ),
        )

    if updated:
        # 바뀐 원소만 제자리 교체 — 보존 계약은 tracked_checkpoints가 소유한다.
        rewritten = rewrite_checkpoints(
            stored, updated, scope="narrative", scope_key=scope_key,
            forbidden_keywords=forbidden, now=as_of,
        )
        conn.execute(
            "UPDATE market_narrative_states SET next_checkpoints_json=?, updated_at=? WHERE state_id=?",
            (json.dumps(rewritten, ensure_ascii=False), as_of, state_id),
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
    as_of = as_of or _now()
    conn = connect(db_path)
    init_db(conn)
    try:
        row = conn.execute("SELECT * FROM market_narrative_states WHERE state_id=?", (state_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "State not found", "stateId": state_id}
        stored = parse_json_list(row["next_checkpoints_json"])
        forbidden = _forbidden_keywords(row)
        scope_key = str(row["state_key"] or state_id)
        merged = merge_checkpoint_lists(
            stored, incoming, scope="narrative", scope_key=scope_key,
            forbidden_keywords=forbidden, now=as_of,
        )
        # 들어온 것 중 검증을 통과한 **개수**(집합이 아니다) — dropped의 의미는
        # "검증 탈락"이다. 집합으로 세면 표기만 다른 중복이 탈락으로 잘못 보고되고,
        # 재실행이 기존 항목을 새로 만든 것처럼 보고된다(2026-08-30 리뷰). 같은
        # validator를 다시 부르는 것뿐이라 규칙이 갈리지 않는다.
        accepted = sum(
            1
            for value in (incoming or [])
            if normalize_tracked_checkpoint(
                value, scope="narrative", scope_key=scope_key, now=as_of,
                forbidden_keywords=forbidden, trusted=False,
            )
        )
        # 검증 실패 dict와 템플릿 문장은 병합 대상이 아니라 보존 대상이다.
        _, invalid, templates = partition_checkpoints(
            stored, scope="narrative", scope_key=scope_key, forbidden_keywords=forbidden, now=as_of
        )
        with conn:
            conn.execute(
                "UPDATE market_narrative_states SET next_checkpoints_json=?, updated_at=? WHERE state_id=?",
                (json.dumps(merged + invalid + templates, ensure_ascii=False), as_of, state_id),
            )
    finally:
        conn.close()
    incoming_count = len(incoming) if isinstance(incoming, list) else 0
    return {
        "ok": True,
        "stateId": state_id,
        "checkpoints": merged,
        "accepted": accepted,
        "rejected": max(0, incoming_count - accepted),
    }


def current_state_id_for_key(db_path, state_key: str) -> str:
    """state_key의 현재 active/watch 행 id. 없으면 빈 문자열.

    귀속은 엔트리의 stateKey를 따른다(계획 A.1 결정 2) — 엔트리가 새 상태를 파생하지
    않아도(중요도 미달 등) 기존 살아 있는 상태를 갱신하는 것이면 체크포인트는 그
    상태의 소유물이다. 상태 행은 날짜별로 회전하므로 id가 아니라 key로 찾아야 한다.
    """
    key = str(state_key or "").strip()
    if not key:
        return ""
    conn = connect(db_path)
    init_db(conn)
    try:
        row = conn.execute(
            """
            SELECT state_id FROM market_narrative_states
            WHERE state_key=? AND status IN ('active','watch')
            ORDER BY updated_at DESC LIMIT 1
            """,
            (key,),
        ).fetchone()
        return str(row["state_id"]) if row else ""
    finally:
        conn.close()
