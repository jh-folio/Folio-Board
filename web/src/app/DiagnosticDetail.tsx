import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, getJson, parseDiagnosticDetail, type DiagnosticDetail as DiagnosticDetailPayload, type DiagnosticRecord } from "../api";
import {
  adapterLabel, availabilityNote, classifyDiagnosticState, confirmationLabel, diagnosticCompletionConfirmed,
  diagnosticInspectionTarget, engineFallbackNote, formatElapsed, lastCompletedStageLabel, nextActionLabel, reasonLabel, stageLabel,
} from "./diagnosticCopy";
import { DiagnosticExport } from "./DiagnosticExport";

type DiagnosticDetailProps = {
  /** SharedJob 실행은 jobId로 조회한다(`/api/diagnostics/jobs/{jobId}`) — 서버가 결정적으로 runId를 잇는다. */
  readonly jobId?: string | null;
  /** job이 없는 실행(자동화 규칙 경로 등)은 diagnosticRunId로 직접 조회한다. jobId가 있으면 그쪽을 우선한다. */
  readonly runId?: string | null;
  /** 부모 목록의 현재 항목 revision. 같은 실행도 상태가 바뀌면 재조회한다. */
  readonly revision?: string | number | null;
  /** 부모 Work Log의 전역 새로고침 세대. 항목 identity가 같아도 열린 상세를 다시 읽는다. */
  readonly refreshKey?: number;
};

type FetchStatus = "idle" | "loading" | "loaded" | "error";

/** 0.6 D3 — 기존 화면에서 실패를 이해하고 찾아가는 안전한 진단 상세.
 *
 *  Work Log와 자동화 실행 내역이 공유하는 단일 컴포넌트다. 두 화면 모두 같은 상세를
 *  열어야 한다는 계약(WORK_LOG_DIAGNOSTICS_PLAN.md D3)이 있는데, 각자 다시 구현하면
 *  문구·상태 분류가 갈린다. */
export function DiagnosticDetail({ jobId, runId, revision = null, refreshKey = 0 }: DiagnosticDetailProps) {
  const [status, setStatus] = useState<FetchStatus>("idle");
  const [detail, setDetail] = useState<DiagnosticDetailPayload | null>(null);
  const [errorCode, setErrorCode] = useState("");
  const detailsRef = useRef<HTMLDetailsElement | null>(null);
  const requestSequence = useRef(0);
  const activeController = useRef<AbortController | null>(null);

  const path = jobId ? `/api/diagnostics/jobs/${encodeURIComponent(jobId)}` : runId ? `/api/diagnostics/runs/${encodeURIComponent(runId)}` : null;
  const identity = `${jobId ? `job:${jobId}` : runId ? `run:${runId}` : "none"}|${revision ?? ""}|refresh:${refreshKey}`;
  const identityRef = useRef(identity);
  // Keep the guard current during render as well as in the effect. A mocked
  // or unusually fast fetch may settle before React runs the next effect.
  identityRef.current = identity;

  const load = useCallback(async () => {
    if (!path) return;
    const request = ++requestSequence.current;
    activeController.current?.abort();
    const controller = new AbortController();
    activeController.current = controller;
    setStatus("loading");
    setErrorCode("");
    try {
      const raw = await getJson<unknown>(path, { signal: controller.signal });
      if (request !== requestSequence.current || identityRef.current !== identity) return;
      setDetail(parseDiagnosticDetail(raw));
      setStatus("loaded");
    } catch (error) {
      if (request !== requestSequence.current || identityRef.current !== identity || controller.signal.aborted) return;
      setErrorCode(error instanceof ApiRequestError ? error.code || `http_${error.status}` : "request_failed");
      setStatus("error");
    } finally {
      if (request === requestSequence.current) activeController.current = null;
    }
  }, [identity, path]);

  useEffect(() => {
    requestSequence.current += 1;
    activeController.current?.abort();
    activeController.current = null;
    setStatus("idle");
    setDetail(null);
    setErrorCode("");
    // Parent revision changes should update an already-open disclosure. This
    // is deliberately one bounded request per revision, not an uncontrolled
    // polling loop.
    if (detailsRef.current?.open) void load();
    return () => {
      requestSequence.current += 1;
      activeController.current?.abort();
      activeController.current = null;
    };
  }, [identity, load]);

  if (!path) return null;

  return (
    <details
      className="diag-detail"
      data-qa="diag-detail"
      ref={detailsRef}
      onToggle={(event) => {
        // Nested disclosures (developer info/export) also emit `toggle`.
        // Only the detail disclosure owns loading; otherwise opening a child
        // briefly replaces the loaded body with the loading state.
        if (event.target !== event.currentTarget) return;
        if (event.currentTarget.open) void load();
      }}
    >
      <summary className="diag-detail-toggle" data-qa="diag-detail-toggle">실행 상세</summary>
      <div className="diag-detail-body" data-qa="diag-detail-body">
        {status === "loading" && <p role="status">불러오는 중입니다.</p>}
        {status === "error" && (
          <p className="diag-detail-error" data-qa="diag-detail-error" role="alert" data-error-code={errorCode}>
            진단 조회에 실패했습니다. ({errorCode})
            {" "}
            <button type="button" className="btn btn--sm btn--text" data-qa="diag-detail-retry" onClick={() => void load()}>다시 시도</button>
          </p>
        )}
        {status === "loaded" && detail && <DiagnosticBody detail={detail} />}
      </div>
    </details>
  );
}

