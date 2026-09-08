import { useCallback, useEffect, useState } from "react";
import { deleteJson, getJson, postJson } from "../../api";
import { BacktestComparisonReport } from "./PresetCompare";
import { BacktestResultReport } from "./BacktestReport";
import { backtestErrorMessage } from "./backtestUi";
import { backtestMetric, isComparison, isComparisonSummary, money, percent, type BacktestComparison, type BacktestComparisonSummary, type BacktestResult, type Preset } from "./portfolioTypes";

const REBALANCE: ReadonlyArray<{ id: string; label: string }> = [
  { id: "none", label: "안 함" }, { id: "monthly", label: "매월" }, { id: "quarterly", label: "분기" }, { id: "yearly", label: "매년" },
];
type SavedBacktest = BacktestResult | BacktestComparisonSummary;
function savedLabel(row: SavedBacktest): string { return row.name || (isComparisonSummary(row) ? "포트폴리오 비교 백테스트" : row.presetName || "백테스트"); }
function rebalanceLabel(value: string): string { return ({ none: "리밸런싱 안 함", monthly: "매월 리밸런싱", quarterly: "분기 리밸런싱", yearly: "매년 리밸런싱" } as Record<string, string>)[value] || "리밸런싱 조건 미기록"; }

/** 조건을 고르고, 결과를 읽고, 사용자가 고른 결과만 저장하는 백테스트 흐름. */
export function PortfolioBacktest({ revision, onOpenPresets }: { readonly revision: number; onOpenPresets?: () => void }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [saved, setSaved] = useState<SavedBacktest[]>([]);
  const [presetId, setPresetId] = useState("");
  const [start, setStart] = useState("2020-01-01");
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [rebalance, setRebalance] = useState("monthly");
  const [baseCurrency, setBaseCurrency] = useState("USD");
  const [initialValue, setInitialValue] = useState("10000");
  const [benchmark, setBenchmark] = useState("SPY");
  const [result, setResult] = useState<BacktestResult | BacktestComparison | null>(null);
  const [busy, setBusy] = useState(""); const [note, setNote] = useState(""); const [error, setError] = useState(""); const [confirmDelete, setConfirmDelete] = useState("");
  const load = useCallback(async () => {
    const [presetPayload, savedPayload] = await Promise.all([getJson<Preset[] | { presets: Preset[] }>("/api/portfolio/presets"), getJson<SavedBacktest[] | { backtests: SavedBacktest[] }>("/api/portfolio/backtests")]);
    const list = Array.isArray(presetPayload) ? presetPayload : presetPayload.presets || [];
    setPresets(list); setPresetId((current) => current || list[0]?.id || ""); setSaved(Array.isArray(savedPayload) ? savedPayload : savedPayload.backtests || []);
  }, []);
  useEffect(() => { void load().catch((reason) => setError(backtestErrorMessage(reason, "백테스트 정보를 불러오지 못했습니다."))); }, [load, revision]);
  const invalid = !presetId || start >= end || !Number.isFinite(Number(initialValue)) || Number(initialValue) <= 0 || !benchmark.trim();
  const run = async () => { setNote(""); setError(""); if (invalid) { setError(!presetId ? "백테스트를 실행하려면 프리셋을 고르세요." : start >= end ? "시작일이 종료일보다 앞서야 합니다." : !Number.isFinite(Number(initialValue)) || Number(initialValue) <= 0 ? "초기 금액은 0보다 커야 합니다." : "벤치마크 티커를 입력하세요."); return; } setBusy("run"); try { setResult(await postJson<BacktestResult>("/api/portfolio/backtests", { presetId, start, end, rebalance, baseCurrency, initialValue: Number(initialValue), benchmark: benchmark.trim() })); } catch (reason) { setError(backtestErrorMessage(reason, "백테스트를 실행하지 못했습니다.")); } finally { setBusy(""); } };
  const save = async () => { if (!result) return; setBusy("save"); setError(""); try { await postJson("/api/portfolio/backtests/save", result); await load(); setNote("화면의 결과를 저장했습니다."); } catch (reason) { setError(backtestErrorMessage(reason, "저장하지 못했습니다.")); } finally { setBusy(""); } };
  const open = async (row: SavedBacktest) => { setBusy(`open-${row.id}`); setError(""); try { setResult(await getJson<BacktestResult | BacktestComparison>(`/api/portfolio/backtests/${encodeURIComponent(row.id)}`)); } catch (reason) { setError(backtestErrorMessage(reason, "저장한 결과를 열지 못했습니다. 현재 화면의 결과는 그대로 유지했습니다.")); } finally { setBusy(""); } };
  const remove = async (row: SavedBacktest) => { if (confirmDelete !== row.id) { setConfirmDelete(row.id); return; } setBusy(`delete-${row.id}`); setError(""); try { await deleteJson(`/api/portfolio/backtests/${encodeURIComponent(row.id)}`, {}); setConfirmDelete(""); await load(); } catch (reason) { setError(backtestErrorMessage(reason, "지우지 못했습니다.")); } finally { setBusy(""); } };
  const noPresets = !presets.length;
  return <div className="portfolio-backtest">
    {noPresets ? <div className="portfolio-empty"><p>새 백테스트는 프리셋이 있어야 돌릴 수 있습니다. 저장한 결과는 아래에서 계속 열거나 지울 수 있습니다.</p><button className="btn" type="button" onClick={onOpenPresets}>프리셋으로 가기</button></div> : <div className="portfolio-block portfolio-backtest-conditions"><h3>조건</h3><p className="portfolio-note">조건을 바꿔도 저장된 결과는 바뀌지 않습니다. 실행 뒤 결과를 확인하고 필요할 때만 저장하세요.</p>
      <div className="portfolio-backtest-fields">
        <label className="field"><span>프리셋</span><select value={presetId} onChange={(event) => setPresetId(event.target.value)}>{presets.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
        <label className="field"><span>시작</span><input type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label><label className="field"><span>종료</span><input type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        <label className="field"><span>기준 통화</span><select value={baseCurrency} onChange={(event) => setBaseCurrency(event.target.value)}><option value="USD">USD</option><option value="KRW">KRW</option></select></label>
        <label className="field"><span>초기 금액</span><input type="number" min="0.01" step="0.01" inputMode="decimal" value={initialValue} onChange={(event) => setInitialValue(event.target.value)} /></label><label className="field"><span>벤치마크</span><input value={benchmark} onChange={(event) => setBenchmark(event.target.value.toUpperCase())} spellCheck={false} /></label>
        <div className="field"><span id="rebalanceLabel">리밸런싱</span><div className="segment" role="group" aria-labelledby="rebalanceLabel">{REBALANCE.map((item) => <button type="button" key={item.id} aria-pressed={rebalance === item.id} onClick={() => setRebalance(item.id)}>{item.label}</button>)}</div></div>
      </div>
      <div className="portfolio-actions"><button className="btn btn--primary" type="button" onClick={() => void run()} disabled={!!busy}>{busy === "run" ? "계산 중" : "백테스트 실행"}</button>{start >= end && <span className="portfolio-note">시작일이 종료일보다 앞서야 합니다.</span>}{(!Number.isFinite(Number(initialValue)) || Number(initialValue) <= 0) && <span className="portfolio-note">초기 금액은 0보다 커야 합니다.</span>}{!benchmark.trim() && <span className="portfolio-note">벤치마크 티커를 입력하세요.</span>}</div>
    </div>}
    {result && <div className="portfolio-block"><div className="portfolio-block__head"><h3>결과</h3><button className="btn" type="button" onClick={() => void save()} disabled={!!busy}>{busy === "save" ? "저장 중" : "결과 저장"}</button></div>{isComparison(result) ? <BacktestComparisonReport result={result} /> : <BacktestResultReport result={result} />}</div>}
    {saved.length > 0 && <div className="portfolio-block"><h3>저장한 결과</h3><ul className="portfolio-preset-list">{saved.map((row) => <li key={row.id} className="portfolio-preset surface"><div><strong>{savedLabel(row)}</strong><small>{row.start} ~ {row.end} · {row.baseCurrency} · 시작 {money(row.initialValue)} · {row.benchmark?.ticker || "벤치마크 미기록"} · {rebalanceLabel(row.rebalance)} · {isComparisonSummary(row) ? `비교 ${row.resultCount ?? "—"}개` : `총 ${percent(backtestMetric(row, "totalReturn"))}`}{row.savedAt ? ` · ${row.savedAt.slice(0, 10)}` : ""}</small></div><div className="portfolio-actions"><button className="btn" type="button" aria-label={`${savedLabel(row)} 결과 열기`} onClick={() => void open(row)} disabled={!!busy}>{busy === `open-${row.id}` ? "여는 중" : "열기"}</button><button className="btn" type="button" aria-label={`${savedLabel(row)} 결과 지우기`} onClick={() => void remove(row)} disabled={!!busy}>{busy === `delete-${row.id}` ? "지우는 중" : confirmDelete === row.id ? "정말 지울까요?" : "지우기"}</button></div></li>)}</ul></div>}
    {note && <p className="react-reader-status" role="status">{note}</p>}{error && <p className="react-dashboard-error" role="alert">{error}</p>}
  </div>;
}
