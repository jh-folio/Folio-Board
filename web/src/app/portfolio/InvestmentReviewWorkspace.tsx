import { useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError, getJson, postJson } from "../../api";
import { openScopedThread } from "../agentWorkspace/openScopedThread";
import { reviewStateDisplay, thesisVerdictDisplay } from "../verification";
import { isOverdue, readinessFor, readinessLabel, reviewReasonLabel, safeReportRoute, sortReviewPositions, type CanonicalReference, type ReviewPosition, type ReviewReason } from "./investmentReviewUi";

type Checkpoint = { id?: string; label?: string; dueAt?: string };
type PositionReview = ReviewPosition & { dueCheckpoints?: Checkpoint[]; quantitativeRiskSignals?: Array<{ weight?: number; baseCurrency?: string }>; counterEvidence?: Array<{ title?: string } | string>; uncertainties?: ReviewReason[]; canonicalReferences?: CanonicalReference[] };
type HistoryItem = Pick<InvestmentReview, "date" | "reviewRevision" | "reviewState" | "reviewedAt" | "generatedAt" | "sourceSchemaVersion">;

export type InvestmentReview = {
  date: string; reviewRevision: number; sourceSchemaVersion?: number; reviewState: "draft" | "reviewed" | "stale" | "due"; reviewedAt?: string; generatedAt?: string; summary?: string;
  freshness?: { status?: string; dueCount?: number; overdueUnresolvedCount?: number; evaluatedAt?: string; reasons?: ReviewReason[] };
  inputBasis?: { status?: string; theses?: Array<{ ticker?: string }>; canonicalReports?: CanonicalReference[] };
  reportSelection?: { candidateCount?: number; includedCount?: number; excludedCount?: number };
  changesSincePrevious?: Array<{ kind?: string; key?: string; change?: string; from?: unknown; to?: unknown }>;
  positionReviews?: PositionReview[]; positionRoster?: ReviewPosition[];
  coverage?: { totalPositionCount?: number; rosterIncludedCount?: number; detailIncludedCount?: number; omittedRosterCount?: number; omittedDetailCount?: number };
  sharedExposures?: Array<{ type?: string; label?: string; key?: string; tickers?: string[]; weight?: number }>;
  portfolioRisks?: Array<{ riskKey?: string; status?: string; concentration?: { top1?: number | null; top3?: number | null; holdings?: number | null }; backtestRef?: { start?: string; end?: string; window?: string } }>;
  counterEvidence?: Array<{ title?: string } | string>; uncertainties?: ReviewReason[]; staleReasons?: ReviewReason[];
  portfolioImpacts?: Array<{ ticker?: string; name?: string; impact?: string; reason?: string }>;
  thesisChanges?: Array<{ ticker?: string; name?: string; verdict?: string }>;
  keyCheckpoints?: Array<{ ticker?: string; checkpoint?: string; dueAt?: string }>;
  recentReports?: Array<{ title?: string; date?: string; type?: string }>;
};
type History = { items: HistoryItem[] };

