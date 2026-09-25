import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";

const webRoot = fileURLToPath(new URL("..", import.meta.url));

const summary = {
  observedAt: "2026-07-27T12:00:00Z",
  counts: {
    total: 2,
    portfolio: 1,
    watchlist: 0,
    both: 1,
    positive: 0,
    watch: 2,
    negative: 0,
    neutral: 0,
    unknown: 0,
  },
  watchContexts: [
    {
      ticker: "NVDA",
      source: "both",
      stance: "watch",
      observedAt: "2026-07-27T12:00:00Z",
      reasonCodes: [],
      marketDrivers: [{ stateId: "ai-capex", label: "AI CAPEX", momentum: "stable" }],
      latestThesisVerdict: "maintained",
      dueCheckpoints: [{ id: "cp-nvda", label: "PRIVATE-CHECKPOINT-CANARY", dueAt: "2026-07-27T00:00:00Z" }],
      linkedReports: [],
      collections: [{ id: "ai-watch", name: "AI watch", revision: 2, health: "active", matchSources: ["saved_filter"] }],
    },
    {
      ticker: "MSFT",
      source: "portfolio",
      stance: "watch",
      observedAt: "2026-07-27T12:00:00Z",
      reasonCodes: [],
      marketDrivers: [{ stateId: "cloud", label: "Cloud demand", momentum: "stable" }],
      latestThesisVerdict: "unknown",
      dueCheckpoints: [],
      linkedReports: [],
      collections: [],
    },
  ],
};

test("card renders bounded personal context and collection filtering without private values", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const { InvestmentContextCardView } = await vite.ssrLoadModule("/src/app/InvestmentContextCard.tsx");

  const home = renderToStaticMarkup(React.createElement(InvestmentContextCardView, { mode: "home", summary }));
  assert.match(home, /data-layer="hypothesis"/);
  assert.match(home, /NVDA/);
  assert.match(home, /MSFT/);
  assert.match(home, /AI CAPEX/);
  assert.match(home, /확인 예정 1/);
  assert.doesNotMatch(home, /quantity|costBasis|averagePrice|portfolioTotal|noteBody/);

  const collection = renderToStaticMarkup(React.createElement(InvestmentContextCardView, {
    mode: "collection",
    summary,
    collectionId: "ai-watch",
  }));
  assert.match(collection, /NVDA/);
  assert.doesNotMatch(collection, /MSFT/);
});

test("the card takes no space until there is context to show", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const { InvestmentContextCardView } = await vite.ssrLoadModule("/src/app/InvestmentContextCard.tsx");
  const empty = { ...summary, counts: { ...summary.counts, total: 0 }, watchContexts: [] };

  // 홈은 이 카드가 상시 떠 있기 가장 쉬운 자리다. 연결이 없으면 아무것도 그리지 않아야
  // 아직 쓰지 않은 기능을 계속 광고하지 않는다.
  for (const mode of ["home", "market-memory", "deep-research"]) {
    assert.equal(
      renderToStaticMarkup(React.createElement(InvestmentContextCardView, { mode, summary: empty, dismissible: true, onDismiss: () => {} })),
      "",
      `${mode} should render nothing without context`,
    );
  }
  // 아직 불러오지 못한 상태도 마찬가지다.
  assert.equal(
    renderToStaticMarkup(React.createElement(InvestmentContextCardView, { mode: "home", summary: null })),
    "",
  );
});

test("dismissing the card is remembered across mounts", async (t) => {
  const source = await readFile(new URL("../src/app/InvestmentContextCard.tsx", import.meta.url), "utf8");
  // state로만 두면 화면을 옮길 때마다 닫은 카드가 되살아난다.
  assert.match(source, /folio\.investmentContext\.dismissed\.v1/);
  assert.match(source, /localStorage\.getItem\(CONTEXT_DISMISS_KEY\)/);
  assert.match(source, /localStorage\.setItem\(CONTEXT_DISMISS_KEY/);
});

test("controlled Agent reply renders headings and bullets without HTML injection", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const { InvestmentContextCardView } = await vite.ssrLoadModule("/src/app/InvestmentContextCard.tsx");
  const html = renderToStaticMarkup(React.createElement(InvestmentContextCardView, {
    mode: "home",
    summary,
    explanation: {
      ticker: "NVDA",
      reply: "### 불확실성\n- 수요 지속성은 미확인\n<script>PRIVATE_CANARY</script>",
    },
  }));
  assert.match(html, /<h3>불확실성<\/h3>/);
  assert.match(html, /class="is-bullet">수요 지속성은 미확인<\/p>/);
  assert.doesNotMatch(html, /<script>PRIVATE_CANARY<\/script>/);
  assert.match(html, /&lt;script&gt;PRIVATE_CANARY&lt;\/script&gt;/);
});

