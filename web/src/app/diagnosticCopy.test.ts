import { describe, expect, it } from "vitest";

import type { DiagnosticDetail, DiagnosticRecord } from "../api";
import { classifyDiagnosticState, diagnosticInspectionTarget, engineFallbackNote, formatElapsed, lastCompletedStageLabel } from "./diagnosticCopy";

// 0.6 D3 — 여섯 상태(기록 없음/보존 만료/기록 일부 누락/조회 실패/실행 중/규칙으로 완료)
// 분류가 우선순위대로 갈리는지 고정한다. 실제 백엔드 값 모양(schema.py)과 맞춰 둔다.

function baseRecord(overrides: Partial<DiagnosticRecord> = {}): DiagnosticRecord {
  return {
    schemaVersion: 1,
    runId: "run_00000000-0000-4000-8000-000000000000",
    jobId: "job_00000000-0000-4000-8000-000000000000",
    requestId: null,
    parentRunId: null,
    retryOfRunId: null,
    processEpoch: "00000000-0000-4000-8000-000000000000",
    featureCode: "briefing",
    routeCode: "report_cli",
    taskType: "briefing",
    authorityKind: "shared_job",
    appVersion: "0.6.0",
    buildId: null,
    os: "windows",
    pythonVersion: "3.12.0",
    createdAt: "2026-09-05T00:00:00.000Z",
    updatedAt: "2026-09-05T00:02:00.000Z",
    finishedAt: "2026-09-05T00:02:00.000Z",
    elapsedMs: 120_000,
    observedStatus: "done",
    attemptedEngine: "cli",
    finalEngine: "cli",
    adapter: "codex",
    fallbackReason: null,
    events: [
      { seq: 1, eventId: "evt_1", stageId: "stg_1", stageCode: "generate", eventCode: "start", producerEpoch: "p", at: "t", durationMs: null, errorId: null, count: 1 },
      { seq: 2, eventId: "evt_2", stageId: "stg_1", stageCode: "generate", eventCode: "end", producerEpoch: "p", at: "t", durationMs: 900, errorId: null, count: 1 },
      { seq: 3, eventId: "evt_3", stageId: "stg_2", stageCode: "commit", eventCode: "start", producerEpoch: "p", at: "t", durationMs: null, errorId: null, count: 1 },
      { seq: 4, eventId: "evt_4", stageId: "stg_2", stageCode: "commit", eventCode: "end", producerEpoch: "p", at: "t", durationMs: 100, errorId: null, count: 1 },
    ],
    errors: [],
    firstFailure: null,
    terminalFailure: null,
    terminalObservation: { observedStatus: "done", observedAt: "2026-09-05T00:02:00.000Z", processEpoch: "p" },
    droppedEvents: 0,
    droppedErrors: 0,
    droppedIssues: 0,
    issueCodes: [],
    requiredProducerCoverage: "complete",
    ...overrides,
  };
}

function baseDetail(overrides: Partial<DiagnosticDetail> = {}): DiagnosticDetail {
  return {
    version: 1,
    runId: "run_00000000-0000-4000-8000-000000000000",
    diagnosticQuality: "complete",
    availabilityReason: "present",
    authorityState: "matched",
    authorityStatus: "done",
    record: baseRecord(),
    warnings: [],
    ...overrides,
  };
}