function DiagnosticBody({ detail }: { detail: DiagnosticDetailPayload }) {
  const state = classifyDiagnosticState(detail, false);
  const record = detail.record;
  const failure = record ? record.terminalFailure || record.firstFailure || record.errors[0] : null;
  const hasFallback = record && (record.fallbackReason || (record.attemptedEngine && record.finalEngine && record.attemptedEngine !== record.finalEngine));
  const hasCoverageLimit = detail.diagnosticQuality === "partial" || record?.requiredProducerCoverage === "partial";
  const hasRecordedLoss = Boolean(record && (record.droppedEvents > 0 || record.droppedErrors > 0 || record.droppedIssues > 0 || record.issueCodes.length > 0));
  const authorityNote = detail.authorityState === "unavailable"
    ? "현재 작업 상태를 확인할 수 없어 결과를 확정할 수 없습니다."
    : detail.authorityState === "changed"
      ? "현재 작업 상태가 진단 기록과 달라 결과 확인이 필요합니다."
      : null;
  const unresolvedOutcome = state.code !== "normal" && state.code !== "rule_completed" && state.code !== "running";
  const nextAction = state.code === "running"
    ? "wait"
    : unresolvedOutcome && (!failure || failure.nextActionCode === "none")
      ? "inspect_result"
      : failure?.nextActionCode || "none";
  const inspectionTarget = record ? diagnosticInspectionTarget(record.featureCode, nextAction) : null;

  return (
    <div className="diag-detail-content">
      <p className="diag-state-line" data-qa="diag-detail-state" data-state={state.code}>
        <span className="diag-state-badge" data-tone={state.tone}>{state.label}</span>
        {!record && <span className="diag-state-note">{availabilityNote(detail.availabilityReason)}</span>}
        {record && hasCoverageLimit && <span className="diag-state-note" data-qa="diag-detail-coverage">진단 범위가 일부 경로에 한정되어 전체 실행을 확인할 수 없습니다.</span>}
        {record && hasRecordedLoss && <span className="diag-state-note" data-qa="diag-detail-loss">기록 손실이 있어 일부 사건을 확인할 수 없습니다.</span>}
        {authorityNote && <span className="diag-state-note" data-qa="diag-detail-authority">{authorityNote}</span>}
      </p>
      {record && (
        <dl className="diag-detail-facts">
          <dt>실패 단계</dt>
          <dd data-qa="diag-detail-failed-stage">{failure ? stageLabel(failure.stageCode) : "실패가 기록되지 않았습니다."}</dd>
          <dt>확인된 원인</dt>
          <dd data-qa="diag-detail-reason">{failure ? `${reasonLabel(failure.reasonCode)} · ${confirmationLabel(failure.confirmation)}` : "없음"}</dd>
          <dt>마지막으로 완료된 단계</dt>
          <dd data-qa="diag-detail-last-stage">{lastCompletedStageLabel(record)}</dd>
          <dt>경과 시간</dt>
          <dd data-qa="diag-detail-elapsed">{formatElapsed(record.elapsedMs)}</dd>
          <dt>다음 행동</dt>
          <dd data-qa="diag-detail-next-action">
            <span>{nextActionLabel(nextAction)}</span>
            {inspectionTarget && (
              <a className="btn btn--sm btn--text diag-detail-next-action-link" href={inspectionTarget.href} data-qa="diag-detail-next-action-link">
                {inspectionTarget.label}
              </a>
            )}
          </dd>
        </dl>
      )}
      {hasFallback && record && <p className="diag-detail-fallback" data-qa="diag-detail-fallback">{engineFallbackNote(record, diagnosticCompletionConfirmed(detail) && record.finalEngine === "rules")}</p>}
      {record && <DevInfo record={record} />}
      {record && <DiagnosticExport key={record.runId} runId={record.runId} />}
    </div>
  );
}

