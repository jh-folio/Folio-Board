import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { RouteHero } from "../RouteHero";
import { MacroMap } from "./MacroMap";
import { lastMacroView, shortKst, tinyLabel } from "./types";
import { PolicyEvents } from "./PolicyEvents";

const AXES: Record<string, string> = { growth: "경기", inflation: "물가", financial_conditions: "금융여건", stress_vulnerability: "위험" };
const WORDS: Record<string, string> = {
  contraction: "위축", weak: "약함", moderate: "중간", strong: "강함", unknown: "확인 자료 부족",
  high: "높음", above_reference: "참고 기준 위", near_reference: "참고 기준 부근", below_reference: "참고 기준 아래",
  tight: "긴축적", neutral: "중립", loose: "완화적", elevated: "다소 높음", normal: "보통",
  rising: "상승", falling: "하락", flat: "변화 작음", mixed: "방향 엇갈림",
  none: "뚜렷한 전환 신호 없음", contraction_warning: "위축 경고", contraction_confirmed: "위축 확인",
  recovery_signal: "회복 신호", recovery_confirmed: "회복 확인",
  agrees: "보조 지표와 일치", strongly_agrees: "보조 지표와 강하게 일치", disagrees: "보조 지표와 불일치", not_available: "보조 확인 자료 없음",
  medium: "중간", low: "낮음", current: "관측기간 최신", stale: "관측기간 오래됨",
};
const CONFLICTS: Record<string, string> = { growthDirectionDisagreement: "생산·고용 지표의 변화 방향이 서로 다릅니다.", growthLevelDisagreement: "GDP와 산업생산이 경기의 강도를 다르게 가리킵니다.", auxiliaryInflationDisagreement: "주 물가 지표와 보조 CPI가 서로 다른 수준을 가리킵니다.", financialDirectionDisagreement: "실효금리와 금융여건 지표의 방향이 엇갈립니다.", fxContext: "원/달러 환율 변화를 금융여건의 보조 맥락으로 함께 확인합니다.", auxiliaryIntegrityConflict: "보조 지표의 원천 값 또는 판본에 충돌이 있습니다." };
const word = (value: string) => WORDS[value] || value;
type Snapshot = { snapshotId: string; inputFingerprint: string; asOf: string; level: string; direction: string; promotion: string; confidence: string; freshness: string; cycleSignal?: string; cycleSignalBasis?: { cycleCorroboration: string }; conflicts: { kind: string; signals?: Record<string, string | number>; seriesId?: string; changePercent?: string }[]; unknownReason: { seriesId: string; period: string; reason: string }[]; sourceRefs: { seriesId: string; period: string; value: string | null; availableAt: string }[] };
type StateResult = { market: string; date: string; cards: { axis: string; snapshot: Snapshot | null; previous: Snapshot | null }[]; notice: string; inflationLimitation: string; nextCheckpoints?: Record<string, { date: string; basis: string; sourceUrl: string }> };

function CurrentState() {
  const [market, setMarket] = useState("US");
  const [date, setDate] = useState("");
  const [data, setData] = useState<StateResult | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true; setData(null); setError("");
    getJson<StateResult>(`/api/macro/state?market=${market}${date ? `&date=${date}` : ""}`).then(value => { if (live) setData(value); }).catch(() => { if (live) setError("거시 기록을 읽지 못했습니다. 날짜를 확인하거나 다시 열어 주세요."); });
    return () => { live = false; };
  }, [market, date]);
  return <section className="macro-state-stack" aria-label="거시 현재 상태">
    <div className="macro-state-toolbar"><div className="segment" role="group" aria-label="거시 상태 시장">{["US", "KR"].map(value => <button key={value} aria-pressed={market === value} onClick={() => setMarket(value)}>{value === "US" ? "미국" : "한국"}</button>)}</div><label>기준일 <input type="date" value={date} onChange={e => setDate(e.target.value)} /></label></div>
    <p>저장된 관측 자료의 요약입니다. 처음 기록하려면 <a href={lastMacroView()}>거시 지도</a>에서 ‘지금 갱신’을 실행하세요.</p>
    {error && <p role="alert">{error}</p>}{!data && !error && <p role="status">저장된 거시 상태를 읽고 있습니다.</p>}
    {data && <><p>{data.notice}</p>{data.cards.map(({ axis, snapshot: s, previous }) => <article className="surface macro-state-card" key={axis}>
      <header><h2>{AXES[axis]}</h2><span className="chip">{s?.promotion === "primary" ? "기준 통과 요약" : "시험 표시"}</span></header>
      {!s ? <p>이 기준일에 저장된 기록이 없습니다.</p> : <>
        {s.cycleSignal && <p><strong>국면 신호: {word(s.cycleSignal)}</strong> · 시험 표시<br />{word(s.cycleSignalBasis?.cycleCorroboration || "not_available")}</p>}
        <p className="macro-state-reading"><strong>{word(s.level)}</strong> · {word(s.direction)}</p>
        <p>자료 신뢰도 {word(s.confidence)} · {word(s.freshness)} · 기록 {shortKst(s.asOf)}</p>
        {axis === "inflation" && market === "US" && <p>{data.inflationLimitation}</p>}
        <p>이전 월말과 비교: {previous ? `${word(previous.level)} · ${word(previous.direction)} (${shortKst(previous.asOf)})` : "저장 기록 없음"}</p>
        {s.conflicts.length > 0 && <ul>{s.conflicts.map((conflict, index) => <li key={index}>{CONFLICTS[conflict.kind] || "입력 지표의 상충 경로를 확인하세요."}{conflict.signals && <span> {Object.entries(conflict.signals).map(([key, value]) => `${tinyLabel(key)}: ${word(String(value))}`).join(" · ")}</span>}{conflict.changePercent && <span> 변화 {conflict.changePercent}%</span>}</li>)}</ul>}
        {market === "KR" && axis === "stress_vulnerability" && <p>한국 신용/GDP는 구조적 취약성의 참고 자료이며 빠른 스트레스 신호가 아닙니다.</p>}
        <details><summary>계산에 쓴 원자료와 확인하지 못한 항목</summary>
          <ul>{s.unknownReason.map((gap, i) => <li key={i}>{tinyLabel(gap.seriesId)} {gap.period}: 자료 또는 비교 구간을 확인하지 못했습니다.</li>)}</ul>
          <div className="macro-state-source-list">{s.sourceRefs.map((ref, i) => <p key={i}><a href={`#/macro/map?market=${market}&series=${encodeURIComponent(ref.seriesId)}`}>{tinyLabel(ref.seriesId)}</a> · {ref.period} · {ref.value ?? "값 없음"} · 가용 {shortKst(ref.availableAt)}</p>)}</div>
          <p className="macro-state-identity">기록 ID: {s.snapshotId}</p>
        </details>
      </>}
    </article>)}<section className="surface macro-state-card"><h2>다음 확인 일정</h2>{Object.keys(data.nextCheckpoints || {}).length ? <ul>{Object.entries(data.nextCheckpoints || {}).map(([key, value]) => <li key={key}>{tinyLabel(key)} · {value.date} · {value.basis === "customary_estimate" ? "관행일 추정" : "발표 일정"}{value.sourceUrl && <> · <a href={value.sourceUrl} target="_blank" rel="noreferrer">일정 출처</a></>}</li>)}</ul> : <p>이 기준일에 알고 있던 다음 발표 일정이 없습니다. 날짜를 임의로 예상하지 않습니다.</p>}</section><PolicyEvents /></>}
  </section>;
}

