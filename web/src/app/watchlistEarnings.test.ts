import { describe, expect, it } from "vitest";
import { daysUntil, ddayLabel, fetchNextEarnings, isEstimated, nextEarningsByTicker } from "./watchlistEarnings";

const NOW = new Date("2026-08-20T09:00:00+09:00");

function event(ticker: string, startsAt: string, status = "estimated") {
  return { kind: "earnings", tickers: [ticker], startsAt, status };
}

describe("daysUntil / ddayLabel", () => {
  it("오늘 일정은 D-DAY다", () => {
    // 날짜 판정은 **보는 사람의 하루** 기준이다. 21:00 UTC는 서울에서 이미 다음 날이라
    // 그것을 오늘이라고 부르면 D-day가 하루씩 어긋난다.
    expect(daysUntil("2026-08-20T18:00:00+09:00", NOW)).toBe(0);
    expect(ddayLabel("2026-08-20T18:00:00+09:00", NOW)).toBe("D-DAY");
  });

  it("자정을 넘긴 해외 일정은 그 지역의 다음 날로 센다", () => {
    // 미국장 실적은 KST로 다음 날 새벽이다. 한국 사용자에게는 내일 일정이 맞다.
    expect(daysUntil("2026-08-20T21:00:00Z", NOW)).toBe(1);
  });

  it("앞으로 남은 날을 센다", () => {
    expect(ddayLabel("2026-08-23T00:00:00Z", NOW)).toBe("D-3");
  });

  it("지난 일정은 배지를 만들지 않는다", () => {
    // 지나간 실적을 "다음 실적"이라고 말하면 안 된다.
    expect(ddayLabel("2026-08-19T00:00:00Z", NOW)).toBe("");
  });

  it("읽을 수 없는 날짜는 조용히 비운다", () => {
    expect(daysUntil("", NOW)).toBeNull();
    expect(ddayLabel("bogus", NOW)).toBe("");
  });
});

describe("isEstimated", () => {
  it("확정만 확정이다", () => {
    // yfinance 예정치는 날짜가 움직인다. 확정과 같은 무게로 보여주면 안 된다.
    expect(isEstimated({ status: "confirmed" })).toBe(false);
    expect(isEstimated({ status: "estimated" })).toBe(true);
    expect(isEstimated({})).toBe(true);
  });
});

describe("nextEarningsByTicker", () => {
  it("티커별로 가장 가까운 다가올 일정만 남긴다", () => {
    const table = nextEarningsByTicker([
      event("AAPL", "2026-09-01T00:00:00Z"),
      event("AAPL", "2026-08-25T00:00:00Z"),
      event("MSFT", "2026-08-27T00:00:00Z"),
    ], NOW);

    expect(table.AAPL.startsAt).toBe("2026-08-25T00:00:00Z");
    expect(table.MSFT.startsAt).toBe("2026-08-27T00:00:00Z");
  });

  it("지난 일정은 버린다", () => {
    const table = nextEarningsByTicker([event("AAPL", "2026-08-01T00:00:00Z")], NOW);

    expect(table.AAPL).toBeUndefined();
  });

  it("실적이 아닌 일정은 세지 않는다", () => {
    // 캘린더에는 지표·중앙은행·휴장·배당도 들어 있다.
    const table = nextEarningsByTicker([
      { kind: "dividend", tickers: ["AAPL"], startsAt: "2026-08-25T00:00:00Z" },
      { kind: "macro", tickers: ["AAPL"], startsAt: "2026-08-24T00:00:00Z" },
    ], NOW);

    expect(table.AAPL).toBeUndefined();
  });

  it("티커는 대문자로 맞춘다", () => {
    const table = nextEarningsByTicker([event("aapl", "2026-08-25T00:00:00Z")], NOW);

    expect(table.AAPL).toBeDefined();
  });

  it("한 일정이 여러 티커를 가리키면 모두에 붙는다", () => {
    const table = nextEarningsByTicker([
      { kind: "earnings", tickers: ["005930", "005930.KS"], startsAt: "2026-08-25T00:00:00Z" },
    ], NOW);

    expect(table["005930"]).toBeDefined();
    expect(table["005930.KS"]).toBeDefined();
  });
});

describe("fetchNextEarnings", () => {
  it("경계를 날짜만으로 보낸다 — 시각을 실으면 당일 실적이 사전순 비교에서 빠진다", async () => {
    // 서버는 `starts_at>=?`를 문자열 사전순으로 건다. 저장값은 거래소 오프셋이 붙은
    // `2026-08-21T00:00:00-04:00`이라, UTC 시각 문자열을 보내면 `T0` 다음 자리에서
    // `'0'` < `'3'`으로 저장값이 앞서 정렬되어 **오늘 실적이 통째로 걸러졌다.**
    const calls: string[] = [];
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      return new Response(JSON.stringify({ events: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;
    try {
      await fetchNextEarnings(["AMD"], new Date("2026-08-21T03:15:00.000Z"));
    } finally {
      globalThis.fetch = originalFetch;
    }

    const query = new URL(calls[0], "http://localhost").searchParams;
    const start = String(query.get("start"));
    expect(start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect("2026-08-21T00:00:00-04:00" >= start).toBe(true);
    expect(String(query.get("end"))).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
