/** 포트폴리오 API가 돌려주는 모양.
 *
 *  백엔드는 처음부터 다 있었고 화면만 없었다. 여기 있는 필드는 전부 실제 응답에서
 *  확인한 것이다 — 추측으로 만든 필드는 없다.
 */

export type PositionRow = {
  readonly id?: string;
  readonly ticker: string;
  readonly symbol?: string;
  readonly name?: string;
  readonly market?: string;
  readonly quantity?: string;
  readonly averagePrice?: string;
  readonly currency?: string;
  readonly sector?: string;
  readonly assetClass?: string;
  readonly currentPrice?: number | null;
  readonly marketValueUsd?: number | null;
  readonly costUsd?: number | null;
  readonly pnlUsd?: number | null;
  readonly pnlPct?: number | null;
  readonly weight?: number | null;
  readonly quoteOk?: boolean;
  readonly quoteError?: string;
  readonly calculationUnavailable?: ReadonlyArray<string>;
};

export type CurrencyBucket = {
  readonly currency: string;
  readonly marketValue: number | null;
  readonly cost: number | null;
  readonly pnl: number | null;
  readonly pnlPct: number | null;
  readonly positions: number;
  readonly baseCurrency?: string;
  readonly calculationUnavailable?: ReadonlyArray<string>;
};

export type CashRow = { readonly currency: string; readonly amount: number };

export type PortfolioSummary = {
  readonly positions: ReadonlyArray<PositionRow>;
  readonly summary: ReadonlyArray<CurrencyBucket>;
  readonly cash: ReadonlyArray<CashRow>;
  readonly baseCurrency: string;
  readonly fxRates: Record<string, { rateToUsd: number; source: string }>;
  readonly updatedAt?: string;
};

export type WeightSlice = {
  readonly label: string;
  readonly marketValue: number | null;
  readonly pnl: number | null;
  readonly positions: number;
  readonly weight: number | null;
  readonly pnlPct: number | null;
  readonly calculationUnavailable?: ReadonlyArray<string>;
};

export type TargetRow = {
  readonly id?: string;
  readonly ticker: string;
  readonly name?: string;
  readonly currentWeight: number | null;
  readonly targetWeight: number;
  readonly diffWeight: number | null;
  readonly diffAmountUsd: number | null;
  readonly marketValueUsd: number | null;
};

export type PortfolioComment = {
  readonly level: "info" | "warn" | string;
  readonly title: string;
  readonly body: string;
};

export type PortfolioAnalytics = PortfolioSummary & {
  readonly analytics: {
    readonly baseCurrency: string;
    readonly totalMarketValue: number | null;
    readonly totalCost: number | null;
    readonly totalPnl: number | null;
    readonly totalPnlPct: number | null;
    readonly positionWeights: ReadonlyArray<PositionRow & { weight?: number | null }>;
    readonly sectorWeights: ReadonlyArray<WeightSlice>;
    readonly marketWeights: ReadonlyArray<WeightSlice>;
    readonly currencyWeights: ReadonlyArray<WeightSlice>;
    readonly assetClassWeights: ReadonlyArray<WeightSlice>;
    readonly pnlContributors: ReadonlyArray<PositionRow>;
    readonly targetWeights: {
      readonly items: ReadonlyArray<TargetRow>;
      readonly targetTotal: number;
      readonly targetGap: number;
      readonly hasTargets: boolean;
    };
    readonly concentration: {
      readonly top1: number | null;
      readonly top3: number | null;
      readonly top5: number | null;
      readonly holdings: number;
    };
    readonly comments: ReadonlyArray<PortfolioComment>;
  };
};

export type Preset = {
  readonly id: string;
  /** 프리셋별 CAS 버전. legacy 저장본은 API projection에서 0으로 읽힌다. */
  readonly revision: number;
  readonly name: string;
  readonly baseCurrency?: "USD" | "KRW";
  readonly positions: ReadonlyArray<{ ticker: string; name?: string; weight: number }>;
  readonly weightTotal?: number;
  readonly updatedAt?: string;
};

