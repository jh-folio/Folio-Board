import { useEffect, useMemo, useRef, useState } from "react";
import { getJson, postJson, type JobStatus } from "../../api";
import { MacroChart, type MacroChartPoint } from "./MacroChart";
import { Sparkline } from "./Sparkline";
import {
  fixed, longDate, navigateMacro, periodLabel, readMacroLocation, shortKst, shortLabel, tinyLabel,
  type MacroHeadline, type MacroItem, type MacroOverview, type MacroRelease, type MacroSnapshot,
} from "./types";

const STATUS_CHIP: Record<string, string> = {
  revised: "수정됨",
  stale: "오래됨",
  provider_failed: "원천 확인 실패",
  partial: "일부 수집",
  method_changed: "정의 변경",
  vintage_conflict: "값 불일치",
};
// 원천 단위를 화면 말로. 수준 보기와 발표 이력 표에 쓴다.
const UNIT_KO: Record<string, string> = {
  "Billions of Chained 2017 Dollars": "십억 달러",
  "Index 2017=100": "지수",
  "Index 1982-1984=100": "지수",
  "2020=100": "지수",
  Percent: "%",
  "연%": "%",
  Index: "지수",
};
const UNIT_NOTE: Record<string, string> = {
  "Billions of Chained 2017 Dollars": "십억 달러, 2017년 연쇄 가격",
  "Index 2017=100": "지수, 2017=100",
  "Index 1982-1984=100": "지수, 1982–84=100",
  "2020=100": "지수, 2020=100",
};
const ADJUSTMENT_KO: Record<string, string> = { SA: "계절조정", SAAR: "계절조정 연율 수준", NSA: "원계열" };
const RELEASE_BASIS: Record<MacroRelease["basis"], string> = {
  provider_schedule: "FRED 일정",
  official_schedule: "한국은행 공시 일정",
  customary_estimate: "관행일 추정",
};
const LEVEL_TRANSFORMS = new Set(["difference", "level", "spread"]);
type Job = { id: string; status: JobStatus; message?: string };
type SourceSummary = { ok: number; notConnected: number; failed: number };
const ACTIVE = new Set(["queued", "running", "cancel_requested", "committing"]);

function unitSuffix(unit: string): string {
  return unit.startsWith("%") ? unit : ` ${unit}`;
}

function koUnit(unit: string): string {
  return UNIT_KO[unit] || unit;
}

function macroHash(patch: Record<string, string>): string {
  const current = { ...readMacroLocation(), period: "", ...patch };
  if (current.market === "KR") current.mode = "latest_revised";
  const params = new URLSearchParams(Object.entries(current).filter(([, value]) => Boolean(value)));
  return `#/macro/map?${params}`;
}

/** 변화 표시. 색은 방향만 말한다(상승 버건디·하락 파랑) — 좋고 나쁨이 아니다. */
function Change({ headline }: { headline: MacroHeadline }) {
  const { delta, tone, digits, deltaUnit, previous, unit } = headline;
  if (delta == null || previous == null) return <small className="macro-change">비교할 직전 값 없음</small>;
  const word = tone === "flat" ? "― 변화 없음" : `${tone === "up" ? "▲" : "▼"} ${fixed(Math.abs(delta), digits)}${unitSuffix(deltaUnit)}`;
  return (
    <small className="macro-change">
      <b data-tone={tone}>{word}</b>
      <span>직전 {fixed(previous, digits)}{unit.startsWith("%") ? unit : ""}</span>
    </small>
  );
}

function statusChips(item: MacroItem) {
  return item.quality.filter((flag) => STATUS_CHIP[flag]).map((flag) => (
    <span className="chip" data-tone={flag === "provider_failed" || flag === "stale" ? "gold" : "muted"} key={flag}>{STATUS_CHIP[flag]}</span>
  ));
}

