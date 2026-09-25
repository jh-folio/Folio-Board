import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const STATUS = {
  version: 1,
  settings: { retentionDays: 30, autoDelete: false, choices: [7, 30, 90, 180, 365], defaultRetentionDays: 30 },
  usage: { bytesUsed: 2048, runFiles: 2, tombstones: 1, entries: 6 },
  limits: { maxBytes: 52428800, maxRunFiles: 4096, maxTombstones: 4096 },
  status: { code: "ready", available: true },
};
const SETTINGS_PREVIEW = { version: 1, previewToken: "dsp1_fixture", retentionDays: 90, autoDelete: true, changed: true, expiresAt: "2026-09-08T15:00:00Z", current: { retentionDays: 30, autoDelete: false }, status: "ready" };
const DELETE_PREVIEW = { version: 1, previewToken: "dpr1_fixture", retentionDays: 30, cutoffAt: "2026-08-09T00:00:00Z", expiresAt: "2026-09-08T15:00:00Z", eligibleCount: 2, eligibleBytes: 1024, oldestCreatedAt: "2026-08-01T00:00:00Z", newestCreatedAt: "2026-08-05T00:00:00Z", excludedCounts: { running: 1, unknown: 0, recovery: 0, privateBlocked: 0, authorityChanged: 0, corrupt: 0, other: 0 }, status: "ready" };

async function json(route: Route, body: unknown, status = 200) { return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }); }

async function install(page: Page, requests: string[], mode: "ready" | "error" | "unavailable" = "ready") {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    requests.push(`${route.request().method()} ${url.pathname}`);
    if (url.pathname === "/api/diagnostics/retention" && route.request().method() === "GET") {
      if (mode === "error") return json(route, { detail: { code: "diagnostics_unavailable" } }, 503);
      return json(route, mode === "unavailable" ? { ...STATUS, status: { code: "writer_conflict", available: false, reason: "writer_conflict" } } : STATUS);
    }
    if (url.pathname === "/api/diagnostics/retention/settings/preview") return json(route, SETTINGS_PREVIEW);
    if (url.pathname === "/api/diagnostics/retention/settings/confirm") return json(route, { version: 1, retentionDays: 90, autoDelete: true, updatedAt: "2026-09-08T14:00:00Z", status: "saved" });
    if (url.pathname === "/api/diagnostics/retention/preview") return json(route, DELETE_PREVIEW);
    if (url.pathname === "/api/diagnostics/retention/confirm") return json(route, { version: 1, retentionDays: 30, deletedCount: 1, deletedBytes: 512, tombstoneCount: 1, oldestCreatedAt: "2026-08-01T00:00:00Z", newestCreatedAt: "2026-08-05T00:00:00Z", status: "partial", skippedCounts: { deleteFailed: 1 } });
    return json(route, { detail: "fixture omitted" }, 404);
  });
}

async function open(page: Page, theme: "light" | "dark", expectStatus = true) {
  await page.addInitScript((selectedTheme) => localStorage.setItem("folio.themePreference.v1", selectedTheme), theme);
  await page.goto(`/?theme=${theme}#/settings`);
  await page.waitForLoadState("networkidle");
  const admin = page.locator('.settings-tabs button').filter({ hasText: "관리" });
  if (await admin.count()) await admin.click();
  await expect(page.locator('[data-qa="diagnostic-retention"]')).toBeVisible();
  if (expectStatus) await expect(page.locator('[data-qa="diagnostic-retention-usage"]')).toBeVisible();
}

for (const mode of [
  { name: "desktop-light", width: 1440, height: 1000, theme: "light" as const },
  { name: "desktop-dark", width: 1440, height: 1000, theme: "dark" as const },
  { name: "mobile-light", width: 375, height: 812, theme: "light" as const },
  { name: "mobile-dark", width: 375, height: 812, theme: "dark" as const },
]) {
  test(`D4 retention ${mode.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: mode.width, height: mode.height });
    const requests: string[] = [];
    await install(page, requests);
    await open(page, mode.theme);
    const accessibility = await new AxeBuilder({ page }).include('[data-qa="diagnostic-retention"]').analyze();
    expect(accessibility.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual([]);
    const retentionPanelLocator = page.locator('[data-qa="diagnostic-retention"]');
    await retentionPanelLocator.scrollIntoViewIfNeeded();
    await retentionPanelLocator.screenshot({ path: testInfo.outputPath(`${mode.name}.png`) });
    const panel = await retentionPanelLocator.boundingBox();
    expect(panel?.width || 0).toBeLessThanOrEqual(mode.width);
  });
}

test("retention settings and deletion require separate preview then confirm", async ({ page }) => {
  const requests: string[] = [];
  await install(page, requests);
  await open(page, "light");
  await page.locator('[data-qa="diagnostic-retention-settings-preview"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-settings-preview-panel"]')).toBeVisible();
  await page.locator('[data-qa="diagnostic-retention-settings-confirm"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-notice"]')).toContainText("보존 설정");
  await page.locator('[data-qa="diagnostic-retention-preview"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-preview-panel"]')).toBeVisible();
  await page.locator('[data-qa="diagnostic-retention-confirm"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-notice"]')).toContainText("일부 정리");
  expect(requests.filter((request) => request.includes("POST /api/diagnostics/retention/settings/confirm")).length).toBe(1);
  expect(requests.filter((request) => request.includes("POST /api/diagnostics/retention/confirm")).length).toBe(1);
});

test("refresh and changed values invalidate retention previews", async ({ page }) => {
  const requests: string[] = [];
  await install(page, requests);
  await open(page, "light");
  await page.locator('[data-qa="diagnostic-retention-settings-preview"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-settings-preview-panel"]')).toBeVisible();
  await page.locator('[data-qa="diagnostic-retention-refresh"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-settings-preview-panel"]')).toHaveCount(0);
  await page.locator('[data-qa="diagnostic-retention-preview"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-preview-panel"]')).toBeVisible();
  await page.locator('[data-qa="diagnostic-retention-settings-preview"]').click();
  await expect(page.locator('[data-qa="diagnostic-retention-preview-panel"]')).toHaveCount(0);
});

test("retention loading error and unavailable states stay honest", async ({ page }) => {
  const requests: string[] = [];
  await install(page, requests, "error");
  await open(page, "light", false);
  await expect(page.locator('[data-qa="diagnostic-retention-error"]')).toBeVisible();
});

test("retention unavailable state disables mutation controls", async ({ page }) => {
  const requests: string[] = [];
  await install(page, requests, "unavailable");
  await open(page, "dark");
  await expect(page.locator('[data-qa="diagnostic-retention-unavailable"]')).toBeVisible();
  await expect(page.locator('[data-qa="diagnostic-retention-preview"]')).toBeDisabled();
  await expect(page.locator('[data-qa="diagnostic-retention-settings-preview"]')).toBeDisabled();
});
