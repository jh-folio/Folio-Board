import { useEffect, useRef, useState } from "react";
import { getJson, postJson, type JobStatus } from "../../api";
import { MacroChart, numberText } from "./MacroChart";
import { navigateMacro, readMacroLocation, type MacroItem, type MacroSnapshot } from "./types";

const STAGES: Record<string, string> = {
  leading: "선행", nowcast: "현재 추정", coincident: "동행", lagging: "후행", structural: "구조",
};
const QUALITY: Record<string, string> = {
  missing: "자료 없음",
  stale: "관측기간 오래됨",
  provider_failed: "원천 확인 실패",
  revised: "수정 이력 있음",
  method_changed: "정의 변경 · 계산 중지",
  vintage_conflict: "같은 보관판 값 불일치",
  partial: "수집 일부 완료",
};
// 방향은 직전 관측 대비일 뿐이다. 상승·하락에 좋고 나쁨의 색을 칠하지 않는다.
const DIRECTION: Record<string, string> = { up: "상승", down: "하락", same: "동일", unavailable: "비교 불가" };
const TRANSFORM: Record<string, string> = {
  yoy: "전년비",
  mom: "전월비",
  qoq: "전분기비 · 비연율",
  difference: "직전 관측 대비",
  spread: "같은 관측일 금리 차",
  level: "수준",
};
const BASIS: Record<string, string> = {
  provider_vintage: "FRED 보관판 날짜 기준",
  local_observed: "Folio Board가 확인한 기록",
  official_release: "공식 발표 근거 확인",
};
type Job = { id: string; status: JobStatus; message?: string };
const ACTIVE = new Set(["queued", "running", "cancel_requested", "committing"]);
const localDate = (value: string, timezone = "Asia/Seoul") =>
  new Intl.DateTimeFormat("sv-SE", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));

