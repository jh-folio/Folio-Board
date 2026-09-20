const test = require("node:test");
const assert = require("node:assert/strict");

test("weekly index snapshots use the daily chart with a one-week default", () => {
  const { availablePeriods, initialPriceState, periodPoints, weeklyReturnSummary } = require("./briefing-visuals.js");
  const daily = { interval: "1d", points: [
    { time: "2026-08-28", close: 100 }, { time: "2026-08-31", close: 101 },
    { time: "2026-09-02", close: 102 }, { time: "2026-09-04", close: 103 },
  ] };
  const weekly = { series: [{ ticker: "^KS11", label: "KOSPI", daily, weeklyReturn: -1.95, weeklyBaselineDate: "2026-08-28" }] };
  // 주간 저장본에는 분봉이 없다 — 누르면 빈 차트가 될 1D는 아예 만들지 않는다.
  assert.deepEqual(availablePeriods(weekly), ["1W", "1M", "3M", "YTD", "1Y"]);
  assert.equal(initialPriceState(weekly, "1W").period, "1W");
  // 답할 수 없는 기간을 권해도 저장본이 가진 것으로 내려온다.
  assert.equal(initialPriceState(weekly, "1D").period, "1W");
  // 1W는 그 주만 담는다. 직전 주 세션(08-28)은 들어오지 않는다.
  assert.deepEqual(
    periodPoints(weekly.series[0], "1W", "2026-09-04").points.map((row) => row.time),
    ["2026-08-31", "2026-09-02", "2026-09-04"],
  );
  // 일간 저장본은 그대로 1D부터 시작한다.
  const dailySnapshot = { series: [{ ticker: "^GSPC", intraday: { interval: "5m", points: [{ time: "2026-09-04T10:00:00-04:00", close: 5 }] }, daily }] };
  assert.deepEqual(availablePeriods(dailySnapshot), ["1D", "1W", "1M", "3M", "YTD", "1Y"]);
  assert.equal(initialPriceState(dailySnapshot).period, "1D");
  // 전체 주간 값은 곡선(주초=0%)이 아니라 직전 주 종가 기준이라 기준일을 함께 적는다.
  assert.equal(weeklyReturnSummary(weekly), "KOSPI 전체 주간 -1.95%(08-28 종가 대비)");
  assert.equal(
    weeklyReturnSummary({ series: [{ label: "KOSDAQ", weeklyReturn: null, weeklyReturnReason: "prior_week_close_missing" }] }),
    "KOSDAQ 전체 주간 비교 자료 없음",
  );
});

test("1W draws hourly bars but still reports the move in closes", () => {
  const {
    periodPoints, priceSummaryForPeriod, hoverTooltipContent, lightweightRows,
    isIntradayInterval, weekBarUnit,
  } = require("./briefing-visuals.js");
  // 실측값이다(^KS11, 2026-08-31 주). 월요일 09시 봉 종가와 월요일 일봉 종가가 2.8%p 다르다.
  const subject = {
    ticker: "^KS11", label: "KOSPI",
    hourly: { interval: "1h", points: [
      { time: "2026-08-31T09:00:00+09:00", close: 6631.82 },
      { time: "2026-08-31T10:00:00+09:00", close: 6700.5 },
      { time: "2026-09-04T14:00:00+09:00", close: 6687.21 },
    ] },
    daily: { interval: "1d", points: [
      { time: "2026-08-28", close: 6789.2 }, { time: "2026-08-31", close: 6820.02 },
      { time: "2026-09-04", close: 6687.21 },
    ] },
  };
  assert.equal(isIntradayInterval("5m"), true);
  assert.equal(isIntradayInterval("1h"), true);
  assert.equal(isIntradayInterval("1d"), false);

  const week = periodPoints(subject, "1W", "2026-09-04");
  assert.equal(week.interval, "1h");
  assert.equal(week.points.length, 3);
  // 더 긴 구간은 시간봉 저장 창(한 주) 밖이라 일봉 그대로다.
  assert.equal(periodPoints(subject, "1M", "2026-09-04").interval, "1d");
  // 시간봉이 없는 저장본은 `1W`도 일봉으로 그린다.
  assert.equal(periodPoints({ daily: subject.daily }, "1W", "2026-09-04").interval, "1d");

  // 값은 그린 날들의 **일봉 종가**로 말한다. 시간봉 첫 점을 기준 삼으면 +0.84%가 되어
  // 같은 카드의 캡션·본문이 말하는 주간 등락과 어긋난다.
  const summary = priceSummaryForPeriod(subject, "1W", week.points);
  assert.equal(summary.close, 6687.21);
  assert.equal(summary.changePct.toFixed(2), "-1.95");
  // hover 기준선도 같아야 툴팁과 머리 숫자가 같은 말을 한다.
  const tooltip = hoverTooltipContent(subject, "1W", week.points[2], { currency: "KRW" }, week.points);
  assert.match(tooltip, /-1\.95%/);
  assert.match(tooltip, /2026-09-04 14:00/);

  // 시간봉은 **봉 시작** 시각 그대로다. 한 시간을 더하면 미국장 15:30 봉이 마감(16:00) 뒤가 된다.
  const rows = lightweightRows(subject.hourly.points, "line", "1h");
  assert.equal(rows[0].time, Date.UTC(2026, 7, 31, 9, 0, 0) / 1000);
  assert.equal(rows.length, 3);
  // 일봉은 지금처럼 날짜 문자열이다.
  assert.equal(lightweightRows(subject.daily.points, "line", "1d")[0].time, "2026-08-28");

  assert.equal(weekBarUnit({ series: [subject] }), "1시간봉");
  assert.equal(weekBarUnit({ series: [{ daily: subject.daily }] }), "일봉");
});

