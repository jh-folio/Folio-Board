import { useEffect, useState } from "react";
import { getJson, postJson } from "../../api";

import { PolicyChannelFields, ChannelSummary, type Channel } from "./PolicyChannelFields";

type Source = { url: string; title: string; kind: string; quote: string };
type Draft = { channels?: Channel[]; title: string; policyType: string; jurisdiction: string; status: string; sourceRef: Source; counterConditions: string; nextCheckpoint: string; announcedAt: string | null; effectiveFrom: string | null; effectiveTo: string | null };
type Preview = { draft: Draft; previewId: string; notice: string; resolvedLinks?: (Channel["resolvedCompanyLink"] | null)[] };
type Event = Draft & { id: string };
const TYPES: Record<string, string> = { central_bank_rate: "기준금리 결정", central_bank_balance_sheet: "중앙은행 자산", fiscal_spending: "재정 지출", tax: "세금", tariff: "관세", subsidy: "보조금", regulation: "규제", export_control: "수출 통제" };
const STATUS: Record<string, string> = { proposed: "제안", announced: "발표", enacted: "법제화", effective: "시행", suspended: "중단", withdrawn: "철회" };
const EMPTY: Draft = { title: "", policyType: "central_bank_rate", jurisdiction: "US", status: "announced", sourceRef: { url: "", title: "", kind: "central_bank", quote: "" }, counterConditions: "", nextCheckpoint: "", announcedAt: null, effectiveFrom: null, effectiveTo: null };

export function PolicyEvents() {
  const [events, setEvents] = useState<Event[]>([]);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => { let live = true; getJson<{ items: Event[] }>("/api/macro/policies").then(r => { if (live) setEvents(r.items); }).catch(() => { if (live) setMessage("정책 기록을 읽지 못했습니다."); }); return () => { live = false; }; }, []);
  const patch = (value: Partial<Draft>) => { setDraft(d => ({ ...d, ...value })); setPreview(null); setChecked(false); };
  async function submit(save: boolean) {
    setBusy(true); setMessage("");
    try {
      if (save && preview && checked) {
        const event = await postJson<Event>("/api/macro/policies/confirm", { draft: preview.draft, previewId: preview.previewId, userConfirmed: true, officialSourceConfirmed: true });
        setEvents(old => [event, ...old.filter(item => item.id !== event.id)]); setDraft(EMPTY); setPreview(null); setChecked(false); setMessage("정책 기록을 저장했습니다.");
      } else {
        setPreview(await postJson<Preview>("/api/macro/policies/preview", draft));
      }
    } catch { setMessage("저장하지 못했습니다. 공식 원문·진행 단계·반대 조건·다음 확인을 확인해 주세요."); }
    finally { setBusy(false); }
  }
  return <section className="surface macro-state-card"><h2>정책 변화 기록</h2><p>공식 발표 내용을 직접 확인해 남깁니다. 금리 지표나 회의 일정만으로 정책 결정을 만들지 않습니다.</p>
    {events.length === 0 && <p>아직 저장한 정책 변화가 없습니다.</p>}
    {events.map(event => <details key={event.id}><summary>{event.title} · {STATUS[event.status]}</summary><p><a href={event.sourceRef.url} target="_blank" rel="noreferrer">{event.sourceRef.title}</a></p><blockquote>{event.sourceRef.quote}</blockquote><p>성립하지 않을 조건: {event.counterConditions}</p><p>다음 확인: {event.nextCheckpoint}</p><ChannelSummary channels={event.channels || []} /></details>)}
    <details><summary>공식 발표를 기록하기</summary><form className="macro-state-form" onSubmit={e => { e.preventDefault(); void submit(false); }}>
      <label>무슨 변화인가요?<input required maxLength={300} value={draft.title} onChange={e => patch({ title: e.target.value })} /></label>
      <label>시장<select value={draft.jurisdiction} onChange={e => patch({ jurisdiction: e.target.value })}><option value="US">미국</option><option value="KR">한국</option></select></label>
      <label>정책 종류<select value={draft.policyType} onChange={e => patch({ policyType: e.target.value })}>{Object.entries(TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>진행 단계<select value={draft.status} onChange={e => patch({ status: e.target.value })}>{Object.entries(STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>공식 발표 제목<input required value={draft.sourceRef.title} onChange={e => patch({ sourceRef: { ...draft.sourceRef, title: e.target.value } })} /></label>
      <label>공식 원문 링크<input required type="url" placeholder="https://…" value={draft.sourceRef.url} onChange={e => patch({ sourceRef: { ...draft.sourceRef, url: e.target.value } })} /></label>
      <label>발표 기관 종류<select value={draft.sourceRef.kind} onChange={e => patch({ sourceRef: { ...draft.sourceRef, kind: e.target.value } })}>{Object.entries({ central_bank: "중앙은행", government: "정부 기관", gazette: "관보", legislation: "법령", company_filing: "기업 공시" }).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>원문에서 확인한 문장<textarea required value={draft.sourceRef.quote} onChange={e => patch({ sourceRef: { ...draft.sourceRef, quote: e.target.value } })} /></label>
      <label>발표일 (모르면 비워 둠)<input type="date" value={draft.announcedAt || ""} onChange={e => patch({ announcedAt: e.target.value || null })} /></label>
      <label>시행 시작일 (모르면 비워 둠)<input type="date" value={draft.effectiveFrom || ""} onChange={e => patch({ effectiveFrom: e.target.value || null })} /></label>
      <label>시행 종료일 (모르면 비워 둠)<input type="date" value={draft.effectiveTo || ""} onChange={e => patch({ effectiveTo: e.target.value || null })} /></label>
      <label>이 영향이 성립하지 않을 조건<textarea required value={draft.counterConditions} onChange={e => patch({ counterConditions: e.target.value })} /></label>
      <label>다음에 무엇을 확인할까요?<textarea required value={draft.nextCheckpoint} onChange={e => patch({ nextCheckpoint: e.target.value })} /></label>
      <PolicyChannelFields value={draft.channels || []} source={draft.sourceRef} onChange={channels => patch({ channels })} />
      <button className="btn" disabled={busy} type="submit">기록 미리보기</button>
    </form>
    {preview && <div className="surface macro-state-card"><h3>{preview.draft.title} · {STATUS[preview.draft.status]}</h3><blockquote>{preview.draft.sourceRef.quote}</blockquote><p>반대 조건: {preview.draft.counterConditions}</p><p>다음 확인: {preview.draft.nextCheckpoint}</p><ChannelSummary channels={(preview.draft.channels || []).map((c, i) => ({ ...c, resolvedCompanyLink: preview.resolvedLinks?.[i] || undefined }))} /><p>{preview.notice}</p><label><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} /> 공식 원문과 내용·날짜·진행 단계를 대조했습니다.</label><button className="btn btn--primary" disabled={!checked || busy} onClick={() => void submit(true)}>확인한 내용 저장</button></div>}
    </details><p role="status">{message}</p>
  </section>;
}
