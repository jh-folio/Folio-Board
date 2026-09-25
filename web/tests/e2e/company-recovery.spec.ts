import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const theme of ["light", "dark"]) {
  test(`Recovery candidate reopens with an honest status (${theme})`, async ({ page }, testInfo) => {
    const id = "recovery-0123456789abcdef0123456789abcdef";
    const message = "출력 한도에 도달했습니다. 복구 후보입니다. 정상 보고서로 저장되지 않았으며 기존 보고서는 유지됩니다.";
    const report = {
      id, headline: "[복구 후보] Test 분석", title: "[복구 후보] Test 분석",
      company: { ticker: "TEST", name: "Test" }, generatedAt: "2026-09-21T01:00:00Z",
      analysisStyle: "beginner", saved: false, recoveryStored: true,
      generation: { mode: "agent", message },
      markdown: "# Test 분석\n\n## 사업\n\n다시 열어 확인할 수 있는 후보 본문입니다.",
      sources: [], quality: {},
    };
    await page.addInitScript((value) => localStorage.setItem("folio.themePreference.v1", value), theme);
    await page.route("**/*", async route => {
      const url = new URL(route.request().url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      const data = url.pathname === "/api/analysis-reports" ? [{ ...report, markdown: undefined }]
        : url.pathname === `/api/analysis-reports/${id}` ? report : null;
      return route.fulfill({ status: data ? 200 : 404, contentType: "application/json", body: JSON.stringify(data ?? { detail: "fixture route omitted" }) });
    });
    await page.goto(`/?theme=${theme}#/analysis/${id}`);
    await expect(page.locator(".report-body")).toContainText("후보 본문");
    await expect(page.locator(".react-reader-status").filter({ hasText: "복구 후보" })).toContainText(message);
    await page.reload();
    await expect(page.locator(".report-body")).toContainText("후보 본문");
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all(document.getAnimations().filter(animation =>
        animation.effect?.getComputedTiming().iterations !== Infinity
      ).map(animation => animation.finished.catch(() => undefined)));
    });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    expect(overflow).toBe(false);
    const axe = await new AxeBuilder({ page }).include(".report-reader-shell").analyze();
    expect(axe.violations.filter(v => ["serious", "critical"].includes(v.impact || ""))).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`recovery-${theme}.png`), fullPage: true });
    await page.getByRole("button", { name: "리더 닫기", exact: true }).click();
    await expect(page).toHaveURL(/#\/analysis$/);
    await expect(page.locator(".report-reader-shell")).toBeHidden();
    await expect(page.getByText("[복구 후보] Test 분석", { exact: true }).first()).toBeVisible();
  });
}
