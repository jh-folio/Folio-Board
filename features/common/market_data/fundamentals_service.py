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
from features.common.market_data.earnings_service import _statement_row

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

# 문자열 칸은 따로 간다 — 숫자 강제 변환을 태우면 전부 None이 된다.
PROFILE_FIELDS = ("sector", "industry", "longBusinessSummary")


# 분기 차트에 싣는 계열 — 재무제표별로 한 묶음이다. 이름은 yfinance 행 그대로다
# (실측: 미국·한국·일본 셋 다 일곱 행 모두 존재. 손익 5~7분기, 재무·현금흐름 5~6분기).
_QUARTER_STATEMENTS = (
    ("quarterly_income_stmt", (
        ("revenue", "Total Revenue"),
        ("operatingIncome", "Operating Income"),
        ("netIncome", "Net Income"),
    )),
    ("quarterly_balance_sheet", (
        # 막대는 유동성 구조(유동자산·유동부채·비유동부채), 선은 비율(유동비율·부채비율)이다.
        # 부채비율의 분자·분모(총부채·자기자본)는 화면이 계산하도록 값으로 싣는다.
        ("currentAssets", "Current Assets"),
        ("currentLiabilities", "Current Liabilities"),
        ("nonCurrentLiabilities", "Total Non Current Liabilities Net Minority Interest"),
        ("totalDebt", "Total Debt"),
        ("stockholdersEquity", "Stockholders Equity"),
    )),
    ("quarterly_cashflow", (
        ("operatingCashFlow", "Operating Cash Flow"),
        ("freeCashFlow", "Free Cash Flow"),
        ("capitalExpenditure", "Capital Expenditure"),
    )),
)
QUARTER_LIMIT = 5


def _quarterly_earnings(ticker) -> list[dict]:
    """최근 분기들의 손익·재무·현금흐름 계열. 행이 없으면 그 계열만 빈다(6501.T의 매출처럼)."""
    series: dict[str, dict[str, float]] = {}
    for attr, rows in _QUARTER_STATEMENTS:
        try:
            frame = getattr(ticker, attr)
        except Exception:  # noqa: BLE001 - 재무제표 하나가 없어도 나머지는 보여준다
            frame = None
        for key, name in rows:
            series[key] = _statement_row(frame, name)
    quarters = sorted({quarter for rows in series.values() for quarter in rows})[-QUARTER_LIMIT:]
    return [
        {"quarter": quarter, **{key: rows.get(quarter) for key, rows in series.items()}}
        for quarter in quarters
    ]


def _download(symbol: str) -> dict:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    out: dict[str, object] = {"symbol": symbol}
    for field in PROFILE_FIELDS:
        out[field] = str(info.get(field) or "")
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
    out["quarters"] = _quarterly_earnings(ticker)
    return out


def get_fundamentals(data_dir: Path, *, symbol: str, runtime: ProviderFetchRuntime | None = None) -> dict:
    # 차트와 같은 심볼 규칙을 쓴다 — 두 패널이 같은 티커 문자열을 받는다.
    symbol, _, _ = normalize_chart_request(symbol, "3m", "1d")
    runtime = runtime or ProviderFetchRuntime(Path(data_dir) / "provider-cache" / "fundamentals", max_workers=2)
    # 지표는 분 단위로 바뀌는 값이 아니다. 1시간 TTL에 하루 stale-while-revalidate면
    # 모달을 여는 순간에는 캐시가 즉시 그려지고 갱신은 뒤에서 돈다(차트와 같은 정책).
    # 캐시 키에 스키마 버전을 넣는다. 없으면 필드를 추가한 판올림 직후 TTL이 지날 때까지
    # 옛 모양의 캐시가 그대로 내려와, 새 화면(분기 차트)이 조용히 비어 있게 된다(실측).
    result = runtime.fetch(
        "yfinance", "fundamentals", {"symbol": symbol, "schema": 5},
        lambda: _download(symbol),
        policy=FetchPolicy(ttl_seconds=3600, timeout_seconds=20, stale_while_revalidate_seconds=86400),
        background_refresh=True,
    )
    value = result.get("value") if isinstance(result.get("value"), dict) else {"symbol": symbol}
    return {
        **{field: None for field in FUNDAMENTAL_FIELDS},
        **{field: "" for field in PROFILE_FIELDS},
        "quarters": [],
        **value,
        "freshness": result.get("status"),
        "fetchedAt": result.get("fetchedAt") or "",
        "fallbackReason": result.get("fallbackReason") or "",
        "provider": "yfinance",
    }