describe("classifyDiagnosticState", () => {
  it("fetch 자체가 실패하면 조회 실패다", () => {
    expect(classifyDiagnosticState(null, true).code).toBe("query_failed");
  });

  it("known job/run에 파일이 아예 없으면 기록 없음이다", () => {
    const detail = baseDetail({ record: null, diagnosticQuality: "unavailable", availabilityReason: "missing_unknown", authorityStatus: null });
    expect(classifyDiagnosticState(detail, false).code).toBe("no_record");
  });

  it("legacy job은 상세가 없어도 기록 없음으로 묶는다", () => {
    const detail = baseDetail({ record: null, diagnosticQuality: "legacy_unavailable", availabilityReason: "legacy_no_detail", authorityStatus: null });
    expect(classifyDiagnosticState(detail, false).code).toBe("no_record");
  });

  it("보존 만료는 별도 상태다", () => {
    const detail = baseDetail({ record: null, diagnosticQuality: "unavailable", availabilityReason: "expired", authorityStatus: null });
    expect(classifyDiagnosticState(detail, false).code).toBe("expired");
  });

  it("잠긴 파일·저장 상한 등은 없음이 아니라 조회 실패다", () => {
    for (const reason of ["writer_conflict", "quota_exceeded", "read_failed", "corrupt", "unsupported_version", "disabled"] as const) {
      const detail = baseDetail({ record: null, diagnosticQuality: "unavailable", availabilityReason: reason, authorityStatus: null });
      expect(classifyDiagnosticState(detail, false).code).toBe("query_failed");
    }
  });

  it("기록이 열려 있어도 현재 권위가 끝났으면 결과 확인 필요다", () => {
    const detail = baseDetail({ record: baseRecord({ finishedAt: null, elapsedMs: null, terminalObservation: null }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("unknown");
  });

  it("권위가 아직 진행 상태를 보고하면 record가 닫혀 있어도 실행 중이다", () => {
    const detail = baseDetail({ authorityStatus: "running" });
    expect(classifyDiagnosticState(detail, false).code).toBe("running");
  });

  it("규칙으로 대체된 완료는 실패가 아니라 규칙 기반 완료다", () => {
    const detail = baseDetail({ record: baseRecord({ fallbackReason: "engine_failed", finalEngine: "rules" }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("rule_completed");
  });

  it("원래 엔진의 firstFailure가 있어도 권위가 완료한 fallback은 완료로 남긴다", () => {
    const firstFailure = {
      errorId: "err_1", stageId: "stg_generate", stageCode: "generate", errorCode: "adapter_failed",
      reasonCode: "adapter_failed", exceptionCode: "runtime_error", frames: [], confirmation: "observed" as const,
      nextActionCode: "none", fingerprint: "fp_1",
    };
    const detail = baseDetail({ record: baseRecord({ firstFailure, errors: [firstFailure], fallbackReason: "engine_failed", finalEngine: "rules" }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("rule_completed");
    expect(engineFallbackNote(detail.record!)).toContain("완료했습니다");
  });

  it("direct 실행은 succeeded terminal observation을 성공으로 인정한다", () => {
    const detail = baseDetail({ authorityState: "not_applicable", authorityStatus: null, record: baseRecord({
      authorityKind: "direct", observedStatus: "succeeded", fallbackReason: "engine_failed", finalEngine: "rules",
      terminalObservation: { observedStatus: "succeeded", observedAt: "2026-09-05T00:02:00.000Z", processEpoch: "p" },
    }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("rule_completed");
  });

  it("권위가 불명인 fallback 문구는 완료를 주장하지 않는다", () => {
    const detail = baseDetail({ authorityState: "unavailable", authorityStatus: null, record: baseRecord({ fallbackReason: "engine_failed", finalEngine: "rules" }) });
    expect(engineFallbackNote(detail.record!, false)).not.toContain("완료했습니다");
  });

  it("부분 관측은 실제 기록 손실과 구분한다", () => {
    const detail = baseDetail({ diagnosticQuality: "partial", record: baseRecord({ requiredProducerCoverage: "partial" }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("partial_coverage");
    const loss = baseDetail({ diagnosticQuality: "partial", record: baseRecord({ requiredProducerCoverage: "partial", droppedEvents: 1 }) });
    expect(classifyDiagnosticState(loss, false).code).toBe("partial_loss");
  });

  it("현재 권위를 읽지 못하면 실행 중이나 정상으로 단정하지 않는다", () => {
    const detail = baseDetail({ authorityState: "unavailable", authorityStatus: null });
    expect(classifyDiagnosticState(detail, false).code).toBe("unknown");
  });

  it("변경된 권위의 열린 진단은 실행 중이 아니라 결과 확인 필요다", () => {
    const detail = baseDetail({ authorityState: "changed", authorityStatus: "failed_restart", record: baseRecord({ finishedAt: null, observedStatus: "running", terminalObservation: null }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("failed");
  });

  it("실패·취소·미확인 결과는 fallbackReason만으로 완료되지 않는다", () => {
    const failed = baseDetail({ authorityStatus: "failed", record: baseRecord({ observedStatus: "failed", finalEngine: "rules", fallbackReason: "engine_failed" }) });
    expect(classifyDiagnosticState(failed, false).code).toBe("failed");
    expect(engineFallbackNote(failed.record!)).not.toContain("완료했습니다");
    const cancelled = baseDetail({ authorityStatus: "cancelled", record: baseRecord({ observedStatus: "cancelled", finalEngine: "rules", fallbackReason: "engine_failed" }) });
    expect(classifyDiagnosticState(cancelled, false).code).toBe("cancelled");
    const unknown = baseDetail({ authorityState: "unavailable", authorityStatus: null, record: baseRecord({ finalEngine: "rules", fallbackReason: "engine_failed" }) });
    expect(classifyDiagnosticState(unknown, false).code).toBe("unknown");
  });

  it("원래도 규칙 경로였다면(대체가 아니면) 규칙 완료로 잡지 않는다", () => {
    const detail = baseDetail({ record: baseRecord({ attemptedEngine: "rules", finalEngine: "rules", fallbackReason: null }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("normal");
  });

  it("사건·오류가 누락되면 일부 누락이다", () => {
    const detail = baseDetail({ record: baseRecord({ droppedEvents: 3 }) });
    expect(classifyDiagnosticState(detail, false).code).toBe("partial_loss");
  });

  it("아무 문제 없는 완료는 정상 기록이다", () => {
    expect(classifyDiagnosticState(baseDetail(), false).code).toBe("normal");
  });
});

describe("diagnostic inspection targets", () => {
  it("uses only known existing routes and inspection actions", () => {
    expect(diagnosticInspectionTarget("briefing", "inspect_result")).toEqual({ href: "#/briefing", label: "목록에서 확인" });
    expect(diagnosticInspectionTarget("briefing", "check_settings")).toEqual({ href: "#/settings", label: "설정에서 확인" });
    expect(diagnosticInspectionTarget("company_analysis", "check_settings")).toEqual({ href: "#/settings", label: "설정에서 확인" });
    expect(diagnosticInspectionTarget("topic_report", "check_settings")).toEqual({ href: "#/settings", label: "설정에서 확인" });
    expect(diagnosticInspectionTarget("topic_report", "inspect_result")).toEqual({ href: "#/deep-research", label: "목록에서 확인" });
    expect(diagnosticInspectionTarget("automation", "check_settings")).toEqual({ href: "#/settings", label: "설정에서 확인" });
    expect(diagnosticInspectionTarget("automation", "inspect_result")).toEqual({ href: "#/settings", label: "설정에서 확인" });
    expect(diagnosticInspectionTarget("rss", "check_settings")).toEqual({ href: "#/settings", label: "설정에서 확인" });
    expect(diagnosticInspectionTarget("rss", "inspect_result")).toEqual({ href: "#/rss", label: "목록에서 확인" });
    expect(diagnosticInspectionTarget("briefing", "wait")).toBeNull();
    expect(diagnosticInspectionTarget("briefing", "none")).toBeNull();
    expect(diagnosticInspectionTarget("briefing", "explicit_retry")).toBeNull();
    expect(diagnosticInspectionTarget("http", "inspect_result")).toBeNull();
  });
});

describe("포맷 도우미", () => {
  it("경과 시간은 분·초 단위로 사람이 읽게 만든다", () => {
    expect(formatElapsed(null)).toBe("측정 안 됨");
    expect(formatElapsed(500)).toBe("500ms");
    expect(formatElapsed(45_000)).toBe("45초");
    expect(formatElapsed(125_000)).toBe("2분 5초");
    expect(formatElapsed(120_000)).toBe("2분");
  });

  it("마지막으로 완료된 단계는 seq가 가장 큰 end 이벤트를 찾는다", () => {
    expect(lastCompletedStageLabel(baseRecord())).toBe("저장");
    expect(lastCompletedStageLabel(baseRecord({ events: [] }))).toBe("완료된 단계 없음");
  });

  it("failure가 붙은 span의 end는 완료 단계에서 제외한다", () => {
    const record = baseRecord({ events: [
      { seq: 1, eventId: "evt_1", stageId: "stg_generate", stageCode: "generate", eventCode: "start", producerEpoch: "p", at: "t", durationMs: null, errorId: null, count: 1 },
      { seq: 2, eventId: "evt_2", stageId: "stg_generate", stageCode: "generate", eventCode: "end", producerEpoch: "p", at: "t", durationMs: 900, errorId: null, count: 1 },
      { seq: 3, eventId: "evt_3", stageId: "stg_commit", stageCode: "commit", eventCode: "start", producerEpoch: "p", at: "t", durationMs: null, errorId: null, count: 1 },
      { seq: 4, eventId: "evt_4", stageId: "stg_commit", stageCode: "commit", eventCode: "failure", producerEpoch: "p", at: "t", durationMs: null, errorId: "err_1", count: 1 },
      { seq: 5, eventId: "evt_5", stageId: "stg_commit", stageCode: "commit", eventCode: "end", producerEpoch: "p", at: "t", durationMs: 100, errorId: null, count: 1 },
    ] });
    expect(lastCompletedStageLabel(record)).toBe("생성");
  });
});
