import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "../../api";
import { pollAgentJobBounded, type PollableAgentJob } from "../agentPolling";

export const FACTOR_LABELS: Record<string, string> = { interest_rate: "금리", fx: "환율", commodity_input: "원재료", freight: "운임", regional_demand: "지역 수요", customer_capex: "고객 설비투자", inventory_cycle: "재고·수요", credit_access: "자금조달", policy_specific: "정책·규제" };
const FACTOR_ORDER = Object.keys(FACTOR_LABELS);

/** "무엇이 오르면" — 공시 방향의 rising이 가리키는 말(방법론 §10.6). 환율은 시장마다 다르다. */
function riseWord(factor: string, market: string): string {
  if (factor === "fx") return market === "KR" ? "원/달러 환율이 오르면" : "달러가 강해지면";
  return ({ interest_rate: "금리가 오르면", commodity_input: "원재료 값이 오르면", freight: "운임이 오르면" } as Record<string, string>)[factor]
    || `${FACTOR_LABELS[factor] || factor} 증가 시`;
}

function directionText(direction: string, factor: string, market: string): string {
  if (direction === "hurt_by_rise") return `${riseWord(factor, market)} 불리`;
  if (direction === "benefits_from_rise") return `${riseWord(factor, market)} 유리`;
  if (direction === "two_sided") return "유리·불리 경로가 함께 있음";
  return "영향 방향을 확인하지 못함";
}

const SERIES_NAME: Record<string, string> = { DFF: "시장 금리", KR_RATE: "기준금리", KR_USDKRW: "원/달러 환율" };
const MOVE: Record<string, string> = { rising: "올랐음", falling: "내렸음", flat: "그대로" };
const MOVED: Record<string, string> = { rising: "올랐습니다", falling: "내렸습니다" };
const UNIT: Record<string, string> = { DFF: "%", KR_RATE: "%", KR_USDKRW: "원" };
const EFFECT: Record<string, string> = {
  challenging: "공시가 불리하다고 한 쪽으로 움직임",
  supportive: "공시가 유리하다고 한 쪽으로 움직임",
  mixed: "유리·불리 경로가 함께 있어 한쪽으로 말할 수 없음",
};

type SourceRef = { url: string; path: string; form: string; date: string; section?: string };
type Exposure = { id: string; factor: string; direction: string; quote: string; sourceRef: SourceRef; sourceRefs?: SourceRef[]; magnitudeBasis: string; magnitudeQuote?: string };
type Observation = { seriesId: string; direction: string; period: string; comparisonPeriod?: string; sourceRefs?: { period: string; value: string }[] };
type Reading = { exposureId: string; factor: string; interpretation: string; observation: Observation | null; dataGap?: string };
type Response = { profile: { market?: string; items: Exposure[]; limitations: string[] } | null; interpretation: { items: Reading[]; notice: string } | null };

