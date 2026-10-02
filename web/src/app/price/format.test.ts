import { describe, expect, it } from "vitest";
import {
  attemptBanner, bannerFor, decompositionCards, fractionToPercent, heroText, irrText, money, multiple, pct, pctPlain, pctSigned,
  percentToFraction, rangePosition, reasonText, scaleLayout, shiftDecimal,
} from "./format";
import type { Projection, ScenarioRow } from "./types";

describe("decimal text", () => {
  it("shifts the point without float error", () => {
    expect(percentToFraction("12")).toBe("0.12");
    expect(percentToFraction("12.5")).toBe("0.125");
    expect(percentToFraction("0")).toBe("0");
    expect(percentToFraction("100")).toBe("1");
    expect(percentToFraction("-5.5")).toBe("-0.055");
    expect(percentToFraction("0.07")).toBe("0.0007");
    expect(fractionToPercent("0.12")).toBe("12");
    expect(fractionToPercent("0.0007")).toBe("0.07");
    expect(fractionToPercent("0")).toBe("0");
    expect(fractionToPercent(null)).toBe("");
    expect(shiftDecimal("abc", 2)).toBe("abc");
    expect(percentToFraction("0.1")).toBe("0.001");
    expect(percentToFraction("1e2")).toBe("1e2"); // not a plain decimal: the server rejects it
  });
});

describe("number words", () => {
  it("formats stored fractions and keeps the true minus sign", () => {
    expect(pct("0.0661")).toBe("6.6%");
    expect(pct("-0.0235")).toBe("−2.4%");
    expect(pct("-0.00001")).toBe("0.0%");
    expect(pctSigned("0.05")).toBe("+5.0%");
    expect(pctSigned("-0.012")).toBe("−1.2%");
    expect(pctPlain("6")).toBe("6%");
    expect(pctPlain(null)).toBe("—");
    expect(multiple("18.04")).toBe("18.0배");
    expect(money("250.123", "USD")).toBe("$250.12");
    expect(money("276000", "KRW")).toBe("276,000원");
    expect(reasonText("history_too_short")).toContain("과거 자료가 부족");
    expect(reasonText("zzz")).toContain("zzz");
  });
  it("names out-of-range returns instead of printing a number", () => {
    const row = { label: "base", horizon: 10, status: "available", irr: null, irrRange: "above_range" } as unknown as ScenarioRow;
    expect(irrText(row)).toBe("100% 초과");
    expect(irrText({ ...row, irrRange: "below_range" } as ScenarioRow)).toBe("−99% 미만");
    expect(irrText({ label: "base", horizon: 5, status: "unavailable", reason: { code: "x" } })).toBe("계산 불가");
    expect(irrText(undefined)).toBe("계산 불가");
  });
});

describe("headline (A form)", () => {
  const base = { horizon: 10 as const, baseIrr: 0.066, holdingYears: 10, baseHoldingIrr: 0.066 };
  it("compares only when the horizon is the chosen holding period", () => {
    expect(heroText({ ...base, required: "6" }).title).toBe("10년간 연 6.6%로, 내 기준 연 6%보다 높습니다.");
    expect(heroText({ ...base, required: "7" }).title).toBe("10년간 연 6.6%로, 내 기준 연 7%보다 낮습니다.");
    expect(heroText({ ...base, required: "6.5" }).title).toContain("연 6.5%");
    const other = heroText({ ...base, horizon: 5, baseIrr: 0.03, required: "6" });
    expect(other.title).toBe("5년간 연 3.0%입니다.");
    expect(other.sub).toContain("기본 보유 10년(연 6.6%)");
  });
  it("never invents a comparison without a criterion or a number", () => {
    expect(heroText({ ...base, required: null, holdingYears: null }).title).toBe("10년간 연 6.6%입니다.");
    expect(heroText({ ...base, required: null, holdingYears: null }).sub).toContain("내 기준을 정하면 비교");
    expect(heroText({ ...base, baseIrr: null, required: "6" }).title).toContain("계산하지 못했습니다");
  });
});

describe("range geometry", () => {
  it("places three scenarios and the criterion on one scale inside 0..100%", () => {
    const layout = scaleLayout([{ key: "a", label: "보수", value: 2 }, { key: "b", label: "기본", value: 6.6 }, { key: "c", label: "낙관", value: 11 }], 6);
    expect(layout.points.map(p => p.left).every(v => v > 0 && v < 100)).toBe(true);
    expect(layout.points[0].left).toBeLessThan(layout.points[1].left);
    expect(layout.points[1].left).toBeLessThan(layout.points[2].left);
    expect(layout.goalLeft).toBeGreaterThan(layout.points[0].left);
    expect(layout.ticks.length).toBeGreaterThan(2);
    expect(scaleLayout([{ key: "a", label: "a", value: 5 }, { key: "b", label: "b", value: 5 }, { key: "c", label: "c", value: 5 }], null).goalLeft).toBeNull();
  });
  it("says where a required value sits against the past range", () => {
    expect(rangePosition(8, 3, 15).where).toBe(" 안에 있습니다");
    expect(rangePosition(2, 3, 15).where).toBe("보다 낮습니다");
    expect(rangePosition(30, 3, 15).where).toBe("보다 높습니다");
    const inside = rangePosition(8, 3, 15);
    expect(inside.minLeft).toBeLessThan(inside.valueLeft);
    expect(inside.valueLeft).toBeLessThan(inside.maxLeft);
  });
  it("splits growth into three yearly parts that keep their sign", () => {
    const cards = decompositionCards({ R: "0.05", M: "0.01", S: "-0.007" });
    expect(cards.map(c => c.key)).toEqual(["R", "M", "S"]);
    expect(cards[0].value).toBeGreaterThan(0.05);
    expect(cards[2].value).toBeLessThan(0);
  });
});

describe("one banner at a time", () => {
  const projection = (extra: Partial<Projection> = {}) => ({ snapshotId: "p", asOf: "2026-10-01", ageDays: 1, notices: [], criteria: null, verdict: {} as never, requirement: { status: "unavailable" }, myAssumptions: null, reviewNeeded: [], ...extra }) as Projection;
  it("prefers save failure, then correction, then age", () => {
    expect(bannerFor({ projection: null, view: null, saveFailed: true })?.title).toContain("저장되지 않았습니다");
    const corrected = projection({ reviewNeeded: [{ reason: "restated", metric: "EPS Diluted", fiscalYear: 2024, detectedBySnapshotId: "n" }], notices: ["snapshot_old"] });
    expect(bannerFor({ projection: corrected, view: null, saveFailed: false })?.title).toContain("정정됐습니다");
    expect(bannerFor({ projection: projection({ notices: ["snapshot_old"] }), view: null, saveFailed: false })?.title).toContain("오래됐습니다");
    expect(bannerFor({ projection: projection(), view: null, saveFailed: false })).toBeNull();
  });
  it("explains a failed attempt in plain words and points to earlier results", () => {
    expect(attemptBanner({ status: "failed", reason: { code: "price_stale" } }, "2026-09-01")?.detail).toContain("2026-09-01 계산은 아래 기록에서");
    expect(attemptBanner({ status: "failed", reason: { code: "company_not_found" } }, null)?.detail).toContain("공식 자료에서 이 종목을 찾지 못했습니다");
    expect(attemptBanner({ status: "saved", snapshotId: "x" }, null)).toBeNull();
    expect(attemptBanner(null, null)).toBeNull();
  });
});
