"""주간 브리핑의 시각자료 — 한 `WeeklyWindow`에서 나오는 세 그림.

일간 시각자료는 **하루 세션**의 그림이다(5분봉 가격, 그날 등락 히트맵). 그것을 한 주를
덮는 보고서에 그대로 붙이면 특정 하루가 그 주를 대표하는 것처럼 읽히므로, 0.5.4는 주간에
세션 스냅샷을 싣지 않기로 했다. 이 모듈은 그 결정을 뒤집는 것이 아니라 **주 단위 계열**을
따로 만든다.

세 그림이 있고 **셋 다 같은 `WeeklyWindow` 객체를 받는다**:

    A. 주간 지수 흐름   — 대표 지수의 주초 대비 % (role=weekly_flow, range=week)
    B. 주간 히트맵      — 구성종목의 주초 종가 대비 주말 종가 (사이드카)
    C. 이야기 비중 추이 — 그 주 거래일별 동인 비중 (role=weekly_story_share)

**경계를 인자로 받지 않고 각자 계산하면 한 보고서 안에서 세 그림이 세 주를 말한다.**
A의 "주초 대비", B의 "주초 종가 대비 주말 종가", C의 "그 주 거래일"이 모두 이 창 하나에서
나오고, 캡션도 같은 구간을 적는다.

수집은 best effort다 — 그림이 실패해도 Canonical 본문은 그대로 나가고 사유만 남는다.
"""

from __future__ import annotations

import datetime as dt
from copy import deepcopy

from features.common.market_data.market_universe import (
    build_europe_heatmap_snapshot,
    build_kospi_heatmap_snapshot,
    build_nikkei_heatmap_snapshot,
    build_us_heatmap_snapshot,
)
from features.common.market_data.price_history import INDEX_UNIVERSE, build_price_history
from features.common.market_calendar import market_open_status
from features.common.markets import (
    SavedMarketScope,
    market_keys_for_scope,
    normalize_saved_market_scope,
)
from features.daily_briefing.schema import visual_sidecar_gzip_file_name
from features.daily_briefing.visuals import (
    MARKET_CACHE_DIR,
    MARKET_META,
    _coverage,
    _heatmap_currency,
    _recommendation,
    _safe_float,
    _series_provider,
    _snapshot_currencies,
)
from features.daily_briefing.weekly import WeeklyWindow

# 슬롯 이름. 렌더러의 `sectionRole()`이 만드는 값과 같아야 한다 — 다르면 추천이
# 어느 슬롯에도 붙지 못해 조용히 그림이 사라진다.
WEEKLY_FLOW_ROLE = "weekly_flow"
WEEKLY_STORY_ROLE = "weekly_story_share"
# 주간 그림이 성립하려면 최소 몇 세션이 있어야 하는가. 두 점이면 선이 되지만 그 선은
# 이틀을 잇는 것이지 한 주가 아니다.
MIN_WEEK_SESSIONS = 3


def _window_dates(window: WeeklyWindow) -> set[str]:
    return set(window.source_dates)


def _clip_daily_points(points, window: WeeklyWindow) -> list[dict]:
    """일봉을 창 안으로 자른다. **거래일 표를 따로 보지 않는다** — 봉이 있는 날이
    그 시장이 실제로 열린 날이고, 휴장일 표가 없는 연도에도 옳다."""
    dates = _window_dates(window)
    clipped = [row for row in (points or []) if str(row.get("time") or "")[:10] in dates]
    clipped.sort(key=lambda row: str(row.get("time") or ""))
    return clipped


