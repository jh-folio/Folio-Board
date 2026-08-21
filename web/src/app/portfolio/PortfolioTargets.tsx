import { useCallback, useEffect, useState } from "react";
import { deleteJson, getJson, postJson } from "../../api";
import { money, percent, signOf, type PortfolioAnalytics, type Preset } from "./portfolioTypes";
import { PresetCompare } from "./PresetCompare";

/** 프리셋 — 목표 비중을 담은 포트폴리오 초안.
 *
 *  **프리셋이 1급 시민이다**(0.5.4). 예전 이름은 "목표 비중"이었고 화면도 그 한 가지
 *  쓰임(현재 보유와의 차이)만 보여줬다. 그런데 백테스트의 입력도, 비교 백테스트의
 *  입력도 프리셋이다 — 목표는 프리셋으로 할 수 있는 **여러 일 중 하나**다.
 *
 *  `/api/portfolio/presets`는 프리셋을 저장하고, `/api/portfolio/analytics`의
 *  `targetWeights`가 현재 비중과의 차이를 계산해 준다. 둘 다 서버가 하던 일이고
 *  화면만 없었다.
 *
 *  `현재 보유에서 만들기`는 지금 평가액 비중을 그대로 담는다. 예전에는 이미 설정된
 *  `targetWeight`만 담아서 **항상 빈 프리셋**이 나왔다(그 값을 넣을 칸이 화면에 없다).
 */

