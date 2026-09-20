import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const JOB_ID = "job-1";
const RUN_ID = "run-aaaaaaaaaaaaaaaaaaaaaaaa";
const CAPTURE_DIR = resolve(process.cwd(), "../.planning/0.6-b0/captures");
const WORK_LOG_ENTRY = {
  id: "wl_aaaaaaaaaaaaaaaaaaaaaaaa",
  jobId: JOB_ID,
  category: "task",
  kind: "agent_bridge",
  taskType: "companion",
  labelCode: "agent_task",
  status: "done",
  progress: 100,
  messageCode: "done",
  createdAt: "2026-09-05T00:00:00Z",
  startedAt: "2026-09-05T00:00:01Z",
  updatedAt: "2026-09-05T00:00:05Z",
  finishedAt: "2026-09-05T00:00:05Z",
  errorCode: null,
  generationMode: "rules",
  adapter: "rules",
  requestedMode: null,
  mode: "answer",
  attemptedEngine: "rules",
  finalEngine: "rules",
  fallbackReason: null,
  artifactTypes: [],
  artifactCount: 0,
  proposalId: null,
  proposalStatus: null,
  resultStatus: "done",
  queueWaitMs: null,
  contextMs: null,
  cliMs: null,
  postprocessMs: null,
  totalMs: null,
};

const DETAIL = {
  version: 1,
  runId: RUN_ID,
  diagnosticQuality: "complete",
  availabilityReason: "present",
  authorityState: "matched",
  authorityStatus: "done",
  record: {
    schemaVersion: 1,
    runId: RUN_ID,
    jobId: JOB_ID,
    requestId: "req-1",
    parentRunId: null,
    retryOfRunId: null,
    processEpoch: "epoch-1",
    featureCode: "agent_mode",
    routeCode: "agent_chat",
    taskType: "companion",
    authorityKind: "shared_job",
    appVersion: "0.6.0",
    buildId: "qa",
    os: "Windows",
    pythonVersion: "3.13",
    createdAt: "2026-09-05T00:00:01Z",
    updatedAt: "2026-09-05T00:00:05Z",
    finishedAt: "2026-09-05T00:00:05Z",
    elapsedMs: 4200,
    observedStatus: "done",
    attemptedEngine: "rules",
    finalEngine: "rules",
    adapter: "rules",
    fallbackReason: null,
    events: [
      { seq: 1, eventId: "ev-1", stageId: "s-1", stageCode: "preflight", eventCode: "start", producerEpoch: "epoch-1", at: "2026-09-05T00:00:01Z", durationMs: null, errorId: null, count: 1 },
      { seq: 2, eventId: "ev-2", stageId: "s-1", stageCode: "preflight", eventCode: "end", producerEpoch: "epoch-1", at: "2026-09-05T00:00:02Z", durationMs: 1000, errorId: null, count: 1 },
    ],
    errors: [],
    firstFailure: null,
    terminalFailure: null,
    terminalObservation: { observedStatus: "done", observedAt: "2026-09-05T00:00:05Z", processEpoch: "epoch-1" },
    droppedEvents: 0,
    droppedErrors: 0,
    droppedIssues: 0,
    issueCodes: [],
    requiredProducerCoverage: "complete",
  },
  warnings: [],
};

const FAILED_DETAIL = {
  ...DETAIL,
  runId: "run-bbbbbbbbbbbbbbbbbbbbbbbb",
  authorityStatus: "failed",
  record: {
    ...DETAIL.record,
    runId: "run-bbbbbbbbbbbbbbbbbbbbbbbb",
    observedStatus: "failed",
    finishedAt: "2026-09-05T00:00:07Z",
    terminalObservation: { observedStatus: "failed", observedAt: "2026-09-05T00:00:07Z", processEpoch: "epoch-1" },
    firstFailure: {
      errorId: "err-1",
      stageId: "s-2",
      stageCode: "generate",
      errorCode: "adapter_failed",
      reasonCode: "adapter_failed",
      exceptionCode: "subprocess_exit",
      frames: [{ moduleCode: "agent_mode", functionCode: "run", line: 42 }],
      confirmation: "observed",
      nextActionCode: "explicit_retry",
      fingerprint: "fp-1",
    },
    terminalFailure: null,
  },
};

type FixtureState = { detailCalls: number; listCalls: number; errorOnce: boolean; stale: boolean; detailVersion?: number };

async function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function captureIfMissing(page: Page, filename: string) {
  const path = resolve(CAPTURE_DIR, filename);
  if (!existsSync(path)) await page.screenshot({ path, fullPage: true });
}

async function captureFinal(page: Page, filename: string) {
  await page.screenshot({ path: resolve(CAPTURE_DIR, filename), fullPage: true });
}

async function installFixture(page: Page, state: FixtureState) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/agent/work-log") {
      state.listCalls += 1;
      return json(route, { schemaVersion: 1, storeRevision: state.listCalls, jobsStoreRevision: 1, retention: { maxEntries: 200, maxDays: 30 }, total: 1, entries: [{ ...WORK_LOG_ENTRY, jobId: state.stale ? "job-2" : JOB_ID }] });
    }
    if (url.pathname === `/api/diagnostics/jobs/${JOB_ID}` || url.pathname === "/api/diagnostics/jobs/job-2") {
      state.detailCalls += 1;
      if (state.errorOnce && state.detailCalls === 1) return json(route, { detail: { code: "read_failed" } }, 500);
      if (state.stale) return json(route, { ...DETAIL, runId: "run-cccccccccccccccccccccccc", record: { ...DETAIL.record, runId: "run-cccccccccccccccccccccccc", jobId: "job-2" } });
      if (state.detailVersion) return json(route, { ...DETAIL, runId: "run-dddddddddddddddddddddddd", record: { ...DETAIL.record, runId: "run-dddddddddddddddddddddddd" } });
      return json(route, DETAIL);
    }
    // The shell's optional surfaces intentionally receive the same 404 fallback as
    // theme-accessibility.spec.ts, preventing malformed success payloads from
    // turning this Work Log fixture into an accidental integration test.
    return json(route, { detail: "QA fixture intentionally omits this route" }, 404);
  });
}

