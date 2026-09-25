import { useEffect, useRef, useState } from "react";
import {
  getThesisWorkspace,
  runThesisReview,
  saveThesis,
  type ThesisReviewJob,
  type ThesisReviewResult,
  type ThesisWorkspacePayload,
  type TrackedCheckpointView,
} from "../../api";
import { pollAgentJobBounded } from "../agentPolling";
import { openScopedThread } from "../agentWorkspace/openScopedThread";
import {
  checkpointDisplay,
  thesisVerdictDisplay,
  transitionLabel,
  verificationDate,
} from "../verification";

/**
 * 종목 Thesis workspace (0.6 Stage C.2 + A.3 + C.3).
 *
 * 계획 C.2의 순서를 그대로 편다:
 *
 *     내 Thesis → 최신 검증 → 근거/반대근거 → 다음 확인 → 검토 이력
 *
 * 위쪽 지표·차트·실적·뉴스는 **사실**이고 여기는 **내 생각**이다. 두 영역을 한 카드에
 * 섞지 않으며, 이 영역은 `data-layer="hypothesis"`와 "근거 아님" 경계를 단다.
 *
 * **판정은 두 층이고 한 배지로 합치지 않는다**(계획 §3.2) — Delta verdict(6값)와
 * 체크포인트 판정(3값)은 각자의 자리에서 각자의 이름으로 보인다.
 *
 * 화면 진입은 저장된 projection만 읽는다. Agent를 자동으로 부르지 않는다.
 */

