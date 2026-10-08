import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson } from "../../api";
import { errorCopy, timeLabel } from "./copy";
import { OwnershipForm } from "./OwnershipForm";
import { OwnershipComparison, IssueSummary, ReviewSummary } from "./OwnershipComparison";
import { newReview, ownershipLink, portfolioReturn, type OwnershipView, type ReviewEntry, type ReviewFields, type SavedReview } from "./ownershipTypes";
import { PreservedInput } from "./PreservedInput";
import { slots, slotLabels, type Operation, type Preview, type Slot } from "./types";

const params = () => new URLSearchParams(window.location.hash.split("?")[1] || "");
export function OwnershipReview({ instrumentId, active, onReason }: { instrumentId: string; active: boolean; onReason: () => void }) {
  const [view, setView] = useState<OwnershipView | null>(null);
  const [journalId, setJournalId] = useState(() => params().get("journal") || "");
  const [original, setOriginal] = useState(() => params().get("original") || "");
  const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false); const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<ReviewFields | null>(null); const [kind, setKind] = useState("ownership_review");
  const [uncertainty, setUncertainty] = useState(""); const [excluded, setExcluded] = useState<Slot[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const epoch = useRef(0); const operationId = useRef(""); const alive = useRef(true);
  const heading = useRef<HTMLHeadingElement>(null); const previewHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++epoch.current; }; }, []);
  useEffect(() => { const changed = () => { if (params().get("tab") !== "ownership") return; setJournalId(params().get("journal") || ""); setOriginal(params().get("original") || ""); }; window.addEventListener("hashchange", changed); return () => window.removeEventListener("hashchange", changed); }, []);
  useEffect(() => { setDraft(null); setPreview(null); }, [journalId, original]);
  const refresh = useCallback(async () => {
    const id = ++epoch.current; setLoading(true); setError("");
    const route = journalId ? `/api/decision-journals/${encodeURIComponent(journalId)}/ownership-review` : `/api/investment-cases/${encodeURIComponent(instrumentId)}/ownership-review${original ? `?originalJournalId=${encodeURIComponent(original)}` : ""}`;
    try { const result = await getJson<OwnershipView>(route); if (id === epoch.current) { if (result.instrumentId !== instrumentId) { setView(null); setError("다른 종목의 기록입니다. 현재 종목의 점검 기록을 선택해 주세요."); } else setView(result); } }
    catch (reason) { if (id === epoch.current) { setView(null); setError(errorCopy(reason)); } }
    finally { if (id === epoch.current) setLoading(false); }
  }, [instrumentId, journalId, original]);
  useEffect(() => { if (active) void refresh(); else { ++epoch.current; setLoading(false); } }, [active, refresh]);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);
  const resetPreview = () => { setPreview(null); operationId.current = ""; };
  function begin(nextKind = "ownership_review", previous?: ReviewEntry) {
    setKind(nextKind); setDraft(newReview(view?.original.id || null, previous)); setUncertainty(""); setExcluded([]); resetPreview(); setError(""); setNotice("");
  }
  async function propose(create = false) {
    if (!view || busy || (!create && !draft)) return;
    if (draft && !create) {
      if (draft.completed && !draft.checkedScope.length) { setError("검토 완료를 표시하려면 이번에 확인한 범위를 선택해 주세요."); return; }
      if (draft.resolution === "resolved" && (["defer", "exception", "undecided"].includes(draft.conclusion) || ["unknown", "missing", "conflicting", "stale"].includes(draft.evidence))) { setError("현재 판단과 근거 수준에서는 미해결로 남겨 주세요. 해소 표시와 검토 완료는 별개입니다."); return; }
    }
    setBusy(true); setError(""); resetPreview();
    try {
      const next = await postJson<Preview>("/api/investment-cases/preview", { instrumentId, expectedCaseRevision: view.caseRevision, action: create ? "create" : "journal", ...(create ? {} : { kind, ownershipReview: draft, uncertainties: uncertainty, excludedSlots: excluded }) });
      if (alive.current) { setPreview(next); operationId.current = crypto.randomUUID().replace(/-/g, ""); }
    } catch (reason) { if (alive.current) setError(errorCopy(reason)); }
    finally { if (alive.current) setBusy(false); }
  }
  async function confirm() {
    if (!preview?.token || busy) return;
    const origin = window.location.hash; setBusy(true); setError("");
    try {
      const result = await postJson<Operation>("/api/investment-cases/confirm", { token: preview.token, operationId: operationId.current });
      if (!alive.current) return;
      setDraft(null); resetPreview(); setNotice("확인한 점검 내용을 저장했습니다.");
      if (window.location.hash === origin && result.journalId) {
        const query = params(); query.set("tab", "ownership"); query.set("journal", result.journalId); window.location.hash = `${origin.split("?")[0]}?${query}`;
      } else await refresh();
    } catch (reason) { if (alive.current) setError(errorCopy(reason)); }
    finally { if (alive.current) setBusy(false); }
  }
  function currentView() { const query = params(); query.delete("journal"); window.location.hash = `${window.location.hash.split("?")[0]}?${query}`; }
  function selectOriginal(value: string) { const query = params(); if (value) query.set("original", value); else query.delete("original"); window.location.hash = `${window.location.hash.split("?")[0]}?${query}`; }
  const returnTo = portfolioReturn();
  const link = (id: string) => ownershipLink(instrumentId.split(":")[1], instrumentId, id, returnTo || undefined);
  const review = view?.review;
  const thisEntry = view?.timeline.find(row => row.id === journalId);
  const previewReview = (preview?.journal as (Preview["journal"] & { ownershipReview?: SavedReview }) | undefined)?.ownershipReview;
  return <section className="case-workspace ownership-workspace" data-ownership-review data-layer="hypothesis" aria-labelledby="ownership-heading" aria-busy={busy || loading}>
    <header className="case-head"><div><p className="section-kicker">OWNERSHIP REVIEW</p><h3 id="ownership-heading" ref={heading} tabIndex={-1}>{journalId ? "당시 보유 점검·복기" : "보유 점검"}</h3></div><span className="chip" data-tone="purple">내 판단 · 근거 아님</span></header>
    <p>당시 이유와 새 사실을 대조하고, 아직 모르는 것과 다음 확인을 남깁니다.</p>
    <div className="case-actions">{returnTo && <a className="btn btn--text" href={returnTo}>투자 리뷰로 돌아가기</a>}<button className="btn btn--text" disabled={busy} onClick={() => { resetPreview(); void refresh(); }}>점검 자료 다시 읽기</button><button className="btn btn--text" onClick={onReason}>현재 투자 이유 열기</button><a className="btn btn--text" href={`${window.location.hash.split("?")[0]}?${new URLSearchParams({ ...Object.fromEntries(params()), tab: "records" })}`}>기록·미완료 작업 열기</a>{journalId && <button className="btn btn--text" onClick={currentView}>현재 보유 점검으로</button>}</div>
    {error && <p role="alert" className="react-dashboard-error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {loading && <p role="status">당시 입력과 검토 이력을 읽는 중입니다.</p>}
    {view && <>
      <p>{view.notice}</p>
      {view.mode === "current" && <label className="field">비교할 당시 기록<select value={original} onChange={event => selectOriginal(event.target.value)}><option value="">현재 검토의 최초 기록</option>{view.originalOptions.map(row => <option key={row.id} value={row.id}>{timeLabel(row.recordedAt)}{row.status !== "available" ? " · 본문 확인 필요" : ""}</option>)}</select></label>}
      {view.mode === "historical" && <p>이 기록의 확인 시각: {timeLabel(view.current.recordedAt)} · 지금의 자료로 바꾸지 않았습니다.</p>}
      <OwnershipComparison view={view} />
      <section className="case-section"><h4>내 검토·미해결 항목</h4>
        {review && <ReviewSummary review={review} uncertainties={thisEntry?.uncertainties} conditionText={thisEntry?.conditionView.text} />}
        {!journalId && (view.issues.length ? <ol className="case-history">{view.issues.map(entry => <li key={entry.review.rootReviewJournalId}><IssueSummary entry={entry} /><div className="case-actions"><a className="btn btn--text" href={link(entry.id)}>이 점검의 당시 입력 열기</a>{entry.status === "available" && !entry.review.purgedAt && <button className="btn" disabled={busy} onClick={() => begin("ownership_review", entry)}>이 점검 이어가기</button>}</div></li>)}</ol> : <p>아직 개인 검토를 남기지 않았습니다. 조건을 쓰지 않았어도 새 변화를 검토할 수 있습니다.</p>)}
        {!journalId && !draft && <button className="btn btn--primary" disabled={busy} onClick={() => view.caseRevision === 0 ? void propose(true) : begin()}>{view.caseRevision === 0 ? "검토 기록 시작" : "내 검토 남기기"}</button>}
        {view.timeline.length > 0 && <details className="ownership-details"><summary>검토·수정·보류 순서</summary><ol className="case-history">{view.timeline.map(entry => <li key={entry.id}><a className="btn btn--text" href={link(entry.id)}>{timeLabel(entry.recordedAt)} · {entry.kind === "postmortem" ? "복기" : "보유 점검"}</a><IssueSummary entry={entry} /></li>)}</ol></details>}
      </section>
      <section className="case-section"><h4>다음 확인</h4><p>검토를 마쳐도 미해결 조건과 과거 기한은 남습니다. 기한은 UTC 날짜 기준이며 기존 이유·Portfolio 검토 기한과 별도로 표시합니다.</p>{!view.issues.some(entry => !entry.review.purgedAt && entry.review.resolution !== "resolved") && <p>현재 표시할 미해결 개인 검토가 없습니다. 모든 위험을 확인했다는 뜻은 아닙니다.</p>}</section>
      {draft && view.mode === "current" && <OwnershipForm view={view} value={draft} onChange={value => { setDraft(value); resetPreview(); }} kind={kind} uncertainty={uncertainty} onUncertainty={value => { setUncertainty(value); resetPreview(); }} excluded={excluded} onExcluded={value => { setExcluded(value); resetPreview(); }} busy={busy} onSubmit={() => void propose()} onClose={() => { setDraft(null); resetPreview(); heading.current?.focus(); }} />}
      <section className="case-section"><h4>복기</h4><p>보유 중에도 당시 판단을 다시 읽을 수 있습니다. 수익률 결과와 판단 품질은 따로 돌아봅니다.</p>{!journalId && !draft && view.caseRevision > 0 && <button className="btn" disabled={busy} onClick={() => begin("postmortem")}>지금 기준으로 복기</button>}</section>
    </>}
    {preview && <section className="surface surface--group case-preview ownership-preview"><h4 ref={previewHeading} tabIndex={-1}>확인할 점검 기록</h4><p>{preview.notice}</p>{preview.action === "create" && <p>조사 중 단계로 검토 기록을 시작합니다. 실제 보유를 바꾸지 않습니다.</p>}
      {previewReview && <><ReviewSummary review={{ ...previewReview, reviewedAt: undefined }} uncertainties={preview.journal?.uncertainties} conditionText={draft?.condition.origin === "previous" ? view?.issues.find(row => row.id === draft.previousReviewJournalId)?.conditionView.text : view?.conditionOptions.find(row => row.origin === draft?.condition.origin && row.field === draft?.condition.field && row.index === draft?.condition.index)?.text} /><p>{previewReview.completed ? "이 범위 검토 완료를 함께 기록합니다. " : "검토 완료 표시는 남기지 않습니다. "}완료 시각은 확인한 점검 저장을 누를 때 기록됩니다.</p></>}
      {preview.journal && <details className="ownership-details"><summary>함께 보존할 현재 입력 · {preview.totalBytes.toLocaleString()} / {preview.maxBytes.toLocaleString()} bytes</summary>{slots.map(slot => <PreservedInput key={slot} name={slot} item={preview.journal!.inputs[slot]} />)}</details>}
      {!preview.canConfirm && <p role="alert">{preview.totalBytes > preview.maxBytes ? "보존 크기 제한을 넘었습니다. 항목을 제외한 뒤 다시 확인해 주세요." : `원본 정정 또는 제외가 필요한 입력: ${preview.blockedSlots.map(slot => slotLabels[slot]).join(" · ")}`}</p>}
      <div className="case-actions">{preview.canConfirm && <button className="btn btn--primary" disabled={busy} onClick={() => void confirm()}>확인한 점검 저장</button>}<button className="btn btn--text" disabled={busy} onClick={resetPreview}>점검 미리보기 닫기</button></div>
    </section>}
  </section>;
}
