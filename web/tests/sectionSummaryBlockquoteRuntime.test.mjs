import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// 두 렌더러(레거시 bridge와 React 폴백)가 같은 규칙을 지키는지 함께 본다 —
// 헤딩 바로 다음(사이 빈 줄 허용) blockquote만 섹션 요약으로 본다. 본문 중간의
// 일반 blockquote는 평범하게 렌더한다.

async function loadBridgeRenderMarkdown() {
  const source = await readFile(new URL("../../public/app.js", import.meta.url), "utf8");
  const sandbox = { console, URL, Intl, Date, setTimeout, clearTimeout, addEventListener() {}, removeEventListener() {}, dispatchEvent() {}, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  sandbox.window = sandbox;
  sandbox.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], body: { classList: { add() {}, remove() {}, toggle() {} } } };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox.FolioBridge.renderMarkdown;
}

const webRoot = fileURLToPath(new URL("..", import.meta.url));

async function loadReactMarkdownRenderer(t) {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const mod = await vite.ssrLoadModule("/src/app/reportReader/MarkdownRenderer.tsx");
  return mod.MarkdownRenderer;
}

test("bridge: 섹션 헤딩 바로 다음 blockquote는 section-summary로 렌더된다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = [
    "## 2. 실적과 재무 품질",
    "",
    "> 원가율 개선이 이익률을 끌어올렸고, 현금흐름이 이익보다 빠르게 늘었다.",
    "",
    "매출은 늘었다.",
  ].join("\n");
  const html = renderMarkdown(markdown);
  assert.match(html, /<h3>2\. 실적과 재무 품질<\/h3><blockquote class="section-summary"><p>원가율 개선이 이익률을 끌어올렸고, 현금흐름이 이익보다 빠르게 늘었다\.<\/p><\/blockquote><p>매출은 늘었다\.<\/p>/);
});

test("bridge: 본문 중간의 일반 blockquote는 section-summary 클래스가 안 붙는다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = ["매출은 늘었다.", "", "> 회사 측 발언 인용.", ""].join("\n");
  const html = renderMarkdown(markdown);
  assert.match(html, /<blockquote><p>회사 측 발언 인용\.<\/p><\/blockquote>/);
  assert.ok(!html.includes("section-summary"));
});

test("bridge: 여러 줄 '>' 는 blockquote 하나로 합쳐진다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = ["## 3. 밸류에이션", "", "> 첫 줄.", "> 둘째 줄."].join("\n");
  const html = renderMarkdown(markdown);
  assert.match(html, /<blockquote class="section-summary"><p>첫 줄\. 둘째 줄\.<\/p><\/blockquote>/);
});

test("react 폴백: 섹션 헤딩(## → h3) 바로 다음 blockquote도 section-summary로 렌더된다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = [
    "## 2. 실적과 재무 품질",
    "",
    "> 원가율 개선이 이익률을 끌어올렸다.",
    "",
    "매출은 늘었다.",
  ].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.match(html, /<h3><span>2\. 실적과 재무 품질<\/span><\/h3><blockquote class="section-summary"><p><span>원가율 개선이 이익률을 끌어올렸다\.<\/span><\/p><\/blockquote>/);
});

test("react 폴백: 헤딩 뒤가 아니면 section-summary 클래스가 안 붙는다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = ["매출은 늘었다.", "", "> 회사 측 발언 인용."].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.match(html, /<blockquote><p><span>회사 측 발언 인용\.<\/span><\/p><\/blockquote>/);
  assert.ok(!html.includes("section-summary"));
});
