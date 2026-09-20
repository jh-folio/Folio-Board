/** 디자인 토큰 → ECharts 테마.
 *
 *  ECharts는 SVG 속성에 색을 쓰므로 `var(--folio-ink)` 같은 CSS 변수를 풀지 못한다. 토큰을 **해석된 값**으로
 *  읽어 테마 객체를 만들고, 테마가 바뀌면 인스턴스를 다시 만들지 않고 `chart.setTheme()`으로 갈아 낀다
 *  (6.1.0, 계획 §2.3.1). 그래서 확대 범위·범례 선택 같은 사용자 조작이 테마 전환 뒤에도 남는다.
 *
 *  새 색을 만들지 않는다 — 색은 `features/frontend_ui/DESIGN_SYSTEM.md`의 토큰이 이긴다.
 *  시리즈에 직접 준 색(히트맵 9단 색처럼 테마와 무관한 것)은 테마가 덮지 않는다.
 */
import type { FolioEChartsTheme } from "./echarts";

/** 토큰 하나를 읽는 함수. 브라우저에서는 `getComputedStyle`, 테스트에서는 맵이다. */
export type TokenReader = (name: string) => string;

const FALLBACK: Record<string, string> = {
  "--folio-ink": "#07111f",
  "--folio-ink-muted": "#44505f",
  "--folio-border": "#dfe3ea",
  "--folio-border-strong": "#c5ccd8",
  "--folio-surface-clean": "#ffffff",
  "--folio-surface-dark": "#101722",
  "--folio-ink-inverse": "#ffffff",
  "--folio-chart-1": "#2f6fb0",
  "--folio-chart-2": "#8a2c52",
  "--folio-chart-3": "#3f7a3a",
  "--folio-chart-4": "#b8862a",
  "--folio-chart-5": "#6a52a8",
};

/** 읽은 값이 비었거나 색이 아니면(`color-mix(...)`, `var(...)`) 대체값을 쓴다. */
export function resolveToken(read: TokenReader, name: string): string {
  const value = String(read(name) || "").trim();
  if (!value || /^(var|color-mix)\(/i.test(value)) return FALLBACK[name] ?? "#888888";
  return value;
}

/** 폰트는 토큰이 아니라 본문에서 상속한 값을 쓴다 — 차트 글자가 주변 글자와 어긋나지 않게. */
export function buildChartTheme(read: TokenReader, fontFamily = "inherit"): FolioEChartsTheme {
  const t = (name: string) => resolveToken(read, name);
  const axis = {
    axisLine: { lineStyle: { color: t("--folio-border") } },
    axisTick: { lineStyle: { color: t("--folio-border") } },
    axisLabel: { color: t("--folio-ink-muted") },
    splitLine: { lineStyle: { color: t("--folio-border") } },
    nameTextStyle: { color: t("--folio-ink-muted") },
  };
  return {
    // 범주 시리즈가 순환하는 팔레트. 검증된 다섯 색이다(DESIGN_SYSTEM.md "차트 데이터색").
    color: [1, 2, 3, 4, 5].map((n) => t(`--folio-chart-${n}`)),
    backgroundColor: "transparent",
    textStyle: { color: t("--folio-ink-muted"), fontFamily },
    title: { textStyle: { color: t("--folio-ink"), fontFamily }, subtextStyle: { color: t("--folio-ink-muted"), fontFamily } },
    legend: { textStyle: { color: t("--folio-ink-muted"), fontFamily } },
    categoryAxis: axis,
    valueAxis: axis,
    timeAxis: axis,
    logAxis: axis,
    // 툴팁은 시장 차트(`.market-chart-tooltip`)와 같은 어두운 면 — 라이트에서도 어둡다.
    tooltip: {
      backgroundColor: t("--folio-surface-dark"),
      borderColor: t("--folio-border-strong"),
      textStyle: { color: t("--folio-ink-inverse"), fontFamily },
    },
    // 그리드 없는 시리즈(히트맵 등)의 기본 글자 색도 같은 토큰을 따른다.
    graph: { color: [1, 2, 3, 4, 5].map((n) => t(`--folio-chart-${n}`)) },
  };
}

/** 현재 문서의 토큰으로 테마를 만든다. 브라우저 전용. */
export function themeFromDocument(): FolioEChartsTheme {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  const fontFamily = getComputedStyle(document.body).fontFamily || "inherit";
  return buildChartTheme((name) => styles.getPropertyValue(name), fontFamily);
}

/** 테마 전환을 듣는다. 반환 함수로 해제한다.
 *
 *  두 신호를 함께 듣는다: `data-theme` 속성(모든 경로가 바꾼다)과 `folio:theme-changed`(사용자 선택 시).
 *  같은 프레임에 둘이 오면 한 번만 부른다. */
export function subscribeThemeChange(onChange: () => void): () => void {
  let frame = 0;
  const schedule = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      onChange();
    });
  };
  const observer = new MutationObserver(schedule);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("folio:theme-changed", schedule);
  return () => {
    if (frame) cancelAnimationFrame(frame);
    observer.disconnect();
    window.removeEventListener("folio:theme-changed", schedule);
  };
}
