import { PreservedInput, Value } from "./PreservedInput";
import { timeLabel } from "./copy";
import { slotLabels } from "./types";
import { assessments, conclusions, evidenceLevels, scopes, signals, type OwnershipView, type ReviewEntry, type SavedReview } from "./ownershipTypes";

const originalGaps: Record<string, string> = { original_not_recorded: "최초 기록 없음", personal_content_deleted: "개인본문이 삭제됨", journal_file_missing: "당시 기록 파일 없음", journal_integrity_error: "당시 기록의 내용 확인 실패", journal_deletion_pending: "당시 본문 삭제 마무리 필요", journal_not_found: "당시 기록 식별자를 찾을 수 없음" };
const inputChanges: Record<string, string> = { unavailable: "비교할 자료 부족", incomparable: "방법이 달라 직접 비교 불가", unchanged_input: "동일한 입력", changed_input: "입력 변경" };
const metricNames: Record<string, string> = { Revenue: "매출", "EPS Diluted": "희석 EPS", "Net Margin": "순이익률", g: "성장 가정", exitPE: "종료 PER 가정", payout: "배당성향 가정", irr: "연환산 시나리오 수익률" };
const numeric = (value: string | null | undefined, unit?: string) => value == null ? "자료 없음" : Number.isFinite(Number(value)) ? `${(Number(value) * (unit === "ratio" ? 100 : 1)).toLocaleString("ko-KR", { maximumFractionDigits: 4 })}${unit === "ratio" || unit === "%" ? "%" : unit === "multiple" ? "배" : unit ? ` ${unit}` : ""}` : "확인 불가";
export function ownershipTime(value?: string | null) { return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value} · 날짜까지만` : timeLabel(value); }

function Reason({ value, label }: { value: Record<string, unknown> | null; label: string }) {
  const body = (value?.content || {}) as Record<string, unknown>;
  return <section className="ownership-reason"><h5>{label}</h5><p className="case-text">{typeof body.core_thesis === "string" && body.core_thesis ? body.core_thesis : "보존된 이유 없음"}</p>
    <dl className="case-values"><div><dt>생각을 바꿀 상황</dt><dd><Value value={body.falsification_triggers} /></dd></div></dl>
    <p>감수할 변화는 별도 항목으로 보존되지 않았습니다. 이유 원문에서 확인하고, 일시적 변화인지 구조적 변화인지는 내 검토에 따로 남겨 주세요.</p>
    {value && <details><summary>{label}의 판본·변경 근거</summary><Value value={value} /></details>}</section>;
}

export function OwnershipComparison({ view }: { view: OwnershipView }) {
  const comparison = view.comparison;
  const axes = [{ name: "사업과 이유", rows: comparison.business }, { name: "가격과 내 기준", rows: comparison.price }, { name: "거시 맥락", rows: comparison.macro }, { name: "전체 구성", rows: comparison.portfolio }];
  const rows = axes.flatMap(axis => axis.rows);
  const gaps = rows.filter(row => row.status === "unavailable" || row.status === "incomparable");
  const originalQuery = new URLSearchParams(window.location.hash.split("?")[1] || "");
  originalQuery.set("tab", "records"); originalQuery.set("instrument", view.instrumentId); originalQuery.set("journal", view.original.id || "");
  return <>
    <section className="case-section"><h4>당시 이유·생각을 바꿀 상황</h4><p>{view.original.recordedAt ? `기준 기록: ${timeLabel(view.original.recordedAt)}` : "최초 기록이 없어 현재 검토만 가능합니다."}{view.original.status !== "available" && view.original.id ? " · 당시 본문을 온전히 읽을 수 없습니다." : ""}</p>
      {view.original.reason && <p>당시 비교의 공백: {originalGaps[view.original.reason] || "당시 입력을 확인할 수 없음"}</p>}
      {view.originalHashChanged && <p>기준 기록의 보존 범위가 이후 바뀌었습니다. 남아 있는 입력만 비교합니다.</p>}
      {view.original.id && <a className="btn btn--text" href={`#/watchlist/${encodeURIComponent(view.instrumentId.split(":")[1])}?${originalQuery}`}>당시 기록 원문 열기</a>}
      <div className="ownership-columns"><Reason value={comparison.reason.before} label="당시" /><Reason value={comparison.reason.after} label={view.mode === "historical" ? "이 검토 당시" : "현재"} /></div>
      {comparison.reason.revisionChanged && <p>이유 판본이 바뀌었습니다. 새로운 이유를 최초 이유의 유지로 소급하지 않습니다.</p>}
    </section>
    <section className="case-section"><h4>새 사실과 입력 변화</h4><p>{comparison.notice}</p>
      <ul className="case-input-list">{rows.map(row => <li key={row.slot}><strong>{slotLabels[row.slot]}</strong><span>{inputChanges[row.status]}</span></li>)}</ul>
      {axes.map(axis => <details className="ownership-details" key={axis.name}><summary>{axis.name} · 당시와 {view.mode === "historical" ? "검토 당시" : "현재"} 자료</summary><div className="ownership-columns"><section><h5>당시 보존 입력</h5>{axis.rows.map(row => <PreservedInput key={row.slot} name={row.slot} item={row.before} />)}</section><section><h5>{view.mode === "historical" ? "검토 당시 보존 입력" : "현재 읽은 입력"}</h5>{axis.rows.map(row => <PreservedInput key={row.slot} name={row.slot} item={row.after} />)}</section></div></details>)}
      <details className="ownership-details"><summary>가정·관측 수치 대조</summary><p>{comparison.quantitative.notice}</p><p>당시의 구조화된 사용자 수치 기대와 회사 가이던스는 보존 입력에 없습니다. 원문을 따로 읽고 비교 공백으로 남깁니다.</p>
        <h5>같은 기간 관측과 이후 자료 정정</h5>{comparison.quantitative.annual.length ? <div className="ownership-table" tabIndex={0} aria-label="관측 수치 비교 표"><table><caption>기간·단위·정의가 맞는 값만 차이를 표시합니다.</caption><thead><tr><th>지표·기간</th><th>당시</th><th>{view.mode === "historical" ? "검토 당시" : "현재"}</th><th>차이</th></tr></thead><tbody>{comparison.quantitative.annual.map((row, i) => <tr key={i}><th>{metricNames[row.metric]}<br />{row.period.start} ~ {row.period.end}</th><td>{numeric(row.before?.value, row.before?.unit)}</td><td>{numeric(row.after?.value, row.after?.unit)}</td><td>{row.difference == null ? row.status === "new_period" ? "이후 기간 · 당시 값 없음" : "직접 비교 불가" : numeric(row.difference, row.after?.unit === "%" ? "%p" : row.after?.unit)}</td></tr>)}</tbody></table></div> : <p>지원하는 기간별 관측 값이 없습니다.</p>}
        <h5>시나리오 가정과 계산 결과</h5>{comparison.quantitative.scenarios.length ? <div className="ownership-table" tabIndex={0} aria-label="시나리오 비교 표"><table><caption>관측 성과나 명시적인 사용자 기대가 아닌 계산 가정입니다.</caption><thead><tr><th>시나리오·지표</th><th>당시</th><th>{view.mode === "historical" ? "검토 당시" : "현재"}</th><th>차이</th></tr></thead><tbody>{comparison.quantitative.scenarios.map((row, i) => <tr key={i}><th>{{ base: "기준", conservative: "보수", optimistic: "낙관" }[row.label] || row.label} · {row.horizon}년<br />{metricNames[row.metric]}</th><td>{numeric(row.before, row.unit)}</td><td>{numeric(row.after, row.unit)}</td><td>{row.difference == null ? "직접 비교 불가" : row.unit === "ratio" ? `${(Number(row.difference) * 100).toLocaleString("ko-KR", { maximumFractionDigits: 4 })}%p` : numeric(row.difference, row.unit)}</td></tr>)}</tbody></table></div> : <p>당시 시나리오 수치가 없어 정량 차이를 만들지 않았습니다.</p>}
      </details>
    </section>
    <section className="case-section"><h4>아직 모르는 것</h4><p>{gaps.length ? `${gaps.map(row => slotLabels[row.slot]).join(" · ")}의 비교가 제한됩니다.` : "입력이 비교 가능해도 조건의 발생이나 근거의 충분함을 보증하지 않습니다."}</p><p>자료 없음·오래된 자료·신호 없음은 이유 유지나 조건 미발생을 뜻하지 않습니다. 보존되지 않은 당시 기대를 현재 수치로 채우지 않습니다.</p>{view.historyGaps.length > 0 && <div><p>열 수 없는 과거 기록 {view.historyGaps.length}개가 있습니다.</p><ul>{view.historyGaps.map(gap => <li key={gap.id}>{originalGaps[gap.reason] || "당시 입력을 확인할 수 없음"} · 기록 {gap.id}</li>)}</ul></div>}</section>
  </>;
}

