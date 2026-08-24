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

/** 서버 필터에 넘길 **날짜만**의 경계값. 로컬 달력 날짜를 쓴다.
 *
 * `starts_at`은 거래소 오프셋이 붙은 문자열(`2026-08-21T00:00:00-04:00`)로 저장되고
 * 서버는 `starts_at>=?`를 **사전순 문자열 비교**로 건다. 시각까지 실은 UTC 문자열을
 * 보내면 `T0` 다음 자리에서 `'0'`(오프셋 표기)이 `'3'`(UTC 시각)보다 앞서 정렬되어
 * **오늘 날짜의 미국 실적이 통째로 걸러진다** — 기능이 가장 필요한 D-DAY 당일에
 * 배지가 사라졌다. 날짜만 보내면 저장값의 접두가 되어 오프셋과 무관하게 통과한다.
 * 하한만 느슨해질 뿐 지난 일정은 `nextEarningsByTicker`가 로컬 날짜로 다시 거른다.
 */
function calendarBound(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
}

/** 워치리스트 티커들의 다음 실적을 한 번에 읽는다. 실패는 빈 표다 — 목록을 막지 않는다. */
export async function fetchNextEarnings(
  tickers: string[],
  now: Date = new Date(),
): Promise<Record<string, EarningsEvent>> {
  const wanted = [...new Set(tickers.map((value) => String(value || "").trim()).filter(Boolean))];
  if (!wanted.length) return {};
  // 상한도 사전순 비교라 날짜만 보내면 **그날 일정이 빠진다**(`...T00:00:00-04:00` > `...`).
  // 마지막 날을 온전히 담으려고 하루 뒤를 경계로 준다.
  const end = new Date(now.getTime() + (LOOKAHEAD_DAYS + 1) * 86_400_000);
  const params = new URLSearchParams({
    start: calendarBound(now),
    end: calendarBound(end),
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
