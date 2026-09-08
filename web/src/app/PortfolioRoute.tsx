import { useEffect, useRef, useState } from "react";
import { ApiRequestError, getJson, postJson } from "../api";
import { setReactAgentContextScope } from "./agentContext";
import { RouteHero } from "./RouteHero";
import { HoldingsTable, SavedHoldingsTable, type PositionDraft, type PositionFieldError } from "./portfolio/HoldingsTable";
import { TossHoldingsImport } from "./portfolio/TossHoldingsImport";
import { ConsultationEntry } from "./portfolio/ConsultationEntry";
import { PortfolioAnalysis } from "./portfolio/PortfolioAnalysis";
import { PortfolioBacktest } from "./portfolio/PortfolioBacktest";
import { PortfolioTargets } from "./portfolio/PortfolioTargets";
import { InvestmentReviewWorkspace, reviewAttentionLabel, type InvestmentReview } from "./portfolio/InvestmentReviewWorkspace";
import type { PositionRow } from "./portfolio/portfolioTypes";

type Portfolio = { revision: number; positions: PositionDraft[]; cash?: Array<{ currency: string; amount: number }>; updatedAt?: string };
type Tab = "holdings" | "review" | "targets" | "backtest";
type HoldingsConflict = { readonly active: boolean };

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: "holdings", label: "보유·평가" },
  { id: "review", label: "투자 리뷰" },
  { id: "targets", label: "프리셋" },
  { id: "backtest", label: "백테스트" },
];

let nextDraftId = 0;
function draftRows(rows: readonly PositionDraft[]): PositionDraft[] {
  return rows.map((row) => ({ ...row, _draftId: `holding-${++nextDraftId}` }));
}
function storedRows(rows: readonly PositionDraft[]): PositionDraft[] {
  return rows.map(({ _draftId: _ignored, ...row }) => row);
}
function sameRows(left: readonly PositionDraft[], right: readonly PositionDraft[]): boolean {
  return JSON.stringify(storedRows(left)) === JSON.stringify(storedRows(right));
}
function fallbackRows(rows: readonly PositionDraft[]): PositionRow[] {
  return rows.map((row) => ({ ...row, quantity: typeof row.quantity === "string" ? row.quantity : String(row.quantity), averagePrice: row.averagePrice === undefined ? undefined : String(row.averagePrice), currentPrice: null, marketValueUsd: null, pnlUsd: null, pnlPct: null, weight: null }));
}

