import { describe, expect, it } from "vitest";
import { checkMetricCondition, parseMetricCondition } from "./conditionMetrics";

const quarters = [
  { quarter: "2026-01-31", revenue: 100, operatingIncome: 62, netIncome: 50 },
  { quarter: "2025-10-31", revenue: 100, operatingIncome: 60, netIncome: 48 },
  { quarter: "2026-04-30", revenue: 100, operatingIncome: 64.1, netIncome: 52 },
  { quarter: "2026-07-31", revenue: 100, operatingIncome: 66.2, netIncome: 49 },
];

describe("판단 조건 문장 읽기", () => {
  it("AI 다듬기가 제안하는 꼴을 읽는다", () => {
    expect(parseMetricCondition("분기 영업이익률이 두 분기 연속 낮아질 때")).toEqual({ metric: "operatingMargin", label: "영업이익률", direction: "down", streak: 2 });
    expect(parseMetricCondition("분기 매출이 3분기 연속 늘어날 때")).toEqual({ metric: "revenue", label: "매출", direction: "up", streak: 3 });
  });

  it("긴 지표 이름을 먼저 본다 — 이익률을 이익 금액으로 읽지 않는다", () => {
    expect(parseMetricCondition("순이익률이 떨어지면")?.metric).toBe("netMargin");
    expect(parseMetricCondition("순이익이 줄어들면")?.metric).toBe("netIncome");
  });

  it("방향은 지표 이름 뒤에서 찾는다", () => {
    expect(parseMetricCondition("매출은 늘지만 영업이익률이 낮아질 때")?.direction).toBe("down");
  });

  it("지표나 방향이 없으면 읽지 않는다(추측 금지)", () => {
    expect(parseMetricCondition("주요 고객이 자체 칩으로 빠르게 이동할 때")).toBeNull();
    expect(parseMetricCondition("영업이익률을 지켜본다")).toBeNull();
    expect(parseMetricCondition("매출이 20% 이상 감소할 때")).toBeNull();
    expect(parseMetricCondition("매출이 전년 동기보다 감소할 때")).toBeNull();
    expect(parseMetricCondition("매출이 4분기 연속 감소할 때")).toBeNull();
  });
});

describe("분기 숫자 대조", () => {
  it("과거 → 최신 순으로 정렬하고 조건 해당 여부만 말한다", () => {
    const check = checkMetricCondition("분기 영업이익률이 두 분기 연속 낮아질 때", quarters);
    expect(check?.points.map((row) => row.label)).toEqual(["26년 1월", "26년 4월", "26년 7월"]);
    expect(check?.points.map((row) => Math.round(row.value * 10) / 10)).toEqual([62, 64.1, 66.2]);
    expect(check?.met).toBe(false);
    expect(check?.unit).toBe("percent");
  });

  it("연속 조건을 모두 만족할 때만 해당으로 본다", () => {
    const falling = [
      { quarter: "2026-01-31", revenue: 100, netIncome: 52 },
      { quarter: "2026-04-30", revenue: 100, netIncome: 50 },
      { quarter: "2026-07-31", revenue: 100, netIncome: 49 },
    ];
    expect(checkMetricCondition("순이익이 두 분기 연속 줄어들 때", falling)?.met).toBe(true);
    expect(checkMetricCondition("순이익이 세 분기 연속 줄어들 때", falling)?.met).toBeNull();
  });

  it("분기 자료가 없으면 아무것도 보여 주지 않는다", () => {
    expect(checkMetricCondition("매출이 줄어들 때", [])).toBeNull();
    expect(checkMetricCondition("매출이 줄어들 때", undefined)).toBeNull();
  });

  it("중간 분기나 최근 분기 값이 없으면 연속 조건을 단정하지 않는다", () => {
    const missing = [
      { quarter: "2026-01-31", revenue: 110 },
      { quarter: "2026-04-30", revenue: 100 },
      { quarter: "2026-07-31", revenue: null },
      { quarter: "2026-10-31", revenue: 90 },
    ];
    expect(checkMetricCondition("매출이 두 분기 연속 줄어들 때", missing)?.met).toBeNull();
    expect(checkMetricCondition("매출이 두 분기 연속 줄어들 때", missing.slice(0, -1))).toBeNull();
    const missingPeriod = [missing[0], missing[1], missing[3]];
    expect(checkMetricCondition("매출이 두 분기 연속 줄어들 때", missingPeriod)?.met).toBeNull();
  });
});
