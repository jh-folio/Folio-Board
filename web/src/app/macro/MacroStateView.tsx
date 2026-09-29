import { useEffect, useId, useState } from "react";
import { getJson } from "../../api";
import type { MacroItem, MacroSnapshot } from "./types";
import { fixed, lastMacroView, longDate, shortKst, tinyLabel } from "./types";
import {
  AXIS_ORDER, AXIS_VIEW, CONFIDENCE, CORROBORATION, CYCLE_STEPS, CYCLE_WORDS, HOLD,
  conflictText, criteria, directionWord, levelWord, scaleMarks, summaryPart,
  type AxisKey, type Market,
} from "./stateWords";

type SourceRef = { seriesId: string; period: string; value: string | null; availableAt: string };
type Gap = { seriesId: string; period: string; reason: string };
type Snapshot = {
  snapshotId: string; asOf: string; level: string; direction: string; promotion: string; confidence: string; freshness: string;
  cycleSignal?: string; cycleSignalPromotion?: string;
  cycleSignalBasis?: { cycleCorroboration?: string; unknownReason?: Gap[]; conditions?: Record<string, boolean | null> };
  conflicts: { kind: string; signals?: Record<string, string | number> }[];
  unknownReason: Gap[]; sourceRefs: SourceRef[];
};
type StateResult = {
  market: Market; date: string; notice: string; inflationLimitation: string;
  cards: { axis: AxisKey; snapshot: Snapshot | null }[];
  nextCheckpoints?: Record<string, { date: string; basis: string; sourceUrl: string }>;
};

const MARKET_NAME: Record<Market, string> = { US: "미국", KR: "한국" };

/** 검증 칩. 내부 값(primary/shadow)은 그대로 두고 화면 이름만 짧게 쓴다. */
function VerifyChip({ passed }: { passed: boolean }) {
  return <span className="chip macro-now__chip" data-tone={passed ? "gold" : "muted"}>{passed ? "검증 통과" : "검증 중"}</span>;
}

