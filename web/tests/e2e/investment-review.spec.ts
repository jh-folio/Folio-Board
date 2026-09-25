import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const review = {
  schemaVersion: 2, sourceSchemaVersion: 2, date: "2026-09-01", reviewRevision: 1,
  reviewState: "draft", summary: "규칙 기반 검토입니다.", generatedAt: "2026-09-01T09:00:00Z",
  freshness: { status: "partial", dueCount: 1, reasons: [] },
  inputBasis: { status: "partial", canonicalReports: [{ kind: "briefing", id: "2026-08-31", asOf: "2026-08-31" }] },
  positionReviews: [{ ticker: "NVDA", name: "NVIDIA", thesisVerdict: "maintained", reviewReasons: ["checkpoint_pending"], dueCheckpoints: [{ label: "실적 확인", dueAt: "2026-10-01" }] }],
  sharedExposures: [{ type: "narrative", key: "ai_power", label: "AI 전력", tickers: ["NVDA"] }],
  portfolioRisks: [{ riskKey: "correlation_volatility", status: "unavailable", uncertainty: "compatible_saved_backtest_missing" }],
  changesSincePrevious: [], counterEvidence: [], uncertainties: [], staleReasons: [],
};

async function openPortfolio(page: import("@playwright/test").Page, theme: "light" | "dark", initial = review, challengeCalls?: Array<{ scope?: unknown; message?: string }>, refreshBodies?: unknown[], acceptedJob = false, deletedThreads?: string[], preserveFailedThread = false) {
  let current = { ...initial };
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/portfolio") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ revision: 1, positions: [{ ticker: "NVDA", quantity: "1", averagePrice: "100" }] }) });
    if (url.pathname === "/api/investment-review/history") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [current] }) });
    if (url.pathname === "/api/investment-review" || url.pathname === "/api/investment-review/generate") {
      if (route.request().method() === "POST") { refreshBodies?.push(route.request().postDataJSON()); current = { ...current, reviewRevision: current.reviewRevision + 1, reviewState: "draft" }; }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(current) });
    }
    if (url.pathname.endsWith("/reviewed")) { current = { ...current, reviewRevision: current.reviewRevision + 1, reviewState: "reviewed", reviewedAt: "2026-09-01T10:00:00Z" }; return route.fulfill({ contentType: "application/json", body: JSON.stringify(current) }); }
    if (/^\/api\/investment-review\/\d{4}-\d{2}-\d{2}$/.test(url.pathname)) return route.fulfill({ contentType: "application/json", body: JSON.stringify(current) });
    if (url.pathname === "/api/agent/threads" && route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { scope?: unknown };
      challengeCalls?.push({ scope: body.scope });
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ id: "challenge-thread", title: "투자 리뷰의 약한 전제", scope: body.scope, messages: [] }) });
    }
    if (url.pathname === "/api/agent/threads/challenge-thread/messages" && route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { message?: string };
      challengeCalls?.push({ message: body.message });
      if (acceptedJob) return route.fulfill({ contentType: "application/json", body: JSON.stringify({ job: { id: "long-running", status: "running", message: "running" } }) });
      return route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"fixture stop"}' });
    }
    if (url.pathname === "/api/agent/threads/challenge-thread" && route.request().method() === "DELETE") {
      deletedThreads?.push("challenge-thread");
      return route.fulfill(preserveFailedThread ? { status: 409, contentType: "application/json", body: '{"detail":"consultation_not_empty"}' } : { contentType: "application/json", body: "{}" });
    }
    if (url.pathname === "/api/jobs/long-running") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ id: "long-running", status: "running", message: "still running" }) });
    return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"fixture"}' });
  });
  await page.addInitScript((selected) => { localStorage.setItem("folio.themePreference.v1", selected); localStorage.setItem("folio.react.agentClosed", "1"); }, theme);
  await page.goto("/#/portfolio", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /^투자 리뷰/ }).click();
  await expect(page.getByRole("heading", { name: "투자 리뷰" })).toBeVisible();
}

