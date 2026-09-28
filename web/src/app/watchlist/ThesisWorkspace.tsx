import { useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  assistReason,
  approveAssistedReason,
  completeReasonReview,
  getThesisWorkspace,
  runThesisReview,
  saveThesis,
  type ThesisReviewJob,
  type ThesisReviewResult,
  type ReasonAssistAnswer,
  type ReasonAssistResult,
  type ThesisWorkspacePayload,
  type TrackedCheckpointView,
} from "../../api";
import { pollAgentJobBounded } from "../agentPolling";
import { openScopedThread } from "../agentWorkspace/openScopedThread";
import type { EarningsEvent } from "../watchlistEarnings";
import {
  checkpointDisplay,
  thesisVerdictDisplay,
  transitionLabel,
  verificationDate,
} from "../verification";

/**
 * 종목 Thesis workspace (0.6 Stage C.2 + A.3 + C.3).
 *
 * 계획 C.2의 순서를 그대로 편다:
 *
 *     내 Thesis → 최신 검증 → 근거/반대근거 → 다음 확인 → 검토 이력
 *
 * 위쪽 지표·차트·실적·뉴스는 **사실**이고 여기는 **내 생각**이다. 두 영역을 한 카드에
 * 섞지 않으며, 이 영역은 `data-layer="hypothesis"`와 "근거 아님" 경계를 단다.
 *
 * **판정은 두 층이고 한 배지로 합치지 않는다**(계획 §3.2) — Delta verdict(6값)와
 * 체크포인트 판정(3값)은 각자의 자리에서 각자의 이름으로 보인다.
 *
 * 화면 진입은 저장된 projection만 읽는다. Agent를 자동으로 부르지 않는다.
 */