function Arrow({ direction }: { direction: string }) {
  const path = direction === "rising" ? "M4 13L13 4M7 4h6v6" : direction === "falling" ? "M4 5l9 9M7 14h6V8" : "M4 9h10";
  return <svg viewBox="0 0 18 18" aria-hidden="true"><path d={path} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function observationText(o: Observation): string {
  const refs = [...(o.sourceRefs || [])].sort((a, b) => a.period.localeCompare(b.period));
  const name = SERIES_NAME[o.seriesId] || o.seriesId;
  const unit = UNIT[o.seriesId] || "";
  return refs.length >= 2 ? `${name} ${refs[0].value}${unit}에서 ${refs[refs.length - 1].value}${unit}로(3개월)` : name;
}

/** 같은 문장이 연차·분기 보고서에 함께 나오면 한 번만 보이고 출처를 모두 적는다. */
function mergeQuotes(items: Exposure[]) {
  const merged = new Map<string, { item: Exposure; sources: SourceRef[] }>();
  for (const item of items) {
    const key = item.quote.trim();
    const row = merged.get(key);
    const refs = item.sourceRefs?.length ? item.sourceRefs : [item.sourceRef];
    if (row) {
      for (const ref of refs) if (!row.sources.some(r => JSON.stringify(r) === JSON.stringify(ref))) row.sources.push(ref);
    } else merged.set(key, { item, sources: [...refs] });
  }
  return [...merged.values()];
}

function sourceText(ref: SourceRef): string {
  return [ref.form, ref.section ? `항목 ${ref.section}` : "", ref.date || "공시일 미확인"].filter(Boolean).join(" · ");
}

function QuoteList({ items }: { items: Exposure[] }) {
  const sorted = [...items].sort((a, b) => Number(a.direction === "unclear") - Number(b.direction === "unclear"));
  return <>{mergeQuotes(sorted).map(({ item, sources }) => <div key={item.id} className="surface surface--inset macro-exposure__quote" data-quiet={item.direction === "unclear" ? "true" : undefined}>
    <blockquote>{item.quote}</blockquote>
    <p>{sources.map((ref, i) => <span key={i}>{i > 0 && " · "}{sourceText(ref)}{ref.url && <> · <a href={ref.url} target="_blank" rel="noreferrer">원문</a></>}</span>)}</p>
  </div>)}</>;
}

type FactorRow = { factor: string; items: Exposure[]; directions: string[]; reading: Reading | null };

function factorRows(items: Exposure[], readings: Reading[]): FactorRow[] {
  return FACTOR_ORDER.map(factor => {
    const rows = items.filter(item => item.factor === factor);
    const directions = [...new Set(rows.map(item => item.direction).filter(d => d !== "unclear"))];
    const ids = new Set(rows.filter(item => item.direction !== "unclear").map(item => item.id));
    const own = readings.filter(r => ids.has(r.exposureId));
    let reading = own.find(r => r.interpretation !== "unknown" && r.observation) || own.find(r => r.observation) || own[0] || null;
    const outcomes = new Set(own.map(r => r.interpretation).filter(value => value !== "unknown"));
    if (reading && (outcomes.size > 1 || outcomes.has("mixed"))) reading = { ...reading, interpretation: "mixed" };
    return { factor, items: rows, directions, reading };
  }).filter(row => row.items.length)
    .sort((a, b) => Number(b.directions.length > 0) - Number(a.directions.length > 0));
}

function NowCell({ reading }: { reading: Reading | null }) {
  if (!reading) return <span className="macro-exposure__quiet">—</span>;
  if (!reading.observation) {
    return <span className="macro-exposure__quiet">연결된 자료 없음{reading.dataGap === "connected_series_unavailable" && <small>이 요인의 지표는 아직 모으지 않습니다</small>}</span>;
  }
  const o = reading.observation;
  return <>
    <span className="macro-exposure__move"><Arrow direction={o.direction} />{MOVE[o.direction] || "판단 보류"}</span>
    <small>{observationText(o)}</small>
    {EFFECT[reading.interpretation] && <span className="macro-exposure__match">{EFFECT[reading.interpretation]}</span>}
  </>;
}

/** 워치리스트 기업 정보: 공시에 적힌 금리·환율 등의 영향. 검증 중(시험 표시)이며 순효과가 아니다. */
export function ExposurePanel({ ticker }: { ticker: string }) {
  const [data, setData] = useState<Response | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    let live = true; setData(null); setLoaded(false); setMessage(""); setError(""); setBusy(false);
    getJson<Response>(`/api/macro/exposures/${encodeURIComponent(ticker)}`)
      .then(r => { if (live) { setData(r); setLoaded(true); } })
      .catch(() => { if (live) { setError("공시 기록을 읽지 못했습니다."); setLoaded(true); } });
    return () => { live = false; controller.current?.abort(); };
  }, [ticker]);

  async function refresh() {
    const control = new AbortController(); controller.current = control;
    setBusy(true); setError(""); setMessage("공시의 위험 문단을 읽고 있습니다.");
    try {
      const job = await postJson<PollableAgentJob>(`/api/macro/exposures/${encodeURIComponent(ticker)}/refresh`, {});
      const terminal = await pollAgentJobBounded(job, { signal: control.signal });
      if (control.signal.aborted) return;
      if (terminal.status !== "done") throw new Error("공시 확인 작업이 끝나지 않았습니다.");
      const response = await getJson<Response>(`/api/macro/exposures/${encodeURIComponent(ticker)}`);
      if (!control.signal.aborted) { setData(response); setMessage(""); }
    } catch (err) { if (!control.signal.aborted) { setMessage(""); setError(err instanceof Error ? err.message : "공시를 확인하지 못했습니다."); } }
    finally { if (!control.signal.aborted) setBusy(false); }
  }

  const items = data?.profile?.items || [];
  const market = data?.profile?.market || (/^\d{6}$/.test(ticker) ? "KR" : "US");
  const rows = factorRows(items, data?.interpretation?.items || []);
  const hurt = rows.filter(r => r.directions.includes("hurt_by_rise")).map(r => riseWord(r.factor, market));
  const help = rows.filter(r => r.directions.includes("benefits_from_rise")).map(r => riseWord(r.factor, market));
  const moved = rows.map(r => r.reading?.observation).find(o => o && o.direction !== "flat");
  const filings = [...new Map(items.flatMap(i => i.sourceRefs?.length ? i.sourceRefs : [i.sourceRef]).map(ref => [`${ref.form} ${ref.date}`, ref])).values()];
  const checked = data?.profile != null;

  return <section className="watchlist-detail-section watchlist-detail-section--exposure macro-exposure" aria-labelledby={`exposure-${ticker}`}>
    <div className="watchlist-detail-section__head">
      <h3 id={`exposure-${ticker}`}>금리·환율 영향 <small>공시 기준</small></h3>
      <span className="macro-exposure__head-side">
        <span className="chip macro-now__chip" data-tone="muted">검증 중</span>
        {checked && <button type="button" className="btn btn--text btn--sm" disabled={busy} onClick={() => void refresh()}>{busy ? "확인 중…" : "공시 다시 확인"}</button>}
      </span>
    </div>
    {!loaded && <p role="status" className="macro-exposure__lead">공시 기록을 읽고 있습니다.</p>}
    {error && <p role="alert" className="macro-exposure__lead">{error}</p>}
    {message && <p role="status" className="macro-exposure__lead">{message}</p>}
    {loaded && !checked && !busy && <div className="macro-exposure__empty">
      <p className="macro-exposure__lead">{market === "KR" ? "자료함의 한국 공식 공시 재무위험 문단" : "SEC 10-K·10-Q의 위험 문단"}에서 금리·환율 같은 영향 경로를 찾아 원문과 함께 보여 줍니다.</p>
      <button type="button" className="btn" onClick={() => void refresh()}>공시에서 찾기</button>
    </div>}
    {checked && !items.length && !busy && <p className="macro-exposure__lead">공시 위험 문단에서 금리·환율 등의 경로를 찾지 못했습니다. 영향이 없다는 뜻은 아닙니다.</p>}
    {items.length > 0 && <>
      <p className="macro-exposure__answer">
        {hurt.length || help.length
          ? <>공시에서 {hurt.length > 0 && <><b>{hurt.join(", ")}</b> 불리하다고</>}{hurt.length > 0 && help.length > 0 && ", "}{help.length > 0 && <><b>{help.join(", ")}</b> 유리하다고</>} 밝혔습니다.</>
          : rows.some(r => r.directions.includes("two_sided"))
            ? <>공시에 유리한 경로와 불리한 경로가 함께 있어 한쪽 영향으로 요약할 수 없습니다.</>
            : <>공시에서 {rows.map(r => FACTOR_LABELS[r.factor]).join("·")}의 영향을 언급했지만, 어느 쪽으로 움직일 때 불리한지는 확인하지 못했습니다.</>}
        {!!(hurt.length || help.length) && rows.some(r => r.directions.includes("two_sided")) && <> 유리한 경로와 불리한 경로가 함께 적힌 항목도 있습니다.</>}
        {moved && MOVED[moved.direction] && <> 최근 3개월 {SERIES_NAME[moved.seriesId] || moved.seriesId}는 <b>{MOVED[moved.direction]}</b>.</>}
      </p>
      <p className="macro-exposure__lead">회사가 스스로 적은 내용이며, 헤지·상쇄를 합친 회사 전체의 영향은 아닙니다.</p>
      <table className="macro-exposure__table">
        <thead><tr><th scope="col">요인</th><th scope="col">공시에 적힌 방향</th><th scope="col">최근 흐름</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.factor}>
          <th scope="row">{FACTOR_LABELS[row.factor]}</th>
          <td>{row.directions.length
            ? <b>{row.directions.map(d => directionText(d, row.factor, market)).join(" · ")}</b>
            : <span className="macro-exposure__quiet">영향 방향을 확인하지 못함</span>}
            <small>문장 {row.items.length}개</small></td>
          <td><NowCell reading={row.directions.length ? row.reading : null} /></td>
        </tr>)}</tbody>
      </table>
      <details className="macro-exposure__quotes">
        <summary>공시 원문 보기 · 문장 {items.length}개</summary>
        {rows.map(row => <div key={row.factor} className="macro-exposure__group">
          <h4>{FACTOR_LABELS[row.factor]}</h4>
          <QuoteList items={row.items} />
        </div>)}
      </details>
      <p className="macro-exposure__foot">{filings.map(f => `${f.form}(${f.date || "공시일 미확인"})`).join(" · ")}의 위험 문단에서 찾았습니다. 모든 영향을 찾았다는 뜻은 아닙니다. · <a href="#/macro/state">시장·거시 현재 상태</a></p>
    </>}
  </section>;
}

