import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

// These tests use a real isolated FastAPI/SQLite/JSON service; the unrelated
// surrounding screens use saved display fixtures and make no provider calls.
const serviceUrl = process.env.CASE_TEST_URL || 'http://127.0.0.1:18789';

async function setup(page: Page, theme: string) {
  const fixture = await page.request.post(`${serviceUrl}/fixture`);
  const { prefix } = await fixture.json();
  await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()); const path = url.pathname;
    if (path.startsWith('/api/investment-cases') || path.startsWith('/api/decision-journals') || (path.startsWith('/api/analysis-reports/') && route.request().method() === 'DELETE')) {
      const response = await route.fetch({ url: `${serviceUrl}${prefix}${path}${url.search}` });
      return route.fulfill({ response });
    }
    if (path === '/api/watchlist') return route.fulfill({ json: { watchlist: ['ABC'], items: ['ABC'] } });
    if (path === '/api/watchlist/overview') return route.fulfill({ json: { items: [{ ticker: 'ABC', market: 'US', name: '예시기업', item: 'ABC' }] } });
    if (path === '/api/watchlist/detail') return route.fulfill({ json: { item: 'ABC', company: { ticker: 'ABC', market: 'US', name: '예시기업' }, news: [] } });
    if (path === '/api/analysis-reports') return route.fulfill({ json: [{ id: 'report-a', title: '예시기업', generatedAt: '2026-10-01T00:00:00Z', company: { ticker: 'ABC', market: 'US', name: '예시기업' } }] });
    if (path === '/api/analysis-reports/report-a') return route.fulfill({ json: { id: 'report-a', title: '예시기업', markdown: '## 기업 분석\n검토할 가정입니다.', company: { ticker: 'ABC', market: 'US', name: '예시기업' } } });
    if (path === '/api/topic-reports') return route.fulfill({ json: { reports: [] } });
    if (path === '/api/portfolio') return route.fulfill({ json: { revision: 1, positions: [], cash: [] } });
    if (path.startsWith('/api/investment-review')) return route.fulfill({ json: path.endsWith('/history') ? { items: [] } : { date: '2026-10-01', reviewRevision: 1, sourceSchemaVersion: 2, reviewState: 'draft', summary: '저장 리뷰', positionRoster: [{ ticker: 'ABC', instrumentId: 'US:ABC', market: 'US', thesisVerdict: 'insufficient_evidence' }], positionReviews: [] } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('/#/watchlist/ABC?tab=records&instrument=US%3AABC');
  await expect(page.getByRole('heading', { name: '이 종목의 검토와 기록' })).toBeVisible();
  return prefix;
}

for (const theme of ['light', 'dark']) {
  test(`0.11 real save replay purge and return flow ${theme}`, async ({ page }) => {
    const prefix = await setup(page, theme);
    const area = page.locator('[data-investment-case]');
    await area.getByRole('button', { name: '검토 기록 시작', exact: true }).click();
    await expect(area.getByRole('heading', { name: '확인할 변경' })).toBeFocused();
    await area.getByRole('button', { name: '확인한 내용 저장' }).click();
    await area.getByRole('button', { name: '기록 남기기' }).click();
    await area.getByLabel('결정이나 변화에 대한 생각').fill('수요의 지속성을 더 확인한다.');
    await area.getByLabel('반대 근거와 불확실성').fill('경쟁 심화로 수익성이 낮아질 수 있다.');
    const formAxe = await new AxeBuilder({ page }).include('.case-form').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
    expect(formAxe.violations.map(v => v.id)).toEqual([]);
    if (process.env.CASE_CAPTURE_DIR) await page.screenshot({ path: `${process.env.CASE_CAPTURE_DIR}/form-${theme}-${test.info().project.name}.png` });
    await area.getByRole('button', { name: '저장 내용 미리보기' }).click();
    await expect(area.locator('.case-preview')).toContainText('저장 크기:');
    const previewAxe = await new AxeBuilder({ page }).include('.case-preview').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
    expect(previewAxe.violations.map(v => v.id)).toEqual([]);
    await area.getByRole('button', { name: '확인한 내용 저장' }).click();
    await expect(area.getByRole('heading', { name: '당시 기록', exact: true })).toBeVisible();
    await expect(area).toContainText('수요의 지속성을 더 확인한다.');
    await page.request.post(`${serviceUrl}${prefix}/revise`);
    await page.reload();
    await area.locator('.case-reader').getByText('기업 분석 · 보존', { exact: true }).click();
    await expect(area).toContainText('보고서 V1의 가정과 불확실성');
    await expect(area).toContainText('원본에 이후 변경 있음');
    await expect(area).not.toContainText('보고서 V2입니다.');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const axe = await new AxeBuilder({ page }).include('[data-investment-case]').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
    expect(axe.violations.map(v => v.id)).toEqual([]);
    if (process.env.CASE_CAPTURE_DIR) {
      await page.screenshot({ path: `${process.env.CASE_CAPTURE_DIR}/reader-${theme}-${test.info().project.name}.png`, fullPage: true });
      await page.screenshot({ path: `${process.env.CASE_CAPTURE_DIR}/reader-viewport-${theme}-${test.info().project.name}.png` });
    }
    await area.getByRole('button', { name: '이 기록의 보존본문 전체 삭제' }).click();
    await area.getByRole('button', { name: '범위 확인 후 본문 삭제' }).click();
    await expect(area).toContainText('개인본문 삭제됨');
    await expect(area).not.toContainText('수요의 지속성을 더 확인한다.');
    await area.getByRole('button', { name: '기록 목록으로' }).click();
    await page.getByRole('button', { name: '기업 정보', exact: true }).click();
    await page.goBack();
    await expect(page.getByRole('button', { name: '기록', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await page.goto('/#/portfolio?tab=review&date=2026-10-01');
    await page.getByRole('link', { name: '이 종목의 기록 열기' }).click();
    await expect(area.getByRole('link', { name: '투자 리뷰로 돌아가기' })).toBeVisible();
    await area.getByRole('link', { name: '투자 리뷰로 돌아가기' }).click();
    await expect(page.getByRole('heading', { name: '투자 리뷰', exact: true })).toBeVisible();
  });
}

test('0.11 source delete previews linked content and defaults to purge', async ({ page }) => {
  const prefix = await setup(page, 'light');
  const base = `${serviceUrl}${prefix}`;
  for (const [action, expectedCaseRevision] of [['create', 0], ['journal', 1]] as const) {
    const proposal = await page.request.post(`${base}/api/investment-cases/preview`, { data: { instrumentId: 'US:ABC', expectedCaseRevision, action } });
    const { token } = await proposal.json();
    await page.request.post(`${base}/api/investment-cases/confirm`, { data: { token, operationId: crypto.randomUUID().replace(/-/g, '') } });
  }
  await page.goto('/#/analysis');
  await page.getByRole('button', { name: /삭제/ }).first().click();
  const dialog = page.getByRole('dialog', { name: '보고서와 연결된 보존 기록 확인' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('보존본문 처리')).toHaveValue('purge');
  await dialog.getByLabel('보존본문 처리').selectOption('preserve');
  await expect(dialog.getByRole('button', { name: '보존본 유지 확인 후 원본 삭제' })).toBeEnabled();
  await dialog.getByLabel('보존본문 처리').selectOption('purge');
  await expect(dialog.getByRole('button', { name: '원본과 연결 보존본문 삭제' })).toBeEnabled();
  const axe = await new AxeBuilder({ page }).include('.case-delete-dialog').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(axe.violations.map(v => v.id)).toEqual([]);
  const removed = page.waitForResponse(response => response.request().method() === 'DELETE' && response.url().includes('/api/analysis-reports/report-a'));
  await dialog.getByRole('button', { name: '원본과 연결 보존본문 삭제' }).click();
  expect((await removed).status()).toBe(200);
  const current = await (await page.request.get(`${base}/api/investment-cases/US:ABC`)).json();
  const saved = await (await page.request.get(`${base}/api/decision-journals/${current.journals[0].id}`)).json();
  expect(saved.journal.inputs.company.content).toBeNull();
});

async function savedJournal(page: Page, prefix: string) {
  const base = `${serviceUrl}${prefix}`;
  for (const [action, expectedCaseRevision] of [['create', 0], ['journal', 1]] as const) {
    const preview = await page.request.post(`${base}/api/investment-cases/preview`, { data: { instrumentId: 'US:ABC', expectedCaseRevision, action, ...(action === 'journal' ? { decisionText: '당시 생각 유지' } : {}) } });
    expect(preview.status()).toBe(200);
    const { token } = await preview.json();
    const response = await page.request.post(`${base}/api/investment-cases/confirm`, { data: { token, operationId: crypto.randomUUID().replace(/-/g, '') } });
    expect(response.status()).toBe(200);
  }
  const view = await (await page.request.get(`${base}/api/investment-cases/US:ABC`)).json();
  return view.journals[0].id as string;
}

test('0.11 historical reader survives current projection failure', async ({ page }) => {
  const prefix = await setup(page, 'dark'); const id = await savedJournal(page, prefix);
  await page.route('**/api/investment-cases/US%3AABC', route => route.fulfill({ status: 503, json: { detail: { code: 'case_source_invalid' } } }));
  await page.goto(`/#/watchlist/ABC?tab=records&instrument=US%3AABC&journal=${id}`);
  await expect(page.getByRole('heading', { name: '당시 기록', exact: true })).toBeVisible();
  await expect(page.locator('.case-reader')).toContainText('당시 생각 유지');
  await expect(page.locator('.case-reader').getByRole('button', { name: '이 기록의 보존본문 전체 삭제' })).toBeDisabled();
});

test('0.11 explicit refresh rereads original status and later source purge', async ({ page }) => {
  const prefix = await setup(page, 'light'); const id = await savedJournal(page, prefix);
  const base = `${serviceUrl}${prefix}`;
  await page.goto(`/#/watchlist/ABC?tab=records&instrument=US%3AABC&journal=${id}`);
  const area = page.locator('[data-investment-case]');
  await area.getByText('기업 분석 · 보존', { exact: true }).click();
  await expect(area).toContainText('원본 판본 일치');
  await page.request.post(`${base}/revise`);
  await area.getByRole('button', { name: '현재 자료 다시 읽기' }).click();
  await area.getByText('기업 분석 · 보존', { exact: true }).click();
  await expect(area).toContainText('원본에 이후 변경 있음');
  const impact = await (await page.request.post(`${base}/api/investment-cases/source-delete-preview`, { data: { kind: 'company', id: 'report-a' } })).json();
  const deleted = await page.request.delete(`${base}/api/analysis-reports/report-a?confirmationToken=${impact.token}&operationId=${crypto.randomUUID().replace(/-/g, '')}`);
  expect(deleted.status()).toBe(200);
  await area.getByRole('button', { name: '현재 자료 다시 읽기' }).click();
  await expect(area).toContainText('기업 분석 · 본문 삭제');
  await expect(area).not.toContainText('보고서 V1의 가정과 불확실성');
});

test('0.11 source recovery reports partial result and preserves replacement', async ({ page }) => {
  const prefix = await setup(page, 'dark'); await savedJournal(page, prefix);
  const base = `${serviceUrl}${prefix}`;
  expect((await page.request.post(`${base}/interrupt-source-delete`)).status()).toBe(200);
  await page.reload();
  await page.getByRole('button', { name: '작업 복구', exact: true }).click();
  await expect(page.locator('[data-investment-case]')).toContainText('이후 복원되거나 바뀐 원본은 남겨 두었습니다');
  const impact = await page.request.post(`${base}/api/investment-cases/source-delete-preview`, { data: { kind: 'company', id: 'report-a' } });
  expect(impact.status()).toBe(200);
});

test('0.11 owned transition can explicitly exclude blocked input', async ({ page }) => {
  const prefix = await setup(page, 'light'); await savedJournal(page, prefix);
  await page.request.post(`${serviceUrl}${prefix}/block-source`);
  await page.reload();
  const area = page.locator('[data-investment-case]');
  await area.getByLabel('다음 단계').selectOption('owned');
  await area.getByRole('button', { name: '단계 변경 미리보기' }).click();
  const preview = area.locator('.case-preview');
  await expect(preview).toContainText('원본을 정정하거나 보존에서 제외할 항목');
  await preview.getByRole('checkbox', { name: '기업 분석', exact: true }).uncheck();
  await preview.getByRole('button', { name: '선택한 항목으로 단계 변경 다시 확인' }).click();
  await preview.getByRole('button', { name: '확인한 내용 저장' }).click();
  await expect(area.getByRole('heading', { name: '당시 기록', exact: true })).toBeVisible();
  await expect(area).toContainText('기업 분석 · 사용자가 제외');
});

test('0.11 correction links later report and late save respects navigation', async ({ page }) => {
  const prefix = await setup(page, 'light'); const id = await savedJournal(page, prefix);
  await page.request.post(`${serviceUrl}${prefix}/new-report`);
  await page.goto(`/#/watchlist/ABC?tab=records&instrument=US%3AABC&journal=${id}`);
  const area = page.locator('[data-investment-case]');
  await area.getByText('기업 분석 · 보존', { exact: true }).click();
  await area.getByRole('button', { name: '이후 자료 연결 확인' }).first().click();
  await area.getByRole('button', { name: '확인한 내용 저장' }).click();
  await expect(area.getByRole('link', { name: '이후 확인한 자료 열기' })).toHaveAttribute('href', '#/analysis/report-b');
  await area.getByRole('button', { name: '기록 목록으로', exact: true }).click();
  await area.getByRole('button', { name: '기록 남기기' }).click();
  await area.getByRole('button', { name: '저장 내용 미리보기' }).click();
  let release!: () => void; const hold = new Promise<void>(resolve => { release = resolve; });
  let arrived!: () => void; const started = new Promise<void>(resolve => { arrived = resolve; });
  await page.route('**/api/investment-cases/confirm', async route => { arrived(); await hold; await route.fallback(); });
  await area.getByRole('button', { name: '확인한 내용 저장' }).click();
  await started;
  await page.goto('/#/portfolio');
  const completed = page.waitForResponse(response => response.url().endsWith('/api/investment-cases/confirm'));
  release(); expect((await completed).status()).toBe(200);
  // The response headers precede the component's refresh and final navigation
  // guard. Await that whole save action before asserting or closing the context.
  await expect(area).toHaveAttribute('aria-busy', 'false');
  await expect(page).toHaveURL(/#\/portfolio$/);
});

test('0.11 cancelled source policy never overwrites a later confirmation', async ({ page }) => {
  const prefix = await setup(page, 'dark'); await savedJournal(page, prefix);
  await page.goto('/#/analysis');
  await page.getByRole('button', { name: /삭제/ }).first().click();
  const dialog = page.getByRole('dialog', { name: '보고서와 연결된 보존 기록 확인' });
  let release!: () => void; const hold = new Promise<void>(resolve => { release = resolve; });
  let arrived!: () => void; const started = new Promise<void>(resolve => { arrived = resolve; });
  let finished!: () => void; const done = new Promise<void>(resolve => { finished = resolve; });
  await page.route('**/api/investment-cases/source-delete-preview', async route => {
    if (route.request().postDataJSON()?.policy !== 'preserve') return route.fallback();
    arrived(); await hold;
    try { await route.fallback(); } finally { finished(); }
  });
  await dialog.getByLabel('보존본문 처리').selectOption('preserve'); await started;
  await dialog.getByRole('button', { name: '취소', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: /삭제/ }).first().click();
  await expect(dialog.getByLabel('보존본문 처리')).toHaveValue('purge');
  release(); await done;
  await expect(dialog.getByLabel('보존본문 처리')).toHaveValue('purge');
  await expect(dialog.getByRole('button', { name: '원본과 연결 보존본문 삭제' })).toBeEnabled();
  await page.keyboard.press('Escape'); await expect(dialog).not.toBeVisible();
});

test('0.11 delayed source preview is dismissed when navigating away', async ({ page }) => {
  await setup(page, 'light'); await page.goto('/#/analysis');
  let release!: () => void; const hold = new Promise<void>(resolve => { release = resolve; });
  let arrived!: () => void; const started = new Promise<void>(resolve => { arrived = resolve; });
  let finished!: () => void; const done = new Promise<void>(resolve => { finished = resolve; });
  let prompts = 0; page.on('dialog', async dialog => { prompts++; await dialog.dismiss(); });
  await page.route('**/api/investment-cases/source-delete-preview', async route => {
    arrived(); await hold;
    try { await route.fulfill({ json: { linkedJournalCount: 0 } }); } finally { finished(); }
  });
  await page.getByRole('button', { name: /삭제/ }).first().click(); await started;
  await page.goto('/#/portfolio'); release(); await done;
  await expect(page).toHaveURL(/#\/portfolio$/);
  expect(prompts).toBe(0);
  await expect(page.getByRole('dialog', { name: '보고서와 연결된 보존 기록 확인' })).not.toBeVisible();
});
