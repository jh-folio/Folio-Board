const test = require("node:test");
const assert = require("node:assert/strict");

const {
  indexSeries,
  heatmapColor,
  shouldRenderTrend,
  comparisonSummary,
  normalizePriceSubject,
  periodPoints,
  priceSummary,
  formatPriceValue,
  priceSummaryForPeriod,
  hoverTooltipContent,
  lightweightTimeLabel,
  initialPriceState,
  lightweightRows,
  sectionRole,
  sectionMarket,
  weeklyCaption,
  signedPercent,
  preferredIndexTicker,
  heatmapNodes,
  compactLevelText,
  abbreviateHeatmapLabel,
  heatmapLayoutHeight,
  createRequestGate,
  controlButton,
  exportControlSelector,
  recommendationPlacement,
  sectionHeadingSelector,
  isSectionBoundaryTag,
  fitChartWhenSized,
  insertSectionSlot,
  captureImages,
  replaceWithStaticImages,
  viewAction,
  viewCopy,
  normalizeVisualMarket,
} = require("./briefing-visuals.js");

test("export market metadata is normalized to closed values", () => {
  assert.equal(normalizeVisualMarket("us"), "US");
  assert.equal(normalizeVisualMarket("KR"), "KR");
  assert.equal(normalizeVisualMarket("unexpected"), "BOTH");
});

test("periodPoints uses 5m for 1D and filters daily points for longer periods", () => {
  const subject = {
    intraday: { interval: "5m", points: [{ time: "2026-06-19T15:55:00-04:00", close: 101 }] },
    daily: { interval: "1d", points: [
      { time: "2025-06-19", close: 80 },
      { time: "2026-01-02", close: 90 },
      { time: "2026-06-19", close: 101 },
    ] },
  };
  assert.equal(periodPoints(subject, "1D", "2026-06-19").interval, "5m");
  assert.deepEqual(periodPoints(subject, "YTD", "2026-06-19").points.map((row) => row.time), ["2026-01-02", "2026-06-19"]);
  assert.deepEqual(periodPoints(subject, "1Y", "2026-06-19").points.map((row) => row.time), ["2025-06-19", "2026-01-02", "2026-06-19"]);
});

test("normalizePriceSubject maps v1 points to daily without inventing intraday", () => {
  const normalized = normalizePriceSubject({ ticker: "SPY", points: [{ time: "2026-06-19", close: 100 }] });
  assert.deepEqual(normalized.intraday.points, []);
  assert.equal(normalized.daily.points.length, 1);
});

test("priceSummary reports the selected period close and signed change", () => {
  assert.deepEqual(priceSummary([
    { time: "2026-06-18", open: 99, high: 101, low: 98, close: 100 },
    { time: "2026-06-19", open: 100, high: 106, low: 99, close: 105 },
  ]), {
    close: 105, change: 5, changePct: 5, open: 99, high: 106, low: 98,
  });
});

test("priceSummaryForPeriod uses official daily close change for 1D summaries", () => {
  const subject = {
    intraday: { interval: "5m", points: [
      { time: "2026-06-23T09:30:00-04:00", close: 100 },
      { time: "2026-06-23T15:55:00-04:00", close: 99.5 },
    ] },
    daily: { interval: "1d", points: [
      { time: "2026-06-22", close: 100 },
      { time: "2026-06-23", close: 97.8 },
    ] },
  };

  const summary = priceSummaryForPeriod(subject, "1D", subject.intraday.points);
  assert.equal(summary.close, 97.8);
  assert.equal(Number(summary.changePct.toFixed(2)), -2.20);
});

