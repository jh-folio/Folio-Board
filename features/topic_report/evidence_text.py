"""근거 문서의 본문을 컨텍스트 분량 안에서 꺼내 온다.

수집은 기사 전문을 저장하는데(`## Full Text`), 생성 컨텍스트에는 검색 스니펫
400자만 들어갔다. 실측으로 근거 29건 중 19건이 전문 보유였고 저장된 본문 합계가
88,792자인데 모델에게 간 것은 약 11,600자였다 — **가진 자료의 13%**다. 그 상태로
"자료가 부족하다"는 한계 문장이 보고서에 실렸다.

전문에는 사이트 내비게이션 같은 군더더기가 앞에 붙기도 한다(CNBC 기준 약 330자).
그것까지 지우려고 추측하지 않는다 — 요약 문장을 본문에서 되찾는 방식은 실측 40건
중 10건만 맞았다. 상한을 넉넉히 두고 판단은 모델에게 맡긴다.
"""
from __future__ import annotations

import os
from pathlib import Path

from features.common.workspace import research_inbox_dir

FULL_TEXT_HEADING = "## Full Text"
SUMMARY_HEADING = "## Summary"


def _limit(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def evidence_body_char_limit() -> int:
    """근거 한 건에서 꺼낼 본문 상한."""
    return _limit("TOPIC_EVIDENCE_BODY_CHARS", 2000)


def evidence_body_total_budget() -> int:
    """본문을 붙이는 데 쓸 전체 분량 상한."""
    return _limit("TOPIC_EVIDENCE_BODY_BUDGET", 50000)


def evidence_body_document_limit() -> int:
    """본문을 붙일 문서 수 상한 (관련도 상위부터)."""
    return _limit("TOPIC_EVIDENCE_BODY_DOCS", 14)


def _resolve(path: str) -> Path | None:
    """자료 폴더 기준 상대 경로를 실제 파일로 옮긴다. 폴더 밖은 읽지 않는다."""
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        return None
    root = research_inbox_dir().parent
    candidate = (root / text) if not Path(text).is_absolute() else Path(text)
    try:
        resolved = candidate.resolve()
        inbox = research_inbox_dir().resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(inbox):
        return None
    return resolved if resolved.is_file() else None


def read_evidence_body(path: str, *, limit: int | None = None) -> str:
    """아카이브 Markdown에서 본문(없으면 요약)을 꺼낸다. 실패하면 빈 문자열."""
    resolved = _resolve(path)
    if resolved is None:
        return ""
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if FULL_TEXT_HEADING in text:
        body = text.split(FULL_TEXT_HEADING, 1)[1]
    elif SUMMARY_HEADING in text:
        body = text.split(SUMMARY_HEADING, 1)[1]
    else:
        return ""
    body = " ".join(body.split()).strip()
    cap = evidence_body_char_limit() if limit is None else max(0, int(limit))
    return body[:cap]


def select_bodies(docs: list[dict]) -> dict[str, str]:
    """관련도 상위 문서의 본문을 예산 안에서 읽어 {근거 id: 본문}으로 돌려준다.

    본문이 이미 스니펫으로 들어간 분량보다 짧으면 붙이지 않는다 — 같은 문장을 두 번
    싣게 된다.
    """
    ranked = sorted(
        [doc for doc in docs or [] if isinstance(doc, dict) and doc.get("path")],
        key=lambda doc: (-float(doc.get("relevance") or 0), str(doc.get("id") or "")),
    )
    budget = evidence_body_total_budget()
    per_doc = evidence_body_char_limit()
    max_docs = evidence_body_document_limit()
    bodies: dict[str, str] = {}
    for doc in ranked[:max_docs]:
        if budget <= 0:
            break
        body = read_evidence_body(str(doc.get("path") or ""), limit=min(per_doc, budget))
        summary = str(doc.get("summary") or "")
        if len(body) <= len(summary) + 200:
            continue
        key = str(doc.get("id") or "")
        if not key:
            continue
        bodies[key] = body
        budget -= len(body)
    return bodies


__all__ = [
    "evidence_body_char_limit",
    "evidence_body_document_limit",
    "evidence_body_total_budget",
    "read_evidence_body",
    "select_bodies",
]
