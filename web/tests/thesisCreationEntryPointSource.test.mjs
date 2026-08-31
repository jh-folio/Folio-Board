import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

// 0.6 Stage B.3 — "연결된 Thesis가 없습니다"에서 끝나던 막다른 길에 만드는 경로를 둔다.
// 빈 상태가 안내로만 끝나면 사용자는 Obsidian 없이 Thesis를 만들 방법을 찾지 못한다.
const CARD = "../src/app/reportReader/HypothesisReviewCard.tsx";

async function cardSource() {
  return readFile(new URL(CARD, import.meta.url), "utf8");
}

test("empty state offers a way to create the thesis", async () => {
  const source = await cardSource();
  assert.match(source, /이 노트로 Thesis 만들기/, "빈 상태에 Thesis 만들기 진입점이 없습니다");
  assert.match(
    source,
    /연결된 Thesis가 없습니다\. 이 노트를 Thesis로 등록하면/,
    "빈 상태 문구가 만드는 경로를 안내하지 않습니다",
  );
});

test("both create and update go through the promote endpoint client", async () => {
  const source = await cardSource();
  assert.match(source, /promoteNoteToThesis\(/, "승격 API 클라이언트를 호출하지 않습니다");
  assert.match(source, /이 노트로 Thesis 갱신/, "명시적 갱신 action이 없습니다");
});

test("overwriting an existing thesis asks first", async () => {
  // 만들기(빈자리)는 잃을 것이 없지만 갱신은 기존 Thesis를 덮는다.
  const source = await cardSource();
  assert.match(
    source,
    /hasThesis && !window\.confirm\(/,
    "기존 Thesis를 덮는 갱신이 확인 없이 실행됩니다",
  );
});

test("the promote client posts to the note-scoped thesis route", async () => {
  const api = await readFile(new URL("../src/api.ts", import.meta.url), "utf8");
  assert.match(
    api,
    /\/api\/investment-notes\/\$\{encodeURIComponent\(noteId\)\}\/thesis/,
    "promoteNoteToThesis가 노트 기준 승격 경로를 쓰지 않습니다",
  );
});