test("hoverTooltipContent shows explicit date, price, and change percent", () => {
  const subject = {
    intraday: { interval: "5m", points: [
      { time: "2026-06-23T09:30:00-04:00", close: 100 },
      { time: "2026-06-23T15:55:00-04:00", close: 97.8 },
    ] },
    daily: { interval: "1d", points: [
      { time: "2026-06-22", close: 100 },
      { time: "2026-06-23", close: 97.8 },
    ] },
  };

  const html = hoverTooltipContent(subject, "1D", subject.intraday.points[1], { currency: "USD" });
  assert.match(html, /2026-06-23 15:55/);
  assert.match(html, /97\.80/);
  assert.match(html, /-2\.20%/);
});

test("lightweightTimeLabel formats crosshair dates with four-digit year", () => {
  const timestamp = Math.floor(Date.parse("2026-06-23T15:55:00-04:00") / 1000);
  assert.match(lightweightTimeLabel(timestamp), /^2026-/);
  assert.equal(lightweightTimeLabel("2026-06-23"), "2026-06-23");
});

test("initialPriceState focuses the first subject with 1D line defaults", () => {
  assert.deepEqual(initialPriceState({ series: [{ ticker: "^GSPC" }, { ticker: "^IXIC" }] }), {
    selectedTicker: "^GSPC", period: "1D", chartType: "line",
  });
});

test("lightweightRows preserves OHLC for candles and converts intraday time", () => {
  const point = { time: "2026-06-19T15:55:00-04:00", open: 100, high: 102, low: 99, close: 101 };
  const candle = lightweightRows([point], "candle", "5m")[0];
  const line = lightweightRows([point], "line", "5m")[0];
  // 축은 UTC로 그려지므로 거래소 현지 벽시계(16:00)를 그대로 UTC epoch로 넘긴다.
  const expectedCloseTime = Math.floor(Date.parse("2026-06-19T16:00:00Z") / 1000);
  assert.equal(typeof candle.time, "number");
  assert.equal(candle.time, expectedCloseTime);
  assert.deepEqual({ open: candle.open, high: candle.high, low: candle.low, close: candle.close }, { open: 100, high: 102, low: 99, close: 101 });
  assert.equal(line.value, 101);
  assert.equal(line.time, candle.time);
  assert.equal(lightweightTimeLabel(candle.time), "2026-06-19 16:00");
});

test("section helpers recognize market flow and numbered leading-company headings", () => {
  assert.equal(sectionRole("1. 미국장 시장 흐름"), "market_flow");
  assert.deepEqual(sectionRole("3. 미국장을 주도한 기업 ① — NVIDIA"), { role: "leading_company", ordinal: 1 });
  assert.deepEqual(sectionRole("4. 한국장을 주도한 기업 ② — SK하이닉스"), { role: "leading_company", ordinal: 2 });
  assert.equal(sectionRole("참고자료"), null);
  assert.equal(sectionMarket("1. 미국장 시장 흐름", "both"), "US");
  assert.equal(sectionMarket("1. 시장 흐름", "kr"), "KR");
});

test("preferredIndexTicker follows prose mention and otherwise uses market default", () => {
  const us = [{ ticker: "^GSPC", label: "S&P 500" }, { ticker: "^IXIC", label: "Nasdaq Composite" }, { ticker: "^DJI", label: "Dow Jones" }];
  assert.equal(preferredIndexTicker("Nasdaq 지수가 하락했다.", us, "US"), "^IXIC");
  assert.equal(preferredIndexTicker("대형주가 강세였다.", us, "US"), "^GSPC");
});

