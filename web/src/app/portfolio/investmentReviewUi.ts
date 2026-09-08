export type ReviewReason = { code?: string; ticker?: string };

export type ReviewPosition = {
  ticker?: string;
  name?: string;
  thesisVerdict?: string;
  thesisPresent?: boolean;
  latestReviewPresent?: boolean;
  reviewReasons?: string[];
  dueCheckpoints?: Array<{ id?: string; label?: string; dueAt?: string }>;
};

export type CanonicalReference = {
  kind?: string;
  id?: string;
  asOf?: string;
  title?: string;
  reportKind?: string;
  marketScope?: string;
  relatedReason?: string;
};

export type PositionReadiness = "missing_thesis" | "missing_review" | "evidence_insufficient" | "ready" | "unknown";

const THESIS_VERDICTS = new Set(["strengthened", "maintained", "weakened", "at_risk", "broken", "insufficient_evidence"]);

/** Stored booleans are authoritative. Old records may only safely add a known-present Thesis. */
export function readinessFor(position: ReviewPosition, knownThesisTickers: ReadonlySet<string> = new Set()): PositionReadiness {
  if (position.thesisPresent === false) return "missing_thesis";
  if (position.thesisPresent !== true) {
    const ticker = String(position.ticker || "").trim().toUpperCase();
    return ticker && knownThesisTickers.has(ticker) ? "unknown" : "unknown";
  }
  if (position.latestReviewPresent === false) return "missing_review";
  if (position.latestReviewPresent === true && position.thesisVerdict === "insufficient_evidence") return "evidence_insufficient";
  return position.latestReviewPresent === true ? "ready" : "unknown";
}

export function readinessLabel(readiness: PositionReadiness): string {
  return {
    missing_thesis: "투자 논리 미작성",
    missing_review: "최신 검토 미작성",
    evidence_insufficient: "검토 후 자료 부족",
    ready: "검토 준비됨",
    unknown: "준비 상태 확인 불가",
  }[readiness];
}

function timestampInKst(value: string): Date | null {
  const raw = String(value || "").trim();
  // Browser parsing treats a timezone-less datetime as the viewer's locale.
  // Stored legacy checkpoint values instead have the same KST convention as
  // the review service, independent of where this browser happens to run.
  const normalized = /^\d{4}-\d{2}-\d{2}T/.test(raw) && !/(Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? `${raw}+09:00` : raw;
  const instant = new Date(normalized);
  return Number.isNaN(instant.getTime()) ? null : instant;
}

function kstDate(value: string): string {
  const instant = timestampInKst(value);
  if (!instant) return "";
  if (Number.isNaN(instant.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(instant);
  const part = (type: string) => parts.find((item) => item.type === type)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** Date-only deadlines become overdue after that calendar day ends in Asia/Seoul. */
export function isOverdue(dueAt: string | undefined, evaluatedAt: string | undefined): boolean {
  const due = String(dueAt || "").trim();
  const evaluated = String(evaluatedAt || "").trim();
  if (!due || !evaluated) return false;
  if (/^\d{4}-\d{2}-\d{2}$/.test(due)) {
    const evaluatedDate = kstDate(evaluated);
    return Boolean(evaluatedDate) && due < evaluatedDate;
  }
  const dueInstant = timestampInKst(due)?.getTime();
  const evaluatedInstant = timestampInKst(evaluated)?.getTime();
  return typeof dueInstant === "number" && typeof evaluatedInstant === "number" && dueInstant <= evaluatedInstant;
}

export function positionPriority(position: ReviewPosition, evaluatedAt?: string, knownThesisTickers?: ReadonlySet<string>): number {
  const verdict = String(position.thesisVerdict || "");
  if (verdict === "broken") return 0;
  if (verdict === "at_risk") return 1;
  if (verdict === "weakened") return 2;
  if ((position.dueCheckpoints || []).some((checkpoint) => isOverdue(checkpoint.dueAt, evaluatedAt))) return 3;
  const readiness = readinessFor(position, knownThesisTickers);
  if (readiness === "missing_thesis") return 4;
  if (readiness === "missing_review") return 5;
  if (readiness === "evidence_insufficient") return 6;
  return 7;
}

/** Display order only. It never mutates the persisted review array or fingerprint. */
export function sortReviewPositions<T extends ReviewPosition>(positions: readonly T[], evaluatedAt?: string, knownThesisTickers?: ReadonlySet<string>): T[] {
  return [...positions].sort((left, right) => positionPriority(left, evaluatedAt, knownThesisTickers) - positionPriority(right, evaluatedAt, knownThesisTickers)
    || String(left.ticker || "").localeCompare(String(right.ticker || "")));
}

export function reviewReasonLabel(code: string | undefined): string {
  return {
    thesis_review_needed: "Thesis 재검토",
    checkpoint_due: "체크포인트 도래",
    checkpoint_pending: "체크포인트 확인",
    thesis_missing: "투자 논리 미작성",
  }[String(code || "")] || "추가 확인 필요";
}

export function safeReportRoute(reference: CanonicalReference): string {
  const kind = String(reference.kind || "");
  const id = String(reference.id || "").trim();
  if (!id) return "";
  if (kind === "company_analysis") return `#/analysis/${encodeURIComponent(id)}`;
  if (kind === "topic_report") return `#/deep-research/${encodeURIComponent(id)}`;
  if (kind !== "briefing") return "";
  // Old saved IDs sometimes carry their own scope/kind suffix. Only accept
  // the known bounded grammar; never turn an arbitrary ID into a route.
  const parsed = id.match(/^(\d{4}-\d{2}-\d{2})(?:\.(us|kr|both|europe|jp))?(?:\.(daily|weekly))?$/);
  if (!parsed) return "";
  const [, date, idScope, idReportKind] = parsed;
  const scope = ["us", "kr", "both", "europe", "jp"].includes(String(reference.marketScope || "")) ? String(reference.marketScope) : idScope || "both";
  const reportKind = ["daily", "weekly"].includes(String(reference.reportKind || "")) ? String(reference.reportKind) : idReportKind || "daily";
  return date ? `#/briefing/${date}/${scope}/${reportKind}` : "";
}

export function isThesisVerdict(value: string | undefined): boolean {
  return THESIS_VERDICTS.has(String(value || ""));
}