/** `from-current`은 파일을 쓰지 않는 편집 초안이다. */
export type PresetFromCurrentDraft = {
  readonly draft: true;
  readonly name: string;
  readonly baseCurrency: "USD" | "KRW";
  readonly positions: ReadonlyArray<{ ticker: string; name?: string; weight: number }>;
  readonly weightTotal?: number;
  readonly warnings?: ReadonlyArray<{ code: string; ticker?: string; message: string }>;
};

/** 새 계산 결과는 숫자 지표와 그 계산 전제를 함께 돌려준다. 이전 저장본은 숫자만 가진다. */
export type BacktestMetricAssumptions = {
  readonly tradingDaysPerYear?: number;
  readonly riskFreeRateAnnual?: number;
  readonly riskFreeRateSource?: string;
  readonly volatilityMethod?: string;
  readonly sharpeMethod?: string;
  readonly alphaMethod?: string;
};

export type BacktestMetrics = Readonly<Record<string, unknown>> & {
  readonly metricAssumptions?: BacktestMetricAssumptions;
  readonly metricUnavailableReasons?: Readonly<Record<string, string>>;
};

export type BacktestPoint = { readonly date: string; readonly value: number };

export type BacktestCoverage = {
  readonly ticker?: string;
  readonly symbol: string;
  readonly currency?: string;
  readonly included: boolean;
  readonly actualStart: string | null;
  readonly actualEnd: string | null;
  readonly simulationStart: string | null;
  readonly simulationEnd: string | null;
  readonly price: { readonly observedDays: number; readonly forwardFilledDays: number; readonly trailingForwardFilledDays: number; readonly coverage: number | null; readonly nativePrice?: boolean };
  readonly fx: { readonly required: boolean; readonly fromCurrency?: string; readonly toCurrency?: string; readonly observedDays: number; readonly forwardFilledDays: number; readonly trailingForwardFilledDays: number; readonly coverage: number | null; readonly unavailableReason?: string | null; readonly nativePrice?: boolean };
  readonly unavailableReasons: ReadonlyArray<string>;
};

export type BacktestCalculationBasis = {
  readonly riskFreeRate?: { readonly annual?: number; readonly source?: string; readonly method?: string };
  readonly annualization?: { readonly tradingDays?: number };
  readonly returnMethod?: string;
  readonly priceAlignment?: { readonly method?: string; readonly simulationStart?: string; readonly simulationEnd?: string; readonly observations?: number; readonly strictCommonObservedStart?: string | null; readonly strictCommonObservedEnd?: string | null; readonly strictCommonObservedDays?: number };
  readonly periodReturnMethod?: string;
};

export type BacktestInterpretation = {
  readonly method?: string;
  readonly isAdvice?: boolean;
  readonly statements?: ReadonlyArray<{ readonly topic: string; readonly status: "available" | "unavailable"; readonly facts?: Readonly<Record<string, unknown>>; readonly text: string }>;
};

