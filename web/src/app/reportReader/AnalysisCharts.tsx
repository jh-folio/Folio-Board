import { useLayoutEffect, useRef, useState } from "react";

type AnalysisChartsPayload = {
  available?: boolean;
  reason?: string;
  charts?: unknown[];
};

type AnalysisChart = {
  id?: string;
  kind?: string;
  title?: string;
  subtitle?: string;
  years?: string[];
  labels?: string[];
  scenarios?: Array<Record<string, unknown>>;
  series?: Record<string, number[]>;
  currentPrice?: number;
  impliedGrowth?: number;
  terminalShare?: number;
  currency?: string;
  [key: string]: unknown;
};

type Series = {
  key: string;
  label: string;
  values: Array<number | null>;
  kind?: "money" | "percent" | "plain";
};

type ChartTooltip = {
  label: string;
  value: string;
  series?: string;
  x?: number;
  y?: number;
} | null;

const COLORS = [
  "var(--folio-chart-1)",
  "var(--folio-chart-2)",
  "var(--folio-chart-3)",
  "var(--folio-chart-4)",
  "var(--folio-chart-5)",
];

const SERIES_LABELS: Record<string, string> = {
  revenue: "매출",
  grossProfit: "매출총이익",
  operatingIncome: "영업이익",
  netIncome: "순이익",
  operatingCashFlow: "영업활동 현금흐름",
  capitalExpenditure: "설비투자",
  freeCashFlow: "잉여현금흐름",
  grossMargin: "매출총이익률",
  operatingMargin: "영업이익률",
  netMargin: "순이익률",
  fcfMargin: "잉여현금흐름률",
};

function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function arrayValues(value: unknown): Array<number | null> {
  return Array.isArray(value) ? value.map(toNumber) : [];
}

function currencySymbol(currency?: string) {
  const normalized = String(currency || "USD").toUpperCase();
  if (normalized === "KRW" || normalized === "KRX") return "₩";
  if (normalized === "JPY") return "¥";
  if (normalized === "EUR") return "€";
  if (normalized === "GBP") return "£";
  return "$";
}

