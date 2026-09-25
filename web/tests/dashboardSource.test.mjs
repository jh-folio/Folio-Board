import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("Dashboard renders the cockpit only", async () => {
  const source = await readFile(new URL("../src/app/Dashboard.tsx", import.meta.url), "utf8");

  assert.match(source, /data-react-dashboard/);
  assert.match(source, /<ResearchCockpit \/>/);
  // Legacy(위젯 보드 + 투자 리뷰 요약)는 0.5에서 삭제했다. 한 릴리즈만 두기로 한
  // rollback 경로였고, 같은 화면을 두 벌 유지할 이유가 없다.
  assert.doesNotMatch(source, /LegacyMarketWidgetBoard/);
  assert.doesNotMatch(source, /dashboardMode/);
  assert.doesNotMatch(source, /\/api\/investment-review/);
  assert.doesNotMatch(source, /home-launcher/);
  assert.doesNotMatch(source, /오늘의 투자 리뷰/);
});

test("cockpit omits the retired content-change feed", async () => {
  const source = await readFile(new URL("../src/app/dashboard/ResearchCockpit.tsx", import.meta.url), "utf8");

  assert.doesNotMatch(source, /ChangeFeed|changeCounts|오늘의 변화 요약|무엇이 달라졌나/);
  assert.match(source, /<StoryShare/);
  const story = source.indexOf("<StoryShare");
  const calendar = source.indexOf("<MarketCalendar");
  const chart = source.indexOf("<NativeMarketChart");
  assert.ok(story >= 0 && calendar > story, "이야기 비중이 일정 전에 온다");
  assert.ok(chart > calendar, "일정이 차트보다 위다 — 오늘 무엇을 지켜볼지가 가격 움직임보다 먼저 필요하다");
  assert.doesNotMatch(source, /InvestmentImplications/);
});

test("AppShell renders Dashboard on the dashboard route", async () => {
  const source = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");

  assert.match(source, /<Dashboard\s*\/>/);
  assert.match(source, /route\.id === "dashboard"/);
  assert.match(source, /renderRoutePane/);
});

test("AppShell suppresses the global agent dock on the home route", async () => {
  const source = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");

  assert.match(source, /const agentVisible = active\.id !== "home"/);
  assert.match(source, /is-agent-suppressed/);
  assert.match(source, /\{agentVisible && \(/);
});

test("dashboard route no longer falls back to the legacy review view", async () => {
  const source = await readFile(new URL("../src/app/routes.ts", import.meta.url), "utf8");

  assert.doesNotMatch(source, /id: "dashboard", label: "대시보드", group: "home", legacyViewId: "review"/);
});
