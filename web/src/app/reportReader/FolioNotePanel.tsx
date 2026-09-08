import { useEffect, useMemo, useRef, useState } from "react";
import { getJson, isActiveJobStatus, postJson, type JobStatus } from "../../api";
import { HypothesisReviewCard } from "./HypothesisReviewCard";
import type { PersonalOverlayPayload } from "../deepResearchPayload";
import { PersonalOverlayView } from "./PersonalOverlayView";
import { ReportBody } from "./ReportBody";

type NoteTab = "chat" | "links";

type NoteEvent = {
  role: "user" | "agent" | string;
  body: string;
  createdAt?: string;
  summary?: string;
};

type InvestmentNote = {
  id?: string;
  title?: string;
  body?: string;
  noteType?: string;
  ticker?: string;
  updatedAt?: string;
  tags?: string[];
  rawThoughts?: NoteEvent[];
  interactionLog?: NoteEvent[];
};

type LinkedNotesPayload = {
  notes?: InvestmentNote[];
};

type AgentResult = {
  reply?: string;
  notice?: string;
};

type AgentJob = {
  id: string;
  status: JobStatus;
  message?: string;
  error?: string;
  result?: AgentResult;
};

export type FolioNoteIdentity = {
  id: string;
  noteType: string;
  title: string;
  ticker?: string;
  company?: string;
  topic?: string;
  label?: string;
  reportKind?: string;
  reportId?: string;
  linkedReports?: string[];
};

const INVESTMENT_NOTE_TEMPLATE = [
  "## 현재 관점",
  "",
  "## 왜 중요한가",
  "",
  "## 근거",
  "",
  "## 반대 근거",
  "",
  "## 다음 체크포인트",
  "",
  "## 결정/업데이트 로그",
  "",
].join("\n");

const THOUGHT_PLACEHOLDER = [
  "떠오르는 생각을 자유롭게 정리해보세요. 막연한 느낌이나 궁금증 한 줄만 작성해도 됩니다.",
  "",
  '예시: "이 주식은 앞으로 받을 수혜가 커 보여서 관심 있음"',
  '예시: "가격이 너무 오른 것 같은데 그래도 들고 갈 만한가?"',
].join("\n");

const CHAT_REPLY_MARKER = "[대화]";
const NOTE_BODY_MARKER = "[투자 노트]";

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function pollAgentJob(job: AgentJob): Promise<AgentJob> {
  let current = job;
  while (isActiveJobStatus(current.status)) {
    await sleep(1000);
    current = await getJson<AgentJob>(`/api/jobs/${encodeURIComponent(current.id)}`);
  }
  if (current.status !== "done") {
    throw new Error(current.message || current.error || "Agent 작업에 실패했습니다.");
  }
  return current;
}

// Agent 응답을 대화 메시지와 완성 노트 본문으로 분리한다.
// [투자 노트] 마커가 없으면 전체를 대화 메시지로 취급하고 노트는 바꾸지 않는다.
export function splitAgentReply(reply: string): { message: string; note: string } {
  const raw = String(reply || "");
  const markerIndex = raw.indexOf(NOTE_BODY_MARKER);
  const stripChatMarker = (text: string) => text.replace(/^\s*\[대화\]\s*/, "").trim();
  if (markerIndex < 0) {
    return { message: stripChatMarker(raw), note: "" };
  }
  return {
    message: stripChatMarker(raw.slice(0, markerIndex)),
    note: raw.slice(markerIndex + NOTE_BODY_MARKER.length).trim(),
  };
}

function appendThought(events: NoteEvent[], thought: string): NoteEvent[] {
  const body = thought.trim();
  if (!body) return events;
  const last = events[events.length - 1];
  if (last?.role === "user" && last.body.trim() === body) return events;
  return [...events, { role: "user", body, createdAt: new Date().toISOString() }];
}

function appendAgentLog(events: NoteEvent[], body: string, summary = ""): NoteEvent[] {
  return [...events, {
    role: "agent",
    body,
    summary: summary || "Agent 답변",
    createdAt: new Date().toISOString(),
  }];
}