/** 화살표는 눈금 위에서 움직인 쪽이다: ↗ 오른쪽 칸 쪽, ↘ 왼쪽 칸 쪽. */
function DirIcon({ axis, direction }: { axis: AxisKey; direction: string | undefined }) {
  const right = AXIS_VIEW[axis].rightward;
  const moving = direction === "rising" || direction === "falling" ? (direction === right ? "right" : "left") : direction;
  const path = moving === "right" ? "M4 13L13 4M7 4h6v6" : moving === "left" ? "M4 5l9 9M7 14h6V8"
    : moving === "mixed" ? "M3 9h5M8 9l6-5M8 9l6 5" : moving === "flat" ? "M4 9h10" : "";
  if (!path) return null;
  return <svg viewBox="0 0 18 18" aria-hidden="true" data-moving={moving}><path d={path} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function Scale({ axis, market, level, compare }: { axis: AxisKey; market: Market; level?: string; compare?: string }) {
  const view = AXIS_VIEW[axis];
  const marks = scaleMarks(axis, market);
  const known = view.levels.includes(level || "");
  const label = `${view.name} ${known ? levelWord(axis, level) : HOLD}. ${view.levels.map(l => view.words[l]).join(", ")} 중, 기준 ${marks.midLabel}${compare ? `. 기준일 ${levelWord(axis, compare)}` : ""}`;
  return <div className="macro-scale" role="img" aria-label={label} data-unknown={known ? undefined : "true"}>
    <div className="macro-scale__cells">
      {view.levels.map(l => <span key={l} aria-current={l === level ? "true" : undefined} data-compare={l === compare ? "true" : undefined}>{view.words[l]}</span>)}
    </div>
    <span className="macro-scale__mid" style={{ left: `${marks.mid}%` }}><b>{marks.midLabel}</b></span>
    {marks.cuts.map(([at, text]) => <span key={text} className="macro-scale__cut" style={{ left: `${at}%` }}>{text}</span>)}
  </div>;
}


/** 최신 원장의 참고값은 저장 판정의 입력과 구분한다. */
/** 지표 이름. 실효 연방기금금리는 중앙은행 기준금리와 구분해 "시장 금리"라 부른다. */
const seriesName = (id: string) => (id === "DFF" ? "시장 금리" : tinyLabel(id));

// 판정에 직접 쓰는 지표를 앞에, 참고 지표를 뒤에 둔다. 금리는 3개월 비교 줄이 대신 말한다.
const MAIN_FIRST: Record<AxisKey, string[]> = {
  growth: ["GDPC1", "INDPRO", "UNRATE", "KR_GDP", "KR_IP", "KR_UNRATE"],
  inflation: ["PCEPILFE", "KR_CPI"],
  financial_conditions: ["NFCI", "KR_USDKRW"],
  stress_vulnerability: ["STLFSI4", "KR_SPREAD"],
};
const REFERENCE_ONLY = new Set(["CPIAUCSL", "KR_USDKRW", "KR_CREDIT"]);
const SKIP = new Set(["DFF", "KR_RATE"]);

const refsOf = (s: Snapshot | null, id: string) => (s?.sourceRefs || []).filter(ref => ref.seriesId === id).sort((a, b) => a.period.localeCompare(b.period));

/** 최신 거시 지도의 참고 숫자. 저장 판정 계산에 사용한 값이라는 뜻은 아니다. */
function facts(axis: AxisKey, map: MacroItem[]): string[] {
  const parts: string[] = [];
  const order = MAIN_FIRST[axis];
  const rows = map.filter(row => row.series.axis === axis && row.headline && !SKIP.has(row.series.id))
    .sort((a, b) => (order.indexOf(a.series.id) + 1 || 99) - (order.indexOf(b.series.id) + 1 || 99));
  for (const item of rows) {
    const h = item.headline!;
    const unit = h.unit === "%" || h.unit === "%p" ? h.unit : h.unit === "원" ? "원" : "";
    const measure = [h.measure && h.measure !== "수준" ? h.measure : "", REFERENCE_ONLY.has(item.series.id) ? "참고" : ""].filter(Boolean).join(", ");
    parts.push(`${seriesName(item.series.id)} ${fixed(h.value, h.digits)}${unit}${measure ? `(${measure})` : ""}`);
    if (axis === "inflation" && order.includes(item.series.id) && h.spark && h.spark.length > 3) {
      const past = h.spark[h.spark.length - 4][1];
      if (past != null) parts.push(`3개월 전 ${fixed(past, h.digits)}%`);
    }
  }
  return parts;
}

function savedComparisons(axis: AxisKey, s: Snapshot | null): string[] {
  const parts: string[] = [];
  if (!s) return parts;
  for (const id of ["NFCI", "STLFSI4"]) {
    const refs = refsOf(s, id);
    if (refs.length >= 2 && refs[0].value != null && refs[refs.length - 1].value != null)
      parts.push(`${seriesName(id)} ${fixed(Number(refs[0].value), 2)}에서 ${fixed(Number(refs[refs.length - 1].value), 2)}로(4주)`);
  }
  if (axis === "financial_conditions" && s) {
    for (const id of ["DFF", "KR_RATE"]) {
      const refs = refsOf(s, id);
      if (refs.length >= 2) parts.push(`${id === "DFF" ? "시장 금리(실효 연방기금금리)" : "기준금리"} ${fixed(Number(refs[0].value), 2)}%에서 ${fixed(Number(refs[refs.length - 1].value), 2)}%로(3개월)`);
    }
  }
  return parts;
}

function Evidence({ s }: { s: Snapshot }) {
  const bySeries = new Map<string, SourceRef[]>();
  for (const ref of s.sourceRefs) bySeries.set(ref.seriesId, [...(bySeries.get(ref.seriesId) || []), ref]);
  const rows = [...bySeries].map(([id, refs]) => {
    const sorted = [...refs].sort((a, b) => a.period.localeCompare(b.period));
    return { id, latest: sorted[sorted.length - 1], count: sorted.length };
  });
  return <div className="surface surface--inset macro-now__evidence">
    <table>
      <thead><tr><th scope="col">지표</th><th scope="col">최근 관측</th><th scope="col">값</th><th scope="col">쓸 수 있게 된 때</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.id}>
        <td>{tinyLabel(row.id)}{row.count > 1 && <small> 외 {row.count - 1}개 관측</small>}</td>
        <td>{row.latest.period}</td><td>{row.latest.value ?? "값 없음"}</td><td>{shortKst(row.latest.availableAt)}</td>
      </tr>)}</tbody>
    </table>
    {s.unknownReason.length > 0 && <p>확인하지 못한 자료: {s.unknownReason.map(gap => `${tinyLabel(gap.seriesId)} ${gap.period}`).join(" · ")}</p>}
    <p>신뢰도 {CONFIDENCE[s.confidence] || s.confidence}{s.freshness === "stale" ? " · 관측이 오래됨" : ""} · 기록 {shortKst(s.asOf)} · 기록 ID {s.snapshotId}</p>
  </div>;
}