function DevInfo({ record }: { record: DiagnosticRecord }) {
  const [copied, setCopied] = useState<"" | "ok" | "fail">("");
  const failure = record.terminalFailure || record.firstFailure || record.errors[0];
  const lossy = record.droppedEvents > 0 || record.droppedErrors > 0 || record.droppedIssues > 0;

  const copyDiagnosticId = async () => {
    const lines = [
      `runId: ${record.runId}`,
      record.jobId ? `jobId: ${record.jobId}` : null,
      failure ? `errorId: ${failure.errorId}` : null,
      failure ? `fingerprint: ${failure.fingerprint}` : null,
    ].filter((line): line is string => line !== null);
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied("ok");
    } catch {
      setCopied("fail");
    }
    window.setTimeout(() => setCopied(""), 2000);
  };

  return (
    <details className="diag-detail-devinfo" data-qa="diag-detail-devinfo">
      <summary>개발자 정보</summary>
      <div className="surface surface--inset diag-detail-devinfo-body">
        <dl className="diag-detail-facts">
          <dt>실행 ID</dt>
          <dd>{record.runId}</dd>
          {record.jobId && <><dt>작업 ID</dt><dd>{record.jobId}</dd></>}
          <dt>영역 · 경로</dt>
          <dd>{record.featureCode} · {record.routeCode}</dd>
          <dt>실행 방식</dt>
          <dd>{adapterLabel(record.adapter)}</dd>
          {failure && <><dt>오류 ID</dt><dd>{failure.errorId}</dd></>}
          {failure && <><dt>지문</dt><dd className="diag-detail-fingerprint">{failure.fingerprint}</dd></>}
          {failure && failure.frames.length > 0 && (
            <><dt>소스 위치</dt><dd>{failure.frames.map((frame) => `${frame.moduleCode}::${frame.functionCode}:${frame.line}`).join(", ")}</dd></>
          )}
          {lossy && (
            <><dt>기록 손실</dt><dd>{`사건 ${record.droppedEvents}건, 오류 ${record.droppedErrors}건, 알림 ${record.droppedIssues}건 누락`}</dd></>
          )}
        </dl>
        <button type="button" className="btn btn--sm btn--text diag-detail-copy" data-qa="diag-detail-copy" onClick={() => void copyDiagnosticId()}>
          {copied === "ok" ? "복사됨" : copied === "fail" ? "복사 실패" : "진단 ID 복사"}
        </button>
      </div>
    </details>
  );
}