for (const theme of ["light", "dark"] as const) {
  test(`investment review workspace is actionable and accessible in ${theme}`, async ({ page }, testInfo) => {
    await openPortfolio(page, theme);
    await expect(page.getByText("규칙 기반 검토입니다.")).toBeVisible();
    await page.getByRole("button", { name: "오늘 리뷰 갱신" }).click();
    await expect(page.getByRole("status")).toContainText("갱신했습니다");
    await page.getByRole("button", { name: "검토 완료" }).click();
    await expect(page.getByText("이 리뷰를 검토 완료로 기록했습니다.")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`investment-review-${theme}.png`), fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    if (!testInfo.project.name.includes("mobile")) {
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
      expect(result.violations.filter((item) => item.impact === "serious" || item.impact === "critical")).toEqual([]);
    } else {
      for (const name of ["오늘 리뷰 갱신", "검토 완료", "이 리뷰의 가장 약한 전제를 찾아줘"]) {
        expect(await page.getByRole("button", { name }).evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
      }
    }
  });
}

test("investment review shows stale and due attention and submits one exact challenge", async ({ page }) => {
  const challengeCalls: Array<{ scope?: unknown; message?: string }> = [];
  await openPortfolio(page, "light", { ...review, reviewState: "stale", freshness: { status: "stale", dueCount: 2, reasons: [{ code: "input_fingerprint_changed" }] } }, challengeCalls);
  await expect(page.getByLabel("리뷰 상태: 오래됨")).toBeVisible();
  await expect(page.getByText("확인 예정 2건").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "검토 완료" })).toBeDisabled();
  await page.getByRole("button", { name: "이 리뷰의 가장 약한 전제를 찾아줘" }).click();
  await expect.poll(() => challengeCalls.length).toBe(2);
  expect(challengeCalls).toEqual([
    { scope: { kind: "investment_review", id: "2026-09-01", revision: 1, intent: "challenge" } },
    { message: "이 리뷰의 가장 약한 전제를 찾아줘" },
  ]);
});

test("today refresh explicitly requests local rules", async ({ page }) => {
  const bodies: unknown[] = [];
  await openPortfolio(page, "light", review, undefined, bodies);
  await page.getByRole("button", { name: "오늘 리뷰 갱신" }).click();
  await expect.poll(() => bodies).toEqual([{ generationMode: "rules" }]);
});

test("challenge acknowledges accepted long-running job before terminal polling and cleans a failed empty thread", async ({ page }) => {
  const accepted: Array<{ scope?: unknown; message?: string }> = [];
  await openPortfolio(page, "light", review, accepted, undefined, true);
  await page.getByRole("button", { name: "이 리뷰의 가장 약한 전제를 찾아줘" }).click();
  await expect(page.getByRole("main").getByRole("status")).toContainText("반증 검토를 요청했습니다");
  await expect.poll(() => accepted).toEqual([
    { scope: { kind: "investment_review", id: "2026-09-01", revision: 1, intent: "challenge" } },
    { message: "이 리뷰의 가장 약한 전제를 찾아줘" },
  ]);

  const deleted: string[] = [];
  // The accepted Dock owns the long-running job and correctly rejects a
  // second scoped request.  Exercise the POST-failure cleanup in an isolated
  // fresh Dock instead of conflating it with that busy rejection.
  const cleanupPage = await page.context().newPage();
  await openPortfolio(cleanupPage, "light", review, undefined, undefined, false, deleted);
  await cleanupPage.getByRole("button", { name: "이 리뷰의 가장 약한 전제를 찾아줘" }).click();
  await expect.poll(() => deleted).toEqual(["challenge-thread"]);
  await cleanupPage.close();
});

test("challenge preserves a server-persisted user turn when job submission fails", async ({ page }) => {
  const deletes: string[] = [];
  await openPortfolio(page, "light", review, undefined, undefined, false, deletes, true);
  await page.getByRole("button", { name: "이 리뷰의 가장 약한 전제를 찾아줘" }).click();
  await expect.poll(() => deletes).toEqual(["challenge-thread"]);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("질문은 대화에 저장되어 보존했습니다");
});

