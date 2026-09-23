import { expect, test, type Page, type Route } from "@playwright/test";

const REQUEST_ID = "req_12345678-1234-4234-8234-123456789abc";
const REQUEST_ID_OTHER = "req_22345678-1234-4234-8234-123456789abc";
const REQUEST_ID_STALE = "req_42345678-1234-4234-8234-123456789abc";
const REQUEST_ID_LIST = "req_32345678-1234-4234-8234-123456789abc";
const RUN_ID = "run_abcdefab-cdef-4abc-8def-abcdefabcdef";
const RUN_ID_LIST = "run_bcdefabc-defa-4bcd-8efa-bcdefabcdefa";
const INVALID_RUN_ID = "run-not-a-uuid";
const BRIEFING_DATE = "2026-09-05";
const BRIEFING_DATE_NEXT = "2026-09-06";
const ANALYSIS_ID = "analysis-1";
const TOPIC_ID = "topic-1";
const JOB_ID = "job_12345678-1234-4234-8234-123456789abc";
let diagnosticFeature = "automation";
let diagnosticNextAction = "inspect_result";

const briefing = {
  id: `briefing-${BRIEFING_DATE}`,
  date: BRIEFING_DATE,
  reportDate: BRIEFING_DATE,
  marketScope: "us",
  kind: "daily",
  generatedAt: "2026-09-05T01:00:00Z",
  title: "미국장 브리핑",
  markdown: "# 미국장 브리핑\n\n안전한 QA fixture 본문입니다.",
};

const briefingNext = { ...briefing, id: `briefing-${BRIEFING_DATE_NEXT}`, date: BRIEFING_DATE_NEXT, reportDate: BRIEFING_DATE_NEXT, title: "다음 미국장 브리핑" };

const analysis = {
  id: ANALYSIS_ID,
  query: "NVDA",
  company: { ticker: "NVDA", name: "NVIDIA" },
  generatedAt: "2026-09-05T01:00:00Z",
  analysisStyle: "beginner",
  markdown: "# NVIDIA\n\n안전한 QA fixture 본문입니다.",
  sources: [],
};

const topic = {
  id: TOPIC_ID,
  topicKey: "power-grid",
  topicLabel: "전력망 투자",
  topic: "전력망 투자",
  date: BRIEFING_DATE,
  generatedAt: "2026-09-05T01:00:00Z",
  mode: "rules",
  saved: true,
  markdown: "# 전력망 투자\n\n안전한 QA fixture 본문입니다.",
  docCount: 0,
  memoryCount: 0,
  userContext: "",
  generation: null,
  sources: [],
};

const settings = {
  agent: { enabled: true, mode: "cli" },
  llm: { provider: "openai", providers: { openai: { label: "OpenAI", model: "gpt-5.6-sol", modelChoices: [{ value: "gpt-5.6-sol", label: "GPT-5.6 Sol" }] } } },
  fred: {}, bok: {}, dart: {}, toss: { enabled: false }, notion: {},
};

const agentSettings = {
  provider: "codex",
  adapters: [{ id: "codex", label: "Codex CLI", installed: true, available: true, authenticated: true, modelChoices: [{ value: "gpt-6-sol", label: "GPT-6 Sol" }], model: "gpt-6-sol" }],
};

const automation = { rss: { enabled: false, intervalMinutes: 60, saveFullText: true, retentionDays: 30 }, marketMemory: { enabled: false, intervalMinutes: 1440, runAfterRss: false }, briefingSchedules: [], missedRuns: { catchUpHours: 3 } };

const workLogEntry = {
  id: "wl_aaaaaaaaaaaaaaaaaaaaaaaa",
  jobId: JOB_ID,
  category: "task",
  kind: "agent_bridge",
  taskType: "companion",
  labelCode: "agent_task",
  status: "done",
  progress: 100,
  messageCode: "done",
  createdAt: "2026-09-05T00:00:01Z",
  startedAt: "2026-09-05T00:00:02Z",
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
  proposalId: "proposal-1",
  proposalStatus: "pending",
  resultStatus: "done",
  queueWaitMs: null,
  contextMs: null,
  cliMs: null,
  postprocessMs: null,
  totalMs: null,
};

