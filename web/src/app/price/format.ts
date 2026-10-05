import type { Attempt, Notice, Overview, Projection, Reason, ScenarioRow, SnapshotView } from "./types";

// 서버가 준 Decimal 문자열을 화면 글자로 바꾼다. 여기서 값을 새로 계산하지 않는다.

const MINUS = "−";

export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function pct(fraction: string | number | null | undefined, places = 1): string {
  const value = toNumber(fraction);
  if (value === null) return "—";
  const text = Math.abs(value * 100).toFixed(places);
  return `${value < 0 && Number(text) !== 0 ? MINUS : ""}${text}%`;
}

export function pctSigned(fraction: string | number | null | undefined, places = 1): string {
  const value = toNumber(fraction);
  if (value === null) return "—";
  const text = Math.abs(value * 100).toFixed(places);
  return `${value > 0 && Number(text) !== 0 ? "+" : value < 0 && Number(text) !== 0 ? MINUS : ""}${text}%`;
}

/** 이미 % 단위인 값(사용자 기준 저장값). */
export function pctPlain(percent: string | number | null | undefined, places = 0): string {
  const value = toNumber(percent);
  return value === null ? "—" : pct(value / 100, places);
}

export function multiple(value: string | number | null | undefined, places = 1): string {
  const parsed = toNumber(value);
  return parsed === null ? "—" : `${parsed.toFixed(places)}배`;
}

export function money(value: string | number | null | undefined, currency: string): string {
  const parsed = toNumber(value);
  if (parsed === null) return "—";
  const digits = Math.abs(parsed) >= 1000 ? 0 : 2;
  const text = Math.abs(parsed).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  // 음수는 기호를 통화 앞에 둔다("$-0.29"가 아니라 "−$0.29").
  const sign = parsed < 0 && Number(text.replace(/,/g, "")) !== 0 ? MINUS : "";
  return currency === "KRW" ? `${sign}${text}원` : currency === "USD" ? `${sign}$${text}` : `${sign}${text} ${currency}`;
}

export const REASON_TEXT: Record<string, string> = {
  "missing_value": "해당 연도의 공시 값이 없어 표시하지 않았습니다",
  "previous_method": "이 계산 기록에는 없는 항목입니다. 다시 계산하면 볼 수 있습니다",
  "non_positive_normalized_earnings": "과거 보통 이익률로 계산한 주당이익이 0 이하입니다",
  "required_return_not_positive": "내 요구수익률이 0 이하라 성장 없는 가치를 계산하지 않았습니다",
  "net_income_sum_not_positive": "대상 연도의 순이익 합이 0 이하라 현금 비율을 계산하지 않았습니다",
  "irr_above_range": "수익률이 계산 구간 상한을 넘어 세 조각으로 나누지 않았습니다",
  "irr_below_range": "수익률이 계산 구간 하한을 넘어 세 조각으로 나누지 않았습니다",
  "flat_irr_out_of_range": "PER이 그대로일 때 수익률이 계산 구간을 벗어납니다",
  "history_too_short": "과거 자료가 부족해 계산하지 않았습니다",
  "share_event_unknown": "주식 수가 바뀐 사건을 확인하지 못해 주당 계산을 하지 않았습니다",
  "price_event_unverified": "가격에 주식 수 변화가 반영됐는지 확인하지 못해 연말 PER을 쓰는 계산을 하지 않았습니다",
  "negative_base_eps": "최근 연도 주당이익이 0 이하라 수익률 계산을 하지 않았습니다",
  "base_eps_missing": "최근 회계연도의 희석 주당이익이 없어 계산하지 않았습니다",
  "stale_financials": "최근 재무제표가 15개월보다 오래돼 계산하지 않았습니다",
  "non_positive_revenue": "최근 매출이 0 이하라 계산하지 않았습니다",
  "adr_ratio_unverified": "ADR 비율을 공시에서 확인하지 못해 주당 계산을 하지 않았습니다",
  "currency_mismatch": "재무제표 통화와 주가 통화가 달라 환산 없이 비교하는 계산을 하지 않았습니다",
  "currency_unknown": "통화를 확인하지 못해 주당 계산을 하지 않았습니다",
  "share_unit_unknown": "주식 수 단위를 확인하지 못해 주당 계산을 하지 않았습니다",
  "share_unit_mismatch": "주식 수 단위가 맞지 않아 주당 계산을 하지 않았습니다",
  "non_common_listing": "보통주가 아닌 종목이라 주당 계산을 하지 않았습니다",
  "class_eps_differs": "주식 종류별 주당이익이 달라 주당 계산을 하지 않았습니다",
  "industry_not_supported": "이 업종은 이 계산 방식이 맞지 않아 지원하지 않습니다",
  "financial_holding": "금융지주는 이 계산 방식이 맞지 않아 지원하지 않습니다",
  "fund_not_supported": "ETF·펀드는 회사 이익으로 계산하는 이 방식의 대상이 아닙니다",
  "dcf_not_computable": "현금흐름 할인 계산에 필요한 입력이 부족해 계산하지 않았습니다",
  "price_stale": "최근 종가가 10거래일 넘게 갱신되지 않아 계산하지 않았습니다",
  "price_unavailable": "종가를 가져오지 못해 계산하지 않았습니다",
  "financial_history_unavailable": "공시 재무 자료를 가져오지 못해 계산하지 않았습니다",
  "company_not_found": "공식 자료에서 이 종목을 찾지 못해 계산하지 않았습니다",
  "source_credential_missing": "필요한 공시 조회 키가 설정되어 있지 않아 계산하지 않았습니다",
  "instrument_not_supported": "지원하지 않는 종목 형식이라 계산하지 않았습니다",
  "criteria_not_set": "내 기준이 정해지지 않았습니다",
  "calculation_failed": "예상하지 못한 오류로 계산하지 못했습니다",
  "dcf_fallback": "내재가치 계산에 자료 부족으로 채운 값이 있어 판정하지 않았습니다",
  "price_snapshot_failed": "가격 시나리오 계산 결과를 저장하지 못해 쓰지 않았습니다",
  "price_snapshot_unavailable": "가격 시나리오를 계산하지 못했습니다"
};

