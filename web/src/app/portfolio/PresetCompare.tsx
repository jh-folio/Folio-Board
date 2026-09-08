import { useEffect, useState } from "react";
import { postJson } from "../../api";
import { BacktestChart, type BacktestChartSeries, type ChartTone } from "./BacktestChart";
import { BacktestResultReport } from "./BacktestReport";
import { backtestErrorMessage } from "./backtestUi";
import { backtestMetric, isComparison, money, percent, signOf, type BacktestComparison, type BacktestPoint, type BacktestResult, type Preset } from "./portfolioTypes";

type Better = "high" | "low" | "nearZero";
const COMPARE_METRICS: ReadonlyArray<{ key: string; label: string; kind: "pct" | "num"; better: Better }> = [
  { key: "totalReturn", label: "총 수익률", kind: "pct", better: "high" }, { key: "cagr", label: "연평균(CAGR)", kind: "pct", better: "high" }, { key: "maxDrawdown", label: "최대 낙폭", kind: "pct", better: "nearZero" }, { key: "volatility", label: "변동성", kind: "pct", better: "low" }, { key: "sharpe", label: "샤프", kind: "num", better: "high" },
];
const SERIES_TONES: readonly ChartTone[] = ["blue", "teal", "gold", "purple", "burgundy"];
const REBALANCE: ReadonlyArray<{ id: string; label: string }> = [{ id: "none", label: "안 함" }, { id: "monthly", label: "매월" }, { id: "quarterly", label: "분기" }, { id: "yearly", label: "매년" }];

function metricValue(result: BacktestResult, key: string): number | null { return backtestMetric(result, key); }
function formatMetric(value: number | null, kind: "pct" | "num"): string { return value === null ? "계산 불가" : kind === "pct" ? percent(value) : money(value, 2); }
function seriesLabel(row: BacktestResult, index: number): string { return row.presetName || row.name || `프리셋 ${index + 1}`; }

/** 이 지표에서 가장 나은 결과의 인덱스. 동점·비교 불가는 어느 쪽도 강조하지 않는다. */
export function bestIndex(results: ReadonlyArray<BacktestResult>, key: string, better: Better): number | null {
  const values = results.map((row) => metricValue(row, key)); const present = values.filter((value): value is number => value !== null);
  if (present.length < 2) return null;
  const score = (value: number) => better === "nearZero" ? -Math.abs(value) : better === "high" ? value : -value;
  const target = Math.max(...present.map(score)); const winners = values.map((value, index) => value !== null && score(value) === target ? index : -1).filter((index) => index >= 0);
  return winners.length === 1 ? winners[0] : null;
}

