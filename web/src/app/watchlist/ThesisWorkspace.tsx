import { useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  assistReason,
  approveAssistedReason,
  completeReasonReview,
  getThesisWorkspace,
  saveThesis,
  type ReasonAssistAnswer,
  type ReasonAssistResult,
  type ReasonNewsItem,
  type ThesisWorkspacePayload,
} from "../../api";
import { openScopedThread } from "../agentWorkspace/openScopedThread";
import { compactAmount } from "../charts/chartFormat";
import { verificationDate } from "../verification";
import { checkMetricCondition } from "./conditionMetrics";
import type { FundamentalsQuarter } from "./FundamentalsPanel";

/**
 * 종목 상세의 "내 관심 이유 / 내 투자 이유" 탭 (0.8 선행, 2026-09-29 시안 v2·v4 확정).
 *
 *     내 이유(보라 줄 — 내가 쓴 것) → 관련 새 소식(중립 — 사실) → 기록(접힘)
 *
 * - **보라는 내가 쓴 것에만** 쓴다. 새 소식은 내 생각이 아니므로 보라 줄 바깥에 두고,
 *   "새로 왔다"는 표시만 금색이다.
 * - **판정을 보여 주지 않는다.** 헤드라인 단어 세기로 만든 강화/약화 판정은 일시적 악재와
 *   논리 훼손을 가르지 못한다(2026-09-29 점검). 대신 판단 조건이 실적 지표로 읽히면
 *   "지금 숫자"(사실)를 보여 주고, 결론은 사용자가 "그대로 두기 / 이유 수정하기"로 남긴다.
 * - 확신도·검토 주기·핵심 가정은 편집 화면에서 뺐다. 값은 보내지 않아 부분 갱신으로 보존된다.
 * - 화면 진입은 저장된 projection만 읽는다. Agent를 자동으로 부르지 않는다.
 */

type ConditionResponse = "unanswered" | "unknown" | "skipped" | "written";
type NewsRef = { key: string; title: string; date: string; url: string };
type Draft = { coreThesis: string; falsificationTriggers: string; conditionResponse: ConditionResponse; changeReason: string; attached: NewsRef[] };
type Pick = "ai" | "mine" | null;

function emptyDraft(): Draft {
  return { coreThesis: "", falsificationTriggers: "", conditionResponse: "unanswered", changeReason: "", attached: [] };
}

// Route changes unmount the detail. Keep unsaved words for this browser session.
const draftCache = new Map<string, { draft: Draft; baseRevisionId: string }>();

const NEWS_VISIBLE = 3;

function shortDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || "");
  return match ? `${Number(match[2])}월 ${Number(match[3])}일` : "";
}

/** 판단 기록 문장. 이전 화면에서 남긴 다른 검토 결과를 "그대로 두기"로 바꿔 부르지 않는다. */
function decisionText(outcome: string, seen: number): string {
  if (outcome === "no_material_change") return seen ? `새 소식 ${seen}건을 보고 이유를 그대로 두었습니다.` : "이유를 그대로 두었습니다.";
  const legacy: Record<string, string> = {
    reviewed: "자료를 확인했다고 기록했습니다.", no_new_material: "새 자료를 확보하지 못했다고 기록했습니다.",
    evidence_gap: "자료가 부족하거나 상충한다고 기록했습니다.", collection_failed: "수집·조회가 실패했다고 기록했습니다.",
    unsupported: "지원하지 않는 자료라고 기록했습니다.", deferred: "판단을 보류했다고 기록했습니다.",
  };
  return legacy[outcome] || "검토를 기록했습니다.";
}

function newsRef(item: ReasonNewsItem): NewsRef {
  return { key: item.key, title: item.title, date: item.date, url: item.url };
}

/** 이유 개정의 참조 모양(id·title·url)으로 바꾼다. id가 소식 키라서 다시 새 소식으로 세지 않는다. */
function revisionRefs(refs: NewsRef[]) {
  return refs.map((ref) => ({ id: ref.key.slice(0, 200), title: ref.title, ...(ref.url ? { url: ref.url } : {}) }));
}

