import { describe, expect, it } from "vitest";

import { captureInteractionState, restoreInteractionState } from "./chartInteractionState";
import { buildChartTheme } from "./chartTheme";
import { loadVendorEcharts } from "./vendorEcharts.testutil";

const echarts = loadVendorEcharts();

const option = {
  animation: false,
  legend: { data: ["매출", "영업이익"] },
  xAxis: { type: "category", data: ["a", "b", "c", "d", "e"] },
  yAxis: {},
  dataZoom: [{ type: "slider", start: 0, end: 100 }],
  series: [
    { name: "매출", type: "line", data: [1, 2, 3, 4, 5] },
    { name: "영업이익", type: "line", data: [2, 1, 4, 3, 5] },
  ],
};
const reader = (dark: boolean) => (name: string) => (dark ? { "--folio-ink-muted": "#b4bbcb" } : { "--folio-ink-muted": "#44505f" })[name as "--folio-ink-muted"] ?? "";

function withChart(run: (chart: ReturnType<typeof echarts.init>) => void) {
  // ssr 인스턴스는 dispose하지 않으면 Node가 끝나지 않는다(6.1.0).
  const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 600, height: 300 });
  try {
    chart.setOption(option);
    run(chart);
  } finally {
    chart.dispose();
  }
}

const zoomOf = (chart: ReturnType<typeof echarts.init>) => {
  const zoom = (chart.getOption() as { dataZoom: Array<{ start: number; end: number }> }).dataZoom[0];
  return [Math.round(zoom.start), Math.round(zoom.end)];
};
const selectedOf = (chart: ReturnType<typeof echarts.init>) => (chart.getOption() as { legend: Array<{ selected?: Record<string, boolean> }> }).legend[0].selected;

describe("테마 전환과 사용자 조작 상태", () => {
  it("setTheme은 확대 범위와 범례 선택을 지운다 — 이 테스트가 그 사실을 고정한다", () => {
    withChart((chart) => {
      chart.dispatchAction({ type: "dataZoom", start: 20, end: 60 });
      chart.dispatchAction({ type: "legendUnSelect", name: "영업이익" });
      expect(zoomOf(chart)).toEqual([20, 60]);
      expect(selectedOf(chart)?.["영업이익"]).toBe(false);

      chart.setTheme(buildChartTheme(reader(true)));

      // 인스턴스는 같고 색은 갈렸지만 조작 상태는 초기값으로 돌아간다(브라우저 실측과 같다).
      expect(zoomOf(chart)).toEqual([0, 100]);
      expect(selectedOf(chart)?.["영업이익"]).not.toBe(false);
    });
  });

  it("읽어 두었다 되돌리면 테마가 바뀌어도 조작 상태가 남는다", () => {
    withChart((chart) => {
      chart.dispatchAction({ type: "dataZoom", start: 20, end: 60 });
      chart.dispatchAction({ type: "legendUnSelect", name: "영업이익" });

      const kept = captureInteractionState(chart);
      chart.setTheme(buildChartTheme(reader(true)));
      restoreInteractionState(chart, kept);

      expect(zoomOf(chart)).toEqual([20, 60]);
      expect(selectedOf(chart)?.["영업이익"]).toBe(false);
      expect(selectedOf(chart)?.["매출"]).toBe(true);
    });
  });

  it("조작하지 않은 차트는 되돌리기가 아무것도 바꾸지 않는다", () => {
    withChart((chart) => {
      const kept = captureInteractionState(chart);
      chart.setTheme(buildChartTheme(reader(true)));
      restoreInteractionState(chart, kept);
      expect(zoomOf(chart)).toEqual([0, 100]);
    });
  });

  it("dataZoom·범례가 없는 차트에서도 안전하다", () => {
    const chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: 300, height: 200 });
    try {
      chart.setOption({ animation: false, series: [{ type: "treemap", data: [{ name: "a", value: 1 }] }] });
      const kept = captureInteractionState(chart);
      expect(kept).toEqual({ dataZoom: [], legend: [] });
      expect(() => restoreInteractionState(chart, kept)).not.toThrow();
    } finally {
      chart.dispose();
    }
  });
});
