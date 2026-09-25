import { describe, expect, it } from "vitest";

import { chartMoney, compactAmount, currencySymbol, quarterAxisLabel } from "./chartFormat";

describe("compactAmount — 통화 기호 없는 본문용", () => {
  it("매출은 통화에 맞는 단위로 접는다", () => {
    // 삼성전자 분기 매출은 자릿수만으로는 읽히지 않는다.
    expect(compactAmount(79_100_000_000_000, "KRW")).toBe("79.1조");
    expect(compactAmount(560_000_000, "KRW")).toBe("5.6억");
    expect(compactAmount(5_600_000_000, "USD")).toBe("5.6B");
    expect(compactAmount(8_130_000, "USD")).toBe("8.13M");
    expect(compactAmount(null)).toBe("—");
  });

  it("엔도 조·억으로 읽는다", () => {
    expect(compactAmount(45_000_000_000_000, "JPY")).toBe("45조");
    expect(compactAmount(320_000_000_000, "JPY")).toBe("3,200억");
  });

  it("달러 1조 이상은 T로 접는다 — 시가총액이 3,500B로 읽히지 않는다", () => {
    expect(compactAmount(3_500_000_000_000, "USD")).toBe("3.5T");
  });

  it("가장 작은 단위 미만은 그대로 자릿수를 맞춘다", () => {
    expect(compactAmount(5_000_000, "KRW")).toBe("5,000,000");
    expect(compactAmount(950_000, "USD")).toBe("950,000");
  });
});

describe("chartMoney — 통화 기호를 붙인 차트 판독값", () => {
  it("같은 한국 회사가 워치리스트와 같은 단위로 읽힌다", () => {
    // 기업분석 차트는 `₩79.1T`였고 워치리스트는 `79.1조`였다.
    expect(chartMoney(79_100_000_000_000, "KRW")).toBe("₩79.1조");
    expect(chartMoney(560_000_000, "KRW")).toBe("₩5.6억");
    expect(chartMoney(79_100_000_000_000, "KRX")).toBe("₩79.1조");
  });

  it("그 외 통화는 T·B·M이고 소수 한 자리로 고정한다", () => {
    expect(chartMoney(1_500_000_000, "USD")).toBe("$1.5B");
    expect(chartMoney(2_000_000_000, "USD")).toBe("$2.0B");
    expect(chartMoney(3_200_000_000_000, "EUR")).toBe("€3.2T");
    expect(chartMoney(410_000_000, "GBP")).toBe("£410.0M");
  });

  it("통화를 모르면 달러로 읽는다", () => {
    expect(chartMoney(1_500_000_000)).toBe("$1.5B");
  });

  it("음수는 부호가 기호 앞에 온다 — 잉여현금흐름 적자가 `$-1.5B`로 읽히지 않는다", () => {
    expect(chartMoney(-1_500_000_000, "USD")).toBe("-$1.5B");
    expect(chartMoney(-3_000_000_000_000, "KRW")).toBe("-₩3.0조");
    expect(chartMoney(-0.3, "USD")).toBe("-$0.3");
  });

  it("단위 미만은 접지 않고 값이 없으면 대시다", () => {
    expect(chartMoney(0, "USD")).toBe("$0");
    expect(chartMoney(950, "USD")).toBe("$950");
    expect(chartMoney(null, "USD")).toBe("-");
    expect(chartMoney(Number.NaN, "USD")).toBe("-");
  });
});

describe("currencySymbol", () => {
  it("알려진 통화만 자기 기호를 갖는다", () => {
    expect(currencySymbol("KRW")).toBe("₩");
    expect(currencySymbol("krx")).toBe("₩");
    expect(currencySymbol("JPY")).toBe("¥");
    expect(currencySymbol("EUR")).toBe("€");
    expect(currencySymbol("GBP")).toBe("£");
    expect(currencySymbol("CHF")).toBe("$");
    expect(currencySymbol(undefined)).toBe("$");
  });
});

describe("quarterAxisLabel", () => {
  it("축 라벨은 분기 종료월이다", () => {
    expect(quarterAxisLabel("2026-06-30")).toBe("26년 6월");
    expect(quarterAxisLabel(undefined)).toBe("");
  });
});