function AxisRow({ axis, market, s, compare, map, limitation }: { axis: AxisKey; market: Market; s: Snapshot | null; compare?: { s: Snapshot | null; date: string }; map: MacroItem[]; limitation: string }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const view = AXIS_VIEW[axis];
  const numbers = facts(axis, map);
  const savedNumbers = savedComparisons(axis, s);
  const conflicts = (s?.conflicts || []).map(c => conflictText(c.kind, c.signals, seriesName)).filter(Boolean);
  return <li className="macro-now__row">
    <div className="macro-now__name"><b>{view.name}</b><small>{view.measure}</small><VerifyChip passed={s?.promotion === "primary"} /></div>
    <Scale axis={axis} market={market} level={s?.level} compare={compare?.s?.level} />
    <span className="macro-now__dir"><DirIcon axis={axis} direction={s?.direction} />{s ? directionWord(axis, s.direction) : HOLD}</span>
    {s && <button type="button" className="btn btn--text btn--sm macro-now__toggle" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(v => !v)}>계산 근거</button>}
    <div className="macro-now__text">
      {!s && <p className="macro-now__facts">저장된 기록이 없습니다.</p>}
      {s && savedNumbers.length > 0 && <p className="macro-now__facts">저장 판정의 입력 · {savedNumbers.join(" · ")}</p>}
      {s && numbers.length > 0 && <p className="macro-now__facts">최신 참고값 · {numbers.join(" · ")}<small>거시 지도의 최신 자료이며 {shortKst(s.asOf)} 저장 판정의 입력과 다를 수 있습니다.</small></p>}
      {conflicts.length > 0 && <p className="macro-now__conflict">{conflicts.join(" · ")}</p>}
      {compare && <p className="macro-now__compare">기준일 {longDate(compare.date)} · {compare.s ? `${levelWord(axis, compare.s.level)} · ${directionWord(axis, compare.s.direction)} (${shortKst(compare.s.asOf)} 기록)` : "그 날짜 이전에 저장된 기록이 없습니다"}</p>}
      <p className="macro-now__criteria"><b>기준</b> · {criteria(axis, market)}{axis === "inflation" && s?.promotion === "primary" && limitation ? " 검증 여유가 작았습니다(한도 5%p 중 4.76%p)." : ""}</p>
      {s && open && <div id={panelId}><Evidence s={s} /></div>}
    </div>
  </li>;
}

// 경기 전환 신호의 네 조건. 규칙이 넷을 하나로 합치면 불명 하나가 전체를 "판단 보류"로 만들므로,
// 화면은 조건마다 없음·켜짐·판단 보류를 따로 보인다(규칙과 저장 값은 그대로).
const CYCLE_CONDITIONS: [string, string][] = [["W", "수축 경고"], ["K", "수축 확인"], ["R", "회복 신호"], ["Q", "회복 확인"]];

/** 받침 있는 말 뒤는 "은", 없으면 "는". */
const topic = (word: string) => {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? "은" : "는";
};

function gapReason(gaps: Gap[]): string {
  if (!gaps.length) return "자료가 부족해";
  return `${gaps.map(gap => gap.reason === "officiallyNotPublished" ? `${gap.period.slice(0, 7)} ${tinyLabel(gap.seriesId)}이 공식 발표되지 않아` : `${tinyLabel(gap.seriesId)} ${gap.period.slice(0, 7)} 자료가 없어`).join(", ")} 최근 1년 안의 수축 여부를 가릴 수 없어`;
}

