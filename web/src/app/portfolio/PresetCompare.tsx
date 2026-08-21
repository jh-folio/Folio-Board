import { useState } from "react";
import { postJson } from "../../api";
import {
  isComparison,
  money,
  percent,
  signOf,
  type BacktestComparison,
  type BacktestResult,
  type Preset,
} from "./portfolioTypes";

/** 프리셋 둘 이상을 나란히 돌려 본다.
 *
 * 서버는 예전부터 이걸 만들 수 있었다 — `POST /api/portfolio/backtests/compare`가
 * 프리셋 2개 이상을 받아 부분 실패까지 허용하며 돌린다. 부르는 화면만 없었다.
 *
 * **리서치용이라는 경계는 단일 백테스트와 같다.** 세금·수수료·체결오차·배당 처리에
 * 한계가 있고, 어느 쪽이 나았다는 것이 매수·매도 지시가 아니다.
 */

/** 어느 쪽이 나은가.
 *
 *  `nearZero`는 **부호 규약에 기대지 않기 위해서다.** 최대 낙폭은 음수로 온다(실측
 *  -0.1346). 그걸 "작을수록 좋다"로 두면 더 깊은 낙폭을 최선으로 강조하게 되고,
 *  "클수록 좋다"로 두면 provider가 양수 크기로 바꾸는 날 정반대가 된다. 낙폭은
 *  0에 가까울수록 낫다 — 그 말을 그대로 적는다.
 */
type Better = "high" | "low" | "nearZero";

const COMPARE_METRICS: ReadonlyArray<{ key: string; label: string; kind: "pct" | "num"; better: Better }> = [
  { key: "totalReturn", label: "총 수익률", kind: "pct", better: "high" },
  { key: "cagr", label: "연평균(CAGR)", kind: "pct", better: "high" },
  { key: "maxDrawdown", label: "최대 낙폭", kind: "pct", better: "nearZero" },
  { key: "volatility", label: "변동성", kind: "pct", better: "low" },
  { key: "sharpe", label: "샤프", kind: "num", better: "high" },
];

// 계열 색. 순위가 아니라 어느 프리셋인지를 가리키므로 고정 팔레트를 순서대로 쓴다.
const SERIES_TONES = ["blue", "teal", "gold", "purple", "burgundy"] as const;

