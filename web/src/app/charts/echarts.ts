/** `window.echarts`로 들어오는 벤더 번들에 대한 타입과 접근자.
 *
 *  ECharts는 React 번들에 들어 있지 않다 — `public/vendor/echarts.js`(`npm run build:vendor`)가
 *  따로 실려 `window.echarts`가 된다. 앱 소스는 **타입만** 가져오고(`import type`) 실행 코드는
 *  여기 한 곳에서만 받는다. 그래야 같은 라이브러리가 React 번들에 두 벌 실리지 않는다
 *  (`vendorScriptsSource.test.mjs`가 지킨다).
 */
import type { EChartsCoreOption, EChartsType } from "echarts/core";

export type { EChartsCoreOption, EChartsType };

/** 테마 객체. 색은 해석된 값(`#2f6fb0`)이어야 한다 — `var(--x)`는 SVG 속성에서 풀리지 않는다. */
export type FolioEChartsTheme = Record<string, unknown>;

export interface EChartsApi {
  init: (
    dom: HTMLElement | null,
    theme?: string | FolioEChartsTheme | null,
    opts?: { renderer?: "svg" | "canvas"; ssr?: boolean; width?: number; height?: number },
  ) => EChartsType;
  use: (extension: unknown) => void;
  registerTheme: (name: string, theme: FolioEChartsTheme) => void;
  getInstanceByDom: (dom: HTMLElement) => EChartsType | undefined;
  version: string;
}

declare global {
  interface Window {
    echarts?: EChartsApi;
  }
}

/** 벤더 스크립트가 아직 안 실렸거나 실패했으면 null. 화면은 이 경우를 오류 상태로 그린다. */
export function getEcharts(): EChartsApi | null {
  return typeof window !== "undefined" && window.echarts ? window.echarts : null;
}