export type BacktestResult = {
  readonly id: string;
  readonly name?: string;
  readonly presetId?: string;
  readonly presetName?: string;
  readonly start: string;
  readonly end: string;
  readonly requestedStart?: string;
  readonly requestedEnd?: string;
  readonly baseCurrency: string;
  readonly initialValue: number;
  readonly rebalance: string;
  readonly benchmark?: { ticker?: string; name?: string };
  readonly metrics: BacktestMetrics;
  readonly series: ReadonlyArray<BacktestPoint>;
  readonly benchmarkSeries?: ReadonlyArray<BacktestPoint>;
  readonly yearlyReturns?: ReadonlyArray<{ period: string; return: number | null; partial?: boolean }>;
  readonly monthlyReturns?: ReadonlyArray<{ period: string; return: number | null; partial?: boolean }>;
  readonly assetContributions?: ReadonlyArray<{ ticker: string; name?: string; weight: number; contribution?: number }>;
  readonly riskContributions?: ReadonlyArray<{ ticker: string; name?: string; weight?: number; volatilityContribution?: number | null; volatilityShare?: number | null; assetBeta?: number | null; betaContribution?: number | null }>;
  readonly rollingMetrics?: ReadonlyArray<{ date: string; rollingReturn?: number | null; rollingVolatility?: number | null; rollingBeta?: number | null; window?: number }>;
  readonly analysisVersion?: string;
  readonly calculationBasis?: BacktestCalculationBasis;
  readonly dataCoverage?: { readonly status?: string; readonly positions?: ReadonlyArray<BacktestCoverage>; readonly benchmark?: BacktestCoverage | null; readonly unavailableMetrics?: ReadonlyArray<{ readonly metric?: string; readonly reason?: string }> };
  readonly drawdownSeries?: ReadonlyArray<{ readonly date: string; readonly drawdown: number; readonly peakDate?: string }>;
  readonly drawdownEpisodes?: ReadonlyArray<{ readonly peakDate: string; readonly troughDate: string; readonly recoveryDate: string | null; readonly maxDrawdown: number; readonly status: "recovered" | "unrecovered"; readonly underwaterTradingDays: number; readonly calendarDaysToTrough: number | null; readonly calendarDaysToRecovery: number | null }>;
  readonly benchmarkComparison?: { readonly status?: "comparable" | "unavailable"; readonly comparisonStart?: string | null; readonly comparisonEnd?: string | null; readonly observations?: number; readonly reason?: string };
  readonly contributionMethod?: string;
  readonly riskContributionMethod?: string;
  readonly interpretation?: BacktestInterpretation;
  readonly sources?: ReadonlyArray<{ readonly ticker?: string; readonly symbol?: string; readonly source?: string; readonly url?: string }>;
  readonly assumptions?: ReadonlyArray<string>;
  readonly savedAt?: string;
};

/** 프리셋 여러 개를 나란히 돌린 결과.
 *
 * 서버는 예전부터 이걸 만들 수 있었다(`POST /api/portfolio/backtests/compare`) —
 * 부르는 화면만 없었다. 한 프리셋이 실패해도 나머지는 돌아오고, 실패한 것은
 * `errors`에 남는다(부분 실패 허용).
 */
export type BacktestComparison = {
  readonly type: "comparison";
  readonly id: string;
  readonly name?: string;
  readonly start: string;
  readonly end: string;
  readonly baseCurrency: string;
  readonly initialValue: number;
  readonly rebalance: string;
  readonly benchmark?: { readonly ticker?: string; readonly name?: string };
  readonly results: ReadonlyArray<BacktestResult>;
  readonly errors?: ReadonlyArray<{ presetId?: string; presetName?: string; error?: string }>;
  readonly assumptions?: ReadonlyArray<string>;
  readonly createdAt?: string;
  readonly savedAt?: string;
};

/** 목록 API는 비교 안의 모든 시계열을 보내지 않는다. 열기 API만 full payload를 돌려준다. */
export type BacktestComparisonSummary = Omit<BacktestComparison, "results"> & {
  readonly results?: ReadonlyArray<BacktestResult>;
  readonly resultCount?: number;
};

export function isComparison(value: BacktestResult | BacktestComparison | null): value is BacktestComparison {
  return Boolean(value && (value as BacktestComparison).type === "comparison" && Array.isArray((value as BacktestComparison).results));
}

export function isComparisonSummary(value: BacktestResult | BacktestComparison | BacktestComparisonSummary): value is BacktestComparisonSummary {
  return (value as BacktestComparisonSummary).type === "comparison";
}

/** 통화 기호 없이 자릿수만 맞춘다. 통화는 라벨이 따로 말한다. */
export function money(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("ko-KR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** 손익 부호. 0은 어느 쪽도 아니다. */
export function signOf(value: number | null | undefined): "up" | "down" | "flat" {
  if (value === null || value === undefined || !Number.isFinite(value) || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

/** API가 없는 값을 0으로 둔갑시키지 않도록 숫자 필드를 읽는 단일 경계. */
export function backtestMetric(result: Pick<BacktestResult, "metrics">, key: string): number | null {
  const value = result.metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function backtestMetricReason(result: Pick<BacktestResult, "metrics">, key: string): string | null {
  const reason = result.metrics.metricUnavailableReasons?.[key];
  return typeof reason === "string" && reason.trim() ? reason : null;
}