/** Stored four-place ratio ×100, rounded half-even as specified for the cash sentence. */
export function cashPerHundred(ratio: string): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(ratio);
  if (!match) return "—";
  const digits = (match[3] ?? "").padEnd(4, "0");
  const scaled = BigInt(match[2]) * 10000n + BigInt(digits.slice(0, 4));
  const whole = scaled / 100n, remainder = scaled % 100n;
  const rounded = whole + (remainder > 50n || (remainder === 50n && whole % 2n === 1n) ? 1n : 0n);
  return `${match[1] && rounded !== 0n ? "−" : ""}${rounded}`;
}

export function reasonText(reason: string | Reason | undefined | null): string {
  const detail: Partial<Reason> = typeof reason === "string" ? { code: reason } : reason ?? {};
  const { code, subCode, range, n, required, historyYears } = detail;
  if (code === "price_unavailable" && subCode === "provider_error") return "가격 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요";
  if (code === "financial_history_unavailable" && subCode === "provider_error") return detail.sourceFailureVerified ? "공시 제공처가 일시적으로 응답하지 않았습니다. 잠시 뒤 다시 계산해 보세요" : "공시 원문을 읽지 못했습니다. 오류가 일시적인지는 확인하지 못했습니다";
  const http = Number.isInteger(detail.httpStatus) && Number(detail.httpStatus) >= 100 && Number(detail.httpStatus) <= 599 ? `(HTTP ${detail.httpStatus})` : "";
  if (code === "financial_history_unavailable" && subCode === "source_not_found") return `공시 원문 주소에서 자료를 찾을 수 없습니다${http}. 이번 계산은 중단했고 이전 저장 결과를 유지합니다`;
  if (code === "financial_history_unavailable" && subCode === "source_access_denied") return `공시 원문 제공처가 접근을 허용하지 않았습니다${http}. 이번 계산은 중단했고 이전 저장 결과를 유지합니다`;
  if (code === "financial_history_unavailable" && subCode === "source_request_failed") return "공시 원문을 읽지 못했습니다. 오류가 일시적인지는 확인하지 못했습니다";
  if (code === "history_too_short" && range !== undefined && n !== undefined && required !== undefined && historyYears !== undefined) {
    const windows = range === "growth" || range === "rpsGrowth";
    if (subCode === "years_too_few") {
      if (windows) return `재무 기록이 ${historyYears}년뿐이라 비교할 5년 구간이 ${n}개입니다(필요 ${required}개). 연속 기록이라면 최소 8년이 필요합니다`;
      const name = ({ pe: "연말 PER", payout: "배당성향", netMargin: "순이익률" } as Record<string, string>)[range] ?? "비교";
      return `재무 기록이 ${historyYears}년뿐이라 ${name}에 쓸 해가 ${n}개입니다(필요 ${required}개)`;
    }
    const cause = subCode === "loss_years" ? "주당이익이 0 이하인 해가 있어" : subCode === "missing_years" ? "일부 연도의 공시 값이 비어" : null;
    if (cause) return `${cause} 비교할 ${windows ? "5년 구간" : "연도"}이 ${n}개입니다(필요 ${required}개)`;
  }
  return (code && REASON_TEXT[code]) || `계산할 수 없습니다(사유 코드: ${code || "unknown"})`;
}