export function PortfolioTargets({ revision, onChanged }: { revision: number; onChanged: () => void }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [gaps, setGaps] = useState<PortfolioAnalytics["analytics"]["targetWeights"] | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState("");
  const [compareId, setCompareId] = useState("");
  const [today] = useState(() => new Date().toISOString().slice(0, 10));

  const load = useCallback(async () => {
    try {
      const payload = await getJson<Preset[] | { presets: Preset[] }>("/api/portfolio/presets");
      const list = Array.isArray(payload) ? payload : payload.presets || [];
      setPresets(list);
      // 비중이 담긴 목표만 비교 대상이 된다. 빈 목표를 고르면 표가 전부 0이 된다.
      // 지금 고른 목표가 목록에서 사라졌으면(지웠거나 다른 탭에서 없앴거나) 다시 고른다 —
      // 그대로 두면 없는 presetId로 조회해 전 종목이 "목표 0%·전량 매도"로 그려진다.
      setCompareId((current) => {
        if (current && list.some((row) => row.id === current && row.positions.length)) return current;
        return list.find((row) => row.positions.length)?.id || "";
      });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "목표 비중을 불러오지 못했습니다.");
    }
  }, []);

  useEffect(() => { void load(); }, [load, revision]);

  useEffect(() => {
    if (!compareId) { setGaps(null); return; }
    let cancelled = false;
    void (async () => {
      try {
        const payload = await getJson<PortfolioAnalytics>(
          `/api/portfolio/analytics?presetId=${encodeURIComponent(compareId)}`,
        );
        if (!cancelled) setGaps(payload.analytics.targetWeights);
      } catch {
        if (!cancelled) setGaps(null);
      }
    })();
    return () => { cancelled = true; };
  }, [compareId, revision]);

  const createFromCurrent = async () => {
    setBusy("create");
    setNote("");
    setError("");
    try {
      const preset = await postJson<Preset>("/api/portfolio/presets/from-current", {
        name: name.trim() || "현재 포트폴리오 목표 비중",
      });
      setName("");
      await load();
      onChanged();
      setNote(preset.positions.length
        ? `${preset.name} — ${preset.positions.length}개 종목의 현재 비중을 목표로 저장했습니다.`
        : "보유 종목이 없어 빈 목표가 만들어졌습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "목표를 만들지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  const remove = async (preset: Preset) => {
    if (confirmDelete !== preset.id) { setConfirmDelete(preset.id); return; }
    setBusy(preset.id);
    setError("");
    try {
      await deleteJson(`/api/portfolio/presets/${encodeURIComponent(preset.id)}`, {});
      setConfirmDelete("");
      // 지운 목표를 비교 대상으로 들고 있으면 표가 옛 수치인 채로 남는다.
      if (compareId === preset.id) { setCompareId(""); setGaps(null); }
      await load();
      onChanged();
      setNote(`${preset.name}을(를) 지웠습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "지우지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="portfolio-targets">
      <div className="portfolio-block">
        <div className="portfolio-block__head">
          <h3>프리셋</h3>
        </div>
        <p className="portfolio-note">
          비중을 담은 포트폴리오 초안입니다. 현재 보유와 얼마나 벌어졌는지 보고, 백테스트를
          돌리고, 여러 개를 나란히 비교하는 데 씁니다.
        </p>
        <div className="portfolio-inline-form">
          <label className="field">
            <span>프리셋 이름</span>
            <input
              value={name}
              placeholder="현재 포트폴리오 목표 비중"
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <button className="btn btn--primary" type="button" onClick={() => void createFromCurrent()} disabled={!!busy}>
            {busy === "create" ? "만드는 중" : "현재 보유에서 만들기"}
          </button>
        </div>

        {presets.length === 0 ? (
          <p className="portfolio-empty">저장한 프리셋이 없습니다.</p>
        ) : (
          <ul className="portfolio-preset-list">
            {presets.map((preset) => (
              <li key={preset.id} className="portfolio-preset surface">
                <div>
                  <strong>{preset.name}</strong>
                  <small>
                    {preset.positions.length}종목 · 합계 {percent(preset.weightTotal ?? 0)}
                    {preset.updatedAt ? ` · ${preset.updatedAt.slice(0, 10)}` : ""}
                  </small>
                </div>
                <button
                  className="btn"
                  type="button"
                  onClick={() => void remove(preset)}
                  disabled={busy === preset.id}
                >
                  {busy === preset.id ? "지우는 중" : confirmDelete === preset.id ? "정말 지울까요?" : "지우기"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {presets.some((preset) => preset.positions.length > 0) && (
        <div className="portfolio-block">
          <div className="portfolio-block__head">
            {/* 프리셋을 고른 뒤의 한 가지 보기다 — 프리셋 자체가 아니다. */}
            <h3>현재 보유와의 차이</h3>
            <label className="field">
              <span>기준 프리셋</span>
              <select value={compareId} onChange={(event) => setCompareId(event.target.value)}>
                {presets.filter((preset) => preset.positions.length > 0).map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.name}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="portfolio-table-scroll">
            <table className="portfolio-mini-table">
              <thead>
                <tr>
                  <th scope="col">종목</th>
                  <th scope="col">현재</th>
                  <th scope="col">목표</th>
                  <th scope="col">차이</th>
                  <th scope="col">조정 금액 (USD)</th>
                </tr>
              </thead>
              <tbody>
                {(gaps?.items ?? []).map((row) => (
                  <tr key={row.id || row.ticker}>
                    <th scope="row">{row.name || row.ticker}</th>
                    <td>{percent(row.currentWeight)}</td>
                    <td>{percent(row.targetWeight)}</td>
                    <td data-sign={signOf(row.diffWeight)}>{percent(row.diffWeight)}</td>
                    <td data-sign={signOf(row.diffAmountUsd)}>{money(row.diffAmountUsd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="portfolio-note">
            차이가 양수면 이 프리셋보다 많이 들고 있다는 뜻입니다. 세금·수수료·최소 매매
            단위는 반영하지 않았습니다.
          </p>
        </div>
      )}

      {/* 프리셋으로 할 수 있는 두 번째 일. 서버는 예전부터 이걸 만들 수 있었는데
          부르는 화면이 없었다(`POST /api/portfolio/backtests/compare`). */}
      <div className="portfolio-block">
        <div className="portfolio-block__head">
          <h3>프리셋 비교</h3>
        </div>
        <p className="portfolio-note">
          프리셋 2개 이상을 골라 같은 기간·같은 리밸런싱 조건으로 나란히 돌려 봅니다.
          기간과 조건을 바꾸려면 <strong>백테스트</strong> 탭을 씁니다.
        </p>
        <PresetCompare presets={presets} start="2020-01-01" end={today} rebalance="monthly" />
      </div>

      {note && <p className="react-reader-status" role="status">{note}</p>}
      {error && <p className="react-dashboard-error" role="alert">{error}</p>}
    </div>
  );
}
