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
import math
import re
from collections.abc import Callable
from datetime import date as _date
from urllib.parse import urlparse

from features.common.engine_lookup import LookupCall, configured_lookup_call
from features.common.markets import market_definition
from features.common.web_search_scope import load_source_scope, render_scope_instruction

# 스냅샷 기준일이 발행일보다 이보다 오래 뒤처지면 "정체"로 본다. 휴장·주말이 겹쳐도
# 대표 지수가 나흘 넘게 멈추는 정규 상황은 없다.
STALE_DAYS = 4
# 한 번의 조회로 메우려는 공백 수 상한. 다 비었다는 것은 provider 전면 장애라
# 웹 조회가 아니라 스냅샷 복구가 답이다.
MAX_GAPS = 6
MAX_CANDIDATES = 12

# Keep this deliberately small.  A web result whose unit is not in this set
# cannot be compared with a local fact safely (``%`` and ``percent`` are not
# interchangeable at this boundary).
SUPPORTED_UNITS = frozenset({"points", "percent", "USD", "KRW", "quote"})
GAP_STATES = frozenset({"missing", "wrongsession", "comparisonmissing", "conflict"})
TrustedEvidenceResolver = Callable[[dict, dict], object]


def _days_between(older: str, newer: str) -> int | None:
    try:
        from datetime import date

        a = date.fromisoformat(str(older)[:10])
        b = date.fromisoformat(str(newer)[:10])
        return (b - a).days
    except (ValueError, TypeError):
        return None


def _gap(
    gap_id: str,
    *,
    instrument: str,
    metric: str,
    session_date: str,
    unit: str,
    state: str,
    detail: str,
) -> dict:
    return {
        "id": gap_id,
        "instrument": instrument,
        "metric": metric,
        "sessionDate": str(session_date)[:10],
        "unit": unit if unit in SUPPORTED_UNITS else "unknown",
        "state": state if state in GAP_STATES else "missing",
        # ``reason``/``status`` are additive aliases for consumers that use
        # the existing data-gap vocabulary instead of the typed state name.
        "reason": state if state in GAP_STATES else "missing",
        "status": state if state in GAP_STATES else "missing",
        "detail": detail,
    }


def _row_unit(row: dict, default: str) -> str:
    value = str((row or {}).get("unit") or (row or {}).get("priceUnit") or default)
    return value if value in SUPPORTED_UNITS else default


def _is_present(row: object, key: str) -> bool:
    if not isinstance(row, dict) or row.get(key) in (None, ""):
        return False
    value = row.get(key)
    if isinstance(value, bool):
        return False
    try:
        numeric = float(str(value).replace(",", "").replace("%", "").strip())
        return math.isfinite(numeric)
    except (TypeError, ValueError):
        return False


def _same_session(row: dict, session_date: str) -> bool:
    observed = str((row or {}).get("asOfDate") or "")[:10]
    return bool(observed) and observed == str(session_date)[:10]


def _normalise_window(window, fallback: str) -> tuple[str, str] | None:
    """Return an explicit weekly [start, end] window; never derive one from a return."""
    if isinstance(window, dict):
        start = str(window.get("start") or window.get("from") or window.get("weekStart") or "")[:10]
        end = str(window.get("end") or window.get("to") or window.get("weekEnd") or "")[:10]
    elif isinstance(window, (tuple, list)) and len(window) >= 2:
        start, end = str(window[0])[:10], str(window[1])[:10]
    else:
        return None
    try:
        _date.fromisoformat(start)
        _date.fromisoformat(end)
    except ValueError:
        return None
    return (start, end) if start <= end else None


