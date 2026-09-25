import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const quantity = "0.1000000000000000000000000001";
const average = "12.345678901234567890123456789012";
const tiny = "0.000000000000000000000000000001";

async function fixture(page: Page, theme: "light" | "dark", blocked = false, unavailable = false) {
  const calls: { path: string; body: any }[] = [];
  let portfolio = { schemaVersion: 3, revision: 4, positions: [
    { ticker: "AAPL", quantity: unavailable ? "1e+1000" : "0.1", averagePrice: "12", market: "US", currency: "USD" },
    { ticker: "SPY", quantity: "1.5", averagePrice: "100", market: "US", currency: "USD" },
  ], cash: [{ currency: "USD", amount: 50 }] };
  const details = [{ positionKey: "US:USD:AAPL", action: "update", ticker: "AAPL", currency: "USD",
    before: { quantity: "0.1", averagePrice: "12" }, after: { quantity, averagePrice: average },
    delta: { quantity: "0.0000000000000000000000000001", averagePrice: "0.345678901234567890123456789012" } },
  { positionKey: "US:USD:MSFT", action: "add", ticker: "MSFT", currency: "USD", before: null,
    after: { quantity: tiny, averagePrice: "20" }, delta: { quantity: tiny, averagePrice: "20" } }];
  await page.route("**/*", async route => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const send = (value: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
    if (route.request().method() === "POST") calls.push({ path: url.pathname, body: route.request().postDataJSON() });
    if (url.pathname === "/api/portfolio") {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON();
        if (body.positions[0].quantity === "bad") return send({ detail: { code: "portfolio_validation_failed", errors: [{ row: 0, field: "quantity", code: "invalid_decimal" }] } }, 422);
        portfolio = { ...portfolio, ...body, schemaVersion: 3, revision: portfolio.revision + 1 };
      }
      return send(portfolio);
    }
    if (url.pathname === "/api/portfolio/toss/accounts") return send({ provider: "toss_open_api", openApiVersion: "1.2.14", accounts: [{ selectionId: "fixture-selection", label: "테스트 계좌", accountType: "BROKERAGE", selectable: true }] });
    if (url.pathname === "/api/portfolio/toss/preview") return send({ previewId: "fixture-preview", expectedRevision: portfolio.revision, canConfirm: !blocked, status: "ready", provider: "toss_open_api", openApiVersion: "1.2.14", details,
      buckets: { additions: ["US:USD:MSFT"], updates: ["US:USD:AAPL"], unchanged: [], preservedManual: ["US:USD:SPY"],
        conflicts: blocked ? [{ positionKey: "US:USD:AAPL", issueCodes: ["market_currency_conflict"] }] : [], unsupported: [] } });
    if (url.pathname === "/api/portfolio/toss/confirm") {
      portfolio = { ...portfolio, revision: portfolio.revision + 1, positions: [
        { ...portfolio.positions[0], quantity, averagePrice: average }, portfolio.positions[1],
        { ticker: "MSFT", quantity: tiny, averagePrice: "20", market: "US", currency: "USD" },
      ] };
      return send({ portfolio, metadataStatus: "ready", idempotent: false });
    }
    if (url.pathname === "/api/portfolio/analytics") {
      if (unavailable) return send({ positions: portfolio.positions.map(row => ({ ...row, calculationUnavailable: ["market_value_unavailable"] })), cash: portfolio.cash,
        summary: [{ currency: "USD 기준", marketValue: null, cost: null, pnl: null, pnlPct: null, positions: 0, calculationUnavailable: ["market_value_total_unavailable"] }], baseCurrency: "USD", fxRates: {}, analytics: {
          totalMarketValue: null, totalCost: null, totalPnl: null, totalPnlPct: null,
          marketWeights: [{ label: "미국", marketValue: null, pnl: null, pnlPct: null, positions: 2, weight: null }], sectorWeights: [], currencyWeights: [], assetClassWeights: [],
          concentration: { holdings: 2, top1: null, top3: null }, comments: [],
        } });
      const slice = [{ label: "미국", marketValue: 162, pnl: 0, pnlPct: 0, positions: 2, weight: 1 }];
      return send({ positions: portfolio.positions, cash: portfolio.cash, summary: [], baseCurrency: "USD", fxRates: {}, analytics: {
        totalMarketValue: 162, totalCost: 162, totalPnl: 0, totalPnlPct: 0, marketWeights: slice, sectorWeights: slice,
        currencyWeights: slice, assetClassWeights: slice, concentration: { holdings: 2, top1: 0.93, top3: 1 }, comments: [],
      } });
    }
    return send({ detail: "isolated fixture" }, 404);
  });
  await page.addInitScript(selected => { localStorage.setItem("folio.themePreference.v1", selected); localStorage.setItem("folio.react.agentClosed", "1"); }, theme);
  await page.goto("/#/portfolio", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "현재 보유 종목" })).toBeVisible();
  return calls;
}

async function preview(page: Page) {
  await page.getByRole("button", { name: "Toss 계좌 불러오기" }).click();
  await page.getByRole("button", { name: /테스트 계좌/ }).click();
  await page.getByRole("button", { name: "미리보기", exact: true }).click();
  await expect(page.getByRole("heading", { name: "변경 미리보기" })).toBeVisible();
}

