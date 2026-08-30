"""구조화 체크포인트 — "다음에 확인할 것"을 기계가 읽을 수 있게 만든 레코드.

저장 위치는 기존 컬럼 그대로다(내러티브 `market_narrative_states.next_checkpoints_json`,
thesis `thesis.next_checkpoints_json`). 새 테이블을 만들지 않는다. 리스트의 원소는

- `str`  : 규칙 엔진이 매 갱신마다 다시 만드는 템플릿 문장(기존 동작)
- `dict` : 아래 스키마의 구조화 체크포인트(판정 pass의 대상)

둘 중 하나이며 **읽는 쪽은 둘 다 받는다**. 기존 저장본은 전부 `str`이므로
호환이 곧 이 모듈의 첫 계약이다.

    { "id": "cp_<정규화(item+matchers) 해시 8자>",
      "item": "전력 설비 기업 실적 가이던스 상향",
      "direction": "supporting" | "challenging",
      "matchers": {"tickers": [...], "keywords": [...]},
      "dueBy": "2026-09-15" | None,
      "status": "open" | "confirmed" | "challenged" | "expired",
      "createdAt": "...",
      "lastVerdict": {"verdict": ..., "at": ..., "evidence": [{...}]},
      "history": [{"at", "from", "to", "verdict"}] }

검증 실패 원소는 **버린다**. 규칙 템플릿 문장이 그 자리를 대신하므로 화면이 비지
않고(0.6 계획 §8.1 결정), 버려진 체크포인트는 판정 대상에서도 빠져 가짜 판정이
생기지 않는다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

DIRECTION_CHOICES = frozenset({"supporting", "challenging"})
CHECKPOINT_STATUS_CHOICES = frozenset({"open", "confirmed", "challenged", "expired"})
CHECKPOINT_STATUS_DEFAULT = "open"
VERDICT_CHOICES = frozenset({"confirmed", "challenged", "no_signal"})
EVIDENCE_ROLE_CHOICES = frozenset({"supporting", "challenging", "neutral"})
SCOPE_CHOICES = frozenset({"narrative", "thesis"})

MAX_CHECKPOINTS = 8
MAX_HISTORY = 20
MAX_EVIDENCE_COPIES = 3
MAX_ITEM_CHARS = 120
MAX_KEYWORDS = 6
MAX_TICKERS = 6
KEYWORD_MIN_CHARS = 2
KEYWORD_MAX_CHARS = 40

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


def squash(value) -> str:
    """공백 제거 + 소문자. 한국어 복합어 띄어쓰기 편차를 흡수한다.

    `report_contract.unanswered_questions`와 같은 처방이다 — "기간 프리미엄"과
    "기간프리미엄"이 다른 글자로 취급되면 매칭이 글쓴이의 띄어쓰기 습관에 좌우된다.
    """
    return re.sub(r"\s+", "", str(value or "")).lower()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _text(value, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _date_part(value) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else ""


def is_tracked_checkpoint(value) -> bool:
    """구조화 체크포인트 후보인지 — dict이면 후보다(검증은 normalize가 한다)."""
    return isinstance(value, dict)


def checkpoint_label(value, limit: int = 240) -> str:
    """str/dict 어느 쪽이든 사람이 읽는 한 줄을 돌려준다.

    구조화 체크포인트가 문자열만 기대하는 옛 소비자(Agent context pack, Delta
    markdown, 리뷰 상태 라벨)로 흘러가도 dict 표현이 그대로 노출되지 않게 한다.
    """
    if isinstance(value, dict):
        for key in ("item", "checkpoint", "label", "text", "title"):
            text = _text(value.get(key), limit)
            if text:
                return text
        return ""
    return _text(value, limit)


def checkpoint_labels(values, limit: int = 240) -> list[str]:
    out = []
    for value in values or []:
        text = checkpoint_label(value, limit)
        if text:
            out.append(text)
    return out


def checkpoint_id(item, tickers, keywords) -> str:
    """재생성·중복 판별 키. item과 matchers가 같으면 같은 id다."""
    raw = "|".join([
        squash(item),
        ",".join(sorted({str(t).strip().upper() for t in tickers or [] if str(t).strip()})),
        ",".join(sorted({squash(k) for k in keywords or [] if squash(k)})),
    ])
    return "cp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def _normalize_keywords(values, forbidden: set) -> list:
    out: list = []
    seen: set = set()
    for value in values or []:
        text = _text(value, KEYWORD_MAX_CHARS + 1)
        if not (KEYWORD_MIN_CHARS <= len(text) <= KEYWORD_MAX_CHARS):
            continue
        key = squash(text)
        # 상태 라벨 전문을 keyword로 쓰면 그 상태의 모든 근거가 매칭돼 과잉 확인이 된다
        # (근거의 matched_terms에 state_key 자체가 들어 있다 — 실측).
        if not key or key in seen or key in forbidden:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= MAX_KEYWORDS:
            break
    return out


def _normalize_tickers(values) -> list:
    out: list = []
    seen: set = set()
    for value in values or []:
        text = str(value or "").strip().upper()
        if not _TICKER_RE.match(text) or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= MAX_TICKERS:
            break
    return out


def _normalize_evidence_copies(values) -> list:
    out: list = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        role = str(value.get("role") or "").strip().lower()
        out.append({
            "memoryId": _text(value.get("memoryId") or value.get("memory_id"), 64),
            "date": _text(value.get("date"), 32),
            "title": _text(value.get("title"), 220),
            "role": role if role in EVIDENCE_ROLE_CHOICES else "",
        })
        if len(out) >= MAX_EVIDENCE_COPIES:
            break
    return out


def _normalize_last_verdict(value):
    if not isinstance(value, dict):
        return None
    verdict = str(value.get("verdict") or "").strip().lower()
    if verdict not in VERDICT_CHOICES:
        return None
    at = _text(value.get("at"), 40)
    if not at:
        return None
    return {"verdict": verdict, "at": at, "evidence": _normalize_evidence_copies(value.get("evidence"))}


def _normalize_history(values) -> list:
    out: list = []
    for value in values or []:
        if not isinstance(value, dict):
            continue
        at = _text(value.get("at"), 40)
        from_status = str(value.get("from") or "").strip().lower()
        to_status = str(value.get("to") or "").strip().lower()
        verdict = str(value.get("verdict") or "").strip().lower()
        if not at or from_status not in CHECKPOINT_STATUS_CHOICES or to_status not in CHECKPOINT_STATUS_CHOICES:
            continue
        out.append({
            "at": at,
            "from": from_status,
            "to": to_status,
            "verdict": verdict if verdict in VERDICT_CHOICES else "",
        })
    return out[-MAX_HISTORY:]


def normalize_tracked_checkpoint(
    raw,
    *,
    scope: str = "narrative",
    now: str = "",
    forbidden_keywords=(),
):
    """구조화 체크포인트를 검증·정규화한다. 실패하면 None(= 그 원소는 버린다).

    - 모르는 키는 제거한다(스키마 고정).
    - `item`은 120자로 자르고, 비어 있으면 버린다.
    - `direction`은 뜻이 뒤집히는 값이라 기본값을 주지 않는다 — enum을 벗어나면 버린다.
    - 내러티브는 keyword ≥1, thesis는 ticker ≥1 **그리고** keyword ≥1을 요구한다.
      티커만으로는 "그 회사 뉴스가 있다"이지 가설 신호가 아니다.
    """
    if not isinstance(raw, dict):
        return None
    scope = scope if scope in SCOPE_CHOICES else "narrative"
    now = now or _now_iso()
    item = _text(raw.get("item") or raw.get("checkpoint") or raw.get("label") or raw.get("text"), MAX_ITEM_CHARS)
    if not item:
        return None
    direction = str(raw.get("direction") or "").strip().lower()
    if direction not in DIRECTION_CHOICES:
        return None

    matchers = raw.get("matchers") if isinstance(raw.get("matchers"), dict) else {}
    forbidden = {squash(x) for x in forbidden_keywords or [] if squash(x)}
    keywords = _normalize_keywords(matchers.get("keywords"), forbidden)
    tickers = _normalize_tickers(matchers.get("tickers"))
    if not keywords:
        return None
    if scope == "thesis" and not tickers:
        return None

    status = str(raw.get("status") or "").strip().lower()
    if status not in CHECKPOINT_STATUS_CHOICES:
        status = CHECKPOINT_STATUS_DEFAULT
    created_at = _text(raw.get("createdAt") or raw.get("created_at"), 40) or now

    due_by = _text(raw.get("dueBy") or raw.get("due_by"), 10)
    if not _DATE_RE.match(due_by) or due_by <= _date_part(created_at):
        due_by = None

    return {
        "id": checkpoint_id(item, tickers, keywords),
        "item": item,
        "direction": direction,
        "matchers": {"tickers": tickers, "keywords": keywords},
        "dueBy": due_by,
        "status": status,
        "createdAt": created_at,
        "lastVerdict": _normalize_last_verdict(raw.get("lastVerdict")),
        "history": _normalize_history(raw.get("history")),
    }


def split_checkpoints(values, *, scope: str = "narrative", forbidden_keywords=(), now: str = ""):
    """저장된 리스트를 (구조화 체크포인트, 템플릿 문장)으로 가른다.

    검증에 실패한 dict는 어느 쪽에도 들어가지 않는다(계획 §8.1 — 버리고 템플릿이 대신한다).
    """
    structured: list = []
    templates: list = []
    seen_ids: set = set()
    for value in values or []:
        if is_tracked_checkpoint(value):
            normalized = normalize_tracked_checkpoint(
                value, scope=scope, now=now, forbidden_keywords=forbidden_keywords
            )
            if normalized and normalized["id"] not in seen_ids:
                seen_ids.add(normalized["id"])
                structured.append(normalized)
            continue
        text = _text(value, 500)
        if text:
            templates.append(text)
    return structured[:MAX_CHECKPOINTS], templates


def _resolved(checkpoint: dict) -> bool:
    return checkpoint.get("status") in {"confirmed", "challenged", "expired"}


def merge_checkpoint_lists(
    existing,
    incoming,
    *,
    scope: str = "narrative",
    forbidden_keywords=(),
    now: str = "",
) -> list:
    """새 구조화 목록을 기존 목록과 병합한다(생성·교체 경로).

    - `id`가 같은 것은 `status`·`history`·`lastVerdict`·`createdAt`을 승계한다.
      판정 결과는 판정 pass만 쓰므로 새 목록이 그것을 되돌리면 안 된다.
    - 새로 온 것은 추가한다.
    - 사라진 것 중 `open`은 유지하고, 해소된 것(confirmed/challenged/expired)은
      상한(8) 안에서 오래된 것부터 정리한다.
    """
    now = now or _now_iso()
    old, _ = split_checkpoints(existing, scope=scope, forbidden_keywords=forbidden_keywords, now=now)
    new, _ = split_checkpoints(incoming, scope=scope, forbidden_keywords=forbidden_keywords, now=now)
    by_id = {item["id"]: item for item in old}

    merged: list = []
    for item in new:
        prior = by_id.pop(item["id"], None)
        if prior:
            item = {
                **item,
                "status": prior.get("status", CHECKPOINT_STATUS_DEFAULT),
                "createdAt": prior.get("createdAt") or item.get("createdAt"),
                "lastVerdict": prior.get("lastVerdict"),
                "history": list(prior.get("history") or []),
            }
        merged.append(item)

    leftovers = list(by_id.values())
    still_open = [item for item in leftovers if not _resolved(item)]
    resolved = sorted(
        (item for item in leftovers if _resolved(item)),
        key=lambda item: str(item.get("createdAt") or ""),
        reverse=True,
    )
    merged.extend(still_open)
    for item in resolved:
        if len(merged) >= MAX_CHECKPOINTS:
            break
        merged.append(item)
    return merged[:MAX_CHECKPOINTS]


def merge_with_templates(
    existing,
    templates,
    *,
    scope: str = "narrative",
    forbidden_keywords=(),
    now: str = "",
) -> list:
    """규칙 갱신용 병합 — 구조화 원소는 보존하고 템플릿 문장만 오늘 것으로 갈아끼운다.

    이 함수가 Stage A의 핵심이다. 예전에는 `refresh_regime_state`가 목록을 통째로
    덮어써서, 구조화 체크포인트를 만들어도 다음 갱신(서버 시작·RSS 수집마다 돈다)에
    status가 초기화됐다.
    """
    structured, _ = split_checkpoints(existing, scope=scope, forbidden_keywords=forbidden_keywords, now=now)
    fresh = [_text(t, 500) for t in templates or []]
    return structured + [t for t in fresh if t]


def append_history(checkpoint: dict, *, at: str, from_status: str, to_status: str, verdict: str) -> dict:
    """상태 전환 한 건을 이력에 남긴다(상한 20, 오래된 것부터 제거)."""
    history = list(checkpoint.get("history") or [])
    history.append({
        "at": at,
        "from": from_status if from_status in CHECKPOINT_STATUS_CHOICES else CHECKPOINT_STATUS_DEFAULT,
        "to": to_status if to_status in CHECKPOINT_STATUS_CHOICES else CHECKPOINT_STATUS_DEFAULT,
        "verdict": verdict if verdict in VERDICT_CHOICES else "",
    })
    checkpoint["history"] = history[-MAX_HISTORY:]
    return checkpoint
