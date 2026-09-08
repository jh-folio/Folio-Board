import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

const targets = () => readFile(new URL("../src/app/portfolio/PortfolioTargets.tsx", import.meta.url), "utf8");

test("지운 목표는 비교 대상에서도 빠진다", async () => {
  const source = await targets();
  const removeBody = source.slice(source.indexOf("const removePreset = async"), source.indexOf("\n  return <"));

  // 지운 목표를 compareId로 들고 있으면 옛 수치 표가 그대로 남고, 이후 재조회되면
  // 서버가 없는 presetId에 200 + targetWeight 0을 줘 전 종목이 "전량 매도"로 그려진다.
  assert.match(removeBody, /compareId === preset\.id/);
  assert.match(removeBody, /setCompareId\(""\)/);
});

test("목록에 없는 목표는 다시 고른다", async () => {
  const source = await targets();
  const loadBody = source.slice(source.indexOf("const load = useCallback"), source.indexOf("useEffect(() => { void load"));

  // 예전에는 `current || ...`이라 현재 값이 있기만 하면 유지했다 — 다른 탭에서
  // 지워진 목표도 계속 붙잡고 있었다.
  assert.doesNotMatch(loadBody, /setCompareId\(\(current\) => current \|\|/);
  assert.match(loadBody, /list\.some\(\(row\) => row\.id === current && row\.positions\.length\)/);
});
