import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const snapshot = {
  id: "story", type: "story_share_series", market: "KR", drivers: ["AI", "정책"], otherLabel: "그 외 이야기",
  days: [
    { date: "2026-08-24", docCount: 100, shares: { AI: .123456, 정책: .5 }, otherShare: .376544 },
    { date: "2026-08-25", docCount: 0, shares: { AI: null, 정책: null }, otherShare: null },
    { date: "2026-08-26", docCount: 20, shares: { AI: 0, 정책: .8 }, otherShare: .2 },
  ],
};
const report = {
  date: "2026-08-30", kind: "weekly", marketScope: "kr", generatedAt: "2026-09-04T09:00:00Z", title: "한국장 주간 요약",
  markdown: "# 한국장 주간 요약\n\n## 1. 지난주 한국장 흐름\n\n시장은 서로 다른 반응을 보였습니다.\n\n· 관찰한 변화를 확인합니다.\n\n세부 설명을 읽은 뒤 업종을 비교합니다.\n\n## 2. 지난주 한국장을 움직인 핵심 변수\n\n수집한 기사 주제의 비중입니다.\n\n## 3. 다음 주 일정\n\n| 날짜 | 시장 | 일정 | 상태 |\n| --- | --- | --- | --- |\n| 09.01 | KR | 수출입 발표 | confirmed |\n\n## 참고자료\n\n[추가 자료](https://example.com/extra)",
  sources: [{ title: "기사", url: "https://example.com/news?mod=rss", source: "매체", date: "2026-08-24" }],
  headlines: [{ sources: [{ title: "같은 기사", url: "https://example.com/news?mod=feed" }] }],
  visualSnapshots: [snapshot],
  visualRecommendations: [{ snapshotId: "story", market: "KR", variant: "story_share_bars", title: "수집 기사 주제 비중", placement: { market: "KR", sectionRole: "weekly_story_share" } }],
};

