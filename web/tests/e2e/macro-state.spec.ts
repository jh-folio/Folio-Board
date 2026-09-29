import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

for (const theme of ['light', 'dark']) {
  test(`0.8 current state and explicit policy confirmation ${theme}`, async ({ page }, info) => {
    let saves = 0;
    await page.addInitScript(value => { localStorage.setItem('folio.themePreference.v1', value); localStorage.setItem('folio.react.agentClosed', '1'); }, theme);
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/macro/state') return route.fulfill({ json: {
        market: 'US', date: '2026-09-29', notice: '이미 나타난 신호의 확인이지 예측이 아닙니다. 과거 전환점 표본이 적습니다.', inflationLimitation: 'B1 대비 4.76%p, 한도 5%p에 가까움',
        cards: [{ axis: 'inflation', previous: null, snapshot: { snapshotId: 'macro-fixture', inputFingerprint: 'test', asOf: '2026-09-29T00:00:00Z', level: 'above_reference', direction: 'falling', promotion: 'primary', confidence: 'medium', freshness: 'current', conflicts: [], unknownReason: [], sourceRefs: [] } }, { axis: 'growth', snapshot: null, previous: null }],
      } });
      if (url.pathname === '/api/macro/policies/targets/T') return route.fulfill({ json: { profile: { ticker: 'T', profileId: 'p', items: [{ id: 'e', factor: 'interest_rate', quote: 'Higher interest rates increase our borrowing costs.' }] }, reason: { revisionId: 'r', conditions: ['금리 상승으로 비용이 늘면 다시 본다.'] } } });
      if (url.pathname === '/api/macro/policies') return route.fulfill({ json: { items: [] } });
      if (url.pathname.endsWith('/policies/preview')) return route.fulfill({ json: { draft: route.request().postDataJSON(), previewId: 'preview-test', notice: '공식 원문 확인 후 저장' } });
      if (url.pathname.endsWith('/policies/confirm')) { saves++; return route.fulfill({ json: { ...route.request().postDataJSON().draft, id: 'saved-policy' } }); }
      return route.fulfill({ status: 404, json: {} });
    });
    await page.goto('/#/macro/state');
    await expect(page.getByRole('heading', { name: '시장·거시', exact: true })).toBeVisible();
    await expect(page.getByText('기준 통과 요약', { exact: true })).toBeVisible();
    await expect(page.getByText('이전 월말과 비교: 저장 기록 없음')).toBeVisible();
    await page.getByText('공식 발표를 기록하기', { exact: true }).click();
    await page.getByLabel('무슨 변화인가요?').fill('공식 정책 테스트');
    await page.getByLabel('공식 발표 제목').fill('테스트 결정문');
    await page.getByLabel('공식 원문 링크').fill('https://www.federalreserve.gov/example');
    await page.getByLabel('원문에서 확인한 문장').fill('테스트용 공식 문장');
    await page.getByLabel('이 영향이 성립하지 않을 조건').fill('시행 전 철회');
    await page.getByLabel('다음에 무엇을 확인할까요?').fill('시행일 확인');
    await page.getByText('기업에 전달되는 경로 기록 (선택)', { exact: true }).click();
    await page.getByRole('button', { name: '전달 경로 추가', exact: true }).click();
    await page.getByLabel('어떤 조건에서 어떻게 전달되나요?').fill('금리 상승으로 차입 비용이 늘 수 있음');
    await page.getByLabel('연결할 기업 (선택)', { exact: true }).fill('T');
    await page.getByRole('button', { name: '저장된 공시 노출 찾기' }).click();
    await page.getByLabel('정책과 직접 연결되는 공시 문장').selectOption('e');
    await page.getByLabel('내가 쓴 조건과 연결 (선택)').selectOption('0');
    await page.getByLabel('내 조건과 위 전달 설명에 그대로 들어 있는 공통 표현').fill('금리 상승');
    await page.getByRole('button', { name: '기록 미리보기' }).click();
    await expect(page.getByRole('button', { name: '확인한 내용 저장' })).toBeDisabled();
    expect(saves).toBe(0);
    await page.getByLabel('공식 원문과 내용·날짜·진행 단계를 대조했습니다.').check();
    await page.getByLabel('무슨 변화인가요?').fill('변경한 정책 테스트');
    await expect(page.getByRole('button', { name: '확인한 내용 저장' })).toHaveCount(0);
    await page.getByRole('button', { name: '기록 미리보기' }).click();
    await page.getByLabel('공식 원문과 내용·날짜·진행 단계를 대조했습니다.').check();
    await page.getByRole('button', { name: '확인한 내용 저장' }).click();
    await expect(page.getByText('정책 기록을 저장했습니다.')).toBeVisible();
    expect(saves).toBe(1);
    await page.getByText('공식 발표를 기록하기', { exact: true }).click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(overflow).toBe(false);
    const a11y = await new AxeBuilder({ page }).include('.macro-state-stack').withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(a11y.violations).toEqual([]);
    await page.screenshot({ path: info.outputPath(`macro-state-${theme}.png`), fullPage: true });
  });
}

test('macro read failures stay visible and never create a policy', async ({ page }) => {
  let writes = 0;
  await page.route('**/api/**', route => { if (route.request().method() === 'POST') writes++; return route.fulfill({ status: 503, json: {} }); });
  await page.goto('/#/macro/state');
  await expect(page.getByRole('alert').filter({ hasText: '거시 기록을 읽지 못했습니다' })).toBeVisible();
  expect(writes).toBe(0);
});
