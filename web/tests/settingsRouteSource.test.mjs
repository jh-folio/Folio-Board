import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("Settings route owns settings, agent bridge, obsidian, and automation APIs", async () => {
  const source = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /data-settings-route/);
  assert.match(source, /\/api\/settings"/);
  assert.match(source, /\/api\/settings\$\{refreshAgent \? "\?refresh=true" : ""\}/);
  assert.match(source, /\/api\/settings\/llm\/test\/\$\{encodeURIComponent\(providerId\)\}/);
  assert.match(source, /\/api\/agent-bridge\/settings/);
  assert.match(source, /\/api\/obsidian\/settings/);
  assert.match(source, /\/api\/automation\/settings/);
  assert.doesNotMatch(source, /\/api\/automation\/run\/\$\{encodeURIComponent\(kind\)\}/);
  assert.match(source, /\/api\/cache\/stats/);
  assert.match(source, /\/api\/cache\/cleanup/);
});

test("Settings route preserves legacy settings visual class contracts", async () => {
  const source = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /RouteHero/);
  // 하위 탭은 포트폴리오와 같은 `.segment` 프리미티브다. 예전 `.sub-tabs`는 테두리 알약을
  // 화면 CSS에서 따로 선언하고 선택을 `aria-current`로 칠해, 같은 자리의 두 화면이 달라 보였다.
  assert.match(source, /className="segment settings-tabs"/);
  assert.match(source, /aria-pressed=\{tab === item\.id\}/);
  assert.doesNotMatch(source, /sub-tabs/);
  assert.match(source, /settings-panel input-panel/);
  assert.match(source, /settings-grid/);
  assert.match(source, /settings-switch/);
  assert.match(source, /settings-agent-header/);
  assert.match(source, /settings-agent-mode-row/);
  assert.match(source, /settings-switch-compact/);
  assert.match(source, /fieldset className="settings-agent-controls"/);
  assert.match(source, /disabled=\{!agentEnabled\}/);
  assert.match(source, /<\/fieldset>\s*<div className="filter-actions settings-actions">/);
  assert.match(source, /className="segment"/);
  assert.match(source, /filter-actions settings-actions/);
  assert.match(source, /automation-routines/);
  assert.match(source, /automation-card/);
  assert.match(source, /automation-inline-switch/);
  assert.match(source, /15분마다/);
  assert.doesNotMatch(source, /RSS 지금 실행/);
  assert.doesNotMatch(source, /시장 메모리 지금 업데이트/);
  assert.doesNotMatch(source, /브리핑 지금 생성/);
  assert.match(source, /RSS Collection/);
  assert.match(source, /Market Memory/);
  assert.match(source, /Daily Briefing/);
  assert.match(source, /cli-provider-list/);
  assert.match(source, /AI Agent 연동/);
  assert.match(source, /AI Agent 모델 설정/);
  assert.match(source, /전역 모델 설정/);
  assert.doesNotMatch(source, /datalist id="reactAgentModelChoices"/);
  assert.doesNotMatch(source, /datalist id="reactProviderModelChoices"/);
  assert.doesNotMatch(source, /list="reactAgentModelChoices"/);
  assert.doesNotMatch(source, /list="reactProviderModelChoices"/);
  assert.match(source, /folio:agent-settings-updated/);
  assert.match(source, /캐시 관리/);
  assert.match(source, /cleanupCache/);
  assert.match(source, /Toss Open API/);
  assert.match(source, /tossDraft\.clientId/);
  assert.match(source, /tossDraft\.clientSecret/);
  assert.match(source, /ariaLabel="Toss Open API 사용"/);
  assert.match(source, /계좌 조회와 Portfolio 반영은 Portfolio에서 직접 눌렀을 때만 시작/);
});

