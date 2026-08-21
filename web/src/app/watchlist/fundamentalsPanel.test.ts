import { describe, expect, it } from "vitest";
import { fractionPercentText, fundamentalsRows, percentValueText, rangeText, ratioText } from "./FundamentalsPanel";

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
