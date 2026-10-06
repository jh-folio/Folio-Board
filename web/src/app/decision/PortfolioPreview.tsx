import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiRequestError, postJson } from "../../api";
import { candidateIdFor } from "./DecisionReadiness";
import { GuideSection } from "../price/Guide";
import { clearPortfolioBasis, rememberPortfolioBasis } from "./session";

type Basis = { basisId: string; expiresAt: string; basisFingerprint: string; candidate: { instrumentId: string }; portfolioRevision: number; dataGaps: string[] };
type Composition = { security: Record<string, string>; industry: Record<string, string>; currency: Record<string, string>; macro: Record<string, string>; concentration: Record<string, string>; coverage?: Array<{ instrumentId: string; profileId: string | null; weight: string; items: Array<{ factor: string; direction: string; quote: string; magnitudeBasis: string; sourceRefs: Array<{ date?: string; url?: string; form?: string }> }> }>; uninvestigatedHoldingWeight: string; etfLookThrough: Array<{ instrumentId: string; status: string; unknownWeight: string; compositionCoverage?: string }> };
type Preview = { status: string; reason?: string; before: Composition | null; after: Composition | null; delta: Composition | null; assumption: string; notice?: string; dataGaps: string[]; candidateWeightPercent: string; sourceRefs: Record<string, unknown>; backtest?: { status: string } };
const percent = (value?: string) => value === undefined ? "확인 불가" : `${(Number(value) * 100).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`;
const factor: Record<string, string> = { interest_rate: "금리", fx: "환율", commodity_input: "원자재 투입", freight: "운임", regional_demand: "지역 수요", customer_capex: "고객 설비투자", inventory_cycle: "재고 주기", credit_access: "자금 조달", policy_specific: "개별 정책" };
const directions: Record<string, string> = { benefits_from_rise: "상승의 이점", hurt_by_rise: "상승의 부담", two_sided: "양쪽 영향", unclear: "방향 미확인" };
function label(value: string) {
  if (value.startsWith("cash:")) return "현금";
  if (value === "maxHolding") return "가장 큰 보유 종목";
  if (value === "top3") return "상위 3개 보유 합계";
  if (value === "top5") return "상위 5개 보유 합계";
  const parts = value.split(":");
  return factor[parts[0]] ? `${factor[parts[0]]} · ${directions[parts[1]] || "방향 미확인"}` : value;
}
let session: { market: string; ticker: string; weight: string; basis: Basis | null; value: Preview | null } = { market: "US", ticker: "", weight: "", basis: null, value: null };

