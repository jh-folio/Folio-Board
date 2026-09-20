import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const RUN_FAILED = "run_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const RUN_FALLBACK = "run_cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const RUN_PERIOD = "run_dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const RUN_AUTOMATION = "run_eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const RUN_PAGE_2 = "run_ffffffff-ffff-4fff-8fff-ffffffffffff";
const JOB_ID = "job-1";
const PROPOSAL_ID = "abcdefabcdef";

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
  runId: RUN_FAILED,
  diagnosticQuality: "complete",
  availabilityReason: "present",
  authorityState: "not_applicable",
  authorityStatus: "succeeded",
  record: {
    schemaVersion: 1,
    runId: RUN_FAILED,
    jobId: null,
    requestId: "req-1",
    parentRunId: null,
    retryOfRunId: null,
    processEpoch: "epoch-1",
    featureCode: "automation",
    routeCode: "automation_run",
    taskType: null,
    authorityKind: "automation",
    appVersion: "qa-v1",
    buildId: "qa",
    os: "Windows",
    pythonVersion: "3.13",
    createdAt: "2026-09-05T00:00:01Z",
    updatedAt: "2026-09-05T00:00:05Z",
    finishedAt: "2026-09-05T00:00:05Z",
    elapsedMs: 4200,
    observedStatus: "failed",
    attemptedEngine: "api",
    finalEngine: "none",
    adapter: "api",
    fallbackReason: null,
    events: [
      { seq: 1, eventId: "ev-1", stageId: "s-1", stageCode: "generate", eventCode: "failure", producerEpoch: "epoch-1", at: "2026-09-05T00:00:05Z", durationMs: null, errorId: "err-1", count: 1 },
    ],
    errors: [],
    firstFailure: {
      errorId: "err-1",
      stageId: "s-1",
      stageCode: "generate",
      errorCode: "adapter_failed",
      reasonCode: "adapter_failed",
      exceptionCode: "subprocess_exit",
      frames: [{ moduleCode: "automation", functionCode: "run", line: 42 }],
      confirmation: "observed",
      nextActionCode: "explicit_retry",
      fingerprint: "fp-1",
    },
    terminalFailure: null,
    terminalObservation: { observedStatus: "failed", observedAt: "2026-09-05T00:00:05Z", processEpoch: "epoch-1" },
    droppedEvents: 0,
    droppedErrors: 0,
    droppedIssues: 0,
    issueCodes: [],
    requiredProducerCoverage: "complete",
  },
  warnings: [],
};

type DiagItemOverrides = Partial<typeof DETAIL.record> & Partial<{
  runId: string;
  createdAt: string;
  finishedAt: string | null;
  observedStatus: string;
  observedOutcome: "failed" | "succeeded" | "cancelled" | "running" | "unknown";
  outcome: "failed" | "succeeded" | "cancelled" | "running" | "unknown" | null;
  featureCode: string;
  routeCode: string;
  authorityKind: "shared_job" | "automation" | "direct" | "recovery";
  authorityState: "matched" | "changed" | "unavailable" | "not_applicable";
  authorityStatus: string | null;
  taskType: string | null;
  jobId: string | null;
  workLogId: string | null;
  diagnosticQuality: "complete" | "partial";
  adapter: string | null;
  attemptedEngine: string | null;
  finalEngine: string | null;
  fallbackReason: string | null;
  fallbackObserved: boolean | null;
  failureReasonCode: string | null;
  failureStageCode: string | null;
}>;

function item(overrides: DiagItemOverrides = {}) {
  return {
    runId: RUN_FAILED,
    createdAt: "2026-09-05T00:00:01Z",
    finishedAt: "2026-09-05T00:00:05Z",
    observedStatus: "failed",
    observedOutcome: "failed" as const,
    outcome: "failed" as const,
    featureCode: "automation",
    routeCode: "automation_run",
    authorityKind: "automation" as const,
    authorityState: "matched" as const,
    authorityStatus: "failed",
    taskType: null,
    jobId: null,
    workLogId: null,
    diagnosticQuality: "complete" as const,
    adapter: "api",
    attemptedEngine: "api",
    finalEngine: "none",
    fallbackReason: null,
    fallbackObserved: null,
    failureReasonCode: "adapter_failed",
    failureStageCode: "generate",
    ...overrides,
  };
}

