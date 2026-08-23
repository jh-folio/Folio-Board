"""Immutable visual data snapshots for dated daily briefings.

Step 2 stores renderer-neutral price series inline and larger heatmap rows in
one dated sidecar.  Collection is best effort: visual failures never block the
Canonical briefing markdown.
"""

from __future__ import annotations

from copy import deepcopy
import datetime as dt
import gzip
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from features.common.market_calendar import is_market_open, latest_trading_day_on_or_before, previous_trading_day
from features.common.markets import PRODUCT_MARKETS
from features.common.config_bootstrap import resolve_config
from features.common.market_data.market_universe import (
    build_europe_heatmap_snapshot,
    build_kospi_heatmap_snapshot,
    build_nikkei_heatmap_snapshot,
    build_us_heatmap_snapshot,
)
from features.common.market_data.price_history import INDEX_UNIVERSE, build_price_history
from features.common.markets import (
    MARKET_REGISTRY,
    PRODUCT_MARKETS,
    SavedMarketScope,
    market_keys_for_scope,
    normalize_saved_market_scope,
)
from features.common.company_resolution import resolve_company_query
from features.common.utils import read_json, write_json
from features.daily_briefing.schema import (
    SINGLE_MARKET_SCOPES,
    normalize_briefing_kind,
    briefing_file_name,
    briefing_scope_view,
    normalize_market_scope,
    visual_sidecar_file_name,
    visual_sidecar_gzip_file_name,
)
from features.common.workspace import data_dir


ROOT = Path(__file__).resolve().parents[2]
MARKET_CACHE_DIR = data_dir() / "market-cache"
# 시장 메타는 레지스트리에서 파생한다. `currency`는 단일 통화 시장의 기본값일 뿐이고,
# 유럽처럼 통화가 둘인 시장은 시리즈별 통화가 권위다(`_price_snapshot` 참고).
MARKET_META = {
    market.value.lower(): {
        "market": market.value,
        "timezone": MARKET_REGISTRY[market].timezone,
        "currency": MARKET_REGISTRY[market].currencies[0] if MARKET_REGISTRY[market].currencies else "",
        "currencies": list(MARKET_REGISTRY[market].currencies),
        "supportsHeatmap": MARKET_REGISTRY[market].capabilities.heatmap,
    }
    for market in PRODUCT_MARKETS
}
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 정규장 시간(현지 시각)과 tzdata가 없을 때의 고정 오프셋. 미국은 서머타임이 있어
# 오프셋을 계산해야 하므로 이 표에 두지 않는다.
_REGULAR_SESSION_HOURS = {
    "us": (dt.time(9, 30), dt.time(16, 0)),
    "kr": (dt.time(9, 0), dt.time(15, 30)),
    "europe": (dt.time(8, 0), dt.time(16, 30)),
    "jp": (dt.time(9, 0), dt.time(15, 30)),
}
_FALLBACK_UTC_OFFSETS = {"kr": (9, "KST"), "jp": (9, "JST"), "europe": (0, "GMT")}


# 단일 시장 스냅샷 필터. 시장 계약에서 파생한다 — {US, KR}로 적어두면 유럽·일본
# 보고서가 필터를 통과하지 못해 전 시장 차트가 섞여 보인다.
VISUAL_SINGLE_MARKETS = frozenset(market.value for market in PRODUCT_MARKETS)


def _safe_float(value):
    try:
        if value is None or value != value:
            return None
        return float(value)
    except Exception:
        return None


def _iso_date(value):
    try:
        return value.date().isoformat()
    except Exception:
        return str(value or "")[:10]


def _provider_symbol(ticker, market):
    ticker = str(ticker or "").strip().upper()
    if str(market).lower() == "kr" and ticker.isdigit() and len(ticker) == 6:
        return f"{ticker}.KS"
    return ticker


def _default_history_fetcher(symbol, start, end):
    import yfinance as yf

    hist = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist:
        return []
    rows = []
    for index, row in hist.iterrows():
        close = _safe_float(row.get("Close"))
        if close is None:
            continue
        rows.append({
            "time": _iso_date(index),
            "open": _safe_float(row.get("Open")),
            "high": _safe_float(row.get("High")),
            "low": _safe_float(row.get("Low")),
            "close": close,
            "volume": _safe_float(row.get("Volume")),
        })
    return rows


def _company_master():
    payload = read_json(resolve_config("company_master.json"), {})
    return [row for row in payload.get("companies", []) if isinstance(row, dict)]


def _market_companies(market):
    target = str(market or "").upper()
    return [row for row in _company_master() if str(row.get("market") or "").upper() == target]


# 시장 라벨은 계약에서 파생한다. 여기에 시장 이름을 다시 적으면 새 시장의
# 주도 기업 제목이 조용히 안 잡히고, 그 기업 차트만 보고서에서 빠진다.
_LEADING_MARKET_LABELS = {"미국장": "us", "한국장": "kr", "유럽장": "europe", "일본장": "jp"}
# ①/②가 표준이지만 LLM이 이따금 1/2로 정규화한다. 그때 제목 파싱이 통째로
# 실패해 기업 차트가 조용히 빠졌으므로 두 표기를 모두 받는다.
LEADING_COMPANY_HEADING_RE = re.compile(
    r"^#{1,6}\s+[34]\.\s*((?:" + "|".join(_LEADING_MARKET_LABELS) + r")(?:을|를)|시장(?:을|를)?)"
    r"\s*주도한 기업\s*([①②12])\s*(?:[-—–:]\s*)?(.+?)\s*$",
    re.MULTILINE,
)


LEADING_COMPANY_MENTION_RE = re.compile(
    r"(" + "|".join(_LEADING_MARKET_LABELS) + r")(?:을|를)?\s*주도한\s*기업"
)


def _leading_mentions_by_market(text):
    """시장별로 본문이 주도 기업 절을 몇 번 불렀는지.

    전체 언급 수 하나로는 부족하다. US와 KR을 함께 담은 보고서는 언급이 넷인데, 그 값을
    시장별 해석 결과와 비교하면 US 둘이 다 풀려도 "모자라다"가 되어 폴백이 헛돈다.

    제목 정규식이 아니라 느슨한 문구로 센다. 제목 형식이 어긋나 파싱에 실패한 경우를
    잡는 것이 이 값의 존재 이유이므로, 파싱과 같은 엄격도로 세면 아무것도 못 잡는다.
    """
    counts = {key: 0 for key in SINGLE_MARKET_SCOPES}
    for label in LEADING_COMPANY_MENTION_RE.findall(str(text or "")):
        key = _LEADING_MARKET_LABELS.get(label)
        if key in counts:
            counts[key] += 1
    return counts


