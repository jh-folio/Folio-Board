import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const ATTRIBUTION = { status: 'available', requestedYears: 5, startFiscalYear: 2020, endFiscalYear: 2025,
  startDate: '2020-12-31', endDate: '2025-12-31', startClose: '100', endClose: '150', priceReturn: '.5000',
  display: { growth: '20.0', rerating: '30.0', dividend: '5.0', total: '55.0', price: '50.0' },
  earnings: { status: 'available', startEps: '10', endEps: '12', startPE: '10', endPE: '12.5' },
  dividend: { status: 'available', amount: '5', contribution: '.0500' }, total: { status: 'available', value: '.5500' },
  benchmark: { status: 'available', id: 'S&P 500', display: { stock: '50.0', index: '25.0', difference: '25.0' } },
};

for (const theme of ['light', 'dark']) {
  test(`0.9.2 historical attribution selection signed bars and exact visible sum ${theme}`, async ({ page }) => {
    const view = { ...V4, methodVersion: 'price-scenario-5', historicalReturnAttribution: ATTRIBUTION };
    const writes = await mockApi(page, { view });
    await page.route('**/api/price-snapshots/price-now?attributionYears=*', route => route.fulfill({ json: { ...view,
      historicalReturnAttribution: { ...ATTRIBUTION, requestedYears: 3, startFiscalYear: 2022,
        display: { ...ATTRIBUTION.display, rerating: '-25.0', total: '0.0' } } } }));
    await openPrice(page, theme);
    const section = page.locator('.price-section:has(#price-historical-return-title)');
    await expect(section).toContainText('배당 포함 전체 수익 +55.0%');
    await expect(section).toContainText('종목 +50.0% / S&P 500 +25.0%');
    await section.getByRole('button', { name: /PER 변화/ }).click();
    await expect(section.locator('.price-explain')).toContainText('함께 변한 효과');
    if (process.env.PRICE_CAPTURE_DIR) await section.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/attribution-${theme}-${test.info().project.name}.png` });
    await section.getByRole('button', { name: '3년', exact: true }).click();
    await expect(section).toContainText('전체 수익 0.0%');
    await expect(section.getByRole('button', { name: /PER 변화/ })).toContainText('−25.0%p');
    await expect(section).toContainText('별도의 5년 이익 성장 구간');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const result = await new AxeBuilder({ page }).include('[data-price-tab]').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
    expect(result.violations.map(v => v.id)).toEqual([]);
    expect(writes).toEqual([]);
  });
}

test('0.9.2 missing dividend and loss retain price comparison, and legacy inputs explain recalculation', async ({ page }) => {
  const view = { ...V4, methodVersion: 'price-scenario-5', historicalReturnAttribution: { ...ATTRIBUTION,
    display: { price: '50.0' }, earnings: { status: 'unavailable', reason: { code: 'non_positive_end_eps', endFiscalYear: 2025 } },
    dividend: { status: 'unavailable', reason: { code: 'dividend_unit_unverified' } }, total: { status: 'unavailable' } } };
  await mockApi(page, { view }); await openPrice(page, 'light');
  const section = page.locator('.price-section:has(#price-historical-return-title)');
  await expect(section).toContainText('끝 연도 FY2025 주당이익이 0 이하');
  await expect(section).toContainText('배당 금액의 주식 단위를 확인하지 못해');
  await expect(section).toContainText('종목 +50.0% / S&P 500 +25.0%');
});

for (const theme of ['light', 'dark']) {
  test(`0.9.2 chart actions need explicit click and transfer the selected dates ${theme}`, async ({ page }) => {
    const writes = await mockApi(page);
    const reads: string[] = [];
    await page.route('**/api/market/chart?*', route => route.fulfill({ json: { symbol: 'ABC', range: '3m', interval: '1d', provider: 'audit', freshness: 'snapshot',
      series: ['2025-01-02','2025-01-03','2025-01-06'].map((time,i) => ({time,close:100+i,open:100+i,high:102+i,low:98+i})) } }));
    await page.route('**/api/price-movement?*', route => {
      reads.push(route.request().url());
      return route.fulfill({ json: { status:'available', snapshotId:'fixed-price', asOf:'2025-01-06',startDate:'2025-01-02',endDate:'2025-01-06',startClose:'100',endClose:'103',displayPriceReturn:'3.0',
        benchmark:{status:'available',id:'S&P 500',display:{index:'1.0'}} } });
    });
    await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1',value);localStorage.setItem('folio.react.agentClosed','1'); },theme);
    await page.goto('/#/watchlist/ABC');
    const section = page.locator('.watchlist-detail-section--chart');
    await expect(section.getByRole('button',{name:'이 움직임 물어보기'})).toBeEnabled();
    await page.evaluate(() => {
      (window as unknown as { actionRequests: unknown[] }).actionRequests=[];
      window.FolioBridge!.openAgentDock = context => { (window as unknown as { actionRequests:unknown[] }).actionRequests.push(context); };
    });
    const chart = section.locator('.cockpit-chart-stage');
    await chart.focus(); await page.keyboard.press('Home');
    await expect(section.getByRole('link',{name:'기준일 이후 네 축 변화 비교'})).toHaveAttribute('href','#/macro/state?market=US&compareDate=2025-01-02');
    expect(reads).toEqual([]); expect(writes).toEqual([]);
    if(process.env.PRICE_CAPTURE_DIR) await section.screenshot({path:`${process.env.PRICE_CAPTURE_DIR}/chart-${theme}-${test.info().project.name}.png`});
    const axe = await new AxeBuilder({page}).include('.watchlist-detail-section--chart').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
    expect(axe.violations.map(v=>v.id)).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await section.getByRole('button',{name:'이 움직임 물어보기'}).click();
    await expect.poll(()=>page.evaluate(()=>(window as unknown as {actionRequests:unknown[]}).actionRequests.length)).toBe(1);
    const action = await page.evaluate(()=>(window as unknown as {actionRequests:Record<string,unknown>[]}).actionRequests[0]);
    expect(action.chartMovement).toEqual({instrumentId:'US:ABC',snapshotId:'fixed-price',startDate:'2025-01-02',endDate:'2025-01-06'});
    expect(action.prompt).toContain('배당 제외 +3.0%'); expect(action.autoSubmit).toBe(true);
    await expect(section).toContainText('차트 종가와 저장 종가가 다릅니다');
  });
}

test('0.9.2 failed index and dividend preserve the observed stock return', async ({ page }) => {
  await mockApi(page, { view: { ...V4, methodVersion: 'price-scenario-5', historicalReturnAttribution: { ...ATTRIBUTION,
    display: { price: '50.0', growth: '20.0', rerating: '30.0' }, dividend: {status:'unavailable',reason:{code:'dividend_history_unavailable'}},
    total:{status:'unavailable'}, benchmark:{status:'unavailable',reason:{code:'benchmark_unavailable'}} } } });
  await openPrice(page, 'dark');
  const section = page.locator('.price-section:has(#price-historical-return-title)');
  await expect(section).toContainText('배당 제외 주가 수익: 종목 +50.0%');
  await expect(section).toContainText('시장지수 자료를 확인하지 못해');
  await expect(section).toContainText('배당 포함 전체 수익을 계산하지 않았습니다');
});

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

const REFERENCE = { status: 'available', currency: 'USD', peNow: { status: 'available', state: 'loss', value: null },
  psNow: { status: 'available', value: '10.5000' }, sbcBasis: 'not_deducted', notices: [{ code: 'sbc_missing_years', years: [2023] }],
  years: [2023, 2024, 2025].map(fiscalYear => ({ fiscalYear, revenue: '100', revenueGrowth: fiscalYear === 2023 ? null : '0.1000',
    netMargin: '-0.2500', fcf: fiscalYear === 2025 ? null : '0', fcfMargin: fiscalYear === 2025 ? null : '0.0000',
    reasons: { revenueGrowth: { code: 'missing_value' }, fcf: { code: 'missing_value' }, fcfMargin: { code: 'missing_value' } } })) };
const BLOCKED = { ...V4, results: { ...V4.results, referenceFacts: REFERENCE,
  scenarios: SCENARIOS.map(r => ({ label: r.label, horizon: r.horizon, status: 'unavailable', reason: { code: 'negative_base_eps' } })) } };

for (const theme of ['light', 'dark']) {
  test(`0.9.1 reference facts loss, missing latest cash, keyboard and axe ${theme}`, async ({ page }) => {
    const writes = await mockApi(page, { view: BLOCKED });
    await openPrice(page, theme);
    const section = page.locator('.price-section:has(#price-reference-title)');
    await expect(section.getByRole('heading', { name: '수익률 대신 볼 수 있는 숫자' })).toBeVisible();
    await expect(page.locator('.price-hero')).toContainText('최근 연도 주당이익이 0 이하라 수익률 계산을 하지 않았습니다');
    // 수익률이 한 칸도 없으면 빈 카드·보유 기간·①② 묶음을 그리지 않는다.
    const tab = page.locator('[data-price-tab]');
    await expect(tab.getByRole('heading', { level: 3, name: '이 종목은 수익률을 계산하지 못했습니다.' })).toBeVisible();
    await expect(tab.locator('.price-card')).toHaveCount(0);
    await expect(tab.getByRole('button', { name: '5년', exact: true })).toHaveCount(0);
    await expect(tab.locator('.price-part')).toHaveCount(0);
    await expect(tab.locator('.price-glance')).toHaveCount(0);
    await expect(tab.getByText('계산 불가')).toHaveCount(0);
    await expect(tab.getByRole('button', { name: '다시 계산' })).toBeVisible();
    await expect(section.locator('.price-dec__card')).toHaveText([/지금 PER.*최근 연도 적자/, /매출 대비 주가.*10\.5배/, /최근 연도 남은 현금 비율.*해당 연도의 공시 값이 없어 표시하지 않았습니다/]);
    await expect(section.getByRole('table')).not.toBeVisible();
    await section.getByText('연도별 참고 숫자 (3개 회계연도)', { exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(section.getByRole('table')).toBeVisible();
    await expect(section.getByRole('table')).toContainText('−25.0%');
    await expect(section.getByRole('table').locator('tbody tr').nth(1)).toContainText('$0');
    expect(await page.locator('[data-price-tab]').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await expect(section).not.toContainText(/판정|매수|매도|목표가/);
    expect((await new AxeBuilder({ page }).include('[data-price-tab]').analyze()).violations).toEqual([]);
    if (process.env.PRICE_CAPTURE_DIR) {
      await section.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/reference-${theme}-${test.info().project.name}.png` });
    }
    expect(writes).toEqual([]);
  });
}

