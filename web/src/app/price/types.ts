// 가격 탭이 읽는 응답 형태. 서버(features/price_scenarios)의 계약을 그대로 옮긴 것이며,
// 숫자는 전부 문자열(Decimal)로 온다 — 화면에서 계산하지 않고 형식만 바꾼다.

export type Reason = { code: string; subCode?: string; range?: string; n?: number; required?: number; historyYears?: number };
export type Notice = string | { code: string; years?: number[]; class?: string };
export type Unavailable = { status: "unavailable"; reason: Reason };
export type PreviousMethod = { status: "not_applicable"; reason: { code: string } };
export type ReturnPart = ({ label: ScenarioRow["label"]; horizon: 5 | 10 } & Unavailable)
  | { label: ScenarioRow["label"]; horizon: 5 | 10; status: "available"; peNow: string; exitPE: string;
      growth: string; dividend: string; rerating: string; irrFlat: string };
export type NoGrowth = Unavailable | PreviousMethod | { status: "available"; value: string; growthShare: string;
  priceCoverage: string; requiredReturn: string; criteriaRevisionId: number; hasGrowthShare: boolean };
export type CashConversion = (Unavailable | { status: "available"; ratio: string;
  class: "cash_below_earnings" | "cash_in_line" | "cash_above_earnings" }) & {
    currency?: string; years?: { fiscalYear: number; netIncome: string; ocf: string; capexRaw: string; capexOut: string; sbc?: string; fcf: string }[];
    sumNetIncome?: string; sumFcf?: string; sbcBasis?: "deducted" | "not_deducted" | "not_applicable_kr";
    notices?: { code: string; years?: number[] }[];
  } | PreviousMethod;

export type ReferenceYear = { fiscalYear: number; revenue: string | null; revenueGrowth: string | null;
  netMargin: string | null; fcf: string | null; fcfMargin: string | null; reasons: Partial<Record<"revenue" | "revenueGrowth" | "netMargin" | "fcf" | "fcfMargin", Reason>> };
export type ReferenceFacts = Unavailable | PreviousMethod | { status: "available"; currency: string;
  peNow: Unavailable | { status: "available"; state: "multiple" | "loss" | "zero"; value: string | null };
  psNow: Unavailable | { status: "available"; value: string }; years: ReferenceYear[];
  sbcBasis: string | null; notices: { code: string; years?: number[] }[] };

export type ScenarioRow =
  | ({ label: "conservative" | "base" | "optimistic"; horizon: 5 | 10; status: "available";
      g: string; exitPE: string; payout: string; irr: string | null; irrRange: "above_range" | "below_range" | null;
      percentiles: { g: number; exitPE: number; payout: number }; n: { g: number; exitPE: number; payout: number } })
  | ({ label: "conservative" | "base" | "optimistic"; horizon: 5 | 10 } & Unavailable);

export type RangeBlock = {
  status: "available" | "unavailable"; reason?: Reason;
  p25?: string; p50?: string; p75?: string; n?: number; values?: { fiscalYear: number; value: string }[];
};

export type DecompositionWindow = {
  start: number; end: number; R: string; M: string; S: string; total: string;
  annual: { R: string; M: string; S: string; total: string };
};

export type BreakEvenPE = { status: "available"; state: "needed" | "not_needed"; exitPE?: string } | Unavailable;
export type BreakEvenMargin =
  | { status: "available"; currentMargin: string; margin: string | null; marginRange: string | null;
      currentMarginPercentile?: string; marginPercentile?: string }
  | Unavailable;

export type SnapshotResults = {
  returnParts?: ReturnPart[] | PreviousMethod;
  noGrowth?: Unavailable | { status: "available"; rps0: string; marginP50: string; marginN: number; normEps: string; recentEps: string | null };
  cashConversion?: CashConversion;
  referenceFacts?: ReferenceFacts;
  support: { status: "supported" | "limited" | "unsupported"; reasons: Reason[]; notices: string[] };
  shareEvents?: { state: string };
  ranges: Record<"growth" | "pe" | "payout" | "rpsGrowth" | "netMargin", RangeBlock>;
  base: { status: "available"; fiscalYear: number; periodEnd: string; monthsBeforeSession: number; eps0: string } | Unavailable;
  scenarios: ScenarioRow[];
  decomposition: ({ status: "available"; windows: DecompositionWindow[]; notes: { code: string }[]; recentWindow: [number, number] } | Unavailable);
  reverse: { breakEvenPE: Record<string, BreakEvenPE>; breakEvenMargin: Record<string, BreakEvenMargin> };
  notices: Notice[];
  dcf?: { status: string; marginOfSafetyJudgment?: string; reason?: Reason };
};

export type SnapshotView = {
  snapshotId: string; instrumentId: string; asOf: string; computedAt: string; methodVersion: string; supportStatus: string;
  results: SnapshotResults;
  inputSummary: { asOf: string; identity: { ticker: string; market: string }; price: { value: string; sessionDate: string; currency: string } };
};

export type ChangeReason = { code: string; [key: string]: unknown };
export type HistoryRow = { snapshotId: string; asOf: string; computedAt: string; method: string; supersedes: string | null; reviewCount: number; changeReasons: ChangeReason[] };
export type Attempt = { status: "saved" | "failed"; reason?: Reason; snapshotId?: string; finishedAt?: string };
export type Overview = {
  instrumentId: string; latest: { snapshotId: string; asOf: string; computedAt: string; supportStatus: string } | null;
  history: HistoryRow[]; lastAttempt: Attempt | null;
};

export type Verdict = { state: "met" | "unmet" | "unknown"; reason?: string; horizon?: number; irr?: string; irrRange?: string; margin?: string; intrinsicValue?: string };
export type Requirement = {
  status: "available" | "unavailable"; reason?: Reason;
  exitPE?: Record<string, { status: string; state?: string; value?: string }>;
  growth?: Record<string, { status: string; value?: string; range?: string; percentile?: string | null }>;
  netMargin?: Record<string, { status: string; value?: string; range?: string; currentMargin?: string; percentile?: string | null }>;
};
export type MyAssumptions = {
  overrideId: number; basedOnSnapshotId: string; basedOnCurrentSnapshot: boolean;
  rows: { horizon: number; status: string; g?: string; exitPE?: string; payout?: string; irr?: string | null; irrRange?: string | null }[];
};
export type Projection = {
  noGrowth?: NoGrowth;
  snapshotId: string; asOf: string; ageDays: number; notices: string[];
  criteria: { revisionId: number; holdingYears: number | null; requiredReturn: string | null; minMarginOfSafety: string | null } | null;
  verdict: { return: Verdict; marginOfSafety: Verdict };
  requirement: Requirement; myAssumptions: MyAssumptions | null;
  reviewNeeded: { reason: string; metric: string; fiscalYear: number; detectedBySnapshotId: string }[];
};

export type Criteria = { revisionId: number; requiredReturn: string | null; minMarginOfSafety: string | null; holdingYears: number | null; createdAt: string };
export type Override = { overrideId: number; instrumentId: string; basedOnSnapshotId: string; growth: string | null; exitPE: string | null; payout: string | null };
