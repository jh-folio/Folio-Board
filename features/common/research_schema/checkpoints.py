"""Common Checkpoint schema for Folio Board research artifacts.

Checkpoint objects are intentionally small: they let dashboards and quality
checks read "what to monitor next" without scraping arbitrary report markdown.
"""
from __future__ import annotations

import hashlib
import re

from features.common.research_schema.enums import (
    normalize_artifact_type,
    normalize_checkpoint_confidence,
    normalize_checkpoint_scope,
)


DEFAULT_POSITIVE_SIGNAL = "해당 변수의 안정 또는 thesis를 뒷받침하는 후속 신호"
DEFAULT_NEGATIVE_SIGNAL = "해당 변수의 악화 또는 thesis와 충돌하는 후속 신호"


def _clean_text(value, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -:\t")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _stable_id(*parts: str) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return "chk_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def normalize_checkpoint(
    item,
    *,
    artifact_type: str,
    artifact_id: str = "",
    scope: str = "market",
    ticker: str = "",
    topic: str = "",
    source_section: str = "",
    confidence: str = "medium",
) -> dict:
    """Return a code-validated Checkpoint object.

    ``item`` may be a string or a partial dict. Unknown enum values fall back to
    safe defaults from ``enums.py``.
    """
    src = item if isinstance(item, dict) else {"checkpoint": item}
    checkpoint = _clean_text(
        src.get("checkpoint")
        or src.get("item")          # 구조화 체크포인트(tracked_checkpoints)의 본문 키
        or src.get("text")
        or src.get("label")
        or src.get("title")
        or src.get("message")
    )
    artifact_type = normalize_artifact_type(src.get("artifactType") or src.get("artifact_type") or artifact_type)
    artifact_id = str(src.get("artifactId") or src.get("artifact_id") or artifact_id or "")
    scope = normalize_checkpoint_scope(src.get("scope") or scope)
    ticker = _clean_text(src.get("ticker") or ticker, 40).upper()
    topic = _clean_text(src.get("topic") or topic, 120)
    source_section = _clean_text(src.get("sourceSection") or src.get("source_section") or source_section, 120)
    confidence = normalize_checkpoint_confidence(src.get("confidence") or confidence)
    positive = _clean_text(src.get("positiveSignal") or src.get("positive_signal") or DEFAULT_POSITIVE_SIGNAL)
    negative = _clean_text(src.get("negativeSignal") or src.get("negative_signal") or DEFAULT_NEGATIVE_SIGNAL)
    cid = str(src.get("id") or "").strip() or _stable_id(
        artifact_type, artifact_id, scope, ticker, topic, source_section, checkpoint
    )
    return {
        "id": cid,
        "artifactType": artifact_type,
        "artifactId": artifact_id,
        "scope": scope,
        "ticker": ticker,
        "topic": topic,
        "checkpoint": checkpoint,
        "positiveSignal": positive,
        "negativeSignal": negative,
        "sourceSection": source_section,
        "confidence": confidence,
    }


def checkpoints_from_list(
    values,
    *,
    artifact_type: str,
    artifact_id: str = "",
    scope: str = "market",
    ticker: str = "",
    topic: str = "",
    source_section: str = "",
    confidence: str = "medium",
    limit: int = 12,
) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    source_values = values if isinstance(values, list) else ([values] if values else [])
    for value in source_values:
        item = normalize_checkpoint(
            value,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            scope=scope,
            ticker=ticker,
            topic=topic,
            source_section=source_section,
            confidence=confidence,
        )
        if not item["checkpoint"] or item["checkpoint"].lower() in seen:
            continue
        seen.add(item["checkpoint"].lower())
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def _heading_pattern(headings: list[str]) -> re.Pattern:
    labels = "|".join(re.escape(h) for h in headings if h)
    return re.compile(rf"(?im)^#{{1,3}}\s*(?:\d+\.\s*)?(?:{labels})\s*$")


def extract_sections(markdown: str, headings: list[str]) -> list[tuple[str, str]]:
    """Every matching section, in document order.

    브리핑은 시장별 markdown을 하나로 이어 붙이므로 같은 라벨의 섹션이 시장 수만큼
    있다. 한 섹션만 고르면 앞선 시장의 내용이 통째로 사라지고, 남은 섹션이 모든
    시장의 것으로 저장된다.
    """
    text = str(markdown or "")
    if not text or not headings:
        return []
    pattern = _heading_pattern(headings)
    sections: list[tuple[str, str]] = []
    for match in pattern.finditer(text):
        heading = re.sub(r"^#+\s*", "", match.group(0)).strip()
        tail = text[match.end():]
        next_heading = re.search(r"(?m)^#{1,3}\s+", tail)
        body = tail[: next_heading.start()] if next_heading else tail
        sections.append((heading, body.strip()))
    return sections


def extract_section(markdown: str, headings: list[str]) -> tuple[str, str]:
    """The first matching section. 여러 섹션이 있으면 ``extract_sections()``를 쓴다."""
    sections = extract_sections(markdown, headings)
    return sections[0] if sections else ("", "")


def _bullet_texts(section_body: str) -> list[str]:
    rows: list[str] = []
    for line in str(section_body or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        m = re.match(r"^(?:[-*]\s+|\d+[.)]\s+)(.+)$", raw)
        if m:
            rows.append(_clean_text(m.group(1)))
    if rows:
        return rows
    # Fallback for compact prose sections: keep short standalone sentences only.
    sentences = re.split(r"(?<=[.!?。])\s+|\n+", section_body)
    return [_clean_text(s) for s in sentences if 12 <= len(_clean_text(s)) <= 220][:6]


def checkpoints_from_markdown(
    markdown: str,
    *,
    artifact_type: str,
    artifact_id: str = "",
    headings: list[str] | None = None,
    scope: str = "market",
    ticker: str = "",
    topic: str = "",
    confidence: str = "low",
    limit: int = 8,
) -> list[dict]:
    headings = headings or ["앞으로 확인할 체크포인트", "내일 확인할 체크포인트", "다음 체크포인트", "체크포인트"]
    rows: list[dict] = []
    for heading, body in extract_sections(markdown, headings):
        if not body or len(rows) >= limit:
            continue
        rows.extend(checkpoints_from_list(
            _bullet_texts(body),
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            scope=scope,
            ticker=ticker,
            topic=topic,
            source_section=heading,
            confidence=confidence,
            limit=limit - len(rows),
        ))
    return rows[:limit]


def checkpoints_from_thesis_delta(delta: dict, *, artifact_id: str = "") -> list[dict]:
    ticker = str(delta.get("ticker") or "").upper()
    return checkpoints_from_list(
        delta.get("nextCheckpoints") or [],
        artifact_type="thesis_delta",
        artifact_id=artifact_id or delta.get("deltaId") or delta.get("generatedAt") or "",
        scope="company",
        ticker=ticker,
        topic=delta.get("company") or ticker,
        source_section="nextCheckpoints",
        confidence="medium",
    )


def checkpoints_from_regime_state(state: dict, *, artifact_id: str = "") -> list[dict]:
    return checkpoints_from_list(
        state.get("nextCheckpoints") or state.get("next_checkpoints") or [],
        artifact_type="regime_state",
        artifact_id=artifact_id or state.get("stateId") or state.get("state_id") or "",
        scope="market",
        topic=state.get("stateLabel") or state.get("state_label") or state.get("story") or "",
        source_section="nextCheckpoints",
        confidence="medium",
    )
