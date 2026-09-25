import { describe, expect, it } from "vitest";
import { applyLiveTick, chartSessionKey, liveCandleUpdate, liveWallClockBucket, providerCopy, realtimeStatusForBootstrap, rowsForChartRedraw, shouldOpenRealtime, type Point } from "./MarketChartFigure";

describe("shared chart realtime helpers", () => {
  it("opens only a non-empty visible 1D bootstrap explicitly marked available by REST", () => {
    const ready = { liveEligible: true, liveStatus: "available", series: [{ time: "2026-06-18T10:30:00-04:00", close: 210 }] };
    expect(shouldOpenRealtime(ready, "1d", true)).toBe(true);
    expect(shouldOpenRealtime({ ...ready, series: [] }, "1d", true)).toBe(false);
    expect(shouldOpenRealtime({ ...ready, liveStatus: "unavailable" }, "1d", true)).toBe(false);
    expect(shouldOpenRealtime({ ...ready, liveEligible: false, liveStatus: "unsupported" }, "1d", true)).toBe(false);
    expect(shouldOpenRealtime({ ...ready, realtimeEligible: false }, "1d", true)).toBe(false);
    expect(shouldOpenRealtime(null, "1d", true)).toBe(false);
    expect(shouldOpenRealtime(ready, "1m", true)).toBe(false);
    expect(shouldOpenRealtime(ready, "1d", false)).toBe(false);
    expect(realtimeStatusForBootstrap({ liveStatus: "available", series: ready.series }, "1d")).toBe("pending");
    expect(realtimeStatusForBootstrap({ liveStatus: "available", realtimeEligible: false, series: ready.series }, "1d")).toBe("rest");
    expect(realtimeStatusForBootstrap({ liveStatus: "available", series: [] }, "1d")).toBe("delayed");
    expect(realtimeStatusForBootstrap({ liveStatus: "not_requested", series: ready.series }, "1d")).toBe("delayed");
    expect(realtimeStatusForBootstrap({ liveStatus: "unsupported", series: ready.series }, "1d")).toBe("unsupported");
    expect(realtimeStatusForBootstrap({ liveStatus: "unavailable", series: [] }, "1d")).toBe("unavailable");
  });

  it("uses a new React session before effects can paint an old REST payload", () => {
    expect(chartSessionKey("AAPL", "1d")).not.toBe(chartSessionKey("MSFT", "1d"));
    expect(chartSessionKey("AAPL", "1d")).not.toBe(chartSessionKey("AAPL", "1m"));
  });

  it("uses the exchange wall clock for official instants, including US daylight saving", () => {
    expect(liveWallClockBucket("2026-06-18T23:30:00+09:00", "US")).toBe("2026-06-18T10:30:00");
    expect(liveWallClockBucket("2026-06-18T09:34:59+09:00", "KR")).toBe("2026-06-18T09:30:00");
  });

  it("keeps the REST chart source distinct from a live Toss headline", () => {
    expect(providerCopy()).toBeNull();
    expect(providerCopy("yfinance")).toBe("yfinance");
    expect(providerCopy("toss_open_api", "toss_open_api")).toBe("Toss Open API");
    expect(providerCopy("yfinance", "toss_open_api")).toBe("현재가 Toss Open API · 차트 yfinance");
  });

  it("keeps the live rows through style or theme redraw until REST bootstraps again", () => {
    const rest: Point[] = [{ time: "2026-06-18T10:30:00-04:00", open: 210, high: 211, low: 209, close: 210.5 }];
    const live = liveCandleUpdate(rest, { type: "tick", status: "live", market: "US", price: 212, asOf: "2026-06-18T23:34:59+09:00" });
    expect(rowsForChartRedraw(rest, live, false)).toBe(live);
    expect(rowsForChartRedraw(rest, live, true)).toBe(rest);
    expect(rowsForChartRedraw([], live, true)).toEqual([]);
  });

  it("updates only the active five-minute candle, drops older ticks, and never assigns stream volume", () => {
    const rows: Point[] = [{ time: "2026-06-18T10:30:00-04:00", open: 210, high: 211, low: 209, close: 210.5, ma20: 200 }];
    const next = liveCandleUpdate(rows, { type: "tick", status: "live", price: 212, asOf: "2026-06-18T23:34:59+09:00", market: "US" });
    expect(next).toHaveLength(1);
    expect(next[0]).toMatchObject({ open: 210, high: 212, low: 209, close: 212 });
    expect(next[0]).not.toHaveProperty("volume");
    const lastInstant = Date.parse("2026-06-18T23:34:59+09:00");
    expect(applyLiveTick(next, lastInstant, { type: "tick", status: "live", price: 190, asOf: "2026-06-18T23:31:00+09:00", market: "US" })).toEqual({ rows: next, instant: lastInstant });
    expect(applyLiveTick(next, lastInstant, { type: "tick", status: "live", price: 190, asOf: "2026-06-18T23:34:59+09:00", market: "US" })).toEqual({ rows: next, instant: lastInstant });
    expect(liveCandleUpdate(next, { type: "tick", status: "live", price: 190, asOf: "2026-06-18T23:25:00+09:00", market: "US" })).toBe(next);
    const advanced = applyLiveTick(next, lastInstant, { type: "tick", status: "live", price: 213, asOf: "2026-06-18T23:35:00+09:00", market: "US" });
    const newCandle = advanced.rows;
    expect(advanced.instant).toBe(Date.parse("2026-06-18T23:35:00+09:00"));
    expect(newCandle[newCandle.length - 1]).toMatchObject({
      time: "2026-06-18T10:35:00", open: 213, high: 213, low: 213, close: 213,
    });
    expect(liveCandleUpdate(rows, { type: "tick", status: "live", price: 212, asOf: "" })).toBe(rows);
  });
});
