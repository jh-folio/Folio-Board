/** 테스트 전용 — 화면에 실리는 벤더 번들(public/vendor/echarts.js)을 Node에서 실행해 window.echarts를 돌려준다. */
import vendorSource from "../../../../public/vendor/echarts.js?raw";
import type { EChartsApi } from "./echarts";

export function loadVendorEcharts(): EChartsApi {
  const scope: Record<string, unknown> = {};
  scope.window = scope;
  scope.self = scope;
  new Function("window", "self", vendorSource)(scope, scope);
  return scope.echarts as EChartsApi;
}
