import { quarterAxisLabel } from "../charts/chartFormat";
import type { FundamentalsQuarter } from "./FundamentalsPanel";

/**
 * 판단 조건 문장 ↔ 분기 실적 숫자 대조 (2026-09-29 사용자 결정 "지금 숫자").
 *
 * 판정이 아니라 **사실**이다. 조건이 Folio가 가진 분기 실적 지표로 읽히면 최근 분기
 * 값을 과거 → 최신 순으로 보여 주고, 조건 문장의 기계적 해당 여부만 말한다. 좋고 나쁨·
 * 투자 판단을 만들지 않으며 저장된 이유를 바꾸지 않는다.
 *
 * 읽는 문장 꼴은 AI 다듬기가 제안하는 꼴과 같다:
 *     "분기 영업이익률이 두 분기 연속 낮아질 때"
 * 지표를 못 찾으면 null — 화면은 아무것도 덧붙이지 않는다(추측하지 않는다).
 */

export type ConditionMetric = "revenue" | "operatingIncome" | "netIncome" | "operatingMargin" | "netMargin" | "operatingCashFlow" | "freeCashFlow";

export type MetricCondition = { metric: ConditionMetric; label: string; direction: "down" | "up"; streak: number };

export type MetricCheck = {
  condition: MetricCondition;
  points: Array<{ label: string; value: number }>;
  /** 최근 streak번의 변화가 모두 조건 방향이면 true. 분기가 모자라면 null(판단하지 않음). */
  met: boolean | null;
  unit: "percent" | "amount";
};

// 긴 이름을 먼저 본다 — "영업이익률"이 "영업이익"으로 잡히면 금액과 비율이 바뀐다.
const METRICS: Array<{ pattern: RegExp; metric: ConditionMetric; label: string }> = [
  { pattern: /영업\s*이익\s*률|영업\s*마진/, metric: "operatingMargin", label: "영업이익률" },
  { pattern: /순\s*이익\s*률|순\s*마진/, metric: "netMargin", label: "순이익률" },
  { pattern: /영업\s*현금\s*흐름/, metric: "operatingCashFlow", label: "영업현금흐름" },
  { pattern: /잉여\s*현금\s*흐름|FCF/i, metric: "freeCashFlow", label: "잉여현금흐름" },
  { pattern: /영업\s*이익/, metric: "operatingIncome", label: "영업이익" },
  { pattern: /순\s*이익/, metric: "netIncome", label: "순이익" },
  { pattern: /매출/, metric: "revenue", label: "매출" },
];
const DOWN = /낮아|줄어|줄|감소|하락|떨어|악화|축소/;
const UP = /높아|늘어|늘|증가|상승|오르|개선|확대/;
const COUNT_WORDS: Record<string, number> = { 한: 1, 두: 2, 세: 3, 네: 4 };

export function parseMetricCondition(text: string): MetricCondition | null {
  const source = String(text || "");
  const found = METRICS.find((entry) => entry.pattern.test(source));
  if (!found) return null;
  // 방향 단어는 지표 이름 뒤에서 찾는다 — "매출은 늘지만 영업이익률이 낮아질 때"에서
  // 앞의 "늘"을 읽으면 방향이 뒤집힌다.
  const tail = source.slice(source.search(found.pattern));
  // 이 첫 버전은 분기 간 단순 증감만 읽는다. 임계값·전년 동기·평균을
  // 무시하고 "조건에 해당함"이라고 표시하면 사용자의 실제 조건을 바꿔 버린다.
  const counted = tail.match(/(한|두|세|[1-3])\s*분기\s*연속|연속\s*(한|두|세|[1-3])\s*분기/);
  const rest = counted ? tail.replace(counted[0], "") : tail;
  if (/(\d|%|퍼센트|이상|이하|초과|미만|전년|동기|전분기|평균|누적|yoy|qoq|year.over.year)/i.test(rest)) return null;
  if (/연속/.test(rest)) return null;
  const down = tail.search(DOWN);
  const up = tail.search(UP);
  if (down < 0 && up < 0) return null;
  const direction = up < 0 || (down >= 0 && down < up) ? "down" : "up";
  const word = counted ? counted[1] || counted[2] : "";
  const streak = word ? (COUNT_WORDS[word] || Number(word) || 1) : 1;
  return { metric: found.metric, label: found.label, direction, streak };
}

function metricValue(row: FundamentalsQuarter, metric: ConditionMetric): number | null {
  const ratio = (top?: number | null, bottom?: number | null) =>
    top == null || bottom == null || !Number.isFinite(top) || !Number.isFinite(bottom) || bottom === 0 ? null : (top / bottom) * 100;
  switch (metric) {
    case "operatingMargin": return ratio(row.operatingIncome, row.revenue);
    case "netMargin": return ratio(row.netIncome, row.revenue);
    default: {
      const value = row[metric];
      return value == null || !Number.isFinite(value) ? null : value;
    }
  }
}

export function checkMetricCondition(text: string, quarters: FundamentalsQuarter[] | undefined): MetricCheck | null {
  const condition = parseMetricCondition(text);
  if (!condition) return null;
  const rows = [...(quarters || [])]
    .filter((row) => /^\d{4}-\d{2}/.test(String(row.quarter || "")))
    .sort((a, b) => String(a.quarter).localeCompare(String(b.quarter)))
    .map((row) => ({ quarter: String(row.quarter), label: quarterAxisLabel(row.quarter), value: metricValue(row, condition.metric) }));
  if (!rows.length || rows[rows.length - 1].value == null) return null;
  // 보여 줄 칸: 조건 판단에 필요한 streak+1칸, 최소 3칸, 최대 4칸.
  const span = Math.min(4, Math.max(3, condition.streak + 1));
  const points = rows.slice(-span)
    .filter((row): row is { quarter: string; label: string; value: number } => row.value != null)
    .map(({ label, value }) => ({ label, value }));
  const needed = rows.slice(-(condition.streak + 1));
  let met: boolean | null = null;
  const quarterIndex = (value: string) => Number(value.slice(0, 4)) * 12 + Number(value.slice(5, 7));
  if (needed.length === condition.streak + 1 && needed.every((row) => row.value != null)
      && needed.slice(1).every((row, index) => quarterIndex(row.quarter) - quarterIndex(needed[index].quarter) === 3)) {
    met = needed.slice(1).every((row, index) => condition.direction === "down"
      ? row.value! < needed[index].value! : row.value! > needed[index].value!);
  }
  const unit = condition.metric === "operatingMargin" || condition.metric === "netMargin" ? "percent" : "amount";
  return { condition, points, met, unit };
}
