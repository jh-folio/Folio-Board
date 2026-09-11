import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// 두 렌더러(레거시 bridge와 React 폴백)가 같은 표 규칙을 지키는지 함께 본다 — 셀 단위
// 판정이라 같은 표 안에서도 섞인다. 리스크·체크포인트 표는 라벨 열 말고도 전부 산문이라
// "첫 열만 라벨" 같은 열 위치 규칙이 안 통해서 셀 내용으로 본다.

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

test("bridge: 통화·배수·퍼센트 값은 num 클래스를 받는다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = [
    "| 항목 | 2025 | 2024 |",
    "|---|---:|---:|",
    "| 매출 | $8.25B | $7.43B |",
    "| PER | 62.7배 | 39.9배 |",
    "| 현재가 대비 | -30.0% | +0.0% |",
  ].join("\n");
  const html = renderMarkdown(markdown);
  assert.match(html, /<td class="num">\$8\.25B<\/td>/);
  assert.match(html, /<td class="num">62\.7배<\/td>/);
  assert.match(html, /<td class="num">-30\.0%<\/td>/);
});

test("react 폴백: 통화·배수·퍼센트 값은 num 클래스를 받는다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = [
    "| 항목 | 2025 | 2024 |",
    "|---|---:|---:|",
    "| 매출 | $8.25B | $7.43B |",
    "| PER | 62.7배 | 39.9배 |",
    "| 현재가 대비 | -30.0% | +0.0% |",
  ].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.match(html, /<td class="num"><span>\$8\.25B<\/span><\/td>/);
  assert.match(html, /<td class="num"><span>62\.7배<\/span><\/td>/);
  assert.match(html, /<td class="num"><span>-30\.0%<\/span><\/td>/);
});

test("bridge: 라벨과 산문 셀은 num 클래스를 받지 않는다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = [
    "| 위험 | 영향 경로 | 근거 |",
    "|---|---|---|",
    "| 관세·통상 정책 | 원가·매출원가율 | 10-K/10-Q 전망 문단 |",
    "| 매출총이익 | 확인되지 않음 | 확인되지 않음 |",
  ].join("\n");
  const html = renderMarkdown(markdown);
  assert.ok(!html.includes('class="num"'));
  assert.match(html, /<td>확인되지 않음<\/td>/);
});

test("react 폴백: 라벨과 산문 셀은 num 클래스를 받지 않는다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = [
    "| 위험 | 영향 경로 | 근거 |",
    "|---|---|---|",
    "| 관세·통상 정책 | 원가·매출원가율 | 10-K/10-Q 전망 문단 |",
    "| 매출총이익 | 확인되지 않음 | 확인되지 않음 |",
  ].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.ok(!html.includes('class="num"'));
  assert.match(html, /<td><span>확인되지 않음<\/span><\/td>/);
});

test("bridge: 연도 헤더도 숫자로 잡혀 데이터 열과 정렬이 맞는다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = ["| 항목 | 2025 | 2024 |", "|---|---:|---:|", "| 매출 | $8.25B | $7.43B |"].join("\n");
  const html = renderMarkdown(markdown);
  assert.match(html, /<th class="num">2025<\/th>/);
  assert.match(html, /<th>항목<\/th>/);
});

test("react 폴백: 연도 헤더도 숫자로 잡혀 데이터 열과 정렬이 맞는다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = ["| 항목 | 2025 | 2024 |", "|---|---:|---:|", "| 매출 | $8.25B | $7.43B |"].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.match(html, /<th class="num"><span>2025<\/span><\/th>/);
  assert.match(html, /<th><span>항목<\/span><\/th>/);
});

test("react 폴백: 표는 문단으로 뭉개지지 않고 table-wrap/table 구조로 렌더된다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = ["| 항목 | 값 |", "|---|---|", "| 매출 | $8.25B |"].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.match(html, /<div class="table-wrap"><table><thead><tr>/);
  assert.match(html, /<\/thead><tbody><tr>/);
  assert.ok(!html.includes("| 항목 | 값 |"));
});

test("bridge: 날짜·일정 표는 캘린더 표로 렌더되고 상태값이 한글로 바뀐다", async () => {
  const renderMarkdown = await loadBridgeRenderMarkdown();
  const markdown = ["| 날짜 | 일정 | 상태 |", "|---|---|---|", "| 2026-09-12 | FOMC 성명 | confirmed |"].join("\n");
  const html = renderMarkdown(markdown);
  assert.match(html, /<div class="table-wrap briefing-calendar-table">/);
  assert.match(html, /<td>확정<\/td>/);
});

test("react 폴백: 날짜·일정 표는 캘린더 표로 렌더되고 상태값이 한글로 바뀐다", async (t) => {
  const MarkdownRenderer = await loadReactMarkdownRenderer(t);
  const markdown = ["| 날짜 | 일정 | 상태 |", "|---|---|---|", "| 2026-09-12 | FOMC 성명 | confirmed |"].join("\n");
  const html = renderToStaticMarkup(React.createElement(MarkdownRenderer, { markdown }));
  assert.match(html, /<div class="table-wrap briefing-calendar-table">/);
  assert.match(html, /<td><span>확정<\/span><\/td>/);
});
