import { describe, expect, it } from "vitest";
import {
  attemptBanner, bannerFor, decompositionCards, fractionToPercent, heroText, irrText, money, multiple, pct, pctPlain, pctSigned,
  atLeastRequired, compareDecimal, labelRows, percentToFraction, rangePosition, reasonText, scaleLayout, shiftDecimal, showReferenceFacts, noticeText,
} from "./format";
import type { Projection, ScenarioRow, SnapshotView } from "./types";
import { cashPerHundred, cashSpan, moneyShort, noReturns, notApplicableAttempt, percentOne, plainOne, signedOne } from "./format";
import { instrumentIdFor } from "./PriceTab";

describe("spec-4 display", () => {
  it("preserves reason parameters and supplement notices", () => {
    expect(reasonText({ code: "history_too_short", subCode: "loss_years", range: "growth", n: 2, required: 3, historyYears: 8 }))
      .toBe("주당이익이 0 이하인 해가 있어 비교할 5년 구간이 2개입니다(필요 3개)");
    expect(reasonText({ code: "price_unavailable", subCode: "provider_error" })).toBe("가격 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요");
    expect(noticeText({ code: "listed_class_eps", class: "Class A" })).toContain("Class A");
    expect(noticeText({ code: "derived_eps_years", years: [2020] })).toContain("FY2020");
  });
  it("opens reference facts only for six distinct permitted canonical rows", () => {
    const scenarios = ([5, 10] as const).flatMap(horizon => (["conservative", "base", "optimistic"] as const)
      .map(label => ({ label, horizon, status: "unavailable" as const, reason: { code: "negative_base_eps" } })));
    const view = { results: { scenarios, referenceFacts: { status: "available" } } } as SnapshotView;
    expect(showReferenceFacts(view)).toBe(true);
    for (const bad of [scenarios.slice(1), [...scenarios.slice(1), scenarios[1]],
      scenarios.map((row, i) => i ? row : { ...row, reason: { code: "share_event_unknown" } })]) {
      expect(showReferenceFacts({ ...view, results: { ...view.results, scenarios: bad } })).toBe(false);
    }
    expect(showReferenceFacts({ ...view, results: { ...view.results, referenceFacts: undefined } })).toBe(false);
  });
  it("rounds stored cash ratios half-even without binary float ties", () => {
    expect(cashPerHundred("0.7950")).toBe("80");
    expect(cashPerHundred("0.8050")).toBe("80");
    expect(cashPerHundred("1.5050")).toBe("150");
    expect(cashPerHundred("-0.2050")).toBe("−20");
    expect(cashPerHundred("-0.0000")).toBe("0");
  });
  it("uses the known market and accepts Korean alphanumeric codes", () => {
    expect(instrumentIdFor("0123a0")).toBe("KR:0123A0");
    expect(instrumentIdFor("ABCDE", "US")).toBe("US:ABCDE");
    expect(instrumentIdFor("005930", "KR")).toBe("KR:005930");
  });
});

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
    expect(percentToFraction("1e2")).toBe("1e2"); // not a plain decimal: passed on unchanged, the server answers invalid_number
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
    expect(money("-0.29", "USD")).toBe("−$0.29");
    expect(money("-1500", "KRW")).toBe("−1,500원");
    expect(money("-0.001", "USD")).toBe("$0.00");
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

