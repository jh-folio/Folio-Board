import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const presets = [
  { id: "core", name: "장기 핵심", baseCurrency: "USD", revision: 2, positions: [{ ticker: "AAPL", weight: .6 }, { ticker: "MSFT", weight: .4 }] },
  { id: "broad", name: "시장 분산", baseCurrency: "USD", revision: 1, positions: [{ ticker: "SPY", weight: 1 }] },
];
const result: any = {
  id: "example", name: "장기 핵심", presetName: "장기 핵심", start: "2023-01-03", end: "2025-12-31", baseCurrency: "USD", initialValue: 10000, rebalance: "monthly",
  benchmark: { ticker: "SPY" }, benchmarkComparison: { status: "comparable", comparisonStart: "2023-01-03", comparisonEnd: "2025-12-31", observations: 5 }, metrics: { totalReturn: .24, cagr: .074, maxDrawdown: -.18, volatility: .16, sharpe: .46, benchmarkTotalReturn: .2, excessReturn: .04 },
  series: [{ date: "2023-01-03", value: 10000 }, { date: "2023-06-01", value: 9000 }, { date: "2024-01-02", value: 11000 }, { date: "2024-06-03", value: 9500 }, { date: "2025-12-31", value: 12400 }],
  benchmarkSeries: [{ date: "2023-01-03", value: 10000 }, { date: "2023-06-01", value: 9800 }, { date: "2024-01-02", value: 10500 }, { date: "2024-06-03", value: 10000 }, { date: "2025-12-31", value: 12000 }],
  assetContributions: [{ ticker: "AAPL", weight: .6, contribution: .16 }, { ticker: "MSFT", weight: .4, contribution: .08 }],
  analysisVersion: "u3-v1", contributionMethod: "actual_simulation_increment_over_initial_value", riskContributionMethod: "static_target_weight_sample_covariance_approximation",
  drawdownSeries: [{ date: "2023-01-03", drawdown: 0 }, { date: "2023-06-01", drawdown: -.1 }, { date: "2024-01-02", drawdown: 0 }, { date: "2024-06-03", drawdown: -.13636 }, { date: "2025-12-31", drawdown: 0 }],
  drawdownEpisodes: [{ peakDate: "2024-01-02", troughDate: "2024-06-03", recoveryDate: "2025-12-31", maxDrawdown: -.13636, status: "recovered", calendarDaysToRecovery: 729, underwaterTradingDays: 1 }],
  yearlyReturns: [{ period: "2023", return: -.1, partial: true }, { period: "2024", return: .05556, partial: false }, { period: "2025", return: .30526, partial: false }],
  monthlyReturns: [{ period: "2023-01", return: null, partial: true }, { period: "2023-06", return: -.1, partial: true }],
  riskContributions: [{ ticker: "AAPL", weight: .6, volatilityShare: .7, volatilityContribution: .112, betaContribution: .6 }, { ticker: "MSFT", weight: .4, volatilityShare: .3, volatilityContribution: .048, betaContribution: .4 }],
  rollingMetrics: [{ date: "2024-01-02", rollingReturn: .1, rollingVolatility: .2, rollingBeta: 1.2, window: 252 }, { date: "2024-06-03", rollingReturn: -.05, rollingVolatility: .15, rollingBeta: .8, window: 252 }, { date: "2025-12-31", rollingReturn: .12, rollingVolatility: .16, rollingBeta: 1.1, window: 252 }],
  calculationBasis: { riskFreeRate: { annual: 0, source: "fixed_assumption" }, annualization: { tradingDays: 252 }, dataAlignment: { commonStart: "2023-01-03", commonEnd: "2025-12-31", observations: 5 } },
  dataCoverage: { positions: [{ ticker: "AAPL", symbol: "AAPL", currency: "USD", actualStart: "2023-01-03", actualEnd: "2025-12-31", simulationStart: "2023-01-03", simulationEnd: "2025-12-31", included: true, unavailableReasons: [], price: { observedDays: 4, forwardFilledDays: 1, trailingForwardFilledDays: 0, coverage: .8 }, fx: { required: false, observedDays: 0, forwardFilledDays: 0, trailingForwardFilledDays: 0, coverage: null } }], benchmark: null, unavailableMetrics: [] },
  interpretation: { method: "rules_v1_numeric_facts_only", isAdvice: false, statements: [{ topic: "return_driver", status: "available", facts: { ticker: "AAPL", contribution: .16 }, text: "AAPL의 누적 손익 기여는 16.0%p입니다." }] },
  sources: [{ ticker: "AAPL", symbol: "AAPL", currency: "USD", source: "fixture", url: "https://example.com/market" }],
  assumptions: ["무위험수익률 연 0% 가정", "세금·수수료·슬리피지 제외", "과거 성과가 미래를 보장하지 않습니다."],
};

