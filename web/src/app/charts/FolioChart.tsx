import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";

import { ChartDataTable } from "./ChartDataTable";
import { nextPointIndex } from "./chartA11y";
import { captureInteractionState, restoreInteractionState } from "./chartInteractionState";
import { subscribeThemeChange, themeFromDocument } from "./chartTheme";
import { getEcharts, type EChartsCoreOption, type EChartsType } from "./echarts";

/** 공통 차트 층 — ECharts를 화면 어디서나 같은 규칙으로 올린다.
 *
 *  화면은 데이터와 의미를 선언하고 option은 **차트 종류별 컴포넌트가** 만든다(계획 §3). 이 컴포넌트가
 *  맡는 것은 네 가지다:
 *
 *  1. **수명** — 마운트·해제, 컨테이너 폭 변화(`ResizeObserver`), 숨은 탭·접힌 `<details>`에서 폭 0으로
 *     시작해도 보이는 순간 바로잡기.
 *  2. **테마** — 토큰으로 만든 테마를 `chart.setTheme()`으로 갈아 낀다. 인스턴스를 다시 만들지 않으므로 깜빡이지
 *     않는다. 다만 setTheme은 확대 범위·범례 선택을 지우므로(실측) 바꾸기 전후로 읽고 되돌린다.
 *  3. **네 상태** — loading / empty / error / stale을 한 문법으로.
 *  4. **텍스트 대체 계약**(계획 §5.1) — `role="img"` + 필수 `label`, 방향키 지점 이동과 `aria-live` 판독,
 *     같은 숫자의 데이터 표.
 *
 *  `option`은 **메모이즈해서 넘긴다.** 참조가 바뀔 때마다 `notMerge`로 다시 그리므로, 렌더마다 새 객체를
 *  만들면 사용자가 조작한 확대 범위가 매번 초기화된다.
 */
export type ChartState = "loading" | "empty" | "error" | "stale" | "ready";

export interface FolioChartKeyboard {
  /** 방향키로 오갈 수 있는 지점 수. 0이면 키보드 이동은 꺼진다. */
  count: number;
  /** 고른 지점을 눈으로도 보이게 한다(`dispatchAction`의 `showTip`·`highlight` 등). */
  focus: (chart: EChartsType, index: number) => void;
  /** 고른 지점의 판독 문장. `aria-live`로 나간다. */
  readout: (index: number) => string;
  /** Escape·초점 이탈 때 강조를 거둔다. */
  clear?: (chart: EChartsType) => void;
}

export interface FolioChartTable {
  /** 표 영역 이름(`○○ 데이터 표`). 없으면 `label`을 쓴다. */
  title?: string;
  /** 행 하나가 무엇인지(`날짜`, `분기`, `종목`). 표본일 때 요약 줄에 들어간다. */
  unit: string;
  columns: ReadonlyArray<string>;
  rows: ReadonlyArray<ReadonlyArray<string>>;
}

export interface FolioChartProps {
  /** 무엇을 그린 그림인지 말하는 이름. **필수** — 화면 읽기 프로그램이 읽는 유일한 그림 설명이다. */
  label: string;
  option: EChartsCoreOption | null;
  /** 생략하면 option이 있으면 ready, 없으면 loading. */
  state?: ChartState;
  /** 상태 안내 문구. 생략하면 상태별 기본 문구. */
  message?: string;
  height?: number;
  table?: FolioChartTable;
  keyboard?: FolioChartKeyboard;
  /** 차트 이벤트(`click` 등). 마운트 때 한 번 붙는다. */
  events?: Record<string, (params: unknown) => void>;
  className?: string;
}

const DEFAULT_MESSAGE: Record<Exclude<ChartState, "ready">, string> = {
  loading: "차트를 불러오는 중입니다.",
  empty: "표시할 자료가 없습니다.",
  error: "차트를 불러오지 못했습니다.",
  stale: "오래된 자료입니다.",
};

const NO_LIBRARY_MESSAGE = "차트 라이브러리를 사용할 수 없습니다.";

/** 표시 상태를 정한다. 벤더 스크립트가 없으면 그리는 상태는 모두 오류다 — 그릴 수 없다. */
export function resolveChartState(args: { state?: ChartState; hasOption: boolean; libraryReady: boolean }): ChartState {
  const requested = args.state ?? (args.hasOption ? "ready" : "loading");
  if ((requested === "ready" || requested === "stale") && !args.libraryReady) return "error";
  return requested;
}