const diagnosticDetail = {
  version: 1,
  runId: RUN_ID,
  diagnosticQuality: "complete",
  availabilityReason: "present",
  authorityState: "not_applicable",
  authorityStatus: "failed",
  record: {
    schemaVersion: 1,
    runId: RUN_ID,
    jobId: null,
    requestId: REQUEST_ID,
    parentRunId: null,
    retryOfRunId: null,
    processEpoch: "qa-epoch",
    featureCode: "automation",
    routeCode: "qa",
    taskType: null,
    authorityKind: "automation",
    appVersion: "qa",
    buildId: "qa",
    os: "Windows",
    pythonVersion: "3.13",
    createdAt: "2026-09-05T00:00:00Z",
    updatedAt: "2026-09-05T00:00:01Z",
    finishedAt: "2026-09-05T00:00:01Z",
    elapsedMs: 1000,
    observedStatus: "failed",
    attemptedEngine: "api",
    finalEngine: "none",
    adapter: "api",
    fallbackReason: null,
    events: [],
    errors: [],
    firstFailure: {
      errorId: "err-qa",
      stageId: "stage-qa",
      stageCode: "generate",
      errorCode: "qa_failure",
      reasonCode: "adapter_failed",
      exceptionCode: "request_failed",
      frames: [],
      confirmation: "observed",
      nextActionCode: "inspect_result",
      fingerprint: "qa-fingerprint",
    },
    terminalFailure: null,
    terminalObservation: { observedStatus: "failed", observedAt: "2026-09-05T00:00:01Z", processEpoch: "qa-epoch" },
    droppedEvents: 0,
    droppedErrors: 0,
    droppedIssues: 0,
    issueCodes: [],
    requiredProducerCoverage: "complete",
  },
  warnings: [],
};

function diagnosticDetailFor(featureCode: string, runId = RUN_ID) {
  return { ...diagnosticDetail, runId, record: { ...diagnosticDetail.record, runId, featureCode, firstFailure: { ...diagnosticDetail.record.firstFailure, nextActionCode: diagnosticNextAction } } };
}

async function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) {
  await route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
}

function errorHeaders(ids: "run" | "request" | "invalid" = "run") {
  if (ids === "run") return { "X-Folio-Request-Id": REQUEST_ID, "X-Folio-Run-Id": RUN_ID };
  if (ids === "request") return { "X-Folio-Request-Id": REQUEST_ID_OTHER };
  return { "X-Folio-Request-Id": "req-invalid", "X-Folio-Run-Id": INVALID_RUN_ID };
}

function listErrorHeaders() {
  return { "X-Folio-Request-Id": REQUEST_ID_LIST, "X-Folio-Run-Id": RUN_ID_LIST };
}

async function installApi(page: Page, handler: (route: Route, url: URL) => Promise<void>) {
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    await handler(route, url);
  });
}

async function commonApi(route: Route, url: URL): Promise<boolean> {
  if (url.pathname === `/api/diagnostics/runs/${RUN_ID}`) { await json(route, diagnosticDetailFor(diagnosticFeature, RUN_ID)); return true; }
  if (url.pathname === `/api/diagnostics/runs/${RUN_ID_LIST}`) { await json(route, diagnosticDetailFor(diagnosticFeature, RUN_ID_LIST)); return true; }
  if (url.pathname === "/api/settings") { await json(route, settings); return true; }
  if (url.pathname === "/api/agent-bridge/settings") { await json(route, agentSettings); return true; }
  if (url.pathname === "/api/automation/settings") { await json(route, automation); return true; }
  if (url.pathname === "/api/automation/runs") { await json(route, { items: [{ kind: "rss", status: "failed", startedAt: "2026-09-05T00:00:00Z", finishedAt: "2026-09-05T00:00:01Z", diagnosticRunId: RUN_ID }] }); return true; }
  if (url.pathname === "/api/obsidian/settings") { await json(route, {}); return true; }
  if (url.pathname === "/api/market-scope") { await json(route, { selected: ["us", "kr", "europe", "jp"], markets: ["us", "kr", "europe", "jp"].map((id) => ({ id, label: id })) }); return true; }
  if (url.pathname === "/api/rss/retention") { await json(route, { days: 30, cutoff: BRIEFING_DATE, files: 0, fileBytes: 0, estimatedIndexBytes: 0, reclaimableBytes: 0 }); return true; }
  if (url.pathname === "/api/agent/work-log" && url.searchParams.get("kind") !== "diagnostic") { await json(route, { schemaVersion: 1, storeRevision: 1, jobsStoreRevision: 1, entries: [workLogEntry], total: 1, retention: { maxDays: 30, maxEntries: 200 } }); return true; }
  if (url.pathname === "/api/cache/stats") { await json(route, { stats: [], total_mb: 0, stale_mb: 0 }); return true; }
  return false;
}

