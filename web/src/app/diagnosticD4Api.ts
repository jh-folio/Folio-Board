import { getJson, postJson } from "../api";

export const DIAGNOSTIC_RETENTION_DAYS = [7, 30, 90, 180, 365] as const;
export type DiagnosticRetentionDays = (typeof DIAGNOSTIC_RETENTION_DAYS)[number];

export type DiagnosticExportRecord = {
  readonly runId: string;
  readonly relation: "selected" | "parent" | "child";
  readonly record: Record<string, unknown>;
};
export type DiagnosticExportPayload = {
  readonly schemaVersion: 1;
  readonly exportType: "diagnostics";
  readonly selectedRunId: string;
  readonly options: { readonly includeParent: boolean; readonly includeChildren: boolean };
  readonly runs: readonly DiagnosticExportRecord[];
  readonly issues: readonly { readonly code: string; readonly runId: string | null }[];
  readonly summary: string;
};
export type DiagnosticExportPreview = {
  readonly version: 1;
  readonly previewToken: string;
  readonly selectedRunId: string;
  readonly includeParent: boolean;
  readonly includeChildren: boolean;
  readonly runCount: number;
  readonly byteCount: number;
  readonly summary: string;
  readonly json: DiagnosticExportPayload;
};

export type DiagnosticRetentionSettings = {
  readonly retentionDays: DiagnosticRetentionDays;
  readonly autoDelete: boolean;
  readonly choices: readonly DiagnosticRetentionDays[];
  readonly defaultRetentionDays: DiagnosticRetentionDays;
};
export type DiagnosticRetentionStatus = {
  readonly version: 1;
  readonly settings: DiagnosticRetentionSettings;
  readonly usage: { readonly bytesUsed: number; readonly runFiles: number; readonly tombstones: number; readonly entries: number };
  readonly limits: { readonly maxBytes: number; readonly maxRunFiles: number; readonly maxTombstones: number };
  readonly status: { readonly code: string; readonly available: boolean; readonly reason?: string };
};
export type DiagnosticRetentionPreview = {
  readonly version: 1;
  readonly previewToken: string;
  readonly retentionDays: DiagnosticRetentionDays;
  readonly cutoffAt: string;
  readonly expiresAt: string;
  readonly eligibleCount: number;
  readonly eligibleBytes: number;
  readonly oldestCreatedAt: string | null;
  readonly newestCreatedAt: string | null;
  readonly excludedCounts: Record<"running" | "unknown" | "recovery" | "privateBlocked" | "authorityChanged" | "corrupt" | "other", number>;
  readonly status: string;
};
export type DiagnosticRetentionConfirm = {
  readonly version: 1;
  readonly retentionDays: DiagnosticRetentionDays;
  readonly deletedCount: number;
  readonly deletedBytes: number;
  readonly tombstoneCount: number;
  readonly oldestCreatedAt: string | null;
  readonly newestCreatedAt: string | null;
  readonly status: string;
  readonly skippedCounts: Record<string, number>;
};
export type DiagnosticRetentionSettingsPreview = {
  readonly version: 1;
  readonly previewToken: string;
  readonly retentionDays: DiagnosticRetentionDays;
  readonly autoDelete: boolean;
  readonly changed: boolean;
  readonly expiresAt: string;
  readonly current: { readonly retentionDays: DiagnosticRetentionDays; readonly autoDelete: boolean };
  readonly status: string;
};
export type DiagnosticRetentionSettingsConfirm = {
  readonly version: 1;
  readonly retentionDays: DiagnosticRetentionDays;
  readonly autoDelete: boolean;
  readonly updatedAt: string;
  readonly status: string;
};

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const hasExactKeys = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => isObject(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
const hasAllowedKeys = (value: unknown, required: readonly string[], optional: readonly string[] = []): value is Record<string, unknown> => isObject(value) && required.every((key) => Object.prototype.hasOwnProperty.call(value, key)) && Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
const isDays = (value: unknown): value is DiagnosticRetentionDays => DIAGNOSTIC_RETENTION_DAYS.includes(value as DiagnosticRetentionDays);
const isToken = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 120;
const isCount = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 0;

export function parseDiagnosticExportPreview(value: unknown): DiagnosticExportPreview {
  if (!hasExactKeys(value, ["version", "previewToken", "selectedRunId", "includeParent", "includeChildren", "runCount", "byteCount", "summary", "json"]) || value.version !== 1 || !isToken(value.previewToken) || typeof value.selectedRunId !== "string"
    || typeof value.includeParent !== "boolean" || typeof value.includeChildren !== "boolean" || !isCount(value.runCount)
    || !isCount(value.byteCount) || typeof value.summary !== "string" || !isObject(value.json)
    || value.json.schemaVersion !== 1 || value.json.exportType !== "diagnostics" || value.json.selectedRunId !== value.selectedRunId
    || !hasExactKeys(value.json, ["schemaVersion", "exportType", "selectedRunId", "options", "runs", "issues", "summary"]) || typeof value.json.summary !== "string"
    || !isObject(value.json.options) || !hasExactKeys(value.json.options, ["includeParent", "includeChildren"]) || typeof value.json.options.includeParent !== "boolean" || typeof value.json.options.includeChildren !== "boolean"
    || !Array.isArray(value.json.runs) || value.json.runs.length > 20 || value.runCount !== value.json.runs.length || value.byteCount > 1024 * 1024
    || value.json.options.includeParent !== value.includeParent || value.json.options.includeChildren !== value.includeChildren
    || !value.json.runs.some((item) => isObject(item) && item.runId === value.selectedRunId && item.relation === "selected")
    || !value.json.runs.every((item) => hasExactKeys(item, ["runId", "relation", "record"]) && typeof item.runId === "string" && ["selected", "parent", "child"].includes(item.relation as string) && isObject(item.record))
    || !Array.isArray(value.json.issues) || !value.json.issues.every((item) => hasExactKeys(item, ["code", "runId"]) && typeof item.code === "string" && (item.runId === null || typeof item.runId === "string"))) {
    throw new Error("diagnostic_export_contract_invalid");
  }
  return value as DiagnosticExportPreview;
}

export function parseDiagnosticRetentionStatus(value: unknown): DiagnosticRetentionStatus {
  if (!hasExactKeys(value, ["version", "settings", "usage", "limits", "status"]) || value.version !== 1 || !hasExactKeys(value.settings, ["retentionDays", "autoDelete", "choices", "defaultRetentionDays"]) || !isDays(value.settings.retentionDays)
    || typeof value.settings.autoDelete !== "boolean" || !Array.isArray(value.settings.choices) || !value.settings.choices.every(isDays)
    || !isDays(value.settings.defaultRetentionDays) || !isObject(value.usage) || !isCount(value.usage.bytesUsed)
    || !hasExactKeys(value.usage, ["bytesUsed", "runFiles", "tombstones", "entries"]) || !isCount(value.usage.runFiles) || !isCount(value.usage.tombstones) || !isCount(value.usage.entries)
    || !hasExactKeys(value.limits, ["maxBytes", "maxRunFiles", "maxTombstones"]) || !isCount(value.limits.maxBytes) || !isCount(value.limits.maxRunFiles) || !isCount(value.limits.maxTombstones)
    || !hasAllowedKeys(value.status, ["code", "available"], ["reason"]) || typeof value.status.code !== "string" || typeof value.status.available !== "boolean") {
    throw new Error("diagnostic_retention_contract_invalid");
  }
  return value as DiagnosticRetentionStatus;
}

function parsePreviewShape(value: unknown, errorCode: string): asserts value is Record<string, unknown> {
  if (!isObject(value) || value.version !== 1 || !isToken(value.previewToken) || !isDays(value.retentionDays) || typeof value.status !== "string") throw new Error(errorCode);
}

export function parseDiagnosticRetentionPreview(value: unknown): DiagnosticRetentionPreview {
  parsePreviewShape(value, "diagnostic_retention_preview_contract_invalid");
  const excludedCounts = value.excludedCounts;
  if (!hasExactKeys(value, ["version", "previewToken", "retentionDays", "cutoffAt", "expiresAt", "eligibleCount", "eligibleBytes", "oldestCreatedAt", "newestCreatedAt", "excludedCounts", "status"]) || typeof value.cutoffAt !== "string" || typeof value.expiresAt !== "string" || !isCount(value.eligibleCount) || !isCount(value.eligibleBytes)
    || (value.oldestCreatedAt !== null && typeof value.oldestCreatedAt !== "string") || (value.newestCreatedAt !== null && typeof value.newestCreatedAt !== "string")
    || !hasExactKeys(excludedCounts, ["running", "unknown", "recovery", "privateBlocked", "authorityChanged", "corrupt", "other"]) || !["running", "unknown", "recovery", "privateBlocked", "authorityChanged", "corrupt", "other"].every((key) => isCount(excludedCounts[key]))) throw new Error("diagnostic_retention_preview_contract_invalid");
  return value as DiagnosticRetentionPreview;
}

export function parseDiagnosticRetentionSettingsPreview(value: unknown): DiagnosticRetentionSettingsPreview {
  parsePreviewShape(value, "diagnostic_retention_settings_preview_contract_invalid");
  if (!hasExactKeys(value, ["version", "previewToken", "retentionDays", "autoDelete", "changed", "expiresAt", "current", "status"]) || typeof value.autoDelete !== "boolean" || typeof value.changed !== "boolean" || typeof value.expiresAt !== "string" || !hasExactKeys(value.current, ["retentionDays", "autoDelete"])
    || !isDays(value.current.retentionDays) || typeof value.current.autoDelete !== "boolean") throw new Error("diagnostic_retention_settings_preview_contract_invalid");
  return value as DiagnosticRetentionSettingsPreview;
}

export const diagnosticExportPreview = (runId: string, includeParent: boolean, includeChildren: boolean) => postJson<unknown>(`/api/diagnostics/runs/${encodeURIComponent(runId)}/export-preview`, { includeParent, includeChildren }).then(parseDiagnosticExportPreview);
export const diagnosticRetentionStatus = () => getJson<unknown>("/api/diagnostics/retention").then(parseDiagnosticRetentionStatus);
export const diagnosticRetentionPreview = (retentionDays: DiagnosticRetentionDays) => postJson<unknown>("/api/diagnostics/retention/preview", { retentionDays }).then(parseDiagnosticRetentionPreview);
export const diagnosticRetentionConfirm = (previewToken: string) => postJson<DiagnosticRetentionConfirm>("/api/diagnostics/retention/confirm", { previewToken, confirm: true });
export const diagnosticRetentionSettingsPreview = (retentionDays: DiagnosticRetentionDays, autoDelete: boolean) => postJson<unknown>("/api/diagnostics/retention/settings/preview", { retentionDays, autoDelete }).then(parseDiagnosticRetentionSettingsPreview);
export const diagnosticRetentionSettingsConfirm = (previewToken: string) => postJson<DiagnosticRetentionSettingsConfirm>("/api/diagnostics/retention/settings/confirm", { previewToken, confirm: true });
