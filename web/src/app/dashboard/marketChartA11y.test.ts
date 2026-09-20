import { describe, expect, it } from "vitest";

import { MAX_TABLE_ROWS, sampleRows, tableSummaryLabel } from "../charts/chartA11y";
import { barReadout, barTimeText, chartSummaryLabel, isCandleView, nextBarIndex, type A11yBar } from "./marketChartA11y";

const daily: A11yBar[] = [
  { time: "2026-09-16", open: 100, high: 110, low: 95, close: 105 },
  { time: "2026-09-17", open: 105, high: 120, low: 104, close: 118 },
  { time: "2026-09-18", open: 118, high: 119, low: 90, close: 92 },
];

describe("차트 이름", () => {
  it("무엇을 언제부터 언제까지 어떻게 움직였는지 말한다", () => {
    const label = chartSummaryLabel({ name: "삼성전자", rangeLabel: "1M", style: "candle", rows: daily, intraday: false });
    expect(label).toContain("삼성전자 1M 캔들 가격 차트.");
    expect(label).toContain("2026-09-16부터 2026-09-18까지 3개 봉.");
    expect(label).toContain("처음 종가 105, 마지막 종가 92 (-12.4%)");
    // 최고·최저는 종가가 아니라 봉의 고가·저가다.
    expect(label).toContain("최고 120, 최저 90.");
    expect(label).toContain("좌우 방향키");
  });

  it("OHLC가 없으면 캔들이라 부르지 않는다", () => {
    const line = daily.map(({ time, close }) => ({ time, close }));
    expect(isCandleView("candle", line)).toBe(false);
    expect(chartSummaryLabel({ name: "X", rangeLabel: "3M", style: "candle", rows: line, intraday: false })).toContain("라인 가격 차트");
    expect(isCandleView("line", daily)).toBe(false);
    expect(isCandleView("candle", daily)).toBe(true);
  });

  it("자료가 없으면 없다고 말한다", () => {
    expect(chartSummaryLabel({ name: "삼성전자", rangeLabel: "1M", style: "line", rows: [], intraday: false })).toBe("삼성전자 가격 차트. 표시할 자료가 없습니다.");
  });

  it("처음 종가가 0이면 등락률을 지어내지 않는다", () => {
    const label = chartSummaryLabel({ name: "X", rangeLabel: "1Y", style: "line", rows: [{ time: "2026-01-02", close: 0 }, { time: "2026-01-03", close: 5 }], intraday: false });
    expect(label).not.toContain("%");
  });
});

describe("봉 판독값", () => {
  it("캔들은 시가·고가·저가·종가와 전일 대비를 읽는다", () => {
    const text = barReadout({ rows: daily, index: 1, intraday: false, candle: true });
    expect(text).toBe("2026-09-17. 시가 105, 고가 120, 저가 104, 종가 118. 전일 대비 +13.00 (+12.38%). 2번째 봉, 전체 3개.");
  });

  it("라인은 종가만 읽고 하락은 마이너스로 읽는다", () => {
    const text = barReadout({ rows: daily, index: 2, intraday: false, candle: false });
    expect(text).toBe("2026-09-18. 종가 92. 전일 대비 -26.00 (-22.03%). 3번째 봉, 전체 3개.");
  });

  it("첫 봉은 비교 대상이 없다고 말한다", () => {
    expect(barReadout({ rows: daily, index: 0, intraday: false, candle: false })).toContain("전일 대비 없음");
  });

  it("분봉은 시각을 읽고 직전 봉과 비교한다", () => {
    const rows: A11yBar[] = [
      { time: "2026-08-07T09:30:00-04:00", close: 200 },
      { time: "2026-08-07T09:35:00-04:00", close: 201 },
    ];
    expect(barTimeText(rows[1].time, true)).toBe("2026-08-07 09:35");
    expect(barReadout({ rows, index: 1, intraday: true, candle: false })).toContain("직전 봉 대비 +1.00 (+0.50%)");
  });

  it("범위를 벗어난 지점은 빈 문자열이다", () => {
    expect(barReadout({ rows: daily, index: 9, intraday: false, candle: false })).toBe("");
  });
});

describe("방향키 이동", () => {
  it("처음 누르면 가장 최근 봉에서 시작한다", () => {
    expect(nextBarIndex({ key: "ArrowLeft", current: null, length: 50 })).toBe(49);
    expect(nextBarIndex({ key: "ArrowRight", current: null, length: 50 })).toBe(49);
  });

  it("한 칸·열 칸·처음·끝으로 옮기고 끝을 넘지 않는다", () => {
    expect(nextBarIndex({ key: "ArrowLeft", current: 10, length: 50 })).toBe(9);
    expect(nextBarIndex({ key: "ArrowRight", current: 49, length: 50 })).toBe(49);
    expect(nextBarIndex({ key: "ArrowLeft", current: 0, length: 50 })).toBe(0);
    expect(nextBarIndex({ key: "PageUp", current: 5, length: 50 })).toBe(0);
    expect(nextBarIndex({ key: "PageDown", current: 45, length: 50 })).toBe(49);
    expect(nextBarIndex({ key: "Home", current: 20, length: 50 })).toBe(0);
    expect(nextBarIndex({ key: "End", current: 20, length: 50 })).toBe(49);
  });

  it("관계없는 키와 빈 자료는 무시한다", () => {
    expect(nextBarIndex({ key: "a", current: 3, length: 50 })).toBeNull();
    expect(nextBarIndex({ key: "ArrowLeft", current: null, length: 0 })).toBeNull();
  });
});

describe("표 표본", () => {
  it("짧으면 전부, 길면 첫·끝을 남기고 균등하게 뽑는다", () => {
    expect(sampleRows([1, 2, 3])).toEqual([1, 2, 3]);
    const long = Array.from({ length: 300 }, (_, index) => index);
    const sampled = sampleRows(long);
    expect(sampled).toHaveLength(MAX_TABLE_ROWS);
    expect(sampled[0]).toBe(0);
    expect(sampled[sampled.length - 1]).toBe(299);
  });

  it("표본이면 몇 개를 보여 주는지 밝힌다", () => {
    expect(tableSummaryLabel(30, "봉")).toBe("30개 봉");
    expect(tableSummaryLabel(300, "봉")).toBe(`${MAX_TABLE_ROWS}개 대표 봉`);
  });
});