test('0.9.1 a fund is told in the headline, not as a first-run prompt with a contradicting banner', async ({ page }) => {
  const writes = await mockApi(page, { overview: { instrumentId: 'US:ABC', latest: null, history: [],
    lastAttempt: { status: 'failed', reason: { code: 'fund_not_supported' }, finishedAt: '2026-10-04T01:00:00Z' } } });
  await openPrice(page, 'light');
  const tab = page.locator('[data-price-tab]');
  await expect(tab.getByRole('heading', { level: 3, name: '이 종목은 이 계산의 대상이 아닙니다.' })).toBeVisible();
  await expect(tab.locator('.price-hero')).toContainText('ETF·펀드는');
  await expect(tab.getByText('아직 이 종목의 가격을 계산하지 않았습니다.')).toHaveCount(0);
  await expect(tab.getByText('이번에는 계산하지 못했습니다.')).toHaveCount(0);
  await expect(tab.getByRole('button', { name: '다시 확인' })).toBeVisible();
  expect(writes).toEqual([]);
});

test('0.9.1 reference facts zero and short records; other blocks stay hidden', async ({ page }) => {
  const short = { code: 'history_too_short', subCode: 'years_too_few', range: 'growth', n: 0, required: 3, historyYears: 3 };
  const view = { ...BLOCKED, results: { ...BLOCKED.results, referenceFacts: { ...REFERENCE, peNow: { status: 'available', state: 'zero', value: null } },
    scenarios: BLOCKED.results.scenarios.map(r => ({ ...r, reason: short })) } };
  await mockApi(page, { view });
  await openPrice(page, 'light');
  await expect(page.locator('.price-section:has(#price-reference-title)')).toContainText('최근 연도 주당이익 0');
  await expect(page.locator('.price-hero')).toContainText('재무 기록이 3년뿐이라');
  // A single other reason closes this section even though values are stored.
  await page.unroute('**/api/**');
  await mockApi(page, { view: { ...BLOCKED, results: { ...BLOCKED.results,
    scenarios: BLOCKED.results.scenarios.map((r, i) => i ? r : { ...r, reason: { code: 'share_event_unknown' } }) } } });
  await page.reload();
  await expect(page.locator('#price-reference-title')).toHaveCount(0);
});

