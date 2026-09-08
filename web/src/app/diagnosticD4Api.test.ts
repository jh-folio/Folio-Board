import { describe, expect, it } from "vitest";
import { parseDiagnosticExportPreview, parseDiagnosticRetentionPreview, parseDiagnosticRetentionSettingsPreview, parseDiagnosticRetentionStatus } from "./diagnosticD4Api";

const exportPreview = {
  version: 1, previewToken: "dxp1_fixture", selectedRunId: "run_fixture", includeParent: false, includeChildren: true, runCount: 2, byteCount: 128,
  summary: "Diagnostics export for run_fixture.",
  json: { schemaVersion: 1, exportType: "diagnostics", selectedRunId: "run_fixture", options: { includeParent: false, includeChildren: true }, runs: [{ runId: "run_fixture", relation: "selected", record: {} }, { runId: "run_child", relation: "child", record: {} }], issues: [], summary: "Diagnostics export for run_fixture." },
};

describe("D4 diagnostic contracts", () => {
  it("accepts bounded export preview and rejects injected fields", () => {
    expect(parseDiagnosticExportPreview(exportPreview).json.runs).toHaveLength(2);
    expect(() => parseDiagnosticExportPreview({ ...exportPreview, secret: "canary" })).toThrow("diagnostic_export_contract_invalid");
  });

  it("accepts retention status and both preview forms", () => {
    expect(parseDiagnosticRetentionStatus({ version: 1, settings: { retentionDays: 30, autoDelete: false, choices: [7, 30, 90, 180, 365], defaultRetentionDays: 30 }, usage: { bytesUsed: 12, runFiles: 1, tombstones: 0, entries: 2 }, limits: { maxBytes: 50, maxRunFiles: 4, maxTombstones: 4 }, status: { code: "ready", available: true } }).settings.autoDelete).toBe(false);
    expect(parseDiagnosticRetentionPreview({ version: 1, previewToken: "dpr1_fixture", retentionDays: 7, cutoffAt: "2026-01-01T00:00:00Z", expiresAt: "2026-01-01T00:10:00Z", eligibleCount: 1, eligibleBytes: 10, oldestCreatedAt: null, newestCreatedAt: null, excludedCounts: { running: 0, unknown: 0, recovery: 0, privateBlocked: 0, authorityChanged: 0, corrupt: 0, other: 0 }, status: "ready" }).eligibleCount).toBe(1);
    expect(parseDiagnosticRetentionSettingsPreview({ version: 1, previewToken: "dsp1_fixture", retentionDays: 90, autoDelete: true, changed: true, expiresAt: "2026-01-01T00:10:00Z", current: { retentionDays: 30, autoDelete: false }, status: "ready" }).changed).toBe(true);
  });
});