function metricValue(result: BacktestResult, key: string): number | null {
  const value = (result.metrics as unknown as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatMetric(value: number | null, kind: "pct" | "num"): string {
  if (value === null) return "—";
  return kind === "pct" ? percent(value) : money(value, 2);
}

function seriesLabel(row: BacktestResult, index: number): string {
  return row.presetName || row.name || `프리셋 ${index + 1}`;
}

/** 이 지표에서 가장 나은 결과의 인덱스. 동점이면 없음(누구도 강조하지 않는다). */
export function bestIndex(
  results: ReadonlyArray<BacktestResult>,
  key: string,
  better: Better,
): number | null {
  const values = results.map((row) => metricValue(row, key));
  const present = values.filter((value): value is number => value !== null);
  if (present.length < 2) return null;
  const score = (value: number) => (better === "nearZero" ? -Math.abs(value) : better === "high" ? value : -value);
  const target = Math.max(...present.map(score));
  const winners = values
    .map((value, index) => (value !== null && score(value) === target ? index : -1))
    .filter((index) => index >= 0);
  return winners.length === 1 ? winners[0] : null;
}

/** 여러 계열을 한 좌표계에 겹친다. 축을 공유해야 비교가 성립한다. */
function OverlaySeries({ results }: { results: ReadonlyArray<BacktestResult> }) {
  const drawable = results.filter((row) => (row.series || []).length > 1);
  if (!drawable.length) return null;
  const width = 640;
  const height = 180;
  const all = drawable.flatMap((row) => row.series.map((point) => point.value));
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  return (
    <svg
      className="portfolio-sparkline portfolio-compare-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`프리셋 ${drawable.length}개의 평가액 추이 비교`}
    >
      {drawable.map((row, index) => (
        <path
          key={row.presetId || row.name || index}
          data-tone={SERIES_TONES[index % SERIES_TONES.length]}
          className="portfolio-compare-line"
          d={row.series
            .map((point, i) => {
              const x = (i / (row.series.length - 1)) * width;
              const y = height - ((point.value - min) / span) * height;
              return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
            })
            .join(" ")}
        />
      ))}
    </svg>
  );
}

export function PresetCompare({
  presets, start, end, rebalance,
}: {
  presets: ReadonlyArray<Preset>;
  start: string;
  end: string;
  rebalance: string;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<BacktestComparison | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  // 비중이 담긴 프리셋만 비교 대상이다. 빈 프리셋을 넣으면 그 줄이 전부 0이 된다.
  const usable = presets.filter((preset) => preset.positions.length);

  const toggle = (id: string) => {
    setSelected((current) => (current.includes(id) ? current.filter((row) => row !== id) : [...current, id]));
  };

  const run = async () => {
    setBusy("run");
    setNote("");
    setError("");
    try {
      const payload = await postJson<BacktestComparison>("/api/portfolio/backtests/compare", {
        presetIds: selected, start, end, rebalance,
      });
      setResult(isComparison(payload) ? payload : null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "비교 백테스트를 실행하지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  const save = async () => {
    if (!result) return;
    setBusy("save");
    try {
      await postJson("/api/portfolio/backtests/save", result);
      setNote("비교 결과를 저장했습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "저장하지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  if (usable.length < 2) {
    return (
      <p className="portfolio-empty">
        비교하려면 비중이 담긴 프리셋이 2개 이상 필요합니다. 위에서 프리셋을 하나 더 만드세요.
      </p>
    );
  }

  return (
    <div className="portfolio-compare">
      <div className="portfolio-compare-picker" role="group" aria-label="비교할 프리셋">
        {usable.map((preset) => (
          <label className="portfolio-compare-option" key={preset.id}>
            <input
              type="checkbox"
              checked={selected.includes(preset.id)}
              onChange={() => toggle(preset.id)}
            />
            <span>{preset.name}</span>
            <small>{preset.positions.length}종목</small>
          </label>
        ))}
      </div>
      <div className="portfolio-compare-actions">
        <button
          className="btn btn--primary"
          type="button"
          onClick={() => void run()}
          // 하나만 고르면 비교가 아니다. 서버도 2개 미만이면 400을 돌려준다.
          disabled={selected.length < 2 || busy === "run"}
        >
          {busy === "run" ? "비교하는 중" : `${selected.length || 0}개 비교 백테스트`}
        </button>
        {result && (
          <button className="btn" type="button" onClick={() => void save()} disabled={busy === "save"}>
            결과 저장
          </button>
        )}
        {selected.length === 1 && <span className="section-subtitle">두 개 이상 골라야 비교할 수 있습니다.</span>}
      </div>
      {error && <p className="react-dashboard-error">{error}</p>}
      {note && <p className="section-subtitle">{note}</p>}

      {result && (
        <div className="portfolio-block">
          <h3>{result.start} ~ {result.end} · {result.baseCurrency} 기준</h3>
          <OverlaySeries results={result.results} />
          <ul className="portfolio-compare-legend">
            {result.results.map((row, index) => (
              <li key={row.presetId || row.name || index}>
                <span className="portfolio-compare-dot" data-tone={SERIES_TONES[index % SERIES_TONES.length]} aria-hidden="true" />
                {seriesLabel(row, index)}
              </li>
            ))}
          </ul>
          <div className="table-scroll">
            <table className="portfolio-compare-table">
              <thead>
                <tr>
                  <th scope="col">지표</th>
                  {result.results.map((row, index) => (
                    <th scope="col" key={row.presetId || row.name || index}>{seriesLabel(row, index)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COMPARE_METRICS.map((metric) => {
                  const best = bestIndex(result.results, metric.key, metric.better);
                  return (
                    <tr key={metric.key}>
                      <th scope="row">{metric.label}</th>
                      {result.results.map((row, index) => {
                        const value = metricValue(row, metric.key);
                        return (
                          <td
                            key={row.presetId || row.name || index}
                            data-best={index === best ? "true" : undefined}
                            data-sign={metric.kind === "pct" && value !== null ? signOf(value) : undefined}
                          >
                            {formatMetric(value, metric.kind)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* 부분 실패를 숨기지 않는다. 몇 개를 골랐는데 몇 개가 돌았는지 보여야 한다. */}
          {result.errors?.length ? (
            <p className="react-dashboard-warning">
              {result.errors.map((row) => row.presetName || row.presetId).join(", ")}는 백테스트에 실패해 표에서 빠졌습니다.
            </p>
          ) : null}
          <p className="section-subtitle">
            리서치용입니다. 과거 가격과 일자별 환율로 계산하며 세금·수수료·체결오차·배당 처리에 한계가 있습니다.
            어느 쪽이 나았다는 것이 매수·매도 지시는 아닙니다.
          </p>
        </div>
      )}
    </div>
  );
}
