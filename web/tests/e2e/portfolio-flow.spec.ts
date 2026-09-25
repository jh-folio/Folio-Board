import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const exactQuantity = "0.1000000000000000000000000001";
const initialPositions = [
  { id: "aapl", ticker: "AAPL", name: "Apple", quantity: "0.1", averagePrice: "120", currency: "USD", market: "US" },
  { id: "spy", ticker: "SPY", name: "SPDR S&P 500", quantity: "1.5", averagePrice: "400", currency: "USD", market: "US" },
];
const presets = [{ id: "core", name: "장기 핵심", revision: 2, baseCurrency: "USD", positions: [{ ticker: "AAPL", weight: .4 }, { ticker: "SPY", weight: .6 }] }];
const initialReview: any = {
  date: "2026-09-04", reviewRevision: 3, reviewState: "draft", summary: "보유 종목의 점검 기한과 반대 근거를 함께 확인하세요.",
  freshness: { status: "partial", dueCount: 1, reasons: [] }, inputBasis: { status: "partial", capturedAt: "2026-09-04T06:00:00Z", canonicalReports: [{ kind: "briefing", id: "2026-09-03.us", asOf: "2026-09-03" }] },
  positionReviews: [{ ticker: "AAPL", name: "Apple", thesisVerdict: "weakened", reviewReasons: ["checkpoint_due"], quantitativeRiskSignals: [{ kind: "position_weight", weight: 20 / 770, baseCurrency: "USD" }], counterEvidence: [{ title: "수요 둔화 근거" }], dueCheckpoints: [{ label: "실적 발표 확인", dueAt: "2026-09-05" }] }],
  changesSincePrevious: [{ kind: "verdict", key: "AAPL", change: "changed", from: "maintained", to: "weakened" }],
  sharedExposures: [{ type: "narrative", key: "growth", label: "성장 기대", tickers: ["AAPL", "SPY"] }], portfolioRisks: [{ riskKey: "portfolio_concentration", concentration: { top1: .974, top3: 1, holdings: 2 } }],
  counterEvidence: [{ title: "공통 반대 근거를 확인해야 합니다" }], uncertainties: [{ code: "market_data_partial" }], staleReasons: [],
};