def _resolve_leading_company(company_text, market_key):
    """본문이 부른 이름을 하나의 기업으로 확정한다. 확신이 없으면 확정하지 않는다.

    해석기는 `company_resolution` 하나를 쓴다. 옛 `find_companies`는 SEC 이름 색인을
    첫 단어 하나로만 만들고 그 단어가 7자 미만이거나 흔하면 통째로 버려서, Intel·Ford·
    Visa·Nike·Western Digital이 영원히 안 잡혔다. 한국 종목은 수동 사전 8곳 밖이면
    전부 실패했다(알테오젠). 여기만 옛 경로를 쓰고 있었다.

    `prefer_home`은 제목의 시장이 정한다. 미국장 제목의 "Toyota"는 US 상장(TM)이고
    일본장 제목의 "Toyota"는 자국 상장(7203.T)이다 — 통화도 시간대도 다른 증권이다.

    확신 판정은 해석기가 갖는다(`CONFIDENT_GAP` 등). 여기서 다시 점수를 매기면 두 벌의
    규칙이 서로 어긋난다. `ambiguous`는 후보가 있어도 고르지 않는다 — 빈 차트보다
    나쁜 것은 틀린 회사의 차트다.
    """
    resolution = resolve_company_query(
        company_text, prefer_home=market_key not in (None, "us")
    )
    match = resolution.get("match") or {}
    resolved_market = str(match.get("market") or "").upper()
    if resolution.get("status") != "confident":
        return None, resolved_market, resolution.get("status") or "unknown"
    if market_key is not None and resolved_market != MARKET_META[market_key]["market"]:
        # 제목은 미국장인데 다른 시장 상장으로 풀렸다. 그 시장 차트에 얹으면 세션도
        # 통화도 맞지 않는다.
        return None, resolved_market, "market_mismatch"
    return match, resolved_market, "confident"


def leading_company_subjects_from_markdown(markdown):
    text = str(markdown or "")
    result = {key: [] for key in SINGLE_MARKET_SCOPES}
    result["warnings"] = []
    # 본문이 주도 기업 절을 몇 번 언급했는지. 파싱 결과가 이보다 적으면 제목
    # 형식이 어긋난 것이므로, 차트 수집이 조용히 0개로 끝나는 대신 fallback을 연다.
    result["headingMentions"] = len(re.findall(r"주도한\s*기업", text))
    result["headingMentionsByMarket"] = _leading_mentions_by_market(text)
    # 이름은 읽었지만 어느 기업인지 확정하지 못한 자리. 차트 대상과 섞지 않는다 —
    # 여기 있는 자리는 그리는 것이 아니라 "못 그렸다"고 말하는 대상이다.
    result["unresolvedByMarket"] = {key: [] for key in SINGLE_MARKET_SCOPES}
    seen = set()
    for match in LEADING_COMPANY_HEADING_RE.finditer(text):
        heading_market = match.group(1)
        ordinal = 1 if match.group(2) in ("①", "1") else 2
        company_text = match.group(3).strip().strip("[]")
        market_key = next(
            (key for label, key in _LEADING_MARKET_LABELS.items() if heading_market.startswith(label)),
            None,
        )
        company, resolved_market, status = _resolve_leading_company(company_text, market_key)
        if market_key is None:
            known = {key.upper() for key in SINGLE_MARKET_SCOPES}
            if resolved_market not in known:
                result["warnings"].append(
                    f"leading company {ordinal} market could not be inferred: {company_text}"
                )
                continue
            market_key = resolved_market.lower()
        market = MARKET_META[market_key]["market"]
        key = (market_key, ordinal)
        if key in seen:
            continue
        seen.add(key)
        if company is None:
            # 조용히 버리지 않되, 차트 대상 목록에는 넣지 않는다. 이 목록은 "그릴 수 있는
            # 기업"이고, 여기에 넣으면 폴백이 그 자리를 다른 회사로 채워 본문이 부른 이름
            # 아래에 엉뚱한 기업 차트가 걸린다. 빈 차트보다 나쁜 것이 틀린 차트다.
            result["warnings"].append(
                f"{market} leading company {ordinal} could not be resolved ({status}): {company_text}"
            )
            result["unresolvedByMarket"][market_key].append({
                "ordinal": ordinal,
                "ticker": "",
                "label": company_text,
                "sector": "Other",
                "market": market,
                "unresolved": True,
                "resolutionStatus": status,
            })
            continue
        result[market_key].append({
            "ordinal": ordinal,
            "ticker": str(company.get("ticker") or "").strip().upper(),
            "label": company.get("name") or company_text or company.get("ticker"),
            "sector": company.get("sector") or "Other",
            "market": market,
        })
    for key in SINGLE_MARKET_SCOPES:
        result[key].sort(key=lambda row: row["ordinal"])
    return result


def leading_company_subjects(scope_result, market, limit=2):
    """Pick chartable companies from the same ranked groups used by prose."""
    target = str(market or "").upper()
    selected = []
    seen = set()
    for group in (scope_result or {}).get("groups", []):
        for doc in group.get("docs", []):
            for company in doc.get("companies", []) or []:
                ticker = str(company.get("ticker") or "").strip().upper()
                company_market = str(company.get("market") or target).upper()
                if not ticker or company_market != target or ticker in seen:
                    continue
                seen.add(ticker)
                selected.append({
                    "ticker": ticker,
                    "label": company.get("name") or ticker,
                    "sector": company.get("sector") or group.get("sector") or "Other",
                })
                if len(selected) >= limit:
                    return selected
    return selected


def _leader_slug(leader, ordinal):
    """스냅샷 id의 기업 부분. 티커가 없어도 자리마다 고유해야 한다."""
    ticker = str(leader.get("ticker") or "").strip().upper()
    if ticker:
        return ticker
    return f"unresolved-{ordinal}"


