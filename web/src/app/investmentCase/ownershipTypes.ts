import type { Input, Slot, SourceRef } from "./types";

export const conclusions: Record<string, string> = { maintain: "기존 이유 유지", withdraw: "기존 이유 철회", new_reason: "새 이유로 판단", defer: "판단 보류", exception: "예외로 판단", undecided: "결론 미정" };
export const evidenceLevels: Record<string, string> = { unknown: "아직 평가하지 않음", sufficient: "내가 보기에 충분함", partial: "일부만 확인", missing: "자료 부족", conflicting: "자료 상충", stale: "자료가 오래됨" };
export const signals: Record<string, string> = { unknown: "아직 판단하지 않음", detected: "변화를 관찰함", no_signal: "변화를 확인하지 못함" };
export const scopes: Record<string, string> = { reason: "이유와 조건", company: "기업", price: "가격과 기준", macro: "거시", portfolio: "전체 구성" };
export const assessments: Record<string, string> = { uncertain: "구분하기 어려움", original_error: "원래 판단의 오류", external_change: "외부 여건의 변화", mixed: "둘 다 해당" };
export type Condition = { origin: string; reasonRevisionId?: string; field?: string; index?: number; anchorJournalId?: string; text?: string };
export type ReviewFields = {
  originalJournalId: string | null; previousReviewJournalId: string | null; condition: Condition;
  observation: { text: string; sourceRefs: Array<{ id?: string; revision?: string; url?: string; title?: string }>; eventAt: string | null; publishedAt: string | null; collectedAt: string | null };
  signal: string; evidence: string; interpretation: string; companyView: string; priceView: string; cashNeed: string; portfolioContext: string;
  conclusion: string; resolution: string; completed: boolean; checkedScope: string[]; nextCheck: string; nextCheckAt: string | null;
  exceptionBasis: string; exceptionEndAt: string | null; exceptionEndEvent: string; postmortemAssessment?: string; expectedPath?: string; observedPath?: string;
};
export type SavedReview = Partial<ReviewFields> & { rootReviewJournalId: string; firstSeenAt: string; latestReviewedAt?: string; reviewedAt?: string; purgedAt?: string; earliestUnresolvedDueAt?: string };
export type ReviewEntry = { sinceReviewed?: { status: string; journalId?: string; reviewedAt?: string; checkedScope?: string[]; changedSlots?: Slot[]; unchangedSlots?: Slot[]; gapSlots?: Slot[] }; id: string; recordedAt: string; kind: string; status: string; review: SavedReview; uncertainties: string; conditionView: { status: string; text: string | null }; due: { schedule: string; nextCheckAt?: string; overdueUnresolved: boolean; earliestUnresolvedDueAt?: string; exceptionExpired: boolean; planMissing: boolean } };
export type AxisRow = { slot: Slot; status: string; before: Input; after: Input };
export type OwnershipView = {
  mode: "current" | "historical"; instrumentId: string; caseId: string; caseRevision: number; checkedAt: string; journalId?: string; review?: SavedReview; notice: string; originalHashChanged?: boolean;
  original: { id: string | null; bodyHash?: string; status: string; reason?: string; recordedAt?: string };
  current: { recordedAt?: string; capturedAt?: string; refs: Record<string, SourceRef> };
  comparison: { business: AxisRow[]; price: AxisRow[]; macro: AxisRow[]; portfolio: AxisRow[]; notice: string;
    reason: { before: Record<string, unknown> | null; after: Record<string, unknown> | null; revisionChanged: boolean };
    quantitative: { notice: string; scenarios: Array<{ metric: string; label: string; horizon: number; unit: string; before?: string; after?: string; difference?: string; status: string }>;
      annual: Array<{ metric: string; period: { start?: string; end?: string }; before: { value?: string; unit?: string } | null; after: { value?: string; unit?: string } | null; difference?: string; status: string }> };
  };
  conditionOptions: Condition[]; issues: ReviewEntry[]; timeline: ReviewEntry[]; historyGaps: Array<{ id: string; reason: string }>;
  originalOptions: Array<{ id: string; recordedAt: string; kind?: string; status?: string }>;
};
export function newReview(original: string | null = null, previous?: ReviewEntry): ReviewFields {
  return { originalJournalId: previous?.review.originalJournalId ?? original, previousReviewJournalId: previous?.id || null,
    condition: { origin: previous ? "previous" : "outside_conditions" }, observation: { text: "", sourceRefs: [], eventAt: null, publishedAt: null, collectedAt: null },
    signal: "unknown", evidence: "unknown", interpretation: "", companyView: "", priceView: "", cashNeed: "", portfolioContext: "", conclusion: "undecided", resolution: "unresolved",
    completed: false, checkedScope: [], nextCheck: previous?.review.nextCheck || "", nextCheckAt: previous?.review.nextCheckAt || null,
    exceptionBasis: "", exceptionEndAt: null, exceptionEndEvent: "" };
}

export function ownershipLink(ticker: string, instrumentId: string, journalId?: string, returnHash?: string, originalJournalId?: string) {
  const params = new URLSearchParams({ tab: "ownership", instrument: instrumentId });
  if (journalId) params.set("journal", journalId);
  if (originalJournalId) params.set("original", originalJournalId);
  if (returnHash?.startsWith("#/portfolio?")) params.set("returnHash", returnHash);
  return `#/watchlist/${encodeURIComponent(ticker)}?${params}`;
}
export function portfolioReviewReturn(date?: string) {
  const query = new URLSearchParams(window.location.hash.split("?")[1] || "");
  query.set("tab", "review");
  if (date) query.set("date", date);
  return `#/portfolio?${query}`;
}
export function portfolioReturn(hash = window.location.hash) {
  const query = new URLSearchParams(hash.split("?")[1] || "");
  const value = query.get("returnHash");
  if (value && /^#\/portfolio(?:\?[^#\r\n]*)?$/.test(value)) {
    if (value === "#/portfolio") return "#/portfolio";
    // The route is application-owned. Only encoded query values come from
    // the caller; never return the caller's URL directly to an href sink.
    return `#/portfolio?${new URLSearchParams(value.slice("#/portfolio?".length))}`;
  }
  return query.get("returnTo") === "review" ? `#/portfolio?tab=review&date=${encodeURIComponent(query.get("reviewDate") || "")}` : null;
}