type Deferred = { promise: Promise<void>; resolve: () => void };
function deferred(): Deferred {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

type FixtureState = {
  listQueries: string[];
  detailCalls: number;
  failNextFilteredQuery?: boolean;
  failNextRefresh?: boolean;
  initialWarnings?: boolean;
  initialWarningsServed?: boolean;
  partialEmpty?: boolean;
  cursor409?: boolean;
  cursorRecovered?: boolean;
  pageMode?: boolean;
  pendingLegacy?: Deferred;
  pendingReset?: Deferred;
  pendingMore?: Deferred;
  detailVersion?: number;
};

async function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function response(items: readonly unknown[], options: { nextCursor?: string | null; truncated?: boolean; complete?: boolean; errors?: readonly { code: string }[] } = {}) {
  return {
    version: 1,
    snapshotAt: "2026-09-05T00:01:00Z",
    items,
    nextCursor: options.nextCursor ?? null,
    truncated: options.truncated ?? false,
    scan: { entriesScanned: items.length, runsScanned: items.length, complete: options.complete ?? true, deadlineMs: 250 },
    errors: options.errors ?? [],
  };
}

async function installFixture(page: Page, state: FixtureState) {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/agent/work-log") {
      if (state.pendingLegacy) await state.pendingLegacy.promise;
      return json(route, { schemaVersion: 1, storeRevision: 1, jobsStoreRevision: 1, retention: { maxEntries: 200, maxDays: 30 }, total: 1, entries: [WORK_LOG_ENTRY] });
    }
    if (url.pathname === "/api/diagnostics/runs") {
      const query = url.search;
      state.listQueries.push(url.pathname + query);
      const cursor = url.searchParams.get("cursor");
      const hasFilter = Boolean(url.searchParams.get("outcome") || url.searchParams.get("fallback") || url.searchParams.get("from"));
      if (state.pendingReset && !cursor) await state.pendingReset.promise;
      if (state.pendingMore && cursor === "page-1") await state.pendingMore.promise;
      if (state.failNextFilteredQuery && hasFilter && !cursor) {
        state.failNextFilteredQuery = false;
        return json(route, { error: "diagnostic_query_failed" }, 503);
      }
      if (state.failNextRefresh && url.searchParams.get("outcome") === "failed" && !cursor) {
        state.failNextRefresh = false;
        return json(route, { error: "diagnostic_query_failed" }, 503);
      }
      if (state.cursor409 && cursor === "stale-cursor") {
        state.cursor409 = false;
        state.cursorRecovered = true;
        return json(route, { error: "cursor_expired" }, 409);
      }
      if (state.partialEmpty) {
        state.partialEmpty = false;
        return json(route, response([], { truncated: true, complete: false, errors: [{ code: "read_failed" }] }));
      }
      if (state.cursorRecovered && !cursor) {
        state.cursorRecovered = false;
        return json(route, response([item()]));
      }
      if (state.pageMode && url.searchParams.get("outcome") === "failed" && !cursor) {
        return json(route, response([item()], { nextCursor: "page-1" }));
      }
      if (state.pageMode && url.searchParams.get("fallback") === "observed" && !cursor) {
        return json(route, response([item({ runId: RUN_FALLBACK, fallbackObserved: true, fallbackReason: "engine_unavailable", finalEngine: "rules" })], { nextCursor: "page-1" }));
      }
      if (state.cursor409 && url.searchParams.get("outcome") === "failed" && !cursor) {
        return json(route, response([item()], { nextCursor: "stale-cursor" }));
      }
      if (cursor === "page-1") return json(route, response([item({ runId: RUN_PAGE_2, featureCode: "rss", failureReasonCode: null, failureStageCode: null, observedStatus: "succeeded", observedOutcome: "succeeded", outcome: "succeeded" })], { nextCursor: "page-2" }));
      if (url.searchParams.get("from")) return json(route, response([item({ runId: RUN_PERIOD, featureCode: "index" })]));
      if (url.searchParams.get("fallback") === "observed") return json(route, response([item({ runId: RUN_FALLBACK, fallbackObserved: true, fallbackReason: "engine_unavailable", finalEngine: "rules" })]));
      if (state.initialWarnings && !state.initialWarningsServed && url.searchParams.get("outcome") === "failed" && !cursor) {
        state.initialWarningsServed = true;
        return json(route, response([item()], { errors: [{ code: "read_failed" }] }));
      }
      if (url.searchParams.get("outcome") === "failed") return json(route, response([item()]));
      return json(route, response([item({ runId: RUN_AUTOMATION, featureCode: "automation" })]));
    }
    const runMatch = url.pathname.match(/^\/api\/diagnostics\/runs\/([^/]+)$/);
    if (runMatch) {
      state.detailCalls += 1;
      const runId = decodeURIComponent(runMatch[1]);
      return json(route, {
        ...DETAIL,
        runId,
        record: {
          ...DETAIL.record,
          runId,
          elapsedMs: state.detailVersion ? 8400 : 4200,
          appVersion: state.detailVersion ? "qa-v2" : "qa-v1",
        },
      });
    }
    if (url.pathname === `/api/agent/proposals/${PROPOSAL_ID}` && route.request().method() === "POST") {
      return json(route, { marketScope: "none", proposalId: PROPOSAL_ID, reportId: "report-1", reportKind: "briefing", status: "applied", targetRevision: null });
    }
    return json(route, { detail: "diagnostic-list fixture omits this route" }, 404);
  });
}