def market_gaps(
    scope: str,
    market_snapshot: dict | None,
    korea_market_data: dict | None,
    date: str,
    *,
    kind: str = "daily",
    window: dict | tuple[str, str] | list[str] | None = None,
) -> list[dict]:
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

    kind = str(kind or "daily").lower()
    expected_date = str(date)[:10]
    weekly_window = _normalise_window(window, expected_date) if kind == "weekly" else None

    def _session_ok(row: dict) -> bool:
        observed = str(row.get("asOfDate") or "")[:10]
        if kind == "weekly" and not weekly_window:
            return False
        if kind == "weekly" and weekly_window:
            return (
                str(row.get("periodStart") or row.get("weekStart") or "")[:10] == weekly_window[0]
                and str(row.get("periodEnd") or row.get("weekEnd") or "")[:10] == weekly_window[1]
            )
        return observed == expected_date

    def _instrument_gaps(instrument: str, row: dict | None, unit: str) -> list[dict]:
        if isinstance(row, dict) and row.get("last") not in (None, "") and not _is_present(row, "last"):
            return [_gap(
                f"us_proxy_conflict:{instrument}", instrument=instrument, metric="close",
                session_date=expected_date, unit=unit, state="conflict",
                detail=f"{instrument} 값이 유한한 숫자가 아닙니다.",
            )]
        if not isinstance(row, dict) or not _is_present(row, "last"):
            return [_gap(
                f"us_proxy_missing:{instrument}", instrument=instrument, metric="close",
                session_date=expected_date, unit=unit, state="missing",
                detail=f"{instrument} 종가가 없습니다.",
            )]
        if not _session_ok(row):
            return [_gap(
                f"us_proxy_wrongsession:{instrument}", instrument=instrument, metric="close",
                session_date=expected_date, unit=unit, state="wrongsession",
                detail=f"{instrument} 값의 기준일이 요청한 세션과 다릅니다.",
            )]
        if row.get("conflict") or row.get("conflictingValues"):
            return [_gap(
                f"us_proxy_conflict:{instrument}", instrument=instrument, metric="close",
                session_date=expected_date, unit=unit, state="conflict",
                detail=f"{instrument} 로컬 값이 충돌합니다.",
            )]
        comparison_key = "weeklyPct" if kind == "weekly" else "oneDayPct"
        # A five-day return is not a weekly fact.  Weekly callers must provide
        # an explicit weekly field (or use the resolver to find one).
        if not _is_present(row, comparison_key):
            return [_gap(
                f"us_proxy_comparisonmissing:{instrument}", instrument=instrument,
                metric=comparison_key, session_date=expected_date, unit="percent",
                state="comparisonmissing",
                detail=f"{instrument}의 {comparison_key} 비교값이 없습니다.",
            )]
        return []

    if scope == "us" and (not snapshot or snapshot.get("ok") is False):
        gaps.append(_gap(
            "snapshot_unavailable", instrument="SPY,QQQ", metric="close",
            session_date=expected_date, unit="USD", state="missing",
            detail="가격 스냅샷 수집이 실패해 프록시·거시 수치가 없습니다.",
        ) | {"label": "시장 가격 스냅샷 전체"})
    elif scope == "us":
        us_gaps = []
        for instrument in ("SPY", "QQQ"):
            us_gaps.extend(_instrument_gaps(instrument, tickers.get(instrument), "USD"))
        # Preserve the old aggregate identifier when both proxies have the
        # same failure state, while retaining individual requirements under
        # ``items``.  A single healthy proxy therefore never hides the other.
        if len(us_gaps) == 2 and len({item["state"] for item in us_gaps}) == 1:
            state = us_gaps[0]["state"]
            gaps.append({
                **_gap(
                    # Legacy consumers use this aggregate id.  The typed
                    # ``state`` and nested ``items`` carry the new detail.
                    "us_proxy_missing",
                    instrument="SPY,QQQ", metric="close", session_date=expected_date,
                    unit="USD", state=state,
                    detail="스냅샷의 SPY와 QQQ 요구 항목이 모두 비어 있습니다.",
                ),
                "items": us_gaps,
                "label": "미국 주요 지수 (S&P500·Nasdaq 종가 등락률)",
            })
        else:
            for item in us_gaps:
                item["label"] = f"{item['instrument']} {item['metric']}"
            gaps.extend(us_gaps)

    if scope == "kr":
        kr = korea_market_data or {}
        indices = kr.get("indices") if isinstance(kr.get("indices"), dict) else {}
        if not kr or kr.get("ok") is False:
            gaps.append(_gap(
                "kr_data_unavailable", instrument="KOSPI,KOSDAQ,USDKRW", metric="close",
                session_date=expected_date, unit="points", state="missing",
                detail="한국장 수치 수집이 실패했습니다.",
            ) | {"label": "한국장 핵심 수치 전체"})
        else:
            for name in ("KOSPI", "KOSDAQ"):
                row = indices.get(name) or {}
                if row.get("close") not in (None, "") and not _is_present(row, "close"):
                    gaps.append(_gap(
                        f"kr_index_conflict:{name}", instrument=name, metric="close",
                        session_date=expected_date, unit="points", state="conflict",
                        detail="종가가 유한한 숫자가 아닙니다.",
                    ) | {"label": f"{name} 종가 등락률"})
                elif not _is_present(row, "close"):
                    gaps.append(_gap(
                        f"kr_index_missing:{name}", instrument=name, metric="close",
                        session_date=expected_date, unit="points", state="missing",
                        detail="종가가 없습니다.",
                    ) | {"label": f"{name} 종가 등락률"})
                elif row.get("changePct") not in (None, "") and not _is_present(row, "changePct"):
                    gaps.append(_gap(
                        f"kr_index_conflict:{name}:changePct", instrument=name, metric="changePct",
                        session_date=expected_date, unit="percent", state="conflict",
                        detail="등락률이 유한한 숫자가 아닙니다.",
                    ) | {"label": f"{name} 종가 등락률"})
                elif not _is_present(row, "changePct"):
                    gaps.append(_gap(
                        f"kr_index_comparisonmissing:{name}", instrument=name, metric="changePct",
                        session_date=expected_date, unit="percent", state="comparisonmissing",
                        detail="등락률 비교값이 없습니다.",
                    ) | {"label": f"{name} 종가 등락률"})
                elif row.get("conflict") or row.get("conflictingValues"):
                    gaps.append(_gap(
                        f"kr_index_conflict:{name}", instrument=name, metric="close",
                        session_date=expected_date, unit="points", state="conflict",
                        detail="한국장 로컬 값이 충돌합니다.",
                    ) | {"label": f"{name} 종가 등락률"})
                elif not _same_session(row, expected_date):
                    gaps.append(_gap(
                        f"kr_index_wrongsession:{name}", instrument=name, metric="close",
                        session_date=expected_date, unit="points", state="wrongsession",
                        detail="기준일이 요청한 세션과 다릅니다.",
                    ) | {"label": f"{name} 종가 등락률"})
            fx = kr.get("fx") if isinstance(kr.get("fx"), dict) else {}
            # fx는 {"USDKRW": {close, changePct, ...}} 모양이다.
            fx_row = fx.get("USDKRW") if isinstance(fx.get("USDKRW"), dict) else None
            if fx_row and fx_row.get("close") not in (None, "") and not _is_present(fx_row, "close"):
                gaps.append(_gap(
                    "kr_fx_conflict", instrument="USDKRW", metric="close",
                    session_date=expected_date, unit="quote", state="conflict",
                    detail="환율 종가가 유한한 숫자가 아닙니다.",
                ) | {"label": "원/달러 환율 종가"})
            elif not _is_present(fx_row, "close"):
                gaps.append(_gap(
                    "kr_fx_missing", instrument="USDKRW", metric="close",
                    session_date=expected_date, unit="quote", state="missing",
                    detail="환율 종가가 없습니다.",
                ) | {"label": "원/달러 환율 종가"})
            elif not _same_session(fx_row, expected_date):
                gaps.append(_gap(
                    "kr_fx_wrongsession", instrument="USDKRW", metric="close",
                    session_date=expected_date, unit="quote", state="wrongsession",
                    detail="환율 기준일이 요청한 세션과 다릅니다.",
                ) | {"label": "원/달러 환율 종가"})

    # JP·유럽은 컨텍스트에 자기 지수 수치 피드가 없다. 로컬 기사가 종가를 다루는 날이
    # 많지만 그것은 확인해야 아는 일이고, 웹 보완이 §6 규칙 9가 말하는 "부족한 지수"
    # 바로 그 자리다.
    if scope == "jp":
        gaps.append(_gap(
            "jp_index_feed_absent", instrument="N225,TOPIX", metric="close",
            session_date=expected_date, unit="points", state="missing",
            detail="로컬 수치 피드가 일본 지수를 다루지 않습니다.",
        ) | {"label": "닛케이 225·TOPIX 종가 등락률"})
    if scope == "europe":
        gaps.append(_gap(
            "europe_index_feed_absent", instrument="STOXX600,DAX,FTSE100", metric="close",
            session_date=expected_date, unit="points", state="missing",
            detail="로컬 수치 피드가 유럽 지수를 다루지 않습니다.",
        ) | {"label": "STOXX600·DAX·FTSE100 종가 등락률"})
    bounded = gaps[:MAX_GAPS]
    for gap in bounded:
        gap.setdefault("market", scope)
        for item in gap.get("items") or []:
            item.setdefault("market", scope)
    return bounded


