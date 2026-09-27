import { useMemo } from "react";
import { FolioChart, type OptionBuilder } from "../charts/FolioChart";
import { axisLabel, fixed, periodLabel } from "./types";

export type MacroChartPoint = { period: string; value: number | null };

/**
 * 거시 지표 상세의 추이. 변화율(전분기·전월 대비)은 막대, 수준·전년비는 선으로 그린다.
 * 과거 시점 재현에서는 `comparison`(현재 수정치)을 점선으로 겹친다 — 선택 시점 계산에는 쓰지 않는다.
 * 테마·키보드·데이터 표·빈 상태는 FolioChart가 소유하므로 여기서 다시 구현하지 않는다.
 */
export function MacroChart({ title, points, frequency, unit, digits, shape, comparison = [], stale = false }: {
  title: string;
  points: MacroChartPoint[];
  frequency: string;
  unit: string;
  digits: number;
  shape: "bars" | "line";
  comparison?: MacroChartPoint[];
  stale?: boolean;
}) {
  const compared = useMemo(() => new Map(comparison.map((p) => [p.period, p.value])), [comparison]);
  const text = (value: number | null | undefined) => (value == null ? "자료 없음" : `${fixed(value, digits)}${unit === "원" || unit === "지수" ? ` ${unit}` : unit}`);
  const option = useMemo<OptionBuilder>(() => (tokens) => {
    const ink = tokens("--folio-chart-1");
    const last = points.length - 1;
    return {
      animation: false,
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        valueFormatter: (value: unknown) => (typeof value === "number" ? text(value) : "자료 없음"),
      },
      // 축 글자와 첫 막대가 붙지 않게 왼쪽 여백과 글자 간격을 넉넉히 둔다.
      grid: { left: 16, right: 16, top: 30, bottom: 30, containLabel: true },
      legend: comparison.length ? { data: ["선택 시점", "현재 수정치"] } : undefined,
      xAxis: {
        type: "category",
        data: points.map((p) => axisLabel(p.period, frequency)),
        boundaryGap: shape === "bars",
        axisLabel: { hideOverlap: true },
      },
      yAxis: { type: "value", scale: shape !== "bars", axisLabel: { margin: 16 } },
      series: [
        shape === "bars"
          ? {
            name: comparison.length ? "선택 시점" : title,
            type: "bar",
            // 강조는 색이 아니라 농도로 한다. 마지막 막대(최신 발표)만 진하게.
            data: points.map((p, i) => (i === last ? { value: p.value, itemStyle: { opacity: 1 } } : p.value)),
            itemStyle: { color: ink, opacity: 0.45 },
          }
          : {
            name: comparison.length ? "선택 시점" : title,
            type: "line",
            showSymbol: false,
            connectNulls: false,
            data: points.map((p) => p.value),
            itemStyle: { color: ink },
          },
        ...(comparison.length ? [{
          name: "현재 수정치",
          type: "line",
          showSymbol: false,
          connectNulls: false,
          data: points.map((p) => compared.get(p.period) ?? null),
          lineStyle: { type: "dashed" },
          itemStyle: { color: tokens("--folio-chart-2") },
        }] : []),
      ],
    };
  }, [points, comparison, compared, title, frequency, shape, digits, unit]);

  return (
    <FolioChart
      label={`${title} 추이`}
      option={option}
      height={280}
      state={!points.some((p) => p.value != null) ? "empty" : stale ? "stale" : "ready"}
      table={{
        title: `${title} 데이터 표`,
        unit: "관측기간",
        columns: ["관측기간", "값", ...(comparison.length ? ["현재 수정치"] : [])],
        rows: points.map((p) => [
          periodLabel(p.period, frequency) + (frequency === "M" || frequency === "Q" ? ` (${p.period.slice(0, 4)})` : ""),
          text(p.value),
          ...(comparison.length ? [text(compared.get(p.period))] : []),
        ]),
      }}
      keyboard={{
        count: points.length,
        focus: (chart, i) => chart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: i }),
        readout: (i) => `${periodLabel(points[i].period, frequency)} ${points[i].period.slice(0, 4)}년, ${text(points[i].value)}`,
      }}
    />
  );
}
