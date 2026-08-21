"""워치리스트 상세의 재무·투자 지표. 예전 TradingView 펀더멘털 위젯의 네이티브 대체.

숫자는 yfinance `info`다. 기업분석은 SEC companyfacts를 최우선으로 쓰므로(§6 절대
규칙 6) 같은 회사라도 값이 다를 수 있다 — 화면이 출처를 밝히고, SEC 등급 숫자는
기업분석이 담당한다. 결측은 그대로 내려보낸다(화면이 `—`로 표시한다). 실측으로
미국·한국·일본 모두 16개 중 14개 이상이 채워지지만, 삼성전자의 PER처럼 provider가
비워 두는 칸이 실제로 있다.
"""
from __future__ import annotations

from pathlib import Path

from features.common.data_reliability.fetch_runtime import FetchPolicy, ProviderFetchRuntime
from features.common.market_data.chart_service import normalize_chart_request

# `info`에서 그대로 옮기는 칸. 이름을 바꾸지 않는 이유는 provider 필드와 화면 사이에
# 번역층이 하나 늘 때마다 결측 원인 추적이 한 단계 어려워지기 때문이다.
FUNDAMENTAL_FIELDS = (
    "marketCap",
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "returnOnEquity",
    "operatingMargins",
    "profitMargins",
    "dividendYield",
    "beta",
    "fiftyTwoWeekLow",
    "fiftyTwoWeekHigh",
    "revenueGrowth",
    "currency",
)


def _download(symbol: str) -> dict:
    import yfinance as yf

    info = yf.Ticker(symbol).info or {}
    out: dict[str, object] = {"symbol": symbol}
    for field in FUNDAMENTAL_FIELDS:
        value = info.get(field)
        if field == "currency":
            out[field] = str(value or "")
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            out[field] = None
            continue
        out[field] = None if number != number else number
    return out


def get_fundamentals(data_dir: Path, *, symbol: str, runtime: ProviderFetchRuntime | None = None) -> dict:
    # 차트와 같은 심볼 규칙을 쓴다 — 두 패널이 같은 티커 문자열을 받는다.
    symbol, _, _ = normalize_chart_request(symbol, "3m", "1d")
    runtime = runtime or ProviderFetchRuntime(Path(data_dir) / "provider-cache" / "fundamentals", max_workers=2)
    # 지표는 분 단위로 바뀌는 값이 아니다. 1시간 TTL에 하루 stale-while-revalidate면
    # 모달을 여는 순간에는 캐시가 즉시 그려지고 갱신은 뒤에서 돈다(차트와 같은 정책).
    result = runtime.fetch(
        "yfinance", "fundamentals", {"symbol": symbol},
        lambda: _download(symbol),
        policy=FetchPolicy(ttl_seconds=3600, timeout_seconds=20, stale_while_revalidate_seconds=86400),
        background_refresh=True,
    )
    value = result.get("value") if isinstance(result.get("value"), dict) else {"symbol": symbol}
    return {
        **{field: None for field in FUNDAMENTAL_FIELDS},
        **value,
        "freshness": result.get("status"),
        "fetchedAt": result.get("fetchedAt") or "",
        "fallbackReason": result.get("fallbackReason") or "",
        "provider": "yfinance",
    }
