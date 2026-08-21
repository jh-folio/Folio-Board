/** 워치리스트 종목의 다음 실적 일정.
 *
 * 백엔드는 이미 다 있다 — 시장 캘린더가 워치리스트 티커의 earnings를 수집하고
 * (`market_calendar/service.py::_calendar_target_tickers`), `/api/market-calendar`가
 * `kind`/`ticker` 필터를 지원한다. 없던 것은 화면뿐이다.
 *
 * **카드마다 부르지 않는다.** 티커를 한 번에 넘겨 한 번만 묻고 티커별로 나눈다 —
 * 종목 20개짜리 워치리스트가 20개의 요청을 만들면 목록이 그만큼 늦게 뜬다.
 */
import { getJson } from "../api";

export type EarningsEvent = {
  id?: string;
  kind?: string;
  title?: string;
  market?: string;
  tickers?: string[];
  startsAt?: string;
  status?: string;
  companyName?: string;
};

/** 확정이 아닌 일정. yfinance 예정치라 날짜가 움직인다. */
export function isEstimated(event: EarningsEvent): boolean {
  return String(event.status || "").toLowerCase() !== "confirmed";
}

/** D-day. 오늘이면 0, 지난 일정이면 음수. */
export function daysUntil(startsAt: string, now: Date = new Date()): number | null {
  const target = new Date(startsAt);
  if (Number.isNaN(target.getTime())) return null;
  const startOfDay = (value: Date) => Date.UTC(value.getFullYear(), value.getMonth(), value.getDate());
  return Math.round((startOfDay(target) - startOfDay(now)) / 86_400_000);
}

/** 배지 문구. `D-3`처럼 짧게, 오늘은 `D-DAY`. */
export function ddayLabel(startsAt: string, now: Date = new Date()): string {
  const days = daysUntil(startsAt, now);
  if (days == null || days < 0) return "";
  return days === 0 ? "D-DAY" : `D-${days}`;
}

export function formatEarningsDate(startsAt: string): string {
  const value = String(startsAt || "").slice(0, 10);
  return value.replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1.$2.$3");
}

/** 티커별 **가장 가까운 다가올** 실적 일정. 지난 일정은 버린다. */
export function nextEarningsByTicker(
  events: EarningsEvent[],
  now: Date = new Date(),
): Record<string, EarningsEvent> {
  const byTicker: Record<string, EarningsEvent> = {};
  for (const event of events || []) {
    if (String(event.kind || "") !== "earnings") continue;
    const startsAt = String(event.startsAt || "");
    const days = daysUntil(startsAt, now);
    if (days == null || days < 0) continue;
    for (const raw of event.tickers || []) {
      const ticker = String(raw || "").toUpperCase();
      if (!ticker) continue;
      const current = byTicker[ticker];
      if (!current || startsAt < String(current.startsAt || "")) byTicker[ticker] = event;
    }
  }
  return byTicker;
}

const LOOKAHEAD_DAYS = 120;

/** 워치리스트 티커들의 다음 실적을 한 번에 읽는다. 실패는 빈 표다 — 목록을 막지 않는다. */
export async function fetchNextEarnings(
  tickers: string[],
  now: Date = new Date(),
): Promise<Record<string, EarningsEvent>> {
  const wanted = [...new Set(tickers.map((value) => String(value || "").trim()).filter(Boolean))];
  if (!wanted.length) return {};
  const end = new Date(now.getTime() + LOOKAHEAD_DAYS * 86_400_000);
  const params = new URLSearchParams({
    start: now.toISOString(),
    end: end.toISOString(),
    kind: "earnings",
    limit: "500",
  });
  for (const ticker of wanted) params.append("ticker", ticker);
  try {
    const payload = await getJson<{ events?: EarningsEvent[] }>(`/api/market-calendar?${params}`);
    return nextEarningsByTicker(payload.events || [], now);
  } catch {
    return {};
  }
}
