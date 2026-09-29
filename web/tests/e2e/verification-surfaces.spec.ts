import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * 0.6 Stage C — 검증 루프가 보이는 두 표면의 품질 게이트.
 *
 * 기존 route sweep은 API를 404로 막아 **빈 상태**만 본다. 판정 배지·무소식 배지·
 * 경고 문구는 데이터가 있어야 그려지므로, 여기서는 fixture를 물려 실제로 그려진
 * 화면을 axe·대비·오버플로로 검사한다.
 */

const VERIFICATION_FIXTURE = {
  asOf: "2026-08-31",
  states: [
    {
      stateId: "state-1",
      stateKey: "ai_power",
      label: "AI 데이터센터 전력 병목",
      status: "active",
      momentum: "strengthening",
      momentumLabel: "강화",
      evidenceCounts: { d7: 2, d30: 6, d90: 12 },
      lastEvidenceAt: "2026-08-29",
      lastConfirmedAt: "2026-08-29",
      lastChallengedAt: "",
      silence: { days: 2, level: "active", label: "2일 전 근거", note: "" },
      checkpoints: [
        {
          id: "cp_a",
          item: "전력 설비 기업 실적 가이던스 상향",
          direction: "supporting",
          status: "confirmed",
          statusLabel: "확인됨",
          dueBy: null,
          lastVerdict: {
            verdict: "confirmed",
            verdictLabel: "확인됨",
            at: "2026-08-29T00:00:00+00:00",
            evidence: [{ date: "2026-08-29", title: "전력기기 수주잔고 사상 최대", role: "supporting" }],
          },
          historyCount: 1,
        },
        {
          id: "cp_b",
          item: "착공 지연 보도",
          direction: "challenging",
          status: "challenged",
          statusLabel: "반증 신호",
          dueBy: "2026-09-30",
          lastVerdict: {
            verdict: "challenged",
            verdictLabel: "반증",
            at: "2026-08-28T00:00:00+00:00",
            evidence: [{ date: "2026-08-28", title: "대형 데이터센터 착공 연기", role: "challenging" }],
          },
          historyCount: 1,
        },
      ],
      checkpointCounts: { open: 0, confirmed: 1, challenged: 1, expired: 0 },
      unverifiableCount: 1,
      templates: ["관련 가격 반응이 이어지는지 확인"],
      timeline: [
        { at: "2026-08-29T00:00:00+00:00", kind: "checkpoint", from: "open", to: "confirmed", reason: "규칙 판정 confirmed", evidenceCount: 2 },
        { at: "2026-08-27T00:00:00+00:00", kind: "status", from: "active", to: "overridden", reason: "새 내러티브로 교체", evidenceCount: 0 },
        { at: "2026-08-25T00:00:00+00:00", kind: "evidence_count", from: '{"d7":0,"d30":2,"d90":6}', to: '{"d7":1,"d30":4,"d90":9}', reason: "새 근거 반영", evidenceCount: 1 },
        { at: "2026-08-20T00:00:00+00:00", kind: "momentum", from: "stable", to: "strengthening", reason: "30일 근거 비중", evidenceCount: 6 },
      ],
    },
    {
      stateId: "state-2",
      stateKey: "middle_east_energy_risk",
      label: "중동 에너지 리스크",
      status: "watch",
      momentum: "fading",
      momentumLabel: "약화",
      evidenceCounts: { d7: 0, d30: 1, d90: 8 },
      lastEvidenceAt: "2026-07-25",
      lastConfirmedAt: "",
      lastChallengedAt: "",
      silence: {
        days: 37,
        level: "dormant",
        label: "37일 무소식 · 정리 후보",
        note: "30일 넘게 새 근거가 없습니다. 상태를 내릴지는 직접 확인해 정하세요 — 자동으로 바뀌지 않습니다.",
      },
      checkpoints: [],
      checkpointCounts: { open: 0, confirmed: 0, challenged: 0, expired: 0 },
      unverifiableCount: 0,
      templates: [],
      timeline: [],
    },
  ],
  summary: { stateCount: 2, checkpointCount: 2, confirmed: 1, challenged: 1, cooling: 1, unverifiable: 1 },
};

const WORKSPACE_FIXTURE = {
  ticker: "NVDA",
  hasThesis: true,
  reasonKind: "interest",
  reasonRevision: { revisionId: "nvda-reason-1", revision: 1, recordedAt: "2026-08-20T00:00:00Z", content: { core_thesis: "AI 가속기 수요가 최소 2년은 이어진다.", falsification_triggers: ["대형 고객이 자체 칩으로 이동"] }, basisRefs: [], conditionResponse: "written", fieldPresence: { conviction: true, review_cycle: true } },
  reasonHistory: [],
  reasonStatus: "reviewed",
  reviewEvents: [],
  reasonConnections: [],
  news: {
    items: [{ key: "https://example.com/nvda-custom-chip", title: "대형 고객, 자체 AI 칩 비중 확대", date: "2026-08-26",
      url: "https://example.com/nvda-custom-chip", condition: "대형 고객이 자체 칩으로 이동" }],
    count: 1,
    since: "2026-08-20T00:00:00Z",
    searchReady: true,
    keywords: ["자체 칩", "custom chip"],
    lastDecisionAt: "",
  },
  thesis: {
    ticker: "NVDA",
    company: "NVIDIA",
    coreThesis: "AI 가속기 수요가 최소 2년은 이어진다.",
    keyAssumptions: ["데이터센터 자본지출 유지"],
    supportingSignals: [],
    weakeningSignals: [],
    falsificationTriggers: ["대형 고객이 자체 칩으로 이동"],
    keyMetrics: ["데이터센터 매출"],
    linkedRegimes: ["ai_power"],
    reviewCycle: "quarterly",
    conviction: "high",
    status: "active",
    lastReviewedAt: "2026-08-20T00:00:00+00:00",
    notePath: "native_note:note-1",
  },
  ownership: {
    source: "native_note",
    appOwned: true,
    vaultNote: { title: "NVDA thesis", relPath: "Thesis/NVDA.md" },
    syncPaused: true,
    message: "이 관심 이유는 Vault에서 더 이상 갱신되지 않습니다. 앱에서 만든 내용이 우선이며, Vault 노트를 반영하려면 그 노트를 이유로 다시 등록하세요.",
  },
  latestDelta: {
    deltaId: "d1",
    verdict: "weakened",
    verdictLabel: "약화",
    generatedAt: "2026-08-28T00:00:00+00:00",
    period: "90d",
    summary: "가이던스는 유지됐지만 고객 집중도가 높아졌다.",
    supportingEvidence: [{ title: "데이터센터 매출 최고치", source: "Reuters", date: "2026-08-20", reason: "" }],
    counterEvidence: [{ title: "대형 고객 자체 칩 확대", source: "Bloomberg", date: "2026-08-26", reason: "핵심 가정과 충돌" }],
    contradictions: [],
    uncertainties: ["다음 실적 발표 전"],
  },
  checkpoints: {
    structured: [
      {
        id: "cp_t",
        item: "데이터센터 매출 가이던스 상향",
        direction: "supporting",
        status: "confirmed",
        statusLabel: "확인됨",
        dueBy: null,
        lastVerdict: {
          verdict: "confirmed",
          verdictLabel: "확인됨",
          at: "2026-08-25T00:00:00+00:00",
          evidence: [{ date: "2026-08-24", title: "엔비디아 가이던스 상향" }],
        },
        history: [{ at: "2026-08-25T00:00:00+00:00", from: "open", to: "confirmed", verdict: "confirmed", verdictLabel: "확인됨" }],
      },
    ],
    templates: [],
    unverifiableCount: 0,
    counts: { open: 0, confirmed: 1, challenged: 0, expired: 0 },
  },
  regimeAlerts: [
    {
      stateId: "state-1",
      stateKey: "ai_power",
      label: "AI 데이터센터 전력 병목",
      status: "active",
      momentum: "strengthening",
      reasons: [{ kind: "challenged_checkpoint", detail: "착공 지연 보도" }],
    },
  ],
  deltaHistory: [
    { deltaId: "d1", verdict: "weakened", verdictLabel: "약화", generatedAt: "2026-08-28T00:00:00+00:00", summary: "고객 집중도 상승" },
  ],
  layer: "hypothesis",
  reuseAsEvidence: false,
};

