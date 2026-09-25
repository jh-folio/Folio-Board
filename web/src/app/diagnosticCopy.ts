import type { DiagnosticDetail, DiagnosticRecord } from "../api";
import { ADAPTER_LABELS, FALLBACK_REASONS } from "./workLogCopy";

// 안전한 코드 값만 사람이 읽는 문장으로 옮긴다. 모르는 코드는 원문을 그대로 보여준다
// (workLogCopy.ts의 fallbackCode()와 같은 원칙 — 새 코드가 추가돼도 정보가 사라지지 않는다).

const STAGE_LABELS: Record<string, string> = {
  queued: "대기",
  preflight: "사전 점검",
  collect: "자료 수집",
  context: "맥락 구성",
  wait_engine: "엔진 응답 대기",
  generate: "생성",
  validate: "검증",
  commit: "저장",
  cleanup: "정리",
  recovery: "복구",
};

const REASON_LABELS: Record<string, string> = {
  timeout: "시간 초과",
  rate_limit: "사용량 한도 초과",
  adapter_unavailable: "연결된 실행 도구를 찾지 못함",
  adapter_failed: "실행 도구가 비정상 종료됨",
  validation: "결과 검증 실패",
  save_permission: "저장 권한 문제",
  save_failed: "저장 실패",
  cancelled: "취소됨",
  interrupted: "서버 재시작으로 중단됨",
  commit_recovery_failed: "저장 복구 실패",
  private_cleanup_failed: "임시 파일 정리 실패",
  store_unavailable: "작업 저장소를 읽지 못함",
  commit_unknown: "저장 결과를 확인하지 못함",
  unknown: "원인이 확인되지 않음",
};

const NEXT_ACTION_LABELS: Record<string, string> = {
  none: "추가로 확인할 것이 없습니다.",
  wait: "아직 진행 중입니다. 잠시 후 다시 확인하세요.",
  check_settings: "설정에서 관련 값을 확인해 보세요.",
  inspect_result: "저장 결과를 다시 확인해 보세요.",
  explicit_retry: "다시 실행할 수 있습니다.",
  contact_support: "원인이 자동으로 확인되지 않았습니다.",
};

const CONFIRMATION_LABELS: Record<string, string> = {
  observed: "확인됨",
  inferred: "추정",
  unknown: "미확인",
};

// availabilityReason(§6 계약)의 사람이 읽는 설명. record가 없을 때만 쓴다.
const AVAILABILITY_NOTES: Record<string, string> = {
  missing_unknown: "이 실행에 대한 진단 기록이 없습니다.",
  legacy_no_detail: "이 실행은 상세 기록이 도입되기 전이라 진단 정보가 없습니다.",
  disabled: "진단 기록이 꺼져 있어 확인할 수 없습니다.",
  writer_conflict: "다른 프로세스가 기록 중이라 지금은 읽을 수 없습니다. 잠시 후 다시 시도하세요.",
  quota_exceeded: "진단 저장 공간 한도에 도달해 이 기록을 확인할 수 없습니다.",
  read_failed: "진단 기록을 읽는 데 실패했습니다.",
  corrupt: "진단 기록이 손상되어 읽을 수 없습니다.",
  unsupported_version: "지원하지 않는 진단 기록 형식입니다.",
  expired: "보존 기간이 지나 기록이 삭제되었습니다.",
};

const ENGINE_LABELS: Record<string, string> = {
  api: "API 직접 호출",
  cli: "AI CLI",
  rules: "규칙 기반",
  none: "실행 없음",
};
const SUCCESS_STATUSES = new Set(["done", "succeeded"]);

export function stageLabel(code: string | null): string {
  if (!code) return "확인되지 않음";
  return STAGE_LABELS[code] || code;
}

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] || code;
}

export function nextActionLabel(code: string): string {
  return NEXT_ACTION_LABELS[code] || code;
}

export function confirmationLabel(code: string): string {
  return CONFIRMATION_LABELS[code] || code;
}

