"""Fetch enriched market data for topic reports: prices, statistics, correlations."""
from __future__ import annotations

import datetime as dt
import statistics
from zoneinfo import ZoneInfo

try:
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = dt.timezone(dt.timedelta(hours=9))


def _safe_float(v):
    try:
        if v != v:
            return None
        return float(v)
    except Exception:
        return None


def _pct(first, last):
    if first is None or last is None or first == 0:
        return None
    return (last / first - 1.0) * 100.0


# `history_period`가 뜻하는 거래일 수. 통계·상관관계는 계속 이 창에서만 계산한다 —
# 창을 늘리면 "1년 상관계수 -0.939" 같은 기존 해석의 의미가 조용히 바뀐다.
_WINDOW_TRADING_DAYS = {
    "1mo": 21, "3mo": 63, "6mo": 126, "1y": 252, "2y": 504, "3y": 756, "5y": 1260, "10y": 2520,
}
_HISTORY_QUARTERS = 28


def _window_length(history_period: str, available: int) -> int:
    want = _WINDOW_TRADING_DAYS.get(str(history_period or "").lower(), 252)
    return max(2, min(available, want))


def _quarterly_closes(dated: list[tuple[str, float]]) -> list[list]:
    """분기마다 마지막 종가 하나. 오래된 것부터.

    과거 국면(2021~2022년 긴축, 2024년 8월 엔캐리 청산)과 지금을 비교하려면 시계열이
    그때까지 닿아야 한다. 일봉을 그대로 실으면 티커 하나가 수천 줄이므로 분기 단위
    궤적으로 압축한다.

    **행은 tuple이 아니라 list다.** 이 값은 보고서 JSON에 그대로 실리고, 정규화
    직렬화기(`common/canonical_json.py`)는 JSON 타입만 받는다 — tuple을 넣으면
    보고서를 다 만들어 놓고 저장 직전에 `assert_never`로 죽는다(실측: 잡이 진행률
    90%에서 `internal_error`로 끝났다).
    """
    picked: dict[str, list] = {}
    for date_text, close in reversed(dated):  # 최신부터 — 분기의 첫 등장이 그 분기 마지막 값
        try:
            year, month = int(date_text[:4]), int(date_text[5:7])
        except Exception:
            continue
        key = f"{year}Q{(month - 1) // 3 + 1}"
        picked.setdefault(key, [key, close])
    rows = [picked[key] for key in sorted(picked, reverse=True)][:_HISTORY_QUARTERS]
    return list(reversed(rows))


def _percentile_rank(series: list[float], value: float) -> float | None:
    """Return the percentile rank of value within series (0–100)."""
    if not series or value is None:
        return None
    below = sum(1 for x in series if x < value)
    return round(below / len(series) * 100, 1)


def fetch_topic_market_data(
    tickers: dict[str, str],
    history_period: str = "3y",
    long_period: str = "10y",
) -> dict:
    """
    Fetch prices + enriched statistics for a set of tickers.

    Returns a dict with:
      - asOf: ISO timestamp
      - tickers: {symbol: {label, last, changes, stats, history_note}}
      - correlations: [{pair, label_a, label_b, corr}]  (top pairs by abs corr)
    """
    try:
        import yfinance as yf
    except Exception:
        return {"ok": False, "error": "yfinance_unavailable", "tickers": {}, "correlations": []}

    raw_closes: dict[str, list[float]] = {}
    result_tickers: dict[str, dict] = {}

    for symbol, label in tickers.items():
        try:
            # 긴 구간을 한 번만 받는다. 요청 비용은 같고, 과거 국면 비교용 시계열이
            # 없어서 못 하던 분석이 가능해진다.
            hist = yf.Ticker(symbol).history(period=long_period, interval="1d", auto_adjust=False)
        except Exception:
            result_tickers[symbol] = {"label": label, "error": "market_data_unavailable"}
            continue
        if hist is None or hist.empty or "Close" not in hist:
            result_tickers[symbol] = {"label": label, "error": "no price data"}
            continue

        dated: list[tuple[str, float]] = []
        for index_value, raw_close in zip(hist.index.tolist(), hist["Close"].tolist(), strict=False):
            close = _safe_float(raw_close)
            if close is not None:
                dated.append((str(index_value)[:10], close))
        if len(dated) < 2:
            result_tickers[symbol] = {"label": label, "error": "insufficient data"}
            continue
        quarterly = _quarterly_closes(dated)
        # 통계·상관관계는 예전과 같은 창(history_period)에서만 계산한다.
        window = _window_length(history_period, len(dated))
        dated_window = dated[-window:]
        closes = [close for _, close in dated_window]

        raw_closes[symbol] = closes
        last = closes[-1]
        prev = closes[-2]

        # Lookback windows (approximate trading days)
        week_ago = closes[-6] if len(closes) >= 6 else closes[0]
        month_ago = closes[-22] if len(closes) >= 22 else closes[0]
        three_month_ago = closes[-66] if len(closes) >= 66 else closes[0]
        six_month_ago = closes[-132] if len(closes) >= 132 else closes[0]
        year_ago = closes[-252] if len(closes) >= 252 else closes[0]

        high_52w = max(closes[-252:]) if len(closes) >= 252 else max(closes)
        low_52w = min(closes[-252:]) if len(closes) >= 252 else min(closes)
        hist_high = max(closes)
        hist_low = min(closes)

        pct_rank = _percentile_rank(closes, last)
        vol_20d = None
        if len(closes) >= 21:
            daily_rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
            try:
                vol_20d = round(statistics.stdev(daily_rets) * (252 ** 0.5) * 100, 2)
            except Exception:
                pass

        result_tickers[symbol] = {
            "label": label,
            "asOfDate": dated[-1][0],
            "last": round(last, 4),
            "changes": {
                "1d": _pct(prev, last),
                "1w": _pct(week_ago, last),
                "1m": _pct(month_ago, last),
                "3m": _pct(three_month_ago, last),
                "6m": _pct(six_month_ago, last),
                "1y": _pct(year_ago, last),
            },
            "stats": {
                "high52w": round(high_52w, 4),
                "low52w": round(low_52w, 4),
                "histHigh": round(hist_high, 4),
                "histLow": round(hist_low, 4),
                "pctRankInPeriod": pct_rank,
                "annualVolatility20d": vol_20d,
                "dataPoints": len(closes),
            },
            "quarterlyHistory": quarterly,
            "historyStart": dated[0][0],
        }

    # Compute pairwise correlations on daily returns
    correlations = []
    symbols = [s for s in raw_closes if len(raw_closes[s]) >= 30]
    if len(symbols) >= 2:
        # Align series by minimum length
        min_len = min(len(raw_closes[s]) for s in symbols)
        daily_rets_by_sym = {}
        for s in symbols:
            c = raw_closes[s][-min_len:]
            daily_rets_by_sym[s] = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]

        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i + 1:]:
                try:
                    ra = daily_rets_by_sym[sym_a]
                    rb = daily_rets_by_sym[sym_b]
                    n = min(len(ra), len(rb))
                    if n < 20:
                        continue
                    corr = _pearson(ra[-n:], rb[-n:])
                    if corr is not None:
                        correlations.append({
                            "pair": f"{sym_a}/{sym_b}",
                            "labelA": tickers.get(sym_a, sym_a),
                            "labelB": tickers.get(sym_b, sym_b),
                            "corr": round(corr, 3),
                        })
                except Exception:
                    continue
        # Sort by absolute correlation (strongest first)
        correlations.sort(key=lambda x: abs(x["corr"]), reverse=True)
        correlations = correlations[:10]

    return {
        "ok": True,
        "asOf": dt.datetime.now(tz=KST).isoformat(),
        "period": history_period,
        "longPeriod": long_period,
        "tickers": result_tickers,
        "correlations": correlations,
    }


