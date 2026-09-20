import { describe, expect, it } from "vitest";
import { basisValues, changeRatio, epsBaseText, formatEps, panelProviderCopy, percentText } from "./EarningsPanel";

describe("실적 숫자 표시", () => {
  it("원·엔 EPS는 소수점을 붙이지 않는다", () => {
    expect(formatEps(10_849, "KRW")).toBe("10,849");
    expect(formatEps(1.33, "USD")).toBe("1.33");
    expect(formatEps(undefined)).toBe("—");
  });
});

describe("기준 대비 증감", () => {
  it("기준이 없거나 0이면 계산하지 않는다", () => {
    expect(changeRatio(1.33, null)).toBeNull();
    expect(changeRatio(1.33, 0)).toBeNull();
    expect(changeRatio(null, 1.2)).toBeNull();
  });

  it("기준이 적자여도 부호가 뒤집히지 않는다", () => {
    // 적자 -1.0에서 -0.5가 되면 개선이다. 부호 있는 값으로 나누면 하락으로 읽힌다.
    expect(changeRatio(-0.5, -1)).toBeCloseTo(0.5);
    expect(percentText(changeRatio(-0.5, -1))).toBe("+50.0%");
  });

  it("퍼센트는 부호를 항상 적는다", () => {
    // 색만으로 방향을 알리지 않는다(WCAG 1.4.1).
    expect(percentText(0.081)).toBe("+8.1%");
    expect(percentText(-0.081)).toBe("-8.1%");
    expect(percentText(null)).toBe("—");
  });
});

describe("비교 기준", () => {
  const row = {
    quarter: "2026-06-30",
    epsActual: 1.33, epsEstimate: 1.21,
    revenueActual: 5.6e9, revenuePriorQuarter: 5.2e9, revenuePriorYear: 3.9e9,
    epsPriorQuarter: 1.25, epsPriorYear: 0.81,
  };

  it("예측치 기준에는 매출 비교값이 없다", () => {
    // provider는 **다음** 분기 매출 컨센서스만 준다. 화면이 그 사실을 적는다.
    expect(basisValues(row, "estimate")).toEqual({ eps: 1.21, revenue: undefined, epsTop: 1.33, fromStatement: false });
  });

  it("지난 분기·작년 동기간은 EPS와 매출을 함께 준다", () => {
    expect(basisValues(row, "priorQuarter")).toEqual({ eps: 1.25, revenue: 5.2e9, epsTop: 1.33, fromStatement: false });
    expect(basisValues(row, "priorYear")).toEqual({ eps: 0.81, revenue: 3.9e9, epsTop: 1.33, fromStatement: false });
  });

  it("작년 EPS를 손익계산서에서 채웠으면 분자도 같은 계열로 바꾼다", () => {
    // 조정 EPS(보고)를 GAAP 기본 EPS로 나누면 조정 폭이 증감률로 둔갑한다.
    const filled = { ...row, epsPriorYear: 1.35, epsPriorYearBasis: "statement", epsActualStatement: 1.31 };
    const values = basisValues(filled, "priorYear");
    expect(values).toEqual({ eps: 1.35, revenue: 3.9e9, epsTop: 1.31, fromStatement: true });
    expect(percentText(changeRatio(values.epsTop, values.eps))).toBe("-3.0%");
  });
});

describe("EPS 비교 기준 줄", () => {
  const row = { quarter: "2026-06-30", epsActual: 1.82, epsPriorYear: 1.35, revenuePriorYear: 5.17e9 };

  it("보고 EPS끼리 비교하면 기준만 적는다", () => {
    expect(epsBaseText({ ...row, epsPriorQuarter: 1.47 }, "priorQuarter", "USD")).toBe("지난 분기 1.47");
  });

  it("분자와 분모가 같으면 계열만 밝힌다", () => {
    const filled = { ...row, epsPriorYearBasis: "statement", epsActualStatement: 1.82 };
    expect(epsBaseText(filled, "priorYear", "USD")).toBe("작년 동기간 1.35 · 손익계산서 기본 EPS 기준");
  });

  it("분자가 다르면 무엇으로 나눴는지 적는다", () => {
    // 조정 EPS 2.00을 보여주면서 1.50/1.35로 나누면 읽는 사람이 직접 나눠 봤을 때 안 맞는다.
    const filled = { ...row, epsActual: 2.0, epsPriorYearBasis: "statement", epsActualStatement: 1.5 };
    expect(epsBaseText(filled, "priorYear", "USD")).toBe("작년 동기간 1.35 · 손익계산서 기본 EPS 1.50 대비");
  });
});

describe("earnings provider copy", () => {
  it("uses the same bounded provider formatter for absent and unknown successful payloads", () => {
    expect(panelProviderCopy("yfinance")).toBe("yfinance");
    expect(panelProviderCopy("toss_open_api")).toBe("Toss Open API");
    expect(panelProviderCopy()).toBe("시장 데이터 제공자");
    expect(panelProviderCopy("internal-debug-code")).toBe("시장 데이터 제공자");
  });
});
