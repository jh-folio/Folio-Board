import { readFile } from "node:fs/promises";
import { test } from "node:test";
import assert from "node:assert/strict";

test("shared chart owns local websocket lifecycle and explicit source/status copy", async () => {
  const source = await readFile(new URL("../src/app/dashboard/MarketChartFigure.tsx", import.meta.url), "utf8");
  assert.match(source, /\/api\/market\/realtime\/chart\?symbol=/);
  assert.match(source, /shouldOpenRealtime/);
  assert.match(source, /key=\{chartSessionKey\(props\.symbol, props\.range\)\}/);
  assert.match(source, /function MarketChartFigureSession/);
  assert.match(source, /const \[showMa, setShowMa\] = useState\(false\)/);
  assert.match(source, /payload\?\.liveEligible === true/);
  assert.match(source, /payload\.liveStatus === "available"/);
  assert.match(source, /primarySeriesRef/);
  assert.match(source, /primary\.update/);
  assert.doesNotMatch(source, /\.setData\(updated/);
  assert.match(source, /rowsForChartRedraw/);
  assert.match(source, /renderedPayloadRef/);
  assert.match(source, /lastProviderInstantRef/);
  assert.match(source, /applyLiveTick/);
  assert.match(source, /styleRef\.current/);
  assert.doesNotMatch(source, /\}, \[symbol, range, style, visible, bootstrapKey, payload\]\)/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /실시간/);
  assert.match(source, /재연결 중/);
  assert.match(source, /Toss 분봉 미지원/);
  assert.match(source, /document\.hidden/);
  assert.match(source, /clearTimeout/);
  assert.match(source, /socketRef\.current !== socket/);
  assert.match(source, /range !== "1d"/);
  assert.match(source, /status === "subscribed"/);
  assert.match(source, /status === "rejected"/);
  assert.match(source, /setLiveStatus\("unsupported"\)/);
  assert.match(source, /attempts = 0/);
  assert.match(source, /if \(!visible\) return/);
  assert.match(source, /setLiveQuote\(null\)/);
  assert.match(source, /liveQuote\?\.key === renderKey/);
  assert.match(source, /currentRowsRef\.current = row\.series/);
  assert.match(source, /!payload\.series\.length/);
  assert.match(source, /bootstrapRequestRef\.current \+= 1/);
  assert.match(source, /bootstrapRequestRef\.current !== requestGeneration/);
  assert.match(source, /providerCopy/);
  assert.match(source, /live_bootstrap: "장중 기준"/);
  assert.match(source, /Math\.min\(4000, 500 \* \(2 \*\* attempts\)\)/);
  assert.doesNotMatch(source, /DELAYED_YFINANCE_EXCHANGE_SUFFIXES/);
});

test("watchlist does not claim one global yfinance source for mixed panels", async () => {
  const [route, fundamentals, earnings] = await Promise.all([
    readFile(new URL("../src/app/WatchlistRoute.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/app/watchlist/FundamentalsPanel.tsx", import.meta.url), "utf8"),
    readFile(new URL("../src/app/watchlist/EarningsPanel.tsx", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(route, /출처 yfinance — 기업분석/);
  assert.match(fundamentals, /출처 \{panelProviderCopy\(payload\.provider\)\}/);
  assert.match(earnings, /출처 \{panelProviderCopy\(payload\.provider\)\}/);
  assert.match(earnings, /panelProviderCopy\(payload\?\.provider\)/);
  assert.doesNotMatch(earnings, /payload\?\.provider \|\| "yfinance"/);
});
