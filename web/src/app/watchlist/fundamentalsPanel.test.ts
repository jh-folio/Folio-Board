import { describe, expect, it } from "vitest";
import { balanceRatio, CHART_SETS, chartScale, fractionPercentText, fundamentalsRows, percentValueText, quarterAxisLabel, rangeText, ratioText, totalLiabilities } from "./FundamentalsPanel";

describe("지표 포맷", () => {
  it("결측은 —다 — provider가 실제로 비워 두는 칸이 있다(삼성전자의 PER)", () => {
    expect(ratioText(null)).toBe("—");
    expect(fractionPercentText(undefined)).toBe("—");
    expect(percentValueText(null)).toBe("—");
    expect(rangeText(null, 100)).toBe("—");
  });

  it("fraction 칸(ROE·마진)만 100을 곱한다", () => {
    expect(fractionPercentText(0.30794)).toBe("30.8%");
  });

  it("배당수익률은 이미 % 단위다 — 100을 곱하면 도요타가 326%가 된다", () => {
    expect(percentValueText(3.26)).toBe("3.26%");
  });

  it("52주 범위는 큰 값이면 소수점을 접는다", () => {
    expect(rangeText(49802, 89000)).toBe("49,802 ~ 89,000");
    expect(rangeText(96.5, 187.11)).toBe("96.5 ~ 187.11");
  });

  it("타일 표가 통화를 알고 시총을 줄여 쓴다", () => {
    const rows = fundamentalsRows({ marketCap: 2.5e12, currency: "KRW", trailingPE: null });
    expect(rows.find((row) => row.label === "시가총액")?.value).toBe("2.5조");
    expect(rows.find((row) => row.label === "PER")?.value).toBe("—");
    expect(rows).toHaveLength(11);
  });
});

describe("분기 이익 차트", () => {
  it("축 라벨은 분기 종료월이다", () => {
    expect(quarterAxisLabel("2026-06-30")).toBe("26년 6월");
    expect(quarterAxisLabel(undefined)).toBe("");
  });

  it("막대 스케일은 0을 포함한다 — 적자를 0으로 접으면 이익 없음으로 읽힌다", () => {
    const { max, min } = chartScale([100, -12, 5, 120, 40, 112], "bars");
    expect(max).toBe(120);
    expect(min).toBe(-12);
  });

  it("선(비율) 스케일은 0을 강제하지 않는다 — 29~35% 구간을 0부터 그리면 변화가 눌린다", () => {
    const { max, min } = chartScale([29, 35], "lines");
    expect(min).toBeGreaterThan(0);
    expect(max).toBeGreaterThan(35);
  });

  it("네 세트가 자기 색을 갖는다 — 색이 지금 어느 탭인지 말한다", () => {
    expect(CHART_SETS.map((set) => set.key)).toEqual(["earnings", "balance", "stability", "cashflow"]);
    const identity = CHART_SETS.map((set) => set.colors[1]);
    expect(new Set(identity).size).toBe(identity.length);
    // 안정성 탭은 선 차트고 %로 말한다.
    const stability = CHART_SETS.find((set) => set.key === "stability");
    expect(stability?.mode).toBe("lines");
    expect(stability?.format).toBe("percent");
  });

  it("비율은 분모가 0이거나 비면 계산하지 않는다", () => {
    expect(balanceRatio(200, 90)).toBeCloseTo(222.2, 1);
    expect(balanceRatio(200, 0)).toBeNull();
    expect(balanceRatio(null, 90)).toBeNull();
  });

  it("부채비율은 부채총계(유동+비유동) ÷ 자본총계다", () => {
    // 이자부채(Total Debt)로 계산했더니 그 행이 최근 분기에만 있는 회사에서
    // 선이 점 하나로 무너졌다. 부채총계의 재료는 전 분기에 있다.
    expect(totalLiabilities({ currentLiabilities: 90, nonCurrentLiabilities: 60 })).toBe(150);
    // 한쪽이 비면 합계도 없다 — 반쪽 합은 부채비율을 실제보다 낮아 보이게 한다.
    expect(totalLiabilities({ currentLiabilities: 90 })).toBeNull();
    const debtRatio = CHART_SETS.find((set) => set.key === "stability")?.series[1];
    expect(debtRatio?.of({ currentLiabilities: 90, nonCurrentLiabilities: 60, stockholdersEquity: 300 })).toBeCloseTo(50, 5);
  });
});
