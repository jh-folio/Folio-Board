import { useCallback, useEffect, useState } from "react";
import { deleteJson, getJson, postJson } from "../../api";
import { money, percent, signOf, type BacktestResult, type Preset } from "./portfolioTypes";

/** 목표 비중으로 과거 성과를 되돌려 본다.
 *
 *  `/api/portfolio/backtests`는 목표 프리셋을 받아 일별 평가액 곡선, 벤치마크 대비
 *  지표 30여 개, 연도별 수익률, 종목별 기여도를 돌려준다. 전부 서버가 하던 일이다.
 *
 *  **리서치용이다.** yfinance 과거 가격과 일자별 환율을 쓰며 세금·수수료·체결오차·
 *  배당 처리에 한계가 있다. 화면이 그 사실을 결과 옆에 계속 둔다.
 *
 *  결과는 자동 저장하지 않는다. 저장 버튼을 눌렀을 때만 남는다.
 */

const REBALANCE: ReadonlyArray<{ id: string; label: string }> = [
  { id: "none", label: "안 함" },
  { id: "monthly", label: "매월" },
  { id: "quarterly", label: "분기" },
  { id: "yearly", label: "매년" },
];

// 지표는 30개가 넘는다. 다 보여주면 아무것도 안 보인다 — 판단에 쓰는 것만 고른다.
const METRICS: ReadonlyArray<{ key: string; label: string; kind: "pct" | "num" }> = [
  { key: "totalReturn", label: "총 수익률", kind: "pct" },
  { key: "cagr", label: "연평균(CAGR)", kind: "pct" },
  { key: "maxDrawdown", label: "최대 낙폭", kind: "pct" },
  { key: "volatility", label: "변동성", kind: "pct" },
  { key: "sharpe", label: "샤프", kind: "num" },
  { key: "benchmarkTotalReturn", label: "벤치마크 수익률", kind: "pct" },
];