test("AI model settings keep global and visible task policies in one panel", async () => {
  const source = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

  assert.match(source, /const SETTINGS_TABS:[\s\S]*id: "ai"[\s\S]*id: "admin"[\s\S]*id: "integrations"/);
  assert.match(source, /useState<SettingsTab>\("ai"\)/);
  assert.match(source, /const TASK_POLICY_VISIBLE_ORDER = \[[\s\S]*"daily_briefing"[\s\S]*"company_analysis"[\s\S]*"topic_report"[\s\S]*"market_memory"[\s\S]*\] as const/);
  assert.match(source, /data-qa="ai-agent-model-settings"/);
  assert.match(source, /data-qa="global-model-settings"/);
  assert.match(source, /data-qa="task-policy-settings"/);
  assert.match(source, /<h4>전역 모델 설정<\/h4>/);
  assert.match(source, /<h4>작업별 모델 설정<\/h4>/);
  assert.match(source, /globalReasoningChoices/);
  assert.match(source, /llm: \{ reasoningEffort: globalReasoningEffort \}/);
  assert.match(source, /agent: \{ mode: agentMode \}/);
  assert.match(source, /agent\.provider = agentProvider/);
  assert.match(source, /agent\.model = agentModel/);
  assert.doesNotMatch(source, /<h3>AI Agent 설정<\/h3>/);
  assert.doesNotMatch(source, /<button[^>]*>모델\/상태 새로고침<\/button>/);
  assert.match(source, /TASK_POLICY_VISIBLE_KEYS\.has\(key\) && row\.enabled === true/);
  assert.match(source, /normalizeTaskPoliciesForFrontend\(rawTaskPolicies\)/);
  assert.match(source, /async function saveTaskPolicies/);
  assert.match(source, /function cancelAiAgentSettings/);
  assert.match(source, /onSave=\{saveTaskPolicies\}/);
  assert.match(source, /onCancel=\{cancelTaskPolicies\}/);
  assert.match(source, /\/api\/settings\/task-policies\/check/);
  assert.match(source, /reasoningByModel/);
  assert.match(source, /function saveGlobalModelSettings/);
  assert.match(source, /function cancelGlobalModelSettings/);
  assert.match(source, /loadAll\(true, true\)/);
  assert.match(source, /refreshDraftRef/);
  assert.match(source, /className="task-policy-section"/);
  assert.match(source, /className="global-model-section"/);
  assert.doesNotMatch(source, /saveAiAgentSettings[\s\S]{0,180}taskPolicyRequest/);
});