def needs_web_lookup(gaps: list[dict]) -> bool:
    return bool(gaps)


def _flatten_gaps(gaps: list[dict]) -> list[dict]:
    """Expand legacy aggregate gaps before prompt/matching; preserve parent labels."""
    flattened: list[dict] = []
    for gap in gaps or []:
        if not isinstance(gap, dict):
            continue
        children = gap.get("items") or []
        if children:
            for child in children:
                if isinstance(child, dict):
                    flattened.append({
                        **child,
                        "label": child.get("label") or gap.get("label") or child.get("instrument", ""),
                        "detail": child.get("detail") or gap.get("detail") or "",
                        "market": child.get("market") or gap.get("market") or "",
                    })
        else:
            flattened.append(gap)
    return flattened[:MAX_GAPS]


_LOOKUP_PROMPT = """당신은 시장 데이터 조사원입니다. 아래에 나열된 수치가 로컬 자료에 없습니다.
웹 검색으로 **그 수치만** 찾아 JSON 하나로 답하세요.

규칙:
- 새 분석이나 해석을 쓰지 마세요. 이것은 찾기 과제입니다.
- 각 결과에 gapId, instrument, metric, sessionDate, unit, value, quote, 출처 URL을 함께 적으세요.
- unit은 points, percent, USD, KRW, quote 중 하나만 사용하세요. 기준일을 확인할 수 없는 수치는 싣지 마세요.
- 아래 허용 출처 목록 밖의 도메인은 쓰지 마세요.
- 찾지 못한 항목은 지어내지 말고 notFound에 남기세요.
- URL·날짜·숫자를 적었다고 검증된 사실이 되는 것은 아닙니다. 원문 문구 또는 구조화 provider 확인이
  없는 결과는 unverifiedCandidates로만 남고, 보고서 작성에 사용할 수 없습니다.

출력 형식(JSON만):
{"facts": [{"gapId": "...", "instrument": "SPY", "metric": "oneDayPct", "sessionDate": "YYYY-MM-DD", "unit": "percent", "value": "수치", "quote": "원문 문구", "source": "매체/기관", "url": "https://..."}],
 "notFound": ["못 찾은 항목"]}
"""


