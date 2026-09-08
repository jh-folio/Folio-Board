import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { resolve } from "node:path";

const REQUEST_ID = "req_12345678-1234-4234-8234-123456789abc";
const RUN_ID = "run_abcdefab-cdef-4abc-8def-abcdefabcdef";

async function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) {
  await route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
}

async function inspectError(page: Page, selector: string, name: string, theme: string, project: string) {
  const panel = page.locator(selector);
  await panel.scrollIntoViewIfNeeded();
  const box = await panel.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
  const result = await new AxeBuilder({ page }).include(selector).analyze();
  expect(result.violations.filter((item) => item.impact === "serious" || item.impact === "critical")).toEqual([]);
  await page.screenshot({ path: resolve(process.cwd(), `../.planning/0.6-b0/captures/http-${name}-${theme}-${project}.png`), fullPage: true });
}

for (const theme of ["light", "dark"] as const) {
test.describe(`0.6 D3 bounded HTTP report diagnostics (${theme})`, () => {
  test.beforeEach(async ({ page }, testInfo) => {
    if (testInfo.project.name.includes("mobile")) await page.setViewportSize({ width: 375, height: 812 });
    await page.addInitScript((value) => localStorage.setItem("folio.themePreference.v1", value), theme);
  });

  test("Briefing links a run ID after a prior archive error without repeating generation", async ({ page }, testInfo) => {
    let archiveCalls = 0;
    let generationSends = 0;
    const diagnosticUrls: string[] = [];
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (url.pathname === "/api/briefings/index") {
        archiveCalls += 1;
        return json(route, { items: [], total: 0, offset: 0, limit: 100 }, archiveCalls === 1 ? 503 : 200);
      }
      if (url.pathname === "/api/briefings" && request.method() === "POST") {
        generationSends += 1;
        return json(route, { error: "generation_failed" }, 502, {
          "X-Folio-Request-Id": REQUEST_ID,
          "X-Folio-Run-Id": RUN_ID,
        });
      }
      if (url.pathname === `/api/diagnostics/runs/${RUN_ID}`) {
        diagnosticUrls.push(url.pathname);
        return json(route, { detail: "fixture does not expose diagnostics" }, 404);
      }
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    await page.goto(`/?theme=${theme}#/briefing`);
    await expect(page.locator("[data-briefing-route]")).toBeVisible();
    await page.getByRole("button", { name: "오늘 브리핑 생성", exact: true }).click();
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
    await expect(page.locator("[data-briefing-route] .react-dashboard-error").filter({ hasText: "/api/briefings failed: 502" })).toHaveCount(1);
    expect(archiveCalls).toBeGreaterThan(0);
    expect(generationSends).toBe(1);

    await page.locator("[data-qa=diag-detail-toggle]").click();
    await expect.poll(() => diagnosticUrls.length).toBe(1);
    expect(diagnosticUrls[0]).toBe(`/api/diagnostics/runs/${RUN_ID}`);
    expect(generationSends).toBe(1);
    await expect(page.locator("[data-qa=diag-detail-error]")).toBeVisible();
    await inspectError(page, "[data-qa=report-error-diagnostic]", "run-error", theme, testInfo.project.name);
  });

  test("Briefing keeps a current generation diagnostic when an archive refresh fails concurrently", async ({ page }) => {
    let archiveCalls = 0;
    let generationSends = 0;
    let releaseArchive!: () => void;
    let releaseGeneration!: () => void;
    let archiveFailedResolve!: () => void;
    const archivePending = new Promise<void>((resolve) => { releaseArchive = resolve; });
    const generationPending = new Promise<void>((resolve) => { releaseGeneration = resolve; });
    const archiveFailed = new Promise<void>((resolve) => { archiveFailedResolve = resolve; });

    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (url.pathname === "/api/briefings/index") {
        archiveCalls += 1;
        if (archiveCalls === 1) {
          await archivePending;
          archiveFailedResolve();
          return json(route, { error: "archive_unavailable" }, 503);
        }
        return json(route, { items: [], total: 0, offset: 0, limit: 100 });
      }
      if (url.pathname === "/api/briefings" && request.method() === "POST") {
        generationSends += 1;
        await generationPending;
        return json(route, { error: "generation_failed" }, 502, {
          "X-Folio-Request-Id": REQUEST_ID,
          "X-Folio-Run-Id": RUN_ID,
        });
      }
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    await page.goto(`/?theme=${theme}#/briefing`);
    await expect(page.locator("[data-briefing-route]")).toBeVisible();
    await page.getByRole("button", { name: "오늘 브리핑 생성", exact: true }).click();
    await expect.poll(() => generationSends).toBe(1);
    releaseArchive();
    await archiveFailed;
    await expect(page.locator("[data-briefing-route] .react-dashboard-error")).toContainText("archive_unavailable");
    // The list failure owns the shared text briefly, but must not cancel the
    // still-current generation attempt or its eventual HTTP diagnostic.
    releaseGeneration();
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
    expect(generationSends).toBe(1);
  });

  test("Company Analysis shows a request-only ID and clears it on recovery", async ({ page }, testInfo) => {
    let generationSends = 0;
    const report = {
      id: "analysis-1",
      query: "NVDA",
      company: { ticker: "NVDA", name: "NVIDIA" },
      generatedAt: "2026-09-05T00:00:00Z",
      analysisStyle: "beginner",
      markdown: "# NVIDIA\n\n분석 본문",
      sources: [],
    };
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (url.pathname === "/api/analysis-reports" && request.method() === "GET") return json(route, []);
      if (url.pathname === "/api/company/resolve") return json(route, { status: "confident", match: { ticker: "NVDA", name: "NVIDIA", market: "US" }, candidates: [] });
      if (url.pathname === "/api/analyze" && request.method() === "GET") {
        generationSends += 1;
        if (generationSends === 1) return json(route, { error: "generation_failed" }, 502, { "X-Folio-Request-Id": REQUEST_ID, "X-Folio-Run-Id": "run_bad" });
        return json(route, report);
      }
      if (url.pathname === "/api/analysis-reports/analysis-1") return json(route, report);
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    await page.goto(`/?theme=${theme}#/analysis`);
    const input = page.locator("[data-company-analysis-route] input").first();
    await input.fill("NVDA");
    await page.getByRole("button", { name: "분석", exact: true }).click();
    await expect(page.locator("[data-qa=report-request-detail]")).toBeVisible();
    await page.locator("[data-qa=report-request-detail-toggle]").click();
    await expect(page.locator("[data-qa=report-request-id]")).toHaveText(REQUEST_ID);
    expect(generationSends).toBe(1);
    await inspectError(page, "[data-qa=report-error-diagnostic]", "request-only", theme, testInfo.project.name);

    await page.getByRole("button", { name: "분석", exact: true }).click();
    await expect(page.locator("[data-company-analysis-route] .report-reader-shell")).toBeVisible();
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(0);
    expect(generationSends).toBe(2);
  });

  test("Company Analysis keeps an unsaved candidate readable and closable", async ({ page }, testInfo) => {
    const report = {
      id: "analysis-unsaved",
      query: "NVDA",
      company: { ticker: "NVDA", name: "NVIDIA" },
      generatedAt: "2026-09-05T00:00:00Z",
      analysisStyle: "beginner",
      saved: false,
      markdown: "# NVIDIA\n\n## 분석 초안\n\n저장 여부를 확인할 수 없는 보고서 본문입니다.",
      sources: [],
    };
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (url.pathname === "/api/analysis-reports" && request.method() === "GET") return json(route, []);
      if (url.pathname === "/api/company/resolve") return json(route, { status: "confident", match: { ticker: "NVDA", name: "NVIDIA", market: "US" }, candidates: [] });
      if (url.pathname === "/api/analyze" && request.method() === "GET") return json(route, report);
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    await page.goto(`/?theme=${theme}#/analysis`);
    await page.locator("[data-company-analysis-route] input").first().fill("NVDA");
    await page.getByRole("button", { name: "분석", exact: true }).click();
    await expect(page.locator(".report-reader-shell")).toBeVisible();
    await expect(page.locator(".report-body")).toContainText("저장 여부를 확인할 수 없는 보고서 본문입니다.");
    await expect(page.locator(".react-reader-status")).toContainText("기업 분석 보고서는 생성했지만 저장 여부를 확인하지 못했습니다.");
    await inspectError(page, ".report-reader-shell", "company-unsaved", theme, testInfo.project.name);
    const closeButton = page.locator("[data-qa=dr-report-close]");
    await closeButton.focus();
    await expect(closeButton).toBeFocused();
    await closeButton.click();
    await expect(page.locator(".report-reader-shell")).toHaveCount(0);
    await expect(page.locator("[data-company-analysis-route] form")).toBeVisible();
  });

  test("Company Analysis keeps the generated body when feed refresh returns 500", async ({ page }) => {
    let listCalls = 0;
    const report = {
      id: "analysis-refresh-failed",
      query: "NVDA",
      company: { ticker: "NVDA", name: "NVIDIA" },
      generatedAt: "2026-09-05T00:00:00Z",
      analysisStyle: "beginner",
      saved: false,
      markdown: "# NVIDIA\n\n## 분석 결과\n\n목록 새로고침이 실패해도 유지되어야 하는 본문입니다.",
      sources: [],
    };
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (url.pathname === "/api/analysis-reports" && request.method() === "GET") {
        listCalls += 1;
        return listCalls === 1 ? json(route, []) : json(route, { error: "archive_unavailable" }, 500);
      }
      if (url.pathname === "/api/company/resolve") return json(route, { status: "confident", match: { ticker: "NVDA", name: "NVIDIA", market: "US" }, candidates: [] });
      if (url.pathname === "/api/analyze" && request.method() === "GET") return json(route, report);
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    await page.goto(`/?theme=${theme}#/analysis`);
    await page.locator("[data-company-analysis-route] input").first().fill("NVDA");
    await page.getByRole("button", { name: "분석", exact: true }).click();
    await expect(page.locator(".report-body")).toContainText("목록 새로고침이 실패해도 유지되어야 하는 본문입니다.");
    await expect.poll(() => listCalls).toBe(2);
    await expect(page.locator(".report-reader-shell")).toBeVisible();
    await expect(page.locator(".report-body")).toContainText("목록 새로고침이 실패해도 유지되어야 하는 본문입니다.");
  });

  test("Deep Research treats restored polling transport loss as unknown without retry encouragement", async ({ page }, testInfo) => {
    const jobId = "job_12345678-1234-4234-8234-123456789abc";
    let jobCalls = 0;
    await page.addInitScript((key) => {
      window.localStorage.setItem("folio.deepResearch.activeJob.v1", key);
    }, jobId);
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      if (url.pathname === "/api/topic-reports" && request.method() === "GET") return json(route, []);
      if (url.pathname === `/api/jobs/${jobId}`) {
        jobCalls += 1;
        if (jobCalls === 1) return json(route, { id: jobId, status: "running", taskType: "topic_report" });
        return route.abort("failed");
      }
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    await page.goto(`/?theme=${theme}#/deep-research`);
    await expect(page.locator("[data-deep-research-route]")).toBeVisible();
    await expect(page.locator("[data-qa=dr-error-generation]")).toBeVisible({ timeout: 5_000 });
    await expect(page.locator("[data-qa=dr-error-generation]")).toContainText("서버 처리 결과를 확인할 수 없습니다.");
    await expect(page.locator("[data-qa=dr-error-generation]")).toContainText("서버 상태를 확인하세요");
    await expect(page.locator("[data-qa=dr-error-generation]")).not.toContainText("다시 시도할 수 있습니다");
    await expect.poll(() => jobCalls).toBe(2);
    const callsAfterFailure = jobCalls;
    await page.waitForTimeout(1_200);
    expect(jobCalls).toBe(callsAfterFailure);
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(0);
    await inspectError(page, "[data-qa=dr-error-generation]", "transport-unknown", theme, testInfo.project.name);
  });
});
}