test("heatmapNodes groups stocks by sector and industry using market cap", () => {
  const nodes = heatmapNodes([
    { ticker: "NVDA", sector: "Technology", industry: "Semiconductors", marketCap: 100, changePct: 2 },
    { ticker: "MSFT", sector: "Technology", industry: "Software", marketCap: 90, changePct: -1 },
  ]);
  assert.deepEqual(nodes.ids.slice(0, 3), ["sector:Technology", "industry:Technology:Semiconductors", "ticker:NVDA"]);
  assert.equal(nodes.values[nodes.ids.indexOf("ticker:NVDA")], 100);
  assert.equal(nodes.parents[nodes.ids.indexOf("ticker:NVDA")], "industry:Technology:Semiconductors");
  // text embeds the per-tile font size via inline span markup (Plotly array textfont breaks treemap layout);
  // ticker and change are separate spans/lines so they don't overlap on large tiles.
  const nvdaText = nodes.text[nodes.ids.indexOf("ticker:NVDA")];
  assert.match(nvdaText, /^<span style="font-size:\d+px"><b>NVDA<\/b><\/span><br><span style="font-size:\d+px">\+2\.00%<\/span>$/);
});

test("heatmapNodes skips duplicate industry layer when sector and industry are identical", () => {
  const nodes = heatmapNodes([
    { ticker: "005930", label: "삼성전자", sector: "전기전자", industry: "전기전자", marketCap: 100, changePct: 1 },
    { ticker: "000660", label: "SK하이닉스", sector: "전기전자", industry: "전기전자", marketCap: 80, changePct: -1 },
  ]);

  assert.ok(!nodes.ids.some((id) => id.startsWith("industry:전기전자:전기전자")));
  assert.equal(nodes.parents[nodes.ids.indexOf("ticker:005930")], "sector:전기전자");
  assert.equal(nodes.parents[nodes.ids.indexOf("ticker:000660")], "sector:전기전자");
});

test("heatmap hides labels that would render below the minimum readable size", () => {
  // one dominant cap + many tiny caps: the tiny tiles fall under the px threshold → blank text
  const rows = [{ ticker: "MEGA", sector: "Technology", industry: "Semiconductors", marketCap: 100000, changePct: 1 }];
  for (let i = 0; i < 30; i += 1) rows.push({ ticker: `T${i}`, sector: "Technology", industry: "Software", marketCap: 1, changePct: -1 });
  const nodes = heatmapNodes(rows);
  const tinyText = nodes.text[nodes.ids.indexOf("ticker:T0")];
  assert.equal(tinyText, "");
  assert.notEqual(nodes.text[nodes.ids.indexOf("ticker:MEGA")], "");
});

test("heatmap font scales ticker size by box area so big caps read larger", () => {
  const nodes = heatmapNodes([
    { ticker: "BIG", sector: "Technology", industry: "Semiconductors", marketCap: 400, changePct: 1 },
    { ticker: "SMALL", sector: "Technology", industry: "Software", marketCap: 4, changePct: -1 },
  ]);
  const big = nodes.textsizes[nodes.ids.indexOf("ticker:BIG")];
  const small = nodes.textsizes[nodes.ids.indexOf("ticker:SMALL")];
  // largest cap gets the biggest font; the small cap still gets a visible, smaller font
  assert.ok(big > small, `expected ${big} > ${small}`);
  assert.ok(small >= 7 && small < big);
  assert.equal(nodes.textsizes.length, nodes.ids.length);
});

test("heatmap group labels stay compact so stock tiles stay visually dominant", () => {
  const nodes = heatmapNodes([
    { ticker: "MEGA", sector: "Technology", industry: "Semiconductors", marketCap: 1000, changePct: 1 },
  ]);
  const sectorSize = nodes.textsizes[nodes.ids.indexOf("sector:Technology")];
  const industrySize = nodes.textsizes[nodes.ids.indexOf("industry:Technology:Semiconductors")];
  const tickerSize = nodes.textsizes[nodes.ids.indexOf("ticker:MEGA")];

  assert.ok(sectorSize <= 8, `sector label should be compact, got ${sectorSize}`);
  assert.ok(industrySize <= 6, `industry label should be compact, got ${industrySize}`);
  assert.match(nodes.text[nodes.ids.indexOf("industry:Technology:Semiconductors")], /font-size:6px/);
  assert.ok(tickerSize > sectorSize, `ticker ${tickerSize} should dominate sector ${sectorSize}`);
});