export function buildAgentNotePrompt(
  identity: FolioNoteIdentity,
  currentBody: string,
  userMessage: string,
  linkedTitle: string,
  rawThoughts: NoteEvent[] = [],
  interactionLog: NoteEvent[] = [],
) {
  const thoughtHistory = rawThoughts.slice(-8).map((item, index) => `${index + 1}. ${item.body}`).join("\n");
  const agentHistory = interactionLog.slice(-8).map((item, index) => {
    const { message, note } = splitAgentReply(item.body);
    return `${index + 1}. ${item.summary || "Agent"}: ${message || (note ? "(투자 노트 전체를 업데이트함)" : "")}`;
  }).join("\n\n");
  return [
    "현재 열린 보고서와 Folio Board Market Memory를 함께 참고해, 사용자와 대화하면서 투자 노트를 완성해줘.",
    "사용자가 적은 생각은 근거가 아니라 hypothesis다. 옹호하지 말고 검증 가능한 투자 노트로 다듬어줘.",
    "없는 사실은 지어내지 말고, 추가 확인 필요로 표시해줘.",
    "사용자 판단과 Agent가 제안하는 해석을 구분하고, 반대 근거와 다음 체크포인트를 포함해줘.",
    "사용자가 `>`로 인용한 문장이 있으면 그 문장에 대한 질문/첨삭 요청으로 이해하고 해당 부분을 중심으로 답해줘.",
    "응답 형식을 반드시 지켜줘:",
    `1) ${CHAT_REPLY_MARKER} 아래에 사용자에게 하는 짧은 대화 답변(무엇을 반영/수정했는지, 확인하고 싶은 점)을 2~5문장으로 써줘.`,
    `2) 노트를 새로 만들거나 수정할 내용이 있으면 ${NOTE_BODY_MARKER} 아래에 투자 노트 전체 Markdown을 써줘. 단순 질문에 답만 하는 경우에는 ${NOTE_BODY_MARKER} 부분을 생략하고 기존 노트를 유지해줘.`,
    "기존 정리본이 있으면 전체를 갈아엎기보다 필요한 부분을 업데이트하고, 결정/업데이트 로그에 변경 이유를 남겨줘.",
    "투자 노트는 아래 큰 구조를 유지하되, 각 섹션은 초보 투자자가 바로 이해할 수 있게 짧고 명확하게 작성해줘.",
    INVESTMENT_NOTE_TEMPLATE,
    `노트 제목: ${identity.title}`,
    `연결 문서: ${linkedTitle || identity.linkedReports?.[0] || identity.title}`,
    `보고서 종류: ${identity.reportKind || identity.noteType || "report"}`,
    `보고서 ID: ${identity.reportId || identity.id}`,
    identity.ticker ? `티커: ${identity.ticker}` : "",
    identity.topic ? `주제: ${identity.topic}` : "",
    userMessage.trim() ? `이번 사용자 메시지:\n${userMessage.trim()}` : "",
    thoughtHistory ? `이전 사용자 메시지 기록:\n${thoughtHistory}` : "",
    agentHistory ? `이전 Agent 대화 기록:\n${agentHistory}` : "",
    currentBody.trim() ? `현재 정리된 투자 노트:\n${currentBody.trim()}` : "",
  ].filter(Boolean).join("\n\n");
}

export function stableNoteKey(prefix: string, text: string) {
  const raw = String(text || prefix || "note");
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return `${prefix}-${hash.toString(36)}`;
}

