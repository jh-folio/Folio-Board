import { useState } from "react";
import { ReportBody } from "../reportReader/ReportBody";
import { inputState, sourceState, sourceLink, timeLabel } from "./copy";
import { slotLabels, type Input, type Slot } from "./types";

const labels: Record<string, string> = { core_thesis: "이유", falsification_triggers: "판단을 바꿀 조건", next_checkpoints: "다음 확인", toleratedChanges: "감수할 변화", key_assumptions: "핵심 가정", supporting_signals: "지지 신호", weakening_signals: "약화 신호", content: "당시 이유", conditionResponse: "조건 응답", fieldPresence: "작성 상태", recordedAt: "실제 기록 시각", userStatedAt: "원래 사용자 보고 시점", editSource: "작성 경로", kindAtWrite: "당시 이유 분류", requiredReturn: "요구수익률", minMarginOfSafety: "최소 안전마진", holdingYears: "검토 기간", allowAboveHistoricalRange: "과거 범위 초과 가정 허용", snapshot: "당시 계산", criteria: "당시 내 기준", results: "계산 결과", inputs: "계산 입력", scenarios: "시나리오", horizon: "기간(년)", label: "구분", irr: "연환산 수익률", returnAttribution: "주가 수익 출처", reviewRows: "수정 필요 항목", asOf: "기준일", generatedAt: "생성 시각", state: "상태", status: "상태", message: "설명", reason: "사유", uncertainties: "불확실성", counterEvidence: "반대 근거", contradictions: "상충 근거", summary: "요약", markdown: "본문", company: "기업", title: "제목", sourceLedger: "출처 계보", sources: "출처", sourceRefs: "근거 연결", quality: "품질 점검", dataGaps: "자료 공백", interpretation: "해석", states: "거시 관측", profile: "기업 노출", marketState: "시장 맥락", positionReviews: "해당 종목 리뷰", nextChecks: "다음 확인", basisRefs: "당시 근거 참조", checkpoints: "확인 항목", verdict: "판정", supportingEvidence: "지지 근거", challengingEvidence: "반대 근거", previousRevisionId: "이전 판본", revisionId: "판본 식별자", revision: "판본", id: "식별자", ticker: "종목", market: "시장", name: "이름", value: "값", notice: "해석 범위", scopeCopy: "해석 범위", blockingReasons: "추가 확인이 필요한 이유", warnings: "주의점" };
const values: Record<string, string> = { unanswered: "답하지 않음", unknown: "알 수 없음", legacy_unknown: "이전 기록 · 작성 상태 미확인", written: "작성됨", skipped: "건너뜀", manual: "직접 작성", manual_edit: "직접 수정", base: "기준", conservative: "보수", optimistic: "낙관", met: "충족", unmet: "미충족", unavailable: "확인 불가", stale: "다시 확인 필요", ready_for_review: "검토 준비", conditions_missing: "조건 없음" };

function Entries({ entries }: { entries: [string, unknown][] }) {
  const [limit, setLimit] = useState(30);
  return <><dl className="case-values">{entries.slice(0, limit).map(([key, value]) => <div key={key}><dt>{labels[key] || key}</dt><dd><Value value={value} /></dd></div>)}</dl>{entries.length > limit && <button className="btn btn--text" type="button" onClick={() => setLimit(limit + 50)}>다음 50항목 보기 ({entries.length - limit}개 남음)</button>}</>;
}
export function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span>기록 없음</span>;
  if (Array.isArray(value)) return value.length ? <Entries entries={value.map((item, i) => [String(i + 1), item])} /> : <span>기록 없음</span>;
  if (typeof value === "object") return <Entries entries={Object.entries(value as Record<string, unknown>)} />;
  return <span className="case-text">{typeof value === "boolean" ? value ? "예" : "아니오" : values[String(value)] || String(value)}</span>;
}
export function PreservedInput({ name, item, availability, onPurge, onCorrection }: { name: Slot; item: Input; availability?: Array<{ status: string }>; onPurge?: () => void; onCorrection?: () => void }) {
  const link = sourceLink(item.ref);
  const markdown = typeof item.content?.markdown === "string" ? item.content.markdown : "";
  const rest = item.content ? Object.entries(item.content).filter(([key]) => key !== "markdown") : [];
  return <details className="case-input"><summary>{slotLabels[name]} · {inputState(item.status)}</summary><div>
    <p>{item.ref.asOf ? `당시 기준: ${timeLabel(item.ref.asOf)}` : "기준 시각 미확인"}{item.ref.revision ? ` · ${item.ref.revision}번째 판본` : ""}</p>
    {item.ref.identityStatus === "unverified" && <p>사용자가 연결한 관련 맥락입니다. 동일 증권의 자료인지는 확인되지 않았습니다.</p>}
    {item.content && <>{markdown && <ReportBody markdown={markdown} />}<Entries entries={rest} /></>}
    {!item.content && <p>{inputState(item.status)}{item.reason === "review_identity_unverified" ? " · 당시 리뷰에 시장 식별 정보가 없어 같은 종목으로 확정하지 않았습니다." : ""}</p>}
    {Boolean(item.preservationScope?.omittedFieldCount) && <p>읽기용 필드만 보존했습니다. 원시 첨부·경로 등 보존 범위 밖 필드 {item.preservationScope?.omittedFieldCount}개는 포함하지 않았습니다.</p>}
    {availability?.length ? <div className="case-current"><strong>지금 확인한 원본</strong>{availability.map((row, index) => <p key={index}>{sourceState(row.status)}{item.status === "purged" ? " · 이 기록의 보존본문도 삭제됨" : ""}</p>)}</div> : null}
    <div className="case-actions">{link && <a className="btn btn--text" href={link}>현재 자료 열기</a>}{onCorrection && <button className="btn btn--text" type="button" onClick={onCorrection}>이후 자료 연결 확인</button>}{onPurge && item.content && <button className="btn btn--danger" type="button" onClick={onPurge}>이 보존본문 삭제</button>}</div>
  </div></details>;
}
