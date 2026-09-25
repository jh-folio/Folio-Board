import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError, deleteJson, getJson, postJson } from "../../api";
import { money, percent, signOf, type PortfolioAnalytics, type Preset, type PresetFromCurrentDraft } from "./portfolioTypes";
import { blankPresetDraft, clonePresetDraft, draftFromPositions, draftFromPreset, draftsEqual, normalizePercentInput, presetSavePayload, type PresetDraft, validatePresetDraft } from "./presetEditor";
import { PresetCompare } from "./PresetCompare";

type PresetConflict = { readonly latest: Preset | null };
type ServerFieldErrors = Record<string, string>;

function requestDetail(reason: unknown): Record<string, unknown> | null {
  if (!(reason instanceof ApiRequestError) || !reason.payload || typeof reason.payload.detail !== "object" || reason.payload.detail === null) return null;
  return reason.payload.detail as Record<string, unknown>;
}
function formatDate(value: string | undefined): string { return value ? value.slice(0, 10) : "저장일 정보 없음"; }

/** 프리셋은 비교·백테스트의 공통 입력이다. 이 표면은 per-preset CAS와 percentage-string write만 소유한다. */
export function PortfolioTargets({ revision, onChanged, onDirtyChange }: {
  revision: number;
  onChanged?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [gaps, setGaps] = useState<PortfolioAnalytics["analytics"]["targetWeights"] | null>(null);
  const [presetRevision, setPresetRevision] = useState(0);
  const [compareId, setCompareId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"" | "from-current" | "save" | "save-as" | `delete:${string}`>("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<PresetDraft | null>(null);
  const [baseline, setBaseline] = useState<PresetDraft | null>(null);
  const [unsavedDraft, setUnsavedDraft] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<ServerFieldErrors>({});
  const [draftWarnings, setDraftWarnings] = useState<ReadonlyArray<{ code: string; ticker?: string; message: string }>>([]);
  const [conflict, setConflict] = useState<PresetConflict | null>(null);
  const [gapsLoading, setGapsLoading] = useState(false);
  const sequence = useRef(0);
  const fields = useRef<Record<string, HTMLInputElement | HTMLSelectElement | null>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await getJson<Preset[] | { presets: Preset[] }>("/api/portfolio/presets");
      const list = Array.isArray(payload) ? payload : payload.presets || [];
      setPresets(list);
      setCompareId((current) => current && list.some((row) => row.id === current && row.positions.length) ? current : list.find((row) => row.positions.length)?.id || "");
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "프리셋을 불러오지 못했습니다."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load, revision]);
  useEffect(() => {
    if (!compareId) { setGaps(null); setGapsLoading(false); return; }
    let cancelled = false;
    setGaps(null); setGapsLoading(true);
    void (async () => {
      try {
        const payload = await getJson<PortfolioAnalytics>(`/api/portfolio/analytics?presetId=${encodeURIComponent(compareId)}`);
        if (!cancelled) setGaps(payload.analytics.targetWeights);
      } catch { if (!cancelled) setGaps(null); }
      finally { if (!cancelled) setGapsLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [compareId, revision, presetRevision]);

  const dirty = Boolean(draft && (unsavedDraft || !draftsEqual(draft, baseline)));
  const validation = useMemo(() => draft ? validatePresetDraft(draft) : null, [draft]);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => () => { onDirtyChange?.(false); }, [onDirtyChange]);
  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const confirmDiscard = (message: string): boolean => !dirty || window.confirm(message);
  const openDraft = (next: PresetDraft, warnings: ReadonlyArray<{ code: string; ticker?: string; message: string }> = [], startsUnsaved = false) => {
    setDraft(next); setBaseline(next); setUnsavedDraft(startsUnsaved); setDraftWarnings(warnings); setFieldErrors({}); setConflict(null); setError(""); setNote("");
  };
  const newDraft = () => { if (confirmDiscard("저장하지 않은 프리셋 변경이 있습니다. 새 초안을 열면 변경이 사라집니다. 계속할까요?")) openDraft(blankPresetDraft()); };
  const fromCurrent = async () => {
    if (!confirmDiscard("저장하지 않은 프리셋 변경이 있습니다. 현재 보유 비중 초안을 열면 변경이 사라집니다. 계속할까요?")) return;
    setBusy("from-current"); setError(""); setNote("");
    try {
      const response = await postJson<PresetFromCurrentDraft>("/api/portfolio/presets/from-current", {});
      openDraft(draftFromPositions(response), response.warnings || [], response.positions.length > 0);
      setNote(response.positions.length ? "현재 보유 비중을 저장하지 않은 초안으로 불러왔습니다. 확인 후 저장하세요." : "현재 보유가 없어 빈 초안을 열었습니다.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "현재 보유 비중을 초안으로 만들지 못했습니다."); }
    finally { setBusy(""); }
  };
  const editPreset = (preset: Preset) => { if (confirmDiscard("저장하지 않은 프리셋 변경이 있습니다. 다른 프리셋을 열면 변경이 사라집니다. 계속할까요?")) openDraft(draftFromPreset(preset)); };
  const clonePreset = (preset: Preset) => { if (confirmDiscard("저장하지 않은 프리셋 변경이 있습니다. 복제 초안을 열면 변경이 사라집니다. 계속할까요?")) openDraft(clonePresetDraft(preset), [], preset.positions.length > 0); };
  const selectComparison = (id: string): boolean => {
    if (dirty && !window.confirm("저장하지 않은 프리셋 변경이 있습니다. 기준 프리셋을 바꾸기 전에 저장하거나 계속할까요?")) return false;
    setCompareId(id);
    return true;
  };
  const cancelDraft = () => {
    if (!confirmDiscard("저장하지 않은 프리셋 변경이 있습니다. 편집을 취소할까요?")) return;
    setDraft(null); setBaseline(null); setUnsavedDraft(false); setFieldErrors({}); setDraftWarnings([]); setConflict(null);
  };
  const updateDraft = (next: PresetDraft) => { setDraft(next); setFieldErrors({}); setConflict(null); };
  const updateRow = (index: number, field: "ticker" | "weightPercent", value: string) => {
    if (!draft) return;
    updateDraft({ ...draft, normalizeWeights: field === "weightPercent" ? false : draft.normalizeWeights, rows: draft.rows.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row) });
  };
  const validateRowOnBlur = (index: number) => {
    if (!draft) return;
    const next = { ...draft, rows: draft.rows.map((row, rowIndex) => rowIndex === index ? { ...row, ticker: row.ticker.trim().toUpperCase(), weightPercent: normalizePercentInput(row.weightPercent) } : row) };
    const validationAfterBlur = validatePresetDraft(next);
    setDraft(next); setConflict(null);
    setFieldErrors((current) => {
      const errors = { ...current };
      delete errors[`row-${index}-ticker`]; delete errors[`row-${index}-weight`];
      for (const key of [`row-${index}-ticker`, `row-${index}-weight`]) if (validationAfterBlur.errors[key]) errors[key] = validationAfterBlur.errors[key];
      return errors;
    });
  };
  const addRow = () => { if (draft) { sequence.current += 1; updateDraft({ ...draft, rows: [...draft.rows, { key: `new-${sequence.current}`, ticker: "", weightPercent: "" }] }); } };
  const removeRow = (index: number) => { if (draft) updateDraft({ ...draft, normalizeWeights: false, rows: draft.rows.filter((_, rowIndex) => rowIndex !== index) }); };
  const focusFirstError = (errors: ServerFieldErrors) => { const key = Object.keys(errors).find((item) => item !== "total") || "name"; window.setTimeout(() => fields.current[key]?.focus(), 0); };
  const mergeServerErrors = (reason: unknown): ServerFieldErrors | null => {
    const detail = requestDetail(reason);
    if (!(reason instanceof ApiRequestError) || reason.status !== 422 || detail?.code !== "preset_validation_failed" || !Array.isArray(detail.errors)) return null;
    const next: ServerFieldErrors = {};
    for (const item of detail.errors) {
      if (!item || typeof item !== "object") continue;
      const row = typeof (item as { row?: unknown }).row === "number" ? (item as { row: number }).row : null;
      const field = typeof (item as { field?: unknown }).field === "string" ? (item as { field: string }).field : "";
      const message = typeof (item as { message?: unknown }).message === "string" ? (item as { message: string }).message : "입력을 확인하세요.";
      next[row === null ? field || "total" : `row-${row}-${field === "weightPercent" || field === "weight" ? "weight" : "ticker"}`] = message;
    }
    return next;
  };
  const saveDraft = async (saveAs: boolean) => {
    if (!draft || !validation) return;
    if (!saveAs && draft.id && !dirty) { setNote("변경된 내용이 없습니다."); return; }
    if (!validation.valid) { setFieldErrors(validation.errors); setError("입력 오류를 고친 뒤 저장하세요."); focusFirstError(validation.errors); return; }
    setBusy(saveAs ? "save-as" : "save"); setError(""); setNote("");
    try {
      const saved = await postJson<Preset>("/api/portfolio/presets", presetSavePayload(saveAs ? { ...draft, id: undefined, revision: undefined } : draft));
      const next = draftFromPreset(saved);
      setDraft(next); setBaseline(next); setUnsavedDraft(false); setDraftWarnings([]); setFieldErrors({}); setConflict(null);
      setGapsLoading(true); setGaps(null); setCompareId(saved.id); setPresetRevision((current) => current + 1);
      await load(); onChanged?.(); setNote(saveAs ? `${saved.name}을(를) 새 프리셋으로 저장했습니다.` : `${saved.name}을(를) 저장했습니다.`);
    } catch (reason) {
      const serverErrors = mergeServerErrors(reason);
      if (serverErrors) { setFieldErrors(serverErrors); setError("입력 오류가 있어 저장하지 않았습니다."); focusFirstError(serverErrors); }
      else {
        const detail = requestDetail(reason);
        if (reason instanceof ApiRequestError && reason.status === 409 && detail?.code === "preset_revision_conflict") {
          setConflict({ latest: detail.latest && typeof detail.latest === "object" ? detail.latest as Preset : null });
          setError("다른 화면에서 이 프리셋이 바뀌었습니다. 현재 편집 내용은 그대로 보존했습니다.");
        } else setError(reason instanceof Error ? reason.message : "프리셋을 저장하지 못했습니다.");
      }
    } finally { setBusy(""); }
  };
  const reloadLatest = () => {
    if (!conflict?.latest || !window.confirm("현재 편집 내용을 버리고 최신 저장본을 불러올까요?")) return;
    openDraft(draftFromPreset(conflict.latest)); setNote("최신 저장본을 불러왔습니다.");
  };
  const removePreset = async (preset: Preset) => {
    if (!confirmDiscard("저장하지 않은 프리셋 변경이 있습니다. 삭제 전에 이 변경은 사라집니다. 계속할까요?")) return;
    if (!window.confirm(`${preset.name}을(를) 삭제할까요? 이 작업은 되돌릴 수 없습니다.`)) return;
    setBusy(`delete:${preset.id}`); setError("");
    try {
      await deleteJson(`/api/portfolio/presets/${encodeURIComponent(preset.id)}`, { expectedRevision: preset.revision });
      if (compareId === preset.id) { setCompareId(""); setGaps(null); }
      if (draft?.id === preset.id) { setDraft(null); setBaseline(null); setUnsavedDraft(false); }
      setPresetRevision((current) => current + 1);
      await load(); onChanged?.(); setNote(`${preset.name}을(를) 삭제했습니다.`);
    } catch (reason) {
      const detail = requestDetail(reason);
      setError(reason instanceof ApiRequestError && reason.status === 409 && detail?.code === "preset_revision_conflict" ? "다른 화면에서 프리셋이 바뀌었거나 삭제되었습니다. 목록을 다시 확인하세요." : reason instanceof Error ? reason.message : "프리셋을 삭제하지 못했습니다.");
    } finally { setBusy(""); }
  };

  return <div className="portfolio-targets">
    <div className="portfolio-block">
      <div className="portfolio-block__head"><h3>{draft ? (draft.id ? "프리셋 편집" : "새 프리셋") : "프리셋 만들기"}</h3></div>
      {draft ? <section className="portfolio-preset-editor surface--group" aria-label="프리셋 편집기">
        <p className="portfolio-note">목표 비중은 퍼센트 단위입니다. 1은 1%, 0.5는 0.5%를 뜻합니다.</p>
        <p className="portfolio-note">{draft.id ? (dirty ? "저장하지 않은 변경이 있습니다." : "저장된 프리셋입니다.") : (unsavedDraft ? "저장하지 않은 초안입니다." : "새 프리셋 초안입니다.")}</p>
        {draftWarnings.map((warning, index) => <p key={`${warning.code}:${warning.ticker || index}`} className="react-dashboard-warning" role="alert">{warning.ticker ? `${warning.ticker} · ${warning.message}` : warning.message}</p>)}
        <div className="portfolio-preset-editor__meta">
          <label className="field"><span>프리셋 이름</span><input ref={(node) => { fields.current.name = node; }} disabled={!!busy} value={draft.name} aria-invalid={Boolean(fieldErrors.name)} aria-describedby={fieldErrors.name ? "preset-name-error" : undefined} onChange={(event) => updateDraft({ ...draft, name: event.target.value })} onBlur={() => updateDraft({ ...draft, name: draft.name.trim() })} /></label>
          <label className="field"><span>기준 통화</span><select ref={(node) => { fields.current.baseCurrency = node; }} disabled={!!busy} value={draft.baseCurrency} aria-invalid={Boolean(fieldErrors.baseCurrency)} onChange={(event) => updateDraft({ ...draft, baseCurrency: event.target.value === "KRW" ? "KRW" : "USD" })}><option value="USD">USD</option><option value="KRW">KRW</option></select></label>
        </div>
        {fieldErrors.name && <p id="preset-name-error" className="portfolio-field-error" role="alert">{fieldErrors.name}</p>}
        {fieldErrors.baseCurrency && <p className="portfolio-field-error" role="alert">{fieldErrors.baseCurrency}</p>}
        <div className="portfolio-preset-editor__rows" aria-label="목표 종목과 비중">
          {draft.rows.map((row, index) => {
            const tickerError = fieldErrors[`row-${index}-ticker`]; const weightError = fieldErrors[`row-${index}-weight`];
            return <div className="portfolio-preset-editor__row surface--inset" key={row.key}>
              <label className="field"><span>종목 코드 {index + 1}</span><input ref={(node) => { fields.current[`row-${index}-ticker`] = node; }} maxLength={16} disabled={!!busy} value={row.ticker} aria-invalid={Boolean(tickerError)} aria-describedby={tickerError ? `preset-row-${index}-ticker-error` : undefined} autoCapitalize="characters" onChange={(event) => updateRow(index, "ticker", event.target.value)} onBlur={() => validateRowOnBlur(index)} /></label>
              <label className="field"><span>목표 비중 {index + 1}</span><input ref={(node) => { fields.current[`row-${index}-weight`] = node; }} type="text" inputMode="decimal" maxLength={256} disabled={!!busy} value={row.weightPercent} aria-invalid={Boolean(weightError)} aria-describedby={weightError ? `preset-row-${index}-weight-error` : undefined} onChange={(event) => updateRow(index, "weightPercent", event.target.value)} onBlur={() => validateRowOnBlur(index)} /></label>
              <button className="btn btn--text btn--sm" type="button" aria-label={`종목 ${index + 1} 삭제`} disabled={!!busy} onClick={() => removeRow(index)}>삭제</button>
              {tickerError && <p id={`preset-row-${index}-ticker-error`} className="portfolio-field-error" role="alert">{tickerError}</p>}
              {weightError && <p id={`preset-row-${index}-weight-error`} className="portfolio-field-error" role="alert">{weightError}</p>}
            </div>;
          })}
        </div>
        <div className="portfolio-preset-editor__sum" role="status" aria-live="polite"><strong>합계 {validation?.total === null ? "확인 필요" : `${validation?.total}%`}</strong>{validation?.total !== "100" && draft.rows.length > 0 && <label className="portfolio-normalize"><input type="checkbox" checked={draft.normalizeWeights} disabled={!!busy || !validation?.canNormalize} onChange={(event) => updateDraft({ ...draft, normalizeWeights: event.target.checked })} /> 합계를 100%로 정규화하여 저장</label>}</div>
        {fieldErrors.total && <p className="portfolio-field-error" role="alert">{fieldErrors.total}</p>}
        <div className="portfolio-preset-editor__actions"><button className="btn" type="button" disabled={!!busy} onClick={addRow}>종목 추가</button><button className="btn btn--text" type="button" disabled={!!busy} onClick={cancelDraft}>취소</button>{draft.id && !conflict && <button className="btn" type="button" disabled={!!busy} onClick={() => void saveDraft(true)}>{busy === "save-as" ? "저장 중" : "다른 이름으로 저장"}</button>}<button className={`btn${dirty || !draft.id ? " btn--primary" : ""}`} type="button" disabled={!!busy} onClick={() => void saveDraft(false)}>{busy === "save" ? "저장 중" : "프리셋 저장"}</button></div>
        {conflict && <div className="portfolio-preset-conflict" role="alert"><p>{conflict.latest ? "저장된 프리셋이 다른 화면에서 바뀌었습니다. 현재 편집 내용은 보존되어 있습니다." : "저장된 프리셋이 다른 화면에서 삭제되었습니다. 현재 내용을 새 프리셋으로 저장할 수 있습니다."}</p><div>{conflict.latest && <button className="btn" type="button" disabled={!!busy} onClick={reloadLatest}>최신 저장본 불러오기</button>}<button className="btn" type="button" disabled={!!busy} onClick={() => void saveDraft(true)}>다른 이름으로 저장</button></div></div>}
      </section> : <><p className="portfolio-note">비중을 담은 포트폴리오 초안입니다. 현재 보유와의 차이를 보고, 백테스트와 비교에 사용합니다.</p><div className="portfolio-inline-form"><button className="btn" type="button" disabled={!!busy} onClick={newDraft}>새 프리셋</button><button className="btn btn--primary" type="button" disabled={!!busy} onClick={() => void fromCurrent()}>{busy === "from-current" ? "초안 만드는 중" : "현재 보유에서 초안 만들기"}</button></div></>}
      {loading ? <p className="portfolio-empty" role="status">프리셋을 불러오는 중입니다.</p> : presets.length === 0 ? <p className="portfolio-empty">저장한 프리셋이 없습니다. 빈 프리셋을 만들거나 현재 보유 비중으로 시작하세요.</p> : <ul className="portfolio-preset-list" aria-label="저장한 프리셋">{presets.map((preset) => <li key={preset.id} className="portfolio-preset surface"><div><strong>{preset.name}</strong><small>{preset.positions.length}종목 · 합계 {percent(preset.weightTotal ?? 0)} · {formatDate(preset.updatedAt)}</small></div><div className="portfolio-preset__actions"><button className="btn btn--sm" type="button" disabled={!!busy} aria-label={`편집 ${preset.name}`} onClick={() => editPreset(preset)}>편집</button><button className="btn btn--sm" type="button" disabled={!!busy} aria-label={`복제 ${preset.name}`} onClick={() => clonePreset(preset)}>복제</button><button className="btn btn--sm" type="button" disabled={!!busy} aria-label={`비교 ${preset.name}`} onClick={() => selectComparison(preset.id)}>비교</button><button className="btn btn--sm btn--danger" type="button" aria-label={`삭제 ${preset.name}`} disabled={!!busy} onClick={() => void removePreset(preset)}>{busy === `delete:${preset.id}` ? "삭제 중" : "삭제"}</button></div></li>)}</ul>}
    </div>
    {presets.some((preset) => preset.positions.length > 0) && <div className="portfolio-block"><div className="portfolio-block__head"><h3>저장된 프리셋 기준 비교</h3><label className="field"><span>기준 프리셋</span><select disabled={!!busy} value={compareId} onChange={(event) => { if (!selectComparison(event.target.value)) event.currentTarget.value = compareId; }}>{presets.filter((preset) => preset.positions.length > 0).map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label></div><p className="portfolio-note">여기서는 저장된 프리셋만 기준으로 사용합니다. 편집 중인 초안은 저장 전까지 비교에 반영되지 않습니다.</p>{gapsLoading ? <p className="portfolio-note" role="status">현재 보유와의 차이를 불러오는 중입니다.</p> : <div className="portfolio-table-scroll" tabIndex={0} role="region" aria-label="현재 보유와의 차이 표"><table className="portfolio-mini-table"><thead><tr><th scope="col">종목</th><th scope="col">현재</th><th scope="col">목표</th><th scope="col">차이</th><th scope="col">조정 금액 (USD)</th></tr></thead><tbody>{(gaps?.items ?? []).map((row) => <tr key={row.id || row.ticker}><th scope="row">{row.name || row.ticker}</th><td>{percent(row.currentWeight)}</td><td>{percent(row.targetWeight)}</td><td data-sign={signOf(row.diffWeight)}>{percent(row.diffWeight)}</td><td data-sign={signOf(row.diffAmountUsd)}>{money(row.diffAmountUsd)}</td></tr>)}</tbody></table></div>}<p className="portfolio-note">차이가 양수면 이 프리셋보다 많이 들고 있다는 뜻입니다. 세금·수수료·최소 매매 단위는 반영하지 않았습니다.</p></div>}
    <div className="portfolio-block"><div className="portfolio-block__head"><h3>프리셋 비교</h3></div><p className="portfolio-note">프리셋 2개 이상을 골라 같은 기간·같은 리밸런싱 조건으로 나란히 돌려 봅니다.</p><PresetCompare presets={presets} /></div>
    {note && <p className="react-reader-status" role="status">{note}</p>}{error && <p className="react-dashboard-error" role="alert">{error}</p>}{error && !loading && <button className="btn btn--text btn--sm" type="button" onClick={() => void load()}>다시 불러오기</button>}
  </div>;
}