def _percent_series(points) -> tuple[list[dict], float | None, float | None]:
    """주초 대비 %. 기준은 창 안 **첫 종가**다.

    창 밖(전주 금요일)을 기준으로 삼지 않는다. 그러면 그림의 첫 점이 0이 아니라
    주말 갭이 되어, "이번 주 어디서 출발했나"라는 물음에 다른 답을 한다.
    """
    closes = [(str(row.get("time") or "")[:10], _safe_float(row.get("close"))) for row in points]
    closes = [(day, value) for day, value in closes if day and value is not None]
    if not closes:
        return [], None, None
    baseline = closes[0][1]
    if not baseline:
        return [], None, None
    rows = [
        {"time": day, "close": value, "changePct": round((value / baseline - 1) * 100, 4)}
        for day, value in closes
    ]
    return rows, baseline, rows[-1]["changePct"]


def _prior_week_return(
    points,
    window: WeeklyWindow,
    *,
    expected_sessions: list[str] | None = None,
    prior_session: str | None = None,
) -> tuple[float | None, float | None, str | None, str | None]:
    """Return the week-over-week close separately from the in-week curve.

    The plotted curve intentionally starts at the first close *inside* the
    window.  The headline weekly return instead uses the last close before the
    window, when that baseline is available, and never substitutes the first
    in-window point for it.
    """
    start = str(window.week_start)[:10]
    dated = []
    for row in points or []:
        day = str(row.get("time") or "")[:10]
        close = _safe_float(row.get("close"))
        if day and close is not None:
            dated.append((day, close))
    dated.sort()
    expected_sessions = expected_sessions or []
    if not expected_sessions or not prior_session:
        return None, None, None, "calendar_unavailable"
    expected_end = expected_sessions[-1]
    values = dict(dated)
    if prior_session not in values:
        return None, None, None, "prior_week_close_missing"
    if expected_end not in values:
        return None, None, prior_session, "week_end_session_missing"
    baseline_day, baseline = prior_session, values[prior_session]
    end_day, end_close = expected_end, values[expected_end]
    if baseline == 0:
        return None, baseline, baseline_day, "zero_prior_week_close"
    try:
        value = (end_close / baseline - 1) * 100
        if value != value or value in (float("inf"), float("-inf")):
            return None, baseline, baseline_day, "nonfinite_week_return"
    except (OverflowError, ZeroDivisionError):
        return None, baseline, baseline_day, "nonfinite_week_return"
    return round(value, 4), baseline, baseline_day, None


def _calendar_status_known(status: dict | None) -> bool:
    if not isinstance(status, dict):
        return False
    source = status.get("source")
    if source in {"static", "exchange_api"}:
        return True
    # Some exchange adapters report ``source=exchange`` and a separate
    # coverage field. Accept only explicitly valid coverage; never infer it.
    return source == "exchange" and (
        status.get("coverageValid") is True
        or status.get("coverage") in {"valid", "covered", "complete", "ok"}
    )


def _prior_session_date(market_key: str, first_session: str) -> str | None:
    code = {"us": "US", "kr": "KR", "europe": "EUROPE", "jp": "JP"}.get(market_key)
    if not code:
        return None
    try:
        cursor = dt.date.fromisoformat(first_session) - dt.timedelta(days=1)
    except ValueError:
        return None
    for _ in range(14):
        status = market_open_status(cursor, code, lambda _day, _market: None)
        if not _calendar_status_known(status):
            return None
        if status.get("isOpen"):
            return cursor.isoformat()
        cursor -= dt.timedelta(days=1)
    return None


def _expected_sessions(market_key: str, window: WeeklyWindow) -> tuple[list[str] | None, str, str | None]:
    """Resolve expected dates from the existing static calendar only.

    A calendar gap is not filled with weekday guesses.  If the existing
    exchange table is unavailable/expired, callers expose coverage as unknown
    rather than claiming JP/EU (or another market) is complete.
    """
    code = {"us": "US", "kr": "KR", "europe": "EUROPE", "jp": "JP"}.get(market_key)
    if not code:
        return None, "unsupported_market", None
    dates = []
    for text in window.source_dates:
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            return None, "invalid_window", None
        status = market_open_status(day, code, lambda _day, _market: None)
        if not _calendar_status_known(status):
            return None, "calendar_unavailable", None
        if status.get("isOpen"):
            dates.append(day.isoformat())
    if not dates:
        return None, "no_expected_sessions", None
    return dates, "market_calendar", _prior_session_date(market_key, dates[0])