const text = (value: unknown) => typeof value === "string" ? value : "";
const ticker = (value: string | undefined) => String(value || "").trim().toUpperCase();
const evidenceText = (value: { title?: string } | string) => typeof value === "string" ? value : value.title || "추가 근거 확인";
const finitePercent = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "확인 필요";
const stateCopy = (state: InvestmentReview["reviewState"]) => reviewStateDisplay(state).label;
const basisLabel = (value: string | undefined) => ({ complete: "확인 완료", partial: "일부 확인", legacy_unknown: "기준 정보 없음" }[String(value || "")] || "확인 필요");
const reportKindLabel = (value: string | undefined) => ({ briefing: "시장 브리핑", company_analysis: "기업 분석", topic_report: "주제 분석" }[String(value || "")] || "연결 자료");
const staleReasonLabel = (reason: ReviewReason) => ({ input_fingerprint_changed: "보유 내역이나 연결 자료가 바뀌어 다시 확인이 필요합니다.", input_changed: "보유 내역이나 연결 자료가 바뀌어 다시 확인이 필요합니다.", input_basis_incomplete: "확인 기준이 충분하지 않습니다.", legacy_input_basis_unknown: "이전 저장본이라 당시 입력 기준을 확인할 수 없습니다." }[String(reason.code || "")] || "다시 확인이 필요합니다.");
const uncertaintyLabel = (reason: ReviewReason) => ({ thesis_missing: "투자 논리가 아직 없습니다.", compatible_saved_backtest_missing: "같은 기준으로 비교할 저장된 백테스트가 없습니다.", first_review: "비교할 이전 저장 리뷰가 없습니다.", previous_review_not_comparable: "이전 저장 리뷰의 기준이 달라 변화 비교가 제한됩니다." }[String(reason.code || "")] || "추가 확인이 필요합니다.");
const checkpointStatusLabel = (value: unknown) => ({ open: "열림", confirmed: "확인됨", challenged: "반증됨", expired: "기한 경과", closed: "종료", pending: "확인 대기", no_signal: "신호 없음" }[text(value)] || "상태 확인 필요");
const checkpointDirectionLabel = (value: unknown) => ({ supporting: "지지 확인", challenging: "반증 확인", up: "상향", down: "하향" }[text(value)] || "방향 확인 필요");
const checkpointVerdictLabel = (value: unknown) => ({ confirmed: "확인됨", challenged: "반증됨", no_signal: "신호 없음", maintained: "유지", weakened: "약화" }[text(value)] || "판정 기록됨");
const riskStatusLabel = (value: unknown) => ({ available: "참고 가능", unavailable: "참고 불가" }[text(value)] || "상태 확인 필요");

function isMissing(review: InvestmentReview | null) { return !review || (review.reviewRevision === 0 && review.sourceSchemaVersion !== 1); }
function changeDetail(kind: string | undefined, value: unknown) {
  const row = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  if (kind === "checkpoint") {
    const last = row.lastVerdict && typeof row.lastVerdict === "object" && !Array.isArray(row.lastVerdict) ? row.lastVerdict as Record<string, unknown> : {};
    const evidence = Array.isArray(last.evidence) ? last.evidence.filter((item) => item && typeof item === "object").length : 0;
    const verdict = text(row.lastVerdict) || text(last.verdict);
    const values = [row.status ? checkpointStatusLabel(row.status) : "", row.direction ? checkpointDirectionLabel(row.direction) : "", text(row.dueBy), verdict ? checkpointVerdictLabel(verdict) : "", evidence ? `근거 ${evidence}개` : ""].filter(Boolean);
    return values.length ? values.join(" · ") : "이전 상세 없음";
  }
  if (kind === "narrative") {
    const momentum = text(row.momentum); const weight = typeof row.weight === "number" && Number.isFinite(row.weight) ? finitePercent(row.weight) : "";
    const tickers = Array.isArray(row.tickers) ? row.tickers.filter((item): item is string => typeof item === "string").slice(0, 12).join(", ") : "";
    const values = [tickers, momentum, weight].filter(Boolean);
    return values.length ? values.join(" · ") : "이전 상세 없음";
  }
  if (kind === "risk") {
    const concentration = row.concentration && typeof row.concentration === "object" ? row.concentration as Record<string, unknown> : {};
    const top1 = typeof concentration.top1 === "number" ? `상위 1개 ${finitePercent(concentration.top1)}` : "";
    const top3 = typeof concentration.top3 === "number" ? `상위 3개 ${finitePercent(concentration.top3)}` : "";
    const holdings = typeof concentration.holdings === "number" ? `보유 ${concentration.holdings}개` : "";
    const contributions = Array.isArray(row.riskContributions) ? row.riskContributions.slice(0, 4).flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const contribution = item as Record<string, unknown>;
      return typeof contribution.ticker === "string" && typeof contribution.weight === "number" ? [`${contribution.ticker} ${finitePercent(contribution.weight)}`] : [];
    }).join(", ") : "";
    const values = [row.status ? riskStatusLabel(row.status) : "", top1, top3, holdings, contributions].filter(Boolean);
    return values.length ? values.join(" · ") : "이전 상세 없음";
  }
  return "이전 상세 없음";
}
function changeCopy(row: NonNullable<InvestmentReview["changesSincePrevious"]>[number]) {
  const key = text(row.key);
  const subjectRoot = row.kind === "verdict" ? ticker(row.key) || "보유 종목" : ({ checkpoint: "체크포인트", narrative: "공동 노출", risk: "정량 위험" }[String(row.kind || "")] || "저장 리뷰");
  const subject = row.kind === "verdict" || !key ? subjectRoot : `${subjectRoot} · ${key}`;
  const action = ({ added: "추가", removed: "제거", changed: "변경" }[String(row.change || "")] || "변경");
  const verdict = (value: unknown) => ["strengthened", "maintained", "weakened", "at_risk", "broken", "insufficient_evidence"].includes(text(value)) ? thesisVerdictDisplay(text(value)).label : "이전 상세 없음";
  if (row.change !== "changed") return `${subject} · ${action}`;
  return row.kind === "verdict" ? `${subject} · ${verdict(row.from)} → ${verdict(row.to)}` : `${subject} · ${changeDetail(row.kind, row.from)} → ${changeDetail(row.kind, row.to)}`;
}
function watchlistRoute(value: string | undefined) { return ticker(value) ? `#/watchlist/${encodeURIComponent(ticker(value))}` : "#/watchlist"; }