test("heatmap displays the representative ticker for collapsed share-class rows", () => {
  const nodes = heatmapNodes([
    {
      ticker: "GOOGL",
      label: "Alphabet Inc.",
      classTickers: ["GOOGL", "GOOG"],
      sector: "Communication Services",
      industry: "Interactive Media & Services",
      marketCap: 1000,
      changePct: 1,
    },
  ]);
  const tickerIndex = nodes.ids.indexOf("ticker:GOOGL");

  assert.equal(nodes.labels[tickerIndex], "GOOGL");
  assert.match(nodes.text[tickerIndex], /GOOGL/);
});

test("price values omit currency for indices and use compact symbols for stocks", () => {
  assert.equal(formatPriceValue(51559, { role: "market_summary", currency: "USD" }, { ticker: "^DJI" }), "51,559");
  assert.equal(formatPriceValue(210.33, { role: "leading_company", currency: "USD" }, { ticker: "NVDA" }), "$210.33");
  assert.equal(formatPriceValue(312000, { role: "leading_company", currency: "KRW" }, { ticker: "005930.KS" }), "₩312,000");
});

test("heatmap labels abbreviate long market groups without changing full hover names", () => {
  assert.equal(abbreviateHeatmapLabel("Consumer Discretionary"), "Consumer Disc.");
  assert.equal(abbreviateHeatmapLabel("Communication Services"), "Comm. Services");
  assert.equal(abbreviateHeatmapLabel("Computer Software: Programming Data Processing"), "Software & Data");
  const nodes = heatmapNodes([
    { ticker: "AMZN", sector: "Consumer Discretionary", industry: "Catalog/Specialty Distribution", marketCap: 100, changePct: 1 },
  ]);
  assert.equal(nodes.labels[0], "Consumer Disc.");
  assert.equal(nodes.labels[1], "Specialty Retail");
  assert.equal(nodes.customdata[0][0], "Consumer Discretionary");
});

test("heatmap layout fills the responsive stage instead of leaving unused space", () => {
  assert.equal(heatmapLayoutHeight({ clientHeight: 720 }), 720);
  assert.equal(heatmapLayoutHeight({ clientHeight: 0 }), 620);
  assert.equal(heatmapLayoutHeight({ clientHeight: 360 }), 520);
});

test("request gate accepts only the newest render request", () => {
  const gate = createRequestGate();
  const first = gate.next();
  const second = gate.next();
  assert.equal(gate.isCurrent(first), false);
  assert.equal(gate.isCurrent(second), true);
});

test("controlButton marks selected options with aria-pressed", () => {
  assert.equal(controlButton("1D", true, "period"), '<button type="button" data-period="1D" aria-pressed="true">1D</button>');
  assert.equal(controlButton("1Y", false, "period"), '<button type="button" data-period="1Y" aria-pressed="false">1Y</button>');
});

test("export cleanup selector covers inline chart controls", () => {
  const selector = exportControlSelector();
  assert.match(selector, /briefing-inline-view-controls/);
  assert.match(selector, /briefing-price-controls/);
});

test("captureImages returns rendered briefing chart PNGs with market metadata", async () => {
  const card = {
    dataset: { visualExportId: "leader-googl", market: "US" },
    querySelector: (selector) => selector === ".briefing-visual-header h3"
      ? { textContent: "Alphabet" }
      : null,
    querySelectorAll: (selector) => selector === "canvas"
      ? [{ width: 640, height: 320, toDataURL: () => "data:image/png;base64,chart" }]
      : [],
  };
  const container = {
    querySelectorAll: (selector) => selector === "[data-visual-export-id]" ? [card] : [],
  };

  assert.deepEqual(await captureImages(container), [{
    id: "leader-googl",
    market: "US",
    title: "Alphabet",
    dataUrl: "data:image/png;base64,chart",
  }]);
});