for (const theme of ["light", "dark"] as const) {
  test(`decimal exact preview and confirmation ${theme}`, async ({ page }, info) => {
    const calls = await fixture(page, theme);
    await preview(page);
    const region = page.locator(".toss-holdings-import__preview");
    await expect(region).toContainText(quantity);
    await expect(region).toContainText(average);
    await expect(region).toContainText(tiny);
    await expect(region.getByText(quantity, { exact: true })).toBeVisible();
    await expect(region.getByText(average, { exact: true })).toBeVisible();
    if (info.project.name.includes("mobile")) {
      for (const value of await region.locator(".toss-holdings-import__detail-value").all()) {
        await expect(value).toBeVisible();
        expect((await value.boundingBox())!.width).toBeGreaterThan(200);
      }
    }
    expect(calls.some(call => call.path.endsWith("/confirm"))).toBe(false);
    await region.screenshot({ path: info.outputPath(`decimal-preview-${theme}.png`) });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    const results = await new AxeBuilder({ page }).include(".toss-holdings-import").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(results.violations.filter(item => ["serious", "critical"].includes(item.impact || ""))).toEqual([]);
    const button = page.getByRole("button", { name: "가져오기 확정" });
    await button.focus();
    await expect(button).toBeFocused();
    if (info.project.name.includes("mobile")) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("table", { name: "저장된 보유 종목" })).toContainText(quantity);
    await page.getByRole("button", { name: "보유 편집", exact: true }).click();
    await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue(quantity);
    await expect(page.getByLabel("AAPL 평균단가", { exact: true })).toHaveValue(average);
    await expect(page.getByLabel("SPY 수량", { exact: true })).toHaveValue("1.5");
    await expect(page.getByLabel("MSFT 수량", { exact: true })).toHaveValue(tiny);
    expect(calls.filter(call => call.path.endsWith("/confirm"))).toEqual([{ path: "/api/portfolio/toss/confirm", body: { previewId: "fixture-preview", expectedRevision: 4 } }]);
  });
}

test("decimal manual draft posts unchanged strings and preserved cash", async ({ page }) => {
  const calls = await fixture(page, "light");
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await page.getByLabel("AAPL 수량", { exact: true }).fill(quantity);
  await page.getByLabel("AAPL 평균단가", { exact: true }).fill(average);
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect.poll(() => calls.filter(call => call.path === "/api/portfolio").length).toBe(1);
  const body = calls.find(call => call.path === "/api/portfolio")!.body;
  expect(body.positions[0]).toMatchObject({ quantity, averagePrice: average });
  expect(body.cash).toEqual([{ currency: "USD", amount: 50 }]);
  expect(body.expectedRevision).toBe(4);
});

test("decimal conflict still blocks complete import", async ({ page }) => {
  const calls = await fixture(page, "dark", true);
  await preview(page);
  await expect(page.getByRole("button", { name: "가져오기 확정" })).toBeDisabled();
  expect(calls.some(call => call.path.endsWith("/confirm"))).toBe(false);
});

test("decimal invalid manual row stays editable with a field error", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  const input = page.getByLabel("AAPL 수량", { exact: true });
  await input.fill("bad");
  await page.getByRole("button", { name: "Portfolio 저장", exact: true }).click();
  await expect(input).toHaveValue("bad");
  await expect(input).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("SPY 수량", { exact: true })).toHaveValue("1.5");
  await expect(page.getByRole("alert").first()).toBeVisible();
});

test("decimal import loading error and empty accounts remain explicit", async ({ page }) => {
  const calls = await fixture(page, "light");
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  const endpoint = "**/api/portfolio/toss/accounts";
  await page.route(endpoint, async route => {
    await pending;
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "provider_unavailable" } }) });
  });
  await page.getByRole("button", { name: "Toss 계좌 불러오기" }).click();
  await expect(page.getByRole("button", { name: "계좌 확인 중" })).toBeDisabled();
  await expect(page.locator(".toss-holdings-import").getByRole("status")).toContainText("계좌를 확인하고 있습니다");
  release();
  await expect(page.locator(".toss-holdings-import").getByRole("alert")).toContainText("수동 Portfolio 입력은 계속 사용할 수 있습니다");
  await page.unroute(endpoint);
  await page.route(endpoint, route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ provider: "toss_open_api", openApiVersion: "1.2.14", accounts: [] }) }));
  await page.getByRole("button", { name: "Toss 계좌 불러오기" }).click();
  await expect(page.locator(".toss-holdings-import").getByRole("status")).toContainText("가져올 수 있는 계좌가 없습니다");
  await expect(page.getByRole("button", { name: "가져오기 확정" })).toHaveCount(0);
  expect(calls.some(call => call.path.endsWith("/confirm"))).toBe(false);
});

test("decimal unrepresentable analytics is explained without replacing authority", async ({ page }) => {
  await fixture(page, "light", false, true);
  const analysis = page.locator(".portfolio-analysis");
  await expect(analysis).toContainText("계산");
  await expect(analysis.locator(".portfolio-metric").first().locator("strong")).toHaveText("—");
  const composition = analysis.locator("details").filter({ hasText: "구성" }).first();
  if (await composition.count()) await composition.locator("summary").click();
  await expect(analysis.locator(".portfolio-weight__value").first()).toHaveText("—");
  await page.getByRole("button", { name: "보유 편집", exact: true }).click();
  await expect(page.getByLabel("AAPL 수량", { exact: true })).toHaveValue("1e+1000");
});