export function formatElapsed(ms: number | null): string {
  if (ms === null) return "측정 안 됨";
  if (ms < 1000) return `${ms}ms`;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}초`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return seconds ? `${minutes}분 ${seconds}초` : `${minutes}분`;
}

/**
 * events[]에서 실제로 성공이 확인된 마지막 단계만 고른다.
 *
 * end는 span의 닫힘이지 성공 신호가 아니다. 같은 stageId에 failure가
 * 있었다면 producer가 후속으로 end를 남겼더라도 성공 단계로 세지 않는다.
 */
export function lastCompletedStageLabel(record: DiagnosticRecord): string {
  const failedStageIds = new Set<string>();
  for (const event of record.events) {
    if (event.eventCode === "failure" || event.errorId !== null) failedStageIds.add(event.stageId);
  }
  for (const failure of [...record.errors, record.firstFailure, record.terminalFailure]) {
    if (failure?.stageId) failedStageIds.add(failure.stageId);
  }
  const ended = record.events
    .filter((event) => event.eventCode === "end" && !failedStageIds.has(event.stageId))
    .sort((a, b) => b.seq - a.seq)[0];
  return ended ? stageLabel(ended.stageCode) : "완료된 단계 없음";
}

function engineHint(code: string | null): string | null {
  if (!code) return null;
  return ENGINE_LABELS[code] || code;
}

/** 규칙 대체 실행에서 "원래 무엇으로 시도했고 실제로 무엇을 썼는지"를 한 문장으로 만든다. */
export function engineFallbackNote(record: DiagnosticRecord, completionConfirmed?: boolean): string {
  const attempted = engineHint(record.attemptedEngine);
  const final = engineHint(record.finalEngine);
  const reason = record.fallbackReason ? FALLBACK_REASONS[record.fallbackReason] || record.fallbackReason : "";
  const completed = completionConfirmed ?? (record.finishedAt !== null
    && SUCCESS_STATUSES.has(record.observedStatus)
    && record.terminalObservation !== null
    && SUCCESS_STATUSES.has(record.terminalObservation.observedStatus)
    && record.finalEngine === "rules"
  )
  if (attempted && final && attempted !== final) {
    return completed
      ? `원래 ${attempted}(으)로 실행하려 했으나 ${final}(으)로 완료했습니다.${reason ? ` ${reason}` : ""}`
      : `원래 ${attempted}(으)로 실행하려 했으나 ${final}(으)로 대체되었습니다. 실행 완료 여부는 확인되지 않았습니다.${reason ? ` ${reason}` : ""}`;
  }
  if (reason) return completed ? `${reason} 대체 실행으로 완료했습니다.` : `${reason} 대체 실행이 있었지만 실행 완료 여부는 확인되지 않았습니다.`;
  return completed ? "다른 방법으로 대체되어 완료했습니다." : "다른 방법으로 대체되었지만 실행 완료 여부는 확인되지 않았습니다.";
}

export function adapterLabel(code: string | null): string {
  if (!code) return "없음";
  return ADAPTER_LABELS[code] || code;
}

export function availabilityNote(reason: string): string {
  return AVAILABILITY_NOTES[reason] || "진단 기록을 확인할 수 없습니다.";
}

export type DiagnosticStateCode = "no_record" | "expired" | "partial_coverage" | "partial_loss" | "query_failed" | "running" | "failed" | "cancelled" | "unknown" | "rule_completed" | "normal";
export type DiagnosticStateTone = "muted" | "warning" | "error" | "running" | "done";
export type DiagnosticState = { readonly code: DiagnosticStateCode; readonly label: string; readonly tone: DiagnosticStateTone };

const STATE_LABELS: Record<DiagnosticStateCode, string> = {
  no_record: "기록 없음",
  expired: "보존 만료",
  partial_coverage: "진단 범위 제한",
  partial_loss: "기록 일부 누락",
  query_failed: "조회 실패",
  running: "실행 중",
  failed: "실행 실패",
  cancelled: "실행 취소",
  unknown: "결과 확인 필요",
  rule_completed: "규칙 기반으로 완료",
  normal: "정상 기록",
};

const STATE_TONES: Record<DiagnosticStateCode, DiagnosticStateTone> = {
  no_record: "muted",
  expired: "muted",
  partial_coverage: "warning",
  partial_loss: "warning",
  query_failed: "error",
  running: "running",
  failed: "error",
  cancelled: "warning",
  unknown: "warning",
  rule_completed: "done",
  normal: "done",
};

// 기록은 있지만 지금 읽을 수 없는 사유들. "기록 없음"(애초에 없음)과는 다른 버킷이다.
const QUERY_FAILURE_REASONS = new Set(["disabled", "writer_conflict", "quota_exceeded", "read_failed", "corrupt", "unsupported_version"]);
const RUNNING_AUTHORITY_STATUSES = new Set(["queued", "running", "cancel_requested", "committing"]);
const FAILED_STATUSES = new Set(["failed", "failed_cancel", "failed_commit", "failed_commit_recovery", "failed_restart"]);
const CANCELLED_STATUSES = new Set(["cancelled"]);
const TERMINAL_STATUSES = new Set([...SUCCESS_STATUSES, ...FAILED_STATUSES, ...CANCELLED_STATUSES]);

function hasActualLoss(record: DiagnosticRecord): boolean {
  return record.droppedEvents > 0 || record.droppedErrors > 0 || record.droppedIssues > 0 || record.issueCodes.length > 0;
}

function successfulTerminal(detail: DiagnosticDetail, record: DiagnosticRecord): boolean {
  if (record.finishedAt === null || !SUCCESS_STATUSES.has(record.observedStatus) || !record.terminalObservation || !SUCCESS_STATUSES.has(record.terminalObservation.observedStatus)) return false;
  // SharedJob authority must agree with the diagnostic. Direct executions have
  // no separate authority, so their own terminal observation is the authority.
  return detail.authorityState === "not_applicable"
    || (detail.authorityState === "matched" && SUCCESS_STATUSES.has(detail.authorityStatus || ""));
}

/** UI가 fallback 완료 문구를 쓸 때 사용하는 현재 권위 기반 성공 판정. */
export function diagnosticCompletionConfirmed(detail: DiagnosticDetail): boolean {
  return Boolean(detail.record && successfulTerminal(detail, detail.record));
}

function diagnosticStateCode(detail: DiagnosticDetail | null, fetchFailed: boolean): DiagnosticStateCode {
  if (fetchFailed || !detail) return "query_failed";
  if (detail.diagnosticQuality === "legacy_unavailable" || detail.availabilityReason === "missing_unknown") return "no_record";
  if (detail.availabilityReason === "expired") return "expired";
  if (QUERY_FAILURE_REASONS.has(detail.availabilityReason)) return "query_failed";
  const record = detail.record;
  if (!record) return "no_record";

  const authorityStatus = detail.authorityStatus;
  const observedStatus = record.observedStatus;
  const runStatus = authorityStatus || observedStatus;
  const terminalSuccess = successfulTerminal(detail, record);
  // firstFailure/errors may describe the engine attempt that was recovered by
  // a successful fallback. Only a terminal failure or an authoritative failed
  // status controls the run outcome; historical attempt errors stay visible in
  // developer details without turning a successful fallback into a failure.
  const hasFailureStatus = FAILED_STATUSES.has(runStatus)
    || FAILED_STATUSES.has(observedStatus)
    || Boolean(record.terminalFailure && !terminalSuccess);
  if (hasFailureStatus) return "failed";
  if (CANCELLED_STATUSES.has(runStatus) || CANCELLED_STATUSES.has(observedStatus)) return "cancelled";
  if (RUNNING_AUTHORITY_STATUSES.has(authorityStatus || "")) return "running";
  if (record.finishedAt === null && authorityStatus === null) return "unknown";
  if (detail.authorityState === "unavailable") return "unknown";
  if (detail.authorityState === "changed") {
    // A changed authority is no longer current evidence of this record. A
    // terminal failure above is still useful, but success must not be inferred.
    return "unknown";
  }
  if (!TERMINAL_STATUSES.has(runStatus) || !terminalSuccess) return "unknown";
  // Actual loss and coverage quality are separate from run outcome. Loss is
  // stronger because it says recorded events are missing, while partial
  // coverage only limits what can be claimed about the run.
  if (hasActualLoss(record)) return "partial_loss";
  if (detail.diagnosticQuality === "partial" || record.requiredProducerCoverage === "partial") return "partial_coverage";
  // 완료됐지만 규칙으로 대체된 실행은 "완료"와 같은 색이되, 문장으로 그 사실을 알린다 —
  // 색만으로 구분해야 한다면 그것도 계약 위반이다(DESIGN_SYSTEM.md 세그먼트 알약 사례와 같은 원칙).
  if (record.fallbackReason && record.finalEngine === "rules") return "rule_completed";
  return "normal";
}

export function classifyDiagnosticState(detail: DiagnosticDetail | null, fetchFailed: boolean): DiagnosticState {
  const code = diagnosticStateCode(detail, fetchFailed);
  return { code, label: STATE_LABELS[code], tone: STATE_TONES[code] };
}

// 0.6 D3 다음 단계 — 공통 진단 목록 행 전용 copy. Work Log 26필드가 없는 non-job
// (자동화·RSS·색인·direct) 실행도 함께 나오므로 featureCode를 직접 번역한다.
const FEATURE_LABELS: Record<string, string> = {
  briefing: "일일 브리핑",
  company_analysis: "기업 분석",
  topic_report: "딥 리서치",
  agent_chat: "Agent 대화",
  automation: "자동화",
  rss: "RSS 수집",
  index: "자료 인덱스",
  personal_judgment: "개인 판단 저장",
  jobs: "공통 작업",
  http: "요청 처리",
  startup: "서버 시작",
};

export function featureLabel(code: string): string {
  return FEATURE_LABELS[code] || code;
}

/**
 * A diagnostic can only offer an existing, bounded inspection surface. The
 * report identifier is deliberately not part of this mapping: a run tells us
 * which feature to inspect, but it does not prove which report (if any) was
 * durably saved. `wait`/`none` and retry-oriented actions therefore never
 * become a clickable action here.
 */
const DIAGNOSTIC_INSPECTION_HREFS: Record<string, string> = {
  briefing: "#/briefing",
  company_analysis: "#/analysis",
  topic_report: "#/deep-research",
  automation: "#/settings",
  rss: "#/rss",
};

export type DiagnosticInspectionTarget = {
  readonly href: string;
  readonly label: "목록에서 확인" | "설정에서 확인";
};

export function diagnosticInspectionTarget(featureCode: string, nextActionCode: string): DiagnosticInspectionTarget | null {
  if (nextActionCode === "check_settings") {
    // Only report features with an existing, bounded settings surface. A
    // diagnostic must not turn an arbitrary feature code into a guessed link.
    return DIAGNOSTIC_INSPECTION_HREFS[featureCode]
      ? { href: "#/settings", label: "설정에서 확인" }
      : null;
  }
  if (nextActionCode !== "inspect_result") return null;
  const href = DIAGNOSTIC_INSPECTION_HREFS[featureCode];
  return href ? { href, label: featureCode === "automation" ? "설정에서 확인" : "목록에서 확인" } : null;
}

export type DiagnosticOutcomeTone = "muted" | "warning" | "error" | "running" | "done";
const OUTCOME_LABELS: Record<string, string> = {
  succeeded: "성공",
  failed: "실패",
  cancelled: "취소됨",
  running: "실행 중",
  unknown: "확인 안 됨",
};
const OUTCOME_TONES: Record<string, DiagnosticOutcomeTone> = {
  succeeded: "done",
  failed: "error",
  cancelled: "muted",
  running: "running",
  unknown: "muted",
};

export function outcomeLabel(code: string): string {
  return OUTCOME_LABELS[code] || code;
}

export function outcomeTone(code: string): DiagnosticOutcomeTone {
  return OUTCOME_TONES[code] || "muted";
}
