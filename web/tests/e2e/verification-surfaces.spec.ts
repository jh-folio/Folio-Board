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
    message: "이 Thesis는 Vault에서 더 이상 갱신되지 않습니다. 앱에서 만든 내용이 우선이며, Vault 노트를 반영하려면 그 노트를 Thesis로 다시 등록하세요.",
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
    { item: "NVDA", ticker: "NVDA", label: "NVIDIA", newsCount: 3, kind: "company" },
    { item: "AMD", ticker: "AMD", label: "AMD", newsCount: 1, kind: "company" },
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

type FixtureOptions = {
  workspace?: (ticker: string) => unknown | Promise<unknown>;
  onThesisPost?: (body: Record<string, unknown>) => unknown | Promise<unknown>;
  agent?: { threads: Array<Record<string, unknown>>; messages: Array<Record<string, unknown>>; beforeCreate?: () => Promise<void> | void };
};

async function prepare(page: Page, theme: "light" | "dark", options: FixtureOptions = {}) {
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
    if (/^\/api\/agent\/threads\/challenge-\d+\/messages$/.test(url.pathname) && route.request().method() === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      options.agent?.messages.push(body);
      return json({ job: { id: `agent-job-${options.agent?.messages.length || 1}`, status: "done", result: {} } });
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
    if (url.pathname === "/api/theses" && route.request().method() === "POST") {
      return json(await (options.onThesisPost?.(route.request().postDataJSON() as Record<string, unknown>) ?? { ok: true, thesis: null }));
    }
    if (url.pathname === "/api/watchlist/overview") return json(WATCHLIST_OVERVIEW);
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

      const workspace = page.getByRole("region", { name: "내 Thesis 검증" });
      await expect(workspace).toBeVisible();
      // 개인 영역 경계
      await expect(workspace).toHaveAttribute("data-layer", "hypothesis");
      await expect(workspace.getByText("내 생각·가설 · 근거 아님")).toBeVisible();
      // 두 층의 판정이 각자 이름으로 보인다(§3.2).
      await expect(workspace.getByText("약화").first()).toBeVisible();
      await expect(workspace.getByText("Thesis 종합 판정", { exact: false }).first()).toBeVisible();
      await expect(workspace.getByText("확인됨").first()).toBeVisible();
      // 소유권과 A.3 전파
      await expect(workspace.getByText("Vault 동기화 멈춤")).toBeVisible();
      await expect(workspace.getByText("연결 내러티브 경고")).toBeVisible();
      await expect(workspace.getByText(/표시일 뿐 Thesis 판정을 바꾸지 않습니다/)).toBeVisible();

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
    const thesisAction = page.getByRole("button", { name: "이 Thesis를 반박해줘" });
    await expect(thesisAction).toBeVisible();
    expect(await thesisAction.evaluate((node) => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await thesisAction.focus();
    await expect(thesisAction).toBeFocused();
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
    await page.getByRole("button", { name: "Thesis 만들기/수정" }).click();
    expect(await page.evaluate(() => window.location.hash)).toBe(before);
    expect(posts).toHaveLength(0);
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByLabel("핵심 Thesis").fill("편집한 핵심 Thesis");
    await editor.getByRole("button", { name: "Thesis 저장" }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ ticker: "NVDA", coreThesis: "편집한 핵심 Thesis" });
    await expect(editor).toHaveCount(0);
    await expect(page.getByText("편집한 핵심 Thesis")).toBeVisible();
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
    await page.getByRole("button", { name: "Thesis 만들기" }).click();
    expect(await page.evaluate(() => window.location.hash)).toBe(before);
    expect(posts).toHaveLength(0);
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByLabel("핵심 Thesis").fill("새 핵심 Thesis");
    await editor.getByRole("button", { name: "Thesis 저장" }).click();
    await expect.poll(() => posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ ticker: "NVDA", company: "NVIDIA", coreThesis: "새 핵심 Thesis" });
    await expect(editor).toHaveCount(0);
    await expect(page.getByText("새 핵심 Thesis")).toBeVisible();
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
    await page.getByRole("button", { name: "Thesis 만들기/수정" }).click();
    const editor = page.locator(".thesis-workspace__editor");
    await editor.getByLabel("핵심 Thesis").fill("이전 종목의 임시 초안");
    await editor.getByRole("button", { name: "Thesis 저장" }).click();
    await expect.poll(() => oldReloadStarted).toBe(true);

    await page.evaluate(() => { window.location.hash = "#/watchlist/AMD"; });
    const workspace = page.getByRole("region", { name: "내 Thesis 검증" });
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

  test("Thesis challenge keeps the selected ticker scope and opens the dock", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Desktop runs the scoped Agent request contract.");
    const agent = { threads: [] as Array<Record<string, unknown>>, messages: [] as Array<Record<string, unknown>> };
    await prepare(page, "dark", { agent });
    await open(page, "watchlist/NVDA");
    await page.getByRole("button", { name: "이 Thesis를 반박해줘" }).click();
    await expect.poll(() => agent.threads.length).toBe(1);
    await expect.poll(() => agent.messages.length).toBe(1);
    expect(agent.threads[0]).toMatchObject({ scope: { kind: "watchlist", id: "NVDA", tickers: ["NVDA"], intent: "challenge" } });
    expect(agent.messages[0]).toMatchObject({ message: "이 Thesis를 반박해줘" });
    await expect(page.getByRole("complementary", { name: "AI Agent" })).toBeVisible();
    await expect(page.locator(".react-agent-scope")).toContainText("NVDA");
    await expect(page.getByText("이 Thesis를 반박해줘").last()).toBeVisible();
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
});
