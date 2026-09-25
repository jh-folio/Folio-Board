import { describe, expect, it } from "vitest";

import { diagnosticListQuery, parseDiagnosticList, type DiagnosticListItem } from "./api";

// 0.6 D3 다음 단계 — 실제 서버가 아직 새 라우트를 로드하지 않은 상태에서도(재시작 전)
// 프런트가 백엔드 계약(features/common/diagnostics/listing.py::_project_item/.list)과
// 정확히 맞물리는지 고정한다. 필드 이름·null 의미까지 그 소스에서 그대로 옮겼다.

function item(overrides: Partial<DiagnosticListItem> = {}): DiagnosticListItem {
  return {
    runId: "run_00000000-0000-4000-8000-000000000000",
    createdAt: "2026-09-05T00:00:00.000Z",
    finishedAt: "2026-09-05T00:02:00.000Z",
    observedStatus: "done",
    observedOutcome: "succeeded",
    outcome: "succeeded",
    featureCode: "rss",
    routeCode: "rss_collect",
    authorityKind: "automation",
    authorityState: "matched",
    authorityStatus: "done",
    taskType: null,
    jobId: null,
    workLogId: null,
    diagnosticQuality: "complete",
    adapter: null,
    attemptedEngine: null,
    finalEngine: null,
    fallbackReason: null,
    fallbackObserved: null,
    failureReasonCode: null,
    failureStageCode: null,
    ...overrides,
  };
}

function envelope(items: DiagnosticListItem[], overrides: Record<string, unknown> = {}) {
  return {
    version: 1,
    snapshotAt: "2026-09-05T00:03:00.000Z",
    items,
    nextCursor: null,
    truncated: false,
    scan: { entriesScanned: items.length, runsScanned: items.length, complete: true, deadlineMs: 250 },
    errors: [],
    ...overrides,
  };
}

describe("parseDiagnosticList", () => {
  it("accepts a real-shaped RSS/automation row (no jobId, authority matched)", () => {
    const parsed = parseDiagnosticList(envelope([item()]));
    expect(parsed.items).toHaveLength(1);
    expect(parsed.items[0].jobId).toBeNull();
  });

  it("accepts a job-linked failure row with an unmatched authority (outcome null, observedOutcome present)", () => {
    const failing = item({
      jobId: "job_11111111-1111-4111-8111-111111111111",
      workLogId: "wl_aaaaaaaaaaaaaaaaaaaaaaaa",
      authorityKind: "shared_job",
      authorityState: "changed",
      authorityStatus: "running",
      observedStatus: "failed",
      observedOutcome: "failed",
      outcome: null,
      diagnosticQuality: "partial",
      failureReasonCode: "adapter_failed",
      failureStageCode: "generate",
      attemptedEngine: "cli",
      finalEngine: "rules",
      fallbackReason: "engine_failed",
      fallbackObserved: true,
    });
    const parsed = parseDiagnosticList(envelope([failing]));
    expect(parsed.items[0].outcome).toBeNull();
    expect(parsed.items[0].observedOutcome).toBe("failed");
    expect(parsed.items[0].fallbackObserved).toBe(true);
  });

  it("accepts a direct execution row (authorityState not_applicable, no job/automation authority)", () => {
    const direct = item({ authorityKind: "direct", authorityState: "not_applicable", authorityStatus: null, outcome: null, taskType: "index" });
    expect(() => parseDiagnosticList(envelope([direct]))).not.toThrow();
  });

  it("accepts a truncated cold-scan page (nextCursor must be null while truncated)", () => {
    const parsed = parseDiagnosticList(envelope([item()], { truncated: true, nextCursor: null, scan: { entriesScanned: 5000, runsScanned: 800, complete: false, deadlineMs: 250 } }));
    expect(parsed.truncated).toBe(true);
    expect(parsed.nextCursor).toBeNull();
    expect(parsed.scan.complete).toBe(false);
  });

  it("accepts a page with a forward cursor and scan errors", () => {
    const parsed = parseDiagnosticList(envelope([item()], { nextCursor: "opaque-token", errors: [{ code: "read_failed" }] }));
    expect(parsed.nextCursor).toBe("opaque-token");
    expect(parsed.errors).toEqual([{ code: "read_failed" }]);
  });

  it("rejects an envelope missing a required key", () => {
    const broken = envelope([item()]) as Record<string, unknown>;
    delete broken.scan;
    expect(() => parseDiagnosticList(broken)).toThrow("diagnostic_list_contract_invalid");
  });

  it("rejects an item with an unknown extra field (closed shape, not just a subset check)", () => {
    const withExtra = { ...item(), unexpectedField: "x" };
    expect(() => parseDiagnosticList(envelope([withExtra as unknown as DiagnosticListItem]))).toThrow("diagnostic_list_contract_invalid");
  });

  it("rejects an invalid outcome enum value", () => {
    const bad = item({ observedOutcome: "success" as unknown as DiagnosticListItem["observedOutcome"] });
    expect(() => parseDiagnosticList(envelope([bad]))).toThrow("diagnostic_list_contract_invalid");
  });

  it("rejects an authoritative outcome when authority is not matched", () => {
    const bad = item({ authorityState: "changed", authorityStatus: "failed", outcome: "failed" });
    expect(() => parseDiagnosticList(envelope([bad]))).toThrow("diagnostic_list_contract_invalid");
  });

  it("rejects a run id that is not the server's UUIDv4 form", () => {
    const bad = item({ runId: "run-bbbbbbbbbbbbbbbbbbbbbbbb" });
    expect(() => parseDiagnosticList(envelope([bad]))).toThrow("diagnostic_list_contract_invalid");
  });

  it("rejects inconsistent scan progress metadata", () => {
    const bad = envelope([item()], { truncated: false, scan: { entriesScanned: 1, runsScanned: 1, complete: false, deadlineMs: 250 } });
    expect(() => parseDiagnosticList(bad)).toThrow("diagnostic_list_contract_invalid");
  });
});

describe("diagnosticListQuery", () => {
  it("omits default/empty filter values instead of sending noisy query params", () => {
    expect(diagnosticListQuery({})).toBe("/api/diagnostics/runs?version=1");
    expect(diagnosticListQuery({ outcome: "all", fallback: "all" })).toBe("/api/diagnostics/runs?version=1");
  });

  it("includes only the filters actually set, matching the closed server allow-list", () => {
    const url = diagnosticListQuery({ outcome: "failed", fallback: "observed", from: "2026-09-01T00:00:00.000Z", limit: 50, cursor: "tok" });
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("outcome")).toBe("failed");
    expect(params.get("fallback")).toBe("observed");
    expect(params.get("from")).toBe("2026-09-01T00:00:00.000Z");
    expect(params.get("limit")).toBe("50");
    expect(params.get("cursor")).toBe("tok");
    expect(params.has("to")).toBe(false);
  });
});