def _fill_missing_leaders(leaders, leader_subjects, scope_result, market_key, warnings):
    """본문이 부른 만큼 자리가 찼는지 보고, 빈 ordinal만 ranked group에서 채운다.

    예전 조건은 `not leaders`였다. ①만 풀리고 ②가 실패하면 목록이 비어 있지 않다는
    이유로 폴백을 건너뛰어, ② 자리는 스냅샷도 추천도 없이 끝났다 — 화면에는 차트가
    있어야 할 자리에 아무것도 없었고 경고는 보고서 JSON에만 남았다.

    미해결로 자리만 잡은 ordinal도 채울 대상이다. 순서는 해석 → ranked group 폴백 →
    unavailable 카드이며, 어느 단계에서 멈추든 자리는 남는다.
    """
    market = MARKET_META[market_key]["market"]
    unresolved = list((leader_subjects.get("unresolvedByMarket") or {}).get(market_key) or [])
    by_market = leader_subjects.get("headingMentionsByMarket") or {}
    expected = int(by_market.get(market_key) or 0)
    if not expected and not leaders and not unresolved:
        # 제목에 시장 라벨조차 없다. 어느 시장 몫인지 셀 수 없으므로 본문 관례대로
        # ①·② 두 자리를 연다 — 이 경로의 기존 동작이다.
        expected = 2 if int(leader_subjects.get("headingMentions") or 0) > 0 else 0

    # 이미 임자가 있는 자리. 미해결 자리도 포함한다 — 본문이 그 자리에 특정 회사를
    # 지목했으므로, 다른 회사로 채우면 이름과 차트가 어긋난다. 그 자리는 채우는 대신
    # unavailable로 남겨 왜 못 그렸는지 말한다.
    taken_ordinals = {int(row.get("ordinal") or 0) for row in (*leaders, *unresolved)}
    free = [o for o in range(1, max(expected, 2) + 1) if o not in taken_ordinals]
    missing = max(0, expected - len(leaders) - len(unresolved))
    if not free or not missing:
        return [*leaders, *unresolved]

    charted = {str(row.get("ticker") or "").upper() for row in leaders}
    pool = [
        row for row in leading_company_subjects(scope_result, market, limit=4)
        if str(row.get("ticker") or "").upper() not in charted
    ]
    filled = []
    for ordinal in free[:missing]:
        if not pool:
            break
        candidate = pool.pop(0)
        leaders.append({
            "ordinal": ordinal,
            "ticker": candidate["ticker"],
            "label": candidate["label"],
            "sector": candidate.get("sector") or "Other",
            "market": market,
            "chartedFromRankedGroup": True,
        })
        filled.append(candidate["ticker"])

    if filled:
        warnings.append(
            f"{market_key}: leading company headings could not be parsed; "
            f"charted ranked-group companies instead: {', '.join(filled)}"
        )
    merged = [*leaders, *unresolved]
    merged.sort(key=lambda row: int(row.get("ordinal") or 0))
    return merged


def _session_date(scope_result, fallback_date):
    return str((scope_result or {}).get("marketSessionDate") or fallback_date or "")[:10]


def _snapshot_session_date(scope_result, fallback_date, market, now=None):
    """Use the latest session that has actually started for today's briefing.

    Legacy Korean briefing windows can still name the briefing date as
    ``krCurrentSessionDate`` before the 09:00 KST open. Price snapshots must
    not request that not-yet-started session: doing so produces empty 5-minute
    bars and can leave the saved chart several days stale. Historical reports
    keep their explicitly stored session date.
    """
    requested = _session_date(scope_result, fallback_date)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    try:
        briefing_timezone = ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        briefing_timezone = dt.timezone(dt.timedelta(hours=9), name="KST")
    if str(fallback_date or "")[:10] != current.astimezone(briefing_timezone).date().isoformat():
        return requested
    latest = _market_clock(market, current)["latestSessionDate"]
    return min(requested, latest) if requested and latest else requested or latest


def _date_window(session_date, lookback_days=45):
    target = dt.date.fromisoformat(session_date)
    return (target - dt.timedelta(days=lookback_days)).isoformat(), (target + dt.timedelta(days=1)).isoformat()


def _coverage(requested, returned, missing):
    requested_count = len(requested)
    return {
        "requested": requested_count,
        "returned": len(returned),
        "ratio": round(len(returned) / requested_count, 4) if requested_count else 0.0,
        "status": "complete" if requested_count and len(returned) == requested_count else "partial" if returned else "unavailable",
        "missingSymbols": list(missing),
    }


def _latest_series_time(series):
    values = []
    for row in series or []:
        for bucket in (row.get("intraday") or {}, row.get("daily") or {}):
            points = bucket.get("points") or []
            if points:
                values.append(str(points[-1].get("time") or ""))
    return max(values, default="")


def _series_provider(series):
    providers = []
    for row in series or []:
        provider = str(row.get("provider") or "").strip()
        if not provider:
            source_by_interval = row.get("sourceByInterval") or {}
            provider = "+".join(
                str(source_by_interval.get(key) or "").strip()
                for key in ("intraday", "daily")
                if str(source_by_interval.get(key) or "").strip()
            )
        for part in provider.split("+"):
            part = part.strip()
            if part and part not in providers:
                providers.append(part)
    return "+".join(providers) if providers else "market-data-v2"


def _snapshot_currencies(meta, series, requested):
    """The currencies the plotted lines are actually denominated in.

    Europe prints the FTSE 100 in GBP and everything else in EUR. Stamping one
    currency on the snapshot would misdescribe half the lines, so the snapshot
    reports the set and each series carries its own.

    Missing series drop out: if the GBP index failed, no axis is in GBP. When no
    series states a currency at all, a single-currency market can safely supply
    its own — but a market with two cannot, and reports unknown rather than
    picking one and being wrong half the time.
    """
    codes = []
    for row in series or requested or []:
        code = str((row or {}).get("currency") or "").strip().upper()
        if code and code not in codes:
            codes.append(code)
    if codes:
        return codes
    return [meta["currency"]] if len(meta["currencies"]) == 1 and meta["currency"] else []


def _heatmap_currency(meta, payload):
    """The currency the box sizes are measured in, read off the weight basis."""
    basis = str((payload or {}).get("weightBasis") or "")
    _, _, suffix = basis.rpartition("_")
    if len(suffix) == 3 and suffix.isalpha():
        return suffix.upper()
    return meta["currency"] if len(meta["currencies"]) == 1 else ""


