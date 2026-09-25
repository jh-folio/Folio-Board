import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { getJson } from "../../api";
import { ChartDataTable } from "../charts/ChartDataTable";
import { KIND_KO, STATUS_KO, timeLabelKST } from "./MarketCalendar";
import { barReadout, barTimeText, chartSummaryLabel, isCandleView, nextBarIndex } from "./marketChartA11y";

/** 네이티브 시장 차트의 **그림 한 장**.
 *
 * 종목 선택·설정 저장·패널 제목은 이 안에 없다 — 대시보드는 그것들을 자기가 갖고,
 * 워치리스트 상세는 종목이 이미 정해져 있어 필요가 없다. 예전에는 그리기와 고르기가
 * 한 컴포넌트에 묶여 있어, 상세 모달이 쓰려면 대시보드용 피커까지 딸려왔다.
 *
 * REST 차트는 provider가 밝히는 기준값을 쓰고, eligible 1D 장중 현재가만 로컬
 * Toss stream을 덧댄다. 두 출처가 다르면 headline에서 명시적으로 나눈다.
 */
export type Point = { time: string; open?: number | null; high?: number | null; low?: number | null; close: number; ma20?: number | null; ma60?: number | null; ma120?: number | null; ma200?: number | null };
type ChartPayload = { symbol: string; range: string; interval: string; series: Point[]; freshness?: string; asOf?: string; notice?: string; fallbackReason?: string; provider?: string; liveStatus?: string; liveEligible?: boolean; realtimeEligible?: boolean };
type LiveFrame = { schemaVersion?: number; type?: string; status?: string; provider?: string; symbol?: string; market?: string; asOf?: string; price?: number | null; currency?: string; code?: string };
type LiveQuote = { key: string; price: number; asOf: string; provider: string };
type CalendarEvent = { id: string; kind: string; title: string; startsAt: string; status: string; allDay?: boolean; tickers?: string[] };
type SeriesApi = { setData: (rows: unknown[]) => void; update?: (row: unknown) => void; priceToCoordinate?: (price: number) => number | null };
type ChartApi = {
  addSeries: (definition: unknown, options?: object) => SeriesApi;
  timeScale: () => { fitContent: () => void; timeToCoordinate?: (time: unknown) => number | null };
  subscribeCrosshairMove: (handler: (param: CrosshairParam) => void) => void;
  /** 키보드로 고른 봉에 십자선을 얹는다 — 눈으로 보는 키보드 사용자도 툴팁을 본다. */
  setCrosshairPosition?: (price: number, horzScaleItem: unknown, series: SeriesApi) => void;
  clearCrosshairPosition?: () => void;
  remove: () => void;
};
type CrosshairParam = { point?: { x: number; y: number }; seriesData?: Map<SeriesApi, { time?: unknown; close?: number; value?: number }> };
type LightweightApi = {
  createChart: (target: HTMLElement, options: object) => ChartApi;
  CandlestickSeries: unknown;
  LineSeries: unknown;
  AreaSeries: unknown;
  LineStyle?: { Dotted?: number };
  CrosshairMode?: { Normal?: number };
};

declare global { interface Window { LightweightCharts?: LightweightApi } }

/** 토큰 hex를 연한 rgba로. Lightweight Charts는 canvas에 직접 그려 `color-mix()`를
 *  못 읽는다 — CSS가 아니라 라이브러리가 색을 파싱한다. */
