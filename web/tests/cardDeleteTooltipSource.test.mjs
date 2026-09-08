import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

const ROUTES = [
  ["WatchlistRoute.tsx", "watchlist-card"],
  ["BriefingRoute.tsx", "briefing-archive-card"],
  ["CompanyAnalysisRoute.tsx", "report-feed-card"],
  ["DeepResearchRoute.tsx", "report-feed-card"],
];

test("card delete tooltips open downward so overflow:hidden cards do not clip them", async () => {
  const css = await readFile(new URL("../../public/styles.css", import.meta.url), "utf8");
  // 카드가 overflow를 자르는 한, 기본 위치(버튼 위)의 툴팁은 카드 밖으로 나가 잘린다.
  for (const [, card] of ROUTES) {
    const block = css.slice(css.indexOf(`.${card} {`));
    assert.match(block.slice(0, 400), /overflow:\s*hidden/, `${card}는 여전히 overflow를 자릅니다`);
  }
  for (const [file] of ROUTES) {
    const source = await readFile(new URL(`../src/app/${file}`, import.meta.url), "utf8");
    const tooltips = source.match(/data-tooltip="삭제"/g) || [];
    const positioned = source.match(/data-tooltip="삭제"[\s\S]{0,120}?data-tooltip-pos="bottom"/g) || [];
    assert.equal(positioned.length, tooltips.length, `${file}의 삭제 툴팁에 data-tooltip-pos="bottom"이 필요합니다`);
  }
});