export const NOTICE_TEXT: Record<string, string> = {
  share_classes_same_eps: "같은 주당이익을 공시하는 여러 주식 종류가 있습니다.",
  preferred_shares_exist: "우선주가 있으며 이 계산은 보통주 기준입니다.",
  holding_company_consolidated: "지주회사: 연결 기준입니다. 자회사 가치를 합산해 보는 관점은 반영하지 않습니다.",
  shares_implied_from_eps: "주식 수는 순이익을 주당이익으로 나눠 구한 값입니다.",
  classification_unknown: "업종 분류를 확인하지 못했습니다.",
  common_row_label_voting_shares: "주식 수 표의 보통주 행을 '의결권 있는 주식' 항목으로 읽었습니다.",
  dividend_assumed_zero_from_absence: "배당 공시가 없는 해는 배당이 없었던 것으로 읽었습니다.",
  excluded_growth_windows: "과거 5년 구간 일부는 값이 없거나 0 이하라 빼고 계산했습니다. 범위가 위로 치우칠 수 있습니다.",
  snapshot_old: "계산 시점이 오래됐습니다. 다시 계산하면 최신 가격·공시로 바뀝니다.",
};

export function noticeText(notice: Notice): string {
  const detail = typeof notice === "string" ? { code: notice } : notice;
  if (detail.code === "derived_eps_years") return `${(detail.years ?? []).map(year => `FY${year}`).join("·")} 주당이익은 공시 정리 자료에 없어 같은 해 순이익 ÷ 희석 주식 수로 계산했습니다.`;
  if (detail.code === "listed_class_eps") return `주식 종류가 여러 개라, 상장된 ${detail.class ?? ""} 기준 주당이익을 공시 원문에서 읽었습니다.`;
  return NOTICE_TEXT[detail.code] ?? "";
}

/** Six canonical rows must all be blocked for one of the two permitted reasons. */
/** 지원 종목인데 시나리오 여섯 칸이 모두 계산되지 않았다(범위 밖 수익률은 계산된 것으로 본다). 결론·①②의 빈 칸을 숨기는 기준. */
export function noReturns(view: SnapshotView): boolean {
  const rows = view.results.scenarios;
  return rows.length > 0 && rows.every(row => row.status !== "available");
}

/** 스냅샷 없이 끝난 계산 중, 다시 눌러도 같은 결과가 나오는 "대상 아님". 결론 영역이 직접 말한다. */
const NOT_APPLICABLE = new Set(["fund_not_supported"]);
export function notApplicableAttempt(attempt: Attempt | null): boolean {
  return Boolean(attempt && attempt.status === "failed" && attempt.reason && NOT_APPLICABLE.has(attempt.reason.code));
}

