import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson, postJson, MARKET_CODE_LABELS, MARKET_KO_LABELS } from "../../api";
import { useMarketScope } from "../useMarketScope";

type Event = {
  id: string; kind: string; title: string; startsAt: string; status: string;
  market?: string; tickers?: string[]; source?: string; sourceUrl?: string;
  actualValue?: string; forecastValue?: string; previousValue?: string; unit?: string; observedAt?: string;
  companyName?: string;
  allDay?: boolean; timezone?: string; importance?: number; provider?: string;
  additionalSources?: { id: string; source?: string; provider: string; sourceUrl?: string }[];
};
type FocusSymbol = { symbol: string; label?: string; source?: string };
type CalendarView = "week" | "month";

export const KIND_KO: Record<string, string> = {
  macro: "경제지표", central_bank: "중앙은행", holiday: "휴장", earnings: "실적", filing: "공시", dividend: "배당",
};
export const STATUS_KO: Record<string, string> = {
  confirmed: "확정", estimated: "추정", tentative: "미정", actual: "발표됨",
};

export function calendarCertainty(event: Event): string {
  if (event.provider === 'bok') return event.actualValue ? '값 확인 · 발표일 미확인' : '추정 일정';
  return STATUS_KO[event.status] || event.status;
}

function macroLink(event: Event): string | null {
  const id = event.provider === 'bok' && event.title.includes('CPI') ? 'KR_CPI'
    : event.provider === 'fred' && event.title === '미국 CPI' ? 'CPIAUCSL'
    : event.provider === 'fred' && event.title === '미국 GDP' ? 'GDPC1'
    : event.provider === 'fred' && event.title === '미국 산업생산' ? 'INDPRO' : null;
  return id ? `#/market-memory/macro?market=${event.market === 'KR' ? 'KR' : 'US'}&series=${id}` : null;
}
const KIND_FILTERS: Array<{ value: string; label: string }> = [
  { value: "earnings", label: "실적" }, { value: "macro", label: "지표" },
  { value: "central_bank", label: "중앙은행" }, { value: "holiday", label: "휴장" },
  { value: "filing", label: "공시" }, { value: "dividend", label: "배당" },
];
const numberOf = (value?: string) => {
  // `Number("")`은 NaN이 아니라 **0**이다. 빈 값을 먼저 걸러내지 않으면 값이 없는
  // 예상치가 0으로 읽혀 `예상  대비 +3.2`처럼 숫자 없는 문구가 뜨고, 그 +3.2는
  // 실제 서프라이즈가 아니라 발표치 그대로다. 서버는 결측을 빈 문자열로 주고
  // (`market_calendar/schema.py::_number`) yfinance 컨센서스는 항상 비어 있어
  // 거의 모든 지표 행이 이 경로를 탔다.
  const text = String(value ?? "").replace(/,/g, "").trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
};

/** 발표 숫자를 무엇과 비교해 읽을지. 예상치가 있으면 그것이 우선이다. */
export function comparisonLabel(event: Event): string {
  const actual = numberOf(event.actualValue);
  const forecast = numberOf(event.forecastValue);
  if (actual !== null && forecast !== null) {
    const diff = actual - forecast;
    const sign = diff > 0 ? "+" : "";
    return `예상 ${event.forecastValue} 대비 ${sign}${Number(diff.toFixed(4))}`;
  }
  return event.previousValue ? `직전 ${event.previousValue}` : "";
}

export function comparisonDirection(event: Event): "up" | "down" | "flat" {
  const actual = numberOf(event.actualValue);
  const base = numberOf(event.forecastValue) ?? numberOf(event.previousValue);
  if (actual === null || base === null || actual === base) return "flat";
  return actual > base ? "up" : "down";
}

/** 캘린더 격자는 좁아 티커로 두고, 아래 표에서는 이름을 펼친다. */
function eventTitleWithName(event: Event): string {
  const ticker = (event.tickers || [])[0];
  const name = String(event.companyName || "").trim();
  if (!ticker || !name) return event.title;
  if (event.title.includes(name)) return event.title;
  return event.title.replace(ticker, `${name} (${ticker})`);
}