/** 네 축과 성격이 다른 경보 칸: 침체·회복이 시작됐는지. 평소엔 조용하고, 켜지면 금색으로 강조한다. */
function CycleStrip({ s }: { s: Snapshot }) {
  const basis = s.cycleSignalBasis || {};
  const conditions = basis.conditions || {};
  const known = CYCLE_CONDITIONS.some(([key]) => key in conditions);
  const unavailable = !known || (s.cycleSignal === "unknown" && (basis.unknownReason || []).some(gap => gap.reason === "asOfVintageUnavailable"));
  const state = (key: string) => conditions[key] === true ? "on" : conditions[key] === false ? "off" : "hold";
  const names = (value: string) => CYCLE_CONDITIONS.filter(([key]) => state(key) === value).map(([, name]) => name);
  const on = names("on"), off = names("off"), hold = names("hold");
  const join = (items: string[]) => items.join("·");
  const corroboration = CORROBORATION[basis.cycleCorroboration || "not_available"];
  return <section className="surface surface--inset macro-cycle" aria-labelledby="macro-cycle-title" data-active={on.length ? "true" : undefined}>
    <div className="macro-cycle__head">
      <h3 id="macro-cycle-title">경기 전환 신호</h3>
      <small>침체나 회복이 시작됐는지 확인하는 경보</small>
      <VerifyChip passed={s.cycleSignalPromotion === "primary"} />
    </div>
    {unavailable
      ? <p className="macro-cycle__note">이 기록 시점에는 당시 발표된 실업수당 청구 자료가 없어 전환 신호를 계산하지 않았습니다.</p>
      : <>
        <ol className="macro-cycle__steps">{CYCLE_CONDITIONS.map(([key, name]) => <li key={key} data-state={state(key)}>
          <b>{name}</b><span>{state(key) === "on" ? "켜짐" : state(key) === "off" ? "없음" : "판단 보류"}</span>
        </li>)}</ol>
        <p className="macro-cycle__note">
          {on.length > 0 && <><b>{join(on)}</b> 신호가 켜졌습니다{corroboration && `(${corroboration})`}. </>}
          {off.length > 0 && <>지금 {join(off)}{topic(off[off.length - 1])} 없습니다. </>}
          {hold.length > 0 && <>{join(hold)}{topic(hold[hold.length - 1])} {gapReason(basis.unknownReason || [])} 판단 보류입니다. </>}
          이미 나타난 신호의 확인이지 예측이 아닙니다.
        </p>
      </>}
  </section>;
}

function nextLine(next: StateResult["nextCheckpoints"]): string {
  const byDate = new Map<string, string[]>();
  for (const [id, item] of Object.entries(next || {})) byDate.set(item.date, [...(byDate.get(item.date) || []), tinyLabel(id)]);
  return [...byDate].sort(([a], [b]) => a.localeCompare(b)).map(([date, ids]) => `${Number(date.slice(5, 7))}/${Number(date.slice(8, 10))} ${ids.join("·")}`).join(" · ");
}