export function ReviewSummary({ review, uncertainties, conditionText }: { review: SavedReview; uncertainties?: string; conditionText?: string | null }) {
  if (review.purgedAt) return <p>개인 검토본문 삭제됨 · {timeLabel(review.purgedAt)}</p>;
  const observed = review.observation;
  return <div className="ownership-summary">
    <p><strong>{conclusions[review.conclusion || "undecided"]}</strong> · {review.resolution === "resolved" ? "사용자가 해소로 기록" : "미해결"} · {review.reviewedAt ? `이 범위 검토 완료 ${timeLabel(review.reviewedAt)}` : "검토 완료 표시 없음"}</p>
    <p>확인 범위: {review.checkedScope?.map(key => scopes[key]).join(" · ") || "기록 없음"}</p>
    <p>연결 조건: {conditionText || (review.condition?.origin === "outside_conditions" ? "기존 조건 밖의 변화 또는 조건 미작성" : "조건 본문 확인 불가")}</p>
    <p>내 관찰: {signals[review.signal || "unknown"]} · 내가 본 근거 수준: {evidenceLevels[review.evidence || "unknown"]}</p>
    <p className="case-text">{observed?.text || "관찰 문장 없음"}</p>
    {observed?.sourceRefs?.length ? <ul>{observed.sourceRefs.map((ref, i) => <li key={i}>{ref.url ? <a href={ref.url} target="_blank" rel="noreferrer">{ref.title || ref.url}</a> : ref.title || ref.id}{ref.id ? ` · ${ref.id}` : ""}{ref.revision ? ` · ${ref.revision}` : ""}</li>)}</ul> : <p>연결한 출처 없음</p>}
    <dl className="case-meta"><div><dt>사건 시각</dt><dd>{ownershipTime(observed?.eventAt)}</dd></div><div><dt>발표 시각</dt><dd>{ownershipTime(observed?.publishedAt)}</dd></div><div><dt>수집 시각</dt><dd>{ownershipTime(observed?.collectedAt)}</dd></div></dl>
    <p className="case-text">조건과의 연결 해석: {review.interpretation || "작성하지 않음"}</p><p className="case-text">반대 근거·불확실성: {uncertainties || "작성하지 않음"}</p>
    <dl className="case-values">{([['companyView', '사업과 이유'], ['priceView', '가격과 내 기준'], ['cashNeed', '내 자금 필요'], ['portfolioContext', '전체 보유 구성']] as const).map(([key, label]) => <div key={key}><dt>{label}</dt><dd className="case-text">{review[key] || "작성하지 않음"}</dd></div>)}</dl>
    <p>다음 확인: {review.nextCheck || "확인할 내용 없음"}{review.nextCheckAt ? ` · ${review.nextCheckAt} (UTC 날짜)` : " · 확인 날짜 없음"}</p>
    {review.conclusion === "exception" && <><p className="case-text">예외 근거: {review.exceptionBasis || "작성하지 않음"}</p><p className="case-text">종료 기준: {[review.exceptionEndAt ? `${review.exceptionEndAt} (UTC 날짜)` : "", review.exceptionEndEvent].filter(Boolean).join(" · ") || "종료 기준 없음"}</p></>}
    {review.postmortemAssessment && <section><h5>내 복기</h5><p>{assessments[review.postmortemAssessment]} · 사용자 회고 분류</p><p className="case-text">예상 경로: {review.expectedPath || "작성하지 않음"}</p><p className="case-text">관측 경로: {review.observedPath || "작성하지 않음"}</p><p>수익률 결과와 판단 품질은 별개입니다. 체결·세금·수수료·현금흐름이 없어 실현 성과로 평가하지 않습니다.</p></section>}
  </div>;
}