async function fixture(page: Page, theme = "light", options: { empty?: boolean; partial?: boolean; portfolioError?: boolean; conflict?: boolean; failSave?: boolean; failAnalytics?: boolean; presetCount?: number } = {}) {
  const calls: { path: string; method: string; body: any }[] = [];
  let portfolio: any = { schemaVersion: 3, revision: 4, positions: options.empty ? [] : structuredClone(initialPositions), cash: [{ currency: "USD", amount: 50 }], updatedAt: "2026-09-04T06:00:00Z" };
  let review = options.empty ? { ...initialReview, reviewRevision: 0, positionReviews: [] } : structuredClone(initialReview);
  let saveCount = 0;
  await page.route("**/*", async route => {
    const req = route.request(); const url = new URL(req.url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const body = req.postData() ? req.postDataJSON() : null;
    calls.push({ path: url.pathname, method: req.method(), body });
    const send = (value: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
    if (url.pathname === "/api/portfolio") {
      if (options.portfolioError) return send({ detail: "보유 내역 읽기 실패" }, 500);
      if (req.method() === "POST") {
        saveCount++;
        if (options.failSave) return send({ detail: "저장 실패" }, 500);
        if (options.conflict && saveCount === 1) { portfolio = { ...portfolio, revision: 5 }; return send({ detail: { code: "portfolio_revision_conflict", latest: portfolio } }, 409); }
        portfolio = { ...portfolio, positions: body.positions, cash: body.cash, revision: portfolio.revision + 1 };
      }
      return send(portfolio);
    }
    if (url.pathname === "/api/portfolio/analytics") {
      if (options.failAnalytics) return send({ detail: "시세 조회 실패" }, 503);
      const rows = portfolio.positions.map((row: any, index: number) => ({ ...row, currentPrice: options.partial && index === 0 ? null : index === 0 ? 200 : 500, marketValueUsd: options.partial && index === 0 ? null : index === 0 ? 20 : 750, costUsd: index === 0 ? 12 : 600, pnlUsd: options.partial && index === 0 ? null : index === 0 ? 8 : 150, pnlPct: index === 0 ? 2 / 3 : .25, weight: index === 0 ? 20 / 770 : 750 / 770, quoteOk: !(options.partial && index === 0), quoteError: options.partial && index === 0 ? "quote_unavailable" : undefined }));
      const slices = rows.length ? [{ label: "미국", marketValue: 770, cost: 612, pnl: 158, pnlPct: 158 / 612, weight: 1, positions: 2 }] : [];
      return send({ positions: rows, cash: portfolio.cash, summary: [{ currency: "USD", marketValue: rows.length ? 770 : 0, cost: 612, pnl: 158, pnlPct: 158 / 612, positions: rows.length }], baseCurrency: "USD", fxRates: { USD: { rateToUsd: 1, source: "identity" } }, updatedAt: portfolio.updatedAt,
        analytics: { baseCurrency: "USD", totalMarketValue: rows.length ? 770 : 0, totalCost: rows.length ? 612 : 0, totalPnl: rows.length ? 158 : 0, totalPnlPct: rows.length ? 158 / 612 : 0, positionWeights: rows, pnlContributors: rows, marketWeights: slices, sectorWeights: slices, currencyWeights: slices, assetClassWeights: slices, concentration: { holdings: rows.length, top1: rows.length ? 750 / 770 : 0, top3: rows.length ? 1 : 0, top5: rows.length ? 1 : 0 }, comments: rows.length ? [{ level: "warn", title: "한 종목 집중", body: "SPY 비중이 높습니다. 분산 상태를 확인하세요." }] : [], targetWeights: { hasTargets: false, targetTotal: 0, targetGap: 0, items: [] } } });
    }
    if (url.pathname === "/api/portfolio/presets") return send((options.empty ? [] : presets).slice(0, options.presetCount ?? 1));
    if (url.pathname === "/api/portfolio/backtests") return send([]);
    if (url.pathname === "/api/investment-review/history") return send({ items: review.reviewRevision ? [review] : [] });
    if (url.pathname === "/api/investment-review") return send(review);
    if (url.pathname === "/api/investment-review/generate") { review = { ...review, reviewRevision: review.reviewRevision + 1 }; return send(review); }
    if (url.pathname.endsWith("/reviewed")) { review = { ...review, reviewState: "reviewed", reviewedAt: "2026-09-04T07:00:00Z" }; return send(review); }
    if (url.pathname === "/api/portfolio/toss/accounts") return send({ detail: { code: "toss_not_enabled", message: "Toss 연동 설정이 필요합니다" } }, 400);
    if (url.pathname === "/api/agent/threads" && req.method() === "POST") return send({ id: "u4-fixture-thread", title: "포트폴리오 대화", scope: body.scope, messages: [] });
    if (url.pathname === "/api/agent/threads/u4-fixture-thread") return send({ id: "u4-fixture-thread", title: "포트폴리오 대화", messages: [] });
    if (url.pathname === "/api/watchlist") return send({ items: [{ ticker: "AAPL", name: "Apple", market: "US" }], watchlist: ["AAPL"] });
    if (url.pathname === "/api/watchlist/overview") return send({ items: [{ ticker: "AAPL", name: "Apple", market: "US", newsCount: 0 }] });
    return send({ detail: "isolated fixture" }, 404);
  });
  await page.addInitScript(selected => { localStorage.setItem("folio.themePreference.v1", selected); localStorage.setItem("folio.react.agentClosed", "1"); }, theme);
  await page.goto("/#/portfolio", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "현재 보유 종목" })).toBeVisible();
  return calls;
}

const writes = (calls: { path: string; method: string }[]) => calls.filter(call => call.method !== "GET");

