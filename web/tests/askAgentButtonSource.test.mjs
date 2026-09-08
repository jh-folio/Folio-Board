import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

// "Agent에게 묻기" 버튼을 가진 화면. 도크를 여는 방식이 화면마다 갈리면
// 한쪽이 조용히 죽는다 — 실제로 시장 내러티브 버튼이 그렇게 무반응이 됐다.
const SURFACES = [
  ["../src/islands/MarketStateDashboard.tsx", "시장 내러티브 드라이버 카드"],
];

test("ask-agent buttons open the dock through openReactAgentDock", async () => {
  for (const [relative, label] of SURFACES) {
    const source = await readFile(new URL(relative, import.meta.url), "utf8");
    assert.match(
      source,
      /openReactAgentDock\(/,
      `${label}이 openReactAgentDock를 호출하지 않습니다`,
    );
    assert.match(
      source,
      /aria-label="Agent에게 묻기"/,
      `${label}의 아이콘 전용 버튼에 aria-label이 없습니다`,
    );
  }
});

test("no surface relies on the removed [data-agent-prompt] document handler", async () => {
  // app.js의 문서 수준 핸들러는 제거됐다. 속성만 달아두면 버튼이 눌려도 아무 일이 없다.
  const bridge = await readFile(new URL("../../public/app.js", import.meta.url), "utf8");
  assert.ok(
    !bridge.includes("data-agent-prompt"),
    "app.js에 핸들러가 되살아났다면 이 계약을 다시 검토해야 합니다",
  );
  for (const [relative, label] of SURFACES) {
    const source = await readFile(new URL(relative, import.meta.url), "utf8");
    assert.ok(
      !/data-agent-prompt=/.test(source),
      `${label}이 동작하지 않는 [data-agent-prompt] 속성에 의존합니다`,
    );
  }
});
