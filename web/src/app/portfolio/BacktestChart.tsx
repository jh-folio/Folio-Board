import { useEffect, useId, useMemo, useRef, useState } from "react";
import { MAX_TABLE_ROWS, sampleRows } from "../charts/chartA11y";
import { money, percent, type BacktestPoint } from "./portfolioTypes";

export type ChartTone = "portfolio" | "benchmark" | "blue" | "teal" | "gold" | "purple" | "burgundy";
export type BacktestChartSeries = {
  readonly id: string;
  readonly label: string;
  readonly points: ReadonlyArray<BacktestPoint>;
  readonly tone: ChartTone;
  readonly pattern?: "solid" | "dashed" | "dotted";
};

type ChartKind = "value" | "percent" | "number";
type PointAtDate = { readonly date: string; readonly values: Readonly<Record<string, number | null>> };

function finitePoints(points: ReadonlyArray<BacktestPoint>): BacktestPoint[] {
  return points.filter((point) => typeof point.date === "string" && Number.isFinite(point.value) && Number.isFinite(new Date(point.date).getTime()));
}

function dateLabel(value: string, compact = false): string {
  const date = new Date(`${value}T00:00:00`);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", compact ? { year: "2-digit", month: "numeric" } : { year: "numeric", month: "long", day: "numeric" }).format(date);
}

