import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError, getJson, postJson } from "../../api";
import type { Criteria } from "./types";

const FIELD_ERRORS: Record<string, string> = {
  invalid_number: "숫자로 적어 주세요.",
  out_of_range: "허용 범위를 벗어났습니다.",
  invalid_holding_years: "기본 보유 기간은 5년 또는 10년입니다.",
  holding_years_required: "숫자 기준을 저장하려면 기본 보유 기간을 골라 주세요.",
  revision_conflict: "다른 화면에서 기준이 바뀌었습니다. 입력한 값은 그대로 두었으니, 확인하고 다시 저장하면 새 기준으로 저장됩니다.",
};

export async function loadCriteria(signal?: AbortSignal): Promise<Criteria | null> {
  return (await getJson<{ criteria: Criteria | null }>("/api/valuation/criteria", { signal })).criteria;
}

/** 전역 투자 기준. 설정 → 관리와 가격 탭의 대화 상자가 같은 폼을 쓴다. 빈 칸은 "정하지 않음"이며 0과 다르다. */
export function CriteriaForm({ initial, onSaved, onCancel, idPrefix = "criteria" }: { initial: Criteria | null; onSaved: (criteria: Criteria | null) => void; onCancel?: () => void; idPrefix?: string }) {
  const [required, setRequired] = useState(initial?.requiredReturn ?? "");
  const [margin, setMargin] = useState(initial?.minMarginOfSafety ?? "");
  const [holding, setHolding] = useState(initial?.holdingYears ? String(initial.holdingYears) : "");
  const [current, setCurrent] = useState<Criteria | null>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    setCurrent(initial); setRequired(initial?.requiredReturn ?? ""); setMargin(initial?.minMarginOfSafety ?? "");
    setHolding(initial?.holdingYears ? String(initial.holdingYears) : "");
  }, [initial]);

  const changed = (required || "") !== (current?.requiredReturn ?? "") || (margin || "") !== (current?.minMarginOfSafety ?? "") || holding !== (current?.holdingYears ? String(current.holdingYears) : "");

  async function save(next: { required: string; margin: string; holding: string }) {
    setBusy(true); setError(""); setStatus("");
    try {
      const response = await postJson<{ criteria: Criteria }>("/api/valuation/criteria", {
        requiredReturn: next.required.trim() || null, minMarginOfSafety: next.margin.trim() || null,
        holdingYears: next.holding ? Number(next.holding) : null, expectedRevisionId: current?.revisionId ?? null,
      });
      setCurrent(response.criteria); setStatus("저장했습니다."); onSaved(response.criteria);
    } catch (err) {
      const code = err instanceof ApiRequestError ? err.code : "";
      setError(FIELD_ERRORS[code] || "저장하지 못했습니다. 입력한 값은 그대로 남겨 두었습니다.");
      // The edited values stay as typed; only the revision the next save is based on is refreshed. The dialog stays open with the message.
      if (code === "revision_conflict") void loadCriteria().then(latest => setCurrent(latest)).catch(() => undefined);
    } finally { setBusy(false); }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    if (!changed) { setStatus("변경 사항이 없습니다."); return; }
    void save({ required, margin, holding });
  }

  return (
    <form className="price-criteria-form" onSubmit={submit}>
      <div className="price-form">
        <label>원하는 연 수익률 (%)
          <input id={`${idPrefix}-required`} type="number" min={-99} max={100} step="any" placeholder="정하지 않음" value={required} onChange={e => setRequired(e.target.value)} />
        </label>
        <label>최소 안전마진 (%)
          <input id={`${idPrefix}-margin`} type="number" min={0} max={100} step="any" placeholder="정하지 않음" value={margin} onChange={e => setMargin(e.target.value)} />
        </label>
        <label>기본 보유 기간
          <select id={`${idPrefix}-holding`} value={holding} required={Boolean(required || margin)} onChange={e => setHolding(e.target.value)}>
            <option value="">고르지 않음</option><option value="5">5년</option><option value="10">10년</option>
          </select>
        </label>
      </div>
      <p className="price-meta">모든 종목에 똑같이 적용됩니다. 빈 칸은 &ldquo;정하지 않음&rdquo;이며 0과 다릅니다. 기준은 이 화면의 비교에만 쓰이고 보고서·이유·포트폴리오를 바꾸지 않습니다.</p>
      <div className="price-row">
        {onCancel && <button className="btn btn--text" type="button" onClick={() => { setRequired(current?.requiredReturn ?? ""); setMargin(current?.minMarginOfSafety ?? ""); setHolding(current?.holdingYears ? String(current.holdingYears) : ""); setError(""); setStatus(""); onCancel(); }}>취소</button>}
        <button className="btn" type="button" disabled={busy} onClick={() => { if (!current?.requiredReturn && !current?.minMarginOfSafety) { setStatus("지울 기준이 없습니다."); return; } setRequired(""); setMargin(""); void save({ required: "", margin: "", holding }); }}>기준 지우기</button>
        <button className={`btn${changed ? " btn--primary" : ""}`} type="submit" disabled={busy}>{busy ? "저장 중…" : "저장"}</button>
        {changed && <span className="price-meta">저장 안 된 변경이 있습니다</span>}
      </div>
      <p className="price-meta" role="status" aria-live="polite">{error || status}</p>
    </form>
  );
}
