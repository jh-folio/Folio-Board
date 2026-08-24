import { isActiveJobStatus, type JobStatus } from "../api";

export const DEEP_RESEARCH_ACTIVE_JOB_KEY = "folio.deepResearch.activeJob.v1";
const JOB_ID_PATTERN = /^job_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const STATUSES = new Set<JobStatus>([
  "queued", "running", "cancel_requested", "committing", "done", "cancelled", "failed",
  "failed_cancel", "failed_commit", "failed_restart", "failed_commit_recovery",
]);
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
type ResumableJob = { id: string; status: JobStatus; taskType?: string; result?: Record<string, unknown>; message?: string; error?: string };
type Recovery = { kind: "none" } | { kind: "active" | "terminal"; job: ResumableJob } | { kind: "unavailable"; id: string } | { kind: "invalid" };

function storageDefault(): StorageLike | null {
  try { return typeof window === "undefined" ? null : window.localStorage; } catch { return null; }
}
function validId(value: unknown): value is string { return typeof value === "string" && JOB_ID_PATTERN.test(value); }

export function clearDeepResearchJobId(storage: StorageLike | null = storageDefault()) {
  try { storage?.removeItem(DEEP_RESEARCH_ACTIVE_JOB_KEY); } catch { /* storage denial is non-fatal */ }
}
export function readDeepResearchJobId(storage: StorageLike | null = storageDefault()) {
  let value: string | null = null;
  try { value = storage?.getItem(DEEP_RESEARCH_ACTIVE_JOB_KEY) ?? null; } catch { return null; }
  if (!value) return null;
  if (!validId(value)) { clearDeepResearchJobId(storage); return null; }
  return value;
}
export function persistDeepResearchJobId(id: string, storage: StorageLike | null = storageDefault()) {
  if (!validId(id) || !storage) return false;
  try { storage.setItem(DEEP_RESEARCH_ACTIVE_JOB_KEY, id); return storage.getItem(DEEP_RESEARCH_ACTIVE_JOB_KEY) === id; } catch { return false; }
}
export async function recoverDeepResearchJob(fetchJob: (id: string) => Promise<unknown>, storage: StorageLike | null = storageDefault()): Promise<Recovery> {
  const id = readDeepResearchJobId(storage);
  if (!id) return { kind: "none" };
  let value: unknown;
  try { value = await fetchJob(id); } catch { return { kind: "unavailable", id }; }
  if (!value || typeof value !== "object" || Array.isArray(value)) { clearDeepResearchJobId(storage); return { kind: "invalid" }; }
  const job = value as ResumableJob;
  if (job.id !== id || !STATUSES.has(job.status) || (job.taskType !== undefined && job.taskType !== "topic_report")) {
    clearDeepResearchJobId(storage); return { kind: "invalid" };
  }
  if (isActiveJobStatus(job.status)) return { kind: "active", job };
  clearDeepResearchJobId(storage);
  return { kind: "terminal", job };
}

