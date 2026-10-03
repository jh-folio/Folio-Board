import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, getJson, postJson } from "../../api";
import { pollAgentJobBounded, type PollableAgentJob } from "../agentPolling";
import { CriteriaForm, loadCriteria } from "./CriteriaForm";
import { CashConversionSection, CashTableDetails, NoGrowthSection, ReturnPartsSection, ReturnPartsSummary } from "./Crosschecks";
import { GlanceSection, GuideSection, PartHeader, SECTION_IDS, glanceItems } from "./Guide";
import {
  CriteriaLine, DecompositionSection, HistoryList, MyAssumptionsResult, RequirementSection, ScaleBar, ScenarioCards, ScenarioTable, SourcesDetails,
} from "./PriceParts";
import { attemptBanner, bannerFor, heroText, irrText, money, pct, percentToFraction, fractionToPercent, reasonText, rowFor, toNumber, type Banner } from "./format";
import type { Criteria, Override, Overview, Projection, SnapshotView } from "./types";

const CALCULATION_TIMEOUT_MS = 10 * 60 * 1000;

export function instrumentIdFor(ticker: string, market?: string): string {
  const clean = ticker.trim().toUpperCase();
  return market?.toUpperCase() === "KR" || (!market && /^[0-9][A-Z0-9]{5}$/.test(clean)) ? `KR:${clean}` : `US:${clean}`;
}

type Loaded = { overview: Overview; view: SnapshotView | null; projection: Projection | null; criteria: Criteria | null; override: Override | null };

async function loadAll(instrument: string, signal?: AbortSignal): Promise<Loaded> {
  const overview = await getJson<Overview>(`/api/price-snapshots?instrumentId=${encodeURIComponent(instrument)}`, { signal });
  const criteria = await loadCriteria(signal);
  const override = (await getJson<{ override: Override | null }>(`/api/valuation/assumptions?instrumentId=${encodeURIComponent(instrument)}`, { signal })).override;
  if (!overview.latest) return { overview, view: null, projection: null, criteria, override };
  const id = encodeURIComponent(overview.latest.snapshotId);
  const [view, projection] = await Promise.all([
    getJson<SnapshotView>(`/api/price-snapshots/${id}`, { signal }),
    getJson<Projection>(`/api/price-snapshots/${id}/projection`, { signal }),
  ]);
  return { overview, view, projection, criteria, override };
}

function errorField(error: unknown): string {
  const detail = error instanceof ApiRequestError ? (error.payload as { detail?: { field?: string } } | null)?.detail : null;
  return detail?.field || "";
}

const ASSUMPTION_FIELDS: Record<string, string> = { growth: "이익 성장", exitPE: "끝날 때 PER", payout: "배당성향" };

