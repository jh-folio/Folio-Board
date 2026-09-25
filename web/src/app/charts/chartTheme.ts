/** 디자인 토큰 → ECharts 테마.
 *
 *  ECharts는 SVG 속성에 색을 쓰므로 `var(--folio-ink)` 같은 CSS 변수를 풀지 못한다. 토큰을 **해석된 값**으로
 *  읽어 테마 객체를 만들고, 테마가 바뀌면 인스턴스를 다시 만들지 않고 `chart.setTheme()`으로 갈아 낀다
 *  (6.1.0). `setTheme`은 확대 범위·범례 선택을 지우므로 되돌리는 일은 `FolioChart`가 맡는다.
 *
 *  **이 파일이 앱 차트의 기본 인상을 정한다.** ECharts의 기본값(점마다 동그라미, 굵은 눈금선, 파란 슬라이더)은
 *  이 앱의 조용한 손 SVG 차트와 어울리지 않는다. 그래서 여기서 지면의 규칙으로 덮는다:
 *  - 선에는 점을 찍지 않는다(호버한 지점만 드러난다). 굵기 2.
 *  - 값 축은 선·눈금 없이 가는 격자만, 카테고리 축은 아래 선 하나만.
 *  - 글자는 12px 무채색. 강조는 색이 아니라 잉크 농도로 한다.
 *  - 슬라이더는 배경 없는 옅은 띠. 범례는 작은 둥근 사각.
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
  "--folio-ink-subtle": "#6b7686",
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

/** `#rgb`·`#rrggbb`에 투명도를 준다. 그 밖의 형식은 그대로 돌려준다(ECharts가 알아서 파싱한다).
 *
 *  손 SVG 차트의 `color-mix(in srgb, X 45%, transparent)`(옅은 톤)와 같은 값이다 — ECharts는
 *  `color-mix()`를 못 읽으므로 rgba로 풀어 쓴다. */