export function showReferenceFacts(view: SnapshotView): boolean {
  const rows = view.results.scenarios;
  const keys = new Set(rows.map(row => `${row.label}:${row.horizon}`));
  return view.results.referenceFacts?.status === "available" && rows.length === 6 && keys.size === 6
    && ([5, 10] as const).every(h => (["conservative", "base", "optimistic"] as const).every(label => keys.has(`${label}:${h}`)))
    && rows.every(row => row.status === "unavailable" && ["negative_base_eps", "history_too_short"].includes(row.reason.code));
}

export const METRIC_TEXT: Record<string, string> = {
  "EPS Diluted": "희석 주당이익", "Net Income": "순이익", Revenue: "매출", DPS: "주당 배당금", "Shares Diluted": "희석 주식 수",
  "Operating Cash Flow": "영업현금흐름", "Dividends Paid": "배당금 지급",
};

export const SCENARIO_NAMES: Record<string, { name: string; note: string; short: string }> = {
  conservative: { name: "보수", short: "과거 낮은 편", note: "과거 10년 중 낮은 편(하위 25%)" },
  base: { name: "기본", short: "과거 보통 수준", note: "과거 10년의 중간값" },
  optimistic: { name: "낙관", short: "과거 높은 편", note: "과거 10년 중 높은 편(상위 25%)" },
};
export const SCENARIO_ORDER = ["conservative", "base", "optimistic"] as const;

export function rowFor(rows: ScenarioRow[], label: string, horizon: number): ScenarioRow | undefined {
  return rows.find(row => row.label === label && row.horizon === horizon);
}

export function irrText(row: ScenarioRow | undefined): string {
  if (!row || row.status !== "available") return "계산 불가";
  if (row.irrRange === "above_range") return "100% 초과";
  if (row.irrRange === "below_range") return "−99% 미만";
  return pct(row.irr);
}

export function irrValue(row: ScenarioRow | undefined): number | null {
  return row && row.status === "available" && row.irr !== null ? toNumber(row.irr) : null;
}

/** 소수 문자열 둘의 크기 비교(부동소수 없이). 평범한 소수가 아니면 null. */
export function compareDecimal(left: string, right: string): -1 | 0 | 1 | null {
  const parse = (text: string) => {
    const match = /^([-−]?)(\d*)(?:\.(\d*))?$/.exec(text.trim());
    return match && (match[2] !== "" || match[3]) ? { negative: match[1] !== "", whole: match[2] || "0", fraction: match[3] ?? "" } : null;
  };
  const a = parse(left);
  const b = parse(right);
  if (!a || !b) return null;
  const places = Math.max(a.fraction.length, b.fraction.length);
  const scaled = (value: NonNullable<typeof a>) => {
    const magnitude = BigInt(value.whole + value.fraction.padEnd(places, "0"));
    return value.negative ? -magnitude : magnitude;
  };
  const x = scaled(a);
  const y = scaled(b);
  return x === y ? 0 : x > y ? 1 : -1;
}

/** 서버 판정(project)과 같은 규칙으로, 시나리오 수익률이 내 기준(% 문자열) 이상인지. 모르면 null. */
export function atLeastRequired(row: ScenarioRow | undefined, required: string | null | undefined): boolean | null {
  if (!row || row.status !== "available" || required === null || required === undefined || required === "") return null;
  if (row.irrRange === "above_range") return true;
  if (row.irrRange === "below_range") return false;
  if (row.irr === null) return null;
  const order = compareDecimal(shiftDecimal(row.irr, 2), required);
  return order === null ? null : order >= 0;
}

const valueText = (row: ScenarioRow | undefined): string | null => (row && row.status === "available" && (row.irr !== null || row.irrRange) ? `연평균 ${irrText(row)}` : null);

/** 내 기준(% 문자열)을 "연 6%"처럼. 정수면 소수 없이. */
export function goalText(required: string): string {
  return `연 ${pctPlain(required, Number(required) % 1 === 0 ? 0 : 1)}`;
}

/** 기준(% 문자열)이 비교 가능한 값인지. */
export function usableGoal(required: string | null | undefined): string | null {
  return required !== null && required !== undefined && required !== "" && compareDecimal(required, "0") !== null ? required : null;
}