export function CurrentState() {
  const [market, setMarket] = useState<Market>("US");
  const [data, setData] = useState<StateResult | null>(null);
  const [map, setMap] = useState<MacroItem[]>([]);
  const [error, setError] = useState("");
  const [comparing, setComparing] = useState(false);
  const [date, setDate] = useState("");
  const [compare, setCompare] = useState<StateResult | null>(null);
  const [compareError, setCompareError] = useState("");

  useEffect(() => {
    let live = true; setData(null); setError(""); setMap([]);
    getJson<StateResult>(`/api/macro/state?market=${market}`).then(value => { if (live) setData(value); })
      .catch(() => { if (live) setError("거시 기록을 읽지 못했습니다. 잠시 뒤 다시 열어 주세요."); });
    // 숫자는 거시 지도와 같은 머리 숫자를 쓴다. 못 읽어도 판정은 그대로 보인다.
    getJson<MacroSnapshot>(`/api/macro?market=${market}&mode=latest_revised&view=summary`).then(value => { if (live) setMap(value.items || []); }).catch(() => undefined);
    return () => { live = false; };
  }, [market]);

  useEffect(() => {
    let live = true; setCompare(null); setCompareError("");
    if (!comparing || !date) return;
    getJson<StateResult>(`/api/macro/state?market=${market}&date=${date}`).then(value => { if (live) setCompare(value); })
      .catch(() => { if (live) setCompareError("기준일 기록을 읽지 못했습니다."); });
    return () => { live = false; };
  }, [market, date, comparing]);

  const cards = new Map((data?.cards || []).map(card => [card.axis, card.snapshot]));
  const compareCards = new Map((compare?.cards || []).map(card => [card.axis, card.snapshot]));
  const anySnapshot = [...cards.values()].some(Boolean);
  const compareAny = [...compareCards.values()].some(Boolean);
  const latestAsOf = [...cards.values()].filter(Boolean).map(s => s!.asOf).sort().pop();
  const parts = AXIS_ORDER.map(axis => summaryPart(axis, cards.get(axis)?.level, cards.get(axis)?.direction));
  const growthSignal = cards.get("growth")?.cycleSignal || "";
  const activeCycle = CYCLE_STEPS.includes(growthSignal) ? growthSignal : "";
  const next = nextLine(data?.nextCheckpoints);

  return <section className="cockpit-panel macro-panel macro-now" aria-label="거시 현재 상태">
    <div className="cockpit-panel__head">
      <div><span>Macro State</span><h2>{MARKET_NAME[market]} 현재 상태</h2>
        <p className="macro-asof">{latestAsOf ? <><b>{shortKst(latestAsOf)}</b><span className="macro-asof__text">기록 · 발표된 자료 기준</span></> : <span className="macro-asof__text">저장된 기록 기준</span>}</p>
      </div>
      <div className="macro-controls">
        <div className="segment" role="group" aria-label="거시 상태 시장">{(["US", "KR"] as Market[]).map(value => <button key={value} type="button" aria-pressed={market === value} onClick={() => setMarket(value)}>{MARKET_NAME[value]}</button>)}</div>
        <button type="button" className="btn btn--sm" aria-pressed={comparing} onClick={() => setComparing(v => !v)}>{comparing ? "비교 끄기" : "날짜와 비교"}</button>
      </div>
    </div>

    {comparing && <div className="macro-now__compare-bar">
      <label className="macro-date">기준일 <input type="date" value={date} max={data?.date} onChange={e => setDate(e.target.value)} /></label>
      <p className="macro-foot">그 날짜 이전의 가장 최근 월말 기록과 지금을 나란히 보여 줍니다. 칸 테두리가 기준일 위치입니다.</p>
      {compareError && <p role="alert" className="macro-foot">{compareError}</p>}
      {date && compare && !compareAny && <p role="status" className="macro-notice">{longDate(date)} 이전에 저장된 기록이 없습니다. 기록은 거시 지도를 갱신할 때마다 쌓입니다.</p>}
    </div>}

    {error && <p role="alert" className="macro-notice">{error}</p>}
    {!data && !error && <div className="macro-skeleton" role="status" aria-label="저장된 거시 상태를 읽고 있습니다"><span className="macro-skeleton__line macro-skeleton__line--title" /><span className="macro-skeleton__line" /><span className="macro-skeleton__line" /><span className="macro-skeleton__line" /></div>}

    {data && !anySnapshot && <p className="macro-notice">아직 저장된 기록이 없습니다. <a href={lastMacroView()}>거시 지도</a>에서 ‘지금 갱신’을 누르면 발표된 자료로 첫 기록을 만듭니다.</p>}

    {data && anySnapshot && <>
      <div className="macro-now__summary">
        <p className="macro-now__answer">{parts.map(part => <span key={part.axis}>{part.subject} <b>{part.level}</b>{part.rest} </span>)}
          {activeCycle && <span>경기 국면 신호는 <b>{CYCLE_WORDS[activeCycle]}</b>입니다.</span>}</p>
        <p className="macro-foot">예측이 아니라 이미 발표된 자료의 요약입니다. 칸 위 ▼는 기준(평균·2% 등)의 위치, 화살표는 최근 3개월(신용 위험은 4주) 방향입니다.</p>
      </div>
      <ul className="macro-now__rows" aria-label="네 가지 판정">
        {AXIS_ORDER.map(axis => <AxisRow key={axis} axis={axis} market={market} s={cards.get(axis) || null} map={map} limitation={data.inflationLimitation}
          compare={comparing && date && compareAny ? { s: compareCards.get(axis) || null, date } : undefined} />)}
      </ul>
      {cards.get("growth")?.cycleSignal && <CycleStrip s={cards.get("growth")!} />}
      <div className="macro-now__legend">
        <span><span className="chip macro-now__chip" data-tone="gold">검증 통과</span> 과거 자료로 미리 정한 기준을 넘었습니다</span>
        <span><span className="chip macro-now__chip" data-tone="muted">검증 중</span> 아직 넘지 못했습니다. 참고로만 보세요</span>
        <a href="#/macro/validation">검증 이력</a>
      </div>
      <p className="macro-foot">{next ? `다음 발표 · ${next}` : "이 기록 시점에 알고 있던 다음 발표 일정이 없습니다."}</p>
    </>}
  </section>;
}