for (const theme of ["light", "dark"]) {
  test(`U4 saved overview and content-first review ${theme}`, async ({ page }, info) => {
    const calls = await fixture(page, theme);
    const suffix = `${info.project.name.includes("mobile") ? "mobile" : "desktop"}-${theme}`;
    const saved = page.getByRole("table", { name: "저장된 보유 종목" });
    await expect(saved).toBeVisible();
    await expect(saved).toContainText("0.1");
    if (!info.project.name.includes("mobile")) {
      const columns = await saved.locator("thead th").evaluateAll(nodes => nodes.map(node => ({ left: node.getBoundingClientRect().left, width: node.getBoundingClientRect().width })));
      const cells = await saved.locator("tbody tr").first().locator("th, td").evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().left));
      expect(cells).toHaveLength(columns.length);
      cells.forEach((left, index) => expect(Math.abs(left - columns[index].left)).toBeLessThanOrEqual(1));
    }
    await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveCount(0);
    expect(calls.some(call => call.path.includes("/toss/"))).toBe(false);
    expect(writes(calls)).toEqual([]);
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/after-holdings-viewport-${suffix}.png` });
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/after-holdings-${suffix}.png`, fullPage: true });
    await saved.screenshot({ path: `../.planning/portfolio-u4-flow/after-saved-table-${suffix}.png` });
    await page.getByRole("button", { name: "보유 편집", exact: true }).click();
    await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue("0.1");
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/after-editor-${suffix}.png`, fullPage: true });
    await page.locator(".portfolio-holdings-table-wrap").screenshot({ path: `../.planning/portfolio-u4-flow/after-editor-fields-${suffix}.png` });
    const editorAxe = await new AxeBuilder({ page }).include(".portfolio-holdings").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(editorAxe.violations.filter(item => ["serious", "critical"].includes(item.impact || ""))).toEqual([]);
    await page.getByRole("button", { name: "편집 취소", exact: true }).click();
    await page.getByRole("button", { name: /^투자 리뷰/ }).click();
    const review = page.locator(".investment-review-workspace");
    await expect(review.getByText("공통 반대 근거를 확인해야 합니다", { exact: false })).toBeVisible();
    await expect(review.getByText(/수요 둔화 근거/).first()).toBeVisible();
    expect(await review.evaluate(el => {
      const summary = Array.from(el.querySelectorAll("h3")).find(item => item.textContent === "저장 리뷰 요약")!;
      const action = Array.from(el.querySelectorAll("button")).find(item => item.textContent === "검토 완료")!;
      return Boolean(summary.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING);
    })).toBe(true);
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/after-review-${suffix}.png`, fullPage: true });
    await review.getByRole("heading", { name: "저장 리뷰 요약" }).evaluate(el => el.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/after-review-viewport-${suffix}.png` });
    expect(writes(calls)).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    const axe = await new AxeBuilder({ page }).include(".portfolio-route").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(axe.violations.filter(item => ["serious", "critical"].includes(item.impact || ""))).toEqual([]);
    for (const name of ["오늘 리뷰 갱신", "검토 완료", "이 리뷰의 가장 약한 전제를 찾아줘"]) {
      const action = page.getByRole("button", { name, exact: true });
      await action.focus(); await expect(action).toBeFocused();
      if (info.project.name.includes("mobile")) expect((await action.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    for (const summary of await review.locator("summary").all()) {
      await summary.focus(); await expect(summary).toBeFocused();
      if (info.project.name.includes("mobile")) expect((await summary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });
}

test("U4 explicit draft preserves exact values and cash, then returns to saved view", async ({ page }) => {
  const calls = await fixture(page);
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  const saved = page.getByRole("table", { name: "저장된 보유 종목" });
  if (await saved.count()) await expect(saved).not.toContainText(exactQuantity);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect(page.getByRole("table", { name: "저장된 보유 종목" })).toContainText(exactQuantity);
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveCount(0);
  expect(writes(calls).filter(call => call.path === "/api/portfolio")).toHaveLength(1);
  expect(calls.find(call => call.method === "POST" && call.path === "/api/portfolio")!.body).toMatchObject({ expectedRevision: 4, cash: [{ currency: "USD", amount: 50 }], positions: [{ ...initialPositions[0], quantity: exactQuantity }, initialPositions[1]] });
});

test("U4 conflict keeps draft and cannot silently overwrite newer holdings", async ({ page }) => {
  const calls = await fixture(page, "dark", { conflict: true });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue(exactQuantity);
  const save = page.getByRole("button", { name: "Portfolio 저장", exact: true });
  if (await save.isEnabled()) await save.click();
  expect(writes(calls).filter(call => call.path === "/api/portfolio")).toHaveLength(1);
});

test("U4 failed save keeps draft and denied tab navigation preserves editor", async ({ page }) => {
  const calls = await fixture(page, "light", { failSave: true });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: /^투자 리뷰/ }).click();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue(exactQuantity);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue(exactQuantity);
  expect(writes(calls).filter(call => call.path === "/api/portfolio")).toHaveLength(1);
});

test("U4 pending save freezes editor, import and tab navigation", async ({ page }) => {
  await fixture(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/portfolio", async route => {
    if (route.request().method() !== "POST") return route.fallback();
    await pending;
    return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"fixture delayed save"}' });
  });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toBeDisabled();
  for (const name of ["종목 추가", "편집 취소"]) await expect(page.getByRole("button", { name, exact: true })).toBeDisabled();
  const toss = page.getByRole("button", { name: "Toss 계좌 불러오기", exact: true });
  if (await toss.count()) await expect(toss).toBeDisabled();
  await expect(page.getByRole("button", { name: /^투자 리뷰/ })).toBeDisabled();
  release();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toBeEnabled();
});

test("U4 late company resolution cannot overwrite a newer quantity", async ({ page }) => {
  await fixture(page);
  let release!: () => void; let requested = false;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/company/resolve?*", async route => {
    requested = true; await pending;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "confident", match: { ticker: "NVDA", name: "NVIDIA", market: "US" } }) });
  });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("1번 종목", { exact: true }).fill("NVIDIA");
  await page.getByLabel("NVIDIA 수량", { exact: true }).fill(exactQuantity);
  await expect.poll(() => requested).toBe(true);
  release();
  await expect(page.getByLabel("1번 종목", { exact: true })).toHaveValue("NVDA");
  await expect(page.getByLabel("NVDA 수량", { exact: true })).toHaveValue(exactQuantity);
});

test("U4 review action is mutually exclusive while generation is pending", async ({ page }) => {
  await fixture(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/investment-review/generate", async route => { await pending; return route.fulfill({ contentType: "application/json", body: JSON.stringify(initialReview) }); });
  await page.getByRole("button", { name: /^투자 리뷰/ }).click();
  await page.getByRole("button", { name: "오늘 리뷰 갱신", exact: true }).click();
  await expect(page.getByRole("button", { name: "검토 완료", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "이 리뷰의 가장 약한 전제를 찾아줘", exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole("button", { name: "오늘 리뷰 갱신", exact: true })).toBeEnabled();
});

test("U4 analytics failure leaves saved authority readable and does not invent valuation", async ({ page }) => {
  const calls = await fixture(page, "dark", { failAnalytics: true });
  const table = page.getByRole("table", { name: "저장된 보유 종목" });
  await expect(table).toBeVisible();
  await expect(table).toContainText("0.1");
  await expect(table).toContainText("120");
  await expect(page.getByRole("alert").first()).toBeVisible();
  expect(writes(calls)).toEqual([]);
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue("0.1");
});

test("U4 failed initial authority load cannot authorize save or import", async ({ page }) => {
  const calls = await fixture(page, "light", { portfolioError: true });
  await expect(page.getByRole("alert").first()).toBeVisible();
  const toss = page.getByRole("button", { name: "Toss 계좌 불러오기", exact: true });
  if (await toss.count()) await expect(toss).toBeDisabled();
  const edit = page.getByRole("button", { name: "보유 편집", exact: true });
  if (await edit.count()) await expect(edit).toBeDisabled();
  expect(writes(calls)).toEqual([]);
  expect(calls.some(call => call.path.includes("/toss/"))).toBe(false);
});

test("U4 resolver completion after deletion cannot resurrect the deleted row", async ({ page }) => {
  await fixture(page);
  let release!: () => void; let requested = false;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/company/resolve?*", async route => { requested = true; await pending; await route.fulfill({ contentType: "application/json", body: JSON.stringify({ status: "confident", match: { ticker: "NVDA", name: "NVIDIA", market: "US" } }) }); });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("1번 종목", { exact: true }).fill("NVIDIA");
  await page.getByLabel("NVIDIA 수량", { exact: true }).focus();
  await expect.poll(() => requested).toBe(true);
  await page.locator(".portfolio-holdings-table tbody tr").first().getByRole("button", { name: "삭제" }).click();
  release();
  await expect(page.getByLabel("1번 종목", { exact: true })).toHaveValue("SPY");
  await expect(page.getByLabel("SPY 수량", { exact: true })).toHaveValue("1.5");
  await expect(page.locator(".portfolio-holdings-table tbody tr")).toHaveCount(1);
});

test("U4 dirty editor protects browser unload and cancel removes only the draft", async ({ page }) => {
  const calls = await fixture(page);
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  const prevented = () => page.evaluate(() => { const event = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(event); return event.defaultPrevented; });
  expect(await prevented()).toBe(true);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "편집 취소", exact: true }).click();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveCount(0);
  expect(await prevented()).toBe(false);
  await expect(page.getByRole("table", { name: "저장된 보유 종목" })).not.toContainText(exactQuantity);
  expect(writes(calls)).toEqual([]);
});

test("U4 pending account lookup prevents starting an editor without saving", async ({ page }) => {
  const calls = await fixture(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/portfolio/toss/accounts", async route => { await pending; return route.fulfill({ contentType: "application/json", body: JSON.stringify({ provider: "toss_open_api", accounts: [] }) }); });
  await page.getByRole("button", { name: "Toss 계좌 불러오기", exact: true }).click();
  await expect(page.getByRole("button", { name: "보유 편집", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^투자 리뷰/ })).toBeDisabled();
  release();
  await expect(page.getByRole("button", { name: "Toss 계좌 불러오기", exact: true })).toBeEnabled();
  await expect(page.getByRole("table", { name: "저장된 보유 종목" })).toContainText("0.1");
  expect(writes(calls)).toEqual([]);
});

test("U4 conversation scope uses saved holdings instead of the draft", async ({ page }) => {
  const calls = await fixture(page);
  await page.evaluate(() => { window.addEventListener("folio:open-agent-thread", event => { (window as any).__u4Scope = (event as CustomEvent).detail.scope; }); });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("1번 종목", { exact: true }).fill("UNSAVED");
  await page.getByRole("button", { name: "포트폴리오 짚어보기", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__u4Scope)).toEqual({ kind: "portfolio", id: "current", tickers: ["AAPL", "SPY"] });
  expect(writes(calls).filter(call => call.path === "/api/portfolio")).toEqual([]);
});

test("U4 narrow editor and long exact saved values do not need horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await fixture(page);
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  const average = `0.${"1234567890".repeat(8)}`;
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  await page.getByLabel("AAPL 평균단가", { exact: true }).fill(average);
  expect(await page.locator(".portfolio-holdings-table-wrap").evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  for (const input of await page.locator(".portfolio-holdings-table input").all()) expect((await input.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  const table = page.getByRole("table", { name: "저장된 보유 종목" });
  await expect(table).toContainText(average);
  await expect(table).toContainText(exactQuantity);
  expect(await page.locator(".portfolio-holdings-table-wrap").evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  for (const cell of await table.locator("tbody td").all()) expect(await cell.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
});

test("U4 partial quote is visible as missing information, not an unexplained dash", async ({ page }) => {
  await fixture(page, "dark", { partial: true });
  await expect(page.locator(".portfolio-analysis")).toContainText(/시세.*(일부|확인|불가|누락)|일부.*시세/);
  const row = page.getByRole("table", { name: "저장된 보유 종목" }).locator("tbody tr").first();
  await expect(row).toContainText(/시세.*(확인|불가|누락)/);
  await expect(row).toContainText("0.1");
});

test("U4 successful authority retry clears the old failure", async ({ page }) => {
  await fixture(page, "light", { portfolioError: true });
  await expect(page.getByRole("alert").first()).toBeVisible();
  await page.route("**/api/portfolio", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ revision: 4, positions: initialPositions, cash: [] }) }));
  await page.getByRole("button", { name: /다시 (시도|불러오기)/ }).click();
  await expect(page.getByRole("button", { name: "보유 편집", exact: true })).toBeEnabled();
  await expect(page.locator(".portfolio-holdings").getByRole("alert")).toHaveCount(0);
});

test("U4 explicit conflict reload locks draft until latest authority is ready", async ({ page }) => {
  const calls = await fixture(page, "light", { conflict: true });
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(exactQuantity);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "최신 저장본 불러오기", exact: true })).toBeVisible();
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/portfolio", async route => { if (route.request().method() !== "GET") return route.fallback(); await pending; return route.fulfill({ contentType: "application/json", body: JSON.stringify({ revision: 5, positions: initialPositions, cash: [{ currency: "USD", amount: 50 }] }) }); });
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "최신 저장본 불러오기", exact: true }).click();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: /^투자 리뷰/ })).toBeDisabled();
  release();
  await expect(page.getByRole("button", { name: "보유 편집", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill("0.2");
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect.poll(() => calls.filter(call => call.path === "/api/portfolio" && call.method === "POST").map(call => call.body.expectedRevision)).toEqual([4, 5]);
});

for (const theme of ["light", "dark"]) {
  test(`U4 empty tabs offer prerequisites without writing ${theme}`, async ({ page }, info) => {
    const calls = await fixture(page, theme, { empty: true });
    await page.getByRole("button", { name: /^투자 리뷰/ }).click();
    await page.getByRole("button", { name: "보유·평가로 가기", exact: true }).click();
    await expect(page.getByRole("heading", { name: "현재 보유 종목" })).toBeVisible();
    await page.getByRole("button", { name: "백테스트", exact: true }).click();
    await page.getByRole("button", { name: "프리셋으로 가기", exact: true }).click();
    await expect(page.getByRole("heading", { name: "프리셋", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "새 프리셋", exact: true })).toBeEnabled();
    expect(writes(calls)).toEqual([]);
    expect(calls.some(call => call.path.includes("/toss/"))).toBe(false);
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/empty-presets-${info.project.name}-${theme}.png`, fullPage: true });
  });
}

