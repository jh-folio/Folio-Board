from __future__ import annotations

import datetime as dt
import os
import gzip
import json
from pathlib import Path
import re
from typing import Any, Callable
import urllib.request

from features.common.atomic_replace import write_bytes_atomic


NASDAQ_SCREENER_URL = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&limit=10000&offset=0&download=true"
)


def _number(value: Any) -> float:
    text = str(value or "").replace("$", "").replace(",", "").strip().upper()
    if not text:
        return 0.0
    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)\s*([KMBT]?)", text)
    if not match:
        return 0.0
    multipliers = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    return float(match.group(1)) * multipliers[match.group(2)]


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value != value:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


SHARE_CLASS_GROUPS = {
    "GOOG": "ALPHABET",
    "GOOGL": "ALPHABET",
    "BRK.A": "BERKSHIRE_HATHAWAY",
    "BRK.B": "BERKSHIRE_HATHAWAY",
    "BRK-A": "BERKSHIRE_HATHAWAY",
    "BRK-B": "BERKSHIRE_HATHAWAY",
    "FOX": "FOX_CORP",
    "FOXA": "FOX_CORP",
    "NWS": "NEWS_CORP",
    "NWSA": "NEWS_CORP",
}
SHARE_CLASS_SUFFIX_RE = re.compile(r"\s*\((?:class|series)\s+[a-z0-9]+\)\s*$", re.IGNORECASE)


def _coverage(requested: int, returned: int) -> dict:
    return {
        "requested": requested,
        "returned": returned,
        "ratio": round(returned / requested, 4) if requested else 0.0,
        "status": "complete" if requested and returned == requested else "partial" if returned else "unavailable",
    }


