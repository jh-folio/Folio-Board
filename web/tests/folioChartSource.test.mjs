import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const chart = await readFile(new URL("../src/app/charts/FolioChart.tsx", import.meta.url), "utf8");
const theme = await readFile(new URL("../src/app/charts/chartTheme.ts", import.meta.url), "utf8");
const styles = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");

// 텍스트 대체 계약(계획 §5.1). 이 컴포넌트를 쓰는 모든 차트가 물려받으므로 여기서 지킨다.
test("FolioChart requires a label and exposes the picture as an img with that name", () => {
  assert.match(chart, /\n  label: string;/, "label must be required, not optional");
  assert.doesNotMatch(chart, /\n  label\?:/);
  assert.match(chart, /role="img"/);
  assert.match(chart, /aria-label=\{label\}/);
  assert.match(chart, /<ChartDataTable /);
  assert.match(chart, /nextPointIndex\(/);
  assert.match(chart, /<p className="sr-only" role="status">\{announcement\}<\/p>/);
});

// 실측 결함: 그림 자리와 상태 자리가 같은 div로 재사용되면 ECharts가 컨테이너를 비울 때 React가 관리하던
// 자식이 사라지고, 상태가 바뀔 때 React가 없는 노드를 지우려다 화면 전체가 무너졌다(removeChild NotFoundError).
test("FolioChart keeps the chart container and the state notice as separate React nodes", () => {
  assert.match(chart, /key="stage"/);
  assert.match(chart, /key="state"/);
});

// 실측 결함: chart.setTheme()은 인스턴스를 지키지만 확대 범위·범례 선택을 지운다.
test("theme changes go through setTheme and give the user's zoom and legend state back", () => {
  assert.match(chart, /captureInteractionState\(chart\)/);
  assert.match(chart, /chart\.setTheme\(themeFromDocument\(\)\)/);
  assert.match(chart, /restoreInteractionState\(chart, kept\)/);
  assert.ok(chart.indexOf("captureInteractionState(chart)") < chart.indexOf("chart.setTheme(themeFromDocument())"), "capture must come before setTheme");
  assert.ok(chart.indexOf("chart.setTheme(themeFromDocument())") < chart.indexOf("restoreInteractionState(chart, kept)"), "restore must come after setTheme");
});

// 시리즈에 직접 준 색은 setTheme이 못 바꾼다 — 토큰에서 색을 만드는 차트는 option을 함수로 넘겨 다시 만들게 한다.
test("token-derived series colors are rebuilt on theme change instead of going stale", () => {
  assert.ok(chart.includes("export type OptionBuilder = (tokens: TokenReader) => EChartsCoreOption;"));
  assert.ok(chart.includes('typeof optionRef.current === "function") chart.setOption(materializeOption('));
});

test("chart colors come from design tokens, never from literals in the component", () => {
  assert.match(theme, /--folio-chart-\$\{n\}/);
  assert.doesNotMatch(chart, /#[0-9a-fA-F]{6}\b/, "FolioChart must not hardcode colors");
});

test("FolioChart styles exist and use only tokens", () => {
  for (const selector of [".folio-chart", ".folio-chart__stage", ".folio-chart__state", ".folio-chart__stale"]) {
    assert.ok(styles.includes(selector), `${selector} missing`);
  }
  assert.match(styles, /\.folio-chart__stage:focus-visible\s*\{/);
});