export const MARKET_KO: Record<string, string> = MARKET_KO_LABELS;
const MARKET_FILTERS = ["US", "KR", "EUROPE", "JP"];
// 중요도는 하한 하나로 고른다. 3단계를 각각 토글하게 하면 "중간만 보기"처럼
// 쓸 일 없는 조합이 생기고, 무엇이 켜졌는지 읽기 어려워진다.
// 막대는 `걸러내는 문턱의 높이`다. 최상위가 가장 꽉 차고 전부가 한 칸이다.
// 처음에는 `보이는 등급 수`로 칠했는데(전부=3칸), 세 칸짜리 아이콘이 가장
// 느슨한 선택지에 붙어 신호 세기 아이콘의 통념과 정반대로 읽혔다.
const IMPORTANCE_FILTERS = [
  { value: 3, label: "최상위", hint: "FOMC·금리 결정 같은 최상위 일정만" },
  { value: 2, label: "중간 이상", hint: "실적·주요 지표까지" },
  { value: 1, label: "전부", hint: "휴장일·배당까지 전부" },
];
// 유럽은 거래소마다 휴장일이 달라 시장 하나로 묶이지 않는다. 칩에서도 어느 거래소가
// 쉬는지 보여야 "유럽 휴장"으로 잘못 읽히지 않는다.
const VENUE_KO: Record<string, string> = {
  nyse: "NYSE", krx: "KRX", lse: "런던", xetra: "프랑크푸르트",
  euronext: "파리·암스테르담", borsa_italiana: "밀라노", bme: "마드리드", jpx: "도쿄",
};
const DOW_KO = ["월", "화", "수", "목", "금", "토", "일"];
const DAY_MS = 24 * 60 * 60 * 1000;

