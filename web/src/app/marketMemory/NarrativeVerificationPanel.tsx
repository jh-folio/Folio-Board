import { useEffect, useState } from "react";
import {
  getNarrativeVerification,
  type NarrativeVerificationPayload,
  type NarrativeVerificationState,
} from "../../api";
import { transitionLabel, verificationDate } from "../verification";
import { openScopedThread } from "../agentWorkspace/openScopedThread";

/**
 * 내러티브 검증 알림 (0.6 Stage C.1 + C.3).
 *
 * 위쪽 드라이버 카드는 **스냅샷이 쓴 해석**이고, 여기는 **저장된 내러티브 상태의
 * 규칙 판정**이다. 둘은 같은 것이 아니다 — 스냅샷 드라이버에는 상태 정체성이 없어
 * (`snapshot-driver:N`) 체크포인트를 붙일 수 없고, 제목으로 이어 붙이는 것은 이
 * 저장소가 여러 번 데인 방식이다. 그래서 층을 섞지 않는다.
 *
 * **주의가 필요한 내러티브만 나온다**(2026-09-01 사용자 결정). 예전에는 활성 상태
 * 전부를 카드로 펼쳐서, 판정이 하나도 없는 날에도 "확인 항목이 아직 없습니다"를
 * 상태 수만큼 반복하는 화면이 한 페이지를 차지했다. 알림은 조용할 때 안 보여야
 * 시끄러울 때 눈에 띈다 — 신호가 없으면 이 섹션은 렌더되지 않는다.
 *
 * 확인 항목 전체 목록·규칙 템플릿 문장·검증 불가 건수는 화면에서 빼고
 * `GET /api/memory/verification`에만 남겼다. 판정 이력은 신호가 있는 내러티브의
 * 접기 안에서만 보여준다(C.3의 시간축은 그 자리를 지킨다).
 *
 * 여기서 아무것도 쓰지 않는다. 판정은 자료 수집 뒤 규칙 pass가 이미 끝냈고,
 * 화면은 그 결과를 읽을 뿐이다.
 */

type Signal = {
  /** 색 없이도 읽히는 텍스트 기호. 이모지가 아니라 기호라서 폰트에 좌우되지 않는다. */
  icon: string;
  label: string;
  tone: "burgundy" | "gold";
  detail: string;
};

/**
 * 이 내러티브가 사용자를 부를 이유가 있는가. 없으면 null이고 줄이 나오지 않는다.
 *
 * 우선순위는 급한 순이다 — 반증은 지금 판단이 틀렸을 수 있다는 신호이고,
 * 무소식은 시장이 이 이야기를 접었다는 신호이며, 기한 경과는 확인하기로 한
 * 것을 확인하지 못한 채 시간이 지났다는 뜻이다.
 */
export function stateSignal(state: NarrativeVerificationState): Signal | null {
  const counts = state.checkpointCounts || {};
  const challenged = Number(counts.challenged || 0);
  const expired = Number(counts.expired || 0);
  if (challenged > 0) {
    return { icon: "!", label: "반증 신호", tone: "burgundy", detail: `확인 항목 ${challenged}건이 반증됐습니다` };
  }
  // 무소식 라벨은 서버가 일수를 담아 만든다(`17일 무소식 · 정리 후보`).
  if (state.silence.level === "dormant") {
    return { icon: "↓", label: "정리 후보", tone: "burgundy", detail: state.silence.label };
  }
  if (state.silence.level === "cooling") {
    return { icon: "↓", label: "식어가는 중", tone: "gold", detail: state.silence.label };
  }
  if (expired > 0) {
    return { icon: "×", label: "기한 경과", tone: "gold", detail: `확인 항목 ${expired}건이 기한을 넘겼습니다` };
  }
  return null;
}

const TIMELINE_PREVIEW = 4;

const TRANSITION_KIND_LABELS: Record<string, string> = {
  checkpoint: "확인 항목",
  momentum: "추세",
  confidence: "확신도",
  status: "상태",
  evidence_count: "근거 수",
};