def _weekly_flow_snapshot(market_key: str, window: WeeklyWindow, series, missing, requested) -> dict:
    meta = MARKET_META[market_key]
    sessions = sorted({point["time"] for row in series for point in row.get("points", [])})
    latest = sessions[-1] if sessions else ""
    # 창의 마지막 날이 휴장이면(일요일 발행이면 늘 그렇다) 마지막 세션은 그 전 거래일이다.
    # 그것은 결측이 아니라 정상이므로 `stale`로 부르지 않는다.
    freshness = "close_snapshot" if sessions else "unavailable"
    warnings = []
    if missing:
        warnings.append(f"missing symbols: {', '.join(missing)}")
    expected_sessions, expected_basis, prior_session = _expected_sessions(market_key, window)
    missing_by_symbol = {
        row["ticker"]: sorted(set(expected_sessions) - {str(point.get("time") or "")[:10] for point in row.get("points", [])})
        for row in series
        if expected_sessions is not None and set(expected_sessions) - {str(point.get("time") or "")[:10] for point in row.get("points", [])}
    }
    for row in series:
        observed = {str(point.get("time") or "")[:10] for point in row.get("points", [])}
        row["expectedSessions"] = expected_sessions
        row["missingSessions"] = sorted(set(expected_sessions) - observed) if expected_sessions is not None else None
    if expected_sessions is None and series:
        warnings.append(f"{market_key}: session coverage unavailable")
    elif missing_by_symbol:
        warnings.append(f"missing sessions: {', '.join(missing_by_symbol)}")
    currencies = _snapshot_currencies(meta, series, requested)
    coverage = _coverage(requested, series, missing)
    session_status = "unavailable" if not series else "unknown" if expected_sessions is None else "partial" if missing_by_symbol else "complete"
    # Symbol count alone is not temporal completeness.  Preserve the existing
    # coverage shape but downgrade when expected sessions are missing/unknown.
    if series and session_status in {"partial", "unknown"}:
        coverage["status"] = "partial"
    coverage.update({
        "expectedSessions": expected_sessions,
        "expectedSessionBasis": expected_basis,
        "priorSession": prior_session,
        "missingSessionsBySymbol": missing_by_symbol,
        "sessionStatus": session_status,
    })
    point_counts = {
        row["ticker"]: {
            "intraday": 0,
            "hourly": len((row.get("hourly") or {}).get("points") or []),
            "daily": len((row.get("daily") or {}).get("points") or []),
        }
        for row in series
    }
    sparse = any(counts["daily"] < 8 for counts in point_counts.values())
    return {
        "id": f"weekly-flow:{market_key}:{window.publication_date}",
        "schemaVersion": 2,
        "type": "price_series",
        # 주간 전용 계열이라 일간의 `market_summary`와 이름을 나눈다. 같은 이름을 쓰면
        # 일간 추천이 주간 슬롯에, 주간 추천이 일간 슬롯에 붙을 수 있다.
        "role": WEEKLY_FLOW_ROLE,
        "range": "week",
        "market": meta["market"],
        "window": window.to_dict(),
        "weekLabel": window.label,
        "sessionDates": sessions,
        "asOf": latest or window.week_end,
        "provider": _series_provider(series),
        "freshness": freshness,
        "coverage": coverage,
        "expectedSessions": expected_sessions,
        "expectedSessionBasis": expected_basis,
        "missingSessionsBySymbol": missing_by_symbol,
        "timezone": meta["timezone"],
        "currency": currencies[0] if len(currencies) == 1 else "MIXED" if currencies else "",
        "currencies": currencies,
        "marketSessionDate": latest or window.week_end,
        "granularities": ["1h", "1d"],
        "dataSufficiency": {"minimumTrendPoints": 8, "pointCounts": point_counts, "status": "sparse" if sparse else "sufficient" if series else "unavailable"},
        "subject": {},
        # 값은 %다. 원 종가도 함께 두어 hover가 실제 지수 레벨을 말할 수 있게 한다.
        "unit": "percent_change_from_week_start",
        "series": series,
        "warnings": warnings,
    }