function SinceReviewed({ entry }: { entry: ReviewEntry }) {
  const changes = entry.sinceReviewed;
  if (!changes) return null;
  if (changes.status === "not_reviewed") return <p>아직 완료한 검토가 없어 이후 새 자료를 구분하지 않았습니다.</p>;
  if (changes.status !== "available") return <p>완료한 검토의 입력을 온전히 읽을 수 없어 이후 변화를 비교할 수 없습니다.</p>;
  return <div className="ownership-since-reviewed"><p>최근 완료한 범위: {changes.checkedScope?.map(scope => scopes[scope]).join(" · ")} · {timeLabel(changes.reviewedAt)}</p>
    <p>{changes.changedSlots?.length ? `완료한 검토 이후 새 입력: ${changes.changedSlots.map(slot => slotLabels[slot]).join(" · ")}` : changes.unchangedSlots?.length ? "완료한 검토 이후 비교 가능한 입력은 그대로입니다." : "완료한 검토 이후 직접 비교할 수 있는 입력이 없습니다."}</p>
    {Boolean(changes.gapSlots?.length) && <p>이후 변화의 비교 공백: {changes.gapSlots!.map(slot => slotLabels[slot]).join(" · ")}</p>}
    <p>기존 판단과 해소 기록은 유지합니다. 확인하지 않은 범위나 남은 공백까지 변화가 없다는 뜻은 아닙니다.</p>
  </div>;
}

