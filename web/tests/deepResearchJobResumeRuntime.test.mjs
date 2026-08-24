import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const webRoot = fileURLToPath(new URL("..", import.meta.url));
const id = "job_3ce336dd-74a7-4f5b-8e5f-fefd4d5c3176";
class MemoryStorage {
  values = new Map();
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
}

test("Deep Research reload stores only its job id and resumes the same topic job", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const resume = await vite.ssrLoadModule("/src/app/deepResearchJobResume.ts");
  const storage = new MemoryStorage();
  assert.equal(resume.persistDeepResearchJobId(id, storage), true);
  assert.equal(storage.getItem(resume.DEEP_RESEARCH_ACTIVE_JOB_KEY), id);
  const active = await resume.recoverDeepResearchJob((jobId) => Promise.resolve({ id: jobId, taskType: "topic_report", status: "committing" }), storage);
  assert.equal(active.kind, "active");
  assert.equal(active.job.id, id);
  const terminal = await resume.recoverDeepResearchJob((jobId) => Promise.resolve({ id: jobId, taskType: "topic_report", status: "done", result: { reportId: "rp-1" } }), storage);
  assert.equal(terminal.kind, "terminal");
  assert.equal(storage.getItem(resume.DEEP_RESEARCH_ACTIVE_JOB_KEY), null);
});

test("Deep Research recovery rejects cross-task and malformed records", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const resume = await vite.ssrLoadModule("/src/app/deepResearchJobResume.ts");
  const storage = new MemoryStorage();
  resume.persistDeepResearchJobId(id, storage);
  const result = await resume.recoverDeepResearchJob((jobId) => Promise.resolve({ id: jobId, taskType: "briefing", status: "running" }), storage);
  assert.equal(result.kind, "invalid");
  assert.equal(storage.getItem(resume.DEEP_RESEARCH_ACTIVE_JOB_KEY), null);
});

test("404는 사라진 잡이다 — 저장된 id를 지워 영구 안내를 막는다", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const resume = await vite.ssrLoadModule("/src/app/deepResearchJobResume.ts");
  const storage = new MemoryStorage();
  resume.persistDeepResearchJobId(id, storage);
  const gone = await resume.recoverDeepResearchJob(() => Promise.reject(Object.assign(new Error("not found"), { status: 404 })), storage);
  assert.equal(gone.kind, "invalid");
  assert.equal(storage.getItem(resume.DEEP_RESEARCH_ACTIVE_JOB_KEY), null);
  // 네트워크 단절(상태 없음)은 계속 unavailable — id를 지키고 다음 방문에 재시도한다.
  resume.persistDeepResearchJobId(id, storage);
  const offline = await resume.recoverDeepResearchJob(() => Promise.reject(new Error("fetch failed")), storage);
  assert.equal(offline.kind, "unavailable");
  assert.equal(storage.getItem(resume.DEEP_RESEARCH_ACTIVE_JOB_KEY), id);
});