def _candidate_gap(row: dict, gaps: list[dict]) -> dict | None:
    """Match a model row to exactly one requested item; aliases are bounded."""
    gap_id = str(row.get("gapId") or row.get("gap_id") or "")
    for gap in gaps:
        if gap_id and gap_id == str(gap.get("id") or ""):
            return gap
        instrument = str(row.get("instrument") or "").strip().upper()
        expected = {part.strip().upper() for part in str(gap.get("instrument") or "").split(",") if part.strip()}
        if instrument and instrument in expected:
            metric = str(row.get("metric") or "").strip()
            if not metric or metric == str(gap.get("metric") or ""):
                return gap
        # Compatibility with the original item-only response shape.  This is
        # still constrained to an exact label match, never substring search.
        if str(row.get("item") or "").strip() == str(gap.get("label") or "").strip():
            return gap
    return None


def _date_matches(value: str, gap: dict, *, kind: str, window, row: dict | None = None) -> bool:
    observed = str(value or "")[:10]
    if not observed:
        return False
    if kind == "weekly":
        bounds = _normalise_window(window, str(gap.get("sessionDate") or ""))
        if not bounds or not isinstance(row, dict):
            return False
        period_start = str(row.get("periodStart") or row.get("weekStart") or "")[:10]
        period_end = str(row.get("periodEnd") or row.get("weekEnd") or "")[:10]
        return period_start == bounds[0] and period_end == bounds[1] and observed == period_end
    return observed == str(gap.get("sessionDate") or "")[:10]


