import { useRef } from "react";
import { conclusions, evidenceLevels, signals, scopes, assessments, type Condition, type OwnershipView, type ReviewFields } from "./ownershipTypes";
import { slots, slotLabels, type Slot } from "./types";

export function OwnershipForm({ view, value, onChange, kind, uncertainty, onUncertainty, excluded, onExcluded, busy, onSubmit, onClose }: {
  view: OwnershipView; value: ReviewFields; onChange: (value: ReviewFields) => void; kind: string;
  uncertainty: string; onUncertainty: (value: string) => void; excluded: Slot[]; onExcluded: (value: Slot[]) => void;
  busy: boolean; onSubmit: () => void; onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const conditionKey = (condition: Condition) => condition.origin === "outside_conditions" ? "outside" : JSON.stringify([condition.origin, condition.reasonRevisionId, condition.field, condition.index]);
  const selectedCondition = conditionKey(value.condition);
  const staleCondition = !value.previousReviewJournalId && selectedCondition !== "outside" && !view.conditionOptions.some(row => conditionKey(row) === selectedCondition);
  const set = <K extends keyof ReviewFields>(key: K, changed: ReviewFields[K]) => onChange({ ...value, [key]: changed });
  const source = value.observation.sourceRefs[0] || {};
  const setSource = (key: string, changed: string) => {
    const row = { ...source, [key]: changed };
    set("observation", { ...value.observation, sourceRefs: Object.values(row).some(Boolean) ? [row] : [] });
  };
  const textArea = (key: "interpretation" | "companyView" | "priceView" | "cashNeed" | "portfolioContext" | "nextCheck" | "exceptionBasis" | "exceptionEndEvent" | "expectedPath" | "observedPath", label: string, rows = 2) => <label className="field">{label}<textarea maxLength={6000} rows={rows} value={value[key] || ""} onChange={event => set(key, event.target.value)} /></label>;
  return <form className="surface surface--group case-form ownership-form" onSubmit={event => { event.preventDefault(); onSubmit(); }}>
    <h4 ref={heading} tabIndex={-1}>{kind === "postmortem" ? "지금 기준으로 복기" : value.previousReviewJournalId ? "미해결 항목 이어서 검토" : "내 검토 남기기"}</h4>
    <p>짧게 쓰거나 비워 두어도 됩니다. 아래 상태는 내 판단이며 기존 이유·시스템 판정을 바꾸지 않습니다.</p>
    {value.previousReviewJournalId ? <p>이전 기록의 조건과 최초 발견 시점을 유지하며 새 기록으로 이어집니다.</p> : <label className="field">연결할 당시 조건<select value={selectedCondition} onChange={event => {
      const option = view.conditionOptions.find(row => conditionKey(row) === event.target.value);
      if (option) { const { text: _text, ...condition } = option; set("condition", condition); } else set("condition", { origin: "outside_conditions" });
    }}><option value="outside">기존 조건 밖의 변화 / 조건 미작성</option>{staleCondition && <option value={selectedCondition} disabled>이전 판본의 조건 — 다시 선택해 주세요</option>}{view.conditionOptions.map(row => <option key={conditionKey(row)} value={conditionKey(row)}>{row.origin === "original" ? "당시" : "현재"} · {row.text}</option>)}</select></label>}
    {staleCondition && <p role="status">자료를 다시 읽는 동안 선택한 조건의 판본이 바뀌었습니다. 초안은 유지했습니다. 연결할 조건을 다시 선택해 주세요.</p>}
    <label className="field">관찰한 사실<textarea value={value.observation.text} maxLength={6000} rows={3} onChange={event => set("observation", { ...value.observation, text: event.target.value })} /></label>
    <div className="case-form-grid"><label className="field">내 관찰 상태<select value={value.signal} onChange={event => set("signal", event.target.value)}>{Object.entries(signals).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="field">내가 본 근거 수준<select value={value.evidence} onChange={event => onChange({ ...value, evidence: event.target.value, resolution: "unresolved" })}>{Object.entries(evidenceLevels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div>
    <p>확인하지 못한 변화와 조건이 발생하지 않은 것은 다릅니다. 시스템 checkpoint와 Thesis 판정은 위 보존 자료에서 따로 읽습니다.</p>
    <details className="ownership-details"><summary>출처와 사건 시점 연결</summary><div className="case-form-grid">
      <label className="field">출처 주소<input type="url" value={source.url || ""} maxLength={1000} onChange={event => setSource("url", event.target.value)} /></label><label className="field">출처 제목<input value={source.title || ""} maxLength={220} onChange={event => setSource("title", event.target.value)} /></label>
      <label className="field">출처 식별자<input value={source.id || ""} maxLength={200} onChange={event => setSource("id", event.target.value)} /></label><label className="field">출처 판본<input value={source.revision || ""} maxLength={120} onChange={event => setSource("revision", event.target.value)} /></label>
      {([['eventAt', '사건 날짜'], ['publishedAt', '발표 날짜'], ['collectedAt', '수집 날짜']] as const).map(([key, label]) => <label className="field" key={key}>{label}<input type="date" value={value.observation[key] || ""} onChange={event => set("observation", { ...value.observation, [key]: event.target.value || null })} /></label>)}
    </div><p>모르는 시점은 비워 둡니다. 날짜만 아는 사건과 같은 날 수정한 기준의 선후는 확정할 수 없습니다. 여기에 연결한 내용은 사용자의 관찰 기록입니다.</p></details>
    {textArea("interpretation", "조건과 변화의 연결 해석")}
    <label className="field">아직 모르는 것·반대 근거<textarea value={uncertainty} maxLength={8000} rows={3} onChange={event => onUncertainty(event.target.value)} /></label>
    <details className="ownership-details"><summary>사업·가격·자금·구성을 따로 기록</summary>{textArea("companyView", "사업과 이유에 대한 내 검토")}{textArea("priceView", "가격과 내 기준에 대한 검토")}{textArea("cashNeed", "내 자금 필요의 변화")}{textArea("portfolioContext", "전체 보유 구성의 변화")}</details>
    <label className="field">내 판단<select value={value.conclusion} onChange={event => onChange({ ...value, conclusion: event.target.value, resolution: "unresolved" })}>{Object.entries(conclusions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    {value.conclusion === "new_reason" && <p>새 이유를 채택했다는 개인 기록입니다. 현재 이유 문장은 기존 투자 이유 화면에서 따로 수정하고 이전/새 판본의 변경 근거를 확인합니다.</p>}
    {value.conclusion === "exception" && <div className="case-form-grid">{textArea("exceptionBasis", "예외로 판단한 근거")}<label className="field">예외 종료 날짜<input type="date" value={value.exceptionEndAt || ""} onChange={event => set("exceptionEndAt", event.target.value || null)} /></label>{textArea("exceptionEndEvent", "예외 종료 사건")}</div>}
    {textArea("nextCheck", "다음에 확인할 것")}<label className="field">다음 확인 날짜<input type="date" value={value.nextCheckAt || ""} onChange={event => set("nextCheckAt", event.target.value || null)} /></label><p>기한은 UTC 날짜 기준입니다. 비워 두면 확인 계획의 공백으로 남습니다. 재예약해도 과거 미해결은 사라지지 않습니다.</p>
    <label className="ownership-check"><input type="checkbox" checked={value.resolution === "resolved"} onChange={event => set("resolution", event.target.checked ? "resolved" : "unresolved")} />이 항목을 해소된 것으로 기록</label>
    <p>보류·예외·결론 미정 또는 부족·상충·오래된·미평가 근거는 미해결로 남겨야 합니다.</p>
    {kind === "postmortem" && <section><h5>결과와 판단을 분리해 복기</h5><label className="field">내 회고 분류<select value={value.postmortemAssessment || "uncertain"} onChange={event => set("postmortemAssessment", event.target.value)}>{Object.entries(assessments).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>{textArea("expectedPath", "당시에 생각한 경로")}{textArea("observedPath", "이후 관측한 경로")}<p>지금 쓰는 회고는 과거 입력에 추가되지 않습니다. 수익률 결과와 판단 품질은 별개이며 실현 손익은 체결·세금·수수료·현금흐름 없이 계산하지 않습니다.</p></section>}
    <label className="ownership-check"><input type="checkbox" checked={value.completed} onChange={event => set("completed", event.target.checked)} />이번 범위의 검토를 마쳤음</label>
    <fieldset className="case-checks"><legend>이번에 확인한 범위{value.completed ? " (완료 표시 시 하나 이상)" : ""}</legend>{Object.entries(scopes).map(([key, label]) => <label key={key}><input type="checkbox" checked={value.checkedScope.includes(key)} onChange={event => set("checkedScope", event.target.checked ? [...value.checkedScope, key] : value.checkedScope.filter(item => item !== key))} />{label}</label>)}</fieldset>
    <p>검토 완료와 미해결은 함께 남을 수 있습니다. 이 표시는 기존 이유·Portfolio 전체 검토의 기한을 바꾸지 않습니다.</p>
    <details className="ownership-details"><summary>이번 기록에 보존할 입력</summary><fieldset className="case-checks"><legend>현재 자료 보존 범위</legend>{slots.map(slot => <label key={slot}><input type="checkbox" checked={!excluded.includes(slot)} onChange={event => onExcluded(event.target.checked ? excluded.filter(item => item !== slot) : [...excluded, slot])} />{slotLabels[slot]}</label>)}</fieldset><p>당시 기준 기록은 참조로 연결하며 다시 복사하지 않습니다. 민감한 내용이 있거나 5 MiB를 넘으면 항목을 제외하거나 원본을 정정해 주세요.</p></details>
    <div className="case-actions"><button className="btn btn--primary" disabled={busy || staleCondition} type="submit">점검 내용 미리보기</button><button className="btn btn--text" type="button" disabled={busy} onClick={onClose}>작성 닫기</button></div>
  </form>;
}