test("legacy weekly snapshots keep the old overlay chart", () => {
  const { hasStoredDailyHistory, shouldRenderTrend, normalizePriceSubject } = require("./briefing-visuals.js");
  // 저장된 옛 주간 보고서의 실제 모양: 주초=0%로 재기준한 5점뿐이고 `daily`가 없다.
  // 그 점에도 원 종가가 들어 있어 기존 판정은 통과한다 — 그래서 판정을 하나 더 둔다.
  const legacy = { series: [{ ticker: "^KS11", label: "KOSPI", points: [
    { time: "2026-08-31", close: 6820.02, changePct: 0 }, { time: "2026-09-01", close: 6760.1, changePct: -0.88 },
    { time: "2026-09-02", close: 6712.4, changePct: -1.58 }, { time: "2026-09-03", close: 6701.9, changePct: -1.73 },
    { time: "2026-09-04", close: 6687.1, changePct: -1.95 },
  ] }] };
  assert.equal(shouldRenderTrend(legacy), true);
  // `normalizePriceSubject`가 그 %-계열을 일봉 자리에 되돌려주므로 기간 버튼도 생겼을 것이다.
  assert.equal(normalizePriceSubject(legacy.series[0]).daily.points.length, 5);
  assert.equal(hasStoredDailyHistory(legacy), false);

  const stored = (count) => ({
    dataSufficiency: { minimumTrendPoints: 8 },
    series: [{ ticker: "^KS11", daily: { interval: "1d", points: Array.from({ length: count }, (_, i) => ({ time: `2026-08-${10 + i}`, close: 100 + i })) } }],
  });
  assert.equal(hasStoredDailyHistory(stored(255)), true);
  // 한 주의 거래일만큼만 담긴 저장본은 기간 버튼이 답할 것이 없어 옛 그림으로 남는다.
  assert.equal(hasStoredDailyHistory(stored(5)), false);
  // 저장본이 문턱을 밝히지 않으면 8을 쓴다.
  assert.equal(hasStoredDailyHistory({ series: stored(8).series }), true);
});

test("story share draws in CSS pixels so type and stroke match the other charts", () => {
  const { storyShareGeometry } = require("./briefing-visuals.js");
  // 1 user unit = 1 CSS px. 폭이 달라져도 높이·여백은 픽셀로 고정된다.
  for (const width of [1180, 574, 308]) {
    const box = storyShareGeometry(width);
    assert.equal(box.width, width);
    assert.equal(box.height, 275);
    assert.equal(box.left, 52);
    // 가운데 정렬한 마지막 날짜 라벨의 절반이 잘리지 않을 만큼 오른쪽을 비운다.
    assert.equal(box.right, width - 24);
    assert.ok(box.right > box.left + 100);
  }
  // 아직 폭을 재지 못한 첫 렌더는 기본 좌표계로 그리고 relayout이 고친다.
  for (const unmeasured of [0, null, undefined, "", 120]) {
    assert.equal(storyShareGeometry(unmeasured).width, 640);
  }
});

