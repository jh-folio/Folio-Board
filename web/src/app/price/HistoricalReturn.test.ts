import { describe, expect, it } from "vitest";
import { attributionConclusion } from "./HistoricalReturn";

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