def _price_snapshot(snapshot_id, market_key, role, session_date, requested, series, missing, subject=None):
    meta = MARKET_META[market_key]
    latest = _latest_series_time(series)
    as_of = latest or session_date
    exact = bool(latest and latest[:10] == session_date)
    freshness = "close_snapshot" if exact else "stale" if latest else "unavailable"
    warnings = []
    if not exact and series:
        warnings.append(f"latest series date {as_of} does not match marketSessionDate {session_date}")
    if missing:
        warnings.append(f"missing symbols: {', '.join(missing)}")
    point_counts = {
        row.get("ticker", ""): {
            "intraday": len(((row.get("intraday") or {}).get("points") or [])),
            "daily": len(((row.get("daily") or {}).get("points") or [])),
        }
        for row in series
    }
    sparse = [ticker for ticker, counts in point_counts.items() if counts["daily"] < 8]
    if sparse:
        warnings.append(f"fewer than 8 temporal points: {', '.join(sparse)}")
    currencies = _snapshot_currencies(meta, series, requested)
    proxies = [
        f"{row.get('ticker', '')} is a proxy for {row.get('proxyFor')}"
        for row in series if row.get("proxyFor")
    ]
    warnings.extend(proxies)
    return {
        "id": snapshot_id,
        "schemaVersion": 2,
        "type": "price_series",
        "role": role,
        "market": meta["market"],
        "marketSessionDate": session_date,
        "asOf": as_of,
        "provider": _series_provider(series),
        "freshness": freshness,
        "coverage": _coverage(requested, series, missing),
        "timezone": meta["timezone"],
        # 단일 통화면 기존과 같은 값이 그대로 나간다. 통화가 섞이면 `MIXED`로 표시하고
        # 실제 통화는 `currencies`와 각 시리즈에서 읽는다.
        "currency": currencies[0] if len(currencies) == 1 else "MIXED" if currencies else "",
        "currencies": currencies,
        "granularities": ["5m", "1d"],
        "dataSufficiency": {"minimumTrendPoints": 8, "pointCounts": point_counts, "status": "sparse" if sparse else "sufficient" if series else "unavailable"},
        "subject": subject or {},
        "series": series,
        "warnings": warnings,
    }


def _recommendation(snapshot, family, variant, title, placement):
    return {
        "id": f"recommendation:{snapshot['id']}",
        "snapshotId": snapshot["id"],
        "market": snapshot["market"],
        "role": snapshot.get("role", ""),
        "family": family,
        "variant": variant,
        "title": title,
        "renderer": "lightweight_charts" if family == "trend" else "plotly",
        "placement": placement,
    }


