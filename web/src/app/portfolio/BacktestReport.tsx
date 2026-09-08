import { BacktestChart, type BacktestChartSeries, type ChartTone } from "./BacktestChart";
import { backtestMetric, backtestMetricReason, money, percent, signOf, type BacktestCoverage, type BacktestPoint, type BacktestResult } from "./portfolioTypes";

const CORE_METRICS: ReadonlyArray<{ key: string; label: string; kind: "pct" | "num" }> = [
  { key: "totalReturn", label: "총 수익률", kind: "pct" }, { key: "cagr", label: "연평균(CAGR)", kind: "pct" },
  { key: "maxDrawdown", label: "최대 낙폭", kind: "pct" }, { key: "volatility", label: "변동성", kind: "pct" },
  { key: "sharpe", label: "샤프", kind: "num" }, { key: "excessReturn", label: "벤치마크 차이", kind: "pct" },
];

function metricText(result: BacktestResult, key: string, kind: "pct" | "num") {
  const value = backtestMetric(result, key);
  return value === null ? "계산 불가" : kind === "pct" ? percent(value) : value.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

function reasonText(reason: string | null): string {
  if (!reason) return "이전 저장본에는 이 지표 또는 계산 불가 사유가 없습니다.";
  const known: Record<string, string> = {
    insufficient_observations: "관측일이 부족합니다.", benchmark_unavailable: "비교 가능한 벤치마크 자료가 없습니다.", no_common_benchmark_period: "포트폴리오와 벤치마크의 공통 기간이 없습니다.", zero_variance: "변동이 없어 계산할 수 없습니다.",
    portfolio_requires_at_least_two_valid_observations: "유효한 관측일이 두 개 이상 필요합니다.", portfolio_start_or_end_value_unavailable: "시작 또는 종료 평가액을 계산하지 못했습니다.", cagr_requires_positive_start_end_values_and_positive_calendar_span: "CAGR에는 양(+)의 시작·종료값과 기간이 필요합니다.", cagr_overflow_or_domain_error_for_observed_values: "관측값 범위 때문에 CAGR을 계산하지 못했습니다.", metric_requires_daily_returns: "일별 수익률 자료가 필요합니다.", volatility_requires_at_least_two_daily_returns: "변동성에는 일별 수익률이 두 개 이상 필요합니다.", sharpe_requires_nonzero_sample_daily_volatility: "샤프에는 0이 아닌 일별 변동성이 필요합니다.", downside_volatility_requires_daily_returns: "하방 변동성에는 일별 수익률이 필요합니다.", sortino_requires_nonzero_downside_volatility: "소르티노에는 0이 아닌 하방 변동성이 필요합니다.", calmar_requires_cagr_and_nonzero_max_drawdown: "칼마에는 CAGR과 0이 아닌 최대 낙폭이 필요합니다.", benchmark_has_no_comparable_two_observation_period: "벤치마크와 공통 관측일이 두 개 이상 필요합니다.", comparable_portfolio_or_benchmark_return_unavailable: "공통 기간의 포트폴리오 또는 벤치마크 수익률을 계산하지 못했습니다.", benchmark_metric_requires_at_least_two_aligned_daily_return_pairs: "벤치마크 지표에는 정렬된 일별 수익률 쌍이 두 개 이상 필요합니다.", beta_requires_nonzero_sample_benchmark_variance: "베타에는 0이 아닌 벤치마크 변동이 필요합니다.", alpha_requires_defined_beta: "알파에는 계산 가능한 베타가 필요합니다.", treynor_requires_defined_nonzero_beta: "트레이너에는 0이 아닌 베타가 필요합니다.", treynor_requires_nonzero_beta: "트레이너에는 0이 아닌 베타가 필요합니다.", correlation_requires_nonzero_sample_portfolio_and_benchmark_variance: "상관계수에는 포트폴리오와 벤치마크의 변동이 필요합니다.", r_squared_requires_defined_correlation: "결정계수에는 계산 가능한 상관계수가 필요합니다.", tracking_error_requires_at_least_two_aligned_active_returns: "추적 오차에는 정렬된 초과 수익률이 두 개 이상 필요합니다.", information_ratio_requires_nonzero_tracking_error: "정보비율에는 0이 아닌 추적 오차가 필요합니다.", up_capture_requires_positive_benchmark_return_days: "상승 캡처에는 벤치마크 상승일이 필요합니다.", down_capture_requires_negative_benchmark_return_days: "하락 캡처에는 벤치마크 하락일이 필요합니다.", insufficient_period_or_daily_return_observations: "기간 또는 일별 수익률 관측이 부족합니다.", benchmark_data_unavailable: "벤치마크 가격 자료를 읽지 못했습니다.",
  };
  return known[reason] || "계산에 필요한 자료가 부족해 이 지표를 계산하지 못했습니다.";
}

function rolling(result: BacktestResult, key: "rollingReturn" | "rollingVolatility" | "rollingBeta"): BacktestPoint[] {
  return (result.rollingMetrics || []).flatMap((row) => typeof row[key] === "number" && Number.isFinite(row[key]) ? [{ date: row.date, value: row[key] as number }] : []);
}

function rebalanceLabel(value: string): string { return ({ none: "리밸런싱 안 함", monthly: "매월 리밸런싱", quarterly: "분기 리밸런싱", yearly: "매년 리밸런싱" } as Record<string, string>)[value] || "리밸런싱 조건 미기록"; }
function calculationText(value: string | undefined, kind: "return" | "alignment" | "volatility" | "sharpe" | "alpha"): string {
  const tables: Record<string, Record<string, string>> = {
    return: { adjusted_close_daily: "조정 종가를 바탕으로 일별 수익률을 계산합니다." },
    alignment: { native_price_forward_fill_then_asof_fx_mark_no_reweighting: "첫 관측 뒤 가격 공백만 직전 값으로 이어가고, 환율은 각 시뮬레이션일의 직전 관측값을 적용합니다. 비중은 공백 때문에 다시 맞추지 않습니다." },
    volatility: { sample_standard_deviation_of_daily_returns_annualized: "일별 수익률의 표본 표준편차를 연율화합니다." },
    sharpe: { arithmetic_mean_daily_excess_return_annualized_over_sample_volatility: "일별 초과수익률의 산술평균을 연율화한 뒤 표본 변동성으로 나눕니다.", annualized_excess_return_over_volatility: "연율화 초과수익률을 변동성으로 나눕니다." },
    alpha: { arithmetic_annualized_capm_excess_return: "일별 수익률을 산술 연율화하고 무위험수익률 0%의 CAPM 초과수익률로 계산합니다.", capm_rf_zero: "무위험수익률 0%를 둔 CAPM 기준으로 계산합니다." },
  };
  return value ? tables[kind][value] || "계산 방식이 기록되었지만 화면용 설명이 아직 없습니다." : "계산 방식이 기록되지 않았습니다.";
}

export function resultChartSeries(result: BacktestResult, tone: ChartTone = "portfolio"): BacktestChartSeries {
  return { id: result.id, label: result.presetName || result.name || "포트폴리오", points: result.series || [], tone };
}

function safeUrl(value: string | undefined): string | null {
  if (!value) return null;
  try { const url = new URL(value); return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null; } catch { return null; }
}

function MetricCards({ result }: { readonly result: BacktestResult }) {
  return <div className="portfolio-metrics portfolio-metrics--compact">
    {CORE_METRICS.map((metric) => {
      const value = backtestMetric(result, metric.key);
      const reason = value === null ? reasonText(backtestMetricReason(result, metric.key)) : null;
      return <div key={metric.key} className="portfolio-metric" data-sign={metric.kind === "pct" && metric.key !== "volatility" && metric.key !== "maxDrawdown" ? signOf(value) : undefined}>
        <span>{metric.label}</span><strong>{metricText(result, metric.key, metric.kind)}</strong>{reason && <small>{reason}</small>}
      </div>;
    })}
  </div>;
}

function ContributionTables({ result }: { readonly result: BacktestResult }) {
  const contributions = result.assetContributions || [];
  const risk = result.riskContributions || [];
  if (!contributions.length && !risk.length) return <p className="portfolio-chart-empty">기여도 자료가 없는 이전 저장본입니다.</p>;
  return <div className="portfolio-report-grid">
    {contributions.length > 0 && <div><h4>성과 기여</h4><p className="portfolio-note">{result.contributionMethod === "actual_simulation_increment_over_initial_value" ? "실제 시뮬레이션의 기간별 증분을 초기 금액으로 나눈 값입니다." : "실제 시뮬레이션 기여도 방식이 없는 저장본입니다. 초기 비중에 자산 수익률을 곱한 근사치일 수 있습니다."}</p><div className="portfolio-table-scroll"><table className="portfolio-mini-table"><thead><tr><th scope="col">종목</th><th scope="col">비중</th><th scope="col">기여</th></tr></thead><tbody>{contributions.map((row) => <tr key={row.ticker}><th scope="row">{row.name || row.ticker}</th><td>{percent(row.weight)}</td><td data-sign={signOf(row.contribution)}>{percent(row.contribution)}</td></tr>)}</tbody></table></div></div>}
    {risk.length > 0 && <div><h4>위험 기여</h4><p className="portfolio-note">{result.riskContributionMethod === "static_target_weight_sample_covariance_approximation" ? "목표 비중과 표본 공분산으로 근사한 변동성·베타 기여도입니다." : "위험 기여도의 계산 방식 정보가 없는 저장본입니다."}</p><div className="portfolio-table-scroll"><table className="portfolio-mini-table"><thead><tr><th scope="col">종목</th><th scope="col">변동성 비중</th><th scope="col">베타 기여</th></tr></thead><tbody>{risk.map((row) => <tr key={row.ticker}><th scope="row">{row.name || row.ticker}</th><td>{percent(row.volatilityShare)}</td><td>{row.betaContribution === null || row.betaContribution === undefined ? "계산 불가" : row.betaContribution.toFixed(2)}</td></tr>)}</tbody></table></div></div>}
  </div>;
}

function Details({ result }: { readonly result: BacktestResult }) {
  const coverage = result.dataCoverage;
  return <details className="portfolio-report-details"><summary>기간별 수익률·rolling 지표·자료 기준 보기</summary>
    <div className="portfolio-report-details__body">
      <div className="portfolio-report-grid">
        <BacktestChart title="Rolling 12개월 수익률" description="최근 252 거래일 누적 수익률입니다." series={rolling(result, "rollingReturn").length ? [{ id: "return", label: "12개월 수익률", points: rolling(result, "rollingReturn"), tone: "portfolio" }] : []} kind="percent" emptyMessage="Rolling 수익률 자료가 없습니다." />
        <BacktestChart title="Rolling 변동성" description="최근 252 거래일 연율화 변동성입니다." series={rolling(result, "rollingVolatility").length ? [{ id: "volatility", label: "변동성", points: rolling(result, "rollingVolatility"), tone: "teal" }] : []} kind="percent" emptyMessage="Rolling 변동성 자료가 없습니다." />
        <BacktestChart title="Rolling 베타" description="최근 252 거래일 벤치마크 대비 베타입니다." series={rolling(result, "rollingBeta").length ? [{ id: "beta", label: "베타", points: rolling(result, "rollingBeta"), tone: "purple" }] : []} kind="number" emptyMessage="비교 가능한 벤치마크 기간이 없어 Rolling 베타를 계산하지 못했습니다." />
      </div>
      <div className="portfolio-report-grid">
        <PeriodTable title="연도별 수익률" rows={result.yearlyReturns || []} /> <PeriodTable title="월별 수익률" rows={result.monthlyReturns || []} />
      </div>
      <AdvancedMetrics result={result} />
      <Coverage result={result} coverage={coverage} />
    </div>
  </details>;
}

const ADVANCED_METRIC_GROUPS: ReadonlyArray<{ readonly title: string; readonly metrics: ReadonlyArray<{ readonly key: string; readonly label: string; readonly kind: "pct" | "num" }> }> = [
  { title: "수익률 분포", metrics: [{ key: "annualizedReturn", label: "연율화 수익률", kind: "pct" }, { key: "bestYear", label: "최고 연도", kind: "pct" }, { key: "worstYear", label: "최저 연도", kind: "pct" }, { key: "positiveYearRatio", label: "양(+) 연도 비율", kind: "pct" }, { key: "worstMonth", label: "최저 월", kind: "pct" }] },
  { title: "하방 위험", metrics: [{ key: "downsideVolatility", label: "하방 변동성", kind: "pct" }, { key: "averageDrawdown", label: "평균 낙폭", kind: "pct" }, { key: "var95", label: "VaR 95%", kind: "pct" }, { key: "cvar95", label: "CVaR 95%", kind: "pct" }, { key: "maxDrawdownDays", label: "최장 낙폭 거래일", kind: "num" }] },
  { title: "위험 조정", metrics: [{ key: "sortino", label: "소르티노", kind: "num" }, { key: "calmar", label: "칼마", kind: "num" }] },
  { title: "벤치마크 민감도", metrics: [{ key: "alpha", label: "알파", kind: "pct" }, { key: "beta", label: "베타", kind: "num" }, { key: "correlation", label: "상관계수", kind: "num" }, { key: "informationRatio", label: "정보비율", kind: "num" }, { key: "trackingError", label: "추적 오차", kind: "pct" }, { key: "upCapture", label: "상승 캡처", kind: "num" }, { key: "downCapture", label: "하락 캡처", kind: "num" }] },
];

function AdvancedMetrics({ result }: { readonly result: BacktestResult }) {
  return <details className="portfolio-advanced-metrics"><summary>추가 성과·위험 지표 보기</summary><div className="portfolio-advanced-metrics__body">{ADVANCED_METRIC_GROUPS.map((group) => <section key={group.title}><h4>{group.title}</h4><dl>{group.metrics.map((metric) => { const value = backtestMetric(result, metric.key); return <div key={metric.key}><dt>{metric.label}</dt><dd>{metricText(result, metric.key, metric.kind)}{value === null && <small>{reasonText(backtestMetricReason(result, metric.key))}</small>}</dd></div>; })}</dl></section>)}</div></details>;
}

function PeriodTable({ title, rows }: { readonly title: string; readonly rows: ReadonlyArray<{ period: string; return: number | null; partial?: boolean }> }) {
  return <section className="portfolio-period-table"><h4>{title}</h4>{rows.length ? <div className="portfolio-table-scroll" role="region" aria-label={`${title} 표`} tabIndex={0}><table className="portfolio-mini-table"><thead><tr><th scope="col">기간</th><th scope="col">수익률</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><th scope="row">{row.period}{row.partial ? <small className="portfolio-partial-label">부분 기간</small> : null}</th><td data-sign={signOf(row.return)}>{percent(row.return)}</td></tr>)}</tbody></table></div> : <p className="portfolio-chart-empty">기간별 수익률 자료가 없습니다.</p>}</section>;
}

