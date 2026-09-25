import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const theme of ["light", "dark"]) {
 for (const kind of ["analysis", "deep-research"]) {
  test(`Report citation links survive reopening (${theme}, ${kind})`, async ({ page }, testInfo) => {
    const id = "citation-fixture";
    const sourceUrl = "https://example.com/annual%282026%29";
    const report = {
      id, headline: "Acme 분석", title: "Acme 분석", company: { ticker: "ACME", name: "Acme" },
      generatedAt: "2026-09-22T01:00:00Z", analysisStyle: "beginner", saved: true,
      topicKey: "custom", topicLabel: "Acme 분석", deepResearch: true,
      markdown: "# Acme 분석\n\n## 사업\n\n매출 증가와 비용 부담을 함께 확인합니다.\n\n<!-- folio-source-ids: ev_001 -->\n\n<!-- folio-citation-links -->\n인용 출처: [Acme 연차보고서](" + sourceUrl + ")\n<!-- /folio-citation-links -->\n\n",
      sourceLedger: [{ sourceId: "ev_001", title: "Acme 연차보고서", url: sourceUrl }],
      sources: [], quality: {},
    };
    await page.addInitScript(value => localStorage.setItem("folio.themePreference.v1", value), theme);
    await page.route("**/*", async route => {
      const url = new URL(route.request().url());
      if (url.hostname !== "127.0.0.1") return route.abort();
      if (!url.pathname.startsWith("/api/")) return route.continue();
      const api = kind === "analysis" ? "/api/analysis-reports" : "/api/topic-reports";
      const data = url.pathname === api ? [{ ...report, markdown: undefined }]
        : url.pathname === `${api}/${id}` ? report : null;
      return route.fulfill({ status: data ? 200 : 404, contentType: "application/json", body: JSON.stringify(data ?? {}) });
    });
    await page.goto(`/?theme=${theme}#/${kind}/${id}`);
    const body = page.locator(".report-body");
    const link = body.getByRole("link", { name: "Acme 연차보고서", exact: true });
    await expect(link).toHaveAttribute("href", sourceUrl);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noreferrer");
    await expect(body).not.toContainText("folio-citation-links");
    await expect(body).not.toContainText("folio-source-ids");
    await page.reload();
    await expect(link).toBeVisible();
    await link.focus();
    await expect(link).toBeFocused();
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all(document.getAnimations().filter(a => a.effect?.getComputedTiming().iterations !== Infinity)
        .map(a => a.finished.catch(() => undefined)));
    });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    const axe = await new AxeBuilder({ page }).include(".report-reader-shell").analyze();
    expect(axe.violations.filter(v => ["serious", "critical"].includes(v.impact || ""))).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`citations-${theme}.png`), fullPage: true });
    // Verify the actual isolation behavior of the existing noreferrer reader.
    await page.context().route(sourceUrl, route => route.fulfill({ contentType: "text/html", body: "<p>Citation fixture</p>" }));
    const opened = page.waitForEvent("popup");
    await link.press("Enter");
    const popup = await opened;
    await popup.waitForLoadState("domcontentloaded");
    expect(await popup.evaluate(() => window.opener)).toBeNull();
    await popup.close();
  });
 }
}
