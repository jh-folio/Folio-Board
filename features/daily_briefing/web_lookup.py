"""브리핑 웹 보완 — 찾기 전용 패스.

§6 규칙 9("웹 검색은 부족한 지수/가격 반응/공식 자료를 보완하는 용도")는 설계·문서·
프롬프트·API 배선·기본값 다섯 곳에 있었지만, 실제 사용 경로(CLI)에는 통로가 없었다 —
실측으로 최근 저장 브리핑 14건 전부 `mode: agent`이고 웹 기여 0건이었다. API 경로도
provider 웹 도구를 **쓰기 호출에** 얹는 방식이라, "쓰기 과제에 검색 얹기는 실패한다"는
이 프로젝트의 4회 실측이 그대로 적용될 수 있는 구조였다.

그래서 기업분석·딥 리서치와 같은 처방을 쓴다: **찾기를 쓰기에서 분리한다.**

발동 조건은 개수가 아니라 **무엇이 비었는가**다. 브리핑은 자료가 늘 많으므로
"문서 N건 미만" 같은 조건은 성립하지 않는다. 미국장 프록시(SPY/QQQ) 결측·정체,
한국장 핵심 수치 결측만 공백으로 보고, JP·유럽은 컨텍스트에 지수 수치 피드 자체가
없어 구조적 공백으로 등재한다. 공백이 없으면 호출도 없다.

경계:
- **찾아온 수치는 로컬 자료를 대체하지 않는다**(§6 규칙 9). 컨텍스트 블록이 그 경계를
  본문 생성 모델에게 그대로 말한다.
- 출처는 허용 목록 안에서만(`web_search_scope`). 목록을 못 읽으면 조회하지 않는다.
- 조회 실패는 브리핑을 죽이지 않는다 — 블록 없이 진행하고 `ok: False`를 남긴다.
"""
from __future__ import annotations

import json
import re

from features.common.engine_lookup import LookupCall, configured_lookup_call
from features.common.markets import market_definition
from features.common.web_search_scope import load_source_scope, render_scope_instruction

# 스냅샷 기준일이 발행일보다 이보다 오래 뒤처지면 "정체"로 본다. 휴장·주말이 겹쳐도
# 대표 지수가 나흘 넘게 멈추는 정규 상황은 없다.
STALE_DAYS = 4
# 한 번의 조회로 메우려는 공백 수 상한. 다 비었다는 것은 provider 전면 장애라
# 웹 조회가 아니라 스냅샷 복구가 답이다.
MAX_GAPS = 6


def _days_between(older: str, newer: str) -> int | None:
    try:
        from datetime import date

        a = date.fromisoformat(str(older)[:10])
        b = date.fromisoformat(str(newer)[:10])
        return (b - a).days
    except (ValueError, TypeError):
        return None