function coverageText(row: BacktestCoverage): string {
  // Old saved payloads can have a partial coverage object. Treat omitted nested
  // detail as unrecorded rather than letting a report reopen fail.
  const price = row.price;
  const fx = row.fx;
  const priceText = price ? `가격 관측 ${price.observedDays ?? "—"}일 / carry ${price.forwardFilledDays ?? "—"}일 / 종료 뒤 carry ${price.trailingForwardFilledDays ?? "—"}일 (${percent(price.coverage ?? null)})` : "가격 관측 범위 미기록";
  const fxText = !fx ? "환율 범위 미기록" : !fx.required ? "환율 불필요" : `환율 관측 ${fx.observedDays ?? "—"}일 / carry ${fx.forwardFilledDays ?? "—"}일 / 종료 뒤 carry ${fx.trailingForwardFilledDays ?? "—"}일 (${percent(fx.coverage ?? null)})`;
  const unavailable = Array.isArray(row.unavailableReasons) && row.unavailableReasons.length ? " · 계산 불가 사유 있음" : "";
  return `${row.ticker || row.symbol || "종목"}: 실제 ${row.actualStart || "—"} ~ ${row.actualEnd || "—"}, 시뮬레이션 ${row.simulationStart || "—"} ~ ${row.simulationEnd || "—"}; ${priceText}; ${fxText}${unavailable}`;
}

