import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "../../api";
import { pollAgentJobBounded, type PollableAgentJob } from "../agentPolling";

export const FACTOR_LABELS: Record<string, string> = { interest_rate: "금리", fx: "환율", commodity_input: "원재료", freight: "운임", regional_demand: "지역 수요", customer_capex: "고객 설비투자", inventory_cycle: "재고 수요", credit_access: "자금조달", policy_specific: "정책·규제" };
export const EXPOSURE_DIRECTIONS: Record<string, string> = { benefits_from_rise: "상승이 유리한 경로", hurt_by_rise: "상승이 불리한 경로", two_sided: "양방향 영향", unclear: "영향 방향 미확인" };
type Exposure = { id: string; factor: string; direction: string; quote: string; sourceRef: { url: string; path: string; form: string; date: string }; magnitudeBasis: string };
type Response = { profile: { items: Exposure[]; limitations: string[] } | null; interpretation: { items: { exposureId: string; interpretation: string; observation: { direction: string; period: string } | null }[]; notice: string } | null };
const EFFECT: Record<string, string> = { supportive: "이 경로에는 유리한 방향", challenging: "이 경로에는 불리한 방향", mixed: "서로 반대인 영향 가능", unknown: "현재 영향은 판단하기 어려움" };

export function ExposurePanel({ ticker }: { ticker: string }) {
  const [data, setData] = useState<Response | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    let live = true; setData(null); setMessage(""); setBusy(false);
    getJson<Response>(`/api/macro/exposures/${encodeURIComponent(ticker)}`).then(r => { if (live) setData(r); }).catch(() => { if (live) setMessage("공시 노출 기록을 읽지 못했습니다."); });
    return () => { live = false; controller.current?.abort(); };
  }, [ticker]);
  async function refresh() {
    const control = new AbortController(); controller.current = control;
    setBusy(true); setMessage("공식 공시에서 노출 근거를 찾고 있습니다.");
    try {
      const job = await postJson<PollableAgentJob>(`/api/macro/exposures/${encodeURIComponent(ticker)}/refresh`, {});
      const terminal = await pollAgentJobBounded(job, { signal: control.signal });
      if (control.signal.aborted) return;
      if (terminal.status !== "done") throw new Error("공시 확인 작업이 완료되지 않았습니다.");
      const response = await getJson<Response>(`/api/macro/exposures/${encodeURIComponent(ticker)}`);
      if (!control.signal.aborted) { setData(response); setMessage(response.profile?.items.length ? "공시 노출 기록을 확인했습니다." : "연결할 공식 공시 문단을 찾지 못했습니다. 노출이 없다는 뜻은 아닙니다."); }
    } catch (error) { if (!control.signal.aborted) setMessage(error instanceof Error ? error.message : "공시를 확인하지 못했습니다."); }
    finally { if (!control.signal.aborted) setBusy(false); }
  }
  const groups = new Map<string, Exposure[]>();
  for (const item of data?.profile?.items ?? []) {
    const key = `${item.factor}:${item.direction}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return <section className="watchlist-detail-section macro-state-card" aria-label="공시에서 확인한 거시 노출"><header><h2>이 기업이 영향을 받는 경로</h2><span className="chip">시험 표시</span></header>
    <p>기업이 공시에서 밝힌 금리·환율 등의 위험입니다. 내 투자 이유와 관계없이 같은 자료를 보여 줍니다.</p>
    {!data?.profile?.items.length && <p>아직 연결된 공시 노출이 없습니다. 공시를 확인하면 원문과 함께 볼 수 있습니다.</p>}
    <button className="btn" disabled={busy} onClick={() => void refresh()}>{busy ? "공시 확인 중…" : "공시에서 확인하기"}</button> <a href="#/macro">시장·거시 보기</a>
    <p role="status">{message}</p>
    {data?.profile && <details><summary>공시 확인 범위와 한계</summary><ul>{data.profile.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul><p>공시 전체의 모든 노출을 찾은 결과가 아닙니다. 문장이 불완전하거나 표와 섞인 구간은 빠질 수 있고, 정량 민감도는 자동으로 계산하지 않습니다.</p></details>}
    {[...groups].map(([key, items]) => <details key={key}><summary>{FACTOR_LABELS[items[0].factor]} · {EXPOSURE_DIRECTIONS[items[0].direction]} · 공시 문장 {items.length}개</summary>
      <p>헤지·시차·상쇄 경로를 포함한 기업 전체의 순효과나 실적 영향 수치가 아닙니다.</p>
      {items.map(item => {
        const reading = data?.interpretation?.items.find(row => row.exposureId === item.id);
        return <div key={item.id}>
          <p>{reading ? EFFECT[reading.interpretation] : "현재 영향은 판단하기 어려움"}{!reading?.observation && " · 연결 자료 없음"}</p>
          <blockquote>{item.quote}</blockquote>
          <p>{item.sourceRef.form} · {item.sourceRef.date || "공시일 미확인"} · {item.sourceRef.url ? <a href={item.sourceRef.url} target="_blank" rel="noreferrer">공식 공시 원문</a> : "내가 저장한 공식 공시"}</p>
        </div>;
      })}
    </details>)}
  </section>;
}

export type PortfolioExposure = { groups: { factor: string; direction: string; combinedWeight: number | null; positions: { ticker: string }[]; evidence: { ticker: string; quote: string; magnitudeQuote?: string; sourceRef: { url: string } }[] }[]; dataGaps: { ticker: string }[]; notice: string; weightBasis: string };
export function PortfolioExposurePanel({ value }: { value?: PortfolioExposure }) {
  if (!value) return null;
  return <section className="portfolio-block macro-state-card"><header><h3>보유 종목이 공유하는 노출</h3><span className="chip">시험 표시</span></header><p>{value.notice}</p><p>{value.weightBasis}</p>
    {!value.groups.length && <p>연결된 공시 노출이 없습니다. 워치리스트 기업 정보에서 공시를 확인할 수 있습니다.</p>}
    {value.groups.map(group => <details key={`${group.factor}:${group.direction}`}><summary>{FACTOR_LABELS[group.factor]} · {EXPOSURE_DIRECTIONS[group.direction]} · {group.combinedWeight == null ? "비중 계산 불가" : `${(group.combinedWeight * 100).toFixed(1)}%`}</summary><p>{group.positions.map(row => row.ticker).join(" · ")}</p><p>이 요인이 상승한다면 아래 공시의 조건을 다시 확인합니다.</p>{group.evidence.map((item, index) => <div key={index}><p><a href={`#/watchlist/${encodeURIComponent(item.ticker)}`}>{item.ticker}</a>{item.sourceRef.url && <> · <a href={item.sourceRef.url} target="_blank" rel="noreferrer">공시 원문</a></>}</p><blockquote>{item.quote}</blockquote>{item.magnitudeQuote && <p>기업이 직접 제시한 수치: {item.magnitudeQuote}</p>}</div>)}</details>)}
    {!!value.dataGaps.length && <p>노출 미확인: {value.dataGaps.map(row => row.ticker).join(" · ")}</p>}<a href="#/macro">시장·거시 보기</a>
  </section>;
}