async function openWorkLog(page: Page, theme: "light" | "dark") {
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem("folio.themePreference.v1", selectedTheme);
    localStorage.setItem("folio.react.agentClosed", "1");
  }, theme);
  await page.goto("/?theme=" + theme + "#/home");
  await page.waitForLoadState("networkidle");
  await expect(page.locator('[data-qa="work-log"]')).toBeVisible();
  const collapse = page.locator(".work-log-collapse");
  if (!(await collapse.getAttribute("open"))) await collapse.locator(":scope > summary").click();
  await expect(page.locator('[data-qa="work-log-item"]')).toBeVisible();
  await page.locator('[data-qa="work-log-diag-filters"] > summary').click();
}

async function openFailedDiagnostics(page: Page, theme: "light" | "dark", state: FixtureState) {
  await installFixture(page, state);
  await openWorkLog(page, theme);
  await page.locator('[data-qa="work-log-diag-failed"]').click();
  await expect(page.locator('[data-qa="work-log-diag-item"]')).toBeVisible();
}

async function settleCapture(page: Page) {
  await page.mouse.move(8, 8);
  await page.waitForTimeout(100);
}

for (const theme of ["light", "dark"] as const) {
  test.describe(`D3 diagnostic list ${theme}`, () => {
    test.beforeEach(async ({ page }, testInfo) => {
      if (testInfo.project.name.includes("mobile")) await page.setViewportSize({ width: 375, height: 812 });
    });

    test(`captures baseline and scoped axe (${theme})`, async ({ page }, testInfo) => {
      const state: FixtureState = { listQueries: [], detailCalls: 0 };
      await openFailedDiagnostics(page, theme, state);
      await settleCapture(page);
      const viewport = testInfo.project.name.includes("mobile") ? "mobile-375" : "desktop";
      const baselinePath = resolve(process.cwd(), `../.planning/0.6-b0/captures/diagnostic-list-${theme}-${viewport}-baseline.png`);
      if (!existsSync(baselinePath)) await page.screenshot({ path: baselinePath, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      const result = await new AxeBuilder({ page }).include('[data-qa="work-log"] .work-log-diag-filters, [data-qa="work-log-diag-list"]').analyze();
      expect(result.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual([]);
    });

    test(`captures final and scoped axe (${theme})`, async ({ page }, testInfo) => {
      const state: FixtureState = { listQueries: [], detailCalls: 0 };
      await openFailedDiagnostics(page, theme, state);
      await settleCapture(page);
      const viewport = testInfo.project.name.includes("mobile") ? "mobile-375" : "desktop";
      await page.screenshot({ path: resolve(process.cwd(), `../.planning/0.6-b0/captures/diagnostic-list-${theme}-${viewport}-final.png`), fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      const result = await new AxeBuilder({ page }).include('[data-qa="work-log"] .work-log-diag-filters, [data-qa="work-log-diag-list"]').analyze();
      expect(result.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual([]);
    });
  });
}

test.describe("D3 diagnostic list contracts", () => {
  test("switches filters and clears stale rows after a failed transition", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0 };
    await openFailedDiagnostics(page, "light", state);
    await expect(page.locator('[data-qa="work-log-diag-feature"]')).toHaveText("자동화");
    state.failNextFilteredQuery = true;
    await page.locator('[data-qa="work-log-diag-fallback"]').click();
    await expect(page.locator('[data-qa="work-log-diag-error"]')).toContainText("diagnostic_query_failed");
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toHaveCount(0);
    await page.locator('[data-qa="work-log-diag-retry"]').click();
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toHaveCount(1);
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toContainText("대체 실행");
    await page.locator('[data-qa="work-log-diag-period"]').selectOption("7d");
    await expect(page.locator('[data-qa="work-log-diag-feature"]')).toHaveText("자료 인덱스");
    expect(state.listQueries.some((query) => query.includes("outcome=failed") && query.includes("fallback=observed"))).toBeTruthy();
    expect(state.listQueries.some((query) => query.includes("from=") && query.includes("outcome=failed"))).toBeTruthy();
  });

  test("keeps an explicit all-runs diagnostic entry reachable when filters are cleared", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0 };
    await openFailedDiagnostics(page, "light", state);
    await page.locator('[data-qa="work-log-diag-failed"]').click();
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toHaveCount(1);
    await expect(page.locator('[data-qa="work-log-diag-feature"]')).toHaveText("자동화");
    await expect.poll(() => state.listQueries.some((query) => {
      const url = new URL(`http://127.0.0.1${query}`);
      return url.pathname === "/api/diagnostics/runs" && !url.searchParams.has("outcome") && !url.searchParams.has("fallback") && !url.searchParams.has("from") && !url.searchParams.has("to") && !url.searchParams.has("cursor");
    })).toBeTruthy();
    const lastQuery = new URL(`http://127.0.0.1${state.listQueries.findLast((query) => !new URL(`http://127.0.0.1${query}`).searchParams.has("outcome")) || ""}`);
    expect(lastQuery.pathname).toBe("/api/diagnostics/runs");
    for (const name of ["outcome", "fallback", "from", "to", "cursor"]) expect(lastQuery.searchParams.has(name)).toBeFalsy();
  });

  test("appends cursor pages without duplicates and disables more while a reset is pending", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0, pageMode: true };
    await openFailedDiagnostics(page, "light", state);
    // The fixture exposes a cursor only for the first filtered page.
    const first = state.listQueries.length;
    await expect(page.locator('[data-qa="work-log-diag-more"]')).toBeVisible();
    await page.locator('[data-qa="work-log-diag-more"]').click();
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toHaveCount(2);
    expect(state.listQueries.length).toBeGreaterThan(first);

    const reset = deferred();
    state.pendingReset = reset;
    // Re-enter the first filtered view, then change filter while its reset is in flight.
    await page.locator('[data-qa="work-log-diag-fallback"]').click();
    await expect.poll(async () => {
      const more = page.locator('[data-qa="work-log-diag-more"]');
      return (await more.count()) === 0 || await more.isDisabled();
    }).toBeTruthy();
    reset.resolve();
  });

  test("recovers once from a 409 cursor and preserves partial scan errors with empty items", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0, cursor409: true };
    await openFailedDiagnostics(page, "light", state);
    await expect(page.locator('[data-qa="work-log-diag-more"]')).toBeVisible();
    await page.locator('[data-qa="work-log-diag-more"]').click();
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toHaveCount(1);
    await expect.poll(() => state.listQueries.filter((query) => !query.includes("cursor=")).length).toBeGreaterThanOrEqual(2);
    expect(state.listQueries.some((query) => query.includes("cursor=stale-cursor"))).toBeTruthy();

    state.partialEmpty = true;
    await page.locator('[data-qa="work-log-diag-fallback"]').click();
    await expect(page.locator('[data-qa="work-log-diag-partial"]')).toContainText("일부 실행");
    await expect(page.locator('[data-qa="work-log-diag-continue"]')).toBeVisible();
    await expect(page.locator('[data-qa="work-log-diag-empty"]')).toHaveCount(0);
  });

  test("reloads an open diagnostic detail from the global Work Log refresh", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0 };
    await openFailedDiagnostics(page, "light", state);
    await page.locator('[data-qa="diag-detail-toggle"]').click();
    await expect(page.locator('[data-qa="diag-detail-state"]')).toBeVisible();
    await page.locator('[data-qa="diag-detail-devinfo"] > summary').click();
    await expect(page.locator('[data-qa="diag-detail-devinfo"]')).toContainText(RUN_FAILED);
    const detailCallsBefore = state.detailCalls;
    state.detailVersion = 1;
    await page.locator('[data-qa="work-log-refresh"]').click();
    await expect.poll(() => state.detailCalls).toBeGreaterThan(detailCallsBefore);
    await expect(page.locator('[data-qa="diag-detail-elapsed"]')).toHaveText("8초");
  });

  test("keeps the snapshot, rows, and loss warning when a same-query refresh fails", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0, initialWarnings: true };
    await openFailedDiagnostics(page, "light", state);
    await expect(page.locator('[data-qa="work-log-diag-partial"]')).toBeVisible();
    const snapshot = await page.locator('[data-qa="work-log-diag-snapshot"]').textContent();
    state.failNextRefresh = true;
    await page.locator('[data-qa="work-log-refresh"]').click();
    await expect(page.locator('[data-qa="work-log-diag-error"]')).toContainText("diagnostic_query_failed");
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toHaveCount(1);
    await expect(page.locator('[data-qa="work-log-diag-snapshot"]')).toHaveText(snapshot || "");
    await expect(page.locator('[data-qa="work-log-diag-partial"]')).toBeVisible();
  });

  test("refreshes the active diagnostic list after a global Work Log lifecycle signal", async ({ page }) => {
    const state: FixtureState = { listQueries: [], detailCalls: 0 };
    await openFailedDiagnostics(page, "light", state);
    const listCallsBefore = state.listQueries.length;
    await page.evaluate(() => window.dispatchEvent(new CustomEvent("folio:proposal-lifecycle")));
    await expect.poll(() => state.listQueries.length).toBeGreaterThan(listCallsBefore);
  });

  test("refreshes diagnostics when the parent Work Log refreshKey changes", async ({ page }) => {
    // Proposal approval normally emits the lifecycle signal and bumps the parent
    // refreshKey together. Suppress only that signal here so this test proves the
    // prop-driven refresh path independently from the lifecycle test above.
    await page.addInitScript(() => {
      const dispatch = window.dispatchEvent.bind(window);
      window.dispatchEvent = (event: Event) => event.type === "folio:proposal-lifecycle" || dispatch(event);
    });
    await page.addInitScript((proposalId) => {
      localStorage.setItem("folio.agentHome.thread.v1", JSON.stringify({
        version: 1,
        updatedAt: "2026-09-05T00:00:00Z",
        messages: [{
          id: "assistant-proposal",
          role: "assistant",
          text: "검토 가능한 제안입니다.",
          proposal: { id: proposalId, summary: "QA 제안", diff: "- old\\n+ new", artifactKind: "briefing", artifactId: "report-1" },
          proposalStatus: "pending",
        }],
      }));
    }, PROPOSAL_ID);
    const state: FixtureState = { listQueries: [], detailCalls: 0 };
    await openFailedDiagnostics(page, "light", state);
    await expect(page.locator('[data-qa="proposal-approve"]')).toBeVisible();
    const listCallsBefore = state.listQueries.length;
    await page.locator('[data-qa="proposal-approve"]').click();
    await expect(page.locator('[data-qa="wb-happy-applied"]')).toBeVisible();
    await expect.poll(() => state.listQueries.length).toBeGreaterThan(listCallsBefore);
  });

  test("leaving a deferred legacy load does not keep the active diagnostics view busy", async ({ page }) => {
    const pendingLegacy = deferred();
    const state: FixtureState = { listQueries: [], detailCalls: 0, pendingLegacy };
    await installFixture(page, state);
    await page.addInitScript((selectedTheme) => {
      localStorage.setItem("folio.themePreference.v1", selectedTheme);
      localStorage.setItem("folio.react.agentClosed", "1");
    }, "light");
    await page.goto("/?theme=light#/home", { waitUntil: "domcontentloaded" });
    await expect(page.locator('[data-qa="work-log"]')).toBeVisible();
    const collapse = page.locator(".work-log-collapse");
    if (!(await collapse.getAttribute("open"))) await collapse.locator(":scope > summary").click();
    await page.locator('[data-qa="work-log-diag-filters"] > summary').click();
    await page.locator('[data-qa="work-log-diag-all"]').click();
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toBeVisible();
    await expect(page.locator('[data-qa="work-log-refresh"]')).toBeEnabled();
    pendingLegacy.resolve();
  });

  test("keeps filter and detail controls keyboard reachable at 375px", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    const state: FixtureState = { listQueries: [], detailCalls: 0 };
    await openFailedDiagnostics(page, "dark", state);
    const filter = page.locator('[data-qa="work-log-diag-fallback"]');
    await filter.focus();
    await expect(filter).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(filter).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('[data-qa="work-log-diag-item"]')).toBeVisible();
    const detailToggle = page.locator('[data-qa="diag-detail-toggle"]').first();
    await detailToggle.focus();
    await expect(detailToggle).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-qa="diag-detail-state"]')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });
});