function formatValue(value: number | null, kind: Series["kind"] = "plain", currency?: string) {
  if (value === null) return "-";
  if (kind === "percent") return `${(value * 100).toFixed(1)}%`;
  if (kind === "money") {
    const symbol = currencySymbol(currency);
    const abs = Math.abs(value);
    if (abs >= 1_000_000_000_000) return `${symbol}${(value / 1_000_000_000_000).toFixed(1)}T`;
    if (abs >= 1_000_000_000) return `${symbol}${(value / 1_000_000_000).toFixed(1)}B`;
    if (abs >= 1_000_000) return `${symbol}${(value / 1_000_000).toFixed(1)}M`;
    return `${symbol}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
  return value.toFixed(Math.abs(value) >= 100 ? 0 : 1);
}

function chartSeries(chart: AnalysisChart): Series[] {
  const keysByKind: Record<string, Array<[string, Series["kind"]]>> = {
    // 마진은 금액과 단위가 달라 오른쪽 축으로 뺀다. 같은 축에 얹으면 그려지지 않는다.
    performance: [["revenue", "money"], ["operatingIncome", "money"], ["netIncome", "money"], ["netMargin", "percent"]],
    quarterly: [["revenue", "money"], ["operatingIncome", "money"], ["netIncome", "money"], ["netMargin", "percent"]],
    cashflow: [["operatingCashFlow", "money"], ["freeCashFlow", "money"], ["capitalExpenditure", "money"]],
    margins: [["grossMargin", "percent"], ["operatingMargin", "percent"], ["netMargin", "percent"]],
  };
  const keys = keysByKind[String(chart.kind || chart.id || "")] || [];
  return keys
    .map(([key, kind]) => ({
      key,
      label: SERIES_LABELS[key] || key,
      values: arrayValues(chart[key]),
      kind,
    }))
    .filter((series) => series.values.some((value) => value !== null));
}

function valueRange(values: Array<number | null>) {
  const valid = values.filter((value): value is number => value !== null);
  if (!valid.length) return { min: 0, max: 1 };
  const min = Math.min(0, ...valid);
  const max = Math.max(0, ...valid);
  if (min === max) return { min: min - 1, max: max + 1 };
  return { min, max };
}

function yFor(value: number, min: number, max: number, top = 16, height = 150) {
  return top + (1 - (value - min) / (max - min)) * height;
}

/** 축 눈금과 오른쪽 비율 축이 들어갈 여백만 남긴다. 폭은 카드에서 재서 넣는다. */
const BARS = { height: 300, top: 20, plot: 212, left: 58, right: 50 };
/** 넓은 화면에서도 이 폭을 넘지 않는다. 4년치 막대가 더 넓어져 봐야 여백만 는다. */
const MAX_WIDTH = 980;
const MIN_WIDTH = 200;

/** 그릴 폭을 화면 픽셀로 잰다.
 *
 *  viewBox 하나를 카드 폭에 맞춰 늘리면 그림만 커지는 게 아니라 축 글자와 연도까지
 *  같이 커진다. 좁은 그리드에서는 드러나지 않고 넓은 단일 컬럼에서만 본문 글씨보다
 *  서너 배 큰 숫자가 된다. 좌표 한 칸을 화면 한 픽셀로 맞추면 그림은 폭을 채우고
 *  글자는 CSS에 적힌 크기 그대로 남는다.
 */
function useMeasuredWidth() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState(520);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const apply = (value: number) => {
      if (value > 0) setBox(Math.round(value));
    };
    apply(node.getBoundingClientRect().width);
    // 창 크기는 따로 듣는다. ResizeObserver가 멈춘 환경에서도 최소한 이건 온다.
    const onResize = () => apply(node.getBoundingClientRect().width);
    window.addEventListener("resize", onResize);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver((entries) => apply(entries[0]?.contentRect.width ?? 0));
    observer?.observe(node);
    return () => {
      window.removeEventListener("resize", onResize);
      observer?.disconnect();
    };
  }, []);
  const width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, box));
  // 상한에 걸려 남는 자리는 좌우로 나눈다. 마우스 옆 상자도 그만큼 밀린다.
  return { ref, width, offset: Math.max(0, Math.round((box - width) / 2)) };
}

/** 라벨 한 줄의 대략적인 폭. 한글은 라틴 문자의 두 배 가까이 넓다. */
function labelWidth(label: string) {
  let width = 0;
  for (const char of label) width += /[ᄀ-ᇿ　-ヿ一-鿿가-힯＀-￯]/.test(char) ? 13 : 7.2;
  return width;
}

/** 칸보다 넓은 라벨은 이웃과 겹친다. `2026 Q1`은 52px인데 분기 여덟 칸이면
 *  칸이 43px밖에 안 된다. 최근 것부터 두고 들어갈 만큼만 남긴다. */
export function labelStride(labels: string[], slot: number) {
  const widest = labels.reduce((max, label) => Math.max(max, labelWidth(label)), 0);
  return Math.max(1, Math.ceil((widest + 6) / Math.max(1, slot)));
}

/** 비교 대상 기간의 인덱스. 없으면 -1.
 *
 *  분기는 계절성이 있어 직전 분기가 아니라 전년 동기와 비교한다. 고정 오프셋
 *  4로는 그 자리를 못 짚는다 — 10-Q에는 Q4가 없어 라벨이 `2025 Q1·Q2·Q3·2026 Q1`처럼
 *  건너뛰기 때문이다. 라벨의 분기 번호로 전년 같은 분기를 직접 찾는다.
 *  연도 라벨(`2025`)에는 분기 규칙이 걸리지 않아 기존 오프셋 동작이 그대로 남고,
 *  compareOffset이 없는 옛 저장 페이로드도 직전 기간과 비교한다.
 */
export function compareIndex(labels: string[], index: number, compareOffset?: unknown): number {
  const quarter = /^(\d{4})\s+Q([1-4])$/.exec(String(labels[index] ?? "").trim());
  if (quarter) {
    const target = `${Number(quarter[1]) - 1} Q${quarter[2]}`;
    return labels.findIndex((label) => String(label ?? "").trim() === target);
  }
  const offset = Number(compareOffset) > 0 ? Number(compareOffset) : 1;
  const previous = index - offset;
  return previous >= 0 ? previous : -1;
}

function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [min, max];
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + step * i);
}

function BarsChart({
  chart,
  series,
  activeIndex,
  onIndex,
  width,
}: {
  chart: AnalysisChart;
  series: Series[];
  activeIndex: number;
  onIndex: (index: number, x: number) => void;
  width: number;
}) {
  const labels = Array.isArray(chart.years) ? chart.years : [];
  // 금액과 비율은 축을 나눈다. 한 축에 얹으면 비율이 0에 붙어 사라진다.
  const amounts = series.filter((item) => item.kind !== "percent");
  const rates = series.filter((item) => item.kind === "percent");
  const { min, max } = valueRange(amounts.flatMap((item) => item.values));
  const rate = valueRange(rates.flatMap((item) => item.values));
  const { height, top, plot, left, right } = BARS;
  const groupWidth = (width - left - right) / Math.max(1, labels.length);
  const barWidth = Math.max(6, Math.min(groupWidth / (amounts.length + 1.6), (groupWidth - 18) / Math.max(1, amounts.length)));
  const zeroY = yFor(0, min, max, top, plot);
  const centre = (index: number) => left + index * groupWidth + groupWidth / 2;
  const stride = labelStride(labels, groupWidth);

  return (
    <svg
      className="analysis-chart-svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={chart.title || "기업 분석 차트"}
    >
      {labels.map((label, index) => (
        <rect
          className="analysis-chart-band"
          key={`band-${label}`}
          data-active={index === activeIndex ? "true" : undefined}
          x={left + index * groupWidth}
          y={top - 4}
          width={groupWidth}
          height={plot + 8}
        />
      ))}
      {niceTicks(min, max).map((tick) => {
        const y = yFor(tick, min, max, top, plot);
        return (
          <g key={`tick-${tick}`}>
            <line x1={left} y1={y} x2={width - right} y2={y} stroke="var(--folio-border)" strokeWidth="0.5" />
            <text className="analysis-chart-axis" x={left - 8} y={y + 4} textAnchor="end">
              {formatValue(tick, "money", chart.currency)}
            </text>
          </g>
        );
      })}
      {rates.length > 0 && niceTicks(rate.min, rate.max, 2).map((tick) => (
        <text
          className="analysis-chart-axis"
          key={`rate-${tick}`}
          x={width - right + 8}
          y={yFor(tick, rate.min, rate.max, top, plot) + 4}
        >
          {formatValue(tick, "percent")}
        </text>
      ))}

      {labels.map((label, labelIndex) =>
        amounts.map((item, seriesIndex) => {
          const value = item.values[labelIndex];
          if (value === null) return null;
          const y = yFor(value, min, max, top, plot);
          const x = centre(labelIndex) - (amounts.length * barWidth) / 2 + seriesIndex * barWidth;
          return (
            <rect
              key={`${item.key}-${label}`}
              x={x}
              y={Math.min(y, zeroY)}
              width={Math.max(2, barWidth - 3)}
              height={Math.max(2, Math.abs(zeroY - y))}
              rx="3"
              fill={COLORS[seriesIndex % COLORS.length]}
            />
          );
        }),
      )}

      {rates.map((item, rateIndex) => {
        const points = labels
          .map((_, index) => [centre(index), item.values[index]] as const)
          .filter((pair): pair is readonly [number, number] => pair[1] !== null)
          .map(([x, value]) => `${x},${yFor(value, rate.min, rate.max, top, plot)}`)
          .join(" ");
        if (!points) return null;
        return (
          <polyline
            key={item.key}
            points={points}
            fill="none"
            strokeWidth="2"
            stroke={COLORS[(amounts.length + rateIndex) % COLORS.length]}
          />
        );
      })}

      {/* 막대 하나가 아니라 그 기간 전체가 대상이다. 조준할 필요가 없다.
          입력을 받는 사각형은 맨 위에 두되 칠하지 않는다 — 칠하면 그 아래 그래프를
          덮는다. 강조 배경은 마크보다 먼저 그려 뒤에 깔린다. */}
      {labels.map((label, index) =>
        index === activeIndex || (labels.length - 1 - index) % stride === 0 ? (
          <text
            className="analysis-chart-axis"
            data-active={index === activeIndex ? "true" : undefined}
            key={`x-${label}`}
            x={centre(index)}
            y={height - 16}
            textAnchor="middle"
          >
            {label}
          </text>
        ) : null,
      )}
      {/* 배경 음영만으로는 어느 기간을 짚었는지 잘 안 보인다. 축 위에 표시를 남긴다. */}
      {labels.length > 0 && (
        <rect
          className="analysis-chart-marker"
          x={left + activeIndex * groupWidth + groupWidth * 0.2}
          y={top + plot + 6}
          width={groupWidth * 0.6}
          height={2}
          rx="1"
        />
      )}
      {labels.map((label, index) => (
        <rect
          className="analysis-chart-hit"
          key={`hit-${label}`}
          x={left + index * groupWidth}
          y={top - 4}
          width={groupWidth}
          height={plot + 8}
          tabIndex={0}
          role="button"
          aria-label={`${label} 수치 보기`}
          onMouseEnter={() => onIndex(index, centre(index))}
          onFocus={() => onIndex(index, centre(index))}
        />
      ))}
    </svg>
  );
}

function LineChart({
  chart,
  series,
  activeIndex,
  onIndex,
  width,
}: {
  chart: AnalysisChart;
  series: Series[];
  activeIndex: number;
  onIndex: (index: number, x: number) => void;
  width: number;
}) {
  const labels = Array.isArray(chart.years) ? chart.years : [];
  const { min, max } = valueRange(series.flatMap((item) => item.values));
  const { height, top, plot, left, right } = BARS;
  const step = (width - left - right) / Math.max(1, labels.length - 1);
  const at = (index: number) => left + index * step;
  const stride = labelStride(labels, step);

  return (
    <svg
      className="analysis-chart-svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={chart.title || "기업 분석 차트"}
    >
      {niceTicks(min, max).map((tick) => {
        const y = yFor(tick, min, max, top, plot);
        return (
          <g key={`tick-${tick}`}>
            <line x1={left} y1={y} x2={width - right} y2={y} stroke="var(--folio-border)" strokeWidth="0.5" />
            <text className="analysis-chart-axis" x={left - 8} y={y + 4} textAnchor="end">
              {formatValue(tick, series[0]?.kind || "percent", chart.currency)}
            </text>
          </g>
        );
      })}

      {/* 마우스를 따라 서는 세로 선. 그 선에 걸리는 값이 아래 상자에 함께 나온다. */}
      {labels.length > 0 && (
        <line
          className="analysis-chart-rule"
          x1={at(activeIndex)}
          y1={top - 4}
          x2={at(activeIndex)}
          y2={top + plot + 4}
        />
      )}

      {series.map((item, seriesIndex) => {
        const points = item.values
          .map((value, index) => (value === null ? null : `${at(index)},${yFor(value, min, max, top, plot)}`))
          .filter(Boolean)
          .join(" ");
        const active = item.values[activeIndex];
        return (
          <g key={item.key}>
            <polyline
              points={points}
              fill="none"
              stroke={COLORS[seriesIndex % COLORS.length]}
              strokeWidth="2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {active !== null && active !== undefined && (
              <circle
                cx={at(activeIndex)}
                cy={yFor(active, min, max, top, plot)}
                r="4"
                fill={COLORS[seriesIndex % COLORS.length]}
              />
            )}
          </g>
        );
      })}

      {labels.map((label, index) =>
        index === activeIndex || (labels.length - 1 - index) % stride === 0 ? (
          <text className="analysis-chart-axis" key={`x-${label}`} x={at(index)} y={height - 16} textAnchor="middle">
            {label}
          </text>
        ) : null,
      )}
      {labels.map((label, index) => (
        <rect
          className="analysis-chart-hit"
          key={`hit-${label}`}
          x={index === 0 ? left : at(index) - step / 2}
          y={top - 4}
          width={index === 0 || index === labels.length - 1 ? step / 2 : step}
          height={plot + 8}
          tabIndex={0}
          role="button"
          aria-label={`${label} 수치 보기`}
          onMouseEnter={() => onIndex(index, at(index))}
          onFocus={() => onIndex(index, at(index))}
        />
      ))}
    </svg>
  );
}

function ScenarioChart({
  chart,
  onPoint,
  onLeave,
}: {
  chart: AnalysisChart;
  onPoint: (tooltip: NonNullable<ChartTooltip>) => void;
  onLeave: () => void;
}) {
  const rows = Array.isArray(chart.scenarios) ? chart.scenarios : [];
  const values = rows.map((row) => toNumber(row.perShare ?? row.price));
  const { max } = valueRange(values);
  const current = toNumber(chart.currentPrice);

  return (
    <div className="analysis-scenario-bars">
      {rows.map((row, index) => {
        const value = toNumber(row.perShare ?? row.price);
        const width = value === null || max <= 0 ? 0 : Math.max(4, Math.min(100, (value / max) * 100));
        const label = String(row.name || row.label || `Scenario ${index + 1}`);
        const formatted = formatValue(value, "money", chart.currency);
        return (
          <div
            aria-label={`${label} ${formatted}`}
            className="analysis-scenario-row"
            key={label}
            onBlur={onLeave}
            onFocus={() => onPoint({ label, value: formatted })}
            onMouseEnter={() => onPoint({ label, value: formatted })}
            onMouseLeave={onLeave}
            tabIndex={0}
          >
            <span>{label}</span>
            <div><i style={{ width: `${width}%`, background: COLORS[index % COLORS.length] }} /></div>
            <strong>{formatted}</strong>
          </div>
        );
      })}
      {current !== null && <p className="analysis-chart-note">현재가: {formatValue(current, "money", chart.currency)}</p>}
    </div>
  );
}

/** 수익률 비교 차트는 라벨과 계열이 다른 키에 담겨 온다. 라인 차트가 읽는 형태로 맞춘다. */
function returnChartData(chart: AnalysisChart): { chart: AnalysisChart; series: Series[] } {
  const labels = Array.isArray(chart.labels) ? chart.labels : [];
  const series = Object.entries(chart.series || {}).map(([key, values]) => ({
    key,
    label: key,
    values: Array.isArray(values) ? values.map((value) => (typeof value === "number" ? value / 100 : null)) : [],
    kind: "percent" as const,
  }));
  return { chart: { ...chart, years: labels }, series };
}

/** 기간별 수치를 한 상자에 모아 보여준다.
 *
 *  예전에는 막대마다 툴팁이 떠서 한 번에 한 계열만 보였고, 그 해의 매출·이익을
 *  나란히 보려면 막대를 차례로 짚어야 했다. 비교가 목적인데 비교가 안 됐다.
 *  상자를 그림 밖에 두어 플롯을 가리지도 않는다.
 */
function PeriodPanel({
  chart,
  series,
  index,
}: {
  chart: AnalysisChart;
  series: Series[];
  index: number;
}) {
  const labels = Array.isArray(chart.years) ? chart.years : [];
  // 분기는 계절성이 있어 직전 분기가 아니라 전년 동기와 비교한다.
  const previous = compareIndex(labels, index, chart.compareOffset);
  const compareLabel = previous >= 0 ? labels[previous] : "";

  return (
    <div className="analysis-chart-readout">
      <p className="analysis-chart-readout-head">
        <strong>{labels[index] || ""}</strong>
        {compareLabel && <span>{compareLabel} 대비</span>}
      </p>
      {series.map((item, seriesIndex) => {
        const value = item.values[index] ?? null;
        const before = previous >= 0 ? item.values[previous] ?? null : null;
        let change = "—";
        let direction: "up" | "down" | "flat" = "flat";
        if (value !== null && before !== null && before !== 0) {
          if (item.kind === "percent") {
            const diff = (value - before) * 100;
            direction = diff >= 0 ? "up" : "down";
            change = `${diff >= 0 ? "+" : ""}${diff.toFixed(1)}%p`;
          } else {
            const diff = ((value - before) / Math.abs(before)) * 100;
            direction = diff >= 0 ? "up" : "down";
            change = `${diff >= 0 ? "+" : ""}${diff.toFixed(1)}%`;
          }
        }
        return (
          <p className="analysis-chart-readout-row" key={item.key}>
            <span className="analysis-chart-swatch" style={{ background: COLORS[seriesIndex % COLORS.length] }} />
            <span>{item.label}</span>
            <b>{formatValue(value, item.kind, chart.currency)}</b>
            <em data-direction={direction}>{change}</em>
          </p>
        );
      })}
    </div>
  );
}

function ChartCard({ chart }: { chart: AnalysisChart }) {
  const [tooltip, setTooltip] = useState<ChartTooltip>(null);
  const kind = String(chart.kind || chart.id || "");
  // 선으로 그리는 차트와 막대로 그리는 차트가 같은 기간 상자를 쓴다.
  const line = kind === "margins"
    ? { chart, series: chartSeries(chart) }
    : kind === "price_return"
      ? returnChartData(chart)
      : null;
  const bars = ["performance", "cashflow", "quarterly"].includes(kind)
    ? { chart, series: chartSeries(chart) }
    : null;
  const banded = line ?? bars;
  const series = banded?.series ?? [];
  const labels = Array.isArray(banded?.chart.years) ? (banded?.chart.years as string[]) : [];
  // 마우스를 올리지 않아도 최신 기간 숫자가 보인다. 짚기 전에는 마지막 기간이다.
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  // 짚은 자리 옆에도 숫자를 띄운다. 아래 상자까지 눈을 내리지 않아도 되게.
  const [anchor, setAnchor] = useState<number | null>(null);
  const plot = useMeasuredWidth();
  const pick = (next: number, x: number) => {
    setActiveIndex(next);
    setAnchor(x);
  };
  const last = Math.max(0, labels.length - 1);
  const index = Math.min(activeIndex ?? last, last);
  const tooltipStyle = tooltip?.x !== undefined
    ? { left: `${Math.max(7, Math.min(93, (tooltip.x / plot.width) * 100))}%`, top: `${Math.max(10, tooltip.y || 10)}px` }
    : undefined;

  return (
    <article className="analysis-chart-card">
      <div className="analysis-chart-title">
        <h4>{chart.title || "기업 분석 차트"}</h4>
        {chart.subtitle && <p>{chart.subtitle}</p>}
      </div>
      <div className="analysis-chart-plot" onBlur={() => setAnchor(null)} onMouseLeave={() => setAnchor(null)} ref={plot.ref}>
        {line && line.series.length ? (
          <LineChart chart={line.chart} series={line.series} activeIndex={index} onIndex={pick} width={plot.width} />
        ) : null}
        {bars && bars.series.length ? (
          <BarsChart chart={bars.chart} series={bars.series} activeIndex={index} onIndex={pick} width={plot.width} />
        ) : null}
        {(kind === "dcf" || kind === "scenario_price") ? <ScenarioChart chart={chart} onPoint={setTooltip} onLeave={() => setTooltip(null)} /> : null}
        {!series.length && !["dcf", "scenario_price"].includes(kind) && (
          <p className="analysis-chart-warning">이 차트에 표시할 수치가 충분하지 않습니다.</p>
        )}
        {tooltip && (
          <div className="analysis-chart-tooltip" style={tooltipStyle}>
            {tooltip.series && <span>{tooltip.series}</span>}
            <strong>{tooltip.value}</strong>
            <em>{tooltip.label}</em>
          </div>
        )}
        {anchor !== null && banded && series.length > 0 && (
          <div
            className="analysis-chart-hover"
            data-side={anchor > plot.width / 2 ? "left" : "right"}
            /* 오른쪽 절반에서는 left가 아니라 right로 세운다. left만 주면 상자가
               쓸 수 있는 폭이 `컨테이너 - left`로 잘려, 이름과 숫자가 서로 겹친다. */
            style={
              anchor > plot.width / 2
                ? { right: `calc(100% - ${anchor + plot.offset}px)` }
                : { left: `${anchor + plot.offset}px` }
            }
          >
            <b>{labels[index] || ""}</b>
            {series.map((item, seriesIndex) => (
              <p key={item.key}>
                <span className="analysis-chart-swatch" style={{ background: COLORS[seriesIndex % COLORS.length] }} />
                <span>{item.label}</span>
                <em>{formatValue(item.values[index] ?? null, item.kind, banded.chart.currency)}</em>
              </p>
            ))}
          </div>
        )}
      </div>
      {banded && series.length > 0 ? <PeriodPanel chart={banded.chart} series={series} index={index} /> : null}
      {/* 역산 성장률이 이 차트의 핵심 숫자다. 내재가치와 현재가의 차이를 보여 주기만
          하면 독자는 그것을 고평가·저평가 판정으로 읽는다 — DCF는 가정 위에 섰고,
          "현재가가 정당화되려면 얼마여야 하는가"가 그 가정을 되돌려 보여 준다. */}
      {kind === "dcf" && typeof chart.impliedGrowth === "number" ? (
        <p className="analysis-chart-note">
          현재가가 정당화되려면 초기 성장률이 <strong>{(chart.impliedGrowth * 100).toFixed(1)}%</strong>여야
          합니다. 내재가치와 현재가의 차이는 고평가·저평가 판정이 아니라 가정의 결과입니다.
        </p>
      ) : null}
    </article>
  );
}

export function AnalysisCharts({
  payload,
  chartIds,
  heading = "기업 분석 시각화",
  intro = "저장된 공식 재무 데이터와 시장 데이터를 기반으로 생성된 참고 차트입니다.",
  compact = false,
}: {
  payload?: AnalysisChartsPayload;
  chartIds?: string[];
  heading?: string;
  intro?: string;
  compact?: boolean;
}) {
  const allowed = chartIds ? new Set(chartIds) : null;
  const charts = ((Array.isArray(payload?.charts) ? payload.charts : []) as AnalysisChart[])
    .filter((chart) => !allowed || allowed.has(String(chart.id || chart.kind || "")));
  if (!payload?.available || !charts.length) return null;
  return (
    <section className={`analysis-charts-panel analysis-charts-inline${compact ? " compact" : ""}`} aria-label={heading}>
      <div className="analysis-chart-head">
        <div>
          <p className="section-kicker">Company Visuals</p>
          <h3>{heading}</h3>
          <p>{intro}</p>
        </div>
      </div>
      <div className="analysis-chart-grid">
        {charts.map((chart, index) => (
          <ChartCard chart={chart} key={chart.id || `${chart.title || "chart"}-${index}`} />
        ))}
      </div>
    </section>
  );
}