test("replaceWithStaticImages keeps briefing visual cards in copied HTML", async () => {
  let removed = false;
  let stageHtml = "";
  let controlRemoved = false;
  const cloneCard = {
    dataset: { visualExportId: "leader-googl", market: "US" },
    remove: () => { removed = true; },
    querySelector: (selector) => selector === ".briefing-visual-stage"
      ? { set innerHTML(value) { stageHtml = value; } }
      : null,
  };
  const originalCard = {
    querySelectorAll: (selector) => selector === "canvas"
      ? [{ width: 640, height: 320, toDataURL: () => "data:image/png;base64,chart" }]
      : [],
  };
  const clone = {
    querySelectorAll: (selector) => {
      if (selector === "[data-visual-export-id]") return [cloneCard];
      if (selector === exportControlSelector()) return [{ remove: () => { controlRemoved = true; } }];
      return [];
    },
  };
  const original = {
    querySelectorAll: (selector) => selector === "[data-visual-export-id]" ? [originalCard] : [],
  };

  await replaceWithStaticImages(clone, original);

  assert.equal(removed, false);
  assert.equal(controlRemoved, true);
  assert.match(stageHtml, /<img /);
  assert.match(stageHtml, /data:image\/png;base64,chart/);
});

test("legacy recommendations derive stable inline placement", () => {
  const recommendations = [
    { snapshotId: "indices", market: "US", role: "market_summary", variant: "multi_series_line" },
    { snapshotId: "leader-a", market: "US", role: "leading_company", variant: "single_series_area" },
    { snapshotId: "leader-b", market: "US", role: "leading_company", variant: "single_series_area" },
    { snapshotId: "heatmap", market: "US", role: "market_summary", variant: "treemap_heatmap" },
  ];
  assert.deepEqual(recommendationPlacement(recommendations[0], recommendations), { market: "US", sectionRole: "market_flow", order: 1 });
  assert.deepEqual(recommendationPlacement(recommendations[2], recommendations), { market: "US", sectionRole: "leading_company", ordinal: 2, order: 1 });
  assert.deepEqual(recommendationPlacement(recommendations[3], recommendations), { market: "US", sectionRole: "market_flow", order: 2 });
});

test("inline slots follow Folio Markdown heading levels", () => {
  assert.equal(sectionHeadingSelector(), "h3");
  assert.equal(isSectionBoundaryTag("H3"), true);
  assert.equal(isSectionBoundaryTag("H2"), true);
  assert.equal(isSectionBoundaryTag("P"), false);
});

test("chart fitting waits until the responsive stage has a real width", () => {
  const queue = [];
  const stage = { clientWidth: 0 };
  let fitCount = 0;
  const chart = { resize: () => {}, timeScale: () => ({ fitContent: () => { fitCount += 1; } }) };
  class FakeResizeObserver {
    constructor(callback) { this.callback = callback; }
    observe() {}
    disconnect() {}
  }

  fitChartWhenSized(chart, stage, {
    schedule: (callback) => queue.push(callback),
    ResizeObserverClass: FakeResizeObserver,
  });
  assert.equal(fitCount, 0);
  queue.shift()();
  stage.clientWidth = 1200;
  queue.shift()();
  assert.equal(fitCount, 1);
});

test("indexSeries rebases valid closes to 100 while retaining actual values", () => {
  const points = indexSeries([
    { time: "2026-06-17", close: 200 },
    { time: "2026-06-18", close: 210 },
  ]);
  assert.deepEqual(points, [
    { time: "2026-06-17", value: 100, actual: 200 },
    { time: "2026-06-18", value: 105, actual: 210 },
  ]);
});

test("heatmapColor uses explicit signed buckets", () => {
  assert.equal(heatmapColor(3), "#168a56");
  assert.equal(heatmapColor(0.2), "#34785f");
  assert.equal(heatmapColor(0), "#667085");
  assert.equal(heatmapColor(-0.2), "#b65b67");
  assert.equal(heatmapColor(-3), "#a92d42");
});