test("saved share values preserve missing versus zero and heatmap hover omits missing close", () => {
  const { storyShareValue, heatmapHoverText, priceSummary } = require("./briefing-visuals.js");
  const day = { shares: { A: .123456, B: 0, C: null }, otherShare: null };
  assert.equal(storyShareValue(day, "A", "other"), .123456);
  assert.equal(storyShareValue(day, "B", "other"), 0);
  for (const label of ["C", "D", "other"]) assert.equal(storyShareValue(day, label, "other"), null);
  assert.equal(heatmapHoverText(["Technology", -3.288084787, null, ""]), "Technology<br>등락 -3.29%");
  assert.match(heatmapHoverText(["A", 1.2345, 1234.5, "2026-09-01"]), /등락 \+1.23%<br>종가/);
  assert.equal(priceSummary([{ close: null }]).close, null);
});

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
  heatmapLabelPlan,
  heatmapRichLabel,
  heatmapTree,
  heatmapSeriesBase,
  heatmapTileSizes,
  heatmapFallbackSize,
  heatmapPlanLabels,
  heatmapHeaderAt,
  heatmapTickerLabel,
  heatmapGroupName,
  abbreviateHeatmapLabel,
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
// 라벨은 그리기 **전에** 정확한 타일 크기로 정한다.
// 예전에는 그린 뒤 타일을 재서 라벨을 얹고 Plotly가 축소하면 예산을 깎아 다시 그렸다
// (4패스 + 비동기 대기). ECharts는 축소하지 않고 `...`로 잘라 버리므로, 들어가는 것만 미리 고른다.
// 아래 측정 함수는 결정적인 stub이다(어느 글꼴이 깔려 있든 같은 답이 나온다).
// ---------------------------------------------------------------------------
const measureStub = (text, size) => String(text).length * size * 0.6;
// 좌우 여백은 칸 폭의 8%(최소 3px)씩, 위아래는 3px씩이다.
const sidePad = (width) => Math.max(3, width * 0.08);
const VERTICAL_PAD = 3;

// 계획이 요구하는 세로 높이. 줄 상자는 글꼴의 1.2배, 줄 간격은 우리가 정한 lineHeight다.
const neededHeight = (plan) =>
  plan.size * 1.2 + (plan.lines.length - 1) * plan.nameStep + (plan.suffix ? plan.tailStep : 0);

test("라벨은 타일에 들어갈 때만 정해지고, 크기는 실제 상자에서 나온다", () => {
  const roomy = heatmapLabelPlan("NVDA", "+2.00%", { width: 200, height: 120 }, measureStub);
  assert.deepEqual(roomy.lines, ["NVDA"]);
  assert.equal(roomy.suffix, "+2.00%");
  assert.ok(roomy.size >= 14, `넓은 타일인데 ${roomy.size}px`);

  const tight = heatmapLabelPlan("NVDA", "+2.00%", { width: 60, height: 30 }, measureStub);
  assert.ok(tight.size < roomy.size, "작은 타일이 더 작은 글자를 받아야 한다");
});

test("고른 라벨은 반드시 상자 안에 들어간다 — 세로로도, 가로로도", () => {
  const boxes = [[400, 300], [200, 120], [90, 100], [60, 30], [130, 60], [45, 40]];
  const labels = [["NVDA", "+2.00%"], ["Mitsubishi UFJ Financial", "+1.00%"], ["Samsung Electronics", "-0.53%"], ["MU", "+1.00%"]];
  for (const [width, height] of boxes) {
    for (const [label, change] of labels) {
      const plan = heatmapLabelPlan(label, change, { width, height }, measureStub);
      if (!plan) continue;
      assert.ok(neededHeight(plan) <= height - VERTICAL_PAD * 2 + 0.01, `${label}@${width}x${height}: 높이 ${neededHeight(plan)}가 넘친다`);
      // ECharts는 폭을 넘는 글자를 `...`로 자른다. 등락률이 잘리면 -0.53%가 -0.5로 읽혀 틀린 숫자가 된다.
      for (const line of plan.lines) {
        assert.ok(measureStub(line, plan.size) <= width - sidePad(width) * 2 + 0.01, `${label}@${width}x${height}: "${line}"이 잘린다`);
      }
      if (plan.suffix) {
        assert.ok(measureStub(plan.suffix, plan.tailSize) <= width - sidePad(width) * 2 + 0.01, `${label}@${width}x${height}: 등락률이 잘린다`);
      }
    }
  }
});

