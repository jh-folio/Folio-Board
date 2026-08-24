import { describe, expect, it } from "vitest";
import { bestIndex, seriesPath } from "./PresetCompare";
import type { BacktestResult } from "./portfolioTypes";

function result(metrics: Record<string, number | null>): BacktestResult {
  return {
    id: "x", start: "2020-01-01", end: "2026-01-01", baseCurrency: "USD",
    initialValue: 100, rebalance: "monthly",
    metrics: metrics as unknown as BacktestResult["metrics"],
    series: [],
  };
}

describe("bestIndex", () => {
  it("높을수록 좋은 지표는 최대값을 고른다", () => {
    const rows = [result({ totalReturn: 0.2 }), result({ totalReturn: 0.5 })];

    expect(bestIndex(rows, "totalReturn", "high")).toBe(1);
  });

  it("낮을수록 좋은 지표는 최소값을 고른다", () => {
    // 변동성은 양수라 작을수록 낫다.
    const rows = [result({ volatility: 0.3 }), result({ volatility: 0.1 })];

    expect(bestIndex(rows, "volatility", "low")).toBe(1);
  });

  it("최대 낙폭은 0에 가까울수록 낫다", () => {
    // 실측 값은 음수다(-0.1346 / -0.1338). "작을수록 좋다"로 두면 **더 깊은** 낙폭을
    // 최선으로 강조하게 된다.
    const rows = [result({ maxDrawdown: -0.4 }), result({ maxDrawdown: -0.1 })];

    expect(bestIndex(rows, "maxDrawdown", "nearZero")).toBe(1);
  });

  it("낙폭이 양수 크기로 와도 같은 답을 준다", () => {
    // provider가 부호 규약을 바꿔도 판단이 뒤집히면 안 된다.
    const rows = [result({ maxDrawdown: 0.4 }), result({ maxDrawdown: 0.1 })];

    expect(bestIndex(rows, "maxDrawdown", "nearZero")).toBe(1);
  });

  it("실측 두 초안에서 낙폭이 얕은 쪽을 고른다", () => {
    // 2023년 실측: 성장 -0.1345596, 방어 -0.1338247.
    const rows = [result({ maxDrawdown: -0.1345596 }), result({ maxDrawdown: -0.1338247 })];

    expect(bestIndex(rows, "maxDrawdown", "nearZero")).toBe(1);
  });

  it("동점이면 아무도 강조하지 않는다", () => {
    // 비교가 성립하지 않는데 우열을 표시하면 없는 판단을 만든다.
    const rows = [result({ sharpe: 1.1 }), result({ sharpe: 1.1 })];

    expect(bestIndex(rows, "sharpe", "high")).toBeNull();
  });

  it("비교 대상이 하나뿐이면 강조하지 않는다", () => {
    const rows = [result({ sharpe: 1.1 }), result({ sharpe: null })];

    expect(bestIndex(rows, "sharpe", "high")).toBeNull();
  });

  it("없는 지표는 우열을 만들지 않는다", () => {
    const rows = [result({}), result({})];

    expect(bestIndex(rows, "sharpe", "high")).toBeNull();
  });
});

describe("seriesPath", () => {
  const bounds = {
    minTime: new Date("2023-01-01").getTime(),
    maxTime: new Date("2023-12-31").getTime(),
    min: 100,
    max: 200,
  };

  it("x는 날짜에서 나온다 — 인덱스가 아니다", () => {
    // 3월에 시작한 계열이 1월에 시작한 계열과 같은 자리에서 출발하면, 같은 가로 위치가
    // 같은 날짜라고 읽히는 전제가 깨진다.
    const early = seriesPath([{ date: "2023-01-01", value: 100 }, { date: "2023-12-31", value: 200 }], bounds, 640, 180);
    const late = seriesPath([{ date: "2023-07-01", value: 100 }, { date: "2023-12-31", value: 200 }], bounds, 640, 180);

    expect(early.startsWith("M0.0,")).toBe(true);
    expect(late.startsWith("M0.0,")).toBe(false);
  });

  it("길이가 달라도 같은 날짜는 같은 x에 온다", () => {
    const dense = seriesPath(
      [{ date: "2023-01-01", value: 100 }, { date: "2023-07-01", value: 150 }, { date: "2023-12-31", value: 200 }],
      bounds, 640, 180,
    );
    const sparse = seriesPath(
      [{ date: "2023-01-01", value: 100 }, { date: "2023-12-31", value: 200 }],
      bounds, 640, 180,
    );

    // 두 계열 모두 마지막 점이 오른쪽 끝이다. 인덱스 기반이면 dense의 중간 점이
    // sparse의 마지막 점과 같은 자리에 왔다.
    expect(dense.endsWith("640.0,0.0")).toBe(true);
    expect(sparse.endsWith("640.0,0.0")).toBe(true);
  });

  it("읽을 수 없는 날짜는 창의 시작으로 떨어뜨린다", () => {
    // NaN이 좌표에 들어가면 경로 전체가 그려지지 않는다.
    const path = seriesPath([{ date: "bogus", value: 150 }, { date: "2023-12-31", value: 200 }], bounds, 640, 180);

    expect(path).not.toContain("NaN");
  });
});