def market_gaps(scope: str, market_snapshot: dict | None, korea_market_data: dict | None, date: str) -> list[dict]:
    """이 시장 브리핑에서 로컬 수치가 비어 있는 자리.

    **쓰기 컨텍스트가 실제로 받는 피드 기준이다.** 대표지수 티커(^GSPC·^N225)는 어느
    시장도 스냅샷에 없다(실측) — 스냅샷은 미국 ETF 프록시(SPY/QQQ)와 거시 티커를,
    한국장 수치는 `korea_market_data`가 갖는다. JP·유럽 지수는 컨텍스트에 수치 피드
    자체가 없어 **구조적 공백**이다(로컬 기사가 종종 메우므로 블록이 기사 우선을
    함께 말한다). 여기서 새 조회를 하지 않는다.
    """
    gaps: list[dict] = []
    snapshot = market_snapshot or {}
    tickers = snapshot.get("tickers") if isinstance(snapshot.get("tickers"), dict) else {}

    def _fresh(row) -> bool:
        if not isinstance(row, dict) or row.get("last") in (None, ""):
            return False
        staleness = _days_between(str(row.get("asOfDate") or ""), date)
        return staleness is None or staleness <= STALE_DAYS

    if not snapshot or snapshot.get("ok") is False:
        gaps.append({
            "id": "snapshot_unavailable",
            "label": "시장 가격 스냅샷 전체",
            "detail": "가격 스냅샷 수집이 실패해 프록시·거시 수치가 없습니다.",
        })
    elif scope == "us" and not (_fresh(tickers.get("SPY")) or _fresh(tickers.get("QQQ"))):
        gaps.append({
            "id": "us_proxy_missing",
            "label": "미국 주요 지수 (S&P500·Nasdaq 종가 등락률)",
            "detail": "스냅샷의 지수 프록시(SPY/QQQ)가 없거나 기준일이 뒤처져 있습니다.",
        })

    if scope == "kr":
        kr = korea_market_data or {}
        indices = kr.get("indices") if isinstance(kr.get("indices"), dict) else {}
        if not kr or kr.get("ok") is False:
            gaps.append({
                "id": "kr_data_unavailable",
                "label": "한국장 핵심 수치 전체",
                "detail": "한국장 수치 수집이 실패했습니다.",
            })
        else:
            for name in ("KOSPI", "KOSDAQ"):
                row = indices.get(name) or {}
                if row.get("close") in (None, "") or row.get("changePct") in (None, ""):
                    gaps.append({
                        "id": f"kr_index_missing:{name}",
                        "label": f"{name} 종가 등락률",
                        "detail": "종가 등락률이 없습니다.",
                    })
            fx = kr.get("fx") if isinstance(kr.get("fx"), dict) else {}
            # fx는 {"USDKRW": {close, changePct, ...}} 모양이다.
            if not any(isinstance(row, dict) and row.get("close") not in (None, "") for row in fx.values()):
                gaps.append({
                    "id": "kr_fx_missing",
                    "label": "원/달러 환율 종가",
                    "detail": "환율 종가가 없습니다.",
                })

    # JP·유럽은 컨텍스트에 자기 지수 수치 피드가 없다. 로컬 기사가 종가를 다루는 날이
    # 많지만 그것은 확인해야 아는 일이고, 웹 보완이 §6 규칙 9가 말하는 "부족한 지수"
    # 바로 그 자리다.
    if scope == "jp":
        gaps.append({
            "id": "jp_index_feed_absent",
            "label": "닛케이 225·TOPIX 종가 등락률",
            "detail": "로컬 수치 피드가 일본 지수를 다루지 않습니다.",
        })
    if scope == "europe":
        gaps.append({
            "id": "europe_index_feed_absent",
            "label": "STOXX600·DAX·FTSE100 종가 등락률",
            "detail": "로컬 수치 피드가 유럽 지수를 다루지 않습니다.",
        })
    return gaps[:MAX_GAPS]


def needs_web_lookup(gaps: list[dict]) -> bool:
    return bool(gaps)


_LOOKUP_PROMPT = """당신은 시장 데이터 조사원입니다. 아래에 나열된 수치가 로컬 자료에 없습니다.
웹 검색으로 **그 수치만** 찾아 JSON 하나로 답하세요.

규칙:
- 새 분석이나 해석을 쓰지 마세요. 이것은 찾기 과제입니다.
- 수치마다 기준일과 출처 URL을 반드시 함께 적으세요. 기준일을 확인할 수 없는 수치는 싣지 마세요.
- 아래 허용 출처 목록 밖의 도메인은 쓰지 마세요.
- 찾지 못한 항목은 지어내지 말고 notFound에 남기세요.

출력 형식(JSON만):
{"facts": [{"item": "무엇", "value": "수치와 단위", "asOf": "YYYY-MM-DD", "source": "매체/기관", "url": "https://..."}],
 "notFound": ["못 찾은 항목"]}
"""


