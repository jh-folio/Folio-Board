import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const webRoot = fileURLToPath(new URL("..", import.meta.url));

async function loadStrip(t) {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const mod = await vite.ssrLoadModule("/src/app/reportReader/ReportBody.tsx");
  return mod.stripInlineReferenceSections;
}

test("참고자료 섹션만 걷어내고 그 뒤 정상 본문은 남긴다", async (t) => {
  const strip = await loadStrip(t);
  // 실측: `### 참고자료` 아래에 `### 밸류에이션과 DCF 관련 주의`가 이어지는데
  // 문서 끝까지 자르면서 그 주의 문단이 통째로 사라졌다(notes 2,031→978자).
  const markdown = [
    "## 8. 자료 한계와 참고자료",
    "",
    "확인 기간: 2024–2026.",
    "",
    "### 참고자료",
    "",
    "- [10-K](https://sec.gov/x)",
    "- [10-Q](https://sec.gov/y)",
    "",
    "### 밸류에이션과 DCF 관련 주의",
    "",
    "역산 성장률은 1년차 값이며 이후 감쇠합니다.",
  ].join("\n");
  const out = strip(markdown);
  assert.ok(out.includes("## 8. 자료 한계와 참고자료"));
  assert.ok(out.includes("확인 기간: 2024–2026."));
  assert.ok(out.includes("### 밸류에이션과 DCF 관련 주의"));
  assert.ok(out.includes("역산 성장률은 1년차 값이며 이후 감쇠합니다."));
  // 참고자료 목록 자체는 패널이 맡으므로 본문에서 제거된다.
  assert.ok(!out.includes("### 참고자료"));
  assert.ok(!out.includes("https://sec.gov/x"));
});

test("참고자료가 문서 맨 끝이면 헤딩부터 끝까지 제거한다(브리핑 기존 동작)", async (t) => {
  const strip = await loadStrip(t);
  const markdown = "## 3. 다음 주 일정\n\n내용.\n\n## 참고자료\n\n- [자료](https://example.com/a)\n";
  const out = strip(markdown);
  assert.equal(out.trim(), "## 3. 다음 주 일정\n\n내용.");
});

test("분석 섹션 'Sources of Uncertainty'는 참고자료로 오인하지 않는다", async (t) => {
  const strip = await loadStrip(t);
  const markdown = "## Analysis\n\nbody\n\n## Sources of Uncertainty\n\nstill body\n";
  assert.equal(strip(markdown), markdown);
});

test("참고자료 헤딩이 둘이어도 둘 다 걷어낸다 (2026-08-22 사용자 보고)", async (t) => {
  const strip = await loadStrip(t);
  // 서버가 저장 시 놓친 경우의 2차 방어. 단일 패스면 두 번째 목록이 본문에 남는다.
  const markdown = [
    "## 본론", "", "분석 내용.", "",
    "## 참고자료", "", "- [a](https://example.com/a)", "",
    "## 참고자료", "", "- [b](https://example.com/b)",
  ].join("\n");
  const out = strip(markdown);
  assert.equal(out.trim(), "## 본론\n\n분석 내용.");
  assert.ok(!out.includes("참고자료"));
  assert.ok(!out.includes("https://example.com/b"));
});

test("서버 strip_markdown_sources_section과 같이 다음 헤딩(레벨 무관)에서 멈춘다", async (t) => {
  const strip = await loadStrip(t);
  // `### 참고자료` 뒤 `### 밸류에이션 주의`(같은 레벨)도, `## 다음`(상위)도 남는다.
  const markdown = "## 자료\n\n### 참고자료\n\n- [a](https://example.com/a)\n\n### 밸류에이션 주의\n\n주의 문단\n";
  const out = strip(markdown);
  assert.ok(out.includes("### 밸류에이션 주의"));
  assert.ok(out.includes("주의 문단"));
  assert.ok(!out.includes("### 참고자료"));
});

test("끝 구분선 제거가 이전 정규식과 같고 구분선이 많아도 되짚지 않는다", async (t) => {
  const strip = await loadStrip(t);
  const hostile = "## 본문\n\n내용" + "\n---\n".repeat(40) + "x\n\n### 참고자료\n\n- [a](https://example.com/a)";
  const started = performance.now();
  const out = strip(hostile);
  assert.ok(performance.now() - started < 100);
  assert.ok(out.endsWith("x"));
  assert.equal(strip("## 본문\n\n내용\n\n---\n\n---\n\n### 참고자료\n\n- [a](https://example.com/a)"), "## 본문\n\n내용");
});
