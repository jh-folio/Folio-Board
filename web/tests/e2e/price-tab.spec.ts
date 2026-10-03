import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const row = (label: string, horizon: number, irr: string, g: string, pe: string, pct: number) => ({
  label, horizon, status: 'available', g, exitPE: pe, payout: '0.3000', irr, irrRange: null,
  percentiles: { g: pct, exitPE: pct, payout: 50 }, n: { g: 5, exitPE: 10, payout: 10 },
});
const SCENARIOS = [
  row('conservative', 5, '0.0210', '0.0300', '15.00', 25), row('base', 5, '0.0590', '0.0600', '18.00', 50), row('optimistic', 5, '0.1180', '0.1100', '24.00', 75),
  row('conservative', 10, '0.0450', '0.0300', '15.00', 25), row('base', 10, '0.0660', '0.0600', '18.00', 50), row('optimistic', 10, '0.0980', '0.1100', '24.00', 75),
];
const block = (values: string[], p25: string, p50: string, p75: string) => ({ status: 'available', n: values.length, p25, p50, p75, values: values.map((value, index) => ({ fiscalYear: 2015 + index, value })) });
const VIEW = {
  snapshotId: 'price-now', instrumentId: 'US:ABC', asOf: '2026-10-01', computedAt: '2026-10-01T18:40:00Z', methodVersion: 'price-scenario-3', supportStatus: 'supported',
  inputSummary: { asOf: '2026-10-01', identity: { ticker: 'ABC', market: 'US' }, price: { value: '100.00', sessionDate: '2026-10-01', currency: 'USD' } },
  results: {
    support: { status: 'supported', reasons: [], notices: ['share_classes_same_eps'] }, notices: [],
    base: { status: 'available', fiscalYear: 2025, periodEnd: '2025-12-31', monthsBeforeSession: 9, eps0: '5.00' },
    ranges: {
      growth: block(['-0.0200', '0.0300', '0.0600', '0.1100', '0.1500'], '0.0300', '0.0600', '0.1100'),
      pe: block(['12.00', '15.00', '18.00', '24.00', '31.00'], '15.00', '18.00', '24.00'),
      payout: block(['0.2800', '0.3000', '0.3000', '0.3100', '0.3200'], '0.3000', '0.3000', '0.3100'),
      rpsGrowth: block(['0.0300', '0.0500', '0.0600'], '0.0400', '0.0500', '0.0550'),
      netMargin: block(['0.0600', '0.0850', '0.1000', '0.1150', '0.1300'], '0.0850', '0.1000', '0.1150'),
    },
    scenarios: SCENARIOS,
    decomposition: { status: 'available', recentWindow: [2020, 2025], notes: [], windows: [{ start: 2020, end: 2025, R: '0.2300', M: '0.0600', S: '0.0350', total: '0.3250', annual: { R: '0.0488', M: '0.0119', S: '0.0070', total: '0.0650' } }] },
    reverse: {
      breakEvenPE: { '5': { status: 'available', state: 'needed', exitPE: '9.00' }, '10': { status: 'available', state: 'needed', exitPE: '7.60' } },
      breakEvenMargin: { '5': { status: 'available', currentMargin: '0.1000', margin: '0.0650', marginRange: null }, '10': { status: 'available', currentMargin: '0.1000', margin: '0.0780', marginRange: null } },
    },
  },
};
const projection = (extra: Record<string, unknown> = {}) => ({
  snapshotId: 'price-now', asOf: '2026-10-01', ageDays: 1, notices: [],
  criteria: { revisionId: 1, holdingYears: 10, requiredReturn: '6', minMarginOfSafety: '20' },
  verdict: { return: { state: 'met', horizon: 10, irr: '0.0660' }, marginOfSafety: { state: 'unknown', reason: 'dcf_fallback' } },
  requirement: { status: 'available', exitPE: { '5': { status: 'available', state: 'needed', value: '9.50' }, '10': { status: 'available', state: 'needed', value: '9.60' } },
    growth: { '5': { status: 'available', value: '0.0600', percentile: '50.0' }, '10': { status: 'available', value: '0.0580', percentile: '45.0' } }, netMargin: {} },
  myAssumptions: null, reviewNeeded: [], ...extra,
});
const OVERVIEW = {
  instrumentId: 'US:ABC', latest: { snapshotId: 'price-now', asOf: '2026-10-01', computedAt: '2026-10-01T18:40:00Z', supportStatus: 'supported' },
  history: [{ snapshotId: 'price-now', asOf: '2026-10-01', computedAt: '2026-10-01T18:40:00Z', method: 'price-scenario-3', supersedes: 'price-old', reviewCount: 0, changeReasons: [{ code: 'price_moved' }] },
    { snapshotId: 'price-old', asOf: '2026-09-01', computedAt: '2026-09-01T18:40:00Z', method: 'price-scenario-3', supersedes: null, reviewCount: 0, changeReasons: [] }],
  lastAttempt: null,
};
const CRITERIA = { revisionId: 1, requiredReturn: '6', minMarginOfSafety: '20', holdingYears: 10, createdAt: '2026-09-30T00:00:00Z' };

