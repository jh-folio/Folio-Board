import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

// 0.6 Stage C — 검증 루프가 보이는 두 표면.
const PANEL = "../src/app/marketMemory/NarrativeVerificationPanel.tsx";
const WORKSPACE = "../src/app/watchlist/ThesisWorkspace.tsx";
const LANGUAGE = "../src/app/verification.ts";
const REVIEW = "../src/app/portfolio/InvestmentReviewWorkspace.tsx";

async function read(relative) {
  return readFile(new URL(relative, import.meta.url), "utf8");
}

test("every personal surface speaks one verdict language", async () => {
  // 각자 라벨을 만들면 같은 상태가 두 이름을 갖는다(계획 C.3). 실제로 `at_risk`가
  // Watchlist에서는 `이탈 위험`, 투자 리뷰에서는 `주의`로 갈려 있었다.
  for (const [file, label] of [[PANEL, "내러티브 알림"], [WORKSPACE, "Thesis workspace"], [REVIEW, "투자 리뷰"]]) {
    const source = await read(file);
    assert.match(source, /from "\.\.\/verification"|from "\.\.\/\.\.\/app\/verification"/, `${label}이 공용 표시 언어를 쓰지 않습니다`);
    // 6값 verdict 라벨을 화면 파일 안에서 다시 정의하면 안 된다.
    assert.ok(!/at_risk:\s*"/.test(source), `${label}이 verdict 라벨을 직접 만듭니다`);
  }
  const workspace = await read(WORKSPACE);
  assert.match(workspace, /checkpointDisplay\(/, "Thesis workspace가 체크포인트 판정 라벨을 직접 만듭니다");
});

test("every state carries an icon and a label, not colour alone", async () => {
  // WCAG 1.4.1 — 색만으로 정보를 전달하지 않는다.
  const language = await read(LANGUAGE);
  const blocks = language.match(/\{ icon: "[^"]+", label: "[^"]+", tone: "[a-z]+" \}/g) || [];
  assert.ok(blocks.length >= 14, `상태 표시 정의가 부족합니다(${blocks.length})`);
  for (const block of blocks) {
    assert.doesNotMatch(block, /icon: ""/, "아이콘 없는 상태 정의가 있습니다");
    assert.doesNotMatch(block, /label: ""/, "라벨 없는 상태 정의가 있습니다");
  }
  for (const file of [PANEL, WORKSPACE, REVIEW]) {
    const source = await read(file);
    assert.match(source, /aria-hidden="true">\{[a-zA-Z.]*(display|signal|verdict)\.icon\}|aria-hidden="true">\{[a-zA-Z]+Display\([^)]*\)\.icon\}/, "기호가 라벨 없이 쓰입니다");
  }
});

test("the two verdict enums never merge into one badge", async () => {
  // 계획 §3.2 — 체크포인트 판정 3값과 Thesis verdict 6값은 다른 층이다.
  const language = await read(LANGUAGE);
  const checkpointKeys = language.match(/CHECKPOINT_STATUS_DISPLAY: Record<CheckpointStatus, Display> = \{([\s\S]*?)\n\};/)?.[1] || "";
  const verdictKeys = language.match(/THESIS_VERDICT_DISPLAY: Record<string, Display> = \{([\s\S]*?)\n\};/)?.[1] || "";
  assert.ok(checkpointKeys && verdictKeys, "두 표시 표를 찾지 못했습니다");
  for (const sixValue of ["strengthened", "maintained", "weakened", "at_risk", "broken", "insufficient_evidence"]) {
    assert.ok(!checkpointKeys.includes(`${sixValue}:`), `체크포인트 표에 Thesis verdict ${sixValue}가 섞였습니다`);
  }
  for (const threeValue of ["confirmed:", "challenged:"]) {
    assert.ok(!verdictKeys.includes(threeValue), `Thesis verdict 표에 체크포인트 판정 ${threeValue}가 섞였습니다`);
  }

  const workspace = await read(WORKSPACE);
  assert.match(workspace, /Thesis 종합 판정/, "Thesis verdict 배지가 어느 층인지 말하지 않습니다");
  assert.match(workspace, /thesisVerdictDisplay\(delta\?\.verdict\)/, "Delta verdict가 6값 표를 쓰지 않습니다");
});

test("the personal area declares the hypothesis boundary", async () => {
  const workspace = await read(WORKSPACE);
  assert.match(workspace, /data-layer="hypothesis"/, "개인 영역이 hypothesis 계층을 선언하지 않습니다");
  assert.match(workspace, /내 생각·가설 · 근거 아님/, "근거 아님 경계 표시가 없습니다");
});

test("silence badge wording comes from the fixed ladder", async () => {
  const language = await read(LANGUAGE);
  assert.match(language, /cooling: \{ icon: "[^"]+", label: "식어가는 중"/, "14일 배지 문구가 없습니다");
  assert.match(language, /dormant: \{ icon: "[^"]+", label: "정리 후보"/, "30일 배지 문구가 없습니다");
});

test("timeline never prints internal evidence ids", async () => {
  // market_regime_changes의 `memory:` 접두는 memory_id 사본이지 evidence_id가 아니다.
  for (const file of [PANEL, WORKSPACE]) {
    const source = await read(file);
    assert.ok(!source.includes("evidenceRefs"), "내부 근거 id를 화면으로 흘립니다");
    assert.ok(!source.includes("memory:"), "내부 id 접두가 화면 코드에 있습니다");
  }
  const panel = await read(PANEL);
  assert.match(panel, /evidenceCount/, "판정 이력이 근거 건수를 말하지 않습니다");
});

test("entering the screen does not run an Agent", async () => {
  // 화면 진입은 저장된 projection만 읽는다(계획 C.2).
  for (const file of [PANEL, WORKSPACE]) {
    const source = await read(file);
    assert.ok(!source.includes("openReactAgentDock"), "화면 진입 컴포넌트가 Agent 도크를 엽니다");
    const loadEffect = source.match(/useEffect\(\(\) => \{[\s\S]*?\}, \[[^\]]*(?:ticker|refreshKey)[^\]]*\]\);/)?.[0] || "";
    assert.ok(!/submitAgent|runThesisReview|\/api\/agent/.test(loadEffect), "화면 진입이 Agent 작업을 실행합니다");
  }
});

test("the workspace reads a projection and writes only from an explicit review click", async () => {
  const workspace = await read(WORKSPACE);
  assert.match(workspace, /getThesisWorkspace\(/, "workspace projection을 읽지 않습니다");
  assert.match(workspace, /async function reviewLatestEvidence\(\)/, "명시적 최신 근거 검토 action이 없습니다");
  assert.match(workspace, /onClick=\{\(\) => void reviewLatestEvidence\(\)\}/, "검토가 사용자 클릭으로 시작되지 않습니다");
  assert.match(workspace, /runThesisReview\(ticker,/, "기존 Thesis Delta 경로를 재사용하지 않습니다");
  assert.match(workspace, /pollAgentJobBounded\(result/, "비동기 Thesis Delta 작업을 공용 bounded polling으로 처리하지 않습니다");
  const effect = workspace.match(/useEffect\(\(\) => \{[\s\S]*?\}, \[ticker\]\);/)?.[0] || "";
  assert.ok(!effect.includes("runThesisReview"), "화면 진입이 검토 write를 실행합니다");
});

test("Watchlist keeps Thesis creation in place and exposes both actions", async () => {
  const watchlist = await read("../src/app/WatchlistRoute.tsx");
  const workspace = await read(WORKSPACE);
  assert.ok(!watchlist.includes("ANALYSIS_HANDOFF_KEY"), "Thesis 만들기가 Watchlist 밖으로 이동합니다");
  assert.match(workspace, /saveThesis\(\{[\s\S]*ticker,/, "명시적 저장이 선택 ticker를 보내지 않습니다");
  assert.match(workspace, /onSubmit=\{\(event\) => \{ event\.preventDefault\(\); void saveDraft\(\); \}\}/, "Thesis 저장이 form action에 묶이지 않았습니다");
  assert.ok(!workspace.includes("window.location.hash"), "Thesis 편집이 Watchlist 밖으로 이동합니다");
  assert.match(workspace, />Thesis 만들기\/수정</, "만들기·수정 action이 없습니다");
  assert.match(workspace, />최신 근거로 검토</, "최신 근거 검토 action이 없습니다");
});

test("timeline labels never expose stored state or evidence-count codes", async () => {
  const language = await read(LANGUAGE);
  assert.match(language, /kind === "status"/, "상태 전환 표시 매핑이 없습니다");
  assert.match(language, /NARRATIVE_STATUS_LABELS\[raw\]/, "상태 enum이 번역되지 않습니다");
  assert.match(language, /kind === "evidence_count"/, "근거 수 변화 표시 매핑이 없습니다");
  assert.match(language, /slice\(1\)\}일/, "근거 수 한국어 표기가 없습니다");
});

test("workspace localizes stored enums and renders bias-control content", async () => {
  const workspace = await read(WORKSPACE);
  assert.match(workspace, /displayConviction/, "conviction 표시 매핑이 없습니다");
  assert.match(workspace, /displayReviewCycle/, "review cycle 표시 매핑이 없습니다");
  assert.match(workspace, /displayPeriod/, "delta period 표시 매핑이 없습니다");
  assert.match(workspace, /모순·반증 관찰/, "contradictions를 표시하지 않습니다");
});

test("async errors announce and disclosures meet the touch target", async () => {
  const panel = await read(PANEL);
  const workspace = await read(WORKSPACE);
  const css = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");
  assert.match(panel, /react-dashboard-error" role="alert"/, "내러티브 오류가 발표되지 않습니다");
  assert.match(workspace, /react-dashboard-error" role="alert"/, "Thesis 오류가 발표되지 않습니다");
  assert.match(css, /verification-alert__detail > summary,[\s\S]*?min-height: 44px/, "disclosure 44px 터치 영역이 없습니다");
});

test("checkpoint direction is explained in words", async () => {
  // direction은 "이 신호가 잡히면 무슨 뜻인가"이므로 라벨 없이 두면 읽히지 않는다.
  for (const file of [PANEL, WORKSPACE]) {
    const source = await read(file);
    assert.match(source, /반증 신호를 기다리는 항목/, "challenging 항목 설명이 없습니다");
    assert.match(source, /확인 신호를 기다리는 항목/, "supporting 항목 설명이 없습니다");
  }
});

test("unverifiable stored checkpoints are surfaced on the thesis surface", async () => {
  // 내러티브 알림 줄에서는 뺐다(2026-09-01 사용자 결정) — 저장 형식이 규칙과 맞지
  // 않는다는 사실은 엔지니어링 신호이지 사용자를 부를 이유가 아니다. 개수는
  // `GET /api/memory/verification`에 그대로 있다. 종목 Thesis는 사용자가 직접 쓴
  // 항목이라 계속 화면이 말한다.
  const workspace = await read(WORKSPACE);
  assert.match(workspace, />\s*검증 불가/, "검증 실패 원소를 Thesis 화면이 말하지 않습니다");
});

test("the ownership pause is announced on the thesis surface", async () => {
  const workspace = await read(WORKSPACE);
  assert.match(workspace, /syncPaused/, "Vault 동기화 중단을 읽지 않습니다");
  assert.match(workspace, /Vault 동기화 멈춤/, "동기화 중단 배지가 없습니다");
});

test("linked-regime propagation says it changes nothing", async () => {
  // A.3 — 전파는 표시일 뿐 verdict를 바꾸지 않는다.
  const workspace = await read(WORKSPACE);
  assert.match(workspace, /regimeAlerts/, "연결 내러티브 경고를 읽지 않습니다");
  assert.match(workspace, /표시일 뿐 Thesis 판정을 바꾸지 않습니다/, "전파 경계 문구가 없습니다");
});

test("new screen CSS uses tokens, not raw radius or weight numbers", async () => {
  const css = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");
  const block = css.match(/0\.6 Stage C — 검증 루프 표시[\s\S]*?(?=\/\* ={10,})/)?.[0] || "";
  assert.ok(block.length > 500, "Stage C CSS 블록을 찾지 못했습니다");
  assert.ok(!/border-radius:\s*\d/.test(block), "모서리에 숫자를 직접 썼습니다(토큰만 허용)");
  assert.ok(!/font-weight:\s*\d/.test(block), "굵기에 숫자를 직접 썼습니다(토큰만 허용)");
  assert.ok(!/min-height:(?! 44px)/.test(block), "44px 터치 타깃 외 min-height를 직접 썼습니다");
});

test("a verification alert names my linked tickers by state ID in the personal-layer colour", async () => {
  // 개인 층(보라)이 판정 칩과 섞이지 않고, 이름이 아니라 상태 ID로만 잇는다(2026-09-25).
  const panel = await read(PANEL);
  assert.match(panel, /ownedTickers=\{ownedTickers\[state\.stateId\]\}/);
  assert.match(panel, /className="chip verification-owned-chip" data-tone="purple" data-layer="hypothesis"/);
  assert.match(panel, /내 종목 \{ownedTickers\.join\(" · "\)\}/);
});
