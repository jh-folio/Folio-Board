import { describe, expect, it } from "vitest";
import { comparisonLabel } from "./StoryShare";

describe("comparisonLabel", () => {
  it("창이 여러 거래일이면 기간과 표본을 말한다", () => {
    // "직전 거래일 대비"는 창이 하루일 때만 맞는 말이다.
    expect(comparisonLabel({ previousSessionCount: 5, previousCollectedCount: 1458 }))
      .toBe("직전 5거래일 합산 1458건 대비");
  });

  it("창이 하루면 예전 문구 그대로다", () => {
    expect(comparisonLabel({ previousSessionCount: 1, previousCollectedCount: 12 }))
      .toBe("직전 거래일 대비");
  });

  it("표본 수를 모르면 기간만 말한다", () => {
    expect(comparisonLabel({ previousSessionCount: 5 })).toBe("직전 5거래일 합산 대비");
  });

  it("비교할 창이 없으면 없다고 말한다", () => {
    // 있지도 않은 비교를 했다고 말하지 않는다.
    expect(comparisonLabel({})).toBe("비교 기준 없음");
  });
});