def _pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 5:
        return None
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    sx = sum((v - mx) ** 2 for v in x) ** 0.5
    sy = sum((v - my) ** 2 for v in y) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return cov / (sx * sy)


def market_data_to_markdown(data: dict) -> str:
    """Format enriched market data as a markdown table for LLM context."""
    if not data.get("ok"):
        return f"시장 데이터를 불러오지 못했습니다: {data.get('error', 'unknown')}"

    def fmt(v, digits=2):
        if v is None:
            return "-"
        return f"{v:.{digits}f}"

    def pct(v):
        if v is None:
            return "-"
        return f"{v:+.2f}%"

    lines = [
        f"데이터 기준: {data.get('asOf', '')} | 조회 기간: {data.get('period', '')}",
        "",
        "| 지표 | 현재값 | 1D | 1W | 1M | 3M | 1Y | 52W 고점 | 52W 저점 | 기간 내 백분위 | 연환산변동성(20D) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for sym, d in data.get("tickers", {}).items():
        if d.get("error"):
            lines.append(f"| {sym} {d.get('label', '')} | ❌ {d.get('error')} | - | - | - | - | - | - | - | - | - |")
            continue
        ch = d.get("changes", {})
        st = d.get("stats", {})
        prank = f"{st.get('pctRankInPeriod', '-')}%" if st.get("pctRankInPeriod") is not None else "-"
        vol = f"{st.get('annualVolatility20d')}%" if st.get("annualVolatility20d") is not None else "-"
        lines.append(
            f"| {sym} {d.get('label', '')} | {fmt(d.get('last'), 4)} "
            f"| {pct(ch.get('1d'))} | {pct(ch.get('1w'))} | {pct(ch.get('1m'))} "
            f"| {pct(ch.get('3m'))} | {pct(ch.get('1y'))} "
            f"| {fmt(st.get('high52w'), 2)} | {fmt(st.get('low52w'), 2)} "
            f"| {prank} | {vol} |"
        )

    history_lines = []
    for sym, d in data.get("tickers", {}).items():
        rows = d.get("quarterlyHistory") or []
        if d.get("error") or len(rows) < 4:
            continue
        body = " | ".join(f"{period} {value:g}" for period, value in rows)
        history_lines.append(f"- {sym} {d.get('label', '')}: {body}")
    if history_lines:
        lines += [
            "",
            f"**분기별 종가 추이 (최대 {data.get('longPeriod', '')})** — 과거 국면과 현재 수준을 비교할 때 쓰세요. "
            "각 분기의 마지막 거래일 종가입니다.",
            "",
            *history_lines,
        ]

    if data.get("correlations"):
        lines += ["", "**주요 상관관계 (일별 수익률 기준)**", ""]
        lines.append("| 지표 쌍 | 상관계수 | 해석 |")
        lines.append("| --- | ---: | --- |")
        for c in data["correlations"][:6]:
            corr = c["corr"]
            if corr > 0.5:
                interp = "강한 양(+) 동조"
            elif corr > 0.2:
                interp = "약한 양(+) 동조"
            elif corr < -0.5:
                interp = "강한 역(-) 관계"
            elif corr < -0.2:
                interp = "약한 역(-) 관계"
            else:
                interp = "무관"
            lines.append(f"| {c.get('labelA', '')} / {c.get('labelB', '')} | {corr:+.3f} | {interp} |")

    return "\n".join(lines)