type History = { decisions?: { seq: number; market: string; axis: string; promotion: string; created_at: string }[]; snapshots?: { id: string }[] };

const RESULTS: { name: string; passed: boolean; reason: string; detail: string }[] = [
  { name: "미국 물가", passed: true, reason: "미리 정한 기준을 모두 넘었습니다", detail: "검증 여유가 작았습니다(한도 5%p 중 4.76%p)." },
  { name: "미국 경기", passed: false, reason: "침체가 아닌데 ‘수축’으로 나온 달이 12개월이었습니다", detail: "허용 3개월. 2020년의 짧은 침체 뒤 늦게 꺼진 기간이 대부분입니다. 자료 수정 때 방향이 바뀐 비율도 기준을 넘었습니다." },
  { name: "경기 국면", passed: false, reason: "헛경고 3번 · 헛회복 2번", detail: "허용 2번 · 1번. 2020년에는 수축 경고가 단순 규칙보다 1개월 빨랐습니다." },
  { name: "미국 유동성", passed: false, reason: "거의 항상 ‘풍부’로만 나왔습니다(91%)", detail: "한 칸이 90%를 넘으면 구분하는 힘이 약하다고 봅니다. 자료 수정 때 바뀐 비율도 기준을 넘었습니다." },
  { name: "미국 신용 위험 · 한국 전체", passed: false, reason: "과거 당시 자료가 부족해 시험할 수 없었습니다", detail: "앞으로 쌓이는 기록으로만 확인합니다." },
];
const AXIS_NAME: Record<string, string> = { growth: "경기", inflation: "물가", financial_conditions: "유동성", stress_vulnerability: "신용 위험" };

export function ValidationHistory() {
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    getJson<History>("/api/macro/state/history").then(r => { if (live) setHistory(r); }).catch(() => { if (live) setError("수용 기록을 읽지 못했습니다."); });
    return () => { live = false; };
  }, []);
  return <section className="cockpit-panel macro-panel macro-now" aria-label="검증 이력">
    <div className="cockpit-panel__head"><div><span>Validation</span><h2>과거 자료로 검증한 결과</h2><p className="macro-asof"><b>2026년 9월 29일</b><span className="macro-asof__text">평가 · 규칙을 먼저 고정하고 최종 시험은 한 번만</span></p></div></div>
    <p className="macro-now__answer">2000년부터의 과거 자료로 미리 정한 기준을 시험했습니다. <b>미국 물가만 통과</b>했고, 나머지는 아래 이유로 ‘검증 중’으로 둡니다.</p>
    <table className="macro-now__table">
      <thead><tr><th scope="col">항목</th><th scope="col">표시</th><th scope="col">이유</th></tr></thead>
      <tbody>{RESULTS.map(row => <tr key={row.name}><th scope="row">{row.name}</th><td><VerifyChip passed={row.passed} /></td><td>{row.reason}<small>{row.detail}</small></td></tr>)}</tbody>
    </table>
    <div className="macro-now__accept">
      <h3>이 워크스페이스의 수용 기록</h3>
      {error && <p role="alert" className="macro-foot">{error}</p>}
      {!history && !error && <p role="status" className="macro-foot">기록을 읽고 있습니다.</p>}
      {history && (history.decisions?.length
        ? <ul>{history.decisions.map(r => <li key={r.seq}>{r.market === "US" ? "미국" : "한국"} {AXIS_NAME[r.axis] || r.axis} · {r.promotion === "primary" ? "검증 통과로 수용" : "검증 중 유지"} · {shortKst(r.created_at)}</li>)}</ul>
        : <p className="macro-foot">아직 수용한 항목이 없습니다. 모든 판정은 ‘검증 중’으로 보입니다.</p>)}
    </div>
    <details className="macro-now__how">
      <summary>어떻게 검증했나요</summary>
      <p>규칙과 기준을 먼저 정해 고정한 뒤, 개발(2000~2012) · 검증(2013~2019) · 최종 시험(2020~) 구간으로 나눠 확인했습니다. 각 시점에는 그때 실제로 발표돼 있던 값만 썼습니다. 결과를 본 뒤 규칙을 고치지 않았고, 최종 시험은 한 번만 실행했습니다. 통과는 ‘발표된 자료를 일관되게 요약한다’는 뜻이지 예측력이나 투자 지침이 아닙니다.</p>
    </details>
  </section>;
}