export function FolioNotePanel({
  identity,
  linkedTitle,
  overlay = null,
}: {
  identity: FolioNoteIdentity;
  linkedTitle: string;
  overlay?: PersonalOverlayPayload | null;
}) {
  const [noteBody, setNoteBody] = useState("");
  const [thoughtDraft, setThoughtDraft] = useState("");
  const [quoteDraft, setQuoteDraft] = useState("");
  const [rawThoughts, setRawThoughts] = useState<NoteEvent[]>([]);
  const [interactionLog, setInteractionLog] = useState<NoteEvent[]>([]);
  const [noteStatus, setNoteStatus] = useState("");
  const [noteTab, setNoteTab] = useState<NoteTab>("chat");
  const [linkedNotes, setLinkedNotes] = useState<InvestmentNote[]>([]);
  const [agentBusy, setAgentBusy] = useState(false);
  const [noteTags, setNoteTags] = useState<string[]>([]);
  const [noteExists, setNoteExists] = useState<boolean | null>(null);
  const [intelligenceRefresh, setIntelligenceRefresh] = useState(0);
  const chatListRef = useRef<HTMLOListElement>(null);
  const agentAssisted = noteTags.includes("agent_assisted");

  const chatEvents = useMemo(
    () => [...rawThoughts, ...interactionLog]
      .sort((a, b) => String(a.createdAt || "").localeCompare(String(b.createdAt || ""))),
    [rawThoughts, interactionLog],
  );

  useEffect(() => {
    let alive = true;
    async function loadNote() {
      setNoteStatus("불러오는 중...");
      setLinkedNotes([]);
      setNoteBody("");
      setThoughtDraft("");
      setQuoteDraft("");
      setRawThoughts([]);
      setInteractionLog([]);
      setNoteExists(null);
      try {
        const saved = await getJson<InvestmentNote>(`/api/investment-notes/${encodeURIComponent(identity.id)}`);
        if (!alive) return;
        setNoteBody(saved.body || "");
        setRawThoughts(saved.rawThoughts || []);
        setInteractionLog(saved.interactionLog || []);
        setNoteTags(saved.tags || []);
        setNoteExists(true);
        setNoteStatus(saved.updatedAt ? `저장됨: ${saved.updatedAt}` : "Folio 로컬 노트를 불러왔습니다.");
      } catch {
        if (!alive) return;
        setNoteTags([]);
        setNoteExists(false);
        setNoteStatus("생각 한 줄에서 시작하세요.");
      }
      try {
        const params = new URLSearchParams({
          ticker: identity.ticker || "",
          topic: identity.topic || "",
          reportId: identity.reportId || "",
        });
        const linked = await getJson<LinkedNotesPayload>(`/api/investment-notes/linked?${params}`);
        if (!alive) return;
        setLinkedNotes(linked.notes || []);
      } catch {
        if (!alive) return;
        setLinkedNotes([]);
      }
    }
    loadNote();
    return () => {
      alive = false;
    };
  }, [identity.id, identity.reportId, identity.ticker, identity.topic]);

  useEffect(() => {
    const list = chatListRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [chatEvents.length, noteTab]);

  async function persistNativeNote(nextBody: string, nextRawThoughts: NoteEvent[], nextInteractionLog: NoteEvent[], nextTags = noteTags) {
    const payload: Record<string, unknown> = {
      ...identity,
      body: nextBody,
      rawThoughts: nextRawThoughts,
      interactionLog: nextInteractionLog,
      tags: nextTags,
    };
    const saved = await postJson<InvestmentNote>("/api/investment-notes", payload);
    setNoteTags(saved.tags || []);
    setNoteExists(true);
    setIntelligenceRefresh((value) => value + 1);
    return saved;
  }

  function composeUserMessage() {
    const text = thoughtDraft.trim();
    const quote = quoteDraft.trim();
    if (quote && text) return `> ${quote}\n\n${text}`;
    return quote ? `> ${quote}` : text;
  }

  function captureQuoteSelection() {
    const text = window.getSelection()?.toString().replace(/\s+/g, " ").trim() || "";
    if (text.length >= 2) setQuoteDraft(text.slice(0, 400));
  }

  async function saveThoughtOnly() {
    const message = composeUserMessage();
    if (!message) return;
    setNoteStatus("저장 중...");
    try {
      const nextRawThoughts = appendThought(rawThoughts, message);
      const saved = await persistNativeNote(noteBody, nextRawThoughts, interactionLog);
      setRawThoughts(saved.rawThoughts || nextRawThoughts);
      setInteractionLog(saved.interactionLog || interactionLog);
      setThoughtDraft("");
      setQuoteDraft("");
      setNoteStatus("생각을 기록했습니다. Agent 정리는 나중에 요청할 수 있습니다.");
    } catch (err) {
      setNoteStatus(err instanceof Error ? `저장 실패: ${err.message}` : "저장 실패");
    }
  }

  async function sendToAgent() {
    const message = composeUserMessage();
    if (!message || agentBusy) return;
    setAgentBusy(true);
    setNoteStatus("Agent가 응답을 준비하는 중...");
    const nextRawThoughts = appendThought(rawThoughts, message);
    setRawThoughts(nextRawThoughts);
    setThoughtDraft("");
    setQuoteDraft("");
    try {
      const job = await postJson<AgentJob>("/api/agent/chat", {
        message: buildAgentNotePrompt(identity, noteBody, message, linkedTitle, nextRawThoughts, interactionLog),
        context: {
          surface: "folio_note",
          viewId: "investment_note",
          reportKind: identity.reportKind || identity.noteType || "",
          reportId: identity.reportId || identity.id || "",
          ticker: identity.ticker || "",
          topic: identity.topic || "",
          noteId: identity.id,
        },
        options: { effort: "high" },
      });
      const done = await pollAgentJob(job);
      const result = done.result || {};
      const reply = String(result.reply || "").trim();
      if (!reply) throw new Error(done.message || "Agent가 응답을 반환하지 않았습니다.");
      const { note } = splitAgentReply(reply);
      const nextInteractionLog = appendAgentLog(interactionLog, reply, result.notice || (note ? "투자 노트 업데이트" : "Agent 답변"));
      const nextBody = note || noteBody;
      const nextTags = note ? Array.from(new Set([...noteTags, "agent_assisted"])) : noteTags;
      const saved = await persistNativeNote(nextBody, nextRawThoughts, nextInteractionLog, nextTags);
      setNoteBody(saved.body || nextBody);
      setRawThoughts(saved.rawThoughts || nextRawThoughts);
      setInteractionLog(saved.interactionLog || nextInteractionLog);
      setNoteStatus(note
        ? "Agent가 투자 노트를 업데이트했습니다. 완성본은 연결 자료 탭에서 확인하세요."
        : "Agent가 답변했습니다. 노트 본문은 그대로 유지했습니다.");
    } catch (err) {
      // Agent 실패 시에도 사용자가 적은 생각은 잃지 않도록 기록만 저장한다.
      try {
        await persistNativeNote(noteBody, nextRawThoughts, interactionLog);
      } catch {
        // 저장 실패는 아래 상태 메시지로만 알린다.
      }
      setNoteStatus(err instanceof Error ? `AI 정리 실패: ${err.message}` : "AI 정리 실패");
    } finally {
      setAgentBusy(false);
    }
  }

  function prepareAgentExplanation() {
    setNoteTab("chat");
    setThoughtDraft("현재 freshness, 최신 verdict, 반대 근거, 체크포인트 상태가 무엇을 의미하는지 설명해줘.");
    setNoteStatus("설명 요청을 준비했습니다. 내용을 확인한 뒤 Agent 버튼을 눌러 실행하세요.");
  }

  return (
    <div className="react-note-panel" data-report-note-panel>
      <div className="report-note-head react-note-panel-head">
        <p className="section-kicker">투자 생각 정리</p>
        <div className="report-note-tabs" role="tablist" aria-label="투자 노트 모드">
          {([
            ["chat", "작성"],
            ["links", "연결 자료"],
          ] as Array<[NoteTab, string]>).map(([value, label]) => (
            <button
              className="report-note-tab"
              type="button"
              key={value}
              aria-pressed={noteTab === value}
              onClick={() => setNoteTab(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <HypothesisReviewCard
        identity={identity}
        noteExists={noteExists}
        refreshKey={intelligenceRefresh}
        onRequestAgent={prepareAgentExplanation}
      />
      {noteTab === "chat" && (
        <div className="report-note-chat">
          {chatEvents.length === 0 ? (
            <p className="report-note-empty report-note-chat-empty">
              먼저 떠오르는 생각 한 줄을 남겨보세요. Agent가 열린 보고서와 Market Memory를 참고해 투자 노트로 정리해줍니다.
            </p>
          ) : (
            <ol className="report-note-chat-list" ref={chatListRef} onMouseUp={captureQuoteSelection}>
              {chatEvents.map((event, index) => {
                const isAgent = event.role === "agent";
                const { message, note } = isAgent ? splitAgentReply(event.body) : { message: event.body, note: "" };
                return (
                  <li key={`${event.role}-${event.createdAt || index}-${index}`} className={`report-note-chat-item ${isAgent ? "is-agent" : "is-user"}`}>
                    <span className="report-note-history-meta">
                      {isAgent ? "Agent" : "사용자"} {event.createdAt || ""}
                    </span>
                    {message && <p className="report-note-chat-text">{message}</p>}
                    {note && (
                      <div className="report-note-chat-note">
                        <span className="report-note-chat-note-label">완성된 투자 노트</span>
                        <ReportBody markdown={note} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
          <div className="report-note-composer">
            {quoteDraft && (
              <div className="report-note-quote-bar">
                <span className="report-note-quote-label">인용</span>
                <p>{quoteDraft}</p>
                <button className="btn btn--icon btn--sm" type="button" onClick={() => setQuoteDraft("")} aria-label="인용 지우기">×</button>
              </div>
            )}
            <textarea
              className="report-note-thought-editor"
              value={thoughtDraft}
              onChange={(event) => setThoughtDraft(event.currentTarget.value)}
              rows={3}
              placeholder={THOUGHT_PLACEHOLDER}
              aria-label={`${identity.title} 사용자의 생각`}
            />
            <div className="report-note-composer-actions">
              <button
                className="btn report-note-secondary-action"
                type="button"
                onClick={saveThoughtOnly}
                disabled={agentBusy || !composeUserMessage()}
              >
                생각만 기록
              </button>
              <button
                className="btn btn--primary report-note-primary-action"
                type="button"
                onClick={sendToAgent}
                disabled={agentBusy || !composeUserMessage()}
              >
                {agentBusy ? "Agent가 정리 중" : "Agent와 투자 노트 정리하기"}
              </button>
            </div>
            <p className="report-note-composer-hint">
              Agent 답변이나 완성본에서 문장을 드래그하면 인용해서 이어서 물어볼 수 있습니다.
            </p>
          </div>
        </div>
      )}
      {noteTab === "links" && (
        <div className="report-note-links">
          <div className="report-note-final">
            <div className="report-note-section-label">
              <strong>정리된 투자 노트</strong>
              <span>
                {noteBody.trim()
                  ? `읽기 전용 완성본입니다. 수정은 작성 탭에서 Agent와 대화로 진행하세요.${agentAssisted ? " (Agent 정리본)" : ""}`
                  : "작성 탭에서 Agent와 정리하면 여기에 완성본이 표시됩니다."}
              </span>
            </div>
            {noteBody.trim() ? (
              <div className="report-note-final-body">
                <ReportBody markdown={noteBody} />
              </div>
            ) : (
              <p className="report-note-empty">아직 완성된 투자 노트가 없습니다.</p>
            )}
          </div>
          <p className="report-note-link-head">
            <strong>{linkedTitle || identity.linkedReports?.[0] || identity.title}</strong>에 연결된 Folio 노트와 참고 정보입니다.
          </p>
          {linkedNotes.length > 0 ? (
            <ul className="report-note-link-list">
              {linkedNotes.slice(0, 8).map((note) => (
                <li key={note.id || note.title}>
                  <span className="report-note-link-title">{note.title || "투자 노트"}</span>
                  <span className="report-note-link-meta">{note.ticker || note.noteType || "note"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="report-note-empty">아직 연결된 노트가 없습니다.</p>
          )}
          <div className="report-note-layer">
              <p className="section-kicker">참고 해석</p>
              <PersonalOverlayView overlay={overlay} />
          </div>
        </div>
      )}
      <div className="report-note-foot">
        {noteStatus && <p className="report-note-status">{noteStatus}</p>}
      </div>
    </div>
  );
}
