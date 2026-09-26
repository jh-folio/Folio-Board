import type { WorkLogEntry } from "../api";

// Work Log는 안전한 코드 값만 받는다. 화면에는 그 코드를 사람이 읽는 문장으로만 바꿔 보여준다.
// 새 코드가 추가되면 사전에 없더라도 코드 원문을 그대로 노출해 정보가 사라지지 않게 한다.

const TASK_TITLES: Record<WorkLogEntry["taskType"], string> = {
  macro_refresh: "거시 자료 갱신",
  companion: "Agent와 대화",
  briefing: "일일 브리핑 생성",
  company_analysis: "기업 분석 생성",
  topic_report: "딥 리서치 생성",
  personal_overlay: "내 노트와 연결",
  thesis_delta: "투자 논거 변화 점검",
  market_memory_llm: "시장 메모리 정리",
  market_state_snapshot: "시장 상태 정리",
  market_memory_update: "시장 메모리 갱신",
  quality_repair: "보고서 품질 보완",
  investment_review: "투자 리뷰 생성",
  index: "자료 인덱스 갱신",
  rss: "RSS 수집",
  setup: "초기 설정",
};

const STATUS_LABELS: Partial<Record<WorkLogEntry["status"], string>> = {
  queued: "대기 중",
  running: "진행 중",
  committing: "저장 중",
  cancel_requested: "취소 요청됨",
  done: "완료",
  cancelled: "취소됨",
  failed: "실패",
  failed_cancel: "취소 중 실패",
  failed_commit: "저장 실패",
  failed_restart: "재시작 중 중단",
  failed_commit_recovery: "저장 복구 실패",
};

const STATUS_TONES: Partial<Record<WorkLogEntry["status"], WorkLogTone>> = {
  queued: "waiting",
  running: "running",
  committing: "running",
  cancel_requested: "waiting",
  done: "done",
  cancelled: "cancelled",
};

const ENGINE_LABELS: Record<string, string> = {
  llm_api: "AI 직접 호출",
  llm_cli: "AI CLI",
  rules: "규칙 기반",
  none: "실행 없음",
};

export const ADAPTER_LABELS: Record<string, string> = {
  auto: "자동 선택",
  codex: "Codex",
  claude: "Claude",
  antigravity: "Antigravity",
  openai_api: "OpenAI",
  gemini_api: "Gemini",
  claude_api: "Claude API",
  rules: "규칙 기반",
  none: "없음",
};

const ARTIFACT_LABELS: Record<string, string> = {
  briefing: "브리핑",
  company_analysis: "기업 분석",
  topic_report: "딥 리서치",
  personal_overlay: "개인 해석",
  market_state: "시장 상태",
  investment_review: "투자 리뷰",
  thesis_delta: "투자 논거 변화",
};

export const FALLBACK_REASONS: Record<string, string> = {
  engine_unavailable: "선택한 AI를 쓸 수 없어 다른 방법으로 실행했습니다.",
  engine_failed: "AI 실행이 실패해 다른 방법으로 대체했습니다.",
  confirmed_zero_evidence: "근거가 없는 상태를 확인하고 규칙 기반으로 실행했습니다.",
};

const ERROR_REASONS: Record<string, string> = {
  adapter_unavailable: "연결된 AI 도구를 찾지 못했습니다.",
  adapter_failed: "AI 도구 실행이 실패했습니다.",
  validation_failed: "요청 값이 올바르지 않아 중단했습니다.",
  save_failed: "결과를 저장하지 못했습니다.",
  cancel_failed: "취소 처리를 끝내지 못했습니다.",
  restart_interrupted: "서버 재시작으로 작업이 끊겼습니다.",
  commit_recovery_failed: "저장 복구에 실패했습니다.",
  private_cleanup_failed: "임시 파일 정리에 실패했습니다.",
  store_unavailable: "작업 저장소를 읽지 못했습니다.",
  internal_error: "예기치 못한 오류가 발생했습니다.",
};

const PROPOSAL_LABELS: Record<string, string> = {
  pending: "승인 대기 중인 수정 제안이 있습니다.",
  applying: "수정 제안을 반영하는 중입니다.",
  applied: "수정 제안을 반영했습니다.",
  rejected: "수정 제안을 거절했습니다.",
  stale: "수정 제안이 만료되었습니다.",
  conflict: "수정 제안이 최신 보고서와 충돌합니다.",
  failed_apply: "수정 제안 반영에 실패했습니다.",
  unavailable: "수정 제안을 열 수 없습니다.",
};

export type WorkLogTone = "running" | "done" | "failed" | "cancelled" | "waiting";

export type WorkLogItemCopy = {
  readonly title: string;
  readonly statusLabel: string;
  readonly tone: WorkLogTone;
  readonly outcome: string;
  readonly details: readonly string[];
  readonly attention: string;
};

function fallbackCode(value: string | null) {
  return value ? value.split("_").join(" ") : "";
}

function statusTone(entry: WorkLogEntry): WorkLogTone {
  const known = STATUS_TONES[entry.status];
  if (known) return known;
  return entry.status.startsWith("failed") ? "failed" : "running";
}

function artifactSummary(entry: WorkLogEntry) {
  if (!entry.artifactCount) return "";
  const names = entry.artifactTypes.map((type) => ARTIFACT_LABELS[type] || fallbackCode(type)).filter(Boolean);
  return names.length ? `${names.join(", ")} ${entry.artifactCount}건 저장` : `산출물 ${entry.artifactCount}건 저장`;
}

/** 하나의 작업 기록을 제목 · 상태 · 결과 한 줄 · 보조 설명으로 정리한다. */
export function workLogItemCopy(entry: WorkLogEntry): WorkLogItemCopy {
  const title = TASK_TITLES[entry.taskType] || fallbackCode(entry.taskType) || "Agent 작업";
  const statusLabel = STATUS_LABELS[entry.status] || fallbackCode(entry.status);
  const tone = statusTone(entry);

  const saved = artifactSummary(entry);
  const outcome = tone === "running" || tone === "waiting"
    ? entry.progress > 0 ? `${entry.progress}% 진행` : "시작을 기다리는 중"
    : tone === "cancelled"
      ? "사용자가 중단했습니다."
      : tone === "failed"
        ? ERROR_REASONS[entry.errorCode || ""] || "작업을 끝내지 못했습니다."
        : saved || (entry.taskType === "companion" ? "답변을 마쳤습니다." : "저장한 산출물 없이 끝났습니다.");

  const details: string[] = [];
  const engine = ENGINE_LABELS[entry.generationMode];
  const adapter = ADAPTER_LABELS[entry.adapter];
  if (engine && entry.generationMode !== "none") {
    details.push(adapter && entry.adapter !== "none" ? `${engine} · ${adapter}` : engine);
  }
  if (entry.fallbackReason) {
    details.push(FALLBACK_REASONS[entry.fallbackReason] || fallbackCode(entry.fallbackReason));
  }
  if (tone === "done" && saved && outcome !== saved) details.push(saved);

  const attention = entry.proposalStatus ? PROPOSAL_LABELS[entry.proposalStatus] || fallbackCode(entry.proposalStatus) : "";

  return { title, statusLabel, tone, outcome, details, attention };
}

/** 접힌 Work Log 머리말에 쓰는 한 줄 요약. */
export function workLogLatestSummary(entry: WorkLogEntry | undefined, loading: boolean) {
  if (loading && !entry) return "확인 중";
  if (!entry) return "최근 작업 없음";
  const copy = workLogItemCopy(entry);
  return `최근: ${copy.title} · ${copy.statusLabel}`;
}