export function PortfolioPreview({ active = true }: { active?: boolean }) {
  const [market, setMarket] = useState(session.market);
  const [ticker, setTicker] = useState(session.ticker);
  const [weight, setWeight] = useState(session.weight);
  const [basis, setBasis] = useState<Basis | null>(session.basis);
  const [value, setValue] = useState<Preview | null>(session.value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const instrument = ticker.trim() ? candidateIdFor(ticker, market) : null;
  useEffect(() => { session = { market, ticker, weight, basis, value }; }, [market, ticker, weight, basis, value]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { if (!active) { controller.current?.abort(); setBusy(false); } }, [active]);
  const changed = basis && basis.candidate.instrumentId !== instrument;
  async function read() {
    if (!instrument) { setError("시장과 종목 기호를 확인해 주세요."); return; }
    const control = new AbortController(); controller.current?.abort(); controller.current = control;
    setBusy(true); setError("");
    try { const next = await postJson<Basis>("/api/portfolio/decision-preview/basis", { instrumentId: instrument }, { signal: control.signal }); if (!control.signal.aborted) { setBasis(next); rememberPortfolioBasis(next.basisId); setValue(null); } }
    catch { if (!control.signal.aborted) setError("미리보기 기준 자료를 읽지 못했습니다. 입력은 그대로 남아 있습니다."); }
    finally { if (!control.signal.aborted) setBusy(false); }
  }
  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!basis || !instrument || changed || !event.currentTarget.reportValidity()) return;
    const control = new AbortController(); controller.current?.abort(); controller.current = control;
    setBusy(true); setError("");
    try { const next = await postJson<Preview>("/api/portfolio/decision-preview", { instrumentId: instrument, basisId: basis.basisId, candidateWeightPercent: weight.trim() }, { signal: control.signal }); if (!control.signal.aborted) setValue(next); }
    catch (err) { if (!control.signal.aborted) { const expired = err instanceof ApiRequestError && ["portfolio_basis_expired", "comparison_inputs_changed"].includes(err.code); if (expired) clearPortfolioBasis(); setError(expired ? "시간이 지났거나 보유 자료가 바뀌었습니다. 입력은 남아 있으니 미리보기 기준을 다시 읽어 주세요." : "비중을 계산하지 못했습니다. 0~100 사이의 숫자와 읽은 후보를 확인해 주세요."); } }
    finally { if (!control.signal.aborted) setBusy(false); }
  }
  return <div className="decision-preview" data-decision-preview><GuideSection headingLevel={3} id="portfolio-decision-preview-title" title="후보 비중 미리보기" question="직접 입력한 후보 비중이면 구성이 어떻게 달라지나요?" calc="후보의 최종 비중을 입력합니다. 나머지 자산과 현금은 기존 비율을 유지하며 함께 조정합니다." read="직접 입력한 가정의 구성 변화입니다. 권장 비중이나 실제 보유 변경이 아닙니다.">
    <form onSubmit={event => void calculate(event)}><div className="price-form">
      <label>후보 시장<select value={market} onChange={event => setMarket(event.target.value)}><option value="US">미국</option><option value="KR">한국</option><option value="JP">일본</option><option value="EUROPE">유럽</option></select></label>
      <label>후보 종목 기호<input value={ticker} placeholder="예: AAPL" onChange={event => setTicker(event.target.value)} /></label>
      <label>후보의 최종 비중 (%)<input type="text" inputMode="decimal" pattern="[0-9]+(\.[0-9]+)?" required value={weight} placeholder="직접 입력 · 0~100" onChange={event => setWeight(event.target.value)} /></label>
    </div><div className="price-row"><button className="btn" type="button" disabled={busy} onClick={() => void read()}>미리보기 기준 읽기</button><button className="btn" type="submit" disabled={busy || !basis || Boolean(changed)}>입력 비중으로 미리보기</button></div></form>
    {busy && <p role="status">미리보기 자료를 확인하고 있습니다…</p>}{error && <p role="alert">{error}</p>}
    {!basis && <p className="price-meta">기준 읽기를 누를 때만 보유 종목의 시세·환율을 조회합니다. 숫자를 입력해도 자동으로 조회하거나 저장하지 않습니다.</p>}
    {basis && <p className="price-meta">보유 {basis.portfolioRevision}번째 판본 · 임시 기준 만료 {basis.expiresAt}. 30분 또는 서버 재시작 뒤에는 다시 읽습니다.</p>}
    {changed && <p role="status">후보가 달라졌습니다. 미리보기 기준을 다시 읽어 주세요.</p>}
    {value && <><p>{value.assumption}</p>{value.status !== "available" ? <p role="status">{value.reason === "no_other_assets" ? "후보 외의 자산이 없어 나머지 비중을 나눌 수 없습니다." : "보유의 시세·환율·수량·현금 또는 종목 식별이 부족해 전체 비중을 계산하지 않았습니다. 빠진 자산을 빼고 합계를 만들지 않습니다."}</p> : value.before && value.after && value.delta && <>
      {Number(weight.trim()) !== Number(value.candidateWeightPercent) && <p role="status">비중 입력이 달라졌습니다. 아래는 앞서 계산한 결과입니다.</p>}
      <p><strong>후보 최종 비중 {value.candidateWeightPercent}%</strong> · 합계는 현금을 포함하며 시세 통화를 USD로 환산했습니다.</p>
      {([ ["security", "종목과 현금"], ["industry", "산업"], ["currency", "시세 통화"], ["concentration", "집중도"], ["macro", "공시 기반 노출"] ] as const).map(([key, title]) => <section key={key}><h4>{title}</h4>{Object.keys(value.after![key]).length ? <div className="decision-table-scroll"><table className="price-table"><thead><tr><th scope="col">항목</th><th scope="col">현재</th><th scope="col">가정 후</th><th scope="col">변화</th></tr></thead><tbody>{Object.keys(value.delta![key]).map(name => <tr key={name}><th scope="row">{label(name)}</th><td data-label="현재">{percent(value.before![key][name] || "0")}</td><td data-label="가정 후">{percent(value.after![key][name] || "0")}</td><td data-label="변화">{(Number(value.delta![key][name]) * 100).toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%p</td></tr>)}</tbody></table></div> : <p>미조사 · 확인된 노출 자료가 없습니다.</p>}</section>)}
      <p>공시 노출을 조사하지 못한 보유 비중: 현재 {percent(value.before.uninvestigatedHoldingWeight)}, 가정 후 {percent(value.after.uninvestigatedHoldingWeight)}. 노출이 없다는 뜻이 아닙니다.</p>
      <details><summary>확인한 공시 노출의 원문과 판본</summary>{(value.after.coverage || []).map(row => <div key={row.instrumentId}><p><strong>{row.instrumentId}</strong> · 확인 보유 비중 {percent(row.weight)} · 공시 노출 판본 {row.profileId || "미조사"}</p>{(row.items || []).map((item, index) => <div key={index}><p>{label(`${item.factor}:${item.direction}`)} · {item.magnitudeBasis === "company_quantified" ? "회사가 수치로 밝힌 노출" : "정성 설명이며 숫자로 밝힌 전체 영향이 아님"}</p><blockquote>{item.quote}</blockquote>{(item.sourceRefs || []).map((ref, i) => <p key={i}>{ref.form || "공시"} · 공시 기준일 {ref.date || "미확인"}{ref.url && /^https?:\/\//.test(ref.url) ? <> · <a href={ref.url} target="_blank" rel="noreferrer">원문 출처</a></> : null}</p>)}</div>)}</div>)}</details>
      {value.after.etfLookThrough.map(row => <p key={row.instrumentId}>{row.instrumentId} ETF 구성: {row.status === "partial" ? `일부 확인 · 구성 확인 ${percent(row.compositionCoverage)}` : "미조사"} · 확인하지 못한 전체 비중 {percent(row.unknownWeight)}. 직접 종목 비중에 중복 합산하지 않습니다.</p>)}
      <p className="price-meta">{value.notice} 후보를 넣은 과거 검사의 입력 일치를 확인하지 못해 분산·공분산·위험 기여 숫자는 표시하지 않았습니다.</p>
    </> }<details><summary>시세·환율 출처와 자료 공백</summary><pre className="decision-source">{JSON.stringify({ sourceRefs: value.sourceRefs, dataGaps: value.dataGaps }, null, 2)}</pre></details></>}
  </GuideSection></div>;
}
