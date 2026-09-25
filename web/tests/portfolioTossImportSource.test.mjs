import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const component = readFileSync(new URL("../src/app/portfolio/TossHoldingsImport.tsx", import.meta.url), "utf8");
const route = readFileSync(new URL("../src/app/PortfolioRoute.tsx", import.meta.url), "utf8");

test("Portfolio Toss import is an explicit masked preview-confirm flow", () => {
  assert.match(component, /\/api\/portfolio\/toss\/accounts/);
  assert.match(component, /\/api\/portfolio\/toss\/preview/);
  assert.match(component, /\/api\/portfolio\/toss\/confirm/);
  assert.match(component, /expectedRevision: preview\.expectedRevision/);
  assert.match(component, /미리보기 후 확인/);
  assert.doesNotMatch(component, /accountNo|accountSeq|averagePurchasePrice|lastPrice/);
  assert.match(component, /setPreview\(null\);/);
  assert.match(component, /role="status"/);
  assert.match(component, /role="listitem"/);
  assert.match(component, /blockDirtyDraft/);
  assert.match(component, /externalBusy = false/);
  assert.match(component, /const controlsLocked = busy !== "" \|\| externalBusy/);
  assert.match(route, /<TossHoldingsImport/);
  assert.match(route, /dirty=\{false\}/);
  assert.match(route, /const authorityRequest = useRef\(0\)/);
  assert.match(route, /const mutationId = \+\+authorityRequest\.current/);
  assert.match(route, /if \(requestId !== authorityRequest\.current\) return;/);
  assert.match(route, /externalBusy=\{saving \|\| reloading\}/);
});