/** 외부 테스트와 비교 차트 양쪽이 쓰는 날짜 기반 경로 계산. */
export function seriesPath(series: ReadonlyArray<{ date: string; value: number }>, bounds: { minTime: number; maxTime: number; min: number; max: number }, width: number, height: number): string {
  const timeSpan = bounds.maxTime - bounds.minTime || 1; const valueSpan = bounds.max - bounds.min || 1;
  return series.map((point, index) => { const time = new Date(point.date).getTime(); const x = ((Number.isFinite(time) ? time : bounds.minTime) - bounds.minTime) / timeSpan * width; const y = height - ((point.value - bounds.min) / valueSpan) * height; return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`; }).join(" ");
}

function chartLines(results: ReadonlyArray<BacktestResult>, source: (result: BacktestResult) => ReadonlyArray<BacktestPoint>, suffix: string): BacktestChartSeries[] {
  return results.map((row, index) => ({ id: `${row.id}-${suffix}`, label: seriesLabel(row, index), points: source(row), tone: SERIES_TONES[index % SERIES_TONES.length] })).filter((row) => row.points.length > 0);
}
function rolling(result: BacktestResult, key: "rollingReturn" | "rollingVolatility" | "rollingBeta"): BacktestPoint[] { return (result.rollingMetrics || []).flatMap((row) => typeof row[key] === "number" && Number.isFinite(row[key]) ? [{ date: row.date, value: row[key] as number }] : []); }
function sameConditions(comparison: BacktestComparison): boolean {
  const rows = comparison.results;
  const methodKey = (row: BacktestResult): string | null => {
    const basis = row.calculationBasis;
    const assumptions = row.metrics.metricAssumptions;
    const riskFree = basis?.riskFreeRate;
    if (!row.analysisVersion || !basis?.returnMethod || !basis.priceAlignment?.method || !riskFree || typeof riskFree.annual !== "number" || !riskFree.source || !riskFree.method || typeof basis.annualization?.tradingDays !== "number" || !assumptions?.volatilityMethod || !assumptions.sharpeMethod || !assumptions.alphaMethod) return null;
    return JSON.stringify([row.analysisVersion, riskFree.annual, riskFree.source, riskFree.method, basis.annualization.tradingDays, basis.returnMethod, basis.priceAlignment.method, assumptions.volatilityMethod, assumptions.sharpeMethod, assumptions.alphaMethod]);
  };
  const firstMethod = rows.length ? methodKey(rows[0]) : null;
  return rows.length > 1 && firstMethod !== null && rows.every((row) => methodKey(row) === firstMethod && row.start === rows[0].start && row.end === rows[0].end && row.baseCurrency === rows[0].baseCurrency && row.initialValue === rows[0].initialValue && row.rebalance === rows[0].rebalance && row.baseCurrency === comparison.baseCurrency && row.initialValue === comparison.initialValue && row.rebalance === comparison.rebalance);
}
function rebalanceLabel(value: string): string { return ({ none: "리밸런싱 안 함", monthly: "매월 리밸런싱", quarterly: "분기 리밸런싱", yearly: "매년 리밸런싱" } as Record<string, string>)[value] || "리밸런싱 조건 미기록"; }

/** 저장본을 포함해 comparison payload를 안전하게 다시 읽는다. */
export function BacktestComparisonReport({ result }: { readonly result: BacktestComparison }) {
  const comparable = sameConditions(result);
  return <div className="portfolio-comparison-report">
    <header className="portfolio-backtest-result-head"><div><h3>{result.name || "포트폴리오 비교"}</h3><p>{result.start} ~ {result.end} · {result.baseCurrency} · 시작 {money(result.initialValue)} · {result.benchmark?.ticker || "벤치마크 미기록"} · {rebalanceLabel(result.rebalance)}</p></div><span className="chip">실행 조건 고정</span></header>
    <BacktestChart title="누적 성과 비교" description={comparable ? "같은 조건에서 실행된 프리셋의 평가액 추이입니다." : "동일한 통화·초기금액·기간을 확인하지 못해 평가액을 겹쳐 그리지 않았습니다."} series={comparable ? chartLines(result.results, (row) => row.series || [], "cumulative") : []} emptyMessage="실제 통화·초기 금액·기간이 서로 달라 누적 평가액을 같은 차트에 겹쳐 그리지 않았습니다." />
    <BacktestChart title="낙폭 비교" description="각 프리셋의 이전 최고점 대비 하락률입니다." series={chartLines(result.results, (row) => (row.drawdownSeries || []).map((point) => ({ date: point.date, value: point.drawdown })), "drawdown")} kind="percent" emptyMessage="이전 비교 저장본에는 낙폭 시계열이 없습니다." />
    <div className="portfolio-report-grid"><BacktestChart title="Rolling 12개월 수익률 비교" description="최근 252 거래일 누적 수익률입니다." series={chartLines(result.results, (row) => rolling(row, "rollingReturn"), "rolling-return")} kind="percent" emptyMessage="Rolling 수익률 자료가 없습니다." /><BacktestChart title="Rolling 변동성 비교" description="최근 252 거래일 연율화 변동성입니다." series={chartLines(result.results, (row) => rolling(row, "rollingVolatility"), "rolling-volatility")} kind="percent" emptyMessage="Rolling 변동성 자료가 없습니다." /><BacktestChart title="Rolling 베타 비교" description="최근 252 거래일 벤치마크 대비 베타입니다." series={chartLines(result.results, (row) => rolling(row, "rollingBeta"), "rolling-beta")} kind="number" emptyMessage="비교 가능한 벤치마크 기간이 없어 Rolling 베타를 계산하지 못했습니다." /></div>
    <section className="portfolio-compare-metrics"><h4>같은 조건의 핵심 지표</h4>{!comparable && <p className="react-dashboard-warning" role="status">프리셋마다 실제 관측 기간, 통화, 초기 금액 또는 리밸런싱 조건이 달라 우열과 누적 평가액을 비교하지 않습니다. 각 결과의 자료 범위를 확인하세요.</p>}<div className="portfolio-table-scroll" role="region" aria-label="비교 지표 표" tabIndex={0}><table className="portfolio-compare-table"><thead><tr><th scope="col">지표</th>{result.results.map((row, index) => <th scope="col" key={row.id}>{seriesLabel(row, index)}</th>)}</tr></thead><tbody>{COMPARE_METRICS.map((metric) => { const best = comparable ? bestIndex(result.results, metric.key, metric.better) : null; return <tr key={metric.key}><th scope="row">{metric.label}</th>{result.results.map((row) => { const value = metricValue(row, metric.key); return <td key={row.id} data-best={result.results.indexOf(row) === best ? "true" : undefined} data-sign={metric.kind === "pct" && value !== null ? signOf(value) : undefined}>{formatMetric(value, metric.kind)}</td>; })}</tr>; })}</tbody></table></div></section>
    {result.errors?.length ? <p className="react-dashboard-warning" role="alert">{result.errors.map((row) => row.presetName || row.presetId || "이름 없는 프리셋").join(", ")}은 백테스트에 실패했습니다. 성공한 결과만 보이며 실패한 프리셋을 조용히 제외하거나 재순위하지 않습니다.</p> : null}
    <details className="portfolio-report-details"><summary>각 프리셋의 기여도·자료 범위·가정 보기</summary><div className="portfolio-report-details__body">{result.results.map((row, index) => <details className="portfolio-report-details" key={row.id}><summary>{seriesLabel(row, index)} 결과 상세</summary><div className="portfolio-report-details__body"><BacktestResultReport result={row} title={seriesLabel(row, index)} tone={SERIES_TONES[index % SERIES_TONES.length]} /></div></details>)}</div></details>
    <p className="portfolio-note">리서치용입니다. 세금·수수료·체결오차·배당 처리에는 한계가 있으며, 비교 결과는 매수·매도나 비중 조정 지시가 아닙니다.</p>
  </div>;
}

export function PresetCompare({ presets }: { readonly presets: ReadonlyArray<Preset> }) {
  const [start, setStart] = useState("2020-01-01"); const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10)); const [rebalance, setRebalance] = useState("monthly");
  const [baseCurrency, setBaseCurrency] = useState("USD"); const [initialValue, setInitialValue] = useState("10000"); const [benchmark, setBenchmark] = useState("SPY"); const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<BacktestComparison | null>(null); const [busy, setBusy] = useState(""); const [note, setNote] = useState(""); const [error, setError] = useState("");
  const usable = presets.filter((preset) => preset.positions.length); const invalid = selected.length < 2 || start >= end || !Number.isFinite(Number(initialValue)) || Number(initialValue) <= 0 || !benchmark.trim();
  useEffect(() => { setSelected((current) => current.filter((id) => presets.some((preset) => preset.id === id && preset.positions.length > 0))); setResult(null); }, [presets]);
  const toggle = (id: string) => { if (!busy) setSelected((current) => current.includes(id) ? current.filter((row) => row !== id) : [...current, id]); };
  const run = async () => { setNote(""); setError(""); if (invalid) { setError(selected.length < 2 ? "비교할 프리셋을 두 개 이상 고르세요." : start >= end ? "시작일이 종료일보다 앞서야 합니다." : !Number.isFinite(Number(initialValue)) || Number(initialValue) <= 0 ? "초기 금액은 0보다 커야 합니다." : "벤치마크 티커를 입력하세요."); return; } setBusy("run"); try { const payload = await postJson<BacktestComparison>("/api/portfolio/backtests/compare", { presetIds: selected, start, end, rebalance, baseCurrency, initialValue: Number(initialValue), benchmark: benchmark.trim() }); setResult(isComparison(payload) ? payload : null); if (!isComparison(payload)) setError("비교 결과 형식을 확인하지 못했습니다."); } catch (reason) { setError(backtestErrorMessage(reason, "비교 백테스트를 실행하지 못했습니다.")); } finally { setBusy(""); } };
  const save = async () => { if (!result) return; setBusy("save"); try { await postJson("/api/portfolio/backtests/save", result); setNote("비교 결과를 저장했습니다. 백테스트 탭의 저장한 결과에서 다시 열 수 있습니다."); } catch (reason) { setError(backtestErrorMessage(reason, "저장하지 못했습니다.")); } finally { setBusy(""); } };
  if (usable.length < 2) return <p className="portfolio-empty">비교하려면 비중이 담긴 프리셋이 2개 이상 필요합니다. 위에서 프리셋을 하나 더 만드세요.</p>;
  return <div className="portfolio-compare"><div className="portfolio-compare-picker" role="group" aria-label="비교할 프리셋">{usable.map((preset) => <label className="portfolio-compare-option" key={preset.id}><input type="checkbox" disabled={!!busy} checked={selected.includes(preset.id)} onChange={() => toggle(preset.id)} /><span>{preset.name}</span><small>{preset.positions.length}종목</small></label>)}</div>
    <div className="portfolio-backtest-fields"><label className="field"><span>시작</span><input disabled={!!busy} type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label><label className="field"><span>종료</span><input disabled={!!busy} type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label><label className="field"><span>기준 통화</span><select disabled={!!busy} value={baseCurrency} onChange={(event) => setBaseCurrency(event.target.value)}><option value="USD">USD</option><option value="KRW">KRW</option></select></label><label className="field"><span>초기 금액</span><input disabled={!!busy} type="number" min="0.01" step="0.01" inputMode="decimal" value={initialValue} onChange={(event) => setInitialValue(event.target.value)} /></label><label className="field"><span>벤치마크</span><input disabled={!!busy} value={benchmark} onChange={(event) => setBenchmark(event.target.value.toUpperCase())} spellCheck={false} /></label><div className="field"><span id="compareRebalanceLabel">리밸런싱</span><div className="segment" role="group" aria-labelledby="compareRebalanceLabel">{REBALANCE.map((item) => <button type="button" disabled={!!busy} key={item.id} aria-pressed={rebalance === item.id} onClick={() => setRebalance(item.id)}>{item.label}</button>)}</div></div></div>
    <div className="portfolio-compare-actions"><button className="btn btn--primary" type="button" onClick={() => void run()} disabled={!!busy}>{busy === "run" ? "비교하는 중" : `${selected.length || 0}개 비교 백테스트`}</button>{result && <button className="btn" type="button" onClick={() => void save()} disabled={!!busy}>{busy === "save" ? "저장 중" : "결과 저장"}</button>}{selected.length === 1 && <span className="section-subtitle">두 개 이상 골라야 비교할 수 있습니다.</span>}</div>
    {error && <p className="react-dashboard-error" role="alert">{error}</p>}{note && <p className="section-subtitle" role="status">{note}</p>}{result && <BacktestComparisonReport result={result} />}
  </div>;
}
