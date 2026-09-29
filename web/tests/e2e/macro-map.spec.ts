import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const labels = ['실질 GDP', '산업생산', '실업률', '소비자물가지수 (CPI)', '근원 PCE 물가지수', '실효 연방기금금리', 'Chicago Fed 금융여건', 'St. Louis Fed 금융스트레스'];
const ids = ['GDPC1', 'INDPRO', 'UNRATE', 'CPIAUCSL', 'PCEPILFE', 'DFF', 'NFCI', 'STLFSI4'];
const krIds = ['KR_GDP', 'KR_IP', 'KR_UNRATE', 'KR_CPI', 'KR_RATE', 'KR_USDKRW', 'KR_SPREAD', 'KR_CREDIT'];
const axes = ['growth', 'growth', 'growth', 'inflation', 'inflation', 'financial_conditions', 'financial_conditions', 'stress_vulnerability'];
const GUIDE_BODY = '소비자가 사는 상품과 서비스 묶음의 가격을 지수로 나타낸 값입니다.';

// 거시 지도 API 모의 응답. 개요는 요약(view=summary: 머리 숫자·짧은 추이), 상세는 전체 이력이다.
function fixture(url: URL, empty = false) {
  const market = url.searchParams.get('market') === 'KR' ? 'KR' : 'US';
  const mode = url.searchParams.get('mode') || 'latest_revised';
  const selected = url.searchParams.get('series');
  const marketIds = market === 'US' ? ids : krIds;
  const points = [100, 101, 102].map((value, i) => ({
    period: `2024-0${i + 1}-01`, value, rawValue: String(value), displayValue: value / 40, displayUnit: '%',
    metadata: { unit: 'Index 2017=100', frequency: 'M', adjustment: 'SA' }, metadataId: 'm1',
    availabilityBasis: market === 'US' ? 'provider_vintage' : 'local_observed', availableAt: '2024-04-01T23:59:59Z',
    vintageDate: market === 'US' ? '2024-04-01' : null, releasedAt: null, fetchedAt: '2026-09-27T00:00:00Z',
    firstSeenAt: market === 'US' ? null : '2026-09-27T00:00:00Z', revised: false,
  }));
  const headline = (i: number) => ({
    value: 2.55, previous: 2.52, delta: i % 3 === 1 ? -0.03 : i % 3 === 2 ? 0 : 0.03, tone: i % 3 === 1 ? 'down' : i % 3 === 2 ? 'flat' : 'up',
    unit: '%', deltaUnit: '%p', digits: 2, measure: '전년 대비', period: '2024-03-01', shape: i === 0 ? 'bars' : 'line',
    spark: points.map((p) => [p.period, p.displayValue]),
  });
  const items = labels.map((label, i) => ({
    series: {
      id: marketIds[i], label, axis: axes[i], stage: i === 2 ? 'lagging' : 'coincident', frequency: 'M', unit: 'Index 2017=100',
      sourceUrl: 'https://fred.stlouisfed.org/', transform: 'yoy', methodVersion: 'macro-2', adjustment: 'SA',
      provider: market === 'US' ? 'fred' : 'ecos', code: marketIds[i],
    },
    latest: empty ? null : points[2],
    history: selected && !empty ? points : [],
    headline: empty ? null : headline(i),
    direction: empty ? 'unavailable' : 'up',
    quality: empty ? ['missing'] : i === 7 ? ['stale', 'provider_failed'] : [],
    providerStates: empty ? [] : [{ status: 'ok', last_success: '2026-09-27T00:00:00Z', error_code: '' }],
    coverage: { firstAvailableAt: '2000-02-01T23:59:59Z' },
    latestRevisedComparison: selected && mode === 'as_of' ? points.map((p) => ({ ...p, value: p.value + 2, displayValue: p.displayValue + 0.2 })) : [],
    revisions: selected ? points : [],
    revisionPeriod: selected ? '2024-03-01' : null,
    nextRelease: i === 3 ? { date: '2026-10-14', sourceUrl: 'https://fred.stlouisfed.org/', precision: 'date', basis: 'provider_schedule' } : null,
    ...(selected ? { guide: [
      { heading: '무엇을 재나요', body: GUIDE_BODY },
      { heading: '여기 숫자는', body: '1년 전 같은 달보다 물가가 몇 % 올랐는지입니다.' },
      { heading: '어떻게 읽나요', body: '여러 달의 흐름을 봅니다.' },
      { heading: '알아 둘 점', body: '계절조정 지수로 계산합니다.' },
    ] } : {}),
  }));
  return {
    view: selected ? 'full' : 'summary',
    overview: selected ? null : {
      recent: [{ seriesId: marketIds[3], period: '2024-03-01', frequency: 'M' }],
      upcoming: [{ date: '2026-10-14', series: [{ seriesId: marketIds[3], basis: 'provider_schedule' }] }],
      collection: { total: 8, collected: empty ? 0 : 8, revised: 0, lastCollectedAt: '2026-09-27T00:00:00Z' },
    },
    market, mode, date: url.searchParams.get('date') || '2026-09-26', timezone: market === 'US' ? 'America/Chicago' : 'Asia/Seoul',
    cutoff: null,
    axes: { growth: '경기', inflation: '물가', financial_conditions: '금융여건', stress_vulnerability: '위험' },
    items: selected ? items.filter((i) => i.series.id === selected) : items,
    notes: market === 'KR'
      ? ['한국은 현재 수정치 추이와 수집 이후 확인한 이력을 제공합니다. 과거 당시 값 재현은 지원하지 않습니다.']
      : ['NFCI와 금융스트레스 지수는 공통 입력이 있습니다.'],
  };
}

