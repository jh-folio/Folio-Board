import { useEffect, useRef, useState } from "react";
import { ApiRequestError, getJson, postJson } from "../../api";
import { GuideSection } from "../price/Guide";
import { clearPortfolioBasis, currentPortfolioBasisId } from "./session";

export type CandidateOption = { item: string; label: string; instrumentId: string | null };
type Criterion = { state: "met" | "unmet" | "unknown"; reason?: string; axes?: Record<string, { state: string; needed: string | null; sampleMax: string | null }> };
type Readiness = { state: string; message: string; scopeCopy: string; criteria: Record<string, Criterion>; blockingReasons: string[]; warnings: string[]; snapshotId: string | null; criteriaRevisionId: number | null };
type Dimension = { status: string; value: unknown; currency: string | null; dataGaps: string[]; basis: Record<string, unknown>; sourceRefs: unknown[]; freshness: string };
type CandidateResult = { identity: { instrumentId: string }; readiness: Readiness; dimensions: Record<string, Dimension>; sourceRefs: Record<string, unknown> };
type Comparison = { evaluatedAt: string; candidates: CandidateResult[]; comparability: Array<{ left: string; right: string; dimensions: Record<string, { status: string; reasons: string[] }> }>; referenceSet: Record<string, unknown>; inputFingerprint: string; notice: string };

const CRITERIA: Record<string, string> = { requiredReturn: "원하는 연 수익률", minMarginOfSafety: "최소 안전마진", holdingYears: "기본 보유기간", allowAboveHistoricalRange: "과거 최고값을 넘는 전제 허용" };
const DIMENSIONS: Array<[string, string]> = [["companyQuality", "기업 품질"], ["scenarioReturn", "시나리오 수익률"], ["uncertainty", "불확실성과 자료 공백"], ["macroFit", "거시 적합"], ["returnSource", "지난 주가 수익의 출처"], ["reasonState", "내 이유와 검토 상태"], ["portfolioOverlap", "Portfolio와 겹치는 부분"]];
const COPY: Record<string, string> = {
  criteria_not_set: "아직 정하지 않은 기준입니다", snapshot_missing: "가격 계산 기록이 없습니다", support_not_checked: "이 종목의 계산 지원 여부를 아직 확인하지 않았습니다",
  unsupported_model: "이 가치 계산이 지원하지 않는 종목입니다", unsupported_market: "이 시장의 가격 모델은 아직 지원하지 않습니다", unknown_price_method: "계산 방법을 확인할 수 없습니다",
  snapshot_old: "가격 계산 기록이 30일을 넘었습니다", snapshot_review_needed: "계산에 쓴 자료가 정정돼 다시 확인해야 합니다", stale_financials: "계산에 쓴 재무 자료가 오래됐습니다",
  eligible_dcf_missing: "안전마진을 확인할 현금 가치 계산 자료가 부족합니다", base_scenario_missing: "기준 시나리오를 계산할 자료가 부족합니다",
  company_report_missing: "저장된 기업분석이 없습니다", company_quality_section_unidentified: "기업 품질 부분을 확인하지 못했습니다", excerpt_is_not_a_company_score: "보고서 원문 일부이며 기업의 종합 점수가 아닙니다",
  company_report_unreadable: "일부 기업분석 파일을 읽지 못했습니다. 자료가 없다는 뜻이 아닙니다", reason_identity_not_verified: "이 이유가 같은 시장·증권의 이유인지 확인하지 못했습니다",
  company_exposure_not_investigated: "공시 노출은 미조사입니다", macro_interpretation_shadow: "거시 해석은 검증 중입니다", exposure_is_partial: "확인한 공시 노출만 반영합니다",
  price_model_unavailable: "지원되거나 확인된 가격 계산이 없습니다", price_snapshot_missing: "가격 계산 기록이 없습니다", reason_history_not_verified: "이유의 판본을 확인하지 못했습니다",
  overlap_weights_not_captured: "겹침 비중은 Portfolio 미리보기에서 확인합니다", economic_currency_not_investigated: "매출의 통화 노출은 미조사입니다", holding_identity_not_verified: "보유 종목의 정확한 증권 식별이 부족합니다",
  missing_or_stale: "자료가 없거나 오래됐습니다", currency_different: "시세 통화가 달라 환율 효과 없이 같은 수익률로 비교할 수 없습니다", asOf_different: "기준일이 다릅니다",
  methodVersion_different: "계산 방법이 다릅니다", specSha256_different: "계산 규칙의 판본이 다릅니다", holdingYears_different: "보유기간이 다릅니다", holding_period_not_set: "비교할 보유기간을 정하지 않았습니다",
  startDate_different: "실제 시작일이 다릅니다", endDate_different: "실제 종료일이 다릅니다", startFiscalYear_different: "시작 회계연도가 다릅니다", endFiscalYear_different: "종료 회계연도가 다릅니다",
  startPeriodEnd_different: "회계기간의 시작 기준이 다릅니다", endPeriodEnd_different: "회계기간의 종료 기준이 다릅니다", definition_different: "숫자의 뜻이 다릅니다", requestedYears_different: "지난 수익의 조회기간이 다릅니다",
  context_missing: "맥락 자료가 일부 없습니다", context_has_different_basis: "서술의 자료 기준이 다릅니다", basis_missing: "비교 기준을 확인하지 못했습니다",
  return_attribution_not_stored: "과거 수익을 나눌 저장 자료가 없습니다", previous_method: "이전 방법의 계산이며 이 항목은 확인할 수 없습니다",
  comparison_inputs_missing: "지난 주가 수익을 나눌 저장 입력이 없습니다", scenario_cells_missing: "같은 시나리오·기간의 계산 숫자가 일부 없습니다",
};
export function gapCopy(code: string) {
  if (COPY[code]) return COPY[code];
  for (const [key, label] of Object.entries(CRITERIA)) {
    if (code === `${key}_unknown`) return `${label}: 기준 또는 자료 확인이 필요합니다`;
    if (code === `${key}_unmet`) return `${label}: 입력한 조건에 미달합니다`;
  }
  return "이 항목의 자료 조건을 더 확인해야 합니다";
}
const object = (value: unknown): Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const rows = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.map(object) : [];
const percent = (value: unknown) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)) ? `${(Number(value) * 100).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%` : "확인 불가";