test("inline visuals are inserted immediately after their section heading", () => {
  let call = null;
  const heading = { insertAdjacentElement: (position, element) => { call = { position, element }; } };
  const slot = { className: "briefing-inline-visual-slot" };
  insertSectionSlot(heading, slot);
  assert.deepEqual(call, { position: "afterend", element: slot });
});

test("trend rendering requires at least two valid v1 or v2 price points", () => {
  assert.equal(shouldRenderTrend({ series: [{ points: [{ close: 1 }, { close: 2 }] }] }), true);
  assert.equal(shouldRenderTrend({ series: [{ intraday: { points: [{ close: 1 }] }, daily: { points: [] } }] }), false);
});

test("viewCopy distinguishes immutable snapshot from latest REST view", () => {
  assert.deepEqual(viewCopy("snapshot"), {
    heading: "생성 당시 시장",
    description: "브리핑 생성 시 저장된 종가 스냅샷입니다.",
  });
  assert.deepEqual(viewCopy("current"), {
    heading: "현재 시장",
    description: "최신 REST 일봉이며 실시간 체결가가 아닙니다.",
  });
});

test("comparisonSummary reports price and sector rank changes", () => {
  const summary = comparisonSummary({
    priceChanges: [{ ticker: "NVDA", changePct: 4.25 }],
    sectorRankChanges: [{ sector: "Technology", generatedRank: 3, currentRank: 1, rankChange: 2 }],
  });
  assert.deepEqual(summary, [
    { kind: "price", label: "NVDA", value: "+4.25%" },
    { kind: "rank", label: "Technology", value: "3위 → 1위 (▲2)" },
  ]);
});

test("snapshot selection cancels a pending current request", () => {
  assert.equal(viewAction("snapshot", "select_snapshot", true), "render_snapshot");
  assert.equal(viewAction("snapshot", "select_snapshot", false), "noop");
  assert.equal(viewAction("current", "select_snapshot", false), "render_snapshot");
});

// ---------------------------------------------------------------------------
// 층에 들어가면 글자 크기도 그 층 기준이어야 한다.
// 전체 지도 기준으로 한 번만 계산하면 섹터에 들어간 산업들이 화면을 가득
// 채우는데도 6px 이름표를 그대로 들고 온다(모바일에서 읽을 수 없었다).
// ---------------------------------------------------------------------------
test("drilling into a sector re-sizes its industries for the visible layer", () => {
  const nodes = heatmapNodes([
    { ticker: "NVDA", sector: "Tech", industry: "Semis", marketCap: 3000, changePct: 2.5 },
    { ticker: "MU", sector: "Tech", industry: "Semis", marketCap: 300, changePct: 0.5 },
    { ticker: "MSFT", sector: "Tech", industry: "Software", marketCap: 2500, changePct: 1.0 },
    { ticker: "JPM", sector: "Fin", industry: "Banks", marketCap: 700, changePct: -0.4 },
  ], true);
  const sectorId = nodes.ids.find((id) => id === "sector:Tech");
  const text = compactLevelText(nodes, sectorId);
  for (const [index, id] of nodes.ids.entries()) {
    if (nodes.parents[index] !== sectorId) continue;
    const match = String(text[index]).match(/font-size:(\d+)px/);
    assert.ok(match, `${id} 라벨에 크기가 없다`);
    assert.ok(Number(match[1]) >= 12, `${id} 라벨이 ${match[1]}px — 층 기준으로 커져야 한다`);
  }
});

