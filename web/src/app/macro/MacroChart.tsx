import { useMemo } from 'react';
import { FolioChart, type OptionBuilder } from '../charts/FolioChart';
import type { MacroPoint } from './types';

export const numberText = (value: number | null | undefined) => value == null ? '자료 없음' : value.toLocaleString('ko-KR', { maximumFractionDigits: 2 });

export function MacroChart({ title, points, comparison = [], stale = false }: { title: string; points: MacroPoint[]; comparison?: MacroPoint[]; stale?: boolean }) {
  const compared = useMemo(() => new Map(comparison.map(p => [p.period, p.displayValue])), [comparison]);
  const option = useMemo<OptionBuilder>(() => (tokens) => ({
    animation: false,
    tooltip: { trigger: 'axis', renderMode: 'richText', valueFormatter: (value: unknown) => typeof value === 'number' ? numberText(value) : '자료 없음' },
    grid: { left: 12, right: 12, top: 30, bottom: 30, containLabel: true },
    legend: comparison.length ? { data: ['선택 시점', '현재 수정치'] } : undefined,
    xAxis: { type: 'category', data: points.map(p => p.period), axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value', scale: true },
    series: [{ name: comparison.length ? '선택 시점' : title, type: 'line', showSymbol: false, connectNulls: false,
      data: points.map(p => p.displayValue), itemStyle: { color: tokens('--folio-chart-1') } },
      ...(comparison.length ? [{ name: '현재 수정치', type: 'line', showSymbol: false, connectNulls: false,
        data: points.map(p => compared.get(p.period) ?? null),
        lineStyle: { type: 'dashed' }, itemStyle: { color: tokens('--folio-chart-2') } }] : [])],
  }), [points, comparison, compared, title]);
  return <FolioChart label={`${title} 추이`} option={option} height={220}
    state={!points.some(p => p.displayValue != null) ? 'empty' : stale ? 'stale' : 'ready'}
    table={{ title: `${title} 데이터 표`, unit: '관측기간', columns: ['관측기간', '표시값', '단위', ...(comparison.length ? ['현재 수정치'] : [])],
      rows: points.map(p => [p.period, numberText(p.displayValue), p.displayUnit, ...(comparison.length ? [numberText(compared.get(p.period))] : [])]) }}
    keyboard={{ count: points.length, focus: (chart, i) => chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: i }),
      readout: i => `${points[i].period}, ${numberText(points[i].displayValue)} ${points[i].displayUnit}` }} />;
}
