"""내러티브 검증 상태 projection — 저장된 판정을 화면이 읽는 모양으로만 옮긴다.

**읽기 전용이다.** 판정·저장 계약은 `checkpoint_verdicts`와 `regime_v2`가 소유하고,
여기서는 아무것도 쓰지 않는다(0.6 Stage C는 보여주는 일이다).

담는 것 셋:

1. 상태별 **구조화 체크포인트와 판정**(status·lastVerdict 근거 사본·dueBy).
2. **무소식 배지** — 계획 §4의 고정 사다리. 14일이면 `식어가는 중`, 30일이면
   `resolved 후보`다. **후보는 제안일 뿐 상태를 바꾸지 않는다**(§3.5).
3. **판정 이력 타임라인**(C.3) — 기존 `market_regime_changes` 행. 새 이력 저장소를
   만들지 않는다.

`market_regime_changes.evidence_ids_json`의 `memory:` 접두 항목은 memory_id 사본이지
진짜 evidence_id가 아니다(근거 행은 갱신마다 지워졌다 다시 들어온다). 그래서 여기서는
**join하지 않고 개수만** 내보낸다 — 화면에 내부 id를 흘리지 않는 규칙과도 같다.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from features.common.research_schema.tracked_checkpoints import partition_checkpoints
from features.market_memory.memory import connect, init_db, parse_json_list
from features.market_memory.regime_v2 import normalize_momentum
from features.market_memory.state_dashboard import MOMENTUM_LABELS
from features.common.workspace import data_dir

MARKET_MEMORY_DB_PATH = data_dir() / "market-memory.sqlite3"

# 계획 §4의 고정 사다리. 사용자 설정으로 노출하지 않는다(§3.8) — 사람마다 숫자가
# 다르면 같은 데이터에서 다른 "중기"가 나와 결과를 신뢰할 수 없다.
COOLING_DAYS = 14
DORMANT_DAYS = 30
TIMELINE_LIMIT = 12
CHECKPOINT_FIELD_PREFIX = "checkpoint:"

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


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _date(value) -> dt.date | None:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _days_since(value, *, today: dt.date) -> int | None:
    day = _date(value)
    if not day:
        return None
    return max(0, (today - day).days)


def silence_badge(days: int | None) -> dict:
    """무소식 배지 — 죽어가는 이야기와 살아있는 이야기가 똑같이 생기지 않게 한다.

    30일은 `resolved` 후보 **제안**이다. 자동 전환하지 않는다(§3.5) — 올리는 것도
    내리는 것도 사용자가 확정한다.
    """
    if days is None:
        return {
            "days": None, "level": "unknown", "label": "근거 없음",
            "note": "이 내러티브로 분류된 근거가 아직 없습니다.",
        }
    if days >= DORMANT_DAYS:
        return {
            "days": days, "level": "dormant", "label": f"{days}일 무소식 · 정리 후보",
            "note": "30일 넘게 새 근거가 없습니다. 상태를 내릴지는 직접 확인해 정하세요 — 자동으로 바뀌지 않습니다.",
        }
    if days >= COOLING_DAYS:
        return {
            "days": days, "level": "cooling", "label": f"{days}일 무소식 · 식어가는 중",
            "note": "2주 넘게 새 근거가 없습니다. 시장이 이 이야기를 덜 하고 있다는 신호입니다.",
        }
    return {
        "days": days, "level": "active", "label": f"{days}일 전 근거",
        "note": "",
    }


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
        "keywords": list((checkpoint.get("matchers") or {}).get("keywords") or []),
        "tickers": list((checkpoint.get("matchers") or {}).get("tickers") or []),
        "lastVerdict": {
            "verdict": last.get("verdict", ""),
            "verdictLabel": VERDICT_LABELS.get(str(last.get("verdict") or ""), ""),
            "at": last.get("at", ""),
            "evidence": [
                {
                    "date": str(item.get("date") or ""),
                    "title": str(item.get("title") or ""),
                    "role": str(item.get("role") or ""),
                }
                for item in (last.get("evidence") or [])[:3]
                if isinstance(item, dict)
            ],
        } if last else None,
        "historyCount": len(checkpoint.get("history") or []),
    }


def _timeline(conn, state_id: str, *, limit: int = TIMELINE_LIMIT) -> list:
    rows = conn.execute(
        """
        SELECT changed_at, field, old_value, new_value, reason, evidence_ids_json
        FROM market_regime_changes
        WHERE state_id = ?
        ORDER BY changed_at DESC
        LIMIT ?
        """,
        (state_id, int(limit or TIMELINE_LIMIT)),
    ).fetchall()
    out = []
    for row in rows:
        field = str(row["field"] or "")
        try:
            refs = json.loads(row["evidence_ids_json"] or "[]")
        except Exception:
            refs = []
        out.append({
            "at": row["changed_at"] or "",
            # 내부 id는 화면에 나가지 않는다 — 체크포인트 행은 `checkpoint:<id>`이므로
            # 종류만 알리고 어떤 항목인지는 reason 문장이 말한다.
            "kind": "checkpoint" if field.startswith(CHECKPOINT_FIELD_PREFIX) else field,
            "from": str(row["old_value"] or ""),
            "to": str(row["new_value"] or ""),
            "reason": str(row["reason"] or ""),
            # `memory:` 접두 사본이라 join하지 않는다. 몇 건이 근거였는지만 말한다.
            "evidenceCount": len([ref for ref in refs if isinstance(ref, str)]),
        })
    return out


def _state_rows(conn, *, status: str, limit: int) -> list:
    where = "WHERE status IN ('active','watch')" if status == "current" else ""
    return conn.execute(
        f"""
        SELECT * FROM market_narrative_states
        {where}
        ORDER BY importance = 'high' DESC, updated_at DESC
        LIMIT ?
        """,
        (int(limit or 20),),
    ).fetchall()


def _latest_evidence_date(conn, state_id: str) -> str:
    row = conn.execute(
        "SELECT MAX(evidence_date) AS latest FROM market_regime_evidence WHERE state_id = ?",
        (state_id,),
    ).fetchone()
    return str((row["latest"] if row else "") or "")


def narrative_verification_payload(
    db_path: str | Path = MARKET_MEMORY_DB_PATH,
    *,
    status: str = "current",
    limit: int = 20,
    as_of: str = "",
) -> dict:
    """활성/관찰 내러티브의 검증 상태를 화면용으로 모은다."""
    anchor = _date(as_of) or _now().date()
    path = Path(db_path)
    if not path.exists():
        return {"asOf": anchor.isoformat(), "states": [], "summary": _summary([])}
    conn = connect(path)
    init_db(conn)
    try:
        states = []
        for row in _state_rows(conn, status=status, limit=limit):
            state_id = row["state_id"]
            state_key = str(row["state_key"] or state_id)
            structured, invalid, templates = partition_checkpoints(
                parse_json_list(row["next_checkpoints_json"]),
                scope="narrative",
                scope_key=state_key,
                forbidden_keywords=[row["state_label"], row["state_key"], row["story_family"], row["story"]],
            )
            checkpoints = [_checkpoint_projection(item) for item in structured]
            latest_evidence = _latest_evidence_date(conn, state_id)
            counts = {key: 0 for key in CHECKPOINT_STATUS_LABELS}
            for item in checkpoints:
                counts[item["status"]] = counts.get(item["status"], 0) + 1
            momentum = normalize_momentum(row["momentum"] if "momentum" in row.keys() else "")
            states.append({
                "stateId": state_id,
                "stateKey": state_key,
                "label": str(row["state_label"] or row["story_family"] or state_key),
                "status": str(row["status"] or "watch"),
                "momentum": momentum,
                "momentumLabel": MOMENTUM_LABELS.get(momentum, "유지"),
                "evidenceCounts": {
                    "d7": int(row["evidence_count_7d"] or 0),
                    "d30": int(row["evidence_count_30d"] or 0),
                    "d90": int(row["evidence_count_90d"] or 0),
                },
                "lastEvidenceAt": latest_evidence,
                "lastConfirmedAt": str(row["last_confirmed_at"] or ""),
                "lastChallengedAt": str(row["last_challenged_at"] or ""),
                "silence": silence_badge(_days_since(latest_evidence, today=anchor)),
                "checkpoints": checkpoints,
                "checkpointCounts": counts,
                # 검증에 실패한 저장 원소는 지우지 않고 보존된다(Stage A). 화면은 그 사실을
                # `검증 불가`로 말한다 — 조용히 사라지면 사용자가 이력을 잃는다.
                "unverifiableCount": len(invalid),
                "templates": templates[:5],
                "timeline": _timeline(conn, state_id),
            })
    finally:
        conn.close()
    return {"asOf": anchor.isoformat(), "states": states, "summary": _summary(states)}


def _summary(states: list) -> dict:
    return {
        "stateCount": len(states),
        "checkpointCount": sum(len(state["checkpoints"]) for state in states),
        "confirmed": sum(state["checkpointCounts"].get("confirmed", 0) for state in states),
        "challenged": sum(state["checkpointCounts"].get("challenged", 0) for state in states),
        "cooling": sum(1 for state in states if state["silence"]["level"] in {"cooling", "dormant"}),
        "unverifiable": sum(state["unverifiableCount"] for state in states),
    }