function Coverage({ result, coverage }: { readonly result: BacktestResult; readonly coverage: BacktestResult["dataCoverage"] }) {
  const sources = result.sources || [];
  const basis = result.calculationBasis;
  return <section className="portfolio-coverage"><h4>자료·계산 가정</h4>
    {basis ? <><p>무위험수익률은 연 {percent(basis.riskFreeRate?.annual)}로 고정했고, 연율화는 {basis.annualization?.tradingDays ?? "—"} 거래일 기준입니다. {calculationText(basis.returnMethod, "return")} {calculationText(basis.priceAlignment?.method, "alignment")} 변동성은 {calculationText(result.metrics.metricAssumptions?.volatilityMethod, "volatility")} 샤프는 {calculationText(result.metrics.metricAssumptions?.sharpeMethod, "sharpe")} 알파는 {calculationText(result.metrics.metricAssumptions?.alphaMethod, "alpha")}</p><details><summary>계산 방식 코드 보기</summary><p className="portfolio-note">수익률 {basis.returnMethod || "—"} · 정렬 {basis.priceAlignment?.method || "—"} · 변동성 {result.metrics.metricAssumptions?.volatilityMethod || "—"} · 샤프 {result.metrics.metricAssumptions?.sharpeMethod || "—"} · 알파 {result.metrics.metricAssumptions?.alphaMethod || "—"}</p></details></> : <p className="portfolio-chart-empty">이전 저장본에는 계산 기준이 기록되지 않았습니다. 현재 결과로 추정하거나 다시 계산하지 않습니다.</p>}
    {basis?.priceAlignment && <p className="portfolio-note">요청 기간 {result.requestedStart || result.start} ~ {result.requestedEnd || result.end}; 시뮬레이션 기간 {basis.priceAlignment.simulationStart || result.start} ~ {basis.priceAlignment.simulationEnd || result.end}; 모든 종목의 실제 공통 관측 기간 {basis.priceAlignment.strictCommonObservedStart || "없음"} ~ {basis.priceAlignment.strictCommonObservedEnd || "없음"} ({basis.priceAlignment.strictCommonObservedDays ?? 0}일)입니다.</p>}
    {coverage?.positions?.length ? <ul>{coverage.positions.map((row) => <li key={row.symbol}>{coverageText(row)}</li>)}</ul> : <p className="portfolio-note">이전 저장본에는 종목별 관측 범위가 없습니다.</p>}
    {coverage?.benchmark && <p className="portfolio-note">벤치마크 {coverageText(coverage.benchmark)}</p>}
    {sources.length > 0 && <ul className="portfolio-sources">{sources.map((source, index) => { const url = safeUrl(source.url); const label = [source.ticker || source.symbol, source.source].filter(Boolean).join(" · ") || "자료 출처"; return <li key={`${label}-${index}`}>{url ? <a href={url} target="_blank" rel="noreferrer">{label}</a> : label}</li>; })}</ul>}
    {(result.assumptions || []).length > 0 && <ul>{result.assumptions?.map((line, index) => <li key={index}>{line}</li>)}</ul>}
  </section>;
}

