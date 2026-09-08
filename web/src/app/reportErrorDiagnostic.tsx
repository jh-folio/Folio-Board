import { ApiRequestError, ApiResponseReadError, ApiTransportError, isAbortError } from "../api";
import { DiagnosticDetail } from "./DiagnosticDetail";

export const RESPONSE_LESS_ERROR_MESSAGE = "서버 처리 결과를 확인할 수 없습니다.";

export function isResponseLessError(error: unknown): boolean {
  return error instanceof ApiTransportError || error instanceof ApiResponseReadError;
}

/** A generation error that can be shown next to the route's existing message. */
export type CapturedReportError = {
  readonly operationId: number;
  readonly requestId: string | null;
  readonly runId: string | null;
  readonly responseLess: boolean;
};

export function reportErrorMessage(error: unknown, fallback: string): string {
  if (isResponseLessError(error)) return RESPONSE_LESS_ERROR_MESSAGE;
  if (isAbortError(error)) return "";
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function reportErrorDiagnosticIds(error: unknown): { readonly requestId: string | null; readonly runId: string | null } | null {
  if (!(error instanceof ApiRequestError)) return null;
  if (!error.requestId && !error.runId) return null;
  return { requestId: error.requestId, runId: error.runId };
}

/** Strip the error object before it enters React state: no payload, URL, or raw message is retained. */
export function captureReportError(error: unknown, operationId: number): CapturedReportError {
  const ids = reportErrorDiagnosticIds(error);
  return {
    operationId,
    requestId: ids?.requestId || null,
    runId: ids?.runId || null,
    responseLess: isResponseLessError(error),
  };
}

type ReportErrorDiagnosticProps = {
  readonly diagnostic: CapturedReportError;
};

/**
 * Bounded report-route diagnostic linking. A run ID delegates to the existing
 * DiagnosticDetail disclosure; a request-only error exposes only the request
 * ID in a collapsed developer disclosure because there is no lookup endpoint.
 */
export function ReportErrorDiagnostic({ diagnostic }: ReportErrorDiagnosticProps) {
  if (!diagnostic.requestId && !diagnostic.runId) return null;

  return (
    <div className="report-error-diagnostic" data-qa="report-error-diagnostic">
      {diagnostic.runId ? (
        <DiagnosticDetail runId={diagnostic.runId} revision={diagnostic.operationId} />
      ) : (
        <details className="diag-detail report-error-request-detail" data-qa="report-request-detail">
          <summary className="diag-detail-toggle" data-qa="report-request-detail-toggle">개발자 정보</summary>
          <div className="surface surface--inset diag-detail-devinfo-body">
            <dl className="diag-detail-facts">
              <dt>요청 ID</dt>
              <dd data-qa="report-request-id">{diagnostic.requestId}</dd>
            </dl>
          </div>
        </details>
      )}
    </div>
  );
}