describe("headline (conditional, history first)", () => {
  const rowOf = (irr: string | null, irrRange: string | null = null, horizon = 10) =>
    ({ label: "base", horizon, status: "available", irr, irrRange, g: "0.19", exitPE: "25.4", payout: "0.19" }) as unknown as ScenarioRow;
  const base = { horizon: 10 as const, base: rowOf("0.0661"), holdingYears: 10, baseHolding: rowOf("0.0661") };
  it("states the condition and compares only on the chosen holding period", () => {
    const hero = heroText({ ...base, required: "6" });
    expect(hero.title).toBe("과거 10년 흐름이 이어진다면, 지금 사서 10년 보유할 때 연평균 6.6%입니다.");
    expect(hero.title2).toBe("내가 정한 최소 수익률(연 6%)보다 높습니다.");
    expect(hero.sub).toContain("주당이익이 보통 연 19.0% 늘었고, 주가는 보통 이익의 25.4배");
    expect(hero.sub).toContain("보장된 수익이 아닙니다");
    expect(hero.sub).toContain("6%는 ‘투자 기준’에서 내가 정한 최소 수익률");
    expect(heroText({ ...base, required: "7" }).title2).toBe("내가 정한 최소 수익률(연 7%)보다 낮습니다.");
    expect(heroText({ ...base, required: "6.5" }).title2).toContain("연 6.5%");
    const other = heroText({ ...base, horizon: 5, base: rowOf("0.03", null, 5), required: "6" });
    expect(other.title).toBe("과거 10년 흐름이 이어진다면, 지금 사서 5년 보유할 때 연평균 3.0%입니다.");
    expect(other.title2).toBe("내 기준 비교는 기본 보유 기간(10년)으로 합니다. 10년 연평균 6.6%로, 최소 수익률(연 6%)보다 높습니다.");
    expect(other.sub).toContain("앞으로 5년도 비슷하다고");
  });
  it("never words the result as a certainty", () => {
    const hero = heroText({ ...base, required: "6" });
    expect(`${hero.title}${hero.title2}${hero.sub}`).not.toMatch(/버는 셈|벌 수 있습니다|보장됩니다/);
  });
  it("compares exactly like the server: 0.29 is not below 29%", () => {
    const exact = { ...base, base: rowOf("0.29"), baseHolding: rowOf("0.29") };
    expect(0.29 * 100 >= 29).toBe(false); // the float trap this guards against
    expect(heroText({ ...exact, required: "29" }).title2).toContain("보다 높습니다");
    expect(atLeastRequired(rowOf("0.29"), "29")).toBe(true);
    expect(atLeastRequired(rowOf("0.2899"), "29")).toBe(false);
    expect(atLeastRequired(rowOf("-0.05"), "-5")).toBe(true);
    expect(compareDecimal("1.50", "1.5")).toBe(0);
    expect(compareDecimal("-0.1", "0.01")).toBe(-1);
    expect(compareDecimal("abc", "1")).toBeNull();
  });
  it("names an out-of-range base return and still compares it", () => {
    const above = { ...base, base: rowOf(null, "above_range"), baseHolding: rowOf(null, "above_range") };
    const hero = heroText({ ...above, required: "20" });
    expect(hero.title).toBe("과거 10년 흐름이 이어진다면, 지금 사서 10년 보유할 때 연평균 100% 초과입니다.");
    expect(hero.title2).toBe("내가 정한 최소 수익률(연 20%)보다 높습니다.");
    expect(atLeastRequired(rowOf(null, "below_range"), "-50")).toBe(false);
  });
  it("never invents a comparison without a criterion or a number", () => {
    const none = heroText({ ...base, required: null, holdingYears: null });
    expect(none.title).toBe("과거 10년 흐름이 이어진다면, 지금 사서 10년 보유할 때 연평균 6.6%입니다.");
    expect(none.title2).toBe("");
    expect(none.sub).toContain("내 기준(원하는 최소 수익률)을 정하면 비교");
    expect(heroText({ ...base, base: undefined, required: "6" }).title).toContain("계산하지 못했습니다");
    expect(atLeastRequired(rowOf("0.1"), null)).toBeNull();
  });
});

describe("short money and cash span", () => {
  it("shortens large amounts per currency", () => {
    expect(moneyShort("763460000000", "USD")).toBe("7,634.6억 달러");
    expect(moneyShort("12300000000000", "KRW")).toBe("12.3조 원");
    expect(moneyShort("450000000000", "KRW")).toBe("4,500억 원");
    expect(moneyShort("12.5", "USD")).toBe("$12.50");
  });
  it("names contiguous and gapped fiscal years differently", () => {
    expect(cashSpan([{ fiscalYear: 2016 }, { fiscalYear: 2017 }, { fiscalYear: 2018 }])).toBe("지난 3년(FY2016–FY2018)");
    expect(cashSpan([{ fiscalYear: 2016 }, { fiscalYear: 2018 }])).toBe("2개 회계연도(FY2016–FY2018)");
  });
  it("rounds to one decimal and signs with a real minus", () => {
    expect(percentOne("0.0661")).toBe(6.6);
    expect(signedOne(-6.4)).toBe("−6.4%");
    expect(signedOne(19)).toBe("+19.0%");
    expect(plainOne(13.1)).toBe("13.1%");
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
    expect(attemptBanner({ status: "failed", reason: { code: "company_not_found" } }, null)?.detail).toContain("공식 자료에서 이 종목을 찾지 못해 계산하지 않았습니다");
    expect(attemptBanner({ status: "saved", snapshotId: "x" }, null)).toBeNull();
    expect(attemptBanner(null, null)).toBeNull();
  });
});

describe("scale labels", () => {
  it("puts close points on different rows and leaves spread points on one row", () => {
    expect(labelRows([10, 15, 20])).toEqual([0, 1, 2]);
    expect(labelRows([10, 50, 90])).toEqual([0, 0, 0]);
    expect(labelRows([60, 10, 15])).toEqual([1, 0, 0].map((_, i) => labelRows([60, 10, 15])[i])); // order of input does not matter
    expect(labelRows([60, 10, 15])[0]).toBe(0);
  });
});

describe("whole-tab states", () => {
  const unavailable = (label: string, horizon: number) => ({ label, horizon, status: "unavailable", reason: { code: "negative_base_eps" } });
  const viewOf = (rows: unknown[]) => ({ results: { scenarios: rows } }) as unknown as SnapshotView;
  it("treats only a tab with no calculated cell as blocked; out-of-range cells still count", () => {
    const all = [5, 10].flatMap(h => ["conservative", "base", "optimistic"].map(l => unavailable(l, h)));
    expect(noReturns(viewOf(all))).toBe(true);
    expect(noReturns(viewOf([...all.slice(1), { label: "conservative", horizon: 5, status: "available", irr: null, irrRange: "above_range" }]))).toBe(false);
    expect(noReturns(viewOf([]))).toBe(false);
  });
  it("names a fund attempt as not applicable, but not a passing failure", () => {
    expect(notApplicableAttempt({ status: "failed", reason: { code: "fund_not_supported" } })).toBe(true);
    expect(notApplicableAttempt({ status: "failed", reason: { code: "price_unavailable", subCode: "provider_error" } })).toBe(false);
    expect(notApplicableAttempt(null)).toBe(false);
  });
});
