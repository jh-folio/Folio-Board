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
  heatmapLabelMarkup,
  heatmapTickerLabel,
  heatmapGroupName,
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
  // 라벨 글자는 여기서 정하지 않는다. 그린 뒤 타일을 재서 얹으므로 노드는
  // 이름과 등락률만 들고 있다.
  assert.equal(nodes.labels[nodes.ids.indexOf("ticker:NVDA")], "NVDA");
  assert.equal(nodes.changes[nodes.ids.indexOf("ticker:NVDA")], 2);
  assert.equal(nodes.text, undefined);
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
// 라벨은 그린 뒤 타일을 재서 정한다.
// 예전에는 시가총액 비율(7 + 21·√(cap/max))로만 크기를 정해 타일 픽셀을 몰랐다.
// 넘치는 라벨은 Plotly가 통째로 축소해 1~5px 얼룩으로 남았고, 실측 US 데스크톱
// 에서 그려진 라벨 424개 중 276개가 6px 미만이었다.
// 아래 측정 함수는 결정적인 stub이다(어느 글꼴이 깔려 있든 같은 답이 나온다).
// ---------------------------------------------------------------------------
const measureStub = (text, size) => String(text).length * size * 0.6;
const labelSize = (markup) => Number(String(markup).match(/font-size:(\d+)px/)[1]);
const lineSizes = (markup) => [...String(markup).matchAll(/font-size:(\d+)px/g)].map((m) => Number(m[1]));

// Plotly의 줄 간격은 span 크기가 아니라 트레이스 기본 글꼴(13px) 기준 `dy="1.3em"`으로
// 고정이다. 줄이 둘 이상이면 그 16.9px 안에 들어와야 겹치지 않는다.
const LINE_STEP = 13 * 1.3;
const assertNoOverlap = (markup) => {
  const sizes = lineSizes(markup);
  const lines = String(markup).split(/<br>/).length;
  const perLine = lines > 1 && sizes.length === 1 ? [sizes[0], sizes[0]] : sizes;
  for (let i = 0; i < perLine.length - 1; i += 1) {
    const needed = perLine[i] * 0.25 + perLine[i + 1] * 0.95;
    assert.ok(needed <= LINE_STEP + 0.01, `${perLine[i]}px 위에 ${perLine[i + 1]}px가 겹친다`);
  }
};

test("라벨은 타일에 들어갈 때만 그려지고, 크기는 실제 상자에서 나온다", () => {
  const roomy = heatmapLabelMarkup("NVDA", "+2.00%", { width: 200, height: 120 }, measureStub);
  assert.match(roomy, /NVDA/);
  assert.match(roomy, /\+2\.00%/);
  assert.ok(labelSize(roomy) >= 14, `넓은 타일인데 ${labelSize(roomy)}px`);

  const tight = heatmapLabelMarkup("NVDA", "+2.00%", { width: 60, height: 30 }, measureStub);
  assert.ok(labelSize(tight) < labelSize(roomy), "작은 타일이 더 작은 글자를 받아야 한다");
});

test("여러 줄 라벨은 고정 줄 간격 안에 들어와 겹치지 않는다", () => {
  // 큰 타일에서 종목명 30px + 등락률 19px이 14.3px 간격에 얹혀 통째로 겹쳤다(실측).
  assertNoOverlap(heatmapLabelMarkup("NVDA", "+2.00%", { width: 400, height: 300 }, measureStub));
  assertNoOverlap(heatmapLabelMarkup("NVDA", "+2.00%", { width: 200, height: 120 }, measureStub));
  assertNoOverlap(heatmapLabelMarkup("Mitsubishi UFJ Financial", "+1.00%", { width: 90, height: 100 }, measureStub));
  // 아무리 넓어도 간격이 허락하는 크기를 넘지 않는다.
  const huge = heatmapLabelMarkup("NVDA", "+2.00%", { width: 800, height: 800 }, measureStub);
  assert.ok(labelSize(huge) <= 20, `${labelSize(huge)}px는 아랫줄을 덮는다`);
});