function Sparkline({ series, benchmark }: {
  series: ReadonlyArray<{ date: string; value: number }>;
  benchmark?: ReadonlyArray<{ date: string; value: number }>;
}) {
  if (series.length < 2) return null;
  const width = 640;
  const height = 160;
  const all = [...series.map((p) => p.value), ...(benchmark || []).map((p) => p.value)];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const path = (points: ReadonlyArray<{ value: number }>) => points
    .map((point, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((point.value - min) / span) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      className="portfolio-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`평가액 추이 ${series[0].date}부터 ${series[series.length - 1].date}까지`}
    >
      {benchmark && benchmark.length > 1 && (
        <path className="portfolio-sparkline__benchmark" d={path(benchmark)} />
      )}
      <path className="portfolio-sparkline__line" d={path(series)} />
    </svg>
  );
}

export function PortfolioBacktest({ revision }: { revision: number }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [saved, setSaved] = useState<BacktestResult[]>([]);
  const [presetId, setPresetId] = useState("");
  const [start, setStart] = useState("2020-01-01");
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [rebalance, setRebalance] = useState("monthly");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");

  const load = useCallback(async () => {
    try {
      const [presetPayload, savedPayload] = await Promise.all([
        getJson<Preset[] | { presets: Preset[] }>("/api/portfolio/presets"),
        getJson<BacktestResult[] | { backtests: BacktestResult[] }>("/api/portfolio/backtests"),
      ]);
      const list = Array.isArray(presetPayload) ? presetPayload : presetPayload.presets || [];
      setPresets(list);
      setPresetId((current) => current || list[0]?.id || "");
      setSaved(Array.isArray(savedPayload) ? savedPayload : savedPayload.backtests || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "백테스트 정보를 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => { void load(); }, [load, revision]);

  const run = async () => {
    if (!presetId) return;
    setBusy("run");
    setNote("");
    setError("");
    try {
      setResult(await postJson<BacktestResult>("/api/portfolio/backtests", { presetId, start, end, rebalance }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "백테스트를 실행하지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    if (!result) return;
    setBusy("save");
    try {
      await postJson("/api/portfolio/backtests/save", result);
      await load();
      setNote("결과를 저장했습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "저장하지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  const remove = async (row: BacktestResult) => {
    if (confirmDelete !== row.id) { setConfirmDelete(row.id); return; }
    setBusy(row.id);
    try {
      await deleteJson(`/api/portfolio/backtests/${encodeURIComponent(row.id)}`, {});
      setConfirmDelete("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "지우지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  if (!presets.length) {
    return (
      <p className="portfolio-empty">
        백테스트는 프리셋이 있어야 돌릴 수 있습니다. <strong>프리셋</strong> 탭에서
        현재 보유로 프리셋을 만든 뒤 다시 오세요.
      </p>
    );
  }

  return (
    <div className="portfolio-backtest">
      <div className="portfolio-block">
        <h3>조건</h3>
        <div className="portfolio-backtest-fields">
          <label className="field">
            <span>프리셋</span>
            <select value={presetId} onChange={(event) => setPresetId(event.target.value)}>
              {presets.map((preset) => (
                <option key={preset.id} value={preset.id}>{preset.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>시작</span>
            <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
          </label>
          <label className="field">
            <span>종료</span>
            <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
          </label>
          <div className="field">
            <span id="rebalanceLabel">리밸런싱</span>
            <div className="segment" role="group" aria-labelledby="rebalanceLabel">
              {REBALANCE.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  aria-pressed={rebalance === item.id}
                  onClick={() => setRebalance(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="portfolio-actions">
          <button className="btn btn--primary" type="button" onClick={() => void run()} disabled={!!busy || start >= end}>
            {busy === "run" ? "계산 중" : "백테스트 실행"}
          </button>
          {start >= end && <span className="portfolio-note">시작일이 종료일보다 앞서야 합니다.</span>}
        </div>
      </div>

      {result && (
        <div className="portfolio-block">
          <div className="portfolio-block__head">
            <h3>{result.presetName || result.name} · {result.start} ~ {result.end}</h3>
            <button className="btn" type="button" onClick={() => void save()} disabled={!!busy}>
              {busy === "save" ? "저장 중" : "결과 저장"}
            </button>
          </div>
          <Sparkline series={result.series} benchmark={result.benchmarkSeries} />
          <p className="portfolio-note">
            진한 선이 이 목표 비중, 옅은 선이 벤치마크({result.benchmark?.ticker || "—"})입니다.
            둘 다 {money(result.initialValue)}에서 시작합니다.
          </p>
          <div className="portfolio-metrics portfolio-metrics--compact">
            {METRICS.map((metric) => {
              const value = result.metrics[metric.key];
              return (
                <div
                  key={metric.key}
                  className="portfolio-metric"
                  data-sign={metric.kind === "pct" && metric.key !== "volatility" && metric.key !== "maxDrawdown" ? signOf(value) : undefined}
                >
                  <span>{metric.label}</span>
                  <strong>{metric.kind === "pct" ? percent(value) : (Number.isFinite(value) ? value.toFixed(2) : "—")}</strong>
                </div>
              );
            })}
          </div>
          {result.assetContributions && result.assetContributions.length > 0 && (
            <div className="portfolio-table-scroll">
              <table className="portfolio-mini-table">
                <thead>
                  <tr><th scope="col">종목</th><th scope="col">비중</th><th scope="col">기여</th></tr>
                </thead>
                <tbody>
                  {result.assetContributions.map((row) => (
                    <tr key={row.ticker}>
                      <th scope="row">{row.name || row.ticker}</th>
                      <td>{percent(row.weight)}</td>
                      <td data-sign={signOf(row.contribution)}>{percent(row.contribution)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="portfolio-note">
            리서치용 계산입니다. 과거 가격과 일자별 환율을 쓰며 세금·수수료·체결오차·배당
            처리에는 한계가 있습니다. 과거 성과가 앞으로를 보장하지 않습니다.
          </p>
        </div>
      )}

      {saved.length > 0 && (
        <div className="portfolio-block">
          <h3>저장한 결과</h3>
          <ul className="portfolio-preset-list">
            {saved.map((row) => (
              <li key={row.id} className="portfolio-preset surface">
                <div>
                  <strong>{row.presetName || row.name}</strong>
                  <small>
                    {row.start} ~ {row.end} · 총 {percent(row.metrics?.totalReturn)}
                    {row.savedAt ? ` · ${row.savedAt.slice(0, 10)}` : ""}
                  </small>
                </div>
                <div className="portfolio-actions">
                  <button
                    className="btn"
                    type="button"
                    onClick={() => void getJson<BacktestResult>(`/api/portfolio/backtests/${encodeURIComponent(row.id)}`).then(setResult)}
                  >
                    열기
                  </button>
                  <button className="btn" type="button" onClick={() => void remove(row)} disabled={busy === row.id}>
                    {busy === row.id ? "지우는 중" : confirmDelete === row.id ? "정말 지울까요?" : "지우기"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {note && <p className="react-reader-status" role="status">{note}</p>}
      {error && <p className="react-dashboard-error" role="alert">{error}</p>}
    </div>
  );
}
