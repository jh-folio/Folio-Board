import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFile } from "node:fs/promises";

const JOB_ID = "job-1";
const RUN_ID = "run-aaaaaaaaaaaaaaaaaaaaaaaa";

const WORK_LOG_ENTRY = {
  id: "wl_aaaaaaaaaaaaaaaaaaaaaaaa", jobId: JOB_ID, category: "task", kind: "agent_bridge", taskType: "companion", labelCode: "agent_task",
  status: "done", progress: 100, messageCode: "done", createdAt: "2026-09-05T00:00:00Z", startedAt: "2026-09-05T00:00:01Z",
  updatedAt: "2026-09-05T00:00:05Z", finishedAt: "2026-09-05T00:00:05Z", errorCode: null, generationMode: "rules", adapter: "rules",
  requestedMode: null, mode: "answer", attemptedEngine: "rules", finalEngine: "rules", fallbackReason: null, artifactTypes: [], artifactCount: 0,
  proposalId: null, proposalStatus: null, resultStatus: "done",
  queueWaitMs: null, contextMs: null, cliMs: null, postprocessMs: null, totalMs: null,
};
const DETAIL = {
  version: 1, runId: RUN_ID, diagnosticQuality: "complete", availabilityReason: "present", authorityState: "matched", authorityStatus: "done",
  record: {
    schemaVersion: 1, runId: RUN_ID, jobId: JOB_ID, requestId: "req-1", parentRunId: null, retryOfRunId: null, processEpoch: "epoch-1",
    featureCode: "agent_mode", routeCode: "agent_chat", taskType: "companion", authorityKind: "shared_job", appVersion: "0.6.0", buildId: "qa",
    os: "Windows", pythonVersion: "3.13", createdAt: "2026-09-05T00:00:01Z", updatedAt: "2026-09-05T00:00:05Z", finishedAt: "2026-09-05T00:00:05Z",
    elapsedMs: 4200, observedStatus: "done", attemptedEngine: "rules", finalEngine: "rules", adapter: "rules", fallbackReason: null,
    events: [{ seq: 1, eventId: "ev-1", stageId: "s-1", stageCode: "preflight", eventCode: "start", producerEpoch: "epoch-1", at: "2026-09-05T00:00:01Z", durationMs: null, errorId: null, count: 1 }],
    errors: [], firstFailure: null, terminalFailure: null, terminalObservation: { observedStatus: "done", observedAt: "2026-09-05T00:00:05Z", processEpoch: "epoch-1" },
    droppedEvents: 0, droppedErrors: 0, droppedIssues: 0, issueCodes: [], requiredProducerCoverage: "complete",
  }, warnings: [],
};
const EXPORT_PREVIEW = {
  version: 1, previewToken: "dxp1_fixture", selectedRunId: RUN_ID, includeParent: false, includeChildren: false, runCount: 1, byteCount: 220,
  summary: `Diagnostics export for ${RUN_ID}.\nIncluded 1 bounded run record(s); 0 issue(s).`,
  json: { schemaVersion: 1, exportType: "diagnostics", selectedRunId: RUN_ID, options: { includeParent: false, includeChildren: false }, runs: [{ runId: RUN_ID, relation: "selected", record: {} }], issues: [], summary: `Diagnostics export for ${RUN_ID}.` },
};

async function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installFixture(page: Page, requests: string[]) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    requests.push(`${route.request().method()} ${url.pathname}`);
    if (url.pathname === "/api/agent/work-log") return json(route, { schemaVersion: 1, storeRevision: 1, jobsStoreRevision: 1, total: 1, retention: { maxEntries: 200, maxDays: 30 }, entries: [WORK_LOG_ENTRY] });
    if (url.pathname === `/api/diagnostics/jobs/${JOB_ID}`) return json(route, DETAIL);
    if (url.pathname === `/api/diagnostics/runs/${RUN_ID}/export-preview`) return json(route, EXPORT_PREVIEW);
    return json(route, { detail: "fixture omitted" }, 404);
  });
}

async function openDetail(page: Page, theme: "light" | "dark") {
  await page.addInitScript((selectedTheme) => localStorage.setItem("folio.themePreference.v1", selectedTheme), theme);
  await page.goto(`/?theme=${theme}#/home`);
  await page.waitForLoadState("networkidle");
  await expect(page.locator('[data-qa="work-log"]')).toBeVisible();
  const collapse = page.locator(".work-log-collapse");
  if (!(await collapse.getAttribute("open"))) await collapse.locator(":scope > summary").click();
  await page.locator('[data-qa="diag-detail-toggle"]').click();
  await expect(page.locator('[data-qa="diag-detail-state"]')).toBeVisible();
}

for (const mode of [
  { name: "desktop-light", width: 1440, height: 1000, theme: "light" as const },
  { name: "desktop-dark", width: 1440, height: 1000, theme: "dark" as const },
  { name: "mobile-light", width: 375, height: 812, theme: "light" as const },
  { name: "mobile-dark", width: 375, height: 812, theme: "dark" as const },
]) {
  test(`D4 detail/export ${mode.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: mode.width, height: mode.height });
    const requests: string[] = [];
    await installFixture(page, requests);
    await openDetail(page, mode.theme);
    await page.locator('[data-qa="diag-export-toggle"]').click();
    await page.locator('[data-qa="diag-export-preview"]').click();
    await expect(page.locator('[data-qa="diag-export-summary"]')).toContainText("Included 1");
    const exportOptions = page.locator('.diag-export-options');
    await expect(exportOptions.locator('label')).toHaveCount(2);
    for (const label of await exportOptions.locator('label').all()) {
      await expect(label).toHaveCSS('white-space', 'nowrap');
      await expect(label.locator('input[type="checkbox"]')).toHaveCSS('width', '16px');
      await expect(label.locator('input[type="checkbox"]')).toHaveCSS('height', '16px');
    }
    const accessibility = await new AxeBuilder({ page }).include('[data-qa="diag-detail"]').analyze();
    expect(accessibility.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual([]);
    const exportPanel = page.locator('[data-qa="diag-export"]');
    await exportPanel.scrollIntoViewIfNeeded();
    await exportPanel.screenshot({ path: testInfo.outputPath(`${mode.name}.png`) });
    const before = requests.filter((request) => request.includes("/export")).length;
    const downloadPromise = page.waitForEvent("download");
    await page.locator('[data-qa="diag-export-download"]').click();
    const download = await downloadPromise;
    expect(await download.failure()).toBeNull();
    const downloadedPath = await download.path();
    expect(downloadedPath).toBeTruthy();
    expect(JSON.parse(await readFile(downloadedPath!, "utf8"))).toEqual(EXPORT_PREVIEW.json);
    expect(requests.filter((request) => request.includes("/export")).length).toBe(before);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });
}

test("D4 export preview is invalidated by a changed option", async ({ page }) => {
  const requests: string[] = [];
  await installFixture(page, requests);
  await openDetail(page, "light");
  await page.locator('[data-qa="diag-export-toggle"]').click();
  await page.locator('[data-qa="diag-export-preview"]').click();
  await expect(page.locator('[data-qa="diag-export-preview-panel"]')).toBeVisible();
  await page.locator('[data-qa="diag-export-toggle"]').click();
  await page.locator('[data-qa="diag-export-toggle"]').click();
  await page.locator('.diag-export-options input[type="checkbox"]').first().check();
  await expect(page.locator('[data-qa="diag-export-preview-panel"]')).toHaveCount(0);
  await expect(page.locator('[data-qa="diag-export-download"]')).toHaveCount(0);
});