type Options = { empty?: boolean; criteria?: unknown; projection?: unknown; overview?: unknown; view?: unknown };

const CASH = {
  status: 'available', currency: 'TWD', ratio: '0.9000', class: 'cash_in_line', sbcBasis: 'deducted', notices: [],
  sumNetIncome: '500', sumFcf: '450',
  years: [2020, 2021, 2022, 2023, 2024].map(fiscalYear => ({ fiscalYear, netIncome: '100', ocf: '120', capexRaw: '-20', capexOut: '20', sbc: '10', fcf: '90' })),
};
const V4 = { ...VIEW, methodVersion: 'price-scenario-4', results: { ...VIEW.results,
  returnParts: SCENARIOS.map(row => ({ label: row.label, horizon: row.horizon, status: 'available', peNow: '20.00', exitPE: row.exitPE,
    growth: row.g, dividend: '0.0150', rerating: (Number(row.irr) - Number(row.g) - .015).toFixed(4), irrFlat: (Number(row.g) + .015).toFixed(4) })),
  noGrowth: { status: 'available', rps0: '30', marginP50: '0.1000', marginN: 10, normEps: '3', recentEps: '5' },
  cashConversion: CASH,
}};
const NOGROWTH = { status: 'available', value: '50.00', growthShare: '0.5000', priceCoverage: '0.5000', requiredReturn: '0.0600', criteriaRevisionId: 1, hasGrowthShare: true };