test("글자 크기는 칸 크기를 따라간다 — 짧은 티커라고 작은 칸에서 커지지 않는다", () => {
  // 크기를 "들어가기만 하면 최대"로 두면 글자 길이가 크기를 정한다. 작은 칸이라도
  // 티커가 짧으면(MU) 큰 칸과 같은 크기를 받아 칸에 비해 글자가 컸다.
  const sizeAt = (w, h) => labelSize(heatmapLabelMarkup("MU", "+1.00%", { width: w, height: h }, measureStub));
  const big = sizeAt(250, 160);
  const mid = sizeAt(90, 70);
  const small = sizeAt(40, 30);
  assert.ok(big > mid && mid > small, `${big} > ${mid} > ${small}이어야 한다`);
  // 완전 비례는 아니다. 면적이 33배인데 글자는 3배를 넘지 않는다.
  assert.ok(big < small * 3, `${big}px는 ${small}px에 비해 과하게 크다`);
  // 상한과 하한은 지킨다.
  assert.ok(sizeAt(2000, 2000) <= 20, "겹침 상한을 넘지 않는다");
  for (const [w, h] of [[250, 160], [90, 70], [40, 30], [30, 22]]) {
    assert.ok(sizeAt(w, h) >= 6, `${w}x${h}에서 하한 미만`);
  }
});

test("이름이 길면 어절 단위로 줄을 나눈다", () => {
  // 실측: 이 줄바꿈 하나가 JP에서 라벨 20개, KR에서 12개를 살린다.
  const markup = heatmapLabelMarkup("Mitsubishi UFJ Financial", "+1.00%", { width: 90, height: 100 }, measureStub);
  assert.match(markup, /Mitsubishi UFJ<br>Financial/);
  assert.ok(labelSize(markup) >= 9);
});

test("자리가 모자라면 등락률 줄을 먼저 버린다", () => {
  const markup = heatmapLabelMarkup("NVDA", "+2.00%", { width: 60, height: 20 }, measureStub);
  assert.match(markup, /NVDA/);
  assert.doesNotMatch(markup, /%/, "이름을 살리려면 등락률이 먼저 빠져야 한다");
});

test("들어가지 않는 라벨은 잘라내지 않고 비운다", () => {
  // 어절 단위로 잘라내면 KR `Samsung…`이 12개사를, JP `Mitsubishi…`가 7개사를
  // 가리킨다. 다른 회사 이름을 말하느니 색만 남기고 hover에 맡긴다.
  assert.equal(heatmapLabelMarkup("NVDA", "+2.00%", { width: 20, height: 20 }, measureStub), "");
  assert.equal(heatmapLabelMarkup("Samsung Electronics", "-1.00%", { width: 24, height: 24 }, measureStub), "");
});

test("종목 이름은 읽히는 쪽을 쓰고 거래소·법인격 꼬리를 뗀다", () => {
  // 숫자로 시작하는 코드는 그 자체로 읽히지 않는다. 한국 6자리는 예전부터
  // 회사명을 썼는데 일본은 `8306.T`가 그대로 나오고 있었다.
  assert.equal(heatmapTickerLabel({
    ticker: "8306.T",
    label: "三菱UFJフィナンシャル・グループ",
    englishName: "Mitsubishi UFJ Financial Group, Inc.",
  }), "Mitsubishi UFJ Financial");
  assert.equal(heatmapTickerLabel({ ticker: "005930", label: "Samsung Electronics" }), "Samsung Electronics");
  // 거래소 지역 코드는 손잡이가 아니다. MUV2가 뮌헨재보험이라고 읽히지 않는다.
  assert.equal(heatmapTickerLabel({ ticker: "ASML.AS", label: "ASML Holding" }), "ASML");
  assert.equal(heatmapTickerLabel({ ticker: "MUV2.DE", label: "Munich Re" }), "Munich Re");
  // 접미사 없는 미국식 티커는 그 자체로 읽힌다.
  assert.equal(heatmapTickerLabel({ ticker: "NVDA", label: "Nvidia" }), "NVDA");
  // 법인격을 떼면 접속 기호가 남는다. 잘린 이름처럼 보이면 안 된다.
  assert.equal(heatmapTickerLabel({ ticker: "8031.T", label: "三井物産", englishName: "Mitsui & Co., Ltd." }), "Mitsui");
  // 라틴 표기 label이 있으면 법인 전체 이름보다 그쪽이 짧고 읽기 좋다.
  assert.equal(heatmapTickerLabel({
    ticker: "MC.PA",
    label: "LVMH",
    englishName: "LVMH Moët Hennessy - Louis Vuitton, Société Européenne",
  }), "LVMH");
});

