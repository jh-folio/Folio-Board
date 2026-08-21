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
  readonly quantity?: number;
  readonly averagePrice?: number;
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
};

export type CurrencyBucket = {
  readonly currency: string;
  readonly marketValue: number;
  readonly cost: number;
  readonly pnl: number;
  readonly pnlPct: number | null;
  readonly positions: number;
  readonly baseCurrency?: string;
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
  readonly marketValue: number;
  readonly pnl: number;
  readonly positions: number;
  readonly weight: number;
  readonly pnlPct: number | null;
};

export type TargetRow = {
  readonly id?: string;
  readonly ticker: string;
  readonly name?: string;
  readonly currentWeight: number;
  readonly targetWeight: number;
  readonly diffWeight: number;
  readonly diffAmountUsd: number;
  readonly marketValueUsd: number;
};

export type PortfolioComment = {
  readonly level: "info" | "warn" | string;
  readonly title: string;
  readonly body: string;
};

export type PortfolioAnalytics = PortfolioSummary & {
  readonly analytics: {
    readonly baseCurrency: string;
    readonly totalMarketValue: number;
    readonly totalCost: number;
    readonly totalPnl: number;
    readonly totalPnlPct: number | null;
    readonly positionWeights: ReadonlyArray<PositionRow & { weight?: number }>;
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
  readonly name: string;
  readonly baseCurrency?: string;
  readonly positions: ReadonlyArray<{ ticker: string; name?: string; weight: number }>;
  readonly weightTotal?: number;
  readonly updatedAt?: string;
};

export type BacktestMetrics = Readonly<Record<string, number>>;

export type BacktestResult = {
  readonly id: string;
  readonly name?: string;
  readonly presetId?: string;
  readonly presetName?: string;
  readonly start: string;
  readonly end: string;
  readonly baseCurrency: string;
  readonly initialValue: number;
  readonly rebalance: string;
  readonly benchmark?: { ticker?: string; name?: string };
  readonly metrics: BacktestMetrics;
  readonly series: ReadonlyArray<{ date: string; value: number }>;
  readonly benchmarkSeries?: ReadonlyArray<{ date: string; value: number }>;
  readonly yearlyReturns?: ReadonlyArray<{ period: string; return: number }>;
  readonly assetContributions?: ReadonlyArray<{ ticker: string; name?: string; weight: number; contribution?: number }>;
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
  readonly results: ReadonlyArray<BacktestResult>;
  readonly errors?: ReadonlyArray<{ presetId?: string; presetName?: string; error?: string }>;
  readonly assumptions?: ReadonlyArray<string>;
  readonly createdAt?: string;
  readonly savedAt?: string;
};

export function isComparison(value: BacktestResult | BacktestComparison | null): value is BacktestComparison {
  return Boolean(value && (value as BacktestComparison).type === "comparison");
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