export function IssueSummary({ entry }: { entry: ReviewEntry }) {
  if (entry.status === "unavailable") return <p>이 검토의 본문을 확인할 수 없습니다. 이전 기록을 최신 상태로 대신 사용하지 않습니다.</p>;
  if (entry.review.purgedAt) return <p>개인 검토본문 삭제됨</p>;
  return <><SinceReviewed entry={entry} /><p><strong>{conclusions[entry.review.conclusion || "undecided"]}</strong> · {entry.review.resolution === "resolved" ? "사용자가 해소로 기록" : "미해결"}{entry.review.latestReviewedAt ? " · 검토 완료 이력 있음" : ""}</p><p className="case-text">{entry.conditionView.text || entry.review.observation?.text || "기존 조건 밖의 검토"}</p><p>최초 기록 {timeLabel(entry.review.firstSeenAt)} · 최근 검토 {timeLabel(entry.review.latestReviewedAt)}</p><p>다음 확인: {entry.review.nextCheck || "확인할 내용 없음"} · {entry.due.nextCheckAt || "날짜 없음"}{entry.due.schedule === "due" ? " · 확인 기한 도래" : ""}</p>{entry.due.overdueUnresolved && <p>이전부터 미해결 · 최초 경과 기한 {entry.due.earliestUnresolvedDueAt}. 새 일정과 별도로 남아 있습니다.</p>}{entry.due.exceptionExpired && <p>예외 적용 기간이 지났습니다. 종료 사건 발생 여부는 별도로 확인하세요.</p>}{entry.due.planMissing && entry.review.resolution !== "resolved" && <p>확인 계획 없음 · 해소된 상태로 처리하지 않았습니다.</p>}</>;
}