def collect_briefing_visuals(
    date,
    market_scope,
    scope_results,
    history_fetcher=None,
    price_history_fetcher=None,
    heatmap_fetchers=None,
    leader_subjects=None,
    include_market_visuals=True,
    now=None,
):
    """Collect renderer-neutral snapshots and a heatmap sidecar payload."""
    if price_history_fetcher is not None:
        fetch_price = price_history_fetcher
    elif history_fetcher is not None:
        def fetch_price(symbol, session_date):
            start, end = _date_window(session_date, lookback_days=370)
            rows = [
                row for row in (history_fetcher(symbol, start, end) or [])
                if str(row.get("time") or "")[:10] <= session_date
            ]
            return {
                "intraday": {"interval": "5m", "points": []},
                "daily": {"interval": "1d", "points": rows},
            }
    else:
        fetch_price = build_price_history
    heatmap_fetchers = heatmap_fetchers or {
        "us": lambda session_date: build_us_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "kr": lambda session_date: build_kospi_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "europe": lambda session_date: build_europe_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "jp": lambda session_date: build_nikkei_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
    }
    # 스냅샷 범위는 브리핑 본문의 scope enum이 아니라 시장 계약을 따른다. 유럽·일본
    # 차트는 브리핑 생성이 그 시장을 지원하기 전에도 만들 수 있어야 하고, 나중에
    # 브리핑 scope가 넓어져도 여기는 그대로 둘 수 있다.
    # `both`는 저장된 US/KR 묶음, `all`은 네 시장이다.
    scope = normalize_saved_market_scope(market_scope, default=SavedMarketScope.BOTH)
    scopes = [
        key for key in (code.value.lower() for code in market_keys_for_scope(scope, saved=True))
        if key in MARKET_META
    ]
    snapshots = []
    recommendations = []
    sidecar_snapshots = {}
    warnings = []
    if isinstance(leader_subjects, dict):
        warnings.extend(str(row) for row in leader_subjects.get("warnings", []) if str(row))
    price_cache = {}

    def subject_history(symbol, session_date):
        key = (symbol, session_date)
        if key not in price_cache:
            try:
                value = fetch_price(symbol, session_date) or {}
                price_cache[key] = {
                    "provider": value.get("provider") or "market-data-v2",
                    "sourceByInterval": value.get("sourceByInterval") or {},
                    "intraday": value.get("intraday") or {"interval": "5m", "points": []},
                    "daily": value.get("daily") or {"interval": "1d", "points": []},
                }
            except Exception:
                price_cache[key] = {
                    "provider": "unavailable",
                    "sourceByInterval": {},
                    "intraday": {"interval": "5m", "points": []},
                    "daily": {"interval": "1d", "points": []},
                }
                warnings.append(f"{symbol}: price_history_unavailable")
        return deepcopy(price_cache[key])

    for market_key in scopes:
        meta = MARKET_META[market_key]
        result = (scope_results or {}).get(market_key) or {}
        session_date = _snapshot_session_date(
            result, date, MARKET_META[market_key]["market"], now=now,
        )
        try:
            dt.date.fromisoformat(session_date)
        except ValueError:
            warnings.append(f"{market_key}: invalid marketSessionDate {session_date}")
            continue

        index_requested = list(INDEX_UNIVERSE[market_key]) if include_market_visuals else []
        index_series, index_missing = [], []
        for item in index_requested:
            history = subject_history(item["ticker"], session_date)
            if not (history["intraday"]["points"] or history["daily"]["points"]):
                index_missing.append(item["ticker"])
                continue
            index_series.append({
                "ticker": item["ticker"],
                "providerSymbol": item["ticker"],
                "label": item["label"],
                "currency": item["currency"],
                "timezone": item["timezone"],
                "country": item["country"],
                **({"proxyFor": item["proxyFor"]} if item.get("proxyFor") else {}),
                **history,
            })
        if include_market_visuals:
            index_snapshot = _price_snapshot(
                f"price-series:{market_key}:indices:{date}", market_key, "market_summary", session_date,
                index_requested, index_series, index_missing,
            )
            snapshots.append(index_snapshot)
            recommendations.append(_recommendation(
                index_snapshot,
                "trend",
                "focus_price_chart",
                f"{MARKET_META[market_key]['market']} 주요 지수",
                {"market": MARKET_META[market_key]["market"], "sectionRole": "market_flow", "order": 1},
            ))

        if isinstance(leader_subjects, dict):
            leaders = _fill_missing_leaders(
                list(leader_subjects.get(market_key, [])),
                leader_subjects,
                result,
                market_key,
                warnings,
            )
        else:
            leaders = leading_company_subjects(result, MARKET_META[market_key]["market"], limit=2)
        for position, leader in enumerate(leaders, start=1):
            ordinal = int(leader.get("ordinal") or position)
            unresolved = bool(leader.get("unresolved"))
            # 해석에 실패한 자리도 스냅샷을 만든다. 만들지 않으면 프런트가 매칭되는
            # 추천이 없는 슬롯을 조용히 지나가, 사용자에게는 차트가 있어야 할 자리가
            # 그냥 비어 보인다. 발행 후에야 발견되는 형태였다.
            symbol = "" if unresolved else _provider_symbol(leader["ticker"], market_key)
            history = subject_history(symbol, session_date) if symbol else None
            available = bool(
                history and (history["intraday"]["points"] or history["daily"]["points"])
            )
            series = [{
                "ticker": leader["ticker"],
                "providerSymbol": symbol,
                "label": leader["label"],
                **history,
            }] if available else []
            snapshot = _price_snapshot(
                f"price-series:{market_key}:company:{_leader_slug(leader, ordinal)}:{date}",
                market_key, "leading_company",
                session_date, [leader], series, [] if available else [symbol or leader["label"]],
                subject=leader,
            )
            snapshots.append(snapshot)
            recommendations.append(_recommendation(
                snapshot,
                "trend",
                "focus_price_chart",
                f"{leader['label']} 가격 추이",
                {
                    "market": MARKET_META[market_key]["market"],
                    "sectionRole": "leading_company",
                    "subjectTicker": leader["ticker"],
                    "ordinal": ordinal,
                    "order": 1,
                },
            ))

        if not include_market_visuals:
            continue

        # 유럽·일본은 재배포 가능한 구성종목 universe가 아직 없다(Task 2.3). 히트맵을
        # `unavailable`로 만들어 붙이면 화면에 빈 카드만 남으므로 아예 만들지 않는다.
        if not meta["supportsHeatmap"]:
            continue

        try:
            heatmap_payload = heatmap_fetchers[market_key](session_date) or {}
        except Exception:
            heatmap_payload = {
                "market": MARKET_META[market_key]["market"],
                "asOf": session_date,
                "provider": "unavailable",
                "freshness": "unavailable",
                "coverage": {"requested": 0, "returned": 0, "ratio": 0.0, "status": "unavailable"},
                "rows": [],
                "warnings": ["heatmap_unavailable"],
            }
            warnings.append(f"{market_key} heatmap: unavailable")
        heatmap_id = f"market-heatmap:{market_key}:{date}"
        sidecar_snapshots[heatmap_id] = {
            "schemaVersion": 2,
            "id": heatmap_id,
            "type": "market_heatmap",
            "role": "market_summary",
            "market": MARKET_META[market_key]["market"],
            "marketSessionDate": session_date,
            "asOf": heatmap_payload.get("asOf") or session_date,
            "provider": heatmap_payload.get("provider") or "unavailable",
            "freshness": heatmap_payload.get("freshness") or "unavailable",
            "coverage": heatmap_payload.get("coverage") or {"requested": 0, "returned": 0, "ratio": 0.0, "status": "unavailable"},
            "timezone": meta["timezone"],
            # 유럽 히트맵 상자 크기는 EUR로 환산된 시가총액이다. 시장 기본 통화(GBP)를
            # 붙이면 상자가 무엇으로 측정됐는지 잘못 말하게 된다.
            "currency": _heatmap_currency(meta, heatmap_payload),
            "weightBasis": str(heatmap_payload.get("weightBasis") or "market_cap"),
            "rows": heatmap_payload.get("rows") or [],
            "warnings": heatmap_payload.get("warnings") or [],
        }
        heatmap_snapshot = {
            key: value for key, value in sidecar_snapshots[heatmap_id].items()
            if key not in {"rows"}
        }
        heatmap_snapshot["sidecarRef"] = {
            "file": f"data/briefings/{visual_sidecar_gzip_file_name(date)}",
            "snapshotId": heatmap_id,
        }
        snapshots.append(heatmap_snapshot)
        recommendations.append(_recommendation(
            heatmap_snapshot,
            "composition",
            "treemap_heatmap",
            f"{MARKET_META[market_key]['market']} 전체 시장 히트맵",
            {"market": MARKET_META[market_key]["market"], "sectionRole": "market_flow", "order": 2},
        ))

    return {
        "visualRecommendations": recommendations,
        "visualSnapshots": snapshots,
        "sidecar": {
            "schemaVersion": 2,
            "date": str(date)[:10],
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "snapshots": sidecar_snapshots,
        },
        "warnings": warnings,
    }


def replace_leading_company_visuals(existing, aligned):
    result = deepcopy(existing or {})
    result["visualSnapshots"] = [
        row for row in result.get("visualSnapshots", [])
        if row.get("role") != "leading_company"
    ] + deepcopy((aligned or {}).get("visualSnapshots") or [])
    result["visualRecommendations"] = [
        row for row in result.get("visualRecommendations", [])
        if row.get("role") != "leading_company"
    ] + deepcopy((aligned or {}).get("visualRecommendations") or [])
    warnings = list(result.get("visualWarnings") or [])
    warnings.extend(str(row) for row in (aligned or {}).get("warnings", []) if str(row))
    result["visualWarnings"] = warnings
    return result