function fadedColor(hex: string, alpha: number): string {
  const match = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return hex;
  const value = parseInt(match[1], 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

// 이평선 계열. 보조선이라 연하고(알파 0.55) 얇게(1px) — 가격 위에 겹쳐도 거슬리지
// 않아야 한다. 범례와 시리즈가 이 표 하나를 읽는다.
export const MA_SERIES = [
  { key: "ma20", label: "20일", token: "--folio-gold", fallback: "#a8842c" },
  { key: "ma60", label: "60일", token: "--folio-chart-1", fallback: "#33506b" },
  { key: "ma120", label: "120일", token: "--folio-chart-3", fallback: "#3f5c39" },
  { key: "ma200", label: "200일", token: "--folio-chart-2", fallback: "#71383f" },
] as const;

const FRESHNESS_KO: Record<string, string> = {
  snapshot: "스냅샷", current: "최신", fresh: "최신", cached: "최근 조회", delayed: "지연", stale: "오래됨", unavailable: "불러올 수 없음", live_bootstrap: "장중 기준",
};
// 1D는 장중(5분봉), 나머지는 일봉이다.
export const RANGES = ["1d", "1m", "3m", "1y", "5y"];
const RANGE_LABELS: Record<string, string> = { "1d": "1D", "1m": "1M", "3m": "3M", "1y": "1Y", "5y": "5Y" };
const intervalFor = (value: string) => (value === "1d" ? "5m" : "1d");

export function isIndexLike(symbol: string): boolean {
  return symbol.startsWith("^") || symbol.includes("=");
}

export function realtimeStatusForBootstrap(payload: Pick<ChartPayload, "liveStatus" | "series" | "realtimeEligible"> | null | undefined, range: string): string {
  if (range !== "1d") return "delayed";
  switch (payload?.liveStatus) {
    case "available": return payload.series.length > 0 ? (payload.realtimeEligible === false ? "rest" : "pending") : "delayed";
    case "not_requested": return "delayed";
    case "unsupported": return "unsupported";
    case "unavailable": return "unavailable";
    default: return "delayed";
  }
}

export function shouldOpenRealtime(payload: Pick<ChartPayload, "liveEligible" | "realtimeEligible" | "liveStatus" | "series"> | null | undefined, range: string, visible: boolean): boolean {
  return visible && range === "1d" && payload?.liveEligible === true && payload.realtimeEligible !== false && payload.liveStatus === "available" && payload.series.length > 0;
}

export function liveWallClockBucket(asOf: string, market = "US"): string {
  const instant = new Date(asOf);
  if (Number.isNaN(instant.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: market === "KR" ? "Asia/Seoul" : "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(instant).reduce<Record<string, string>>((result, part) => ({ ...result, [part.type]: part.value }), {});
  const minute = Math.floor(Number(parts.minute || 0) / 5) * 5;
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${String(minute).padStart(2, "0")}:00`;
}

export function liveCandleUpdate(rows: Point[], frame: LiveFrame): Point[] {
  if (frame.type !== "tick" || frame.status !== "live" || typeof frame.price !== "number" || !Number.isFinite(frame.price) || !frame.asOf) return rows;
  const bucket = liveWallClockBucket(frame.asOf, frame.market);
  if (!bucket) return rows;
  const previous = rows[rows.length - 1];
  if (!previous) return rows;
  if (Number(chartTime(bucket, true)) < Number(chartTime(previous.time, true))) return rows;
  if (chartTime(previous.time, true) === chartTime(bucket, true)) {
    return [...rows.slice(0, -1), { ...previous, high: Math.max(previous.high ?? previous.close, frame.price), low: Math.min(previous.low ?? previous.close, frame.price), close: frame.price }];
  }
  return [...rows, { time: bucket, open: frame.price, high: frame.price, low: frame.price, close: frame.price }];
}

export function providerInstantMs(asOf: string): number | null {
  const value = Date.parse(asOf);
  return Number.isFinite(value) ? value : null;
}

export function shouldAcceptProviderInstant(previous: number | null, asOf: string): boolean {
  const next = providerInstantMs(asOf);
  return next !== null && (previous === null || next > previous);
}

export function applyLiveTick(rows: Point[], previousInstant: number | null, frame: LiveFrame): { rows: Point[]; instant: number | null } {
  const instant = providerInstantMs(frame.asOf || "");
  if (instant === null || !shouldAcceptProviderInstant(previousInstant, frame.asOf || "")) return { rows, instant: previousInstant };
  const updated = liveCandleUpdate(rows, frame);
  return updated === rows ? { rows, instant: previousInstant } : { rows: updated, instant };
}

export function providerCopy(restProvider?: string, liveProvider?: string): string | null {
  const rest = restProvider === "toss_open_api" ? "Toss Open API" : restProvider === "yfinance" ? "yfinance" : "";
  const live = liveProvider === "toss_open_api" ? "Toss Open API" : liveProvider === "yfinance" ? "yfinance" : "";
  if (live && rest && live !== rest) return `현재가 ${live} · 차트 ${rest}`;
  return live || rest || null;
}

export function rowsForChartRedraw(restRows: Point[], liveRows: Point[], hasNewRestPayload: boolean): Point[] {
  return hasNewRestPayload || liveRows.length === 0 ? restRows : liveRows;
}

/** 5분봉 시각을 Lightweight Charts가 받는 형태로 바꾼다.
 *
 *  분봉은 거래소 현지 시각 문자열(`2026-08-07T09:30:00-04:00`)로 들어오는데,
 *  라이브러리가 받는 것은 `yyyy-mm-dd` 문자열 아니면 UTC epoch 초다. ISO
 *  문자열을 그대로 넘기면 예외 없이 통과한 뒤 하루로 접혀 78개 봉이 한 점에
 *  겹친다(실측: 19개 봉을 넣었더니 보이는 범위의 from과 to가 같았다).
 *
 *  epoch를 그대로 쓰면 이번엔 축이 UTC로 그려져 미국장 09:30이 13:30으로
 *  보인다. 그래서 벽시계 값을 UTC인 척 넘긴다 — `public/briefing-visuals.js`의
 *  `intradayChartTime()`이 같은 이유로 같은 일을 한다.
 */
function intradayTime(rawTime: string): number {
  const match = String(rawTime || "").match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!match) return NaN;
  const wallClock = Date.UTC(
    Number(match[1]), Number(match[2]) - 1, Number(match[3]),
    Number(match[4]), Number(match[5]), Number(match[6] || 0),
  );
  return Number.isFinite(wallClock) ? Math.floor(wallClock / 1000) : NaN;
}

/** 일봉은 `yyyy-mm-dd` 그대로, 분봉은 epoch 초로. */
export function chartTime(rawTime: string, intraday: boolean): string | number {
  if (!intraday) return String(rawTime || "");
  const stamp = intradayTime(rawTime);
  return Number.isFinite(stamp) ? stamp : String(rawTime || "");
}

function nextEventLabel(event: CalendarEvent): string {
  const date = new Date(event.startsAt);
  const day = Number.isNaN(date.getTime())
    ? event.startsAt.slice(0, 10)
    : date.toLocaleDateString("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric", weekday: "short" });
  const kind = KIND_KO[event.kind] || event.kind;
  const tag = event.kind === "earnings" ? timeLabelKST(event) : "";
  return `${day} ${kind} 예정${tag && tag !== "종일" ? ` · ${tag}` : ""}`;
}

type MarketChartFigureProps = {
  symbol: string;
  label?: string;
  range: string;
  style: "candle" | "line";
  onRange: (value: string) => void;
  onStyle: (value: "candle" | "line") => void;
  showEvent?: boolean;
};

export function chartSessionKey(symbol: string, range: string): string {
  return `${symbol}|${range}`;
}

/** A key change unmounts the old canvas and its payload in the same commit.
 * This is stricter than clearing state from an effect, which runs after paint. */
export function MarketChartFigure(props: MarketChartFigureProps) {
  // 범위 전환은 REST/canvas session을 바꾸지만, 사용자가 고른 이평선 보조선은
  // 차트 기간보다 한 단계 위의 화면 선택이라 wrapper가 보존한다.
  const [showMa, setShowMa] = useState(false);
  return <MarketChartFigureSession key={chartSessionKey(props.symbol, props.range)} {...props} showMa={showMa} onShowMa={() => setShowMa((value) => !value)} />;
}

function MarketChartFigureSession({
  symbol, label, range, style, onRange, onStyle, showEvent = true, showMa, onShowMa,
}: MarketChartFigureProps & { showMa: boolean; onShowMa: () => void }) {
  const [payload, setPayload] = useState<ChartPayload | null>(null);
  const [nextEvent, setNextEvent] = useState<CalendarEvent | null>(null);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(() => typeof document === "undefined" || !document.hidden);
  const [bootstrapKey, setBootstrapKey] = useState("");
  const [liveStatus, setLiveStatus] = useState("loading");
  const [liveQuote, setLiveQuote] = useState<LiveQuote | null>(null);
  const targetRef = useRef<HTMLDivElement | null>(null);
  const primarySeriesRef = useRef<SeriesApi | null>(null);
  const currentRowsRef = useRef<Point[]>([]);
  const renderedPayloadRef = useRef<ChartPayload | null>(null);
  const lastProviderInstantRef = useRef<{ key: string; value: number } | null>(null);
  const bootstrapRequestRef = useRef(0);
  const styleRef = useRef(style);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chartRef = useRef<ChartApi | null>(null);
  // 차트 안에서 툴팁을 봉 하나에 붙여 보여 주는 함수. 그리기 효과가 만든다.
  const showBarTipRef = useRef<((row: Point) => void) | null>(null);
  // 키보드로 띄운 툴팁은 마우스가 십자선을 움직이기 전까지 십자선 콜백이 지우지 않는다.
  const keyboardTipRef = useRef(false);
  // 키보드로 고른 봉. 그림은 canvas라 화면 읽기 프로그램이 못 읽으므로 판독값을 따로 알린다.
  const [cursor, setCursor] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => { styleRef.current = style; }, [style]);

  useEffect(() => {
    const update = () => {
      const nextVisible = !document.hidden;
      if (!nextVisible) {
        // Effect cleanup runs after render. Invalidate/close here so a hidden
        // tab cannot retain an accepted bootstrap or reconnect before its
        // return-to-visible REST reconciliation finishes.
        bootstrapRequestRef.current += 1;
        if (reconnectRef.current !== null) clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
        const socket = socketRef.current;
        socketRef.current = null;
        if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
        setBootstrapKey("");
        setLiveQuote(null);
        currentRowsRef.current = [];
        renderedPayloadRef.current = null;
        lastProviderInstantRef.current = null;
        setPayload(null);
        setLiveStatus(range === "1d" ? "loading" : "delayed");
      }
      setVisible(nextVisible);
    };
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, [range]);

  useEffect(() => {
    let alive = true;
    const requestKey = `${symbol}|${range}`;
    // 숨김 전환은 REST를 다시 읽거나 화면 상태를 덮어쓰지 않고 소켓 정리만
    // 맡긴다. 다시 보일 때의 effect가 reconciliation bootstrap을 수행한다.
    if (!visible) return () => { alive = false; };
    const requestGeneration = ++bootstrapRequestRef.current;
    setBootstrapKey("");
    setError("");
    // 새 bootstrap의 제목·기간 아래에 직전 소켓 가격을 남기지 않는다. REST는
    // 숨김 상태에서는 갱신하지 않아야 하므로, 돌아왔을 때에만 다시 맞춘다.
    setLiveQuote(null);
    lastProviderInstantRef.current = null;
    setLiveStatus(range === "1d" ? "loading" : "delayed");
    // **종목이 바뀔 때만 비운다.** 그리기 효과는 range를 보지 않으므로 기간만 바꾼
    // 동안에는 옛 계열이 그대로 남아 있다가 새 자료로 교체된다 — 비우면 캐시가 없는
    // 첫 전환에서 200ms쯤 빈 판이 번쩍인다. 반대로 다른 종목의 계열이 새 제목 아래
    // 남아 있는 것은 잘못된 정보다. 무대는 고정 높이라 어느 쪽도 레이아웃이 튀지 않는다.
    setPayload((prev) => (prev && prev.symbol === symbol ? prev : null));
    getJson<ChartPayload>(`/api/market/chart?symbol=${encodeURIComponent(symbol)}&range=${range}&interval=${intervalFor(range)}`)
      .then((row) => {
        if (!alive || bootstrapRequestRef.current !== requestGeneration) return;
        // Every accepted bootstrap, including an empty response, is the new
        // snapshot authority. Never let a previous symbol's rows/tick clock
        // seed a socket that has no initial REST candle.
        currentRowsRef.current = row.series;
        renderedPayloadRef.current = row;
        lastProviderInstantRef.current = null;
        setPayload(row);
        setBootstrapKey(requestKey);
        setLiveStatus(realtimeStatusForBootstrap(row, range));
      })
      .catch((err) => {
        if (!alive || bootstrapRequestRef.current !== requestGeneration) return;
        setError(err instanceof Error ? err.message : "차트를 불러오지 못했습니다.");
        setLiveStatus("unavailable");
      });
    return () => { alive = false; };
  }, [symbol, range, visible]);

  useEffect(() => {
    let alive = true;
    setNextEvent(null);
    if (!showEvent || !symbol || isIndexLike(symbol)) return undefined;
    const start = new Date();
    const end = new Date(start.getTime() + 90 * 24 * 60 * 60 * 1000);
    getJson<{ events?: CalendarEvent[] }>(
      `/api/market-calendar?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&ticker=${encodeURIComponent(symbol)}&limit=20`,
    )
      .then((row) => {
        if (!alive) return;
        const upcoming = (row.events || [])
          .filter((event) => ["earnings", "dividend", "filing"].includes(event.kind))
          .sort((a, b) => a.startsAt.localeCompare(b.startsAt));
        setNextEvent(upcoming[0] || null);
      })
      .catch(() => undefined);
    return () => { alive = false; };
  }, [symbol, showEvent]);

  // 테마가 바뀌면 토큰 색으로 다시 그린다.
  const [themeKey, setThemeKey] = useState(0);
  useEffect(() => {
    const observer = new MutationObserver(() => setThemeKey((value) => value + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const target = targetRef.current;
    const library = window.LightweightCharts;
    if (!target || !library || !payload) return undefined;
    if (!payload.series.length) {
      primarySeriesRef.current = null;
      target.innerHTML = "";
      return undefined;
    }
    target.innerHTML = "";
    // 브리핑 본문 차트(public/briefing-visuals.js)와 같은 형식으로 맞춘다.
    const tokens = getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string) => tokens.getPropertyValue(name).trim() || fallback;
    const upColor = token("--folio-green", "#3b6d11");
    const downColor = token("--folio-burgundy", "#8a1024");
    // 스타일·테마·이평선은 같은 REST payload를 다시 그릴 뿐이다. 그때 REST
    // 원본을 재사용하면 직전에 `series.update()`한 live 봉이 사라진다. payload
    // 객체가 실제로 바뀐 bootstrap일 때만 authoritative REST rows로 되돌린다.
    const hasNewRestPayload = renderedPayloadRef.current !== payload;
    const rows = rowsForChartRedraw(payload.series, currentRowsRef.current, hasNewRestPayload);
    if (hasNewRestPayload) renderedPayloadRef.current = payload;
    currentRowsRef.current = rows;
    const intraday = payload.interval === "5m";
    const positive = rows.length > 1 ? rows[rows.length - 1].close >= rows[0].close : true;
    const lineColor = positive ? upColor : downColor;
    const chart = library.createChart(target, {
      autoSize: true,
      height: 360,
      width: target.clientWidth || 0,
      layout: { background: { type: "solid", color: token("--folio-surface-clean", "#ffffff") }, textColor: token("--folio-ink-muted", "#44505f"), attributionLogo: true },
      grid: { vertLines: { visible: false }, horzLines: { color: token("--folio-border", "#dde2e9"), style: library.LineStyle?.Dotted ?? 1 } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      // 분봉은 축이 날짜만 찍으면 하루치가 같은 라벨로 반복된다. 시각을 보여준다.
      timeScale: { borderVisible: false, rightOffset: 1, barSpacing: 8, minBarSpacing: 2, timeVisible: intraday, secondsVisible: false },
      localization: { locale: "ko-KR", dateFormat: "yyyy-MM-dd" },
      crosshair: { mode: library.CrosshairMode?.Normal ?? 0 },
      handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: false, mouseWheel: false, pinch: true },
    });
    const ohlcRows = rows.filter((row) => row.open != null && row.high != null && row.low != null);
    const useCandle = style === "candle" && ohlcRows.length > 0;
    const series = useCandle
      ? chart.addSeries(library.CandlestickSeries, { upColor, downColor, wickUpColor: upColor, wickDownColor: downColor, borderVisible: false })
      : chart.addSeries(library.AreaSeries, { lineColor, topColor: `${lineColor}38`, bottomColor: `${lineColor}05`, lineWidth: 3, priceLineVisible: false, lastValueVisible: true });
    series.setData(useCandle
      ? ohlcRows.map((row) => ({ time: chartTime(row.time, intraday), open: row.open, high: row.high, low: row.low, close: row.close }))
      : rows.map((row) => ({ time: chartTime(row.time, intraday), value: row.close })));
    primarySeriesRef.current = series;
    chartRef.current = chart;

    // 이동평균 — 서버가 워밍업 구간까지 받아 계산해 두므로 구간 안에서 선이 끊기지
    // 않는다. 분봉에는 없다(서버가 일봉에만 붙인다). 창을 못 채운 계열(짧은 상장
    // 이력의 200일선)은 건너뛴다.
    if (showMa && !intraday) {
      for (const def of MA_SERIES) {
        const maRows = rows
          .filter((row) => row[def.key] != null)
          .map((row) => ({ time: chartTime(row.time, intraday), value: row[def.key] as number }));
        if (maRows.length < 2) continue;
        chart.addSeries(library.LineSeries, {
          color: fadedColor(token(def.token, def.fallback), 0.55),
          lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
          crosshairMarkerVisible: false,
        }).setData(maRows);
      }
    }

    // 조회 키도 라이브러리가 돌려주는 값과 같은 형태여야 한다. 원본 ISO 문자열로
    // 담아두면 분봉에서 crosshair가 무엇도 못 찾아 툴팁이 빈 채로 뜬다.
    const closeByTime = new Map(rows.map((row, index) => [String(chartTime(row.time, intraday)), { close: row.close, previous: index > 0 ? rows[index - 1].close : null }]));
    const tooltip = document.createElement("div");
    tooltip.className = "market-chart-tooltip";
    tooltip.hidden = true;
    target.appendChild(tooltip);
    const renderTooltip = (point: { x: number; y: number }, key: string, fallbackClose: number | null) => {
      const stage = target.getBoundingClientRect();
      const source = closeByTime.get(key);
      const close = source?.close ?? fallbackClose;
      const previous = source?.previous ?? null;
      const change = close != null && previous != null ? close - previous : null;
      const changePctValue = change != null && previous ? (change / previous) * 100 : null;
      const direction = change == null || change >= 0 ? "up" : "down";
      const priceText = close == null ? "가격 없음" : close.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const changeText = change == null || changePctValue == null
        ? (intraday ? "직전 봉 대비 없음" : "전일 대비 없음")
        : `${change >= 0 ? "+" : ""}${change.toLocaleString(undefined, { maximumFractionDigits: 2 })} (${changePctValue >= 0 ? "+" : ""}${changePctValue.toFixed(2)}%)`;
      tooltip.innerHTML = "";
      const dateNode = document.createElement("div");
      dateNode.className = "market-chart-tooltip__date";
      // 분봉 키는 epoch 초다. 그대로 찍으면 `1786... `이 뜬다.
      dateNode.textContent = intraday
        ? new Date(Number(key) * 1000).toISOString().slice(11, 16)
        : key;
      const priceNode = document.createElement("div");
      priceNode.className = "market-chart-tooltip__price";
      priceNode.textContent = priceText;
      const changeNode = document.createElement("div");
      changeNode.className = "market-chart-tooltip__change";
      changeNode.dataset.direction = direction;
      changeNode.textContent = changeText;
      tooltip.append(dateNode, priceNode, changeNode);
      const width = tooltip.offsetWidth || 150;
      const height = tooltip.offsetHeight || 76;
      const left = Math.min(Math.max(8, point.x + 14), Math.max(8, stage.width - width - 8));
      const top = Math.min(Math.max(8, point.y - height - 12), Math.max(8, stage.height - height - 8));
      tooltip.style.transform = `translate(${left}px, ${top}px)`;
      tooltip.hidden = false;
    };
    chart.subscribeCrosshairMove((param) => {
      const point = param?.point;
      const seriesPoint = param?.seriesData?.get(series);
      const stage = target.getBoundingClientRect();
      if (!point || !seriesPoint || point.x < 0 || point.y < 0 || point.x > stage.width || point.y > stage.height) {
        // 키보드로 고른 봉의 툴팁은 여기서 지우지 않는다 — 프로그램으로 놓은 십자선은 point가 없다.
        if (!keyboardTipRef.current) tooltip.hidden = true;
        return;
      }
      keyboardTipRef.current = false;
      renderTooltip(point, String(seriesPoint.time), seriesPoint.close ?? seriesPoint.value ?? null);
    });
    showBarTipRef.current = (row: Point) => {
      const time = chartTime(row.time, intraday);
      const x = chart.timeScale().timeToCoordinate?.(time);
      const y = series.priceToCoordinate?.(row.close);
      if (x == null || y == null) return;
      keyboardTipRef.current = true;
      renderTooltip({ x, y }, String(time), row.close);
    };
    chart.timeScale().fitContent();
    return () => {
      primarySeriesRef.current = null;
      chartRef.current = null;
      showBarTipRef.current = null;
      chart.remove();
    };
  }, [payload, themeKey, style, showMa]);

  // 새 자료가 오면 옛 위치는 뜻을 잃는다(봉 수가 달라진다).
  useEffect(() => { setCursor(null); setAnnouncement(""); }, [payload]);

  useEffect(() => {
    const key = `${symbol}|${range}`;
    const close = () => {
      if (reconnectRef.current !== null) clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
    };
    close();
    if (!shouldOpenRealtime(payload, range, visible) || bootstrapKey !== key) {
      if (!visible || bootstrapKey !== key || !payload) return close;
      setLiveStatus(realtimeStatusForBootstrap(payload, range));
      return close;
    }
    let active = true;
    let attempts = 0;
    const connect = () => {
      if (!active || document.hidden || socketRef.current) return;
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(`${protocol}//${window.location.host}/api/market/realtime/chart?symbol=${encodeURIComponent(symbol)}`);
      socketRef.current = socket;
      socket.onopen = () => { if (active && socketRef.current === socket) setLiveStatus("pending"); };
      socket.onmessage = (event) => {
        if (!active || socketRef.current !== socket || bootstrapKey !== key) return;
        let frame: LiveFrame;
        try { frame = JSON.parse(String(event.data)) as LiveFrame; } catch { return; }
        if (frame.symbol && String(frame.symbol).trim().toUpperCase() !== symbol.replace(/\.(KS|KQ)$/i, "").trim().toUpperCase()) return;
        if (frame.type === "status") {
          const status = frame.status || "unavailable";
          if (status === "subscribed") {
            attempts = 0;
            setLiveStatus("pending");
            return;
          }
          if (status === "rejected") {
            setLiveStatus("unsupported");
            close();
            return;
          }
          setLiveStatus(status);
          if (["unsupported", "unavailable"].includes(status)) close();
          return;
        }
        if (frame.type !== "tick" || frame.status !== "live") return;
        const previousInstant = lastProviderInstantRef.current?.key === key ? lastProviderInstantRef.current.value : null;
        const applied = applyLiveTick(currentRowsRef.current, previousInstant, frame);
        if (applied.rows === currentRowsRef.current || applied.instant === null) return;
        currentRowsRef.current = applied.rows;
        lastProviderInstantRef.current = { key, value: applied.instant };
        const point = applied.rows[applied.rows.length - 1];
        const primary = primarySeriesRef.current;
        if (primary?.update) {
          const time = chartTime(point.time, true);
          primary.update(styleRef.current === "candle" && point.open != null && point.high != null && point.low != null
            ? { time, open: point.open, high: point.high, low: point.low, close: point.close }
            : { time, value: point.close });
        }
        setLiveQuote({ key, price: frame.price as number, asOf: frame.asOf || "", provider: frame.provider || "toss_open_api" });
        attempts = 0;
        setLiveStatus("live");
      };
      socket.onclose = () => {
        if (!active || socketRef.current !== socket) return;
        socketRef.current = null;
        if (attempts >= 3 || document.hidden) { setLiveStatus("unavailable"); return; }
        attempts += 1; setLiveStatus("reconnecting");
        reconnectRef.current = setTimeout(connect, Math.min(4000, 500 * (2 ** attempts)));
      };
      socket.onerror = () => socket.close();
    };
    connect();
    return () => { active = false; close(); };
  }, [symbol, range, visible, bootstrapKey, payload]);

  const renderKey = `${symbol}|${range}`;
  const activeLiveQuote = liveQuote?.key === renderKey ? liveQuote : null;
  const series = payload?.series || [];
  const lastClose = activeLiveQuote?.price ?? (series.length ? series[series.length - 1].close : null);
  // 일봉이면 직전 봉이 전일이지만, 5분봉에서 직전 봉은 5분 전이라 등락률이 늘
  // 0%에 가깝게 나온다. 1D의 등락률은 그 세션 시초가 대비여야 하고, 차트 색을
  // 정하는 기준(`rows[0].close`)과도 그래야 어긋나지 않는다.
  const intradayHeadline = payload?.interval === "5m";
  const baseClose = series.length > 1
    ? (intradayHeadline ? series[0].close : series[series.length - 2].close)
    : null;
  const changePct = lastClose != null && baseClose ? ((lastClose - baseClose) / baseClose) * 100 : null;
  const freshnessLabel = FRESHNESS_KO[payload?.freshness || ""] || (payload ? "차트 기준" : "불러오는 중");
  const liveLabel: Record<string, string> = { live: "실시간", rest: "Toss 1분봉", reconnecting: "재연결 중", delayed: "지연", unsupported: "Toss 분봉 미지원", unavailable: "사용할 수 없음", pending: "연결 대기", loading: "불러오는 중" };
  const sourceCopy = providerCopy(payload?.provider, activeLiveQuote?.provider);
  const asOf = activeLiveQuote?.asOf || payload?.asOf || "";

  // 텍스트 대체는 서버가 준 봉(`payload.series`)을 기준으로 한다. 장중 틱은 마지막 봉을
  // 덮어쓰거나 한 봉을 더하는데, 그건 위 헤드라인의 현재가가 이미 말한다.
  const libraryReady = typeof window !== "undefined" && Boolean(window.LightweightCharts);
  const chartName = label || symbol;
  const candleView = isCandleView(style, series);
  const summaryLabel = useMemo(
    () => chartSummaryLabel({ name: chartName, rangeLabel: RANGE_LABELS[range] || range, style, rows: series, intraday: intradayHeadline }),
    [chartName, range, style, series, intradayHeadline],
  );
  const tableColumns = candleView
    ? [intradayHeadline ? "시각" : "날짜", "시가", "고가", "저가", "종가"]
    : [intradayHeadline ? "시각" : "날짜", "종가"];
  const tableRows = useMemo(() => {
    const fmt = (value: number | null | undefined) => (value == null ? "-" : value.toLocaleString("ko-KR", { maximumFractionDigits: 2 }));
    return series.map((row) => {
      const when = barTimeText(row.time, intradayHeadline);
      return candleView ? [when, fmt(row.open), fmt(row.high), fmt(row.low), fmt(row.close)] : [when, fmt(row.close)];
    });
  }, [series, candleView, intradayHeadline]);

  // 키보드는 **그려진 봉**을 따라간다(장중 틱이 더한 봉 포함). 이름과 표는 서버 봉 기준이다.
  const drawnRows = () => (currentRowsRef.current.length ? currentRowsRef.current : series);
  const moveCursor = (index: number) => {
    const rows = drawnRows();
    const row = rows[index];
    if (!row) return;
    setCursor(index);
    setAnnouncement(barReadout({ rows, index, intraday: intradayHeadline, candle: candleView }));
    // 십자선과 툴팁은 눈으로 보는 키보드 사용자를 위한 것이다. 라이브러리가 못 받으면 조용히 넘어간다.
    chartRef.current?.setCrosshairPosition?.(row.close, chartTime(row.time, intradayHeadline), primarySeriesRef.current as SeriesApi);
    showBarTipRef.current?.(row);
  };
  const clearCursor = () => {
    chartRef.current?.clearCrosshairPosition?.();
    keyboardTipRef.current = false;
    const tip = targetRef.current?.querySelector<HTMLElement>(".market-chart-tooltip");
    if (tip) tip.hidden = true;
    setCursor(null);
  };
  const onStageKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      if (cursor === null) return;
      clearCursor();
      setAnnouncement("");
      event.preventDefault();
      return;
    }
    const next = nextBarIndex({ key: event.key, current: cursor, length: drawnRows().length });
    if (next === null) return;
    event.preventDefault();
    moveCursor(next);
  };
  const onStageBlur = () => {
    if (cursor !== null) clearCursor();
  };

  return (
    <>
      <div className="chart-headline">
        <div className="chart-quote">
          <span className="chart-quote__name">{label || symbol}</span>
          <div className="chart-quote__value">
            {lastClose != null ? <b>{lastClose.toLocaleString(undefined, { maximumFractionDigits: 2 })}</b> : null}
            {changePct != null ? (
              <span className={changePct > 0 ? "up" : changePct < 0 ? "down" : "flat"}>
                {changePct > 0 ? "▲" : changePct < 0 ? "▼" : "—"} {changePct > 0 ? "+" : ""}{changePct.toFixed(1)}%
              </span>
            ) : null}
          </div>
          <small>{freshnessLabel}{asOf ? ` · ${asOf} 기준` : ""}</small>
          <span className="chip chart-live-status" aria-live="polite">{liveLabel[liveStatus] || "지연"}</span>
          {sourceCopy ? <small className="chart-provider">출처 {sourceCopy}</small> : null}
        </div>
        <div className="cockpit-chart-controls">
          {range !== "1d" && (
            // 이평선은 유형·기간보다 한 단계 아래의 보조 컨트롤이다 — 작은 텍스트
            // 버튼(btn--sm btn--text)으로 낮추고, 범례는 버튼 밖(차트 위 오른쪽)에 둔다.
            <button
              type="button"
              className="btn btn--sm btn--text chart-ma-toggle"
              aria-pressed={showMa}
              onClick={onShowMa}
            >
              이평선
            </button>
          )}
          <div className="segment" role="group" aria-label="차트 유형">
            <button type="button" aria-pressed={style === "line"} onClick={() => onStyle("line")}>라인</button>
            <button type="button" aria-pressed={style === "candle"} onClick={() => onStyle("candle")}>캔들</button>
          </div>
          <div className="segment" role="group" aria-label="차트 기간">
            {RANGES.map((value) => (
              <button type="button" aria-pressed={range === value} onClick={() => onRange(value)} key={value}>
                {RANGE_LABELS[value] || value}
              </button>
            ))}
          </div>
        </div>
      </div>
      {error && <p className="react-dashboard-error">{error}</p>}
      {showMa && range !== "1d" && (
        <div className="chart-ma-legend" aria-label="이동평균선 범례">
          {MA_SERIES.map((def) => (
            <span key={def.key}><i data-ma={def.key} aria-hidden="true" />{def.label}</span>
          ))}
        </div>
      )}
      <div
        className="cockpit-chart-stage"
        ref={targetRef}
        // 그림은 canvas라 읽을 것이 없다. 이름과 방향키 판독을 붙인다.
        // role="img"가 아니라 group인 이유: 이 무대 안에는 TradingView 출처 링크(`attributionLogo`,
        // 라이선스가 요구해 뺄 수 없다)가 있고, img는 자손을 모두 숨겨 그 링크를 화면 읽기
        // 프로그램에서 지운다(axe nested-interactive). 라이브러리가 없으면 그림이 아니므로
        // 아무것도 주지 않고 아래 안내 문구를 그대로 읽게 한다.
        {...(libraryReady && series.length > 0
          ? { role: "group", "aria-roledescription": "차트", "aria-label": summaryLabel, tabIndex: 0, onKeyDown: onStageKeyDown, onBlur: onStageBlur }
          : {})}
      >
        {!libraryReady && <p>차트 라이브러리를 사용할 수 없습니다.</p>}
      </div>
      <p className="sr-only" role="status">{announcement}</p>
      <ChartDataTable title={`${chartName} 가격`} unit="봉" columns={tableColumns} rows={tableRows} />
      {showEvent && nextEvent && (
        <p className="chart-next">
          <span className={`chip certainty-badge--${nextEvent.status}`}>{STATUS_KO[nextEvent.status] || nextEvent.status}</span>
          다음 일정 — <b>{nextEventLabel(nextEvent)}</b>
          <small>시장 캘린더 연동</small>
        </p>
      )}
      {payload?.notice ? <div className="cockpit-chart-foot"><small>{payload.notice}</small></div> : null}
    </>
  );
}
