import { useEffect, useState } from "react";
import {
  getNarrativeVerification,
  type NarrativeVerificationPayload,
  type NarrativeVerificationState,
  type TrackedCheckpointView,
} from "../../api";
import {
  MOMENTUM_LABELS,
  NARRATIVE_STATUS_LABELS,
  checkpointDisplay,
  silenceDisplay,
  transitionLabel,
  verificationDate,
} from "../verification";

/**
 * 내러티브 검증 상태 (0.6 Stage C.1 + C.3).
 *
 * 위쪽 드라이버 카드는 **스냅샷이 쓴 해석**이고, 이 패널은 **저장된 내러티브 상태의
 * 규칙 판정**이다. 둘은 같은 것이 아니다 — 스냅샷 드라이버에는 상태 정체성이 없어
 * (`snapshot-driver:N`) 체크포인트를 붙일 수 없고, 제목으로 이어 붙이는 것은 이
 * 저장소가 여러 번 데인 방식이다. 그래서 층을 섞지 않고 자기 자리에서 보여준다.
 *
 * 여기서 아무것도 쓰지 않는다. 판정은 자료 수집 뒤 규칙 pass가 이미 끝냈고,
 * 화면은 그 결과를 읽을 뿐이다.
 */

function CheckpointRow({ checkpoint }: { checkpoint: TrackedCheckpointView }) {
  const display = checkpointDisplay(checkpoint.status);
  const evidence = checkpoint.lastVerdict?.evidence || [];
  return (
    <li className="verification-checkpoint">
      <div className="verification-checkpoint__head">
        {/* 색만으로 상태를 전달하지 않는다 — 기호와 라벨을 함께 둔다. */}
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

function StateCard({ state }: { state: NarrativeVerificationState }) {
  const silence = silenceDisplay(state.silence.level);
  const statusLabel = NARRATIVE_STATUS_LABELS[state.status] || state.status;
  const momentumLabel = MOMENTUM_LABELS[state.momentum] || state.momentumLabel;
  const hasVerdicts = state.checkpoints.length > 0;
  return (
    <article className="surface surface--group verification-state" data-qa="verification-state">
      <header className="verification-state__head">
        <div>
          <h4>{state.label}</h4>
          <p className="verification-state__meta">
            {statusLabel} · 추세 {momentumLabel} · 근거 7일 {state.evidenceCounts.d7} / 30일 {state.evidenceCounts.d30}
          </p>
        </div>
        {/* 무소식 배지 — 죽어가는 이야기와 살아있는 이야기가 똑같이 생기지 않게 한다. */}
        <span
          className="chip verification-chip verification-silence"
          data-tone={silence.tone}
          data-level={state.silence.level}
          title={state.silence.note || undefined}
        >
          <span aria-hidden="true">{silence.icon}</span> {state.silence.label}
        </span>
      </header>

      {state.silence.note && <p className="verification-state__note">{state.silence.note}</p>}

      {hasVerdicts ? (
        <ul className="verification-checkpoint-list">
          {state.checkpoints.map((checkpoint) => (
            <CheckpointRow key={checkpoint.id} checkpoint={checkpoint} />
          ))}
        </ul>
      ) : (
        <p className="verification-state__empty">
          기계가 대조할 확인 항목이 아직 없습니다. 시장 메모리 업데이트가 만들면 여기에서 매일 대조합니다.
        </p>
      )}

      {state.unverifiableCount > 0 && (
        <p className="verification-state__note" data-qa="verification-unverifiable">
          <span className="chip verification-chip" data-tone="gold">
            <span aria-hidden="true">?</span> 검증 불가
          </span>{" "}
          {state.unverifiableCount}건은 저장된 형식이 지금 규칙과 맞지 않아 판정에서 빠집니다(내용은 지워지지 않습니다).
        </p>
      )}

      {state.templates.length > 0 && (
        <details className="verification-templates">
          <summary>규칙이 만든 확인 문장 {state.templates.length}건</summary>
          <ul>
            {state.templates.map((text, index) => <li key={`${text}-${index}`}>{text}</li>)}
          </ul>
        </details>
      )}

      {state.timeline.length > 0 && (
        <details className="verification-timeline">
          <summary>판정 이력 {state.timeline.length}건</summary>
          <ol className="verification-timeline__list">
            {state.timeline.map((row, index) => (
              <li key={`${row.at}-${index}`}>
                <span className="verification-timeline__date">{verificationDate(row.at)}</span>
                <span className="verification-timeline__body">
                  <strong>{row.kind === "checkpoint" ? "확인 항목" : row.kind === "momentum" ? "추세" : "확신도"}</strong>
                  {" "}
                  {transitionLabel(row.kind, row.from)} → {transitionLabel(row.kind, row.to)}
                  {row.reason ? ` · ${row.reason}` : ""}
                  {row.evidenceCount ? ` · 근거 ${row.evidenceCount}건` : ""}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  );
}

function Skeleton() {
  // 인라인 콘텐츠의 로딩은 스피너가 아니라 최종 레이아웃을 닮은 스켈레톤이다.
  return (
    <div className="verification-skeleton" aria-hidden="true">
      {[0, 1].map((index) => (
        <div className="surface surface--group verification-state" key={index}>
          <span className="verification-skeleton__line verification-skeleton__line--title" />
          <span className="verification-skeleton__line" />
          <span className="verification-skeleton__line verification-skeleton__line--short" />
        </div>
      ))}
    </div>
  );
}

export function NarrativeVerificationPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [payload, setPayload] = useState<NarrativeVerificationPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    getNarrativeVerification({ signal: controller.signal })
      .then(setPayload)
      .catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : "검증 상태를 불러오지 못했습니다.");
      });
    return () => controller.abort();
  }, [refreshKey]);

  const summary = payload?.summary;
  return (
    <section className="surface verification-panel" aria-label="내러티브 검증 상태">
      <header className="verification-panel__head">
        <div>
          <p className="section-kicker">Verification</p>
          <h3>내러티브 검증 상태</h3>
          <p className="section-subtitle">
            저장해 둔 확인 항목을 새 근거와 매일 대조한 결과입니다. 규칙 기반이라 AI를 부르지 않습니다.
          </p>
        </div>
        {summary && summary.stateCount > 0 && (
          <p className="verification-panel__summary">
            확인 {summary.confirmed} · 반증 {summary.challenged} · 식어가는 중 {summary.cooling}
          </p>
        )}
      </header>

      {error && <p className="react-dashboard-error">{error}</p>}
      {!payload && !error && <Skeleton />}

      {payload && payload.states.length === 0 && (
        <p className="verification-state__empty">
          활성·관찰 중인 내러티브가 아직 없습니다. 시장 메모리 업데이트를 실행하면 여기에 쌓입니다.
        </p>
      )}

      {payload && payload.states.length > 0 && (
        <div className="verification-state-list">
          {payload.states.map((state) => <StateCard key={state.stateId} state={state} />)}
        </div>
      )}
    </section>
  );
}