async function fixture(page: Page, theme: string, options: { count?: number; legacy?: boolean; short?: boolean; failRun?: boolean; failOpen?: boolean; failSave?: boolean; mismatched?: boolean; endCluster?: boolean } = {}) {
  const calls: { path: string; method: string; body: any }[] = [];
  const payload = structuredClone(result);
  payload.requestedStart = "2020-01-01";
  payload.requestedEnd = "2026-09-04";
  payload.calculationBasis.returnMethod = "adjusted_close_daily";
  payload.calculationBasis.riskFreeRate.method = "constant_annual_zero";
  payload.calculationBasis.priceAlignment = { method: "native_price_forward_fill_then_asof_fx_mark_no_reweighting", simulationStart: payload.start, simulationEnd: payload.end, observations: 5, strictCommonObservedStart: payload.start, strictCommonObservedEnd: payload.end, strictCommonObservedDays: 4 };
  payload.metrics.metricAssumptions = { volatilityMethod: "sample_standard_deviation_of_daily_returns_annualized", sharpeMethod: "arithmetic_mean_daily_excess_return_annualized_over_sample_volatility", alphaMethod: "arithmetic_annualized_capm_excess_return" };
  payload.dataCoverage.benchmark = { ...structuredClone(payload.dataCoverage.positions[0]), ticker: "SPY", symbol: "SPY" };
  if (options.legacy) { delete payload.analysisVersion; delete payload.calculationBasis; delete payload.dataCoverage; delete payload.interpretation; }
  if (options.short) { payload.rollingMetrics = []; payload.metrics.sharpe = null; payload.metrics.alpha = null; payload.metrics.metricUnavailableReasons = { sharpe: "sharpe_requires_nonzero_sample_volatility", alpha: "alpha_requires_defined_beta" }; }
  if (options.endCluster) { payload.series = ["2024-01-01", "2024-12-25", "2024-12-31"].map((date, index) => ({ date, value: 10000 + index * 100 })); payload.benchmarkSeries = []; }
  const comparison = { type: "comparison", id: "compare", name: "비교 저장본", start: result.start, end: result.end, baseCurrency: "USD", initialValue: 10000, rebalance: "monthly", results: [payload, { ...payload, id: "broad-result", presetName: "시장 분산", metrics: { ...payload.metrics, totalReturn: .20 } }], errors: [{ presetId: "missing", presetName: "자료 없는 종목", error: "backtest_failed" }] };
  if (options.mismatched) { comparison.results[1].baseCurrency = "KRW"; comparison.results[1].initialValue = 1000000; }
  let saved: any[] = [{ ...payload, id: "saved", name: "기존 저장본" }, comparison];
  await page.route("**/*", async route => {
    const req = route.request(); const url = new URL(req.url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    calls.push({ path: url.pathname, method: req.method(), body: req.postData() ? req.postDataJSON() : null });
    const send = (body: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/portfolio") return send({ schemaVersion: 3, revision: 4, positions: [], cash: [] });
    if (url.pathname === "/api/portfolio/presets") return send(presets.slice(0, options.count ?? 2));
    const fail = (message: string) => route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: message }) });
    if (url.pathname === "/api/portfolio/backtests") return req.method() === "POST" ? (options.failRun ? fail("가격 자료를 읽지 못했습니다") : send({ ...payload, baseCurrency: req.postDataJSON().baseCurrency || payload.baseCurrency, initialValue: req.postDataJSON().initialValue || payload.initialValue, benchmark: { ticker: req.postDataJSON().benchmark || "SPY" } })) : send(saved.map(row => ({ id: row.id, name: row.name, presetName: row.presetName, type: row.type || "single", start: row.start, end: row.end, baseCurrency: row.baseCurrency, initialValue: row.initialValue, rebalance: row.rebalance, benchmark: row.benchmark, metrics: row.metrics || {}, resultCount: row.results?.length || 1 })));
    if (url.pathname === "/api/portfolio/backtests/compare") return send(comparison);
    if (url.pathname === "/api/portfolio/backtests/save") {
      if (options.failSave) return fail("저장할 수 없습니다");
      const value = req.postDataJSON(); saved = [{ ...value, savedAt: "2026-09-04" }, ...saved]; return send(value);
    }
    if (url.pathname.startsWith("/api/portfolio/backtests/")) {
      if (req.method() === "DELETE") { saved = saved.filter(row => row.id !== url.pathname.split("/").at(-1)); return send({ deleted: true }); }
      return options.failOpen ? fail("저장본을 읽지 못했습니다") : send(url.pathname.endsWith("/compare") ? comparison : { ...payload, id: "saved", presetName: "기존 저장본" });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await page.addInitScript(value => { localStorage.setItem("folio.themePreference.v1", value); localStorage.setItem("folio.react.agentClosed", "1"); }, theme);
  await page.goto("/#/portfolio", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "백테스트", exact: true }).click();
  if (options.count !== 0) await expect(page.getByRole("button", { name: "백테스트 실행", exact: true })).toBeVisible();
  return calls;
}