export function reviewAttentionLabel(review: InvestmentReview | null | undefined): string {
  if (!review || isMissing(review)) return "";
  const overdue = review.freshness?.overdueUnresolvedCount || 0;
  const due = review.freshness?.dueCount || 0;
  if (review.reviewState === "stale") return overdue ? `오래됨 · 기한 경과 ${overdue}건` : due ? `오래됨 · 확인 예정 ${due}건` : "오래됨";
  return overdue ? `기한 경과 ${overdue}건` : review.reviewState === "due" ? `확인 예정 ${due}건` : "";
}

export function InvestmentReviewWorkspace({ onGenerated, onNavigateHoldings, hasSavedHoldings = false }: { onGenerated?: () => void; onNavigateHoldings?: () => void; hasSavedHoldings?: boolean }) {
  const [review, setReview] = useState<InvestmentReview | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [working, setWorking] = useState<"generate" | "reviewed" | "challenge" | "">("");
  const [notice, setNotice] = useState(""); const [error, setError] = useState("");
  const requestEpoch = useRef(0);

  async function refresh(selectedDate = "") {
    const epoch = ++requestEpoch.current; setLoading(true); setError("");
    try {
      const [latest, snapshots, selected] = await Promise.all([
        getJson<InvestmentReview>("/api/investment-review"),
        getJson<History>("/api/investment-review/history"),
        selectedDate ? getJson<InvestmentReview>(`/api/investment-review/${encodeURIComponent(selectedDate)}`) : Promise.resolve(null),
      ]);
      if (epoch !== requestEpoch.current) return;
      setReview(selected || latest); setHistory(Array.isArray(snapshots.items) ? snapshots.items : []);
    } catch (reason) { if (epoch === requestEpoch.current) setError(reason instanceof Error ? reason.message : "투자 리뷰를 불러오지 못했습니다."); }
    finally { if (epoch === requestEpoch.current) setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  async function selectHistory(item: HistoryItem) {
    const epoch = ++requestEpoch.current; setHistoryLoading(true); setNotice(""); setError("");
    try { const selected = await getJson<InvestmentReview>(`/api/investment-review/${encodeURIComponent(item.date)}`); if (epoch === requestEpoch.current) setReview(selected); }
    catch (reason) { if (epoch === requestEpoch.current) setError(reason instanceof Error ? reason.message : "선택한 저장 리뷰를 불러오지 못했습니다."); }
    finally { if (epoch === requestEpoch.current) setHistoryLoading(false); }
  }
  async function generate() {
    setWorking("generate"); setNotice(""); setError("");
    try { const updated = await postJson<InvestmentReview>("/api/investment-review/generate", { generationMode: "rules" }); setReview(updated); setNotice("오늘의 규칙 기반 리뷰를 갱신했습니다."); await refresh(updated.date); onGenerated?.(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "리뷰 갱신에 실패했습니다."); } finally { setWorking(""); }
  }
  async function reviewed() {
    if (!review) return; setWorking("reviewed"); setNotice(""); setError("");
    try { const updated = await postJson<InvestmentReview>(`/api/investment-review/${encodeURIComponent(review.date)}/reviewed`, { expectedReviewRevision: review.reviewRevision }); setReview(updated); setNotice("이 리뷰를 검토 완료로 기록했습니다."); await refresh(updated.date); }
    catch (reason) { if (reason instanceof ApiRequestError && reason.status === 409) { await refresh(review.date); setError("리뷰 기준이 바뀌었거나 이미 오래되었습니다. 최신 리뷰를 확인한 뒤 다시 시도하세요."); } else setError(reason instanceof Error ? reason.message : "검토 완료 기록에 실패했습니다."); } finally { setWorking(""); }
  }
  async function challenge() {
    if (!review || review.reviewRevision < 1) return; setWorking("challenge"); setNotice(""); setError("");
    try { await openScopedThread({ title: "투자 리뷰의 약한 전제", scope: { kind: "investment_review", id: review.date, revision: review.reviewRevision, intent: "challenge" }, initialMessage: "이 리뷰의 가장 약한 전제를 찾아줘", autoSubmit: true }); setNotice("Agent에게 이 리뷰의 반증 검토를 요청했습니다."); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Agent 요청에 실패했습니다."); } finally { setWorking(""); }
  }

  const knownTheses = useMemo(() => new Set((review?.inputBasis?.theses || []).map((row) => ticker(row.ticker)).filter(Boolean)), [review]);
  if (loading) return <section className="cockpit-panel investment-review-workspace" aria-busy="true"><p role="status">투자 리뷰를 불러오는 중입니다.</p></section>;
  if (error && !review) return <section className="cockpit-panel investment-review-workspace" role="alert"><p>{error}</p><button className="btn" type="button" onClick={() => void refresh()}>다시 시도</button></section>;
  const missing = isMissing(review); const state = review?.reviewState || "draft"; const locked = working !== "" || historyLoading;
  const detailRows = review?.positionReviews || []; const roster = review?.positionRoster?.length ? review.positionRoster : detailRows;
  const detailByTicker = new Map(detailRows.map((row) => [ticker(row.ticker), row]));
  // The minimal roster is capped at 100, while the backend can deliberately
  // select a high-risk detail outside that cap. Preserve both without
  // reinterpreting the backend coverage counts as a complete roster.
  const rosterTickers = new Set(roster.map((row) => ticker(row.ticker)).filter(Boolean));
  const displayRows = [...roster, ...detailRows.filter((row) => !rosterTickers.has(ticker(row.ticker)))];
  const displayPositions = sortReviewPositions(displayRows.map((row) => detailByTicker.get(ticker(row.ticker)) || row), review?.freshness?.evaluatedAt, knownTheses);
  const count = (kind: ReturnType<typeof readinessFor>) => displayRows.filter((row) => readinessFor(row, knownTheses) === kind).length;
  const overdue = review?.freshness?.overdueUnresolvedCount; const due = review?.freshness?.dueCount || 0;
  const criticalRows = displayPositions.filter((row) => {
    const detail = detailByTicker.get(ticker(row.ticker));
    return ["broken", "at_risk", "weakened"].includes(String(row.thesisVerdict || ""))
      || (detail?.dueCheckpoints || []).some((checkpoint) => isOverdue(checkpoint.dueAt, review?.freshness?.evaluatedAt))
      || (detail?.counterEvidence || []).length;
  });
  const explicitlyMissingThesisTickers = new Set(displayRows.filter((row) => readinessFor(row, knownTheses) === "missing_thesis").map((row) => ticker(row.ticker)).filter(Boolean));
  const groupedUncertainties = (() => {
    const groups = new Map<string, ReviewReason[]>();
    for (const reason of review?.uncertainties || []) {
      // New records carry an explicit boolean and are counted above. Older
      // records do not: retain their saved warning rather than inferring a
      // missing Thesis from an omitted boolean or silently dropping it.
      if (reason.code === "thesis_missing" && reason.ticker && explicitlyMissingThesisTickers.has(ticker(reason.ticker))) continue;
      const key = String(reason.code || "unknown"); groups.set(key, [...(groups.get(key) || []), reason]);
    }
    return [...groups.entries()];
  })();
  const historySection = <details className="investment-review-details"><summary>리뷰 이력</summary><div><section className="investment-review-section"><h3>날짜별 저장 리뷰</h3>{history.length ? <ul className="investment-review-history">{history.map((item) => <li key={`${item.date}:${item.reviewRevision}`}><button className="btn btn--text" type="button" aria-pressed={review?.date === item.date} disabled={locked} onClick={() => void selectHistory(item)}>{item.date} · {stateCopy(item.reviewState)}{item.reviewRevision > 1 ? ` · ${item.reviewRevision}번째 갱신` : item.sourceSchemaVersion === 1 ? " · 이전 저장 형식" : ""}</button></li>)}</ul> : <p>아직 저장된 이력이 없습니다.</p>}</section></div></details>;
  const actions = <div className="investment-review-actions" aria-label="투자 리뷰 작업"><button className="btn btn--primary" type="button" disabled={locked} onClick={() => void generate()}>{working === "generate" ? "갱신 중" : "오늘 리뷰 갱신"}</button><button className="btn" type="button" disabled={locked || missing || state === "stale" || review?.reviewRevision === 0} onClick={() => void reviewed()}>{working === "reviewed" ? "기록 중" : "검토 완료"}</button><button className="btn" type="button" disabled={locked || missing || review?.reviewRevision === 0} onClick={challenge}>{working === "challenge" ? "Agent 요청 중" : "이 리뷰의 가장 약한 전제를 찾아줘"}</button></div>;

  return <section className="cockpit-panel investment-review-workspace" data-layer="hypothesis" aria-labelledby="investment-review-title">
    <header className="cockpit-panel__head"><div><span>INVESTMENT REVIEW</span><h2 id="investment-review-title">투자 리뷰</h2></div><div className="investment-review-head-chips"><span className="chip verification-chip" data-tone="muted">내 판단 · 근거 아님</span>{!missing && (() => { const display = reviewStateDisplay(state); return <span className="chip verification-chip" data-tone={display.tone} aria-label={`리뷰 상태: ${display.label}`}><span aria-hidden="true">{display.icon}</span> {display.label}</span>; })()}</div></header>
    <p className="section-subtitle">저장된 보유 포지션과 명시적으로 연결된 Thesis·시장 상태를 함께 읽습니다. 매수·매도 지시는 만들지 않습니다.</p>
    {(notice || error) && <p className={error ? "react-dashboard-error" : "react-reader-status"} role={error ? "alert" : "status"} aria-live="polite">{error || notice}</p>}
    {missing ? <><section className="investment-review-section investment-review-empty"><h3>저장된 리뷰가 없습니다</h3>{hasSavedHoldings ? <p>현재 저장된 보유 내역을 기준으로 오늘 리뷰를 갱신할 수 있습니다.</p> : <><p>저장된 보유 종목이 없습니다. 보유·평가에서 종목을 저장한 뒤 오늘 리뷰를 갱신하세요.</p><button className="btn" type="button" onClick={onNavigateHoldings}>보유·평가로 가기</button></>}</section>{actions}{historySection}</> : <>
      <section className="investment-review-section"><h3>저장 리뷰 요약</h3><p>{review?.summary || "요약이 없습니다."}</p><dl className="investment-review-meta"><div><dt>기준일</dt><dd>{review?.date || "확인 필요"}</dd></div><div><dt>상태</dt><dd>{stateCopy(state)}</dd></div><div><dt>입력 기준</dt><dd>{basisLabel(review?.inputBasis?.status)}</dd></div><div><dt>새로 도래</dt><dd>확인 예정 {due}건</dd></div>{typeof overdue === "number" && <div><dt>기한 경과</dt><dd>{overdue}건</dd></div>}</dl></section>
      <section className="investment-review-section"><h3>지난 리뷰 이후 변화</h3>{(review?.changesSincePrevious || []).length ? <ul>{review!.changesSincePrevious!.map((row, index) => <li key={`${row.kind}:${row.key}:${index}`}>{changeCopy(row)}</li>)}</ul> : <p>비교할 이전 날짜 리뷰가 없거나, 확인 가능한 변화가 없습니다.</p>}</section>
      {review?.sourceSchemaVersion === 1 && <section className="investment-review-section"><h3>이전 저장본의 항목</h3>{(review.portfolioImpacts || []).length ? <ul>{review.portfolioImpacts!.map((row, index) => <li key={`legacy-impact-${row.ticker || index}`}>{row.ticker || row.name || "보유 종목"}{row.impact ? ` · ${row.impact}` : ""}{row.reason ? ` · ${row.reason}` : ""}</li>)}</ul> : null}{(review.thesisChanges || []).length ? <ul>{review.thesisChanges!.map((row, index) => <li key={`legacy-thesis-${row.ticker || index}`}>{row.ticker || row.name || "Thesis"}{row.verdict ? ` · ${row.verdict}` : ""}</li>)}</ul> : null}{(review.keyCheckpoints || []).length ? <ul>{review.keyCheckpoints!.map((row, index) => <li key={`legacy-checkpoint-${row.ticker || index}`}>{row.ticker ? `${row.ticker} · ` : ""}{row.checkpoint || "체크포인트"}{row.dueAt ? ` · ${row.dueAt}` : ""}</li>)}</ul> : null}{(review.recentReports || []).length ? <ul>{review.recentReports!.map((row, index) => <li key={`legacy-report-${row.title || index}`}>{row.title || "연결 자료"}{row.date ? ` · ${row.date}` : ""}{row.type ? ` · ${row.type}` : ""}</li>)}</ul> : null}{!(review.portfolioImpacts || []).length && !(review.thesisChanges || []).length && !(review.keyCheckpoints || []).length && !(review.recentReports || []).length && <p>이전 저장 형식의 세부 항목은 없습니다.</p>}</section>}
      <section className="investment-review-section investment-review-attention" aria-label="중요 반대 근거와 불확실성"><h3>중요 반대 근거와 불확실성</h3>{state === "stale" && <ul>{(review?.staleReasons || review?.freshness?.reasons || [{ code: "" }]).map((reason, index) => <li key={`${reason.code || "stale"}:${reason.ticker || ""}:${index}`}>{staleReasonLabel(reason)}{reason.ticker ? ` · ${reason.ticker}` : ""}</li>)}</ul>}{(review?.counterEvidence || []).length ? <div><strong>반대 근거</strong><ul>{review!.counterEvidence!.map((item, index) => <li key={`counter-${index}`}>{evidenceText(item)}</li>)}</ul></div> : null}{criticalRows.length ? <div><strong>우선 확인 신호</strong><ul>{criticalRows.map((row) => { const detail = detailByTicker.get(ticker(row.ticker)); const readiness = readinessFor(row, knownTheses); const overdueRows = (detail?.dueCheckpoints || []).filter((checkpoint) => isOverdue(checkpoint.dueAt, review?.freshness?.evaluatedAt)); const label = ["missing_thesis", "missing_review"].includes(readiness) ? readinessLabel(readiness) : thesisVerdictDisplay(row.thesisVerdict).label; return <li key={`critical-${row.ticker}`}>{row.ticker} · {label}{overdueRows.length ? ` · 기한 경과 ${overdueRows.map((checkpoint) => checkpoint.label || "체크포인트").join(" · ")}` : ""}{(detail?.counterEvidence || []).length ? ` · 반대 근거 ${detail!.counterEvidence!.map(evidenceText).join(" · ")}` : ""}</li>; })}</ul></div> : null}{(review?.sharedExposures || []).length ? <p>공동 위험: {review!.sharedExposures!.map((row) => `${row.label || "공동 노출"}${typeof row.weight === "number" ? ` ${finitePercent(row.weight)}` : ""}`).join(" · ")}</p> : null}{count("missing_thesis") > 0 && <p>투자 논리가 아직 없는 보유 종목 {count("missing_thesis")}개가 있습니다. 이 상태는 검토 결과가 아닙니다.</p>}{count("missing_review") > 0 && <p>투자 논리는 있으나 최신 검토가 없는 보유 종목 {count("missing_review")}개가 있습니다.</p>}{count("evidence_insufficient") > 0 && <p>검토 후 자료가 부족한 보유 종목 {count("evidence_insufficient")}개가 있습니다.</p>}{groupedUncertainties.length ? <ul>{groupedUncertainties.map(([code, reasons]) => <li key={code}>{uncertaintyLabel({ code })}{reasons.length > 1 ? ` · ${reasons.length}개` : ""}{reasons.some((reason) => reason.ticker) ? ` · ${reasons.map((reason) => reason.ticker).filter(Boolean).join(", ")}` : ""}</li>)}</ul> : null}{typeof overdue === "number" && <p>기한 경과 {overdue}건은 저장된 리뷰의 체크포인트 범위에서만 센 값입니다. 전체 미완료 항목이 0건이라는 뜻은 아닙니다.</p>}</section>
      {actions}
      <section className="investment-review-section"><h3>우선 확인할 포지션</h3>{displayPositions.length ? <div className="investment-review-list">{displayPositions.map((row) => { const detail = detailByTicker.get(ticker(row.ticker)); const readiness = readinessFor(row, knownTheses); const dueRows = detail?.dueCheckpoints || []; const overdueRows = dueRows.filter((checkpoint) => isOverdue(checkpoint.dueAt, review?.freshness?.evaluatedAt)); const hasVerdict = !["missing_thesis", "missing_review"].includes(readiness); return <article key={row.ticker}><div className="investment-review-position-head"><h4>{row.ticker} <small>{row.name}</small></h4>{hasVerdict ? <span className="chip verification-chip" data-tone={thesisVerdictDisplay(row.thesisVerdict).tone}><span aria-hidden="true">{thesisVerdictDisplay(row.thesisVerdict).icon}</span> {thesisVerdictDisplay(row.thesisVerdict).label}</span> : <span className="chip verification-chip" data-tone="muted">{readinessLabel(readiness)}</span>}</div><p>준비 상태: {readinessLabel(readiness)}</p>{!detail && <p>저장 리뷰에 상세가 포함되지 않았습니다. 위험 없음으로 해석하지 마세요.</p>}{(detail?.reviewReasons || []).length ? <p>검토 이유: {detail!.reviewReasons!.map(reviewReasonLabel).join(" · ")}</p> : null}{overdueRows.length ? <p>기한 경과: {overdueRows.map((checkpoint) => checkpoint.label || "체크포인트").join(" · ")}</p> : null}{(detail?.counterEvidence || []).length ? <div><strong>반대 근거</strong><ul>{detail!.counterEvidence!.map((item, index) => <li key={`position-counter-${index}`}>{evidenceText(item)}</li>)}</ul></div> : null}{readiness === "missing_thesis" && <a className="btn btn--text investment-review-watchlist-link" href={watchlistRoute(row.ticker)}>워치리스트에서 Thesis 열기</a>}{((dueRows.length > 0 || (detail?.quantitativeRiskSignals || []).length > 0 || (detail?.uncertainties || []).length > 0) && <details className="investment-review-position-details"><summary>세부 확인 항목</summary><div>{dueRows.map((checkpoint, index) => <p key={`checkpoint-${checkpoint.id || index}`}>확인: {checkpoint.label || "체크포인트"}{checkpoint.dueAt ? ` · ${checkpoint.dueAt}` : ""}</p>)}{(detail?.uncertainties || []).map((reason, index) => <p key={`position-uncertainty-${reason.code || index}`}>불확실성: {uncertaintyLabel(reason)}</p>)}{(detail?.quantitativeRiskSignals || []).map((signal, index) => <p key={`signal-${index}`}>현재 비중: {finitePercent(signal.weight)}{signal.baseCurrency ? ` · ${signal.baseCurrency} 환산` : ""}</p>)}</div></details>)}</article>; })}</div> : <p>현재 Portfolio 보유 포지션이 없습니다.</p>}{review?.coverage && <p className="investment-review-coverage">상세 {review.coverage.detailIncludedCount ?? detailRows.length}개 / 저장된 최소 목록 {review.coverage.rosterIncludedCount ?? roster.length}개{typeof review.coverage.totalPositionCount === "number" ? ` / 전체 ${review.coverage.totalPositionCount}개` : ""}{typeof review.coverage.omittedRosterCount === "number" && review.coverage.omittedRosterCount > 0 ? ` · 최소 목록에서 제외 ${review.coverage.omittedRosterCount}개` : ""}{typeof review.coverage.omittedDetailCount === "number" && review.coverage.omittedDetailCount > 0 ? ` · 상세에서 제외 ${review.coverage.omittedDetailCount}개` : ""}</p>}</section>
      <section className="investment-review-section"><h3>공동 위험</h3>{(review?.sharedExposures || []).length ? <ul>{review!.sharedExposures!.map((row) => <li key={`${row.type}:${row.key}`}>{row.label || "공동 노출"}{typeof row.weight === "number" ? ` · 비중 ${finitePercent(row.weight)}` : ""} · {(row.tickers || []).join(", ") || "연결 보유 없음"}</li>)}</ul> : <p>명시적으로 연결된 공동 노출이 없습니다.</p>}{(review?.sharedExposures || []).some((row) => typeof row.weight === "number") && <p>비중은 생성 당시 평가 가능한 보유의 USD 환산 기준입니다. 시세·환율 시각은 알 수 없고 ETF 기초자산 중복은 계산하지 않았습니다.</p>}{(review?.portfolioRisks || []).map((row) => row.riskKey === "portfolio_concentration" ? <p key={row.riskKey}>집중도: 상위 1개 {finitePercent(row.concentration?.top1)} · 상위 3개 {finitePercent(row.concentration?.top3)} · 보유 {typeof row.concentration?.holdings === "number" ? row.concentration.holdings : "확인 필요"}개</p> : row.status === "available" ? <p key={row.riskKey}>저장된 백테스트 · {row.backtestRef?.window || "기간 정보"} · {row.backtestRef?.start || ""} ~ {row.backtestRef?.end || ""}</p> : <p key={row.riskKey}>정량 위험 참고 불가: 추가 확인 필요</p>)}</section>
      <details className="investment-review-details"><summary>연결 자료</summary><div><section className="investment-review-section"><h3>연결 자료</h3>{(review?.inputBasis?.canonicalReports || []).length ? <ul>{review!.inputBasis!.canonicalReports!.map((row) => { const route = safeReportRoute(row); const copy = <>{reportKindLabel(row.kind)}{row.title ? ` · ${row.title}` : ""}{row.asOf ? ` · ${row.asOf} 기준` : ""}{row.relatedReason ? ` · ${row.relatedReason}` : ""}</>; return <li key={`${row.kind}:${row.id}`}>{route ? <a href={route}>{copy}</a> : copy}</li>; })}</ul> : <p>현재 보유와 연결된 자료가 없습니다.</p>}{review?.reportSelection && <p className="investment-review-coverage">후보 {review.reportSelection.candidateCount ?? "확인 필요"}건 중 {review.reportSelection.includedCount ?? "확인 필요"}건을 연결했습니다{typeof review.reportSelection.excludedCount === "number" && review.reportSelection.excludedCount > 0 ? ` · 선별 한계로 제외 ${review.reportSelection.excludedCount}건` : ""}.</p>}</section></div></details>{historySection}
    </>}
  </section>;
}
