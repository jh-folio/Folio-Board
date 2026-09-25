import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ApiRequestError, ApiResponseReadError, ApiTransportError } from "../api";
import {
  ReportErrorDiagnostic,
  captureReportError,
  isResponseLessError,
  reportErrorDiagnosticIds,
  reportErrorMessage,
} from "./reportErrorDiagnostic";

const REQUEST_ID = "req_12345678-1234-4234-8234-123456789abc";
const RUN_ID = "run_abcdefab-cdef-4abc-8def-abcdefabcdef";

describe("ReportErrorDiagnostic", () => {
  it("delegates a run-linked HTTP error to the existing detail disclosure", () => {
    const error = new ApiRequestError("/api/topic-reports", 500, "generation_failed", null, REQUEST_ID, RUN_ID);
    const html = renderToStaticMarkup(createElement(ReportErrorDiagnostic, { diagnostic: captureReportError(error, 7) }));
    expect(html).toContain('data-qa="report-error-diagnostic"');
    expect(html).toContain('data-qa="diag-detail"');
    expect(html).not.toContain("report-request-id");
    expect(reportErrorDiagnosticIds(error)).toEqual({ requestId: REQUEST_ID, runId: RUN_ID });
  });

  it("shows a request-only ID in a collapsed developer disclosure", () => {
    const error = new ApiRequestError("/api/analysis", 502, "request_failed", null, REQUEST_ID, null);
    const html = renderToStaticMarkup(createElement(ReportErrorDiagnostic, { diagnostic: captureReportError(error, 8) }));
    expect(html).toContain('data-qa="report-request-detail"');
    expect(html).toContain('data-qa="report-request-id"');
    expect(html).toContain(REQUEST_ID);
    expect(html).toContain("개발자 정보");
  });

  it("does not render a lookup affordance when no validated ID is available", () => {
    const error = new ApiRequestError("/api/briefings", 500, "request_failed", null, "req_bad", "run_bad");
    const html = renderToStaticMarkup(createElement(ReportErrorDiagnostic, { diagnostic: captureReportError(error, 9) }));
    expect(html).toBe("");
    expect(reportErrorDiagnosticIds(error)).toBeNull();
  });
});

describe("report error copy", () => {
  it("keeps response-less generation failures neutral and safe", () => {
    const transport = new ApiTransportError();
    const bodyRead = new ApiResponseReadError();
    expect(isResponseLessError(transport)).toBe(true);
    expect(isResponseLessError(bodyRead)).toBe(true);
    expect(reportErrorMessage(transport, "fallback")).toBe("서버 처리 결과를 확인할 수 없습니다.");
    expect(reportErrorMessage(bodyRead, "fallback")).toBe("서버 처리 결과를 확인할 수 없습니다.");
    expect(reportErrorMessage(new Error("AbortError"), "fallback")).toBe("AbortError");
  });
});