const WATCHLIST_OVERVIEW = {
  items: [
    { item: "NVDA", ticker: "NVDA", companyName: "NVIDIA", newsCount: 3, kind: "company" },
    { item: "AMD", ticker: "AMD", companyName: "AMD", newsCount: 1, kind: "company" },
  ],
};

const WATCHLIST_DETAIL = {
  item: "NVDA",
  company: { name: "NVIDIA", ticker: "NVDA" },
  news: [],
  count: 0,
};

const AMD_WORKSPACE_FIXTURE = {
  ...WORKSPACE_FIXTURE,
  ticker: "AMD",
  thesis: { ...WORKSPACE_FIXTURE.thesis, ticker: "AMD", company: "AMD", coreThesis: "AMD 새 화면 Thesis" },
};

// Agent Dock Stage E: web search control fixtures. supportsWebSearch is
// server-authoritative (bridge.py::adapter_supports_web_search()) — the
// popover only reads it, it never guesses per-CLI capability itself.
const AGENT_BRIDGE_SETTINGS = {
  provider: "codex",
  adapters: [
    { id: "codex", label: "Codex CLI", model: "gpt-6-sol", modelChoices: [{ value: "gpt-6-sol", label: "GPT-6 Sol" }], bridgeSupported: true, supportsWebSearch: true },
  ],
};

const AGENT_BRIDGE_SETTINGS_NO_SEARCH = {
  provider: "antigravity",
  adapters: [
    { id: "antigravity", label: "Antigravity", modelChoices: [], bridgeSupported: true, supportsWebSearch: false },
  ],
};

const AGENT_BRIDGE_PREFLIGHT_OK = { ok: true, adapter: "codex", checks: [] };

type FixtureOptions = {
  overview?: Record<string, unknown>;
  workspace?: (ticker: string) => unknown | Promise<unknown>;
  onThesisPost?: (body: Record<string, unknown>) => unknown | Promise<unknown>;
  onReviewPost?: (body: Record<string, unknown>) => unknown | Promise<unknown>;
  onAssist?: (body: Record<string, unknown>) => unknown | Promise<unknown>;
  onApprove?: (body: Record<string, unknown>) => unknown | Promise<unknown>;
  fundamentals?: Record<string, unknown>;
  agent?: { threads: Array<Record<string, unknown>>; messages: Array<Record<string, unknown>>; beforeCreate?: () => Promise<void> | void };
  // Agent Dock Stage C: lets one test keep the job "running" (with a
  // phaseCode) for a few poll ticks before "done", to prove the live phase
  // hint actually reaches the rendered pending card — every other test's job
  // still completes on the first response, unaffected.
  jobPolls?: Array<{ status: string; phaseCode?: string | null; result?: Record<string, unknown> }>;
  // Agent Dock Stage E: only tests that open the run-settings popover need a
  // real adapter list (supportsWebSearch, model choices) — every other test
  // leaves this unset and /api/agent-bridge/* keeps 404ing as before.
  agentBridge?: { settings: Record<string, unknown>; preflight?: Record<string, unknown> };
  // Agent Dock Stage E: lets a test attach `search` metadata to the single-message
  // GET response the reply is fetched through, without touching the fixed
  // default body every other test relies on.
  getMessageResponse?: (messageId: string) => Record<string, unknown>;
};

async function prepare(page: Page, theme: "light" | "dark", options: FixtureOptions = {}) {
  let jobPollIndex = 0;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") {
      await route.abort();
      return;
    }
    if (!url.pathname.startsWith("/api/")) {
      await route.continue();
      return;
    }
    const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/memory/verification") return json(VERIFICATION_FIXTURE);
    if (url.pathname === "/api/agent/threads" && route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      options.agent?.threads.push(body);
      await options.agent?.beforeCreate?.();
      return json({ id: `challenge-${options.agent?.threads.length || 1}`, title: body.title || "반박 대화", scope: body.scope, status: "active", revision: 1, messages: [] });
    }
    if (/^\/api\/agent\/threads\/challenge-\d+\/messages\/[^/]+$/.test(url.pathname) && route.request().method() === "GET") {
      const messageId = url.pathname.split("/").at(-1) || "";
      return json(options.getMessageResponse?.(messageId) ?? { id: messageId, role: "assistant", content: "단일 메시지 조회로 받은 답변" });
    }
    if (url.pathname === "/api/agent-bridge/settings") {
      if (!options.agentBridge) return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"fixture"}' });
      return json(options.agentBridge.settings);
    }
    if (url.pathname === "/api/agent-bridge/preflight") {
      if (!options.agentBridge) return route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"fixture"}' });
      return json(options.agentBridge.preflight ?? AGENT_BRIDGE_PREFLIGHT_OK);
    }
    if (/^\/api\/agent\/threads\/challenge-\d+\/messages$/.test(url.pathname) && route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      options.agent?.messages.push(body);
      const jobId = `agent-job-${options.agent?.messages.length || 1}`;
      if (options.jobPolls?.length) return json({ job: { id: jobId, status: "queued" } });
      return json({ job: { id: jobId, status: "done", result: {} } });
    }
    if (options.jobPolls?.length && /^\/api\/jobs\/[^/]+$/.test(url.pathname) && route.request().method() === "GET") {
      const step = options.jobPolls[Math.min(jobPollIndex, options.jobPolls.length - 1)];
      jobPollIndex += 1;
      return json({ id: url.pathname.split("/").at(-1), status: step.status, phaseCode: step.phaseCode ?? null, result: step.result ?? {} });
    }
    if (/^\/api\/agent\/threads\/challenge-\d+$/.test(url.pathname) && route.request().method() === "GET") {
      const id = url.pathname.split("/").at(-1) || "challenge-1";
      const created = options.agent?.threads.find((_row, index) => id === `challenge-${index + 1}`) || {};
      return json({ id, title: created.title || "반박 대화", scope: created.scope || { kind: "general" }, status: "active", revision: 2,
        messages: [{ id: "agent-reply", role: "assistant", content: "반박 검토를 시작했습니다.", createdAt: "2026-08-31T00:00:00Z" }] });
    }
    if (/^\/api\/theses\/[^/]+\/workspace$/.test(url.pathname)) {
      const ticker = decodeURIComponent(url.pathname.split("/")[3] || "");
      return json(await (options.workspace?.(ticker) ?? WORKSPACE_FIXTURE));
    }
    if (/^\/api\/theses\/[^/]+\/reason-review$/.test(url.pathname) && route.request().method() === "POST") {
      return json(await (options.onReviewPost?.(route.request().postDataJSON() as Record<string, unknown>) ?? { eventId: "event-1" }));
    }
    if (/^\/api\/theses\/[^/]+\/reason-assist$/.test(url.pathname) && route.request().method() === "POST") {
      return json(await (options.onAssist?.(route.request().postDataJSON() as Record<string, unknown>) ?? { phase: "question", question: "질문", revisionId: "" }));
    }
    if (/^\/api\/theses\/[^/]+\/reason-assist\/approve$/.test(url.pathname) && route.request().method() === "POST") {
      return json(await (options.onApprove?.(route.request().postDataJSON() as Record<string, unknown>) ?? { ok: true }));
    }
    if (url.pathname === "/api/market/fundamentals" && options.fundamentals) return json(options.fundamentals);
    if (url.pathname === "/api/theses" && route.request().method() === "POST") {
      return json(await (options.onThesisPost?.(route.request().postDataJSON() as Record<string, unknown>) ?? { ok: true, thesis: null }));
    }
    if (url.pathname === "/api/watchlist" && route.request().method() === "GET")
      return json((options.overview?.items as Array<{ item: string }> | undefined)?.map((item) => item.item) ?? ["NVDA", "AMD"]);
    if (url.pathname === "/api/watchlist/overview") return json(options.overview ?? WATCHLIST_OVERVIEW);
    if (url.pathname === "/api/watchlist/detail") {
      return json(url.searchParams.get("item") === "AMD"
        ? { ...WATCHLIST_DETAIL, item: "AMD", company: { name: "AMD", ticker: "AMD" } }
        : WATCHLIST_DETAIL);
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"fixture"}' });
  });
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem("folio.themePreference.v1", selectedTheme);
    localStorage.setItem("folio.react.agentClosed", "1");
  }, theme);
}