for (const theme of ["light", "dark"]) {
  test(`backtest capture and accessibility ${theme}`, async ({ page }, info) => {
    await fixture(page, theme);
    await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
    await expect(page.getByRole("button", { name: "결과 저장", exact: true })).toBeVisible();
    await expect(page.locator(".portfolio-backtest-report")).not.toContainText(/undefined|NaN/);
    await page.getByText("기간별 수익률·rolling 지표·자료 기준 보기", { exact: true }).click();
    const suffix = `${info.project.name.includes("mobile") ? "mobile" : "desktop"}-${theme}`;
    await page.locator(".portfolio-backtest").screenshot({ path: `../.planning/portfolio-u3-backtest/after-${suffix}.png` });
    await page.locator(".portfolio-chart").first().screenshot({ path: `../.planning/portfolio-u3-backtest/chart-${suffix}.png` });
    for (const [part, selector] of [["summary", ".portfolio-backtest-result-head"], ["drawdown", ".portfolio-drawdown-summary"], ["coverage", ".portfolio-coverage"]]) {
      await page.locator(selector).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `../.planning/portfolio-u3-backtest/viewport-${part}-${suffix}.png` });
    }
    const findings = await new AxeBuilder({ page }).include(".portfolio-backtest").analyze();
    expect(findings.violations.filter(v => v.impact === "serious" || v.impact === "critical")).toEqual([]);
    expect(await page.locator(".portfolio-backtest").evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  });
}

test("conditions are sent and saved result stays frozen after form changes", async ({ page }) => {
  const calls = await fixture(page, "light");
  await page.getByRole("combobox", { name: "기준 통화", exact: true }).selectOption("KRW");
  await page.getByLabel("초기 금액", { exact: true }).fill("25000");
  await page.getByLabel("벤치마크", { exact: true }).fill("QQQ");
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await expect(page.locator(".portfolio-backtest-result-head")).toContainText("KRW");
  await page.getByLabel("초기 금액", { exact: true }).fill("999");
  await page.getByRole("button", { name: "결과 저장", exact: true }).click();
  await expect.poll(() => calls.filter(c => c.path.endsWith("/save")).length).toBe(1);
  const run = calls.find(c => c.path === "/api/portfolio/backtests" && c.method === "POST")!;
  expect(run.body).toMatchObject({ initialValue: 25000, baseCurrency: "KRW", benchmark: "QQQ" });
  expect(calls.find(c => c.path.endsWith("/save"))!.body).toMatchObject({ initialValue: 25000, baseCurrency: "KRW" });
  expect(calls.filter(c => c.path === "/api/portfolio" && c.method !== "GET")).toHaveLength(0);
});

test("invalid amount never runs", async ({ page }) => {
  const calls = await fixture(page, "light");
  await page.getByLabel("초기 금액", { exact: true }).fill("-1");
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(/초기|금액|0/);
  expect(calls.filter(c => c.path === "/api/portfolio/backtests" && c.method === "POST")).toHaveLength(0);
});

test("run failure shows error without a fabricated result", async ({ page }) => {
  await fixture(page, "dark", { failRun: true });
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("가격 자료");
  await expect(page.locator(".portfolio-backtest-report")).toHaveCount(0);
});

test("saved read failure retains current result", async ({ page }) => {
  await fixture(page, "light", { failOpen: true });
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await expect(page.locator(".portfolio-backtest-result-head")).toBeVisible();
  await page.getByRole("button", { name: /열기.*기존 저장본|기존 저장본.*열기/ }).click();
  await expect(page.getByRole("alert")).toContainText("저장본을 읽지");
  await expect(page.locator(".portfolio-backtest-result-head")).toContainText("장기 핵심");
});

test("legacy result read never reruns or autosaves", async ({ page }) => {
  const calls = await fixture(page, "dark", { legacy: true });
  await page.getByRole("button", { name: /열기.*기존 저장본|기존 저장본.*열기/ }).click();
  await page.getByText("기간별 수익률·rolling 지표·자료 기준 보기", { exact: true }).click();
  await expect(page.getByText(/이전 저장본에는 계산 기준이 기록되지 않았습니다/)).toBeVisible();
  expect(calls.filter(c => c.method === "POST")).toHaveLength(0);
});

test("saved comparison opens named failures without single-result crash", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: /열기.*비교 저장본|비교 저장본.*열기/ }).click();
  await expect(page.getByText(/자료 없는 종목.*실패|실패.*자료 없는 종목/)).toBeVisible();
  await expect(page.locator(".portfolio-comparison-report").getByText("시장 분산", { exact: true }).first()).toBeVisible();
});

