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
  ],
};

const WATCHLIST_DETAIL = {
  item: "NVDA",
  company: { name: "NVIDIA", ticker: "NVDA" },
  news: [],
  count: 0,
};

async function prepare(page: Page, theme: "light" | "dark") {
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
    if (/^\/api\/theses\/[^/]+\/workspace$/.test(url.pathname)) return json(WORKSPACE_FIXTURE);
    if (url.pathname === "/api/watchlist/overview") return json(WATCHLIST_OVERVIEW);
    if (url.pathname === "/api/watchlist/detail") return json(WATCHLIST_DETAIL);
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

      const panel = page.getByRole("region", { name: "내러티브 검증 상태" });
      await expect(panel).toBeVisible();
      // 판정은 색만으로 전달하지 않는다 — 라벨이 읽힌다.
      await expect(panel.getByText("확인됨").first()).toBeVisible();
      await expect(panel.getByText("반증 신호").first()).toBeVisible();
      // 무소식 배지: 죽어가는 이야기가 살아있는 이야기와 다르게 보인다.
      await expect(panel.getByText("37일 무소식 · 정리 후보")).toBeVisible();
      await expect(panel.getByText(/자동으로 바뀌지 않습니다/)).toBeVisible();
      // 검증 실패 원소는 숨기지 않는다.
      await expect(panel.getByText("검증 불가")).toBeVisible();

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

  test("keyboard reaches the disclosure controls of the verification panel", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Keyboard contract is desktop-specific.");
    await prepare(page, "light");
    await open(page, "market-memory");
    const timeline = page.locator(".verification-timeline summary").first();
    await timeline.focus();
    await expect(timeline).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(".verification-timeline__list").first()).toBeVisible();
  });
});