export function candidateIdFor(ticker: string, market?: string): string | null {
  const clean = ticker.trim().toUpperCase();
  const original = market?.toUpperCase();
  const inferred = original || (/\.(KS|KQ)$/.test(clean) || /^[0-9][A-Z0-9]{5}$/.test(clean) ? "KR" : /\.T$/.test(clean) ? "JP" : /\.(L|DE|PA|AS|MI|MC)$/.test(clean) ? "EUROPE" : "US");
  if (!["US", "KR", "JP", "EUROPE"].includes(inferred) || !/^[A-Z0-9][A-Z0-9.\-]{0,24}$/.test(clean)) return null;
  const symbol = inferred === "KR" ? clean.replace(/\.(KS|KQ)$/, "") : clean;
  return `${inferred}:${symbol}`;
}

function GapList({ values }: { values: string[] }) {
  return values.length ? <ul className="decision-gaps">{values.map(code => <li key={code}>{gapCopy(code)}</li>)}</ul> : null;
}

export function ReadinessCard({ value }: { value: Readiness }) {
  return <div className="decision-readiness" data-readiness-state={value.state}>
    <p><strong>{value.message}</strong></p>
    <p className="price-meta">{value.scopeCopy}</p>
    <dl className="decision-criteria">{Object.entries(value.criteria).map(([key, entry]) => <div key={key}><dt>{CRITERIA[key] || key}</dt><dd>
      <span className="chip">{entry.state === "met" ? key === "holdingYears" ? "기간 설정됨" : "입력 조건 충족" : entry.state === "unmet" ? "입력 조건 미달" : "확인 보류"}</span>
      {entry.axes && <ul className="decision-gaps">{Object.entries(entry.axes).map(([axis, item]) => <li key={axis}>{axis === "growth" ? "이익 성장" : axis === "exitPE" ? "끝날 때 PER" : "순이익률"}: {item.state === "not_needed" ? "배당 조건만으로 설명됨" : item.state === "unknown" ? "비교 자료 부족" : `${axis === "exitPE" ? `${item.needed}배` : percent(item.needed)} · 과거 최고 ${axis === "exitPE" ? `${item.sampleMax}배` : percent(item.sampleMax)}${item.state === "above_sample" ? "를 넘음" : " 이하"}`}</li>)}</ul>}
    </dd></div>)}</dl>
    {value.blockingReasons.length > 0 && <><h4>다음 확인</h4><GapList values={value.blockingReasons} /></>}
    {value.warnings.length > 0 && <><h4>함께 남아 있는 자료 공백</h4><GapList values={value.warnings} /></>}
    <p className="price-meta">가격 계산 {value.snapshotId ? "기록 있음" : "기록 없음"} · 내 기준 {value.criteriaRevisionId === null ? "미설정" : `${value.criteriaRevisionId}번째 판본`}</p>
  </div>;
}

