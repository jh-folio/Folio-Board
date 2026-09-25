import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const figure = await readFile(new URL("../src/app/dashboard/MarketChartFigure.tsx", import.meta.url), "utf8");
const styles = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");

// 가격 차트는 canvas라 화면 읽기 프로그램이 볼 것이 없다. 아래 셋이 텍스트 대체 계약이다
// (계획 §5.1) — 하나라도 빠지면 공개 화면 WCAG 2.2 AA 계약이 조용히 깨진다.
test("market chart names the picture, reads bars by keyboard, and ships a data table", () => {
  assert.match(figure, /"aria-label": summaryLabel/);
  assert.match(figure, /tabIndex: 0, onKeyDown: onStageKeyDown/);
  assert.match(figure, /nextBarIndex\(/);
  assert.match(figure, /<p className="sr-only" role="status">\{announcement\}<\/p>/);
  assert.match(figure, /<ChartDataTable /);
});

// role="img"는 자손을 숨긴다. 이 무대 안에는 라이선스가 요구하는 TradingView 출처 링크가 있어
// img로 두면 그 링크가 화면 읽기 프로그램에서 사라진다(axe nested-interactive로 실측).
test("market chart stage is a group, not an img, so the required attribution link stays reachable", () => {
  assert.match(figure, /role: "group"/);
  assert.doesNotMatch(figure, /role: "img"/);
  assert.match(figure, /attributionLogo: true/);
});

test("chart data table and keyboard focus ring have styles", () => {
  assert.match(styles, /\.chart-data__scroll\b/);
  assert.match(styles, /\.cockpit-chart-stage:focus-visible\s*\{/);
});