function Row({ item }: { item: MacroItem }) {
  const { series, headline } = item;
  const missing = !headline;
  const notConnected = !item.providerStates.length || item.providerStates.some((s) => !s.status || s.status === "not_connected");
  return (
    <li>
      {/* 링크 이름은 보이는 글자 그대로다(이름·값·변화). aria-label로 덮으면 값이 읽히지 않는다. */}
      <a className="macro-row" href={macroHash({ series: series.id })}>
        <span className="macro-row__name">
          <b>{shortLabel(series)}</b>
          <small>{headline ? `${headline.measure} · ${periodLabel(headline.period, series.frequency)}` : notConnected ? "연결된 공식 자료 없음" : "이 시점의 자료 없음"}</small>
          {statusChips(item)}
        </span>
        {headline ? <Sparkline points={headline.spark} shape={headline.shape} /> : <span className="macro-spark" aria-hidden="true" />}
        <span className="macro-row__figure">
          <span className="macro-row__value">
            {missing ? "—" : fixed(headline.value, headline.digits)}
            {!missing && <small>{headline.unit}</small>}
          </span>
          {headline && <Change headline={headline} />}
        </span>
        <span className="sr-only"> 상세 보기</span>
      </a>
    </li>
  );
}

function recentText(overview: MacroOverview, items: MacroItem[]): string {
  const byId = new Map(items.map((i) => [i.series.id, i]));
  return overview.recent.map((r) => `${tinyLabel(r.seriesId, byId.get(r.seriesId)?.series.label)} ${periodLabel(r.period, r.frequency)}`).join(" · ") || "자료 없음";
}

function upcomingText(overview: MacroOverview, items: MacroItem[]): string {
  const byId = new Map(items.map((i) => [i.series.id, i]));
  return overview.upcoming.map((u) => {
    const [, month, day] = u.date.split("-").map(Number);
    const names = u.series.map((s) => `${tinyLabel(s.seriesId, byId.get(s.seriesId)?.series.label)}${s.basis === "customary_estimate" ? " (추정)" : ""}`);
    return `${month}/${day} ${names.join("·")}`;
  }).join(" · ") || "확인된 일정 없음";
}

function Controls({ market, mode, date }: { market: string; mode: string; date: string }) {
  return (
    <div className="macro-controls">
      <div className="segment" role="group" aria-label="거시 자료 시장">
        {(["US", "KR"] as const).map((m) => (
          <button key={m} type="button" aria-pressed={market === m} onClick={() => navigateMacro({ market: m, series: "", date: "" })}>
            {m === "US" ? "미국" : "한국"}
          </button>
        ))}
      </div>
      {/* 과거 시점 재현은 미국만 제공한다(D2). 한국은 선택지 자체를 두지 않는다. */}
      {market === "US" && (
        <div className="segment" role="group" aria-label="자료 기준">
          <button type="button" aria-pressed={mode === "latest_revised"} onClick={() => navigateMacro({ mode: "latest_revised", date: "" })}>현재 수정치</button>
          <button type="button" aria-pressed={mode === "as_of"} onClick={() => navigateMacro({ mode: "as_of" })}>과거 시점</button>
        </div>
      )}
      {mode === "as_of" && (
        <label className="macro-date">
          <small>기준일</small>
          <input aria-label="기준일" type="date" value={date} onChange={(e) => { if (e.target.value) navigateMacro({ date: e.target.value }); }} />
        </label>
      )}
    </div>
  );
}

function AsOfLine({ snapshot }: { snapshot: MacroSnapshot }) {
  return (
    <p className="macro-asof">
      <b>{longDate(snapshot.date)}</b>
      <span className="macro-asof__text">
        기준 · {snapshot.mode === "as_of" ? "과거 시점 재현 (그날 현지 마감까지 알려진 값)" : "현재 수정치"}
      </span>
      {snapshot.market === "KR" && <small className="chip" data-tone="muted">과거 시점 재현 미지원</small>}
    </p>
  );
}

function Skeleton() {
  return (
    <div className="macro-axes" aria-hidden="true">
      {[0, 1, 2, 3].map((n) => (
        <div className="surface surface--group macro-axis macro-skeleton" key={n}>
          <span className="macro-skeleton__line macro-skeleton__line--title" />
          <span className="macro-skeleton__line" />
          <span className="macro-skeleton__line" />
        </div>
      ))}
    </div>
  );
}

