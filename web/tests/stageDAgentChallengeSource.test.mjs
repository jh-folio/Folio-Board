import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("Stage D challenge actions carry IDs only and auto-submit only after an explicit click", async () => {
  const [panel, workspace, scoped, dock, threadList, watchlist, portfolio] = await Promise.all([
    read("../src/app/marketMemory/NarrativeVerificationPanel.tsx"),
    read("../src/app/watchlist/ThesisWorkspace.tsx"),
    read("../src/app/agentWorkspace/openScopedThread.ts"),
    read("../src/app/ReactAgentDock.tsx"),
    read("../src/app/agentWorkspace/ThreadList.tsx"),
    read("../src/app/watchlist/ConsultationEntry.tsx"),
    read("../src/app/portfolio/ConsultationEntry.tsx"),
  ]);

  assert.match(panel, /이 전제를 반박해줘/);
  assert.match(panel, /scope: \{ kind: "market_memory", id: state\.stateId, intent: "challenge" \}/);
  assert.match(workspace, /이 Thesis를 반박해줘/);
  assert.match(workspace, /scope: \{ kind: "watchlist", id: ticker, tickers: \[ticker\], intent: "challenge" \}/);
  assert.match(panel, /autoSubmit: true/);
  assert.match(workspace, /autoSubmit: true/);
  assert.match(scoped, /autoSubmit\?: boolean/);
  assert.match(scoped, /folio:agent-thread-ack/);
  assert.match(scoped, /Promise<void>/);
  assert.match(dock, /scopedAutoSubmitInFlight/);
  assert.match(dock, /scopedAutoSubmitInFlight\.current\.size > 0/);
  assert.match(dock, /await threads\.createThread\(\{ title: detail\.title, scope: detail\.scope \}\)/);
  assert.match(dock, /void submitAgentMessage\(detail\.initialMessage, \{\}, created\.id, \{/);
  assert.match(dock, /onAccepted: \(\) =>/);
  assert.match(dock, /onRejected: \(\) =>/);
  assert.match(dock, /threads\.deleteEmptyThread\(created\.id\)/);
  assert.match(dock, /ok: false, error: "Agent가 다른 요청을 처리 중입니다/);
  assert.doesNotMatch(watchlist, /autoSubmit:\s*true/);
  assert.doesNotMatch(portfolio, /autoSubmit:\s*true/);
  assert.match(threadList, /scope\.kind === "market_memory"\) return base/);
});

test("Stage D UI actions use the shared button primitive without a load-time Agent side effect", async () => {
  const [panel, workspace, css, investmentReview] = await Promise.all([
    read("../src/app/marketMemory/NarrativeVerificationPanel.tsx"),
    read("../src/app/watchlist/ThesisWorkspace.tsx"),
    read("../../public/styles.css"),
    read("../src/app/portfolio/InvestmentReviewWorkspace.tsx"),
  ]);
  // 알림 줄의 반박 버튼은 `.btn--sm`이다. 프리미티브를 쓰는지만 본다 — 크기 변형까지
  // 고정하면 배치가 바뀔 때마다 계약이 깨진다.
  assert.match(panel, /className="btn(\s|")/);
  assert.match(workspace, /className="btn(\s|")/);
  const panelEffect = panel.match(/useEffect\(\(\) => \{[\s\S]*?\}, \[refreshKey\]\);/)?.[0] || "";
  const workspaceEffect = workspace.match(/useEffect\(\(\) => \{[\s\S]*?\}, \[ticker\]\);/)?.[0] || "";
  assert.doesNotMatch(panelEffect, /openScopedThread|autoSubmit|agent/);
  assert.doesNotMatch(workspaceEffect, /openScopedThread|autoSubmit|agent/);
  // 모바일에서 버튼은 자기 줄을 갖고 44px 타깃을 지킨다.
  assert.match(css, /\.verification-alert__action \{[\s\S]*?margin-left: auto/);
  assert.match(css, /\.verification-alert__action \{ margin-left: 0; min-height: 44px; \}/);
  // Investment Review change rows are now grouped by a safe, kind-specific
  // projection; raw saved values must not be stringified into the UI.
  assert.match(investmentReview, /function changeCopy/);
  assert.match(investmentReview, /function changeDetail/);
  assert.doesNotMatch(investmentReview, /\{text\(row\.key\)\}/);
});