def _collect_weekly_flow(market_key: str, window: WeeklyWindow, fetch_price, warnings) -> dict:
    requested = list(INDEX_UNIVERSE[market_key])
    series, missing = [], []
    for item in requested:
        try:
            history = fetch_price(item["ticker"], window.week_end) or {}
        except Exception:
            warnings.append(f"{item['ticker']}: weekly_price_history_unavailable")
            missing.append(item["ticker"])
            continue
        warnings.extend(
            f"{item['ticker']}: {warning}"
            for warning in history.get("warnings") or []
            if str(warning)
        )
        raw_points = list((history.get("daily") or {}).get("points") or [])
        clipped_points = _clip_daily_points(raw_points, window)
        points, baseline, change = _percent_series(clipped_points)
        expected_sessions, _basis, prior_session = _expected_sessions(market_key, window)
        weekly_return, weekly_baseline, weekly_baseline_date, weekly_reason = _prior_week_return(
            raw_points, window, expected_sessions=expected_sessions, prior_session=prior_session,
        )
        if not points or sum(_safe_float(row.get("close")) is not None for row in raw_points) < 2:
            warnings.append(f"{item['ticker']}: weekly_price_history_insufficient")
            missing.append(item["ticker"])
            continue
        series.append({
            "ticker": item["ticker"],
            "providerSymbol": item["ticker"],
            "label": item["label"],
            "currency": item["currency"],
            "timezone": item["timezone"],
            "country": item["country"],
            **({"proxyFor": item["proxyFor"]} if item.get("proxyFor") else {}),
            "provider": history.get("provider") or "market-data-v2",
            "sourceByInterval": deepcopy(history.get("sourceByInterval") or {}),
            "hourly": deepcopy(history.get("hourly") or {"interval": "1h", "points": []}),
            "daily": deepcopy(history.get("daily") or {"interval": "1d", "points": []}),
            "baselineClose": baseline,
            "changePct": change,
            "weeklyReturn": weekly_return,
            "weeklyBaselineClose": weekly_baseline,
            "weeklyBaselineDate": weekly_baseline_date,
            "weeklyEndDate": str(points[-1].get("time") or "")[:10] if points else None,
            "weeklyReturnReason": weekly_reason,
            "points": points,
        })
    return _weekly_flow_snapshot(market_key, window, series, missing, requested)


def _heatmap_rows_by_ticker(payload) -> dict[str, dict]:
    return {
        str(row.get("ticker") or ""): row
        for row in (payload or {}).get("rows") or []
        if str(row.get("ticker") or "")
    }


def _weekly_heatmap_rows(start_payload, end_payload) -> tuple[list[dict], list[str]]:
    """주간 등락으로 다시 계산한 히트맵 행.

    상자 크기(시가총액)와 분류는 **주말 스냅샷**을 그대로 쓴다 — 주초 값으로 그리면
    한 주 동안 오른 종목이 작은 상자에 담겨 그림이 스스로와 어긋난다. 바꾸는 것은
    색을 정하는 `changePct` 하나이며, 주초 종가가 없는 종목은 그리지 않는다(0%로 두면
    "안 움직였다"가 되어 결측이 사실로 둔갑한다).
    """
    starts = _heatmap_rows_by_ticker(start_payload)
    rows, dropped = [], []
    for row in (end_payload or {}).get("rows") or []:
        ticker = str(row.get("ticker") or "")
        start_close = _safe_float((starts.get(ticker) or {}).get("close"))
        end_close = _safe_float(row.get("close"))
        if not ticker or not start_close or end_close is None:
            if ticker:
                dropped.append(ticker)
            continue
        rows.append({
            **row,
            "changePct": round((end_close / start_close - 1) * 100, 4),
            "startClose": start_close,
        })
    return rows, dropped