function CheckpointRow({ checkpoint }: { checkpoint: TrackedCheckpointView }) {
  const display = checkpointDisplay(checkpoint.status);
  const evidence = checkpoint.lastVerdict?.evidence || [];
  return (
    <li className="verification-checkpoint">
      <div className="verification-checkpoint__head">
        <span className="chip verification-chip" data-tone={display.tone}>
          <span aria-hidden="true">{display.icon}</span> {display.label}
        </span>
        <strong>{checkpoint.item}</strong>
      </div>
      <p className="verification-checkpoint__meta">
        {checkpoint.direction === "challenging" ? "반증 신호를 기다리는 항목" : "확인 신호를 기다리는 항목"}
        {checkpoint.lastVerdict?.at ? ` · 마지막 판정 ${verificationDate(checkpoint.lastVerdict.at)}` : ""}
        {checkpoint.dueBy ? ` · 기한 ${checkpoint.dueBy}` : ""}
      </p>
      {evidence.length > 0 && (
        <ul className="verification-evidence">
          {evidence.map((item, index) => (
            <li key={`${item.title}-${index}`}>
              <span className="verification-evidence__date">{verificationDate(item.date)}</span>
              <span className="verification-evidence__title">{item.title}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function EvidenceList({ items, empty }: { items: Array<{ title: string; source: string; date: string; reason: string }>; empty: string }) {
  if (!items.length) return <p className="thesis-workspace__empty">{empty}</p>;
  return (
    <ul className="verification-evidence">
      {items.map((item, index) => (
        <li key={`${item.title}-${index}`}>
          <span className="verification-evidence__date">{verificationDate(item.date)}</span>
          <span className="verification-evidence__title">
            {item.title}
            {item.source ? <small> · {item.source}</small> : null}
            {item.reason ? <small className="verification-evidence__reason">{item.reason}</small> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

function emptyDraft() {
  return { coreThesis: "", keyAssumptions: "", falsificationTriggers: "", reviewCycle: "", conviction: "",
    conditionResponse: "unanswered" as "unanswered" | "unknown" | "skipped" | "written", changeReason: "" };
}

// Route changes unmount the detail. Keep unsaved words for this browser session.
const draftCache = new Map<string, ReturnType<typeof emptyDraft>>();

export function ThesisWorkspace({ ticker, companyName = "", earningsEvent }: { ticker: string; companyName?: string; earningsEvent?: EarningsEvent }) {
  const [payload, setPayload] = useState<ThesisWorkspacePayload | null>(null);
  const [error, setError] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [assistantError, setAssistantError] = useState("");
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState("");
  const [assistantAnswers, setAssistantAnswers] = useState<ReasonAssistAnswer[]>([]);
  const [assistantPreview, setAssistantPreview] = useState<ReasonAssistResult | null>(null);
  const [assistantFinalReason, setAssistantFinalReason] = useState("");
  const [assistantFinalCondition, setAssistantFinalCondition] = useState("");
  const [reviewOutcome, setReviewOutcome] = useState("");
  const [reviewScope, setReviewScope] = useState("");
  const reviewController = useRef<AbortController | null>(null);
  const saveController = useRef<AbortController | null>(null);
  const assistantController = useRef<AbortController | null>(null);
  // effect 정리보다 먼저 최신 prop을 보관해, ticker 전환 렌더와 effect 사이에
  // 도착한 이전 종목 저장 응답도 새 화면을 덮지 못하게 한다.
  const activeTicker = useRef(ticker);
  activeTicker.current = ticker;

  useEffect(() => {
    reviewController.current?.abort();
    assistantController.current?.abort();
    saveController.current?.abort();
    saveController.current = null;
    setPayload(null);
    setError("");
    setEditing(draftCache.has(ticker));
    setSaving(false);
    setReviewBusy(false);
    setAssistantBusy(false);
    setAssistantError("");
    setAssistantQuestion("");
    setAssistantAnswers([]);
    setAssistantPreview(null);
    setReviewOutcome("");
    setReviewScope("");
    setDraft(draftCache.get(ticker) || emptyDraft());
    if (!ticker) return;
    const controller = new AbortController();
    getThesisWorkspace(ticker, { signal: controller.signal })
      .then(setPayload)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "관심·투자 이유를 불러오지 못했습니다.");
      });
    return () => { controller.abort(); reviewController.current?.abort(); saveController.current?.abort(); assistantController.current?.abort(); };
  }, [ticker]);

  const thesis = payload?.thesis || null;
  const delta = payload?.latestDelta || null;
  const verdict = thesisVerdictDisplay(delta?.verdict);
  const checkpoints = payload?.checkpoints;
  const reasonLabel = payload?.reasonKind === "investment" ? "투자 이유" : "관심 이유";

  function updateDraft(next: ReturnType<typeof emptyDraft>) {
    setDraft(next);
    draftCache.set(ticker, next);
  }

  async function runAssistant(phase: "question" | "draft", answers = assistantAnswers) {
    if (!ticker || assistantBusy) return;
    const controller = new AbortController();
    assistantController.current?.abort();
    assistantController.current = controller;
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
        setAssistantFinalReason(result.suggestedReason || "");
        setAssistantFinalCondition(result.suggestedCondition || "");
      }
    } catch (err) {
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setAssistantError(err instanceof ApiRequestError && err.status === 409
        ? "이유가 다른 화면에서 바뀌었습니다. 초안은 남아 있습니다. 최신 이유를 확인해 주세요."
        : "AI 정리를 마치지 못했습니다. 직접 입력과 저장은 계속 사용할 수 있습니다.");
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
    if (next.length < 3) void runAssistant("question", next);
    else void runAssistant("draft", next);
  }

  async function approveAssistant() {
    if (!assistantPreview?.previewToken || assistantBusy) return;
    const controller = new AbortController();
    assistantController.current = controller;
    setAssistantBusy(true);
    setAssistantError("");
    try {
      await approveAssistedReason(ticker, {
        expectedRevisionId: assistantPreview.revisionId,
        previewToken: assistantPreview.previewToken,
        suggestedReason: assistantPreview.suggestedReason,
        suggestedCondition: assistantPreview.suggestedCondition,
        coreThesis: assistantFinalReason,
        conditionText: assistantFinalCondition,
        conditionResponse: draft.conditionResponse,
        changeReason: draft.changeReason,
      }, { signal: controller.signal });
      const refreshed = await getThesisWorkspace(ticker, { signal: controller.signal });
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setPayload(refreshed);
      setEditing(false);
      setAssistantPreview(null);
      draftCache.delete(ticker);
    } catch (err) {
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setAssistantError(err instanceof ApiRequestError && err.status === 409
        ? "현재 이유가 바뀌어 제안을 저장하지 않았습니다. 원문과 최신 기록을 비교해 주세요."
        : "제안을 저장하지 못했습니다. 원문과 직접 저장은 그대로 사용할 수 있습니다.");
    } finally {
      if (assistantController.current === controller) setAssistantBusy(false);
    }
  }

  function beginEdit() {
    const current = payload?.thesis;
    updateDraft(draftCache.get(ticker) || {
      coreThesis: current?.coreThesis || "",
      keyAssumptions: (current?.keyAssumptions || []).join("\n"),
      falsificationTriggers: (current?.falsificationTriggers || []).join("\n"),
      reviewCycle: payload?.reasonRevision?.fieldPresence.review_cycle === true ? current?.reviewCycle || "" : "",
      conviction: payload?.reasonRevision?.fieldPresence.conviction === true ? current?.conviction || "" : "",
      conditionResponse: (payload?.reasonRevision?.conditionResponse === "legacy_unknown" ? "unanswered" : payload?.reasonRevision?.conditionResponse) || "unanswered",
      changeReason: "",
    });
    setError("");
    setEditing(true);
  }

  async function saveDraft() {
    if (!ticker || saving || !draft.coreThesis.trim()) return;
    const controller = new AbortController();
    saveController.current?.abort();
    saveController.current = controller;
    setSaving(true);
    setError("");
    try {
      await saveThesis({
        ticker,
        company: payload?.thesis?.company || companyName,
        coreThesis: draft.coreThesis.trim(),
        keyAssumptions: draft.keyAssumptions.split("\n").map((value) => value.trim()).filter(Boolean),
        falsificationTriggers: draft.falsificationTriggers.split("\n").map((value) => value.trim()).filter(Boolean),
        expectedRevisionId: payload?.reasonRevision?.revisionId || "",
        conditionResponse: draft.falsificationTriggers.trim() ? "written" : draft.conditionResponse,
        changeReason: draft.changeReason,
        ...(draft.reviewCycle ? { reviewCycle: draft.reviewCycle } : {}),
        ...(draft.conviction ? { conviction: draft.conviction } : {}),
      }, { signal: controller.signal });
      const refreshed = await getThesisWorkspace(ticker, { signal: controller.signal });
      if (controller.signal.aborted || saveController.current !== controller || activeTicker.current !== ticker) return;
      setPayload(refreshed);
      setEditing(false);
      draftCache.delete(ticker);
    } catch (err) {
      if (controller.signal.aborted || saveController.current !== controller || activeTicker.current !== ticker) return;
      setError(err instanceof ApiRequestError && err.status === 409
        ? "다른 화면에서 이유가 먼저 바뀌었습니다. 입력한 문장은 남아 있습니다. 최신 기록을 확인한 뒤 다시 저장해 주세요."
        : err instanceof Error ? err.message : "이유를 저장하지 못했습니다.");
      if (err instanceof ApiRequestError && err.status === 409) {
        getThesisWorkspace(ticker).then((current) => { if (activeTicker.current === ticker) setPayload(current); });
      }
    } finally {
      if (saveController.current === controller && activeTicker.current === ticker) {
        saveController.current = null;
        setSaving(false);
      }
    }
  }

  async function reviewLatestEvidence() {
    if (!ticker || reviewBusy) return;
    let controller: AbortController | null = null;
    setReviewBusy(true);
    setError("");
    try {
      // 사용자의 명시적 클릭만 delta write를 시작한다. projection GET은 계속 read-only다.
      controller = new AbortController();
      reviewController.current?.abort();
      reviewController.current = controller;
      const result = await runThesisReview(ticker, { signal: controller.signal });
      if (isReviewJob(result)) await pollAgentJobBounded(result, { signal: controller.signal });
      const refreshed = await getThesisWorkspace(ticker, { signal: controller.signal });
      if (!controller.signal.aborted && activeTicker.current === ticker) setPayload(refreshed);
    } catch (err) {
      if (controller?.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
      if (activeTicker.current === ticker) setError(err instanceof Error ? err.message : "최신 근거 검토를 완료하지 못했습니다.");
    } finally {
      if (reviewController.current?.signal === controller?.signal) reviewController.current = null;
      if (activeTicker.current === ticker) setReviewBusy(false);
    }
  }

  async function completeReview() {
    if (!ticker || !payload?.reasonRevision || !reviewOutcome || reviewBusy) return;
    const controller = new AbortController();
    reviewController.current?.abort();
    reviewController.current = controller;
    setReviewBusy(true);
    setError("");
    try {
      await completeReasonReview(ticker, {
        expectedRevisionId: payload.reasonRevision.revisionId,
        outcome: reviewOutcome,
        checkedScope: reviewScope.split(/[\n,]/).map((text) => text.trim()).filter(Boolean),
      }, { signal: controller.signal });
      const refreshed = await getThesisWorkspace(ticker, { signal: controller.signal });
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setPayload(refreshed);
      setReviewOutcome("");
      setReviewScope("");
    } catch (err) {
      if (controller.signal.aborted || activeTicker.current !== ticker) return;
      setError(err instanceof ApiRequestError && err.status === 409
        ? "검토 중 이유가 바뀌었습니다. 새 이유를 확인한 뒤 다시 검토해 주세요."
        : "검토 종료를 저장하지 못했습니다. 선택과 확인 범위를 다시 살펴봐 주세요.");
    } finally {
      if (reviewController.current === controller) setReviewBusy(false);
    }
  }

  return (
    <section
      className="thesis-workspace"
      data-layer="hypothesis"
      data-qa="thesis-workspace"
      aria-label={`내 ${reasonLabel}와 확인`}
    >
      <div className="watchlist-detail-section__head">
        <h3>내 {reasonLabel}</h3>
        {/* 사실 영역과 개인 영역의 경계를 화면이 직접 말한다. */}
        <span className="chip verification-chip" data-tone="muted">내 생각·가설 · 근거 아님</span>
      </div>

      {error && <p className="react-dashboard-error" role="alert">{error}</p>}
      {!payload && !error && <div className="verification-skeleton" aria-label="관심·투자 이유를 불러오는 중"><span className="verification-skeleton__line verification-skeleton__line--title" /><span className="verification-skeleton__line" /><span className="verification-skeleton__line verification-skeleton__line--short" /></div>}

      {payload && editing && (
        <form className="thesis-workspace__editor" onSubmit={(event) => { event.preventDefault(); void saveDraft(); }}>
          <h4>{payload.hasThesis ? `${reasonLabel} 수정` : `${reasonLabel} 남기기`}</h4>
          <label className="field">{reasonLabel}<textarea required value={draft.coreThesis} onChange={(event) => updateDraft({ ...draft, coreThesis: event.target.value })} rows={3} placeholder="예: 돈을 잘 벌어서" /></label>
          <p className="thesis-workspace__note">어떤 일이 생기면 이 이유를 더는 믿기 어려울까요?</p>
          <label className="field">생각을 바꿀 상황 (선택)<textarea value={draft.falsificationTriggers} onChange={(event) => updateDraft({ ...draft, falsificationTriggers: event.target.value, conditionResponse: event.target.value.trim() ? "written" : "unanswered" })} rows={3} placeholder="예: 고객이 경쟁 제품으로 떠나면" /></label>
          <details><summary>상세 입력 (선택)</summary>
          <p className="thesis-workspace__note">아직 떠오르지 않으면 빈칸으로 저장해도 됩니다.</p>
          <div className="segment" role="group" aria-label="판단 변경 조건 답변">
            {([ ["unanswered", "나중에 답하기"], ["unknown", "아직 모르겠어요"], ["skipped", "건너뛰기"] ] as const).map(([value, label]) => <button key={value} type="button" aria-pressed={draft.conditionResponse === value && !draft.falsificationTriggers.trim()} onClick={() => updateDraft({ ...draft, falsificationTriggers: "", conditionResponse: value })}>{label}</button>)}
          </div>
          <label className="field">핵심 가정 (한 줄에 하나)<textarea value={draft.keyAssumptions} onChange={(event) => updateDraft({ ...draft, keyAssumptions: event.target.value })} rows={3} /></label>
          <div className="thesis-workspace__editor-grid">
            <label className="field">확신도<select value={draft.conviction} onChange={(event) => updateDraft({ ...draft, conviction: event.target.value })}><option value="">입력하지 않음</option><option value="low">낮음</option><option value="medium">보통</option><option value="medium_high">중상</option><option value="high">높음</option></select></label>
            <label className="field">검토 주기<select value={draft.reviewCycle} onChange={(event) => updateDraft({ ...draft, reviewCycle: event.target.value })}><option value="">입력하지 않음</option><option value="weekly">매주</option><option value="monthly">매월</option><option value="quarterly">분기별</option><option value="event_driven">이벤트 발생 시</option></select></label>
          </div>
          <label className="field">수정 이유 (선택)<input value={draft.changeReason} onChange={(event) => updateDraft({ ...draft, changeReason: event.target.value })} /></label>
          </details>
          <div className="thesis-workspace__editor-actions"><button className="btn btn--primary" type="submit" disabled={saving || !draft.coreThesis.trim()}>{saving ? "저장 중…" : `${reasonLabel} 저장`}</button><button className="btn" type="button" onClick={() => setEditing(false)} disabled={saving}>닫기</button></div>
          <details className="thesis-workspace__assistant"><summary>AI와 함께 정리하기 (선택)</summary>
            <div className="surface surface--inset">
              <p>AI 제안은 저장 전까지 초안입니다. 한 번에 한 질문씩 답하거나 언제든 건너뛸 수 있습니다.</p>
              {assistantError && <p role="alert">{assistantError}</p>}
              {!assistantQuestion && !assistantPreview && <button className="btn" type="button" disabled={assistantBusy} onClick={() => void runAssistant("question")}>{assistantBusy ? "질문 준비 중…" : "질문 받기"}</button>}
              {assistantQuestion && <div>
                <p><strong>{assistantQuestion}</strong></p>
                <label className="field">내 답변<textarea value={assistantAnswer} onChange={(event) => setAssistantAnswer(event.target.value)} rows={2} /></label>
                <div className="thesis-workspace__editor-actions">
                  <button className="btn" type="button" disabled={assistantBusy || !assistantAnswer.trim()} onClick={() => answerAssistant("written")}>답하고 계속</button>
                  <button className="btn" type="button" disabled={assistantBusy} onClick={() => answerAssistant("unknown")}>모르겠어요</button>
                  <button className="btn" type="button" disabled={assistantBusy} onClick={() => answerAssistant("skipped")}>건너뛰기</button>
                  <button className="btn" type="button" disabled={assistantBusy} onClick={() => void runAssistant("draft")}>질문 마치고 초안 보기</button>
                </div>
              </div>}
              {assistantPreview && <div>
                <h5>원문과 AI 제안 비교</h5>
                <p>원문: <del>{assistantPreview.originalReason || "(비어 있음)"}</del></p>
                <p>제안: <ins>{assistantPreview.suggestedReason}</ins></p>
                <p>조건 원문: {assistantPreview.originalCondition || "(비어 있음)"} · 제안: {assistantPreview.suggestedCondition || "(비어 있음)"}</p>
                {(assistantPreview.uncertainties || []).length > 0 && <p>아직 모르는 점: {assistantPreview.uncertainties?.join(" · ")}</p>}
                <label className="field">저장할 내 문장<textarea value={assistantFinalReason} onChange={(event) => setAssistantFinalReason(event.target.value)} rows={3} /></label>
                <label className="field">저장할 판단 변경 조건<textarea value={assistantFinalCondition} onChange={(event) => setAssistantFinalCondition(event.target.value)} rows={2} /></label>
                <button className="btn btn--primary" type="button" disabled={assistantBusy || !assistantFinalReason.trim()} onClick={() => void approveAssistant()}>{assistantBusy ? "저장 중…" : "확인하고 저장"}</button>
              </div>}
            </div>
          </details>
        </form>
      )}

      {payload && !payload.hasThesis && !editing && (
        <div className="thesis-workspace__intro">
          <p className="thesis-workspace__empty">
            이 종목에 남긴 {reasonLabel}가 없습니다. 한 줄만 적어도 됩니다. 작성하지 않아도 기업 자료를 볼 수 있습니다.
          </p>
          {payload.ownership?.vaultNote ? (
            <p className="thesis-workspace__note">
              Obsidian Vault에 <strong>{payload.ownership.vaultNote.title || payload.ownership.vaultNote.relPath}</strong>{" "}
              노트가 있습니다. Vault 동기화가 돌면 자동으로 등록됩니다.
            </p>
          ) : (
            <p className="thesis-workspace__note">
              기업 분석 보고서의 <strong>투자 생각 정리</strong>에서 노트를 쓰면 같은 이유 기록으로 연결됩니다.
            </p>
          )}
          <button className="btn btn--primary" type="button" onClick={beginEdit}>{reasonLabel} 남기기</button>
        </div>
      )}

      {payload && payload.hasThesis && thesis && (
        <>
          {/* 소유권 — 동기화가 멈춘 사실이 조용하면 사용자는 낡은 이유를 찾을 수 없다. */}
          {payload.ownership?.syncPaused && (
            <p className="thesis-workspace__warning" data-qa="thesis-sync-paused">
              <span className="chip verification-chip" data-tone="gold">
                <span aria-hidden="true">!</span> Vault 동기화 멈춤
              </span>{" "}
              {payload.ownership.message}
            </p>
          )}

          {/* A.3 — 연결한 내러티브의 반증 신호를 여기로 전한다. 표시일 뿐 verdict를 바꾸지 않는다. */}
          {payload.regimeAlerts.length > 0 && (
            <div className="thesis-workspace__alerts" data-qa="thesis-regime-alert">
              {payload.regimeAlerts.map((alert) => (
                <p className="thesis-workspace__warning" key={alert.stateId}>
                  <span className="chip verification-chip" data-tone="burgundy">
                    <span aria-hidden="true">!</span> 연결 내러티브 경고
                  </span>{" "}
                  <strong>{alert.label}</strong>에 반증 신호가 있습니다
                  {alert.reasons[0]?.detail ? ` — ${alert.reasons[0].detail}` : ""}.
                  <small> 이 경고는 표시일 뿐 이유나 종합 판정을 바꾸지 않습니다.</small>
                </p>
              ))}
            </div>
          )}

          <div className="thesis-workspace__block">
            <h4>{reasonLabel}</h4>
            <p className="thesis-workspace__core">{thesis.coreThesis || "핵심 논지가 비어 있습니다."}</p>
            <p className="thesis-workspace__meta">{payload.reasonRevision ? `저장됨 · ${verificationDate(payload.reasonRevision.recordedAt)}` : "저장됨"}</p>
            {thesis.falsificationTriggers.length > 0 && (
              <>
                <h5>생각을 바꿀 상황</h5>
                <ul className="thesis-workspace__list">
                  {thesis.falsificationTriggers.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
                </ul>
              </>
            )}
            {payload.reasonRevision?.conditionResponse === "unknown" && <p className="thesis-workspace__note">판단을 바꿀 상황: 아직 모르겠어요</p>}
            {payload.reasonRevision?.conditionResponse === "skipped" && <p className="thesis-workspace__note">판단을 바꿀 상황: 이번에는 건너뜀</p>}
            <button className="btn" type="button" onClick={beginEdit}>{reasonLabel} 수정</button>
          </div>

          <details className="thesis-workspace__more" data-qa="reason-review-details">
            <summary>자료·검토·이전 기록 보기 (선택)</summary>
            <div className="thesis-workspace__more-content">
              <p className="thesis-workspace__meta">이유 상태: {reasonStatusLabel(payload.reasonStatus)}{payload.reasonRevision ? ` · 개정 ${payload.reasonRevision.revision}` : ""}</p>
              {(payload.reasonRevision?.fieldPresence.conviction === true || payload.reasonRevision?.fieldPresence.review_cycle === true) && <p className="thesis-workspace__meta">
                {payload.reasonRevision?.fieldPresence.conviction === true ? `확신도 ${displayConviction(thesis.conviction)}` : ""}
                {payload.reasonRevision?.fieldPresence.conviction === true && payload.reasonRevision?.fieldPresence.review_cycle === true ? " · " : ""}
                {payload.reasonRevision?.fieldPresence.review_cycle === true ? `검토 주기 ${displayReviewCycle(thesis.reviewCycle)}` : ""}
              </p>}
          <div className="thesis-workspace__block" data-qa="reason-connections">
            <h4>이 이유와 함께 볼 변화</h4>
            <p className="thesis-workspace__note">연결된 자료는 판단을 대신하지 않습니다. 관계를 확인하지 못한 변화는 따로 표시합니다.</p>
            {payload.reasonConnections.length ? <ul className="thesis-workspace__list">
              {payload.reasonConnections.map((item) => <li key={`${item.kind}:${item.identity}`}>
                <strong>{item.kind === "checkpoint" ? "확인 항목" : item.kind === "delta" ? "종합 검토" : "연결 자료"}</strong> · {item.label}
                {item.at ? ` · ${verificationDate(item.at)}` : ""} · {item.source}
                {item.kind === "checkpoint" && <small> · {item.status === "no_signal" ? "신호 없음" : item.status === "confirmed" ? "확인됨" : item.status === "challenged" ? "반증" : item.status === "expired" ? "기한 경과" : "상태 미확인"}</small>}
                {item.kind === "delta" && item.status && <small> · {thesisVerdictDisplay(item.status).label}</small>}
                <small> · {item.relationship === "exact_condition" || item.relationship === "exact_revision" || item.relationship === "user_linked" ? `이유 개정 ${payload.reasonRevision?.revision}에 연결` : "이 이유에 미치는 영향 미확인"}</small>
                {item.gap && <small> · {item.gap}</small>}
                {item.url && <a href={item.url} target="_blank" rel="noopener noreferrer"> 원문 열기</a>}
              </li>)}
            </ul> : <p className="thesis-workspace__empty">아직 이 이유에 연결된 변화가 없습니다. 새 자료를 확인하지 않았다는 뜻과는 다릅니다.</p>}
            {earningsEvent?.startsAt && <p className="thesis-workspace__note">다음 실적 예정 {verificationDate(earningsEvent.startsAt)} · 이 이유에 미치는 영향은 아직 확인하지 못했습니다. <button className="btn btn--text" type="button" onClick={() => document.getElementById("watchlist-earnings")?.scrollIntoView({ block: "start", behavior: "smooth" })}>실적 보기</button></p>}
            {!earningsEvent?.startsAt && <p className="thesis-workspace__note">실적 일정은 아래 실적 패널에서 확인하세요. 이 이유와의 관계는 자동 판정하지 않습니다.</p>}
          </div>

          <div className="thesis-workspace__block">
            <h4>이번 검토 마치기</h4>
            <p className="thesis-workspace__note">읽기만 하거나 화면을 닫아도 검토 완료로 기록되지 않습니다. 실제로 확인한 범위만 남겨 주세요.</p>
            <label className="field">확인 결과<select value={reviewOutcome} onChange={(event) => setReviewOutcome(event.target.value)}>
              <option value="">선택해 주세요</option><option value="no_material_change">확인한 범위에서 중요한 변화 없음</option>
              <option value="no_new_material">새 자료를 확보하지 못함</option><option value="evidence_gap">자료가 부족하거나 상충함</option>
              <option value="collection_failed">수집 또는 조회 실패</option><option value="unsupported">이 자료는 현재 지원하지 않음</option>
              <option value="deferred">판단을 보류하고 마침</option><option value="reviewed">자료를 확인함</option>
            </select></label>
            <label className="field">실제로 확인한 자료·범위<input value={reviewScope} onChange={(event) => setReviewScope(event.target.value)} placeholder="예: 최근 실적 발표, 저장된 Delta" /></label>
            <button className="btn" type="button" disabled={reviewBusy || !reviewOutcome || !reviewScope.trim()} onClick={() => void completeReview()}>{reviewBusy ? "기록 중…" : "이번 검토 마치기"}</button>
            {payload.reviewEvents.filter((event) => event.source === "manual_review" || event.source === "explicit_delta").slice(0, 1).map((event) => <p key={event.eventId} className="thesis-workspace__meta">최근 검토 {verificationDate(event.reviewedAt)} · {reviewOutcomeLabel(event.outcome)} · 범위 {event.checkedScope.join(", ") || "기록 없음"}</p>)}
          </div>

          <details className="thesis-workspace__block">
            <summary>이전 이유와 조건 보기 ({Math.max(0, payload.reasonHistory.length - 1)}건)</summary>
            <ol className="verification-timeline__list">
              {payload.reasonHistory.map((revision) => <li key={revision.revisionId}>
                <span className="verification-timeline__date">개정 {revision.revision} · 앱 기록 {verificationDate(revision.recordedAt)}</span>
                <span className="verification-timeline__body">{String(revision.content.core_thesis || "(비어 있음)")}
                  {(revision.content.falsification_triggers as string[] || []).length > 0 && ` · 조건: ${(revision.content.falsification_triggers as string[]).join(" / ")}`}
                  {revision.changeReason ? ` · 수정 이유: ${revision.changeReason}` : " · 수정 이유 미입력"}
                  {revision.userStatedAt ? ` · 사용자 진술 시각: ${revision.userStatedAt}` : ""}
                  {revision.basisRefs.length ? ` · 자료 참조 ${revision.basisRefs.map((ref) => `${ref.id || ref.title || "자료"}@${ref.revision || "시점 미상"}`).join(", ")}` : ""}
                </span>
              </li>)}
            </ol>
          </details>

          <div className="thesis-workspace__block">
            <h4>최신 검증</h4>
            {delta ? (
              <>
                <p className="thesis-workspace__verdict">
                  {/* 6값 enum. 아래 확인 항목의 3값 판정과 다른 층이다. */}
                  <span className="chip verification-chip" data-tone={verdict.tone}>
                    <span aria-hidden="true">{verdict.icon}</span> {verdict.label}
                  </span>
                  <span className="thesis-workspace__meta">
                    이유 종합 판정 · {verificationDate(delta.generatedAt)}
                    {delta.period ? ` · ${displayPeriod(delta.period)} 창` : ""}
                  </span>
                </p>
                {delta.summary && <p className="thesis-workspace__core">{delta.summary}</p>}
              </>
            ) : (
              <p className="thesis-workspace__empty">
                아직 종합 검증이 없습니다. 아래의 <strong>최신 근거로 검토</strong>를 실행하면 만들어집니다.
              </p>
            )}
          </div>

          <div className="thesis-workspace__block">
            <h4>근거와 반대 근거</h4>
            <h5>강화 근거</h5>
            <EvidenceList items={delta?.supportingEvidence || []} empty="확인된 강화 근거가 없습니다." />
            <h5>반대 근거</h5>
            <EvidenceList items={delta?.counterEvidence || []} empty="기록된 반대 근거가 없습니다." />
            {delta?.uncertainties?.length ? (
              <>
                <h5>불확실성</h5>
                <ul className="thesis-workspace__list">
                  {delta.uncertainties.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
                </ul>
              </>
            ) : null}
            {delta?.contradictions?.length ? (
              <>
                <h5>모순·반증 관찰</h5>
                <ul className="thesis-workspace__list">
                  {delta.contradictions.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
                </ul>
              </>
            ) : null}
          </div>

          <div className="thesis-workspace__block">
            <h4>다음 확인</h4>
            {checkpoints && checkpoints.structured.length > 0 ? (
              <ul className="verification-checkpoint-list">
                {checkpoints.structured.map((checkpoint) => (
                  <CheckpointRow key={checkpoint.id} checkpoint={checkpoint} />
                ))}
              </ul>
            ) : (
              <p className="thesis-workspace__empty">기계가 대조할 확인 항목이 아직 없습니다.</p>
            )}
            {checkpoints && checkpoints.unverifiableCount > 0 && (
              <p className="thesis-workspace__note" data-qa="thesis-unverifiable">
                <span className="chip verification-chip" data-tone="gold">
                  <span aria-hidden="true">?</span> 검증 불가
                </span>{" "}
                {checkpoints.unverifiableCount}건은 저장된 형식이 지금 규칙과 맞지 않아 판정에서 빠집니다.
              </p>
            )}
            {checkpoints && checkpoints.templates.length > 0 && (
              <ul className="thesis-workspace__list">
                {checkpoints.templates.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
              </ul>
            )}
          </div>

          <div className="thesis-workspace__block thesis-workspace__actions">
            <h4>{reasonLabel} 작업</h4>
            <button className="btn" type="button" onClick={() => void reviewLatestEvidence()} disabled={reviewBusy}>
              {reviewBusy ? "최신 근거를 검토하는 중…" : "최신 근거로 검토"}
            </button>
            <button
              className="btn"
              type="button"
              onClick={() => openScopedThread({
                title: `${ticker} ${reasonLabel} 반박 대화`,
            scope: { kind: "watchlist", id: ticker, tickers: [ticker], intent: "challenge", reasonRevisionId: payload.reasonRevision?.revisionId || "" },
                initialMessage: `이 ${reasonLabel}를 반박해줘`,
                autoSubmit: true,
              })}
            >
              이 {reasonLabel}를 반박해줘
            </button>
          </div>

          <div className="thesis-workspace__block">
            <h4>검토 이력</h4>
            {payload.deltaHistory.length || checkpoints?.structured.some((item) => item.history?.length) ? (
              <ol className="verification-timeline__list">
                {[...payload.deltaHistory.map((row) => ({ kind: "delta" as const, at: row.generatedAt, row })),
                  ...(checkpoints?.structured || []).flatMap((checkpoint) => (checkpoint.history || []).map((row, index) => ({ kind: "checkpoint" as const, at: row.at, row, checkpoint, index })))
                ].sort((a, b) => timelineTimestamp(b.at) - timelineTimestamp(a.at)).map((entry) => {
                  if (entry.kind === "delta") {
                    const row = entry.row;
                  const display = thesisVerdictDisplay(row.verdict);
                  return (
                    <li key={row.deltaId}>
                      <span className="verification-timeline__date">{verificationDate(row.generatedAt)}</span>
                      <span className="verification-timeline__body">
                        <strong>종합 판정</strong> {display.label}
                        {row.summary ? ` · ${row.summary}` : ""}
                      </span>
                    </li>
                  );
                  }
                  const { checkpoint, row, index } = entry;
                  return <li key={`${checkpoint.id}-${index}`}>
                      <span className="verification-timeline__date">{verificationDate(row.at)}</span>
                      <span className="verification-timeline__body">
                        <strong>확인 항목</strong> {checkpoint.item} ·{" "}
                        {transitionLabel("checkpoint", row.from)} → {transitionLabel("checkpoint", row.to)}
                      </span>
                    </li>;
                })}
              </ol>
            ) : (
              <p className="thesis-workspace__empty">아직 기록된 검토 이력이 없습니다.</p>
            )}
          </div>
            </div>
          </details>
        </>
      )}
    </section>
  );
}

function isReviewJob(result: ThesisReviewResult): result is ThesisReviewJob {
  return "id" in result && "status" in result;
}

function displayConviction(value: string) {
  return ({ low: "낮음", medium: "보통", medium_high: "중상", high: "높음" } as Record<string, string>)[value] || "판단 보류";
}
function reasonStatusLabel(value: string) {
  return ({ unwritten: "미작성", unreviewed: "작성 후 미검토", reviewed: "이번 이유를 검토함", evidence_gap: "검토했으나 근거 공백 있음" } as Record<string, string>)[value] || "상태 확인 필요";
}
function reviewOutcomeLabel(value: string) {
  return ({ reviewed: "자료 확인", no_material_change: "확인 범위에 중요한 변화 없음", no_new_material: "새 자료 미확보", evidence_gap: "근거 부족·상충", collection_failed: "수집·조회 실패", unsupported: "자료 미지원", deferred: "판단 보류" } as Record<string, string>)[value] || "검토 기록";
}
function displayReviewCycle(value: string) {
  return ({ weekly: "매주", monthly: "매월", quarterly: "분기별", event_driven: "이벤트 발생 시" } as Record<string, string>)[value] || "정기 검토 없음";
}
function displayPeriod(value: string) {
  return ({ "30d": "최근 30일", "90d": "최근 90일", since_last_review: "지난 검토 이후", since_last_note: "지난 노트 이후", last_earnings: "지난 실적 이후" } as Record<string, string>)[value] || "기록된 기간";
}
function timelineTimestamp(value: string) {
  const timestamp = Date.parse(value || "");
  // malformed date는 time axis의 끝에, 같은 종류끼리는 안정적인 입력 순서로 둔다.
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY;
}
