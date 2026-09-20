import type { EChartsApi } from "./echarts";

/** 트리맵 타일의 크기를 **그리기 전에** 얻는다 — 히트맵 라벨 계획의 입력(계획 §6.5).
 *
 *  squarify는 자료와 크기의 순수 함수라, DOM 없는 ssr 인스턴스에 같은 시리즈 설정으로 배치만 시키면
 *  진짜 차트와 같은 좌표가 나온다. 그 폭·높이로 라벨이 들어갈지 미리 정하면 그린 뒤 DOM을 읽을 필요가
 *  없고(수렴 루프·폴링 없음), ECharts가 넘치는 라벨을 `...`로 자르는 일도 없다.
 *
 *  **주의: 배치를 읽는 경로는 ECharts의 공개 API가 아니다**(`getModel().getSeriesByIndex(0).getData().tree`
 *  의 `getLayout()`). 그래서 (1) 벤더 파일이 정확 고정 버전이고, (2) `treemapLayout.test.ts`가 실제 벤더
 *  번들로 이 경로를 매번 확인하며(ECharts를 올리면 여기서 먼저 걸린다), (3) 읽기에 실패하면 이 함수는
 *  `null`을 돌려주고 호출자가 안전한 추정으로 물러난다 — 틀린 크기를 조용히 내주지 않는다.
 */
export interface TileRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** `id`가 있는 노드만 돌려준다. 실패하거나 유한하지 않은 값이 하나라도 있으면 null. */
export function probeTreemapLayout(
  echarts: Pick<EChartsApi, "init">,
  args: { series: Record<string, unknown>; width: number; height: number },
): Map<string, TileRect> | null {
  if (!(args.width > 0) || !(args.height > 0)) return null;
  // ssr 인스턴스는 dispose하지 않으면 Node 프로세스가 끝나지 않는다(6.1.0 실측). 반드시 finally에서 푼다.
  let chart: ReturnType<EChartsApi["init"]> | null = null;
  try {
    chart = echarts.init(null, null, { renderer: "svg", ssr: true, width: args.width, height: args.height });
    chart.setOption({
      animation: false,
      // 진짜 차트와 같은 시리즈 설정(머리띠 높이·테두리·간격 포함)을 그대로 넘긴다 — 다르면 배치가 다르다.
      series: [{ ...args.series, type: "treemap" }],
    });
    // 비공개 경로 — 위 주석 참고.
    const model = (chart as unknown as { getModel: () => { getSeriesByIndex: (i: number) => unknown } }).getModel();
    const data = (model.getSeriesByIndex(0) as { getData: () => TreemapData }).getData();
    const rects = new Map<string, TileRect>();
    for (let index = 0; index < data.count(); index += 1) {
      const node = data.tree.getNodeByDataIndex(index);
      const layout = node.getLayout();
      const id = node.getModel().get("id");
      if (id == null) continue;
      if (!layout || ![layout.x, layout.y, layout.width, layout.height].every(Number.isFinite)) return null;
      rects.set(String(id), { x: layout.x, y: layout.y, width: layout.width, height: layout.height });
    }
    return rects;
  } catch {
    return null;
  } finally {
    chart?.dispose();
  }
}

type TreemapData = {
  count: () => number;
  tree: {
    getNodeByDataIndex: (index: number) => {
      getLayout: () => { x: number; y: number; width: number; height: number } | null;
      getModel: () => { get: (key: string) => unknown };
    };
  };
};
