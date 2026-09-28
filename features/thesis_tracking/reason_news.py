"""이유와 연결된 새 소식 — Watchlist 상세·목록이 함께 읽는 읽기 projection.

"새 소식"은 **사용자가 적은 판단 조건과 문장이 같은 구조화 확인 항목**이 뉴스 제목에서
찾은 근거다. 확인 항목 판정(`checkpoint_verdicts`)이 RSS 수집 때 규칙으로 만든 사본을
읽기만 하며, 여기서 새 의미 판정을 하지 않는다.

- 소식은 사실이지 판정이 아니다. 강화/약화 같은 결론을 싣지 않는다.
- 사용자가 "그대로 두기"로 본 소식과, 이유를 수정하며 연결한 소식은 다시 세지 않는다
  (정확한 참조 키로만 비교한다 — 같은 제목의 다른 URL은 다른 소식이다).
- 이유를 저장하기 전 날짜의 소식은 "새 소식"이 아니다.
- 대조할 단어가 하나도 없으면 찾지 않았다는 사실(`searchReady=False`)을 그대로 알린다.
  "새 소식 없음"과 "찾지 않음"을 섞지 않는다.
"""
from __future__ import annotations

import re
import hashlib

from features.common.research_schema.tracked_checkpoints import MAX_ITEM_CHARS, partition_checkpoints

DECISION_SOURCES = frozenset({"manual_review"})
KEEP_OUTCOME = "no_material_change"
MAX_ITEMS = 20


def _public_url(value) -> str:
    url = str(value or "").strip()
    return url[:2048] if url.lower().startswith(("https://", "http://")) else ""


def _item_text(value) -> str:
    """확인 항목 문장 정규화와 같은 규칙(공백 한 칸, 길이 상한)."""
    return re.sub(r"\s+", " ", str(value or "")).strip()[:MAX_ITEM_CHARS]


def news_key(item: dict) -> str:
    """소식의 정확한 참조 키. URL이 있으면 URL, 없으면 날짜+제목."""
    url = _public_url(item.get("url") or item.get("docId") or item.get("id"))
    if url:
        return url if len(url) <= 200 else "url-sha256:" + hashlib.sha256(url.encode("utf-8")).hexdigest()
    label = f"{str(item.get('date') or '')[:10]}|{str(item.get('title') or '').strip().lower()}"
    return label if len(label) <= 200 else "title-sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _acknowledged(reason: dict | None, review_events: list) -> set:
    keys: set = set()
    refs = list((reason or {}).get("basisRefs") or [])
    for event in review_events or []:
        if event.get("source") in DECISION_SOURCES:
            refs.extend(event.get("basisRefs") or [])
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        # 판단 기록은 `key`에, 이유 개정은 `id`와 `url`에 소식 참조를 싣는다.
        # 어느 쪽으로 들어와도 같은 소식을 알아보도록 후보를 모두 넣는다.
        for key in (str(ref.get("key") or ""), str(ref.get("id") or ""), news_key(ref)):
            if key.strip("|"):
                keys.add(key)
    return keys


def reason_news(thesis: dict | None, reason: dict | None, review_events: list) -> dict:
    """현재 이유 개정 기준의 새 소식 묶음.

    반환: ``{"items": [...], "count": n, "since": iso, "searchReady": bool,
    "keywords": [...], "lastDecisionAt": iso}``.
    """
    empty = {"items": [], "count": 0, "since": "", "searchReady": False, "keywords": [], "lastDecisionAt": ""}
    if not thesis or not reason or not str(thesis.get("core_thesis") or "").strip():
        return empty
    # 확인 항목 문장은 MAX_ITEM_CHARS에서 잘린다. 같은 길이로 잘라 비교해야 긴 조건도 이어진다.
    conditions = {_item_text(text) for text in (thesis.get("falsification_triggers") or []) if _item_text(text)}
    structured, _invalid, _templates = partition_checkpoints(
        thesis.get("next_checkpoints"),
        scope="thesis",
        scope_key=str(thesis.get("ticker") or ""),
        forbidden_keywords=[thesis.get("ticker"), thesis.get("company")],
    )
    linked = [item for item in structured if _item_text(item.get("item")) in conditions]
    keywords: list = []
    for checkpoint in linked:
        for word in (checkpoint.get("matchers") or {}).get("keywords") or []:
            if word not in keywords:
                keywords.append(word)
    since = str(reason.get("recordedAt") or "")
    since_day = since[:10]
    acknowledged = _acknowledged(reason, review_events)
    # "그대로 두기"(no_material_change)만 사용자의 유지 판단이다. 이전 화면의 다른 검토 결과
    # (새 자료 미확보 등)를 "그대로 두었다"로 부르지 않는다.
    decisions = [event for event in review_events or []
                 if event.get("source") in DECISION_SOURCES and event.get("outcome") == KEEP_OUTCOME]
    items: dict = {}
    for checkpoint in linked:
        last = checkpoint.get("lastVerdict") or {}
        for evidence in last.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            title = str(evidence.get("title") or "").strip()
            day = str(evidence.get("date") or "")[:10]
            if not title or not day or (since_day and day < since_day):
                continue
            row = {"title": title[:220], "date": day, "url": _public_url(evidence.get("docId") or evidence.get("url")),
                   "condition": str(checkpoint.get("item") or "")}
            key = news_key(row)
            if key in acknowledged or key in items:
                continue
            items[key] = {**row, "key": key}
    ordered = sorted(items.values(), key=lambda row: (row["date"], row["title"]), reverse=True)[:MAX_ITEMS]
    return {
        "items": ordered,
        "count": len(ordered),
        "since": since,
        "searchReady": bool(keywords),
        "keywords": keywords[:12],
        "lastDecisionAt": str(decisions[0].get("reviewedAt") or "") if decisions else "",
    }
