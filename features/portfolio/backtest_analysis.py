"""Pure, explicit analysis helpers for research-only Portfolio backtests.

The service owns provider access and persistence.  This module only turns an
already simulated series into transparent statistics and explanations, so it
is deterministic and can be tested without network or workspace state.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any


TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.0
ANALYSIS_VERSION = "u3-v1"


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def daily_returns(values: list[dict]) -> list[dict]:
    rows: list[dict] = []
    previous: float | None = None
    for row in values:
        value = finite_number(row.get("value"))
        if previous is not None and previous != 0 and value is not None:
            rows.append({"date": row.get("date"), "return": value / previous - 1.0})
        previous = value
    return rows


def sample_variance(items: list[float | None]) -> float | None:
    values = [item for item in items if item is not None]
    if len(values) < 2:
        return None
    average = sum(values) / len(values)
    return sum((item - average) ** 2 for item in values) / (len(values) - 1)


def sample_covariance(left: list[float | None], right: list[float | None]) -> float | None:
    pairs = [(a, b) for a, b in zip(left, right) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    left_average = sum(a for a, _ in pairs) / len(pairs)
    right_average = sum(b for _, b in pairs) / len(pairs)
    return sum((a - left_average) * (b - right_average) for a, b in pairs) / (len(pairs) - 1)


def portfolio_return(values: list[dict]) -> float | None:
    if len(values) < 2:
        return None
    start = finite_number(values[0].get("value"))
    end = finite_number(values[-1].get("value"))
    return end / start - 1.0 if start not in (None, 0) and end is not None else None


def _iso_days(start: str | None, end: str | None) -> int | None:
    try:
        return (dt.date.fromisoformat(str(end)) - dt.date.fromisoformat(str(start))).days
    except (TypeError, ValueError):
        return None


def drawdown_analysis(values: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return dated drawdown points and complete/recovering peak-to-trough episodes.

    ``calendarDays`` uses calendar dates while ``underwaterTradingDays`` counts
    submitted value observations.  They intentionally are not interchangeable.
    """
    if not values:
        return [], []
    first_value = finite_number(values[0].get("value"))
    if first_value is None or first_value <= 0:
        return [], []
    peak_value = first_value
    peak_date = str(values[0].get("date") or "")
    points: list[dict] = []
    episodes: list[dict] = []
    active: dict | None = None
    for row in values:
        date = str(row.get("date") or "")
        value = finite_number(row.get("value"))
        if value is None:
            continue
        if value >= peak_value:
            if active is not None:
                active["recoveryDate"] = date
                active["status"] = "recovered"
                active["calendarDaysToRecovery"] = _iso_days(active["peakDate"], date)
                episodes.append(active)
                active = None
            peak_value = value
            peak_date = date
        drawdown = value / peak_value - 1.0
        point = {"date": date, "drawdown": drawdown, "peakDate": peak_date}
        points.append(point)
        if drawdown < 0:
            if active is None:
                active = {
                    "peakDate": peak_date,
                    "troughDate": date,
                    "recoveryDate": None,
                    "maxDrawdown": drawdown,
                    "status": "unrecovered",
                    "underwaterTradingDays": 0,
                }
            active["underwaterTradingDays"] += 1
            if drawdown < active["maxDrawdown"]:
                active["maxDrawdown"] = drawdown
                active["troughDate"] = date
    if active is not None:
        active["calendarDaysToRecovery"] = None
        episodes.append(active)
    for episode in episodes:
        episode["calendarDaysToTrough"] = _iso_days(episode["peakDate"], episode["troughDate"])
    return points, episodes


def _unavailable(metrics: dict, reasons: dict[str, str], name: str, reason: str) -> None:
    metrics[name] = None
    reasons[name] = reason


