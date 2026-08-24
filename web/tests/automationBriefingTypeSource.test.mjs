import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

const settings = await readFile(new URL("../src/app/SettingsRoute.tsx", import.meta.url), "utf8");

test("automation exposes the briefing type the schema already stores", async () => {
  // 스키마·서비스는 briefingType을 읽고 있었는데 화면에 선택이 없어서 늘 default로
  // 고정됐다. 셋 중 하나라도 빠지면 자동 브리핑 유형을 고를 수 없다.
  for (const value of ["default", "market_focused", "concise"]) {
    assert.ok(
      settings.includes(`${value}:`),
      `자동화 유형 목록에 ${value}가 없습니다`,
    );
  }
  // 브리핑 예약이 목록이 되면서 유형은 예약마다 고른다(2026-08-09).
  assert.match(settings, /value=\{row\.briefingType\}/, "선택값이 예약에서 읽히지 않습니다");
});

test("the automation save payload carries briefingType", () => {
  // payload에서 빠지면 저장할 때마다 스키마가 default로 되돌린다 — 화면만 고쳐도 소용없다.
  const block = settings.slice(settings.indexOf("    briefingSchedules: ("));
  assert.match(
    block.slice(0, 500),
    /briefingType: row\.briefingType/,
    "저장 payload에 briefingType이 없습니다",
  );
});

test("every schedule field survives the save payload", () => {
  // 예약이 목록이 되면서 필드가 늘었다. payload에서 빠진 필드는 저장할 때마다
  // 서버 기본값으로 되돌아가고, 화면에서는 되돌아간 뒤에야 보인다.
  const block = settings.slice(settings.indexOf("    briefingSchedules: ("));
  // 창은 payload 객체 리터럴을 다 담을 만큼만 — 필드에 붙는 주석이 늘며 500자를 넘겼다.
  for (const field of ["id", "enabled", "time", "markets", "briefingType", "qualityMode", "runPrerequisites"]) {
    assert.ok(block.slice(0, 900).includes(`${field}:`), `저장 payload에 ${field}가 없습니다`);
  }
});

test("the schedule count is capped in the browser as well as the server", () => {
  // 상한이 없으면 24개를 만들어 하루 종일 LLM을 돌릴 수 있다. 서버만 자르면
  // 화면은 만들었다고 보여주고 저장 뒤에 조용히 사라진다.
  assert.match(settings, /const MAX_SCHEDULES = 5/, "화면 쪽 예약 상한이 없습니다");
  assert.match(settings, /slice\(0, MAX_SCHEDULES\)/, "저장 payload가 상한으로 자르지 않습니다");
});