export function withAlpha(color: string, alpha: number): string {
  const match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (!match) return color;
  const hex = match[1].length === 3 ? match[1].replace(/./g, (c) => c + c) : match[1];
  const value = parseInt(hex, 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

/** 캐스케이드 차트(매출→영업이익→순이익처럼 한 흐름)의 색 — 잉크, 그 차트의 색 하나, 그 옅은 톤.
 *
 *  범주 색 여러 개를 섞으면 알록달록하다. 규칙은 `DESIGN_SYSTEM.md` "차트 데이터색"과 같고
 *  `AnalysisCharts`·`FundamentalsPanel`이 이미 이 세 값을 쓴다(잉크 42%, 옅은 톤 45%).
 *  첫 계열(규모 기준)이 잉크, 나머지가 색과 그 옅은 톤이다. */
export function cascadeColors(read: TokenReader, accentToken: string): [string, string, string] {
  const ink = resolveToken(read, "--folio-ink");
  const accent = resolveToken(read, accentToken);
  return [withAlpha(ink, 0.42), accent, withAlpha(accent, 0.45)];
}

/** 폰트는 토큰이 아니라 본문에서 상속한 값을 쓴다 — 차트 글자가 주변 글자와 어긋나지 않게. */
export function buildChartTheme(read: TokenReader, fontFamily = "inherit"): FolioEChartsTheme {
  const t = (name: string) => resolveToken(read, name);
  const ink = t("--folio-ink");
  const muted = t("--folio-ink-muted");
  const subtle = t("--folio-ink-subtle");
  const border = t("--folio-border");
  const label = { color: subtle, fontSize: 12, fontFamily };

  // 값 축: 선도 눈금도 없이 가는 격자만. 손 SVG 차트의 0.5px 격자와 같은 인상이다.
  const valueAxis = {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { ...label, margin: 10 },
    splitLine: { show: true, lineStyle: { color: border, width: 1, opacity: 0.7 } },
    nameTextStyle: { color: subtle, fontSize: 12, fontFamily },
  };
  // 카테고리·시간 축: 아래 선 하나. 격자는 값 축이 그린다.
  const categoryAxis = {
    axisLine: { show: true, lineStyle: { color: border } },
    axisTick: { show: false },
    axisLabel: { ...label, margin: 12 },
    splitLine: { show: false },
    nameTextStyle: { color: subtle, fontSize: 12, fontFamily },
  };

  const palette = [1, 2, 3, 4, 5].map((n) => t(`--folio-chart-${n}`));
  return {
    // 범주 시리즈가 순환하는 팔레트. 검증된 다섯 색이다(DESIGN_SYSTEM.md "차트 데이터색").
    // 캐스케이드 차트는 이 팔레트를 쓰지 않고 `cascadeColors()`를 시리즈에 직접 준다.
    color: palette,
    backgroundColor: "transparent",
    textStyle: { color: muted, fontSize: 12, fontFamily },
    title: { textStyle: { color: ink, fontFamily }, subtextStyle: { color: muted, fontFamily } },
    legend: {
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 18,
      textStyle: { color: muted, fontSize: 12, fontFamily },
    },
    categoryAxis,
    valueAxis,
    timeAxis: { ...categoryAxis },
    logAxis: { ...valueAxis },
    // 선: 점을 찍지 않는다. 축 트리거 호버 때 그 지점만 드러난다.
    line: {
      showSymbol: false,
      symbol: "circle",
      symbolSize: 7,
      smooth: false,
      lineStyle: { width: 2 },
      emphasis: { lineStyle: { width: 2 } },
    },
    // 막대: 위쪽만 살짝 둥글게(손 SVG 막대와 같다), 너무 넓어지지 않게.
    bar: { barMaxWidth: 28, itemStyle: { borderRadius: [3, 3, 0, 0] } },
    scatter: { symbolSize: 8 },
    // 확대 슬라이더: 배경·테두리 없는 옅은 띠. ECharts 기본(파란 채움·굵은 핸들)은 이 앱 톤과 맞지 않는다.
    dataZoom: {
      backgroundColor: "transparent",
      borderColor: "transparent",
      fillerColor: withAlpha(ink, 0.08),
      dataBackground: { lineStyle: { color: border, width: 1 }, areaStyle: { color: withAlpha(ink, 0.04) } },
      selectedDataBackground: { lineStyle: { color: subtle, width: 1 }, areaStyle: { color: withAlpha(ink, 0.08) } },
      handleStyle: { color: t("--folio-surface-clean"), borderColor: subtle, borderWidth: 1 },
      moveHandleStyle: { color: subtle, opacity: 0.5 },
      handleSize: "70%",
      textStyle: { color: subtle, fontSize: 11, fontFamily },
      brushSelect: false,
    },
    // 툴팁은 시장 차트(`.market-chart-tooltip`)와 같은 어두운 면 — 라이트에서도 어둡다.
    tooltip: {
      backgroundColor: t("--folio-surface-dark"),
      borderColor: t("--folio-border-strong"),
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: t("--folio-ink-inverse"), fontSize: 12, fontFamily },
      // 축 트리거의 세로 가이드: 손 SVG 차트의 점선 커서와 같다.
      axisPointer: { lineStyle: { color: subtle, width: 1, type: "dashed" } },
    },
    // 그리드 없는 시리즈(히트맵 등)의 기본 글자 색도 같은 토큰을 따른다.
    graph: { color: palette },
  };
}

/** 브라우저 토큰 읽기. 테마와 캐스케이드 색이 같은 값을 읽도록 한 곳에 둔다. */
export function documentTokenReader(): TokenReader {
  const styles = getComputedStyle(document.documentElement);
  return (name) => styles.getPropertyValue(name);
}

/** 현재 문서의 토큰으로 테마를 만든다. 브라우저 전용. */
export function themeFromDocument(): FolioEChartsTheme {
  const fontFamily = getComputedStyle(document.body).fontFamily || "inherit";
  return buildChartTheme(documentTokenReader(), fontFamily);
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