/**
 * 결론 문장. 확정적으로 말하지 않고, 과거 기록에서 출발해 조건을 붙인다("과거 10년 흐름이 이어진다면").
 * 판정은 기본 보유 기간의 기본 시나리오로만 한다. 값과 비교는 서버가 준 문자열에서 바로 만든다.
 */
export function heroText(input: { horizon: number; base: ScenarioRow | undefined; required: string | null; holdingYears: number | null; baseHolding: ScenarioRow | undefined }): { title: string; title2: string; sub: string } {
  const { horizon, base, required, holdingYears, baseHolding } = input;
  const value = valueText(base);
  if (value === null || !base || base.status !== "available") return { title: "이 기간의 수익률은 계산하지 못했습니다.", title2: "", sub: base && base.status !== "available" ? `${reasonText(base.reason)}.` : "아래 사유를 확인해 주세요." };
  const history = `이 회사는 지난 10년 동안 주당이익이 보통 연 ${pct(base.g)} 늘었고, 주가는 보통 이익의 ${multiple(base.exitPE)}에서 거래됐습니다. 이 흐름이 앞으로 ${horizon}년도 비슷하다고 보고 계산한 값이며, 보장된 수익이 아닙니다.`;
  const title = `과거 10년 흐름이 이어진다면, 지금 사서 ${horizon}년 보유할 때 ${value}입니다.`;
  const plain = irrText(base);
  const goal = usableGoal(required);
  if (goal === null || holdingYears === null) {
    return { title, title2: "", sub: `${history} ${plain}는 주가 상승과 배당을 합친 1년 평균입니다. 내 기준(원하는 최소 수익률)을 정하면 비교해 드립니다.` };
  }
  const goalLabel = goalText(goal);
  const sub = `${history} ${plain}는 주가 상승과 배당을 합친 1년 평균이고, ${pctPlain(goal, Number(goal) % 1 === 0 ? 0 : 1)}는 ‘투자 기준’에서 내가 정한 최소 수익률입니다.`;
  const word = (row: ScenarioRow | undefined) => (atLeastRequired(row, goal) ? "높습니다" : "낮습니다");
  if (horizon === holdingYears) return { title, title2: `내가 정한 최소 수익률(${goalLabel})보다 ${word(base)}.`, sub };
  const holdingValue = valueText(baseHolding);
  const title2 = holdingValue === null
    ? `내 기준 비교는 기본 보유 기간(${holdingYears}년)으로 하며, 그 기간의 수익률은 계산하지 못했습니다.`
    : `내 기준 비교는 기본 보유 기간(${holdingYears}년)으로 합니다. ${holdingYears}년 ${holdingValue}로, 최소 수익률(${goalLabel})보다 ${word(baseHolding)}.`;
  return { title, title2, sub };
}

/** 큰 금액을 짧게(예: 7,634.6억 달러, 12.3조 원). 1억 미만은 그대로 둔다. */
export function moneyShort(value: string | number | null | undefined, currency: string): string {
  const parsed = toNumber(value);
  if (parsed === null) return "—";
  const abs = Math.abs(parsed);
  const sign = parsed < 0 ? MINUS : "";
  const unit = currency === "USD" ? "달러" : currency === "KRW" ? "원" : currency;
  const fmt = (v: number, places: number) => v.toLocaleString("ko-KR", { minimumFractionDigits: places, maximumFractionDigits: places });
  if (currency === "KRW" && abs >= 1e12) return `${sign}${fmt(abs / 1e12, 1)}조 ${unit}`;
  if (abs >= 1e8) return `${sign}${fmt(abs / 1e8, currency === "KRW" ? 0 : 1)}억 ${unit}`;
  return money(value, currency);
}

/** 현금 비교의 대상 기간: 연속이면 "지난 N년(FYa–FYb)", 떨어져 있으면 "N개 회계연도(FYa–FYb)". */
export function cashSpan(years: { fiscalYear: number }[]): string {
  if (!years.length) return "";
  const contiguous = years.every((row, index) => index === 0 || row.fiscalYear === years[index - 1].fiscalYear + 1);
  return `${contiguous ? `지난 ${years.length}년` : `${years.length}개 회계연도`}(FY${years[0].fiscalYear}–FY${years[years.length - 1].fiscalYear})`;
}