/** 보유는 저장된 상태를 먼저 읽고, 편집은 명시적으로 연 draft에서만 한다. */
export function PortfolioRoute() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<PositionDraft[]>([]);
  const [editing, setEditing] = useState(false);
  const [tab, setTab] = useState<Tab>("holdings");
  const [saving, setSaving] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<readonly PositionFieldError[]>([]);
  const [holdingsConflict, setHoldingsConflict] = useState<HoldingsConflict | null>(null);
  const [resolverEpoch, setResolverEpoch] = useState(0);
  const [reviewAttention, setReviewAttention] = useState("");
  const [presetDirty, setPresetDirty] = useState(false);
  const authorityRequest = useRef(0);
  const reviewRequest = useRef(0);

  const mutationBusy = saving || importBusy || reloading;
  const holdingsDirty = editing && !sameRows(positions, portfolio?.positions || []);

  function invalidateResolvers() { setResolverEpoch((current) => current + 1); }

  async function loadAuthority() {
    const requestId = ++authorityRequest.current;
    const payload = await getJson<Portfolio>("/api/portfolio");
    if (requestId !== authorityRequest.current) return;
    setPortfolio(payload);
    setError("");
  }

  async function refreshReviewAttention() {
    const requestId = ++reviewRequest.current;
    try {
      const review = await getJson<InvestmentReview>("/api/investment-review");
      if (requestId === reviewRequest.current) setReviewAttention(reviewAttentionLabel(review));
    } catch {
      if (requestId === reviewRequest.current) setReviewAttention("확인 필요");
    }
  }

  useEffect(() => {
    void loadAuthority().catch((reason) => setError(reason instanceof Error ? reason.message : "Portfolio를 불러오지 못했습니다."));
    void refreshReviewAttention();
    setReactAgentContextScope("portfolio", { surface: "portfolio", viewId: "portfolio", reportKind: "portfolio", reportId: "current" });
  }, []);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (holdingsDirty || presetDirty) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [holdingsDirty, presetDirty]);

  function beginEdit() {
    if (!portfolio || mutationBusy) return;
    invalidateResolvers(); setPositions(draftRows(portfolio.positions || [])); setEditing(true); setFieldErrors([]); setHoldingsConflict(null); setError(""); setStatus("");
  }
  function discardEdit(confirmDirty = true): boolean {
    if (mutationBusy) return false;
    if (confirmDirty && holdingsDirty && !window.confirm("저장하지 않은 보유 변경이 있습니다. 편집을 취소할까요?")) return false;
    invalidateResolvers(); setPositions([]); setEditing(false); setFieldErrors([]); setHoldingsConflict(null); setError(""); return true;
  }

  async function save() {
    if (!portfolio || mutationBusy || holdingsConflict) return;
    const mutationId = ++authorityRequest.current;
    invalidateResolvers();
    setSaving(true); setError(""); setStatus("");
    try {
      const payload = await postJson<Portfolio>("/api/portfolio", { expectedRevision: portfolio.revision, positions: storedRows(positions), cash: portfolio.cash || [] });
      // This mutation owns authority until it completes. Earlier reads cannot replace it.
      if (mutationId === authorityRequest.current) setPortfolio(payload);
      invalidateResolvers(); setPositions([]); setEditing(false); setFieldErrors([]); setHoldingsConflict(null); setStatus("보유 변경을 저장했습니다.");
      void refreshReviewAttention();
    } catch (reason) {
      const detail = reason instanceof ApiRequestError && reason.payload && typeof reason.payload.detail === "object" && reason.payload.detail !== null ? reason.payload.detail as Record<string, unknown> : null;
      if (reason instanceof ApiRequestError && reason.status === 422 && reason.code === "portfolio_validation_failed" && Array.isArray(detail?.errors)) {
        const next = detail.errors.filter((item): item is PositionFieldError => Boolean(item) && typeof item === "object" && typeof (item as PositionFieldError).row === "number" && typeof (item as PositionFieldError).field === "string" && typeof (item as PositionFieldError).code === "string");
        setFieldErrors(next); setError("입력 오류가 있어 전체 변경을 저장하지 않았습니다.");
      } else if (reason instanceof ApiRequestError && reason.status === 409) {
        // Draft와 기존 authority를 모두 보존한다. 최신 revision을 몰래 받아 재저장하지 않는다.
        setHoldingsConflict({ active: true }); setError("다른 화면에서 보유 내역이 먼저 바뀌었습니다. 현재 편집 내용은 보존했습니다.");
      } else setError(reason instanceof Error ? reason.message : "Portfolio 저장에 실패했습니다.");
    } finally { setSaving(false); }
  }

  async function reloadLatest() {
    if (mutationBusy || !holdingsConflict || !window.confirm("현재 편집 내용을 버리고 최신 저장본을 불러올까요?")) return;
    setReloading(true);
    try {
      invalidateResolvers(); await loadAuthority(); setPositions([]); setEditing(false); setHoldingsConflict(null); setFieldErrors([]); setError(""); setStatus("최신 저장본을 불러왔습니다.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "최신 보유 내역을 불러오지 못했습니다."); }
    finally { setReloading(false); }
  }

  function commitImport(payload: Portfolio) {
    ++authorityRequest.current;
    invalidateResolvers(); setPortfolio(payload); setPositions([]); setEditing(false); setFieldErrors([]); setHoldingsConflict(null); setStatus("보유 내역을 반영했습니다."); void refreshReviewAttention();
  }

  function selectTab(next: Tab) {
    if (next === tab || mutationBusy) return;
    if (tab === "holdings" && holdingsDirty && !discardEdit(true)) return;
    if (tab === "targets" && presetDirty && !window.confirm("저장하지 않은 프리셋 변경이 있습니다. 탭을 이동하면 변경이 사라집니다. 계속할까요?")) return;
    if (tab === "targets") setPresetDirty(false);
    setTab(next);
  }

  const savedPositions = portfolio?.positions || [];
  return <main className="portfolio-route">
    <RouteHero eyebrow="Portfolio" title="보유 종목과 리서치 연결" description="저장한 보유 현황에서 시작해 평가·집중도와 투자 리뷰를 함께 확인합니다." />

    <div className="segment portfolio-tabs" role="group" aria-label="포트폴리오 보기">
      {TABS.map((item) => <button type="button" key={item.id} aria-pressed={tab === item.id} disabled={mutationBusy} onClick={() => selectTab(item.id)}>{item.label}{item.id === "review" && reviewAttention ? ` · ${reviewAttention}` : ""}</button>)}
    </div>

    {tab === "holdings" && <div className="portfolio-route-grid">
      <section className="cockpit-panel portfolio-holdings" aria-labelledby="portfolio-holdings-title">
        <div className="cockpit-panel__head"><div><span>HOLDINGS</span><h2 id="portfolio-holdings-title">현재 보유 종목</h2></div><span className="chip status-chip" data-tone="muted">{!portfolio ? (error ? "불러오기 실패" : "불러오는 중") : editing ? "편집 중" : "저장됨"}</span></div>
        {!portfolio ? <div className="portfolio-empty" role={error ? "alert" : "status"}><p>{error || "저장된 보유 내역을 불러오는 중입니다."}</p>{error && <button className="btn" type="button" onClick={() => void loadAuthority().catch((reason) => setError(reason instanceof Error ? reason.message : "Portfolio를 불러오지 못했습니다."))}>다시 시도</button>}</div> : editing ? <>
          <p className="portfolio-note">저장하기 전 변경은 마지막으로 저장한 보유 내역과 분리해 둡니다.</p>
          <div className="portfolio-actions"><button className="btn" type="button" disabled={mutationBusy} onClick={() => setPositions((current) => [...current, { ticker: "", quantity: "", averagePrice: "", _draftId: `holding-${++nextDraftId}` }])}>종목 추가</button><button className="btn btn--text" type="button" disabled={mutationBusy} onClick={() => discardEdit(true)}>편집 취소</button><button className="btn btn--primary" type="button" disabled={mutationBusy || Boolean(holdingsConflict)} onClick={() => void save()}>{saving ? "저장 중" : "Portfolio 저장"}</button></div>
          <HoldingsTable positions={positions} errors={fieldErrors} disabled={mutationBusy} resolverEpoch={resolverEpoch} onResolverInvalidated={invalidateResolvers} onChange={(next) => { if (!mutationBusy) { setFieldErrors([]); setPositions(next); } }} />
          <p className="portfolio-note">이 탭 안 이동은 확인하지만, 앱의 다른 메뉴 이동은 자동으로 막지 못합니다. 저장 또는 편집 취소 후 이동하세요.</p>
          {holdingsConflict && <div className="portfolio-holdings-conflict" role="alert"><p>현재 편집 내용은 그대로입니다. 최신 저장본을 확인하거나 편집을 취소한 뒤 다시 진행하세요.</p><div><button className="btn" type="button" disabled={mutationBusy} onClick={() => void reloadLatest()}>최신 저장본 불러오기</button><button className="btn btn--text" type="button" disabled={mutationBusy} onClick={() => discardEdit(false)}>편집 취소</button></div></div>}
        </> : <>
          <div className="portfolio-actions"><button className="btn" type="button" disabled={mutationBusy} onClick={beginEdit}>보유 편집</button></div>
          <PortfolioAnalysis revision={portfolio.revision}>{(analytics) => <section className="portfolio-block portfolio-saved-holdings"><h3>저장된 보유 종목</h3><SavedHoldingsTable positions={analytics?.positions || fallbackRows(savedPositions)} baseCurrency={analytics?.baseCurrency || "USD"} /></section>}</PortfolioAnalysis>
          <TossHoldingsImport portfolio={portfolio} dirty={false} externalBusy={saving || reloading} onBusyChange={setImportBusy} onCommitted={commitImport} />
        </>}
        {status && <p className="react-reader-status" role="status">{status}</p>}
        {error && portfolio && <p className="react-dashboard-error" role="alert">{error}</p>}
      </section>
      <aside className="cockpit-panel portfolio-research" aria-labelledby="portfolio-research-title"><div className="cockpit-panel__head"><div><span>RESEARCH</span><h2 id="portfolio-research-title">Agent와 검토</h2></div></div><p>마지막으로 저장한 보유 종목을 기준으로 최근 변화와 반대 근거를 함께 살펴봅니다.</p><ConsultationEntry tickers={savedPositions.map((row) => row.ticker).filter(Boolean)} /><small>대화 내용은 보고서 근거로 사용되지 않습니다.</small></aside>
    </div>}

    {tab === "review" && <InvestmentReviewWorkspace hasSavedHoldings={savedPositions.length > 0} onGenerated={() => { void refreshReviewAttention(); }} onNavigateHoldings={() => selectTab("holdings")} />}
    {tab === "targets" && <section className="cockpit-panel" aria-labelledby="portfolio-targets-title"><div className="cockpit-panel__head"><div><span>PRESETS</span><h2 id="portfolio-targets-title">프리셋</h2></div></div><PortfolioTargets revision={portfolio?.revision ?? 0} onDirtyChange={setPresetDirty} /></section>}
    {tab === "backtest" && <section className="cockpit-panel" aria-labelledby="portfolio-backtest-title"><div className="cockpit-panel__head"><div><span>BACKTEST</span><h2 id="portfolio-backtest-title">백테스트</h2></div></div><PortfolioBacktest revision={portfolio?.revision ?? 0} onOpenPresets={() => selectTab("targets")} /></section>}
  </main>;
}
