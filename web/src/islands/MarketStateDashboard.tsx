import { useCallback, useEffect, useState, type ReactNode } from "react";
import { getJson } from "../api";
import { openReactAgentDock } from "../app/agentContext";
import { legacyBridge as bridge } from "../app/legacyBridge";
import { useMarketScope } from "../app/useMarketScope";
import { marketStateContextProjection, readMarketStateRef, type MarketStateRef, type MarketStateStatus } from "../app/marketStateContext";

export { marketStateContextProjection } from "../app/marketStateContext";

// Mirrors features/market_memory/state_dashboard.py::summarize_market_state.
interface Driver {
  id: string;
  title: string;
  status: string;
  momentum: string;
  momentumLabel: string;
  directionLabel?: string;
  directionTone?: string;
  confidence: string;
  confidencePct: number;
  interpretation: string;
  marketImpact?: string;
  rationale: string;
  whyItMatters?: string;
  evidenceSummary?: string;
  elaboration: string;
  evidenceCounts: { d7: number; d30: number; d90: number };
  linkedCompanies: string[];
  nextCheckpoint: string;
  whatToWatch?: string;
  nextMemoryCheck?: string;
  askAgentPrompt: string;
}

interface BriefItem {
  label: string;
  value: string;
}

interface Posture {
  label: string;
  tone: string;
  summary: string;
}

interface ActionGuide {
  headline: string;
  action: string;
  timing: string;
}

export interface DashboardPayload {
  title: string;
  summary: string;
  plainConclusion?: string;
  reasonSummary?: string;
  sourceSummary?: string;
  source?: string;
  stance?: string;
  posture?: Posture;
  actionGuide?: ActionGuide;
  briefs?: BriefItem[];
  watchItems?: string[];
  drivers: Driver[];
  counterEvidence?: CheckItem[];
  uncertainties?: CheckItem[];
  sourceRefs?: Array<{ id?: string; title?: string; source?: string; date?: string; url?: string }>;
  snapshot?: { asOf?: string; status?: string; confidence?: number; marketRegime?: string };
  freshness?: { snapshotAsOf?: string; latestMemoryAt?: string; latestMemoryTitle?: string; stale?: boolean };
  marketViews?: Partial<Record<MarketScope, DashboardPayload>>;
  marketStateRef?: MarketStateRef;
}

const CONFIDENCE_LABELS: Record<string, string> = { high: "높음", medium: "보통", low: "낮음" };
type MarketScope = "overall" | "us" | "kr" | "europe" | "jp";
/* 백엔드는 us/kr/europe/jp 네 시장의 view를 만들어 저장하는데 화면이 us/kr만
   알고 있어서, 유럽·일본 내러티브는 생성되어도 열 방법이 없었다.
   라벨은 브리핑 시장 선택과 같은 US/KR/EU/JP를 쓴다. */
const MARKET_SCOPE_ORDER: MarketScope[] = ["overall", "us", "kr", "europe", "jp"];
const MARKET_SCOPE_LABELS: Record<MarketScope, string> = { overall: "종합", us: "US", kr: "KR", europe: "EU", jp: "JP" };
type CheckItem = string | { title?: string; summary?: string; sourceRefs?: string[] };

/** 문장 단위로 가른다. 소수점은 문장 끝이 아니다.
 *
 * `[^.!?。]+`로 자르면 "S&P 500이 7736.52로 1일 +1.79%"가 세 조각이 된다.
 * 문장 끝 마침표는 뒤에 공백이나 문자열 끝이 오지만 소수점은 숫자가 온다.
 */
export function splitSentences(text: string): string[] {
  const out: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch !== "." && ch !== "!" && ch !== "?" && ch !== "。") continue;
    const next = text[i + 1];
    if (ch !== "。") {
      if (next && !/\s/.test(next)) continue;
      // 1.79처럼 숫자 사이에 낀 점은 소수점이다.
      if (/\d/.test(text[i - 1] || "") && /\d/.test(next || "")) continue;
    }
    out.push(text.slice(start, i + 1).trim());
    start = i + 1;
  }
  const tail = text.slice(start).trim();
  if (tail) out.push(tail);
  return out.filter(Boolean);
}

