import { useCallback, useEffect, useRef, useState } from "react";
import { getJson, postJson } from "../../api";
import { openScopedThread } from "../agentWorkspace/openScopedThread";
import { errorCopy, sourceDeletePartialNotice, sourceLink, timeLabel } from "./copy";
import { PreservedInput, Value } from "./PreservedInput";
import { kinds, slots, slotLabels, stages, type CaseView, type JournalView, type Operation, type Preview, type Slot } from "./types";

const params = () => new URLSearchParams(window.location.hash.split("?")[1] || "");
function journalHash(id?: string) {
  const next = params(); next.set("tab", "records");
  if (id) next.set("journal", id); else next.delete("journal");
  window.location.hash = `${window.location.hash.split("?")[0]}?${next}`;
}
const scenarioLabel = (label: string) => ({ base: "기준", conservative: "보수", optimistic: "낙관" }[label] || label);

export function InvestmentCase({ instrumentId, active, onReason }: { instrumentId: string; active: boolean; onReason: () => void }) {
  const [current, setCurrent] = useState<CaseView | null>(null);
  const [journal, setJournal] = useState<JournalView | null>(null);
  const [journalId, setJournalId] = useState(() => params().get("journal") || "");
  const [loading, setLoading] = useState(false); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(false); const [preview, setPreview] = useState<Preview | null>(null);
  const [kind, setKind] = useState("decision"); const [previous, setPrevious] = useState("");
  const [decision, setDecision] = useState(""); const [uncertainties, setUncertainties] = useState("");
  const [precision, setPrecision] = useState("unknown"); const [reported, setReported] = useState("");
  const [stage, setStage] = useState("considering"); const [reentryStage, setReentryStage] = useState("");
  const [excluded, setExcluded] = useState<Slot[]>([]); const [scenario, setScenario] = useState("");
  const [research, setResearch] = useState(""); const [company, setCompany] = useState("");
  const [reviewDate, setReviewDate] = useState(() => params().get("reviewDate") || "");
  const [reports, setReports] = useState<Array<{ id: string; title?: string; generatedAt?: string }>>([]);
  const [companies, setCompanies] = useState<Array<{ id: string; title?: string; generatedAt?: string }>>([]);
  const [cancel, setCancel] = useState<string | null>(null);
  const [readerRefresh, setReaderRefresh] = useState(0);
  const epoch = useRef(0); const readerEpoch = useRef(0); const operationId = useRef("");
  const heading = useRef<HTMLHeadingElement>(null); const previewHeading = useRef<HTMLHeadingElement>(null);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; ++epoch.current; ++readerEpoch.current; }; }, []);
  useEffect(() => {
    if (preview && active) previewHeading.current?.focus();
  }, [preview, active]);
  useEffect(() => {
    if (journal && active && !preview) heading.current?.focus();
  }, [journal, active, preview]);

  const refresh = useCallback(async () => {
    setReaderRefresh(value => value + 1);
    const id = ++epoch.current; setLoading(true);
    try { const value = await getJson<CaseView>(`/api/investment-cases/${encodeURIComponent(instrumentId)}`); if (id === epoch.current) { setCurrent(value); setResearch(value.sourceRefs.research?.id || ""); } }
    catch (reason) { if (id === epoch.current) { setCurrent(null); setError(errorCopy(reason)); } }
    finally { if (id === epoch.current) setLoading(false); }
  }, [instrumentId]);
  useEffect(() => { if (active) void refresh(); }, [active, refresh, journalId]);
  useEffect(() => {
    const onHash = () => setJournalId(params().get("journal") || "");
    window.addEventListener("hashchange", onHash); return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    const id = ++readerEpoch.current; setJournal(null);
    if (!journalId || !active) return;
    void getJson<JournalView>(`/api/decision-journals/${encodeURIComponent(journalId)}`).then(value => {
      if (id === readerEpoch.current && value.journal.instrumentId === instrumentId) setJournal(value);
      else if (id === readerEpoch.current) setError("다른 종목의 기록입니다. 현재 종목의 기록을 선택해 주세요.");
    }).catch(reason => { if (id === readerEpoch.current) setError(errorCopy(reason)); });
  }, [journalId, active, instrumentId, current?.caseRevision, readerRefresh]);
  useEffect(() => {
    if (!editing) return;
    const controller = new AbortController();
    void Promise.all([getJson<unknown>("/api/topic-reports", { signal: controller.signal }), getJson<unknown>("/api/analysis-reports", { signal: controller.signal })]).then(([topics, analyses]) => {
      const list = (value: unknown) => Array.isArray(value) ? value : (value as { reports?: unknown[]; items?: unknown[] } | null)?.reports || (value as { items?: unknown[] } | null)?.items || [];
      setReports(list(topics) as typeof reports);
      setCompanies((list(analyses) as Array<{ id: string; company?: { ticker?: string; market?: string } }>).filter(row => `${row.company?.market}:${row.company?.ticker}` === instrumentId));
    }).catch(() => { if (!controller.signal.aborted) setNotice("선택할 보고서 목록을 읽지 못했습니다. 현재 연결된 자료로 기록하거나 다시 열어 주세요."); });
    return () => controller.abort();
  }, [editing, instrumentId]);

  const invalidPreview = () => { setPreview(null); operationId.current = ""; };
  async function propose(extra: Record<string, unknown>) {
    if (!current || busy) return;
    setBusy(true); setError(""); setNotice(""); invalidPreview();
    try {
      const value = await postJson<Preview>("/api/investment-cases/preview", { instrumentId, expectedCaseRevision: current.caseRevision, ...extra });
      if (!live.current) return;
      setPreview(value); operationId.current = crypto.randomUUID().replace(/-/g, "");
    } catch (reason) { if (live.current) { setError(errorCopy(reason)); await refresh(); } }
    finally { if (live.current) setBusy(false); }
  }
  function previewJournal() {
    if (precision !== "unknown" && !reported) { setError("보고 시점을 입력하거나 알 수 없음을 선택해 주세요."); return; }
    const chosen = current?.scenarioOptions?.find((row) => `${row.label}:${row.horizon}` === scenario);
    const selection: Record<string, string | null> = { researchId: research || null };
    if (company) selection.companyId = company;
    if (reviewDate) selection.reviewDate = reviewDate;
    void propose({ action: "journal", kind, decisionText: decision, uncertainties, excludedSlots: excluded,
      selection, selectedScenario: chosen || null, previousJournalId: previous || undefined,
      ...(kind === "reentry" && reentryStage ? { toStage: reentryStage } : {}),
      userReportedAt: { precision, value: precision === "unknown" ? null : precision === "datetime" ? new Date(reported).toISOString() : reported } });
  }
  async function confirm() {
    if (!preview?.token || busy) return;
    const origin = window.location.hash;
    setBusy(true); setError("");
    try {
      const result = await postJson<Operation>("/api/investment-cases/confirm", { token: preview.token, operationId: operationId.current });
      if (!live.current) return;
      invalidPreview(); setEditing(false); setNotice("확인한 내용을 저장했습니다."); setDecision(""); setUncertainties("");
      await refresh();
      if (window.location.hash === origin) {
        if (result.journalId) journalHash(result.journalId);
        else requestAnimationFrame(() => heading.current?.focus());
      }
    } catch (reason) {
      if (live.current) { setError(errorCopy(reason)); await refresh(); }
    } finally { if (live.current) setBusy(false); }
  }
  async function recover(op: Operation, cancelling = false) {
    if (busy) return; setBusy(true); setError("");
    try {
      const result = await postJson<Operation>(`/api/investment-cases/operations/${op.operationId}/${cancelling ? "cancel" : "recover"}`, cancelling ? { confirmed: true } : {});
      if (!live.current) return;
      setCancel(null); invalidPreview(); setNotice(cancelling ? "미완료 저장을 취소했습니다. 새 미리보기를 만들 수 있습니다." : sourceDeletePartialNotice(result) || "작업을 복구했습니다."); await refresh();
    } catch (reason) { setError(errorCopy(reason)); } finally { setBusy(false); }
  }
  async function askAgent(draft = false) {
    if (!current && !journal) return;
    setBusy(true); setError("");
    try {
      const scope = journal ? { kind: "decision_journal", id: journal.journal.id, bodyHash: journal.bodyHash, intent: "challenge" as const } : { kind: "investment_case", id: current!.caseId, caseRevision: current!.caseRevision, inputFingerprint: current!.inputFingerprint, methodVersion: current!.methodVersion, intent: "challenge" as const };
      await openScopedThread({ title: draft ? "기록 초안" : "기록의 약한 전제", scope, autoSubmit: true,
        initialMessage: draft ? "이 선택한 기록 범위로 결정 기록 초안을 제안해줘. 없는 결정이나 과거 시점을 만들어 내지 말고 반대 근거와 불확실성을 포함해줘. 초안은 내가 확인하고 옮겨 저장할게." : "선택한 당시 기록의 가장 약한 전제와 반대 근거, 불확실성을 검토해줘. 당시 알 수 있던 것과 이후 바뀐 것을 구분하고 투자 행동을 권하지 마." });
      setNotice("Agent 응답은 대화에서 확인하세요. 필요한 글을 기록 폼에 옮기고 미리보기를 확인해야 저장됩니다.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Agent 연결을 확인해 주세요."); } finally { setBusy(false); }
  }

  if (!current && !journal && loading) return <section className="case-workspace" aria-busy="true"><p role="status">현재 입력과 기록을 읽는 중입니다.</p></section>;
  if (!current && !journal) return <section className="case-workspace"><p role="alert">{error || "기록을 불러오지 못했습니다."}</p><button className="btn" onClick={() => void refresh()}>다시 읽기</button></section>;
  const selected = journal?.journal;
  return <section className="case-workspace" data-investment-case data-layer="hypothesis" aria-labelledby="case-heading" aria-busy={busy}>
    <header className="case-head"><div><p className="section-kicker">INVESTMENT CASE</p><h3 id="case-heading" ref={heading} tabIndex={-1}>{selected ? "당시 기록" : "이 종목의 검토와 기록"}</h3></div><span className="chip" data-tone="purple">내 판단 · 근거 아님</span></header>
    <p>지금 보는 자료와 당시 남긴 생각을 함께 읽습니다. 현재 투자 이유는 기존 이유 화면에서 작성합니다.</p>
    {params().get("returnTo") === "review" && <a className="btn btn--text" href={`#/portfolio?tab=review&date=${encodeURIComponent(params().get("reviewDate") || "")}`}>투자 리뷰로 돌아가기</a>}
    {error && <p role="alert" className="react-dashboard-error">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="case-actions"><button className="btn btn--text" disabled={busy} onClick={() => { setError(""); void refresh(); }}>현재 자료 다시 읽기</button><button className="btn btn--text" onClick={onReason}>현재 투자 이유 열기</button>{(journal || (current && current.caseRevision > 0)) && <button className="btn btn--text" disabled={busy} onClick={() => void askAgent()}>Agent로 약한 전제 검토</button>}</div>
    {current?.pendingOperations.map(op => <section className="surface surface--group case-recovery" key={op.operationId}><h4>마무리가 필요한 {op.status === "deleting" ? "삭제" : "저장"}</h4><p>준비된 당시 내용으로 이어서 처리합니다.</p><div className="case-actions"><button className="btn" disabled={busy} onClick={() => void recover(op)}>작업 복구</button>{op.cancelAllowed && <button className="btn btn--text" disabled={busy} onClick={() => setCancel(op.operationId)}>미완료 저장 취소</button>}</div>{cancel === op.operationId && <><p>이 미완료 기록의 준비 파일을 지우고 저장을 종결합니다. 게시된 기록은 취소하지 않습니다.</p><button className="btn btn--danger" disabled={busy} onClick={() => void recover(op, true)}>미완료 저장 취소 확인</button><button className="btn btn--text" onClick={() => setCancel(null)}>돌아가기</button></>}</section>)}
    {journalId && !selected && <p role="status">{error ? "당시 기록을 표시할 수 없습니다." : "당시 기록을 읽는 중입니다."}<button className="btn btn--text" onClick={() => journalHash()}>기록 목록으로</button></p>}
    {selected && <section className="case-section case-reader"><div className="case-actions"><button className="btn btn--text" onClick={() => { journalHash(); setError(""); }}>기록 목록으로</button><span className="chip">{kinds[selected.kind]}</span></div>
      <dl className="case-meta"><div><dt>실제 기록 시각</dt><dd>{timeLabel(selected.recordedAt)}</dd></div><div><dt>사용자가 보고한 시점</dt><dd>{selected.userReportedAt.value || "알 수 없음"}{selected.userReportedAt.precision === "date" ? " · 날짜까지만" : ""}</dd></div></dl>
      <h4>당시 남긴 생각</h4><p className="case-text">{selected.decisionText || (selected.personalPurgedAt ? "개인본문 삭제됨" : "결정 글 없음")}</p><h4>당시 불확실성</h4><p className="case-text">{selected.uncertainties || "작성하지 않음"}</p>
      {selected.previousJournalId && <button className="btn btn--text" onClick={() => journalHash(selected.previousJournalId)}>연결한 이전 기록 열기</button>}
      {selected.selectedScenario && <p>선택 시나리오: {scenarioLabel(selected.selectedScenario.label)} · {selected.selectedScenario.horizon}년</p>}
      <h4>당시 보존한 입력</h4>{slots.map(slot => <PreservedInput key={`${selected.id}:${slot}`} name={slot} item={selected.inputs[slot]} availability={journal?.sourceAvailability[slot]}
        onPurge={current ? () => void propose({ action: "purge", targetJournalId: selected.id, purgeSlots: [slot] }) : undefined}
        onCorrection={current ? () => void propose({ action: "correction", targetJournalId: selected.id, correctionSlot: slot }) : undefined} />)}
      {journal && journal.corrections.length > 0 && <section className="case-current"><h4>이후 확인한 자료 연결</h4>{journal.corrections.map(link => <p key={link.id}>{slotLabels[link.slot]} · {timeLabel(link.notedAt)} · 당시 본문 유지 · {link.newRef.id || "자료 없음"}{link.newRef.revision ? ` · ${link.newRef.revision}번째 판본` : ""}{sourceLink(link.newRef) && <a className="btn btn--text" href={sourceLink(link.newRef)!}>이후 확인한 자료 열기</a>}</p>)}</section>}
      <button className="btn btn--danger" disabled={busy || !current} onClick={() => void propose({ action: "purge", targetJournalId: selected.id, purgePersonal: true })}>이 기록의 보존본문 전체 삭제</button>
    </section>}
    {!selected && !journalId && current && <>
      <section className="case-section"><h4>현재 검토 단계</h4><p><strong>{current.lifecycle ? stages[current.lifecycle] : "아직 검토 기록을 만들지 않았습니다"}</strong> · 직접 선택한 검토 단계입니다. 실제 보유는 Portfolio가 기준입니다.</p>
        {current.lifecycleMismatch && <p>선택한 단계와 현재 Portfolio 보유 상태가 다릅니다. 자동으로 맞추지 않았습니다.</p>}
        {current.caseRevision === 0 ? <button className="btn btn--primary" disabled={busy} onClick={() => void propose({ action: "create" })}>검토 기록 시작</button> : <div className="case-actions"><label className="field">다음 단계<select value={stage} onChange={e => { setStage(e.target.value); invalidPreview(); }}>{Object.entries(stages).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button className="btn" disabled={busy} onClick={() => void propose({ action: "transition", toStage: stage, excludedSlots: excluded })}>단계 변경 미리보기</button></div>}
        {current.events && current.events.length > 0 && <details><summary>단계와 기록 이력</summary><ul>{current.events.map((event, i) => <li key={i}>{timeLabel(event.recorded_at)} · {kinds[event.kind] || (event.kind === "create" ? "검토 시작" : event.kind === "purge" ? "본문 삭제" : "명시적 변경")}{event.to_stage ? ` · ${stages[event.to_stage]}` : ""}</li>)}</ul></details>}
      </section>
      <section className="case-section"><h4>현재 연결된 입력</h4><ul className="case-input-list">{slots.map(slot => <li key={slot}><strong>{slotLabels[slot]}</strong><span>{current.inputs[slot]?.status === "preserved" ? "현재 자료 있음" : "자료 없음"}{current.staleReasons.some(row => row.slot === slot) ? " · 이전 기록 후 변경" : ""}</span></li>)}</ul><p>{current.readiness?.message} · 기준 충족은 가격과 내 기준의 검토 상태입니다.</p>
        <details><summary>현재 이유 · 조건 · 다음 확인</summary><Value value={current.reasonSummary || { summary: "아직 작성한 이유가 없습니다." }} /></details>
      </section>
      <section className="case-section"><div className="case-head"><h4>이전 기록</h4>{current.caseRevision > 0 && <button className={`btn${editing ? "" : " btn--primary"}`} onClick={() => { setEditing(!editing); invalidPreview(); }}> {editing ? "작성 폼 닫기" : "기록 남기기"}</button>}</div>
        {current.journals.length ? <ol className="case-history">{current.journals.map(row => <li key={row.id}><button className="btn btn--text case-history-link" onClick={() => { setEditing(false); invalidPreview(); journalHash(row.id); }}><strong>{timeLabel(row.recordedAt)} · {kinds[row.kind || ""] || "기록"}</strong><span>{row.status !== "ready" ? "본문 확인 필요" : row.purged ? "개인본문 삭제됨" : row.preview || "결정 글 없음"}</span></button></li>)}</ol> : <p>아직 남긴 기록이 없습니다. 아무 글도 강제로 채우지 않아도 됩니다.</p>}
      </section>
    </>}
    {editing && !selected && current && <form className="surface surface--group case-form" onChangeCapture={invalidPreview} onSubmit={event => { event.preventDefault(); previewJournal(); }}>
      <h4>새 기록</h4><p>작성하지 않은 내용은 그대로 비워 둡니다. 과거에 알고 있었다고 소급해 기록하지 않습니다.</p>
      <label className="field">기록 종류<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(kinds).filter(([key]) => key !== "stage_change").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      {kind !== "decision" && <label className="field">연결할 이전 기록<select value={previous} onChange={e => setPrevious(e.target.value)}><option value="">기록을 선택해 주세요</option>{current.journals.map(row => <option key={row.id} value={row.id}>{timeLabel(row.recordedAt)} · {row.preview?.slice(0, 40) || "결정 글 없음"}</option>)}</select></label>}
      {kind === "reentry" && <><p>이전 기록과 연결된 새 검토를 시작합니다. 실제 거래 기록을 만들지는 않습니다.</p><label className="field">새 검토 단계<select value={reentryStage} onChange={e => setReentryStage(e.target.value)}><option value="">현재 단계 유지</option>{Object.entries(stages).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></>}
      <label className="field">결정이나 변화에 대한 생각<textarea value={decision} maxLength={12000} onChange={e => setDecision(e.target.value)} rows={4} /></label>
      <label className="field">반대 근거와 불확실성<textarea value={uncertainties} maxLength={8000} onChange={e => setUncertainties(e.target.value)} rows={3} /></label>
      <div className="case-form-grid"><label className="field">사용자가 보고한 시점<select value={precision} onChange={e => { setPrecision(e.target.value); setReported(""); }}><option value="unknown">알 수 없음</option><option value="date">날짜까지만</option><option value="datetime">날짜와 시간</option></select></label>{precision !== "unknown" && <label className="field">보고 시점<input type={precision === "date" ? "date" : "datetime-local"} value={reported} onChange={e => setReported(e.target.value)} /></label>}</div>
      <p>실제 저장 시각은 별도로 남습니다. 위 시점은 사용자의 진술입니다.</p>
      <label className="field">당시 선택한 가격 시나리오<select value={scenario} onChange={e => setScenario(e.target.value)}><option value="">선택하지 않음</option>{current.scenarioOptions?.map(row => <option key={`${row.label}:${row.horizon}`} value={`${row.label}:${row.horizon}`}>{scenarioLabel(row.label)} · {row.horizon}년</option>)}</select></label>
      <details><summary>보존할 자료 선택</summary><div className="case-form-grid"><label className="field">기업 분석<select value={company} onChange={e => setCompany(e.target.value)}><option value="">현재 연결된 최신 보고서</option>{companies.map(row => <option key={row.id} value={row.id}>{row.title || "기업 분석"} · {timeLabel(row.generatedAt)}</option>)}</select></label><label className="field">관련 딥 리서치<select value={research} onChange={e => setResearch(e.target.value)}><option value="">연결하지 않음</option>{research && !reports.some(row => row.id === research) && <option value={research}>기존 연결 자료</option>}{reports.map(row => <option key={row.id} value={row.id}>{row.title || "딥 리서치"} · {timeLabel(row.generatedAt)}</option>)}</select></label><label className="field">참고할 리뷰 날짜<input type="date" value={reviewDate} onChange={e => setReviewDate(e.target.value)} /></label></div><p>딥 리서치는 직접 선택한 관련 맥락입니다. 같은 종목인지 확인되지 않으면 그 상태를 표시합니다.</p><fieldset className="case-checks"><legend>보존할 입력</legend>{slots.map(slot => <label key={slot}><input type="checkbox" checked={!excluded.includes(slot)} onChange={e => setExcluded(e.target.checked ? excluded.filter(key => key !== slot) : [...excluded, slot])} />{slotLabels[slot]}</label>)}</fieldset><p>첨부 파일·기기 경로·전체 대화는 보존하지 않습니다. 한 기록은 최대 5 MiB이며 자동 만료되지 않습니다.</p></details>
      <div className="case-actions"><button className="btn btn--primary" disabled={busy} type="submit">저장 내용 미리보기</button><button className="btn" type="button" disabled={busy} onClick={() => void askAgent(true)}>Agent에 초안 요청</button></div>
    </form>}
    {preview && <section className="surface surface--group case-preview" aria-labelledby="case-preview-heading"><h4 id="case-preview-heading" ref={previewHeading} tabIndex={-1}>확인할 변경</h4><p>{preview.notice}</p>
      {preview.action === "create" || preview.action === "transition" ? <p>검토 단계: {stages[preview.lifecycle.from] || "미시작"} → {stages[preview.lifecycle.to]}</p> : null}
      {preview.journal && <><p>저장 크기: {preview.totalBytes.toLocaleString()} bytes / {preview.maxBytes.toLocaleString()} bytes</p><p className="case-text">{preview.journal.decisionText || "결정 글 없음"}</p><p className="case-text">{preview.journal.uncertainties || "불확실성 작성하지 않음"}</p>{slots.map(slot => <PreservedInput key={slot} name={slot} item={preview.journal!.inputs[slot]} />)}</>}
      {!preview.journal && preview.totalBytes > preview.maxBytes && <p>용량 제한을 넘었습니다. 보존할 자료 선택에서 항목을 제외한 뒤 다시 미리보기를 만드세요. ({preview.totalBytes.toLocaleString()} bytes)</p>}
      {preview.action === "transition" && (preview.totalBytes > preview.maxBytes || preview.blockedSlots.length > 0) && <fieldset className="case-checks"><legend>보유 단계 기록에서 보존할 입력</legend>{slots.map(slot => <label key={slot}><input type="checkbox" checked={!excluded.includes(slot)} onChange={e => setExcluded(e.target.checked ? excluded.filter(key => key !== slot) : [...excluded, slot])} />{slotLabels[slot]}</label>)}<button className="btn" disabled={busy} onClick={() => void propose({ action: "transition", toStage: stage, excludedSlots: excluded })}>선택한 항목으로 단계 변경 다시 확인</button></fieldset>}{preview.blockedSlots.length > 0 && <p role="alert">원본을 정정하거나 보존에서 제외할 항목: {preview.blockedSlots.map(slot => slotLabels[slot]).join(", ")}</p>}
      {preview.purge && <p>{preview.purge.personal ? "개인 글·보고 시점·선택 시나리오와 모든 보존본문을 삭제합니다. 식별자와 실제 기록 시각은 남습니다." : `${preview.purge.slots.map(slot => slotLabels[slot]).join(", ")} 보존본문을 삭제합니다.`}</p>}
      {preview.correction && <p>{slotLabels[preview.correction.slot]}의 현재 자료를 이후 확인으로 연결합니다. 당시 본문은 유지됩니다.</p>}
      <div className="case-actions">{preview.canConfirm && <button className={`btn btn--primary${preview.purge ? " btn--danger" : ""}`} disabled={busy} onClick={() => void confirm()}>{preview.purge ? "범위 확인 후 본문 삭제" : "확인한 내용 저장"}</button>}<button className="btn btn--text" disabled={busy} onClick={() => { invalidPreview(); heading.current?.focus(); }}>미리보기 닫기</button></div>
    </section>}
  </section>;
}
