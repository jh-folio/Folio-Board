import { openReactAgentDock } from "../agentContext";
import type { ConsultationSession } from "./types";

export type ScopedThreadRequest = {
  title?: string;
  scope: ConsultationSession["scope"];
  initialMessage?: string;
  /** 명시 action에서만 새 scoped thread를 만들고 첫 문장을 즉시 보낸다. */
  autoSubmit?: boolean;
  requestId?: string;
};

/**
 * 주제가 붙은 대화를 시작하며 도크를 연다.
 *
 * 도크가 대화의 집이다. 예전에는 별도 상담 패널이 떴는데, 같은 일을 하는 화면이
 * 둘이면 대화 목록도 둘로 갈린다. 주제는 별도 이름이 아니라 칩으로 보여준다.
 */
export function openScopedThread(request: ScopedThreadRequest): Promise<void> {
  const requestId = request.requestId || crypto.randomUUID();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => finish(new Error("Agent 요청을 확인하지 못했습니다. 다시 시도하세요.")), 15000);
    const finish = (error?: Error) => {
      window.clearTimeout(timeout);
      window.removeEventListener("folio:agent-thread-ack", acknowledge);
      if (error) reject(error); else resolve();
    };
    const acknowledge = (event: Event) => {
      const detail = (event as CustomEvent<{ requestId?: string; ok?: boolean; error?: string }>).detail || {};
      if (detail.requestId !== requestId) return;
      finish(detail.ok ? undefined : new Error(detail.error || "Agent 요청에 실패했습니다."));
    };
    window.addEventListener("folio:agent-thread-ack", acknowledge);
    window.dispatchEvent(new CustomEvent<ScopedThreadRequest>("folio:open-agent-thread", { detail: { ...request, requestId } }));
    openReactAgentDock({});
  });
}