function Item({ item, detail, asOf }: { item: MacroItem; detail: boolean; asOf: boolean }) {
  const { series, latest } = item;
  const providerMissing = !item.providerStates.length || item.providerStates.some((s) => !s.status || s.status === "not_connected");
  return (
    <article className="surface macro-card" aria-label={series.label}>
      <div className="macro-card-heading">
        <h3>{series.label}</h3>
        <span className="chip">{STAGES[series.stage]}</span>
      </div>
      <p className="macro-value">{numberText(latest?.displayValue)} {latest?.displayValue != null ? latest.displayUnit : ""}</p>
      <p className="macro-meta">{TRANSFORM[series.transform]} · {DIRECTION[item.direction]}{latest ? ` · ${latest.period} 관측` : ""}</p>
      {latest && series.transform !== "level" && <p className="macro-meta">원값 {numberText(latest.value)} {latest.metadata.unit}</p>}
      <div className="macro-flags">
        {item.quality.map((flag) => <span className="chip" key={flag}>{QUALITY[flag] || flag}</span>)}
      </div>
      {providerMissing && <p className="macro-meta">연결된 공식 자료를 아직 수집하지 않았습니다. <a href="#/settings">설정 확인</a></p>}
      {latest?.calculationGap && (
        <p className="macro-meta">
          {latest.calculationGap === "method_changed"
            ? "기준·산식이 달라 변화율을 계산하지 않았습니다."
            : "같은 기준의 비교 관측값이 없어 변화율을 계산하지 않았습니다."}
        </p>
      )}
      <MacroChart
        title={series.label}
        points={item.history}
        comparison={detail && asOf ? item.latestRevisedComparison : undefined}
        stale={item.quality.includes("stale")}
      />
      {asOf && (
        <p className="macro-meta">
          재현 지원 시작: {item.coverage.firstAvailableAt ? localDate(item.coverage.firstAvailableAt, "America/Chicago") : "자료 없음"}
        </p>
      )}
      <p className="macro-meta">
        {latest?.releasedAt ? `공식 발표 ${latest.releasedAt}` : "공식 발표시각 미확인"}{" · "}
        {item.nextRelease
          ? <a href={item.nextRelease.sourceUrl} target="_blank" rel="noopener noreferrer">다음 일정 {item.nextRelease.date} (FRED 날짜 기준)</a>
          : "다음 공식 일정 미확인"}
      </p>
      {detail ? (
        <>
          <dl className="macro-facts">
            <dt>출처</dt>
            <dd><a href={series.sourceUrl} target="_blank" rel="noopener noreferrer">공식 원천</a></dd>
            <dt>자료 기준</dt>
            <dd>{latest ? BASIS[latest.availabilityBasis] : "수집 전"}</dd>
            {/* 한국(local_observed)은 공식 최초 발표값이 아니라 Folio Board가 처음 확인한 시각이다. */}
            <dt>{latest?.availabilityBasis === "local_observed" ? "처음 확인한 시각" : "재현 지원 시작"}</dt>
            <dd>{latest?.firstSeenAt || item.coverage.firstAvailableAt || "미확인"}</dd>
            <dt>현재 관측의 보관판</dt>
            <dd>{latest?.vintageDate || "공식 과거판 미지원"}</dd>
            <dt>이 값 수집 시각</dt>
            <dd>{latest?.fetchedAt || "수집 전"}</dd>
            <dt>수집 실행 완료</dt>
            <dd>{item.providerStates.map((s) => s.last_success).filter(Boolean).sort()[0] || "확인 전"}</dd>
            <dt>단위·조정</dt>
            <dd>{latest?.metadata.unit || series.unit} · {latest?.metadata.adjustment || series.adjustment}</dd>
            <dt>계산 방식</dt>
            <dd>{TRANSFORM[series.transform]} · {series.methodVersion}</dd>
            <dt>교차 검증</dt>
            <dd>비교 경로 없음</dd>
          </dl>
          {asOf && <p className="macro-meta">점선은 현재 수정치입니다. 선택 시점의 계산에는 사용하지 않습니다.</p>}
          <details>
            <summary>선택 관측기간의 수정 이력</summary>
            <label className="macro-revision-period">
              관측기간 날짜 <input
                aria-label="수정 비교 관측기간"
                type="date"
                value={item.revisionPeriod || latest?.period || ""}
                onChange={(e) => { if (e.target.value) navigateMacro({ period: e.target.value }); }}
              />
            </label>
            <p className="macro-meta">차트 데이터 표의 관측기간 날짜를 선택합니다. 보관된 값이 없는 날짜는 비어 있습니다.</p>
            {item.revisions.length ? (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>확인 기준</th><th>원값</th><th>단위</th></tr></thead>
                  <tbody>
                    {item.revisions.map((p, i) => (
                      <tr key={`${p.availableAt}-${i}`}>
                        <td>{p.vintageDate || p.fetchedAt}</td>
                        <td>{numberText(p.value)}</td>
                        <td>{p.metadata.unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p>이 관측기간의 수정 비교 자료가 없습니다.</p>}
          </details>
        </>
      ) : (
        <button className="btn btn--sm" type="button" onClick={() => navigateMacro({ series: series.id })}>출처·전체 이력·수정 비교</button>
      )}
    </article>
  );
}

export function MacroMap() {
  const [location, setLocation] = useState(readMacroLocation);
  const [snapshot, setSnapshot] = useState<MacroSnapshot | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const completedJob = useRef("");
  const [config, setConfig] = useState<{ enabled: boolean; startYear: number } | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  // URL hash가 바뀌면 보기 상태를 다시 읽고, 탭 전환 뒤 돌아올 위치로 기억한다.
  useEffect(() => {
    const sync = () => {
      if (!window.location.hash.startsWith("#/market-memory/macro")) return;
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
    const params = new URLSearchParams(location);
    void getJson<MacroSnapshot>(`/api/macro?${params}`)
      .then((value) => { if (current) setSnapshot(value); })
      .catch(() => { if (current) setError("거시 자료를 읽지 못했습니다. 날짜와 연결 상태를 확인해 주세요."); });
    return () => { current = false; };
  }, [location, revision]);

  useEffect(() => {
    let current = true;
    void getJson<{ enabled: boolean; startYear: number }>("/api/macro/settings")
      .then((v) => { if (current) setConfig(v); })
      .catch(() => { if (current) setMessage("자동 갱신 설정을 읽지 못했습니다."); });
    return () => { current = false; };
  }, []);

  // 수집 작업 상태를 따라가다 끝나면 지도를 한 번 다시 읽는다.
  useEffect(() => {
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const { job: value } = await getJson<{ job: Job | null }>("/api/macro/refresh");
        if (!current) return;
        setJob(value);
        if (value && !ACTIVE.has(value.status) && completedJob.current !== value.id) {
          completedJob.current = value.id;
          setRevision((v) => v + 1);
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
    try { setJob(await postJson<Job>("/api/macro/refresh", {})); }
    catch { setMessage("수집 요청 결과를 확인하지 못했습니다. 연결 상태를 확인해 주세요."); }
    finally { setSubmitting(false); }
  }

  async function toggleEnabled(enabled: boolean) {
    try { setConfig(await postJson("/api/macro/settings", { enabled })); }
    catch { setMessage("자동 갱신 설정을 저장하지 못했습니다."); }
  }

  const active = job && ACTIVE.has(job.status);
  return (
    <section className="macro-map" aria-label="거시 지도">
      <div className="surface macro-toolbar">
        <div className="macro-controls">
          <div className="segment" role="group" aria-label="거시 자료 시장">
            {["US", "KR"].map((m) => (
              <button key={m} type="button" aria-pressed={location.market === m} onClick={() => navigateMacro({ market: m, series: "", date: "" })}>
                {m === "US" ? "미국" : "한국"}
              </button>
            ))}
          </div>
          {/* 과거 시점 재현은 미국만 제공한다(D2). */}
          {location.market === "US" && (
            <label>
              자료 기준 <select aria-label="자료 기준" value={location.mode} onChange={(e) => navigateMacro({ mode: e.target.value })}>
                <option value="latest_revised">현재 수정치</option>
                <option value="as_of">과거 시점 재현</option>
              </select>
            </label>
          )}
          {location.mode === "as_of" && (
            <label>
              기준일 <input
                aria-label="기준일"
                type="date"
                value={location.date || snapshot?.date || ""}
                onChange={(e) => { if (e.target.value) navigateMacro({ date: e.target.value }); }}
              />
            </label>
          )}
          <label>
            표시 기간 <select aria-label="표시 기간" value={location.years} onChange={(e) => navigateMacro({ years: e.target.value })}>
              <option value="5">최근 5년</option>
              <option value="50">전체 이력</option>
            </select>
          </label>
          <button className="btn" type="button" onClick={() => void refresh()} disabled={submitting || Boolean(active)}>공식 자료 갱신</button>
          <a className="btn btn--text" href="#/dashboard">시장 캘린더</a>
        </div>
        <p className="macro-meta">경기·물가·금융여건·위험의 관측값을 봅니다. 방향은 직전 관측 대비이며 좋고 나쁨을 뜻하지 않습니다.</p>
        {config && (
          <label className="macro-opt-in">
            <input type="checkbox" checked={config.enabled} onChange={(e) => void toggleEnabled(e.target.checked)} /> 서버 실행 중 하루 2회 자동 갱신 (09:00·21:00 한국시간)
          </label>
        )}
        <p className="macro-meta">PC가 꺼진 동안의 갱신은 재기동 후 한 번으로 모읍니다. 한국은 공식 최초 발표값이 아니라 Folio Board가 처음 확인한 값을 보관합니다.</p>
      </div>
      {message && <p role="status" className="macro-notice">{message}</p>}
      {job && (
        <div className="macro-job" role="status">
          <span>
            {active
              ? "공식 자료 수집 중"
              : job.status === "done"
                ? "수집 완료"
                : job.status === "cancelled"
                  ? "수집 취소됨 · 저장된 부분은 유지됩니다"
                  : "수집이 완료되지 않았습니다. 지표별 상태를 확인해 주세요."}
          </span>
          {active && (
            <button
              className="btn btn--sm"
              type="button"
              onClick={() => void postJson(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, {}).catch(() => setMessage("취소 요청 상태를 확인하지 못했습니다."))}
            >
              수집 취소
            </button>
          )}
        </div>
      )}
      {error ? (
        <div role="alert" className="macro-notice">
          <p>{error}</p>
          <button className="btn" type="button" onClick={() => setRevision((v) => v + 1)}>다시 읽기</button>
        </div>
      ) : !snapshot ? (
        <p role="status">거시 자료를 불러오는 중입니다.</p>
      ) : (
        <>
          <div className="macro-summary">
            <h2>{snapshot.market === "US" ? "미국" : "한국"} 거시 지도</h2>
            <p>{snapshot.mode === "as_of" ? `${snapshot.date} 현지 날짜 마감 기준 (${snapshot.timezone})` : "현재 수정치 기준"}</p>
            {snapshot.notes.map((note) => <p className="macro-meta" key={note}>{note}</p>)}
            <p className="macro-meta">
              {snapshot.items.filter((i) => i.quality.includes("missing")).length}개 지표 자료 부족 · 공식 발표 일정과 교차 검증 경로는 확인된 경우에만 표시합니다.
            </p>
          </div>
          {location.series && <button className="btn" type="button" onClick={() => navigateMacro({ series: "" })}>네 축 모두 보기</button>}
          {Object.entries(snapshot.axes).map(([axis, label]) => {
            const items = snapshot.items.filter((i) => i.series.axis === axis);
            return items.length ? (
              <section key={axis} className="macro-axis" aria-label={label}>
                <h2>{label}</h2>
                <div className="macro-grid">
                  {items.map((item) => <Item key={item.series.id} item={item} detail={Boolean(location.series)} asOf={snapshot.mode === "as_of"} />)}
                </div>
              </section>
            ) : null;
          })}
        </>
      )}
    </section>
  );
}
