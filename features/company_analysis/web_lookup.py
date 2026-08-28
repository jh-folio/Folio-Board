"""회사 자료 공백을 웹에서 메운다 — **찾기 전용** 패스.

로컬 색인은 보관 기간상 약 3개월이라, 뉴스가 거의 없는 종목은 구조적으로 채울 수 없다.
실측(저장된 4건): 로컬 문서가 11 / 5 / 2 / **0**건이고, 문서 0건인 Howmet은 데이터 갭
6개가 전부 "실적발표 프레젠테이션·컨퍼런스콜·증권사 리포트가 없다"였다.

딥 리서치에서 네 번 실패하고 얻은 결론이 그대로 적용된다 — **찾기와 쓰기를 분리한다.**
본문 생성 호출에 "필요하면 검색하라"를 얹는 방식은 도구 활성화·팩 허가문·겉 프롬프트
허가·축별 의무 네 가지 모두 실패했고(신규 URL 0~1건), 순수한 찾기 과제를 주자 곧바로
검색했다(사실 12건·발언 6건).

기업분석에서 값진 것:
- 최근 분기 실적과 가이던스 (로컬 filings는 연차 위주다)
- **경영진 컨퍼런스콜 발언** — 누가 언제 무슨 취지로
- 가이던스 변경에 대한 시장 반응

경계:
- 찾아온 사실은 **원장에 등재해야** 본문이 인용한다. 등재하지 않으면 계약상 인용할
  자격이 없는 자료가 된다(딥 리서치 실측: 등재 전 1건 → 등재 후 12/13건).
- **한 출처는 한 ID를 갖는다.** 사실마다 번호를 매기면 원장의 URL 중복 제거와 어긋나
  본문이 인용한 ID가 원장에 없어진다(실측 28건 중 10건이 그렇게 무효가 됐다).
- 허용 목록(`web_search_scope`) 밖은 쓰지 않는다. 회사 공식 도메인은 그 회사 분석에서만
  허용된다.
- 실패해도 보고서를 죽이지 않는다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

WebCall = Callable[[str, str], str]

# 로컬 보조 자료가 이보다 적으면 웹으로 메운다. 실측 4건 중 3건이 여기 걸린다.
THIN_DOCUMENT_COUNT = 6
_MAX_ROWS = 8


PROMPT = """당신은 조사원이다. 아래 회사에 대해 **웹에서 사실을 찾아** 보고하라.
글을 쓰지 말고 찾은 것만 돌려준다.

무엇을 찾는가 (이 순서로):
1. 가장 최근 분기 실적 — 매출·이익과 전년 대비, 그리고 회사가 제시한 가이던스
2. **경영진의 실제 발언** — 실적발표·컨퍼런스콜에서 누가(이름과 직함) 무슨 취지로 말했는지
3. 가이던스나 전망이 바뀐 것이 있으면 무엇이 어떻게 바뀌었는지

규칙:
- 허용 출처 목록 안에서만 찾는다. 목록 밖에서 본 것은 넣지 않는다.
- 사실마다 **출처 URL을 반드시** 붙인다. URL이 없는 사실은 넣지 마라.
- 수치는 값과 기간을 함께 적는다(예: "2026년 2분기 매출 $8.7B, 전년 대비 +22%").
- 발언은 **이름과 직함**을 그대로 적는다. "경영진은"으로 뭉개지 마라.
- 찾지 못하면 빈 배열을 돌려준다. 지어내지 마라.
- 주가 전망이나 투자 의견은 찾지 마라. 사실만 가져온다.

