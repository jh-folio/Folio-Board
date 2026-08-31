/**
 * 검증 루프의 공용 표시 언어 (0.6 Stage C).
 *
 * 내러티브 카드와 Watchlist Thesis workspace가 **같은 verdict·시각·근거 변화 언어**를
 * 써야 한다(계획 C.3). 두 화면이 각자 라벨을 만들면 같은 상태가 두 이름을 갖는다.
 *
 * 판정은 **두 층이고 섞지 않는다**(계획 §3.2):
 *
 * - 체크포인트 판정 3값 — `confirmed | challenged | no_signal`
 * - Thesis 종합 verdict 6값 — `strengthened | maintained | ... | insufficient_evidence`
 *
 * 상태는 **색으로만 전달하지 않는다**. 각 항목이 아이콘(텍스트 기호)과 라벨을 함께
 * 갖고, 색은 그 위에 얹는 보조 신호다(WCAG 1.4.1).
 */

export type CheckpointStatus = "open" | "confirmed" | "challenged" | "expired";
export type SilenceLevel = "active" | "cooling" | "dormant" | "unknown";

type Display = {
  /** 색 없이도 읽히는 텍스트 기호. 이모지가 아니라 기호라서 폰트에 좌우되지 않는다. */
  icon: string;
  label: string;
  /** `.chip` 프리미티브의 data-tone 값. 색은 보조 신호다. */
  tone: "muted" | "burgundy" | "gold" | "blue" | "teal";
};

export const CHECKPOINT_STATUS_DISPLAY: Record<CheckpointStatus, Display> = {
  confirmed: { icon: "✓", label: "확인됨", tone: "teal" },
  challenged: { icon: "!", label: "반증 신호", tone: "burgundy" },
  open: { icon: "·", label: "확인 대기", tone: "muted" },
  expired: { icon: "×", label: "기한 경과", tone: "gold" },
};

export const SILENCE_DISPLAY: Record<SilenceLevel, Display> = {
  active: { icon: "·", label: "최근 근거 있음", tone: "muted" },
  cooling: { icon: "↓", label: "식어가는 중", tone: "gold" },
  dormant: { icon: "↓", label: "정리 후보", tone: "burgundy" },
  unknown: { icon: "?", label: "근거 없음", tone: "muted" },
};

/** Thesis 종합 verdict(6값). 체크포인트 판정과 한 배지로 합치지 않는다. */
export const THESIS_VERDICT_DISPLAY: Record<string, Display> = {
  strengthened: { icon: "▲", label: "강화", tone: "teal" },
  maintained: { icon: "=", label: "유지", tone: "muted" },
  weakened: { icon: "▼", label: "약화", tone: "gold" },
  at_risk: { icon: "!", label: "이탈 위험", tone: "burgundy" },
  broken: { icon: "×", label: "이탈", tone: "burgundy" },
  insufficient_evidence: { icon: "?", label: "판단 보류", tone: "muted" },
};

export const MOMENTUM_LABELS: Record<string, string> = {
  strengthening: "강화",
  stable: "유지",
  fading: "약화",
  turning: "전환",
  conflicted: "혼재",
  agent: "Agent 판단",
};

export const NARRATIVE_STATUS_LABELS: Record<string, string> = {
  active: "활성",
  watch: "관찰",
  resolved: "종료",
  overridden: "대체됨",
};

export function checkpointDisplay(status: string | undefined): Display {
  return CHECKPOINT_STATUS_DISPLAY[(status || "open") as CheckpointStatus] || CHECKPOINT_STATUS_DISPLAY.open;
}

export function silenceDisplay(level: string | undefined): Display {
  return SILENCE_DISPLAY[(level || "unknown") as SilenceLevel] || SILENCE_DISPLAY.unknown;
}

export function thesisVerdictDisplay(verdict: string | undefined): Display {
  return THESIS_VERDICT_DISPLAY[verdict || "insufficient_evidence"] || THESIS_VERDICT_DISPLAY.insufficient_evidence;
}

/**
 * 이력의 전환 값(`open` → `confirmed`, `stable` → `strengthening`)을 사람 말로 옮긴다.
 * 내부 enum 문자열은 화면에 나가지 않는다 — 상태 라벨은 이미 이 파일이 갖고 있다.
 */
export function transitionLabel(kind: string, value: string | undefined): string {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  if (kind === "momentum") return MOMENTUM_LABELS[raw] || raw;
  if (kind === "confidence") return raw;
  return CHECKPOINT_STATUS_DISPLAY[raw as CheckpointStatus]?.label || THESIS_VERDICT_DISPLAY[raw]?.label || raw;
}

/** 날짜 한 줄. 두 화면이 같은 자리에서 같은 모양으로 시각을 말한다. */
export function verificationDate(value: string | null | undefined): string {
  const text = String(value || "").slice(0, 10);
  return text || "—";
}
