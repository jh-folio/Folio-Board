import type { EChartsType } from "./echarts";

/** 사용자가 차트에서 조작한 상태 — 확대 범위와 범례 선택.
 *
 *  **`chart.setTheme()`은 이 상태를 지운다.** 인스턴스는 그대로인데(다시 만들지 않는다) 색이 갈리는 순간
 *  `dataZoom`이 0~100으로, 범례 선택이 전부 켜짐으로 돌아간다(6.1.0, 브라우저에서 실측). 계획 §2.3.1은
 *  처음에 이것이 남는다고 적었으나 검증하지 않은 가정이었고 틀렸다. 그래서 테마를 바꾸기 전에 읽어 두고
 *  바꾼 뒤에 되돌려 놓는다 — 다크 모드를 켰다고 확대해 둔 구간이 풀리면 안 된다.
 */
export interface InteractionState {
  dataZoom: Array<{ start?: number; end?: number }>;
  legend: Array<{ selected?: Record<string, boolean> }>;
}

type ReadableOption = {
  dataZoom?: Array<{ start?: number; end?: number }>;
  legend?: Array<{ selected?: Record<string, boolean> }>;
};

export function captureInteractionState(chart: Pick<EChartsType, "getOption">): InteractionState {
  const option = chart.getOption() as ReadableOption;
  return {
    dataZoom: (option.dataZoom || []).map((zoom) => ({ start: zoom.start, end: zoom.end })),
    legend: (option.legend || []).map((legend) => ({ selected: legend.selected ? { ...legend.selected } : undefined })),
  };
}

/** 읽어 둔 상태를 병합으로 되돌린다. 값이 없는 항목은 건드리지 않는다. */
export function restoreInteractionState(chart: Pick<EChartsType, "setOption">, state: InteractionState): void {
  const patch: Record<string, unknown> = {};
  if (state.dataZoom.some((zoom) => zoom.start !== undefined || zoom.end !== undefined)) patch.dataZoom = state.dataZoom;
  if (state.legend.some((legend) => legend.selected)) patch.legend = state.legend;
  if (Object.keys(patch).length) chart.setOption(patch);
}