for (const theme of ["light", "dark"] as const) {
test(`U.5 keeps critical evidence before actions while grouping readiness and exposing safe links in ${theme}`, async ({ page }, testInfo) => {
  const missingRoster = Array.from({ length: 18 }, (_, index) => ({
    ticker: `MISS${String(index + 1).padStart(2, "0")}`,
    thesisVerdict: "insufficient_evidence",
    thesisPresent: false,
    latestReviewPresent: false,
  }));
  await openPortfolio(page, theme, {
    ...review,
    freshness: { status: "partial", dueCount: 2, overdueUnresolvedCount: 1, evaluatedAt: "2026-09-05T00:00:00Z", reasons: [] },
    inputBasis: {
      status: "partial",
      canonicalReports: [
        { kind: "briefing", id: "2026-09-04.us", reportKind: "weekly", marketScope: "us", title: "주간 시장 브리핑", relatedReason: "NVDA 확인" },
        { kind: "unknown", id: "https://example.invalid", title: "외부 주소가 아닌 식별자" },
      ],
    },
    reportSelection: { candidateCount: 12, includedCount: 4, excludedCount: 8 },
    coverage: { totalPositionCount: 20, rosterIncludedCount: 19, detailIncludedCount: 2, omittedRosterCount: 1, omittedDetailCount: 18 },
    positionRoster: [
      { ticker: "NVDA", thesisVerdict: "broken", thesisPresent: true, latestReviewPresent: true },
      ...missingRoster,
    ],
    positionReviews: [{
      ticker: "NVDA", name: "NVIDIA", thesisVerdict: "broken", thesisPresent: true, latestReviewPresent: true,
      counterEvidence: [{ title: "가정과 다른 수요 둔화" }], dueCheckpoints: [{ label: "실적 확인", dueAt: "2026-09-04" }],
    }, {
      ticker: "SYM100", thesisVerdict: "broken", thesisPresent: true, latestReviewPresent: true,
      counterEvidence: [{ title: "최소 목록 밖 위험 반증" }],
    }],
    changesSincePrevious: [{
      kind: "checkpoint", key: "NVDA:earnings", change: "changed",
      from: { status: "open", lastVerdict: { verdict: "watch", evidence: [{ memoryId: "m-1" }] } },
      to: { status: "closed", lastVerdict: { verdict: "resolved", evidence: [{ memoryId: "m-2" }, { memoryId: "m-3" }] } },
    }, {
      kind: "risk", key: "portfolio_concentration+v1", change: "changed",
      from: { status: "available", concentration: { top1: 0.2 }, riskContributions: [{ ticker: "NVDA", weight: 0.2 }] },
      to: { status: "available", concentration: { top1: 0.3 }, riskContributions: [{ ticker: "NVDA", weight: 0.3 }] },
    }],
    sharedExposures: [{ type: "narrative", key: "ai_power", label: "AI 전력", tickers: ["NVDA"], weight: 0.31 }],
  });

  const attention = page.locator(".investment-review-attention");
  await expect(attention.getByText("가정과 다른 수요 둔화")).toBeVisible();
  await expect(attention.getByText("최소 목록 밖 위험 반증")).toBeVisible();
  await expect(attention.getByText("투자 논리가 아직 없는 보유 종목 18개가 있습니다.")).toBeVisible();
  await expect(page.getByText("최소 목록에서 제외 1개")).toBeVisible();
  await expect(page.getByText("상세에서 제외 18개")).toBeVisible();
  await expect(page.getByRole("heading", { name: /SYM100/ })).toBeVisible();
  await expect(page.getByText("체크포인트 · NVDA:earnings · 열림 · 판정 기록됨 · 근거 1개 → 종료 · 판정 기록됨 · 근거 2개")).toBeVisible();
  await expect(page.getByText("정량 위험 · portfolio_concentration+v1 · 참고 가능 · 상위 1개 20.0% · NVDA 20.0% → 참고 가능 · 상위 1개 30.0% · NVDA 30.0%")).toBeVisible();
  await expect(page.locator('a[href="#/watchlist/MISS01"]')).toBeVisible();
  expect(await attention.evaluate((element) => Number(element.compareDocumentPosition(document.querySelector(".investment-review-actions")!)) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  await expect(page.getByText("판단 보류", { exact: true })).toHaveCount(0);

  await page.getByText("연결 자료", { exact: true }).first().click();
  await expect(page.locator('a[href="#/briefing/2026-09-04/us/weekly"]')).toBeVisible();
  await expect(page.getByText("후보 12건 중 4건을 연결했습니다 · 선별 한계로 제외 8건.")).toBeVisible();
  await expect(page.locator('a[href="https://example.invalid"]')).toHaveCount(0);
  await page.getByText("연결 자료", { exact: true }).first().click();
  await page.screenshot({ path: testInfo.outputPath(`investment-review-u5-${theme}.png`), fullPage: true });
  await page.getByRole("heading", { name: "저장 리뷰 요약" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath(`investment-review-u5-${theme}-summary-viewport.png`) });
  await attention.scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath(`investment-review-u5-${theme}-attention-viewport.png`) });
  await page.locator(".investment-review-actions").scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath(`investment-review-u5-${theme}-actions-viewport.png`) });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  const result = await new AxeBuilder({ page }).include(".investment-review-workspace").withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.filter((item) => item.impact === "serious" || item.impact === "critical")).toEqual([]);
});
}

async function openPortfolioWithSnapshots(page: import("@playwright/test").Page, latest: Record<string, unknown>, items: Array<Record<string, unknown>>, byDate: Record<string, Record<string, unknown>>) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/portfolio") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ revision: 1, positions: [{ ticker: "NVDA", quantity: "1", averagePrice: "100" }] }) });
    if (url.pathname === "/api/investment-review") return route.fulfill({ contentType: "application/json", body: JSON.stringify(latest) });
    if (url.pathname === "/api/investment-review/history") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ items }) });
    const matched = url.pathname.match(/^\/api\/investment-review\/(\d{4}-\d{2}-\d{2})$/);
    if (matched) return route.fulfill({ contentType: "application/json", body: JSON.stringify(byDate[matched[1]] || latest) });
    if (url.pathname.endsWith("/reviewed")) {
      const date = url.pathname.match(/investment-review\/(\d{4}-\d{2}-\d{2})/)?.[1] || "";
      const selected = byDate[date] || latest;
      const updated = { ...selected, reviewRevision: Number(selected.reviewRevision || 0) + 1, reviewState: "reviewed", reviewedAt: "2026-09-04T11:00:00Z" };
      byDate[date] = updated;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(updated) });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"fixture"}' });
  });
  await page.addInitScript(() => { localStorage.setItem("folio.themePreference.v1", "light"); localStorage.setItem("folio.react.agentClosed", "1"); });
  await page.goto("/#/portfolio", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: /^투자 리뷰/ }).click();
}