def portfolio_metrics(
    values: list[dict],
    benchmark_values: list[dict] | None = None,
    *,
    risk_free_rate_annual: float = RISK_FREE_RATE_ANNUAL,
) -> dict:
    """Calculate research metrics with each undefined value explained.

    Returns based on arithmetic daily means deliberately retain the historical
    metric scale.  CAGR is separately labelled and is never substituted into
    Sharpe or alpha.
    """
    metrics: dict[str, Any] = {}
    unavailable: dict[str, str] = {}
    if len(values) < 2:
        for name in ("totalReturn", "cagr", "annualizedReturn", "volatility", "sharpe", "sortino"):
            _unavailable(metrics, unavailable, name, "portfolio_requires_at_least_two_valid_observations")
        metrics["observations"] = len(values)
        metrics["days"] = 0
        metrics["metricUnavailableReasons"] = unavailable
        return metrics

    start_value = finite_number(values[0].get("value"))
    end_value = finite_number(values[-1].get("value"))
    days = _iso_days(values[0].get("date"), values[-1].get("date"))
    metrics.update({"startValue": start_value, "endValue": end_value, "days": max(days or 0, 0), "observations": len(values)})
    total = portfolio_return(values)
    if total is None:
        _unavailable(metrics, unavailable, "totalReturn", "portfolio_start_or_end_value_unavailable")
    else:
        metrics["totalReturn"] = total
    if total is None or days is None or days <= 0 or start_value is None or end_value is None or end_value <= 0:
        _unavailable(metrics, unavailable, "cagr", "cagr_requires_positive_start_end_values_and_positive_calendar_span")
    else:
        try:
            metrics["cagr"] = (end_value / start_value) ** (365.25 / days) - 1.0
            if not math.isfinite(metrics["cagr"]):
                raise OverflowError
        except (OverflowError, ValueError, ZeroDivisionError):
            _unavailable(metrics, unavailable, "cagr", "cagr_overflow_or_domain_error_for_observed_values")

    returns = [row["return"] for row in daily_returns(values)]
    if not returns:
        for name in ("annualizedReturn", "volatility", "downsideVolatility", "sharpe", "sortino"):
            _unavailable(metrics, unavailable, name, "metric_requires_daily_returns")
    else:
        average = sum(returns) / len(returns)
        metrics["annualizedReturn"] = average * TRADING_DAYS_PER_YEAR
        variance = sample_variance(returns)
        if variance is None:
            _unavailable(metrics, unavailable, "volatility", "volatility_requires_at_least_two_daily_returns")
        else:
            metrics["volatility"] = math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)
        daily_rf = (1.0 + risk_free_rate_annual) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
        excess = [value - daily_rf for value in returns]
        excess_average = sum(excess) / len(excess)
        volatility = metrics.get("volatility")
        if volatility in (None, 0):
            _unavailable(metrics, unavailable, "sharpe", "sharpe_requires_nonzero_sample_daily_volatility")
        else:
            metrics["sharpe"] = excess_average * TRADING_DAYS_PER_YEAR / volatility
        downside = [min(0.0, value - daily_rf) for value in returns]
        downside_variance = sum(value**2 for value in downside) / len(downside) if downside else None
        if downside_variance is None:
            _unavailable(metrics, unavailable, "downsideVolatility", "downside_volatility_requires_daily_returns")
            _unavailable(metrics, unavailable, "sortino", "sortino_requires_nonzero_downside_volatility")
        else:
            downside_vol = math.sqrt(downside_variance) * math.sqrt(TRADING_DAYS_PER_YEAR)
            metrics["downsideVolatility"] = downside_vol
            if downside_vol == 0:
                _unavailable(metrics, unavailable, "sortino", "sortino_requires_nonzero_downside_volatility")
            else:
                metrics["sortino"] = excess_average * TRADING_DAYS_PER_YEAR / downside_vol

    drawdown_points, episodes = drawdown_analysis(values)
    drawdowns = [row["drawdown"] for row in drawdown_points]
    metrics["maxDrawdown"] = min(drawdowns) if drawdowns else None
    metrics["averageDrawdown"] = (sum(value for value in drawdowns if value < 0) / sum(1 for value in drawdowns if value < 0)) if any(value < 0 for value in drawdowns) else 0.0
    metrics["maxDrawdownDays"] = max((row["underwaterTradingDays"] for row in episodes), default=0)
    if metrics.get("cagr") is None or metrics.get("maxDrawdown") in (None, 0):
        _unavailable(metrics, unavailable, "calmar", "calmar_requires_cagr_and_nonzero_max_drawdown")
    else:
        metrics["calmar"] = metrics["cagr"] / abs(metrics["maxDrawdown"])

    # Benchmark values must already be trimmed to precisely the comparable
    # portfolio dates by the provider-facing service.
    benchmark_total = portfolio_return(benchmark_values or [])
    if not benchmark_values or len(benchmark_values) < 2:
        for name in ("benchmarkTotalReturn", "excessReturn", "beta", "alpha", "correlation", "rSquared", "trackingError", "informationRatio", "treynor", "upCapture", "downCapture"):
            _unavailable(metrics, unavailable, name, "benchmark_has_no_comparable_two_observation_period")
    else:
        metrics["benchmarkTotalReturn"] = benchmark_total
        comparable_total = portfolio_return(values)
        if comparable_total is None or benchmark_total is None:
            _unavailable(metrics, unavailable, "excessReturn", "comparable_portfolio_or_benchmark_return_unavailable")
        else:
            metrics["excessReturn"] = comparable_total - benchmark_total
        p_returns = [row["return"] for row in daily_returns(values)]
        b_returns = [row["return"] for row in daily_returns(benchmark_values)]
        pairs = [(p, b) for p, b in zip(p_returns, b_returns) if p is not None and b is not None]
        if len(pairs) < 2:
            for name in ("beta", "alpha", "correlation", "rSquared", "trackingError", "informationRatio", "treynor", "upCapture", "downCapture"):
                _unavailable(metrics, unavailable, name, "benchmark_metric_requires_at_least_two_aligned_daily_return_pairs")
        else:
            p, b = zip(*pairs)
            covariance = sample_covariance(list(p), list(b))
            benchmark_variance = sample_variance(list(b))
            portfolio_variance = sample_variance(list(p))
            beta = covariance / benchmark_variance if covariance is not None and benchmark_variance not in (None, 0) else None
            if beta is None:
                _unavailable(metrics, unavailable, "beta", "beta_requires_nonzero_sample_benchmark_variance")
                _unavailable(metrics, unavailable, "alpha", "alpha_requires_defined_beta")
                _unavailable(metrics, unavailable, "treynor", "treynor_requires_defined_nonzero_beta")
            else:
                metrics["beta"] = beta
                daily_rf = (1.0 + risk_free_rate_annual) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
                metrics["alpha"] = (sum(p) / len(p) - daily_rf) * TRADING_DAYS_PER_YEAR - beta * (sum(b) / len(b) - daily_rf) * TRADING_DAYS_PER_YEAR
                metrics["treynor"] = ((sum(p) / len(p) - daily_rf) * TRADING_DAYS_PER_YEAR / beta) if beta != 0 else None
                if beta == 0:
                    unavailable["treynor"] = "treynor_requires_nonzero_beta"
            correlation = covariance / math.sqrt(portfolio_variance * benchmark_variance) if covariance is not None and portfolio_variance not in (None, 0) and benchmark_variance not in (None, 0) else None
            if correlation is None:
                _unavailable(metrics, unavailable, "correlation", "correlation_requires_nonzero_sample_portfolio_and_benchmark_variance")
                _unavailable(metrics, unavailable, "rSquared", "r_squared_requires_defined_correlation")
            else:
                metrics["correlation"] = correlation
                metrics["rSquared"] = correlation**2
            active = [left - right for left, right in pairs]
            tracking_variance = sample_variance(active)
            tracking_error = math.sqrt(tracking_variance) * math.sqrt(TRADING_DAYS_PER_YEAR) if tracking_variance is not None else None
            if tracking_error is None:
                _unavailable(metrics, unavailable, "trackingError", "tracking_error_requires_at_least_two_aligned_active_returns")
                _unavailable(metrics, unavailable, "informationRatio", "information_ratio_requires_nonzero_tracking_error")
            else:
                metrics["trackingError"] = tracking_error
                if tracking_error == 0:
                    _unavailable(metrics, unavailable, "informationRatio", "information_ratio_requires_nonzero_tracking_error")
                else:
                    metrics["informationRatio"] = (sum(active) / len(active)) * TRADING_DAYS_PER_YEAR / tracking_error
            up = [(left, right) for left, right in pairs if right > 0]
            down = [(left, right) for left, right in pairs if right < 0]
            metrics["upCapture"] = sum(left for left, _ in up) / sum(right for _, right in up) if up and sum(right for _, right in up) else None
            metrics["downCapture"] = sum(left for left, _ in down) / sum(right for _, right in down) if down and sum(right for _, right in down) else None
            if metrics["upCapture"] is None:
                unavailable["upCapture"] = "up_capture_requires_positive_benchmark_return_days"
            if metrics["downCapture"] is None:
                unavailable["downCapture"] = "down_capture_requires_negative_benchmark_return_days"

    metrics["metricAssumptions"] = {
        "tradingDaysPerYear": TRADING_DAYS_PER_YEAR,
        "riskFreeRateAnnual": risk_free_rate_annual,
        "riskFreeRateSource": "fixed_assumption",
        "volatilityMethod": "sample_standard_deviation_of_daily_returns_annualized",
        "sharpeMethod": "arithmetic_mean_daily_excess_return_annualized_over_sample_volatility",
        "alphaMethod": "arithmetic_annualized_capm_excess_return",
    }
    metrics["metricUnavailableReasons"] = unavailable
    return metrics