/** 시장 해석을 첫 문장(강조)과 나머지 본문으로 가른다.
 *
 * 나머지는 전부 남긴다. 예전에는 `slice(1, 3)`으로 4번째 문장부터 버렸는데,
 * 그때까지 저장된 해석이 모두 1~2문장이라 아무도 손실을 보지 못했다. 모델이
 * 더 긴 문단을 쓰기 시작하자 뒷문장이 통째로 사라졌다.
 */
export function splitNarrative(value: string) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  const parts = splitSentences(normalized);
  return {
    lead: parts[0] || normalized,
    support: parts.slice(1).join(" "),
  };
}

function displaySnapshotTime(value?: string) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });
}

function signalTone(driver: Driver) {
  const direction = String(driver.directionLabel || "").trim();
  if (direction === "중립") return "neutral";
  if (direction === "혼재" || direction === "변동성") return "warning";
  if (direction === "도움" || direction === "부담 완화") return "positive";
  if (direction === "부담") return "negative";
  const label = `${driver.directionLabel || ""} ${driver.directionTone || ""}`.toLowerCase();
  if (/neutral|중립/.test(label)) return "neutral";
  if (/mixed|conflicted|혼재|변동성/.test(label)) return "warning";
  if (/support|positive|완화|호재|긍정|지지|강화|도움/.test(label)) return "positive";
  if (/risk|negative|부담|악화|위험|하방/.test(label)) return "negative";
  return "neutral";
}

function signalLabel(driver: Driver) {
  const label = String(driver.directionLabel || "").trim();
  if (!label || label === "도움") return "긍정 요인";
  if (label === "부담") return "부담 가중";
  if (label === "변동성") return "변동성 증가";
  return label;
}

