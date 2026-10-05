import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

test('0.9.2 chart comparison link opens the same monthly-record reader with exact market and date', async ({page})=>{
  const {stateUrls,writes}=await mockApi(page);
  await page.goto('/#/macro/state?market=KR&compareDate=2025-01-02');
  await expect(page.getByRole('heading',{name:'한국 현재 상태'})).toBeVisible();
  await expect(page.locator('input[type="date"]')).toHaveValue('2025-01-02');
  await expect.poll(()=>stateUrls.includes('?market=KR&date=2025-01-02')).toBe(true);
  await expect(page.locator('.macro-notice').filter({hasText:'이전에 저장된 기록이 없습니다.'})).toBeVisible();
  expect(writes).toEqual([]);
  await page.goto('/#/macro/state?market=KR&compareDate=2099-01-01');
  await expect(page.getByText('기준일 또는 시장이 올바르지 않습니다. 미래 날짜는 비교할 수 없습니다.')).toBeVisible();
  expect(stateUrls.some(s=>s.includes('2099'))).toBe(false);
});

const snap = (axis: string, level: string, direction: string, extra: Record<string, unknown> = {}) => ({
  snapshotId: `macro-${axis}`, inputFingerprint: 'test', asOf: '2026-09-29T10:00:00Z', axis, level, direction,
  promotion: 'shadow', confidence: 'medium', freshness: 'current', conflicts: [], unknownReason: [], sourceRefs: [], ...extra,
});

const STATE = {
  market: 'US', date: '2026-09-29', notice: '이미 나타난 신호의 확인이지 예측이 아닙니다.', inflationLimitation: 'B1 대비 4.76%p',
  nextCheckpoints: { GDPC1: { date: '2026-09-30', basis: 'provider_schedule', sourceUrl: 'https://fred.stlouisfed.org/release?rid=53' }, PCEPILFE: { date: '2026-09-30', basis: 'provider_schedule', sourceUrl: '' } },
  cards: [
    { axis: 'growth', snapshot: snap('growth', 'moderate', 'mixed', {
      conflicts: [{ kind: 'growthDirectionDisagreement', signals: { GDPC1: 'flat', UNRATE: 'rising' } }],
      cycleSignal: 'unknown', cycleSignalPromotion: 'shadow',
      cycleSignalBasis: { cycleCorroboration: 'not_available', conditions: { W: false, K: false, R: null, Q: null }, unknownReason: [{ seriesId: 'UNRATE', period: '2025-10-01', reason: 'officiallyNotPublished' }] },
      sourceRefs: [{ seriesId: 'GDPC1', period: '2026-04-01', value: '24269.6', availableAt: '2026-08-27T00:00:00Z' }, { seriesId: 'GDPC1', period: '2026-01-01', value: '24180.4', availableAt: '2026-06-26T00:00:00Z' }],
    }) },
    { axis: 'inflation', snapshot: snap('inflation', 'above_reference', 'flat', { promotion: 'primary', confidence: 'high' }) },
    { axis: 'financial_conditions', snapshot: snap('financial_conditions', 'loose', 'rising', {
      conflicts: [{ kind: 'financialDirectionDisagreement', signals: { DFF: 'rising', NFCI: 'flat' } }],
      sourceRefs: [{ seriesId: 'DFF', period: '2026-06-25', value: '3.63', availableAt: '2026-06-27T00:00:00Z' }, { seriesId: 'DFF', period: '2026-09-25', value: '3.88', availableAt: '2026-09-27T00:00:00Z' }],
    }) },
    { axis: 'stress_vulnerability', snapshot: snap('stress_vulnerability', 'normal', 'flat') },
  ],
};

const MAP = {
  market: 'US', mode: 'latest_revised', items: [
    { series: { id: 'PCEPILFE', axis: 'inflation', label: '근원 PCE' }, headline: { value: 3.344, digits: 2, unit: '%', measure: '전년 대비', spark: [['2026-04-01', 3.33], ['2026-05-01', 3.46], ['2026-06-01', 3.34], ['2026-07-01', 3.344]] } },
    { series: { id: 'CPIAUCSL', axis: 'inflation', label: 'CPI' }, headline: { value: 3.35, digits: 2, unit: '%', measure: '전년 대비', spark: [] } },
  ],
};