function ValidationHistory() {
  const [history, setHistory] = useState<{ snapshots?: { id: string; market: string; axis: string; as_of: string }[]; decisions?: { seq: number; market: string; axis: string; promotion: string; created_at: string }[] } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { let live = true; getJson<NonNullable<typeof history>>("/api/macro/state/history").then(r => { if (live) setHistory(r); }).catch(() => { if (live) setError("저장 이력을 읽지 못했습니다."); }); return () => { live = false; }; }, []);
  return <section className="surface macro-state-card"><h2>검증 결과와 해석 범위</h2>
    <p>2026년 9월 29일 동결 평가 · macro-state-1</p>
    <p>공개 평가에서 미국 물가만 기준 통과 요약의 수용 후보가 되었습니다. 이 워크스페이스의 실제 수용 상태는 ‘현재 상태’ 카드에 표시합니다. 검증 구간 B1 대비 이탈 차이는 4.76%p로 한도 5%p에 가깝습니다.</p>
    <ul><li>경기: 방향 수정 이탈과 오경보 기간이 기준을 넘었습니다.</li><li>국면 신호: 헛경고 3건·헛회복 2건으로 시험 표시를 유지합니다.</li><li>금융여건: 수정 이탈과 완화 판정 쏠림으로 시험 표시를 유지합니다.</li><li>미국 빠른 스트레스·한국 전 축: 시험 표시 대상입니다.</li></ul>
    <h3>이 워크스페이스의 수용·저장 이력</h3>{error && <p role="alert">{error}</p>}{!history && !error && <p role="status">이력을 읽고 있습니다.</p>}
    {history && <><p>수용 결정 {history.decisions?.length || 0}건 · 최근 저장 기록 {history.snapshots?.length || 0}건</p><ul>{history.decisions?.map(r => <li key={r.seq}>{r.market} {AXES[r.axis]} · {r.promotion === "primary" ? "기준 통과 요약 수용" : "시험 표시 유지"} · {shortKst(r.created_at)}</li>)}</ul><details><summary>최근 저장 기록 보기</summary><ul>{history.snapshots?.map(r => <li key={r.id}>{r.market} {AXES[r.axis]} · {shortKst(r.as_of)}</li>)}</ul></details></>}
    <p>개발 이후 규칙을 동결하고 검증·최종 시험을 분리했습니다. 최종 시험은 한 번만 실행했습니다. 시험 표시를 예측이나 투자 지침으로 읽지 마세요.</p>
  </section>;
}

export function MacroRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const sync = () => {
      const current = window.location.hash;
      if (current.startsWith("#/market-memory/macro")) { window.location.replace(current.replace("#/market-memory/macro", "#/macro/map")); return; }
      if (current === "#/macro" || current === "#/macro/") { window.location.replace(lastMacroView()); return; }
      setHash(current);
    };
    sync(); window.addEventListener("hashchange", sync); return () => window.removeEventListener("hashchange", sync);
  }, []);
  const active = hash.startsWith("#/macro/state") ? "state" : hash.startsWith("#/macro/validation") ? "validation" : "map";
  return <div className="macro-state-stack"><RouteHero eyebrow="Market & Macro" title="시장·거시" description="공식 지표의 변화와 공시에서 확인한 전달 경로를 살펴봅니다." />
    <div className="segment memory-tabs" role="group" aria-label="시장·거시 하위 보기">{[["state", "현재 상태"], ["map", "거시 지도"], ["validation", "검증 이력"]].map(([id, label]) => <button key={id} aria-pressed={active === id} onClick={() => { window.location.hash = id === "map" ? lastMacroView() : `#/macro/${id}`; }}>{label}</button>)}</div>
    {active === "map" ? <MacroMap /> : active === "state" ? <CurrentState /> : <ValidationHistory />}
  </div>;
}