export function FolioChart({ label, option, state, message, height = 320, table, keyboard, events, className }: FolioChartProps) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const optionRef = useRef(option);
  const eventsRef = useRef(events);
  const staleId = useId();
  const [cursor, setCursor] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const libraryReady = getEcharts() !== null;
  const requested = state ?? (option !== null ? "ready" : "loading");
  const resolved = resolveChartState({ state, hasOption: option !== null, libraryReady });
  const drawn = (resolved === "ready" || resolved === "stale") && option !== null;
  optionRef.current = option;
  eventsRef.current = events;

  // 수명: 그릴 때만 인스턴스를 만든다. 폭이 0이면(숨은 탭·접힌 details) 보일 때까지 기다린다.
  useEffect(() => {
    if (!drawn) return undefined;
    const element = stageRef.current;
    const echarts = getEcharts();
    if (!element || !echarts) return undefined;
    let alive = true;
    let chart: EChartsType | null = null;

    const ensure = () => {
      if (chart || !alive) return;
      if (element.clientWidth <= 0 || element.clientHeight <= 0) return;
      chart = echarts.init(element, themeFromDocument(), { renderer: "svg" });
      chartRef.current = chart;
      for (const [name, handler] of Object.entries(eventsRef.current || {})) chart.on(name, handler as never);
      if (optionRef.current) chart.setOption(optionRef.current, { notMerge: true });
    };
    const observer = typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => { if (chart) chart.resize(); else ensure(); });
    observer?.observe(element);
    ensure();
    // setTheme은 인스턴스를 지키지만 확대 범위·범례 선택을 지운다 — 바꾸기 전에 읽어 두고 바꾼 뒤 되돌린다.
    const unsubscribe = subscribeThemeChange(() => {
      if (!chart) return;
      const kept = captureInteractionState(chart);
      chart.setTheme(themeFromDocument());
      restoreInteractionState(chart, kept);
    });

    return () => {
      alive = false;
      observer?.disconnect();
      unsubscribe();
      chart?.dispose();
      chartRef.current = null;
    };
  }, [drawn]);

  // 자료가 바뀌면 다시 그린다. 사용자가 조작한 상태는 자료가 바뀐 시점에 뜻을 잃으므로 `notMerge`다.
  useEffect(() => {
    if (option && chartRef.current) chartRef.current.setOption(option, { notMerge: true });
    setCursor(null);
    setAnnouncement("");
  }, [option]);

  const clearCursor = () => {
    if (chartRef.current) keyboard?.clear?.(chartRef.current);
    setCursor(null);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!keyboard || keyboard.count <= 0) return;
    if (event.key === "Escape") {
      if (cursor === null) return;
      clearCursor();
      setAnnouncement("");
      event.preventDefault();
      return;
    }
    const next = nextPointIndex({ key: event.key, current: cursor, length: keyboard.count });
    if (next === null) return;
    event.preventDefault();
    setCursor(next);
    setAnnouncement(keyboard.readout(next));
    if (chartRef.current) keyboard.focus(chartRef.current, next);
  };

  const stageStyle: CSSProperties = { height };
  const rootClass = ["folio-chart", className].filter(Boolean).join(" ");
  const keyboardOn = Boolean(keyboard && keyboard.count > 0);
  // 상태 안내: 라이브러리가 없어서 오류가 된 경우는 요청한 문구보다 그 사실을 말한다.
  const stateText = !libraryReady && requested !== resolved
    ? NO_LIBRARY_MESSAGE
    : message || DEFAULT_MESSAGE[resolved === "ready" ? "loading" : resolved];

  return (
    <figure className={rootClass} data-state={resolved}>
      {resolved === "stale" && (
        <p className="folio-chart__stale chip" id={staleId}>{message || DEFAULT_MESSAGE.stale}</p>
      )}
      {drawn ? (
        <div
          // key로 두 자리를 가른다. 같은 div로 재사용되면 ECharts가 컨테이너를 비울 때 React가 관리하던
          // 자식(상태 문구)까지 사라져, 상태가 바뀔 때 React가 없는 노드를 지우려다 화면 전체가 무너진다(실측).
          key="stage"
          className="folio-chart__stage"
          ref={stageRef}
          style={stageStyle}
          // ECharts SVG에는 링크·버튼이 없으므로 role="img"가 맞다(계획 §5.1). 상호작용 자손이
          // 생기는 차트는 img가 그 자손을 숨기므로 group을 써야 한다 — MarketChartFigure 참고.
          role="img"
          aria-label={label}
          aria-describedby={resolved === "stale" ? staleId : undefined}
          tabIndex={keyboardOn ? 0 : undefined}
          onKeyDown={keyboardOn ? onKeyDown : undefined}
          onBlur={keyboardOn ? () => { if (cursor !== null) clearCursor(); } : undefined}
        />
      ) : (
        <div
          key="state"
          className="folio-chart__state"
          style={stageStyle}
          role={resolved === "error" ? "alert" : "status"}
          aria-busy={resolved === "loading" ? true : undefined}
        >
          <span>{stateText}</span>
        </div>
      )}
      <p className="sr-only" role="status">{announcement}</p>
      {drawn && table ? <ChartDataTable title={table.title || label} unit={table.unit} columns={table.columns} rows={table.rows} /> : null}
    </figure>
  );
}