test("the market-memory strip is one quiet line that links each ticker to where it lives", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const { InvestmentContextStripView } = await vite.ssrLoadModule("/src/app/InvestmentContextCard.tsx");
  const turning = {
    ...summary,
    watchContexts: summary.watchContexts.map((context, index) => ({
      ...context,
      marketDrivers: index === 0 ? [{ stateId: "ai-capex", label: "AI CAPEX", momentum: "turning" }] : context.marketDrivers,
    })),
  };

  const html = renderToStaticMarkup(React.createElement(InvestmentContextStripView, { summary: turning, onExplain: () => {} }));
  assert.match(html, /data-qa="investment-context-market-memory"/);
  assert.match(html, /data-layer="hypothesis"/);
  assert.match(html, /근거 아님/);
  assert.match(html, /AI CAPEX\(전환\)/);
  // NVDA는 워치리스트에도 있고(both), MSFT는 포트폴리오에만 있다.
  assert.match(html, /href="#\/watchlist"[^>]*>워치리스트에서 보기/);
  assert.match(html, /href="#\/portfolio"[^>]*>포트폴리오에서 보기/);
  assert.doesNotMatch(html, /href="#\/market-memory"/);
  assert.doesNotMatch(visibleText(html), /Canonical|evidence/);
  assert.doesNotMatch(html, /quantity|costBasis|averagePrice|portfolioTotal|noteBody|PRIVATE-CHECKPOINT-CANARY/);

  const empty = { ...summary, watchContexts: [] };
  assert.equal(renderToStaticMarkup(React.createElement(InvestmentContextStripView, { summary: empty })), "");
  assert.equal(renderToStaticMarkup(React.createElement(InvestmentContextStripView, { summary: null })), "");
});

test("owned tickers are keyed by narrative state ID, never by label", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const { ownedTickersByState } = await vite.ssrLoadModule("/src/app/InvestmentContextCard.tsx");
  const shared = {
    ...summary,
    watchContexts: summary.watchContexts.map((context) => ({
      ...context,
      marketDrivers: [{ stateId: "ai-capex", label: "Same label", momentum: "turning" }],
    })),
  };
  assert.deepEqual(ownedTickersByState(shared), { "ai-capex": ["NVDA", "MSFT"] });
  assert.deepEqual(ownedTickersByState(null), {});
});

test("the home card hides an empty due count and keeps boundary copy in plain words", async (t) => {
  const vite = await createServer({ configFile: false, root: webRoot, server: { middlewareMode: true, hmr: false }, appType: "custom" });
  t.after(() => vite.close());
  const { InvestmentContextCardView } = await vite.ssrLoadModule("/src/app/InvestmentContextCard.tsx");
  const noDue = { ...summary, watchContexts: summary.watchContexts.map((context) => ({ ...context, dueCheckpoints: [] })) };
  const html = renderToStaticMarkup(React.createElement(InvestmentContextCardView, { mode: "home", summary: noDue }));
  assert.doesNotMatch(html, /확인 예정 0/);
  assert.match(html, /보고서 근거로는 쓰지 않아요/);
  assert.doesNotMatch(visibleText(html), /Canonical|evidence/);
  assert.match(html, /class="btn btn--sm btn--text" href="#\/portfolio"/);
});

test("dismissing on Home does not hide the card on screens without a close button", async () => {
  const source = await readFile(new URL("../src/app/InvestmentContextCard.tsx", import.meta.url), "utf8");
  assert.match(source, /if \(dismissed && props\.dismissible\) return null;/);
});

function visibleText(html) {
  return html.replace(/<[^>]+>/g, " ");
}