export type PortfolioExposure = { groups: { factor: string; direction: string; combinedWeight: number | null; positions: { ticker: string; market?: string }[]; evidence: { ticker: string; quote: string; magnitudeQuote?: string; sourceRef: { url: string }; sourceRefs?: { url: string }[] }[] }[]; dataGaps: { ticker: string }[]; notice: string; weightBasis: string };

const pct = (value: number | null) => value == null ? "계산 불가" : `${(value * 100).toFixed(1)}%`;

/** 포트폴리오: 같은 요인·같은 방향을 공시에 적은 보유 종목을 묶는다. 비중 추천은 없다. */
function groupDirection(group: PortfolioExposure["groups"][number]): string {
  const markets = [...new Set(group.positions.map(p => p.market || (/^\d{6}$/.test(p.ticker) ? "KR" : "US")))];
  if (group.factor === "fx" && markets.length > 1 && ["hurt_by_rise", "benefits_from_rise"].includes(group.direction)) {
    return `미국은 달러 강세, 한국은 원/달러 상승 시 ${group.direction === "hurt_by_rise" ? "불리" : "유리"}`;
  }
  return directionText(group.direction, group.factor, markets[0] || "US");
}

export function PortfolioExposurePanel({ value }: { value?: PortfolioExposure }) {
  if (!value) return null;
  const groups = [...value.groups].sort((a, b) => Number(b.direction !== "unclear") - Number(a.direction !== "unclear") || (b.combinedWeight ?? -1) - (a.combinedWeight ?? -1));
  const lead = groups.find(g => g.direction === "hurt_by_rise" || g.direction === "benefits_from_rise");
  return <section className="portfolio-block macro-exposure" aria-labelledby="portfolio-exposure-title">
    <div className="portfolio-block__head">
      <h3 id="portfolio-exposure-title">보유 종목의 금리·환율 영향</h3>
      <span className="chip macro-now__chip" data-tone="muted">검증 중</span>
    </div>
    {!groups.length && <p className="macro-exposure__lead">연결된 공시 기록이 없습니다. 워치리스트 기업 정보에서 공시를 확인하면 여기에 모입니다.</p>}
    {lead && <p className="macro-exposure__answer">보유 비중 <b>{pct(lead.combinedWeight)}</b>({lead.positions.length}종목)가 공시에서 <b>{groupDirection(lead)}</b>하다고 밝혔습니다.</p>}
    {groups.length > 0 && <table className="macro-exposure__table">
      <thead><tr><th scope="col">요인</th><th scope="col">공시에 적힌 방향</th><th scope="col">종목</th><th scope="col" className="macro-exposure__num">보유 비중</th></tr></thead>
      <tbody>{groups.map(group => <tr key={`${group.factor}:${group.direction}`}>
        <th scope="row">{FACTOR_LABELS[group.factor] || group.factor}</th>
        <td>{group.direction === "unclear" ? <span className="macro-exposure__quiet">영향 방향을 확인하지 못함</span> : <b>{groupDirection(group)}</b>}</td>
        <td className="macro-exposure__quiet">{group.positions.map(row => row.ticker).join(" · ")}</td>
        <td className="macro-exposure__num"><b>{pct(group.combinedWeight)}</b></td>
      </tr>)}</tbody>
    </table>}
    {groups.length > 0 && <details className="macro-exposure__quotes">
      <summary>공시 원문 보기</summary>
      {groups.map(group => <div key={`${group.factor}:${group.direction}`} className="macro-exposure__group">
        <h4>{FACTOR_LABELS[group.factor] || group.factor} · {group.direction === "unclear" ? "방향 없음" : groupDirection(group)}</h4>
        {group.evidence.map((item, index) => <div key={index} className="surface surface--inset macro-exposure__quote">
          <blockquote>{item.quote}</blockquote>
          <p><a href={`#/watchlist/${encodeURIComponent(item.ticker)}`}>{item.ticker}</a>{(item.sourceRefs?.length ? item.sourceRefs : [item.sourceRef]).filter(ref => ref.url).map((ref, i) => <span key={i}> · <a href={ref.url} target="_blank" rel="noreferrer">공시 원문</a></span>)}{item.magnitudeQuote && <> · 회사가 밝힌 수치: {item.magnitudeQuote}</>}</p>
        </div>)}
      </div>)}
    </details>}
    <p className="macro-exposure__foot">{value.weightBasis} · 회사마다 영향 크기는 다르며 비중 조정 제안이 아닙니다.{value.dataGaps.length > 0 && <> 공시를 아직 확인하지 않은 종목: {value.dataGaps.map(row => row.ticker).join(" · ")}.</>} <a href="#/watchlist">워치리스트</a></p>
  </section>;
}
