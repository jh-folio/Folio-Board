import { ApiRequestError } from "../../api";
import type { SourceRef } from "./types";

export function errorCopy(error: unknown) {
  const code = error instanceof ApiRequestError ? error.code : "";
  const labels: Record<string, string> = {
    inputs_changed: "확인 중 입력이 바뀌었습니다. 현재 자료를 새로 읽고 다시 미리보기를 확인해 주세요.",
    ownership_review_changed: "이 점검이나 기준 기록이 바뀌었습니다. 자료를 다시 읽고 최신 점검에서 이어 주세요.",
    ownership_condition_changed: "연결한 조건 판본을 확인할 수 없습니다. 자료를 다시 읽고 정확한 조건을 선택해 주세요.",
    ownership_condition_unavailable: "당시 조건 본문을 확인할 수 없어 해소로 기록할 수 없습니다. 미해결로 남기거나 현재 자료로 별도 검토해 주세요.",
    previous_ownership_review_unavailable: "이전 검토본문이 없어 이어 쓸 수 없습니다. 현재 자료로 별도 점검을 남겨 주세요.",
    ownership_condition_requires_preserved_reason: "선택한 현재 조건을 다시 읽으려면 투자 이유와 조건을 함께 보존해야 합니다.",
    ownership_scope_required: "검토 완료를 표시하려면 이번에 확인한 범위를 하나 이상 선택해 주세요.",
    unresolved_ownership_review: "보류·예외·근거 공백이 남아 있습니다. 미해결로 기록해 주세요. 검토 완료 표시는 함께 남길 수 있습니다.",
    invalid_ownership_refs: "출처 주소 또는 식별자를 확인해 주세요. 주소는 http 또는 https 형식이어야 합니다.",
    invalid_ownership_time: "날짜와 시각 형식을 확인해 주세요. 정확한 시각에는 시차 정보가 필요합니다.",
    case_revision_changed: "다른 작업에서 기록이 바뀌었습니다. 새로 읽고 다시 확인해 주세요.",
    preview_expired: "미리보기 확인 시간이 지났습니다. 다시 미리보기를 열어 주세요.",
    case_recovery_required: "마무리하지 못한 저장 또는 삭제가 있습니다. 아래 복구 항목을 확인해 주세요.",
    journal_deletion_pending: "본문 삭제를 마무리하는 중입니다. 복구가 끝날 때까지 본문을 표시하지 않습니다.",
    journal_integrity_error: "저장된 본문이 원래 기록과 달라 내용을 확인할 수 없습니다.",
    journal_file_missing: "기록 파일을 찾을 수 없습니다. 현재 자료로 대체하지 않았습니다.",
    recovery_unavailable: "준비된 파일이 없거나 달라 복구할 수 없습니다. 미완료 저장을 취소한 뒤 새 기록을 만들어 주세요.",
    recovery_requires_confirmation: "이전 삭제 작업에 원본 판본 확인 정보가 없어 자동으로 이어갈 수 없습니다. 현재 원본은 유지했습니다. 삭제 작업 점검이 필요합니다.",
    previous_journal_required: "연결할 이전 기록을 선택해 주세요.",
    journal_episode_mismatch: "현재 검토의 기록을 선택해 주세요. 이전 검토를 다시 시작하려면 새 검토 시작을 선택하세요.",
    lifecycle_unchanged: "이미 같은 검토 단계입니다.",
    invalid_user_reported_time: "사용자 보고 시점의 날짜와 시간을 확인해 주세요.",
    sensitive_content_requires_exclusion: "기기 경로나 자격 증명 형태가 포함되어 있습니다. 내용을 정정하거나 해당 보존 항목을 제외해 주세요.",
    journal_changed: "기록 내용이 바뀌었습니다. 다시 열고 삭제 범위를 확인해 주세요.",
    source_changed: "원자료가 새 판본으로 바뀌었습니다. 새 자료의 삭제 범위를 다시 확인해 주세요.",
    journal_links_changed: "연결 기록이 바뀌었습니다. 삭제 범위를 다시 확인해 주세요.",
    source_not_found: "원자료를 찾을 수 없습니다. 보존 기록은 기록 탭에서 별도로 확인하세요.",
  };
  return labels[code] || "처리 결과를 확인하지 못했습니다. 입력을 유지했습니다. 새로 읽거나 같은 작업을 다시 확인해 주세요.";
}
export const timeLabel = (value?: string | null) => value ? new Date(value).toLocaleString("ko-KR", { timeZoneName: "short" }) : "알 수 없음";
export const inputState = (status: string) => ({ preserved: "보존", unavailable: "자료 없음", excluded: "사용자가 제외", purged: "본문 삭제" }[status] || "확인 필요");
export function sourceDeletePartialNotice(result: { outcome?: string; sourceOutcome?: string }) {
  if (result.outcome !== "partial") return "";
  return result.sourceOutcome === "changed" ? "확인한 보존 정책은 반영했지만 이후 복원되거나 바뀐 원본은 남겨 두었습니다. 현재 원본을 삭제하려면 새로 확인해 주세요." : "확인한 보존 정책은 반영했지만 원본은 이미 없어 삭제 여부를 확인할 수 없습니다.";
}
export function sourceState(status: string) { return ({ current: "원본 판본 일치", source_changed: "원본에 이후 변경 있음", source_missing: "원본 없음 · 보존본 별도 존재", source_unreadable: "현재 원본 확인 불가", unknown: "현재 원본 확인 불가" }[status] || "현재 상태 미확인"); }
export function sourceLink(ref: SourceRef) {
  if (!ref.id) return null;
  if (ref.kind === "company") return `#/analysis/${encodeURIComponent(ref.id)}`;
  if (ref.kind === "topic") return `#/deep-research/${encodeURIComponent(ref.id)}`;
  if (ref.kind === "investment_review") return `#/portfolio?tab=review&date=${encodeURIComponent(ref.id)}`;
  return null;
}
