import { describe, expect, it } from "vitest";

import type { EChartsApi } from "./echarts";
import { probeTreemapLayout } from "./treemapLayout";
import { loadVendorEcharts } from "./vendorEcharts.testutil";

const echarts = loadVendorEcharts();

const series = {
  squareRatio: 1,
  width: "100%",
  height: "100%",
  top: 0, left: 0, right: 0, bottom: 0,
  breadcrumb: { show: false },
  data: [
    { id: "a", name: "A", value: 60, children: [{ id: "a1", name: "A1", value: 40 }, { id: "a2", name: "A2", value: 20 }] },
    { id: "b", name: "B", value: 40 },
  ],
};

type Rects = Map<string, { x: number; y: number; width: number; height: number }>;

// 이 파일은 canary다(계획 §6.5). 배치를 읽는 경로가 ECharts 비공개 API라서, 벤더 번들을 올리는 사람이
// 여기서 먼저 걸린다. 실패하면 히트맵 라벨 계획의 여백(7px)도 다시 재야 한다.
describe("트리맵 배치 선계산 canary", () => {
  it("벤더 번들에서 모든 노드의 폭·높이가 유한하게 읽힌다", () => {
    const rects = probeTreemapLayout(echarts, { series, width: 800, height: 600 }) as Rects | null;
    expect(rects).not.toBeNull();
    expect([...rects!.keys()].sort()).toEqual(["a", "a1", "a2", "b"]);
    for (const rect of rects!.values()) {
      expect(Number.isFinite(rect.width) && rect.width > 0).toBe(true);
      expect(Number.isFinite(rect.height) && rect.height > 0).toBe(true);
    }
  });

  it("squarify 결과가 고정된 버전에서 바뀌지 않았다", () => {
    // ECharts 6.1.0 실측. 값은 면적에 비례한다: A=60% → 폭 480, B=40% → 폭 320(높이는 캔버스 전체).
    const rects = probeTreemapLayout(echarts, { series, width: 800, height: 600 }) as Rects;
    const size = (id: string) => [Math.round(rects.get(id)!.width), Math.round(rects.get(id)!.height)];
    expect(size("a")).toEqual([480, 600]);
    expect(size("a1")).toEqual([480, 400]);
    expect(size("a2")).toEqual([480, 200]);
    expect(size("b")).toEqual([320, 600]);
  });

  it("같은 입력은 같은 배치다 — 결정적이다", () => {
    const first = probeTreemapLayout(echarts, { series, width: 640, height: 480 });
    const second = probeTreemapLayout(echarts, { series, width: 640, height: 480 });
    expect([...first!]).toEqual([...second!]);
  });

  it("머리띠 높이는 배치에 들어간다 — 진짜 차트와 같은 설정을 넘겨야 하는 이유", () => {
    const flat = probeTreemapLayout(echarts, { series, width: 800, height: 600 }) as Rects;
    const withHeader = probeTreemapLayout(
      echarts,
      { series: { ...series, upperLabel: { show: true, height: 26 } }, width: 800, height: 600 },
    ) as Rects;
    expect(withHeader.get("a1")!.height).toBeLessThan(flat.get("a1")!.height);
  });

  it("읽지 못하면 null이다 — 틀린 크기를 조용히 내주지 않는다", () => {
    const broken = { init: () => { throw new Error("no renderer"); } } as unknown as Pick<EChartsApi, "init">;
    expect(probeTreemapLayout(broken, { series, width: 800, height: 600 })).toBeNull();
    expect(probeTreemapLayout(echarts, { series, width: 0, height: 600 })).toBeNull();
    // 배치 경로가 사라진 버전을 흉내 낸다.
    const noModel = { init: () => ({ setOption() {}, dispose() {} }) } as unknown as Pick<EChartsApi, "init">;
    expect(probeTreemapLayout(noModel, { series, width: 800, height: 600 })).toBeNull();
  });

  it("ssr 인스턴스를 남기지 않는다 — 6.1.0은 dispose하지 않으면 Node가 끝나지 않는다", () => {
    let disposed = 0;
    const spy = {
      init: (...args: Parameters<EChartsApi["init"]>) => {
        const chart = echarts.init(...args);
        const original = chart.dispose.bind(chart);
        chart.dispose = () => { disposed += 1; original(); };
        return chart;
      },
    } as Pick<EChartsApi, "init">;
    probeTreemapLayout(spy, { series, width: 800, height: 600 });
    probeTreemapLayout({ init: () => { throw new Error("x"); } } as unknown as Pick<EChartsApi, "init">, { series, width: 800, height: 600 });
    expect(disposed).toBe(1);
  });
});