JSON 객체 하나만 출력하라:
{"facts": [{"statement": "사실 한 문장", "url": "https://…"}], "quotes": [{"who": "이름·직함", "when": "시점", "what": "발언 요지", "url": "https://…"}]}"""


def needs_web_lookup(*, document_count: int, data_gaps=None) -> bool:
    """웹으로 메워야 하는가.

    개수만 보지 않는다 — 자료가 있어도 최근 실적·IR이 통째로 비면 그 회사의 지금을
    말할 수 없다. 데이터 갭이 그것을 이미 알고 있다.
    """
    if int(document_count or 0) < THIN_DOCUMENT_COUNT:
        return True
    rows = (data_gaps or {}).get("gaps") if isinstance(data_gaps, dict) else (data_gaps or [])
    return any(
        any(word in str(row.get("label") or row.get("message") or "") for word in ("실적", "IR", "가이던스"))
        for row in rows or []
        if isinstance(row, dict)
    )


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
        if len(out) >= _MAX_ROWS:
            break
    return out


def lookup_company(company: dict, scope_text: str, run_call: WebCall) -> dict:
    """회사 하나에 대해 웹에서 사실과 발언을 찾아 온다. 실패해도 예외를 올리지 않는다."""
    name = str((company or {}).get("name") or "").strip()
    ticker = str((company or {}).get("ticker") or "").strip()
    if not name and not ticker:
        return {"status": "skipped", "facts": [], "quotes": []}
    context = "\n\n".join(
        block for block in [
            f"회사: {name} ({ticker})".strip(),
            scope_text,
        ] if block
    )
    try:
        payload = _extract(run_call(PROMPT, context))
    except Exception:  # noqa: BLE001 - 조회 실패가 보고서를 죽이지 않는다
        return {"status": "unavailable", "facts": [], "quotes": []}
    facts = _rows(payload.get("facts"), ("statement",))
    quotes = _rows(payload.get("quotes"), ("who", "when", "what"))
    return {
        "status": "ok" if (facts or quotes) else "empty",
        "ticker": ticker,
        "facts": facts,
        "quotes": quotes,
    }


def assign_source_ids(row: dict) -> dict:
    """인용 ID를 URL 기준으로 매긴다.

    사실마다 새 번호를 매기면 원장이 URL로 중복을 제거하는 순간 조회 블록이 인용하라고
    알려 준 ID의 일부가 원장에 없어진다(딥 리서치 실측: 28건 중 10건). 같은 문서에서
    나온 여러 사실은 한 출처의 여러 서술이므로 ID를 공유하는 것이 사실과도 맞는다.
    """
    by_url: dict[str, str] = {}
    for item in (row.get("facts") or []) + (row.get("quotes") or []):
        url = str(item.get("url") or "")
        if url not in by_url:
            by_url[url] = f"web_{len(by_url) + 1:03d}"
        item["sourceId"] = by_url[url]
    return row


def web_source_items(row: dict) -> list[dict]:
    """조회 결과를 원장 항목으로. 본문이 `web_001`로 인용할 수 있게 한다."""
    items: list[dict] = []
    seen: set[str] = set()
    for item in (row.get("facts") or []) + (row.get("quotes") or []):
        source_id = str(item.get("sourceId") or "")
        url = str(item.get("url") or "")
        if not source_id or source_id in seen or not url.startswith("http"):
            continue
        seen.add(source_id)
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


def speaker_sources(row: dict) -> list[dict]:
    """발언 근거와 화자의 직함. 계약이 본문의 귀속 여부를 이것으로 본다.

    사람 이름은 대조할 수 없다 — 원문이 "Colette Kress·CFO"인데 본문은 "크레스 CFO"라
    글자가 어긋난다. 직함은 두 표기에 함께 남는다.
    """
    from features.common.report_prose import speaker_identity

    out: list[dict] = []
    for quote in row.get("quotes") or []:
        identity = speaker_identity(quote.get("who"))
        if quote.get("sourceId") and (identity["role"] or identity["name"]):
            out.append({"sourceId": str(quote["sourceId"]), **identity})
    return out


def render_lookup(row: dict) -> str:
    """생성 컨텍스트에 실을 블록."""
    facts = row.get("facts") or []
    quotes = row.get("quotes") or []
    if not facts and not quotes:
        return ""
    lines = [
        "## 웹에서 찾은 최근 사실 (로컬 자료에 없던 것)",
        "허용 출처에서 직접 확인한 내용입니다. 각 줄 앞의 `web_xxx`가 근거 ID이며,",
        "로컬 근거와 똑같이 섹션 태그에 쓸 수 있습니다.",
        "발언은 **이름과 직함을 그대로** 본문에 쓰세요 — 「경영진은」으로 뭉개지 마세요.",
        "여기 없는 사실을 웹에서 본 것처럼 쓰지 마세요.",
        "",
    ]
    for fact in facts:
        lines.append(f"- [{fact.get('sourceId', '')}] {fact['statement']} — {fact['url']}")
    for quote in quotes:
        who = " / ".join(part for part in (quote.get("who"), quote.get("when")) if part)
        lines.append(f"- [{quote.get('sourceId', '')}] (발언) {who}: {quote.get('what', '')} — {quote['url']}")
    return "\n".join(lines)


def lookup_summary(row: dict) -> dict:
    row = row or {}
    return {
        "status": str(row.get("status") or "skipped"),
        "factCount": len(row.get("facts") or []),
        "quoteCount": len(row.get("quotes") or []),
        "speakerSources": speaker_sources(row),
        "urls": sorted({
            item["url"]
            for item in (row.get("facts") or []) + (row.get("quotes") or [])
            if item.get("url")
        }),
    }


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "").removeprefix("www.")


__all__ = [
    "PROMPT",
    "THIN_DOCUMENT_COUNT",
    "assign_source_ids",
    "lookup_company",
    "lookup_summary",
    "needs_web_lookup",
    "render_lookup",
    "speaker_sources",
    "web_source_items",
]