async function mockApi(page: Page, options: { empty?: boolean } = {}) {
  const writes: string[] = [];
  const stateUrls: string[] = [];
  await page.route('**/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== 'GET') writes.push(url.pathname);
    if (url.pathname === '/api/macro/state') {
      stateUrls.push(url.search);
      if (url.searchParams.get('date') || options.empty) return route.fulfill({ json: { ...STATE, cards: STATE.cards.map(card => ({ axis: card.axis, snapshot: null })) } });
      return route.fulfill({ json: STATE });
    }
    if (url.pathname === '/api/macro') return route.fulfill({ json: MAP });
    if (url.pathname === '/api/macro/state/history') return route.fulfill({ json: { decisions: [{ seq: 1, market: 'US', axis: 'inflation', promotion: 'primary', created_at: '2026-09-29T10:13:00Z' }], snapshots: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  return { writes, stateUrls };
}

for (const theme of ['light', 'dark']) {
  test(`0.8 current state reads as one sentence, scales and directions ${theme}`, async ({ page }, info) => {
    await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
    const { writes, stateUrls } = await mockApi(page);
    await page.goto('/#/macro/state');
    const panel = page.getByRole('region', { name: '거시 현재 상태' });
    await expect(panel.getByRole('heading', { name: '미국 현재 상태' })).toBeVisible();

    // 한 줄 요약은 판정 값을 정해진 틀에 끼운 문장이다.
    await expect(panel.locator('.macro-now__answer')).toContainText('물가는 2%보다 높고, 보합입니다.');
    await expect(panel.locator('.macro-now__answer')).toContainText('유동성은 풍부하지만 축소되는 중입니다.');

    // 칸 수는 규칙 그대로(4·4·3·3)이고 이름만 화면 말로 바뀐다.
    await expect(panel.getByRole('img', { name: /^경기 추세 성장\. 수축, 부진, 추세 성장, 호조 중/ })).toBeVisible();
    await expect(panel.getByRole('img', { name: /^물가 높음\. 낮음, 2% 부근, 높음, 매우 높음 중/ })).toBeVisible();
    await expect(panel.getByRole('img', { name: /^유동성 풍부\. 부족, 중립, 풍부 중/ })).toBeVisible();
    await expect(panel.getByRole('img', { name: /^신용 위험 안정\. 안정, 주의, 경계 중/ })).toBeVisible();
    await expect(panel.locator('.macro-scale__cells span[aria-current="true"]')).toHaveText(['추세 성장', '높음', '풍부', '안정']);

    // 검증 칩: 물가만 검증 통과.
    const rows = panel.locator('.macro-now__row');
    await expect(rows.nth(1).locator('.macro-now__name .chip')).toHaveText('검증 통과');
    await expect(rows.nth(0).locator('.macro-now__name .chip')).toHaveText('검증 중');

    // 방향과 근거: 실효 연방기금금리는 기준금리가 아니라 시장 금리로 부른다.
    await expect(rows.nth(2).locator('.macro-now__dir')).toHaveText('축소');
    // 축소는 부족 쪽(왼쪽)으로 움직이는 것이라 ↘, 물가 보합은 수평선이다.
    await expect(rows.nth(2).locator('.macro-now__dir svg')).toHaveAttribute('data-moving', 'left');
    await expect(rows.nth(1).locator('.macro-now__dir svg')).toHaveAttribute('data-moving', 'flat');
    await expect(rows.nth(2)).toContainText('시장 금리(실효 연방기금금리) 3.63%에서 3.88%로(3개월)');
    await expect(rows.nth(2)).toContainText('시장 금리와 금융여건지수의 움직임이 다릅니다: 시장 금리 상승 · 금융여건지수 보합');
    await expect(rows.nth(2)).not.toContainText('기준금리 3');
    await expect(rows.nth(1)).toContainText('최신 참고값');
    await expect(rows.nth(1)).toContainText('저장 판정의 입력과 다를 수 있습니다');
    await expect(rows.nth(2)).toContainText('저장 판정의 입력');
    await expect(rows.nth(1)).toContainText('근원 PCE 3.34%(전년 대비) · 3개월 전 3.33% · CPI 3.35%(전년 대비, 참고)');
    // 경기 전환 신호는 네 축과 다른 별도 칸이고, 조건마다 없음·켜짐·판단 보류를 따로 보인다.
    await expect(rows).toHaveCount(4);
    const cycle = panel.getByRole('region', { name: '경기 전환 신호' });
    await expect(cycle.locator('.macro-cycle__steps li')).toHaveText(['수축 경고없음', '수축 확인없음', '회복 신호판단 보류', '회복 확인판단 보류']);
    await expect(cycle).toContainText('지금 수축 경고·수축 확인은 없습니다.');
    await expect(cycle).toContainText('회복 신호·회복 확인은 2025-10 실업률이 공식 발표되지 않아 최근 1년 안의 수축 여부를 가릴 수 없어 판단 보류입니다.');
    await expect(cycle).not.toHaveAttribute('data-active', 'true');
    await expect(panel.locator('.macro-now__answer')).not.toContainText('경기 국면 신호는');

    // 계산 근거는 누를 때만 펼친다(원자료 전체 나열 없음).
    const toggle = rows.nth(0).getByRole('button', { name: '계산 근거' });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(rows.nth(0).locator('.macro-now__evidence tbody tr')).toHaveCount(1);
    await expect(rows.nth(0)).toContainText('외 1개 관측');

    // 정책 변화 기록 양식은 0.8 화면에서 뺐다.
    await expect(page.getByText('공식 발표를 기록하기')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '기록 미리보기' })).toHaveCount(0);

    // 기준일 비교: 저장 기록이 없으면 한 번만 알린다.
    await panel.getByRole('button', { name: '날짜와 비교' }).click();
    await panel.getByLabel('기준일').fill('2026-08-15');
    await expect(panel.getByRole('status').filter({ hasText: '2026년 8월 15일 이전에 저장된 기록이 없습니다' })).toBeVisible();
    await expect(panel.locator('.macro-now__compare')).toHaveCount(0);
    expect(stateUrls.some(search => search.includes('date=2026-08-15'))).toBe(true);
    await panel.getByRole('button', { name: '비교 끄기' }).click();

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const a11y = await new AxeBuilder({ page }).include('.macro-now').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(a11y.violations).toEqual([]);
    await page.screenshot({ path: info.outputPath(`macro-state-${theme}.png`), fullPage: true });

    await page.getByRole('button', { name: '검증 이력' }).click();
    const history = page.getByRole('region', { name: '검증 이력' });
    await expect(history.getByRole('row', { name: /미국 물가 검증 통과/ })).toBeVisible();
    await expect(history.getByRole('row', { name: /경기 국면 검증 중/ })).toBeVisible();
    await expect(history).toContainText('미국 물가 · 검증 통과로 수용');
    const a11yHistory = await new AxeBuilder({ page }).include('.macro-now').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(a11yHistory.violations).toEqual([]);
    expect(writes).toEqual([]);
  });
}

test('an active cycle signal is highlighted in the growth row and the summary', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('folio.react.agentClosed', '1'));
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/macro/state') {
      const cards = STATE.cards.map(card => card.axis === 'growth'
        ? { axis: 'growth', snapshot: { ...card.snapshot, cycleSignal: 'contraction_warning', cycleSignalBasis: { cycleCorroboration: 'agrees', conditions: { W: true, K: false, R: false, Q: false }, unknownReason: [] } } }
        : card);
      return route.fulfill({ json: { ...STATE, cards } });
    }
    if (url.pathname === '/api/macro') return route.fulfill({ json: MAP });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('/#/macro/state');
  const cycle = page.getByRole('region', { name: '경기 전환 신호' });
  await expect(cycle).toHaveAttribute('data-active', 'true');
  await expect(cycle.locator('li[data-state="on"]')).toHaveText('수축 경고켜짐');
  await expect(cycle).toContainText('수축 경고 신호가 켜졌습니다(보조 지표(CFNAI)와 일치).');
  await expect(cycle).toContainText('지금 수축 확인·회복 신호·회복 확인은 없습니다.');
  await expect(cycle.getByText('검증 중', { exact: true })).toBeVisible();
  await expect(page.locator('.macro-now__answer')).toContainText('경기 국면 신호는 수축 경고입니다.');
});

test('empty workspace points to the macro map without inventing a state', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('folio.react.agentClosed', '1'));
  const { writes } = await mockApi(page, { empty: true });
  await page.goto('/#/macro/state');
  await expect(page.getByText('아직 저장된 기록이 없습니다.')).toBeVisible();
  await expect(page.getByRole('link', { name: '거시 지도' })).toBeVisible();
  await expect(page.locator('.macro-now__rows')).toHaveCount(0);
  expect(writes).toEqual([]);
});

test('macro read failures stay visible and never write', async ({ page }) => {
  let writes = 0;
  await page.route('**/api/**', route => { if (route.request().method() === 'POST') writes++; return route.fulfill({ status: 503, json: {} }); });
  await page.goto('/#/macro/state');
  await expect(page.getByRole('alert').filter({ hasText: '거시 기록을 읽지 못했습니다' })).toBeVisible();
  expect(writes).toBe(0);
});