async function expectRunDetail(page: Page, expectedHref?: string, runId = RUN_ID) {
  const count = await page.locator("[data-qa=diag-detail]").count();
  await expectRunDetailAt(page, Math.max(count - 1, 0), expectedHref, runId);
}

async function expectRunDetailAt(page: Page, index: number, expectedHref?: string, runId = RUN_ID) {
  const detail = page.locator("[data-qa=diag-detail]").nth(index);
  await expect(detail).toBeVisible();
  await detail.locator("[data-qa=diag-detail-toggle]").click();
  await expect(detail.locator("[data-qa=diag-detail-state]")).toBeVisible();
  await detail.locator("[data-qa=diag-detail-devinfo] summary").click();
  await expect(detail).toContainText(runId);
  if (expectedHref) await expect(detail.locator("[data-qa=diag-detail-next-action-link]")).toHaveAttribute("href", expectedHref);
}

async function expectRequestOnly(page: Page) {
  const disclosure = page.locator("[data-qa=report-request-detail]").last();
  await expect(disclosure).toBeVisible();
  await disclosure.locator("[data-qa=report-request-detail-toggle]").click();
  await expect(disclosure.locator("[data-qa=report-request-id]")).toHaveText(REQUEST_ID_OTHER);
  await expect(disclosure.locator("[data-qa=diag-detail]")).toHaveCount(0);
}