function AlertRow({ state, signal, ownedTickers = [] }: { state: NarrativeVerificationState; signal: Signal; ownedTickers?: readonly string[] }) {
  // 반증된 항목의 근거만 싣는다. 확인된 항목까지 담으면 반증이 그 안에 묻힌다.
  const challenged = state.checkpoints.filter((checkpoint) => checkpoint.status === "challenged");
  const timeline = state.timeline.slice(0, TIMELINE_PREVIEW);
  const hasDetail = challenged.length > 0 || timeline.length > 0;
  return (
    <li className="verification-alert">
      <div className="verification-alert__head">
        <span className="chip verification-chip" data-tone={signal.tone}>
          <span aria-hidden="true">{signal.icon}</span> {signal.label}
        </span>
        <strong className="verification-alert__label">{state.label}</strong>
        <span className="verification-alert__reason">{signal.detail}</span>
        {/* 이 내러티브와 닿은 내 종목. 상태 ID로만 잇고, 보라=개인 층이라 판정과 섞이지 않는다. */}
        {ownedTickers.length ? (
          <span className="chip verification-owned-chip" data-tone="purple" data-layer="hypothesis">
            내 종목 {ownedTickers.join(" · ")}
          </span>
        ) : null}
        <button
          className="btn btn--sm verification-alert__action"
          type="button"
          aria-label={`${state.label}의 전제를 반박해줘`}
          onClick={() => openScopedThread({
            title: "내러티브 반박 대화",
            scope: { kind: "market_memory", id: state.stateId, intent: "challenge" },
            initialMessage: "이 전제를 반박해줘",
            autoSubmit: true,
          })}
        >
          반박해줘
        </button>
      </div>

      {/* 무소식 신호에는 "자동으로 바뀌지 않는다"는 경계가 붙는다. 정리 후보라는 말이
          곧 정리하겠다는 뜻으로 읽히면 안 된다(§3.5 자동 상태 전환 없음). */}
      {signal.icon === "↓" && state.silence.note && (
        <p className="verification-alert__note">{state.silence.note}</p>
      )}

      {hasDetail && (
        <details className="verification-alert__detail">
          <summary>근거 보기</summary>
          {challenged.map((checkpoint) => (
            <div className="verification-checkpoint" key={checkpoint.id}>
              <div className="verification-checkpoint__head">
                <strong>{checkpoint.item}</strong>
              </div>
              <p className="verification-checkpoint__meta">
                {/* direction은 "이 신호가 잡히면 무슨 뜻인가"라 라벨 없이 두면 읽히지 않는다. */}
                {checkpoint.direction === "challenging" ? "반증 신호를 기다리는 항목" : "확인 신호를 기다리는 항목"}
                {checkpoint.lastVerdict?.at ? ` · 마지막 판정 ${verificationDate(checkpoint.lastVerdict.at)}` : ""}
              </p>
              {(checkpoint.lastVerdict?.evidence || []).length > 0 && (
                <ul className="verification-evidence">
                  {(checkpoint.lastVerdict?.evidence || []).map((item, index) => (
                    <li key={`${item.title}-${index}`}>
                      <span className="verification-evidence__date">{verificationDate(item.date)}</span>
                      <span className="verification-evidence__title">{item.title}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}

          {timeline.length > 0 && (
            <ol className="verification-timeline__list">
              {timeline.map((row, index) => (
                <li key={`${row.at}-${index}`}>
                  <span className="verification-timeline__date">{verificationDate(row.at)}</span>
                  <span className="verification-timeline__body">
                    <strong>{TRANSITION_KIND_LABELS[row.kind] || "변화"}</strong>{" "}
                    {transitionLabel(row.kind, row.from)} → {transitionLabel(row.kind, row.to)}
                    {row.reason ? ` · ${row.reason}` : ""}
                    {row.evidenceCount ? ` · 근거 ${row.evidenceCount}건` : ""}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </details>
      )}
    </li>
  );
}

export function NarrativeVerificationPanel({ refreshKey = 0, ownedTickers = {} }: { refreshKey?: number; ownedTickers?: Readonly<Record<string, readonly string[]>> }) {
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

  // 조회 실패는 조용히 넘기지 않는다 — 신호가 없는 것과 못 읽은 것은 다르다.
  if (error) {
    return (
      <section className="surface verification-panel" aria-label="내러티브 검증 알림">
        <p className="react-dashboard-error" role="alert">{error}</p>
      </section>
    );
  }

  // 로딩 중에도 자리를 잡지 않는다. 대개 신호가 없어 사라질 자리라 스켈레톤을 그리면
  // 화면이 떴다 꺼지는 것으로 보인다.
  if (!payload) return null;

  const alerts = payload.states
    .map((state) => ({ state, signal: stateSignal(state) }))
    .filter((row): row is { state: NarrativeVerificationState; signal: Signal } => row.signal !== null);
  if (alerts.length === 0) return null;

  return (
    <section className="surface verification-panel" aria-labelledby="verificationAlertTitle">
      <div className="verification-panel__head">
        <p className="section-kicker">Verification</p>
        <h3 id="verificationAlertTitle">확인이 필요한 내러티브 {alerts.length}건</h3>
        <p className="section-subtitle">
          저장해 둔 확인 항목을 새 근거와 대조한 결과입니다. 판정은 규칙이 하며 AI를 부르지 않습니다.
        </p>
      </div>
      <ul className="verification-alert-list">
        {alerts.map(({ state, signal }) => <AlertRow key={state.stateId} state={state} signal={signal} ownedTickers={ownedTickers[state.stateId]} />)}
      </ul>
    </section>
  );
}