test("ticker tiles keep their change line after the level resize", () => {
  const nodes = heatmapNodes([
    { ticker: "NVDA", sector: "Tech", industry: "Semis", marketCap: 3000, changePct: 2.93 },
    { ticker: "MU", sector: "Tech", industry: "Semis", marketCap: 300, changePct: -1.2 },
  ], true);
  const industryId = nodes.ids.find((id) => id.startsWith("industry:"));
  const text = compactLevelText(nodes, industryId);
  const nvda = nodes.ids.indexOf("ticker:NVDA");
  assert.match(String(text[nvda]), /NVDA/);
  assert.match(String(text[nvda]), /\+2\.93%/);
});

test("the root level resize keeps every sector label readable", () => {
  const nodes = heatmapNodes([
    { ticker: "A", sector: "Big", industry: "X", marketCap: 5000, changePct: 1 },
    { ticker: "B", sector: "Small", industry: "Y", marketCap: 50, changePct: -1 },
  ], true);
  const text = compactLevelText(nodes, "");
  for (const [index, id] of nodes.ids.entries()) {
    if (nodes.parents[index] !== "") continue;
    const match = String(text[index]).match(/font-size:(\d+)px/);
    assert.ok(Number(match[1]) >= 12, `${id}가 ${match[1]}px`);
  }
});

test("네 시장 모두 섹션 슬롯을 얻는다", () => {
  // 유럽·일본이 빠져 있던 시절 그 두 시장 브리핑은 슬롯이 하나도 만들어지지 않아,
  // 저장된 스냅샷 네 장이 화면에 아무것도 그리지 못했다(실측 2026-08-12~14, 6건).
  assert.equal(sectionMarket("1. 유럽장 시장 흐름", "europe"), "EUROPE");
  assert.equal(sectionMarket("1. 일본장 시장 흐름", "jp"), "JP");
  assert.equal(sectionMarket("1. 시장 흐름", "europe"), "EUROPE");
  assert.equal(sectionMarket("1. 시장 흐름", "jp"), "JP");
  assert.equal(sectionMarket("1. 시장 흐름", "both"), "");
  // 카드 태그도 같이 안다. `BOTH`로 접으면 내보내기·필터가 통합 카드로 오인한다.
  assert.equal(normalizeVisualMarket("EUROPE"), "EUROPE");
  assert.equal(normalizeVisualMarket("JP"), "JP");
  assert.equal(normalizeVisualMarket("both"), "BOTH");
});

test("주간 헤딩은 주간 슬롯을, 일간 헤딩은 일간 슬롯을 만든다", () => {
  assert.equal(sectionRole("1. 지난주 미국장 흐름"), "weekly_flow");
  assert.equal(sectionRole("2. 지난주 미국장을 움직인 핵심 변수"), "weekly_story_share");
  // 일간 §2도 "핵심 변수"다. `지난주`가 없으면 일간에 빈 슬롯이 생긴다.
  assert.equal(sectionRole("2. 미국장을 움직인 핵심 변수"), null);
  assert.equal(sectionRole("1. 미국장 시장 흐름"), "market_flow");
  // 주간 §3은 기업 ①②가 없다 — 주간에는 종목별 세션 차트를 만들지 않는다.
  assert.equal(sectionRole("3. 지난주 한국장을 주도한 기업·업종"), null);
});

test("주간 캡션은 창을, 퍼센트는 결측을 정직하게 말한다", () => {
  assert.equal(weeklyCaption({ weekLabel: "08.10~08.16" }, "본문"), "08.10~08.16 · 본문");
  assert.equal(
    weeklyCaption({ window: { weekStart: "2026-08-10", weekEnd: "2026-08-16" } }, "본문"),
    "2026-08-10~2026-08-16 · 본문",
  );
  assert.equal(signedPercent(1.234), "+1.23%");
  assert.equal(signedPercent(-0.5), "-0.50%");
  assert.equal(signedPercent(0), "0.00%");
  // `Number(null)`이 0이라 결측이 "0.00%"가 되면 "안 움직였다"는 사실로 둔갑한다.
  assert.equal(signedPercent(null), "—");
  assert.equal(signedPercent(undefined), "—");
});
