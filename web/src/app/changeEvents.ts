/** 변화 이벤트를 화면 문장으로 옮기는 공용 helper.
 *
 * 대시보드 변화 피드와 브리핑 상단 스트립이 함께 쓴다. 예전에는 워치리스트
 * 상세의 "확인된 변화 기록" 컴포넌트 파일에 얹혀 있었는데, 그 레일이 사라진
 * 뒤에도 두 화면이 계속 쓰므로 중립 위치로 옮겼다.
 */
export type ChangeEvent = {
  artifactKind?: string;
  artifactId?: string;
  lineageId?: string;
  status?: string;
  generatedAt?: string;
  materiality?: number;
  reliability?: number;
  changedItems?: ChangedItem[];
  baselineRef?: { id?: string; committedAt?: string };
  /** 서버가 남긴 의미 판정 결과. `reason`은 판정하지 못한 이유다. */
  semanticEvaluation?: { status?: string; reason?: string | null; provider?: string; model?: string };
};

export type ChangedItem = {
  id?: string;
  subject?: string;
  change?: string;
  kind?: string;
  horizon?: string;
  currentValue?: unknown;
  previousValue?: unknown;
  contextDocs?: string[];
  previousContextDocs?: string[];
  semanticVerdict?: string;
  semanticNote?: string;
  semanticCitedTitles?: string[];
};

const CHANGE_VERB_LABELS: Record<string, string> = {
  added: "새로 등장", removed: "사라짐", changed: "내용 변화",
};
const UNIT_KIND_LABELS: Record<string, string> = {
  market_driver: "시장 동인", issue_coverage: "이슈 보도", market_metric: "지표",
};

function formatNumber(value: unknown): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? "");
}

type DriverValue = { rank?: unknown; share?: unknown };

/** {rank, share}를 "3순위 · 비중 18%" 한 조각으로. 전/후 대조표가 양쪽에 쓴다. */
export function driverValueText(value: unknown): string {
  const row = (value || {}) as DriverValue;
  const rank = Number(row.rank);
  const share = Number(row.share);
  const parts: string[] = [];
  if (Number.isFinite(rank) && rank > 0) parts.push(`${rank}순위`);
  if (Number.isFinite(share) && share > 0) parts.push(`비중 ${Math.round(share * 100)}%`);
  return parts.join(" · ");
}

/** 항목 종류에 맞춰 한쪽(직전/현재) 값을 읽을 수 있는 문장으로. */
export function changedValueText(item: ChangedItem, value: unknown): string {
  if (value == null) return "";
  if (item.kind === "market_metric") return formatNumber(value);
  if (typeof value !== "object") return formatNumber(value);
  const driver = driverValueText(value);
  if (driver) return driver;
  const row = value as { market?: unknown; impact?: unknown; docCount?: unknown };
  const parts: string[] = [];
  if (row.market) parts.push(String(row.market));
  if (row.impact) parts.push(String(row.impact));
  // 구형(rank/share 이전) 동인 값은 기사 수라도 보여준다.
  if (!parts.length && Number(row.docCount) > 0) parts.push(`기사 ${Number(row.docCount)}건`);
  return parts.join(" · ");
}

/** 동인은 그날 전체 비중에서 몇 위였고 얼마를 차지했는지가 읽을 값이다. */
function driverDetail(item: ChangedItem): string {
  const current = (item.currentValue || {}) as DriverValue;
  const previous = (item.previousValue || {}) as DriverValue;
  const rank = Number(current.rank);
  const previousRank = Number(previous.rank);
  const share = Number(current.share);
  const parts: string[] = [];
  if (Number.isFinite(rank) && rank > 0) {
    parts.push(Number.isFinite(previousRank) && previousRank > 0 && previousRank !== rank
      ? `${previousRank}순위 → ${rank}순위`
      : `${rank}순위`);
  }
  if (Number.isFinite(share) && share > 0) parts.push(`비중 ${Math.round(share * 100)}%`);
  return parts.join(" · ");
}

/** 항목 종류별로 실제로 담긴 값을 짧게 풀어 쓴다. */
function changeDetail(item: ChangedItem): string {
  const current = item.currentValue;
  if (item.kind === "market_metric") {
    if (item.previousValue != null && current != null) return `${formatNumber(item.previousValue)} → ${formatNumber(current)}`;
    return current != null ? formatNumber(current) : "";
  }
  // 동인의 markets는 시장이 아니라 "US 전일 정규장" 같은 세션 구간 이름이라 읽을 값이 아니다.
  if (item.kind === "market_driver") return driverDetail(item);
  if (current && typeof current === "object") {
    const row = current as { markets?: unknown; market?: unknown; docCount?: unknown; impact?: unknown };
    const parts: string[] = [];
    if (Array.isArray(row.markets) && row.markets.length) parts.push(row.markets.join(", "));
    else if (row.market) parts.push(String(row.market));
    if (Number(row.docCount) > 0) parts.push(`기사 ${Number(row.docCount)}건`);
    if (row.impact) parts.push(String(row.impact));
    return parts.join(" · ");
  }
  return "";
}

/** 무엇이 어떻게 달라졌는지 한 줄로. 눌러서 이동하기 전에 이유를 알 수 있어야 한다. */
export function changeReasonText(event: ChangeEvent): string {
  const items = event.changedItems || [];
  if (!items.length) return "";
  const first = items[0];
  const verb = CHANGE_VERB_LABELS[String(first.change || "")] || "변화";
  const kind = UNIT_KIND_LABELS[String(first.kind || "")];
  const head = kind ? `${kind} ${verb}` : verb;
  const rest = items.length > 1 ? `외 ${items.length - 1}건` : "";
  return [head, changeDetail(first), rest].filter(Boolean).join(" · ");
}

/** 어떤 산출물과 비교했는지. 비교 대상이 없으면 빈 문자열. */
export function baselineText(event: ChangeEvent): string {
  const id = event.baselineRef?.id;
  return id ? `${id} 대비` : "";
}

export const ARTIFACT_KIND_LABELS: Record<string, string> = {
  briefing: "브리핑",
  company_analysis: "기업 분석",
  topic_report: "딥 리서치",
  market_memory: "시장 내러티브",
};
