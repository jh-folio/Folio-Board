import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "line",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:4173",
    locale: "ko-KR",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [{
    command: "python -m http.server 4173 --bind 127.0.0.1 --directory ../public",
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  }, ...(process.env.CASE_TEST_URL ? [] : [{
    command: "python -m uvicorn features.investment_case.tests.browser_server:app --host 127.0.0.1 --port 18789 --log-level warning",
    cwd: "..",
    port: 18789,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  }])],
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 7"] },
    },
  ],
});