function Overview({ snapshot }: { snapshot: MacroSnapshot }) {
  const overview = snapshot.overview;
  return (
    <>
      {overview && (
        <dl className="macro-strip">
          <div className="surface surface--inset">
            <dt>최근 자료</dt>
            <dd>{recentText(overview, snapshot.items)}<small>월·분기 지표의 최신 관측기간</small></dd>
          </div>
          <div className="surface surface--inset">
            <dt>다음 발표</dt>
            <dd>
              {upcomingText(overview, snapshot.items)}
              <small>{snapshot.market === "US" ? "FRED 일정 날짜 · 발표시각 미확인" : "관행일 추정 포함 · 금통위는 한국은행 공시"}</small>
            </dd>
          </div>
        </dl>
      )}
      <div className="macro-axes">
        {Object.entries(snapshot.axes).map(([axis, label]) => {
          const items = snapshot.items.filter((i) => i.series.axis === axis);
          return items.length ? (
            <section key={axis} className="surface surface--group macro-axis" aria-label={label}>
              <h3>{label}<small>{items.length}개 지표</small></h3>
              <ul className="macro-rows">{items.map((item) => <Row key={item.series.id} item={item} />)}</ul>
            </section>
          ) : null;
        })}
      </div>
      <p className="macro-foot">
        ▲▼는 직전 관측 대비 변화이며 좋고 나쁨을 뜻하지 않습니다. 공식 발표시각은 확인되지 않아 날짜만 표시합니다. {snapshot.notes.join(" ")}
      </p>
    </>
  );
}

// 발표 이력 선택지: 분기 "26년 2분기", 월 "2026년 8월", 일·주 "2026-09-18".
function periodOption(period: string, frequency: string): string {
  if (frequency === "Q") return periodLabel(period, frequency);
  if (frequency === "M") return `${period.slice(0, 4)}년 ${Number(period.slice(5, 7))}월`;
  return period;
}

// 원천 값은 받은 자릿수 그대로, 천 단위 쉼표만 붙인다(24,270.599).
function rawText(raw: string | null | undefined, value: number | null): string {
  if (raw == null) return fixed(value, 2);
  const digits = raw.includes(".") ? raw.split(".")[1].length : 0;
  return fixed(Number(raw), digits);
}

function revisionLabel(index: number, basis: string): string {
  if (basis === "local_observed") return index === 0 ? "처음 확인" : `변경 확인 ${index}`;
  return index === 0 ? "첫 발표" : `수정 ${index}`;
}