for (const theme of ["light", "dark"]) {
  test(`saved reader lifecycle and values ${theme}`, async ({ page }, info) => {
    const writes: string[] = [];
    let releaseIndex!: () => void;
    const indexReady = new Promise<void>(resolve => { releaseIndex = resolve; });
    await page.route("**/api/**", async route => {
      const request = route.request();
      if (request.method() !== "GET") writes.push(request.url());
      const path = new URL(request.url()).pathname;
      if (path === "/api/briefings/index") await indexReady;
      const body = path === "/api/briefings/2026-08-30" ? report : path === "/api/briefings/index" ? { items: [], total: 0 } : {};
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.addInitScript(value => { localStorage.setItem("folio.themePreference.v1", value); localStorage.setItem("folio.react.agentClosed", "1"); }, theme);
    await page.goto("/#/briefing/2026-08-30/kr/weekly", { waitUntil: "domcontentloaded" });
    const chart = page.locator(".briefing-story-share-card");
    await expect(chart).toHaveCount(1);
    releaseIndex(); // A late archive response rerenders the route after the chart mounted.
    await page.waitForLoadState("networkidle");
    await expect(chart).toHaveCount(1);
    // 결측일에서 선이 끊기고(두 번째 M) 0%가 바닥선(y=234)에 놓인다. x는 카드 폭을
    // 따르는 1:1 좌표계라 고정값으로 박지 않는다.
    await expect(chart.locator("svg path").first()).toHaveAttribute("d", /^M[\d.]+,[\d.]+\s+M[\d.]+,234$/);
    // 다른 차트와 같은 CSS 픽셀로 그린다: 축 글자 12.5px, 선 2px.
    const metrics = await chart.locator("svg").evaluate((svg) => {
      const box = svg.getAttribute("viewBox")!.split(/\s+/).map(Number);
      const scale = svg.getBoundingClientRect().width / box[2];
      const text = getComputedStyle(svg.querySelector("text")!);
      const path = getComputedStyle(svg.querySelector("path")!);
      return { scale, fontPx: parseFloat(text.fontSize) * scale, strokePx: parseFloat(path.strokeWidth) * scale };
    });
    expect(Math.abs(metrics.scale - 1)).toBeLessThanOrEqual(0.02);
    expect(Math.abs(metrics.fontPx - 12.5)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(metrics.strokePx - 2)).toBeLessThanOrEqual(0.1);
    await expect(chart.locator(".briefing-story-share-values")).toContainText("12.3%");
    await chart.getByRole("combobox").selectOption("1");
    await expect(chart.locator(".briefing-story-share-values")).toContainText("0건");
    await expect(chart.locator(".briefing-story-share-values")).toContainText("자료 없음");
    await chart.getByRole("combobox").selectOption("2");
    await expect(chart.locator(".briefing-story-share-values")).toContainText("0.0%");
    await page.reload({ waitUntil: "networkidle" });
    await expect(chart).toHaveCount(1);
    await page.evaluate(() => { window.dispatchEvent(new Event("resize")); });
    await expect(chart).toHaveCount(1);
    await expect(page.locator(".report-hero-meta")).toContainText("생성");
    await expect(page.locator(".briefing-calendar-table")).toContainText("확정");
    await page.locator(".source-panel summary").click();
    await expect(page.locator(".source-panel a")).toHaveCount(2);
    if (info.project.name.includes("mobile")) {
      expect(await page.locator(".report-reader-body").evaluate(el => getComputedStyle(el).overflowY)).toBe("visible");
      await page.getByRole("button", { name: "투자 노트 열기", exact: true }).click();
      await expect(page.getByRole("button", { name: "투자 노트 닫기", exact: true })).toBeVisible();
      await page.keyboard.press("Escape");
    } else {
      await page.getByRole("button", { name: "읽기에 집중", exact: true }).click();
      await expect(page.locator(".report-note-panel")).toBeHidden();
      await expect(chart).toHaveCount(1);
      await page.getByRole("button", { name: "조작·노트 펼치기", exact: true }).click();
    }
    await chart.scrollIntoViewIfNeeded();
    await chart.screenshot({ path: `review-captures/q6-fixture-${info.project.name}-${theme}.png` });
    const violations = await new AxeBuilder({ page }).include(".briefing-story-share-card").analyze();
    expect(violations.violations.filter(v => ["serious", "critical"].includes(v.impact || ""))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    expect(writes).toEqual([]);
  });
}

// 주간 지수 카드는 저장본에 따라 두 그림으로 갈린다. 새 저장본은 일간과 같은 차트를
// 그 주 구간으로 열고, 자기 일봉이 없는 옛 저장본은 예전 겹쳐 그리기로 남는다 —
// 저장 시각자료는 불변이라 이미 발행된 보고서의 그림이 바뀌면 안 된다.
const weekPoints = [
  { time: "2026-08-31", close: 6820.02, changePct: 0 },
  { time: "2026-09-01", close: 6760.1, changePct: -0.88 },
  { time: "2026-09-02", close: 6712.4, changePct: -1.58 },
  { time: "2026-09-03", close: 6701.9, changePct: -1.73 },
  { time: "2026-09-04", close: 6687.1, changePct: -1.95 },
];
const dailyHistory = Array.from({ length: 24 }, (_, index) => ({
  time: new Date(Date.UTC(2026, 7, 3 + index)).toISOString().slice(0, 10),
  close: 6700 + index * 5,
}));
function weeklyReport(series: Record<string, unknown>, extra: Record<string, unknown>, defaultPeriod?: string) {
  return {
    date: "2026-09-06", kind: "weekly", marketScope: "kr", title: "한국장 주간 요약",
    markdown: "# 한국장 주간 요약\n\n## 1. 지난주 한국장 흐름\n\n한 주의 흐름입니다.\n\n## 2. 지난주 한국장을 움직인 핵심 변수\n\n주제 비중입니다.",
    visualSnapshots: [{
      id: "weekly-flow", type: "price_series", role: "weekly_flow", market: "KR", range: "week",
      asOf: "2026-09-04", currency: "KRW", timezone: "Asia/Seoul", freshness: "close_snapshot",
      unit: "percent_change_from_week_start", weekLabel: "08.31~09.06",
      window: { weekStart: "2026-08-31", weekEnd: "2026-09-06" },
      series: [{ ticker: "^KS11", label: "KOSPI", currency: "KRW", timezone: "Asia/Seoul", points: weekPoints, ...series }],
      ...extra,
    }],
    visualRecommendations: [{
      snapshotId: "weekly-flow", market: "KR", variant: "weekly_flow_chart", title: "KR 주요 지수 · 08.31~09.06",
      placement: { market: "KR", sectionRole: "weekly_flow", order: 1 }, ...(defaultPeriod ? { defaultPeriod } : {}),
    }],
  };
}

// 그 주 1시간봉. 하루 세 봉이면 `1W`가 시간봉으로 내려가는지 보기에 충분하다.
const hourlyHistory = ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
  .flatMap((date, day) => ["09:00", "11:00", "13:00"].map((clock, slot) => ({
    time: `${date}T${clock}:00+09:00`, close: 6700 + day * 10 + slot * 3,
  })));

for (const variant of [
  {
    name: "시간봉을 담은 저장본은 그 주를 1시간봉으로 그린다",
    report: weeklyReport(
      {
        daily: { interval: "1d", points: dailyHistory }, hourly: { interval: "1h", points: hourlyHistory },
        weeklyReturn: -1.95, weeklyBaselineDate: "2026-08-28",
      },
      { granularities: ["1h", "1d"], dataSufficiency: { minimumTrendPoints: 8, status: "sufficient" } },
      "1W",
    ),
    card: ".briefing-price-card", absent: ".briefing-weekly-flow-card", unit: "1시간봉",
  },
  {
    name: "시간봉 없이 일봉만 있는 저장본은 그 주를 일봉으로 그린다",
    report: weeklyReport(
      { daily: { interval: "1d", points: dailyHistory }, weeklyReturn: -1.95, weeklyBaselineDate: "2026-08-28" },
      { granularities: ["1d"], dataSufficiency: { minimumTrendPoints: 8, status: "sufficient" } },
      "1W",
    ),
    card: ".briefing-price-card", absent: ".briefing-weekly-flow-card", unit: "일봉",
  },
  {
    name: "일봉이 없는 옛 저장본은 예전 겹쳐 그리기로 남는다",
    report: weeklyReport({}, {}),
    card: ".briefing-weekly-flow-card", absent: ".briefing-price-card", unit: "",
  },
]) {
  test(`weekly index chart — ${variant.name}`, async ({ page }) => {
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      const body = path === "/api/briefings/2026-09-06" ? variant.report : path === "/api/briefings/index" ? { items: [], total: 0 } : {};
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.addInitScript(() => { localStorage.setItem("folio.react.agentClosed", "1"); });
    await page.goto("/#/briefing/2026-09-06/kr/weekly", { waitUntil: "networkidle" });
    await expect(page.locator(variant.card)).toHaveCount(1);
    await expect(page.locator(variant.absent)).toHaveCount(0);
    if (variant.card === ".briefing-price-card") {
      const card = page.locator(".briefing-price-card");
      // 저장본에 분봉이 없으므로 누르면 빈 차트가 될 1D는 아예 만들지 않는다.
      await expect(card.locator('[data-period="1D"]')).toHaveCount(0);
      await expect(card.locator('[data-period="1W"]')).toHaveAttribute("aria-pressed", "true");
      // 곡선(주초=0%)이 아니라 직전 주 종가 기준이므로 값과 기준일을 함께 적는다.
      await expect(card.locator(".briefing-visual-caption")).toContainText("전체 주간 -1.95%(08-28 종가 대비)");
      // 캡션은 저장본이 실제로 가진 봉 단위를 말한다.
      await expect(card.locator(".briefing-visual-caption")).toContainText(`그 주 구간(${variant.unit})`);
      await expect(card.locator(".briefing-visual-header h3")).toHaveText("KOSPI");
      await card.locator('[data-period="1M"]').click();
      await expect(card.locator('[data-period="1M"]')).toHaveAttribute("aria-pressed", "true");
      await expect(card.locator("canvas").first()).toBeVisible();
    } else {
      await expect(page.locator("[data-period]")).toHaveCount(0);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  });
}

test("company reader retains references and Markdown table/list semantics", async ({ page }) => {
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const company = { id: "fixture", company: "기업 예시", title: "기업 예시 분석", markdown: "# 기업 예시 분석\n\n## 사업\n\n· 실제 목록\n\n| 구분 | 값 |\n| --- | --- |\n| 매출 | 100 |\n\n## 참고자료\n\n[공식 자료](https://example.com/official)" };
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(path === "/api/analysis-reports/fixture" ? company : path === "/api/analysis-reports" ? [] : {}) });
  });
  await page.goto("/#/analysis/fixture", { waitUntil: "networkidle" });
  await expect(page.locator(".report-body li")).toContainText("실제 목록");
  await expect(page.locator(".report-body table")).toContainText("매출");
  await expect(page.locator(".report-body a", { hasText: "공식 자료" })).toHaveAttribute("href", "https://example.com/official");
});