def _ticker_key(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", ".")


def _base_company_label(row: dict) -> str:
    label = str(row.get("label") or row.get("name") or row.get("ticker") or "").strip()
    label = SHARE_CLASS_SUFFIX_RE.sub("", label).strip()
    return label or str(row.get("ticker") or "").strip()


def _share_class_group_key(row: dict) -> str:
    ticker = _ticker_key(row.get("ticker"))
    explicit = SHARE_CLASS_GROUPS.get(ticker) or SHARE_CLASS_GROUPS.get(ticker.replace(".", "-"))
    if explicit:
        return f"share-class:{explicit}"
    base = _base_company_label(row)
    original = str(row.get("label") or row.get("name") or row.get("ticker") or "").strip()
    if base and base != original:
        return f"label:{base.casefold()}:{str(row.get('sector') or '').casefold()}:{str(row.get('industry') or '').casefold()}"
    return f"ticker:{ticker}"


def _combined_provider(rows: list[dict]) -> str:
    parts = []
    for row in rows:
        parts.extend(_provider_parts(row.get("priceProvider") or ""))
    deduped = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
    return "+".join(deduped) or "unknown"


def collapse_share_class_rows(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(_share_class_group_key(row), []).append(row)
    collapsed = []
    for members in groups.values():
        ordered = sorted(members, key=lambda row: _number(row.get("marketCap")), reverse=True)
        primary = dict(ordered[0])
        tickers = [str(row.get("ticker") or "").strip().upper() for row in ordered if str(row.get("ticker") or "").strip()]
        if len(ordered) > 1:
            weighted = 0.0
            weight_total = 0.0
            for row in ordered:
                weight = _number(row.get("marketCap"))
                change = _safe_float(row.get("changePct"))
                if weight > 0 and change is not None:
                    weighted += change * weight
                    weight_total += weight
            primary.update({
                "label": _base_company_label(primary),
                "marketCap": max(_number(row.get("marketCap")) for row in ordered),
                "changePct": round(weighted / weight_total, 6) if weight_total else primary.get("changePct"),
                "classTickers": tickers,
                "classLabels": [str(row.get("label") or row.get("name") or row.get("ticker") or "").strip() for row in ordered],
                "priceProvider": _combined_provider(ordered),
            })
        collapsed.append(primary)
    return sorted(collapsed, key=lambda row: _number(row.get("marketCap")), reverse=True)


def collapse_share_class_universe(rows: list[dict]) -> list[dict]:
    return collapse_share_class_rows([
        {**row, "priceProvider": str(row.get("priceProvider") or "universe")}
        for row in rows
    ])


def normalize_nasdaq_row(row: dict) -> dict:
    ticker = str(row.get("symbol") or "").strip().upper()
    return {
        "ticker": ticker,
        "providerSymbol": ticker.replace("/", "-"),
        "label": str(row.get("name") or ticker).strip(),
        "sector": str(row.get("sector") or "Other").strip(),
        "industry": str(row.get("industry") or "Other").strip(),
        "marketCap": _number(row.get("marketCap")),
    }


def heatmap_row(meta: dict, price: dict | None) -> dict | None:
    if not price or not meta.get("ticker") or _number(meta.get("marketCap")) <= 0:
        return None
    close = _safe_float(price.get("close"))
    previous = _safe_float(price.get("previousClose"))
    if close is None:
        return None
    return {
        **meta,
        "close": close,
        "changePct": round(((close / previous) - 1.0) * 100.0, 6) if previous not in {None, 0} else None,
        "asOf": str(price.get("asOf") or "")[:10],
        "priceProvider": str(price.get("provider") or "").strip() or "unknown",
    }


def snapshot_payload(market: str, date: str, provider: str, requested: list, rows: list[dict]) -> dict:
    requested_count = len(requested)
    returned = len(rows)
    return {
        "market": market,
        "asOf": str(date)[:10],
        "provider": provider,
        "freshness": "close_snapshot" if returned else "unavailable",
        "coverage": _coverage(requested_count, returned),
        "rows": rows,
        "warnings": [],
    }


def unavailable_snapshot(market: str, date: str, provider: str, error: str) -> dict:
    return {
        "market": market,
        "asOf": str(date)[:10],
        "provider": provider,
        "freshness": "unavailable",
        "coverage": _coverage(0, 0),
        "rows": [],
        "warnings": [str(error)[:160]],
    }


def save_last_good_snapshot(path: Path | str, payload: dict) -> bool:
    """마지막 정상 스냅샷을 저장한다. 저장 실패는 스냅샷 생성을 죽이지 않는다.

    이 캐시는 부가물이다. 여기 오면 시세를 이미 다 받아 rows를 만든 뒤라, 캐시
    저장 하나 때문에 예외를 올리면 그 시장 히트맵이 통째로 비고 브리핑 사이드카는
    immutable이라 영구히 unavailable로 남는다.

    교체는 `atomic_replace`를 거친다 — Windows에서 백신·색인기가 대상 파일을 잠깐
    잡으면 원자적 교체가 거부되는데, 붙잡는 시간이 보통 수십 밀리초라 잠깐
    물러났다 다시 시도하면 풀린다.
    """
    try:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        write_bytes_atomic(Path(path), gzip.compress(body, 6))
        return True
    except OSError:
        return False


def load_last_good_snapshot(path: Path | str) -> dict | None:
    try:
        with gzip.open(Path(path), "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def fetch_nasdaq_screener() -> list[dict]:
    request = urllib.request.Request(NASDAQ_SCREENER_URL, headers={
        "User-Agent": "Mozilla/5.0 Folio-OS/1.0",
        "Accept": "application/json",
        "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return (((payload or {}).get("data") or {}).get("rows") or [])


def _close_pairs(frame, ticker: str, target: str) -> list[tuple[str, float]]:
    if frame is None or getattr(frame, "empty", True):
        return []
    subframe = frame
    columns = getattr(frame, "columns", None)
    if getattr(columns, "nlevels", 1) > 1:
        level_zero = {str(value) for value in columns.get_level_values(0)}
        level_one = {str(value) for value in columns.get_level_values(1)}
        if ticker in level_zero:
            subframe = frame[ticker]
        elif ticker in level_one:
            subframe = frame.xs(ticker, axis=1, level=1)
        else:
            return []
    try:
        series = subframe["Close"]
    except Exception:
        return []
    pairs = []
    for index, value in series.items():
        date = index.date().isoformat() if hasattr(index, "date") else str(index)[:10]
        close = _safe_float(value)
        if close is not None and date <= target:
            pairs.append((date, close))
    return pairs


def fetch_bulk_daily_prices(tickers: list[str], date: str) -> dict[str, dict]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("market_data_network_disabled_in_tests")
    import yfinance as yf

    target = str(date)[:10]
    target_date = dt.date.fromisoformat(target)
    output = {}
    for offset in range(0, len(tickers), 100):
        batch = tickers[offset:offset + 100]
        provider_symbols = {
            ticker: f"{ticker}.KS" if re.fullmatch(r"\d{6}", str(ticker or "")) else re.sub(r"[./]", "-", ticker)
            for ticker in batch
        }
        frame = yf.download(
            list(provider_symbols.values()),
            start=(target_date - dt.timedelta(days=14)).isoformat(),
            end=(target_date + dt.timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        for ticker, provider_symbol in provider_symbols.items():
            pairs = _close_pairs(frame, provider_symbol, target)
            if not pairs:
                continue
            output[ticker] = {
                "close": pairs[-1][1],
                "previousClose": pairs[-2][1] if len(pairs) >= 2 else None,
                "asOf": pairs[-1][0],
                "provider": "yfinance",
            }
    return output


def _provider_parts(*providers: str) -> list[str]:
    parts = []
    for provider in providers:
        for part in str(provider or "").split("+"):
            part = part.strip()
            if part and part not in parts:
                parts.append(part)
    return parts


def _provider_label(prefix: str, rows: list[dict], fallback: str) -> str:
    parts = []
    for row in rows:
        parts.extend(_provider_parts(row.get("priceProvider") or ""))
    deduped = []
    for part in parts:
        if part in {"unavailable", "unknown"}:
            continue
        if part and part not in deduped:
            deduped.append(part)
    return f"{prefix}+{'+'.join(deduped)}" if deduped else fallback


def fetch_toss_then_bulk_daily_prices(tickers: list[str], date: str) -> dict[str, dict]:
    """Prefer Toss current prices when they match the target date.

    Toss batch prices do not include previous close in the current public
    contract, so yfinance daily bars remain the bulk fallback used for previous
    close and missing symbols.
    """
    target = str(date)[:10]
    try:
        from features.llm_settings.client import toss_open_api_enabled
        if not toss_open_api_enabled():
            return fetch_bulk_daily_prices(tickers, target)
    except Exception:
        return fetch_bulk_daily_prices(tickers, target)
    toss_rows = []
    try:
        from features.common.market_data.toss_open_api import fetch_toss_prices
        for offset in range(0, len(tickers), 200):
            toss_rows.extend(fetch_toss_prices(tickers[offset:offset + 200]))
    except Exception:
        toss_rows = []
    toss_by_symbol = {
        str(row.get("symbol") or "").strip().upper(): row
        for row in toss_rows
        if _safe_float(row.get("lastPrice")) is not None
    }
    try:
        yfinance_prices = fetch_bulk_daily_prices(tickers, target)
    except Exception:
        yfinance_prices = {}
    if not toss_by_symbol:
        return yfinance_prices
    output = dict(yfinance_prices)
    for ticker in tickers:
        raw = str(ticker or "").strip().upper()
        toss_symbol = raw.split(".", 1)[0] if raw.endswith((".KS", ".KQ")) else raw
        toss = toss_by_symbol.get(toss_symbol)
        toss_date = str((toss or {}).get("timestamp") or "")[:10]
        if not toss or toss_date != target:
            continue
        baseline = yfinance_prices.get(ticker) or {}
        baseline_as_of = str(baseline.get("asOf") or "")[:10]
        previous = baseline.get("previousClose") if baseline_as_of == target else baseline.get("close")
        provider = "toss_open_api+yfinance" if previous not in {None, 0} else "toss_open_api"
        output[ticker] = {
            "close": _safe_float(toss.get("lastPrice")),
            "previousClose": previous,
            "asOf": target,
            "provider": provider,
        }
    return output


def _default_constituents_loader() -> list[dict]:
    from features.common.market_data.sp500_universe import load_sp500_constituents

    return load_sp500_constituents()


def build_us_heatmap_snapshot(
    date: str,
    *,
    cache_dir: Path | str | None = None,
    constituents: list[dict] | None = None,
    constituents_loader: Callable[[], list[dict]] | None = None,
    price_fetcher: Callable[[list[str], str], dict] | None = None,
    limit: int | None = None,
) -> dict:
    """Build the US heatmap from the embedded S&P 500 universe.

    Membership and sector / sub-industry labels come from the committed
    ``config/sp500_constituents.json`` (GICS taxonomy); only daily prices are
    fetched live, so there is no dependency on a Nasdaq screener call.
    """
    if constituents is None:
        loader = constituents_loader or _default_constituents_loader
        constituents = loader()
    universe = [
        row for row in (constituents or [])
        if str(row.get("ticker") or "") and _number(row.get("marketCap")) > 0
    ]
    if not universe:
        return unavailable_snapshot("US", date, "sp500+yfinance", "embedded S&P 500 universe is empty")
    ranked = sorted(universe, key=lambda row: _number(row.get("marketCap")), reverse=True)
    if limit is not None:
        ranked = ranked[:max(0, int(limit))]
    requested = collapse_share_class_universe(ranked)
    try:
        prices = (price_fetcher or fetch_toss_then_bulk_daily_prices)([row["ticker"] for row in ranked], str(date)[:10])
    except Exception:
        result = unavailable_snapshot("US", date, "sp500+yfinance", "market_data_unavailable")
        result["coverage"] = _coverage(len(requested), 0)
        return result
    rows = [heatmap_row(meta, prices.get(meta["ticker"])) for meta in ranked]
    rows = [row for row in rows if row is not None and row["asOf"] == str(date)[:10]]
    rows = collapse_share_class_rows(rows)
    return snapshot_payload("US", date, _provider_label("sp500", rows, "sp500+yfinance"), requested, rows)


def _pick(row: Any, *names: str) -> Any:
    for name in names:
        try:
            value = row.get(name)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


def _frame_row(frame, ticker: str):
    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        return frame.loc[ticker]
    except Exception:
        try:
            return frame.loc[int(ticker)]
        except Exception:
            return None


def kospi_frames_to_rows(date: str, prices, caps, sectors, members=None) -> list[dict]:
    if prices is None or getattr(prices, "empty", True):
        return []
    member_set = {str(code).zfill(6) for code in members} if members else None
    rows = []
    for raw_ticker, price_row in prices.iterrows():
        ticker = str(raw_ticker).zfill(6)
        if member_set is not None and ticker not in member_set:
            continue
        cap_row = _frame_row(caps, ticker)
        sector_row = _frame_row(sectors, ticker)
        close = _safe_float(_pick(price_row, "종가", "Close", "close", "현재가", "lastPrice"))
        market_cap = _safe_float(_pick(
            cap_row,
            "시가총액", "MarketCap", "marketCap", "market_cap", "Marcap", "marcap", "시총",
        ))
        if close is None or market_cap is None or market_cap <= 0:
            continue
        sector = str(_pick(sector_row, "업종명", "섹터", "sector", "Sector", "업종") or "기타")
        industry = str(_pick(sector_row, "산업명", "industry", "Industry", "업종명", "섹터") or sector)
        label = str(_pick(sector_row, "종목명", "name", "Name", "한글명") or ticker)
        rows.append({
            "ticker": ticker,
            "label": label,
            "sector": sector,
            "industry": industry,
            "close": close,
            "changePct": _safe_float(_pick(price_row, "등락률", "changePct", "Change", "change", "변동률")),
            "marketCap": market_cap,
            "asOf": str(date)[:10],
        })
    return rows


KOSPI200_INDEX_CODE = "1028"


DEFAULT_KOSPI200_FALLBACK_CONSTITUENTS = [
    {"ticker": "005930", "label": "삼성전자", "sector": "전기전자", "industry": "반도체", "marketCap": 100.0},
    {"ticker": "000660", "label": "SK하이닉스", "sector": "전기전자", "industry": "반도체", "marketCap": 62.0},
    {"ticker": "373220", "label": "LG에너지솔루션", "sector": "전기전자", "industry": "2차전지", "marketCap": 28.0},
    {"ticker": "207940", "label": "삼성바이오로직스", "sector": "의약품", "industry": "바이오", "marketCap": 24.0},
    {"ticker": "005380", "label": "현대차", "sector": "운수장비", "industry": "자동차", "marketCap": 23.0},
    {"ticker": "000270", "label": "기아", "sector": "운수장비", "industry": "자동차", "marketCap": 18.0},
    {"ticker": "068270", "label": "셀트리온", "sector": "의약품", "industry": "바이오", "marketCap": 17.0},
    {"ticker": "035420", "label": "NAVER", "sector": "서비스업", "industry": "인터넷", "marketCap": 16.0},
    {"ticker": "105560", "label": "KB금융", "sector": "금융업", "industry": "은행", "marketCap": 15.0},
    {"ticker": "055550", "label": "신한지주", "sector": "금융업", "industry": "은행", "marketCap": 13.0},
    {"ticker": "005490", "label": "POSCO홀딩스", "sector": "철강금속", "industry": "철강", "marketCap": 12.0},
    {"ticker": "006400", "label": "삼성SDI", "sector": "전기전자", "industry": "2차전지", "marketCap": 11.0},
    {"ticker": "051910", "label": "LG화학", "sector": "화학", "industry": "화학", "marketCap": 10.0},
    {"ticker": "012330", "label": "현대모비스", "sector": "운수장비", "industry": "자동차부품", "marketCap": 10.0},
    {"ticker": "035720", "label": "카카오", "sector": "서비스업", "industry": "인터넷", "marketCap": 9.0},
    {"ticker": "086790", "label": "하나금융지주", "sector": "금융업", "industry": "은행", "marketCap": 9.0},
    {"ticker": "028260", "label": "삼성물산", "sector": "유통업", "industry": "상사/건설", "marketCap": 8.0},
    {"ticker": "034020", "label": "두산에너빌리티", "sector": "기계", "industry": "에너지장비", "marketCap": 7.0},
    {"ticker": "012450", "label": "한화에어로스페이스", "sector": "운수장비", "industry": "방산", "marketCap": 7.0},
    {"ticker": "015760", "label": "한국전력", "sector": "전기가스업", "industry": "전력", "marketCap": 7.0},
    {"ticker": "066570", "label": "LG전자", "sector": "전기전자", "industry": "가전", "marketCap": 7.0},
    {"ticker": "032830", "label": "삼성생명", "sector": "보험", "industry": "생명보험", "marketCap": 6.0},
    {"ticker": "000810", "label": "삼성화재", "sector": "보험", "industry": "손해보험", "marketCap": 6.0},
    {"ticker": "316140", "label": "우리금융지주", "sector": "금융업", "industry": "은행", "marketCap": 6.0},
    {"ticker": "033780", "label": "KT&G", "sector": "음식료품", "industry": "담배", "marketCap": 5.0},
]


def _default_kospi200_constituents() -> list[dict]:
    """Embedded KOSPI 200 universe, with the tiny hardcoded list as last resort."""
    try:
        from features.common.market_data.kospi200_universe import load_kospi200_constituents

        rows = load_kospi200_constituents()
    except Exception:
        rows = []
    return rows or DEFAULT_KOSPI200_FALLBACK_CONSTITUENTS


def _kospi_static_fallback_snapshot(
    date: str,
    constituents: list[dict] | None,
    reason: str,
    price_fetcher: Callable[[list[str], str], dict] | None = None,
    *,
    provider_prefix: str = "kospi200-static",
    fallback_freshness: str = "fallback_universe",
) -> dict:
    requested = [
        row for row in (constituents or _default_kospi200_constituents())
        if str(row.get("ticker") or "").strip()
    ]
    try:
        prices = (price_fetcher or fetch_toss_then_bulk_daily_prices)(
            [str(row.get("ticker") or "").strip().zfill(6) for row in requested],
            str(date)[:10],
        )
    except Exception:
        prices = {}
    target = str(date)[:10]
    rows = []
    priced = 0
    for row in requested:
        ticker = str(row.get("ticker") or "").strip().zfill(6)
        size = _safe_float(row.get("marketCap"))
        if not ticker or size is None or size <= 0:
            continue
        sector = str(row.get("sector") or "기타")
        price = prices.get(ticker) or {}
        close = _safe_float(price.get("close"))
        previous = _safe_float(price.get("previousClose"))
        as_of = str(price.get("asOf") or date)[:10]
        exact_price = close is not None and as_of == target
        if exact_price:
            priced += 1
        else:
            close = None
            previous = None
            as_of = target
        rows.append({
            "ticker": ticker,
            "label": str(row.get("label") or row.get("name") or ticker),
            "sector": sector,
            "industry": str(row.get("industry") or sector),
            "close": close,
            "changePct": round(((close / previous) - 1.0) * 100.0, 6) if close is not None and previous not in {None, 0} else None,
            "marketCap": size,
            "asOf": as_of,
            "priceProvider": str(price.get("provider") or "").strip() if exact_price else "unavailable",
        })
    payload = snapshot_payload(
        "KR",
        date,
        _provider_label(provider_prefix, rows, provider_prefix),
        requested,
        rows,
    )
    payload["freshness"] = "close_snapshot" if priced else fallback_freshness if rows else "unavailable"
    payload["priceCoverage"] = _coverage(len(requested), priced)
    if priced < len(requested):
        payload["warnings"].append(f"KOSPI200 price coverage {priced}/{len(requested)}")
    if reason:
        payload["warnings"].append(
            f"{reason}; static KOSPI fallback universe used. Live prices/change rates are unavailable."
        )
    return payload


def build_kospi_heatmap_snapshot(
    date: str,
    *,
    cache_dir: Path | str,
    krx_fetcher: Callable[[str], list[dict]] | None = None,
    fallback_constituents: list[dict] | None = None,
    fallback_price_fetcher: Callable[[list[str], str], dict] | None = None,
) -> dict:
    cache_path = Path(cache_dir) / "kospi-heatmap-last-good.json.gz"
    primary = _kospi_static_fallback_snapshot(
        date,
        fallback_constituents,
        "",
        fallback_price_fetcher,
        provider_prefix="kospi200",
        fallback_freshness="unavailable",
    )
    if (primary.get("priceCoverage") or {}).get("returned"):
        save_last_good_snapshot(cache_path, primary)
        return primary
    try:
        # KRX 직접 조회는 주입된 fetcher가 있을 때만 한다. 기본 경로에서는 정적
        # 구성종목 universe와 yfinance 시세가 먼저 성공하므로 여기까지 오지 않는다.
        # pykrx 기반 기본 fetcher는 2026-08-12에 제거했다 — 1.2.x부터 KRX 계정
        # 자격증명을 요구해 자격증명 없는 설치에서는 절대 성공할 수 없었다.
        rows = krx_fetcher(str(date)[:10]) if krx_fetcher else []
        if rows:
            payload = snapshot_payload("KR", date, "krx_direct", rows, rows)
            save_last_good_snapshot(cache_path, payload)
            return payload
        cached = load_last_good_snapshot(cache_path)
        if cached and cached.get("rows"):
            cached["freshness"] = "stale"
            cached.setdefault("warnings", []).append(
                "KRX returned no KOSPI200 rows; last-good snapshot used"
            )
            return cached
        return _kospi_static_fallback_snapshot(
            date,
            fallback_constituents,
            "KRX returned no KOSPI200 rows",
            fallback_price_fetcher,
        )
    except Exception:
        cached = load_last_good_snapshot(cache_path)
        if not cached or not cached.get("rows"):
            return _kospi_static_fallback_snapshot(date, fallback_constituents, "krx_unavailable", fallback_price_fetcher)
        cached["freshness"] = "stale"
        cached.setdefault("warnings", []).append(
            "KRX unavailable; last-good snapshot used"
        )
        return cached


def fetch_bulk_daily_prices_by_symbol(symbols: list[str], date: str) -> dict[str, dict]:
    """Daily closes keyed by the provider symbol, passed through untouched.

    ``fetch_bulk_daily_prices`` rewrites dots to dashes for US share classes,
    which would turn ``SAP.DE`` into ``SAP-DE`` and ``7203.T`` into ``7203-T``.
    Overseas symbols carry their exchange in that suffix, so they go as-is.
    """
    # 테스트에서는 네트워크를 부르지 않는다. `test_index_snapshots.py`가 heatmap
    # fetcher를 스텁하지 않은 채 collect_briefing_visuals를 불러 실제 yfinance를
    # 때리고, 그 결과(요청일 2026-07-31)를 **실제 last-good 캐시에 저장**했다 —
    # 그날 밤 provider 지연으로 fallback한 브리핑 두 건이 한 달 전 히트맵을 실었다
    # (2026-08-28 실측). 여기서 막으면 어떤 테스트도 캐시를 오염시킬 수 없다.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("market_data_network_disabled_in_tests")
    import yfinance as yf

    target = str(date)[:10]
    target_date = dt.date.fromisoformat(target)
    output: dict[str, dict] = {}
    for offset in range(0, len(symbols), 100):
        batch = [str(symbol or "").strip() for symbol in symbols[offset:offset + 100] if str(symbol or "").strip()]
        if not batch:
            continue
        frame = yf.download(
            batch,
            start=(target_date - dt.timedelta(days=14)).isoformat(),
            end=(target_date + dt.timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        for symbol in batch:
            pairs = _close_pairs(frame, symbol, target)
            if not pairs:
                continue
            output[symbol] = {
                "close": pairs[-1][1],
                "previousClose": pairs[-2][1] if len(pairs) >= 2 else None,
                "asOf": pairs[-1][0],
                "provider": "yfinance",
            }
    return output


def build_overseas_heatmap_snapshot(
    market: str,
    date: str,
    *,
    provider_prefix: str,
    cache_dir: Path | str | None = None,
    constituents: list[dict] | None = None,
    constituents_loader: Callable[[], list[dict]] | None = None,
    price_fetcher: Callable[[list[str], str], dict] | None = None,
    weight_basis: str = "market_cap",
    universe_metadata: dict | None = None,
    limit: int | None = None,
) -> dict:
    """Heatmap for a market whose universe is a committed constituent file.

    ``weightBasis`` travels with the payload because Europe's caps are restated
    into one currency at build time. A consumer that reads the sizes without
    reading what they are denominated in would be guessing.

    A provider failure falls back to the last good snapshot rather than an empty
    map, and says so — an empty heatmap and a flat market look the same.
    """
    if constituents is None:
        constituents = (constituents_loader or (lambda: []))()
    universe = [
        row for row in (constituents or [])
        if str(row.get("providerSymbol") or row.get("ticker") or "") and _number(row.get("marketCap")) > 0
    ]
    if not universe:
        return unavailable_snapshot(market, date, provider_prefix, f"{provider_prefix} universe is empty")
    ranked = sorted(universe, key=lambda row: _number(row.get("marketCap")), reverse=True)
    if limit is not None:
        ranked = ranked[:max(0, int(limit))]
    symbols = [str(row.get("providerSymbol") or row.get("ticker")) for row in ranked]
    cache_path = Path(cache_dir) / f"{provider_prefix}-heatmap-last-good.json.gz" if cache_dir else None

    def _stale_or_unavailable(reason: str) -> dict:
        cached = load_last_good_snapshot(cache_path) if cache_path else None
        if cached and cached.get("rows"):
            cached["freshness"] = "stale"
            cached.setdefault("warnings", []).append(f"{reason}; last-good snapshot used")
            return cached
        result = unavailable_snapshot(market, date, provider_prefix, reason)
        result["coverage"] = _coverage(len(ranked), 0)
        result["weightBasis"] = weight_basis
        return result

    try:
        prices = (price_fetcher or fetch_bulk_daily_prices_by_symbol)(symbols, str(date)[:10])
    except Exception:
        return _stale_or_unavailable("market_data_unavailable")
    rows = [
        row for row in (
            heatmap_row({**meta, "ticker": str(meta.get("providerSymbol") or meta.get("ticker"))},
                        prices.get(str(meta.get("providerSymbol") or meta.get("ticker"))))
            for meta in ranked
        )
        if row is not None and row["asOf"] == str(date)[:10]
    ]
    if not rows:
        return _stale_or_unavailable("no constituent closed on the session date")
    payload = snapshot_payload(market, date, _provider_label(provider_prefix, rows, provider_prefix), ranked, rows)
    payload["weightBasis"] = weight_basis
    # 구성종목 명단의 출처와 기준일을 스냅샷이 함께 들고 간다. 시세 provider만
    # 표시하면 "이 200종목이 어디서 왔는가"에 답할 수 없다.
    if universe_metadata:
        payload["universe"] = dict(universe_metadata)
    if cache_path:
        save_last_good_snapshot(cache_path, payload)
    return payload


def build_europe_heatmap_snapshot(date: str, *, cache_dir: Path | str | None = None, **kwargs) -> dict:
    from features.common.market_data.europe_core_universe import (
        WEIGHT_BASIS,
        load_europe_core_constituents,
        universe_metadata,
    )

    kwargs.setdefault("universe_metadata", universe_metadata())
    kwargs.setdefault("constituents_loader", load_europe_core_constituents)
    kwargs.setdefault("weight_basis", WEIGHT_BASIS)
    return build_overseas_heatmap_snapshot(
        "EUROPE", date, provider_prefix="europe-core", cache_dir=cache_dir, **kwargs,
    )


def build_nikkei_heatmap_snapshot(date: str, *, cache_dir: Path | str | None = None, **kwargs) -> dict:
    from features.common.market_data.nikkei225_universe import (
        WEIGHT_BASIS,
        load_nikkei225_constituents,
        universe_metadata,
    )

    kwargs.setdefault("universe_metadata", universe_metadata())
    kwargs.setdefault("constituents_loader", load_nikkei225_constituents)
    kwargs.setdefault("weight_basis", WEIGHT_BASIS)
    return build_overseas_heatmap_snapshot(
        "JP", date, provider_prefix="nikkei225", cache_dir=cache_dir, **kwargs,
    )
