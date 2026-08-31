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
        # `last_reviewed`를 찍지 않는다 — 노트 저장은 검토가 아니다. 저장 시각을 넣으면
        # 검토한 적 없는 thesis가 "최근 검토: 오늘"이 되고, Delta의 since_last_review
        # 창이 0일로 접혀 첫 검토가 insufficient_evidence로 끝난다. 기계 판정이
        # updated_at을 못 만지는 것(§A.2)과 같은 규칙의 노트판이다.
    }
    thesis = M.parse_company_thesis(
        meta, body, note_path=note_path_ref(note.get("id")), source=SOURCE
    )
    # 파서는 last_reviewed가 없으면 created로 물러난다(Vault frontmatter 관례).
    # 네이티브 노트에는 그 관례가 없다 — 검토 이력이 없다는 사실을 그대로 둔다.
    thesis.last_reviewed_at = ""
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
            # 갱신에서도 **노트가 값을 주지 않는 필드는 기존을 유지한다.** 노트에는
            # 그 값이 없어서 빈 값·기본값으로 되돌아가기 때문이다 — 확인 대화상자는
            # "노트 내용으로 덮을까요"를 물었지 이탈 조건·핵심 지표를 지우겠다고
            # 묻지 않았다. 명시적 action이 곧 손실 없는 action은 아니다(수동 부분
            # 갱신 API와 같은 규칙).
            thesis.review_cycle = existing.get("review_cycle") or thesis.review_cycle
            thesis.conviction = existing.get("conviction") or thesis.conviction
            thesis.status = existing.get("status") or thesis.status
            thesis.created_at = existing.get("created_at") or thesis.created_at
            # 노트 저장은 검토가 아니다 — 검토 시각은 사용자 검토 경로만 쓴다.
            thesis.last_reviewed_at = str(existing.get("last_reviewed_at") or "")
            for field in (
                "key_assumptions", "supporting_signals", "weakening_signals",
                "falsification_triggers", "key_metrics", "linked_regimes",
            ):
                if not getattr(thesis, field):
                    setattr(thesis, field, list(existing.get(field) or []))
            thesis.company = thesis.company or str(existing.get("company") or "")
        ST.upsert_thesis(conn, thesis)
        return {
            "status": "updated" if existing else "created",
            "ticker": thesis.ticker,
            "thesis": ST.get_thesis(conn, thesis.ticker),
        }
    finally:
        conn.close()


AGENT_NOTE_TAG = "agent_assisted"


def auto_register_block(note: dict) -> str:
    """자동 등록을 막는 사유. 빈 문자열이면 등록해도 된다.

    자동 경로는 명시적 승격보다 엄격하다(2026-08-30 리뷰):

    - **Agent가 정리한 노트는 자동 등록하지 않는다.** Agent 자유 텍스트가 확인 없이
      hypothesis 정본이 되는 것은 §3.13("구조화된 Thesis 변경은 별도 확인 후에만
      저장한다") 위반이다. 사용자가 `이 노트로 Thesis 만들기`를 누르면 그 확인이다.
    - **본문 없는 생각 한 줄은 자동 등록하지 않는다.** `생각만 기록`이 기본 입구라
      지나가는 한 줄("실적 전에 좀 더 봐야 함")이 영구 레지스트리 행이 되고, 그 행이
      빈자리를 차지해 나중에 공들여 쓴 노트·Vault 노트가 전부 skipped가 된다.
      명시적 승격은 생각 fallback을 그대로 쓴다 — 사용자가 그것을 골랐으므로.
    """
    note = note or {}
    tags = note.get("tags") if isinstance(note.get("tags"), list) else []
    if AGENT_NOTE_TAG in [str(t or "").strip() for t in tags]:
        return "skipped_agent_note"
    body = str(note.get("body") or "")
    # 실질 = 본문이 논지를 준다(템플릿 섹션 또는 첫 문단). 생각 이벤트·제목 fallback만
    # 있는 노트는 자동 경로에서 제외한다.
    parsed = M.parse_company_thesis({"ticker": "X"}, body, note_path="", source=SOURCE)
    if not parsed.core_thesis and not _first_paragraph(body):
        return "skipped_no_substance"
    return ""


def link_note_on_save(note: dict, *, db_path=None) -> dict:
    """노트 저장 훅 — 빈자리 자동 등록. **실패가 노트 저장을 되돌리지 않는다.**

    thesis 등록은 노트의 부가물이다. 레지스트리가 잠겨 있다고 사용자가 방금 쓴
    노트를 잃으면 안 된다.
    """
    if str((note or {}).get("noteType") or "") != NOTE_TYPE:
        return {"status": "skipped_not_thesis", "ticker": ""}
    blocked = auto_register_block(note)
    if blocked:
        return {"status": blocked, "ticker": str((note or {}).get("ticker") or "")}
    try:
        return register_thesis_from_note(note, db_path=db_path, overwrite=False)
    except Exception:
        return {"status": "failed", "ticker": str((note or {}).get("ticker") or "")}