async function openWorkLog(page: Page, theme: "light" | "dark") {
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem("folio.themePreference.v1", selectedTheme);
    localStorage.setItem("folio.react.agentClosed", "1");
  }, theme);
  page.on("pageerror", (error) => console.log(`[pageerror] ${error.message}`));
  page.on("console", (message) => { if (message.type() === "error") console.log(`[console] ${message.text()}`); });
  await page.goto(`/?theme=${theme}#/home`);
  await page.waitForLoadState("networkidle");
  await expect(page.locator('[data-qa="work-log"]')).toBeVisible();
  const summary = page.locator(".work-log-collapse > summary");
  if (!(await page.locator(".work-log-collapse").getAttribute("open"))) await summary.click();
  await expect(page.locator('[data-qa="work-log-item"]')).toBeVisible();
}

test.describe("Work Log DiagnosticDetail", () => {
  test("captures desktop Light baseline and renders the complete detail", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop project owns the desktop Light capture.");
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toHaveText(/정상 기록/);
    await expect(page.locator('[data-qa="diag-detail-last-stage"]')).toHaveText("사전 점검");
    await expect(page.locator('[data-qa="diag-detail-elapsed"]')).toHaveText("4초");
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).toBeVisible();
    await captureIfMissing(page, "diagnostic-detail-desktop-light-baseline.png");
    await captureFinal(page, "diagnostic-detail-desktop-light-refresh-simplification-final.png");
  });

  test("captures desktop Dark detail", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop project owns the desktop Dark capture.");
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "dark");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toHaveText(/정상 기록/);
    await captureIfMissing(page, "diagnostic-detail-desktop-dark.png");
    await captureFinal(page, "diagnostic-detail-desktop-dark-refresh-simplification-final.png");
  });

  test("captures 375px Dark baseline and keeps the detail within the viewport", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("desktop"), "Mobile project owns the 375px capture.");
    await page.setViewportSize({ width: 375, height: 812 });
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "dark");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toHaveText(/정상 기록/);
    await captureIfMissing(page, "diagnostic-detail-mobile-dark-baseline.png");
    await captureFinal(page, "diagnostic-detail-mobile-dark-refresh-simplification-final.png");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("captures 375px Light detail", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("desktop"), "Mobile project owns the 375px Light capture.");
    await page.setViewportSize({ width: 375, height: 812 });
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toHaveText(/정상 기록/);
    await captureIfMissing(page, "diagnostic-detail-mobile-light.png");
    await captureFinal(page, "diagnostic-detail-mobile-light-refresh-simplification-final.png");
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  test("keyboard opens the disclosure and exposes a focusable developer disclosure", async ({ page }) => {
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    const toggle = page.locator('[data-qa="diag-detail-toggle"]');
    await toggle.focus();
    await expect(toggle).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-qa="diag-detail-state"]')).toBeVisible();
    const devSummary = page.locator('[data-qa="diag-detail-devinfo"] > summary');
    await devSummary.focus();
    await expect(devSummary).toBeFocused();
  });

  test("scoped diagnostics pass axe in Light and Dark", async ({ page }) => {
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    const light = await new AxeBuilder({ page }).include("[data-qa=diag-detail]").analyze();
    expect(light.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    const dark = await new AxeBuilder({ page }).include("[data-qa=diag-detail]").analyze();
    expect(dark.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });

  test("shows a retry action after a diagnostic read error", async ({ page }) => {
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: true, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-error"]')).toContainText("read_failed");
    await page.locator('[data-qa="diag-detail-retry"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toHaveText(/정상 기록/);
    expect(state.detailCalls).toBe(2);
  });

  test("refreshes the Work Log without displaying a stale job/run identity", async ({ page }) => {
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toBeVisible();
    const devSummary = page.locator('[data-qa="diag-detail-devinfo"] > summary');
    await devSummary.focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).toContainText(RUN_ID);
    state.stale = true;
    await expect(page.locator('[data-qa="work-log-refresh"]')).toBeEnabled();
    await page.locator('[data-qa="work-log-refresh"]').click();
    await expect.poll(() => state.listCalls).toBeGreaterThan(1);
    await expect.poll(() => state.detailCalls).toBeGreaterThan(1);
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).toContainText("run-cccccccccccccccccccccccc");
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).not.toContainText(RUN_ID);
  });

  test("the global Work Log refresh reloads an open detail with the same entry identity", async ({ page }) => {
    const state: FixtureState = { detailCalls: 0, listCalls: 0, errorOnce: false, stale: false, detailVersion: 0 };
    await installFixture(page, state);
    await openWorkLog(page, "light");
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).toContainText(RUN_ID);
    await expect(page.locator('[data-qa="diag-detail-refresh"]')).toHaveCount(0);

    state.detailVersion = 1;
    await page.locator('[data-qa="work-log-refresh"]').click();
    await expect.poll(() => state.listCalls).toBeGreaterThan(1);
    await expect.poll(() => state.detailCalls).toBeGreaterThan(1);
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).toContainText("run-dddddddddddddddddddddddd");
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).not.toContainText(RUN_ID);
  });
});