for (const theme of ['light', 'dark']) {
  test(`0.9.1 crosschecks card selection, cash table and keyboard ${theme}`, async ({ page }) => {
    const writes = await mockApi(page, { view: V4, projection: projection({ noGrowth: NOGROWTH }) });
    await openPrice(page, theme);
    const tab = page.locator('[data-price-tab]');
    // 읽는 순서: 결론 → 한눈에 보기 → ①②③ 묶음.
    await expect(tab.getByRole('heading', { level: 3, name: '한눈에 보기' })).toBeVisible();
    for (const name of ['얼마를 벌 수 있나', '지금 가격이 무엇을 가정하나', '과거 기록은 어땠나']) await expect(tab.getByRole('heading', { level: 3, name })).toBeVisible();
    await expect(tab.locator('.price-glance')).toContainText('사고팔라는 의견이나 판정이 아닙니다');

    // A: 결론 카드·보유 기간을 따라가고, 조각 카드를 누르면 그 조각만 남기고 설명한다.
    const parts = tab.locator('.price-section:has(#price-parts-title)');
    await expect(parts).toContainText('연 6.6%를 나눠 보면');
    await expect(parts.locator('.price-dec__card')).toHaveText([/이익 성장\s*\+6\.0%/, /배당\s*\+1\.5%/, /PER 변화.*−0\.9%/]);
    await expect(parts).toContainText('PER이 지금 20.0배 그대로라면 연 7.5%');
    await parts.locator('.price-dec__card').nth(2).click();
    await expect(parts.locator('.price-dec__card').nth(2)).toHaveAttribute('aria-pressed', 'true');
    await expect(parts.locator('.price-explain')).toContainText('PER 변화 −0.9%');
    await expect(parts.locator('.price-dec__bar .is-dim')).toHaveCount(2);
    await tab.locator('.price-card').nth(2).focus();
    await page.keyboard.press('Enter');
    await expect(parts).toContainText('낙관 · 10년 보유');
    await tab.getByRole('button', { name: '5년', exact: true }).click();
    await expect(parts).toContainText('낙관 · 5년 보유');

    // B: 카드는 보기만 한다(버튼 아님).
    const noGrowth = tab.locator('.price-section:has(#price-no-growth-title)');
    await expect(noGrowth).toContainText('지금 가격의 약 50%는 앞으로의 성장에 거는 몫입니다.');
    await expect(noGrowth).toContainText('$50.00');
    await expect(noGrowth).toContainText('최근 주당이익은 $5.00');
    await expect(noGrowth.getByRole('button')).toHaveCount(0);

    // C: 섹션은 문장·카드·막대, 연도별 표는 아래 접기 목록에 있다.
    const cash = tab.locator('.price-section:has(#price-cash-title)');
    await expect(cash).toContainText('순이익 100당 현금이 약 90');
    await expect(cash).toContainText('지난 5년(FY2020–FY2024)');
    await expect(cash.getByRole('button')).toHaveCount(0);
    const folds = tab.locator('.price-folds');
    await expect(folds.getByRole('table')).not.toBeVisible();
    await folds.getByText('연도별 현금 근거 (5개 회계연도)', { exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(folds.getByRole('table')).toBeVisible();
    await expect(folds.getByRole('table')).toContainText('TWD');
    await expect(folds.getByRole('table').locator('tbody tr')).toHaveCount(5);
    // 펼친 표는 자기 상자 안에서만 옆으로 넘긴다: 가격 탭 전체가 옆으로 밀리지 않는다.
    expect(await tab.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);

    // 한눈에 보기의 링크는 해시 주소를 바꾸지 않고 해당 섹션으로 옮겨 준다.
    const hash = await page.evaluate(() => location.hash);
    await tab.locator('.price-glance').getByRole('button', { name: '③ 이익이 현금으로 남았나' }).click();
    await expect(page.locator('#price-cash-title')).toBeInViewport();
    expect(await page.evaluate(() => location.hash)).toBe(hash);
    expect(writes).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const viewportWidth = page.viewportSize()!.width;
    expect(await page.evaluate(() => innerWidth)).toBeLessThanOrEqual(viewportWidth + 1);
    expect((await cash.boundingBox())!.x + (await cash.boundingBox())!.width).toBeLessThanOrEqual(viewportWidth + 1);
    await page.locator('.price-cash-table').focus();
    await page.keyboard.press('ArrowRight');
    await parts.scrollIntoViewIfNeeded();
    const a11y = await new AxeBuilder({ page }).include('[data-price-tab]').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(a11y.violations.map(v => `${v.id}: ${v.nodes.map(n => n.target.join(' ')).join(' | ')}`)).toEqual([]);
    if (process.env.PRICE_CAPTURE_DIR) {
      await page.locator('.price-hero').scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/crosschecks-${theme}-${test.info().project.name}.png` });
      await noGrowth.scrollIntoViewIfNeeded();
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
  await expect(page.locator('.price-section:has(#price-no-growth-title)')).toContainText('성장이 없어도 지금 가격이 설명됩니다(성장 없는 가치가 가격의 1.0배)');
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
  await expect(page.locator('.price-section:has(#price-parts-title)')).toContainText('기본 · 10년 보유');
  expect(writes).toEqual([]);
});

for (const theme of ['light', 'dark']) {
  test(`0.9 price tab reads as one sentence, three cards and a scale ${theme}`, async ({ page }) => {
    const writes = await mockApi(page);
    await openPrice(page, theme);
    const tab = page.locator('[data-price-tab]');
    if (process.env.PRICE_CAPTURE_DIR) await page.screenshot({ path: `${process.env.PRICE_CAPTURE_DIR}/${theme}-${test.info().project.name}.png`, fullPage: true });
    await expect(tab.getByRole('heading', { level: 3, name: /^과거 10년 흐름이 이어진다면, 지금 사서 10년 보유할 때 연평균 6\.6%입니다\.\s*내가 정한 최소 수익률\(연 6%\)보다 높습니다\.$/ })).toBeVisible();
    await expect(tab.getByText('이 흐름이 앞으로 10년도 비슷하다고 보고 계산한 값이며, 보장된 수익이 아닙니다.')).toBeVisible();

    // 카드 세 장: 기본이 처음부터 선택돼 있고, 같은 카드를 다시 누르면 기본으로 돌아간다. 강조는 보기용이다.
    const cards = tab.locator('.price-card');
    await expect(cards).toHaveCount(3);
    await expect(cards.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await cards.nth(2).click();
    await expect(cards.nth(2)).toHaveAttribute('aria-pressed', 'true');
    await cards.nth(2).click();
    await expect(cards.nth(1)).toHaveAttribute('aria-pressed', 'true');
    await expect(tab.getByRole('img', { name: /^10년 보유 시 연 수익률: 보수 4\.5%, 기본 6\.6%, 낙관 9\.8%\. 내 기준 연 6%/ })).toBeVisible();
    await expect(tab.getByRole('heading', { level: 3, name: /^과거 10년 흐름이 이어진다면, 지금 사서 10년 보유할 때 연평균 6\.6%입니다\.\s*내가 정한 최소 수익률\(연 6%\)보다 높습니다\.$/ })).toBeVisible();

    // 판정은 기본 보유 기간으로만 한다: 5년으로 바꿔도 비교 문장은 기본 보유 10년을 말한다.
    await tab.getByRole('button', { name: '5년', exact: true }).click();
    await expect(tab.getByRole('heading', { level: 3, name: /^과거 10년 흐름이 이어진다면, 지금 사서 5년 보유할 때 연평균 5\.9%입니다\./ })).toBeVisible();
    await expect(tab.locator('.price-hero__title2')).toHaveText('내 기준 비교는 기본 보유 기간(10년)으로 합니다. 10년 연평균 6.6%로, 최소 수익률(연 6%)보다 높습니다.');
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

    // 전제 줄을 누르면(키보드 포함) 계산 방법이 펼쳐지고, 보유 기간을 바꾸면 그 기간 설명으로 바뀐다.
    const premise = tab.locator('.price-rev--toggle').first();
    await premise.click();
    await expect(premise).toHaveAttribute('aria-expanded', 'true');
    await expect(tab.locator('.price-rev-explain')).toContainText('5년 뒤 PER을 바꿔 가며 연 수익률이 정확히 0%가 되는 지점');
    await tab.getByRole('button', { name: '10년', exact: true }).click();
    await expect(tab.locator('.price-rev-explain')).toContainText('10년 뒤 PER을 바꿔 가며');
    await premise.focus();
    await page.keyboard.press('Enter');
    await expect(premise).toHaveAttribute('aria-expanded', 'false');
    await expect(tab.locator('.price-rev-explain')).toHaveCount(0);

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
  await expect(tab.getByRole('heading', { level: 3, name: '과거 10년 흐름이 이어진다면, 지금 사서 10년 보유할 때 연평균 6.6%입니다.', exact: true })).toBeVisible();
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