def _safe_candidate(row: dict, gap: dict, *, scope: str, kind: str, window) -> tuple[dict | None, str | None]:
    """Validate model metadata without treating it as source verification."""
    url = str(row.get("url") or "").strip()
    parsed = urlparse(url)
    source_scope = load_source_scope(None)
    if parsed.scheme != "https":
        return None, "invalid_scheme"
    tier, label = source_scope.classify(url)
    if not label or tier == "rejected":
        return None, "source_not_allowed"
    market = str(row.get("market") or "").strip().lower()
    if market != str(scope or "").strip().lower():
        return None, "market_mismatch"
    instrument = str(row.get("instrument") or "").strip().upper()
    if not instrument:
        return None, "missing_instrument"
    expected_instruments = {part.strip().upper() for part in str(gap.get("instrument") or "").split(",") if part.strip()}
    if instrument and instrument not in expected_instruments:
        return None, "instrument_mismatch"
    metric = str(row.get("metric") or "").strip()
    if not metric:
        return None, "missing_metric"
    if metric != str(gap.get("metric") or ""):
        return None, "metric_mismatch"
    session_date = str(row.get("sessionDate") or "")[:10]
    try:
        _date.fromisoformat(session_date)
    except ValueError:
        return None, "invalid_date"
    if not _date_matches(session_date, gap, kind=kind, window=window, row=row):
        return None, "wrong_session"
    unit = str(row.get("unit") or "")
    if unit not in SUPPORTED_UNITS:
        return None, "invalid_unit"
    if unit != str(gap.get("unit") or ""):
        return None, "unit_mismatch"
    raw_value = row.get("value")
    if raw_value in (None, "") or isinstance(raw_value, bool):
        return None, "missing_value"
    value = str(raw_value).strip()
    try:
        numeric = float(value.replace(",", "").replace("%", "").strip())
        if not math.isfinite(numeric):
            return None, "nonfinite_value"
    except (TypeError, ValueError):
        return None, "invalid_value"
    # Values are writer-facing text; keep them one-line and table-safe.
    value = re.sub(r"[\r\n|<>\[\]]", " ", value)[:120].strip()
    if not value:
        return None, "invalid_value"
    return {
        "gapId": str(gap.get("id") or ""),
        "item": str(row.get("item") or gap.get("label") or gap.get("instrument") or "")[:120],
        "instrument": instrument or str(gap.get("instrument") or ""),
        "metric": metric,
        "sessionDate": session_date,
        "asOf": session_date,
        "market": market,
        "unit": unit,
        "value": value[:120],
        "quote": str(row.get("quote") or "")[:500],
        "source": str(row.get("source") or label)[:80],
        "url": url[:300],
        "sourceTier": tier,
        **({
            "periodStart": str(row.get("periodStart") or row.get("weekStart") or "")[:10],
            "periodEnd": str(row.get("periodEnd") or row.get("weekEnd") or "")[:10],
        } if kind == "weekly" else {}),
    }, None


def _resolver_verified(result) -> bool:
    return bool(
        isinstance(result, dict)
        and result.get("verified") is True
        and result.get("evidenceMethod") in {"public_quote_exact", "structured_provider"}
        and str(result.get("sourceId") or "")
        and re.fullmatch(r"[0-9a-f]{16,128}", str(result.get("sourceEvidenceHash") or ""))
        and not result.get("conflict")
    )