export function ReadinessSection({ instrumentId, active = true, snapshotId, criteriaRevisionId }: { instrumentId: string; active?: boolean; snapshotId?: string; criteriaRevisionId?: number | null }) {
  const [value, setValue] = useState<Readiness | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController(); setError(false); setValue(null);
    const query = new URLSearchParams();
    if (snapshotId) query.set("snapshotId", snapshotId);
    if (criteriaRevisionId !== null && criteriaRevisionId !== undefined) query.set("criteriaRevisionId", String(criteriaRevisionId));
    getJson<{ readiness: Readiness }>(`/api/decision-readiness/${encodeURIComponent(instrumentId)}?${query}`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setValue(data.readiness); }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [instrumentId, active, snapshotId, criteriaRevisionId]);
  return <GuideSection headingLevel={3} id="decision-readiness-title" title="내 기준과 검토 준비 상태" question="이 가격 계산을 내 기준과 함께 검토할 자료가 갖춰졌나요?" read="입력한 조건을 확인하는 화면입니다. 이유를 적지 않거나 짧게 적어도 준비 상태의 불이익이 되지 않습니다.">
    {error ? <p role="alert">준비 상태 자료를 읽지 못했습니다. 기준이나 기록은 바뀌지 않았습니다.</p> : value ? <ReadinessCard value={value} /> : <p role="status">준비 상태를 읽고 있습니다…</p>}
    <a className="btn btn--text btn--sm" href="#/settings/admin">설정에서 전역 투자 기준 보기</a>
  </GuideSection>;
}

function DimensionValue({ name, value }: { name: string; value: Dimension }) {
  if (value.status === "unavailable" || value.value === null) return <><p>비교할 자료가 없습니다.</p><GapList values={value.dataGaps} /></>;
  const packet = object(value.value);
  let content;
  if (name === "companyQuality") content = <p className="decision-excerpt">{String(value.value)}</p>;
  else if (name === "scenarioReturn") content = <ul className="decision-values">{rows(value.value).map((row, index) => <li key={index}>{row.label === "base" ? "기준" : row.label === "conservative" ? "보수" : "낙관"} · {String(row.horizon)}년: {row.status === "available" ? row.irrRange ? "계산 탐색 범위 밖" : percent(row.irr) : "자료 부족"}</li>)}</ul>;
  else if (name === "macroFit") content = <><p>검증 중 · 확인한 공시 노출의 조건부 해석</p><ul className="decision-values">{rows(packet.items).map((row, index) => <li key={index}>{({ interest_rate: "금리", fx: "환율", commodity_input: "원자재 투입", freight: "운임", regional_demand: "지역 수요", customer_capex: "고객 설비투자", inventory_cycle: "재고 주기", credit_access: "자금 조달", policy_specific: "개별 정책" } as Record<string, string>)[String(row.factor)] || "공시 요인"}: {row.interpretation === "supportive" ? "확인한 노출에 유리한 방향" : row.interpretation === "challenging" ? "확인한 노출에 부담인 방향" : row.interpretation === "mixed" ? "양쪽 영향" : "미확인"} · {String(object(row.observation).period || "관측일 미확인")}</li>)}</ul></>;
  else if (name === "returnSource") content = <><p>{String(packet.startFiscalYear)}~{String(packet.endFiscalYear)} 회계연도 · {String(packet.startDate)}~{String(packet.endDate)}</p><p>주가 수익 {String(object(packet.display).price || "미확인")}% · 이익 {String(object(packet.display).growth || "미확인")}% · PER 변화 {String(object(packet.display).rerating || "미확인")}% · 배당 {String(object(packet.display).dividend || "미확인")}%</p><p className="price-meta">앞으로의 시나리오 수익률과 다른 과거 기록입니다.</p></>;
  else if (name === "reasonState") content = <><p>{packet.status === "unwritten" ? "아직 이유를 남기지 않았습니다" : packet.status === "reviewed" ? "현재 이유 판본 검토 기록 있음" : packet.status === "evidence_gap" ? "검토에서 자료 공백 확인" : packet.status === "unreviewed" ? "이유 있음 · 아직 검토 기록 없음" : "이유 판본 확인 필요"}</p>{packet.text ? <p className="decision-excerpt">{String(packet.text).slice(0, 500)}</p> : null}<p className="price-meta">작성량과 준비 상태는 별개입니다.</p></>;
  else if (name === "portfolioOverlap") content = <><p>{packet.heldSameSecurity === true ? "같은 증권을 보유하고 있습니다" : packet.heldSameSecurity === false ? "같은 증권의 현재 보유가 없습니다" : "보유 증권의 정확한 식별을 확인해야 합니다"}</p><p>산업: {String(packet.industry || "미조사")} · 시세 통화: {String(packet.quoteCurrency || "미확인")}</p>{packet.confirmedWeights ? <p>고정한 보유 기준에서 같은 증권 {percent(object(packet.confirmedWeights).sameSecurity)} · 같은 산업 {percent(object(packet.confirmedWeights).sameIndustry)} · 같은 시세 통화 {percent(object(packet.confirmedWeights).sameQuoteCurrency)}. 공시 노출 미조사 보유 {percent(object(packet.confirmedWeights).uninvestigatedHoldingWeight)}.</p> : null}</>;
  else content = <><GapList values={Array.isArray(packet.blockingReasons) ? packet.blockingReasons as string[] : []} /><p>{rows(packet.reviewRows).length ? "정정·재확인 기록 있음" : "확인된 정정 기록 없음"}</p></>;
  return <>{content}<p className="price-meta">{value.currency || "통화 해당 없음"}{value.basis.asOf ? ` · ${String(value.basis.asOf)} 기준` : " · 기준일 미확인"}{value.status === "stale" ? " · 오래된 자료" : ""}</p><GapList values={value.dataGaps} /><details><summary>출처와 계산 기준</summary><pre className="decision-source">{JSON.stringify({ basis: value.basis, sourceRefs: value.sourceRefs }, null, 2)}</pre></details></>;
}