test("글자 크기는 칸 크기를 따라간다 — 짧은 티커라고 작은 칸에서 커지지 않는다", () => {
  // 크기를 "들어가기만 하면 최대"로 두면 글자 길이가 크기를 정한다. 작은 칸이라도
  // 티커가 짧으면(MU) 큰 칸과 같은 크기를 받아 칸에 비해 글자가 컸다.
  const sizeAt = (w, h) => heatmapLabelPlan("MU", "+1.00%", { width: w, height: h }, measureStub).size;
  const big = sizeAt(250, 160);
  const mid = sizeAt(90, 70);
  const small = sizeAt(40, 30);
  assert.ok(big > mid && mid > small, `${big} > ${mid} > ${small}이어야 한다`);
  // 완전 비례는 아니다. 면적이 33배인데 글자는 3배를 넘지 않는다.
  assert.ok(big < small * 3, `${big}px는 ${small}px에 비해 과하게 크다`);
  // 상한과 하한은 지킨다.
  assert.ok(sizeAt(2000, 2000) <= 20, "상한을 넘지 않는다");
  for (const [w, h] of [[250, 160], [90, 70], [50, 30]]) {
    assert.ok(sizeAt(w, h) >= 6, `${w}x${h}에서 하한 미만`);
  }
});

test("이름이 길면 어절 단위로 줄을 나눈다", () => {
  // 실측: 이 줄바꿈 하나가 JP에서 라벨 20개, KR에서 12개를 살린다.
  const plan = heatmapLabelPlan("Mitsubishi UFJ Financial", "+1.00%", { width: 110, height: 100 }, measureStub);
  assert.equal(plan.lines.length, 2);
  // 어절 경계로만 나눈다 — 한 어절을 가르지 않고, 이어 붙이면 원래 이름이다.
  assert.equal(plan.lines.join(" "), "Mitsubishi UFJ Financial");
  assert.ok(plan.size >= 8);
});

test("자리가 모자라면 등락률 줄을 먼저 버린다", () => {
  const plan = heatmapLabelPlan("NVDA", "+2.00%", { width: 70, height: 16 }, measureStub);
  assert.deepEqual(plan.lines, ["NVDA"]);
  assert.equal(plan.suffix, "", "이름을 살리려면 등락률이 먼저 빠져야 한다");
});

test("들어가지 않는 라벨은 잘라내지 않고 비운다", () => {
  // 어절 단위로 잘라내면 KR `Samsung…`이 12개사를, JP `Mitsubishi…`가 7개사를
  // 가리킨다. 다른 회사 이름을 말하느니 색만 남기고 hover에 맡긴다.
  assert.equal(heatmapLabelPlan("NVDA", "+2.00%", { width: 20, height: 20 }, measureStub), null);
  assert.equal(heatmapLabelPlan("Samsung Electronics", "-1.00%", { width: 24, height: 24 }, measureStub), null);
  assert.equal(heatmapLabelPlan("", "+1.00%", { width: 200, height: 200 }, measureStub), null);
});

test("좌우 여백 3px 안쪽에만 라벨이 선다 — 여백보다 좁은 칸은 비운다", () => {
  // 6px(양쪽 3px) 이하의 칸에는 글자 폭이 남지 않는다.
  assert.equal(heatmapLabelPlan("A", "", { width: 6, height: 100 }, measureStub), null);
  assert.notEqual(heatmapLabelPlan("A", "", { width: 20, height: 100 }, measureStub), null);
});

test("라벨은 칸 폭의 84%를 넘지 않는다 — 가장자리에 붙어 보이지 않게 비율로 여백을 둔다", () => {
  // 3px 고정 여백일 때는 폭에 꼭 맞는 라벨이 칸 가장자리에 붙어 보였다(실측: 폭의 85%를 넘는 타일이 KR 8개·JP 14개).
  // 칸 폭의 8%(최소 3px)씩이면 폭 38px 이상에서 라벨은 폭의 84% 안이다.
  for (const width of [40, 60, 90, 130, 200, 400]) {
    for (const [label, change] of [["Samsung Electronics", "-0.53%"], ["NVDA", "+2.00%"], ["Mitsubishi UFJ Financial", "+1.00%"]]) {
      const plan = heatmapLabelPlan(label, change, { width, height: 200 }, measureStub);
      if (!plan) continue;
      const widest = Math.max(...plan.lines.map((line) => measureStub(line, plan.size)), plan.suffix ? measureStub(plan.suffix, plan.tailSize) : 0);
      assert.ok(widest / width <= 0.84 + 1e-9, `${label}@${width}: 폭의 ${(widest / width * 100).toFixed(0)}%를 차지한다`);
    }
  }
  // 아주 좁은 칸은 최소 3px씩만 남긴다.
  const narrow = heatmapLabelPlan("AB", "", { width: 20, height: 100 }, measureStub);
  assert.ok(measureStub(narrow.lines[0], narrow.size) <= 20 - 6 + 1e-9);
});

