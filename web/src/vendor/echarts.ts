/** ECharts 벤더 번들의 진입점 — `public/vendor/echarts.js`를 만든다.
 *
 *  React 번들(`folio-react.js`)이 아니라 **별도 파일**로 나가서 `window.echarts`로 노출된다.
 *  `public/briefing-visuals.js`(React 밖 브리핑 시각자료)와 React가 같은 인스턴스를 쓰게 하려는 것이고,
 *  React가 `window.LightweightCharts`를 쓰는 것과 같은 방식이라 새 개념이 아니다.
 *
 *  **쓰는 차트·컴포넌트만 등록한다.** 전체를 싣지 않는 것이 이 파일의 존재 이유다
 *  (전체 334KB gzip → 이 세트 264KB, 계획 §2.3.1). 새 차트 종류가 필요하면 여기에 한 줄 더하고
 *  `npm run build:vendor`로 다시 만든다 — 그 크기 증가가 리뷰에 보인다.
 *
 *  렌더러는 SVG다(계획 §4.1): 대비 검사·화면 읽기 경로가 손 SVG와 같은 도구로 검증된다.
 */
import * as core from "echarts/core";
import {
  BarChart,
  BoxplotChart,
  CandlestickChart,
  HeatmapChart,
  LineChart,
  SankeyChart,
  ScatterChart,
  TreemapChart,
} from "echarts/charts";
import {
  DataZoomComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

core.use([
  BarChart,
  BoxplotChart,
  CandlestickChart,
  HeatmapChart,
  LineChart,
  SankeyChart,
  ScatterChart,
  TreemapChart,
  DataZoomComponent,
  GraphicComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  SVGRenderer,
]);

/** 화면이 쓰는 표면만 내보낸다. 네임스페이스 통째로 노출하면 트리셰이킹이 무력해진다. */
(window as unknown as { echarts: unknown }).echarts = {
  init: core.init,
  use: core.use,
  registerTheme: core.registerTheme,
  getInstanceByDom: core.getInstanceByDom,
  version: core.version,
};