export function BacktestResultReport({ result, title, tone = "portfolio" }: { readonly result: BacktestResult; readonly title?: string; readonly tone?: ChartTone }) {
  const benchmarkUnavailable = result.benchmarkComparison?.status === "unavailable";
  const benchmarkOverlaySafe = result.benchmarkComparison?.status === "comparable" && result.benchmarkComparison.comparisonStart === result.start && result.benchmarkComparison.comparisonEnd === result.end;
  const drawdown = (result.drawdownSeries || []).map((row) => ({ date: row.date, value: row.drawdown }));
  const worst = (result.drawdownEpisodes || []).slice().sort((left, right) => left.maxDrawdown - right.maxDrawdown)[0];
  const duration = (value: unknown): string | null => typeof value === "number" && Number.isFinite(value) ? `${value}일` : null;
  const unrecoveredSummary = worst && duration(worst.underwaterTradingDays) ? `결과 종료일 기준 ${duration(worst.underwaterTradingDays)}째 이전 고점을 회복하지 못했습니다.` : "결과 종료일 기준 이전 고점을 회복하지 못했습니다.";
  return <div className="portfolio-backtest-report">
    <header className="portfolio-backtest-result-head"><div><h3>{title || result.presetName || result.name || "백테스트 결과"}</h3><p>{result.start} ~ {result.end} · {result.baseCurrency} · 시작 {money(result.initialValue)} · {result.benchmark?.ticker || "벤치마크 미기록"} · {rebalanceLabel(result.rebalance)}</p></div><span className="chip">실행 조건 고정</span></header>
    <MetricCards result={result} />
    <BacktestChart title="누적 성과" description="실행 조건에서 시작한 평가액 추이입니다." series={[resultChartSeries(result, tone), ...(benchmarkOverlaySafe && result.benchmarkSeries?.length ? [{ id: `${result.id}-benchmark`, label: result.benchmark?.ticker || "벤치마크", points: result.benchmarkSeries, tone: "benchmark" as const, pattern: "dashed" as const }] : [])]} />
    <BacktestChart title="낙폭" description="이전 최고점 대비 하락률입니다." series={drawdown.length ? [{ id: `${result.id}-drawdown`, label: "낙폭", points: drawdown, tone: "burgundy" }] : []} kind="percent" emptyMessage="이전 저장본에는 낙폭 시계열이 없습니다." />
    {worst && <p className="portfolio-drawdown-summary">가장 깊은 낙폭은 {worst.peakDate} 고점부터 {worst.troughDate} 저점까지 {percent(worst.maxDrawdown)}였습니다{duration(worst.calendarDaysToTrough) ? ` (${duration(worst.calendarDaysToTrough)})` : ""}. {worst.recoveryDate ? `${worst.recoveryDate}에 이전 고점을 회복했고, 회복까지 ${duration(worst.calendarDaysToRecovery) || "기간 미기록"}이 걸렸습니다.` : unrecoveredSummary}</p>}
    <section className="portfolio-benchmark"><h4>벤치마크 비교</h4>{benchmarkUnavailable ? <p className="portfolio-chart-empty">비교 가능한 공통 기간이 없어 벤치마크 지표를 계산하지 못했습니다. {reasonText(result.benchmarkComparison?.reason || null)}</p> : <p>{result.benchmark?.ticker || "벤치마크"} 대비 초과 수익률은 {metricText(result, "excessReturn", "pct")}이고, 베타는 {metricText(result, "beta", "num")}입니다. 공통 기간: {result.benchmarkComparison?.comparisonStart || "이전 저장본에는 없음"} ~ {result.benchmarkComparison?.comparisonEnd || ""}.</p>}{result.benchmarkSeries?.length && !benchmarkOverlaySafe && <p className="portfolio-note">포트폴리오와 벤치마크의 시작 기준이 같다고 확인할 수 없어 누적 성과 차트에는 겹쳐 그리지 않았습니다.</p>}</section>
    {result.interpretation?.statements?.length ? <section className="portfolio-interpretation"><h4>숫자로 읽는 결과</h4><ul>{result.interpretation.statements.map((statement, index) => <li key={`${statement.topic}-${index}`} data-status={statement.status}><strong>{({ return_driver: "성과 요인", worst_loss: "가장 큰 손실", risk_concentration: "위험 집중", benchmark_tradeoff: "벤치마크와의 차이", rolling_vs_overall: "최근 구간과 전체 기간" } as Record<string, string>)[statement.topic] || "계산 결과"}</strong><span>{statement.text}</span></li>)}</ul><p className="portfolio-note">계산된 수치만 정리한 설명이며, 매수·매도나 비중 조정 지시가 아닙니다.</p></section> : null}
    <section className="portfolio-contributions"><h4>성과와 위험의 기여</h4><ContributionTables result={result} /></section>
    <Details result={result} />
    <p className="portfolio-note">리서치용 계산입니다. 과거 가격과 환율을 사용하며 세금·수수료·체결오차는 반영하지 않습니다. 과거 성과는 미래 결과를 보장하지 않습니다.</p>
  </div>;
}