function normalizeCheckItem(item: CheckItem) {
  const humanize = (value: string) => String(value || "")
    .replace(/marketTape와 macroSnapshot가 비어 있어 가격 검증이 약하다\.?/g, "가격·거시 데이터가 아직 충분하지 않아 뉴스 흐름을 숫자로 검증하기 어렵습니다.")
    .replace(/marketTape/g, "가격 데이터")
    .replace(/macroSnapshot/g, "거시 데이터")
    .trim();
  if (typeof item !== "string") {
    return {
      title: humanize(item.title || ""),
      summary: humanize(item.summary || ""),
      sourceRefs: item.sourceRefs || [],
    };
  }
  const raw = humanize(item.trim());
  const title = raw.match(/['"]title['"]:\s*['"]([^'"]+)['"]/)?.[1] || "";
  const summary = raw.match(/['"]summary['"]:\s*['"]([^'"]+)['"]/)?.[1] || "";
  const sourceRefsRaw = raw.match(/['"]sourceRefs['"]:\s*\[([^\]]*)\]/)?.[1] || "";
  const sourceRefs = sourceRefsRaw
    .split(",")
    .map((ref) => ref.replace(/['"]/g, "").trim())
    .filter(Boolean);
  return title || summary ? { title, summary, sourceRefs } : { title: "", summary: raw, sourceRefs: [] };
}

function CheckList({ items }: { items: CheckItem[] }) {
  return (
    <ul className="market-state-check-list">
      {items.slice(0, 5).map((item, index) => {
        const normalized = normalizeCheckItem(item);
        return (
          <li className="market-state-check-item" key={`${normalized.title || normalized.summary}-${index}`}>
            {normalized.title && <strong>{normalized.title}</strong>}
            {normalized.summary && <span>{normalized.summary}</span>}
            {normalized.sourceRefs.length ? <small>{normalized.sourceRefs.join(" · ")}</small> : null}
          </li>
        );
      })}
    </ul>
  );
}

function DriverCard({ driver }: { driver: Driver }) {
  const confidence = CONFIDENCE_LABELS[driver.confidence] || driver.confidence || "보통";
  const judgement = driver.interpretation;
  const impact = driver.marketImpact || driver.interpretation;
  const evidenceSummary = driver.evidenceSummary || driver.whyItMatters || driver.rationale;
  const nextMemoryCheck = driver.nextMemoryCheck || driver.whatToWatch || driver.nextCheckpoint;
  const showImpact = Boolean(impact && impact !== judgement && impact !== evidenceSummary);
  const detailItems = [
    evidenceSummary ? { label: "근거 요약", value: evidenceSummary } : null,
    showImpact ? { label: "시장 영향", value: impact } : null,
    nextMemoryCheck ? { label: "다음 확인", value: nextMemoryCheck } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;
  return (
    <article className={`market-driver-card momentum-${driver.momentum || "stable"}`}>
      <div className="market-driver-top">
        <h3>{driver.title}</h3>
        <div className="market-driver-chip-row">
          {driver.directionLabel && <span className={`market-direction-chip direction-${signalTone(driver)}`}>{signalLabel(driver)}</span>}
        </div>
      </div>
      {judgement && <p className="market-driver-summary">{judgement}</p>}
      {detailItems.length ? (
        <details className="market-driver-details">
          <summary>근거 보기</summary>
          <dl className="market-driver-detail-list">
            {detailItems.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        </details>
      ) : null}
      <footer>
        <small>
          확신도 {confidence}
          {driver.confidencePct ? ` · ${driver.confidencePct}%` : ""}
        </small>
        {/* Opens the dock directly. The [data-agent-prompt] document handler this
            once relied on no longer exists, which left the button inert.
            .agent-logo-slot is filled by the shared applyAgentBranding bridge. */}
        <button
          type="button"
          className="btn btn--icon agent-action agent-ask-btn"
          data-tooltip="Agent에게 묻기"
          aria-label="Agent에게 묻기"
          onClick={() => openReactAgentDock({ message: driver.askAgentPrompt })}
        >
          <span className="agent-logo-slot" aria-hidden="true" />
        </button>
      </footer>
    </article>
  );
}

interface MarketStateDashboardProps {
  onUpdate?: () => void;
  updating?: boolean;
  updateDisabled?: boolean;
  onContext?: (context: ReturnType<typeof marketStateContextProjection>) => void;
  /** "다음 확인" 아래에 놓는 개인 맥락 한 줄. 이 패널은 내용을 모르고 자리만 준다. */
  personalContext?: ReactNode;
}

const STATE_LABELS: Record<MarketStateStatus, string> = {
  current: "현재",
  stale: "업데이트 필요",
  fallback: "참고용 대체 상태",
  empty: "상태 없음",
};

const SOURCE_LABELS: Record<MarketStateRef["sourceKind"], string> = {
  snapshot: "Market State 스냅샷",
  state_fallback: "기존 중기 내러티브 참고값",
  none: "사용 가능한 상태 없음",
};

const REASON_COPY: Record<string, string> = {
  within_window: "최신 자료 기준과 생성 시각이 유효 범위 안에 있습니다.",
  new_relevant_evidence: "스냅샷 이후 새 외부 자료가 들어왔습니다. 갱신 전 판단은 현재 투자 자세로 사용하지 않습니다.",
  age_exceeded: "생성 후 72시간이 지나 최신성이 만료됐습니다.",
  update_failed: "최근 업데이트가 실패해 현재 상태로 확정할 수 없습니다.",
  invalid_as_of: "기준 시각이 없거나 올바르지 않아 현재 상태로 사용할 수 없습니다.",
  future_as_of: "기준 시각이 현재보다 미래여서 검증이 필요합니다.",
  missing_input_watermark: "입력 자료 기준점이 없어 최신성을 확인할 수 없습니다.",
  state_fallback: "정식 스냅샷이 없어 기존 중기 내러티브를 참고용으로만 보여줍니다.",
  no_state: "아직 생성된 시장 상태가 없습니다.",
};

function stateAge(ref: MarketStateRef | null) {
  if (!ref?.asOf || !ref.resolvedAt) return "계산 불가";
  const asOf = new Date(ref.asOf).getTime();
  const resolvedAt = new Date(ref.resolvedAt).getTime();
  if (!Number.isFinite(asOf) || !Number.isFinite(resolvedAt) || resolvedAt < asOf) return "계산 불가";
  const minutes = Math.floor((resolvedAt - asOf) / 60_000);
  if (minutes < 60) return `${minutes}분`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}시간`;
  return `${Math.floor(hours / 24)}일 ${hours % 24}시간`;
}

function StateMeta({ stateRef }: { stateRef: MarketStateRef | null }) {
  const statusLabel = stateRef?.freshnessReason === "age_exceeded"
    ? "만료"
    : stateRef ? STATE_LABELS[stateRef.status] : "확인 불가";
  return (
    <dl className="market-state-meta" aria-label="시장 상태 기준 정보">
      <div><dt>상태</dt><dd>{statusLabel}</dd></div>
      <div data-qa="market-state-asof"><dt>기준 시각</dt><dd>{displaySnapshotTime(stateRef?.asOf || undefined) || "없음"}</dd></div>
      <div><dt>경과</dt><dd>{stateAge(stateRef)}</dd></div>
      <div data-qa="market-state-source"><dt>출처</dt><dd>{stateRef ? SOURCE_LABELS[stateRef.sourceKind] : "응답 검증 실패"}</dd></div>
      {stateRef ? <div><dt>범위</dt><dd>{stateRef.scope}</dd></div> : null}
    </dl>
  );
}

function StaleNotice({ stateRef }: { stateRef: MarketStateRef }) {
  const expired = stateRef.freshnessReason === "age_exceeded";
  const message = stateRef.freshnessReason === "new_relevant_evidence"
    ? "새 외부 자료가 들어왔습니다."
    : REASON_COPY[stateRef.freshnessReason] || "최신성을 다시 확인해야 합니다.";
  const evidenceTime = stateRef.freshnessReason === "new_relevant_evidence"
    ? displaySnapshotTime(stateRef.relevantEvidenceWatermark || undefined)
    : "";
  return (
    <div className="market-state-stale-notice" data-qa="market-state-stale-notice" role="status" aria-live="polite">
      <strong>{expired ? "최신성 만료" : "업데이트 필요"}</strong>
      <span>{message} 이전 스냅샷을 표시 중입니다.</span>
      {evidenceTime ? <time dateTime={stateRef.relevantEvidenceWatermark || undefined}>새 자료 기준 {evidenceTime}</time> : null}
    </div>
  );
}

function StateGap({ state, stateRef, error, drivers }: { state: Exclude<MarketStateStatus, "current" | "stale">; stateRef: MarketStateRef | null; error?: string; drivers: Driver[] }) {
  const title = state === "fallback" ? "참고용 내러티브만 있습니다" : "아직 생성된 시장 상태가 없습니다";
  const copy = error
    ? `시장 상태 응답을 사용할 수 없습니다: ${error}`
    : REASON_COPY[stateRef?.freshnessReason || ""] || "현재 상태를 검증할 수 없습니다. 업데이트 후 다시 확인하세요.";
  return (
    <section className={`market-state-gap state-${state}`} role="status">
      <span>{STATE_LABELS[state]}</span>
      <h3>{title}</h3>
      <p>{copy}</p>
      {state === "fallback" && drivers.length ? <p>기존 내러티브 {drivers.length}건은 탐색 단서일 뿐, 현재 투자 판단으로 사용하지 마세요.</p> : null}
    </section>
  );
}

type MarketStateDashboardViewProps = {
  payload: DashboardPayload | null;
  selectedMarket?: MarketScope;
  loading?: boolean;
  updating?: boolean;
  updateDisabled?: boolean;
  error?: string;
  onSelectMarket?: (scope: MarketScope) => void;
  onUpdate?: () => void;
  onReload?: () => void;
  personalContext?: ReactNode;
};

export function MarketStateDashboardView({ payload, selectedMarket = "overall", loading = false, updating = false, updateDisabled = false, error = "", onSelectMarket, onUpdate, onReload, personalContext = null }: MarketStateDashboardViewProps) {
  const ref = readMarketStateRef(payload);
  const state: MarketStateStatus = ref?.status || "empty";
  const marketViews = payload?.marketViews || {};
  // 관심 시장 범위 밖의 뷰는 세그먼트에 올리지 않는다. 스냅샷이 만들었더라도
  // 사용자가 끈 시장이면 숨는다 — 범위는 화면 필터가 아니라 제품의 테두리다.
  const { isSelected: marketInScope } = useMarketScope();
  const availableMarkets = MARKET_SCOPE_ORDER.filter(
    (scope) => scope === "overall" || (Boolean(marketViews[scope]) && marketInScope(scope)),
  );
  const activeMarket = availableMarkets.includes(selectedMarket) ? selectedMarket : "overall";
  const activePayload = activeMarket === "overall" ? (marketViews.overall || payload) : (marketViews[activeMarket] || payload);
  const drivers = activePayload?.drivers ?? [];
  const visibleSummary = activePayload?.plainConclusion || activePayload?.summary || "";
  const reasonSummary = activePayload?.reasonSummary || activePayload?.sourceSummary || activePayload?.stance || "";
  const interpretation = splitNarrative(reasonSummary);
  const showsSnapshot = state === "current" || state === "stale";
  const briefs = activePayload?.briefs?.length ? activePayload.briefs : [
    { label: "현재 판단", value: visibleSummary },
    { label: "시장 해석", value: reasonSummary },
    { label: "행동 가이드", value: activePayload?.actionGuide?.action || activePayload?.stance || "" },
    { label: "다음 확인", value: activePayload?.actionGuide?.timing || (activePayload?.watchItems || []).slice(0, 3).join("; ") },
  ].filter((item) => item.value);
  return (
    <section className={`market-state-surface market-state-surface-${state}`} data-qa={`market-state-${state}`}>
      <div className="market-state-head">
        <div>
          <p className="section-kicker">Market State</p>
          <h2>{activePayload?.title || payload?.title || "현재 중기 시장 상황"}</h2>
        </div>
        <div className="market-state-head-actions">
          <button className="btn btn--primary" type="button" data-qa="market-state-update" onClick={onUpdate} disabled={!onUpdate || updateDisabled || updating || loading}>
            {updating ? "업데이트 중" : state === "current" ? "시장 메모리 업데이트" : "시장 상태 업데이트"}
          </button>
          <button className="btn" type="button" onClick={onReload} disabled={!onReload || loading || updating}>
            {loading ? "불러오는 중…" : "새로고침"}
          </button>
        </div>
      </div>
      <StateMeta stateRef={ref} />
      {state === "stale" && ref ? <StaleNotice stateRef={ref} /> : null}
      {/* 상호배타 선택은 .segment 프리미티브가 소유한다. 예전 커스텀 알약은
          ::before 위치가 종합/us/kr 셋에 하드코딩돼 있어, 유럽·일본을 켜
          항목이 4~5개가 되는 순간 폭과 위치가 깨졌다. */}
      {showsSnapshot && availableMarkets.length > 1 ? (
        <div className="segment market-scope-tabs" role="group" aria-label="시장 범위 선택">
          {availableMarkets.map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={activeMarket === key}
              onClick={() => onSelectMarket?.(key)}
            >
              {MARKET_SCOPE_LABELS[key]}
            </button>
          ))}
        </div>
      ) : null}
      {showsSnapshot ? (
        <>
        {state === "current" ? <p className="market-state-current-note">{REASON_COPY[ref?.freshnessReason || "within_window"]}</p> : null}
        <div className="market-state-overview" data-qa="market-state-posture">
          {reasonSummary ? (
            <section className="market-state-interpretation">
              <span>시장 해석</span>
              <strong>{interpretation.lead}</strong>
              {interpretation.support ? <p>{interpretation.support}</p> : null}
            </section>
          ) : null}
          {activePayload?.actionGuide || activePayload?.posture || visibleSummary ? (
            <section className={`market-state-posture posture-${activePayload?.posture?.tone || "watch"}`}>
              <span>판단 및 투자 행동</span>
              {visibleSummary && <p className="market-state-summary">{visibleSummary}</p>}
              {activePayload?.actionGuide ? (
                <div className="market-state-action-body">
                  <strong>{activePayload.actionGuide.headline}</strong>
                  <p>{activePayload.actionGuide.action}</p>
                  {activePayload.actionGuide.timing && <small>{activePayload.actionGuide.timing}</small>}
                </div>
              ) : activePayload?.posture ? (
                <div className="market-state-action-body">
                  <strong>{activePayload.posture.label}</strong>
                  <p>{activePayload.posture.summary}</p>
                </div>
              ) : null}
              {(activePayload?.watchItems?.length || briefs[3]?.value) ? (
                <div className="market-state-action-list">
                  <b>다음 확인</b>
                  {activePayload?.watchItems?.length ? (
                    <ul>
                      {activePayload.watchItems.slice(0, 3).map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>{briefs[3]?.value}</p>
                  )}
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      <div className="market-state-drivers" data-qa="market-state-drivers">
        {drivers.map((driver, index) => (
          <DriverCard key={driver.id || index} driver={driver} />
        ))}
      </div>
      {activePayload && ((activePayload.counterEvidence?.length || 0) > 0 || (activePayload.uncertainties?.length || 0) > 0) ? (
        <div className="market-state-checks" aria-label="반대 근거와 불확실성">
          {activePayload.counterEvidence?.length ? (
            <section data-qa="market-state-counter-evidence">
              <h3>반대 근거</h3>
              <CheckList items={activePayload.counterEvidence} />
            </section>
          ) : null}
          {activePayload.uncertainties?.length ? (
            <section data-qa="market-state-uncertainties">
              <h3>불확실성</h3>
              <CheckList items={activePayload.uncertainties} />
            </section>
          ) : null}
        </div>
      ) : null}
      {(activePayload?.watchItems?.length || briefs[3]?.value) ? <section className="market-state-next-checks" data-qa="market-state-next-checks"><h3>다음 확인</h3><ul>{(activePayload?.watchItems || [briefs[3]?.value]).filter(Boolean).slice(0, 5).map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      </>
      ) : <StateGap state={state} stateRef={ref} error={error} drivers={drivers} />}
      {personalContext}
      {showsSnapshot && payload?.sourceRefs?.length ? (
        <details className="market-state-sources">
          <summary>사용한 출처 {payload.sourceRefs.length}개</summary>
          <ul>
            {payload.sourceRefs.slice(0, 8).map((source, index) => (
              <li key={source.id || index}>
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noreferrer">{source.title || source.source || source.url}</a>
                ) : (
                  <span>{source.title || source.source || source.id}</span>
                )}
                {source.source && <small>{source.source}</small>}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

export function MarketStateDashboard({ onUpdate, updating = false, updateDisabled = false, onContext, personalContext = null }: MarketStateDashboardProps = {}) {
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [selectedMarket, setSelectedMarket] = useState<MarketScope>("overall");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getJson<DashboardPayload>("/api/memory/state-dashboard?limit=5");
      setPayload(data);
      const marketState = marketStateContextProjection(data);
      bridge().updateAgentContext?.({ surface: "market_state", viewId: "memory", reportKind: "", reportId: "", marketState });
      onContext?.(marketState);
    } catch (err) {
      setPayload(null);
      setError(err instanceof Error ? err.message : String(err));
      onContext?.(null);
    } finally {
      setLoading(false);
    }
  }, [onContext]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { bridge().applyAgentBranding?.(); }, [payload]);

  return <MarketStateDashboardView payload={payload} selectedMarket={selectedMarket} loading={loading} updating={updating} updateDisabled={updateDisabled} error={error} onSelectMarket={setSelectedMarket} onUpdate={onUpdate} onReload={load} personalContext={personalContext} />;
}