test("U4 review action placement comparison capture", async ({ page }, info) => {
  test.skip(process.env.U4_LAYOUT_COMPARE !== "1", "Disposable layout experiment, no production styles changed.");
  const calls = await fixture(page, "light");
  await page.getByRole("button", { name: /^투자 리뷰/ }).click();
  const heading = page.getByRole("heading", { name: "저장 리뷰 요약", exact: true });
  await heading.evaluate(el => el.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: `../.planning/portfolio-u4-flow/placement-content-${info.project.name}.png` });
  await page.locator(".investment-review-actions").evaluate(el => {
    const node = el as HTMLElement;
    const rect = node.getBoundingClientRect();
    Object.assign(node.style, { position: "fixed", bottom: "16px", left: `${rect.left}px`, width: `${rect.width}px`, zIndex: "50", background: getComputedStyle(node.closest(".cockpit-panel")!).backgroundColor, padding: "12px" });
  });
  await page.screenshot({ path: `../.planning/portfolio-u4-flow/placement-sticky-${info.project.name}.png` });
  expect(writes(calls)).toEqual([]);
});

for (const theme of ["light", "dark"]) {
  test(`U4 baseline ${theme}`, async ({ page }, info) => {
    test.skip(process.env.U4_BASELINE !== "1", "Baseline capture is opt-in, never overwritten by final acceptance.");
    await fixture(page, theme);
    const suffix = `${info.project.name.includes("mobile") ? "mobile" : "desktop"}-${theme}`;
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/before-holdings-${suffix}.png` });
    await page.getByRole("button", { name: /^투자 리뷰/ }).click();
    await expect(page.getByRole("heading", { name: "저장 리뷰 요약" })).toBeVisible();
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/before-review-${suffix}.png` });
    await page.getByRole("button", { name: "워치리스트", exact: true }).click();
    await expect(page.getByRole("heading", { name: "워치리스트", exact: true })).toBeVisible();
    await page.screenshot({ path: `../.planning/portfolio-u4-flow/adjacent-watchlist-${suffix}.png` });
  });
}