function Detail({ snapshot }: { snapshot: MacroSnapshot }) {
  const item = snapshot.items[0];
  const [view, setView] = useState<"rate" | "level">("rate");
  const { series, headline, latest } = item;
  const levelOnly = LEVEL_TRANSFORMS.has(series.transform);
  const showLevel = levelOnly || view === "level";
  const rawUnit = latest?.metadata.unit || series.unit;
  const unit = showLevel ? (levelOnly && headline ? headline.unit : koUnit(rawUnit)) : "%";
  const digits = showLevel ? (levelOnly && headline ? headline.digits : 2) : 2;
  const pick = (p: MacroItem["history"][number]): MacroChartPoint => ({ period: p.period, value: showLevel ? p.value : p.displayValue });
  const points = useMemo(() => item.history.map(pick), [item.history, showLevel]);
  const comparison = useMemo(() => item.latestRevisedComparison.map(pick), [item.latestRevisedComparison, showLevel]);
  const periods = item.history.slice(-12).map((p) => p.period).reverse();
  const market = snapshot.market === "US" ? "미국" : "한국";
  const lastSuccess = item.providerStates.map((s) => s.last_success).filter(Boolean).sort().pop();
  const release = item.nextRelease;
  const revisions = item.revisions;

  return (
    <>
      <div className="macro-detail-top">
        <div className="macro-hero">
          <span className="macro-hero__value">
            {headline ? fixed(headline.value, headline.digits) : "—"}
            {headline && <small>{headline.unit}</small>}
          </span>
          {headline && (
            <span className="macro-hero__meta">
              {headline.measure}{series.transform === "qoq" ? "(연율 아님)" : ""} · {periodLabel(headline.period, series.frequency)} · <Change headline={headline} />
            </span>
          )}
          <span className="macro-hero__chips">
            {statusChips(item)}
            {snapshot.market === "US" && item.coverage.firstAvailableAt && (
              <span className="chip" data-tone="muted">과거 재현 {item.coverage.firstAvailableAt.slice(0, 7)}부터</span>
            )}
            {snapshot.market === "KR" && <span className="chip" data-tone="muted">Folio Board 확인 기록</span>}
          </span>
        </div>
        <div className="macro-detail-controls">
          {!levelOnly && (
            <div className="segment" role="group" aria-label="표시 값">
              <button type="button" aria-pressed={!showLevel} onClick={() => setView("rate")}>{headline?.measure || "변화율"}</button>
              <button type="button" aria-pressed={showLevel} onClick={() => setView("level")}>수준</button>
            </div>
          )}
          <div className="segment" role="group" aria-label="표시 기간">
            <button type="button" aria-pressed={readMacroLocation().years === "5"} onClick={() => navigateMacro({ years: "5" })}>5년</button>
            <button type="button" aria-pressed={readMacroLocation().years === "50"} onClick={() => navigateMacro({ years: "50" })}>전체</button>
          </div>
        </div>
      </div>
      {latest?.calculationGap === "method_changed" && <p className="macro-foot">기준·산식이 달라져 변화율을 계산하지 않았습니다.</p>}
      <div className="surface surface--group macro-chart-wrap">
        <MacroChart
          title={`${market} ${shortLabel(series)}`}
          points={points}
          frequency={series.frequency}
          unit={unit}
          digits={digits}
          shape={!showLevel && headline?.shape === "bars" ? "bars" : "line"}
          comparison={snapshot.mode === "as_of" ? comparison : undefined}
          stale={item.quality.includes("stale")}
        />
        {snapshot.mode === "as_of" && <p className="macro-foot">점선은 현재 수정치입니다. 선택 시점의 계산에는 사용하지 않습니다.</p>}
      </div>
      <div className="macro-detail-grid">
        <section className="surface surface--group">
          <h3>
            이 값의 발표 이력
            <label className="macro-period">
              <span className="sr-only">관측기간</span>
              <select value={item.revisionPeriod || ""} onChange={(e) => navigateMacro({ period: e.target.value })}>
                {periods.map((p) => <option key={p} value={p}>{periodOption(p, series.frequency)}</option>)}
              </select>
            </label>
          </h3>
          {revisions.length ? (
            <div className="macro-table-scroll">
              <table className="macro-table">
                <thead><tr><th>발표</th><th>확인 기준</th><th className="num">값</th><th className="num">직전 대비</th></tr></thead>
                <tbody>
                  {revisions.map((r, i) => {
                    const prev = i ? revisions[i - 1].value : null;
                    const diff = r.value != null && prev != null ? r.value - prev : null;
                    return (
                      <tr key={`${r.availableAt}-${i}`}>
                        <td>{revisionLabel(i, r.availabilityBasis)}</td>
                        <td>{r.vintageDate || shortKst(r.fetchedAt)}</td>
                        <td className="num">{rawText(r.rawValue, r.value)} <small>{koUnit(r.metadata.unit)}</small></td>
                        <td className="num">{diff == null ? "—" : `${diff > 0 ? "+" : ""}${fixed(diff, 2)}`}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="macro-foot">이 관측기간의 발표 이력이 없습니다.</p>}
          <p className="macro-foot">
            {snapshot.market === "US"
              ? "같은 기간의 값이 발표마다 고쳐질 수 있습니다. 과거 시점을 고르면 그날까지 나온 판만 씁니다."
              : "한국은 Folio Board가 확인한 변경만 기록합니다. 그때 알 수 있었던 값은 재현하지 않습니다."}
          </p>
        </section>
        <section className="surface surface--group">
          <h3>출처와 기준</h3>
          <dl className="macro-facts">
            <dt>원천</dt>
            <dd>
              {series.provider === "fred" ? "FRED" : "한국은행 ECOS"} ·{" "}
              <a href={series.sourceUrl} target="_blank" rel="noopener noreferrer">{series.code}</a>
            </dd>
            <dt>단위</dt>
            <dd>{UNIT_NOTE[rawUnit] || koUnit(rawUnit)} · {ADJUSTMENT_KO[latest?.metadata.adjustment || series.adjustment] || "조정 정보 미확인"}</dd>
            <dt>계산</dt>
            <dd>{headline?.measure || "수준"} · 계산 방식 {series.methodVersion}</dd>
            <dt>날짜 기준</dt>
            <dd>{snapshot.market === "US" ? "FRED 보관판 날짜 · 공식 발표시각 미확인" : "Folio Board가 처음 확인한 시각"}</dd>
            <dt>다음 발표</dt>
            <dd>{release ? `${release.date} (${RELEASE_BASIS[release.basis]})` : "확인된 일정 없음"}</dd>
            <dt>교차 확인</dt>
            <dd>비교할 두 번째 원천 없음</dd>
            <dt>마지막 수집</dt>
            <dd>{shortKst(lastSuccess)}</dd>
          </dl>
        </section>
      </div>
      {item.guide && item.guide.length > 0 && (
        <details className="surface surface--group macro-guide">
          <summary>
            <span className="macro-guide__title">처음 보는 분을 위한 설명</span>
            <small>무엇을 재고 어떻게 읽나요?</small>
          </summary>
          <div className="macro-guide__body">
            {item.guide.map((part) => (
              <section key={part.heading}>
                <h4>{part.heading}</h4>
                <p>{part.body}</p>
              </section>
            ))}
          </div>
          <p className="macro-foot macro-guide__foot">이 설명과 화면은 좋고 나쁨이나 투자 판단을 말하지 않습니다.</p>
        </details>
      )}
    </>
  );
}

// 키가 없는 원천은 실패가 아니라 건너뜀이다. 원천 장애와 같은 "실패"로 보이지 않게 나눠 말한다.
function jobText(job: Job, active: boolean, sources: SourceSummary | null): string {
  if (active) return "공식 자료 수집 중";
  if (job.status === "cancelled") return "수집 취소됨 · 저장된 부분은 유지됩니다";
  if (job.status === "done") {
    return sources?.notConnected
      ? `수집 완료 · API 키가 연결되지 않은 원천 ${sources.notConnected}개는 건너뛰었습니다`
      : "수집 완료";
  }
  if (sources?.failed) return "일부 원천을 확인하지 못했습니다. 이미 받은 자료는 그대로 있으며, 지표별 상태에서 실패한 원천을 확인할 수 있습니다.";
  if (sources && !sources.ok && sources.notConnected) return "연결된 API 키가 없어 수집하지 않았습니다. 설정에서 FRED 또는 BOK API 키를 등록해 주세요.";
  return "수집이 완료되지 않았습니다. 지표별 상태를 확인해 주세요.";
}

export function MacroMap() {
  const [location, setLocation] = useState(readMacroLocation);
  const [snapshot, setSnapshot] = useState<MacroSnapshot | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const completedJob = useRef("");
  const [config, setConfig] = useState<{ enabled: boolean } | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [sources, setSources] = useState<SourceSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  // URL hash가 바뀌면 보기 상태를 다시 읽고, 탭 전환 뒤 돌아올 위치로 기억한다.
  useEffect(() => {
    const sync = () => {
      if (!window.location.hash.startsWith("#/macro/map")) return;
      setLocation(readMacroLocation());
      sessionStorage.setItem("folio.macro.lastView.v1", window.location.hash);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    let current = true;
    setSnapshot(null);
    setError("");
    // 개요는 요약 응답(머리 숫자·짧은 추이)만 받는다. 전체 이력은 상세에서만 받는다.
    const params = new URLSearchParams({ ...location, ...(location.series ? {} : { view: "summary" }) });
    void getJson<MacroSnapshot>(`/api/macro?${params}`)
      .then((value) => { if (current) setSnapshot(value); })
      .catch(() => { if (current) setError("거시 자료를 읽지 못했습니다. 날짜와 연결 상태를 확인해 주세요."); });
    return () => { current = false; };
  }, [location, revision]);

  useEffect(() => {
    let current = true;
    void getJson<{ enabled: boolean }>("/api/macro/settings")
      .then((v) => { if (current) setConfig(v); })
      .catch(() => { if (current) setConfig(null); });
    return () => { current = false; };
  }, []);

  // 수집 작업 상태를 따라가다 끝나면 지도를 한 번 다시 읽는다.
  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const { job: value, sources: summary } = await getJson<{ job: Job | null; sources?: SourceSummary }>("/api/macro/refresh");
        if (!current) return;
        setJob(value);
        setSources(summary || null);
        if (value && !ACTIVE.has(value.status) && completedJob.current !== value.id) {
          const first = completedJob.current === "";
          completedJob.current = value.id;
          // 화면을 열 때 이미 끝나 있던 작업은 다시 읽을 이유가 없다.
          if (!first) setRevision((v) => v + 1);
        }
      } catch {
        if (current) setMessage("수집 상태를 확인하지 못했습니다. 새 수집을 중복 요청하지 말고 연결을 확인해 주세요.");
      }
      if (current) timer = setTimeout(() => void poll(), 2500);
    };
    void poll();
    return () => { current = false; clearTimeout(timer); };
  }, []);

  async function refresh() {
    setSubmitting(true);
    setMessage("");
    try {
      const submitted = await postJson<Job>("/api/macro/refresh", {});
      completedJob.current = completedJob.current || "submitted";
      setJob(submitted);
    } catch {
      setMessage("수집 요청 결과를 확인하지 못했습니다. 연결 상태를 확인해 주세요.");
    } finally {
      setSubmitting(false);
    }
  }

  const active = Boolean(job && ACTIVE.has(job.status));
  const detail = Boolean(location.series && snapshot?.items.length === 1);
  const detailItem = detail ? snapshot?.items[0] : null;
  const title = detailItem
    ? `${snapshot?.market === "US" ? "미국" : "한국"} ${shortLabel(detailItem.series)}`
    : `${location.market === "US" ? "미국" : "한국"} 거시 지도`;
  const kicker = detailItem ? `MACRO MAP · ${snapshot?.axes[detailItem.series.axis] || ""}` : "MACRO MAP";
  const collection = snapshot?.overview?.collection;

  return (
    <section className="cockpit-panel macro-panel" aria-label="거시 지도">
      <div className="cockpit-panel__head">
        <div>
          <span>{kicker}</span>
          <h2>{title}</h2>
          {snapshot && <AsOfLine snapshot={snapshot} />}
        </div>
        {detailItem
          ? <a className="btn btn--text btn--sm" href={macroHash({ series: "" })}>← 거시 지도</a>
          : <Controls market={location.market} mode={location.mode} date={location.date || snapshot?.date || ""} />}
      </div>
      {message && <p role="status" className="macro-notice">{message}</p>}
      {error ? (
        <div role="alert" className="macro-notice">
          <p>{error}</p>
          <button className="btn" type="button" onClick={() => setRevision((v) => v + 1)}>다시 읽기</button>
        </div>
      ) : !snapshot ? (
        <>
          <p className="sr-only" role="status">거시 자료를 불러오는 중입니다.</p>
          <Skeleton />
        </>
      ) : detail ? <Detail snapshot={snapshot} /> : <Overview snapshot={snapshot} />}
      <div className="macro-refresh">
        <span role="status">
          {job && (active || completedJob.current === job.id) ? `${jobText(job, active, sources)} · ` : ""}
          {collection ? `${collection.total}개 중 ${collection.collected}개 자료 있음${collection.revised ? ` · 수정 ${collection.revised}` : ""} · 마지막 수집 ${shortKst(collection.lastCollectedAt)} · ` : ""}
          {config ? (config.enabled ? "자동 갱신 켜짐(하루 2회, 09:00·21:00)" : "자동 갱신 꺼짐") : "자동 갱신 상태 확인 전"} ·{" "}
          <a href="#/settings/admin">설정에서 변경</a>
        </span>
        {active && job ? (
          <button
            className="btn btn--sm"
            type="button"
            onClick={() => void postJson(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, {}).catch(() => setMessage("취소 요청 상태를 확인하지 못했습니다."))}
          >
            수집 취소
          </button>
        ) : (
          <button className="btn btn--sm" type="button" onClick={() => void refresh()} disabled={submitting}>지금 갱신</button>
        )}
      </div>
    </section>
  );
}