test("U.5 reads a legacy revision-zero snapshot and keeps actions disabled", async ({ page }) => {
  const legacy = {
    schemaVersion: 2, sourceSchemaVersion: 1, date: "2026-08-30", reviewRevision: 0, reviewState: "stale", summary: "이전 저장 요약",
    freshness: { status: "unknown", dueCount: 0, reasons: [{ code: "legacy_input_basis_unknown" }] }, inputBasis: { status: "legacy_unknown" },
    portfolioImpacts: [{ ticker: "NVDA", impact: "영향 검토" }], thesisChanges: [{ ticker: "NVDA", verdict: "weakened" }],
    keyCheckpoints: [{ ticker: "NVDA", checkpoint: "다음 실적", dueAt: "2026-09-10" }], recentReports: [{ title: "이전 시장 자료", date: "2026-08-30", type: "briefing" }],
  };
  await openPortfolioWithSnapshots(page, legacy, [legacy], { "2026-08-30": legacy });
  await expect(page.getByRole("heading", { name: "저장 리뷰 요약" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "이전 저장본의 항목" })).toBeVisible();
  await expect(page.getByText("이전 시장 자료 · 2026-08-30 · briefing")).toBeVisible();
  await expect(page.getByRole("button", { name: "검토 완료" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "이 리뷰의 가장 약한 전제를 찾아줘" })).toBeDisabled();
});

test("U.5 retains an old-v2 saved thesis-missing warning when readiness flags are absent", async ({ page }) => {
  const oldV2 = {
    ...review, date: "2026-08-30", reviewRevision: 2, sourceSchemaVersion: 2,
    positionRoster: [{ ticker: "NVDA", thesisVerdict: "insufficient_evidence" }],
    positionReviews: [{ ticker: "NVDA", thesisVerdict: "insufficient_evidence" }],
    uncertainties: [{ code: "thesis_missing", ticker: "NVDA" }],
  };
  await openPortfolioWithSnapshots(page, oldV2, [oldV2], { "2026-08-30": oldV2 });
  await expect(page.getByText("투자 논리가 아직 없습니다. · NVDA")).toBeVisible();
  await expect(page.getByText("준비 상태: 준비 상태 확인 불가")).toBeVisible();
});

test("U.5 leaves history available after an exact-date selection resolves to missing", async ({ page }) => {
  const latest = { ...review, date: "2026-09-04", reviewRevision: 4 };
  const missing = { schemaVersion: 2, sourceSchemaVersion: 2, date: "2026-08-30", reviewRevision: 0, reviewState: "draft", summary: "아직 저장된 투자 리뷰가 없습니다.", freshness: { status: "unknown", dueCount: 0, reasons: [] }, inputBasis: { status: "partial" } };
  await openPortfolioWithSnapshots(page, latest, [latest, missing], { "2026-08-30": missing, "2026-09-04": latest });
  await page.getByText("리뷰 이력", { exact: true }).click();
  await page.getByRole("button", { name: /2026-08-30/ }).click();
  await expect(page.getByRole("heading", { name: "저장된 리뷰가 없습니다" })).toBeVisible();
  await expect(page.getByText("리뷰 이력", { exact: true })).toBeVisible();
  await page.getByText("리뷰 이력", { exact: true }).click();
  await expect(page.getByRole("button", { name: /2026-09-04/ })).toBeVisible();
});

test("U.5 keeps the selected historical date after review completion refresh", async ({ page }) => {
  const latest = { ...review, date: "2026-09-04", reviewRevision: 4 };
  const historical = { ...review, date: "2026-08-30", reviewRevision: 2, reviewState: "draft" };
  await openPortfolioWithSnapshots(page, latest, [latest, historical], { "2026-08-30": historical, "2026-09-04": latest });
  await page.getByText("리뷰 이력", { exact: true }).click();
  await page.getByRole("button", { name: /2026-08-30/ }).click();
  await expect(page.locator(".investment-review-meta")).toContainText("2026-08-30");
  await page.getByRole("button", { name: "검토 완료" }).click();
  await expect(page.getByText("이 리뷰를 검토 완료로 기록했습니다.")).toBeVisible();
  await expect(page.locator(".investment-review-meta")).toContainText("2026-08-30");
});