async function prepare(page: Page, theme: string, options = { empty: false, fail: false }) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/macro') return route.fulfill({ status: options.fail ? 503 : 200, json: fixture(url, options.empty) });
    if (url.pathname === '/api/macro/settings') return route.fulfill({ json: { enabled: true, startYear: 2000 } });
    if (url.pathname === '/api/macro/refresh') return route.fulfill({ json: { job: null } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.addInitScript((value) => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
  await page.goto('/#/market-memory/macro');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('region', { name: '거시 지도', exact: true })).toBeVisible();
}

for (const theme of ['light', 'dark']) {
  test(`macro map reading, navigation and accessibility: ${theme}`, async ({ page }, testInfo) => {
    await prepare(page, theme);
    await expect(page.locator('.macro-row')).toHaveCount(8);
    // 방향 색은 좋고 나쁨이 아니라 늘었다·줄었다만 말한다.
    await expect(page.locator('.macro-change b[data-tone="up"]').first()).toBeVisible();
    await expect(page.locator('.macro-change b[data-tone="down"]').first()).toBeVisible();
    await expect(page.locator('.macro-refresh')).toContainText('자동 갱신 켜짐');
    await page.getByRole('group', { name: '자료 기준' }).getByRole('button', { name: '과거 시점' }).click();
    await page.getByLabel('기준일', { exact: true }).fill('2024-04-02');
    await expect(page.locator('.macro-asof')).toContainText('2024년 4월 2일');
    await expect(page.locator('.macro-asof')).toContainText('과거 시점 재현');
    // 링크 이름은 보이는 글자(이름·값·변화)와 "상세 보기"다. 값이 함께 읽혀야 한다.
    const cpiRow = page.getByRole('link', { name: /^소비자물가 \(CPI\).*2\.55.*상세 보기$/ });
    await expect(cpiRow).toHaveCount(1);
    await cpiRow.click();
    await expect(page.getByRole('heading', { name: '미국 소비자물가 (CPI)' })).toBeVisible();
    await expect(page.getByText('점선은 현재 수정치입니다. 선택 시점의 계산에는 사용하지 않습니다.')).toBeVisible();
    const chart = page.getByRole('img', { name: '미국 소비자물가 (CPI) 추이' });
    await chart.focus();
    await page.keyboard.press('ArrowRight');
    await expect(chart).toBeFocused();
    // 초심자 설명은 처음엔 접혀 있다.
    await expect(page.getByText(GUIDE_BODY)).toBeHidden();
    await page.getByText('처음 보는 분을 위한 설명').click();
    await expect(page.getByText(GUIDE_BODY)).toBeVisible();
    await page.getByRole('group', { name: '표시 기간' }).getByRole('button', { name: '전체' }).click();
    await expect(page).toHaveURL(/years=50/);
    await page.goBack();
    await expect(page).not.toHaveURL(/years=50/);
    await expect(page.getByRole('heading', { name: '미국 소비자물가 (CPI)' })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', { name: '미국 소비자물가 (CPI)' })).toBeVisible();
    await expect(page.locator('.macro-asof')).toContainText('2024년 4월 2일');
    const violations = (await new AxeBuilder({ page }).include('.macro-panel').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations;
    expect(violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
    await page.screenshot({ path: `test-results/macro-detail-${testInfo.project.name}-${theme}.png`, fullPage: true });
    await page.getByRole('link', { name: '← 거시 지도' }).click();
    await expect(page.locator('.macro-row')).toHaveCount(8);
    const overview = (await new AxeBuilder({ page }).include('.macro-panel').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations;
    expect(overview).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
    await page.screenshot({ path: `test-results/macro-map-${testInfo.project.name}-${theme}.png`, fullPage: true });
    await page.getByRole('group', { name: '거시 자료 시장' }).getByRole('button', { name: '한국' }).click();
    await expect(page.locator('.macro-asof')).toContainText('과거 시점 재현 미지원');
    await expect(page.getByRole('group', { name: '자료 기준' })).toHaveCount(0);
    await page.getByRole('group', { name: '시장·거시 하위 보기' }).getByRole('button', { name: '검증 이력' }).click();
    await expect(page.getByRole('heading', { name: '검증 결과와 해석 범위' })).toBeVisible();
    await page.getByRole('group', { name: '시장·거시 하위 보기' }).getByRole('button', { name: '거시 지도' }).click();
    await expect(page.getByRole('group', { name: '거시 자료 시장' }).getByRole('button', { name: '한국' })).toHaveAttribute('aria-pressed', 'true');
  });
}

test('missing data and failed reads have useful recovery', async ({ page }) => {
  await prepare(page, 'light', { empty: true, fail: false });
  await expect(page.locator('.macro-row')).toHaveCount(8);
  await expect(page.getByText('연결된 공식 자료 없음', { exact: true })).toHaveCount(8);
  await page.route('**/api/macro?*', (route) => route.fulfill({ status: 503, json: {} }));
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('거시 자료를 읽지 못했습니다');
  await expect(page.getByRole('button', { name: '다시 읽기' })).toBeVisible();
});

test('system theme, loading skeleton and a fast collection completion keep the view current', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await prepare(page, 'system');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  let reads = 0;
  let submitted = false;
  await page.route('**/api/macro?*', async (route) => { reads++; await route.fulfill({ json: fixture(new URL(route.request().url())) }); });
  await page.route('**/api/macro/refresh', (route) => {
    if (route.request().method() === 'POST') { submitted = true; return route.fulfill({ json: { id: 'fast', status: 'queued' } }); }
    return route.fulfill({ json: { job: submitted ? { id: 'fast', status: 'done' } : null } });
  });
  await page.getByRole('button', { name: '지금 갱신', exact: true }).click();
  await expect(page.locator('.macro-refresh')).toContainText('수집 완료');
  await expect.poll(() => reads).toBeGreaterThan(0);
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/macro?*', async (route) => { await held; await route.fulfill({ json: fixture(new URL(route.request().url())) }); });
  await page.getByRole('group', { name: '거시 자료 시장' }).getByRole('button', { name: '한국' }).click();
  // 인라인 로딩은 최종 모양을 닮은 뼈대로 보인다.
  await expect(page.locator('.macro-skeleton')).toHaveCount(4);
  release();
  await expect(page.locator('.macro-row')).toHaveCount(8);
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
    await page.route('**/api/dashboard/cockpit', (route) => route.fulfill({ json: { focusSymbols: [] } }));
    await page.route('**/api/dashboard/settings', (route) => route.fulfill({ json: {} }));
    await page.route('**/api/market-calendar?*', (route) => route.fulfill({ json: { events, count: events.length, dataGaps: [] } }));
    await page.goto('/#/dashboard');
    const calendar = page.locator('.cockpit-calendar');
    await calendar.scrollIntoViewIfNeeded();
    await expect(calendar.getByText('값 확인 · 발표일 미확인')).toBeVisible();
    await expect(calendar.getByText('발표됨', { exact: true })).toBeVisible();
    await expect(calendar.getByText('추정 일정', { exact: true })).toBeVisible();
    await expect(calendar.getByText('확정', { exact: true })).toBeVisible();
    const violations = (await new AxeBuilder({ page }).include('.cockpit-calendar').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations;
    expect(violations).toEqual([]);
    await calendar.screenshot({ path: `test-results/calendar-${info.project.name}-${theme}.png` });
    await calendar.getByRole('link', { name: '거시 지도', exact: true }).click();
    await expect(page.getByRole('heading', { name: '한국 소비자물가 (CPI)' })).toBeVisible();
    await page.goBack();
    await expect(page.locator('.cockpit-calendar')).toBeVisible();
  });
}

test('missing API keys read as skipped sources, not as a failed collection', async ({ page }) => {
  await prepare(page, 'light');
  // FRED 키만 있는 사용자: 미국은 수집됐고 한국 9계열은 키가 없어 건너뛰었다.
  await page.route('**/api/macro/refresh', (route) => route.fulfill({ json: {
    job: { id: 'one-key', status: 'done' }, sources: { ok: 8, notConnected: 9, failed: 0 },
  } }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.macro-refresh')).toContainText('수집 완료 · API 키가 연결되지 않은 원천 9개는 건너뛰었습니다');

  // 연결된 원천이 실제로 실패한 경우는 건너뜀과 다른 문구로 보인다.
  await page.unroute('**/api/macro/refresh');
  await page.route('**/api/macro/refresh', (route) => route.fulfill({ json: {
    job: { id: 'outage', status: 'failed' }, sources: { ok: 7, notConnected: 9, failed: 1 },
  } }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.macro-refresh')).toContainText('일부 원천을 확인하지 못했습니다.');

  // 키가 하나도 없으면 등록을 안내한다.
  await page.unroute('**/api/macro/refresh');
  await page.route('**/api/macro/refresh', (route) => route.fulfill({ json: {
    job: { id: 'no-keys', status: 'failed' }, sources: { ok: 0, notConnected: 17, failed: 0 },
  } }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.macro-refresh')).toContainText('연결된 API 키가 없어 수집하지 않았습니다.');
});