test.describe("0.6 scoped diagnostic errors", () => {
  test("each saved report surface keeps list, read, delete, and export errors scoped", async ({ page }) => {
    type ReportCase = {
      key: "briefing" | "analysis" | "topic";
      listPath: string;
      detailPath: string;
      detailHash: string;
      listBody: unknown;
      detailBody: unknown;
      card: string;
      deletePath: string;
      exportPath: string;
      listHref: string;
      title: string;
    };
    const reportCases: ReportCase[] = [
      { key: "briefing", listPath: "/api/briefings/index", detailPath: `/api/briefings/${BRIEFING_DATE}`, detailHash: `#/briefing/${BRIEFING_DATE}/us/daily`, listBody: { items: [briefing], total: 1, offset: 0, limit: 100 }, detailBody: briefing, card: "button.briefing-archive-card", deletePath: `/api/briefings/${BRIEFING_DATE}`, exportPath: `/api/briefings/${BRIEFING_DATE}/export-notion`, listHref: "#/briefing", title: "미국장 브리핑" },
      { key: "analysis", listPath: "/api/analysis-reports", detailPath: `/api/analysis-reports/${ANALYSIS_ID}`, detailHash: `#/analysis/${ANALYSIS_ID}`, listBody: [analysis], detailBody: analysis, card: "button.report-feed-card.is-analysis", deletePath: `/api/analysis-reports/${ANALYSIS_ID}`, exportPath: "/api/export-notion/analysis", listHref: "#/analysis", title: "NVIDIA" },
      { key: "topic", listPath: "/api/topic-reports", detailPath: `/api/topic-reports/${TOPIC_ID}`, detailHash: `#/deep-research/${TOPIC_ID}`, listBody: [topic], detailBody: topic, card: `[data-report-id="${TOPIC_ID}"]`, deletePath: `/api/topic-reports/${TOPIC_ID}`, exportPath: "/api/export-notion/topic-report", listHref: "#/deep-research", title: "전력망 투자" },
    ];
    let phase: "list-error" | "list-ok" | "read-error" | "read-ok" | "delete-error" | "export-error" = "list-error";
    const calls: string[] = [];
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      const report = reportCases.find((candidate) => candidate.listPath === url.pathname || candidate.detailPath === url.pathname || candidate.deletePath === url.pathname || candidate.exportPath === url.pathname);
      if (report) {
        diagnosticFeature = report.key === "analysis" ? "company_analysis" : report.key === "topic" ? "topic_report" : "briefing";
        if (url.pathname === report.listPath && method === "GET") {
          calls.push(`${report.key}-list`);
          return phase === "list-error" ? json(route, { error: `${report.key}_list_failed` }, 503, errorHeaders("run")) : json(route, report.listBody);
        }
        if (url.pathname === report.detailPath && method === "GET") {
          calls.push(`${report.key}-read`);
          return phase === "read-error" ? json(route, { error: `${report.key}_read_failed` }, 404, errorHeaders("request")) : json(route, report.detailBody);
        }
        if (url.pathname === report.deletePath && method === "DELETE") {
          return phase === "delete-error" ? json(route, { error: `${report.key}_delete_failed` }, 503, errorHeaders("run")) : json(route, { deleted: true });
        }
        if (url.pathname === report.exportPath && method === "POST") {
          return phase === "export-error" ? json(route, { error: `${report.key}_export_failed` }, 502, errorHeaders("run")) : json(route, { title: "fixture" });
        }
      }

      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });

    for (const report of reportCases) {
      phase = "list-error";
      await page.goto(`/${report.key === "briefing" ? "#/briefing" : report.key === "analysis" ? "#/analysis" : "#/deep-research"}`);
      await page.reload(); // Reset retained inactive route disclosures between report cases.
      await expect(page.locator(report.key === "briefing" ? "[data-briefing-route]" : report.key === "analysis" ? "[data-company-analysis-route]" : "[data-deep-research-route]")).toBeVisible();
      await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
      await expectRunDetail(page, report.listHref);
      await expect(page.locator("[data-qa=diag-detail-retry]")).toHaveCount(0);

      phase = "list-ok";
      await page.reload();
      await expect(page.locator(report.card)).toBeVisible();
      phase = "read-error";
      await page.goto(`/${report.detailHash}`);
      await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
      await expectRequestOnly(page);
      const readCalls = calls.filter((item) => item === `${report.key}-read`).length;
      await page.waitForTimeout(300);
      expect(calls.filter((item) => item === `${report.key}-read`).length).toBe(readCalls);

      phase = "read-ok";
      await page.reload();
      await expect(page.getByText(report.title, { exact: false }).first()).toBeVisible();
      phase = "export-error";
      await page.getByRole("button", { name: "Notion으로 내보내기", exact: true }).click();
      await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
      await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(1);
      await expectRunDetail(page, report.listHref);

      phase = "list-ok";
      await page.goto(`/${report.key === "briefing" ? "#/briefing" : report.key === "analysis" ? "#/analysis" : "#/deep-research"}`);
      await expect(page.locator(report.card)).toBeVisible();
      phase = "delete-error";
      page.once("dialog", (dialog) => void dialog.accept());
      await page.getByRole("button", { name: /삭제/ }).first().click();
      await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
      await expectRunDetail(page, report.listHref);
    }
  });

  test("delete errors keep the selected report operation ID and never trigger a second delete", async ({ page }) => {
    let deleteCalls = 0;
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/briefings/index") return json(route, { items: [briefing], total: 1, offset: 0, limit: 100 });
      if (url.pathname === `/api/briefings/${BRIEFING_DATE}` && method === "GET") return json(route, briefing);
      if (url.pathname === `/api/briefings/${BRIEFING_DATE}` && method === "DELETE") {
        deleteCalls += 1;
        return json(route, { error: "delete_failed" }, 503, errorHeaders("run"));
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto("/#/briefing");
    await expect(page.getByRole("button", { name: /브리핑 삭제/ })).toBeVisible();
    page.once("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: /브리핑 삭제/ }).click();
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
    await expectRunDetail(page);
    expect(deleteCalls).toBe(1);
    await page.waitForTimeout(300);
    expect(deleteCalls).toBe(1);
  });

  test("generation and list failures retain separate valid run IDs; invalid IDs stay request-less", async ({ page }) => {
    diagnosticFeature = "briefing";
    let listCalls = 0;
    let generationCalls = 0;
    let malformedGeneration = false;
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/briefings/index") {
        listCalls += 1;
        return json(route, { error: "list_failed" }, 503, listErrorHeaders());
      }
      if (url.pathname === "/api/briefings" && method === "POST") {
        generationCalls += 1;
        // A second case below proves malformed headers do not create a link;
        // this response checks that a valid generation run is not overwritten
        // by the concurrently failing list request.
        return json(route, { error: "generation_failed" }, 502, malformedGeneration ? errorHeaders("invalid") : errorHeaders("run"));
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto("/#/briefing");
    await expect(page.locator("[data-briefing-route]")).toBeVisible();
    await page.getByRole("button", { name: "오늘 브리핑 생성", exact: true }).click();
    await expect(page.locator("[data-briefing-route] .react-dashboard-error").filter({ hasText: "generation_failed" })).toHaveCount(1);
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(2);
    await expectRunDetailAt(page, 0, "#/briefing", RUN_ID);
    await expectRunDetailAt(page, 1, "#/briefing", RUN_ID_LIST);
    expect(generationCalls).toBe(1);
    const listCount = listCalls;
    await page.waitForTimeout(300);
    expect(listCalls).toBe(listCount);

    // A malformed run/request header is ignored; there is no invented detail
    // link even though the HTTP failure itself remains visible to the user.
    malformedGeneration = true;
    await page.reload();
    await expect(page.locator("[data-briefing-route]")).toBeVisible();
    await page.getByRole("button", { name: "오늘 브리핑 생성", exact: true }).click();
    await expect(page.locator("[data-briefing-route] .react-dashboard-error").filter({ hasText: "generation_failed" })).toHaveCount(1);
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(1);
  });

  test("a stale report read cannot attach its old request ID after navigation", async ({ page }) => {
    let firstReadStarted!: () => void;
    let releaseFirstRead!: () => void;
    const firstRead = new Promise<void>((resolve) => { firstReadStarted = resolve; });
    const firstResponse = new Promise<void>((resolve) => { releaseFirstRead = resolve; });
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/briefings/index") return json(route, { items: [briefing, briefingNext], total: 2, offset: 0, limit: 100 });
      if (url.pathname === `/api/briefings/${BRIEFING_DATE}` && method === "GET") {
        firstReadStarted();
        await firstResponse;
        return json(route, { error: "stale_first_read" }, 404, { "X-Folio-Request-Id": REQUEST_ID_STALE });
      }
      if (url.pathname === `/api/briefings/${BRIEFING_DATE_NEXT}` && method === "GET") return json(route, { error: "current_second_read" }, 404, errorHeaders("request"));
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto(`/#/briefing/${BRIEFING_DATE}/us/daily`);
    await firstRead;
    await page.goto(`/#/briefing/${BRIEFING_DATE_NEXT}/us/daily`);
    await expectRequestOnly(page);
    releaseFirstRead();
    await page.waitForTimeout(300);
    await expect(page.locator("[data-qa=report-request-id]")).toHaveText(REQUEST_ID_OTHER);
  });

  test("transport failures stay neutral and do not create a retrying diagnostic link", async ({ page }) => {
    let listCalls = 0;
    await installApi(page, async (route, url) => {
      if (url.pathname === "/api/briefings/index") {
        listCalls += 1;
        return route.abort("failed");
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto("/#/briefing");
    await expect(page.locator("[data-briefing-route] .react-dashboard-error")).toContainText("서버 처리 결과를 확인할 수 없습니다.");
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(0);
    const callsAfterError = listCalls;
    await page.waitForTimeout(300);
    expect(listCalls).toBe(callsAfterError);
  });

  test("diagnostic next actions only navigate for explicit inspection/settings actions", async ({ page }) => {
    const actions = ["check_settings", "inspect_result", "unknown", "wait", "none", "explicit_retry"];
    await installApi(page, async (route, url) => {
      if (url.pathname === "/api/briefings/index") {
        diagnosticFeature = diagnosticNextAction === "check_settings" ? "automation" : "briefing";
        return json(route, { error: "diagnostic_action_fixture" }, 503, errorHeaders("run"));
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    for (const action of actions) {
      diagnosticNextAction = action;
      await page.goto("/#/briefing");
      await page.reload();
      await expect(page.locator("[data-qa=report-error-diagnostic]")).toBeVisible();
      const detail = page.locator("[data-qa=diag-detail]").last();
      await detail.locator("[data-qa=diag-detail-toggle]").click();
      await expect(detail.locator("[data-qa=diag-detail-state]")).toBeVisible();
      if (action === "check_settings") {
        await expect(detail.locator("[data-qa=diag-detail-next-action-link]")).toHaveAttribute("href", "#/settings");
      } else if (action === "inspect_result" || action === "none") {
        // A failed/unresolved run with no suggested action retains the existing
        // read-only inspect-result fallback; it never retries the operation.
        await expect(detail.locator("[data-qa=diag-detail-next-action-link]")).toHaveAttribute("href", "#/briefing");
      } else {
        await expect(detail.locator("[data-qa=diag-detail-next-action-link]")).toHaveCount(0);
      }
    }
  });

  test("settings distinguishes top-level read failure from a PanelNote save failure", async ({ page }) => {
    let readFailure = true;
    let saveCalls = 0;
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/settings" && method === "GET" && readFailure) return json(route, { error: "settings_read_failed" }, 503, errorHeaders("run"));
      if (url.pathname === "/api/settings" && method === "POST") {
        saveCalls += 1;
        return json(route, { error: "settings_save_failed" }, 503, errorHeaders("request"));
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto("/#/settings");
    await expect(page.locator("[data-settings-route]")).toBeVisible();
    await expect(page.locator("[data-settings-route] > .react-dashboard-error")).toContainText("settings_read_failed");
    diagnosticFeature = "automation";
    // The preceding next-action matrix intentionally leaves its last action
    // in the shared fixture; reset it so this settings-scoped case asserts the
    // explicit settings inspection link rather than inherited test state.
    diagnosticNextAction = "inspect_result";
    await expectRunDetail(page, "#/settings");
    const topErrorCount = await page.locator("[data-settings-route] > .react-dashboard-error").count();
    await page.waitForTimeout(300);
    expect(await page.locator("[data-settings-route] > .react-dashboard-error").count()).toBe(topErrorCount);

    // Recover the read before exercising a panel-local save. The panel note is
    // intentionally scoped to API settings and must not replace the page error.
    readFailure = false;
    await page.reload();
    await page.getByRole("button", { name: "연동", exact: true }).click();
    await expect(page.getByText("API 연동", { exact: true })).toBeVisible();
    await expect(page.locator("[data-settings-route] > .react-dashboard-error")).toHaveCount(0);
    await page.getByLabel("FRED API Key").fill("fixture-key");
    await page.getByRole("button", { name: "API 설정 저장", exact: true }).click();
    await expect(page.locator("[data-settings-route] .react-dashboard-error").last()).toContainText("settings_save_failed");
    await expectRequestOnly(page);
    expect(saveCalls).toBe(1);
  });

  test("work log list, clear, and proposal failures are bounded and do not auto-retry or cross IDs", async ({ page }) => {
    diagnosticFeature = "automation";
    diagnosticNextAction = "inspect_result";
    let listCalls = 0;
    let clearCalls = 0;
    let proposalCalls = 0;
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/agent/work-log" && url.searchParams.get("kind") !== "diagnostic") {
        listCalls += 1;
        return json(route, { error: "work_log_list_failed" }, 503, errorHeaders("request"));
      }
      if (url.pathname === "/api/agent/work-log/clear-preview" && method === "POST") {
        clearCalls += 1;
        return json(route, { error: "work_log_clear_failed" }, 503, errorHeaders("run"));
      }
      if (url.pathname === "/api/agent/proposals/proposal-1" && method === "GET") {
        proposalCalls += 1;
        return json(route, { error: "proposal_read_failed" }, 503, errorHeaders("request"));
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto("/#/home");
    await expect(page.locator("[data-qa=work-log]")).toBeVisible();
    const collapse = page.locator(".work-log-collapse");
    if (!(await collapse.getAttribute("open"))) await collapse.locator(":scope > summary").click();
    await expect(page.locator("[data-qa=work-log-error]")).toContainText("work_log_list_failed");
    await expectRequestOnly(page);
    const initialListCalls = listCalls;
    await page.waitForTimeout(300);
    expect(listCalls).toBe(initialListCalls);

    // A list failure has no row to act on; use a safe second response only for
    // the explicit recovery click, then make clear/proposal operations fail.
    await page.unroute("**/*");
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/agent/work-log" && url.searchParams.get("kind") !== "diagnostic") return json(route, { schemaVersion: 1, storeRevision: 1, jobsStoreRevision: 1, entries: [workLogEntry], total: 1, retention: { maxDays: 30, maxEntries: 200 } });
      if (url.pathname === "/api/agent/work-log/clear-preview" && method === "POST") { clearCalls += 1; return json(route, { error: "work_log_clear_failed" }, 503, errorHeaders("run")); }
      if (url.pathname === "/api/agent/proposals/proposal-1" && method === "GET") { proposalCalls += 1; return json(route, { error: "proposal_read_failed" }, 503, errorHeaders("request")); }
      if (url.pathname === "/api/diagnostics/runs") return json(route, { error: "diagnostic_list_failed" }, 503, errorHeaders("request"));
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.locator("[data-qa=work-log-refresh]").click();
    await expect(page.locator("[data-qa=work-log-item]")).toBeVisible();
    await page.getByRole("button", { name: "기록 숨기기" }).click();
    await expect(page.locator("[data-qa=work-log-clear-error]")).toContainText("work_log_clear_failed");
    await expectRunDetailAt(page, 0, "#/settings");
    await expect(page.locator("[data-qa=work-log-clear-dialog]")).toHaveCount(0);
    await page.getByRole("button", { name: "승인 검토" }).click();
    await expect(page.locator("[data-qa=work-log-proposal-error]")).toContainText("proposal_read_failed");
    await expectRequestOnly(page);
    expect(clearCalls).toBe(1);
    expect(proposalCalls).toBe(1);
    await page.waitForTimeout(300);
    expect(clearCalls).toBe(1);
    expect(proposalCalls).toBe(1);
    await page.locator("[data-qa=work-log-diag-filters] > summary").click();
    await page.locator("[data-qa=work-log-diag-all]").click();
    await expect(page.locator("[data-qa=work-log-diag-error]")).toContainText("diagnostic_list_failed");
    await expectRequestOnly(page);
  });

  test("Deep Research delete transport loss stays neutral without a duplicate generation recovery prompt", async ({ page }) => {
    let deleteCalls = 0;
    await installApi(page, async (route, url) => {
      const method = route.request().method();
      if (url.pathname === "/api/topic-reports" && method === "GET") return json(route, [topic]);
      if (url.pathname === `/api/topic-reports/${TOPIC_ID}` && method === "DELETE") {
        deleteCalls += 1;
        return route.abort("failed");
      }
      const common = await commonApi(route, url);
      if (common) return common;
      return json(route, { detail: "fixture route omitted" }, 404);
    });
    await page.goto("/#/deep-research");
    await expect(page.locator(`[data-report-id="${TOPIC_ID}"]`)).toBeVisible();
    page.once("dialog", (dialog) => void dialog.accept());
    await page.getByRole("button", { name: /삭제/ }).click();
    await expect(page.locator("[data-qa=dr-report-action-error]")).toContainText("서버 처리 결과를 확인할 수 없습니다.");
    await expect(page.locator("[data-qa=dr-report-action-error]")).not.toContainText("다시 시도할 수 있습니다");
    await expect(page.locator("[data-qa=dr-error-generation]")).toHaveCount(0);
    await expect(page.locator("[data-qa=report-error-diagnostic]")).toHaveCount(0);
    expect(deleteCalls).toBe(1);
  });
});