function dateKey(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

/** 지금의 **KST 달력 날짜**를 로컬 자정 Date로 만든다.
 *
 *  일정은 KST로 묶이는데(`eventDateKeyKST`) 격자·`오늘` 표시·선택일은 브라우저
 *  로컬 달력을 썼다. 두 축이 갈리면 서울 밖에서 일정이 옆 칸에 붙고 `오늘`이
 *  엉뚱한 날을 가리킨다. 격자는 시각이 아니라 달력 산술만 하므로 KST 날짜
 *  성분을 로컬 Date에 담아 두면 `dateKey()`가 곧 일정 키가 된다. */
function kstToday(): Date {
  const text = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const [year, month, day] = text.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function eventDateKeyKST(event: Event): string {
  if (event.allDay || /^\d{4}-\d{2}-\d{2}$/.test(event.startsAt)) return event.startsAt.slice(0, 10);
  const date = new Date(event.startsAt);
  if (Number.isNaN(date.getTime())) return event.startsAt.slice(0, 10);
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function timeLabelKST(event: Pick<Event, "allDay" | "startsAt" | "kind">): string {
  if (event.allDay || /^\d{4}-\d{2}-\d{2}$/.test(event.startsAt)) return "종일";
  const date = new Date(event.startsAt);
  if (Number.isNaN(date.getTime())) return "—";
  if (event.kind === "earnings") {
    const et = new Intl.DateTimeFormat("en-GB", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
    if (et === "00:00") return "발표일";
    if (et < "09:30") return "장전";
    if (et >= "16:00") return "장후";
  }
  return new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

// 날짜 이동은 밀리초가 아니라 달력 성분으로 한다. `+24h` 누적은 DST 되돌림 주에
// 같은 날짜를 두 번 만들어(격자 중복 + React 중복 key) 한 칸을 통째로 잃는다.
function addDays(value: Date, days: number): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate() + days);
}

function mondayOf(value: Date): Date {
  const date = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  return addDays(date, -((date.getDay() + 6) % 7));
}

function shortChip(event: Event): string {
  if (event.kind === "earnings" && event.tickers?.length) return `${event.tickers[0]} · ${timeLabelKST(event)}`;
  if (event.kind === "holiday") {
    const venue = VENUE_KO[event.provider || ""];
    return venue ? `휴장 · ${venue}` : event.title.slice(0, 22);
  }
  return event.title.slice(0, 22);
}

export function MarketCalendar({ focusSymbols }: { focusSymbols: FocusSymbol[] }) {
  const [events, setEvents] = useState<Event[]>([]);
  const [view, setView] = useState<CalendarView>("week");
  // 빈 집합 = 전체. 브리핑 시장 선택과 같은 규칙이라 조작을 새로 배우지 않는다.
  const [kinds, setKinds] = useState<string[]>([]);
  const [markets, setMarkets] = useState<string[]>([]);
  // 중요도 하한. 3=최상위만, 2=중간 이상, 1=전부. 일정이 넷 시장에서 몰려오면
  // 무엇을 먼저 볼지 고르는 축이 필요하다.
  const [minImportance, setMinImportance] = useState(1);
  // 관심 시장 범위 밖의 일정은 칩에서도 목록에서도 뺀다.
  const { isSelected: marketInScope } = useMarketScope();
  const [watchOnly, setWatchOnly] = useState(false);
  const [anchor, setAnchor] = useState(() => kstToday());
  const [selectedDay, setSelectedDay] = useState(() => dateKey(kstToday()));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const start = new Date(anchor.getTime() - 40 * DAY_MS);
    const end = new Date(anchor.getTime() + 70 * DAY_MS);
    try {
      const payload = await getJson<{ events?: Event[] }>(
        `/api/market-calendar?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&limit=500`,
      );
      setEvents(payload.events || []);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "일정을 불러오지 못했습니다.");
    }
  }, [anchor]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    getJson<{ calendarView?: CalendarView; calendarKinds?: string[]; calendarMarkets?: string[]; calendarKind?: string; calendarMarket?: string; calendarWatchlistOnly?: boolean; calendarMinImportance?: number }>("/api/dashboard/settings")
      .then((row) => {
        if (row.calendarView === "week" || row.calendarView === "month") setView(row.calendarView);
        // 예전 단일 선택 설정은 한 개짜리 배열로 읽어 기존 사용자의 선택을 잃지 않는다.
        setKinds(row.calendarKinds || (row.calendarKind && row.calendarKind !== "all" ? [row.calendarKind] : []));
        setMarkets(row.calendarMarkets || (row.calendarMarket && row.calendarMarket !== "all" ? [row.calendarMarket] : []));
        setWatchOnly(Boolean(row.calendarWatchlistOnly));
        setMinImportance(Math.min(Math.max(Number(row.calendarMinImportance) || 1, 1), 3));
      })
      .catch(() => undefined);
  }, []);

  function persist(partial: Record<string, unknown>) {
    postJson("/api/dashboard/settings", partial).catch(() => undefined);
  }

  const watchSymbols = useMemo(
    () => new Set(focusSymbols.filter((row) => row.source !== "fallback").map((row) => row.symbol.toUpperCase())),
    [focusSymbols],
  );

  const filtered = useMemo(() => events.filter((event) => {
    if (kinds.length && !kinds.includes(event.kind)) return false;
    if (!marketInScope(event.market || "")) return false;
    if ((event.importance || 1) < minImportance) return false;
    if (markets.length && !markets.includes((event.market || "").toUpperCase())) return false;
    if (watchOnly && !(event.tickers || []).some((t) => watchSymbols.has(t.toUpperCase()))) return false;
    return true;
  }), [events, kinds, markets, watchOnly, watchSymbols, marketInScope, minImportance]);

  const byDay = useMemo(() => {
    const map = new Map<string, Event[]>();
    for (const event of filtered) {
      const key = eventDateKeyKST(event);
      map.set(key, [...(map.get(key) || []), event]);
    }
    for (const rows of map.values()) rows.sort((a, b) => (b.importance || 0) - (a.importance || 0) || a.startsAt.localeCompare(b.startsAt));
    return map;
  }, [filtered]);

  const weekStart = mondayOf(anchor);
  const weekDays = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
  const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const monthCells = useMemo(() => {
    const first = mondayOf(monthStart);
    const cells: Date[] = [];
    for (let index = 0; index < 42; index += 1) cells.push(addDays(first, index));
    while (cells.length > 7 && cells[cells.length - 7].getMonth() !== anchor.getMonth()) cells.splice(-7, 7);
    return cells;
  }, [anchor, monthStart]);
  const todayKey = dateKey(kstToday());
  const dayEvents = byDay.get(selectedDay) || [];
  const selectedLabel = new Date(`${selectedDay}T00:00:00`).toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long" });
  const dayKindCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of dayEvents) counts.set(event.kind, (counts.get(event.kind) || 0) + 1);
    return [...counts.entries()].map(([key, count]) => `${KIND_KO[key] || key} ${count}`).join(" · ");
  }, [dayEvents]);

  function move(step: number) {
    if (view === "week") setAnchor((prev) => addDays(prev, step * 7));
    else setAnchor((prev) => new Date(prev.getFullYear(), prev.getMonth() + step, 1));
  }

  async function refresh() {
    setBusy(true); setNotice(""); setError("");
    try {
      const result = await postJson<{ stored?: number; providers?: Record<string, number | string> }>("/api/market-calendar/refresh", {});
      const fred = result.providers?.fred_macro;
      setNotice(`일정 ${result.stored ?? 0}건 수집${fred === "fred_key_required" ? " · 미국 지표 일정은 설정에서 FRED API Key를 등록하면 함께 수집됩니다" : ""}`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "일정 수집에 실패했습니다.");
    } finally { setBusy(false); }
  }

  return (
    <section className="cockpit-panel cockpit-calendar" aria-labelledby="market-calendar-title">
      <div className="cockpit-panel__head">
        <div><span>MARKET CALENDAR</span><h2 id="market-calendar-title">주요 실적·지표 일정</h2></div>
        <div className="cockpit-panel__actions">
          <div className="cockpit-chart-controls"><div className="segment" role="group" aria-label="캘린더 보기">
            <button type="button" aria-pressed={view === "week"} onClick={() => { setView("week"); persist({ calendarView: "week" }); }}>주간</button>
            <button type="button" aria-pressed={view === "month"} onClick={() => { setView("month"); persist({ calendarView: "month" }); }}>월간</button>
          </div></div>
          <button className="btn btn--icon" type="button" aria-label={view === "week" ? "이전 주" : "이전 달"} onClick={() => move(-1)}>◀</button>
          <button className="btn" type="button" onClick={() => { const now = kstToday(); setAnchor(now); setSelectedDay(dateKey(now)); }}>오늘</button>
          <button className="btn btn--icon" type="button" aria-label={view === "week" ? "다음 주" : "다음 달"} onClick={() => move(1)}>▶</button>
          <button className="btn btn--primary" type="button" onClick={refresh} disabled={busy}>{busy ? "수집 중" : "일정 수집"}</button>
        </div>
      </div>
      {/* 유형과 시장을 각각 한 줄로 나눈다. 열 개를 한 줄에 늘어놓으면 다중 선택에서
          무엇이 켜졌는지 읽히지 않는다. 아무것도 고르지 않은 상태가 "전체"다. */}
      <div className="cal-filter-row" role="group" aria-label="일정 유형 필터">
        <span className="cal-filter-label">유형</span>
        {KIND_FILTERS.map((row) => (
          <button key={row.value} type="button" className="cal-filter" aria-pressed={kinds.includes(row.value)}
            onClick={() => {
              const next = kinds.includes(row.value) ? kinds.filter((v) => v !== row.value) : [...kinds, row.value];
              setKinds(next); persist({ calendarKinds: next });
            }}>{row.label}</button>
        ))}
      </div>
      <div className="cal-filter-row" role="group" aria-label="일정 시장 필터">
        <span className="cal-filter-label">시장</span>
        {MARKET_FILTERS.filter((value) => marketInScope(value)).map((value) => (
          <button key={value} type="button" className="cal-filter" aria-pressed={markets.includes(value)}
            onClick={() => {
              const next = markets.includes(value) ? markets.filter((v) => v !== value) : [...markets, value];
              setMarkets(next); persist({ calendarMarkets: next });
            }}>{MARKET_CODE_LABELS[value] || value}</button>
        ))}
        {/* 옆 칩들과 같은 토글이다. 혼자 체크박스라 크기·정렬이 어긋나 있었다. */}
        <button type="button" className="cal-filter cal-watch-toggle" aria-pressed={watchOnly}
          onClick={() => { const next = !watchOnly; setWatchOnly(next); persist({ calendarWatchlistOnly: next }); }}>
          보유·관심만
        </button>
      </div>
      <div className="cal-filter-row" role="group" aria-label="일정 중요도 필터">
        <span className="cal-filter-label">중요도</span>
        {IMPORTANCE_FILTERS.map((row) => (
          <button
            key={row.value}
            type="button"
            className="cal-filter cal-imp-filter"
            aria-pressed={minImportance === row.value}
            data-tooltip={row.hint}
            onClick={() => { setMinImportance(row.value); persist({ calendarMinImportance: row.value }); }}
          >
            <span className="imp" aria-hidden="true">
              {[1, 2, 3].map((level) => <u key={level} className={level <= row.value ? "on" : ""} />)}
            </span>
            {row.label}
          </button>
        ))}
      </div>
      {notice && <p className="react-reader-status">{notice}</p>}
      {error && <p className="react-dashboard-error" role="alert">{error}</p>}

      {view === "week" ? (
        <div className="cal-week-strip" role="tablist" aria-label="이번 주">
          {weekDays.map((day, index) => {
            const key = dateKey(day);
            const rows = byDay.get(key) || [];
            const kinds = [...new Set(rows.map((row) => row.kind))].slice(0, 3);
            return (
              <button key={key} type="button" role="tab" aria-selected={key === selectedDay}
                className={`cal-day${key === selectedDay ? " cal-day--active" : ""}${index >= 5 ? " cal-day--dim" : ""}${key === todayKey ? " cal-day--today" : ""}`}
                onClick={() => setSelectedDay(key)}>
                <span>{DOW_KO[index]}{key === todayKey ? " · 오늘" : ""}</span>
                <b>{day.getMonth() + 1}.{day.getDate()}</b>
                <small>{rows.length ? `${rows.length}건` : "—"}</small>
                <i>{kinds.map((value) => <u key={value} data-kind={value} />)}</i>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="cal-month-grid" aria-label={`${anchor.getFullYear()}년 ${anchor.getMonth() + 1}월`}>
          {DOW_KO.map((label, index) => <span key={label} className={`cal-dow${index >= 5 ? " cal-dow--dim" : ""}`}>{label}</span>)}
          {monthCells.map((day) => {
            const key = dateKey(day);
            const rows = byDay.get(key) || [];
            const outside = day.getMonth() !== anchor.getMonth();
            return (
              <button key={key} type="button"
                aria-pressed={key === selectedDay}
                className={`cal-cell${key === todayKey ? " cal-cell--today" : ""}${outside ? " cal-cell--dim" : ""}${key === selectedDay ? " cal-cell--active" : ""}`}
                onClick={() => setSelectedDay(key)}>
                <header>{day.getDate()}{rows.length ? <b>{rows.length}건</b> : null}{key === todayKey ? <i>오늘</i> : null}</header>
                {rows.slice(0, 3).map((event) => <span key={event.id} className="ev" data-kind={event.kind}>{shortChip(event)}</span>)}
                {rows.length > 3 ? <em>+{rows.length - 3}건</em> : null}
              </button>
            );
          })}
        </div>
      )}

      <p className="cal-day-head"><b>{selectedLabel}</b>{dayEvents.length ? <> · {dayEvents.length}건 — {dayKindCounts}</> : null}</p>
      {dayEvents.length ? (
        <div className="table-scroll"><table className="cal-table">
          <thead><tr><th scope="col">시간(KST)</th><th scope="col">시장</th><th scope="col">중요도</th><th scope="col">이벤트</th><th scope="col">결과</th><th scope="col">확정도</th></tr></thead>
          <tbody>
            {dayEvents.map((event) => (
              <tr key={event.id}>
                <td>{timeLabelKST(event)}</td>
                <td><span className="chip mkt-chip">{MARKET_KO[event.market || ""] || event.market || "—"}</span></td>
                <td><span className="imp" role="img" aria-label={`중요도 ${event.importance || 1}/3`}>{[1, 2, 3].map((level) => <u key={level} className={(event.importance || 1) >= level ? "on" : ""} />)}</span></td>
                <td>
                  <strong>{eventTitleWithName(event)}</strong>
                  <small>
                    {KIND_KO[event.kind] || event.kind}{event.source ? ` · ${event.source}` : ""}
                    {/* 링크는 사용자가 읽을 원문이 있을 때만 단다. 수집 경로(yfinance
                        캘린더 등)로 내보내면 우리 화면 밖 제3자 페이지로 나가버린다. */}
                    {event.sourceUrl ? <> · <a href={event.sourceUrl} target="_blank" rel="noopener noreferrer">원문</a></> : null}
                    {macroLink(event) ? <> · <a href={macroLink(event)!}>거시 지도</a></> : null}
                    {event.additionalSources?.length ? <details><summary>같은 값의 추가 출처 {event.additionalSources.length}개</summary>{event.additionalSources.map(source => <div key={source.id}>{source.sourceUrl ? <a href={source.sourceUrl} target="_blank" rel="noopener noreferrer">{source.source || source.provider}</a> : source.source || source.provider}</div>)}</details> : null}
                  </small>
                </td>
                <td className="cal-actual">
                  {event.actualValue ? (
                    <>
                      <b>{event.actualValue}{event.unit ? ` ${event.unit}` : ""}</b>
                      {/* 발표 숫자는 예상 대비로 읽어야 의미가 생긴다. 예상치를 주는
                          제공처가 있을 때만 쓰고, 없으면 직전 대비로 내려간다. */}
                      {comparisonLabel(event) ? <small data-direction={comparisonDirection(event)}>{comparisonLabel(event)}</small> : null}
                      {event.observedAt ? <small>{event.observedAt} 기준</small> : null}
                    </>
                  ) : <span className="cal-actual__pending">—</span>}
                </td>
                <td><span className={`chip certainty-badge--${event.provider === 'bok' ? 'estimated' : event.status}`}>{calendarCertainty(event)}</span></td>
              </tr>
            ))}
          </tbody>
        </table></div>
      ) : (
        <p className="cockpit-empty">
          {events.length ? "이 날짜에는 표시할 일정이 없습니다." : "저장된 시장 일정이 없습니다. 위의 일정 수집을 실행하면 미국·한국·유럽·일본 휴장일, FOMC·ECB·BoE·BOJ 금리 결정, 보유/관심 종목 실적이 채워집니다."}
        </p>
      )}
    </section>
  );
}
