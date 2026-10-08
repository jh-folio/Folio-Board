import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const serviceUrl = process.env.CASE_TEST_URL || 'http://127.0.0.1:18789';
async function setup(page: Page, theme: string, seeded = true) {
  const fixture = await page.request.post(`${serviceUrl}/fixture?ownership=${seeded}`);
  const { prefix, originalJournalId } = await fixture.json();
  await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname;
    if (path.startsWith('/api/investment-cases') || path.startsWith('/api/decision-journals')) {
      const response = await route.fetch({ url: `${serviceUrl}${prefix}${path}${url.search}` }); return route.fulfill({ response });
    }
    if (path === '/api/watchlist') return route.fulfill({ json: { watchlist: ['ABC'], items: ['ABC'] } });
    if (path === '/api/watchlist/overview') return route.fulfill({ json: { items: [{ ticker: 'ABC', market: 'US', name: '예시기업', item: 'ABC' }] } });
    if (path === '/api/watchlist/detail') return route.fulfill({ json: { item: 'ABC', company: { ticker: 'ABC', market: 'US', name: '예시기업' }, news: [] } });
    if (path === '/api/portfolio') return route.fulfill({ json: { revision: 1, positions: [], cash: [] } });
    if (path.startsWith('/api/investment-review')) return route.fulfill({ json: path.endsWith('/history') ? { items: [{ date: '2026-09-20', reviewRevision: 1, reviewState: 'draft' }] } : { date: path.endsWith('/2026-09-20') ? '2026-09-20' : '2026-10-01', reviewRevision: 1, sourceSchemaVersion: 2, reviewState: 'draft', summary: '저장된 전체 구성 검토', inputBasis: { originalDecisions: [{ instrumentId: 'US:ABC', journalId: originalJournalId }] }, positionRoster: [{ ticker: 'ABC', instrumentId: 'US:ABC', market: 'US', thesisVerdict: 'insufficient_evidence' }], positionReviews: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('/#/watchlist/ABC?tab=ownership&instrument=US%3AABC');
  await expect(page.getByRole('heading', { name: '보유 점검', exact: true })).toBeVisible();
  await expect(page.locator('[data-ownership-review]')).toContainText('당시 이유·생각을 바꿀 상황');
  return { prefix, originalJournalId };
}
async function capture(page: Page, name: string) {
  if (process.env.OWNERSHIP_CAPTURE_DIR) await page.screenshot({ path: `${process.env.OWNERSHIP_CAPTURE_DIR}/${name}-${test.info().project.name}.png` });
}
async function a11y(page: Page, selector: string) {
  expect((await new AxeBuilder({ page }).include(selector).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()).violations.map(row => row.id)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
}

for (const theme of ['light', 'dark']) {
  test(`0.12 real deferral completion continuity postmortem and portfolio return ${theme}`, async ({ page }) => {
    test.setTimeout(60000);
    const { prefix, originalJournalId } = await setup(page, theme);
    const area = page.locator('[data-ownership-review]');
    await expect(area).toContainText('반복 매출이 안정적으로 이어질 것');
    await capture(page, `overview-${theme}`); await a11y(page, '[data-ownership-review]');
    await area.getByText('가정·관측 수치 대조', { exact: true }).click();
    await expect(area.getByLabel('시나리오 비교 표')).toBeVisible();
    await area.getByLabel('시나리오 비교 표').focus();
    await expect(area.getByLabel('시나리오 비교 표')).toBeFocused();
    await capture(page, `numbers-${theme}`); await a11y(page, '[data-ownership-review]');
    await area.getByText('가정·관측 수치 대조', { exact: true }).click();
    await area.getByRole('button', { name: '내 검토 남기기', exact: true }).click();
    await area.getByLabel('연결할 당시 조건').selectOption({ label: '당시 · 현금 전환이 악화될 때' });
    await area.getByRole('textbox', { name: '관찰한 사실', exact: true }).fill('이번 발표의 현금 흐름은 더 확인해야 한다.');
    await area.getByLabel('내가 본 근거 수준').selectOption('missing');
    await area.getByLabel('아직 모르는 것·반대 근거').fill('일시적인지 구조적인지 구분할 자료가 없다.');
    await area.getByRole('combobox', { name: '내 판단', exact: true }).selectOption('defer');
    await area.getByLabel('다음 확인 날짜', { exact: true }).fill('2020-01-01');
    await area.getByLabel('이번 범위의 검토를 마쳤음').check();
    await area.getByRole('checkbox', { name: '기업', exact: true }).check();
    await area.getByRole('checkbox', { name: '이유와 조건', exact: true }).check();
    expect((await area.getByLabel('이번 범위의 검토를 마쳤음').boundingBox())!.width).toBeLessThan(30);
    await capture(page, `form-${theme}`); await a11y(page, '.ownership-form');
    await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
    await expect(area.getByRole('heading', { name: '확인할 점검 기록' })).toBeFocused();
    await expect(area.locator('.ownership-preview')).toContainText('판단 보류');
    await expect(area.locator('.ownership-preview')).not.toContainText('Invalid Date');
    await a11y(page, '.ownership-preview');
    await area.getByRole('button', { name: '확인한 점검 저장' }).click();
    await expect(area.getByRole('heading', { name: '당시 보유 점검·복기' })).toBeVisible();
    await expect(area.locator('.ownership-summary')).toContainText('미해결');
    await expect(area.locator('.ownership-summary')).toContainText('이 범위 검토 완료');
    const firstHash = new URLSearchParams(page.url().split('?')[1]).get('journal');
    await page.request.post(`${serviceUrl}${prefix}/revise`);
    await page.reload();
    await expect(area).toContainText('반복 매출이 안정적으로 이어질 것');
    await area.getByRole('button', { name: '현재 보유 점검으로' }).click();
    await area.getByRole('button', { name: '이 점검 이어가기', exact: true }).click();
    await area.getByRole('combobox', { name: '내 판단', exact: true }).selectOption('exception');
    await area.getByLabel('예외 종료 날짜').fill('2020-01-02');
    await area.getByLabel('예외 종료 사건').fill('다음 분기 실적 발표');
    await area.getByLabel('다음 확인 날짜').fill('2099-10-20');
    await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
    await area.getByRole('button', { name: '확인한 점검 저장' }).click();
    await expect(area.getByRole('heading', { name: '당시 보유 점검·복기' })).toBeVisible();
    await expect(area.locator('.ownership-summary')).toContainText('2020-01-02 (UTC 날짜) · 다음 분기 실적 발표');
    await area.getByRole('button', { name: '현재 보유 점검으로' }).click();
    await expect(area).toContainText('이전부터 미해결');
    await expect(area).toContainText('예외 적용 기간이 지났습니다');
    await expect(area.getByRole('button', { name: '이 점검 이어가기', exact: true })).toHaveCount(1);
    await area.getByRole('button', { name: '지금 기준으로 복기', exact: true }).click();
    await area.getByLabel('내 회고 분류').selectOption('external_change');
    await area.getByLabel('당시에 생각한 경로').fill('성장이 이어질 것으로 생각했다.');
    await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
    await area.getByRole('button', { name: '확인한 점검 저장' }).click();
    await expect(area.locator('.ownership-summary')).toContainText('외부 여건의 변화');
    await area.locator('.ownership-summary').scrollIntoViewIfNeeded(); await capture(page, `saved-${theme}`); await a11y(page, '[data-ownership-review]');
    await page.goto('/#/portfolio?tab=review&date=2026-10-01&filter=due&selected=ABC');
    const portfolioHash = new URL(page.url()).hash;
    await page.getByRole('link', { name: '이 종목의 보유 점검 열기' }).click();
    await expect(area.getByLabel('비교할 당시 기록')).toHaveValue(originalJournalId);
    await area.getByRole('link', { name: '투자 리뷰로 돌아가기' }).click();
    expect(new URL(page.url()).hash).toBe(portfolioHash);
    const historical = await page.request.get(`${serviceUrl}${prefix}/api/decision-journals/${firstHash}/ownership-review`);
    expect(historical.status()).toBe(200);
    expect((await historical.json()).review.conclusion).toBe('defer');
  });
}

test('0.12 return links reject external targets in ownership and records readers', async ({ page }) => {
  await setup(page, 'light');
  for (const value of ['javascript:alert(1)', 'https://example.invalid/', '//example.invalid/']) {
    const query = new URLSearchParams({ tab: 'ownership', instrument: 'US:ABC', returnHash: value });
    await page.goto(`/#/watchlist/ABC?${query}`);
    await expect(page.getByRole('heading', { name: '보유 점검', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: '투자 리뷰로 돌아가기' })).toHaveCount(0);
    await page.getByRole('link', { name: '기록·미완료 작업 열기' }).click();
    await expect(page.getByRole('heading', { name: '이 종목의 검토와 기록' })).toBeVisible();
    await expect(page.getByRole('link', { name: '투자 리뷰로 돌아가기' })).toHaveCount(0);
  }
});

test('0.12 missing original empty fields and closed form are not completion', async ({ page }) => {
  const { prefix } = await setup(page, 'light', false);
  const area = page.locator('[data-ownership-review]');
  await expect(area).toContainText('최초 기록이 없어 현재 검토만 가능합니다');
  await area.getByRole('button', { name: '검토 기록 시작', exact: true }).click();
  await area.getByRole('button', { name: '확인한 점검 저장' }).click();
  await area.getByRole('button', { name: '내 검토 남기기', exact: true }).click();
  await area.getByRole('button', { name: '작성 닫기', exact: true }).click();
  let current = await (await page.request.get(`${serviceUrl}${prefix}/api/investment-cases/US%3AABC/ownership-review`)).json();
  expect(current.issues).toEqual([]);
  await area.getByRole('button', { name: '내 검토 남기기', exact: true }).click();
  await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
  await area.getByRole('button', { name: '확인한 점검 저장' }).click();
  await expect(area.getByRole('heading', { name: '당시 보유 점검·복기' })).toBeVisible();
  await expect(area.locator('.ownership-summary')).toContainText('검토 완료 표시 없음');
  current = await (await page.request.get(`${serviceUrl}${prefix}/api/investment-cases/US%3AABC/ownership-review`)).json();
  expect(current.issues[0].due.planMissing).toBe(true);
  expect(current.issues[0].review.reviewedAt).toBeNull();
});

test('0.12 stale preview retains draft and GET failure has visible retry', async ({ page }) => {
  const { prefix } = await setup(page, 'dark'); const area = page.locator('[data-ownership-review]');
  await area.getByRole('button', { name: '내 검토 남기기', exact: true }).click();
  await area.getByRole('textbox', { name: '관찰한 사실', exact: true }).fill('저장되지 않은 초안 유지');
  await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
  await expect(area.getByRole('heading', { name: '확인할 점검 기록' })).toBeFocused();
  await page.request.post(`${serviceUrl}${prefix}/revise`);
  await area.getByRole('button', { name: '확인한 점검 저장' }).click();
  await expect(area.getByRole('alert')).toContainText('확인 중 입력이 바뀌었습니다');
  await expect(area.getByRole('textbox', { name: '관찰한 사실', exact: true })).toHaveValue('저장되지 않은 초안 유지');
  await page.route('**/api/investment-cases/*/ownership-review', route => route.fulfill({ status: 503, json: { detail: { code: 'case_store_unavailable' } } }));
  await area.getByRole('button', { name: '점검 자료 다시 읽기' }).click();
  await expect(area.getByRole('alert')).toBeVisible();
  await expect(area.getByRole('button', { name: '점검 자료 다시 읽기' })).toBeEnabled();
  await a11y(page, '[data-ownership-review]');
});

test('0.12 normal portfolio navigation preserves selected historical review', async ({ page }) => {
  await setup(page, 'light');
  await page.goto('/#/portfolio');
  await page.getByRole('button', { name: '투자 리뷰', exact: true }).click();
  await page.getByText('리뷰 이력', { exact: true }).click();
  await page.getByRole('button', { name: /2026-09-20/ }).click();
  await expect(page.locator('.investment-review-meta')).toContainText('2026-09-20');
  await page.getByRole('link', { name: '이 종목의 보유 점검 열기' }).click();
  await page.getByRole('link', { name: '투자 리뷰로 돌아가기' }).click();
  expect(new URL(page.url()).hash).toBe('#/portfolio?tab=review&date=2026-09-20');
  await expect(page.locator('.investment-review-meta')).toContainText('2026-09-20');
});

test('0.12 changed condition requires reselection while draft survives', async ({ page }) => {
  const { prefix } = await setup(page, 'dark'); const area = page.locator('[data-ownership-review]');
  await area.getByRole('button', { name: '내 검토 남기기', exact: true }).click();
  await area.getByLabel('연결할 당시 조건').selectOption({ label: '현재 · 현금 전환이 악화될 때' });
  await area.getByRole('textbox', { name: '관찰한 사실', exact: true }).fill('판본이 바뀌어도 초안 보존');
  await page.request.post(`${serviceUrl}${prefix}/revise-reason`);
  await area.getByRole('button', { name: '점검 자료 다시 읽기' }).click();
  await expect(area).toContainText('이전 판본의 조건 — 다시 선택해 주세요');
  await expect(area.getByRole('button', { name: '점검 내용 미리보기', exact: true })).toBeDisabled();
  await expect(area.getByRole('textbox', { name: '관찰한 사실', exact: true })).toHaveValue('판본이 바뀌어도 초안 보존');
  await area.getByLabel('연결할 당시 조건').selectOption({ label: '현재 · 현금 전환의 새 조건' });
  await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
  await area.getByRole('button', { name: '확인한 점검 저장' }).click();
  await expect(area.getByRole('heading', { name: '당시 보유 점검·복기' })).toBeVisible();
  await expect(area.locator('.ownership-summary')).toContainText('현금 전환의 새 조건');
});

test('0.12 normal record to review navigation clears unrelated journal', async ({ page }) => {
  const { originalJournalId } = await setup(page, 'light');
  await page.goto(`/#/watchlist/ABC?tab=records&instrument=US%3AABC&journal=${originalJournalId}`);
  await page.getByRole('button', { name: '보유 점검', exact: true }).click();
  await expect(page.getByRole('heading', { name: '보유 점검', exact: true })).toBeVisible();
  expect(new URLSearchParams(new URL(page.url()).hash.split('?')[1]).has('journal')).toBe(false);
  await expect(page.locator('[data-ownership-review]')).toContainText('반복 매출이 안정적으로 이어질 것');
});

test('0.12 resolved review, source purge, and loading keep honest states', async ({ page }) => {
  const { prefix } = await setup(page, 'dark'); const area = page.locator('[data-ownership-review]');
  await area.getByRole('button', { name: '내 검토 남기기', exact: true }).click();
  await area.getByRole('combobox', { name: '내 판단', exact: true }).selectOption('maintain');
  await area.getByLabel('내가 본 근거 수준').selectOption('sufficient');
  await area.getByLabel('이 항목을 해소된 것으로 기록').check();
  await area.getByLabel('이번 범위의 검토를 마쳤음').check();
  await area.getByRole('checkbox', { name: '기업', exact: true }).check();
  await area.getByRole('button', { name: '점검 내용 미리보기', exact: true }).click();
  await area.getByRole('button', { name: '확인한 점검 저장' }).click();
  await expect(area.getByRole('heading', { name: '당시 보유 점검·복기' })).toBeVisible();
  await area.getByRole('button', { name: '현재 보유 점검으로' }).click();
  await expect(area).toContainText('사용자가 해소로 기록');
  await expect(area).not.toContainText('해소된 상태로 처리하지 않았습니다');
  await expect(area.locator('.ownership-since-reviewed')).toContainText('완료한 검토 이후 비교 가능한 입력은 그대로입니다');
  await page.request.post(`${serviceUrl}${prefix}/revise`);
  await area.getByRole('button', { name: '점검 자료 다시 읽기' }).click();
  await expect(area.locator('.ownership-since-reviewed')).toContainText('완료한 검토 이후 새 입력: 기업 분석');
  await expect(area).toContainText('사용자가 해소로 기록');
  const proposal = await (await page.request.post(`${serviceUrl}${prefix}/api/investment-cases/source-delete-preview`, { data: { kind: 'company', id: 'report-a' } })).json();
  const deleted = await page.request.delete(`${serviceUrl}${prefix}/api/analysis-reports/report-a?confirmationToken=${proposal.token}&operationId=${crypto.randomUUID().replace(/-/g, '')}`);
  expect(deleted.status()).toBe(200);
  await area.getByRole('button', { name: '점검 자료 다시 읽기' }).click();
  await area.getByText('사업과 이유 · 당시와 현재 자료', { exact: true }).click();
  await expect(area.getByText('기업 분석 · 본문 삭제', { exact: true })).toBeVisible();
  await expect(area).not.toContainText('보고서 V1의 가정과 불확실성');
  await expect(area.locator('.ownership-since-reviewed')).toContainText('완료한 검토 이후 직접 비교할 수 있는 입력이 없습니다');
  await a11y(page, '[data-ownership-review]');
  let release!: () => void;
  const pause = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/investment-cases/*/ownership-review', async route => { await pause; await route.fallback(); });
  await area.getByRole('button', { name: '점검 자료 다시 읽기' }).click();
  await expect(area.getByRole('status').filter({ hasText: '당시 입력과 검토 이력을 읽는 중입니다' })).toBeVisible();
  await expect(area).toHaveAttribute('aria-busy', 'true');
  release();
  await expect(area).toHaveAttribute('aria-busy', 'false');
});
