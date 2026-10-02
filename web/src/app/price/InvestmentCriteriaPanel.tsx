import { useEffect, useState } from "react";
import { CriteriaForm, loadCriteria } from "./CriteriaForm";
import type { Criteria } from "./types";

/** 설정 → 관리 → 투자 기준. 모든 종목에 똑같이 적용되는 전역 기준 하나. */
export function InvestmentCriteriaPanel() {
  const [criteria, setCriteria] = useState<Criteria | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    const control = new AbortController();
    loadCriteria(control.signal).then(value => { setCriteria(value); setState("ready"); }).catch(() => { if (!control.signal.aborted) setState("error"); });
    return () => control.abort();
  }, []);
  return (
    <section className="settings-panel input-panel" aria-labelledby="investmentCriteriaTitle">
      <div className="input-panel-header">
        <div>
          <h3 id="investmentCriteriaTitle">투자 기준</h3>
          <p>가격 탭이 계산 결과와 비교하는 내 기준입니다. 정하지 않으면 비교하지 않고 &ldquo;기준 없음&rdquo;으로 보여 줍니다.</p>
        </div>
      </div>
      {state === "loading" && <p className="price-meta" role="status">불러오는 중입니다…</p>}
      {state === "error" && <p className="react-dashboard-error" role="alert">투자 기준을 읽지 못했습니다. 잠시 뒤 다시 열어 주세요.</p>}
      {state === "ready" && <CriteriaForm idPrefix="settings-criteria" initial={criteria} onSaved={setCriteria} />}
    </section>
  );
}