def merge_visual_sidecar(current, incoming, market_scope):
    merged = dict(current or {})
    merged.update({key: value for key, value in (incoming or {}).items() if key != "snapshots"})
    snapshots = dict((current or {}).get("snapshots") or {})
    scope = normalize_market_scope(market_scope)
    if scope == "both":
        snapshots = {}
    else:
        target = scope.upper()
        snapshots = {key: value for key, value in snapshots.items() if str(value.get("market") or "").upper() != target}
    snapshots.update((incoming or {}).get("snapshots") or {})
    merged["snapshots"] = snapshots
    return merged


def _read_sidecar_file(path):
    path = Path(path)
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                return json.load(stream)
        return read_json(path, None)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _write_gzip_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
    temporary.replace(path)


def write_visual_sidecar(path, payload, market_scope):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = merge_visual_sidecar(_read_sidecar_file(path) or {}, payload, market_scope)
    if path.suffix == ".gz":
        _write_gzip_json(path, merged)
    else:
        write_json(path, merged)
    return merged


def load_visual_sidecar(date, base_dir=None, market_scope=None, kind=None):
    """Load one immutable dated sidecar without allowing path traversal.

    **종류를 함께 받는다.** 주간 사이드카는 같은 날 같은 시장의 일간 사이드카와
    발행일·시장이 겹치므로, 종류가 없으면 주간 히트맵을 물었을 때 그날 일간 히트맵이
    돌아온다 — 한 주 등락이라고 적힌 카드에 하루 등락이 그려진다.
    """
    date_text = str(date or "").strip()
    if not DATE_PATTERN.fullmatch(date_text):
        return None
    try:
        dt.date.fromisoformat(date_text)
    except ValueError:
        return None
    root = Path(base_dir) if base_dir is not None else data_dir() / "briefings"
    scope = str(market_scope or "").strip().lower()
    report_kind = normalize_briefing_kind(kind)
    file_names = []
    if scope in SINGLE_MARKET_SCOPES:
        file_names.extend((
            visual_sidecar_gzip_file_name(date_text, scope, report_kind),
            visual_sidecar_file_name(date_text, scope, report_kind),
        ))
    file_names.extend((
        visual_sidecar_gzip_file_name(date_text, None, report_kind),
        visual_sidecar_file_name(date_text, None, report_kind),
    ))
    for file_name in file_names:
        payload = _read_sidecar_file(root / file_name)
        if isinstance(payload, dict) and str(payload.get("date") or "") == date_text:
            return payload
    return None


def _load_visual_report(root, date_text, market_scope=""):
    scope = str(market_scope or "").strip().lower()
    if scope in SINGLE_MARKET_SCOPES:
        scoped = read_json(root / briefing_file_name(date_text, scope), None, root=root)
        if isinstance(scoped, dict):
            return briefing_scope_view(scoped, scope)
        legacy = read_json(root / briefing_file_name(date_text), None, root=root)
        if isinstance(legacy, dict):
            return briefing_scope_view(legacy, scope)
        return None

    legacy = read_json(root / briefing_file_name(date_text), None, root=root)
    if isinstance(legacy, dict):
        return legacy
    scoped_reports = {
        key: read_json(root / briefing_file_name(date_text, key), None, root=root)
        for key in SINGLE_MARKET_SCOPES
    }
    present = [key for key in SINGLE_MARKET_SCOPES if isinstance(scoped_reports.get(key), dict)]
    if not present:
        return None
    # 어느 시장이 실제로 있는지에 따라 범위를 정한다. 유럽·일본만 있는 날짜에
    # `both`를 붙이면 담지도 않은 두 시장을 담았다고 말하게 된다.
    return {
        "date": date_text,
        "marketScope": "all" if len(present) > 1 else present[0],
        "includedMarkets": [key.upper() for key in present],
        "visualSnapshots": [
            item for key in present
            for item in ((scoped_reports.get(key) or {}).get("visualSnapshots") or [])
        ],
        "visualRecommendations": [
            item for key in present
            for item in ((scoped_reports.get(key) or {}).get("visualRecommendations") or [])
        ],
    }


def _market_clock(market, now=None):
    # 시장 코드에서 직접 고른다. 예전에는 `US가 아니면 KR`이라 유럽·일본이 KRX 달력과
    # 서울 09:00~15:30에 갇혔고, KRX만 쉬는 날 뒤에는 스냅샷이 본문보다 며칠 이른
    # 세션을 요청했다(설 연휴 뒤 실측 5거래일 차이). 그래도 `close_snapshot`으로
    # 표시돼 어긋난 사실이 드러나지 않았다.
    market_key = str(market or "").lower()
    if market_key not in MARKET_META:
        market_key = "kr"
    meta = MARKET_META[market_key]
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    try:
        timezone = ZoneInfo(meta["timezone"])
    except ZoneInfoNotFoundError:
        if market_key in _FALLBACK_UTC_OFFSETS:
            offset_hours, offset_name = _FALLBACK_UTC_OFFSETS[market_key]
            timezone = dt.timezone(dt.timedelta(hours=offset_hours), name=offset_name)
        else:
            year = current.year
            march = dt.date(year, 3, 1)
            second_sunday_march = march + dt.timedelta(days=(6 - march.weekday()) % 7 + 7)
            november = dt.date(year, 11, 1)
            first_sunday_november = november + dt.timedelta(days=(6 - november.weekday()) % 7)
            eastern_date = current.date()
            offset = -4 if second_sunday_march <= eastern_date < first_sunday_november else -5
            timezone = dt.timezone(dt.timedelta(hours=offset), name="EDT" if offset == -4 else "EST")
    local = current.astimezone(timezone)
    trading_day = is_market_open(local.date(), meta["market"])
    opens, closes = _REGULAR_SESSION_HOURS[market_key]
    state = "open" if trading_day and opens <= local.time() < closes else "closed"
    if trading_day and local.time() < opens:
        reason = "before_regular_session"
        target = previous_trading_day(local.date(), meta["market"])
    else:
        reason = "regular_session" if state == "open" else "outside_regular_session" if trading_day else "non_trading_day"
        target = latest_trading_day_on_or_before(local.date(), meta["market"])
    return {
        "market": meta["market"],
        "state": state,
        "reason": reason,
        "timezone": meta["timezone"],
        "localTime": local.isoformat(),
        "latestSessionDate": target.isoformat(),
    }


