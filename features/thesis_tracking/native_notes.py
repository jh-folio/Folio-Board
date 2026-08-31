"""네이티브 `company_thesis` 노트 ↔ thesis 레지스트리 연결 (0.6 Stage B.2).

예전에는 Vault의 `company_thesis` 노트만 레지스트리에 동기화돼서, Obsidian 없이
앱 안에서만 쓰는 사용자는 성실히 노트를 써도 thesis가 생기지 않았다 — 그리고 바로
그 노트 위의 카드가 계속 "연결된 Thesis가 없습니다"를 표시했다.

**키 정책(계획 §8.2 결정): 빈자리만 자동, 갱신은 명시적.**

- thesis가 없는 종목은 첫 `company_thesis` 노트가 자동 등록된다.
- 이미 있으면 노트 저장이 thesis를 덮지 않는다. 덮는 것은 노트 쪽
  `이 노트로 Thesis 갱신` action(`overwrite=True`)뿐이다.

공들인 thesis가 지나가는 메모에 조용히 덮이는 것을 막고, "저장물 변경은 명시적
action"이라는 경계(§3.12)와 같은 규칙이다. 레지스트리는 원본 노트 참조
(`note_path = native_note:{id}`)를 유지해 어느 노트에서 왔는지 잃지 않는다.
"""
from __future__ import annotations

import re

from features.thesis_tracking import model as M
from features.thesis_tracking import store as ST

NOTE_TYPE = "company_thesis"
SOURCE = "native_note"
NOTE_PATH_PREFIX = "native_note:"


def note_path_ref(note_id: str) -> str:
    return f"{NOTE_PATH_PREFIX}{str(note_id or '').strip()}"


def _first_paragraph(body: str) -> str:
    """헤딩·불릿이 아닌 첫 문단 — 노트가 템플릿 형식이 아닐 때의 core_thesis 후보."""
    buffer: list = []
    for line in str(body or "").splitlines():
        text = line.strip()
        if not text:
            if buffer:
                break
            continue
        if text.startswith("#") or re.match(r"^[-*]\s+", text) or text.startswith(">"):
            if buffer:
                break
            continue
        buffer.append(text)
    return " ".join(buffer).strip()


def _latest_thought(note: dict) -> str:
    """가장 최근 `생각만 기록` 한 줄 — 본문이 빈 노트의 core_thesis 후보."""
    events = note.get("rawThoughts")
    if not isinstance(events, list):
        return ""
    for event in reversed(events):
        text = str((event or {}).get("body") or "").strip() if isinstance(event, dict) else ""
        if text:
            return text
    return ""


def thesis_from_note(note: dict):
    """네이티브 노트를 Thesis 모델로 옮긴다. ticker가 없으면 None.

    본문이 `## 핵심 Thesis` 같은 템플릿 형식이면 섹션 파서가 각 필드를 채우고,
    자유 형식이면 첫 문단이 `core_thesis`가 된다 — 노트를 쓰는 방식을 강요하지 않는다.
    """
    note = note or {}
    ticker = str(note.get("ticker") or "").strip().upper()
    if not ticker:
        return None
    body = str(note.get("body") or "")
    meta = {
        "ticker": ticker,
        "company": note.get("company") or "",
        "created": str(note.get("createdAt") or "")[:19],
        "last_reviewed": str(note.get("updatedAt") or note.get("createdAt") or "")[:19],
    }
    thesis = M.parse_company_thesis(
        meta, body, note_path=note_path_ref(note.get("id")), source=SOURCE
    )
    if not thesis.core_thesis:
        # 노트 패널의 기본 입구는 `생각만 기록`이라 본문이 비고 생각만 쌓인 노트가 흔하다.
        # 그때 제목("HWM 투자 노트")을 논지로 삼으면 등록은 되는데 알맹이가 없다 —
        # 가장 최근 생각이 그 사람이 실제로 적은 가설이다.
        thesis.core_thesis = (
            _first_paragraph(body)
            or _latest_thought(note)
            or str(note.get("title") or "").strip()
        )
    if not thesis.company:
        thesis.company = str(note.get("label") or "").strip()[:120]
    return thesis


def register_thesis_from_note(note: dict, *, db_path=None, overwrite: bool = False) -> dict:
    """노트에서 thesis를 등록한다. 무엇을 했는지 status로 돌려준다.

    `overwrite=False`(노트 저장 경로)는 **빈자리만** 채운다. `overwrite=True`는
    사용자가 명시적으로 누른 `이 노트로 Thesis 갱신`이다.
    """
    note = note or {}
    if str(note.get("noteType") or "") != NOTE_TYPE:
        return {"status": "skipped_not_thesis", "ticker": ""}
    thesis = thesis_from_note(note)
    if thesis is None:
        return {"status": "skipped_no_ticker", "ticker": ""}
    conn = ST.connect(db_path)
    try:
        existing = ST.get_thesis(conn, thesis.ticker)
        if existing and not overwrite:
            return {"status": "skipped_existing", "ticker": thesis.ticker}
        if existing:
            # 갱신에서도 사용자가 손댄 운영 필드는 노트가 덮지 않는다 — 노트에는
            # 그 값이 없어서 기본값으로 되돌아가기 때문이다(검토 주기가 조용히
            # 분기로 리셋되는 식).
            thesis.review_cycle = existing.get("review_cycle") or thesis.review_cycle
            thesis.conviction = existing.get("conviction") or thesis.conviction
            thesis.status = existing.get("status") or thesis.status
            thesis.created_at = existing.get("created_at") or thesis.created_at
            thesis.linked_regimes = thesis.linked_regimes or existing.get("linked_regimes") or []
        ST.upsert_thesis(conn, thesis)
        return {
            "status": "updated" if existing else "created",
            "ticker": thesis.ticker,
            "thesis": ST.get_thesis(conn, thesis.ticker),
        }
    finally:
        conn.close()


def link_note_on_save(note: dict, *, db_path=None) -> dict:
    """노트 저장 훅 — 빈자리 자동 등록. **실패가 노트 저장을 되돌리지 않는다.**

    thesis 등록은 노트의 부가물이다. 레지스트리가 잠겨 있다고 사용자가 방금 쓴
    노트를 잃으면 안 된다.
    """
    try:
        return register_thesis_from_note(note, db_path=db_path, overwrite=False)
    except Exception:
        return {"status": "failed", "ticker": str((note or {}).get("ticker") or "")}
