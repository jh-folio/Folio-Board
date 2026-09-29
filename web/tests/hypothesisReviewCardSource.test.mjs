import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const card = fs.readFileSync(
  new URL("../src/app/reportReader/HypothesisReviewCard.tsx", import.meta.url),
  "utf8",
);
const panel = fs.readFileSync(
  new URL("../src/app/reportReader/FolioNotePanel.tsx", import.meta.url),
  "utf8",
);
const api = fs.readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const styles = fs.readFileSync(new URL("../../public/styles.css", import.meta.url), "utf8");

test("all report readers reuse one deterministic hypothesis review card", () => {
  assert.match(panel, /HypothesisReviewCard/);
  assert.match(panel, /noteExists=/);
  assert.match(card, /getHypothesisIntelligence/);
  assert.match(card, /updateHypothesisCheckpoint/);
  assert.doesNotMatch(card, /\/api\/agent\/chat/);
});

test("review card renders controlled state and explicit actions", () => {
  for (const label of [
    "최신 근거로 검토",
    "체크포인트 확인",
    "Agent에게 설명 요청",
    "아직 저장된 노트가 없습니다",
    "티커가 없어 관심·투자 이유와 연결할 수 없습니다",
    "최신 Delta가 없습니다",
    "Agent를 사용할 수 없습니다",
  ]) {
    assert.match(card, new RegExp(label));
  }
  assert.match(card, /checkpointCounts/);
  assert.match(card, /counterEvidenceCount/);
  assert.match(card, /lastReviewedAt/);
  assert.match(card, /nextReviewAt/);
  assert.match(card, /reviewState\.freshness/);
});

test("typed intelligence API and stacked card styles are present", () => {
  assert.match(api, /export type HypothesisIntelligencePayload/);
  assert.match(api, /\/api\/investment-notes\/\$\{encodeURIComponent\(noteId\)\}\/intelligence/);
  assert.match(api, /\/api\/theses\/\$\{encodeURIComponent\(ticker\)\}\/review\/checkpoints/);
  assert.match(styles, /\.hypothesis-review-card/);
  assert.match(styles, /\.hypothesis-review-actions[\s\S]*grid-template-columns:\s*1fr/);
})

test("explicit review click reuses Thesis Delta job polling without automatic execution", () => {
  assert.match(api, /export async function runThesisReview/);
  assert.match(card, /pollReviewJob/);
  assert.match(card, /runExplicitReview/);
  assert.match(card, /onClick=\{runExplicitReview\}/);
  const effectBodies = [...card.matchAll(/useEffect\(\(\) => \{([\s\S]*?)\}, \[/g)]
    .map((match) => match[1]);
  assert.ok(effectBodies.every((body) => !body.includes("runThesisReview(")));
});
