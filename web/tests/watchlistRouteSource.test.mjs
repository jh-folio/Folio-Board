import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("Watchlist route owns list, overview, resolve, save, and detail APIs", async () => {
  const source = await readFile(new URL("../src/app/WatchlistRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /data-watchlist-route/);
  assert.match(source, /\/api\/watchlist"/);
  assert.match(source, /\/api\/watchlist\/overview/);
  assert.match(source, /\/api\/watchlist\/resolve\?keyword=/);
  assert.match(source, /\/api\/watchlist\/detail\?item=/);
});

test("Watchlist route preserves legacy visual class contracts", async () => {
  const source = await readFile(new URL("../src/app/WatchlistRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /RouteHero/);
  assert.match(source, /watchlist-editor input-panel/);
  assert.match(source, /watchlist-grid/);
  assert.match(source, /watchlist-card/);
  assert.match(source, /watchlist-card-delete/);
  assert.match(source, /watchlist-detail-inline/);
  assert.match(source, /watchlist-detail-dialog/);
  assert.match(source, /compact-item/);
});

test("상세는 네이티브 차트·실적 패널과 대화·Agent 맥락을 함께 싣는다", async () => {
  const source = await readFile(new URL("../src/app/WatchlistRoute.tsx", import.meta.url), "utf8");

  // 위젯 브리지는 이 모달이 마지막 소비자였다. 되살아나면 iframe 세 장이 다시 쌓인다.
  assert.doesNotMatch(source, /FolioTradingViewWidgets/);
  assert.match(source, /<MarketChartFigure/);
  assert.match(source, /<EarningsPanel/);
  assert.match(source, /surface: "watchlist_detail"/);
  assert.match(source, /ConsultationEntry/);
  assert.match(source, /setReactAgentContextScope/);
});

test("AppShell renders WatchlistRoute on the watchlist route", async () => {
  const source = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");

  assert.match(source, /<WatchlistRoute\s*\/>/);
  assert.match(source, /route\.id === "watchlist"/);
  assert.match(source, /renderRoutePane/);
});

test("watchlist route no longer falls back to the legacy watchlist view", async () => {
  const source = await readFile(new URL("../src/app/routes.ts", import.meta.url), "utf8");

  assert.doesNotMatch(source, /id: "watchlist", label: "워치리스트", group: "portfolio", legacyViewId: "watchlist"/);
});

test("후보 선택이 자기가 만든 입력 변경으로 초기화되지 않는다", async () => {
  const hook = await readFile(new URL("../src/app/companyAnalysis/useCompanyResolution.ts", import.meta.url), "utf8");
  const route = await readFile(new URL("../src/app/WatchlistRoute.tsx", import.meta.url), "utf8");

  // 선택은 입력칸을 그 회사 이름으로 바꾼다. 훅이 그 변경을 새 타이핑으로 읽으면
  // 방금 고른 후보가 지워져 재조회가 끝날 때까지 후보 목록이 다시 뜨고,
  // 그 창에서 Enter를 누르면 이름 안의 쉼표가 구분자로 쪼개진다.
  assert.match(hook, /pickedQueryRef/);
  assert.match(hook, /if \(pickedQueryRef\.current !== null && pickedQueryRef\.current === query\) return;/);
  assert.match(hook, /const pick = useCallback\(/);
  assert.match(hook, /return \{ resolution, pending, picked, setPicked, pick, effective \}/);

  // 워치리스트는 선택과 입력 변경을 한 번에 알린다.
  assert.match(route, /pick\(candidate, candidate\.name\); setKeyword\(candidate\.name\);/);
  assert.doesNotMatch(route, /setPicked\(candidate\)/);
});