def _weekly_heatmap_snapshot(market_key, window, session_start, session_end, payload, rows, dropped) -> dict:
    meta = MARKET_META[market_key]
    requested = int(((payload or {}).get("coverage") or {}).get("requested") or 0)
    warnings = list((payload or {}).get("warnings") or [])
    if dropped:
        warnings.append(f"no week-start close for {len(dropped)} constituents")
    return {
        "schemaVersion": 2,
        "id": f"weekly-heatmap:{market_key}:{window.publication_date}",
        "type": "market_heatmap",
        "role": WEEKLY_FLOW_ROLE,
        "range": "week",
        "market": meta["market"],
        "window": window.to_dict(),
        "weekLabel": window.label,
        # 색이 무엇을 재는지 그림이 스스로 말할 수 있게 두 끝을 남긴다.
        "changeBasis": {"startDate": session_start, "endDate": session_end, "kind": "week_over_week_close"},
        "asOf": session_end,
        "provider": (payload or {}).get("provider") or "unavailable",
        "freshness": "close_snapshot" if rows else "unavailable",
        "coverage": {
            "requested": requested,
            "returned": len(rows),
            "ratio": round(len(rows) / requested, 3) if requested else 0.0,
            # 일간 히트맵(`visuals.py`)과 프론트 `renderHeatmap()`이 "완전"을
            # "complete"로만 인식한다 — "ok"를 쓰면 100% 채워진 주간 히트맵도
            # 매번 불완전으로 오판해 그림 자체가 나오지 않는다(2026-09-13 실측).
            "status": "complete" if rows and requested and len(rows) / requested >= 0.8 else "partial" if rows else "unavailable",
        },
        "timezone": meta["timezone"],
        "currency": _heatmap_currency(meta, payload),
        "weightBasis": str((payload or {}).get("weightBasis") or "market_cap"),
        "rows": rows,
        "warnings": warnings,
    }


def _session_bounds(flow_snapshot, window: WeeklyWindow) -> tuple[str, str]:
    """히트맵이 쓸 주초·주말 거래일. **지수 계열이 실제로 가진 날**을 쓴다.

    A와 B가 같은 두 날을 써야 "지수는 이만큼 올랐는데 종목은 이렇게 갈렸다"가 같은
    구간의 이야기가 된다. 달력 날짜로 각자 잡으면 휴장일에서 하루씩 어긋난다.
    """
    sessions = list(flow_snapshot.get("sessionDates") or [])
    if len(sessions) >= 2:
        return sessions[0], sessions[-1]
    return window.week_start, window.week_end


