import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// Display fixtures; the Decimal hand calculations and read/write boundary have separate Python tests.
const options = ['NONE', 'SHORT', 'LONG', 'ETF', 'OLD', '7203.T'];
const identities = options.map(ticker => `${ticker === '7203.T' ? 'JP' : 'US'}:${ticker}`);
function candidate(id: string) {
  const ticker = id.split(':')[1];
  const state = ['ETF', '7203.T'].includes(ticker) ? 'unknown' : ticker === 'OLD' ? 'stale' : 'ready_for_review';
  const currency = ticker === 'SHORT' ? 'EUR' : 'USD';
  const cell = (value: unknown, gaps: string[] = []) => ({ status: value === null ? 'unavailable' : 'available', value, currency, freshness: 'current', basis: { asOf: '2026-10-06' }, sourceRefs: [], dataGaps: gaps });
  return { identity: { instrumentId: id }, sourceRefs: { instrumentId: id, snapshotId: `price-${ticker}` },
    readiness: { state, message: state === 'ready_for_review' ? '가격과 내 기준을 검토할 자료가 갖춰졌습니다' : state === 'stale' ? '오래되었거나 정정된 자료를 다시 확인해야 합니다' : '기준이나 자료가 없어 준비 상태를 확인할 수 없습니다', scopeCopy: '가격과 내 기준의 확인 범위입니다. 다른 자료 공백은 아래에 남아 있으며 투자 판단이나 안전성을 뜻하지 않습니다.', snapshotId: `price-${ticker}`, criteriaRevisionId: 1,
      criteria: { requiredReturn: { state: state === 'ready_for_review' ? 'met' : 'unknown' }, minMarginOfSafety: { state: state === 'ready_for_review' ? 'met' : 'unknown' }, holdingYears: { state: 'met' }, allowAboveHistoricalRange: { state: 'unknown' } }, blockingReasons: state === 'stale' ? ['snapshot_old'] : state === 'unknown' ? ['unsupported_model'] : [], warnings: ['company_exposure_not_investigated'] },
    dimensions: { companyQuality: cell('재무 품질: 현금 전환과 경쟁 압력에 확인할 부분이 있습니다.', ['excerpt_is_not_a_company_score']), scenarioReturn: cell(state === 'unknown' ? null : [{ label: 'base', horizon: 10, status: 'available', irr: '.12' }], state === 'unknown' ? ['price_model_unavailable'] : []), uncertainty: cell({ blockingReasons: [], reviewRows: [] }), macroFit: cell(null, ['company_exposure_not_investigated']), returnSource: cell(null, ['return_attribution_not_stored']), reasonState: cell({ status: ticker === 'NONE' ? 'unwritten' : 'unreviewed', text: ticker === 'SHORT' ? '한 줄 이유' : ticker === 'LONG' ? '긴 분석과 반증 조건입니다. '.repeat(20) : '' }), portfolioOverlap: cell({ heldSameSecurity: false, industry: '미조사', quoteCurrency: currency }, ['overlap_weights_not_captured']) } };
}
function result(ids: string[]) {
  const rows = ids.map(candidate);
  const comparability: any[] = [];
  rows.forEach((left, i) => rows.slice(i + 1).forEach(right => comparability.push({ left: left.identity.instrumentId, right: right.identity.instrumentId,
    dimensions: Object.fromEntries(Object.keys(left.dimensions).map(key => [key, { status: 'incomparable', reasons: key === 'scenarioReturn' ? ['currency_different'] : [] }])) })));
  return { evaluatedAt: '2026-10-06T10:00:00Z', candidates: rows, comparability, inputFingerprint: 'fixture', referenceSet: { candidates: rows.map(row => row.sourceRefs), criteriaRevisionId: 1, portfolioHash: 'original' }, notice: '선택한 순서로 같은 항목을 나란히 봅니다. 순위나 투자 결론이 아닙니다.' };
}
function preview() {
  const composition = (security: Record<string, string>, industry: Record<string, string>, currency: Record<string, string>, max: string, topSum: string, unknown: string) => ({ security, industry, currency, concentration: { maxHolding: max, top3: topSum, top5: topSum }, macro: { 'interest_rate:hurt_by_rise': security['US:A'] }, coverage: [{ instrumentId: 'US:A', profileId: 'profile-fixture', weight: security['US:A'], items: [{ factor: 'interest_rate', direction: 'hurt_by_rise', quote: 'Higher interest rates increase borrowing costs.', magnitudeBasis: 'qualitative_only', sourceRefs: [{ date: '2026-01-01', form: '10-K', url: 'https://www.sec.gov/Archives/example' }] }] }], uninvestigatedHoldingWeight: unknown, etfLookThrough: [] });
  return { status: 'available', candidateWeightPercent: '20.00', assumption: '후보의 최종 비중을 바꾸고 나머지 자산과 현금을 같은 비율로 조정합니다.', dataGaps: [], sourceRefs: {},
    before: composition({ 'US:A': '.6', 'KR:000001': '.3', 'cash:0': '.1' }, { same: '.6', other: '.3', '현금': '.1' }, { USD: '.7', KRW: '.3' }, '.6', '.9', '.3'),
    after: composition({ 'US:A': '.48', 'KR:000001': '.24', 'cash:0': '.08', 'US:C': '.2' }, { same: '.68', other: '.24', '현금': '.08' }, { USD: '.76', KRW: '.24' }, '.48', '.92', '.44'),
    delta: composition({ 'US:A': '-.12', 'KR:000001': '-.06', 'cash:0': '-.02', 'US:C': '.2' }, { same: '.08', other: '-.06', '현금': '-.02' }, { USD: '.06', KRW: '-.06' }, '-.12', '.02', '.14'), notice: '공시 노출 비중은 확인된 보유 비중이며 전체 위험률이 아닙니다.' };
}
async function mock(page: Page, theme: string) {
  const calls: Array<{ path: string; method: string; body: any }> = [];
  const control = { expired: false, changed: false, failComparison: false };
  await page.route('**/*', async route => {
    const req = route.request(); const url = new URL(req.url());
    if (url.hostname !== '127.0.0.1') return route.abort();
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const path = url.pathname; const body = req.postData() ? req.postDataJSON() : null;
    calls.push({ path, method: req.method(), body });
    const send = (json: unknown, status = 200) => route.fulfill({ status, json });
    if (path === '/api/watchlist') return send({ watchlist: options, items: options.map((ticker, index) => ({ ticker, item: ticker, name: ticker, market: index === 5 ? 'JP' : 'US' })) });
    if (path === '/api/watchlist/overview') return send({ items: options.map((ticker, index) => ({ ticker, item: ticker, name: ticker, market: index === 5 ? 'JP' : 'US', newsCount: 0 })) });
    if (path === '/api/watchlist/detail') return send({ item: url.searchParams.get('item'), company: { ticker: url.searchParams.get('item'), market: 'US', name: '선택 후보' }, news: [] });
    if (path === '/api/opportunity-comparison') return control.expired && body.portfolioBasisId ? send({ detail: { code: 'portfolio_basis_expired' } }, 409) : control.failComparison ? send({ detail: { code: 'decision_store_unavailable' } }, 503) : send(result(body.candidates.map((row: any) => row.instrumentId)));
    if (path.startsWith('/api/decision-readiness/')) { const id = decodeURIComponent(path.slice('/api/decision-readiness/'.length)); return send({ ...candidate(id), referenceSet: { candidates: [candidate(id).sourceRefs], criteriaRevisionId: control.changed ? 2 : 1, portfolioHash: 'original' } }); }
    if (path === '/api/portfolio') return send({ schemaVersion: 3, revision: 1, positions: [], cash: [] });
    if (path === '/api/portfolio/decision-preview/basis') return send({ basisId: 'basis-fixture', candidate: { instrumentId: body.instrumentId }, portfolioRevision: 1, basisFingerprint: 'basis', expiresAt: '2026-10-06T10:30:00Z', dataGaps: [] });
    if (path === '/api/portfolio/decision-preview') return control.expired ? send({ detail: { code: 'portfolio_basis_expired' } }, 409) : send(preview());
    if (path === '/api/portfolio/presets' || path === '/api/portfolio/backtests') return send([]);
    if (path === '/api/investment-review/history') return send({ items: [] });
    return send({ detail: 'isolated fixture' }, 404);
  });
  await page.addInitScript(selected => { localStorage.setItem('folio.themePreference.v1', selected); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
  return { calls, control };
}
async function checkSurface(page: Page, selector: string, name: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  const axe = await new AxeBuilder({ page }).include(selector).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
  expect(axe.violations.map(row => ({ id: row.id, targets: row.nodes.map(node => node.target) }))).toEqual([]);
  if (process.env.DECISION_CAPTURE_DIR) {
    await page.locator(selector).evaluate(el => el.scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: `${process.env.DECISION_CAPTURE_DIR}/${name}-${test.info().project.name}-viewport.png` });
    // The app scrolls inside its route pane. Capture each visible part instead of a clipped tall element.
    for (const [index, section] of (await page.locator(`${selector} .decision-dimension, ${selector} section`).all()).entries()) {
      await section.evaluate(el => el.scrollIntoView({ block: 'start' }));
      await page.screenshot({ path: `${process.env.DECISION_CAPTURE_DIR}/${name}-${test.info().project.name}-part${index + 1}.png` });
    }
  }
}
for (const theme of ['light', 'dark']) {
  test(`0.10 comparison same readiness for missing short long reasons and different currency ${theme}`, async ({ page }) => {
    const { calls } = await mock(page, theme);
    await page.goto('/#/watchlist');
    const surface = page.locator('.decision-comparison');
    await surface.getByRole('button', { name: '열기', exact: true }).click();
    for (const name of ['NONE', 'SHORT', 'LONG']) await surface.getByLabel(name, { exact: true }).check();
    const read = surface.getByRole('button', { name: '선택 후보 현재 자료로 읽기' });
    await read.focus(); await page.keyboard.press('Enter');
    await expect(surface.locator('[data-readiness-state="ready_for_review"]')).toHaveCount(3);
    await expect(surface).toContainText('한 줄 이유');
    await expect(surface).toContainText('아직 이유를 남기지 않았습니다');
    await expect(surface).toContainText('시세 통화가 달라');
    expect(calls.filter(row => row.method !== 'GET').map(row => row.path)).toEqual(['/api/opportunity-comparison']);
    expect(calls.find(row => row.path === '/api/opportunity-comparison')?.body.candidates).toEqual(['US:NONE', 'US:SHORT', 'US:LONG'].map(instrumentId => ({ instrumentId })));
    await checkSurface(page, '.decision-comparison', `comparison-${theme}`);
    const open = surface.getByRole('button', { name: '기업 정보·가격·내 이유 열기' }).first();
    await open.focus(); await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/#\/watchlist\/NONE$/);
    await page.goto('/#/watchlist');
    await expect(surface.getByLabel('NONE', { exact: true })).toBeChecked();
    await expect(surface.locator('[data-readiness-state="ready_for_review"]')).toHaveCount(3);
    await expect(surface.getByRole('button', { name: '기업 정보·가격·내 이유 열기' }).first()).toBeFocused();
  });
  test(`0.10 explicit candidate final weight preview and no actual portfolio writes ${theme}`, async ({ page }) => {
    const { calls, control } = await mock(page, theme);
    await page.goto('/#/portfolio');
    const surface = page.locator('[data-decision-preview]');
    await expect(surface).toBeVisible();
    await surface.getByLabel('후보 종목 기호').fill('C');
    await surface.getByLabel('후보의 최종 비중 (%)').fill('20');
    expect(calls.some(row => row.path.includes('decision-preview/'))).toBe(false);
    await expect(surface.getByRole('button', { name: '입력 비중으로 미리보기' })).toBeDisabled();
    await surface.getByRole('button', { name: '미리보기 기준 읽기' }).click();
    await surface.getByRole('button', { name: '입력 비중으로 미리보기' }).click();
    const security = surface.getByRole('table').first();
    await expect(security.getByRole('row').filter({ hasText: 'US:A' })).toContainText('48%');
    await expect(security.getByRole('row').filter({ hasText: 'US:C' })).toContainText('20%');
    const topThree = surface.getByRole('table').nth(3).getByRole('row').filter({ hasText: '상위 3개 보유 합계' });
    await expect(topThree.getByRole('cell').nth(0)).toHaveText('90%');
    await expect(topThree.getByRole('cell').nth(1)).toHaveText('92%');
    await expect(topThree.getByRole('cell').nth(2)).toHaveText('2%p');
    await expect(surface).toContainText('현재 30%, 가정 후 44%');
    await expect(surface).not.toContainText('비중 입력이 달라졌습니다');
    await surface.getByText('확인한 공시 노출의 원문과 판본', { exact: true }).click();
    await expect(surface).toContainText('profile-fixture');
    await expect(surface).toContainText('Higher interest rates increase borrowing costs.');
    await expect(surface).toContainText('2026-01-01');
    await expect(surface).toContainText('정성 설명이며');
    await checkSurface(page, '[data-decision-preview]', `preview-${theme}`);
    await page.goto('/#/watchlist'); await page.goto('/#/portfolio');
    await expect(surface.getByLabel('후보의 최종 비중 (%)')).toHaveValue('20');
    await expect(security.getByRole('row').filter({ hasText: 'US:C' })).toContainText('20%');
    control.expired = true;
    await surface.getByLabel('후보의 최종 비중 (%)').fill('30');
    await surface.getByRole('button', { name: '입력 비중으로 미리보기' }).click();
    await expect(surface.getByRole('alert')).toContainText('입력은 남아');
    await expect(surface.getByLabel('후보의 최종 비중 (%)')).toHaveValue('30');
    expect(calls.filter(row => row.method !== 'GET').map(row => row.path)).toEqual(['/api/portfolio/decision-preview/basis', '/api/portfolio/decision-preview', '/api/portfolio/decision-preview']);
  });
}
test('0.10 unsupported ETF foreign market stale snapshot preserve context and refresh detects global changes', async ({ page }) => {
  const { control, calls } = await mock(page, 'light');
  await page.goto('/#/watchlist');
  const surface = page.locator('.decision-comparison');
  await surface.getByRole('button', { name: '열기', exact: true }).click();
  for (const name of ['ETF', 'OLD', '7203.T']) await surface.getByLabel(name, { exact: true }).check();
  await surface.getByRole('button', { name: '선택 후보 현재 자료로 읽기' }).click();
  await expect(surface.locator('[data-readiness-state="unknown"]')).toHaveCount(2);
  await expect(surface.locator('[data-readiness-state="stale"]')).toHaveCount(1);
  await expect(surface).toContainText('재무 품질:');
  expect(calls.find(row => row.path === '/api/opportunity-comparison')?.body.candidates[2].instrumentId).toBe('JP:7203.T');
  control.changed = true;
  await page.goto('/#/home'); await page.goto('/#/watchlist');
  await expect(surface.getByRole('status')).toContainText('앞서 읽은 결과');
  control.failComparison = true;
  await surface.getByRole('button', { name: '선택 후보 현재 자료로 읽기' }).click();
  await expect(surface.getByRole('alert')).toContainText('선택은 그대로');
  await expect(surface.getByLabel('ETF', { exact: true })).toBeChecked();
});

test('0.10 expired optional Portfolio basis can be separated without losing selected candidates', async ({ page }) => {
  const { control, calls } = await mock(page, 'light');
  await page.goto('/#/portfolio');
  const preview = page.locator('[data-decision-preview]');
  await preview.getByLabel('후보 종목 기호').fill('C');
  await preview.getByRole('button', { name: '미리보기 기준 읽기' }).click();
  await expect(preview).toContainText('30분');
  await page.goto('/#/watchlist');
  const compare = page.locator('.decision-comparison');
  await compare.getByRole('button', { name: '열기', exact: true }).click();
  await compare.getByLabel('NONE', { exact: true }).check();
  control.expired = true;
  await compare.getByRole('button', { name: '선택 후보 현재 자료로 읽기' }).click();
  await expect(compare.getByRole('alert')).toContainText('겹침 비중 참조 없이');
  await expect(compare.getByLabel('NONE', { exact: true })).toBeChecked();
  await compare.getByRole('button', { name: '선택 후보 현재 자료로 읽기' }).click();
  await expect(compare.locator('[data-readiness-state="ready_for_review"]')).toHaveCount(1);
  const requests = calls.filter(row => row.path === '/api/opportunity-comparison');
  expect(requests[0].body.portfolioBasisId).toBe('basis-fixture');
  expect(requests[1].body.portfolioBasisId).toBeUndefined();
});
