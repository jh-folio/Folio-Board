import { useRef, useState } from "react";
import { getJson } from "../../api";
import { FACTOR_LABELS } from "./ExposurePanel";
export type CompanyLink = { ticker: string; profileId: string; exposureId: string; condition?: { revisionId: string; index: number; overlapQuote: string } };
export type Channel = { channel: string; explanation: string; sourceRef: { url: string; title: string; kind: string; quote: string }; companyLink?: CompanyLink; resolvedCompanyLink?: { ticker: string; quote: string; sourceRef: { url?: string }; condition?: { quote: string } } };
type Targets = { profile: { ticker: string; profileId: string; items: { id: string; factor: string; quote: string }[] } | null; reason: { revisionId: string; conditions: string[] } | null };
const CHANNELS: Record<string, string> = { demand_revenue: "수요·매출", input_cost: "투입 비용", financing_cost: "자금조달 비용", capex_incentive: "설비투자 유인", market_access: "시장 접근", compliance_cost: "규정 준수 비용", fx: "환율" };
export function PolicyChannelFields({ value, source, onChange }: { value: Channel[]; source: Channel["sourceRef"]; onChange: (value: Channel[]) => void }) {
  const [ticker, setTicker] = useState(""); const [targets, setTargets] = useState<Targets | null>(null); const [message, setMessage] = useState("");
  const requestVersion = useRef(0);
  const entry = value[0];
  const patch = (p: Partial<Channel>) => { if (entry) onChange([{ ...entry, ...p }]); };
  async function load() {
    const version = ++requestVersion.current;
    setTargets(null); setMessage("공시 노출을 읽고 있습니다.");
    try { const result = await getJson<Targets>(`/api/macro/policies/targets/${encodeURIComponent(ticker.trim())}`); if (version !== requestVersion.current) return; setTargets(result); setMessage(result.profile?.items.length ? "이 정책 경로와 직접 이어지는 공시 문장만 선택하세요." : "저장된 공시 노출이 없습니다. 기업 정보에서 공시를 먼저 확인하세요."); }
    catch { if (version !== requestVersion.current) return; setMessage("기업의 공시 노출을 읽지 못했습니다."); }
  }
  return <details><summary>기업에 전달되는 경로 기록 (선택)</summary><p>공식 발표의 전달 근거와 기업 공시의 해당 문장을 직접 대조하세요.</p>
    {!entry ? <button className="btn" type="button" onClick={() => onChange([{ channel: "financing_cost", explanation: "", sourceRef: { ...source } }])}>전달 경로 추가</button> : <>
      <label>전달 경로<select value={entry.channel} onChange={e => patch({ channel: e.target.value, companyLink: undefined })}>{Object.entries(CHANNELS).map(([v, l]) => <option value={v} key={v}>{l}</option>)}</select></label>
      <label>어떤 조건에서 어떻게 전달되나요?<textarea required value={entry.explanation} onChange={e => patch({ explanation: e.target.value })} /></label>
      <label>이 경로를 뒷받침하는 공식 원문 링크<input type="url" required value={entry.sourceRef.url} onChange={e => patch({ sourceRef: { ...entry.sourceRef, url: e.target.value } })} /></label>
      <label>전달 경로의 원문 제목<input required value={entry.sourceRef.title} onChange={e => patch({ sourceRef: { ...entry.sourceRef, title: e.target.value } })} /></label>
      <label>전달 경로의 원문 인용<textarea required value={entry.sourceRef.quote} onChange={e => patch({ sourceRef: { ...entry.sourceRef, quote: e.target.value } })} /></label>
      <label>연결할 기업 (선택)<input value={ticker} onChange={e => { requestVersion.current++; setTicker(e.target.value); setTargets(null); setMessage(""); patch({ companyLink: undefined }); }} /></label>
      <button type="button" className="btn" onClick={() => void load()} disabled={!ticker.trim()}>저장된 공시 노출 찾기</button><p role="status">{message}</p>
      {targets?.profile && <label>정책과 직접 연결되는 공시 문장<select value={entry.companyLink?.exposureId || ""} onChange={e => patch({ companyLink: e.target.value ? { ticker: targets.profile!.ticker, profileId: targets.profile!.profileId, exposureId: e.target.value } : undefined })}><option value="">연결하지 않음</option>{targets.profile.items.map(item => <option key={item.id} value={item.id}>{FACTOR_LABELS[item.factor]}: {item.quote}</option>)}</select></label>}
      {entry.companyLink && <blockquote>{targets?.profile?.items.find(r => r.id === entry.companyLink?.exposureId)?.quote}</blockquote>}
      {entry.companyLink && targets?.reason && <><label>내가 쓴 조건과 연결 (선택)<select value={entry.companyLink.condition?.index ?? ""} onChange={e => patch({ companyLink: { ...entry.companyLink!, condition: e.target.value === "" ? undefined : { revisionId: targets.reason!.revisionId, index: Number(e.target.value), overlapQuote: "" } } })}><option value="">연결하지 않음</option>{targets.reason.conditions.map((q, i) => <option key={i} value={i}>{q}</option>)}</select></label>
        {entry.companyLink.condition && <label>내 조건과 위 전달 설명에 그대로 들어 있는 공통 표현<input required value={entry.companyLink.condition.overlapQuote} onChange={e => patch({ companyLink: { ...entry.companyLink!, condition: { ...entry.companyLink!.condition!, overlapQuote: e.target.value } } })} /></label>}<p>내 조건은 개인 가설로 연결하며 공시의 근거로 쓰지 않습니다.</p></>}
      <button className="btn" type="button" onClick={() => { requestVersion.current++; onChange([]); setTargets(null); setMessage(""); }}>전달 경로 빼기</button>
    </>}
  </details>;
}

export function ChannelSummary({ channels }: { channels: Channel[] }) {
  return <>{channels.map((c, i) => <div key={i}><h4>{CHANNELS[c.channel]}</h4><p>{c.explanation}</p><a href={c.sourceRef.url} target="_blank" rel="noreferrer">{c.sourceRef.title}</a><blockquote>{c.sourceRef.quote}</blockquote>{c.resolvedCompanyLink && <><p><a href={`#/watchlist/${encodeURIComponent(c.resolvedCompanyLink.ticker)}`}>{c.resolvedCompanyLink.ticker} 공시 노출</a></p><blockquote>{c.resolvedCompanyLink.quote}</blockquote>{c.resolvedCompanyLink.condition && <p>연결한 내 조건(가설): {c.resolvedCompanyLink.condition.quote}</p>}</>}</div>)}</>;
}
