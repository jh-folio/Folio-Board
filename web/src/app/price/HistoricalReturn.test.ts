import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { attributionConclusion, HistoricalReturnSection } from "./HistoricalReturn";
import { glanceItems } from "./Guide";
import type { AttributionBlock, SnapshotView } from "./types";

const period: AttributionBlock = {
  status: "available", startFiscalYear: 2020, endFiscalYear: 2025,
  startDate: "2020-12-31", endDate: "2025-12-31", startClose: "100", endClose: "150", priceReturn: "0.5000",
  display: { price: "50.0", growth: "20.0", rerating: "30.0", dividend: "5.0", total: "55.0" },
  earnings: { status: "available", startEps: "10", endEps: "12", startPE: "10", endPE: "12.5" },
  dividend: { status: "available", amount: "5", contribution: "0.0500" }, total: { status: "available", value: "0.5500" },
  benchmark: { status: "available", id: "S&P 500", startClose: "100", endClose: "125", display: { stock: "50.0", index: "25.0", difference: "25.0" } },
};
const viewFor = (block: AttributionBlock) => ({
  methodVersion: "price-scenario-5", snapshotId: "fixed", asOf: "2026-10-01", inputSummary: { price: { currency: "USD" } },
  historicalReturnAttribution: block, results: { scenarios: [], reverse: { breakEvenPE: {} }, decomposition: { status: "unavailable" } },
}) as unknown as SnapshotView;
const render = (block: AttributionBlock) => renderToStaticMarkup(createElement(HistoricalReturnSection, { view: viewFor(block) }));

describe("independent review display boundaries", () => {
  it("uses the exact server price display in the lead, summary and calculation", () => {
    const block = { ...period, endClose: "110.05", priceReturn: "0.1005",
      earnings: { ...period.earnings!, endPE: "9.170833333333333333333333333" },
      dividend: { status: "available", amount: "0", contribution: "0.0000" }, total: { status: "available", value: "0.1005" },
      benchmark: { ...period.benchmark!, display: { stock: "10.0", index: "25.0", difference: "-15.0" } },
      display: { price: "10.0", growth: "20.0", rerating: "-10.0", dividend: "0.0", total: "10.0" } };
    const html = render(block);
    expect(html).toContain("<strong>+10.0%</strong>");
    expect(html).not.toContain("+10.1%");
    const item = glanceItems({ view: viewFor(block), projection: null, criteria: null, horizon: 5 }).find(x => x.key === "historical");
    expect(renderToStaticMarkup(createElement("div", null, item?.body))).toContain("+10.0%");
  });
  it("keeps a known dividend display exact, even at a half-even boundary", () => {
    const html = render({ ...period, dividend: { status: "available", amount: "10.05", contribution: "0.1005" },
      total: { status: "available", value: "0.6005" }, display: { price: "50.0", growth: "20.0", rerating: "30.0", dividend: "10.0", total: "60.0" } });
    expect(html).not.toContain("+10.1%");
    expect(html).toContain("<strong>+10.0%</strong>");
  });
  it("describes missing EPS as missing records and retains available dividends and total", () => {
    const html = render({ ...period, earnings: { status: "unavailable", reason: { code: "attribution_history_too_short", subCode: "missing_endpoint_eps", endFiscalYear: 2025, endpoints: ["end"] } } });
    expect(html).not.toContain("적자 구간");
    expect(html).toContain("주당이익이 없어");
    expect(html).toContain("받은 배당은 시작 주가 대비 +5.0%");
    expect(html).toContain("받은 배당까지 더하면 전체 +55.0%");
    expect(html).not.toContain("price-dec__card");
  });
  it("retains dividend failure when EPS is also unavailable", () => {
    const html = render({ ...period, earnings: { status: "unavailable", reason: { code: "share_event_unknown" } },
      dividend: { status: "unavailable", reason: { code: "dividend_unit_unverified" } }, total: { status: "unavailable" } });
    expect(html).toContain("배당 포함 전체 수익을 계산하지 않았습니다");
    expect(html).toContain("주식 수가 바뀐 사건을 확인하지 못해");
    expect(html).not.toContain("적자 구간");
  });
  it("uses positive source ratios when rounded stock and index returns are minus 100 percent", () => {
    const html = render({ ...period, endClose: "0.004", priceReturn: "-1.0000",
      earnings: { ...period.earnings!, endPE: "0.0003333333333333333333333333333" },
      dividend: { status: "available", amount: "0", contribution: "0.0000" }, total: { status: "available", value: "-1.0000" },
      display: { price: "-100.0", growth: "20.0", rerating: "-120.0", dividend: "0.0", total: "-100.0" },
      benchmark: { ...period.benchmark!, endClose: "0.004", display: { stock: "-100.0", index: "-100.0", difference: "0.0" } } });
    expect(html).not.toMatch(/NaN|Infinity/);
    expect(html).toContain("×0.00004");
    expect(html).not.toContain("width:0.00%");
  });
  it("does not let an invalid index ratio collapse valid stock and earnings bars", () => {
    const html = render({ ...period, benchmark: { ...period.benchmark!, startClose: "0" } });
    expect(html).not.toMatch(/NaN|Infinity/);
    expect(html).toContain("주가 ×1.50");
  });
});

describe("historical return conclusion (facts only, no cause)", () => {
  it("names which factor was larger without claiming why", () => {
    expect(attributionConclusion(28.8, 0.32, true)).toBe("주당이익은 늘었지만 PER이 낮아져, 이익이 늘어난 만큼 오르지는 못했습니다.");
    expect(attributionConclusion(3.69, 0.97, true)).toBe("거의 주당이익이 늘어난 만큼 움직였고, PER은 거의 그대로였습니다.");
    expect(attributionConclusion(1.74, 3.6, true)).toBe("주당이익 증가와 PER 상승이 함께 끌어올렸고, PER 쪽 몫이 더 컸습니다.");
    expect(attributionConclusion(1.05, 1.4, true)).toBe("주당이익은 거의 그대로였고, 대부분 PER이 오른 몫입니다.");
    expect(attributionConclusion(0.7, 0.8, false)).toBe("주당이익 감소와 PER 하락이 함께 끌어내렸고, 주당이익 쪽 몫이 더 컸습니다.");
    expect(attributionConclusion(0.8, 1.6, true)).toBe("주당이익은 줄었지만 PER이 올라, 이익이 줄어든 만큼 내리지는 않았습니다.");
    expect(attributionConclusion(1.02, 0.95, false)).toBe("주당이익과 PER 모두 크게 변하지 않았습니다.");
  });
  it("never uses causal or verdict words", () => {
    for (const [e, p] of [[28.8, 0.32], [3.69, 0.97], [1.74, 3.6], [0.7, 0.8], [0.8, 1.6]]) {
      expect(attributionConclusion(e, p, e * p >= 1)).not.toMatch(/때문|덕분|매수|매도|고평가|저평가|좋은|나쁜/);
    }
  });
});