test("머리띠 라벨은 한 줄이고 띠 안에 들어간다", () => {
  const plan = heatmapLabelPlan("Consumer Disc.", "", { width: 200, height: 26, maxSize: 13, maxLines: 1 }, measureStub);
  assert.equal(plan.lines.length, 1);
  assert.ok(plan.size <= 13);
  assert.ok(neededHeight(plan) <= 26 - VERTICAL_PAD * 2);
  // 폭이 모자라면 줄바꿈으로 버티지 않고 비운다.
  assert.equal(heatmapLabelPlan("Consumer Discretionary Goods", "", { width: 90, height: 26, maxSize: 13, maxLines: 1 }, measureStub), null);
});

test("계획은 ECharts 라벨 설정이 된다 — 줄 간격도 우리가 정한다", () => {
  const plan = heatmapLabelPlan("NVDA", "+2.00%", { width: 200, height: 120 }, measureStub);
  const label = heatmapRichLabel(plan);
  assert.equal(label.formatter, "{n|NVDA}\n{c|+2.00%}");
  assert.equal(label.rich.n.fontSize, plan.size);
  assert.equal(label.rich.n.lineHeight, plan.nameStep);
  assert.equal(label.rich.c.fontSize, plan.tailSize);
  assert.equal(label.rich.n.fontWeight, 700);
});

test("여러 줄과 등락률이 없는 라벨의 서식", () => {
  assert.equal(
    heatmapRichLabel({ lines: ["Mitsubishi UFJ", "Financial"], size: 12, suffix: "", tailSize: 8, nameStep: 16, tailStep: 10 }).formatter,
    "{n|Mitsubishi UFJ}\n{n|Financial}",
  );
});

test("서식 예약 문자는 이름에서 지운다 — 남으면 라벨이 통째로 깨진다", () => {
  const label = heatmapRichLabel({ lines: ["A{b|c}d"], size: 12, suffix: "+1.00%", tailSize: 8, nameStep: 16, tailStep: 10 });
  assert.equal(label.formatter, "{n|Abcd}\n{c|+1.00%}");
});

const treeRows = [
  { ticker: "NVDA", label: "NVIDIA", sector: "Technology", industry: "Semiconductors", marketCap: 300, changePct: 2.5, close: 100, asOf: "2026-09-01" },
  { ticker: "AVGO", label: "Broadcom", sector: "Technology", industry: "Semiconductors", marketCap: 100, changePct: -1.2, close: 50, asOf: "2026-09-01" },
  { ticker: "MSFT", label: "Microsoft", sector: "Technology", industry: "Software", marketCap: 200, changePct: 0.3, close: 400, asOf: "2026-09-01" },
  { ticker: "JPM", label: "JPMorgan", sector: "Financials", industry: "Banks", marketCap: 150, changePct: 1.1, close: 200, asOf: "2026-09-01" },
];

test("heatmapTree는 평면 배열을 중첩 트리로 바꾼다", () => {
  const tree = heatmapTree(heatmapNodes(treeRows));
  assert.deepEqual(tree.map((node) => node.id), ["sector:Technology", "sector:Financials"]);
  const tech = tree[0];
  assert.deepEqual(tech.children.map((node) => node.id), ["industry:Technology:Semiconductors", "industry:Technology:Software"]);
  const semis = tech.children[0];
  assert.deepEqual(semis.children.map((node) => node.id), ["ticker:NVDA", "ticker:AVGO"]);
  // 잎에는 children 키가 없다(ECharts는 빈 배열도 부모로 본다).
  assert.equal("children" in semis.children[0], false);
  assert.equal(semis.children[0].value, 300);
  assert.equal(semis.children[0].itemStyle.color, heatmapColor(2.5));
  // hover가 쓸 원본 행.
  assert.equal(semis.children[0]._row[0], "NVIDIA");
});