def _current_freshness(as_of, target_date, market_state, market):
    if not as_of:
        return "unavailable"
    if as_of == target_date:
        return "delayed" if market_state == "open" else "snapshot"
    try:
        target = dt.date.fromisoformat(target_date)
        if dt.date.fromisoformat(as_of) == previous_trading_day(target, market):
            return "delayed"
    except ValueError:
        pass
    return "stale"


def _latest_close(series):
    points = ((series or {}).get("daily") or {}).get("points") or (series or {}).get("points") or []
    if not points:
        return None
    return _safe_float(points[-1].get("close"))


def _price_comparison(saved, current):
    saved_by_ticker = {str(row.get("ticker") or ""): row for row in saved.get("series") or []}
    changes = []
    for row in current.get("series") or []:
        ticker = str(row.get("ticker") or "")
        generated_close = _latest_close(saved_by_ticker.get(ticker) or {})
        current_close = _latest_close(row)
        change_pct = None
        if generated_close not in {None, 0} and current_close is not None:
            change_pct = (current_close / generated_close - 1.0) * 100.0
        changes.append({
            "ticker": ticker,
            "label": row.get("label") or ticker,
            "generatedClose": generated_close,
            "currentClose": current_close,
            "changePct": round(change_pct, 4) if change_pct is not None else None,
        })
    return {"priceChanges": changes, "sectorRankChanges": []}


def _sector_ranking(rows):
    sectors = {}
    for row in rows or []:
        change = _safe_float(row.get("changePct"))
        weight = _safe_float(row.get("weight"))
        if change is None or weight is None or weight <= 0:
            continue
        sector = row.get("sector") or "Other"
        bucket = sectors.setdefault(sector, {"weighted": 0.0, "weight": 0.0})
        bucket["weighted"] += change * weight
        bucket["weight"] += weight
    ranked = sorted(
        ((sector, values["weighted"] / values["weight"]) for sector, values in sectors.items() if values["weight"]),
        key=lambda item: item[1],
        reverse=True,
    )
    return {sector: {"rank": index + 1, "changePct": change} for index, (sector, change) in enumerate(ranked)}


def _heatmap_comparison(saved, current):
    old_ranks = _sector_ranking(saved.get("rows") or [])
    new_ranks = _sector_ranking(current.get("rows") or [])
    rows = []
    for sector in sorted(set(old_ranks) | set(new_ranks)):
        old = old_ranks.get(sector) or {}
        new = new_ranks.get(sector) or {}
        old_rank, new_rank = old.get("rank"), new.get("rank")
        rows.append({
            "sector": sector,
            "generatedRank": old_rank,
            "currentRank": new_rank,
            "rankChange": old_rank - new_rank if old_rank and new_rank else None,
            "generatedChangePct": round(old["changePct"], 4) if old.get("changePct") is not None else None,
            "currentChangePct": round(new["changePct"], 4) if new.get("changePct") is not None else None,
        })
    rows.sort(key=lambda row: row.get("currentRank") or 10_000)
    return {"priceChanges": [], "sectorRankChanges": rows}


def _current_price_snapshot(saved, fetch_price, clock, warnings, retrieved_at):
    market_key = str(saved.get("market") or "").lower()
    target = clock["latestSessionDate"]
    requested, series, missing = [], [], []
    for saved_series in saved.get("series") or []:
        ticker = str(saved_series.get("ticker") or "").strip().upper()
        symbol = saved_series.get("providerSymbol") or _provider_symbol(ticker, market_key)
        requested.append({"ticker": ticker, "providerSymbol": symbol})
        try:
            history = fetch_price(symbol, target) or {}
        except Exception:
            history = {}
            warnings.append(f"{symbol}: price_history_unavailable")
        intraday = history.get("intraday") or {"interval": "5m", "points": []}
        daily = history.get("daily") or {"interval": "1d", "points": []}
        if not (intraday.get("points") or daily.get("points")):
            missing.append(symbol)
            continue
        series.append({
            "ticker": ticker,
            "providerSymbol": symbol,
            "label": saved_series.get("label") or ticker,
            "intraday": intraday,
            "daily": daily,
        })
    current = _price_snapshot(saved.get("id"), market_key, saved.get("role"), target, requested, series, missing, subject=deepcopy(saved.get("subject") or {}))
    current.update({
        "mode": "current",
        "sourceSnapshotAsOf": saved.get("asOf"),
        "retrievedAt": retrieved_at,
        "marketStatus": deepcopy(clock),
    })
    current["freshness"] = _current_freshness(str(current.get("asOf") or "")[:10] if series else "", target, clock["state"], saved.get("market"))
    return current


def _current_heatmap_snapshot_v2(saved, payload, clock, retrieved_at):
    current = deepcopy(saved)
    current.update({
        "rows": deepcopy(payload.get("rows") or []),
        "marketSessionDate": clock["latestSessionDate"],
        "asOf": payload.get("asOf") or clock["latestSessionDate"],
        "provider": payload.get("provider") or "unavailable",
        "freshness": payload.get("freshness") or "unavailable",
        "coverage": deepcopy(payload.get("coverage") or {"requested": 0, "returned": 0, "ratio": 0.0, "status": "unavailable"}),
        "weightBasis": "market_cap",
        "mode": "current",
        "sourceSnapshotAsOf": saved.get("asOf"),
        "retrievedAt": retrieved_at,
        "marketStatus": deepcopy(clock),
        "warnings": deepcopy(payload.get("warnings") or []),
    })
    current.pop("sidecarRef", None)
    return current