def lookup_briefing(scope: str, date: str, gaps: list[dict], lookup: LookupCall) -> dict:
    """공백 목록을 찾기 과제로 보내고 결과를 구조화한다. 실패는 ok=False로 돌아온다."""
    if not gaps:
        return {}
    source_scope = load_source_scope(None)
    if not (source_scope.official or source_scope.media):
        # 허용 목록을 못 읽으면 조회하지 않는다 — 목록 없이 웹을 여는 것보다 안 쓰는 편이 낫다.
        return {"ok": False, "reason": "source_scope_unavailable"}
    try:
        label = market_definition(scope).label_ko
    except Exception:
        label = scope
    context = "\n".join([
        f"브리핑 발행일: {date} / 대상 시장: {label}",
        "",
        "## 찾아야 할 수치",
        *[f"- {gap['label']}: {gap['detail']}" for gap in gaps],
        "",
        render_scope_instruction(source_scope),
    ])
    try:
        raw = lookup(_LOOKUP_PROMPT, context)
        payload = _parse_json(raw)
    except Exception as exc:  # noqa: BLE001 - 조회 실패가 브리핑을 죽이지 않는다
        return {"ok": False, "reason": type(exc).__name__}
    facts = [
        {
            "item": str(row.get("item") or "")[:120],
            "value": str(row.get("value") or "")[:120],
            "asOf": str(row.get("asOf") or "")[:10],
            "source": str(row.get("source") or "")[:80],
            "url": str(row.get("url") or "")[:300],
        }
        for row in (payload.get("facts") or [])
        if isinstance(row, dict) and row.get("value") and row.get("url")
    ]
    return {
        "ok": True,
        "gaps": [gap["id"] for gap in gaps],
        "facts": facts,
        "notFound": [str(item)[:120] for item in (payload.get("notFound") or [])][:MAX_GAPS],
    }


def _parse_json(raw: str) -> dict:
    text = str(raw or "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    payload = json.loads(match.group(0) if match else text)
    return payload if isinstance(payload, dict) else {}


def render_web_lookup(row: dict, gaps: list[dict]) -> str:
    """본문 생성 컨텍스트에 넣는 블록. 경계(보완이지 대체가 아님)를 함께 말한다."""
    if not row or not row.get("ok") or not row.get("facts"):
        return ""
    lines = [
        "## 웹에서 보완한 시장 수치",
        "로컬 스냅샷에 없어 웹에서 확인한 값입니다. 다음 항목이 비어 있었습니다: "
        + ", ".join(gap["label"] for gap in gaps) + ".",
        "",
        "| 항목 | 값 | 기준일 | 출처 |",
        "|---|---|---|---|",
    ]
    for fact in row["facts"]:
        lines.append(f"| {fact['item']} | {fact['value']} | {fact['asOf']} | [{fact['source']}]({fact['url']}) |")
    if row.get("notFound"):
        lines.append("")
        lines.append("웹에서도 확인하지 못한 항목: " + ", ".join(row["notFound"]) + " — 이 수치는 추정하지 말고 한계를 명시하세요.")
    lines += [
        "",
        "- 이 표는 **비어 있던 수치의 보완**입니다. 로컬 기사에 같은 수치가 있으면 로컬 기사를 우선하세요.",
        "- 표의 수치를 인용할 때는 기준일을 함께 적으세요.",
    ]
    return "\n".join(lines)


def web_supplement(
    scope: str,
    date: str,
    *,
    market_snapshot: dict | None,
    korea_market_data: dict | None,
    web_search: bool,
    lookup: LookupCall | None = None,
) -> tuple[str, dict]:
    """(컨텍스트 블록, 저장용 요약). **두 생성 경로가 이 함수 하나를 부른다** —
    조립기를 공유해도 호출부가 넘기는 인자가 갈리면 같은 일이 난다(§6 규칙 14)."""
    gaps = market_gaps(scope, market_snapshot, korea_market_data, date)
    summary: dict = {"webSearch": bool(web_search), "gaps": [gap["id"] for gap in gaps]}
    if not web_search or not needs_web_lookup(gaps):
        return "", summary
    row = lookup_briefing(scope, date, gaps, lookup or briefing_lookup_call())
    summary.update({k: v for k, v in row.items() if k != "gaps"})
    return render_web_lookup(row, gaps), summary


def briefing_lookup_call(*, adapter: str = "", job_id: str = "") -> LookupCall:
    return configured_lookup_call(
        adapter=adapter,
        job_id=job_id,
        api_timeout_env="BRIEFING_LOOKUP_API_TIMEOUT_SECONDS",
        cli_timeout_env="BRIEFING_LOOKUP_CLI_TIMEOUT_SECONDS",
    )


__all__ = [
    "briefing_lookup_call",
    "lookup_briefing",
    "market_gaps",
    "needs_web_lookup",
    "render_web_lookup",
    "web_supplement",
]
