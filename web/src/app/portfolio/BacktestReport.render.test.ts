import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BacktestComparisonReport } from "./PresetCompare";
import { BacktestResultReport } from "./BacktestReport";
import type { BacktestComparison, BacktestResult } from "./portfolioTypes";

function result(id = "one"): BacktestResult {
  return {
    id, presetName: "장기 핵심", start: "2023-01-03", end: "2024-12-31", baseCurrency: "USD", initialValue: 10000, rebalance: "monthly", benchmark: { ticker: "SPY" },
    analysisVersion: "u3-v1", metrics: { totalReturn: 0.24, cagr: 0.11, maxDrawdown: -0.18, volatility: 0.16, sharpe: 0.46, excessReturn: 0.04, beta: 0.9, metricUnavailableReasons: { alpha: "insufficient_observations" }, metricAssumptions: { volatilityMethod: "sample_daily_return_standard_deviation_annualized", sharpeMethod: "annualized_excess_return_over_volatility", alphaMethod: "capm_rf_zero" } },
    series: [{ date: "2023-01-03", value: 10000 }, { date: "2024-12-31", value: 12400 }], benchmarkSeries: [{ date: "2023-01-03", value: 10000 }, { date: "2024-12-31", value: 12000 }],
    calculationBasis: { riskFreeRate: { annual: 0 }, annualization: { tradingDays: 252 }, returnMethod: "adjusted_close_daily", priceAlignment: { method: "native_price_forward_fill_then_asof_fx_mark_no_reweighting" } },
    benchmarkComparison: { status: "comparable", comparisonStart: "2023-01-03", comparisonEnd: "2024-12-31", observations: 500 }, drawdownSeries: [{ date: "2023-01-03", drawdown: 0 }, { date: "2023-08-01", drawdown: -0.18 }], drawdownEpisodes: [{ peakDate: "2023-04-01", troughDate: "2023-08-01", recoveryDate: null, maxDrawdown: -0.18, status: "unrecovered", underwaterTradingDays: 80, calendarDaysToTrough: 122, calendarDaysToRecovery: null }],
    rollingMetrics: [{ date: "2024-12-31", rollingReturn: 0.08, rollingVolatility: 0.16, rollingBeta: 0.9, window: 252 }], yearlyReturns: [{ period: "2023", return: 0.1, partial: true }], monthlyReturns: [{ period: "2023-01", return: 0.02, partial: true }], assetContributions: [{ ticker: "AAPL", weight: 1, contribution: 0.24 }], riskContributions: [{ ticker: "AAPL", volatilityShare: 1, betaContribution: 0.9 }], contributionMethod: "actual_simulation_increment_over_initial_value", riskContributionMethod: "static_target_weight_sample_covariance_approximation", interpretation: { statements: [{ topic: "return_driver", status: "available", text: "수익률은 24.0%입니다." }] }, dataCoverage: { positions: [], unavailableMetrics: [] }, assumptions: ["세금 제외"],
  };
}

describe("BacktestResultReport", () => {
  it("keeps performance, drawdown, and exact-value controls above progressive details", () => {
    const html = renderToStaticMarkup(createElement(BacktestResultReport, { result: result() }));
    expect(html).toContain("누적 성과"); expect(html).toContain("낙폭"); expect(html).toContain("날짜 선택"); expect(html).toContain("가장 깊은 낙폭"); expect(html).toContain("기간별 수익률·rolling 지표·자료 기준 보기"); expect(html).toContain("부분 기간");
    expect(html.indexOf("누적 성과")).toBeLessThan(html.indexOf("기간별 수익률·rolling 지표·자료 기준 보기"));
  });

  it("does not invent calculation assumptions for legacy saved results", () => {
    const legacy = { ...result(), calculationBasis: undefined, dataCoverage: undefined, drawdownSeries: undefined, drawdownEpisodes: undefined };
    const html = renderToStaticMarkup(createElement(BacktestResultReport, { result: legacy }));
    expect(html).toContain("이전 저장본에는 계산 기준이 기록되지 않았습니다");
  });
});

describe("BacktestComparisonReport", () => {
  it("does not rank results with different actual periods and retains a partial failure", () => {
    const first = result("first"); const second = { ...result("second"), start: "2023-04-01" };
    const comparison: BacktestComparison = { type: "comparison", id: "compare", start: "2023-01-03", end: "2024-12-31", baseCurrency: "USD", initialValue: 10000, rebalance: "monthly", results: [first, second], errors: [{ presetName: "방어", error: "backtest_failed" }] };
    const html = renderToStaticMarkup(createElement(BacktestComparisonReport, { result: comparison }));
    expect(html).toContain("우열과 누적 평가액을 비교하지 않습니다"); expect(html).toContain("방어은 백테스트에 실패했습니다"); expect(html).toContain("Rolling 베타 비교");
  });

  it("does not treat missing or changed calculation bases as comparable", () => {
    const first = result("first");
    const unknown = { ...result("unknown"), analysisVersion: undefined, calculationBasis: undefined };
    const mismatch = { ...result("mismatch"), calculationBasis: { ...result().calculationBasis, riskFreeRate: { annual: 0.02, source: "fixed_assumption", method: "constant_annual" } } };
    for (const second of [unknown, mismatch]) {
      const comparison: BacktestComparison = { type: "comparison", id: `compare-${second.id}`, start: "2023-01-03", end: "2024-12-31", baseCurrency: "USD", initialValue: 10000, rebalance: "monthly", results: [first, second] };
      const html = renderToStaticMarkup(createElement(BacktestComparisonReport, { result: comparison }));
      expect(html).toContain("우열과 누적 평가액을 비교하지 않습니다");
    }
  });
});
