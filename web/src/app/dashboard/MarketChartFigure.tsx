import { useEffect, useRef, useState } from "react";
import { getJson } from "../../api";
import { KIND_KO, STATUS_KO, timeLabelKST } from "./MarketCalendar";

/** 네이티브 시장 차트의 **그림 한 장**.
 *
 * 종목 선택·설정 저장·패널 제목은 이 안에 없다 — 대시보드는 그것들을 자기가 갖고,
 * 워치리스트 상세는 종목이 이미 정해져 있어 필요가 없다. 예전에는 그리기와 고르기가
 * 한 컴포넌트에 묶여 있어, 상세 모달이 쓰려면 대시보드용 피커까지 딸려왔다.
 *
 * 시세는 yfinance 지연값이다. TradingView 위젯이 주던 준실시간·지표를 잃는 대신
 * 앱 토큰을 따르고 iframe이 없어진다 — freshness 라벨로 지연을 밝히는 기존 방식을
 * 그대로 쓴다(계획 §11 5-A-3의 트레이드오프).
 */
type Point = { time: string; open?: number | null; high?: number | null; low?: number | null; close: number; ma20?: number | null; ma60?: number | null; ma120?: number | null; ma200?: number | null };
type ChartPayload = { symbol: string; range: string; interval: string; series: Point[]; freshness?: string; asOf?: string; notice?: string; fallbackReason?: string };
type CalendarEvent = { id: string; kind: string; title: string; startsAt: string; status: string; allDay?: boolean; tickers?: string[] };
type SeriesApi = { setData: (rows: unknown[]) => void };
type ChartApi = {
  addSeries: (definition: unknown, options?: object) => SeriesApi;
  timeScale: () => { fitContent: () => void };
  subscribeCrosshairMove: (handler: (param: CrosshairParam) => void) => void;
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
  snapshot: "스냅샷", current: "최신", fresh: "최신", cached: "최근 조회", delayed: "지연", stale: "오래됨", unavailable: "불러올 수 없음",
};
// 1D는 장중(5분봉), 나머지는 일봉이다.
export const RANGES = ["1d", "1m", "3m", "1y", "5y"];
const RANGE_LABELS: Record<string, string> = { "1d": "1D", "1m": "1M", "3m": "3M", "1y": "1Y", "5y": "5Y" };
const intervalFor = (value: string) => (value === "1d" ? "5m" : "1d");

export function isIndexLike(symbol: string): boolean {
  return symbol.startsWith("^") || symbol.includes("=");
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

export function MarketChartFigure({
  symbol, label, range, style, onRange, onStyle, showEvent = true,
}: {
  symbol: string;
  label?: string;
  range: string;
  style: "candle" | "line";
  onRange: (value: string) => void;
  onStyle: (value: "candle" | "line") => void;
  showEvent?: boolean;
}) {
  const [payload, setPayload] = useState<ChartPayload | null>(null);
  // 이동평균 토글. 저장하지 않는다 — 잠깐 겹쳐 보는 보조선이지 설정이 아니다.
  const [showMa, setShowMa] = useState(false);
  const [nextEvent, setNextEvent] = useState<CalendarEvent | null>(null);
  const [error, setError] = useState("");
  const targetRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    setError("");
    // **종목이 바뀔 때만 비운다.** 그리기 효과는 range를 보지 않으므로 기간만 바꾼
    // 동안에는 옛 계열이 그대로 남아 있다가 새 자료로 교체된다 — 비우면 캐시가 없는
    // 첫 전환에서 200ms쯤 빈 판이 번쩍인다. 반대로 다른 종목의 계열이 새 제목 아래
    // 남아 있는 것은 잘못된 정보다. 무대는 고정 높이라 어느 쪽도 레이아웃이 튀지 않는다.
    setPayload((prev) => (prev && prev.symbol === symbol ? prev : null));
    getJson<ChartPayload>(`/api/market/chart?symbol=${encodeURIComponent(symbol)}&range=${range}&interval=${intervalFor(range)}`)
      .then((row) => { if (alive) setPayload(row); })
      .catch((err) => { if (alive) setError(err instanceof Error ? err.message : "차트를 불러오지 못했습니다."); });
    return () => { alive = false; };
  }, [symbol, range]);

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
    if (!target || !library || !payload?.series?.length) return undefined;
    target.innerHTML = "";
    // 브리핑 본문 차트(public/briefing-visuals.js)와 같은 형식으로 맞춘다.
    const tokens = getComputedStyle(document.documentElement);
    const token = (name: string, fallback: string) => tokens.getPropertyValue(name).trim() || fallback;
    const upColor = token("--folio-green", "#3b6d11");
    const downColor = token("--folio-burgundy", "#8a1024");
    const rows = payload.series;
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
    chart.subscribeCrosshairMove((param) => {
      const point = param?.point;
      const seriesPoint = param?.seriesData?.get(series);
      const stage = target.getBoundingClientRect();
      if (!point || !seriesPoint || point.x < 0 || point.y < 0 || point.x > stage.width || point.y > stage.height) {
        tooltip.hidden = true;
        return;
      }
      const key = String(seriesPoint.time);
      const source = closeByTime.get(key);
      const close = source?.close ?? seriesPoint.close ?? seriesPoint.value ?? null;
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
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [payload, themeKey, style, showMa]);

  const series = payload?.series || [];
  const lastClose = series.length ? series[series.length - 1].close : null;
  // 일봉이면 직전 봉이 전일이지만, 5분봉에서 직전 봉은 5분 전이라 등락률이 늘
  // 0%에 가깝게 나온다. 1D의 등락률은 그 세션 시초가 대비여야 하고, 차트 색을
  // 정하는 기준(`rows[0].close`)과도 그래야 어긋나지 않는다.
  const intradayHeadline = payload?.interval === "5m";
  const baseClose = series.length > 1
    ? (intradayHeadline ? series[0].close : series[series.length - 2].close)
    : null;
  const changePct = lastClose != null && baseClose ? ((lastClose - baseClose) / baseClose) * 100 : null;
  const freshnessLabel = FRESHNESS_KO[payload?.freshness || ""] || (payload ? payload.freshness : "불러오는 중");

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
          <small>{freshnessLabel}{payload?.asOf ? ` · ${payload.asOf} 기준` : ""}</small>
        </div>
        <div className="cockpit-chart-controls">
          {range !== "1d" && (
            // 이평선은 유형·기간보다 한 단계 아래의 보조 컨트롤이다 — 작은 텍스트
            // 버튼(btn--sm btn--text)으로 낮추고, 범례는 버튼 밖(차트 위 오른쪽)에 둔다.
            <button
              type="button"
              className="btn btn--sm btn--text chart-ma-toggle"
              aria-pressed={showMa}
              onClick={() => setShowMa((value) => !value)}
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
      <div className="cockpit-chart-stage" ref={targetRef}>
        {!window.LightweightCharts && <p>차트 라이브러리를 사용할 수 없습니다.</p>}
      </div>
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
