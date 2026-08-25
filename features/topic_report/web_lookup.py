"""과거 국면을 웹에서 직접 찾아 오는 전용 조회.

축별 브리프 호출에 "필요하면 검색도 하라"고 얹는 방식은 네 번 시도해 모두 실패했다
(도구 활성화 → 팩 허가문 → 겉 프롬프트 허가 → 축별 의무). 실측으로 웹에서 새로 온
URL이 0~1건이었다.

이유는 **일의 모양**이다. 브리프 호출은 "주어진 근거로 이 축을 정리하라"는 쓰기 과제라,
모델은 팩에 근거가 있으면 충분하다고 판단한다. 반면 같은 어댑터에 "2024년 8월 엔캐리
청산 당시 닛케이가 얼마나 빠졌나, URL과 함께 답하라"는 **찾기 과제**를 주면 곧바로
검색해서 정확한 사실을 가져왔다(닛케이 12.4%, 31,458.42, URL 2건).

그래서 찾기와 쓰기를 분리한다. 이 모듈은 찾기만 한다.

발동 조건은 개수가 아니라 **시점**이다. 로컬 색인은 보관 기간상 약 3개월이라, 그 창
밖의 국면은 근거가 몇 건 잡히든 실제로는 답할 수 없다 — 실측으로 "2021~2022 인플레이션"
축이 근거 4건을 받았지만 전부 2021년을 스쳐 언급한 2026년 기사였다.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable

WebCall = Callable[[str, str], str]

MAX_LOOKUPS = 4
_MAX_FACTS = 6
_YEAR = re.compile(r"(?:19|20)\d{2}")


def historical_years(text: str, *, as_of: str = "") -> list[str]:
    """이 축이 가리키는 과거 연도. 올해와 작년은 로컬 색인이 닿을 수 있으므로 뺀다."""
    try:
        current = dt.date.fromisoformat(str(as_of or "")[:10]).year
    except Exception:
        current = dt.date.today().year
    years = []
    for raw in _YEAR.findall(str(text or "")):
        year = int(raw)
        if year < current and raw not in years:
            years.append(raw)
    return years


def needs_web_lookup(axis: dict, questions: list[str], evidence_count: int, *, as_of: str = "") -> bool:
    """웹으로 찾아야 하는 축인가.

    개수만 보면 안 된다 — 스쳐 지나가는 언급으로도 근거 개수는 찬다. 과거 시점을
    가리키는 축은 개수와 무관하게 로컬로 답할 수 없다.
    """
    text = " ".join([str(axis.get("label") or ""), *[str(q) for q in questions or []]])
    if historical_years(text, as_of=as_of):
        return True
    return evidence_count < 3


_PROMPT = """당신은 조사원이다. 아래 주제에 대해 **웹에서 사실을 찾아** 보고하라.
글을 쓰지 말고 찾은 것만 돌려준다.

규칙:
- 허용 출처 목록 안에서만 찾는다. 목록 밖에서 본 것은 넣지 않는다.
- 사실마다 **출처 URL을 반드시** 붙인다. URL이 없는 사실은 넣지 마라.
- 수치는 값과 시점을 함께 적는다(예: "닛케이225 -12.4%, 2024-08-05 종가 31,458.42").
- 정책 당국자·시장 참가자의 실제 발언이 있으면 누가 언제 무슨 취지로 말했는지 적는다.
- 찾지 못하면 빈 배열을 돌려준다. 지어내지 마라.