/** 저장된 소수(4자리) 비율 → 소수 1자리 퍼센트 숫자. 화면 표시용. */
export function percentOne(fraction: string | number | null | undefined): number | null {
  const value = toNumber(fraction);
  return value === null ? null : Math.round(value * 1000) / 10;
}

/** 소수 1자리 퍼센트 숫자를 부호와 함께. */
export function signedOne(percent: number): string {
  const text = Math.abs(percent).toFixed(1);
  return `${percent > 0 && Number(text) !== 0 ? "+" : percent < 0 && Number(text) !== 0 ? MINUS : ""}${text}%`;
}

/** 소수 1자리 퍼센트 숫자(음수는 −). */
export function plainOne(percent: number): string {
  const text = Math.abs(percent).toFixed(1);
  return `${percent < 0 && Number(text) !== 0 ? MINUS : ""}${text}%`;
}

export type ScalePoint = { key: string; label: string; value: number; left: number; row: number };

/** 가까운 점의 글자가 겹치지 않게 줄을 나눈다(왼쪽부터, 서로 gap(%) 안에 있으면 다른 줄). */
export function labelRows(lefts: number[], gap = 26): number[] {
  const order = lefts.map((left, index) => ({ left, index })).sort((a, b) => a.left - b.left);
  const rows: number[] = new Array(lefts.length).fill(0);
  const placed: { left: number; row: number }[] = [];
  for (const item of order) {
    let row = 0;
    while (placed.some(other => other.row === row && Math.abs(other.left - item.left) < gap)) row += 1;
    rows[item.index] = row;
    placed.push({ left: item.left, row });
  }
  return rows;
}
/** 범위 막대 눈금: 세 점과 내 기준을 한 줄 위에 놓는 좌표(%)와 눈금 값. */
export function scaleLayout(values: { key: string; label: string; value: number }[], goal: number | null) {
  const all = values.map(v => v.value).concat(goal === null ? [] : [goal]);
  const span = Math.max(...all) - Math.min(...all) || 1;
  const lo = Math.min(...all) - span * 0.1;
  const hi = Math.max(...all) + span * 0.1;
  const at = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const raw = (hi - lo) / 5;
  const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(k => k * magnitude).find(k => k >= raw) || magnitude;
  const ticks: { value: number; left: number }[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) {
    const rounded = Math.round(t * 100) / 100;
    ticks.push({ value: rounded, left: at(rounded) });
  }
  return {
    points: (() => {
      const lefts = values.map(v => at(v.value));
      const rows = labelRows(lefts);
      return values.map((v, index) => ({ ...v, left: lefts[index], row: rows[index] }));
    })(),
    goalLeft: goal === null ? null : at(goal),
    ticks,
    spanLeft: at(Math.min(...values.map(v => v.value))),
    spanRight: at(Math.max(...values.map(v => v.value))),
  };
}

/** 과거 범위 위에 필요한 값이 어디쯤인지. */
export function rangePosition(value: number, min: number, max: number) {
  const span = max - min || 1;
  const lo = min - span * 0.35;
  const hi = max + span * 0.35;
  const clamp = (v: number) => Math.min(Math.max((v - lo) / (hi - lo), 0), 1) * 100;
  const where = value < min ? "보다 낮습니다" : value > max ? "보다 높습니다" : " 안에 있습니다";
  return { valueLeft: clamp(value), minLeft: clamp(min), maxLeft: clamp(max), where };
}

export function decompositionCards(annual: { R: string; M: string; S: string }) {
  const approx = (log: string) => Math.exp(Number(log)) - 1;
  return [
    { key: "R", title: "매출 성장", value: approx(annual.R), weight: Math.abs(Number(annual.R)) },
    { key: "M", title: "이익률 개선", value: approx(annual.M), weight: Math.abs(Number(annual.M)) },
    { key: "S", title: "주식 수 감소", value: approx(annual.S), weight: Math.abs(Number(annual.S)) },
  ];
}

export type Banner = { tone: "info" | "warn"; title: string; detail: string } | null;

