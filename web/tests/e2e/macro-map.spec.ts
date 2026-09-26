import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const labels = ['실질 GDP', '산업생산', '실업률', '소비자물가지수 (CPI)', '근원 PCE 물가지수', '실효 연방기금금리', 'Chicago Fed 금융여건', 'St. Louis Fed 금융스트레스'];
const ids = ['GDPC1', 'INDPRO', 'UNRATE', 'CPIAUCSL', 'PCEPILFE', 'DFF', 'NFCI', 'STLFSI4'];
const axes = ['growth', 'growth', 'growth', 'inflation', 'inflation', 'financial_conditions', 'financial_conditions', 'stress_vulnerability'];
function fixture(url: URL, empty = false) {
  const market = url.searchParams.get('market') === 'KR' ? 'KR' : 'US';
  const mode = url.searchParams.get('mode') || 'latest_revised';
  const selected = url.searchParams.get('series');
  const marketIds = market === 'US' ? ids : ['KR_GDP', 'KR_IP', 'KR_UNRATE', 'KR_CPI', 'KR_RATE', 'KR_USDKRW', 'KR_SPREAD', 'KR_CREDIT'];
  const points = [100, 101, 102].map((value, i) => ({ period: `2024-0${i + 1}-01`, value, displayValue: value, displayUnit: '지수', metadata: { unit: '지수', frequency: 'M', adjustment: 'SA' }, metadataId: 'm1', availabilityBasis: market === 'US' ? 'provider_vintage' : 'local_observed', availableAt: '2024-04-01T23:59:59Z', vintageDate: market === 'US' ? '2024-04-01' : null, firstSeenAt: market === 'KR' ? '2026-09-27T00:00:00Z' : null, fetchedAt: '2026-09-27T00:00:00Z' }));
  const items = labels.map((label, i) => ({ series: { id: ids[i], label, axis: axes[i], stage: i === 2 ? 'lagging' : 'coincident', frequency: 'M', unit: '지수', sourceUrl: 'https://fred.stlouisfed.org/', transform: 'level', methodVersion: 'macro-1', adjustment: 'SA' }, latest: empty ? null : points[2], history: empty ? [] : points, direction: empty ? 'unavailable' : 'up', quality: empty ? ['missing'] : i === 7 ? ['stale', 'provider_failed'] : [], providerStates: empty ? [] : [{ status: 'ok' }], coverage: { firstAvailableAt: '2000-02-01T23:59:59Z' }, latestRevisedComparison: mode === 'as_of' ? points.map(p => ({ ...p, displayValue: p.displayValue + 2 })) : [], revisions: points }));
  items.forEach((item, i) => { item.series.id = marketIds[i]; });
  return { market, mode, date: url.searchParams.get('date') || '2026-09-26', timezone: market === 'US' ? 'America/Chicago' : 'Asia/Seoul', axes: { growth: '경기', inflation: '물가', financial_conditions: '금융여건', stress_vulnerability: '위험' }, items: selected ? items.filter(i => i.series.id === selected) : items, notes: market === 'KR' ? ['한국은 현재 수정치 추이와 수집 이후 확인한 이력을 제공합니다. 과거 당시 값 재현은 지원하지 않습니다.'] : ['NFCI와 금융스트레스 지수는 공통 입력이 있습니다.'] };
}
async function prepare(page: Page, theme: string, options = { empty: false, fail: false }) {
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/macro') return route.fulfill({ status: options.fail ? 503 : 200, json: fixture(url, options.empty) });
    if (url.pathname === '/api/macro/settings') return route.fulfill({ json: { enabled: false, startYear: 2000 } });
    if (url.pathname === '/api/macro/refresh') return route.fulfill({ json: { job: null } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
  await page.goto('/#/market-memory/macro');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('region', { name: '거시 지도', exact: true })).toBeVisible();
}

for (const theme of ['light', 'dark']) {
  test(`macro map reading, navigation and accessibility: ${theme}`, async ({ page }, testInfo) => {
    await prepare(page, theme);
    await expect(page.locator('.macro-card')).toHaveCount(8);
    await expect(page.getByLabel('서버 실행 중 하루 2회 자동 갱신')).not.toBeChecked();
    await page.getByLabel('자료 기준', { exact: true }).selectOption('as_of');
    await page.getByLabel('기준일', { exact: true }).fill('2024-04-02');
    await expect(page.getByText('2024-04-02 현지 날짜 마감 기준 (America/Chicago)')).toBeVisible();
    await page.getByRole('article', { name: '소비자물가지수 (CPI)', exact: true }).getByRole('button', { name: '출처·전체 이력·수정 비교' }).click();
    await expect(page.locator('.macro-card')).toHaveCount(1);
    await expect(page.getByText('점선은 현재 수정치입니다. 선택 시점의 계산에는 사용하지 않습니다.')).toBeVisible();
    const chart = page.getByRole('img', { name: '소비자물가지수 (CPI) 추이' });
    await chart.focus(); await page.keyboard.press('ArrowRight');
    await expect(chart).toBeFocused();
    await page.getByLabel('표시 기간').selectOption('50');
    await page.getByRole('link', { name: '시장 캘린더', exact: true }).click();
    await page.goBack();
    await expect(page.getByLabel('기준일', { exact: true })).toHaveValue('2024-04-02');
    await expect(page.locator('.macro-card')).toHaveCount(1);
    await page.reload();
    await expect(page.locator('.macro-card')).toHaveCount(1);
    await expect(page.getByLabel('표시 기간')).toHaveValue('50');
    await expect(page.getByLabel('기준일', { exact: true })).toHaveValue('2024-04-02');
    const violations = (await new AxeBuilder({ page }).include('.macro-map').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations;
    expect(violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
    const toggleBox = await page.getByLabel('서버 실행 중 하루 2회 자동 갱신').boundingBox();
    expect(toggleBox!.width).toBeLessThan(30);
    await page.screenshot({ path: `../plan/audits/macro-0.7-p0/map-${testInfo.project.name}-${theme}.png`, fullPage: true });
    await page.locator('.macro-card').scrollIntoViewIfNeeded();
    await page.locator('.macro-card').screenshot({ path: `../plan/audits/macro-0.7-p0/detail-${testInfo.project.name}-${theme}.png` });
    await page.getByRole('button', { name: '한국', exact: true }).click();
    await expect(page.getByText('한국은 현재 수정치 추이와 수집 이후 확인한 이력을 제공합니다. 과거 당시 값 재현은 지원하지 않습니다.')).toBeVisible();
    await expect(page.getByLabel('자료 기준', { exact: true })).toHaveCount(0);
    await page.getByRole('link', { name: '내러티브', exact: true }).click();
    await expect(page.locator('.react-market-memory-content')).toBeVisible();
    await page.getByRole('link', { name: '거시 지도', exact: true }).click();
    await expect(page.getByRole('button', { name: '한국', exact: true })).toHaveAttribute('aria-pressed', 'true');
  });
}
test('missing data and failed reads have useful recovery', async ({ page }) => {
  await prepare(page, 'light', { empty: true, fail: false });
  await expect(page.locator('.macro-card')).toHaveCount(8);
  await expect(page.getByText('연결된 공식 자료를 아직 수집하지 않았습니다.', { exact: false })).toHaveCount(8);
  await page.route('**/api/macro?*', route => route.fulfill({ status: 503, json: {} }));
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('거시 자료를 읽지 못했습니다');
  await expect(page.getByRole('button', { name: '다시 읽기' })).toBeVisible();
});

test('system theme, loading and a fast collection completion keep the view current', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await prepare(page, 'system');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  let reads = 0; let submitted = false;
  await page.route('**/api/macro?*', async route => { reads++; await route.fulfill({ json: fixture(new URL(route.request().url())) }); });
  await page.route('**/api/macro/refresh', route => {
    if (route.request().method() === 'POST') { submitted = true; return route.fulfill({ json: { id: 'fast', status: 'queued' } }); }
    return route.fulfill({ json: { job: submitted ? { id: 'fast', status: 'done' } : null } });
  });
  await page.getByRole('button', { name: '공식 자료 갱신', exact: true }).click();
  await expect(page.getByText('수집 완료', { exact: true })).toBeVisible();
  expect(reads).toBeGreaterThan(0);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/macro?*', async route => { await held; await route.fulfill({ json: fixture(new URL(route.request().url())) }); });
  await page.getByLabel('표시 기간').selectOption('50');
  await expect(page.getByText('거시 자료를 불러오는 중입니다.')).toBeVisible();
  release(); await expect(page.locator('.macro-card')).toHaveCount(8);
});

for (const theme of ['light', 'dark']) {
  test(`calendar date certainty and macro return flow: ${theme}`, async ({ page }, info) => {
    await page.clock.setFixedTime(new Date('2026-09-27T03:00:00Z'));
    await prepare(page, theme);
    const base = { kind: 'macro', market: 'KR', startsAt: '2026-09-27', allDay: true, timezone: 'Asia/Seoul', importance: 3, observedAt: '202608', unit: '2020=100' };
    const events = [
      { ...base, id: 'estimated-value', title: '한국 소비자물가지수 (CPI)', provider: 'bok', source: 'ECOS', status: 'estimated', actualValue: '120.1', sourceUrl: 'https://ecos.bok.or.kr/' },
      { ...base, id: 'official-value', title: '공식 발표값 fixture', provider: 'official_fixture', source: '공식 발표문 fixture', status: 'actual', actualValue: '120.1', sourceUrl: 'https://www.bok.or.kr/' },
      { ...base, id: 'no-value', title: '한국 PPI fixture', provider: 'bok', status: 'estimated', actualValue: '' },
      { ...base, id: 'meeting', kind: 'central_bank', title: '한국은행 통화정책방향 결정회의 fixture', provider: 'bank_of_korea', status: 'confirmed', sourceUrl: 'https://www.bok.or.kr/' },
    ];
    await page.route('**/api/dashboard/cockpit', route => route.fulfill({ json: { focusSymbols: [] } }));
    await page.route('**/api/dashboard/settings', route => route.fulfill({ json: {} }));
    await page.route('**/api/market-calendar?*', route => route.fulfill({ json: { events, count: events.length, dataGaps: [] } }));
    await page.getByRole('link', { name: '시장 캘린더', exact: true }).click();
    const calendar = page.locator('.cockpit-calendar');
    await calendar.scrollIntoViewIfNeeded();
    await expect(calendar.getByText('값 확인 · 발표일 미확인')).toBeVisible();
    await expect(calendar.getByText('발표됨', { exact: true })).toBeVisible();
    await expect(calendar.getByText('추정 일정', { exact: true })).toBeVisible();
    await expect(calendar.getByText('확정', { exact: true })).toBeVisible();
    const violations = (await new AxeBuilder({ page }).include('.cockpit-calendar').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations;
    expect(violations).toEqual([]);
    await calendar.screenshot({ path: `../plan/audits/macro-0.7-p0/calendar-${info.project.name}-${theme}.png` });
    await calendar.getByRole('link', { name: '거시 지도', exact: true }).click();
    await expect(page.getByRole('button', { name: '한국', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('.macro-card')).toHaveCount(1);
    await page.goBack();
    await expect(page.locator('.cockpit-calendar')).toBeVisible();
  });
}

test('missing API keys read as skipped sources, not as a failed collection', async ({ page }) => {
  await prepare(page, 'light');
  // FRED 키만 있는 사용자: 미국은 수집됐고 한국 9계열은 키가 없어 건너뛰었다.
  await page.route('**/api/macro/refresh', route => route.fulfill({ json: {
    job: { id: 'one-key', status: 'done' }, sources: { ok: 8, notConnected: 9, failed: 0 },
  } }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('수집 완료 · API 키가 연결되지 않은 원천 9개는 건너뛰었습니다', { exact: true })).toBeVisible();

  // 연결된 원천이 실제로 실패한 경우는 건너뜀과 다른 문구로 보인다.
  await page.unroute('**/api/macro/refresh');
  await page.route('**/api/macro/refresh', route => route.fulfill({ json: {
    job: { id: 'outage', status: 'failed' }, sources: { ok: 7, notConnected: 9, failed: 1 },
  } }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('일부 원천을 확인하지 못했습니다.', { exact: false })).toBeVisible();

  // 키가 하나도 없으면 등록을 안내한다.
  await page.unroute('**/api/macro/refresh');
  await page.route('**/api/macro/refresh', route => route.fulfill({ json: {
    job: { id: 'no-keys', status: 'failed' }, sources: { ok: 0, notConnected: 17, failed: 0 },
  } }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('연결된 API 키가 없어 수집하지 않았습니다.', { exact: false })).toBeVisible();
});