def _story_share_snapshot(market_key, window, documents, warnings) -> dict:
    """그 주 거래일별 동인 비중.

    입력은 **그 주간 보고서가 쓴 자료 풀 그대로**다(`weekly_documents`). 대시보드처럼
    세션 창으로 다시 고르지 않는다 — 세션 창은 보통 이틀이라 이웃한 날의 창이 겹쳐
    같은 기사가 두 막대에 들어간다. 문서를 자기 날짜에만 세면 "어느 날 어떤 이야기가
    있었나"가 정직해지고, 그림이 보고서 자신의 근거 구성을 보여주게 된다.

    동인 어휘표는 대시보드와 **같은 것**을 쓴다(`infer_drivers`).
    """
    from features.daily_briefing.issue_selection import documents_for_scope
    from features.dashboard.story_share import (
        MIN_CONFIDENT_SAMPLE,
        OTHER_LABEL,
        TOP_STORY_LIMIT,
        UNCLASSIFIED_DRIVERS,
        _story_counts,
    )
    from features.daily_briefing.selection import DRIVER_TERMS

    scoped = documents_for_scope(list(documents or []), market_key)
    by_date: dict[str, list[dict]] = {}
    for doc in scoped:
        day = str(doc.get("date") or "")[:10]
        if day in _window_dates(window):
            by_date.setdefault(day, []).append(doc)

    total_counts, _ = _story_counts(scoped)
    ranked = sorted(
        ((label, count) for label, count in total_counts.items() if label != OTHER_LABEL),
        key=lambda row: (-row[1], row[0]),
    )
    # **색과 순서는 그 주 전체 기준으로 한 번 정한다.** 날마다 상위 넷을 다시 고르면
    # 같은 색이 막대마다 다른 이야기를 가리켜 추이를 읽을 수 없다.
    drivers = [label for label, _ in ranked[:TOP_STORY_LIMIT]]
    days = []
    for day in sorted(by_date):
        counts, doc_count = _story_counts(by_date[day])
        total = sum(counts.values())
        if not total:
            continue
        shares = {label: round(counts.get(label, 0) / total, 4) for label in drivers}
        other = total - sum(counts.get(label, 0) for label in drivers)
        days.append({
            "date": day,
            "docCount": doc_count,
            "shares": shares,
            "otherShare": round(other / total, 4) if other > 0 else 0.0,
        })
    if not days:
        warnings.append(f"{market_key}: no weekly story share documents")
    small = [row["date"] for row in days if row["docCount"] < MIN_CONFIDENT_SAMPLE]
    snapshot_warnings = []
    if small:
        # 표본이 적으면 기사 한두 건이 비중을 수십 %p 움직인다. 대시보드와 같은 경계다.
        snapshot_warnings.append(f"small sample on {len(small)} of {len(days)} days")
    return {
        "id": f"weekly-story-share:{market_key}:{window.publication_date}",
        "schemaVersion": 2,
        "type": "story_share_series",
        "role": WEEKLY_STORY_ROLE,
        "range": "week",
        "market": MARKET_META[market_key]["market"],
        "window": window.to_dict(),
        "weekLabel": window.label,
        "asOf": days[-1]["date"] if days else window.week_end,
        "provider": "folio-research-index",
        "freshness": "close_snapshot" if days else "unavailable",
        "coverage": {
            "requested": len(window.source_dates),
            "returned": len(days),
            "ratio": round(len(days) / len(window.source_dates), 3) if window.source_dates else 0.0,
            "status": "ok" if days else "unavailable",
        },
        "timezone": MARKET_META[market_key]["timezone"],
        "drivers": drivers,
        "otherLabel": OTHER_LABEL,
        "days": days,
        "collectedCount": len(scoped),
        "minConfidentSample": MIN_CONFIDENT_SAMPLE,
        "smallSample": bool(small),
        # 규칙 계산 표시용 계약. 비중 이동은 보도량 변화이지 내용 변화가 아니다.
        "basis": "collected_news_volume",
        "driverBasis": {"kind": "fixed_vocabulary", "count": len(DRIVER_TERMS)},
        "unclassifiedExcluded": sorted(UNCLASSIFIED_DRIVERS),
        "warnings": snapshot_warnings,
    }


