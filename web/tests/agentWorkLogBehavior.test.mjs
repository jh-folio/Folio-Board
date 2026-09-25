import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("Work Log implements preview-confirm, stale-safe requests, and pagination ordering", async () => {
  const source = await readFile(new URL("../src/app/AgentWorkLog.tsx", import.meta.url), "utf8");
  assert.match(source, /AbortController/);
  assert.match(source, /requestSequence/);
  assert.match(source, /clear-preview/);
  assert.match(source, /deleteJson<WorkLogClearResponse>/);
  assert.match(source, /setOffset\(0\)/);
  assert.match(source, /Math\.max\(0, offset - pageSize\)/);
  assert.match(source, /offset \+ pageSize/);
});

test("legacy job migration moved to Settings and kept its preview-confirm gate", async () => {
  const [migration, settings, workLog] = await Promise.all([
    readFile(new URL("../src/app/WorkLogMigration.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/app/AgentWorkLog.tsx", import.meta.url), "utf8"),
  ]);

  assert.match(migration, /migration-preview/);
  assert.match(migration, /migration-confirm/);
  assert.match(migration, /previewToken: preview\.previewToken/);
  assert.match(migration, /preview\.collisions\.length > 0/);
  assert.match(migration, /role="dialog"/);
  assert.match(migration, /aria-modal="true"/);
  assert.match(settings, /<WorkLogMigrationControl \/>/);
  // 매일 보는 작업 기록에는 일회성 마이그레이션이 남아 있으면 안 된다.
  assert.doesNotMatch(workLog, /migration/i);
});

test("Work Log hides controls that cannot act on the current data", async () => {
  const source = await readFile(new URL("../src/app/AgentWorkLog.tsx", import.meta.url), "utf8");
  assert.match(source, /const showFilters = filter !== "all" \|\| \(data\?\.total \?\? 0\) > 1/);
  assert.match(source, /const showPagination = Boolean\(data && data\.total > pageSize\)/);
  assert.match(source, /\{showFilters \? \(/);
  assert.match(source, /\{showPagination && </);
  // 필터와 새로고침은 한 줄을 공유한다. 접힌 머리말 아래에 빈 행이 생기면 안 된다.
  assert.match(source, /className="work-log-toolbar"/);
  assert.match(source, /data-qa="work-log-refresh"[\s\S]*?aria-label="작업 기록 새로고침"/);
  assert.match(source, /setDetailRefreshKey\(\(key\) => key \+ 1\)/);
  assert.match(source, /<DiagnosticDetail jobId=\{entry\.jobId\} revision=\{entry\.updatedAt\} refreshKey=\{detailRefreshKey\} \/>/);
});

test("proposal bodies are loaded only after an explicit proposal GET", async () => {
  const source = await readFile(new URL("../src/app/AgentWorkLog.tsx", import.meta.url), "utf8");
  const getIndex = source.indexOf("getJson<AgentProposalRecord>");
  const clickIndex = source.indexOf("openProposal");
  assert.ok(clickIndex >= 0 && getIndex > clickIndex);
  assert.doesNotMatch(source, /entry\.(?:summary|diff|markdown|revisedMarkdown|message|path|title)\b/);
});