def deterministic_interpretation(result: dict) -> dict:
    """Make non-advisory, numeric-only statements from a completed result."""
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    contributions = result.get("assetContributions") if isinstance(result.get("assetContributions"), list) else []
    risk = result.get("riskContributions") if isinstance(result.get("riskContributions"), list) else []
    episodes = result.get("drawdownEpisodes") if isinstance(result.get("drawdownEpisodes"), list) else []
    rolling = result.get("rollingMetrics") if isinstance(result.get("rollingMetrics"), list) else []
    statements: list[dict] = []
    usable_contributions = [row for row in contributions if finite_number(row.get("contribution")) is not None]
    top = max(usable_contributions, key=lambda row: abs(finite_number(row.get("contribution")) or 0.0), default=None)
    statements.append({
        "topic": "return_driver",
        "status": "available" if top else "unavailable",
        "facts": {"ticker": top.get("ticker"), "contribution": top.get("contribution"), "method": result.get("contributionMethod")} if top else {},
        "text": f"{top.get('ticker')}의 기간 기여도는 {top.get('contribution') * 100:.2f}%p입니다." if top else "공통 시뮬레이션 증분이 부족해 수익 기여도를 계산할 수 없습니다.",
    })
    worst = min(episodes, key=lambda row: row.get("maxDrawdown", 0)) if episodes else None
    statements.append({
        "topic": "worst_loss",
        "status": "available" if worst else "unavailable",
        "facts": dict(worst) if worst else {},
        "text": f"가장 깊은 낙폭은 {worst.get('troughDate')}에 {worst.get('maxDrawdown') * 100:.2f}%였습니다." if worst else "관측 기간에 하락 구간이 없거나 낙폭을 계산할 수 없습니다.",
    })
    usable_risk = [row for row in risk if finite_number(row.get("volatilityShare")) is not None]
    concentrated = max(usable_risk, key=lambda row: abs(finite_number(row.get("volatilityShare")) or 0.0), default=None)
    statements.append({
        "topic": "risk_concentration",
        "status": "available" if concentrated else "unavailable",
        "facts": {"ticker": concentrated.get("ticker"), "volatilityShare": concentrated.get("volatilityShare"), "method": result.get("riskContributionMethod")} if concentrated else {},
        "text": f"정적 목표비중 공분산 근사에서 {concentrated.get('ticker')}의 변동성 기여 비중은 {concentrated.get('volatilityShare') * 100:.2f}%입니다." if concentrated else "공분산 표본이 부족해 위험 집중도를 계산할 수 없습니다.",
    })
    excess = finite_number(metrics.get("excessReturn"))
    portfolio_volatility = finite_number(metrics.get("benchmarkComparablePortfolioVolatility"))
    benchmark_volatility = finite_number(metrics.get("benchmarkComparableVolatility"))
    portfolio_drawdown = finite_number(metrics.get("benchmarkComparablePortfolioMaxDrawdown"))
    benchmark_drawdown = finite_number(metrics.get("benchmarkComparableMaxDrawdown"))
    portfolio_sharpe = finite_number(metrics.get("benchmarkComparablePortfolioSharpe"))
    benchmark_sharpe = finite_number(metrics.get("benchmarkComparableSharpe"))
    risk_facts = {
        "portfolioVolatility": portfolio_volatility, "benchmarkVolatility": benchmark_volatility,
        "volatilityDifference": (portfolio_volatility - benchmark_volatility) if portfolio_volatility is not None and benchmark_volatility is not None else None,
        "portfolioMaxDrawdown": portfolio_drawdown, "benchmarkMaxDrawdown": benchmark_drawdown,
        "portfolioSharpe": portfolio_sharpe, "benchmarkSharpe": benchmark_sharpe,
    }
    if excess is not None and portfolio_volatility is not None and benchmark_volatility is not None:
        volatility_text = f"변동성은 포트폴리오 {portfolio_volatility * 100:.2f}%, 벤치마크 {benchmark_volatility * 100:.2f}%로 {((portfolio_volatility - benchmark_volatility) * 100):+.2f}%p 차이입니다"
        drawdown_text = f", 최대 낙폭은 포트폴리오 {portfolio_drawdown * 100:.2f}%, 벤치마크 {benchmark_drawdown * 100:.2f}%입니다" if portfolio_drawdown is not None and benchmark_drawdown is not None else ""
        benchmark_text = f"비교 가능 기간의 벤치마크 대비 수익률 차이는 {excess * 100:.2f}%p입니다. {volatility_text}{drawdown_text}."
    elif excess is not None:
        benchmark_text = f"비교 가능 기간의 벤치마크 대비 수익률 차이는 {excess * 100:.2f}%p입니다. 위험 지표는 계산할 수 없습니다."
    else:
        benchmark_text = "비교 가능한 벤치마크 기간이 없어 초과수익을 계산하지 않았습니다."
    statements.append({
        "topic": "benchmark_tradeoff",
        "status": "available" if excess is not None else "unavailable",
        "facts": {"excessReturn": excess, **risk_facts, "comparison": result.get("benchmarkComparison")} if excess is not None else {"reason": metrics.get("metricUnavailableReasons", {}).get("excessReturn")},
        "text": benchmark_text,
    })
    latest = rolling[-1] if rolling else None
    overall = finite_number(metrics.get("totalReturn"))
    statements.append({
        "topic": "rolling_vs_overall",
        "status": "available" if latest and overall is not None and finite_number(latest.get("rollingReturn")) is not None else "unavailable",
        "facts": {"rollingReturn": latest.get("rollingReturn"), "overallCagr": metrics.get("cagr"), "window": latest.get("window"), "comparisonMethod": "recent_window_return_vs_full_period_cagr_different_horizons"} if latest and finite_number(metrics.get("cagr")) is not None else {},
        "text": f"최근 {latest.get('window')}거래일 수익률은 {latest.get('rollingReturn') * 100:.2f}%이고, 전체 기간 CAGR은 {metrics.get('cagr') * 100:.2f}%입니다. 기간 길이가 달라 직접 우열 비교가 아닙니다." if latest and finite_number(latest.get("rollingReturn")) is not None and finite_number(metrics.get("cagr")) is not None else "rolling 기간을 채울 관측치가 부족해 전체 기간과 비교하지 않았습니다.",
    })
    return {"method": "rules_v1_numeric_facts_only", "isAdvice": False, "statements": statements}
