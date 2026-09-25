import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

for (const theme of ["light", "dark"]) {
  test(`Welcome offers CLI or no AI without changing untouched legacy settings (${theme})`, async ({ page }, testInfo) => {
    const writes: unknown[] = [];
    await page.addInitScript(theme => localStorage.setItem("folio.themePreference.v1", theme), theme);
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      let body: unknown = {};
      if (path === "/api/onboarding") body = { firstRun: true, completed: false, reason: "fresh" };
      if (path === "/api/settings") {
        if (route.request().method() === "POST") writes.push(route.request().postDataJSON());
        body = { agent: { enabled: true, mode: "api" } };
      }
      if (path === "/api/market-scope") body = { selected: ["US"], markets: [{ id: "US", label: "미국" }] };
      if (path === "/api/agent-bridge/settings") body = { adapters: [] };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto("/#settings");
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "다음", exact: true }).click();
    await dialog.getByRole("button", { name: "다음", exact: true }).click();
    await expect(dialog.getByRole("heading", { name: "AI를 쓰시겠어요?" })).toBeVisible();
    await expect(dialog.getByRole("group", { name: "생성 방식" }).getByRole("button")).toHaveCount(2);
    await expect(dialog.locator('input[type="password"]')).toHaveCount(0);
    await dialog.getByRole("button", { name: "저장하고 다음" }).click();
    expect(writes).toEqual([]);
    await dialog.getByRole("button", { name: "이전", exact: true }).click();
    await dialog.getByRole("button", { name: "CLI", exact: true }).click();
    await expect(dialog.getByText("내 컴퓨터에 설치해서 쓰는 AI 프로그램", { exact: true })).toBeVisible();
    expect((await new AxeBuilder({ page }).include('.welcome-shell').analyze()).violations.filter(v => ["critical", "serious"].includes(v.impact || ""))).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`welcome-cli-${theme}.png`), fullPage: true });
    expect(await dialog.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(false);
    await dialog.getByRole("button", { name: "AI 없이", exact: true }).click();
    await dialog.getByRole("button", { name: "저장하고 다음" }).click();
    expect(writes).toEqual([{ agent: { enabled: false, mode: "cli" } }]);
  });

  test(`CLI transition settings preserve data integrations (${theme})`, async ({ page }, testInfo) => {
    let saved: Record<string, unknown> | null = null;
    let mode = "api";
    const providerRequests: string[] = [];
    await page.addInitScript((theme) => {
      localStorage.setItem("folio.themePreference.v1", theme);
      document.documentElement.dataset.theme = theme;
    }, theme);
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const path = url.pathname;
      if (path.includes("/settings/llm/")) providerRequests.push(path);
      let body: unknown = {};
      if (path === "/api/onboarding") body = { required: false, completed: true };
      if (path === "/api/settings") {
        if (route.request().method() === "POST") {
          saved = route.request().postDataJSON();
          mode = "cli";
        }
        body = { agent: { enabled: true, mode }, llm: { reasoningEffort: "provider_default" },
          taskPolicies: { schemaVersion: 1, revision: 3, tasks: { company_analysis: {
            enabled: true, config: { mode: "api", provider: "openai", model: "old-model", reasoningEffort: "medium" },
          } } }, fred: {}, bok: {}, dart: {}, notion: {}, toss: { enabled: false } };
      }
      if (path === "/api/agent-bridge/settings") body = { provider: "codex", selectedAdapter: "codex", adapters: [{
        id: "codex", label: "Codex CLI", installed: true, available: true, authenticated: true, bridgeSupported: true,
        model: "gpt-6-sol", modelChoices: [{ value: "gpt-6-sol", label: "GPT-6 Sol" }],
      }] };
      if (path === "/api/automation/settings") body = { rss: { enabled: false }, marketMemory: { enabled: false }, briefingSchedules: [] };
      if (path === "/api/market-scope") body = { selected: ["us"], markets: [{ id: "us", label: "미국" }] };
      if (path === "/api/automation/runs") body = { items: [] };
      if (path === "/api/agent/work-log") body = { entries: [], total: 0 };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto("/#settings");
    await expect(page.getByRole("heading", { name: "AI Agent 연동", exact: true })).toBeVisible();
    await expect(page.getByText(/LLM API 지원이 종료되었습니다/)).toBeVisible();
    await expect(page.getByRole("button", { name: "LLM API", exact: true })).toHaveCount(0);
    await expect(page.locator('[data-qa="agent-integration-settings"] input[type="password"]')).toHaveCount(0);
    await expect(page.getByText("이전 API 설정 · CLI 전환 필요", { exact: true })).toBeVisible();
    const row = page.locator(".task-policy-row").filter({ has: page.getByText("기업분석", { exact: true }) });
    await page.getByRole("combobox", { name: "실행 방식", exact: true }).selectOption("cli");
    await expect(row.getByText("이전 API 설정 · CLI 전환 필요", { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "AI Agent 연동 저장", exact: true }).click();
    await expect.poll(() => saved).toEqual({ agent: { enabled: true, mode: "cli" } });
    await expect(page.getByText(/LLM API 지원이 종료되었습니다/)).toHaveCount(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    expect(overflow).toBe(false);
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement !== document.body)).toBe(true);
    const axe = await new AxeBuilder({ page }).include('[data-settings-route]').analyze();
    expect(axe.violations.filter(v => ["critical", "serious"].includes(v.impact || ""))).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`cli-settings-${theme}.png`), fullPage: true });
    await page.getByRole("button", { name: "연동", exact: true }).click();
    await expect(page.getByText("FRED API Key", { exact: true })).toBeVisible();
    await expect(page.getByText("DART API Key", { exact: true })).toBeVisible();
    expect(providerRequests).toEqual([]);
  });
}