let session: { selected: string[]; value: Comparison | null; open: boolean } = { selected: [], value: null, open: false };
let returnFocus: string | null = null;

export function OpportunityComparison({ options, active = true, onOpen }: { options: CandidateOption[]; active?: boolean; onOpen: (item: string) => void }) {
  const [selected, setSelected] = useState(session.selected);
  const [value, setValue] = useState<Comparison | null>(session.value);
  const [open, setOpen] = useState(session.open);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [changed, setChanged] = useState(false);
  const request = useRef<AbortController | null>(null);
  const surface = useRef<HTMLElement | null>(null);
  useEffect(() => { session = { selected, value, open }; }, [selected, value, open]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (!active) { request.current?.abort(); setBusy(false); return; }
    if (returnFocus) { surface.current?.querySelector<HTMLButtonElement>(`button[data-compare-open="${CSS.escape(returnFocus)}"]`)?.focus(); returnFocus = null; }
  }, [active]);
  useEffect(() => {
    if (!value || !active) return;
    const controller = new AbortController();
    Promise.all(value.candidates.map(row => getJson<{ referenceSet: { candidates: Array<Record<string, unknown>>; criteriaRevisionId: number | null; portfolioHash: string | null } }>(`/api/decision-readiness/${encodeURIComponent(row.identity.instrumentId)}`, { signal: controller.signal })))
      .then(current => { if (!controller.signal.aborted) setChanged(current.some((data, i) => data.referenceSet.criteriaRevisionId !== value.referenceSet.criteriaRevisionId || data.referenceSet.portfolioHash !== value.referenceSet.portfolioHash || JSON.stringify(data.referenceSet.candidates[0]) !== JSON.stringify(value.referenceSet.candidates && (value.referenceSet.candidates as unknown[])[i]))); })
      .catch(() => { if (!controller.signal.aborted) setChanged(true); });
    return () => controller.abort();
  }, [active, value]);
  async function compare() {
    const picked = options.filter(row => selected.includes(row.item));
    const ordered = selected.map(item => picked.find(row => row.item === item)).filter((row): row is CandidateOption => Boolean(row?.instrumentId));
    if (!ordered.length) { setError("비교할 후보를 골라 주세요."); return; }
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError("");
    try {
      const result = await postJson<Comparison>("/api/opportunity-comparison", { candidates: ordered.map(row => ({ instrumentId: row.instrumentId })), ...(currentPortfolioBasisId() ? { portfolioBasisId: currentPortfolioBasisId() } : {}) }, { signal: controller.signal });
      if (!controller.signal.aborted) { setValue(result); setChanged(false); }
    } catch (err) {
      if (!controller.signal.aborted) {
        if (err instanceof ApiRequestError && ["portfolio_basis_expired", "comparison_inputs_changed"].includes(err.code) && currentPortfolioBasisId()) {
          clearPortfolioBasis();
          setError("Portfolio의 임시 기준이 만료됐거나 보유 자료가 바뀌었습니다. 선택과 앞선 결과는 남아 있습니다. 현재 자료로 읽기를 다시 누르면 겹침 비중 참조 없이 비교합니다. 비중까지 보려면 Portfolio에서 기준을 다시 읽어 주세요.");
        } else setError("비교 자료를 읽지 못했습니다. 선택은 그대로 남아 있습니다. 자료가 바뀌었다면 다시 읽어 주세요.");
      }
    }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section ref={surface} className="decision-comparison surface surface--group" aria-labelledby="opportunity-title">
    <div className="decision-head"><h3 id="opportunity-title">후보 비교</h3><button className="btn btn--sm" type="button" aria-expanded={open} aria-controls="opportunity-content" onClick={() => setOpen(!open)}>{open ? "접기" : "열기"}</button></div>
    {open && <div id="opportunity-content">
      <p>같은 항목에서 장단점과 자료 공백을 읽습니다. 선택한 순서이며 종목의 순위가 아닙니다. 2~4개부터, 최대 8개를 고를 수 있습니다.</p>
      <fieldset className="decision-options"><legend>비교할 워치리스트 후보</legend>{options.map(row => <label key={row.item}><input type="checkbox" checked={selected.includes(row.item)} disabled={!row.instrumentId || (!selected.includes(row.item) && selected.length >= 8)} onChange={event => setSelected(current => event.target.checked ? [...current, row.item] : current.filter(item => item !== row.item))} />{row.label}{!row.instrumentId ? " · 종목 식별 미확인" : ""}</label>)}</fieldset>
      <button className="btn" type="button" onClick={() => void compare()} disabled={busy}>{busy ? "비교 자료 읽는 중…" : "선택 후보 현재 자료로 읽기"}</button>
      {error && <p role="alert">{error}</p>}
      {value && <><p className="price-meta">읽은 시각 {value.evaluatedAt} · 이 화면의 결과는 영구 저장되지 않습니다.</p>
        {(changed || selected.join("|") !== value.candidates.map(row => options.find(option => option.instrumentId === row.identity.instrumentId)?.item).join("|")) && <p role="status">현재 자료 또는 선택이 달라졌습니다. 아래는 앞서 읽은 결과입니다. 현재 자료로 읽기를 누르면 갱신합니다.</p>}
        <div className="decision-grid">{value.candidates.map(row => <div className="decision-candidate" key={row.identity.instrumentId}><h4>{options.find(option => option.instrumentId === row.identity.instrumentId)?.label || row.identity.instrumentId}</h4><ReadinessCard value={row.readiness} /><button className="btn btn--text btn--sm" data-compare-open={row.identity.instrumentId} type="button" onClick={() => { returnFocus = row.identity.instrumentId; onOpen(options.find(option => option.instrumentId === row.identity.instrumentId)?.item || row.identity.instrumentId.split(":")[1]); }}>기업 정보·가격·내 이유 열기</button></div>)}</div>
        {DIMENSIONS.map(([name, label]) => <section className="decision-dimension" key={name} aria-labelledby={`compare-${name}`}><h4 id={`compare-${name}`}>{label}</h4><div className="decision-grid">{value.candidates.map(row => <div key={row.identity.instrumentId}><h5>{options.find(option => option.instrumentId === row.identity.instrumentId)?.label || row.identity.instrumentId}</h5><DimensionValue name={name} value={row.dimensions[name]} /></div>)}</div>{value.comparability.map(pair => pair.dimensions[name].reasons.length ? <div className="decision-limits" key={`${pair.left}-${pair.right}`}><p><strong>{pair.left} ↔ {pair.right}</strong> · {pair.dimensions[name].status === "incomparable" ? "같은 숫자로 비교할 수 없는 이유" : "자료 기준"}</p><GapList values={pair.dimensions[name].reasons} /></div> : null)}</section>)}
        <p className="price-meta">{value.notice}</p><details><summary>입력 판본과 당시 참조</summary><pre className="decision-source">{JSON.stringify(value.referenceSet, null, 2)}</pre></details>
      </>}
    </div>}
  </section>;
}