function numberLabel(value: number, kind: ChartKind): string {
  if (!Number.isFinite(value)) return "계산 불가";
  if (kind === "percent") return percent(value);
  if (kind === "value") return money(value);
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

/** Portfolio 결과와 비교 결과가 공유하는 최소 SVG 차트 층.
 *
 * SVG의 좌표계는 ResizeObserver가 읽은 실제 컨테이너 폭에서 계산한다. 고정 640 viewBox를
 * 늘리는 방식은 좁은 화면의 tick·터치 위치를 모두 부정확하게 만든다.
 */
export function BacktestChart({
  title,
  description,
  series,
  kind = "value",
  emptyMessage = "표시할 시계열이 없습니다.",
}: {
  readonly title: string;
  readonly description: string;
  readonly series: ReadonlyArray<BacktestChartSeries>;
  readonly kind?: ChartKind;
  readonly emptyMessage?: string;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const instanceId = useId().replace(/[^A-Za-z0-9_-]/g, "");
  const [chartWidth, setChartWidth] = useState(0);
  const clean = useMemo(() => series.map((row) => ({ ...row, points: finitePoints(row.points) })).filter((row) => row.points.length > 0), [series]);
  const allDates = useMemo(() => Array.from(new Set(clean.flatMap((row) => row.points.map((point) => point.date)))).sort(), [clean]);
  const [selectedDate, setSelectedDate] = useState("");

  useEffect(() => {
    if (!allDates.length) { setSelectedDate(""); return; }
    setSelectedDate((current) => allDates.includes(current) ? current : allDates[allDates.length - 1]);
  }, [allDates]);

  useEffect(() => {
    const element = holder.current;
    if (!element) return undefined;
    const measure = () => setChartWidth(Math.max(1, Math.floor(element.getBoundingClientRect().width)));
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [clean.length]);

  const pointsBySeries = useMemo(() => new Map(clean.map((row) => [row.id, new Map(row.points.map((point) => [point.date, point.value]))])), [clean]);
  const selectedIndex = Math.max(0, allDates.indexOf(selectedDate));
  const selected = allDates[selectedIndex];
  const rows = useMemo<PointAtDate[]>(() => allDates.map((date) => ({
    date,
    values: Object.fromEntries(clean.map((row) => [row.id, pointsBySeries.get(row.id)?.get(date) ?? null])),
  })), [allDates, clean, pointsBySeries]);

  if (!clean.length || !allDates.length) {
    return <p className="portfolio-chart-empty" role="status">{emptyMessage}</p>;
  }

  const outerWidth = chartWidth || 320;
  const height = 260;
  const inset = { top: 18, right: 14, bottom: 42, left: 66 };
  const plotWidth = Math.max(1, outerWidth - inset.left - inset.right);
  const plotHeight = Math.max(1, height - inset.top - inset.bottom);
  const values = clean.flatMap((row) => row.points.map((point) => point.value));
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (kind === "percent") { min = Math.min(min, 0); max = Math.max(max, 0); }
  const padding = (max - min || Math.max(Math.abs(max), 1)) * 0.08;
  min -= padding;
  max += padding;
  const minTime = new Date(allDates[0]).getTime();
  const maxTime = new Date(allDates[allDates.length - 1]).getTime();
  const timeSpan = maxTime - minTime || 1;
  const valueSpan = max - min || 1;
  const xForDate = (date: string) => inset.left + ((new Date(date).getTime() - minTime) / timeSpan) * plotWidth;
  const yForValue = (value: number) => inset.top + (1 - ((value - min) / valueSpan)) * plotHeight;
  const pathFor = (points: ReadonlyArray<BacktestPoint>) => points.map((point, index) => `${index ? "L" : "M"}${xForDate(point.date).toFixed(2)},${yForValue(point.value).toFixed(2)}`).join(" ");
  const yTicks = Array.from({ length: 4 }, (_, index) => min + ((max - min) * index / 3));
  // 날짜 간격은 관측 건수와 비례하지 않는다. 월초에 몰린 sparse series에서 index로
  // 고르면 375px 화면의 tick 글자가 서로 붙는다. 시간 좌표의 최소 간격을 보장한다.
  const desiredTicks = Array.from({ length: 5 }, (_, index) => minTime + (timeSpan * index / 4));
  const candidateTicks = Array.from(new Set(desiredTicks.map((time) => allDates.reduce((best, date, index) => Math.abs(new Date(date).getTime() - time) < Math.abs(new Date(allDates[best]).getTime() - time) ? index : best, 0))));
  const minimumTickGap = outerWidth < 440 ? 72 : 92;
  const finalTick = allDates.length - 1;
  const xTicks = [0];
  for (const index of candidateTicks) {
    if (index <= 0 || index >= finalTick) continue;
    if (xForDate(allDates[index]) - xForDate(allDates[xTicks[xTicks.length - 1]]) >= minimumTickGap) xTicks.push(index);
  }
  // The final date is useful even for sparse dates, but must evict any label
  // crowding it at the right edge (not merely when it was absent from candidates).
  while (xTicks.length > 1 && xForDate(allDates[finalTick]) - xForDate(allDates[xTicks[xTicks.length - 1]]) < minimumTickGap) xTicks.pop();
  if (finalTick > 0) xTicks.push(finalTick);
  const selectNearest = (clientX: number, element: SVGSVGElement) => {
    const rect = element.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left - (inset.left / outerWidth) * rect.width) / ((plotWidth / outerWidth) * rect.width)));
    const intended = minTime + ratio * timeSpan;
    let closest = 0;
    for (let index = 1; index < allDates.length; index += 1) {
      if (Math.abs(new Date(allDates[index]).getTime() - intended) < Math.abs(new Date(allDates[closest]).getTime() - intended)) closest = index;
    }
    setSelectedDate(allDates[closest]);
  };

  return (
    <section className="portfolio-chart" aria-labelledby={`${instanceId}-chart-title`}>
      <div className="portfolio-chart__head">
        <div><h4 id={`${instanceId}-chart-title`}>{title}</h4><p>{description}</p></div>
        <ul className="portfolio-chart__legend" aria-label={`${title} 범례`}>
          {clean.map((row) => <li key={row.id}><i data-tone={row.tone} data-pattern={row.pattern || "solid"} aria-hidden="true" />{row.label}</li>)}
        </ul>
      </div>
      <div className="portfolio-chart__canvas" ref={holder}>
        <svg
          viewBox={`0 0 ${outerWidth} ${height}`}
          width={outerWidth}
          height={height}
          role="img"
          aria-label={`${title}. ${description}. 날짜 선택 막대 또는 차트 터치로 정확한 값을 확인할 수 있습니다.`}
          onPointerMove={(event) => { if (event.pointerType === "mouse") selectNearest(event.clientX, event.currentTarget); }}
          onPointerDown={(event) => selectNearest(event.clientX, event.currentTarget)}
        >
          {yTicks.map((value) => <g key={value}><line className="portfolio-chart__grid" x1={inset.left} x2={outerWidth - inset.right} y1={yForValue(value)} y2={yForValue(value)} /><text className="portfolio-chart__axis" x={inset.left - 8} y={yForValue(value) + 4} textAnchor="end">{numberLabel(value, kind)}</text></g>)}
          {xTicks.map((index) => <text key={index} className="portfolio-chart__axis" x={xForDate(allDates[index])} y={height - 13} textAnchor={index === 0 ? "start" : index === allDates.length - 1 ? "end" : "middle"}>{dateLabel(allDates[index], true)}</text>)}
          {clean.map((row) => <path key={row.id} className="portfolio-chart__line" data-tone={row.tone} data-pattern={row.pattern || "solid"} d={pathFor(row.points)} />)}
          {selected && <><line className="portfolio-chart__cursor" x1={xForDate(selected)} x2={xForDate(selected)} y1={inset.top} y2={inset.top + plotHeight} />{clean.map((row) => {
            const value = pointsBySeries.get(row.id)?.get(selected);
            return value === undefined ? null : <circle key={row.id} className="portfolio-chart__point" data-tone={row.tone} cx={xForDate(selected)} cy={yForValue(value)} r="4" />;
          })}</>}
        </svg>
      </div>
      <label className="portfolio-chart__slider">
        <span>날짜 선택</span>
        <input type="range" min="0" max={Math.max(0, allDates.length - 1)} value={selectedIndex} onChange={(event) => setSelectedDate(allDates[Number(event.target.value)])} />
      </label>
      {selected && <dl className="portfolio-chart__readout" aria-live="polite"><div><dt>날짜</dt><dd>{dateLabel(selected)}</dd></div>{clean.map((row) => <div key={row.id}><dt>{row.label}</dt><dd>{numberLabel(pointsBySeries.get(row.id)?.get(selected) ?? Number.NaN, kind)}</dd></div>)}</dl>}
      <details className="portfolio-chart__data"><summary>차트 데이터 표 보기 ({rows.length > MAX_TABLE_ROWS ? `${MAX_TABLE_ROWS}개 대표 날짜` : `${rows.length}개 날짜`})</summary><div className="portfolio-table-scroll" role="region" aria-label={`${title} 데이터 표`} tabIndex={0}><table><thead><tr><th scope="col">날짜</th>{clean.map((row) => <th scope="col" key={row.id}>{row.label}</th>)}</tr></thead><tbody>{sampleRows(rows).map((row) => <tr key={row.date}><th scope="row">{row.date}</th>{clean.map((line) => <td key={line.id}>{numberLabel(row.values[line.id] ?? Number.NaN, kind)}</td>)}</tr>)}</tbody></table></div></details>
    </section>
  );
}