test("five charts expose keyboard values and table data", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await page.getByText("기간별 수익률·rolling 지표·자료 기준 보기", { exact: true }).click();
  for (const title of ["누적 성과", "낙폭", "Rolling 12개월 수익률", "Rolling 변동성", "Rolling 베타"]) {
    const chart = page.locator(".portfolio-chart").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
    await expect(chart).toBeVisible();
    const slider = chart.getByRole("slider");
    await slider.focus(); await slider.press("Home");
    await expect(slider).toHaveValue("0");
    await expect(chart.locator(".portfolio-chart__readout")).not.toContainText("NaN");
    await chart.getByText(/차트 데이터 표 보기/).click();
    await expect(chart.getByRole("table")).toBeVisible();
  }
});

test("short history explains absent rolling and null metrics", async ({ page }) => {
  await fixture(page, "dark", { short: true });
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await expect(page.locator(".portfolio-metrics")).toContainText("계산 불가");
  await page.getByText("기간별 수익률·rolling 지표·자료 기준 보기", { exact: true }).click();
  await expect(page.getByText(/Rolling 수익률 자료가 없습니다/)).toBeVisible();
  await expect(page.locator(".portfolio-backtest-report")).not.toContainText("NaN");
});

test("empty preset state does not hide saved results", async ({ page }) => {
  await fixture(page, "light", { count: 0 });
  await expect(page.getByRole("button", { name: /열기.*기존 저장본|기존 저장본.*열기/ })).toBeVisible();
});

test("save failure preserves unsaved result and reports failure", async ({ page }) => {
  await fixture(page, "dark", { failSave: true });
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await page.getByRole("button", { name: "결과 저장", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("저장할 수 없습니다");
  await expect(page.locator(".portfolio-backtest-result-head")).toContainText("장기 핵심");
});

test("375px and landscape charts remain inside container", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  await page.getByText("기간별 수익률·rolling 지표·자료 기준 보기", { exact: true }).click();
  for (const viewport of [{ width: 375, height: 812 }, { width: 812, height: 375 }]) {
    await page.setViewportSize(viewport);
    await expect.poll(() => page.locator(".portfolio-backtest").evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
    const chart = page.locator(".portfolio-chart").first();
    const outer = await chart.boundingBox(); const svg = await chart.locator("svg").boundingBox();
    expect(svg!.width).toBeLessThanOrEqual(outer!.width + 1);
    const ticks = await chart.locator("svg text").evaluateAll(nodes => nodes.filter(node => Number(node.getAttribute("y")) > 240).map(node => { const box = node.getBoundingClientRect(); return { left: box.left, right: box.right }; }).sort((a, b) => a.left - b.left));
    for (let index = 1; index < ticks.length; index++) expect(ticks[index].left).toBeGreaterThanOrEqual(ticks[index - 1].right);
  }
  // Linux system fonts are wider than Windows/macOS ones; the landscape side
  // column overflowed by 4px only on Ubuntu CI. Widen text to reproduce that here.
  await page.addStyleTag({ content: ".portfolio-backtest, .portfolio-backtest * { letter-spacing: 0.08em !important; }" });
  await page.setViewportSize({ width: 812, height: 375 });
  await expect.poll(() => page.locator(".portfolio-backtest").evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
});

test("different currencies and amounts never produce comparison winners", async ({ page }) => {
  await fixture(page, "light", { mismatched: true });
  await page.getByRole("button", { name: /열기.*비교 저장본|비교 저장본.*열기/ }).click();
  const report = page.locator(".portfolio-comparison-report");
  await expect(report.locator("[data-best=true]")).toHaveCount(0);
  await expect(report).toContainText(/통화|초기 금액/);
  await expect(report.getByRole("heading", { name: "누적 성과 비교", exact: true })).toHaveCount(0);
});

test("end-clustered date ticks do not collide with final tick", async ({ page }) => {
  await fixture(page, "light", { endCluster: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.getByRole("button", { name: "백테스트 실행", exact: true }).click();
  const chart = page.locator(".portfolio-chart").first();
  await expect(chart).toBeVisible();
  const ticks = await chart.locator("svg text").evaluateAll(nodes => nodes.filter(node => Number(node.getAttribute("y")) > 240).map(node => { const box = node.getBoundingClientRect(); return { left: box.left, right: box.right }; }).sort((a, b) => a.left - b.left));
  expect(ticks.length).toBeGreaterThanOrEqual(2);
  for (let index = 1; index < ticks.length; index++) expect(ticks[index].left).toBeGreaterThanOrEqual(ticks[index - 1].right);
});
