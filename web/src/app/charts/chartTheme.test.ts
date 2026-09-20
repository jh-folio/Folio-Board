import { describe, expect, it } from "vitest";

import { buildChartTheme, resolveToken } from "./chartTheme";
import { resolveChartState } from "./FolioChart";

const light: Record<string, string> = {
  "--folio-ink": "#07111f",
  "--folio-ink-muted": "#44505f",
  "--folio-border": "#dfe3ea",
  "--folio-surface-dark": "#101722",
  "--folio-ink-inverse": "#ffffff",
  "--folio-border-strong": "#c5ccd8",
  "--folio-chart-1": "#2f6fb0",
  "--folio-chart-2": "#8a2c52",
  "--folio-chart-3": "#3f7a3a",
  "--folio-chart-4": "#b8862a",
  "--folio-chart-5": "#6a52a8",
};
const dark: Record<string, string> = { ...light, "--folio-ink": "#f1f2f4", "--folio-ink-muted": "#b4bbcb", "--folio-chart-1": "#4a8cc7" };
const reader = (table: Record<string, string>) => (name: string) => table[name] ?? "";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;

describe("토큰 → ECharts 테마", () => {
  it("범주 팔레트는 검증된 --folio-chart-1~5를 그대로 순환한다", () => {
    expect((buildChartTheme(reader(light)) as { color: string[] }).color).toEqual(["#2f6fb0", "#8a2c52", "#3f7a3a", "#b8862a", "#6a52a8"]);
  });

  it("라이트와 다크는 같은 구조에 다른 색을 낸다 — 테마 전환이 setTheme 한 번이면 되는 이유", () => {
    const a = buildChartTheme(reader(light)) as Loose;
    const b = buildChartTheme(reader(dark)) as Loose;
    expect(Object.keys(a)).toEqual(Object.keys(b));
    expect(a.textStyle.color).toBe("#44505f");
    expect(b.textStyle.color).toBe("#b4bbcb");
    expect(a.color[0]).not.toBe(b.color[0]);
  });

  it("툴팁은 라이트에서도 어두운 면이다 — 시장 차트 툴팁과 같다", () => {
    const theme = buildChartTheme(reader(light)) as Loose;
    expect(theme.tooltip.backgroundColor).toBe("#101722");
    expect(theme.tooltip.textStyle.color).toBe("#ffffff");
  });

  it("ECharts가 못 푸는 값(var(), color-mix())은 쓰지 않고 대체색을 쓴다", () => {
    expect(resolveToken(() => "var(--x)", "--folio-ink")).toBe("#07111f");
    expect(resolveToken(() => "color-mix(in srgb, red 40%, transparent)", "--folio-ink")).toBe("#07111f");
    expect(resolveToken(() => "  ", "--folio-chart-1")).toBe("#2f6fb0");
    expect(resolveToken(() => "#123456", "--folio-ink")).toBe("#123456");
    // 알려지지 않은 토큰도 색 문자열을 돌려준다(빈 문자열이 SVG 속성에 들어가면 검정으로 그려진다).
    expect(resolveToken(() => "", "--unknown")).toMatch(/^#/);
  });

  it("폰트는 넘겨 준 값을 모든 글자 요소에 준다", () => {
    const theme = buildChartTheme(reader(light), "SUIT, sans-serif") as Loose;
    expect(theme.textStyle.fontFamily).toBe("SUIT, sans-serif");
    expect(theme.legend.textStyle.fontFamily).toBe("SUIT, sans-serif");
    expect(theme.tooltip.textStyle.fontFamily).toBe("SUIT, sans-serif");
  });
});

describe("차트 상태", () => {
  it("option이 있으면 ready, 없으면 loading이 기본이다", () => {
    expect(resolveChartState({ hasOption: true, libraryReady: true })).toBe("ready");
    expect(resolveChartState({ hasOption: false, libraryReady: true })).toBe("loading");
  });

  it("명시한 상태를 따른다", () => {
    for (const state of ["loading", "empty", "error", "stale", "ready"] as const) {
      expect(resolveChartState({ state, hasOption: true, libraryReady: true })).toBe(state);
    }
  });

  it("라이브러리가 없으면 그리는 상태는 오류가 된다 — 그릴 수 없는데 그림이라 말하지 않는다", () => {
    expect(resolveChartState({ state: "ready", hasOption: true, libraryReady: false })).toBe("error");
    expect(resolveChartState({ state: "stale", hasOption: true, libraryReady: false })).toBe("error");
    // 이미 그리지 않는 상태는 그대로다.
    expect(resolveChartState({ state: "empty", hasOption: false, libraryReady: false })).toBe("empty");
    expect(resolveChartState({ state: "loading", hasOption: false, libraryReady: false })).toBe("loading");
  });
});