def collect_weekly_visuals(
    window: WeeklyWindow,
    market_scope,
    *,
    documents=None,
    markets=None,
    price_history_fetcher=None,
    heatmap_fetchers=None,
) -> dict:
    """주간 A·B·C를 한 창에서 모은다. 반환 모양은 `collect_briefing_visuals`와 같다."""
    fetch_price = price_history_fetcher or build_price_history
    heatmap_fetchers = heatmap_fetchers or {
        "us": lambda session_date: build_us_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "kr": lambda session_date: build_kospi_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "europe": lambda session_date: build_europe_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "jp": lambda session_date: build_nikkei_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
    }
    # **시장은 목록으로 받는 것이 정답이다.** 범위 라벨은 임의 조합을 담지 못한다 —
    # 한국+일본은 `multi`가 되고, `multi`는 정규화가 몰라 기본값 `BOTH`(미국+한국)로
    # 떨어진다. 그러면 일본 주간은 시각자료 0장으로 조용히 저장되고 미국 universe를
    # 받아서 버린다(예약이 고른 시장만 만든다는 §10 계약과 같은 결함). 라벨은 목록이
    # 없는 옛 호출자 호환용 fallback으로만 남는다.
    if markets:
        scopes = [key for key in (str(market).lower() for market in markets) if key in MARKET_META]
    else:
        scope = normalize_saved_market_scope(market_scope, default=SavedMarketScope.BOTH)
        scopes = [
            key for key in (code.value.lower() for code in market_keys_for_scope(scope, saved=True))
            if key in MARKET_META
        ]
    snapshots, recommendations, sidecar_snapshots, warnings = [], [], {}, []

    for market_key in scopes:
        meta = MARKET_META[market_key]
        market = meta["market"]

        flow = _collect_weekly_flow(market_key, window, fetch_price, warnings)
        snapshots.append(flow)
        recommendations.append(_recommendation(
            flow, "trend", "weekly_flow_chart",
            f"{market} 주요 지수 · {window.label}",
            {"market": market, "sectionRole": WEEKLY_FLOW_ROLE, "order": 1},
        ))
        recommendations[-1]["defaultPeriod"] = "1W"

        if documents is not None:
            story = _story_share_snapshot(market_key, window, documents, warnings)
            snapshots.append(story)
            recommendations.append(_recommendation(
                story, "composition", "story_share_bars",
                f"{market} 이야기 비중 추이 · {window.label}",
                {"market": market, "sectionRole": WEEKLY_STORY_ROLE, "order": 1},
            ))

        # 히트맵 지원은 시장 계약이 정한다. 네 시장 모두 구성종목 universe를 갖고 있고
        # (실측 2026-08-14: 유럽 199·일본 225·미국 497 종목), 계약이 바뀌면 여기도 따라간다.
        if not meta["supportsHeatmap"]:
            continue

        session_start, session_end = _session_bounds(flow, window)
        try:
            end_payload = heatmap_fetchers[market_key](session_end) or {}
            start_payload = heatmap_fetchers[market_key](session_start) or {}
        except Exception:
            warnings.append(f"{market_key} weekly heatmap: unavailable")
            continue
        rows, dropped = _weekly_heatmap_rows(start_payload, end_payload)
        if not rows:
            warnings.append(f"{market_key} weekly heatmap: no week-over-week rows")
            continue
        sidecar = _weekly_heatmap_snapshot(
            market_key, window, session_start, session_end, end_payload, rows, dropped,
        )
        sidecar_snapshots[sidecar["id"]] = sidecar
        inline = {key: value for key, value in sidecar.items() if key != "rows"}
        inline["sidecarRef"] = {
            "file": f"data/briefings/{visual_sidecar_gzip_file_name(window.publication_date, market_key, 'weekly')}",
            "snapshotId": sidecar["id"],
        }
        snapshots.append(inline)
        recommendations.append(_recommendation(
            inline, "composition", "treemap_heatmap",
            f"{market} 주간 히트맵 · {window.label}",
            {"market": market, "sectionRole": WEEKLY_FLOW_ROLE, "order": 2},
        ))

    return {
        "visualRecommendations": recommendations,
        "visualSnapshots": snapshots,
        "sidecar": {
            "schemaVersion": 2,
            "date": window.publication_date,
            "kind": "weekly",
            "window": window.to_dict(),
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "snapshots": sidecar_snapshots,
        },
        "warnings": warnings,
    }