JSON 객체 하나만 출력하라:
{{"facts": [{{"statement": "사실 한 문장", "url": "https://…"}}], "quotes": [{{"who": "이름·직책", "when": "시점", "what": "발언 요지", "url": "https://…"}}]}}"""


def _extract(text: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.IGNORECASE | re.DOTALL)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return {}


def _rows(values, keys: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []
    for row in values or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        cleaned = {key: " ".join(str(row.get(key) or "").split())[:300] for key in keys}
        if not any(cleaned.values()):
            continue
        cleaned["url"] = url[:400]
        out.append(cleaned)
        if len(out) >= _MAX_FACTS:
            break
    return out


def lookup_axis(axis: dict, questions: list[str], asked: str, scope_text: str, run_call: WebCall) -> dict:
    """한 축에 대해 웹에서 사실과 발언을 찾아 온다. 실패해도 예외를 올리지 않는다."""
    context = "\n\n".join(
        block
        for block in [
            f"보고서 전체 질문:\n{asked}" if asked else "",
            f"찾을 주제: {axis.get('label', '')}",
            "답해야 할 것:\n" + "\n".join(f"- {q}" for q in questions[:4]) if questions else "",
            scope_text,
        ]
        if block
    )
    try:
        payload = _extract(run_call(_PROMPT, context))
    except Exception:
        return {"axisKey": str(axis.get("key") or ""), "status": "unavailable", "facts": [], "quotes": []}
    facts = _rows(payload.get("facts"), ("statement",))
    quotes = _rows(payload.get("quotes"), ("who", "when", "what"))
    return {
        "axisKey": str(axis.get("key") or ""),
        "label": str(axis.get("label") or ""),
        "status": "ok" if (facts or quotes) else "empty",
        "facts": facts,
        "quotes": quotes,
    }


def assign_source_ids(rows) -> list[dict]:
    """조회 결과에 인용 ID를 매긴다. 렌더와 원장이 같은 ID를 써야 태그가 맞는다.

    번호는 **URL 기준**이다. 사실마다 새 번호를 매기면 원장이 URL로 중복을 제거하는
    순간 조회 블록이 인용하라고 알려 준 ID의 일부가 원장에 없게 된다 — 모델은 시킨 대로
    인용하고 계약은 그것을 `unknown_source_tag`(심각도 60)로 잡는다(실측: 28건 중
    10건이 모르는 ID가 되어 품질 상한이 89로 묶였다). 같은 문서에서 나온 여러 사실은
    한 출처의 여러 서술이므로 ID를 공유하는 것이 사실과도 맞는다.
    """
    by_url: dict[str, str] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for item in (row.get("facts") or []) + (row.get("quotes") or []):
            url = str(item.get("url") or "")
            if url not in by_url:
                by_url[url] = f"web_{len(by_url) + 1:03d}"
            item["sourceId"] = by_url[url]
    return list(rows or [])


def render_lookup(rows) -> str:
    """축별 브리프와 본문 생성이 함께 읽는 블록."""
    usable = [row for row in rows or [] if row.get("facts") or row.get("quotes")]
    if not usable:
        return ""
    lines = [
        "=" * 60,
        "## 웹에서 찾은 사실 (로컬 자료에 없던 것)",
        "아래는 허용 출처에서 직접 확인한 내용입니다. 각 줄 앞의 `web_xxx`가 그 사실의 근거 ID이며,",
        "다른 근거와 똑같이 섹션 태그에 쓸 수 있습니다. 본문에는 출처 이름과 URL을 함께 인용하세요.",
        "여기 없는 사실을 웹에서 본 것처럼 쓰지 마세요.",
        "",
    ]
    for row in usable:
        lines.append(f"### {row.get('label', '')}")
        for fact in row.get("facts") or []:
            lines.append(f"- [{fact.get('sourceId', '')}] {fact['statement']} — {fact['url']}")
        for quote in row.get("quotes") or []:
            who = " / ".join(part for part in (quote.get("who"), quote.get("when")) if part)
            lines.append(f"- [{quote.get('sourceId', '')}] (발언) {who}: {quote.get('what', '')} — {quote['url']}")
        lines.append("")
    return "\n".join(lines)


def speaker_sources(rows) -> list[dict]:
    """발언 근거와 그 화자의 직함.

    사람 이름은 대조할 수 없다 — 원문은 "Jerome H. Powell"인데 본문은 "파월"이라 글자가
    겹치지 않는다. 직함(의장·총재·이사)은 두 표기에 함께 남으므로 그것으로 귀속 여부를
    본다. 계약 검사가 이 목록을 받아 "본문이 화자를 밝혔는가"를 판정한다.
    """
    from features.topic_report.report_contract import SPEAKER_ROLE_WORDS

    out: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for quote in row.get("quotes") or []:
            who = str(quote.get("who") or "")
            role = next((word for word in SPEAKER_ROLE_WORDS if word in who), "")
            if role and quote.get("sourceId"):
                out.append({"sourceId": str(quote["sourceId"]), "role": role})
    return out


def lookup_summary(rows) -> dict:
    rows = [row for row in rows or [] if isinstance(row, dict)]
    return {
        "speakerSources": speaker_sources(rows),
        "axisCount": len(rows),
        "okCount": sum(1 for row in rows if row.get("status") == "ok"),
        "factCount": sum(len(row.get("facts") or []) for row in rows),
        "quoteCount": sum(len(row.get("quotes") or []) for row in rows),
        "urls": sorted({
            item["url"]
            for row in rows
            for item in (row.get("facts") or []) + (row.get("quotes") or [])
            if item.get("url")
        }),
    }




def web_source_items(rows) -> list[dict]:
    """조회 결과를 source ledger 항목으로. 본문이 `web_001`로 인용할 수 있게 한다."""
    items: list[dict] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for item in (row.get("facts") or []) + (row.get("quotes") or []):
            url = str(item.get("url") or "")
            if not url.startswith("http"):
                continue
            source_id = str(item.get("sourceId") or f"web_{len(items) + 1:03d}")
            if any(existing["sourceId"] == source_id for existing in items):
                continue  # 같은 출처의 다른 서술. 원장에는 한 줄이면 된다.
            title = item.get("statement") or " ".join(
                part for part in (item.get("who"), item.get("what")) if part
            )
            items.append({
                "id": source_id,
                "sourceId": source_id,
                "title": str(title)[:200],
                "source": _host(url),
                "url": url,
                "date": str(item.get("when") or "")[:10],
                "type": "web_reference",
                "evidenceRole": "supporting",
            })
    return items


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "").removeprefix("www.")


__all__ = [
    "MAX_LOOKUPS",
    "historical_years",
    "lookup_axis",
    "lookup_summary",
    "needs_web_lookup",
    "render_lookup",
    "assign_source_ids",
    "speaker_sources",
    "web_source_items",
]