for (const theme of ['light', 'dark']) {
  test(`0.9.1 crosschecks card selection, cash table and keyboard ${theme}`, async ({ page }) => {
    const writes = await mockApi(page, { view: V4, projection: projection({ noGrowth: NOGROWTH }) });
    await openPrice(page, theme);
    const tab = page.locator('[data-price-tab]');
    await expect(tab.locator('.price-return-parts')).toContainText('기본 10년: 이익 성장 +6.00% + 배당 +1.50% + PER 변화 −0.90% = 연 6.60%');
    await tab.locator('.price-card').nth(2).focus();
    await page.keyboard.press('Enter');
    await expect(tab.locator('.price-return-parts')).toContainText('낙관 10년');
    await tab.getByRole('button', { name: '5년', exact: true }).click();
    await expect(tab.locator('.price-return-parts')).toContainText('낙관 5년');
    await expect(tab.locator('.price-no-growth')).toContainText('성장이 없다면, 이 가격의 약 50%');
    await expect(tab.locator('.price-no-growth')).toContainText('성장 없는 가치 $50.00');
    await expect(tab.locator('.price-no-growth')).toContainText('최근 주당이익 $5.00');
    const cash = tab.getByRole('heading', { name: '이익이 현금으로 남았나' }).locator('..').locator('..');
    await expect(cash).toContainText('순이익 100당 현금이 약 90');
    await expect(cash).toContainText('지난 5년(FY2020–FY2024)');
    await expect(cash.getByRole('table')).not.toBeVisible();
    await cash.getByText('연도별 현금 근거 (5개 회계연도)', { exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(cash.getByRole('table')).toBeVisible();
    await expect(cash.getByRole('table')).toContainText('TWD');
    await expect(cash.getByRole('table').locator('tbody tr')).toHaveCount(5);
    expect(writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const viewportWidth = page.viewportSize()!.width;
    expect(await page.evaluate(() => innerWidth)).toBeLessThanOrEqual(viewportWidth + 1);
    expect((await cash.boundingBox())!.x + (await cash.boundingBox())!.width).toBeLessThanOrEqual(viewportWidth + 1);
    await page.locator('.price-cash-table').focus();
    await page.keyboard.press('ArrowRight');
    await page.locator('.price-return-parts').scrollIntoViewIfNeeded();
    const a11y = await new AxeBuilder({ page }).include('[data-price-tab]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(a11y.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)).toEqual([]);
    if (process.env.PRICE_CAPTURE_DIR) {
      await page.locator('.price-hero').scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/crosschecks-${theme}-${test.info().project.name}.png` });
      await page.locator('.price-no-growth').scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/no-growth-${theme}-${test.info().project.name}.png` });
      await cash.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/cash-${theme}-${test.info().project.name}.png` });
    }
  });
}

test('0.9.1 limited quote support still displays raw cash, and legacy calculation stays read-only', async ({ page }) => {
  const limited = { ...V4, results: { ...V4.results, support: { status: 'limited', reasons: [{ code: 'currency_mismatch' }], notices: [] } } };
  const writes = await mockApi(page, { view: limited });
  await openPrice(page, 'dark');
  const tab = page.locator('[data-price-tab]');
  await expect(tab.getByRole('heading', { name: '이익이 현금으로 남았나' })).toBeVisible();
  await expect(tab.locator('.price-card')).toHaveCount(0);
  await tab.getByRole('button', { name: '열기' }).click();
  await expect(page.getByRole('dialog', { name: '2026-09-01 계산' })).toContainText('이 계산 기록에는 없는 항목입니다');
  expect(writes).toEqual([]);
});

test('0.9.1 no-growth sentence uses the pre-rounding branch and cash handles losses and gaps', async ({ page }) => {
  const view = { ...V4, results: { ...V4.results, cashConversion: { ...CASH, ratio: '-0.2050', class: 'cash_below_earnings', years: CASH.years.map(r => ({ ...r, fiscalYear: r.fiscalYear === 2022 ? 2018 : r.fiscalYear })).sort((a,b) => a.fiscalYear-b.fiscalYear) } } };
  await mockApi(page, { view, projection: projection({ noGrowth: { ...NOGROWTH, value: '100.00', growthShare: '-0.0000', priceCoverage: '1.0000', hasGrowthShare: false } }) });
  await openPrice(page, 'light');
  await expect(page.locator('.price-no-growth')).toContainText('성장이 없어도 지금 가격이 설명됩니다(성장 없는 가치가 가격의 1.0배)');
  await expect(page.locator('[data-price-tab]')).toContainText('같은 기간 순이익은 플러스였지만 설비투자를 뺀 현금은 마이너스였습니다.');
  await expect(page.locator('[data-price-tab]')).toContainText('5개 회계연도(FY2018–FY2024)');
});

test('0.9.1 leaving the price screen stops polling without cancelling the server job', async ({ page }) => {
  await mockApi(page);
  let polls = 0;
  await page.route('**/api/price-snapshots/calculate', route => route.fulfill({ json: { id: 'price-job', status: 'running' } }));
  await page.route('**/api/jobs/price-job', route => { polls++; return route.fulfill({ json: { id: 'price-job', status: 'running' } }); });
  await openPrice(page, 'light');
  await page.getByRole('button', { name: '다시 계산', exact: true }).click();
  await expect.poll(() => polls).toBeGreaterThan(0);
  await page.goto('/#/home');
  const stopped = polls;
  await page.waitForTimeout(2200);
  expect(polls).toBe(stopped);
});

async function mockApi(page: Page, options: Options = {}) {
  const writes: { path: string; body: unknown }[] = [];
  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() !== 'GET') writes.push({ path, body: request.postDataJSON() });
    if (path === '/api/watchlist') return route.fulfill({ json: { items: [{ ticker: 'ABC', name: '예시기업', market: 'US' }], watchlist: ['ABC'] } });
    if (path === '/api/watchlist/overview') return route.fulfill({ json: { items: [{ ticker: 'ABC', name: '예시기업', item: 'ABC', market: 'US', newsCount: 0 }] } });
    if (path === '/api/watchlist/detail') return route.fulfill({ json: { item: 'ABC', company: { ticker: 'ABC', name: '예시기업', market: 'US' }, news: [] } });
    if (path === '/api/price-snapshots' && request.method() === 'GET') return route.fulfill({ json: options.empty ? { instrumentId: 'US:ABC', latest: null, history: [], lastAttempt: null } : options.overview ?? OVERVIEW });
    if (path === '/api/price-snapshots/price-now') return route.fulfill({ json: options.view ?? VIEW });
    if (path === '/api/price-snapshots/price-old') return route.fulfill({ json: { ...VIEW, snapshotId: 'price-old', asOf: '2026-09-01', inputSummary: { ...VIEW.inputSummary, price: { ...VIEW.inputSummary.price, value: '90.00' } } } });
    if (path === '/api/price-snapshots/price-now/projection') return route.fulfill({ json: options.projection ?? projection() });
    if (path === '/api/valuation/criteria' && request.method() === 'GET') return route.fulfill({ json: { criteria: 'criteria' in options ? options.criteria : CRITERIA } });
    if (path === '/api/valuation/criteria') return route.fulfill({ json: { criteria: { ...CRITERIA, revisionId: 2 } } });
    if (path === '/api/valuation/assumptions' && request.method() === 'GET') return route.fulfill({ json: { override: null } });
    if (path === '/api/valuation/assumptions') return route.fulfill({ json: { override: { overrideId: 1 } } });
    return route.fulfill({ status: 404, json: {} });
  });
  return writes;
}

async function openPrice(page: Page, theme: string) {
  await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
  await page.goto('/#/watchlist/ABC');
  await page.getByRole('button', { name: '가격', exact: true }).click();
}

test('0.9.1 loading and read failure recover without rewriting saved results', async ({ page }) => {
  const writes = await mockApi(page, { view: V4, projection: projection({ noGrowth: NOGROWTH }) });
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  const pattern = '**/api/price-snapshots?**';
  await page.route(pattern, async route => {
    await waiting;
    return route.fulfill({ status: 503, json: { detail: 'temporary read failure' } });
  });
  await openPrice(page, 'light');
  await expect(page.getByRole('status').filter({ hasText: '가격 계산 기록을 불러오는 중' })).toBeVisible();
  release();
  await expect(page.getByRole('alert')).toContainText('가격 계산 기록을 읽지 못했습니다.');
  await expect(page.getByRole('alert')).toContainText('이전 기록은 지워지지 않았습니다.');
  await page.unroute(pattern);
  await page.getByRole('button', { name: '다시 읽기', exact: true }).click();
  await expect(page.locator('.price-return-parts')).toContainText('기본 10년');
  expect(writes).toEqual([]);
});

for (const theme of ['light', 'dark']) {
  test(`0.9 price tab reads as one sentence, three cards and a scale ${theme}`, async ({ page }) => {
    const writes = await mockApi(page);
    await openPrice(page, theme);
    const tab = page.locator('[data-price-tab]');
    if (process.env.PRICE_CAPTURE_DIR) await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/${theme}-${test.info().project.name}.png`, fullPage: true });
    await expect(tab.getByRole('heading', { level: 3, name: '10년간 연 6.6%로, 내 기준 연 6%보다 높습니다.' })).toBeVisible();
    await expect(tab.getByText('회사가 과거 보통 수준으로 성장하고')).toBeVisible();

    // 카드 세 장: 기본이 처음부터 선택돼 있고, 같은 카드를 다시 누르면 기본으로 돌아간다. 강조는 보기용이다.
    const cards = tab.locator('.price-card');
    await expect(cards).toHaveCount(3);
    await expect(cards.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await cards.nth(2).click();
    await expect(cards.nth(2)).toHaveAttribute('aria-pressed', 'true');
    await cards.nth(2).click();
    await expect(cards.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.getByRole('img', { name: /^10년 보유 시 연 수익률: 보수 4\.5%, 기본 6\.6%, 낙관 9\.8%\. 내 기준 연 6%/ })).toBeVisible();
    await expect(tab.getByRole('heading', { level: 3, name: '10년간 연 6.6%로, 내 기준 연 6%보다 높습니다.' })).toBeVisible();

    // 판정은 기본 보유 기간으로만 한다: 5년으로 바꿔도 비교 문장은 기본 보유 10년을 말한다.
    await tab.getByRole('button', { name: '5년', exact: true }).click();
    await expect(tab.getByRole('heading', { level: 3, name: '5년간 연 5.9%입니다.' })).toBeVisible();
    await expect(tab.getByText('내 기준 비교는 기본 보유 10년(연 6.6%)')).toBeVisible();
    await expect(tab.locator('.price-verdict .chip').first()).toHaveText('수익률 기준 충족 · 10년');
    await expect(tab.locator('.price-verdict')).toContainText('안전마진 판정 보류');

    // 표와 역산과 분해.
    await expect(tab.locator('.price-table tbody tr')).toHaveCount(3);
    await expect(tab.locator('.price-table tbody tr').nth(1)).toContainText('과거 10년의 중간값');
    await expect(tab.getByText('손실이 나지 않으려면(손익분기)').first()).toBeVisible();
    await expect(tab.getByText('본전')).toHaveCount(0);
    await expect(tab.getByRole('img', { name: /^매출이 늘어서 연 \+5\.0%/ })).toBeVisible();
    await tab.locator('.price-dec__card').first().click();
    await expect(tab.locator('.price-dec__card').first()).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.locator('.price-dec__bar span.is-dim')).toHaveCount(2);

    // 확률·목표가·매수매도 표현이 없다.
    for (const word of ['확률', '목표가', '적정가', '매수', '매도', '고평가', '저평가', '상승여력']) await expect(tab).not.toContainText(word);

    // 읽기만 했으니 쓰기는 없다.
    expect(writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const a11y = await new AxeBuilder({ page }).include('[data-price-tab]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(a11y.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(" ")).join(" | ")}`)).toEqual([]);
  });
}

test('0.9 first run, criteria dialog saves exact decimal text, previous result is read-only', async ({ page }) => {
  const writes = await mockApi(page, { empty: true, criteria: null });
  await openPrice(page, 'light');
  const tab = page.locator('[data-price-tab]');
  await expect(tab.getByRole('heading', { level: 3, name: '아직 이 종목의 가격을 계산하지 않았습니다.' })).toBeVisible();
  await expect(tab.getByRole('button', { name: '계산하기' })).toBeVisible();
  await expect(tab.locator('.price-table')).toHaveCount(0);
  expect(writes).toEqual([]);

  // 값이 있는 화면으로 다시 연다.
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  const next = await mockApi(page, { criteria: null, projection: projection({ criteria: null, verdict: { return: { state: 'unknown', reason: 'criteria_not_set' }, marginOfSafety: { state: 'unknown', reason: 'criteria_not_set' } }, requirement: { status: 'unavailable', reason: { code: 'criteria_not_set' } } }) });
  await page.reload();
  await page.getByRole('button', { name: '가격', exact: true }).click();
  await expect(tab.getByRole('heading', { level: 3, name: '10년간 연 6.6%입니다.' })).toBeVisible();
  await expect(tab.locator('.price-verdict .chip')).toHaveText('내 기준 없음');
  await tab.getByRole('button', { name: '기준 정하기' }).first().click();
  const dialog = page.getByRole('dialog', { name: '투자 기준' });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('원하는 연 수익률 (%)').fill('6.5');
  await dialog.getByLabel('기본 보유 기간').selectOption('10');
  await dialog.getByRole('button', { name: '저장' }).click();
  await expect.poll(() => next.length).toBe(1);
  expect(next[0]).toEqual({ path: '/api/valuation/criteria', body: { requiredReturn: '6.5', minMarginOfSafety: null, holdingYears: 10, expectedRevisionId: null } });

  // 이전 계산은 읽기만 한다.
  await tab.getByRole('button', { name: '열기' }).click();
  const previous = page.getByRole('dialog', { name: '2026-09-01 계산' });
  await expect(previous).toContainText('당시 종가 $90.00');
  await expect(previous).toContainText('읽기만 하는 화면');
  await previous.getByRole('button', { name: '닫기' }).click();
  expect(next.length).toBe(1);
});

test('0.9 correction banner and old-basis assumptions are shown without rewriting anything', async ({ page }) => {
  const reviewed = { ...OVERVIEW, history: [OVERVIEW.history[0], { ...OVERVIEW.history[1], reviewCount: 1 }] };
  const writes = await mockApi(page, { overview: reviewed, projection: projection({
    reviewNeeded: [{ reason: 'restated', metric: 'EPS Diluted', fiscalYear: 2024, detectedBySnapshotId: 'price-new' }],
    myAssumptions: { overrideId: 1, basedOnSnapshotId: 'price-old', basedOnCurrentSnapshot: false, rows: [{ horizon: 10, status: 'available', g: '0.1200', exitPE: '18.00', payout: '0.3000', irr: '0.0900', irrRange: null }] },
  }) });
  await openPrice(page, 'light');
  const tab = page.locator('[data-price-tab]');
  await expect(tab.getByText('계산에 쓴 공시 숫자가 정정됐습니다.')).toBeVisible();
  await expect(tab.locator('.price-history').getByText('다시 볼 필요')).toBeVisible();
  await expect(tab.getByText('내 가정은 이전 계산을 바탕으로 합니다.')).toBeVisible();
  await expect(tab.getByText('내 가정이면 10년 보유 시')).toContainText('연 9.0%');
  await expect(tab.locator('.price-mine')).not.toContainText('기준 충족');
  expect(writes).toEqual([]);
});

test('0.9 scale labels never overlap, even when the personal goal sits far from the three cases', async ({ page }) => {
  for (const viewport of [{ width: 1280, height: 900 }, { width: 375, height: 812 }]) {
    await page.setViewportSize(viewport);
    await mockApi(page, { criteria: { ...CRITERIA, requiredReturn: '30' }, projection: projection({ criteria: { revisionId: 1, holdingYears: 10, requiredReturn: '30', minMarginOfSafety: '20' } }) });
    await openPrice(page, 'light');
    const bar = page.locator('[data-price-tab] .price-hr');
    await expect(bar).toBeVisible();
    const boxes = await bar.locator('.price-hr__t').evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return { text: node.textContent, x: r.x, y: r.y, w: r.width, h: r.height }; }));
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i]; const b = boxes[j];
        const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
        expect(overlap, `${a.text} overlaps ${b.text} at ${viewport.width}px`).toBe(false);
      }
    }
  }
});