function CheckpointRow({ checkpoint }: { checkpoint: TrackedCheckpointView }) {
  const display = checkpointDisplay(checkpoint.status);
  const evidence = checkpoint.lastVerdict?.evidence || [];
  return (
    <li className="verification-checkpoint">
      <div className="verification-checkpoint__head">
        <span className="chip verification-chip" data-tone={display.tone}>
          <span aria-hidden="true">{display.icon}</span> {display.label}
        </span>
        <strong>{checkpoint.item}</strong>
      </div>
      <p className="verification-checkpoint__meta">
        {checkpoint.direction === "challenging" ? "반증 신호를 기다리는 항목" : "확인 신호를 기다리는 항목"}
        {checkpoint.lastVerdict?.at ? ` · 마지막 판정 ${verificationDate(checkpoint.lastVerdict.at)}` : ""}
        {checkpoint.dueBy ? ` · 기한 ${checkpoint.dueBy}` : ""}
      </p>
      {evidence.length > 0 && (
        <ul className="verification-evidence">
          {evidence.map((item, index) => (
            <li key={`${item.title}-${index}`}>
              <span className="verification-evidence__date">{verificationDate(item.date)}</span>
              <span className="verification-evidence__title">{item.title}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function EvidenceList({ items, empty }: { items: Array<{ title: string; source: string; date: string; reason: string }>; empty: string }) {
  if (!items.length) return <p className="thesis-workspace__empty">{empty}</p>;
  return (
    <ul className="verification-evidence">
      {items.map((item, index) => (
        <li key={`${item.title}-${index}`}>
          <span className="verification-evidence__date">{verificationDate(item.date)}</span>
          <span className="verification-evidence__title">
            {item.title}
            {item.source ? <small> · {item.source}</small> : null}
            {item.reason ? <small className="verification-evidence__reason">{item.reason}</small> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

function emptyDraft() {
  return { coreThesis: "", keyAssumptions: "", falsificationTriggers: "", reviewCycle: "quarterly", conviction: "medium" };
}

export function ThesisWorkspace({ ticker, companyName = "" }: { ticker: string; companyName?: string }) {
  const [payload, setPayload] = useState<ThesisWorkspacePayload | null>(null);
  const [error, setError] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const reviewController = useRef<AbortController | null>(null);
  const saveController = useRef<AbortController | null>(null);
  // effect 정리보다 먼저 최신 prop을 보관해, ticker 전환 렌더와 effect 사이에
  // 도착한 이전 종목 저장 응답도 새 화면을 덮지 못하게 한다.
  const activeTicker = useRef(ticker);
  activeTicker.current = ticker;

  useEffect(() => {
    reviewController.current?.abort();
    saveController.current?.abort();
    saveController.current = null;
    setPayload(null);
    setError("");
    setEditing(false);
    setSaving(false);
    setDraft(emptyDraft());
    if (!ticker) return;
    const controller = new AbortController();
    getThesisWorkspace(ticker, { signal: controller.signal })
      .then(setPayload)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "Thesis 상태를 불러오지 못했습니다.");
      });
    return () => { controller.abort(); reviewController.current?.abort(); saveController.current?.abort(); };
  }, [ticker]);

  const thesis = payload?.thesis || null;
  const delta = payload?.latestDelta || null;
  const verdict = thesisVerdictDisplay(delta?.verdict);
  const checkpoints = payload?.checkpoints;

  function beginEdit() {
    const current = payload?.thesis;
    setDraft({
      coreThesis: current?.coreThesis || "",
      keyAssumptions: (current?.keyAssumptions || []).join("\n"),
      falsificationTriggers: (current?.falsificationTriggers || []).join("\n"),
      reviewCycle: current?.reviewCycle || "quarterly",
      conviction: current?.conviction || "medium",
    });
    setError("");
    setEditing(true);
  }

  async function saveDraft() {
    if (!ticker || saving || !draft.coreThesis.trim()) return;
    const controller = new AbortController();
    saveController.current?.abort();
    saveController.current = controller;
    setSaving(true);
    setError("");
    try {
      await saveThesis({
        ticker,
        company: payload?.thesis?.company || companyName,
        coreThesis: draft.coreThesis.trim(),
        keyAssumptions: draft.keyAssumptions.split("\n").map((value) => value.trim()).filter(Boolean),
        falsificationTriggers: draft.falsificationTriggers.split("\n").map((value) => value.trim()).filter(Boolean),
        reviewCycle: draft.reviewCycle,
        conviction: draft.conviction,
      }, { signal: controller.signal });
      const refreshed = await getThesisWorkspace(ticker, { signal: controller.signal });
      if (controller.signal.aborted || saveController.current !== controller || activeTicker.current !== ticker) return;
      setPayload(refreshed);
      setEditing(false);
    } catch (err) {
      if (controller.signal.aborted || saveController.current !== controller || activeTicker.current !== ticker) return;
      setError(err instanceof Error ? err.message : "Thesis를 저장하지 못했습니다.");
    } finally {
      if (saveController.current === controller && activeTicker.current === ticker) {
        saveController.current = null;
        setSaving(false);
      }
    }
  }

  async function reviewLatestEvidence() {
    if (!ticker || reviewBusy) return;
    let controller: AbortController | null = null;
    setReviewBusy(true);
    setError("");
    try {
      // 사용자의 명시적 클릭만 delta write를 시작한다. projection GET은 계속 read-only다.
      controller = new AbortController();
      reviewController.current?.abort();
      reviewController.current = controller;
      const result = await runThesisReview(ticker, { signal: controller.signal });
      if (isReviewJob(result)) await pollAgentJobBounded(result, { signal: controller.signal });
      setPayload(await getThesisWorkspace(ticker, { signal: controller.signal }));
    } catch (err) {
      if (controller?.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
      setError(err instanceof Error ? err.message : "최신 근거 검토를 완료하지 못했습니다.");
      } finally {
      if (reviewController.current?.signal === controller?.signal) reviewController.current = null;
      setReviewBusy(false);
    }
  }

  return (
    <section
      className="thesis-workspace"
      data-layer="hypothesis"
      data-qa="thesis-workspace"
      aria-label="내 Thesis 검증"
    >
      <div className="watchlist-detail-section__head">
        <h3>내 Thesis</h3>
        {/* 사실 영역과 개인 영역의 경계를 화면이 직접 말한다. */}
        <span className="chip verification-chip" data-tone="muted">내 생각·가설 · 근거 아님</span>
      </div>

      {error && <p className="react-dashboard-error" role="alert">{error}</p>}
      {!payload && !error && <div className="verification-skeleton" aria-label="Thesis 상태를 불러오는 중"><span className="verification-skeleton__line verification-skeleton__line--title" /><span className="verification-skeleton__line" /><span className="verification-skeleton__line verification-skeleton__line--short" /></div>}

      {payload && editing && (
        <form className="thesis-workspace__editor" onSubmit={(event) => { event.preventDefault(); void saveDraft(); }}>
          <h4>{payload.hasThesis ? "Thesis 수정" : "Thesis 만들기"}</h4>
          <label className="field">핵심 Thesis<textarea required value={draft.coreThesis} onChange={(event) => setDraft({ ...draft, coreThesis: event.target.value })} rows={4} /></label>
          <label className="field">핵심 가정 (한 줄에 하나)<textarea value={draft.keyAssumptions} onChange={(event) => setDraft({ ...draft, keyAssumptions: event.target.value })} rows={3} /></label>
          <label className="field">이탈 조건 (한 줄에 하나)<textarea value={draft.falsificationTriggers} onChange={(event) => setDraft({ ...draft, falsificationTriggers: event.target.value })} rows={3} /></label>
          <div className="thesis-workspace__editor-grid">
            <label className="field">확신도<select value={draft.conviction} onChange={(event) => setDraft({ ...draft, conviction: event.target.value })}><option value="low">낮음</option><option value="medium">보통</option><option value="medium_high">중상</option><option value="high">높음</option></select></label>
            <label className="field">검토 주기<select value={draft.reviewCycle} onChange={(event) => setDraft({ ...draft, reviewCycle: event.target.value })}><option value="weekly">매주</option><option value="monthly">매월</option><option value="quarterly">분기별</option><option value="event_driven">이벤트 발생 시</option></select></label>
          </div>
          <div className="thesis-workspace__editor-actions"><button className="btn btn--primary" type="submit" disabled={saving || !draft.coreThesis.trim()}>{saving ? "저장 중…" : "Thesis 저장"}</button><button className="btn" type="button" onClick={() => setEditing(false)} disabled={saving}>취소</button></div>
        </form>
      )}

      {payload && !payload.hasThesis && (
        <div className="thesis-workspace__intro">
          <p className="thesis-workspace__empty">
            이 종목에 등록된 Thesis가 없습니다. Thesis를 만들면 저장해 둔 확인 항목을 새 근거와 매일 대조합니다.
          </p>
          {payload.ownership?.vaultNote ? (
            <p className="thesis-workspace__note">
              Obsidian Vault에 <strong>{payload.ownership.vaultNote.title || payload.ownership.vaultNote.relPath}</strong>{" "}
              노트가 있습니다. Vault 동기화가 돌면 자동으로 등록됩니다.
            </p>
          ) : (
            <p className="thesis-workspace__note">
              기업 분석 보고서의 <strong>투자 생각 정리</strong>에서 노트를 쓰면 Thesis로 등록됩니다.
            </p>
          )}
          <button className="btn" type="button" onClick={beginEdit}>Thesis 만들기</button>
        </div>
      )}

      {payload && payload.hasThesis && thesis && (
        <>
          {/* 소유권 — 동기화가 멈춘 사실이 조용하면 사용자는 낡은 이유를 찾을 수 없다. */}
          {payload.ownership?.syncPaused && (
            <p className="thesis-workspace__warning" data-qa="thesis-sync-paused">
              <span className="chip verification-chip" data-tone="gold">
                <span aria-hidden="true">!</span> Vault 동기화 멈춤
              </span>{" "}
              {payload.ownership.message}
            </p>
          )}

          {/* A.3 — 연결한 내러티브의 반증 신호를 여기로 전한다. 표시일 뿐 verdict를 바꾸지 않는다. */}
          {payload.regimeAlerts.length > 0 && (
            <div className="thesis-workspace__alerts" data-qa="thesis-regime-alert">
              {payload.regimeAlerts.map((alert) => (
                <p className="thesis-workspace__warning" key={alert.stateId}>
                  <span className="chip verification-chip" data-tone="burgundy">
                    <span aria-hidden="true">!</span> 연결 내러티브 경고
                  </span>{" "}
                  <strong>{alert.label}</strong>에 반증 신호가 있습니다
                  {alert.reasons[0]?.detail ? ` — ${alert.reasons[0].detail}` : ""}.
                  <small> 이 경고는 표시일 뿐 Thesis 판정을 바꾸지 않습니다.</small>
                </p>
              ))}
            </div>
          )}

          <div className="thesis-workspace__block">
            <h4>핵심 Thesis</h4>
            <p className="thesis-workspace__core">{thesis.coreThesis || "핵심 논지가 비어 있습니다."}</p>
            <p className="thesis-workspace__meta">
              확신도 {displayConviction(thesis.conviction)} · 검토 주기 {displayReviewCycle(thesis.reviewCycle)} · 최근 검토{" "}
              {verificationDate(thesis.lastReviewedAt)}
            </p>
            {thesis.falsificationTriggers.length > 0 && (
              <>
                <h5>이탈 조건</h5>
                <ul className="thesis-workspace__list">
                  {thesis.falsificationTriggers.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
                </ul>
              </>
            )}
          </div>

          <div className="thesis-workspace__block">
            <h4>최신 검증</h4>
            {delta ? (
              <>
                <p className="thesis-workspace__verdict">
                  {/* 6값 enum. 아래 확인 항목의 3값 판정과 다른 층이다. */}
                  <span className="chip verification-chip" data-tone={verdict.tone}>
                    <span aria-hidden="true">{verdict.icon}</span> {verdict.label}
                  </span>
                  <span className="thesis-workspace__meta">
                    Thesis 종합 판정 · {verificationDate(delta.generatedAt)}
                    {delta.period ? ` · ${displayPeriod(delta.period)} 창` : ""}
                  </span>
                </p>
                {delta.summary && <p className="thesis-workspace__core">{delta.summary}</p>}
              </>
            ) : (
              <p className="thesis-workspace__empty">
                아직 종합 검증이 없습니다. 아래의 <strong>최신 근거로 검토</strong>를 실행하면 만들어집니다.
              </p>
            )}
          </div>

          <div className="thesis-workspace__block">
            <h4>근거와 반대 근거</h4>
            <h5>강화 근거</h5>
            <EvidenceList items={delta?.supportingEvidence || []} empty="확인된 강화 근거가 없습니다." />
            <h5>반대 근거</h5>
            <EvidenceList items={delta?.counterEvidence || []} empty="기록된 반대 근거가 없습니다." />
            {delta?.uncertainties?.length ? (
              <>
                <h5>불확실성</h5>
                <ul className="thesis-workspace__list">
                  {delta.uncertainties.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
                </ul>
              </>
            ) : null}
            {delta?.contradictions?.length ? (
              <>
                <h5>모순·반증 관찰</h5>
                <ul className="thesis-workspace__list">
                  {delta.contradictions.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
                </ul>
              </>
            ) : null}
          </div>

          <div className="thesis-workspace__block">
            <h4>다음 확인</h4>
            {checkpoints && checkpoints.structured.length > 0 ? (
              <ul className="verification-checkpoint-list">
                {checkpoints.structured.map((checkpoint) => (
                  <CheckpointRow key={checkpoint.id} checkpoint={checkpoint} />
                ))}
              </ul>
            ) : (
              <p className="thesis-workspace__empty">기계가 대조할 확인 항목이 아직 없습니다.</p>
            )}
            {checkpoints && checkpoints.unverifiableCount > 0 && (
              <p className="thesis-workspace__note" data-qa="thesis-unverifiable">
                <span className="chip verification-chip" data-tone="gold">
                  <span aria-hidden="true">?</span> 검증 불가
                </span>{" "}
                {checkpoints.unverifiableCount}건은 저장된 형식이 지금 규칙과 맞지 않아 판정에서 빠집니다.
              </p>
            )}
            {checkpoints && checkpoints.templates.length > 0 && (
              <ul className="thesis-workspace__list">
                {checkpoints.templates.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
              </ul>
            )}
          </div>

          <div className="thesis-workspace__block thesis-workspace__actions">
            <h4>Thesis 작업</h4>
            <button className="btn" type="button" onClick={beginEdit}>Thesis 만들기/수정</button>
            <button className="btn" type="button" onClick={() => void reviewLatestEvidence()} disabled={reviewBusy}>
              {reviewBusy ? "최신 근거를 검토하는 중…" : "최신 근거로 검토"}
            </button>
            <button
              className="btn"
              type="button"
              onClick={() => openScopedThread({
                title: `${ticker} Thesis 반박 대화`,
            scope: { kind: "watchlist", id: ticker, tickers: [ticker], intent: "challenge" },
                initialMessage: "이 Thesis를 반박해줘",
                autoSubmit: true,
              })}
            >
              이 Thesis를 반박해줘
            </button>
          </div>

          <div className="thesis-workspace__block">
            <h4>검토 이력</h4>
            {payload.deltaHistory.length || checkpoints?.structured.some((item) => item.history?.length) ? (
              <ol className="verification-timeline__list">
                {[...payload.deltaHistory.map((row) => ({ kind: "delta" as const, at: row.generatedAt, row })),
                  ...(checkpoints?.structured || []).flatMap((checkpoint) => (checkpoint.history || []).map((row, index) => ({ kind: "checkpoint" as const, at: row.at, row, checkpoint, index })))
                ].sort((a, b) => timelineTimestamp(b.at) - timelineTimestamp(a.at)).map((entry) => {
                  if (entry.kind === "delta") {
                    const row = entry.row;
                  const display = thesisVerdictDisplay(row.verdict);
                  return (
                    <li key={row.deltaId}>
                      <span className="verification-timeline__date">{verificationDate(row.generatedAt)}</span>
                      <span className="verification-timeline__body">
                        <strong>종합 판정</strong> {display.label}
                        {row.summary ? ` · ${row.summary}` : ""}
                      </span>
                    </li>
                  );
                  }
                  const { checkpoint, row, index } = entry;
                  return <li key={`${checkpoint.id}-${index}`}>
                      <span className="verification-timeline__date">{verificationDate(row.at)}</span>
                      <span className="verification-timeline__body">
                        <strong>확인 항목</strong> {checkpoint.item} ·{" "}
                        {transitionLabel("checkpoint", row.from)} → {transitionLabel("checkpoint", row.to)}
                      </span>
                    </li>;
                })}
              </ol>
            ) : (
              <p className="thesis-workspace__empty">아직 기록된 검토 이력이 없습니다.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function isReviewJob(result: ThesisReviewResult): result is ThesisReviewJob {
  return "id" in result && "status" in result;
}

function displayConviction(value: string) {
  return ({ low: "낮음", medium: "보통", medium_high: "중상", high: "높음" } as Record<string, string>)[value] || "판단 보류";
}
function displayReviewCycle(value: string) {
  return ({ weekly: "매주", monthly: "매월", quarterly: "분기별", event_driven: "이벤트 발생 시" } as Record<string, string>)[value] || "정기 검토 없음";
}
function displayPeriod(value: string) {
  return ({ "30d": "최근 30일", "90d": "최근 90일", since_last_review: "지난 검토 이후", since_last_note: "지난 노트 이후", last_earnings: "지난 실적 이후" } as Record<string, string>)[value] || "기록된 기간";
}
function timelineTimestamp(value: string) {
  const timestamp = Date.parse(value || "");
  // malformed date는 time axis의 끝에, 같은 종류끼리는 안정적인 입력 순서로 둔다.
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY;
}