/** 화면 위쪽에 한 번만 보이는 상태 안내. 같은 말을 두 곳에 쓰지 않는다. */
export function bannerFor(args: { projection: Projection | null; view: SnapshotView | null; saveFailed: boolean }): Banner {
  const { projection, view, saveFailed } = args;
  if (saveFailed) return { tone: "warn", title: "이 결과는 저장되지 않았습니다.", detail: "화면에는 보이지만 기록에 남지 않았습니다. 이전 기록은 그대로입니다. 다시 계산하면 저장을 다시 시도합니다." };
  if (projection && projection.reviewNeeded.length > 0) {
    const first = projection.reviewNeeded[0];
    return { tone: "warn", title: `${view?.asOf ?? projection.asOf} 계산에 쓴 공시 숫자가 정정됐습니다.`, detail: `${first.fiscalYear}년 ${METRIC_TEXT[first.metric] ?? first.metric} 값이 바뀌었습니다. 정정 전 숫자로 계산한 기록이라 다시 볼 필요가 있습니다. 지난 기록과 내 가정은 자동으로 바꾸지 않습니다.` };
  }
  if (projection?.notices.includes("snapshot_old")) return { tone: "info", title: "계산 시점이 오래됐습니다.", detail: NOTICE_TEXT.snapshot_old };
  return null;
}

export function attemptBanner(attempt: Attempt | null, latestAsOf: string | null): Banner {
  if (!attempt || attempt.status !== "failed") return null;
  const code = attempt.reason?.code;
  const tail = latestAsOf ? ` ${latestAsOf} 계산은 아래 기록에서 볼 수 있습니다.` : "";
  if (code === "price_stale") return { tone: "warn", title: "최근 종가가 오래돼 새로 계산하지 않았습니다.", detail: `마지막 종가가 10거래일 넘게 갱신되지 않았습니다.${tail}` };
  return { tone: "warn", title: "이번에는 계산하지 못했습니다.", detail: `${reasonText(attempt.reason)}. 틀린 숫자를 보여 드리지 않으려고 멈췄습니다.${tail}` };
}

export function overviewHasResult(overview: Overview | null): boolean {
  return Boolean(overview?.latest);
}

/** 소수점을 문자열 그대로 옮긴다(부동소수 오차 없이). shift > 0 이면 오른쪽. 형식이 아니면 원문을 돌려준다. */
export function shiftDecimal(text: string, shift: number): string {
  const trimmed = text.trim();
  const match = /^([-−+]?)(\d*)(?:\.(\d*))?$/.exec(trimmed);
  if (!match || (match[2] === "" && !match[3])) return text;
  const [, sign, whole, fraction = ""] = match;
  const digits = whole + fraction;
  const point = whole.length + shift;
  let padded = digits;
  let position = point;
  if (position < 0) { padded = "0".repeat(-position) + padded; position = 0; }
  if (position > padded.length) padded += "0".repeat(position - padded.length);
  const integer = padded.slice(0, position).replace(/^0+(?=\d)/, "") || "0";
  const rest = padded.slice(position).replace(/0+$/, "");
  const negative = sign === "-" || sign === "−";
  const out = rest ? `${integer}.${rest}` : integer;
  return negative && Number(out) !== 0 ? `-${out}` : out;
}

export const percentToFraction = (text: string): string => shiftDecimal(text, -2);
export const fractionToPercent = (text: string | null | undefined): string => (text === null || text === undefined ? "" : shiftDecimal(text, 2));

/** 비율(0.5 = 50%)을 부호와 천 단위 구분이 있는 %로. */
export function ratioText(fraction: number, places = 1): string {
  const text = Math.abs(fraction * 100).toLocaleString("en-US", { minimumFractionDigits: places, maximumFractionDigits: places });
  const zero = Number(text.replace(/,/g, "")) === 0;
  return `${fraction > 0 && !zero ? "+" : fraction < 0 && !zero ? "−" : ""}${text}%`;
}
/** 배수(1.25 → ×1.25, 28.82 → ×28.8). 10 미만은 소수 둘째 자리까지 보여 ×1.2와 ×1.25를 구별한다. */
export const timesText = (factor: number) => `×${factor < 10 ? factor.toFixed(2) : factor.toFixed(1)}`;
