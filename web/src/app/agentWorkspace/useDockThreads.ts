import { useCallback, useEffect, useRef, useState } from "react";
import { deleteJson, getJson, postJson } from "../../api";
import {
  AGENT_HOME_THREAD_STORAGE_KEY,
  getAgentThreadMessages,
  isGreeting,
  resetAgentThreadMessages,
} from "./storage";
import type { AgentMessage, ConsultationMessage, ConsultationSession } from "./types";

const MIGRATED_KEY = "folio.agentThreads.migrated.v1";

// 도크가 대화의 집이다. 대화는 서버에 저장되므로 브라우저를 닫아도, 기기를 바꿔도
// 남고 — 무엇보다 Agent가 다음 세션에서 context로 읽을 수 있다. localStorage에만
// 있던 예전 구조에서는 그게 원천적으로 불가능했다.

function toAgentMessage(row: ConsultationMessage, index: number): AgentMessage {
  return {
    id: row.id || `restored-${index}`,
    role: row.role === "assistant" ? "assistant" : "user",
    text: String(row.content || ""),
    createdAt: row.createdAt,
  };
}

/** 아직 서버에 만들지 않은 대화의 주제와 제목. 첫 메시지에서 실제 스레드가 된다. */
export type PendingThread = { title?: string; scope?: ConsultationSession["scope"] };

export function useDockThreads(welcome: AgentMessage) {
  const [threadId, setThreadId] = useState("");
  const [pending, setPending] = useState<PendingThread | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [scope, setScope] = useState<ConsultationSession["scope"] | null>(null);
  const migratedRef = useRef(false);

  const bumpList = useCallback(() => setRefreshKey((value) => value + 1), []);

  const createThread = useCallback(async (detail: { title?: string; scope?: ConsultationSession["scope"] } = {}) => {
    const created = await postJson<ConsultationSession>("/api/agent/threads", {
      title: detail.title || "새 대화",
      // 주제를 주지 않으면 주제 없는 대화다. 예전에는 알 수 없는 주제가 조용히
      // 포트폴리오로 떨어져 무관한 대화에 포트폴리오 맥락이 딸려 들어갔다.
      scope: detail.scope || { kind: "general" },
    });
    setThreadId(created.id);
    setScope(created.scope || null);
    setPending(null);
    bumpList();
    return created;
  }, [bumpList]);

  const openThread = useCallback(async (id: string): Promise<AgentMessage[]> => {
    const session = await getJson<ConsultationSession>(`/api/agent/threads/${encodeURIComponent(id)}`);
    setThreadId(session.id);
    setScope(session.scope || null);
    setPending(null);
    const rows = session.messages || [];
    return rows.length ? rows.map(toAgentMessage) : [{ ...welcome, createdAt: new Date().toISOString() }];
  }, [welcome]);

  const deleteEmptyThread = useCallback(async (id: string) => {
    await deleteJson(`/api/agent/threads/${encodeURIComponent(id)}`, { confirm: true });
    if (threadId === id) {
      setThreadId("");
      setScope(null);
      setPending(null);
    }
    bumpList();
  }, [bumpList, threadId]);

  /** 브라우저에만 있던 대화를 서버 스레드로 한 번 옮긴다. 실패하면 원본을 지우지 않는다. */
  const migrateLocalThread = useCallback(async () => {
    if (migratedRef.current) return;
    migratedRef.current = true;
    if (window.localStorage.getItem(MIGRATED_KEY)) return;
    const local = getAgentThreadMessages().filter((row) => row.text && !isGreeting(row));
    if (!local.length) {
      window.localStorage.setItem(MIGRATED_KEY, new Date().toISOString());
      return;
    }
    try {
      // 기록만 옮긴다. 메시지 API로 재생하면 옛 질문이 전부 Agent 잡으로 다시 실행된다.
      const created = await postJson<ConsultationSession>("/api/agent/threads", {
        title: "이전 대화",
        scope: { kind: "general" },
        importMessages: local.map((row) => ({ role: row.role, content: row.text, createdAt: row.createdAt })),
      });
      // 저장된 건수를 확인하고 나서야 원본을 지운다. 2xx만 믿으면 옛 서버처럼
      // importMessages를 모르는 쪽에 붙었을 때 빈 대화를 만들고 원본을 지운다.
      if ((created.messageCount || 0) < local.length) {
        await deleteJson(`/api/agent/threads/${encodeURIComponent(created.id)}`, { confirm: true }).catch(() => {});
        migratedRef.current = false;
        return;
      }
      window.localStorage.setItem(MIGRATED_KEY, new Date().toISOString());
      resetAgentThreadMessages();
      window.localStorage.removeItem(AGENT_HOME_THREAD_STORAGE_KEY);
      bumpList();
    } catch {
      // 이관은 편의 기능이다. 실패해도 사용자가 쓰던 대화는 브라우저에 남는다.
      migratedRef.current = false;
    }
  }, [bumpList]);

  /** 마지막 Agent 답변. 잡 결과에는 transcript를 담지 않으므로 스레드에서 읽는다. */
  const latestReply = useCallback(async (id: string): Promise<string> => {
    try {
      const session = await getJson<ConsultationSession>(`/api/agent/threads/${encodeURIComponent(id)}`);
      const rows = session.messages || [];
      for (let index = rows.length - 1; index >= 0; index -= 1) {
        if (rows[index].role === "assistant") return String(rows[index].content || "");
      }
    } catch {
      // 답변을 못 읽어도 대화는 서버에 남아 있다. 호출부가 안내 문구를 쓴다.
    }
    return "";
  }, []);

  useEffect(() => { void migrateLocalThread(); }, [migrateLocalThread]);

  return { threadId, setThreadId, scope, setScope, pending, setPending, refreshKey, bumpList, createThread, openThread, deleteEmptyThread, latestReply };
}