test("뿌리(평면) 트리는 섹터 아래에 종목이 바로 붙는다", () => {
  const tree = heatmapTree(heatmapNodes(treeRows, { flat: true }));
  assert.deepEqual(tree[0].children.map((node) => node.id), ["ticker:NVDA", "ticker:AVGO", "ticker:MSFT"]);
});

test("시리즈 설정은 깊이와 머리띠 규칙을 담는다 — 진짜 차트와 배치 선계산이 같은 것을 쓴다", () => {
  const series = heatmapSeriesBase(2);
  assert.equal(series.type, "treemap");
  assert.equal(series.leafDepth, 2);
  assert.equal(series.nodeClick, false, "드릴다운은 우리가 직접 한다");
  // 기본값 `▶ `가 붙으면 그만큼 폭이 줄어 계획한 라벨이 잘린다(브라우저 실측: `Heavy Indust...`).
  assert.equal(series.drillDownIcon, "");
  // 트리맵 라벨 기본 padding 5는 글자 폭을 칸보다 10px 줄여 계획한 라벨을 잘랐다(브라우저 실측).
  assert.equal(series.label.padding, 0);
  assert.equal(series.upperLabel.padding, 0);
  assert.equal(series.upperLabel.height, 26);
  // 보이지 않는 뿌리가 머리띠를 갖으면 맨 위 26px이 빈 띠로 남는다.
  assert.equal(series.levels[0].upperLabel.show, false);
  assert.equal(heatmapSeriesBase(1).leafDepth, 1);
});

test("heatmapHeaderAt은 클릭 좌표로 머리띠를 가린다", () => {
  const headers = [
    { id: "sector:A", x: 0, y: 0, width: 100, height: 26 },
    { id: "sector:B", x: 100, y: 0, width: 80, height: 26 },
  ];
  assert.equal(heatmapHeaderAt(headers, 50, 10), "sector:A");
  assert.equal(heatmapHeaderAt(headers, 150, 25), "sector:B");
  assert.equal(heatmapHeaderAt(headers, 50, 40), "", "머리띠 아래는 아니다");
  assert.equal(heatmapHeaderAt(headers, undefined, 10), "");
  assert.equal(heatmapHeaderAt([], 5, 5), "");
});

const fakeRects = (entries) => new Map(entries.map(([id, width, height, x = 0, y = 0]) => [id, { x, y, width, height }]));

test("라벨 계획은 머리띠·잎·깊이 상한의 그룹을 모두 다룬다", () => {
  const roots = heatmapTree(heatmapNodes(treeRows, { flat: true }));
  const rects = fakeRects([
    ["sector:Technology", 500, 400, 0, 0], ["ticker:NVDA", 240, 160], ["ticker:AVGO", 100, 30], ["ticker:MSFT", 160, 120],
    ["sector:Financials", 160, 400, 500, 0], ["ticker:JPM", 150, 200],
  ]);
  const headers = heatmapPlanLabels(roots, { rects, total: 750, width: 660, height: 400, depth: 2, measure: measureStub });
  // 머리띠: 섹터가 이름을 받고, 띠 색은 틈 색(borderColor)으로 간다.
  assert.match(roots[0].upperLabel.formatter, /^\{n\|Technology\}$/);
  assert.equal(roots[0].upperLabel.height, 26);
  assert.equal(roots[0].itemStyle.borderColor, roots[0].itemStyle.color);
  // 잎: 이름 + 등락률.
  const nvda = roots[0].children[0];
  assert.equal(nvda.label.show, true);
  assert.match(nvda.label.formatter, /NVDA/);
  assert.match(nvda.label.formatter, /\+2\.50%/);
  // 머리띠 좌표는 클릭 판정에 쓰인다.
  assert.deepEqual(headers.map((h) => h.id), ["sector:Technology", "sector:Financials"]);
  assert.deepEqual(headers[1], { id: "sector:Financials", x: 500, y: 0, width: 160, height: 26 });
});