def _current_heatmap_snapshot(saved, saved_detail, fetch, clock, cache, warnings, retrieved_at):
    market_key = str(saved.get("market") or "").lower()
    target = clock["latestSessionDate"]
    start, end = _date_window(target)
    requested = saved_detail.get("rows") or []
    rows, missing = [], []
    for saved_row in requested:
        ticker = str(saved_row.get("ticker") or "").strip().upper()
        symbol = saved_row.get("providerSymbol") or _provider_symbol(ticker, market_key)
        if symbol not in cache:
            try:
                cache[symbol] = [row for row in (fetch(symbol, start, end) or []) if str(row.get("time") or "")[:10] <= target]
            except Exception:
                cache[symbol] = []
                warnings.append(f"{symbol}: price_history_unavailable")
        points = cache[symbol]
        if not points:
            missing.append(symbol)
            continue
        latest = points[-1]
        previous = points[-2] if len(points) >= 2 else None
        close = _safe_float(latest.get("close"))
        previous_close = _safe_float((previous or {}).get("close"))
        change_pct = (close / previous_close - 1.0) * 100.0 if close is not None and previous_close not in {None, 0} else None
        volume = _safe_float(latest.get("volume"))
        rows.append({
            "ticker": ticker,
            "providerSymbol": symbol,
            "label": saved_row.get("label") or ticker,
            "sector": saved_row.get("sector") or "Other",
            "close": close,
            "changePct": change_pct,
            "weight": close * volume if close is not None and volume is not None else close,
            "weightBasis": "session_trading_value" if volume is not None else "close_price_fallback",
            "asOf": latest.get("time"),
        })
    as_of = max((str(row.get("asOf") or "") for row in rows), default="")
    current = deepcopy(saved)
    current.update({
        "rows": rows,
        "marketSessionDate": target,
        "asOf": as_of or target,
        "provider": "yfinance",
        "freshness": _current_freshness(as_of, target, clock["state"], saved.get("market")),
        "coverage": _coverage(requested, rows, missing),
        "mode": "current",
        "sourceSnapshotAsOf": saved.get("asOf"),
        "retrievedAt": retrieved_at,
        "marketStatus": deepcopy(clock),
        "warnings": ([f"missing symbols: {', '.join(missing)}"] if missing else []),
    })
    current.pop("sidecarRef", None)
    return current


def load_current_visuals(
    date,
    base_dir=None,
    history_fetcher=None,
    now=None,
    price_history_fetcher=None,
    heatmap_fetchers=None,
    market="",
    snapshot_id="",
):
    """Build an ephemeral latest REST view from a saved briefing universe.

    This function is deliberately read-only: neither the Canonical report nor
    its immutable visual sidecar is written or merged with current data.
    """
    date_text = str(date or "").strip()
    if not DATE_PATTERN.fullmatch(date_text):
        return None
    root = Path(base_dir) if base_dir is not None else data_dir() / "briefings"
    market_scope = str(market or "").strip().lower()
    report = _load_visual_report(root, date_text, market_scope)
    if not isinstance(report, dict):
        return None
    sidecar = load_visual_sidecar(date_text, root, market_scope=market_scope) or {"snapshots": {}}
    saved_details = sidecar.get("snapshots") or {}
    target_market = str(market or "").strip().upper()
    selected_snapshots = deepcopy(report.get("visualSnapshots") or [])
    if target_market in VISUAL_SINGLE_MARKETS:
        selected_snapshots = [
            row for row in selected_snapshots
            if str(row.get("market") or "").upper() == target_market
        ]
    if snapshot_id:
        selected_snapshots = [row for row in selected_snapshots if row.get("id") == snapshot_id]
    if price_history_fetcher is not None:
        fetch_price = price_history_fetcher
    elif history_fetcher is not None:
        def fetch_price(symbol, session_date):
            start, end = _date_window(session_date, lookback_days=370)
            rows = [
                row for row in (history_fetcher(symbol, start, end) or [])
                if str(row.get("time") or "")[:10] <= session_date
            ]
            return {
                "intraday": {"interval": "5m", "points": []},
                "daily": {"interval": "1d", "points": rows},
            }
    else:
        fetch_price = build_price_history
    batch_heatmaps = heatmap_fetchers or {
        "us": lambda session_date: build_us_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
        "kr": lambda session_date: build_kospi_heatmap_snapshot(session_date, cache_dir=MARKET_CACHE_DIR),
    }
    current_time = now or dt.datetime.now(dt.timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=dt.timezone.utc)
    retrieved_at = current_time.astimezone(dt.timezone.utc).isoformat()
    markets = {str(row.get("market") or "").upper() for row in selected_snapshots if row.get("market")}
    clocks = {market: _market_clock(market, current_time) for market in markets}
    snapshots, comparisons, warnings, legacy_cache, heatmap_cache = [], {}, [], {}, {}
    for saved in selected_snapshots:
        market = str(saved.get("market") or "").upper()
        clock = clocks.get(market) or _market_clock(market, current_time)
        if saved.get("type") == "price_series":
            current = _current_price_snapshot(saved, fetch_price, clock, warnings, retrieved_at)
            comparisons[current["id"]] = _price_comparison(saved, current)
        elif saved.get("type") == "market_heatmap":
            detail = deepcopy(saved_details.get(saved.get("id")) or {})
            if history_fetcher is not None and heatmap_fetchers is None:
                current = _current_heatmap_snapshot(
                    saved, detail, history_fetcher, clock, legacy_cache, warnings, retrieved_at,
                )
            else:
                market_key = market.lower()
                if market_key not in heatmap_cache:
                    try:
                        heatmap_cache[market_key] = batch_heatmaps[market_key](clock["latestSessionDate"]) or {}
                    except Exception:
                        heatmap_cache[market_key] = {
                            "asOf": clock["latestSessionDate"],
                            "provider": "unavailable",
                            "freshness": "unavailable",
                            "coverage": {"requested": 0, "returned": 0, "ratio": 0.0, "status": "unavailable"},
                            "rows": [],
                            "warnings": ["heatmap_unavailable"],
                        }
                        warnings.append(f"{market} heatmap: unavailable")
                current = _current_heatmap_snapshot_v2(saved, heatmap_cache[market_key], clock, retrieved_at)
            comparisons[current["id"]] = _heatmap_comparison(detail, current)
        else:
            continue
        snapshots.append(current)
    available = sum(1 for row in snapshots if row.get("freshness") != "unavailable")
    status = "ok" if snapshots and available == len(snapshots) else "partial" if available else "unavailable"
    if status == "unavailable":
        warnings.append("current market snapshot is unavailable; saved briefing snapshot remains unchanged")
    return {
        "mode": "current",
        "status": status,
        "sourceReportDate": date_text,
        "retrievedAt": retrieved_at,
        "provider": "yfinance" if history_fetcher is not None and price_history_fetcher is None else "market-data-v2",
        "marketStatus": clocks,
        "visualRecommendations": [
            deepcopy(row) for row in report.get("visualRecommendations") or []
            if any(snapshot.get("id") == row.get("snapshotId") for snapshot in selected_snapshots)
        ],
        "visualSnapshots": snapshots,
        "comparisons": comparisons,
        "warnings": warnings,
    }