/** 상세는 "기업 정보 | 내 이유" 두 탭이다(2026-09-29). 이유 화면은 두 번째 탭에 있다. */
async function openReasonTab(page: Page) {
  const tab = page.getByRole("group", { name: "상세 보기" }).getByRole("button", { name: /^내 (관심|투자) 이유/ });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-pressed", "true");
}

async function open(page: Page, hash: string) {
  await page.goto(`/#/${hash}`, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({
    content: "*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }",
  });
  // 셸이 페이드인을 마치기 전에는 안의 모든 것이 opacity 0이라 "hidden"이다.
  await expect
    .poll(() => page.locator(".react-shell").evaluate((element) => getComputedStyle(element).opacity))
    .toBe("1");
}

test.describe("0.6 verification surfaces", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`narrative verdicts and silence badges pass axe in ${theme} mode`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the axe sweep.");
      await prepare(page, theme);
      await open(page, "market-memory");

      const panel = page.getByRole("region", { name: /확인이 필요한 내러티브/ });
      await expect(panel).toBeVisible();
      // 판정은 색만으로 전달하지 않는다 — 라벨이 읽힌다.
      await expect(panel.getByText("반증 신호").first()).toBeVisible();
      await expect(panel.getByText("정리 후보").first()).toBeVisible();
      // 무소식 배지: 죽어가는 이야기가 살아있는 이야기와 다르게 보인다.
      await expect(panel.getByText("37일 무소식 · 정리 후보")).toBeVisible();
      // 정리 후보라는 말이 정리하겠다는 뜻으로 읽히면 안 된다.
      await expect(panel.getByText(/자동으로 바뀌지 않습니다/)).toBeVisible();
      // 신호가 없는 내러티브는 줄을 만들지 않는다(알림은 조용할 때 조용하다).
      await expect(panel.locator(".verification-alert")).toHaveCount(2);

      const results = await new AxeBuilder({ page })
        .include(".verification-panel")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(blocking, blocking.map((v) => v.id).join(", ")).toEqual([]);
    });

    test(`thesis workspace passes axe in ${theme} mode`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the axe sweep.");
      await prepare(page, theme);
      await open(page, "watchlist/NVDA");

      await openReasonTab(page);
      const workspace = page.getByRole("region", { name: "내 관심 이유" });
      await expect(workspace).toBeVisible();
      // 개인 영역 경계 — 보라 칩은 내가 쓴 것에만 붙는다.
      await expect(workspace).toHaveAttribute("data-layer", "hypothesis");
      await expect(workspace.getByText("내 생각 · 근거 아님")).toBeVisible();
      // 헤드라인 단어 세기 판정은 보여 주지 않는다(2026-09-29).
      await expect(workspace.getByText("약화")).toHaveCount(0);
      await expect(workspace.getByText("이유 종합 판정")).toHaveCount(0);
      // 관련 새 소식은 사실로, 줄 전체가 원문 링크다.
      await expect(workspace.getByRole("heading", { name: "관련 새 소식" })).toBeVisible();
      await expect(workspace.getByRole("link", { name: /대형 고객, 자체 AI 칩 비중 확대/ })).toHaveAttribute("href", "https://example.com/nvda-custom-chip");
      // 소유권과 A.3 전파
      await expect(workspace.getByText("Vault 동기화 멈춤")).toBeVisible();
      await expect(workspace.getByText("연결 내러티브 경고")).toBeVisible();
      await expect(workspace.getByText(/표시일 뿐 이유를 바꾸지 않습니다/)).toBeVisible();

      const results = await new AxeBuilder({ page })
        .include(".thesis-workspace")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(blocking, blocking.map((v) => v.id).join(", ")).toEqual([]);
    });
  }

  test("verification surfaces do not overflow on mobile", async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.includes("mobile"), "Mobile layout contract runs on the mobile project.");
    await prepare(page, "dark");
    // 셸은 지난 라우트 pane을 DOM에 남겨 둔다 — 선택자를 **현재 라우트 안으로** 좁히지
    // 않으면 앞 화면의 숨은 패널이 먼저 걸린다(실측으로 이 테스트가 그렇게 실패했다).
    const surfaces: Array<[string, string, string]> = [
      ["market-memory", "market-memory", ".verification-panel"],
      ["watchlist/NVDA", "watchlist", ".thesis-workspace"],
    ];
    for (const [hash, route, selector] of surfaces) {
      await open(page, hash);
      if (route === "watchlist") await openReasonTab(page);
      await expect(page.locator(`.react-route-host[data-route="${route}"] ${selector}`)).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${hash} horizontal overflow`).toBeLessThanOrEqual(1);
    }
  });

  test("mobile Stage C/D actions meet the 44px target and retain keyboard focus", async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.includes("mobile"), "Mobile target runs on the mobile project.");
    await prepare(page, "light");
    await open(page, "watchlist/NVDA");
    const tab = page.getByRole("group", { name: "상세 보기" }).getByRole("button", { name: /^내 관심 이유/ });
    expect(await tab.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await openReasonTab(page);
    const edit = page.getByRole("button", { name: "수정하기", exact: true });
    const newsRow = page.getByRole("link", { name: /대형 고객, 자체 AI 칩 비중 확대/ });
    const debate = page.getByRole("button", { name: "AI와 따져보기" });
    for (const target of [edit, newsRow, debate]) {
      await expect(target).toBeVisible();
      expect(await target.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    }
    await debate.focus();
    await expect(debate).toBeFocused();
    await open(page, "market-memory");
    // 알림 줄의 버튼 라벨은 짧지만, 접근성 이름은 어느 내러티브인지 말한다.
    const narrativeAction = page.getByRole("button", { name: /전제를 반박해줘/ }).first();
    await expect(narrativeAction).toBeVisible();
    expect(await narrativeAction.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await narrativeAction.focus();
    await expect(narrativeAction).toBeFocused();
  });

  test("keyboard reaches the disclosure controls of the verification panel", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Keyboard contract is desktop-specific.");
    await prepare(page, "light");
    await open(page, "market-memory");
    const timeline = page.locator(".verification-alert__detail > summary").first();
    await timeline.focus();
    await expect(timeline).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(".verification-timeline__list").first()).toBeVisible();
  });

  test("narrative timeline uses Korean labels instead of stored status or JSON", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the rendered timeline contract.");
    await prepare(page, "light");
    await open(page, "market-memory");
    await page.locator(".verification-alert__detail > summary").first().click();
    const timeline = page.locator(".verification-timeline__list").first();
    await expect(timeline).toContainText("상태 활성 → 대체됨");
    await expect(timeline).toContainText("근거 수 7일 0 · 30일 2 · 90일 6 → 7일 1 · 30일 4 · 90일 9");
    await expect(timeline).not.toContainText('{"d7"');
    await expect(timeline).not.toContainText("overridden");
  });

  test("twenty companies stay scannable with view, search and holdings filter", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop checks the dense list interaction.");
    const items = Array.from({ length: 20 }, (_, index) => ({
      item: `T${String(index).padStart(2, "0")}`, ticker: `T${String(index).padStart(2, "0")}`,
      companyName: `Company ${index}`, count: index, reasonKind: index < 2 ? "investment" : "interest",
      reasonPreview: index === 19 ? "마지막 종목의 짧은 이유" : "", reasonStatus: index === 19 ? "unreviewed" : "unwritten",
      reasonNewsCount: index === 19 ? 2 : 0,
    }));
    await prepare(page, "light", { overview: { items, news: [] } });
    await open(page, "watchlist");
    await expect(page.locator(".watchlist-reason-row")).toHaveCount(20);
    await expect(page.getByText("마지막 종목의 짧은 이유")).toBeVisible();
    // 목록은 절차 상태 대신 이유와 연결된 새 소식만 알린다(2026-09-29).
    await expect(page.locator(".watchlist-reason-news-chip")).toHaveCount(1);
    await expect(page.locator(".watchlist-reason-news-chip")).toHaveText("새 소식 2");
    await expect(page.locator(".watchlist-reason-list")).not.toContainText("미검토");
    await page.getByRole("button", { name: "보유", exact: true }).click();
    await expect(page.locator(".watchlist-reason-row")).toHaveCount(2);
    await page.getByRole("button", { name: "전체", exact: true }).click();
    await page.getByRole("textbox", { name: "종목 찾기" }).fill("T19");
    await expect(page.locator(".watchlist-reason-row")).toHaveCount(1);
    await page.getByRole("textbox", { name: "종목 찾기" }).fill("");
    await page.getByRole("button", { name: "카드", exact: true }).click();
    await expect(page.locator(".watchlist-card")).toHaveCount(20);
  });

  test("Watchlist Thesis edit writes only on explicit save without leaving the detail", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the request lifecycle contract.");
    let workspace = WORKSPACE_FIXTURE;
    const posts: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      workspace: () => workspace,
      onThesisPost: (body) => {
        posts.push(body);
        workspace = {
          ...WORKSPACE_FIXTURE,
          thesis: { ...WORKSPACE_FIXTURE.thesis, coreThesis: String(body.coreThesis || "") },
        };
        return { ok: true, thesis: workspace.thesis };
      },
    });
    await open(page, "watchlist/NVDA");
    const before = await page.evaluate(() => window.location.hash);
    await openReasonTab(page);
    await page.getByRole("button", { name: "수정하기", exact: true }).click();
    expect(await page.evaluate(() => window.location.hash)).toBe(before);
    expect(posts).toHaveLength(0);
    const editor = page.locator(".thesis-workspace__editor");
    // 편집을 열면 보기 화면을 대체한다 — 같은 문장이 두 번 보이지 않는다.
    await expect(page.locator(".reason-view")).toHaveCount(0);
    await editor.getByLabel("이 종목에 관심이 있는 이유가 무엇인가요?").fill("편집한 관심 이유");
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ ticker: "NVDA", coreThesis: "편집한 관심 이유" });
    // 확신도·검토 주기·핵심 가정은 보내지 않아 부분 갱신으로 보존된다.
    expect(posts[0]).not.toHaveProperty("conviction");
    expect(posts[0]).not.toHaveProperty("reviewCycle");
    expect(posts[0]).not.toHaveProperty("keyAssumptions");
    await expect(editor).toHaveCount(0);
    await expect(page.getByText("편집한 관심 이유")).toBeVisible();
  });

  test("Watchlist Thesis create retains the detail ticker and company context", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the request lifecycle contract.");
    let workspace = { ...WORKSPACE_FIXTURE, hasThesis: false, thesis: null };
    const posts: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      workspace: () => workspace,
      onThesisPost: (body) => {
        posts.push(body);
        workspace = {
          ...WORKSPACE_FIXTURE,
          thesis: { ...WORKSPACE_FIXTURE.thesis, coreThesis: String(body.coreThesis || ""), company: String(body.company || "") },
        };
        return { ok: true, thesis: workspace.thesis };
      },
    });
    await open(page, "watchlist/NVDA");
    const before = await page.evaluate(() => window.location.hash);
    await openReasonTab(page);
    await page.getByRole("button", { name: "관심 이유 남기기" }).click();
    expect(await page.evaluate(() => window.location.hash)).toBe(before);
    expect(posts).toHaveLength(0);
    const editor = page.locator(".thesis-workspace__editor");
    // 비운 채 저장하면 막지 않고 그 자리에서 말한다(버튼은 비활성으로 두지 않는다).
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect(editor.getByText("한 줄만 적어 주세요. 짧아도 괜찮아요.")).toBeVisible();
    expect(posts).toHaveLength(0);
    await editor.getByLabel("이 종목에 관심이 있는 이유가 무엇인가요?").fill("새 관심 이유");
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ ticker: "NVDA", company: "NVIDIA", coreThesis: "새 관심 이유" });
    await expect(editor).toHaveCount(0);
    await expect(page.getByText("새 관심 이유")).toBeVisible();
  });

  test("a saved investment reason needs no review action in the basic view", async ({ page }) => {
    let workspace = { ...WORKSPACE_FIXTURE, hasThesis: false, reasonKind: "investment", thesis: null };
    const posts: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      overview: { items: [{ item: "NVDA", ticker: "NVDA", companyName: "NVIDIA", reasonKind: "investment" }] },
      workspace: () => workspace,
      onThesisPost: (body) => {
        posts.push(body);
        workspace = {
          ...WORKSPACE_FIXTURE,
          reasonKind: "investment",
          news: { ...WORKSPACE_FIXTURE.news, items: [], count: 0 },
          thesis: {
            ...WORKSPACE_FIXTURE.thesis,
            coreThesis: String(body.coreThesis || ""),
            falsificationTriggers: body.falsificationTriggers as string[] || [],
          },
        };
        return { ok: true, thesis: workspace.thesis };
      },
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "투자 이유 남기기" }).click();
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByLabel("이 종목에 투자한 이유가 무엇인가요?").fill("제품 생태계가 오래 유지된다");
    await editor.getByLabel("어떤 일이 확인되면 이 이유가 틀렸다고 판단하시겠어요?").fill("고객이 경쟁 제품으로 이동한다");
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ coreThesis: "제품 생태계가 오래 유지된다", falsificationTriggers: ["고객이 경쟁 제품으로 이동한다"], conditionResponse: "written" });
    await expect(editor).toHaveCount(0);
    const reason = page.locator(".thesis-workspace");
    await expect(reason.getByText("제품 생태계가 오래 유지된다")).toBeVisible();
    await expect(reason.locator(".reason-view__cond").filter({ hasText: "고객이 경쟁 제품으로 이동한다" })).toBeVisible();
    await expect(reason.getByText("저장 8월 20일")).toBeVisible();
    // 기본 보기에는 수정하기 하나뿐이다. 판정 생성·검토 마치기·반박 버튼은 없다.
    await expect(reason.getByRole("button", { name: "수정하기", exact: true })).toBeVisible();
    await expect(reason.getByRole("button", { name: /최신 근거로 검토|이번 검토 마치기|반박해줘/ })).toHaveCount(0);
    await expect(reason.getByText("이 투자 이유와 연결된 새 소식은 아직 없습니다.", { exact: false })).toHaveCount(0);
    await expect(reason.getByText("이 이유와 연결된 새 소식은 아직 없습니다.")).toBeVisible();
  });

  test("unknown condition is a text action under the field and saves as an explicit answer", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the request lifecycle contract.");
    const posts: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      workspace: () => ({ ...WORKSPACE_FIXTURE, hasThesis: false, thesis: null }),
      onThesisPost: (body) => { posts.push(body); return { ok: true, thesis: null }; },
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "관심 이유 남기기" }).click();
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByLabel("이 종목에 관심이 있는 이유가 무엇인가요?").fill("돈을 잘 벌어서");
    await editor.getByRole("button", { name: "아직 모르겠어요" }).click();
    await expect(editor.getByText("“아직 모르겠어요”로 남깁니다.")).toBeVisible();
    await expect(editor.getByRole("checkbox")).toHaveCount(0);
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ coreThesis: "돈을 잘 벌어서", falsificationTriggers: [], conditionResponse: "unknown" });
  });

    test("ticker change makes an in-flight old Thesis save unable to overwrite the new detail", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the stale-save ownership contract.");
    let nvdaReads = 0;
    let releaseOldReload: (() => void) | undefined;
    let oldReloadStarted = false;
    const oldReload = new Promise<void>((resolve) => { releaseOldReload = resolve; });
    await prepare(page, "light", {
      workspace: async (ticker) => {
        if (ticker === "AMD") return AMD_WORKSPACE_FIXTURE;
        nvdaReads += 1;
        if (nvdaReads > 1) {
          oldReloadStarted = true;
          await oldReload;
          return { ...WORKSPACE_FIXTURE, thesis: { ...WORKSPACE_FIXTURE.thesis, coreThesis: "이전 종목의 늦은 저장" } };
        }
        return WORKSPACE_FIXTURE;
      },
      onThesisPost: () => ({ ok: true, thesis: WORKSPACE_FIXTURE.thesis }),
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "수정하기", exact: true }).click();
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByLabel("이 종목에 관심이 있는 이유가 무엇인가요?").fill("이전 종목의 임시 초안");
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => oldReloadStarted).toBe(true);

    await page.evaluate(() => { window.location.hash = "#/watchlist/AMD"; });
    await openReasonTab(page);
    const workspace = page.getByRole("region", { name: "내 관심 이유" });
    await expect(workspace.getByText("AMD 새 화면 Thesis")).toBeVisible();
    await expect(workspace.locator(".thesis-workspace__editor")).toHaveCount(0);
    await expect(workspace).not.toContainText("이전 종목의 임시 초안");
    await expect(workspace).not.toContainText("이전 종목의 늦은 저장");
    await expect(workspace.locator(".react-dashboard-error")).toHaveCount(0);

    releaseOldReload?.();
    await page.waitForTimeout(50);
    await expect(workspace.getByText("AMD 새 화면 Thesis")).toBeVisible();
    await expect(workspace).not.toContainText("이전 종목의 늦은 저장");
  });

  test("related news shows one line per item, opens sources, and keeping the reason records what was seen", async ({ page }) => {
    const items = [
      { key: "https://example.com/a", title: "대형 고객, 자체 AI 칩 비중 확대", date: "2026-09-02", url: "https://example.com/a", condition: "대형 고객이 자체 칩으로 이동" },
      { key: "2026-09-01|제목만 수집된 소식", title: "제목만 수집된 소식", date: "2026-09-01", url: "", condition: "대형 고객이 자체 칩으로 이동" },
      { key: "https://example.com/c", title: "세 번째 소식", date: "2026-08-31", url: "https://example.com/c", condition: "대형 고객이 자체 칩으로 이동" },
      { key: "https://example.com/d", title: "네 번째 소식", date: "2026-08-30", url: "https://example.com/d", condition: "대형 고객이 자체 칩으로 이동" },
    ];
    let workspace = { ...WORKSPACE_FIXTURE, news: { ...WORKSPACE_FIXTURE.news, items, count: items.length } };
    const reviews: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      workspace: () => workspace,
      onReviewPost: (body) => {
        reviews.push(body);
        workspace = { ...workspace, news: { ...workspace.news, items: [], count: 0, lastDecisionAt: "2026-09-03T00:00:00Z" } };
        return { eventId: "event-1" };
      },
    });
    await open(page, "watchlist/NVDA");
    // 새 소식이 있으면 두 번째 탭 이름 옆에 표시가 붙는다(스크린 리더는 건수를 읽는다).
    await expect(page.getByRole("button", { name: /내 관심 이유 \(새 소식 4건\)/ })).toBeVisible();
    await openReasonTab(page);
    const news = page.locator('[data-qa="reason-news"]');
    await expect(news.locator(".reason-news__count")).toHaveText("4");
    await expect(news.getByRole("link", { name: /대형 고객, 자체 AI 칩 비중 확대/ })).toHaveAttribute("href", "https://example.com/a");
    await expect(news.getByText("9월 1일 · 원문 없음")).toBeVisible();
    await expect(news.getByRole("link", { name: /제목만 수집된 소식/ })).toHaveCount(0);
    await expect(news.getByText("네 번째 소식")).toHaveCount(0);
    await news.getByRole("button", { name: "1건 더 보기" }).click();
    await expect(news.getByText("네 번째 소식")).toBeVisible();
    await news.getByRole("button", { name: "그대로 두기" }).click();
    await expect.poll(() => reviews.length).toBe(1);
    expect(reviews[0]).toMatchObject({ expectedRevisionId: "nvda-reason-1", outcome: "no_material_change" });
    expect((reviews[0].basisRefs as Array<{ key: string }>).map((ref) => ref.key)).toEqual(items.map((item) => item.key));
    await expect(news.getByText("9월 3일에 이유를 그대로 두었어요. 그 뒤로 연결된 새 소식은 없습니다.")).toBeVisible();
    await expect(news.getByText("찾는 단어: 자체 칩, custom chip")).toBeVisible();
    await expect(page.getByRole("button", { name: /새 소식 \d+건/ })).toHaveCount(0);
  });

  test("no search words is reported as not searching, not as no news", async ({ page }) => {
    const workspace = { ...WORKSPACE_FIXTURE, news: { ...WORKSPACE_FIXTURE.news, items: [], count: 0, searchReady: false, keywords: [] } };
    await prepare(page, "dark", { workspace: () => workspace });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    const news = page.locator('[data-qa="reason-news"]');
    await expect(news.getByText("판단 조건과 대조할 단어가 없어 새 소식을 찾지 않고 있어요.")).toBeVisible();
    await expect(news.getByText(/새 소식은 아직 없습니다/)).toHaveCount(0);
  });

  test("related news keeps different source URLs that share a title", async ({ page }) => {
    const urls = ["https://example.com/filing-a", "https://example.com/filing-b"];
    const items = urls.map((url) => ({ key: url, title: "같은 제목의 공시", date: "2026-09-01", url, condition: "대형 고객이 자체 칩으로 이동" }));
    await prepare(page, "light", { workspace: () => ({ ...WORKSPACE_FIXTURE, news: { ...WORKSPACE_FIXTURE.news, items, count: 2 } }) });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    const links = page.locator('[data-qa="reason-news"]').getByRole("link", { name: /같은 제목의 공시/ });
    await expect(links).toHaveCount(2);
    await expect(links.nth(0)).toHaveAttribute("href", urls[0]);
    await expect(links.nth(1)).toHaveAttribute("href", urls[1]);
  });

  test("a condition read as an earnings metric shows the current numbers as facts", async ({ page }) => {
    const condition = "분기 영업이익률이 두 분기 연속 낮아질 때";
    await prepare(page, "light", {
      workspace: () => ({ ...WORKSPACE_FIXTURE, thesis: { ...WORKSPACE_FIXTURE.thesis, falsificationTriggers: [condition] } }),
      fundamentals: { symbol: "NVDA", currency: "USD", quarters: [
        { quarter: "2026-01-31", revenue: 100, operatingIncome: 62 },
        { quarter: "2026-04-30", revenue: 100, operatingIncome: 64.1 },
        { quarter: "2026-07-31", revenue: 100, operatingIncome: 66.2 },
      ] },
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    const check = page.locator('[data-qa="reason-metric-check"]');
    await expect(check).toContainText("최근 3분기 영업이익률");
    await expect(check).toContainText("62.0% → 64.1% →");
    await expect(check.locator("b")).toHaveText("66.2%");
    await expect(check).toContainText("(26년 1월 → 26년 4월 → 26년 7월)");
    await expect(check).toContainText("조건에 해당하지 않음");
  });

  test("AI refinement compares per field and saves once through the approval path", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the request lifecycle contract.");
    const assists: Array<Record<string, unknown>> = [];
    const approvals: Array<Record<string, unknown>> = [];
    const directSaves: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      onAssist: (body) => {
        assists.push(body);
        return body.phase === "question"
          ? { phase: "question", question: "“돈을 잘 번다”는 어떤 모습을 보고 느끼셨나요?", revisionId: "nvda-reason-1" }
          : { phase: "draft", revisionId: "nvda-reason-1", previewToken: "123.token",
            suggestedReason: "매출이 크게 늘면서 남는 이익도 함께 커지고 있어서", reasonBasis: "최근 분기 영업이익률 66.2%",
            suggestedCondition: "분기 영업이익률이 두 분기 연속 낮아질 때", conditionBasis: "Folio가 매 분기 실적으로 확인할 수 있어요. “두 분기”는 제안입니다.",
            conditionKeywords: ["margin", "이익률 하락"], uncertainties: [] };
      },
      onApprove: (body) => { approvals.push(body); return { ok: true }; },
      onThesisPost: (body) => { directSaves.push(body); return { ok: true, thesis: null }; },
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "수정하기", exact: true }).click();
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByRole("button", { name: "AI와 함께 다듬기" }).click();
    const ai = editor.getByRole("region", { name: "AI 질문" });
    await expect(ai.getByText("“돈을 잘 번다”는 어떤 모습을 보고 느끼셨나요?")).toBeVisible();
    await ai.getByRole("button", { name: "답하기" }).click();
    await expect(ai.getByText("답을 적거나 ‘모르겠어요’를 눌러 주세요.")).toBeVisible();
    await ai.getByRole("button", { name: "여기까지 하고 정리" }).click();
    await expect(editor.getByText("본 자료: 최근 분기 영업이익률 66.2%")).toBeVisible();
    await expect(editor.locator("del")).toHaveCount(0);
    const [reasonPick, conditionPick] = [editor.locator(".reason-q").nth(0), editor.locator(".reason-q").nth(1)];
    await reasonPick.getByRole("button", { name: "이 제안 쓰기" }).click();
    await expect(editor.getByLabel("이 종목에 관심이 있는 이유가 무엇인가요?")).toHaveValue("매출이 크게 늘면서 남는 이익도 함께 커지고 있어서");
    await conditionPick.getByRole("button", { name: "이 제안 쓰기" }).click();
    await expect(editor.getByRole("button", { name: "저장", exact: true })).toHaveCount(1);
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => approvals.length).toBe(1);
    expect(directSaves).toHaveLength(0);
    expect(approvals[0]).toMatchObject({
      previewToken: "123.token",
      coreThesis: "매출이 크게 늘면서 남는 이익도 함께 커지고 있어서",
      conditionText: "분기 영업이익률이 두 분기 연속 낮아질 때",
      conditionKeywords: ["margin", "이익률 하락"],
      conditionResponse: "written",
    });
    expect(assists.map((row) => row.phase)).toEqual(["question", "draft"]);
  });

  test("AI approval conflict discards the old signed preview after explicit rebase", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop covers the signed preview conflict.");
    let workspace = { ...WORKSPACE_FIXTURE,
      reasonRevision: { ...WORKSPACE_FIXTURE.reasonRevision, revisionId: "a".repeat(32) },
      thesis: { ...WORKSPACE_FIXTURE.thesis, coreThesis: "이전 이유 A" } };
    const approvals: Array<Record<string, unknown>> = [];
    const directSaves: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      workspace: () => workspace,
      onAssist: (body) => body.phase === "question"
        ? { phase: "question", question: "어떤 점을 보셨나요?", revisionId: "a".repeat(32) }
        : { phase: "draft", revisionId: "a".repeat(32), previewToken: "123.token",
          suggestedReason: "AI가 다듬은 이유", suggestedCondition: "분기 매출이 두 분기 연속 줄어들 때",
          conditionKeywords: ["revenue"], uncertainties: [] },
      onThesisPost: (body) => { directSaves.push(body); return { ok: true, thesis: null }; },
    });
    await page.route("**/api/theses/NVDA/reason-assist/approve", async (route) => {
      approvals.push(route.request().postDataJSON() as Record<string, unknown>);
      workspace = { ...workspace, reasonRevision: { ...workspace.reasonRevision, revisionId: "b".repeat(32) },
        thesis: { ...workspace.thesis, coreThesis: "다른 화면의 이유 B" } };
      return route.fulfill({ status: 409, contentType: "application/json", body: '{"detail":"revision_conflict"}' });
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "수정하기", exact: true }).click();
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByRole("button", { name: "AI와 함께 다듬기" }).click();
    await editor.getByRole("button", { name: "여기까지 하고 정리" }).click();
    await editor.locator(".reason-q").nth(0).getByRole("button", { name: "이 제안 쓰기" }).click();
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect(page.getByText("지금 저장된 이유: 다른 화면의 이유 B")).toBeVisible();
    await expect(page.getByText(/기존 AI 제안 승인은 이전 기록에 묶여 있습니다/)).toBeVisible();
    await page.getByRole("button", { name: "최신 기록을 확인하고 이 초안을 다시 저장하기" }).click();
    await editor.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => directSaves.length).toBe(1);
    expect(approvals).toHaveLength(1);
    expect(directSaves[0]).toMatchObject({ expectedRevisionId: "b".repeat(32), coreThesis: "AI가 다듬은 이유" });
  });

    test("restored reason draft keeps its original revision; list refreshes", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop covers the cross-screen revision contract.");
    const overview = { items: [{ item: "NVDA", ticker: "NVDA", companyName: "NVIDIA",
      reasonPreview: "원문 A", reasonStatus: "unreviewed" }] };
    let workspace = { ...WORKSPACE_FIXTURE,
      reasonRevision: { ...WORKSPACE_FIXTURE.reasonRevision, revisionId: "a".repeat(32) },
      thesis: { ...WORKSPACE_FIXTURE.thesis, coreThesis: "원문 A" } };
    const posts: Array<Record<string, unknown>> = [];
    await prepare(page, "light", {
      overview,
      workspace: () => workspace,
      onThesisPost: (body) => {
        posts.push(body);
        workspace = { ...workspace, thesis: { ...workspace.thesis, coreThesis: String(body.coreThesis || "") },
          reasonRevision: { ...workspace.reasonRevision, revisionId: "c".repeat(32) } };
        overview.items[0].reasonPreview = String(body.coreThesis || "");
        return { ok: true, thesis: workspace.thesis };
      },
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "수정하기", exact: true }).click();
    await page.getByPlaceholder("예: 돈을 잘 벌어서").fill("복원한 A 초안");
    await page.evaluate(() => { window.location.hash = "#/watchlist"; });
    await page.locator('[data-watchlist-detail-item="NVDA"]').waitFor();
    workspace = { ...workspace, reasonRevision: { ...workspace.reasonRevision, revisionId: "b".repeat(32) },
      thesis: { ...workspace.thesis, coreThesis: "다른 화면의 B" } };
    await page.locator('[data-watchlist-detail-item="NVDA"]').click();
    await openReasonTab(page);
    await expect(page.getByPlaceholder("예: 돈을 잘 벌어서")).toHaveValue("복원한 A 초안");
    await page.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ expectedRevisionId: "a".repeat(32), coreThesis: "복원한 A 초안" });
    expect(posts[0]).not.toHaveProperty("conviction");
    await page.evaluate(() => { window.location.hash = "#/watchlist"; });
    await expect(page.locator(".watchlist-reason-row__summary")).toHaveText("복원한 A 초안");
  });

  test("a reason conflict shows the latest words before explicit rebase", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop covers the conflict comparison.");
    let workspace = { ...WORKSPACE_FIXTURE,
      reasonRevision: { ...WORKSPACE_FIXTURE.reasonRevision, revisionId: "a".repeat(32) },
      thesis: { ...WORKSPACE_FIXTURE.thesis, coreThesis: "이전 이유 A" } };
    const posts: Array<Record<string, unknown>> = [];
    await prepare(page, "light", { workspace: () => workspace });
    await page.route("**/api/theses", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      posts.push(route.request().postDataJSON() as Record<string, unknown>);
      if (posts.length === 1) {
        workspace = { ...workspace,
          reasonRevision: { ...workspace.reasonRevision, revisionId: "b".repeat(32) },
          thesis: { ...workspace.thesis, coreThesis: "다른 화면의 이유 B" } };
        return route.fulfill({ status: 409, contentType: "application/json", body: '{"detail":"revision_conflict"}' });
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: '{"ok":true}' });
    });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "수정하기", exact: true }).click();
    await page.getByPlaceholder("예: 돈을 잘 벌어서").fill("내 초안 A");
    await page.getByRole("button", { name: "저장", exact: true }).click();
    await expect(page.getByText("지금 저장된 이유: 다른 화면의 이유 B")).toBeVisible();
    await expect(page.getByPlaceholder("예: 돈을 잘 벌어서")).toHaveValue("내 초안 A");
    expect(posts[0].expectedRevisionId).toBe("a".repeat(32));
    await page.getByRole("button", { name: "최신 기록을 확인하고 이 초안을 다시 저장하기" }).click();
    await page.getByRole("button", { name: "저장", exact: true }).click();
    await expect.poll(() => posts.length).toBe(2);
    expect(posts[1].expectedRevisionId).toBe("b".repeat(32));
  });

  test("narrative challenge creates one scoped thread and auto-submits exactly once", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the scoped Agent request contract.");
    const agent = { threads: [] as Array<Record<string, unknown>>, messages: [] as Array<Record<string, unknown>> };
    await prepare(page, "light", { agent });
    await open(page, "market-memory");
    const action = page.getByRole("button", { name: /전제를 반박해줘/ }).first();
    await action.click();
    await expect.poll(() => agent.threads.length).toBe(1);
    await expect.poll(() => agent.messages.length).toBe(1);
    expect(agent.threads[0]).toMatchObject({ scope: { kind: "market_memory", id: "state-1", intent: "challenge" } });
    expect(agent.messages[0]).toMatchObject({ message: "이 전제를 반박해줘" });
    await expect(page.getByRole("complementary", { name: "AI Agent" })).toBeVisible();
    await expect(page.locator(".react-agent-scope")).toHaveText(/시장 내러티브/);
    await expect(page.locator(".react-agent-scope")).not.toContainText("state-1");
    await expect(page.getByText("이 전제를 반박해줘").last()).toBeVisible();
    await page.waitForTimeout(25);
    expect(agent.threads).toHaveLength(1);
    expect(agent.messages).toHaveLength(1);
  });

  test("pending card shows the real job phase and the reply comes from the single-message endpoint", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the scoped Agent request contract.");
    // Agent Dock Stage A/C: proves `onUpdate` actually reaches the rendered
    // pending card (not just that the code compiles), and that a completed
    // reply is read via the single-message endpoint, not a full-thread
    // refetch — the two fixture reply strings below are deliberately
    // different so the assertion can tell which path actually ran.
    const agent = { threads: [] as Array<Record<string, unknown>>, messages: [] as Array<Record<string, unknown>> };
    await prepare(page, "light", {
      agent,
      jobPolls: [
        { status: "running", phaseCode: "wait_engine" },
        { status: "running", phaseCode: "generate" },
        { status: "done", result: { assistantMessageId: "agent-reply-single", sessionId: "challenge-1" } },
      ],
    });
    await open(page, "market-memory");
    await page.getByRole("button", { name: /전제를 반박해줘/ }).first().click();
    await expect.poll(() => agent.messages.length).toBe(1);

    await expect(page.locator(".agent-run-eta")).toHaveText(/다른 작업이 끝나길 기다리는 중|Agent가 응답을 생성하는 중/);

    await expect(page.getByText("단일 메시지 조회로 받은 답변")).toBeVisible();
    await expect(page.getByText("반박 검토를 시작했습니다.")).toHaveCount(0);
  });

  test("debating related news keeps the selected ticker scope and opens the dock", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the scoped Agent request contract.");
    const agent = { threads: [] as Array<Record<string, unknown>>, messages: [] as Array<Record<string, unknown>> };
    await prepare(page, "dark", { agent });
    await open(page, "watchlist/NVDA");
    await openReasonTab(page);
    await page.getByRole("button", { name: "AI와 따져보기" }).click();
    await expect.poll(() => agent.threads.length).toBe(1);
    await expect.poll(() => agent.messages.length).toBe(1);
    expect(agent.threads[0]).toMatchObject({ scope: { kind: "watchlist", id: "NVDA", tickers: ["NVDA"], intent: "challenge", reasonRevisionId: "nvda-reason-1" } });
    const message = String(agent.messages[0].message || "");
    expect(message).toContain("일시적인 일인지 이유 자체를 흔드는 일인지");
    expect(message).toContain("대형 고객, 자체 AI 칩 비중 확대");
    await expect(page.getByRole("complementary", { name: "AI Agent" })).toBeVisible();
    await expect(page.locator(".react-agent-scope")).toContainText("NVDA");
  });

    test("a second challenge click during creation cannot leave an empty thread", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the scoped Agent request contract.");
    let releaseCreate: (() => void) | undefined;
    let firstCreateStarted = false;
    const gate = new Promise<void>((resolve) => { releaseCreate = resolve; });
    const agent = {
      threads: [] as Array<Record<string, unknown>>,
      messages: [] as Array<Record<string, unknown>>,
      beforeCreate: async () => {
        firstCreateStarted = true;
        await gate;
      },
    };
    await prepare(page, "light", { agent });
    await open(page, "market-memory");
    const actions = page.getByRole("button", { name: /전제를 반박해줘/ });
    await actions.nth(0).click();
    await expect.poll(() => firstCreateStarted).toBe(true);
    await actions.nth(1).click();
    expect(agent.threads).toHaveLength(1);
    expect(agent.messages).toHaveLength(0);
    releaseCreate?.();
    await expect.poll(() => agent.messages.length).toBe(1);
    expect(agent.threads).toHaveLength(1);
  });

  test("Agent Dock Stage E: choosing 사용 sends searchPolicy in the submit body", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the run-settings popover contract.");
    const agent = { threads: [] as Array<Record<string, unknown>>, messages: [] as Array<Record<string, unknown>> };
    await prepare(page, "light", { agent, agentBridge: { settings: AGENT_BRIDGE_SETTINGS } });
    await open(page, "market-memory");
    await page.getByRole("button", { name: "AI Agent 열기" }).click();
    const dock = page.getByRole("complementary", { name: "AI Agent" });
    await expect(dock).toBeVisible();
    await dock.locator('[data-qa="agent-input"]').fill("이 화면 요약해줘");
    await dock.getByRole("button", { name: /^실행 설정:/ }).click();
    const searchGroup = dock.getByRole("group", { name: "웹 검색" });
    await expect(searchGroup.getByRole("button", { name: "끔" })).toHaveAttribute("aria-pressed", "true");
    await searchGroup.getByRole("button", { name: "사용" }).click();
    await expect(searchGroup.getByRole("button", { name: "사용" })).toHaveAttribute("aria-pressed", "true");
    await dock.locator('[data-qa="agent-submit"]').click();
    await expect.poll(() => agent.messages.length).toBe(1);
    expect(agent.messages[0]).toMatchObject({ options: { searchPolicy: "on" } });
  });

  test("Agent Dock Stage E: an unsupported adapter disables the web search segment", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the run-settings popover contract.");
    await prepare(page, "light", { agentBridge: { settings: AGENT_BRIDGE_SETTINGS_NO_SEARCH } });
    await open(page, "market-memory");
    await page.getByRole("button", { name: "AI Agent 열기" }).click();
    const dock = page.getByRole("complementary", { name: "AI Agent" });
    await dock.getByRole("button", { name: /^실행 설정:/ }).click();
    const searchGroup = dock.getByRole("group", { name: "웹 검색" });
    await expect(searchGroup.getByRole("button", { name: "끔" })).toBeEnabled();
    await expect(searchGroup.getByRole("button", { name: "자동" })).toBeDisabled();
    await expect(searchGroup.getByRole("button", { name: "사용" })).toBeDisabled();
    await expect(dock.getByText("이 CLI는 웹 검색을 지원하지 않습니다.")).toBeVisible();
  });

  test("Agent Dock Stage E: a completed reply that used web search shows its sources", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the run-settings popover contract.");
    const agent = { threads: [] as Array<Record<string, unknown>>, messages: [] as Array<Record<string, unknown>> };
    await prepare(page, "light", {
      agent,
      agentBridge: { settings: AGENT_BRIDGE_SETTINGS },
      jobPolls: [{ status: "done", result: { assistantMessageId: "reply-with-sources" } }],
      getMessageResponse: (messageId) => ({
        id: messageId,
        role: "assistant",
        content: "웹에서 확인한 최신 내용입니다.",
        search: {
          requestedPolicy: "on",
          toolEnabled: true,
          toolUsed: "yes",
          sourceRefs: [
            { url: "https://example.com/a", tier: "primary", label: "출처 A" },
            { url: "https://example.com/b", tier: "secondary", label: "출처 B" },
          ],
        },
      }),
    });
    await open(page, "market-memory");
    await page.getByRole("button", { name: "AI Agent 열기" }).click();
    const dock = page.getByRole("complementary", { name: "AI Agent" });
    await dock.locator('[data-qa="agent-input"]').fill("최근 뉴스 찾아줘");
    await dock.locator('[data-qa="agent-submit"]').click();
    await expect.poll(() => agent.messages.length).toBe(1);
    await expect(dock.getByText("웹에서 확인한 최신 내용입니다.")).toBeVisible();
    await expect(dock.getByText("웹 검색 · 출처 2개", { exact: false })).toBeVisible();
    await expect(dock.getByRole("link", { name: "출처 A" })).toHaveAttribute("href", "https://example.com/a");
    await expect(dock.getByRole("link", { name: "출처 B" })).toHaveAttribute("href", "https://example.com/b");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`Agent Dock open state passes axe in ${theme} mode`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the axe sweep.");
      await prepare(page, theme, { agentBridge: { settings: AGENT_BRIDGE_SETTINGS } });
      await open(page, "market-memory");
      await page.getByRole("button", { name: "AI Agent 열기" }).click();
      const dock = page.getByRole("complementary", { name: "AI Agent" });
      await expect(dock).toBeVisible();
      await dock.getByRole("button", { name: /^실행 설정:/ }).click();
      await expect(dock.getByRole("group", { name: "웹 검색" })).toBeVisible();

      const results = await new AxeBuilder({ page })
        .include(".react-agent-dock")
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(blocking, blocking.map((v) => v.id).join(", ")).toEqual([]);
    });
  }
});

for (const theme of ["light", "dark"] as const) {
  test(`0.8 company exposure grouped sources ${theme}`, async ({ page }, info) => {
    await prepare(page, theme);
    let writes = 0;
    await page.route("**/api/macro/exposures/NVDA**", route => {
      if (route.request().method() !== "GET") writes++;
      return route.fulfill({ json: { profile: { limitations: ["공식 공시 일부 문단"], items: [1, 2].map(n => ({ id: `e${n}`, factor: "interest_rate", direction: "hurt_by_rise", quote: `Higher interest rates increase our borrowing costs. Source ${n}.`, sourceRef: { url: "https://www.sec.gov/example", form: "10-K", date: "2026-01-01" } })) }, interpretation: null } });
    });
    await open(page, "watchlist/NVDA");
    const panel = page.getByRole("region", { name: "공시에서 확인한 거시 노출" });
    const summary = panel.locator("summary").filter({ hasText: "공시 문장 2개" });
    await expect(summary).toHaveCount(1);
    await summary.focus(); await page.keyboard.press("Enter");
    await expect(panel.getByRole("link", { name: "공식 공시 원문" })).toHaveCount(2);
    await expect(panel.getByText(/현재 영향은 판단하기 어려움/)).toHaveCount(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect((await new AxeBuilder({ page }).include('[aria-label="공시에서 확인한 거시 노출"]').withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([]);
    await panel.screenshot({ path: info.outputPath(`exposure-${theme}.png`) });
    await openReasonTab(page);
    await expect(panel).toHaveCount(0);
    expect(writes).toBe(0);
  });
}