test("깊이 상한에서 잎이 된 그룹은 잘리지 않고 이름과 등락률을 받는다", () => {
  // 좁은 화면(depth 1): 섹터가 타일이다. 예전 기본 처리는 `▶ M...`처럼 잘랐다.
  const roots = heatmapTree(heatmapNodes(treeRows, { flat: true }));
  const rects = fakeRects([["sector:Technology", 200, 300], ["sector:Financials", 60, 60]]);
  const headers = heatmapPlanLabels(roots, { rects, total: 750, width: 260, height: 300, depth: 1, measure: measureStub });
  assert.deepEqual(headers, [], "이 깊이에는 머리띠가 없다");
  assert.equal(roots[0].label.show, true);
  assert.match(roots[0].label.formatter, /Technology/);
  assert.equal("upperLabel" in roots[0], false);
});

test("안 들어가는 라벨은 비우고, 머리띠는 남기되 글자만 비운다", () => {
  const roots = heatmapTree(heatmapNodes(treeRows, { flat: true }));
  const rects = fakeRects([
    ["sector:Technology", 40, 300, 0, 0], ["ticker:NVDA", 15, 15], ["ticker:AVGO", 15, 15], ["ticker:MSFT", 15, 15],
    ["sector:Financials", 160, 300, 40, 0], ["ticker:JPM", 150, 200],
  ]);
  heatmapPlanLabels(roots, { rects, total: 750, width: 200, height: 300, depth: 2, measure: measureStub });
  // 40px 머리띠에는 이름이 안 들어간다. show를 끄면 띠 자체가 사라져 자식이 그 자리를 먹는다.
  assert.equal(roots[0].upperLabel.show, true);
  // 빈 문자열은 서식 없음으로 읽혀 ECharts가 기본 이름을 잘라 그린다 — 공백으로 글자 없음을 명시한다.
  assert.equal(roots[0].upperLabel.formatter, " ");
  assert.equal(roots[0].children[0].label.show, false);
});

test("정확한 크기를 못 읽으면 보수적인 추정으로 물러난다 — 라벨은 줄지만 잘리지는 않는다", () => {
  const roots = heatmapTree(heatmapNodes(treeRows, { flat: true }));
  const total = 750;
  const fallback = heatmapFallbackSize(300, total, 660, 400);
  // 실측 타일 폭 / √면적의 최소가 0.58이다. 그보다 좁게 가정한다.
  assert.ok(Math.abs(fallback.width / fallback.height - 0.58) < 1e-9);
  assert.equal(fallback.x, null);
  const headers = heatmapPlanLabels(roots, { rects: null, total, width: 660, height: 400, depth: 2, measure: measureStub });
  assert.deepEqual(headers, [], "좌표를 모르면 머리띠 클릭 판정은 끈다");
  // 그래도 큰 종목은 라벨을 받는다.
  assert.equal(roots[0].children[0].label.show, true);
});

// ---------------------------------------------------------------------------
// canary — 배치를 읽는 경로가 ECharts 비공개 API라서 실제 벤더 번들로 매번 확인한다.
// ECharts를 올리는 사람이 여기서 먼저 걸린다. 실패하면 라벨 여백(3px)도 다시 재야 한다.
// ---------------------------------------------------------------------------
const loadVendorEcharts = () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const scope = {};
  scope.window = scope;
  scope.self = scope;
  new Function("window", "self", fs.readFileSync(path.join(__dirname, "vendor", "echarts.js"), "utf8"))(scope, scope);
  return scope.echarts;
};
const vendorEcharts = loadVendorEcharts();

const probeSeries = () => ({
  ...heatmapSeriesBase(2),
  data: [
    { id: "a", name: "A", value: 60, children: [{ id: "a1", name: "A1", value: 40 }, { id: "a2", name: "A2", value: 20 }] },
    { id: "b", name: "B", value: 40 },
  ],
});

test("canary: 벤더 번들에서 모든 그려진 노드의 크기가 유한하게 읽힌다", () => {
  const rects = heatmapTileSizes(vendorEcharts, probeSeries(), 800, 600);
  assert.ok(rects, "배치를 읽지 못했다 — ECharts 비공개 경로가 바뀌었을 수 있다");
  assert.deepEqual([...rects.keys()].sort(), ["a", "a1", "a2", "b"]);
  for (const rect of rects.values()) {
    assert.ok(Number.isFinite(rect.width) && rect.width > 0);
    assert.ok(Number.isFinite(rect.height) && rect.height > 0);
  }
});