def lookup_briefing(
    scope: str,
    date: str,
    gaps: list[dict],
    lookup: LookupCall,
    *,
    kind: str = "daily",
    window: dict | tuple[str, str] | list[str] | None = None,
    trusted_evidence_resolver: TrustedEvidenceResolver | None = None,
) -> dict:
    """Find missing items and return only resolver-verified writer facts.

    ``trusted_evidence_resolver(candidate, gap)`` is intentionally injectable:
    it must fetch/read the allow-listed page or query a trusted structured
    provider and return independent metadata: ``{"verified": True,
    "evidenceMethod": "public_quote_exact"|"structured_provider",
    "sourceId": "...", "sourceEvidenceHash": "..."}``. Without it,
    model rows remain candidates and never enter writer context.
    """
    gaps = _flatten_gaps(gaps)
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
        *[
            f"- gapId={gap.get('id', '')}; market={scope}; instrument={gap.get('instrument', '')}; "
            f"metric={gap.get('metric', '')}; sessionDate={gap.get('sessionDate', '')}; unit={gap.get('unit', '')}; "
            f"{gap.get('label', gap.get('instrument', ''))}: {gap.get('detail', '')}"
            for gap in gaps
        ],
        "",
        render_scope_instruction(source_scope),
    ])
    try:
        raw = lookup(_LOOKUP_PROMPT, context)
        payload = _parse_json(raw)
    except Exception as exc:  # noqa: BLE001 - 조회 실패가 브리핑을 죽이지 않는다
        return {"ok": False, "reason": type(exc).__name__}
    facts: list[dict] = []
    unverified: list[dict] = []
    rejected_reasons: list[str] = []
    for raw_row in (payload.get("facts") or [])[:MAX_CANDIDATES]:
        if not isinstance(raw_row, dict):
            continue
        gap = _candidate_gap(raw_row, gaps)
        if gap is None:
            unverified.append({"item": str(raw_row.get("item") or "")[:120], "reason": "item_not_requested"})
            continue
        candidate, reason = _safe_candidate(
            raw_row, gap, scope=scope, kind=str(kind or "daily").lower(), window=window,
        )
        if candidate is None:
            rejected_reasons.append(reason or "invalid_candidate")
            unverified.append({"item": str(raw_row.get("item") or gap.get("label") or "")[:120], "reason": reason or "invalid_candidate"})
            continue
        if trusted_evidence_resolver is None:
            unverified.append({"item": candidate["item"], "reason": "trusted_evidence_unavailable"})
            continue
        try:
            verified = trusted_evidence_resolver(candidate, gap)
        except Exception:
            verified = False
        if not _resolver_verified(verified):
            rejected_reasons.append("trusted_evidence_rejected")
            unverified.append({"item": candidate["item"], "reason": "trusted_evidence_rejected"})
            continue
        candidate["verified"] = True
        candidate["evidenceStatus"] = "verified"
        candidate["evidenceMethod"] = str(verified["evidenceMethod"])
        candidate["sourceId"] = str(verified["sourceId"])[:128]
        candidate["sourceEvidenceHash"] = str(verified["sourceEvidenceHash"])[:128]
        facts.append(candidate)
    # Two differing accepted values for one request are not safe to write.
    by_gap: dict[tuple[str, str, str, str], list[dict]] = {}
    for fact in facts:
        key = (
            str(fact.get("instrument") or ""), str(fact.get("metric") or ""),
            str(fact.get("sessionDate") or ""), str(fact.get("market") or ""),
        )
        by_gap.setdefault(key, []).append(fact)
    conflicts = {key for key, rows in by_gap.items() if len({(r.get("value"), r.get("unit")) for r in rows}) > 1}
    if conflicts:
        rejected_reasons.append("conflict")
        for fact in facts:
            key = (
                str(fact.get("instrument") or ""), str(fact.get("metric") or ""),
                str(fact.get("sessionDate") or ""), str(fact.get("market") or ""),
            )
            if key in conflicts:
                unverified.append({"item": fact["item"], "reason": "conflict"})
        facts = [fact for fact in facts if (
            str(fact.get("instrument") or ""), str(fact.get("metric") or ""),
            str(fact.get("sessionDate") or ""), str(fact.get("market") or ""),
        ) not in conflicts]
    return {
        "ok": True,
        "gaps": [gap["id"] for gap in gaps],
        "facts": facts,
        "notFound": [str(item)[:120] for item in (payload.get("notFound") or [])][:MAX_GAPS],
        "unverifiedCandidates": unverified[:MAX_GAPS],
        "rejectedReasons": sorted(set(rejected_reasons))[:MAX_GAPS],
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
        lines.append(f"| {fact['item']} | {fact['value']} {fact.get('unit', '')} | {fact.get('sessionDate', fact.get('asOf', ''))} | [{fact['source']}]({fact['url']}) |")
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
    kind: str = "daily",
    window: dict | tuple[str, str] | list[str] | None = None,
    weekly_window: dict | tuple[str, str] | list[str] | None = None,
    trusted_evidence_resolver: TrustedEvidenceResolver | None = None,
) -> tuple[str, dict]:
    """(컨텍스트 블록, 저장용 요약). **두 생성 경로가 이 함수 하나를 부른다** —
    조립기를 공유해도 호출부가 넘기는 인자가 갈리면 같은 일이 난다(§6 규칙 14)."""
    kind = str(kind or "daily").lower()
    window = window if window is not None else weekly_window
    gaps = market_gaps(scope, market_snapshot, korea_market_data, date, kind=kind, window=window)
    summary: dict = {"webSearch": bool(web_search), "gaps": [gap["id"] for gap in gaps]}
    if web_search:
        summary.update({
            "kind": kind,
            "lookupAttempted": False,
            # Default until (and unless) the call below actually observes a
            # signal. Unknown is intentional; absence of telemetry is not
            # evidence of "no".
            "toolUse": "unknown",
            "acceptedFactCount": 0,
            "unverifiedCandidateCount": 0,
        })
    if not web_search or not needs_web_lookup(gaps):
        return "", summary
    summary["lookupAttempted"] = True
    internal_lookup = lookup is None
    lookup_call = lookup or briefing_lookup_call()
    resolver = trusted_evidence_resolver
    if resolver is None and internal_lookup:
        # Internal configured lookup may opt into the bounded public fetcher.
        # Injected lookups (tests/callers) never trigger network verification
        # implicitly; they must pass a resolver explicitly.
        try:
            from features.daily_briefing.web_evidence import public_evidence_resolver

            resolver = public_evidence_resolver()
        except Exception:
            resolver = None
    row = lookup_briefing(
        scope, date, gaps, lookup_call, kind=kind,
        window=window, trusted_evidence_resolver=resolver,
    )
    summary.update({k: v for k, v in row.items() if k != "gaps"})
    summary["acceptedFactCount"] = len(row.get("facts") or [])
    summary["unverifiedCandidateCount"] = len(row.get("unverifiedCandidates") or [])
    # The internal lookup call (engine_lookup.py) stamps this attribute with
    # what bridge.py actually observed from the adapter's own structured
    # output when the CLI path ran. An externally injected `lookup` (tests,
    # other callers) or the API branch never sets it, so this stays "unknown"
    # exactly where nothing was observed — never guessed.
    observed = getattr(lookup_call, "web_search_facts", None)
    if isinstance(observed, dict) and observed.get("used") in {"yes", "no", "unknown"}:
        summary["toolUse"] = observed["used"]
    return render_web_lookup(row, gaps), summary


def briefing_lookup_call(*, adapter: str = "", job_id: str = "") -> LookupCall:
    from features.common.quality_generation.call_budget import current_briefing_budget
    budget = current_briefing_budget()
    return configured_lookup_call(
        adapter=adapter,
        job_id=job_id,
        cli_timeout_env="BRIEFING_LOOKUP_CLI_TIMEOUT_SECONDS",
        timeout_limit=budget.remaining_seconds if budget else None,
    )


__all__ = [
    "briefing_lookup_call",
    "GAP_STATES",
    "SUPPORTED_UNITS",
    "TrustedEvidenceResolver",
    "lookup_briefing",
    "market_gaps",
    "needs_web_lookup",
    "render_web_lookup",
    "web_supplement",
]