/** 워치리스트 기업 상세의 `가격` 탭. 계산은 서버가 하고 여기는 읽고 보여 준다. */
export function PriceTab({ ticker, market, active = true, onOpenSettings }: { ticker: string; market?: string; active?: boolean; onOpenSettings?: () => void }) {
  const instrument = instrumentIdFor(ticker, market);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [calculating, setCalculating] = useState(false);
  const [message, setMessage] = useState("");
  const [feedback, setFeedback] = useState("");
  const [horizon, setHorizon] = useState<5 | 10>(10);
  const [selected, setSelected] = useState(1);
  const [decSelected, setDecSelected] = useState<string | null>(null);
  const [previous, setPrevious] = useState<SnapshotView | null>(null);
  const [form, setForm] = useState({ growth: "", exitPE: "", payout: "" });
  const [formError, setFormError] = useState("");
  const [moving, setMoving] = useState(false);
  const criteriaDialog = useRef<HTMLDialogElement | null>(null);
  const previousDialog = useRef<HTMLDialogElement | null>(null);
  const criteriaOrigin = useRef<HTMLElement | null>(null);
  const controller = useRef<AbortController | null>(null);

  const apply = useCallback((next: Loaded, resetHorizon: boolean) => {
    setLoaded(next);
    if (resetHorizon && next.criteria?.holdingYears) setHorizon(next.criteria.holdingYears as 5 | 10);
    setForm({ growth: fractionToPercent(next.override?.growth), exitPE: next.override?.exitPE ?? "", payout: fractionToPercent(next.override?.payout) });
  }, []);

  useEffect(() => {
    if (!active) { controller.current?.abort(); return; }
    const control = new AbortController();
    controller.current?.abort(); controller.current = control;
    setPhase("loading"); setLoaded(null); setMessage(""); setFeedback(""); setCalculating(false); setSelected(1); setDecSelected(null);
    loadAll(instrument, control.signal)
      .then(next => { if (!control.signal.aborted) { apply(next, true); setPhase("ready"); } })
      .catch(() => { if (!control.signal.aborted) setPhase("error"); });
    return () => { control.abort(); controller.current?.abort(); };
  }, [instrument, apply, active]);

  async function reload(resetHorizon = false, signal = controller.current?.signal) {
    try { const next = await loadAll(instrument, signal); if (!signal?.aborted) { apply(next, resetHorizon); setPhase("ready"); } }
    catch { if (!signal?.aborted) setPhase("error"); }
  }

  async function calculate() {
    const control = new AbortController();
    controller.current = control;
    setCalculating(true); setFeedback(""); setMessage("공시 실적, 분할 내역, 종가를 확인하고 있습니다. 보통 수십 초 걸립니다.");
    try {
      const job = await postJson<PollableAgentJob>("/api/price-snapshots/calculate", { instrumentId: instrument }, { signal: control.signal });
      await pollAgentJobBounded(job, { signal: control.signal, timeoutMs: CALCULATION_TIMEOUT_MS, onUpdate: current => current.message && setMessage(current.message) });
      if (control.signal.aborted) return;
      await reload(false, control.signal);
    } catch (error) {
      if (control.signal.aborted) return;
      await reload(false, control.signal);
      if (control.signal.aborted) return;
      setFeedback(error instanceof Error && error.name === "AgentPollTimeout" ? "계산이 아직 진행 중입니다. 잠시 뒤 다시 열어 확인해 주세요." : "");
    } finally { if (!control.signal.aborted) { setCalculating(false); setMessage(""); } }
  }

  function openCriteria(origin: HTMLElement | null) {
    criteriaOrigin.current = origin;
    criteriaDialog.current?.showModal();
  }
  function closeCriteria() { criteriaDialog.current?.close(); criteriaOrigin.current?.focus(); }

  async function openPrevious(id: string) {
    try { setPrevious(await getJson<SnapshotView>(`/api/price-snapshots/${encodeURIComponent(id)}`)); previousDialog.current?.showModal(); }
    catch { setFeedback("이전 계산을 읽지 못했습니다."); }
  }

  async function saveAssumptions(event: FormEvent<HTMLFormElement>, basis?: SnapshotView | null) {
    event.preventDefault();
    const view = basis ?? loaded?.view;
    if (!view || !event.currentTarget.reportValidity()) return;
    setFormError(""); setFeedback("");
    try {
      await postJson("/api/valuation/assumptions", {
        instrumentId: instrument, basedOnSnapshotId: view.snapshotId,
        growth: form.growth.trim() ? percentToFraction(form.growth) : null, exitPE: form.exitPE.trim() || null,
        payout: form.payout.trim() ? percentToFraction(form.payout) : null, expectedOverrideId: loaded?.override?.overrideId ?? null,
      });
      await reload(false); setFeedback("내 가정을 저장했습니다."); setMoving(false);
    } catch (error) {
      const field = errorField(error);
      const code = error instanceof ApiRequestError ? error.code : "";
      setFormError(code === "revision_conflict" ? "다른 화면에서 내 가정이 바뀌었습니다. 새로 불러온 값을 확인하고 다시 저장해 주세요."
        : field ? `값을 확인해 주세요: ${ASSUMPTION_FIELDS[field] || field}` : "저장하지 못했습니다. 입력한 값은 그대로 남겨 두었습니다.");
      if (code === "revision_conflict") await reload(false);
    }
  }

  if (phase === "loading") return <p className="price-meta" role="status">가격 계산 기록을 불러오는 중입니다…</p>;
  if (phase === "error" || !loaded) {
    return <div className="surface surface--group price-banner" role="alert"><strong>가격 계산 기록을 읽지 못했습니다.</strong>
      <p className="price-meta">잠시 뒤 다시 시도해 주세요. 이전 기록은 지워지지 않았습니다.</p>
      <div><button className="btn btn--sm" type="button" onClick={() => void reload(true)}>다시 읽기</button></div></div>;
  }

  const { overview, view, projection, criteria, override } = loaded;
  const rows = view?.results.scenarios ?? [];
  const supported = view?.results.support.status === "supported";
  const currency = view?.inputSummary.price.currency ?? "";
  const baseRow = rowFor(rows, "base", horizon);
  const holding = criteria?.holdingYears ?? null;
  const baseHolding = holding ? rowFor(rows, "base", holding) : undefined;
  const requiredText = criteria?.requiredReturn ?? null;
  const goal = requiredText !== null && toNumber(requiredText) !== null ? Number(requiredText) : null;
  const hero = heroText({ horizon, base: baseRow, required: requiredText, holdingYears: holding, baseHolding });
  const banner: Banner = bannerFor({ projection, view, saveFailed: false }) || attemptBanner(overview.lastAttempt, overview.latest?.asOf ?? null);
  const marginNote = view && criteria?.minMarginOfSafety !== null && criteria?.minMarginOfSafety !== undefined && projection?.verdict.marginOfSafety.state === "unknown"
    ? `안전마진 판정 보류: ${reasonText(projection.verdict.marginOfSafety.reason)}. 수익률 비교도 계산상 비교일 뿐 투자 판단을 대신하지 않습니다.` : "";
  const noResult = !view;
  const showTitle2 = !calculating && !noResult && supported && Boolean(hero.title2);
  const heroTitle = calculating ? "계산하고 있습니다…" : noResult ? "아직 이 종목의 가격을 계산하지 않았습니다." : !supported
    ? "이 종목은 지금 계산하지 않았습니다." : hero.title;
  const heroSub = calculating ? message : noResult ? "가장 최근 거래일 종가와 공시 실적으로 계산합니다. 내 관심 이유를 쓰지 않아도 됩니다."
    : !supported ? `${reasonText(view?.results.support.reasons[0]?.code)}. 틀린 숫자를 보여 드리지 않으려고 계산을 멈췄습니다.` : hero.sub;

  return (
    <div className="price-stack" data-price-tab>
      <section className="surface surface--group price-hero" aria-labelledby="price-hero-title">
        {view && !calculating && (
          <div className="price-row price-row--between">
            <p className="price-meta">종가 <strong>{money(view.inputSummary.price.value, currency)}</strong> · {view.inputSummary.price.sessionDate} 기준</p>
            {supported && (
              <div className="price-horizon"><span id="price-horizon-label">보유 기간</span>
                <div className="segment" role="group" aria-labelledby="price-horizon-label">
                  {([5, 10] as const).map(years => <button key={years} type="button" aria-pressed={horizon === years} onClick={() => setHorizon(years)}>{years}년</button>)}
                </div>
              </div>
            )}
          </div>
        )}
        <div className="price-hero__head">
          <h3 className="price-hero__title" id="price-hero-title">{heroTitle}{showTitle2 && <span className="price-hero__title2">{hero.title2}</span>}</h3>
          <p className="price-note" role={calculating ? "status" : undefined}>{heroSub}</p>
        </div>
        {view && supported && !calculating && (
          <>
            <div className="price-hchart">
              <p className="price-note">{horizon}년 보유 시 연 수익률 <span className="price-meta">· 카드를 누르면 막대에서 위치를 보여 줍니다</span></p>
              <ScenarioCards rows={rows} horizon={horizon} selected={selected} required={requiredText} onSelect={index => setSelected(current => (current === index && index !== 1 ? 1 : index))} />
              <ScaleBar rows={rows} horizon={horizon} selected={selected} goal={goal} />
            </div>
            <CriteriaLine projection={projection} criteria={criteria} onEdit={() => openCriteria(document.activeElement as HTMLElement | null)} />
            {marginNote && <p className="price-meta">{marginNote}</p>}
          </>
        )}
        <div className="price-row">
          <button className="btn btn--primary" type="button" disabled={calculating} onClick={() => void calculate()}>{calculating ? "계산 중" : noResult ? "계산하기" : "다시 계산"}</button>
          {view && !calculating && <span className="price-meta">계산 시각 {view.computedAt.replace("T", " ").replace("Z", "").slice(0, 16)}</span>}
        </div>
      </section>

      {banner && <div className="surface surface--group price-banner" role="status"><strong>{banner.title}</strong><p className="price-meta">{banner.detail}</p></div>}

      {view && supported && (
        <>
          <GlanceSection items={glanceItems({ view, projection, criteria, horizon })} />

          <PartHeader number={1} title="얼마를 벌 수 있나" sub="수익률이 어디서 나오고, 가정에 따라 얼마나 달라지는지" />
          <ReturnPartsSection view={view} horizon={horizon} selected={selected} />
          <GuideSection id="price-scenario-title" title="가정별 수익률" meta="이 회사의 과거 10년 기록에서 가져온 가정"
            question="가정을 과거 10년 기록의 낮은 편·보통·높은 편으로 바꾸면 수익률이 얼마나 달라지는지 봅니다."
            calc={`지금 가격 ${money(view.inputSummary.price.value, currency)}에 사서, 주당이익 ${view.results.base.status === "available" ? money(view.results.base.eps0, currency) : "—"}이 매년 ‘이익 성장’만큼 늘고, 이익의 ‘배당성향’만큼 배당을 받고, 끝에 이익의 ‘끝날 때 PER’배 가격에 판다고 본 연 수익률입니다.`}
            read="보수와 낙관의 차이가 클수록 결과가 가정에 크게 기댑니다. 끝날 때 PER은 보유를 끝내는 시점에 주가가 1년 이익의 몇 배일지이며, 일어날 가능성은 계산하지 않습니다.">
            <ScenarioTable rows={rows} horizon={horizon} />
          </GuideSection>

          <PartHeader number={2} title="지금 가격이 무엇을 가정하나" sub="지금 가격이 맞으려면 필요한 조건과, 가격 중 성장에 거는 몫" />
          <GuideSection id={SECTION_IDS.reverse} title="지금 가격이 전제하는 것" meta={`${horizon}년 보유 기준`}
            question="결과를 거꾸로 돌려, 지금 가격이 맞으려면 무엇이 필요한지 봅니다." hint="줄을 누르면 계산 방법이 펼쳐집니다"
            calc={`다른 가정은 기본값으로 두고, 연 수익률이 0%(손익분기)${requiredText !== null ? " 또는 내 기준" : ""}이 되는 값을 거꾸로 찾았습니다. 시장이 실제로 이렇게 기대한다는 뜻은 아니며, 달성 가능성을 판정하지 않습니다.`}
            read="필요한 값이 과거 10년 범위보다 낮으면 지금 가격이 요구하는 조건이 과거 기록보다 낮다는 뜻이고, 높으면 과거보다 높은 조건을 요구한다는 뜻입니다.">
            <RequirementSection view={view} projection={projection} horizon={horizon} onSetCriteria={() => openCriteria(document.activeElement as HTMLElement | null)} />
          </GuideSection>
          <NoGrowthSection view={view} projection={projection} onSetCriteria={() => openCriteria(document.activeElement as HTMLElement | null)} />

          <PartHeader number={3} title="과거 기록은 어땠나" sub="이익이 무엇으로 늘었고, 현금으로 얼마나 남았는지" />
          <GuideSection id="price-decomp-title" title="지난 5년 이익 성장은 어디서 왔나"
            meta={view.results.decomposition.status === "available" ? `FY${view.results.decomposition.recentWindow[0]} → FY${view.results.decomposition.recentWindow[1]}` : undefined}
            question="지난 5년 주당이익 성장이 무엇에서 왔는지 나눠 봅니다."
            calc="주당이익 = 매출 × 이익률 ÷ 주식 수이므로, 5년 동안의 변화를 매출·이익률·주식 수 세 가지로 나눴습니다. 위의 가정과는 따로 계산합니다."
            read="이익률 개선이나 주식 수 감소가 큰 몫이면, 같은 속도의 성장이 계속되기 어려울 수 있습니다.">
            <DecompositionSection view={view} selected={decSelected} onSelect={setDecSelected} />
          </GuideSection>
          <CashConversionSection block={view.results.cashConversion} tableInside={false} />

          <div className="price-folds">
          <CashTableDetails block={view.results.cashConversion} />
          <details className="price-details" open={Boolean(override || projection?.myAssumptions)}>
            <summary>내 가정으로 계산해 보기 <span className="chip" data-tone="purple">개인 가정</span></summary>
            {projection?.myAssumptions && !projection.myAssumptions.basedOnCurrentSnapshot && (
              <div className="surface surface--group price-banner">
                <strong>내 가정은 이전 계산을 바탕으로 합니다.</strong>
                <p className="price-meta">새 계산이 생겨도 내 가정은 자동으로 옮기지 않습니다. 옮기기 전에 값을 확인해 주세요.</p>
                {moving ? (
                  <form onSubmit={event => void saveAssumptions(event)}>
                    <p className="price-meta">{view.asOf} 계산으로 옮기면 값은 그대로 두고 기반만 바뀝니다: 이익 성장 {form.growth || "기본"}% · PER {form.exitPE || "기본"}배 · 배당성향 {form.payout || "기본"}%</p>
                    <div className="price-row"><button className="btn btn--text" type="button" onClick={() => setMoving(false)}>취소</button><button className="btn" type="submit">옮기기 확인</button></div>
                  </form>
                ) : <div><button className="btn btn--sm" type="button" onClick={() => setMoving(true)}>{view.asOf} 계산으로 옮기기</button></div>}
              </div>
            )}
            <p className="price-note">비워 둔 칸은 기본 가정을 씁니다. 위의 결과와 내 기준 비교는 바뀌지 않습니다.</p>
            <form onSubmit={event => void saveAssumptions(event)}>
              <div className="price-form">
                <label>이익 성장 (연 %)<input type="number" step="any" min={-99.999} placeholder={`기본 ${pct(baseRow && baseRow.status === "available" ? baseRow.g : null)}`} value={form.growth} onChange={e => setForm({ ...form, growth: e.target.value })} /></label>
                <label>끝날 때 PER (배)<input type="number" step="any" min={0} placeholder={`기본 ${baseRow && baseRow.status === "available" ? Number(baseRow.exitPE).toFixed(1) : "—"}`} value={form.exitPE} onChange={e => setForm({ ...form, exitPE: e.target.value })} /></label>
                <label>배당성향 (%)<input type="number" step="any" min={0} max={100} placeholder={`기본 ${pct(baseRow && baseRow.status === "available" ? baseRow.payout : null, 0)}`} value={form.payout} onChange={e => setForm({ ...form, payout: e.target.value })} /></label>
              </div>
              <MyAssumptionsResult mine={projection?.myAssumptions ?? null} base={baseRow} horizon={horizon} />
              <p className="price-meta" role="status" aria-live="polite">{formError}</p>
              <div className="price-row"><button className="btn" type="submit">이 가정 저장</button>
                <button className="btn btn--text" type="button" onClick={() => setForm({ growth: "", exitPE: "", payout: "" })}>기본 가정으로</button></div>
            </form>
          </details>

          <details className="price-details"><summary>숫자의 근거와 출처</summary><SourcesDetails view={view} /></details>
          </div>
        </>
      )}

      {view && !supported && view.results.support.status !== "unsupported" && !calculating && <CashConversionSection block={view.results.cashConversion} />}

      {overview.history.length > 0 && !calculating && (
        <section className="price-section" aria-labelledby="price-history-title">
          <div className="watchlist-detail-section__head"><h3 id="price-history-title">계산 기록</h3><span className="price-meta">이전 계산은 지우지 않고 남깁니다</span></div>
          <HistoryList history={overview.history} currentId={overview.latest?.snapshotId ?? null} onOpen={id => void openPrevious(id)} />
        </section>
      )}
      <p className="price-meta" role="status" aria-live="polite">{feedback}</p>

      <dialog ref={criteriaDialog} className="surface price-dialog" aria-labelledby="price-criteria-title">
        <h2 id="price-criteria-title">투자 기준</h2>
        <p className="price-meta">설정 → 관리 → 투자 기준에서도 바꿀 수 있습니다.{onOpenSettings && <> <button className="btn btn--text btn--sm" type="button" onClick={onOpenSettings}>설정 열기</button></>}</p>
        <CriteriaForm idPrefix="price-dialog" initial={criteria} onCancel={closeCriteria} onSaved={() => { closeCriteria(); void reload(true); }} />
      </dialog>

      <dialog ref={previousDialog} className="surface price-dialog" aria-labelledby="price-previous-title">
        {previous && <PreviousBody view={previous} />}
        <div className="price-row"><button className="btn" type="button" onClick={() => previousDialog.current?.close()}>닫기</button></div>
      </dialog>
    </div>
  );
}

function PreviousBody({ view }: { view: SnapshotView }) {
  const rows = view.results.scenarios;
  const five = rowFor(rows, "base", 5);
  const ten = rowFor(rows, "base", 10);
  const base = ten && ten.status === "available" ? ten : five && five.status === "available" ? five : null;
  return (
    <>
      <h2 id="price-previous-title">{view.asOf} 계산</h2>
      <ReturnPartsSummary view={view} horizon={10} />
      <CashConversionSection block={view.results.cashConversion} id="price-previous-cash" />
      <p>당시 종가 {money(view.inputSummary.price.value, view.inputSummary.price.currency)} · 기본 가정 5년 {irrText(five)}, 10년 {irrText(ten)}</p>
      <p className="price-meta">{base ? `당시 이익 성장 ${pct(base.g)} · 끝날 때 PER ${Number(base.exitPE).toFixed(1)}배 · 배당성향 ${pct(base.payout, 0)}. ` : ""}지난 계산을 읽기만 하는 화면입니다. 현재 기준과 내 가정은 바뀌지 않습니다.</p>
    </>
  );
}
