"""발표된 실적과 다음 발표 컨센서스. yfinance 하나에서 읽고 출처를 밝힌다.

**기업분석의 숫자와 등급이 다르다.** 기업분석은 SEC companyfacts를 최우선으로 쓰지만
(§6 절대 규칙 6) 워치리스트의 이 패널은 제3자 집계인 yfinance다. 응답에 `provider`를
싣고 화면이 그것을 표시한다 — 같은 앱 안에서 등급이 다른 숫자를 같은 무게로 보이게
하지 않는다.

실측(2026-08-21)으로 정한 경계:

- `earnings_history`는 EPS만 준다(`epsActual`/`epsEstimate`/`epsDifference`/
  `surprisePercent`). **매출 열이 없다** — 매출 실제치는 분기 손익계산서에서 따로 읽는다.
- `calendar`는 다음 발표일과 EPS·매출 컨센서스를 준다. 발표일은 **제3자 예정치**이므로
  확정 배지를 붙이지 않는다(시장 캘린더의 `estimated` 계약과 같다).
- **지난 분기의 매출 컨센서스는 없다.** `calendar`의 매출 평균은 다음 분기 것이라
  매출 서프라이즈 %는 재현할 수 없다. 화면이 "컨센서스 없음"을 숨기지 않고 적는다.
- 모든 종목이 다 주지는 않는다. 실측으로 히타치(6501.T)는 EPS 컨센서스가 `None`이고
  분기 손익계산서에 `Total Revenue` 행 자체가 없다. 빈 칸은 빈 칸으로 둔다.
- `get_earnings_dates()`는 lxml 의존이라 쓰지 않는다(현 환경에 없고 스크래핑 계열).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from features.common.data_reliability.fetch_runtime import FetchPolicy, ProviderFetchRuntime
from features.common.instruments.registry import suffix_currency

# 최근 몇 분기를 보여줄지. `earnings_history`가 주는 것이 보통 4개다.
HISTORY_LIMIT = 4
# 상세 모달을 열 때만 부르는 값이라 짧게 잡을 이유가 없다. 실적은 분기에 한 번
# 바뀌고, 다음 발표일도 하루 단위로 움직인다.
TTL_SECONDS = 6 * 3600


def normalize_ticker(value: str) -> str:
    """차트 API와 같은 모양의 검증. 임의 문자열이 provider로 넘어가지 않게 한다."""
    symbol = str(value or "").strip().upper()
    if not re.fullmatch(r"(?:\^|[0-9A-Z])[0-9A-Z.^=-]{0,23}", symbol):
        raise ValueError("earnings_ticker_invalid")
    return symbol


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # NaN은 자기 자신과 다르다. pandas 결측이 이 모양으로 온다.
    return None if number != number else number


def _quarter_key(value) -> str:
    """분기 종료일을 `YYYY-MM-DD`로. 못 읽으면 빈 문자열."""
    if isinstance(value, (dt.datetime, dt.date)):
        return value.date().isoformat() if isinstance(value, dt.datetime) else value.isoformat()
    text = str(value or "")[:10]
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else ""


def quarter_label(quarter: str) -> str:
    """분기 **종료월**로 부른다.

    회계분기 번호를 붙이지 않는다. 회계연도가 달력과 다른 회사가 많아(LRCX는 6월 결산)
    종료월에서 뽑은 번호가 그 회사의 실제 분기와 어긋난다 — `2026 2Q`라고 적으면 LRCX의
    4분기를 2분기라고 말하는 셈이다. 종료월은 어느 회사에서나 사실이다.
    """
    key = _quarter_key(quarter)
    if not key:
        return ""
    return f"{key[:4]}.{key[5:7]} 종료 분기"


def _earnings_history(ticker) -> list[dict]:
    frame = ticker.earnings_history
    if frame is None or getattr(frame, "empty", True):
        return []
    rows = []
    for index, row in frame.tail(HISTORY_LIMIT * 2).iterrows():
        quarter = _quarter_key(index)
        if not quarter:
            continue
        rows.append({
            "quarter": quarter,
            "label": quarter_label(quarter),
            "epsActual": _number(row.get("epsActual")),
            "epsEstimate": _number(row.get("epsEstimate")),
            "epsDifference": _number(row.get("epsDifference")),
            "surprisePercent": _number(row.get("surprisePercent")),
        })
    rows.sort(key=lambda item: item["quarter"])
    return rows


def _statement_row(frame, name: str) -> dict[str, float]:
    """분기 손익계산서의 한 행을 `분기 종료일 → 값`으로. 행이 없으면 빈 표다."""
    if frame is None or getattr(frame, "empty", True):
        return {}
    label = next((row for row in frame.index if str(row).strip() == name), None)
    if label is None:
        return {}
    series: dict[str, float] = {}
    for column in frame.columns:
        key = _quarter_key(column)
        value = _number(frame.loc[label, column])
        if key and value is not None:
            series[key] = value
    return series


def _quarterly_statement(ticker) -> tuple[dict[str, float], dict[str, float]]:
    """(매출, 기본 EPS). 실측으로 6501.T에는 `Total Revenue` 행 자체가 없다."""
    try:
        frame = ticker.quarterly_income_stmt
    except Exception:  # noqa: BLE001 - 손익계산서가 없어도 보고 EPS는 보여준다
        return {}, {}
    return _statement_row(frame, "Total Revenue"), _statement_row(frame, "Basic EPS")


def _first_date(value) -> str:
    """`calendar`의 발표일은 날짜 하나가 아니라 **목록**으로 온다(범위일 때 2개)."""
    if isinstance(value, (list, tuple)):
        for item in value:
            key = _quarter_key(item)
            if key:
                return key
        return ""
    return _quarter_key(value)


def _next_release(ticker) -> dict:
    try:
        calendar = ticker.calendar
    except Exception:  # noqa: BLE001 - 다음 일정이 없어도 지난 실적은 보여준다
        return {}
    if not isinstance(calendar, dict):
        return {}
    return {
        "date": _first_date(calendar.get("Earnings Date")),
        "epsEstimate": _number(calendar.get("Earnings Average")),
        "epsHigh": _number(calendar.get("Earnings High")),
        "epsLow": _number(calendar.get("Earnings Low")),
        "revenueEstimate": _number(calendar.get("Revenue Average")),
        "revenueHigh": _number(calendar.get("Revenue High")),
        "revenueLow": _number(calendar.get("Revenue Low")),
        # 공식 IR 소스가 아니다. 시장 캘린더의 실적 행과 같은 등급이다.
        "status": "estimated",
    }


def year_ago_key(quarter: str, available) -> str:
    """1년 전 같은 분기의 키. **인덱스로 세지 않는다.**

    `earnings_history`는 보통 4개 분기만 주므로 인덱스로 4칸 뒤를 보면 가장 최근
    분기의 작년 동기가 늘 비어 있다 — 정작 사용자가 가장 보고 싶은 줄이다. 반면 분기
    손익계산서는 그보다 더 뒤까지 준다(실측 LRCX 5개 열). 연도만 하나 빼고 **종료월이
    같은** 키를 찾으면 분기 말일이 며칠 달라도 걸린다.
    """
    key = _quarter_key(quarter)
    if not key:
        return ""
    wanted = f"{int(key[:4]) - 1}-{key[5:7]}"
    return next((row for row in available if str(row).startswith(wanted)), "")


def _download(symbol: str) -> dict:
    import yfinance as yf

    from features.common.market_data.symbols import yfinance_symbol_candidates

    ticker = None
    history, revenue, basic_eps = [], {}, {}
    for candidate in yfinance_symbol_candidates(symbol):
        ticker = yf.Ticker(candidate)
        history = _earnings_history(ticker)
        revenue, basic_eps = _quarterly_statement(ticker)
        # 통화 추정(`suffix_currency`)도 접미사에서 나온다 — 해석된 심볼로 바꿔 둔다.
        symbol = candidate
        if history or revenue:
            break
    eps_by_quarter = {row["quarter"]: row["epsActual"] for row in history}
    for index, row in enumerate(history):
        row["revenueActual"] = revenue.get(row["quarter"])
        # 비교 기준 둘. **직전 분기**는 계절성 때문에 오해하기 쉬우므로 화면이
        # 세 기준을 나란히 두고 사용자가 고르게 한다.
        previous = history[index - 1] if index >= 1 else None
        row["epsPriorQuarter"] = previous["epsActual"] if previous else None
        row["revenuePriorQuarter"] = revenue.get(previous["quarter"]) if previous else None
        row["epsPriorYear"] = eps_by_quarter.get(year_ago_key(row["quarter"], eps_by_quarter))
        row["revenuePriorYear"] = revenue.get(year_ago_key(row["quarter"], revenue))
        if row["epsPriorYear"] is None:
            # **보고 EPS 이력이 1년을 못 채우는 것이 보통이다**(실측 LRCX 4개 분기 →
            # 최근 두 분기의 작년 동기가 비어 있다). 손익계산서는 더 뒤까지 주므로
            # 그쪽 기본 EPS로 채우되, **양쪽을 같은 계열로 맞춘다** — 조정 EPS(보고)와
            # GAAP 기본 EPS를 한 비율의 분자·분모로 섞으면 조정 폭이 증감률로 둔갑한다.
            ago = year_ago_key(row["quarter"], basic_eps)
            current = basic_eps.get(row["quarter"])
            if ago and current is not None:
                row["epsPriorYear"] = basic_eps.get(ago)
                row["epsActualStatement"] = current
                row["epsPriorYearBasis"] = "statement"
    return {
        "ticker": symbol,
        "currency": suffix_currency(symbol) or "USD",
        "next": _next_release(ticker),
        # 최신이 앞. 화면은 가장 최근 발표를 먼저 읽는다.
        "history": list(reversed(history))[:HISTORY_LIMIT],
        "provider": "yfinance",
        "hasRevenue": bool(revenue),
    }


def get_earnings(data_dir: Path, *, ticker: str, runtime: ProviderFetchRuntime | None = None) -> dict:
    """한 종목의 실적 패널 데이터. 상세 모달을 열 때만 부른다.

    카드 그리드에서는 부르지 않는다 — 티커당 provider 호출이라 목록 전체에 걸면
    종목 수만큼 네트워크가 된다(계획 §11 5-A-2 경계).
    """
    symbol = normalize_ticker(ticker)
    runtime = runtime or ProviderFetchRuntime(Path(data_dir) / "provider-cache" / "earnings", max_workers=3)
    result = runtime.fetch(
        "yfinance", "earnings_panel", {"ticker": symbol},
        lambda: _download(symbol),
        policy=FetchPolicy(ttl_seconds=TTL_SECONDS, timeout_seconds=20, stale_while_revalidate_seconds=7 * 86400),
        background_refresh=True,
    )
    # 실패·부분 응답도 같은 모양으로 돌려준다. 키가 빠진 payload를 내려보내면
    # 화면이 종목마다 다른 결측을 각자 방어해야 한다.
    value = {
        "ticker": symbol, "currency": suffix_currency(symbol) or "USD",
        "next": {}, "history": [], "provider": "yfinance", "hasRevenue": False,
        **(result.get("value") if isinstance(result.get("value"), dict) else {}),
    }
    warnings = []
    if not value.get("history"):
        warnings.append("earnings_history_unavailable")
    if not value.get("hasRevenue"):
        warnings.append("revenue_unavailable")
    # **지난 분기의 매출 컨센서스는 어느 종목에도 없다.** provider가 다음 분기 것만
    # 주기 때문이며, 종목 문제로 읽히지 않게 항상 남긴다.
    warnings.append("revenue_consensus_unavailable")
    return {
        **value,
        "freshness": result.get("status"),
        "fetchedAt": result.get("fetchedAt") or "",
        "fallbackReason": result.get("fallbackReason") or "",
        "warnings": warnings,
    }
