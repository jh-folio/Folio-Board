(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root && root.document) root.FolioBriefingVisuals = api;
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  const chartRecords = new Map();
  const PALETTE = ["#185fa5", "#c79a45", "#534ab7", "#0f6e56"];
  const renderGate = createRequestGate();

  function finite(value) {
    if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function indexSeries(points) {
    const clean = (points || [])
      .map((point) => ({ time: String(point.time || "").slice(0, 10), actual: finite(point.close) }))
      .filter((point) => point.time && point.actual !== null);
    const base = clean[0]?.actual;
    if (!base) return [];
    return clean.map((point) => ({
      time: point.time,
      value: Number(((point.actual / base) * 100).toFixed(4)),
      actual: point.actual,
    }));
  }

  function normalizePriceSubject(subject) {
    const row = subject || {};
    const legacyPoints = Array.isArray(row.points) ? row.points : [];
    return {
      ...row,
      intraday: row.intraday && Array.isArray(row.intraday.points)
        ? row.intraday
        : { interval: "5m", points: [] },
      // 주 단위 1시간봉. 없는 저장본은 `1W`도 일봉으로 그린다.
      hourly: row.hourly && Array.isArray(row.hourly.points)
        ? row.hourly
        : { interval: "1h", points: [] },
      daily: row.daily && Array.isArray(row.daily.points)
        ? row.daily
        : { interval: "1d", points: legacyPoints },
    };
  }

  /** 분·시간 단위면 참이다. `1d`는 거짓. 그리는 방식(시각 축·wall-clock 변환)과
   *  값 요약 방식(종가 기준)이 이 하나로 갈린다. */
  function isIntradayInterval(interval) {
    return /^\d+\s*[mh]$/i.test(String(interval || ""));
  }

  function pointsAreIntraday(points) {
    return (points || []).some((row) => /\d{2}:\d{2}/.test(String(row.time || "")));
  }

  function periodPoints(subject, period, asOf) {
    const normalized = normalizePriceSubject(subject);
    if (period === "1D") return normalized.intraday;
    const end = new Date(`${String(asOf || "").slice(0, 10)}T00:00:00Z`);
    if (Number.isNaN(end.getTime())) return { interval: "1d", points: [] };
    const starts = {
      // 주간 보고서의 기본 구간. asOf가 그 주 마지막 세션이라 달력 7일이면 월~금(주말
      // 포함)이 정확히 들어오고 직전 주 세션은 들어오지 않는다.
      "1W": new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate() - 6)),
      "1M": new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 1, end.getUTCDate())),
      "3M": new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 3, end.getUTCDate())),
      YTD: new Date(Date.UTC(end.getUTCFullYear(), 0, 1)),
      "1Y": new Date(Date.UTC(end.getUTCFullYear() - 1, end.getUTCMonth(), end.getUTCDate())),
    };
    const start = starts[period] || starts["1Y"];
    const inWindow = (row) => {
      const value = new Date(`${String(row.time || "").slice(0, 10)}T00:00:00Z`);
      return !Number.isNaN(value.getTime()) && value >= start && value <= end;
    };
    // `1W`만 시간봉으로 그린다. 한 주는 일봉으로는 5점이라 선이 아니라 꺾인 선분 넷이고,
    // 그 주 안에서 언제 움직였는지를 말하지 못한다. 더 긴 구간은 시간봉이 없거나(저장 창이
    // 한 주다) 너무 촘촘해 일봉 그대로다.
    const hourly = period === "1W" ? normalized.hourly.points.filter(inWindow) : [];
    if (hourly.length >= 2) return { interval: normalized.hourly.interval || "1h", points: hourly };
    return { interval: "1d", points: normalized.daily.points.filter(inWindow) };
  }

  function priceSummary(points) {
    const clean = (points || []).filter((row) => finite(row.close) !== null);
    if (!clean.length) return { close: null, change: null, changePct: null, open: null, high: null, low: null };
    const first = clean[0];
    const last = clean[clean.length - 1];
    const firstClose = finite(first.close);
    const close = finite(last.close);
    const change = firstClose === null || close === null ? null : close - firstClose;
    const highs = clean.map((row) => finite(row.high)).filter((value) => value !== null);
    const lows = clean.map((row) => finite(row.low)).filter((value) => value !== null);
    return {
      close,
      change,
      changePct: firstClose ? (change / firstClose) * 100 : null,
      open: finite(first.open),
      high: highs.length ? Math.max(...highs) : null,
      low: lows.length ? Math.min(...lows) : null,
    };
  }

  function dailyCloseWindow(subject) {
    const daily = normalizePriceSubject(subject).daily.points
      .filter((row) => finite(row.close) !== null);
    return daily.length >= 2 ? daily.slice(-2) : [];
  }

  /** 그린 날들의 **일봉 종가**만 남긴다.
   *
   *  값 요약은 봉을 잘게 쪼개도 종가 기준이어야 한다. 1W를 시간봉으로 그리면 첫 점이
   *  월요일 09시 봉의 종가라 월요일 **종가**와 다르고(실측 KOSPI 6631.82 vs 6820.02,
   *  2.8%p), 그대로 두면 머리 숫자가 −1.95%에서 +0.8%로 뛰어 같은 카드의 캡션·본문이
   *  말하는 주간 등락과 어긋난다. 1D가 세션 5분봉을 그리면서 값은 전일 종가 대비로
   *  말하는 것과 같은 규칙이다. */
  function closeWindowForDrawn(subject, points) {
    const days = new Set((points || []).map((row) => String(row.time || "").slice(0, 10)).filter(Boolean));
    if (!days.size) return [];
    return normalizePriceSubject(subject).daily.points
      .filter((row) => days.has(String(row.time || "").slice(0, 10)) && finite(row.close) !== null);
  }

  function closeWindow(subject, period, points) {
    if (period === "1D") return dailyCloseWindow(subject);
    return pointsAreIntraday(points) ? closeWindowForDrawn(subject, points) : [];
  }

  function priceSummaryForPeriod(subject, period, points) {
    const dailyWindow = closeWindow(subject, period, points);
    return priceSummary(dailyWindow.length >= 2 ? dailyWindow : points);
  }

  function hoverBaseline(subject, period, points) {
    const dailyWindow = closeWindow(subject, period, points);
    if (dailyWindow.length >= 2) return finite(dailyWindow[0].close);
    const first = (points || []).find((row) => finite(row.close) !== null || finite(row.value) !== null);
    return finite(first?.close ?? first?.value);
  }

  function formatHoverTime(value) {
    const raw = String(value || "");
    const textMatch = raw.match(/^(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}))?/);
    if (textMatch) return textMatch[2] ? `${textMatch[1]} ${textMatch[2]}` : textMatch[1];
    const numeric = finite(value);
    if (numeric !== null) {
      const date = new Date(numeric * 1000);
      if (!Number.isNaN(date.getTime())) return date.toISOString().slice(0, 16).replace("T", " ");
    }
    return raw || "날짜 없음";
  }

  function formatTooltipNumber(value, currency) {
    const number = finite(value);
    if (number === null) return "—";
    return new Intl.NumberFormat("ko-KR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      style: currency ? "currency" : "decimal",
      currency: currency || undefined,
    }).format(number);
  }

  function hoverTooltipContent(subject, period, point, snapshot, points) {
    const close = finite(point?.close ?? point?.value);
    const baseline = hoverBaseline(subject, period, points || normalizePriceSubject(subject).daily.points);
    const change = close === null || baseline === null ? null : close - baseline;
    const changePct = change === null || !baseline ? null : (change / baseline) * 100;
    const direction = change === null || change >= 0 ? "up" : "down";
    const date = formatHoverTime(point?.time);
    const price = close === null ? "가격 없음" : formatTooltipNumber(close, snapshot?.currency === "USD" ? "USD" : "");
    const changeText = change === null
      ? "등락률 없음"
      : `${change >= 0 ? "+" : ""}${formatTooltipNumber(change)} (${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%)`;
    return `<div class="briefing-price-tooltip-date">${escapeHtml(date)}</div><div class="briefing-price-tooltip-price">${escapeHtml(price)}</div><div class="briefing-price-tooltip-change" data-direction="${direction}">${escapeHtml(changeText)}</div>`;
  }

  function lightweightTimeLabel(value) {
    if (typeof value === "string") return formatHoverTime(value);
    if (value && typeof value === "object") {
      const year = String(value.year || "").padStart(4, "0");
      const month = String(value.month || "").padStart(2, "0");
      const day = String(value.day || "").padStart(2, "0");
      return year && month && day ? `${year}-${month}-${day}` : "";
    }
    return formatHoverTime(value);
  }

  /** 봉 라벨을 **봉 끝**으로 옮길 때 쓰는 분 수.
   *
   *  분봉만 옮긴다. 5분봉은 봉 길이가 정확히 5분이라 마지막 봉 `15:55`가 장 마감 `16:00`으로
   *  읽혀 맞지만, 시간봉의 마지막 봉은 한 시간이 아니다 — 미국장 `15:30` 봉은 30분(마감 16:00),
   *  한국장 `14:00` 봉은 90분(마감 15:30)이라 한 시간을 더하면 장이 끝난 뒤 시각이 된다.
   *  그래서 시간봉은 **봉 시작** 시각 그대로 쓴다(`1h`는 여기서 0이다). */
  function intervalMinutes(interval) {
    const match = String(interval || "").match(/^(\d+)m$/i);
    return match ? Number(match[1]) : 0;
  }

  function offsetMinutes(offsetText) {
    if (offsetText === "Z") return 0;
    const match = String(offsetText || "").match(/^([+-])(\d{2}):(\d{2})$/);
    if (!match) return null;
    const sign = match[1] === "-" ? -1 : 1;
    return sign * (Number(match[2]) * 60 + Number(match[3]));
  }

  function shiftedIsoTime(rawTime, minutes) {
    const raw = String(rawTime || "");
    const match = raw.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?([+-]\d{2}:\d{2}|Z)?$/);
    const parsed = Date.parse(raw);
    if (!match || !Number.isFinite(parsed)) return raw;
    const shifted = parsed + (minutes * 60 * 1000);
    const offset = offsetMinutes(match[5]);
    if (offset === null) return new Date(shifted).toISOString().slice(0, 19);
    const local = new Date(shifted + offset * 60 * 1000).toISOString().slice(0, 19);
    return `${local}${match[5] || ""}`;
  }

  function intradayDisplayTime(rawTime, interval) {
    const minutes = intervalMinutes(interval);
    return minutes ? shiftedIsoTime(rawTime, minutes) : String(rawTime || "");
  }

  // 5분봉 시각은 거래소 현지 시각(`2026-06-19T15:55:00-04:00`)으로 들어온다.
  // Lightweight Charts는 축과 crosshair 라벨을 항상 UTC로 그리므로 epoch를 그대로 넘기면
  // 미국장 09:35~16:00이 13:35~20:00으로 보인다. 벽시계 값을 UTC인 척 넘겨 현지 시각을 표시한다.
  function intradayChartTime(rawTime, interval) {
    const match = String(rawTime || "").match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (!match) return NaN;
    const wallClock = Date.UTC(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      Number(match[6] || 0),
    );
    if (!Number.isFinite(wallClock)) return NaN;
    return Math.floor((wallClock + intervalMinutes(interval) * 60 * 1000) / 1000);
  }

  /** 저장본이 실제로 답할 수 있는 기간만 남긴다.
   *
   *  주간 스냅샷에는 분봉이 없다(`granularities: ["1d"]`). 1D 버튼을 그대로 두면
   *  누르는 순간 빈 차트가 되므로, 있는 자료로만 버튼을 만든다. */
  function availablePeriods(snapshot) {
    const series = snapshot?.series || [];
    const has = (kind) => series.some((row) => (normalizePriceSubject(row)[kind].points || []).length > 0);
    const periods = [];
    if (has("intraday")) periods.push("1D");
    if (has("daily")) periods.push("1W", "1M", "3M", "YTD", "1Y");
    return periods.length ? periods : ["1D"];
  }

  function initialPriceState(snapshot, defaultPeriod) {
    const periods = availablePeriods(snapshot);
    const requested = String(defaultPeriod || "");
    return {
      selectedTicker: snapshot?.series?.[0]?.ticker || "",
      // 저장본이 권하는 기간(주간은 `1W`)을 쓰되, 그 저장본이 답할 수 있을 때만 쓴다.
      period: periods.includes(requested) ? requested : periods[0],
      chartType: "line",
    };
  }

  function lightweightRows(points, chartType, interval) {
    const intraday = isIntradayInterval(interval);
    return (points || []).map((point) => {
      const rawTime = String(point.time || "");
      const time = intraday ? intradayChartTime(rawTime, interval) : rawTime.slice(0, 10);
      if (!time || (intraday && !Number.isFinite(time))) return null;
      if (chartType === "candle") {
        const open = finite(point.open);
        const high = finite(point.high);
        const low = finite(point.low);
        const close = finite(point.close);
        return [open, high, low, close].some((value) => value === null)
          ? null
          : { time, open, high, low, close };
      }
      const value = finite(point.close);
      return value === null ? null : { time, value };
    }).filter(Boolean);
  }

  function sectionRole(text) {
    const value = String(text || "").replace(/\s+/g, " ").trim();
    // 주간 규칙을 먼저 본다. 주간 §1은 `지난주 미국장 흐름`이라 일간의 `시장 흐름`에
    // 걸리지 않고, §2는 `지난주 …을 움직인 핵심 변수`다 — `지난주`가 없으면 일간
    // §2(`미국장을 움직인 핵심 변수`)까지 슬롯을 만들어 빈 자리가 생긴다.
    if (/지난주 .*흐름/.test(value)) return "weekly_flow";
    if (/지난주 .*핵심 변수/.test(value)) return "weekly_story_share";
    if (/시장 흐름/.test(value)) return "market_flow";
    const leader = value.match(/주도한 기업\s*([①②])/);
    if (leader) return { role: "leading_company", ordinal: leader[1] === "①" ? 1 : 2 };
    return null;
  }

  // 시장 판정은 **네 시장 전부**를 안다. 미국·한국만 알던 시절 유럽장·일본장 브리핑은
  // 슬롯이 하나도 만들어지지 않아, 저장된 스냅샷 네 장이 화면에 아무것도 그리지 못했다
  // (실측 2026-08-12~14 유럽·일본 보고서 6건 전부).
  const MARKET_HEADING_PATTERNS = [
    ["US", /미국장|us market/],
    ["KR", /한국장|korea market/],
    ["EUROPE", /유럽장|europe market/],
    ["JP", /일본장|japan market/],
  ];
  const SCOPE_MARKETS = { us: "US", kr: "KR", europe: "EUROPE", jp: "JP" };

  function sectionMarket(text, articleScope = "both") {
    const value = String(text || "").toLowerCase();
    const matched = MARKET_HEADING_PATTERNS.find(([, pattern]) => pattern.test(value));
    if (matched) return matched[0];
    return SCOPE_MARKETS[String(articleScope || "").toLowerCase()] || "";
  }

  function preferredIndexTicker(sectionText, series, market) {
    const text = String(sectionText || "").toLowerCase();
    const aliases = {
      "^GSPC": ["s&p 500", "s&p500", "에스앤피 500"],
      "^IXIC": ["nasdaq", "nasdaq composite", "나스닥", "나스닥 종합", "나스닥종합"],
      "^NDX": ["nasdaq 100", "나스닥 100", "나스닥100"],
      "^DJI": ["dow jones", "다우존스", "다우 지수"],
      "^KS11": ["kospi", "코스피"],
      "^KS200": ["kospi 200", "코스피 200", "코스피200"],
    };
    const mentioned = (series || []).find((row) => {
      const names = [row.label, row.ticker, ...(aliases[row.ticker] || [])]
        .map((value) => String(value || "").toLowerCase()).filter(Boolean);
      return names.some((name) => text.includes(name));
    });
    if (mentioned) return mentioned.ticker;
    const fallback = String(market || "").toUpperCase() === "KR" ? "^KS11" : "^GSPC";
    return (series || []).some((row) => row.ticker === fallback) ? fallback : (series?.[0]?.ticker || "");
  }

  function sectionHeadingSelector() {
    return "h3";
  }

  function isSectionBoundaryTag(tagName) {
    return tagName === "H2" || tagName === "H3";
  }

  function insertSectionSlot(heading, slot) {
    const lead = heading.nextElementSibling;
    (lead?.tagName === "P" ? lead : heading).insertAdjacentElement("afterend", slot);
  }

  function buildSectionSlots(article) {
    article.querySelectorAll(".briefing-inline-visual-slot").forEach((slot) => slot.remove());
    const scope = article.dataset.marketScope || "both";
    const slots = [];
    for (const heading of article.querySelectorAll(sectionHeadingSelector())) {
      const role = sectionRole(heading.textContent);
      if (!role) continue;
      const market = sectionMarket(heading.textContent, scope);
      if (!market) continue;
      const slot = document.createElement("div");
      slot.className = "briefing-inline-visual-slot";
      slot.dataset.sectionRole = typeof role === "string" ? role : role.role;
      slot.dataset.market = market;
      if (typeof role === "object") slot.dataset.ordinal = String(role.ordinal);
      let cursor = heading;
      const sectionParts = [];
      while (cursor.nextElementSibling && !isSectionBoundaryTag(cursor.nextElementSibling.tagName)) {
        cursor = cursor.nextElementSibling;
        sectionParts.push(cursor.textContent || "");
      }
      slot._sectionText = sectionParts.join(" ");
      insertSectionSlot(heading, slot);
      slots.push(slot);
    }
    return slots;
  }

  /** 방향은 색상, 등락 크기는 휘도가 말한다.
   *
   *  타일의 3분의 2는 라벨을 받지 못해 색이 정보를 다 져야 한다. 예전 5단은
   *  보합 회색과 소폭 상승 초록의 휘도비가 1.06:1이라 사실상 같은 밝기였고,
   *  흰 글자 대비가 #168a56 4.37:1 · #b65b67 4.49:1로 WCAG AA(4.5:1)에 못 미쳤다.
   *  지금 단계는 전부 5.26:1 이상이고 이웃 단계끼리 1.23:1 이상 벌어진다.
   *
   *  적록색약에서 같은 크기의 상승·하락은 여전히 구분되지 않는다(1.13:1).
   *  빨강/초록을 쓰는 한 색으로는 못 고치며, 방향은 라벨의 부호와 hover가 받는다.
   */
  // 회색은 **표시상 0.00%이거나 등락을 모르는 칸**만이다. 예전에는 |등락| < 0.5%를
  // 통째로 회색으로 칠했는데, 그러면 전체 타일의 26%가 회색이 되고 그중 실제로
  // 0.00%인 것은 US 129개 중 1개뿐이었다 — 움직인 종목이 안 움직인 것처럼 보인다.
  const HEATMAP_FLAT_EPSILON = 0.005;
  const HEATMAP_BANDS = [
    { max: -3, color: "#6d1823" },
    { max: -1.5, color: "#882e3a" },
    { max: -0.5, color: "#904852" },
    { max: -HEATMAP_FLAT_EPSILON, color: "#875960" },
    { max: HEATMAP_FLAT_EPSILON, color: "#676c78" },
    { max: 0.5, color: "#486d5f" },
    { max: 1.5, color: "#326853" },
    { max: 3, color: "#195840" },
  ];
  const HEATMAP_TOP_BAND = "#05412a";

  function heatmapColor(change) {
    const value = finite(change) || 0;
    for (const band of HEATMAP_BANDS) {
      // 음수 쪽은 경계값을 아래 단계에 넣는다(-3%는 `-3% 이하`다).
      if (band.max < 0 ? value <= band.max : value < band.max) return band.color;
    }
    return HEATMAP_TOP_BAND;
  }

  // KR 유니버스는 GICS 영문 섹터를 한글로 옮겨 저장한다
  // (kospi200_universe.py::GICS_SECTOR_KO). 지도에서만 영문으로 되돌린다 —
  // 저장된 시각자료는 불변이라 여기서 고쳐야 이미 만들어진 브리핑도 함께 영문이 된다.
  // **되돌리기만 하고 다시 분류하지 않는다.** KRX식 그룹(IT·Heavy Industries·
  // Constructions·Energy & Chemicals·Steels & Materials)은 GICS와 체계가 달라,
  // 묶으면 종목이 엉뚱한 섹터로 간다(석유화학은 Energy와 Materials로 갈린다).
  const HEATMAP_GROUP_EN = {
    "정보기술": "Information Technology",
    "금융": "Financials",
    "헬스케어": "Health Care",
    "경기소비재": "Consumer Discretionary",
    "커뮤니케이션서비스": "Communication Services",
    "산업재": "Industrials",
    "필수소비재": "Consumer Staples",
    "소재": "Materials",
    "에너지": "Energy",
    "유틸리티": "Utilities",
    "부동산": "Real Estate",
    "건설": "Constructions",
    "중공업": "Heavy Industries",
    "에너지화학": "Energy & Chemicals",
    "철강소재": "Steels & Materials",
  };

  function heatmapGroupName(value) {
    const name = String(value || "Other").trim() || "Other";
    return HEATMAP_GROUP_EN[name] || name;
  }

  // 법인격 꼬리와 거래소 접미사는 타일에서 자리만 차지한다.
  const HEATMAP_LEGAL_SUFFIX = /(,?\s+(Inc|Incorporated|Corporation|Corp|Company|Co|Ltd|Limited|PLC|N\.V|NV|S\.A|SA|AG|SE|Holdings?|Group)\.?)+$/i;
  const HEATMAP_EXCHANGE_SUFFIX = /\.(L|AS|PA|DE|MI|MC|SW|BR|HE|ST|CO|OL|VI|LS|IR|T|KS|KQ)$/;

  // 라틴 문자로 적힌 이름인가. 일본 행의 `label`은 현지 표기(`トヨタ自動車`)이고
  // `englishName`에 영문이 들어 있다. 유럽·한국은 반대로 `label`이 이미 짧은 영문
  // 표시명이라(`ASML Holding`) 그쪽을 먼저 본다 — `englishName`은 법인 전체 이름이다.
  const LATIN_NAME = /^[ -~À-ɏ‐-’\s]+$/;

  function shortCompanyName(value) {
    return String(value || "")
      .replace(HEATMAP_LEGAL_SUFFIX, "")
      // `Mitsui & Co., Ltd.`에서 법인격을 떼면 `Mitsui &`가 남는다. 접속 기호로
      // 끝나는 이름은 잘린 것처럼 읽히므로 함께 정리한다.
      .replace(/[\s,]*[&＆]\s*$/, "")
      .replace(/[\s,]+$/, "")
      .trim();
  }

  /** 타일에 쓸 종목 이름.
   *
   *  숫자 코드(`005930`·`8306.T`)와 거래소 지역 코드(`MUV2.DE`·`ALV.DE`)는 사람이
   *  읽는 손잡이가 아니다. 접미사 없는 미국식 티커(`NVDA`)만 그 자체로 읽힌다.
   *  한국 6자리는 예전부터 회사명으로 바꿔 왔는데 일본·유럽은 코드가 그대로
   *  나오고 있었다 — 저장된 행에 읽을 수 있는 이름이 전부 들어 있는데도.
   *
   *  전체 이름은 hover가 계속 들고 있다.
   */
  function heatmapTickerLabel(row) {
    const ticker = String(row.ticker || "");
    if (ticker && !/^\d/.test(ticker) && !HEATMAP_EXCHANGE_SUFFIX.test(ticker)) return ticker;
    const label = String(row.label || "");
    const preferred = label && LATIN_NAME.test(label) ? label : (row.englishName || label || ticker);
    return shortCompanyName(preferred) || ticker.replace(HEATMAP_EXCHANGE_SUFFIX, "") || "—";
  }

  function abbreviateHeatmapLabel(label) {
    const value = String(label || "Other").trim() || "Other";
    const aliases = {
      "Consumer Discretionary": "Consumer Disc.",
      "Consumer Cyclical": "Consumer Cyc.",
      "Consumer Defensive": "Consumer Def.",
      "Communication Services": "Comm. Services",
      "Financial Services": "Financials",
      "Information Technology": "Technology",
      "Basic Materials": "Materials",
      "Computer Software: Programming Data Processing": "Software & Data",
      "Catalog/Specialty Distribution": "Specialty Retail",
      "Semiconductor Equipment & Materials": "Semi. Equipment",
      "Banks - Diversified": "Diversified Banks",
      "Banks - Regional": "Regional Banks",
      "Drug Manufacturers - General": "Major Pharma",
      "Oil & Gas Integrated": "Integrated Energy",
      "Oil & Gas E&P": "Energy E&P",
      "Utilities - Regulated Electric": "Electric Utilities",
    };
    if (aliases[value]) return aliases[value];
    if (value.length <= 26) return value;
    return value
      .replace(/Manufacturers?/gi, "Mfrs.")
      .replace(/Manufacturing/gi, "Mfg.")
      .replace(/Services/gi, "Svcs.")
      .replace(/Technology/gi, "Tech")
      .replace(/Communication/gi, "Comm.")
      .replace(/Discretionary/gi, "Disc.")
      .replace(/Diversified/gi, "Divers.")
      .slice(0, 27)
      .replace(/[\s:;,.\/-]+$/, "")
      .concat("…");
  }

  /** 히트맵 계층을 만든다.
   *
   *  `options.flat`이면 산업 층을 접고 섹터 바로 아래에 종목을 붙인다. 뿌리
   *  화면이 그것을 쓴다 — 산업 127개가 각각 머리띠와 여백을 가져가면서 종목이
   *  쓸 자리를 먹는데, 정작 그 머리띠는 실측에서 13%(127개 중 16개)만 읽혔다.
   *  섹터를 누르면 계층이 있는 쪽으로 바꿔 그 안에서 산업을 다시 연다.
   */
  function heatmapNodes(inputRows, options) {
    const flat = Boolean(options && options.flat);
    const rows = (inputRows || []).filter((row) => {
      const value = finite(row.marketCap ?? row.weight);
      return value !== null && value > 0;
    });
    const result = { ids: [], labels: [], parents: [], values: [], colors: [], customdata: [], changes: [] };
    const capOf = (row) => finite(row.marketCap ?? row.weight) || 0;
    const weightedChange = (items) => {
      const usable = items.filter((row) => finite(row.changePct) !== null);
      const total = usable.reduce((sum, row) => sum + capOf(row), 0);
      return total ? usable.reduce((sum, row) => sum + finite(row.changePct) * capOf(row), 0) / total : null;
    };
    const normalizedGroupName = (value) => String(value || "Other").trim() || "Other";
    const shouldSkipIndustryLayer = (sector, industry) => {
      const sectorName = normalizedGroupName(sector).toLowerCase();
      const industryName = normalizedGroupName(industry).toLowerCase();
      return !industryName || industryName === "other" || industryName === sectorName;
    };
    const addGroup = (groupId, rawName, parentId, items) => {
      const change = weightedChange(items);
      const name = heatmapGroupName(rawName);
      result.ids.push(groupId);
      result.labels.push(abbreviateHeatmapLabel(name));
      result.parents.push(parentId);
      result.values.push(items.reduce((sum, row) => sum + capOf(row), 0));
      result.colors.push(heatmapColor(change));
      result.customdata.push([name, change, null, ""]);
      result.changes.push(change);
    };
    const addTicker = (row, parentId) => {
      result.ids.push(`ticker:${row.ticker}`);
      result.labels.push(heatmapTickerLabel(row));
      result.parents.push(parentId);
      result.values.push(capOf(row));
      result.colors.push(heatmapColor(row.changePct));
      result.customdata.push([row.label || row.ticker, row.changePct, row.close, row.asOf]);
      result.changes.push(finite(row.changePct));
    };
    const sectors = [...new Set(rows.map((row) => row.sector || "Other"))];
    for (const sector of sectors) {
      const sectorRows = rows.filter((row) => (row.sector || "Other") === sector);
      const sectorId = `sector:${sector}`;
      addGroup(sectorId, sector, "", sectorRows);
      if (flat) {
        for (const row of sectorRows) addTicker(row, sectorId);
        continue;
      }
      const industries = [...new Set(sectorRows.map((row) => row.industry || "Other"))];
      for (const industry of industries) {
        const industryRows = sectorRows.filter((row) => (row.industry || "Other") === industry);
        if (shouldSkipIndustryLayer(sector, industry)) {
          for (const row of industryRows) addTicker(row, sectorId);
          continue;
        }
        const industryId = `industry:${sector}:${industry}`;
        addGroup(industryId, industry, sectorId, industryRows);
        for (const row of industryRows) addTicker(row, industryId);
      }
    }
    return result;
  }

  // 좁은 화면에서는 종목까지 한 번에 그리지 않는다. 375px 휴대폰에서 재보면
  // 253x620 안에 타일 637개가 들어가고 그중 587개(92%)가 라벨을 담을 수 없는
  // 크기다. 색만 남고 무엇을 보는지 알 수 없어 지도가 되지 않는다.
  const HEATMAP_COMPACT_MAX_WIDTH = 520;

  function heatmapCompact(stage) {
    const width = finite(stage?.clientWidth);
    return width !== null && width > 0 && width < HEATMAP_COMPACT_MAX_WIDTH;
  }

  const HEATMAP_FONT_FAMILY = 'Inter, "IBM Plex Sans", SUIT, sans-serif';
  // 라벨 글자는 6px에서 20px 사이다. 정한 크기가 곧 그려지는 크기라(ECharts는 라벨을 줄이지
  // 않는다) 하한이 곧 화면에 나오는 가장 작은 글자다.
  const HEATMAP_MAX_LABEL_PX = 20;
  const HEATMAP_MIN_LABEL_PX = 6;
  // **좌우 여백은 칸 폭의 8%(최소 3px)씩이다.** 처음엔 3px 고정이었는데, 폭에 꼭 맞게 들어가는 라벨이 칸 가장자리에
  // 붙어 보였다 — 실측에서 라벨 폭이 칸 폭의 85%를 넘는 타일이 KR 8개·JP 14개였다. 비율로 두면 그 타일이 0개가 되고
  // 라벨은 KR 2개·JP 2개·US 3개만 줄어든다(KR 69→67, JP 137→135, US 268→265).
  // 안전 측면: ECharts는 트리맵 라벨의 기본 padding 5 때문에 글자 폭을 칸 폭보다 10px 줄여 자른다. heatmapSeriesBase가
  // padding을 0으로 두면 여백 1px부터 잘림 0이었으므로(KR·JP·US 실측), 최소 3px는 글꼴이 늦게 내려와 폭이 조금
  // 달라져도 받아낼 여유(2px)다. 글꼴을 바꾸면 다시 잰다.
  const HEATMAP_LABEL_MIN_SIDE_PAD_PX = 3;
  const HEATMAP_LABEL_SIDE_PAD_RATIO = 0.08;
  // 위아래는 잘리지 않고 넘칠 뿐이고 라벨이 세로 가운데라 양쪽이 같다. 실측에서 세로로 칸의 85%를 넘는 라벨은 없었다.
  const HEATMAP_LABEL_VERTICAL_PAD_PX = 3;
  // 칸 크기에 글자 크기가 따라붙는 정도. 완전 비례가 아니라 면적의 제곱근에
  // 완만하게 따라간다(면적을 그대로 쓰면 큰 칸만 남고 작은 칸은 전부 하한이 된다).
  const HEATMAP_SIZE_PER_ROOT_AREA = 0.105;
  // 섹터·산업 머리띠. 이름은 한 줄이고 이 띠 안에 들어가야 한다.
  const HEATMAP_HEADER_PX = 28;
  // 섹터 이름은 지도에서 가장 먼저 읽혀야 하는 글자다. 머리띠는 **섹터 평균 등락 색**이고(시가총액 가중), 그 색은 색 그대로
  // 남긴다 — 색이 바로 "이 섹터가 오늘 어땠는가"의 답이다. 예전에는 13px 흰 글자였고 섹터 경계가 종목 경계와 같은 얇은 선이라
  // 띠가 옆 종목 칸에 섞였다. 그래서 **색은 그대로 두고 경계를 색과 따로** 준다: 섹터 바깥선(아래 heatmapSectorOutlines)이
  // 등락 색과 무관한 무채색으로 섹터를 감싼다. 흰 글자는 등락 색 9단 모두에서 5.26:1 이상이다(heatmapColor).
  // 섹터 바깥선. 섹터끼리 떨어져 보이려고 굵고 진한 선을 두르면 지도가 한 장으로 안 읽히고 카드 여러 개로 갈라졌다
  // (사용자 피드백). 경계는 **간격의 위계**가 말한다 — 종목 사이 1px, 섹터 사이 그보다 넓게 — 바깥선은 기본으로 끈다.
  // 0보다 크면 그 투명도의 잉크색 선을 섹터마다 얹는다(heatmapSectorOutlines).
  const HEATMAP_SECTOR_OUTLINE_PX = 1;
  const HEATMAP_SECTOR_OUTLINE_ALPHA = 0;
  const HEATMAP_HEADER_MAX_LABEL_PX = 14;
  const HEATMAP_HEADER_MIN_LABEL_PX = 11;
  // 두 줄로 나눈 머리띠 이름의 하한. 한 줄보다 1px 작게 시작해 이 값까지만 내려간다.
  const HEATMAP_HEADER_TWO_LINE_MIN_LABEL_PX = 9;
  // 머리띠 글자의 왼쪽·오른쪽 여백. ECharts가 글자 폭을 이만큼 줄여 재므로 계획도 같은 값을 뺀다.
  const HEATMAP_HEADER_SIDE_PAD_PX = 6;
  // 섹터 사이의 틈. 종목 사이 틈(1px)보다 뚜렷하게 굵어야 "묶음"이 보인다. 틈에는 카드 배경이 비쳐 나온다.
  const HEATMAP_SECTOR_GAP_PX = 3;
  // 섹터를 감싸는 틀. 종목 칸을 한 묶음으로 두르는 띠와 같은 색이다.
  const HEATMAP_SECTOR_FRAME_PX = 1;
  // 세 줄까지 늘려도 실측에서 라벨이 하나도 늘지 않았다(JP 77 → 77).
  const HEATMAP_MAX_LABEL_LINES = 2;
  // 글자가 baseline 위아래로 차지하는 몫. 렌더된 줄 상자가 글꼴 크기의 약 1.2배다.
  const HEATMAP_ASCENT_RATIO = 0.95;
  const HEATMAP_DESCENT_RATIO = 0.25;
  const HEATMAP_LINE_HEIGHT = 1.3;
  // 정확한 타일 크기를 못 읽을 때의 추정. 실측 타일 폭 / √면적의 **최소**가 0.58이었다.
  // 라벨은 줄지만 잘리지는 않는다 — 틀린 숫자를 그리는 쪽으로는 실패하지 않는다.
  const HEATMAP_FALLBACK_WIDTH_RATIO = 0.58;

  /** 이 칸이 쓸 수 있는 최대 글자 크기.
   *
   *  크기를 "들어가기만 하면 최대"로 두면 **글자 길이가 크기를 정한다** — 작은
   *  칸이라도 티커가 짧으면(`MU`) 큰 칸과 같은 크기를 받아 칸에 비해 글자가 크다.
   *  대략적인 눈금: 250×160 → 20px(상한), 130×110 → 18px, 80×70 → 13px,
   *  60×45 → 11px, 35×28 → 9px, 25×20 → 8px, 15×12 → 7px, 10×8 → 6px(하한).
   */
  function heatmapSizeCeiling(width, height) {
    const area = Math.max(0, width) * Math.max(0, height);
    if (!area) return HEATMAP_MIN_LABEL_PX;
    const scaled = HEATMAP_MIN_LABEL_PX + HEATMAP_SIZE_PER_ROOT_AREA * Math.sqrt(area);
    return Math.max(HEATMAP_MIN_LABEL_PX, Math.min(HEATMAP_MAX_LABEL_PX, Math.round(scaled)));
  }

  /** 어절 경계로만 줄을 나눈다. 한 줄도 폭을 넘으면 실패로 돌려준다. */
  function wrapLabelLines(text, size, width, measure, maxLines) {
    const words = String(text).split(/\s+/).filter(Boolean);
    const lines = [];
    let current = "";
    for (const word of words) {
      const candidate = current ? `${current} ${word}` : word;
      if (!current || measure(candidate, size, true) <= width) current = candidate;
      else {
        lines.push(current);
        current = word;
      }
    }
    if (current) lines.push(current);
    if (!lines.length || lines.length > (maxLines || HEATMAP_MAX_LABEL_LINES)) return null;
    return lines.every((line) => measure(line, size, true) <= width) ? lines : null;
  }

  /** 이 타일에 실제로 들어가는 라벨을 **그리기 전에** 정한다. 안 들어가면 null이다.
   *
   *  `box`는 타일의 정확한 폭·높이다(heatmapTileSizes). 예전에는 그린 뒤 타일을 재서 라벨을
   *  얹고, Plotly가 넘치는 라벨을 통째로 축소하면 폭 예산을 깎아 다시 그렸다(4패스 + 비동기 대기).
   *  ECharts는 축소하지 않고 잘라 버리므로 처음부터 **들어가는 것만** 고르면 되고, 고른 값이 곧
   *  그려지는 값이라 수렴할 대상이 없다.
   *
   *  이름+등락 → 어절 줄바꿈+등락 → 이름만 순으로 물러난다. 어절 단위로 **잘라 내지는** 않는다:
   *  한 어절로 줄이면 KR에서 `Samsung…`이 12개사를, JP에서 `Mitsubishi…`가 7개사를 가리켜 다른
   *  회사 이름을 말하게 된다.
   */
  function heatmapLabelPlan(label, change, box, measure) {
    const text = String(label || "").trim();
    if (!text) return null;
    const boxWidth = finite(box && box.width) || 0;
    const sidePad = Math.max(HEATMAP_LABEL_MIN_SIDE_PAD_PX, boxWidth * HEATMAP_LABEL_SIDE_PAD_RATIO);
    const width = boxWidth - sidePad * 2;
    const height = (finite(box && box.height) || 0) - HEATMAP_LABEL_VERTICAL_PAD_PX * 2;
    if (width <= 0 || height <= 0) return null;
    const ceiling = Math.min(
      finite(box && box.maxSize) ?? HEATMAP_MAX_LABEL_PX,
      heatmapSizeCeiling(width, height),
    );
    const maxLines = finite(box && box.maxLines) ?? HEATMAP_MAX_LABEL_LINES;
    const tail = String(change || "");
    for (const withTail of [true, false]) {
      if (withTail && !tail) continue;
      const suffix = withTail ? tail : "";
      for (let size = ceiling; size >= HEATMAP_MIN_LABEL_PX; size -= 1) {
        const tailSize = Math.max(8, Math.round(size * 0.62));
        if (suffix && measure(suffix, tailSize, false) > width) continue;
        const lines = wrapLabelLines(text, size, width, measure, maxLines);
        if (!lines) continue;
        const nameStep = Math.round(size * HEATMAP_LINE_HEIGHT);
        const tailStep = Math.round(tailSize * HEATMAP_LINE_HEIGHT);
        const needed = size * (HEATMAP_ASCENT_RATIO + HEATMAP_DESCENT_RATIO)
          + (lines.length - 1) * nameStep + (suffix ? tailStep : 0);
        if (needed > height) continue;
        return { lines, size, suffix, tailSize, nameStep, tailStep };
      }
    }
    return null;
  }

  /** 계획을 ECharts 라벨 설정으로. 줄 간격도 우리가 정한다(글꼴 기본 간격에 맡기지 않는다). */
  function heatmapRichLabel(plan) {
    // `{스타일|글자}` 문법의 예약 문자는 지운다. 이름에 들어 있으면 라벨이 통째로 깨진다.
    const safe = (value) => String(value).replace(/[{}|]/g, "");
    const body = plan.lines.map((line) => `{n|${safe(line)}}`).join("\n");
    const tail = plan.suffix ? `\n{c|${safe(plan.suffix)}}` : "";
    return {
      formatter: body + tail,
      rich: {
        n: { fontSize: plan.size, lineHeight: plan.nameStep, fontWeight: 700, color: "#ffffff", fontFamily: HEATMAP_FONT_FAMILY },
        c: { fontSize: plan.tailSize, lineHeight: plan.tailStep, color: "#ffffff", fontFamily: HEATMAP_FONT_FAMILY },
      },
    };
  }

  let labelMeasureContext = null;
  function measureLabelWidth(text, size, bold) {
    if (labelMeasureContext === null) {
      const canvas = root.document?.createElement?.("canvas");
      labelMeasureContext = (canvas && canvas.getContext?.("2d")) || false;
    }
    if (!labelMeasureContext) return String(text).length * size * 0.62;
    labelMeasureContext.font = `${bold ? 700 : 400} ${size}px ${HEATMAP_FONT_FAMILY}`;
    return labelMeasureContext.measureText(String(text)).width;
  }

  const heatmapChangeText = (value) => {
    const change = finite(value);
    return change === null ? "" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;
  };

  /** 섹터 머리띠의 라벨 — **이름 + 섹터 평균 등락**. 안 들어가면 이름만, 그래도 안 들어가면 두 줄로, 그래도 안 되면 비운다.
   *
   *  섹터 이름은 한 줄일 때 11px, 두 줄일 때 10px 밑으로 내리지 않는다(읽혀야 한다). 두 줄은 머리띠 높이(28px)에 들어가는
   *  `Energy &` / `Chemicals` 같은 어절 줄바꿈이다. 이름이 좁은 섹터에서 통째로 비면 그 칸은 어느 섹터인지 알 수 없다.
   *  `width`는 머리띠 폭이다. ECharts는 글자 폭을 **좌우 padding과 틀 두께(양쪽)만큼** 줄여 재므로 그만큼과 잘림 여유 2px을 뺀다.
   */
  function heatmapHeaderPlan(name, change, width, measure) {
    const text = String(name || "").trim();
    if (!text) return null;
    const available = (finite(width) || 0) - HEATMAP_HEADER_SIDE_PAD_PX * 2 - HEATMAP_SECTOR_FRAME_PX * 2 - 2;
    if (available <= 0) return null;
    const tail = String(change || "");
    const tailGap = 8;
    for (let size = HEATMAP_HEADER_MAX_LABEL_PX; size >= HEATMAP_HEADER_MIN_LABEL_PX; size -= 1) {
      const nameWidth = measure(text, size, true);
      if (nameWidth > available) continue;
      const tailSize = Math.max(10, size - 2);
      const withTail = tail && nameWidth + tailGap + measure(tail, tailSize, false) <= available;
      // **줄 높이를 띠 높이와 같게** 둔다. 줄 높이가 글자 크기와 같으면 ECharts가 글자를 띠 맨 위에 붙여 그린다 —
      // `verticalAlign: "middle"`은 효과가 없었고(브라우저 실측: 글자 중심이 띠 중심보다 7px 위), 줄 상자가 띠만큼 높으면
      // 글자가 그 안의 세로 가운데에 앉는다.
      return { lines: [text], size, lineHeight: HEATMAP_HEADER_PX, tail: withTail ? tail : "", tailSize, tailGap };
    }
    // 한 줄에 안 들어가는 좁은 섹터: 두 줄로. 어절 경계로만 나누고 자르지 않는다.
    for (let size = HEATMAP_HEADER_MIN_LABEL_PX - 1; size >= HEATMAP_HEADER_TWO_LINE_MIN_LABEL_PX; size -= 1) {
      const lines = wrapLabelLines(text, size, available, measure, 2);
      // 두 줄은 줄 높이를 띠 높이의 절반으로 — 두 줄이 정확히 띠를 채워 위아래 여백이 같다.
      if (lines && lines.length === 2) return { lines, size, lineHeight: HEATMAP_HEADER_PX / 2, tail: "", tailSize: size, tailGap };
    }
    return null;
  }

  function heatmapHeaderLabel(plan) {
    const safe = (value) => String(value).replace(/[{}|]/g, "");
    const body = plan.lines.map((line) => `{n|${safe(line)}}`).join("\n");
    return {
      formatter: body + (plan.tail ? `{c|${safe(plan.tail)}}` : ""),
      rich: {
        n: { fontSize: plan.size, lineHeight: plan.lineHeight, fontWeight: 700, color: "#ffffff", fontFamily: HEATMAP_FONT_FAMILY },
        // 평균 등락은 이름보다 한 걸음 물러난 톤이다.
        // 등락도 같은 줄 높이여야 이름과 같은 세로 위치에 앉는다.
        c: { fontSize: plan.tailSize, lineHeight: plan.lineHeight, fontWeight: 500, color: "rgba(255, 255, 255, 0.78)", fontFamily: HEATMAP_FONT_FAMILY, padding: [0, 0, 0, plan.tailGap] },
      },
    };
  }

  /** heatmapNodes의 평면 배열을 ECharts가 받는 중첩 트리로. 자료 모양 변환일 뿐이다. */
  function heatmapTree(nodes) {
    const byId = new Map();
    nodes.ids.forEach((id, index) => {
      byId.set(id, {
        id,
        name: nodes.labels[index],
        value: nodes.values[index],
        children: [],
        itemStyle: { color: nodes.colors[index] },
        _row: nodes.customdata[index],
        _change: nodes.changes[index],
      });
    });
    const roots = [];
    nodes.ids.forEach((id, index) => {
      const parent = nodes.parents[index];
      const node = byId.get(id);
      if (parent && byId.has(parent)) byId.get(parent).children.push(node);
      else roots.push(node);
    });
    const prune = (node) => {
      if (!node.children.length) delete node.children;
      else node.children.forEach(prune);
    };
    roots.forEach(prune);
    return roots;
  }

  /** 시리즈 설정 — **진짜 차트와 배치 선계산이 같은 것을 쓴다.** 머리띠 높이·테두리·간격이 다르면
   *  배치가 달라져 계획한 라벨 폭이 어긋난다. `depth`는 뿌리에서 몇 겹까지 그리는지(잎 포함). */
  function heatmapSeriesBase(depth) {
    return {
      type: "treemap",
      roam: false,
      nodeClick: false,
      // 깊이 상한에서 잎이 된 그룹 앞에 ECharts가 `▶ `를 붙인다(기본값). 그 자리만큼 라벨 폭이 줄어 계획한 폭과 어긋나고
      // 이름이 잘린다. 들어갈 수 있다는 안내는 위 경로 버튼의 힌트가 이미 한다.
      drillDownIcon: "",
      breadcrumb: { show: false },
      leafDepth: depth,
      width: "100%",
      height: "100%",
      top: 0, left: 0, right: 0, bottom: 0,
      squareRatio: 1,
      // 종목 칸: 테두리 없이 1px 틈만 둔다. 틈은 부모(섹터)의 borderColor — 섹터 색 — 로 비쳐 가는 선이 된다.
      itemStyle: { borderColor: "transparent", borderWidth: 0, gapWidth: 1 },
      // 라벨은 노드마다 heatmapPlanLabels가 정한다. 여기서 자르거나 줄바꿈하지 않는다.
      // **padding 0.** 트리맵 라벨의 기본 padding은 5라서 ECharts가 글자에 쓸 수 있는 폭을 칸 폭보다 양쪽 5px씩
      // 줄인다 — 계획한 폭이 넉넉히 들어가는데도 `...`로 잘렸다(브라우저 실측: 여백 5px 이하에서 잘림 다수).
      label: { show: false, position: "inside", padding: 0, color: "#ffffff", fontFamily: HEATMAP_FONT_FAMILY },
      upperLabel: { show: true, height: HEATMAP_HEADER_PX, padding: [0, HEATMAP_HEADER_SIDE_PAD_PX, 0, HEATMAP_HEADER_SIDE_PAD_PX], color: "#ffffff", fontFamily: HEATMAP_FONT_FAMILY, overflow: "truncate" },
      levels: [
        // 보이지 않는 뿌리는 머리띠를 갖지 않는다 — 안 그러면 맨 위 26px이 빈 띠로 남는다.
        // 섹터 사이 틈. 카드 배경이 비쳐 나와 라이트·다크 어느 쪽에서도 섹터가 갈라져 보인다.
        { itemStyle: { borderWidth: 0, gapWidth: HEATMAP_SECTOR_GAP_PX }, upperLabel: { show: false } },
        // 섹터 틀. 종목 칸을 한 묶음으로 두르고 위에 머리띠가 얹힌다. 색은 노드마다 자기 섹터 색을 준다.
        { itemStyle: { borderWidth: HEATMAP_SECTOR_FRAME_PX, gapWidth: 1 } },
      ],
    };
  }

  /** 타일의 정확한 크기를 그리기 **전에** 얻는다.
   *
   *  squarify는 자료와 크기의 순수 함수라, DOM 없는 ssr 인스턴스에 같은 시리즈 설정으로 배치만
   *  시키면 진짜 차트와 같은 좌표가 나온다. 예전에는 Plotly가 그린 SVG를 읽었다
   *  (`__data__`·`_fullLayout`) — Plotly가 무엇을 했는지 알아내려는 역공학이었다. 이건 **우리가 그릴
   *  것의 크기를 미리 묻는** 것이다.
   *
   *  **배치를 읽는 경로(`getModel().getSeriesByIndex(0).getData().tree`의 `getLayout()`)는 ECharts의
   *  공개 API가 아니다.** 그래서 (1) 벤더 파일이 정확 고정 버전이고, (2) briefing-visuals.test.js가
   *  실제 벤더 번들로 이 함수를 매번 확인하며(ECharts를 올리면 여기서 먼저 걸린다), (3) 읽지 못하면
   *  null을 돌려주고 호출자가 추정으로 물러난다 — 틀린 크기를 조용히 내주지 않는다.
   *  ssr 인스턴스는 dispose하지 않으면 Node 프로세스가 끝나지 않는다(6.1.0). 반드시 finally에서 푼다.
   */
  function heatmapTileSizes(echarts, series, width, height) {
    if (!echarts || typeof echarts.init !== "function" || !(width > 0) || !(height > 0)) return null;
    let chart = null;
    try {
      chart = echarts.init(null, null, { renderer: "svg", ssr: true, width, height });
      chart.setOption({ animation: false, series: [series] });
      const data = chart.getModel().getSeriesByIndex(0).getData();
      const rects = new Map();
      for (let index = 0; index < data.count(); index += 1) {
        const node = data.tree.getNodeByDataIndex(index);
        const id = node.getModel().get("id");
        const layout = node.getLayout();
        // 깊이 상한 아래의 노드는 그려지지 않는다. 배치가 아예 없거나 면적(area)만 남아 있어
        // 폭이 없다 — 건너뛴다. **그려진 노드**의 값이 하나라도 깨졌으면 전부 못 믿는다.
        if (id == null || !layout || layout.width === undefined) continue;
        if (![layout.x, layout.y, layout.width, layout.height].every(Number.isFinite)) return null;
        rects.set(String(id), { x: layout.x, y: layout.y, width: layout.width, height: layout.height });
      }
      return rects.size ? rects : null;
    } catch (_) {
      return null;
    } finally {
      if (chart) chart.dispose();
    }
  }

  /** 정확한 크기를 못 읽을 때의 추정 타일. 좌표는 모르므로 머리띠 클릭 판정은 꺼진다. */
  function heatmapFallbackSize(value, total, width, height) {
    const area = total > 0 ? (Math.max(0, value) / total) * width * height : 0;
    const side = Math.sqrt(area);
    return { x: null, y: null, width: side * HEATMAP_FALLBACK_WIDTH_RATIO, height: side };
  }

  /** 트리의 모든 노드에 라벨을 계획해 붙이고, 머리띠 클릭 판정에 쓸 좌표를 돌려준다.
   *
   *  섹터·산업 **머리띠**(자식을 함께 그리는 부모)와 **깊이 상한에서 잎이 된 그룹**(좁은 화면의
   *  `Materials`)도 같은 계획기를 쓴다. 안 그러면 ECharts 기본 처리가 `▶ M...`처럼 자른다.
   *  안 들어가는 이름은 비운다 — 자르지 않는다.
   */
  function heatmapPlanLabels(roots, context) {
    const { rects, total, width, height, depth, measure } = context;
    const headers = [];
    const rectOf = (node) => (rects && rects.get(node.id)) || heatmapFallbackSize(node.value, total, width, height);
    const walk = (node, level) => {
      const rect = rectOf(node);
      const hasChildren = Array.isArray(node.children) && node.children.length > 0;
      if (hasChildren && level < depth) {
        // 틀·틈은 투명이다 — 카드 배경이 비쳐 지도 전체가 같은 색 선으로 나뉜 한 장으로 읽힌다. 머리띠는 borderColor가 아니라
        // 라벨 배경으로 칠한다(트리맵은 띠·틀·틈을 borderColor 한 색으로 칠해서, 그러면 띠 색과 틈 색을 따로 못 준다).
        node.itemStyle = Object.assign({}, node.itemStyle, { borderColor: "transparent" });
        const plan = heatmapHeaderPlan(node.name, heatmapChangeText(node._change), rect.width, measure);
        // 띠 색은 섹터 평균 등락 색 그대로다(시가총액 가중). 라벨 상자가 띠 전체를 덮는다(폭·높이를 트리맵이 채운다).
        const band = node.itemStyle.color;
        node.upperLabel = plan
          ? Object.assign({ show: true, height: HEATMAP_HEADER_PX, backgroundColor: band }, heatmapHeaderLabel(plan))
          // 머리띠는 남기고 글자만 비운다. `show: false`면 띠 자체가 사라져 자식이 그 자리를 먹는다.
          // 빈 문자열("")은 서식이 없는 것으로 읽혀 기본 이름이 `Steels ...`처럼 잘려 그려진다(브라우저 실측) —
          // 공백 한 글자로 "글자 없음"을 명시한다.
          : { show: true, height: HEATMAP_HEADER_PX, formatter: " ", backgroundColor: band };
        if (finite(rect.x) !== null && finite(rect.y) !== null) {
          headers.push({ id: node.id, x: rect.x, y: rect.y, width: rect.width, height: HEATMAP_HEADER_PX });
        }
        node.children.forEach((child) => walk(child, level + 1));
        return;
      }
      const plan = heatmapLabelPlan(node.name, heatmapChangeText(node._change), { width: rect.width, height: rect.height }, measure);
      node.label = plan ? Object.assign({ show: true }, heatmapRichLabel(plan)) : { show: false };
      // **마우스를 올려도 라벨이 그대로여야 한다.** 올린 칸은 별도의 강조 상태(emphasis)로 그려지는데 그 상태의
      // 라벨은 시리즈 기본(show: false)을 따라 통째로 꺼진다 — 기업명이 사라지는 것으로 보였다(브라우저 실측).
      // 강조 상태의 표시 여부를 평상시와 같게 못 박고, 서식(formatter·rich)은 평상시 것을 그대로 물려받는다.
      node.emphasis = { label: { show: Boolean(plan) } };
      // 깊이 상한에서 잎이 된 섹터(좁은 화면)는 틀이 있는 레벨이라 자기 색 틀을 준다 — 안 주면 시리즈 기본(투명)이 아니라 어두운 링이 생긴다.
      if (hasChildren) node.itemStyle = Object.assign({}, node.itemStyle, { borderColor: "transparent" });
    };
    roots.forEach((node) => walk(node, 1));
    return headers;
  }

  /** 클릭 좌표가 어느 머리띠 위인가. ECharts는 머리띠를 눌러도 부모가 아니라 보이지 않는 뿌리를 알려 준다. */
  function heatmapHeaderAt(headers, x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return "";
    const hit = (headers || []).find((header) =>
      x >= header.x && x <= header.x + header.width && y >= header.y && y <= header.y + header.height);
    return hit ? hit.id : "";
  }

  /** 섹터 바깥선 — 등락 색과 **따로** 그리는 무채색 테두리.
   *
   *  트리맵은 머리띠·틀·틈을 모두 한 색(borderColor)으로 칠해서, 띠를 섹터 색으로 두면 테두리를 따로 줄 수 없다. 그래서
   *  배치 선계산이 준 섹터 사각형 위에 `graphic` 사각형(채움 없음, 선만)을 얹는다. 클릭·hover는 통과한다(`silent`).
   *  선은 사각형 안쪽으로 그려 이웃 섹터 쪽 틈(4px)을 침범하지 않는다. 좌표를 못 읽은 경우(추정으로 물러남)엔 없다.
   *  색은 잉크 토큰이라 라이트에선 어둡고 다크에선 밝다 — 어느 쪽이든 섹터 색과도 카드 배경과도 갈린다.
   */
  function heatmapSectorOutlines(roots, rects, color) {
    if (!rects || !color) return [];
    const half = HEATMAP_SECTOR_OUTLINE_PX / 2;
    return (roots || []).map((node) => rects.get(node.id)).filter(Boolean).map((rect) => ({
      type: "rect",
      silent: true,
      z: 20,
      shape: { x: rect.x + half, y: rect.y + half, width: Math.max(0, rect.width - HEATMAP_SECTOR_OUTLINE_PX), height: Math.max(0, rect.height - HEATMAP_SECTOR_OUTLINE_PX) },
      style: { fill: "none", stroke: color, lineWidth: HEATMAP_SECTOR_OUTLINE_PX },
    }));
  }

  /** 머리띠와 종목 칸 사이의 가는 구분선 — 카드 배경색 1px.
   *
   *  띠가 섹터 색 그대로라 그 아래 종목 칸과 맞붙으면 한 덩어리로 보인다. 종목 사이 틈(1px)과 **같은 색 같은 굵기**의 선을 띠 아래에
   *  두면 지도 전체가 한 가지 선으로 나뉜 한 장으로 읽히면서도 띠가 칸과 갈린다. 좌표는 머리띠 클릭 판정에 쓰는 것과 같다.
   */
  function heatmapHeaderRules(headers, color) {
    if (!color) return [];
    return (headers || []).map((header) => ({
      type: "rect",
      silent: true,
      z: 21,
      shape: { x: header.x + HEATMAP_SECTOR_FRAME_PX, y: header.y + header.height - 1, width: Math.max(0, header.width - HEATMAP_SECTOR_FRAME_PX * 2), height: 1 },
      style: { fill: color },
    }));
  }

  /** `#rgb`·`#rrggbb`에 투명도를. 그 밖의 형식(rgb() 등)은 그대로 돌려준다. */
  function heatmapWithAlpha(color, alpha) {
    const match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(color).trim());
    if (!match) return color;
    const hex = match[1].length === 3 ? match[1].replace(/./g, (c) => c + c) : match[1];
    const value = parseInt(hex, 16);
    return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
  }

  /** 카드 배경색. 머리띠 구분선이 종목 사이 틈(카드가 비쳐 나온다)과 같은 색이어야 한다. */
  function heatmapSurfaceColor(element) {
    const value = element ? getComputedStyle(element).backgroundColor : "";
    return value && value !== "rgba(0, 0, 0, 0)" && value !== "transparent" ? value : "";
  }

  function heatmapTooltipTheme() {
    const css = getComputedStyle(document.documentElement);
    const token = (name, fallback) => {
      const value = css.getPropertyValue(name).trim();
      return value && !/^(var|color-mix)\(/i.test(value) ? value : fallback;
    };
    return {
      backgroundColor: token("--folio-surface-dark", "#101829"),
      borderColor: token("--folio-border-strong", "#c5ccd8"),
      color: token("--folio-ink-inverse", "#ffffff"),
      // 섹터 바깥선(기본 꺼짐). 라이트에선 어두운 잉크, 다크에선 밝은 잉크다.
      outline: HEATMAP_SECTOR_OUTLINE_ALPHA > 0 ? heatmapWithAlpha(token("--folio-ink", "#07111f"), HEATMAP_SECTOR_OUTLINE_ALPHA) : "",
    };
  }

  function createRequestGate() {
    let current = 0;
    return {
      next() { current += 1; return current; },
      isCurrent(token) { return token === current; },
    };
  }

  function controlButton(label, selected, dataName, value = label) {
    return `<button type="button" data-${escapeHtml(dataName)}="${escapeHtml(value)}" aria-pressed="${selected}">${escapeHtml(label)}</button>`;
  }

  function exportControlSelector() {
    return ".briefing-inline-view-controls,.briefing-price-controls,.briefing-visual-view-toggle";
  }

  function fitChartWhenSized(chart, stage, options = {}) {
    const schedule = options.schedule
      || root.requestAnimationFrame?.bind(root)
      || ((callback) => setTimeout(callback, 0));
    const ResizeObserverClass = options.ResizeObserverClass || root.ResizeObserver;
    let disposed = false;
    let observer = null;
    const fit = () => {
      if (disposed || !stage?.clientWidth) return false;
      // autoSize 미사용: 컨테이너 폭이 잡히면(모달 열림/리사이즈) 차트를 실제 폭으로 맞춘다.
      chart.resize(stage.clientWidth, stage.clientHeight || 360);
      chart.timeScale().fitContent();
      return true;
    };
    schedule(() => schedule(fit));
    if (typeof ResizeObserverClass === "function") {
      observer = new ResizeObserverClass(() => {
        if (!fit()) return;
        observer?.disconnect();
        observer = null;
      });
      observer.observe(stage);
    }
    return () => {
      disposed = true;
      observer?.disconnect();
      observer = null;
    };
  }

  function recommendationPlacement(recommendation, recommendations) {
    if (recommendation?.placement?.sectionRole) return recommendation.placement;
    const market = String(recommendation?.market || "").toUpperCase();
    if (recommendation?.role === "market_summary") {
      return { market, sectionRole: "market_flow", order: recommendation.variant === "treemap_heatmap" ? 2 : 1 };
    }
    if (recommendation?.role === "leading_company") {
      const leaders = (recommendations || []).filter((row) =>
        String(row.market || "").toUpperCase() === market && row.role === "leading_company"
      );
      const ordinal = Math.max(1, leaders.findIndex((row) => row === recommendation || row.snapshotId === recommendation.snapshotId) + 1);
      return { market, sectionRole: "leading_company", ordinal, order: 1 };
    }
    return {};
  }

  function shouldRenderTrend(snapshot) {
    if (!snapshot) return false;
    return (snapshot.series || []).some((series) => {
      const normalized = normalizePriceSubject(series);
      return [...normalized.intraday.points, ...normalized.daily.points]
        .filter((point) => finite(point.close) !== null).length >= 2;
    });
  }

  function viewCopy(mode) {
    return mode === "current"
      ? { heading: "현재 시장", description: "최신 REST 일봉이며 실시간 체결가가 아닙니다." }
      : { heading: "생성 당시 시장", description: "브리핑 생성 시 저장된 종가 스냅샷입니다." };
  }

  function viewAction(mode, action, currentRequestPending = false) {
    if (action === "select_snapshot") {
      return mode !== "snapshot" || currentRequestPending ? "render_snapshot" : "noop";
    }
    if (action === "select_current") return mode === "current" || currentRequestPending ? "noop" : "fetch_current";
    return "noop";
  }

  function comparisonSummary(comparison) {
    const rows = [];
    for (const item of comparison?.priceChanges || []) {
      const change = finite(item.changePct);
      if (change === null) continue;
      rows.push({ kind: "price", label: item.ticker || item.label || "종목", value: `${change >= 0 ? "+" : ""}${change.toFixed(2)}%` });
    }
    for (const item of comparison?.sectorRankChanges || []) {
      if (!item.generatedRank || !item.currentRank) continue;
      const rankChange = finite(item.rankChange) || 0;
      const direction = rankChange > 0 ? `▲${rankChange}` : rankChange < 0 ? `▼${Math.abs(rankChange)}` : "—";
      rows.push({ kind: "rank", label: item.sector || "섹터", value: `${item.generatedRank}위 → ${item.currentRank}위 (${direction})` });
    }
    return rows;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]));
  }

  function formatNumber(value, currency) {
    const number = finite(value);
    if (number === null) return "—";
    return new Intl.NumberFormat("ko-KR", {
      maximumFractionDigits: number >= 1000 ? 0 : 2,
      style: currency ? "currency" : "decimal",
      currency: currency || undefined,
    }).format(number);
  }

  const SINGLE_VISUAL_MARKETS = new Set(["US", "KR", "EUROPE", "JP"]);

  function normalizeVisualMarket(value) {
    const market = String(value || "").toUpperCase();
    return SINGLE_VISUAL_MARKETS.has(market) ? market : "BOTH";
  }

  function formatPriceValue(value, snapshot, subject) {
    const ticker = String(subject?.ticker || "");
    const isIndex = snapshot?.role === "market_summary" || ticker.startsWith("^");
    if (isIndex) return formatNumber(value);
    const currency = String(snapshot?.currency || "").toUpperCase();
    if (currency === "USD") return `$${formatNumber(value)}`;
    if (currency === "KRW") return `₩${formatNumber(value)}`;
    return formatNumber(value, currency || undefined);
  }

  function metaText(snapshot) {
    const coverage = snapshot.coverage || {};
    const ratio = finite(coverage.ratio);
    const coverageText = ratio === null ? "확인 불가" : `${Math.round(ratio * 100)}%`;
    return `${snapshot.asOf || snapshot.marketSessionDate || "기준일 없음"} · 저장 자료 범위 ${coverageText}`;
  }

  function cardShell(snapshot, title, kind) {
    const id = `brief-visual-${String(snapshot.id || Math.random()).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
    const card = document.createElement("article");
    card.className = `briefing-visual-card briefing-visual-${kind}`;
    card.dataset.visualExportId = id;
    card.dataset.market = normalizeVisualMarket(snapshot.market);
    card.innerHTML = `
      <header class="briefing-visual-header">
        <div><span class="briefing-visual-kicker">${escapeHtml(snapshot.market || "MARKET")}</span><h3>${escapeHtml(title)}</h3></div>
        <span class="briefing-visual-freshness" data-state="${escapeHtml(snapshot.freshness || "unavailable")}">${escapeHtml(snapshot.type === "story_share_series" ? "수집 기사 기준" : ({ close_snapshot: "종가 기준", snapshot: "저장 시점", delayed: "지연 자료", stale: "오래된 자료", unavailable: "자료 없음" }[snapshot.freshness] || "저장 자료"))}</span>
      </header>
      <p class="briefing-visual-meta">${escapeHtml(metaText(snapshot))}</p>
      <details class="briefing-visual-data-details"><summary>자료 정보</summary><p>${escapeHtml(snapshot.provider || "제공처 미상")} · 자료 범위는 수집 대상 기준이며 사실의 정확성이나 모든 거래일 확보를 뜻하지 않습니다.</p></details>
      <div class="briefing-visual-stage" role="img" aria-label="${escapeHtml(title)}"></div>`;
    return { id, card, stage: card.querySelector(".briefing-visual-stage") };
  }

  function unavailableCard(snapshot, title, message) {
    const { card, stage } = cardShell(snapshot, title, "unavailable");
    stage.innerHTML = `<p>${escapeHtml(message)}</p>`;
    return card;
  }

  function chartTheme() {
    const css = getComputedStyle(document.documentElement);
    return {
      text: css.getPropertyValue("--folio-ink-muted").trim() || "#44505f",
      grid: css.getPropertyValue("--folio-border").trim() || "#dde2e9",
      background: css.getPropertyValue("--folio-surface-clean").trim() || "#ffffff",
    };
  }

  function appendComparison(card, comparison) {
    const rows = comparisonSummary(comparison);
    if (!rows.length) return;
    const footer = document.createElement("div");
    footer.className = "briefing-visual-comparison";
    footer.innerHTML = `<b>생성 당시 대비</b>${rows.slice(0, 6).map((row) => `<span data-kind="${row.kind}">${escapeHtml(row.label)} <strong>${escapeHtml(row.value)}</strong></span>`).join("")}`;
    card.append(footer);
  }

  function renderTrend(snapshot, title, variant, comparison, options = {}) {
    if (!shouldRenderTrend(snapshot)) {
      // 본문이 부른 이름을 어느 기업인지 확정하지 못한 경우와, 기업은 알지만 가격이
      // 없는 경우는 원인이 다르다. 같은 문구로 덮으면 읽는 사람이 무엇을 확인해야
      // 하는지 알 수 없다.
      const subject = snapshot?.subject || {};
      if (subject.unresolved) {
        const name = subject.label ? `— ${subject.label}` : "";
        return unavailableCard(snapshot, title, `본문이 언급한 기업을 특정하지 못해 차트를 그리지 못했습니다 ${name}`.trim());
      }
      return unavailableCard(snapshot, title, "추세를 그리기에 저장된 데이터 포인트가 충분하지 않습니다.");
    }
    const LC = root.LightweightCharts;
    if (!LC?.createChart) return unavailableCard(snapshot, title, "가격 차트 라이브러리를 불러오지 못했습니다.");
    const { id, card } = cardShell(snapshot, title, "trend");
    card.classList.add("briefing-price-card");
    const originalStage = card.querySelector(".briefing-visual-stage");
    const controls = document.createElement("div");
    controls.className = "briefing-price-controls";
    originalStage.before(controls);
    const periods = availablePeriods(snapshot);
    const state = initialPriceState(snapshot, options.defaultPeriod);
    let chart = null;
    let stopAutoFit = null;

    function draw() {
      stopAutoFit?.();
      stopAutoFit = null;
      if (chart) {
        try { chart.remove(); } catch (_) {}
        chart = null;
      }
      const subject = (snapshot.series || []).find((row) => row.ticker === state.selectedTicker) || snapshot.series?.[0];
      const selected = periodPoints(subject, state.period, snapshot.asOf || snapshot.marketSessionDate);
      const summary = priceSummaryForPeriod(subject, state.period, selected.points);
      const positive = finite(summary.change) !== null && summary.change >= 0;
      const color = positive ? "#159447" : "#d64545";
      const label = subject?.label || subject?.ticker || title;
      const changeText = summary.change === null
        ? "변동 확인 불가"
        : `${summary.change >= 0 ? "+" : ""}${formatNumber(summary.change)} (${summary.changePct >= 0 ? "+" : ""}${summary.changePct.toFixed(2)}%)`;
      card.querySelector(".briefing-visual-header h3").textContent = label;
      let valueArea = card.querySelector(".briefing-price-summary");
      if (!valueArea) {
        valueArea = document.createElement("div");
        valueArea.className = "briefing-price-summary";
        card.querySelector(".briefing-visual-header").insertAdjacentElement("afterend", valueArea);
      }
      valueArea.innerHTML = `<strong class="briefing-price-value">${escapeHtml(formatPriceValue(summary.close, snapshot, subject))}</strong><span class="briefing-price-change" data-direction="${positive ? "up" : "down"}">${escapeHtml(changeText)}</span>`;
      const indexButtons = (snapshot.series || []).length > 1
        ? `<div class="briefing-index-strip" role="group" aria-label="지수 선택">${snapshot.series.map((row) => `<button type="button" data-ticker="${escapeHtml(row.ticker)}" aria-pressed="${row.ticker === state.selectedTicker}"><span>${escapeHtml(row.label || row.ticker)}</span><small>${escapeHtml(row.ticker)}</small></button>`).join("")}</div>`
        : "";
      controls.innerHTML = `${indexButtons}<div class="briefing-chart-controls"><div role="group" aria-label="차트 기간">${periods.map((period) => controlButton(period, period === state.period, "period")).join("")}</div><div role="group" aria-label="차트 유형">${controlButton("라인", state.chartType === "line", "chart-type", "line")}${controlButton("캔들", state.chartType === "candle", "chart-type", "candle")}</div></div>`;
      controls.querySelectorAll("[data-ticker]").forEach((button) => button.addEventListener("click", () => { state.selectedTicker = button.dataset.ticker; draw(); }));
      controls.querySelectorAll("[data-period]").forEach((button) => button.addEventListener("click", () => { state.period = button.dataset.period; draw(); }));
      controls.querySelectorAll("[data-chart-type]").forEach((button) => button.addEventListener("click", () => { state.chartType = button.dataset.chartType; draw(); }));
      controls.querySelectorAll('[role="group"]').forEach((group) => group.addEventListener("keydown", (event) => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        const buttons = [...group.querySelectorAll("button:not(:disabled)")];
        const index = buttons.indexOf(document.activeElement);
        if (index < 0 || !buttons.length) return;
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        const next = buttons[(index + direction + buttons.length) % buttons.length];
        next.focus();
        next.click();
      }));
      originalStage.innerHTML = "";
      originalStage.classList.add("briefing-price-stage");
      const values = lightweightRows(selected.points, state.chartType, selected.interval);
      if (values.length < 2) {
        originalStage.innerHTML = `<p class="briefing-visual-empty">${state.period === "1D" ? "1D 5분봉 데이터가 없습니다." : "선택한 기간의 가격 데이터가 부족합니다."}</p>`;
        chartRecords.delete(id);
        return;
      }
      const pointByTime = new Map();
      values.forEach((row, index) => {
        const original = selected.points[index] || {};
        // 5분봉만 봉 끝으로 옮긴다(`intervalMinutes` 주석). 시간봉·일봉은 저장된 시각 그대로다.
        const displayTime = selected.interval === "5m"
          ? intradayDisplayTime(original.time || row.time, selected.interval)
          : (original.time || row.time);
        pointByTime.set(String(row.time), { ...original, time: displayTime, close: original.close ?? row.value ?? row.close });
      });
      const theme = chartTheme();
      chart = LC.createChart(originalStage, {
        height: 360,
        width: originalStage.clientWidth || 0,
        layout: { background: { type: "solid", color: theme.background }, textColor: theme.text, attributionLogo: true },
        grid: { vertLines: { visible: false }, horzLines: { color: theme.grid, style: LC.LineStyle?.Dotted ?? 1 } },
        rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
        // 오른쪽 여백은 **한 봉 너비**다. 봉이 수십 개면 눈에 띄지 않지만 주간 `1W`처럼
        // 다섯 개뿐이면 `fitContent()`가 자리를 1/6이나 비워 두어(실측 462px 중 116px)
        // 그 주가 수요일에 끝난 것처럼 보인다. 봉이 적을 때만 여백을 없앤다.
        // 축의 시각 표시는 **기간 이름이 아니라 실제 봉 단위**가 정한다. `1W`가 시간봉으로
        // 내려오는데 날짜만 찍으면 하루에 봉 예닐곱 개가 같은 라벨 아래 겹쳐 선다.
        timeScale: { borderVisible: false, rightOffset: values.length <= 8 ? 0 : 1, barSpacing: state.period === "1D" ? 6 : 8, minBarSpacing: 2, timeVisible: isIntradayInterval(selected.interval), secondsVisible: false },
        localization: { locale: "ko-KR", dateFormat: "yyyy-MM-dd", timeFormatter: lightweightTimeLabel },
        crosshair: { mode: LC.CrosshairMode?.Normal ?? 0 },
        handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
        handleScale: { axisPressedMouseMove: false, mouseWheel: false, pinch: true },
      });
      const seriesApi = state.chartType === "candle"
        ? chart.addSeries(LC.CandlestickSeries, { upColor: "#159447", downColor: "#d64545", borderVisible: false, wickUpColor: "#159447", wickDownColor: "#d64545" })
        : chart.addSeries(LC.AreaSeries, { lineColor: color, topColor: `${color}38`, bottomColor: `${color}05`, lineWidth: 3, priceLineVisible: false, lastValueVisible: true });
      seriesApi.setData(values);
      const tooltip = document.createElement("div");
      tooltip.className = "briefing-price-tooltip";
      tooltip.hidden = true;
      originalStage.appendChild(tooltip);
      chart.subscribeCrosshairMove((param) => {
        const stageRect = originalStage.getBoundingClientRect();
        const point = param?.point;
        const seriesPoint = param?.seriesData?.get(seriesApi);
        if (!point || !seriesPoint || point.x < 0 || point.y < 0 || point.x > stageRect.width || point.y > stageRect.height) {
          tooltip.hidden = true;
          return;
        }
        const sourcePoint = pointByTime.get(String(seriesPoint.time)) || {
          time: seriesPoint.time,
          close: seriesPoint.close ?? seriesPoint.value,
        };
        tooltip.innerHTML = hoverTooltipContent(subject, state.period, sourcePoint, snapshot, selected.points);
        const tooltipWidth = tooltip.offsetWidth || 160;
        const tooltipHeight = tooltip.offsetHeight || 78;
        const left = Math.min(Math.max(8, point.x + 14), Math.max(8, stageRect.width - tooltipWidth - 8));
        const top = Math.min(Math.max(8, point.y - tooltipHeight - 12), Math.max(8, stageRect.height - tooltipHeight - 8));
        tooltip.style.transform = `translate(${left}px, ${top}px)`;
        tooltip.hidden = false;
      });
      stopAutoFit = fitChartWhenSized(chart, originalStage);
      chartRecords.set(id, {
        kind: "lightweight",
        chart,
        title: label,
        element: originalStage,
        snapshot,
        selectedTicker: state.selectedTicker,
        period: state.period,
        chartType: state.chartType,
        cleanup: () => stopAutoFit?.(),
      });
    }

    draw();
    appendComparison(card, comparison);
    return card;
  }

  // ── 주간 그림 ─────────────────────────────────────────────────────────────
  //
  // `renderWeeklyFlow`는 이제 **옛 저장본 전용**이다. 대표 지수를 함께 겹쳐 주초 대비
  // %로 그리고 기간 버튼이 없다(그 저장본이 가진 것이 그 주 5점뿐이라 기간이 곧 그 주다).
  // 자기 일봉 이력을 담은 새 저장본은 `renderTrend`가 일간과 **같은 차트**로 그리고
  // 기본 구간만 `1W`로 둔다(`hasStoredDailyHistory`가 둘을 가른다). 저장 시각자료는
  // 불변이므로 이 함수를 지우면 옛 주간 보고서의 그림이 사라진다.

  // 색은 이 파일이 이미 쓰는 `PALETTE`를 그대로 쓴다. 차트는 canvas에 그려 CSS 변수를
  // 못 읽으므로 hex가 필요한데, 목록을 따로 두면 두 그림이 서서히 다른 색이 된다.

  /** 캡션. 세 그림이 같은 문장으로 같은 구간을 말한다 — 그림마다 기간이 다르면
   *  한 보고서 안에서 세 그림이 세 주를 말하게 된다. */
  function weeklyCaption(snapshot, body) {
    const period = snapshot.window || {};
    const range = snapshot.weekLabel || `${period.weekStart || ""}~${period.weekEnd || ""}`;
    return `${range} · ${body}`;
  }

  function appendCaption(card, text) {
    const caption = document.createElement("p");
    caption.className = "briefing-visual-caption";
    caption.textContent = text;
    card.append(caption);
    return caption;
  }

  function signedPercent(value) {
    // `finite()`를 그대로 쓰지 않는다 — `Number(null)`이 0이라 결측이 "0.00%"가 되어
    // "안 움직였다"는 사실로 둔갑한다. 모르는 것은 모른다고 적는다.
    if (value === null || value === undefined || value === "") return "—";
    const number = finite(value);
    if (number === null) return "—";
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
  }

  function renderWeeklyFlow(snapshot, title) {
    const series = (snapshot.series || []).filter((row) => (row.points || []).length >= 2);
    if (!series.length) {
      return unavailableCard(snapshot, title, "그 주 지수 종가가 충분히 저장되지 않았습니다.");
    }
    const LC = root.LightweightCharts;
    if (!LC?.createChart) return unavailableCard(snapshot, title, "가격 차트 라이브러리를 불러오지 못했습니다.");
    const { id, card, stage } = cardShell(snapshot, title, "trend");
    card.classList.add("briefing-weekly-flow-card");
    stage.classList.add("briefing-price-stage");

    const legend = document.createElement("div");
    legend.className = "briefing-weekly-legend";
    legend.innerHTML = series.map((row, index) => `
      <span class="briefing-weekly-legend__item">
        <i style="background:${PALETTE[index % PALETTE.length]}" aria-hidden="true"></i>
        <b>${escapeHtml(row.label || row.ticker)}</b>
        <em data-direction="${signedPercent(row.changePct) === "—" ? "flat" : (finite(row.changePct) || 0) > 0 ? "up" : finite(row.changePct) < 0 ? "down" : "flat"}">${escapeHtml(signedPercent(row.changePct))}</em>
        <small>${escapeHtml(String(row.points?.[0]?.time || "주초"))} 종가=0 · 전체 주간 ${escapeHtml(signedPercent(row.weeklyReturn))}${finite(row.weeklyReturn) === null ? " (비교 자료 없음)" : ""}</small>
      </span>`).join("");
    stage.before(legend);

    const theme = chartTheme();
    const chart = LC.createChart(stage, {
      height: 300,
      width: stage.clientWidth || 0,
      layout: { background: { type: "solid", color: theme.background }, textColor: theme.text, attributionLogo: true },
      grid: { vertLines: { visible: false }, horzLines: { color: theme.grid, style: LC.LineStyle?.Dotted ?? 1 } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.14, bottom: 0.14 } },
      timeScale: { borderVisible: false, rightOffset: 1, barSpacing: 26, minBarSpacing: 8, timeVisible: false },
      localization: {
        locale: "ko-KR",
        dateFormat: "yyyy-MM-dd",
        // 축과 tooltip이 모두 %다. 절대 지수 레벨은 시리즈마다 자릿수가 달라 한
        // 좌표계에 겹칠 수 없다 — 그래서 이 그림의 값은 처음부터 %다.
        priceFormatter: (value) => `${value > 0 ? "+" : ""}${Number(value).toFixed(1)}%`,
      },
      crosshair: { mode: LC.CrosshairMode?.Normal ?? 0 },
      handleScroll: false,
      handleScale: false,
    });
    const apis = series.map((row, index) => {
      const api = chart.addSeries(LC.LineSeries, {
        color: PALETTE[index % PALETTE.length],
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
      });
      api.setData((row.points || []).map((point) => finite(point.changePct) === null ? { time: point.time } : { time: point.time, value: finite(point.changePct) }));
      return { api, row };
    });

    const tooltip = document.createElement("div");
    tooltip.className = "briefing-price-tooltip";
    tooltip.hidden = true;
    stage.appendChild(tooltip);
    chart.subscribeCrosshairMove((param) => {
      const rect = stage.getBoundingClientRect();
      const point = param?.point;
      if (!point || point.x < 0 || point.y < 0 || point.x > rect.width || point.y > rect.height) {
        tooltip.hidden = true;
        return;
      }
      const rows = apis.map(({ api, row }) => {
        const value = param.seriesData?.get(api);
        if (!value) return "";
        // %와 함께 그날 종가도 적는다. 그림은 %지만 독자가 확인하려는 것은 지수 레벨이다.
        const close = (row.points || []).find((item) => item.time === String(param.time))?.close;
        return `<div><span>${escapeHtml(row.label || row.ticker)}</span><b>${escapeHtml(signedPercent(value.value))}</b>${
          close === undefined ? "" : `<small>${escapeHtml(formatNumber(close))}</small>`}</div>`;
      }).filter(Boolean).join("");
      if (!rows) {
        tooltip.hidden = true;
        return;
      }
      tooltip.innerHTML = `<strong>${escapeHtml(String(param.time || ""))}</strong>${rows}`;
      const width = tooltip.offsetWidth || 180;
      const height = tooltip.offsetHeight || 90;
      tooltip.style.transform = `translate(${Math.min(Math.max(8, point.x + 14), Math.max(8, rect.width - width - 8))}px, ${
        Math.min(Math.max(8, point.y - height - 12), Math.max(8, rect.height - height - 8))}px)`;
      tooltip.hidden = false;
    });
    const stopAutoFit = fitChartWhenSized(chart, stage);
    chartRecords.set(id, {
      kind: "lightweight",
      chart,
      title,
      element: stage,
      snapshot,
      cleanup: () => stopAutoFit?.(),
    });
    appendCaption(card, weeklyCaption(snapshot, "대표 지수의 주초 대비 등락률. 저장된 일봉 종가 기준이며 실시간 체결가가 아닙니다."));
    return card;
  }

  function heatmapHoverText(row) {
    const parts = [escapeHtml(row[0]), `등락 ${signedPercent(row[1])}`];
    if (finite(row[2]) !== null) parts.push(`종가 ${formatNumber(row[2])}`);
    if (row[3]) parts.push(escapeHtml(row[3]));
    return parts.join("<br>");
  }

  function storyShareValue(day, label, otherLabel) {
    const value = finite(label === otherLabel ? day.otherShare : day.shares?.[label]);
    return value !== null && value >= 0 && value <= 1 ? value : null;
  }

  /** 이야기 비중 그림의 좌표계 — **1 user unit = 1 CSS px**.
   *
   *  이 그림만 SVG라 viewBox를 고정폭(640)으로 두면 카드 폭에 비례해 글자·선·점이
   *  함께 줄어든다. 옆 차트들은 CSS 픽셀로 그리므로 같은 카드 안에서 서식이 갈렸다 —
   *  실측으로 축 글자 11.2px(데스크톱)/12.0px(모바일), 선 1.79px/**0.96px**였고
   *  히트맵 라벨 13px·LWC 선 2~3px과 어긋났다. 모바일 글자만 미디어 쿼리로 두 배
   *  키우고 선·점은 그대로 둔 보정이 그 어긋남을 더 벌렸다.
   *
   *  viewBox를 실제 폭에 맞추면 `--fs-meta`에 적은 12.5px가 그대로 12.5px로 나온다.
   *  폭을 아직 재지 못한 첫 렌더는 640으로 그리고 `relayout()`/ResizeObserver가 고친다. */
  const STORY_SHARE_HEIGHT = 275;
  function storyShareGeometry(width) {
    const measured = Math.round(finite(width) || 0);
    const box = measured >= 240 ? measured : 640;
    // 여백은 실제 글자 크기가 정한다. `100%`(12.5px에서 약 34px)가 왼쪽 밖으로 나가지
    // 않고, 가운데 정렬한 마지막 날짜 라벨의 절반(약 17px)이 오른쪽에서 잘리지 않아야
    // 한다 — 실측으로 오른쪽 12px에서는 `09.06`이 잘렸다.
    return {
      width: box,
      height: STORY_SHARE_HEIGHT,
      left: 52,
      right: Math.max(160, box - 24),
      baseline: 234,
      span: 210,
    };
  }

  function renderStoryShareBars(snapshot, title) {
    const days = (snapshot.days || []).filter((row) => /^\d{4}-\d{2}-\d{2}$/.test(row.date || "") && Number.isFinite(Date.parse(`${row.date}T00:00:00Z`)));
    if (!days.length) {
      return unavailableCard(snapshot, title, "그 주 수집된 뉴스가 없어 이야기 비중을 그리지 못했습니다.");
    }
    const { id, card, stage } = cardShell(snapshot, title, "story-share");
    card.classList.add("briefing-story-share-card");
    const drivers = [...(snapshot.drivers || [])];
    const otherLabel = snapshot.otherLabel || "그 외 이야기";
    const rows = [...drivers, otherLabel];
    const colorOf = (index) => index < drivers.length
      ? `var(--folio-chart-${index % 5 + 1})`
      : "var(--folio-ink-muted)";
    const shareOf = (day, label) => storyShareValue(day, label, otherLabel);
    const shareText = (day, label) => {
      const share = shareOf(day, label);
      return share === null ? "자료 없음" : `${(share * 100).toFixed(1)}%`;
    };
    const countText = (day) => finite(day.docCount) === null ? "기사 수 미상" : `${day.docCount}건`;
    const dates = days.map((day) => Date.parse(`${day.date}T00:00:00Z`));
    const start = Math.min(...dates), end = Math.max(...dates);
    let geometry = storyShareGeometry(0);
    const x = (index) => end === start
      ? (geometry.left + geometry.right) / 2
      : geometry.left + (dates[index] - start) / (end - start) * (geometry.right - geometry.left);
    const y = (share) => geometry.baseline - share * geometry.span;
    const chartMarkup = () => {
      const paths = rows.map((label, index) => {
        let connected = false;
        const path = days.map((day, dayIndex) => {
          const value = shareOf(day, label);
          if (value === null) { connected = false; return ""; }
          if (dayIndex && dates[dayIndex] - dates[dayIndex - 1] > 86400000) connected = false;
          const command = `${connected ? "L" : "M"}${x(dayIndex)},${y(value)}`;
          connected = true;
          return command;
        }).join(" ");
        const points = days.map((day, dayIndex) => {
          const value = shareOf(day, label);
          return value === null ? "" : `<circle cx="${x(dayIndex)}" cy="${y(value)}" r="3" />`;
        }).join("");
        return `<g style="color:${colorOf(index)}"><path d="${path}" fill="none" stroke="currentColor" stroke-width="2"/>${points.replaceAll('<circle ', '<circle fill="currentColor" ')}</g>`;
      }).join("");
      // 날짜 라벨은 **카드 폭**이 정한다. 뷰포트 미디어 쿼리로 감추면 도크·노트 패널이
      // 열려 카드만 좁아진 경우를 놓친다. 감춘 라벨은 아예 그리지 않는다 — CSS로만
      // 숨기면 내보낸 PNG(스타일 없는 SVG)에서 도로 겹쳐 나온다.
      const spacing = (geometry.right - geometry.left) / Math.max(days.length - 1, 1);
      const dateLabels = days.map((day, index) => (spacing < 44 && index % 2 && index !== days.length - 1)
        ? ""
        : `<text class="story-share-date" x="${x(index)}" y="${geometry.baseline + 29}" text-anchor="middle">${escapeHtml(day.date.slice(5).replace("-", "."))}</text>`).join("");
      return `<svg class="briefing-story-share-lines" viewBox="0 0 ${geometry.width} ${geometry.height}" width="${geometry.width}" height="${geometry.height}" role="img" aria-label="${escapeHtml(title)}: 기사 비중 0~100%, 수집 날짜별 추이">
        ${[0, 25, 50, 75, 100].map((value) => `<line x1="${geometry.left}" x2="${geometry.right}" y1="${y(value / 100)}" y2="${y(value / 100)}" class="story-share-grid"/><text x="${geometry.left - 10}" y="${y(value / 100) + 4}" text-anchor="end">${value}%</text>`).join("")}
        ${paths}
        ${dateLabels}
      </svg>`;
    };
    stage.classList.add("briefing-story-share-stage");
    stage.innerHTML = `
      <p class="briefing-visual-caption">수집 기사 주제 비중 · 날짜별 수집 기사 수가 분모입니다. 시장 수익률이나 주가 기여도가 아닙니다.</p>
      <div class="briefing-story-share-plot"></div>
      <div class="briefing-story-share-legend">${rows.map((label, index) => `
        <span><i style="background:${colorOf(index)}" aria-hidden="true"></i>${escapeHtml(label)}</span>`).join("")}
      </div>
      <label class="briefing-story-share-selection">수집 날짜 <select aria-label="이야기 비중 수집 날짜">${days.map((day, index) => `<option value="${index}">${escapeHtml(day.date)} · ${escapeHtml(countText(day))}</option>`).join("")}</select></label>
      <div class="briefing-story-share-values" aria-live="polite"></div>
      <details><summary>날짜별 전체 값</summary><div class="table-wrap"><table><thead><tr><th>수집 날짜</th><th>기사 수</th>${rows.map((label) => `<th>${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${days.map((day) => `<tr><th scope="row">${escapeHtml(day.date)}</th><td>${escapeHtml(countText(day))}</td>${rows.map((label) => `<td>${shareText(day, label)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
    stage.removeAttribute("role");
    stage.removeAttribute("aria-label");
    // 그림만 다시 그린다. 고른 날짜와 펼쳐 둔 표는 폭이 바뀌어도 그대로 남는다.
    const plot = stage.querySelector(".briefing-story-share-plot");
    const drawChart = () => {
      geometry = storyShareGeometry(plot.clientWidth || stage.clientWidth);
      plot.innerHTML = chartMarkup();
    };
    const select = stage.querySelector("select");
    let activeDay = -1;
    const showDay = (index) => {
      // 같은 날을 다시 그리지 않는다 — hover가 픽셀마다 aria-live 영역을 새로 쓰면
      // 스크린 리더가 같은 값을 계속 읽는다.
      if (index === activeDay || !days[index]) return;
      activeDay = index;
      select.value = String(index);
      const day = days[index];
      stage.querySelector(".briefing-story-share-values").innerHTML = `<b>${escapeHtml(day.date)} · ${escapeHtml(countText(day))}</b><ul>${rows.map((label) => `<li><span>${escapeHtml(label)}</span><b>${shareText(day, label)}</b></li>`).join("")}</ul>`;
    };
    select.addEventListener("change", () => showDay(Number(select.value)));
    plot.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch") return;
      const rect = plot.getBoundingClientRect();
      if (!rect.width) return;
      const position = (event.clientX - rect.left) / rect.width * geometry.width;
      showDay(days.reduce((best, _, index) => Math.abs(x(index) - position) < Math.abs(x(best) - position) ? index : best, 0));
    });
    drawChart();
    showDay(0);
    let observer = null;
    if (typeof root.ResizeObserver === "function") {
      let lastWidth = geometry.width;
      observer = new root.ResizeObserver(() => {
        const width = storyShareGeometry(plot.clientWidth || stage.clientWidth).width;
        if (width === lastWidth) return;
        lastWidth = width;
        drawChart();
      });
      observer.observe(plot);
    }
    chartRecords.set(id, {
      kind: "svg",
      title,
      element: stage,
      redraw: drawChart,
      cleanup: () => observer?.disconnect(),
    });
    let note = "주말을 포함한 수집 날짜별 보도량입니다. 저장된 비중을 그대로 표시하며 자료가 없는 값은 선을 연결하지 않습니다.";
    if (snapshot.smallSample) {
      // 표본이 적으면 기사 한두 건이 비중을 수십 %p 움직인다. 그 사실을 숨기면
      // 수집량 변동이 이야기의 변화처럼 읽힌다.
      note += ` 표본이 적은 날이 있어(하루 ${snapshot.minConfidentSample || 12}건 미만) 비중이 흔들릴 수 있습니다.`;
    }
    appendCaption(card, weeklyCaption(snapshot, note));
    return card;
  }

  /** 주간 지수 카드의 "전체 주간" 값. 창 안 첫 종가(=0%)가 아니라 **직전 주 종가**가
   *  기준이라 그림의 곡선과는 다른 수치다. 그래서 값과 기준일을 함께 적는다. */
  function weeklyReturnSummary(snapshot) {
    const parts = (snapshot?.series || []).map((row) => {
      const label = row.label || row.ticker || "";
      if (finite(row.weeklyReturn) === null) return `${label} 전체 주간 비교 자료 없음`;
      const baseline = String(row.weeklyBaselineDate || "").slice(5);
      return `${label} 전체 주간 ${signedPercent(row.weeklyReturn)}${baseline ? `(${baseline} 종가 대비)` : ""}`;
    });
    return parts.join(" · ");
  }

  /** 새 주간 저장본만 일간 차트로 보낸다.
   *
   *  옛 주간 저장본은 계열마다 `points`(주초=0%로 재기준한 **퍼센트**) 하나뿐인데
   *  그 점에도 원 종가가 함께 들어 있어 `shouldRenderTrend`는 통과한다. 게다가
   *  `normalizePriceSubject`가 `daily`가 없으면 그 `points`를 일봉 자리에 되돌려주므로,
   *  통과시키면 5점짜리 주간 계열이 1M·3M·1Y 버튼을 단 지수 차트로 그려진다 —
   *  버튼은 답할 자료가 없고 그림은 그 주만 반복한다. 그래서 **자기 일봉 이력을 가진**
   *  저장본만 새 경로로 보내고, 기준은 저장본이 스스로 밝힌 최소 점수(`minimumTrendPoints`)다.
   *  한 주의 거래일보다 많은 값이라 이 문턱을 넘으면 기간 버튼이 실제로 답할 수 있다. */
  /** `1W`가 실제로 어떤 봉으로 그려지는지. 시간봉 조회가 실패한 저장본은 일봉으로
   *  그리므로 캡션이 없는 단위를 말하지 않게 저장본을 보고 정한다. */
  function weekBarUnit(snapshot) {
    const hourly = (snapshot?.series || [])
      .some((row) => (normalizePriceSubject(row).hourly.points || []).length >= 2);
    return hourly ? "1시간봉" : "일봉";
  }

  function hasStoredDailyHistory(snapshot) {
    const declared = finite(snapshot?.dataSufficiency?.minimumTrendPoints);
    const minimum = Math.max(2, Math.round(declared || 8));
    return (snapshot?.series || []).some((row) => {
      const points = row && row.daily && Array.isArray(row.daily.points) ? row.daily.points : [];
      return points.filter((point) => finite(point.close) !== null).length >= minimum;
    });
  }

  /** 추천의 `variant`가 어떤 그림인지 정한다.
   *
   *  주간 지수는 예전에 전용 렌더러(주초=0% 겹쳐 그리기)를 썼다. 지금은 저장본이
   *  일간과 같은 가격 이력을 담으므로 **같은 차트**로 그리고 기본 구간만 그 주로 둔다.
   *  이력이 없는 옛 저장본은 저장 시각자료가 불변이므로 예전 그림 그대로 읽힌다. */
  function renderRecommendation(snapshot, recommendation, comparison) {
    if (recommendation.variant === "weekly_flow_chart") {
      if (!hasStoredDailyHistory(snapshot)) return renderWeeklyFlow(snapshot, recommendation.title);
      const card = renderTrend(snapshot, recommendation.title, recommendation.variant, comparison, {
        defaultPeriod: recommendation.defaultPeriod || "1W",
      });
      const summary = weeklyReturnSummary(snapshot);
      appendCaption(card, weeklyCaption(snapshot, `${summary ? `${summary}. ` : ""}기본은 그 주 구간(${weekBarUnit(snapshot)})이고, 기간 버튼으로 더 긴 흐름을 함께 봅니다.`));
      return card;
    }
    if (recommendation.variant === "story_share_bars") return renderStoryShareBars(snapshot, recommendation.title);
    if (recommendation.variant === "treemap_heatmap") {
      const card = renderHeatmap(snapshot, recommendation.title, comparison);
      // 주간 히트맵은 일간과 **같은 그림**이라 캡션이 없으면 하루 등락으로 읽힌다.
      // `renderHeatmap` 자체는 일간 계약이므로 건드리지 않고 여기서 한 줄을 붙인다.
      if (snapshot.range === "week") {
        const basis = snapshot.changeBasis || {};
        appendCaption(card, weeklyCaption(snapshot,
          `구성종목의 주간 등락(${basis.startDate || "주초"} 종가 대비 ${basis.endDate || "주말"} 종가). `
          + "상자 크기는 시가총액이고, 주초 종가가 없는 종목은 그리지 않습니다."));
      }
      return card;
    }
    return renderTrend(snapshot, recommendation.title, recommendation.variant, comparison);
  }

  function renderHeatmap(snapshot, title, comparison) {
    const coverage = snapshot.coverage || {};
    const ratio = finite(coverage.ratio);
    const incomplete = (coverage.status && coverage.status !== "complete")
      || (ratio !== null && ratio < 1);
    if (incomplete) {
      const declaredMissing = finite(coverage.missingCount);
      const requested = finite(coverage.requested);
      const returned = finite(coverage.returned);
      const missing = declaredMissing !== null
        ? declaredMissing
        : requested !== null && returned !== null ? Math.max(0, requested - returned) : null;
      const detail = missing === null ? "전체 구성 종목 범위를 확인할 수 없습니다." : `누락 종목 ${Math.max(0, Math.round(missing))}개`;
      return unavailableCard(snapshot, title, `히트맵 자료가 완전하지 않아 전체 시장 지도를 표시하지 않습니다. ${detail}`);
    }
    const rows = snapshot.rows || [];
    // 뿌리 화면은 산업 층을 접은 쪽, 들어간 뒤에는 계층이 있는 쪽을 쓴다.
    const flatNodes = heatmapNodes(rows, { flat: true });
    if (!flatNodes.ids.length) {
      return unavailableCard(snapshot, title, "저장된 히트맵 구성 종목이 없습니다.");
    }
    if (!root.echarts?.init) return unavailableCard(snapshot, title, "히트맵 라이브러리를 불러오지 못했습니다.");
    const groupedNodes = heatmapNodes(rows);
    const flatTree = heatmapTree(flatNodes);
    const groupedTree = heatmapTree(groupedNodes);
    const { id, card, stage } = cardShell(snapshot, title, "heatmap");
    stage.classList.add("briefing-heatmap-stage");
    const values = document.createElement("details");
    values.className = "briefing-visual-values";
    values.innerHTML = `<summary>종목별 수치</summary><div class="table-wrap"><table><thead><tr><th>종목</th><th>등락</th><th>종가</th></tr></thead><tbody>${rows.map((row) => `<tr><th scope="row">${escapeHtml(row.label || row.ticker)}</th><td>${signedPercent(row.changePct)}</td><td>${finite(row.close) === null ? "자료 없음" : escapeHtml(formatNumber(row.close))}</td></tr>`).join("")}</tbody></table></div>`;
    card.append(values);
    const nav = document.createElement("nav");
    nav.className = "briefing-heatmap-path";
    nav.setAttribute("aria-label", "히트맵 위치");
    stage.insertAdjacentElement("beforebegin", nav);

    let level = "";
    let wanted = false;
    let chart = null;
    let resizeObserver = null;
    let lastSize = "";
    let headers = [];

    const findNode = (tree, nodeId) => {
      for (const node of tree) {
        if (node.id === nodeId) return node;
        const hit = node.children && findNode(node.children, nodeId);
        if (hit) return hit;
      }
      return null;
    };

    /** 이 층에서 무엇을 몇 겹까지 그릴지. `roots`는 이 층의 새 뿌리, `depth`는 뿌리부터 잎까지 겹 수다.
     *
     *  뿌리는 섹터→종목이다. 섹터에 들어가면 그 섹터의 산업이 새 뿌리가 되고(넓은 화면은 종목까지 한
     *  겹 더), 산업에 들어가면 그 산업의 종목만 남는다. 이름 띠는 위 경로 버튼이 이미 보여 주므로 다시
     *  그리지 않는다. 누를 때마다 더 자세해지는 방향이라 되돌아오는 길은 경로 버튼이 맡는다.
     */
    const viewFor = (levelId) => {
      const compact = heatmapCompact(stage);
      const rootView = { roots: flatTree, depth: compact ? 1 : 2 };
      if (!levelId) return rootView;
      const node = findNode(groupedTree, levelId);
      if (!node || !node.children) return rootView;
      if (levelId.startsWith("sector:")) return { roots: node.children, depth: compact ? 1 : 2 };
      return { roots: node.children, depth: 1 };
    };

    const onClick = (params) => {
      const nodeId = String(params?.data?.id || "");
      if (nodeId) {
        // 종목이 마지막 층이다. 더 들어갈 곳이 없다.
        if (!nodeId.startsWith("ticker:")) goToLevel(nodeId);
        return;
      }
      // 머리띠·틈을 누르면 부모가 아니라 보이지 않는 뿌리가 온다. 좌표로 어느 머리띠인지 가린다.
      const hit = heatmapHeaderAt(headers, params?.event?.offsetX, params?.event?.offsetY);
      if (hit) goToLevel(hit);
    };

    const draw = () => {
      const width = stage.clientWidth;
      const height = stage.clientHeight;
      // 숨은 탭·접힌 곳에서는 폭이 0이다. 보이면 ResizeObserver와 relayout이 다시 부른다.
      if (!(width > 0) || !(height > 0)) return;
      lastSize = `${width}x${height}`;
      const view = viewFor(level);
      // 라벨 계획이 노드를 바꾸므로 층마다 복사본을 쓴다(같은 트리를 다른 깊이로 다시 그린다).
      const roots = JSON.parse(JSON.stringify(view.roots));
      const series = Object.assign(heatmapSeriesBase(view.depth), { data: roots });
      const total = roots.reduce((sum, node) => sum + node.value, 0);
      // 배치를 먼저 물어 타일 폭·높이를 안다 — 그 값으로 들어가는 라벨만 고른다.
      const rects = heatmapTileSizes(root.echarts, series, width, height);
      headers = heatmapPlanLabels(roots, { rects, total, width, height, depth: view.depth, measure: measureLabelWidth });
      if (!chart) {
        chart = root.echarts.init(stage, null, { renderer: "svg" });
        chart.on("click", onClick);
      }
      const tooltip = heatmapTooltipTheme();
      chart.setOption({
        animation: false,
        backgroundColor: "transparent",
        tooltip: {
          confine: true,
          backgroundColor: tooltip.backgroundColor,
          borderColor: tooltip.borderColor,
          borderWidth: 1,
          textStyle: { color: tooltip.color, fontSize: 12, fontFamily: HEATMAP_FONT_FAMILY },
          formatter: (params) => (params?.data?._row ? heatmapHoverText(params.data._row) : ""),
        },
        series: [series],
        graphic: { elements: [...heatmapSectorOutlines(roots, rects, tooltip.outline), ...heatmapHeaderRules(headers, heatmapSurfaceColor(card))] },
      }, { notMerge: true });
      stage.dataset.rendered = "true";
      card.dataset.heatmapCompact = heatmapCompact(stage) ? "true" : "false";
      renderPath();
      redrawWhenFontsLoad();
    };

    /** 글꼴이 다 내려온 뒤 한 번 더 그린다.
     *
     *  라벨 폭은 캔버스로 재는데, 웹 글꼴(Inter·IBM Plex·SUIT)이 아직 안 내려왔으면 대체 글꼴로 잰다. 다 내려온 뒤
     *  ECharts가 진짜 글꼴로 그리면 글자가 조금 넓어져 계획한 폭에 딱 맞던 라벨이 `...`로 잘린다(브라우저 실측:
     *  `Heavy Industr...`). 다 내려온 뒤 다시 재서 계획을 새로 세운다. 이미 다 내려와 있으면 아무것도 안 한다. */
    let fontRedrawQueued = false;
    const redrawWhenFontsLoad = () => {
      const fonts = root.document?.fonts;
      if (!fonts || fonts.status === "loaded" || fontRedrawQueued) return;
      fontRedrawQueued = true;
      Promise.resolve(fonts.ready).then(() => {
        fontRedrawQueued = false;
        if (chart) {
          lastSize = "";
          draw();
        }
      }).catch(() => { fontRedrawQueued = false; });
    };

    const plot = () => {
      wanted = true;
      if (stage.dataset.rendered !== "true") draw();
      return Promise.resolve();
    };

    /** 폭이 바뀌면 라벨 계획이 달라진다(깊이도 폭이 정한다). 다시 물어 다시 그린다 — 읽을 비동기 레이아웃이
     *  없으므로 경합이 없다. */
    const redraw = () => {
      // 아직 한 번도 못 그렸다면(폭 0에서 시작) 그릴 차례가 온 것이다.
      if (!chart) {
        if (wanted) draw();
        return;
      }
      const size = `${stage.clientWidth}x${stage.clientHeight}`;
      if (size === lastSize) return;
      lastSize = size;
      chart.resize();
      draw();
    };

    function goToLevel(nodeId) {
      level = String(nodeId || "");
      draw();
    }

    /** 어디까지 들어왔고 어떻게 나가는지. */
    function renderPath() {
      const labelOf = (nodeId) => {
        const index = groupedNodes.ids.indexOf(nodeId);
        return index >= 0 ? groupedNodes.labels[index] : "";
      };
      const parentOf = (nodeId) => {
        const index = groupedNodes.ids.indexOf(nodeId);
        return index >= 0 ? groupedNodes.parents[index] : "";
      };
      const chain = [];
      let cursor = level;
      while (cursor) {
        chain.unshift(cursor);
        cursor = parentOf(cursor);
      }
      const steps = [{ id: "", label: "전체" }, ...chain.map((nodeId) => ({ id: nodeId, label: labelOf(nodeId) }))];
      nav.innerHTML = "";
      steps.forEach((step, index) => {
        const last = index === steps.length - 1;
        if (index > 0) {
          const separator = document.createElement("span");
          separator.className = "briefing-heatmap-path-sep";
          separator.setAttribute("aria-hidden", "true");
          separator.textContent = "›";
          nav.appendChild(separator);
        }
        if (last) {
          const here = document.createElement("span");
          here.className = "briefing-heatmap-path-here";
          here.setAttribute("aria-current", "true");
          here.textContent = step.label;
          nav.appendChild(here);
          return;
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn--text";
        button.textContent = step.label;
        button.addEventListener("click", () => goToLevel(step.id));
        nav.appendChild(button);
      });
      if (steps.length === 1) {
        const hint = document.createElement("span");
        hint.className = "briefing-heatmap-hint";
        hint.textContent = "칸을 누르면 그 안을 봅니다.";
        nav.appendChild(hint);
      }
    }

    // 깊이는 폭이 정한다. 도크를 접거나 화면을 돌려 폭이 두 배가 돼도 섹터 열한 개만 남으면 안 된다.
    if (typeof root.ResizeObserver === "function") {
      resizeObserver = new root.ResizeObserver(redraw);
      resizeObserver.observe(stage);
    }
    chartRecords.set(id, {
      kind: "echarts",
      title,
      element: stage,
      ensureRendered: plot,
      redraw: () => {
        lastSize = "";
        redraw();
      },
      cleanup: () => {
        resizeObserver?.disconnect();
        chart?.dispose();
        chart = null;
      },
    });
    if (typeof root.IntersectionObserver === "function") {
      const observer = new root.IntersectionObserver((entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        plot();
      }, { rootMargin: "300px" });
      observer.observe(stage);
    } else {
      plot();
    }
    appendComparison(card, comparison);
    return card;
  }

  async function loadSidecar(briefing) {
    const needsHeatmap = (briefing.visualSnapshots || []).some((snapshot) => snapshot.type === "market_heatmap" && snapshot.sidecarRef);
    if (!needsHeatmap || !briefing.date) return {};
    try {
      const scope = String(briefing.marketScope || "").toLowerCase();
      const params = new URLSearchParams();
      if (SCOPE_MARKETS[scope]) params.set("market", scope);
      // **종류가 빠지면 주간 카드에 그날 일간 히트맵이 그려진다.** 발행일과 시장이
      // 같아 파일 이름이 종류로만 갈린다.
      if (String(briefing.kind || "") === "weekly") params.set("kind", "weekly");
      const query = params.toString() ? `?${params}` : "";
      const response = await fetch(`/api/briefings/${encodeURIComponent(briefing.date)}/visuals${query}`);
      if (!response.ok) return {};
      return (await response.json()).snapshots || {};
    } catch (_) {
      return {};
    }
  }

  // 모달처럼 늦게 폭이 잡히는 컨테이너에서 autoSize가 0폭으로 굳는 경우,
  // 보이는 시점에 각 차트를 실제 element 폭으로 다시 맞춘다.
  function relayout() {
    for (const record of chartRecords.values()) {
      const el = record.element;
      if (!el || !el.clientWidth) continue;
      try {
        if (record.kind === "lightweight") {
          record.chart.resize(el.clientWidth, el.clientHeight || 360);
          record.chart.timeScale().fitContent();
        } else if (record.kind === "echarts") {
          // 폭이 바뀌면 라벨 계획이 달라진다 — 다시 물어 다시 그린다.
          record.redraw?.();
        } else if (record.kind === "svg") {
          // 1:1 좌표계라 폭이 바뀌면 다시 그려야 글자·선 두께가 유지된다.
          record.redraw?.();
        }
      } catch (_) {}
    }
  }

  function applyChartTheme() {
    const theme = chartTheme();
    for (const record of chartRecords.values()) {
      try {
        if (record.kind === "lightweight") {
          record.chart.applyOptions({
            layout: {
              background: { type: "solid", color: theme.background },
              textColor: theme.text,
              attributionLogo: true,
            },
            grid: {
              vertLines: { visible: false },
              horzLines: { color: theme.grid },
            },
          });
        } else if (record.kind === "echarts") {
          // 타일 색은 테마와 무관하지만 섹터 바깥선은 잉크 토큰이라 테마를 따른다.
          record.redraw?.();
        }
      } catch (_) {}
    }
  }

  function cleanup(container) {
    for (const [id, record] of chartRecords) {
      if (container && !container.querySelector(`[data-visual-export-id="${id}"]`)) continue;
      try {
        record.cleanup?.();
        if (record.kind === "lightweight") record.chart.remove();
      } catch (_) {}
      chartRecords.delete(id);
    }
  }

  function visualCards(container) {
    return Array.from(container?.querySelectorAll?.("[data-visual-export-id]") || []);
  }

  function visualCardTitle(card) {
    return String(card?.querySelector?.(".briefing-visual-header h3")?.textContent || "").trim();
  }

  function visualCardCanvasDataUrl(card) {
    const canvases = Array.from(card?.querySelectorAll?.("canvas") || []);
    for (const canvas of canvases) {
      if (!canvas?.width || !canvas?.height || typeof canvas.toDataURL !== "function") continue;
      try {
        const dataUrl = canvas.toDataURL("image/png");
        if (/^data:image\/png;base64,/i.test(dataUrl || "")) return dataUrl;
      } catch (_) {}
    }
    return card?._storySharePng || "";
  }

  async function captureStoryShare(card) {
    const original = card.querySelector?.(".briefing-story-share-lines");
    if (!original) return;
    const clone = original.cloneNode(true);
    const sources = [original, ...original.querySelectorAll("*")];
    [clone, ...clone.querySelectorAll("*")].forEach((element, index) => {
      const style = getComputedStyle(sources[index]);
      for (const name of ["fill", "stroke", "color", "font-family", "font-size"]) element.style.setProperty(name, style.getPropertyValue(name));
    });
    const lines = [...card.querySelectorAll(".briefing-story-share-legend span")].map((item) => item.textContent);
    lines.push(...[...card.querySelectorAll("select option")].map((item) => item.textContent));
    // viewBox는 이제 카드 폭을 따라간다(1:1 좌표계). 640을 다시 적으면 내보낸 그림만
    // 화면과 다른 축척으로 나온다.
    const [, , boxWidth, boxHeight] = String(original.getAttribute("viewBox") || "").split(/\s+/).map(Number);
    const plotWidth = Number.isFinite(boxWidth) && boxWidth > 0 ? boxWidth : 640;
    const plotHeight = Number.isFinite(boxHeight) && boxHeight > 0 ? boxHeight : STORY_SHARE_HEIGHT;
    const height = plotHeight + 25 + lines.length * 20;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("viewBox", `0 0 ${plotWidth} ${height}`);
    clone.setAttribute("width", String(plotWidth)); clone.setAttribute("height", String(height));
    lines.forEach((line, index) => {
      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", "48"); text.setAttribute("y", String(plotHeight + 17 + index * 20));
      text.setAttribute("fill", getComputedStyle(card).color); text.setAttribute("font-size", "14");
      text.textContent = line;
      if (index < card.querySelectorAll(".briefing-story-share-legend i").length) {
        text.setAttribute("fill", getComputedStyle(card.querySelectorAll(".briefing-story-share-legend i")[index]).backgroundColor);
      }
      clone.append(text);
    });
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
    try {
      const bitmap = new Image(); bitmap.src = url;
      await bitmap.decode();
      const canvas = document.createElement("canvas"); canvas.width = plotWidth * 2; canvas.height = height * 2;
      const context = canvas.getContext("2d");
      context.fillStyle = chartTheme().background; context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      card._storySharePng = canvas.toDataURL("image/png");
    } catch (_) {
      // 그림 하나를 못 만들었다고 나머지 내보내기까지 멈추지 않는다.
    } finally { URL.revokeObjectURL(url); }
  }

  async function render(container, briefing, mode = "snapshot", currentPayload = null) {
    if (!container) return;
    const token = renderGate.next();
    cleanup();
    container.innerHTML = "";
    const recommendations = briefing?.visualRecommendations || [];
    const inline = Object.fromEntries((briefing?.visualSnapshots || []).map((snapshot) => [snapshot.id, snapshot]));
    if (!recommendations.length) {
      container.hidden = true;
      return;
    }
    const sidecar = mode === "snapshot" ? await loadSidecar(briefing) : {};
    if (!renderGate.isCurrent(token) || !container.isConnected) return;
    const payload = mode === "current" ? (currentPayload || {}) : briefing;
    const payloadInline = Object.fromEntries((payload?.visualSnapshots || []).map((snapshot) => [snapshot.id, snapshot]));
    const snapshots = mode === "current" ? payloadInline : { ...inline, ...sidecar };
    const comparisons = payload?.comparisons || {};
    const copy = viewCopy(mode);
    const section = document.createElement("section");
    section.className = "briefing-visuals-section";
    section.innerHTML = `<div class="briefing-visuals-heading"><div><span>MARKET VISUALS</span><h2>${escapeHtml(copy.heading)}</h2><p>${escapeHtml(copy.description)}</p></div></div>`;
    if (mode === "current") {
      const status = document.createElement("div");
      status.className = "briefing-visual-current-status";
      const marketStates = Object.values(payload.marketStatus || {}).map((item) => `${item.market} ${item.state === "open" ? "정규장 진행" : "정규장 종료"}`).join(" · ");
      status.innerHTML = `<strong>${escapeHtml(payload.provider || "provider 미상")}</strong><span>${escapeHtml(payload.retrievedAt || "조회 시각 없음")}</span>${marketStates ? `<span>${escapeHtml(marketStates)}</span>` : ""}`;
      section.append(status);
    }
    const grid = document.createElement("div");
    grid.className = "briefing-visuals-grid";
    for (const recommendation of payload.visualRecommendations || recommendations) {
      const snapshot = snapshots[recommendation.snapshotId];
      if (!snapshot) continue;
      const card = recommendation.variant === "treemap_heatmap"
        ? renderHeatmap(snapshot, recommendation.title, comparisons[snapshot.id])
        : renderTrend(snapshot, recommendation.title, recommendation.variant, comparisons[snapshot.id]);
      grid.append(card);
    }
    section.append(grid);
    if (mode === "current" && (payload.warnings || []).length) {
      const warning = document.createElement("p");
      warning.className = "briefing-visuals-warning";
      warning.textContent = payload.status === "unavailable"
        ? "현재 데이터를 불러오지 못했습니다. 생성 당시 보기는 그대로 사용할 수 있습니다."
        : `일부 최신 데이터가 누락되었습니다: ${(payload.warnings || []).slice(0, 2).join(" · ")}`;
      section.append(warning);
    }
    const notice = document.createElement("p");
    notice.className = "briefing-visuals-attribution";
    notice.innerHTML = `가격 차트: <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a> · Copyright © 2025 TradingView, Inc. · 데이터: ${mode === "current" ? "최신 REST snapshot" : "저장된 provider snapshot"}`;
    section.append(notice);
    container.append(section);
    container.hidden = !grid.children.length;
  }

  async function renderInline(article, briefing, mode = "snapshot", currentPayload = null, activeMarket = "") {
    if (!article) return;
    const token = renderGate.next();
    cleanup(article);
    const slots = buildSectionSlots(article);
    if (!slots.length) return;
    const recommendations = briefing?.visualRecommendations || [];
    const inline = Object.fromEntries((briefing?.visualSnapshots || []).map((snapshot) => [snapshot.id, snapshot]));
    const sidecar = await loadSidecar(briefing);
    if (!renderGate.isCurrent(token) || !article.isConnected) return;
    const payload = mode === "current" ? (currentPayload || {}) : briefing;
    const payloadInline = Object.fromEntries((payload?.visualSnapshots || []).map((snapshot) => [snapshot.id, snapshot]));
    const snapshots = mode === "current"
      ? { ...inline, ...sidecar, ...payloadInline }
      : { ...inline, ...sidecar };
    const comparisons = payload?.comparisons || {};
    const ordered = [...recommendations].sort((a, b) =>
      Number(recommendationPlacement(a, recommendations).order || 0)
      - Number(recommendationPlacement(b, recommendations).order || 0)
    );

    for (const recommendation of ordered) {
      const placement = recommendationPlacement(recommendation, recommendations);
      const slot = slots.find((candidate) =>
        candidate.dataset.market === String(placement.market || recommendation.market || "").toUpperCase()
        && candidate.dataset.sectionRole === placement.sectionRole
        && (placement.sectionRole !== "leading_company" || Number(candidate.dataset.ordinal) === Number(placement.ordinal))
      );
      const stored = snapshots[recommendation.snapshotId];
      if (!slot) continue;
      if (!stored) {
        slot.append(unavailableCard({ market: recommendation.market, id: recommendation.snapshotId }, recommendation.title, "이 시각자료의 저장 데이터를 찾지 못했습니다."));
        continue;
      }
      let snapshot = stored;
      if (placement.sectionRole === "market_flow" && stored.type === "price_series" && (stored.series || []).length > 1) {
        const preferred = preferredIndexTicker(slot._sectionText, stored.series, stored.market);
        snapshot = {
          ...stored,
          series: [...stored.series].sort((a, b) => (a.ticker === preferred ? -1 : b.ticker === preferred ? 1 : 0)),
        };
      }
      const card = renderRecommendation(snapshot, recommendation, comparisons[snapshot.id]);
      // Keep the section's interpretation between its two large figures.
      let anchor = slot.nextElementSibling;
      if (recommendation.variant === "treemap_heatmap") {
        while (anchor && !isSectionBoundaryTag(anchor.tagName) && anchor.tagName !== "P") anchor = anchor.nextElementSibling;
      }
      if (recommendation.variant === "treemap_heatmap" && anchor?.tagName === "P") {
        const later = document.createElement("div");
        later.className = "briefing-inline-visual-slot";
        anchor.insertAdjacentElement("afterend", later);
        later.append(card);
      } else slot.append(card);
    }

    // 주간 지수 흐름도 Lightweight Charts로 그린다 — 같은 credit이 붙어야 한다.
    for (const slot of slots.filter((candidate) =>
      ["market_flow", "weekly_flow"].includes(candidate.dataset.sectionRole) && candidate.children.length
    )) {
      const notice = document.createElement("p");
      notice.className = "briefing-visuals-attribution";
      notice.innerHTML = `가격 차트: <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a> · 데이터: 저장된 provider snapshot`;
      slot.append(notice);
    }
  }

  async function captureImages(container) {
    const images = [];
    for (const card of visualCards(container).slice(0, 12)) {
      await captureStoryShare(card);
      const dataUrl = visualCardCanvasDataUrl(card);
      if (!dataUrl) continue;
      images.push({
        id: String(card.dataset?.visualExportId || ""),
        market: normalizeVisualMarket(card.dataset?.market || ""),
        title: visualCardTitle(card),
        dataUrl,
      });
    }
    return images;
  }

  async function replaceWithStaticImages(clone, original) {
    const originals = visualCards(original);
    await Promise.all(originals.map(captureStoryShare));
    visualCards(clone).forEach((card, index) => {
      const dataUrl = visualCardCanvasDataUrl(originals[index]);
      const stage = card.querySelector?.(".briefing-visual-stage");
      if (dataUrl && stage) {
        const title = visualCardTitle(card) || `Briefing visual ${index + 1}`;
        stage.innerHTML = `<img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(title)}" style="max-width:100%;height:auto;display:block;" />`;
      }
    });
    clone.querySelectorAll(exportControlSelector()).forEach((control) => control.remove());
    return [];
  }

  root?.addEventListener?.("folio:theme-changed", applyChartTheme);

  return {
    render,
    renderInline,
    relayout,
    applyChartTheme,
    cleanup,
    captureImages,
    replaceWithStaticImages,
    indexSeries,
    heatmapColor,
    shouldRenderTrend,
    comparisonSummary,
    viewAction,
    viewCopy,
    normalizePriceSubject,
    periodPoints,
    priceSummary,
    priceSummaryForPeriod,
    hoverTooltipContent,
    lightweightTimeLabel,
    formatPriceValue,
    initialPriceState,
    lightweightRows,
    sectionRole,
    sectionMarket,
    renderRecommendation,
    weeklyCaption,
    signedPercent,
    heatmapHoverText,
    storyShareValue,
    storyShareGeometry,
    availablePeriods,
    weeklyReturnSummary,
    hasStoredDailyHistory,
    isIntradayInterval,
    weekBarUnit,
    preferredIndexTicker,
    buildSectionSlots,
    heatmapNodes,
    heatmapLabelPlan,
    heatmapRichLabel,
    heatmapHeaderPlan,
    heatmapHeaderLabel,
    heatmapTree,
    heatmapSeriesBase,
    heatmapTileSizes,
    heatmapFallbackSize,
    heatmapPlanLabels,
    heatmapHeaderAt,
    heatmapSectorOutlines,
    heatmapHeaderRules,
    heatmapWithAlpha,
    heatmapTickerLabel,
    heatmapGroupName,
    abbreviateHeatmapLabel,
    createRequestGate,
    controlButton,
    exportControlSelector,
    normalizeVisualMarket,
    recommendationPlacement,
    sectionHeadingSelector,
    isSectionBoundaryTag,
    insertSectionSlot,
    fitChartWhenSized,
  };
});
