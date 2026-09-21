import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

const wizard = () => readFile(new URL("../src/app/WelcomeWizard.tsx", import.meta.url), "utf8");
const css = () => readFile(new URL("../../public/styles.css", import.meta.url), "utf8");

test("첫 실행 안내는 다섯 단계이고 테마가 자기 단계를 갖는다", async () => {
  const source = await wizard();

  // 예전 4단계에서는 환영 카드가 "이 앱은 무엇인가"와 "무슨 색으로 볼 것인가"를 함께 물었다.
  assert.match(source, /const STEPS: ReadonlyArray<StepId> = \["welcome", "theme", "engine", "markets", "done"\]/);
  assert.match(source, /step === "theme" &&/);
  assert.match(source, /어떤 화면으로 보시겠어요\?/);
  // 환영 단계에서는 테마를 더 이상 묻지 않는다.
  const welcomeBlock = source.slice(source.indexOf('{step === "welcome" &&'), source.indexOf('{step === "theme" &&'));
  assert.doesNotMatch(welcomeBlock, /THEME_CHOICES/);
});

test("AI 단계는 부담이 적은 것부터 두 가지를 같은 말로 낸다", async () => {
  const source = await wizard();
  const block = source.slice(source.indexOf('aria-label="생성 방식"'));
  const labels = [...block.slice(0, 700).matchAll(/>([^<>{]+)<\/button>/g)].map((m) => m[1].trim());

  assert.deepEqual(labels.slice(0, 2), ["AI 없이", "CLI"]);
  // 짧은 라벨은 설명을 대신하지 못한다. 셋 다 고르면 무엇인지 한 문단이 따라온다.
  assert.match(source, /engine === "none" && \(/);
  assert.match(source, /내 컴퓨터에 설치해서 쓰는/);
  assert.doesNotMatch(source, /제공사 서버를 부르는 열쇠/);
});

test("CLI를 고르면 안내 안에서 설치와 로그인을 끝낼 수 있다", async () => {
  const source = await wizard();
  const settings = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");
  const setup = await readFile(new URL("../src/app/AgentCliSetup.tsx", import.meta.url), "utf8");

  // 예전 안내는 "설정 탭에서 설치와 로그인을 마칠 수 있습니다"라고 적어 뒀는데 설정 탭에도
  // 그 버튼이 없었다 — install/login API를 부르는 화면이 저장소에 하나도 없었다.
  assert.match(source, /<AgentCliSetup/);
  assert.match(settings, /<AgentCliSetup/);
  assert.match(setup, /\/api\/agent-bridge\/install\//);
  assert.match(setup, /\/api\/agent-bridge\/login\//);
  assert.match(setup, /\/api\/agent-bridge\/settings\?refresh=true/);

  // 경계 셋을 화면이 먼저 말한다.
  assert.match(setup, /Windows에서만/);
  assert.match(setup, /별도 콘솔 창/);

  // 상태 문구는 한 곳이 소유한다. 설정 탭에 사본을 두면 같은 상태를 두 화면이 다르게 말한다.
  assert.doesNotMatch(settings, /function adapterStatus\(/);
  assert.doesNotMatch(settings, /function adapterStatusClass\(/);
  assert.doesNotMatch(settings, /function checkedAtLabel\(/);
});

test("설정은 API 키 입력과 연결 호출 없이 이전 설정 전환을 안내한다", async () => {
  const settings = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(settings, /providerApiKey|testProvider|\/settings\/llm\/test/);
  assert.match(settings, /LLM API 지원이 종료되었습니다/);
  assert.match(settings, /CLI 전환 필요/);
});

test("완료 화면은 둘러보기를 물어볼 뿐 카드 안에서 돌지 않는다", async () => {
  const source = await wizard();
  const app = await readFile(new URL("../src/app/App.tsx", import.meta.url), "utf8");

  // 카드 안에서 돌면 정작 보여줄 화면이 카드에 가려진다. 카드는 묻기만 하고
  // 둘러보기는 App이 앱 위에 띄운다.
  assert.match(source, /둘러보기를 진행할까요\?/);
  assert.doesNotMatch(source, /WelcomeTour/);
  assert.match(source, /onFinish: \(startTour: boolean\) => void/);
  // 건너뛰기는 "지금은 됐다"는 뜻이다. 건너뛰면 둘러보기도 하지 않는다.
  assert.match(source, /onFinish\(!skipped && wantsTour === true\)/);
  assert.match(app, /<AppTour onDone=/);
});

test("둘러보기는 실제 탭을 옮겨 다니며 그 자리를 조명한다", async () => {
  const tour = await readFile(new URL("../src/app/AppTour.tsx", import.meta.url), "utf8");
  const shell = await readFile(new URL("../src/app/AppShell.tsx", import.meta.url), "utf8");
  const css = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");

  // 들르는 곳 셋: 자료가 들어오고 → 이야기가 되고 → 결과물이 된다.
  const routes = [...tour.matchAll(/route: "([a-z-]+)"/g)].map((m) => m[1]);
  assert.deepEqual(routes, ["rss", "market-memory", "briefing"]);
  // 설명만 바뀌고 뒤가 그대로면 어디를 말하는지 알 수 없다.
  assert.match(tour, /window\.location\.hash = next/);

  // 조명이 붙을 앵커. 클래스는 여럿이 공유하므로 화면 순서에 기대지 않는다.
  assert.match(shell, /data-route=\{route\.id\}/);
  assert.match(tour, /\.react-left-nav-item\[data-route="\$\{route\}"\]/);

  // 같은 div라 key가 없으면 React가 노드를 재사용해 트랜지션이 시작값에 갇힌다.
  assert.match(tour, /key="spot"/);
  assert.match(tour, /key="scrim"/);

  // 9999px 그림자를 단 fixed 요소의 기하 전환은 실측으로 움직이지 않았다.
  const block = css.slice(css.indexOf(".tour-spot,"), css.indexOf(".tour-card {"));
  assert.doesNotMatch(block, /transition:/);
  assert.match(block, /box-shadow: 0 0 0 9999px/);
});

test("안내 색은 앱 계약을 따른다 — 블루는 의미색이라 UI 액센트가 아니다", async () => {
  const sheet = await css();
  const block = sheet.slice(sheet.indexOf("/* ── 첫 실행 안내"), sheet.indexOf(".welcome-shell :focus-visible"));

  // 실측으로 안내의 CTA는 rgb(122,182,234)인데 앱의 .btn--primary는 rgb(11,12,15)라
  // 첫 화면만 톤이 달랐다(DESIGN_SYSTEM §1 원칙 4 — 색은 의미를 가질 때만).
  assert.doesNotMatch(block, /--folio-blue/);
  assert.match(block, /\.welcome-btn--go \{[^}]*background: var\(--folio-surface-dark\)/);
  assert.match(
    block,
    /\.welcome-markets button\[aria-pressed="true"\] \{[^}]*background: var\(--folio-surface-dark\)/,
  );
  // 포커스 링만 계속 블루다 — 그건 앱 전역 계약(--folio-focus)이다.
  assert.match(sheet, /\.welcome-shell :focus-visible \{ outline: 2px solid var\(--folio-focus\)/);
});

test("역방향 Tab이 카드 밖으로 나가지 않는다", async () => {
  const source = await wizard();

  // 단계 제목 h1은 `tabIndex={-1}`이라 focusables() 선택자에 잡히지 않는데, 카드가
  // 열린 직후와 단계 전환 직후에는 포커스가 바로 거기 있고 그 앞에는 포커스 가능한
  // 요소가 없다. 첫 요소로 쳐 주지 않으면 Shift+Tab이 aria-modal 밖으로 빠진다.
  assert.match(source, /const title = shellRef\.current\?\.querySelector<HTMLElement>\("h1"\) \?\? null;/);
  assert.match(source, /event\.shiftKey && \(active === first \|\| active === title \|\| !shellRef\.current\?\.contains\(active\)\)/);
});
