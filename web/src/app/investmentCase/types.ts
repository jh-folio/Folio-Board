export const slots = ["company", "research", "macro", "price", "reason", "delta", "review", "readiness"] as const;
export type Slot = typeof slots[number];
export const slotLabels: Record<Slot, string> = { company: "기업 분석", research: "딥 리서치", macro: "거시 맥락", price: "가격과 내 기준", reason: "투자 이유와 조건", delta: "이유 검증", review: "투자 리뷰", readiness: "기준 충족 여부" };
export const stages: Record<string, string> = { researching: "조사 중", considering: "검토 중", owned: "보유 단계", archived: "보관" };
export const kinds: Record<string, string> = { decision: "결정 기록", stage_change: "단계 변경", partial_change: "일부 변화", reason_replaced: "이유 교체", reentry: "새 검토 시작", ownership_review: "보유 점검", postmortem: "복기" };
export type SourceRef = { kind?: string; id?: string; revision?: number; asOf?: string; contentHash?: string; identityStatus?: string; relation?: string };
export type Input = { status: string; reason?: string; ref: SourceRef; content?: Record<string, unknown> | null; originalLayer?: string; preservationScope?: { omittedFieldCount?: number } };
export type Scenario = { snapshotId: string; label: string; horizon: number };
export type Operation = { operationId: string; status: string; kind?: string; journalId?: string; cancelAllowed?: boolean; outcome?: string; sourceOutcome?: string; result?: { caseRevision?: number } };
export type CaseView = { caseId: string; caseRevision: number; inputFingerprint: string; methodVersion: string; lifecycle: string | null; lifecycleMismatch: boolean; inputs: Record<Slot, Input>; sourceRefs: Record<Slot, SourceRef>; reasonSummary?: Record<string, unknown>; readiness?: { message?: string }; scenarioOptions?: Scenario[]; staleReasons: Array<{ slot: Slot; code: string }>; journals: Array<{ id: string; recordedAt: string; preview?: string; kind?: string; status: string; purged?: boolean }>; pendingOperations: Operation[]; portfolioPresence?: { held: boolean | null }; events?: Array<{ kind: string; from_stage?: string; to_stage?: string; recorded_at: string }> };
export type Journal = { id: string; caseId: string; instrumentId: string; recordedAt: string; kind: string; previousJournalId?: string; decisionText: string; uncertainties: string; userReportedAt: { value: string | null; precision: string }; selectedScenario?: Scenario; inputs: Record<Slot, Input>; personalPurgedAt?: string };
export type JournalView = { journal: Journal; bodyHash: string; sourceAvailability: Record<Slot, Array<{ status: string; ref: SourceRef }>>; corrections: Array<{ id: string; slot: Slot; notedAt: string; newRef: SourceRef }> };
export type Preview = { token: string | null; canConfirm: boolean; action: string; totalBytes: number; maxBytes: number; blockedSlots: Slot[]; notice: string; journal?: Journal; inputs: Array<Input & { slot: Slot; bytes?: number }>; lifecycle: { from: string; to: string }; purge?: { personal: boolean; slots: Slot[] }; correction?: { slot: Slot; newRef: SourceRef } };

export function recordsLink(ticker: string, instrumentId: string, reviewDate?: string) {
  const params = new URLSearchParams({ tab: "records", instrument: instrumentId });
  if (reviewDate) { params.set("reviewDate", reviewDate); params.set("returnTo", "review"); }
  return `#/watchlist/${encodeURIComponent(ticker)}?${params}`;
}
