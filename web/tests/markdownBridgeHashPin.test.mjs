import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

test("Briefing and Company canonical Markdown bridge remains byte-for-byte pinned", async () => {
  const source = await readFile(new URL("../../public/app.js", import.meta.url), "utf8");
  const sandbox = { console, URL, Intl, Date, setTimeout, clearTimeout, addEventListener() {}, removeEventListener() {}, dispatchEvent() {}, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };
  sandbox.window = sandbox;
  sandbox.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], body: { classList: { add() {}, remove() {}, toggle() {} } } };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  const markdown = "# Canonical Title\n\n## Decision\n\n> 요약 문장.\n\nPlain **bold** with [safe link](https://example.com/a_(b)).\n\n- first\n  - nested\n\n| Metric | Value | Note |\n|---|---:|---|\n| Revenue | 42 | 확인되지 않음 |\n| Margin | 62.7배 | -30.0% |\n\n### Unsafe canary\n\n<script id=\"todo13-canary\">globalThis.pwned=true</script>\n\n[bad](javascript:alert(1))\n\n<img src=x onerror=\"globalThis.pwned=true\">";
  const split = sandbox.FolioBridge.splitReportTitle(markdown, "fallback");
  const html = sandbox.FolioBridge.renderMarkdown(split.body);
  // 헤딩 바로 다음 blockquote(섹션 요약)와 셀 단위 숫자 판정("확인되지 않음"은
  // 숫자로 안 잡고, "62.7배"·"-30.0%"는 잡는다)을 같은 canary에 함께 고정한다.
  const expected = "<h3>Decision</h3><blockquote class=\"section-summary\"><p>요약 문장.</p></blockquote><p>Plain <strong>bold</strong> with <a href=\"https://example.com/a_(b\" target=\"_blank\" rel=\"noreferrer\">safe link</a>).</p><ul><li class=\"depth-0\">first</li><li class=\"depth-1\">nested</li></ul><div class=\"table-wrap\"><table><thead><tr><th>Metric</th><th>Value</th><th>Note</th></tr></thead><tbody><tr><td>Revenue</td><td class=\"num\">42</td><td>확인되지 않음</td></tr><tr><td>Margin</td><td class=\"num\">62.7배</td><td class=\"num\">-30.0%</td></tr></tbody></table></div><h4>Unsafe canary</h4><p>&lt;script id=&quot;todo13-canary&quot;&gt;globalThis.pwned=true&lt;/script&gt;</p><p>[bad](javascript:alert(1))</p><p>&lt;img src=x onerror=&quot;globalThis.pwned=true&quot;&gt;</p>";
  assert.equal(html, expected);
  assert.equal(createHash("sha256").update(html).digest("hex"), "63ac63e87ce45dddfe4fef4649e20e97959f4d86a06730b17c855048348912c8");
  const briefing = await readFile(new URL("../src/app/BriefingRoute.tsx", import.meta.url), "utf8");
  const company = await readFile(new URL("../src/app/reportReader/CompanyAnalysisBody.tsx", import.meta.url), "utf8");
  assert.match(briefing, /<ReportBody/);
  assert.match(company, /<ReportBody/);
});