function MetricLine({ text, quarters, currency }: { text: string; quarters?: FundamentalsQuarter[]; currency?: string }) {
  const check = checkMetricCondition(text, quarters);
  if (!check) return null;
  const format = (value: number) => check.unit === "percent" ? `${value.toFixed(1)}%` : compactAmount(value, currency || "USD");
  const earlier = check.points.slice(0, -1);
  const latest = check.points[check.points.length - 1];
  const verdict = check.met === null ? "판단할 분기가 부족함" : check.met ? "조건에 해당함" : "조건에 해당하지 않음";
  return (
    <p className="reason-check" data-qa="reason-metric-check">
      <span>최근 {check.points.length}분기 {check.condition.label}</span>
      <span className="reason-check__num">{earlier.map((row) => `${format(row.value)} → `).join("")}</span>
      <b>{format(latest.value)}</b>
      <span>({check.points.map((row) => row.label).join(" → ")})</span>
      <span>· {verdict}</span>
    </p>
  );
}

export function ThesisWorkspace({
  ticker,
  companyName = "",
  quarters,
  currency = "",
  onNewsCountChange,
}: {
  ticker: string;
  companyName?: string;
  quarters?: FundamentalsQuarter[];
  currency?: string;
  onNewsCountChange?: (count: number) => void;
}) {
  const [payload, setPayload] = useState<ThesisWorkspacePayload | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [emptyTried, setEmptyTried] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [baseRevisionId, setBaseRevisionId] = useState("");
  const [draftConflict, setDraftConflict] = useState(false);
  const [conflictLatestReady, setConflictLatestReady] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [assistantError, setAssistantError] = useState("");
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState("");
  const [answerEmpty, setAnswerEmpty] = useState(false);
  const [assistantAnswers, setAssistantAnswers] = useState<ReasonAssistAnswer[]>([]);
  const [assistantPreview, setAssistantPreview] = useState<ReasonAssistResult | null>(null);
  const [reasonPick, setReasonPick] = useState<Pick>(null);
  const [conditionPick, setConditionPick] = useState<Pick>(null);
  const [newsExpanded, setNewsExpanded] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const saveController = useRef<AbortController | null>(null);
  const assistantController = useRef<AbortController | null>(null);
  const decisionController = useRef<AbortController | null>(null);
  // effect 정리보다 먼저 최신 prop을 보관해, ticker 전환 렌더와 effect 사이에
  // 도착한 이전 종목 저장 응답도 새 화면을 덮지 못하게 한다.
  const activeTicker = useRef(ticker);
  activeTicker.current = ticker;

  function resetAssistant() {
    assistantController.current?.abort();
    setAssistantOpen(false);
    setAssistantBusy(false);
    setAssistantError("");
    setAssistantQuestion("");
    setAssistantAnswer("");
    setAnswerEmpty(false);
    setAssistantAnswers([]);
    setAssistantPreview(null);
    setReasonPick(null);
    setConditionPick(null);
  }

  useEffect(() => {
    saveController.current?.abort();
    saveController.current = null;
    decisionController.current?.abort();
    resetAssistant();
    setPayload(null);
    setError("");
    setEditing(draftCache.has(ticker));
    setSaving(false);
    setEmptyTried(false);
    setNewsExpanded(false);
    setDecisionBusy(false);
    setDraft(draftCache.get(ticker)?.draft || emptyDraft());
    setBaseRevisionId(draftCache.get(ticker)?.baseRevisionId || "");
    setDraftConflict(false);
    setConflictLatestReady(false);
    if (!ticker) return;
    const controller = new AbortController();
    getThesisWorkspace(ticker, { signal: controller.signal })
      .then(setPayload)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "관심·투자 이유를 불러오지 못했습니다.");
      });
    return () => { controller.abort(); saveController.current?.abort(); assistantController.current?.abort(); decisionController.current?.abort(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  useEffect(() => {
    if (payload) onNewsCountChange?.(payload.news?.count || 0);
  }, [payload, onNewsCountChange]);

  const thesis = payload?.thesis || null;
  const investment = payload?.reasonKind === "investment";
  const reasonLabel = investment ? "투자 이유" : "관심 이유";
  const reasonQuestion = investment ? "이 종목에 투자한 이유가 무엇인가요?" : "이 종목에 관심이 있는 이유가 무엇인가요?";
  const conditionQuestion = "어떤 일이 확인되면 이 이유가 틀렸다고 판단하시겠어요?";
  const news = payload?.news;

  function updateDraft(next: Draft) {
    setDraft(next);
    draftCache.set(ticker, { draft: next, baseRevisionId });
  }

  function beginEdit(attached: NewsRef[] = []) {
    const current = payload?.thesis;
    const revisionId = payload?.reasonRevision?.revisionId || "";
    setBaseRevisionId(draftCache.get(ticker)?.baseRevisionId ?? revisionId);
    setDraftConflict(false);
    setConflictLatestReady(false);
    setEmptyTried(false);
    resetAssistant();
    const cached = draftCache.get(ticker)?.draft;
    const response = payload?.reasonRevision?.conditionResponse;
    const nextDraft: Draft = cached ? { ...cached, attached: attached.length ? attached : cached.attached } : {
      coreThesis: current?.coreThesis || "",
      falsificationTriggers: (current?.falsificationTriggers || []).join("\n"),
      conditionResponse: response === "unknown" ? "unknown" : "unanswered",
      changeReason: "",
      attached,
    };
    setDraft(nextDraft);
    draftCache.set(ticker, { draft: nextDraft, baseRevisionId: draftCache.get(ticker)?.baseRevisionId ?? revisionId });
    setError("");
    setEditing(true);
  }

  function cancelEdit() {
    draftCache.delete(ticker);
    resetAssistant();
    setEditing(false);
    setEmptyTried(false);
    setError("");
  }

  async function refreshAfterWrite(controller: AbortController) {
    const refreshed = await getThesisWorkspace(ticker, { signal: controller.signal });
    if (controller.signal.aborted || activeTicker.current !== ticker) return false;
    setPayload(refreshed);
    return true;
  }

  async function saveDraft() {
    if (!ticker || saving) return;
    if (!draft.coreThesis.trim()) { setEmptyTried(true); return; }
    const controller = new AbortController();
    saveController.current?.abort();
    saveController.current = controller;
    setSaving(true);
    setError("");
    const conditionText = draft.falsificationTriggers.trim();
    const conditionResponse: ConditionResponse = conditionText ? "written" : draft.conditionResponse;
    const refs = draft.attached.length ? { basisRefs: revisionRefs(draft.attached) } : {};
    const usedAi = Boolean(assistantPreview?.previewToken) && (reasonPick === "ai" || conditionPick === "ai");
    try {
      if (usedAi && assistantPreview) {
        // AI 제안을 하나라도 골랐다면 승인 경로로 저장한다 — 편집 출처가 agent_approved로 남는다.
        await approveAssistedReason(ticker, {
          expectedRevisionId: assistantPreview.revisionId,
          previewToken: assistantPreview.previewToken,
          suggestedReason: assistantPreview.suggestedReason,
          suggestedCondition: assistantPreview.suggestedCondition,
          conditionKeywords: assistantPreview.conditionKeywords || [],
          coreThesis: draft.coreThesis.trim(),
          conditionText,
          conditionResponse,
          changeReason: draft.changeReason,
          ...refs,
        }, { signal: controller.signal });
      } else {
        await saveThesis({
          ticker,
          company: payload?.thesis?.company || companyName,
          coreThesis: draft.coreThesis.trim(),
          falsificationTriggers: conditionText.split("\n").map((value) => value.trim()).filter(Boolean),
          expectedRevisionId: baseRevisionId,
          conditionResponse,
          changeReason: draft.changeReason,
          ...refs,
        }, { signal: controller.signal });
      }
      if (!(await refreshAfterWrite(controller)) || saveController.current !== controller) return;
      setEditing(false);
      setDraftConflict(false);
      resetAssistant();
      draftCache.delete(ticker);
    } catch (err) {
      if (controller.signal.aborted || saveController.current !== controller || activeTicker.current !== ticker) return;
      const conflict = err instanceof ApiRequestError && err.status === 409;
      setError(conflict
        ? "다른 화면에서 이유가 먼저 바뀌었습니다. 입력한 문장은 남아 있습니다. 최신 기록을 확인한 뒤 다시 저장해 주세요."
        : usedAi ? "AI 제안을 넣어 저장하지 못했습니다. 입력한 문장은 그대로 남아 있습니다."
          : err instanceof Error ? err.message : "이유를 저장하지 못했습니다.");
      if (conflict) {
        setDraftConflict(true);
        setConflictLatestReady(false);
        getThesisWorkspace(ticker).then((current) => {
          if (activeTicker.current === ticker) { setPayload(current); setConflictLatestReady(true); }
        }).catch(() => { if (activeTicker.current === ticker) setError("최신 기록을 불러오지 못했습니다. 입력한 문장은 남아 있습니다."); });
      }
    } finally {
      if (saveController.current === controller && activeTicker.current === ticker) {
        saveController.current = null;
        setSaving(false);
      }
    }
  }

  async function runAssistant(phase: "question" | "draft", answers = assistantAnswers) {
    if (!ticker || assistantBusy) return;
    const controller = new AbortController();
    assistantController.current?.abort();
    assistantController.current = controller;
    setAssistantOpen(true);
    setAssistantBusy(true);
    setAssistantError("");
    try {
      const result = await assistReason(ticker, {
        expectedRevisionId: payload?.reasonRevision?.revisionId || "",
        draftReason: draft.coreThesis, draftCondition: draft.falsificationTriggers,
        answers, phase,
      }, { signal: controller.signal });
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      if (result.phase === "question") {
        setAssistantQuestion(result.question || "");
        setAssistantAnswer("");
      } else {
        setAssistantQuestion("");
        setAssistantPreview(result);
        setReasonPick(null);
        setConditionPick(result.suggestedCondition ? null : "mine");
      }
    } catch (err) {
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setAssistantError(err instanceof ApiRequestError && err.status === 409
        ? "이유가 다른 화면에서 바뀌었습니다. 적어 둔 문장은 그대로입니다. 최신 이유를 확인해 주세요."
        : "AI가 응답하지 않았어요. 적어 둔 문장은 그대로이고, 바로 저장할 수 있어요.");
    } finally {
      if (assistantController.current === controller) setAssistantBusy(false);
    }
  }

  function answerAssistant(response: ReasonAssistAnswer["response"]) {
    if (!assistantQuestion) return;
    const next = [...assistantAnswers, { question: assistantQuestion,
      answer: response === "written" ? assistantAnswer.trim() : "", response }];
    setAssistantAnswers(next);
    setAssistantQuestion("");
    setAssistantAnswer("");
    void runAssistant(next.length < 3 ? "question" : "draft", next);
  }

  function pickReason(pick: "ai" | "mine") {
    setReasonPick(pick);
    if (pick === "ai" && assistantPreview?.suggestedReason) updateDraft({ ...draft, coreThesis: assistantPreview.suggestedReason });
  }

  function pickCondition(pick: "ai" | "mine") {
    setConditionPick(pick);
    if (pick === "ai" && assistantPreview?.suggestedCondition) {
      updateDraft({ ...draft, falsificationTriggers: assistantPreview.suggestedCondition, conditionResponse: "written" });
    }
  }

  async function keepReason() {
    if (!ticker || !payload?.reasonRevision || !news?.items.length || decisionBusy) return;
    const controller = new AbortController();
    decisionController.current?.abort();
    decisionController.current = controller;
    setDecisionBusy(true);
    setError("");
    try {
      await completeReasonReview(ticker, {
        expectedRevisionId: payload.reasonRevision.revisionId,
        outcome: "no_material_change",
        checkedScope: [`관련 새 소식 ${news.items.length}건 제목 확인`],
        basisRefs: news.items.map(newsRef),
      }, { signal: controller.signal });
      await refreshAfterWrite(controller);
    } catch (err) {
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setError(err instanceof ApiRequestError && err.status === 409
        ? "그 사이 이유가 바뀌었습니다. 새 이유를 확인한 뒤 다시 골라 주세요."
        : "판단을 기록하지 못했습니다. 잠시 뒤 다시 시도해 주세요.");
    } finally {
      if (decisionController.current === controller) setDecisionBusy(false);
    }
  }

  function debateNews() {
    if (!news?.items.length) return;
    const lines = news.items.slice(0, 5).map((item) => `- ${item.title}${item.date ? ` (${item.date})` : ""}`).join("\n");
    void openScopedThread({
      title: `${ticker} ${reasonLabel} · 새 소식 따져보기`,
      scope: { kind: "watchlist", id: ticker, tickers: [ticker], intent: "challenge", reasonRevisionId: payload?.reasonRevision?.revisionId || "" },
      initialMessage: `내 ${reasonLabel}와 판단 조건에 비추어, 아래 새 소식이 일시적인 일인지 이유 자체를 흔드는 일인지 양쪽 근거로 따져 줘. 확인해야 할 자료도 알려 줘. 결론은 내가 내릴게.\n${lines}`,
      autoSubmit: true,
    }).catch((err) => setError(err instanceof Error ? err.message : "AI 대화를 열지 못했습니다."));
  }

  const conditions = thesis?.falsificationTriggers || [];
  const previousRevisions = (payload?.reasonHistory || []).filter((row) => row.revisionId !== payload?.reasonRevision?.revisionId);
  const decisions = (payload?.reviewEvents || []).filter((event) => event.source === "manual_review");

  const conditionEditor = (
    <div className="reason-q">
      <label className="reason-q__label" htmlFor={`reason-condition-${ticker}`}>{conditionQuestion}</label>
      {draft.conditionResponse === "unknown" && !draft.falsificationTriggers.trim() ? (
        <div className="reason-q__state">
          <span>“아직 모르겠어요”로 남깁니다.</span>
          <button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => updateDraft({ ...draft, conditionResponse: "unanswered" })}>다시 적기</button>
        </div>
      ) : (
        <>
          <textarea
            id={`reason-condition-${ticker}`}
            value={draft.falsificationTriggers}
            onChange={(event) => updateDraft({ ...draft, falsificationTriggers: event.target.value, conditionResponse: event.target.value.trim() ? "written" : "unanswered" })}
            rows={2}
            placeholder="예: 매출은 느는데 남는 돈이 계속 줄어들면"
          />
          <div className="reason-q__below">
            <button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => updateDraft({ ...draft, falsificationTriggers: "", conditionResponse: "unknown" })}>아직 모르겠어요</button>
            <span className="reason-q__hint">비워 두면 나중에 써도 돼요.</span>
          </div>
        </>
      )}
    </div>
  );

  return (
    <section
      className="thesis-workspace reason-workspace"
      data-layer="hypothesis"
      data-qa="thesis-workspace"
      aria-label={`내 ${reasonLabel}`}
    >
      {error && <p className="react-dashboard-error" role="alert">{error}</p>}
      {!payload && !error && <div className="verification-skeleton" aria-label="관심·투자 이유를 불러오는 중"><span className="verification-skeleton__line verification-skeleton__line--title" /><span className="verification-skeleton__line" /><span className="verification-skeleton__line verification-skeleton__line--short" /></div>}

      {payload && (
        <div className="reason-mine">
          <div className="reason-mine__head">
            <h3>내 {reasonLabel}</h3>
            <div className="reason-mine__head-right">
              {/* 사실 영역과 개인 영역의 경계를 화면이 직접 말한다. 보라 = 내가 쓴 것. */}
              <span className="chip" data-tone="purple">내 생각 · 근거 아님</span>
              {payload.hasThesis && !editing && <button className="btn btn--sm" type="button" onClick={() => beginEdit()}>수정하기</button>}
            </div>
          </div>

          {payload.ownership?.syncPaused && (
            <p className="thesis-workspace__warning" data-qa="thesis-sync-paused">
              <span className="chip verification-chip" data-tone="gold"><span aria-hidden="true">!</span> Vault 동기화 멈춤</span>{" "}
              {payload.ownership.message}
            </p>
          )}
          {payload.regimeAlerts.length > 0 && (
            <div className="thesis-workspace__alerts" data-qa="thesis-regime-alert">
              {payload.regimeAlerts.map((alert) => (
                <p className="thesis-workspace__warning" key={alert.stateId}>
                  <span className="chip verification-chip" data-tone="burgundy"><span aria-hidden="true">!</span> 연결 내러티브 경고</span>{" "}
                  <strong>{alert.label}</strong>에 반증 신호가 있습니다
                  {alert.reasons[0]?.detail ? ` — ${alert.reasons[0].detail}` : ""}.
                  <small> 이 경고는 표시일 뿐 이유를 바꾸지 않습니다.</small>
                </p>
              ))}
            </div>
          )}

          {draftConflict && editing && !conflictLatestReady && <p className="reason-note">최신 기록을 불러오는 중입니다.</p>}
          {draftConflict && conflictLatestReady && payload.reasonRevision && editing && (
            <div className="reason-conflict">
              <p>지금 저장된 이유: {payload.thesis?.coreThesis || "이유 없음"}</p>
              <p>지금 저장된 판단 조건: {(payload.thesis?.falsificationTriggers || []).join(" · ") || "입력 없음"}</p>
              {assistantPreview?.previewToken && <p>기존 AI 제안 승인은 이전 기록에 묶여 있습니다. 최신 기록을 확인한 뒤 AI 정리를 다시 실행하거나 현재 초안을 직접 저장할 수 있습니다.</p>}
              <button className="btn btn--sm" type="button" onClick={() => {
                const revisionId = payload.reasonRevision?.revisionId || "";
                setBaseRevisionId(revisionId);
                draftCache.set(ticker, { draft, baseRevisionId: revisionId });
                // 이전 revision으로 서명한 AI 미리보기를 재사용하면 재시도도 계속 409다.
                // 사용자가 골라 둔 문장은 초안에 남기고 승인 토큰만 폐기한다.
                resetAssistant();
                setDraftConflict(false);
                setConflictLatestReady(false);
                setError("");
              }}>최신 기록을 확인하고 이 초안을 다시 저장하기</button>
            </div>
          )}

          {!payload.hasThesis && !editing && (
            <div className="reason-empty">
              <p>이 종목에 {investment ? "투자한" : "관심을 둔"} 이유를 한 줄로 남겨 두면, 관련 소식이 생겼을 때 여기서 함께 보여 드려요.</p>
              {payload.ownership?.vaultNote && (
                <p className="reason-note">Obsidian Vault에 <strong>{payload.ownership.vaultNote.title || payload.ownership.vaultNote.relPath}</strong> 노트가 있습니다. Vault 동기화가 돌면 자동으로 등록됩니다.</p>
              )}
              <button className="btn btn--primary" type="button" onClick={() => beginEdit()}>{reasonLabel} 남기기</button>
            </div>
          )}

          {editing && (
            <form className="reason-form thesis-workspace__editor" onSubmit={(event) => { event.preventDefault(); void saveDraft(); }} noValidate>
              <div className="reason-q">
                {assistantPreview && reasonPick === null ? (
                  <>
                    <span className="reason-q__label">{reasonQuestion}</span>
                    <div className="reason-cmp">
                      <div className="reason-cmp__col"><span className="reason-cmp__who">내 문장</span><p className="reason-cmp__text">{draft.coreThesis || "(비어 있음)"}</p></div>
                      <div className="reason-cmp__col"><span className="reason-cmp__who">AI 제안</span><p className="reason-cmp__text reason-cmp__text--ai">{assistantPreview.suggestedReason}</p>
                        {assistantPreview.reasonBasis && <p className="reason-cmp__basis">본 자료: {assistantPreview.reasonBasis}</p>}</div>
                    </div>
                    <div className="reason-actions"><button className="btn btn--sm" type="button" onClick={() => pickReason("ai")}>이 제안 쓰기</button><button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => pickReason("mine")}>내 문장 유지</button></div>
                  </>
                ) : (
                  <>
                    <label className="reason-q__label" htmlFor={`reason-core-${ticker}`}>{reasonQuestion}</label>
                    <textarea
                      id={`reason-core-${ticker}`}
                      value={draft.coreThesis}
                      onChange={(event) => { setEmptyTried(false); updateDraft({ ...draft, coreThesis: event.target.value }); }}
                      rows={2}
                      placeholder="예: 돈을 잘 벌어서 / 제품을 매일 써서"
                      aria-invalid={emptyTried && !draft.coreThesis.trim() ? true : undefined}
                      aria-describedby={emptyTried && !draft.coreThesis.trim() ? `reason-core-error-${ticker}` : undefined}
                    />
                    {emptyTried && !draft.coreThesis.trim() && <p className="reason-q__error" id={`reason-core-error-${ticker}`}>한 줄만 적어 주세요. 짧아도 괜찮아요.</p>}
                    {reasonPick === "ai" && <p className="reason-q__hint">AI 제안을 넣었어요. 더 고쳐도 됩니다.</p>}
                  </>
                )}
              </div>

              {assistantPreview && conditionPick === null ? (
                <div className="reason-q">
                  <span className="reason-q__label">{conditionQuestion}</span>
                  <div className="reason-cmp">
                    <div className="reason-cmp__col"><span className="reason-cmp__who">내 문장</span><p className="reason-cmp__text">{draft.falsificationTriggers || "(비어 있음)"}</p></div>
                    <div className="reason-cmp__col"><span className="reason-cmp__who">AI 제안</span><p className="reason-cmp__text reason-cmp__text--ai">{assistantPreview.suggestedCondition}</p>
                      {assistantPreview.conditionBasis && <p className="reason-cmp__basis">{assistantPreview.conditionBasis}</p>}</div>
                  </div>
                  <div className="reason-actions"><button className="btn btn--sm" type="button" onClick={() => pickCondition("ai")}>이 제안 쓰기</button><button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => pickCondition("mine")}>{draft.falsificationTriggers.trim() ? "내 문장 유지" : "비워 두기"}</button></div>
                </div>
              ) : conditionEditor}

              {assistantPreview && (assistantPreview.uncertainties || []).length > 0 && (
                <p className="reason-q__hint">AI가 찾은 아직 모르는 점: {(assistantPreview.uncertainties || []).join(" · ")}</p>
              )}

              {assistantOpen && !assistantPreview && (
                <div className="reason-ai" role="region" aria-label="AI 질문">
                  <p className="reason-ai__who">AI 질문{assistantAnswers.length ? ` · ${assistantAnswers.length + 1}번째` : ""}</p>
                  {assistantBusy && <p className="reason-note" role="status">AI가 생각하는 중이에요…</p>}
                  {assistantError && !assistantBusy && (
                    <>
                      <p className="reason-note" role="status">{assistantError}</p>
                      <div className="reason-actions"><button className="btn btn--sm" type="button" onClick={() => void runAssistant(assistantAnswers.length ? "draft" : "question")}>다시 시도</button><button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={resetAssistant}>닫기</button></div>
                    </>
                  )}
                  {assistantQuestion && !assistantBusy && (
                    <>
                      <p className="reason-ai__q">{assistantQuestion}</p>
                      <textarea aria-label="내 답변" value={assistantAnswer} onChange={(event) => { setAnswerEmpty(false); setAssistantAnswer(event.target.value); }} rows={2} placeholder="짧게 답해도 돼요" />
                      {answerEmpty && <p className="reason-q__error">답을 적거나 ‘모르겠어요’를 눌러 주세요.</p>}
                      <div className="reason-actions">
                        <button className="btn btn--sm" type="button" onClick={() => assistantAnswer.trim() ? answerAssistant("written") : setAnswerEmpty(true)}>답하기</button>
                        <button className="btn btn--sm" type="button" onClick={() => answerAssistant("unknown")}>모르겠어요</button>
                        <button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => void runAssistant("draft")}>여기까지 하고 정리</button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {payload.hasThesis && (
                <div className="reason-q reason-change">
                  <label className="reason-q__label reason-q__label--minor" htmlFor={`reason-change-${ticker}`}>무엇 때문에 수정하나요? <span className="reason-q__optional">(선택)</span></label>
                  <input id={`reason-change-${ticker}`} type="text" value={draft.changeReason} onChange={(event) => updateDraft({ ...draft, changeReason: event.target.value })} placeholder="예: 새 소식을 보고 전제를 다시 적음" />
                  {draft.attached.length > 0 && (
                    <div className="reason-attached">
                      <span>함께 기록되는 소식</span>
                      {draft.attached.slice(0, 3).map((ref) => <span className="chip" data-tone="gold" key={ref.key}>{ref.title.length > 28 ? `${ref.title.slice(0, 28)}…` : ref.title}</span>)}
                      {draft.attached.length > 3 && <span>외 {draft.attached.length - 3}건</span>}
                      <button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => updateDraft({ ...draft, attached: [] })}>빼기</button>
                    </div>
                  )}
                </div>
              )}

              <div className="reason-actions reason-actions--form">
                <button className="btn btn--primary" type="submit" disabled={saving}>{saving ? "저장 중…" : "저장"}</button>
                <button className="btn btn--text" type="button" onClick={cancelEdit} disabled={saving}>취소</button>
                <span className="reason-actions__spacer" />
                {!assistantOpen && <button className="btn btn--sm" type="button" onClick={() => void runAssistant("question")}>AI와 함께 다듬기</button>}
              </div>
            </form>
          )}

          {payload.hasThesis && thesis && !editing && (
            <div className="reason-view">
              <div>
                <p className="reason-view__label">{reasonLabel}</p>
                <p className="reason-view__reason">{thesis.coreThesis || "이유 문장이 비어 있습니다."}</p>
              </div>
              <div>
                <p className="reason-view__label">판단을 바꿀 조건</p>
                {conditions.length ? conditions.map((text, index) => (
                  <div key={`${text}-${index}`}>
                    <p className="reason-view__cond">{text}</p>
                    <MetricLine text={text} quarters={quarters} currency={currency} />
                  </div>
                )) : (
                  <p className="reason-view__cond reason-view__cond--empty">
                    {payload.reasonRevision?.conditionResponse === "unknown" ? "아직 모르겠어요" : "아직 적지 않았어요"}
                  </p>
                )}
              </div>
              <p className="reason-note">{payload.reasonRevision ? `저장 ${shortDate(payload.reasonRevision.recordedAt) || verificationDate(payload.reasonRevision.recordedAt)}` : "저장됨"}</p>
              {(previousRevisions.length > 0 || decisions.length > 0) && (
                <details className="reason-log">
                  <summary>기록 — 이전 이유 {previousRevisions.length}건 · 내린 판단 {decisions.length}건</summary>
                  <ol className="reason-log__list">
                    {decisions.map((event) => (
                      <li key={event.eventId}><span className="reason-log__date">{shortDate(event.reviewedAt)}</span> {decisionText(event.outcome, Array.isArray(event.basisRefs) ? event.basisRefs.length : 0)}</li>
                    ))}
                    {previousRevisions.map((revision) => (
                      <li key={revision.revisionId}>
                        <span className="reason-log__date">{shortDate(revision.recordedAt)}</span>{" "}
                        {String(revision.content.core_thesis || "(비어 있음)")}
                        {(revision.content.falsification_triggers as string[] || []).length > 0 && ` · 판단 조건: ${(revision.content.falsification_triggers as string[]).join(" / ")}`}
                        {revision.changeReason ? ` · 수정 이유: ${revision.changeReason}` : ""}
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      {payload?.hasThesis && thesis && !editing && news && (
        <div className="reason-news" data-qa="reason-news">
          <div className="reason-news__head">
            <h4>관련 새 소식</h4>
            {news.count > 0 && <span className="reason-news__count">{news.count}</span>}
            {news.since && <span className="reason-news__since">{shortDate(news.since)} 저장 이후</span>}
          </div>
          {!news.searchReady ? (
            <>
              <p className="reason-news__quiet">
                {conditions.length ? "판단 조건과 대조할 단어가 없어 새 소식을 찾지 않고 있어요." : "판단 조건을 적으면 관련 소식을 찾을 수 있어요."}
              </p>
              {conditions.length > 0 && <p className="reason-note">‘수정하기’에서 AI와 함께 조건을 다듬으면 뉴스 제목과 대조할 단어가 생겨요.</p>}
            </>
          ) : news.count === 0 ? (
            <>
              <p className="reason-news__quiet">
                {news.lastDecisionAt ? `${shortDate(news.lastDecisionAt)}에 이유를 그대로 두었어요. 그 뒤로 연결된 새 소식은 없습니다.` : "이 이유와 연결된 새 소식은 아직 없습니다."}
              </p>
              <p className="reason-note">찾는 단어: {news.keywords.join(", ")}</p>
            </>
          ) : (
            <>
              <ul className="reason-news__list">
                {news.items.slice(0, newsExpanded ? news.items.length : NEWS_VISIBLE).map((item) => (
                  <li key={item.key}>
                    {item.url ? (
                      <a className="reason-news__row" href={item.url} target="_blank" rel="noopener noreferrer">
                        <span className="reason-news__title">{item.title}</span>
                        <span className="reason-news__side">{shortDate(item.date)} <span aria-hidden="true">↗</span><span className="sr-only">원문 열기</span></span>
                      </a>
                    ) : (
                      <div className="reason-news__row reason-news__row--static">
                        <span className="reason-news__title">{item.title}</span>
                        <span className="reason-news__side">{shortDate(item.date)} · 원문 없음</span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              {news.items.length > NEWS_VISIBLE && !newsExpanded && (
                <button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={() => setNewsExpanded(true)}>{news.items.length - NEWS_VISIBLE}건 더 보기</button>
              )}
              <p className="reason-note">제목으로 찾은 소식입니다. 일시적인 일인지, 이유 자체가 흔들리는 일인지는 원문과 다음 실적을 함께 보고 판단하세요.</p>
              <div className="reason-actions">
                <button className="btn btn--sm" type="button" onClick={() => void keepReason()} disabled={decisionBusy}>{decisionBusy ? "기록 중…" : "그대로 두기"}</button>
                <button className="btn btn--sm" type="button" onClick={() => beginEdit(news.items.map(newsRef))}>이유 수정하기</button>
                <span className="reason-actions__spacer" />
                <button className="btn btn--sm btn--text reason-text-btn" type="button" onClick={debateNews}>AI와 따져보기</button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
