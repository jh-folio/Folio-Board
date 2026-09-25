import { useCallback, useEffect, useState } from "react";
import { deleteJson, getJson, postJson } from "../../api";
import type { ConsultationSession } from "./types";

type ThreadListPayload = { items?: ConsultationSession[]; nextCursor?: string | null };

// 주제는 별도 이름이 아니라 칩으로 보여준다. 화면에서는 전부 "대화"다.
const SCOPE_LABELS: Record<string, string> = {
  watchlist: "관심 종목",
  portfolio: "포트폴리오",
  briefing: "브리핑",
  company_analysis: "기업 분석",
  topic_report: "딥 리서치",
  market_memory: "시장 내러티브",
  investment_review: "투자 리뷰",
  change: "변화",
};

export function scopeChipLabel(scope: ConsultationSession["scope"] | undefined): string {
  if (!scope || scope.kind === "general") return "";
  const base = SCOPE_LABELS[scope.kind] || scope.kind;
  // market-memory stateId는 저장소 식별자라 사용자용 대화 칩에 노출하지 않는다.
  if (scope.kind === "market_memory") return base;
  // Date/revision is the human-visible identity of a stored review.  Never
  // surface its internal input fingerprint in a conversation chip.
  if (scope.kind === "investment_review") return scope.id ? `${scope.id} · r${scope.revision || 0}` : base;
  // 티커가 있으면 그게 가장 알아보기 쉬운 표시다.
  const subject = (scope.tickers && scope.tickers[0]) || scope.id || "";
  return subject ? `${subject}` : base;
}

/** 목록에서는 "언제"가 정확한 시각보다 유용하다. */
function relativeTime(value: string | undefined): string {
  if (!value) return "";
  const at = Date.parse(value);
  if (Number.isNaN(at)) return "";
  const minutes = Math.floor((Date.now() - at) / 60000);
  if (minutes < 1) return "방금";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  return days < 7 ? `${days}일 전` : new Date(at).toLocaleDateString();
}

export function ThreadList({
  activeId,
  refreshKey,
  onSelect,
  onDeleted,
}: {
  activeId: string;
  refreshKey: number;
  onSelect: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  const [threads, setThreads] = useState<ConsultationSession[]>([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [renamingId, setRenamingId] = useState("");
  const [titleDraft, setTitleDraft] = useState("");

  const load = useCallback(async () => {
    try {
      const payload = await getJson<ThreadListPayload>("/api/agent/threads?limit=60");
      setThreads(payload.items || []);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "대화 목록을 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => { void load(); }, [load, refreshKey]);

  async function remove(thread: ConsultationSession) {
    // 지운 대화는 되돌릴 수 없다. 저장소도 confirmed 없이는 지우지 않는다.
    if (!window.confirm(`"${thread.title}" 대화를 삭제할까요? 삭제 후 복구할 수 없습니다.`)) return;
    setBusyId(thread.id);
    try {
      await deleteJson(`/api/agent/threads/${encodeURIComponent(thread.id)}`, { confirm: true });
      onDeleted(thread.id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "삭제하지 못했습니다.");
    } finally {
      setBusyId("");
    }
  }

  async function archive(thread: ConsultationSession) {
    setBusyId(thread.id);
    try {
      await postJson(`/api/agent/threads/${encodeURIComponent(thread.id)}/archive`, {});
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "보관하지 못했습니다.");
    } finally {
      setBusyId("");
    }
  }

  async function rename(thread: ConsultationSession) {
    const title = titleDraft.trim();
    setRenamingId("");
    if (!title || title === thread.title) return;
    setBusyId(thread.id);
    try {
      await postJson(`/api/agent/threads/${encodeURIComponent(thread.id)}`, { title });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "제목을 바꾸지 못했습니다.");
    } finally {
      setBusyId("");
    }
  }

  // 보관한 대화는 목록에서 빼고 개수만 알린다. 활성 대화가 밀리지 않게 한다.
  const active = threads.filter((thread) => thread.status !== "archived");
  const archivedCount = threads.length - active.length;

  return (
    <div className="agent-threads" aria-label="저장된 대화">
      <p className="agent-threads__summary">
        <span>{active.length ? `대화 ${active.length}개` : "저장된 대화 없음"}</span>
        {archivedCount > 0 && <span>보관 {archivedCount}개</span>}
      </p>
      {error && <p className="agent-threads__error">{error}</p>}
      {!active.length && !error && (
        <p className="agent-threads__empty">질문을 보내면 대화가 여기에 저장됩니다.</p>
      )}
      <ul>
        {active.map((thread) => {
          const chip = scopeChipLabel(thread.scope);
          const meta = [chip, thread.messageCount ? `${thread.messageCount}개` : "", relativeTime(thread.updatedAt)]
            .filter(Boolean)
            .join(" · ");
          return (
            <li key={thread.id} data-active={thread.id === activeId ? "true" : undefined}>
              {renamingId === thread.id ? (
                <form
                  className="agent-threads__rename"
                  onSubmit={(event) => { event.preventDefault(); void rename(thread); }}
                >
                  <input
                    value={titleDraft}
                    autoFocus
                    aria-label="대화 제목"
                    onChange={(event) => setTitleDraft(event.currentTarget.value)}
                    onBlur={() => void rename(thread)}
                  />
                </form>
              ) : (
                <button
                  type="button"
                  className="agent-threads__open"
                  aria-current={thread.id === activeId ? "true" : undefined}
                  onClick={() => onSelect(thread.id)}
                >
                  <span className="agent-threads__title">{thread.title}</span>
                  <span className="agent-threads__meta">{meta || "비어 있음"}</span>
                </button>
              )}
              <span className="agent-threads__actions">
                <button
                  type="button" className="btn btn--icon btn--sm" disabled={busyId === thread.id}
                  aria-label={`${thread.title} 제목 바꾸기`} data-tooltip="제목"
                  onClick={() => { setRenamingId(thread.id); setTitleDraft(thread.title); }}
                >
                  <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M11 2.5l2.5 2.5-8 8H3v-2.5z" strokeLinejoin="round" />
                  </svg>
                </button>
                <button
                  type="button" className="btn btn--icon btn--sm" disabled={busyId === thread.id}
                  aria-label={`${thread.title} 보관하기`} data-tooltip="보관"
                  onClick={() => void archive(thread)}
                >
                  <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M2 4.5h12M3.5 4.5v8h9v-8M6.5 7.5h3" strokeLinecap="round" />
                  </svg>
                </button>
                <button
                  type="button" className="btn btn--icon btn--sm" disabled={busyId === thread.id}
                  aria-label={`${thread.title} 삭제하기`} data-tooltip="삭제"
                  onClick={() => void remove(thread)}
                >
                  <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4">
                    <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