test("each settings panel reports its own outcome next to its own button", async () => {
  const source = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

  // 결과를 화면 맨 위 한 곳에 모으면, 문서상 1,991px에 있는 자동화 저장을 눌러도
  // 메시지가 54px에 떠 두 화면 반 위에 있다 — 보이지 않는 확인이다.
  assert.match(source, /function PanelNote/);
  for (const panel of ["agent", "api", "notion", "obsidian", "automation", "cache"]) {
    assert.match(source, new RegExp(`<PanelNote note=\{note\} panel="${panel}" />`), panel);
  }
  // 페이지 전체를 못 불러온 것만 위에 남는다.
  assert.doesNotMatch(source, /\{status && <p/);
  assert.doesNotMatch(source, /setStatus\(/);
});

test("제출된 실행은 완료가 아니라 생성 중으로 보인다", async () => {
  const source = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

  // CLI 브리핑은 job을 띄우고 바로 돌아온다. 그 행을 완료로 그리면, 뒤이어 실패로
  // 바뀌는 실행이 화면에서는 계속 성공으로 남는다.
  const body = source.slice(source.indexOf("function runOutcome"), source.indexOf("/** 브리핑 예약 목록."));
  assert.match(body, /run\.status === "submitted"/);
  assert.match(body, /제출됨 — 생성 중/);
  // 중립 tone이다 — 아직 성공도 실패도 아니다.
  assert.match(body, /run\.status === "submitted"\) return \{ tone: "",/);
});

test("자료를 옮긴 뒤 수집·정리가 쉰다는 사실을 안내에 남긴다", async () => {
  const source = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

  // 서버는 collectionPausedUntilRestart로 알리는데 소비자가 없었다. 말하지 않으면
  // 그 창에서 수집 버튼이 아무것도 모으지 않는 이유를 알 길이 없다.
  const body = source.slice(source.indexOf("const move = async"), source.indexOf("const reveal = async"));
  assert.match(body, /재시작 전까지는 RSS 수집과 보관 기간 정리가 일시정지됩니다/);
});

test("AppShell renders SettingsRoute on the settings route", async () => {
  const source = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");

  assert.match(source, /<SettingsRoute\s*\/>/);
  assert.match(source, /route\.id === "settings"/);
  assert.match(source, /renderRoutePane/);
});

test("settings route no longer falls back to the legacy settings view", async () => {
  const source = await readFile(new URL("../src/app/routes.ts", import.meta.url), "utf8");

  assert.doesNotMatch(source, /id: "settings", label: "설정", group: "system", legacyViewId: "settings"/);
});

test("React navigation exposes Portfolio and keeps standalone notes hidden", async () => {
  const source = await readFile(new URL("../src/app/routes.ts", import.meta.url), "utf8");

  assert.match(source, /label: "포트폴리오"/);
  assert.doesNotMatch(source, /label: "투자 노트"/);
  assert.doesNotMatch(source, /legacyViewId: "portfolio"/);
  assert.doesNotMatch(source, /legacyViewId: "notes"/);
});

test("Phase 6 shell no longer ships standalone portfolio and notes legacy surfaces", async () => {
  const app = await readFile(new URL("../../public/app.js", import.meta.url), "utf8");
  const html = await readFile(new URL("../../public/index.html", import.meta.url), "utf8");

  assert.doesNotMatch(app, /portfolio\.addPosition/);
  assert.doesNotMatch(app, /notes\.add/);
  assert.doesNotMatch(html, /data-view="portfolio"/);
  assert.doesNotMatch(html, /<section id="notes"/);
  assert.match(html, /id="folioReactRoot"/);
});

test("the agent dock never forces itself wider than its column", async () => {
  const css = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");
  const dock = await readFile(new URL("../src/app/ReactAgentDock.tsx", import.meta.url), "utf8");

  // 도크는 384px 고정 열이다. 컨트롤 셋을 나란히 두면 폼이 461px로 벌어져 77px이
  // 잘렸다. 지금은 버튼 하나로 접고, 열린 컨트롤은 팝오버 안에 세로로 쌓는다.
  assert.match(dock, /react-agent-run-trigger/);
  assert.match(dock, /className="react-agent-run-menu"/);
  // 요약을 버튼에 적어 열지 않고도 무엇으로 도는지 읽힌다.
  assert.match(dock, /const runSummary =/);

  // 바닥은 그대로 열어 둔다 — 나중에 무엇을 더해도 도크를 밀어내지 않는다.
  const toolbar = css.slice(css.indexOf(".react-agent-form-toolbar {"));
  assert.match(toolbar.slice(0, 220), /min-width:\s*0/);
  assert.match(toolbar.slice(0, 220), /flex-wrap:\s*wrap/);
  const trigger = css.slice(css.indexOf(".react-agent-run-trigger {"));
  assert.match(trigger.slice(0, 420), /min-width:\s*0/);
  assert.match(trigger.slice(0, 420), /max-width:\s*100%/);
  // 팝오버는 위로 열린다. 도크 맨 아래라 아래로 열면 화면 밖이다.
  const menu = css.slice(css.indexOf(".react-agent-run-menu {"));
  assert.match(menu.slice(0, 320), /bottom:\s*calc\(100% \+/);
});

test("the dock header keeps its title on one line", async () => {
  const css = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");
  const dock = await readFile(new URL("../src/app/ReactAgentDock.tsx", import.meta.url), "utf8");

  // 글자 버튼 셋이 175px을 가져가면 제목이 두 줄로 접혀 헤더가 107px까지 자란다 —
  // 그만큼 대화가 밀린다. 셋 다 아이콘으로 줄이고 이름은 툴팁으로 남긴다.
  const actions = dock.slice(dock.indexOf('className="react-agent-header-actions"'));
  const block = actions.slice(0, actions.indexOf("</header>"));
  assert.doesNotMatch(block, /react-agent-new-chat/);
  for (const label of ["대화 목록", "새 대화", "AI Agent 닫기"]) {
    assert.match(block, new RegExp(`aria-label="${label}"`), label);
  }
  // 아이콘만 남으므로 이름은 툴팁이 진다.
  assert.equal(block.match(/data-tooltip="/g)?.length, 3);

  const title = css.slice(css.indexOf(".react-agent-dock-title h2 {"));
  assert.match(title.slice(0, 320), /white-space:\s*nowrap/);
  assert.match(title.slice(0, 320), /text-overflow:\s*ellipsis/);
});