test("KR 섹터는 영문으로 되돌리되 다시 분류하지 않는다", () => {
  // kospi200_universe.py가 GICS 영문을 한글로 옮겨 저장한다. 저장된 시각자료는
  // 불변이라 표시 시점에 되돌려야 과거 브리핑도 함께 영문이 된다.
  assert.equal(heatmapGroupName("경기소비재"), "Consumer Discretionary");
  assert.equal(heatmapGroupName("금융"), "Financials");
  // KRX식 그룹은 GICS와 체계가 달라 묶지 않는다(석유화학은 Energy와 Materials로 갈린다).
  assert.equal(heatmapGroupName("IT"), "IT");
  assert.equal(heatmapGroupName("Heavy Industries"), "Heavy Industries");
  assert.equal(heatmapGroupName("Technology"), "Technology");
});

test("뿌리 화면은 산업 층을 접어 종목에 자리를 준다", () => {
  // 산업 127개가 각각 머리띠와 여백을 가져가는데 실측에서 13%만 읽혔다.
  const rows = [
    { ticker: "NVDA", sector: "Technology", industry: "Semiconductors", marketCap: 100, changePct: 2 },
    { ticker: "MSFT", sector: "Technology", industry: "Software", marketCap: 90, changePct: -1 },
  ];
  const flat = heatmapNodes(rows, { flat: true });
  assert.ok(!flat.ids.some((id) => id.startsWith("industry:")), "뿌리에는 산업 층이 없다");
  assert.equal(flat.parents[flat.ids.indexOf("ticker:NVDA")], "sector:Technology");
  // 들어갔을 때 쓸 계층은 그대로 만들어진다.
  assert.ok(heatmapNodes(rows).ids.some((id) => id.startsWith("industry:")));
});

test("heatmapColor는 방향을 색상으로, 등락 크기를 휘도로 말한다", () => {
  // 흰 글자 대비가 전 구간 5.26:1 이상이다. 예전 #168a56은 4.37:1로 AA 미달이었다.
  assert.equal(heatmapColor(-3), "#6d1823");
  assert.equal(heatmapColor(-2), "#882e3a");
  assert.equal(heatmapColor(-1), "#904852");
  assert.equal(heatmapColor(-0.3), "#875960");
  assert.equal(heatmapColor(0), "#676c78");
  assert.equal(heatmapColor(0.3), "#486d5f");
  assert.equal(heatmapColor(1), "#326853");
  assert.equal(heatmapColor(2), "#195840");
  assert.equal(heatmapColor(3), "#05412a");
  // 경계는 대칭이다.
  assert.equal(heatmapColor(-0.5), "#904852");
  assert.notEqual(heatmapColor(0.4), heatmapColor(0.6));
});

test("회색은 표시상 0.00%인 칸만이다", () => {
  // |등락| < 0.5%를 통째로 회색으로 칠하던 시절 전체 타일의 26%가 회색이었고,
  // 그중 실제로 0.00%인 것은 US 129개 중 1개뿐이었다 — 움직인 종목이 안 움직인
  // 것처럼 보인다.
  const flat = heatmapColor(0);
  assert.equal(heatmapColor(0.004), flat, "0.00%로 찍히는 값은 회색이다");
  assert.equal(heatmapColor(null), flat, "등락을 모르면 회색이다");
  for (const value of [0.01, 0.05, 0.32, 0.49]) {
    assert.notEqual(heatmapColor(value), flat, `+${value}%가 회색이면 안 된다`);
    assert.notEqual(heatmapColor(-value), flat, `-${value}%가 회색이면 안 된다`);
  }
  // 옅은 단계도 방향이 갈린다.
  assert.notEqual(heatmapColor(0.3), heatmapColor(-0.3));
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