test("canary: squarify 결과가 고정된 버전에서 바뀌지 않았다", () => {
  // ECharts 6.1.0 실측. 면적에 비례한다: A=60% → 폭 480, B=40% → 폭 320.
  // 머리띠 26px이 있어 A의 자식들은 그만큼 낮다.
  const rects = heatmapTileSizes(vendorEcharts, probeSeries(), 800, 600);
  const size = (id) => [Math.round(rects.get(id).width), Math.round(rects.get(id).height)];
  // 테두리(0.45px)가 폭을 1px 안쪽으로 깎을 수 있어 1.5px 오차를 둔다.
  assert.ok(Math.abs(size("a")[0] - 480) <= 1.5 && size("a")[1] === 600, `A ${size("a")}`);
  assert.ok(Math.abs(size("b")[0] - 320) <= 1.5 && size("b")[1] === 600, `B ${size("b")}`);
  assert.ok(rects.get("a1").height + rects.get("a2").height <= 600 - 26 + 1, "머리띠 높이가 배치에 들어가야 한다");
});

test("canary: 같은 입력은 같은 배치다", () => {
  const first = heatmapTileSizes(vendorEcharts, probeSeries(), 640, 480);
  const second = heatmapTileSizes(vendorEcharts, probeSeries(), 640, 480);
  assert.deepEqual([...first], [...second]);
});

test("canary: 깊이 상한 아래의 노드는 배치가 없어 건너뛰고, 실패로 치지 않는다", () => {
  const series = { ...probeSeries(), leafDepth: 1 };
  const rects = heatmapTileSizes(vendorEcharts, series, 800, 600);
  assert.ok(rects, "depth 1도 읽혀야 한다(좁은 화면)");
  assert.ok(rects.has("a") && rects.has("b"));
  assert.equal(rects.has("a1"), false, "그려지지 않는 자식은 없다");
});

test("읽지 못하면 null이다 — 틀린 크기를 조용히 내주지 않는다", () => {
  assert.equal(heatmapTileSizes({ init() { throw new Error("no renderer"); } }, probeSeries(), 800, 600), null);
  assert.equal(heatmapTileSizes(vendorEcharts, probeSeries(), 0, 600), null);
  assert.equal(heatmapTileSizes(null, probeSeries(), 800, 600), null);
  // 배치 경로가 사라진 버전을 흉내 낸다.
  assert.equal(heatmapTileSizes({ init: () => ({ setOption() {}, dispose() {} }) }, probeSeries(), 800, 600), null);
});

test("ssr 인스턴스를 남기지 않는다 — 6.1.0은 dispose하지 않으면 Node가 끝나지 않는다", () => {
  let disposed = 0;
  const spy = {
    init: (...args) => {
      const chart = vendorEcharts.init(...args);
      const original = chart.dispose.bind(chart);
      chart.dispose = () => { disposed += 1; original(); };
      return chart;
    },
  };
  heatmapTileSizes(spy, probeSeries(), 800, 600);
  assert.equal(disposed, 1);
});

test("파이프라인: 실제 배치로 고른 라벨은 어느 것도 타일 폭을 넘지 않는다", () => {
  const nodes = heatmapNodes(treeRows, { flat: true });
  const roots = heatmapTree(nodes);
  const series = { ...heatmapSeriesBase(2), data: roots };
  const rects = heatmapTileSizes(vendorEcharts, series, 660, 400);
  const total = roots.reduce((sum, node) => sum + node.value, 0);
  const headers = heatmapPlanLabels(roots, { rects, total, width: 660, height: 400, depth: 2, measure: measureStub });
  assert.equal(headers.length, 2);
  const visit = (node) => {
    const rect = rects.get(node.id);
    const label = node.label && node.label.show ? node.label : null;
    if (label) {
      const lines = label.formatter.split("\n").map((line) => line.replace(/^\{[nc]\|/, "").replace(/\}$/, ""));
      for (const line of lines) {
        const style = line === lines[lines.length - 1] && /%$/.test(line) ? label.rich.c : label.rich.n;
        assert.ok(measureStub(line, style.fontSize) <= rect.width - sidePad(rect.width) * 2 + 0.01, `${node.id}: "${line}"이 ${rect.width}px 칸에서 잘린다`);
      }
    }
    (node.children || []).forEach(visit);
  };
  roots.forEach(visit);
  // 머리띠 좌표는 배치가 준 실제 좌표다.
  const tech = headers.find((header) => header.id === "sector:Technology");
  assert.deepEqual(tech, { id: "sector:Technology", x: rects.get("sector:Technology").x, y: rects.get("sector:Technology").y, width: rects.get("sector:Technology").width, height: 26 });
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
