import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PUBLIC_ROUTES = [
  "home",
  "dashboard",
  "watchlist",
  // 0.4에서 공개로 복귀한 화면. 목록에서 빠져 있어 axe 검사도 모바일 오버플로
  // 게이트도 한 번도 이 화면을 보지 않았다.
  "portfolio",
  "briefing",
  "rss",
  "market-memory",
  "analysis",
  "deep-research",
  "settings",
] as const;

const preparedPages = new WeakSet<Page>();

async function openRoute(page: Page, route: string, theme: "light" | "dark" = "light") {
  if (!preparedPages.has(page)) {
    await page.route("**/*", async (requestRoute) => {
      const url = new URL(requestRoute.request().url());
      if (url.hostname !== "127.0.0.1") {
        await requestRoute.abort();
      } else if (url.pathname.startsWith("/api/")) {
        await requestRoute.fulfill({
          status: 404,
          contentType: "application/json",
          body: '{"detail":"UI quality fixture"}',
        });
      } else {
        await requestRoute.continue();
      }
    });
    await page.addInitScript((selectedTheme) => {
      if (!localStorage.getItem("folio.themePreference.v1")) {
        localStorage.setItem("folio.themePreference.v1", selectedTheme);
      }
      if (!window.matchMedia("(max-width: 1024px)").matches && localStorage.getItem("folio.react.agentClosed") === null) {
        localStorage.setItem("folio.react.agentClosed", "1");
      }
    }, theme);
    preparedPages.add(page);
  }
  await page.goto(`/#/${route}`, { waitUntil: "domcontentloaded" });
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-delay: 0s !important;
        animation-duration: 0s !important;
        transition-delay: 0s !important;
        transition-duration: 0s !important;
      }
    `,
  });
  await expect(page.locator(`.react-route-host[data-route="${route}"]`)).toBeVisible();
  await expect.poll(() => page.locator(".react-shell").evaluate((element) => getComputedStyle(element).opacity)).toBe("1");
}

test.describe("public workspace quality gate", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`all public routes meet serious WCAG checks in ${theme} mode`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name.includes("mobile"), "Desktop performs the full axe route sweep.");
      for (const route of PUBLIC_ROUTES) {
        await openRoute(page, route, theme);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
          .analyze();
        const blocking = results.violations.filter((violation) =>
          violation.impact === "serious" || violation.impact === "critical"
        );
        expect(blocking, `${route} (${theme}): ${blocking.map((item) => item.id).join(", ")}`).toEqual([]);
      }
    });
  }

  test("Dashboard and Watchlist are public and legacy Pixel Office hashes return Home", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Navigation contract is covered once on desktop.");
    await openRoute(page, "dashboard");
    await expect(page.getByRole("button", { name: "대시보드" })).toBeVisible();
    await expect(page.getByRole("button", { name: "워치리스트" })).toBeVisible();
    await page.goto("/#/office", { waitUntil: "domcontentloaded" });
    await expect(page.locator('.react-route-host[data-route="home"]')).toBeVisible();
    await expect(page).toHaveURL(/#\/home$/);
  });

  test("theme selection persists and updates the resolved document theme", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Settings interaction is covered once on desktop.");
    await openRoute(page, "settings");
    // `exact`가 없으면 상단바 전환 버튼의 접근성 이름("…누르면 다크")까지 걸린다.
    await page.getByRole("button", { name: "다크", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByRole("button", { name: "다크", exact: true })).toHaveAttribute("aria-pressed", "true");
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  test("the top bar theme menu opens, applies, and agrees with the settings panel", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Settings interaction is covered once on desktop.");
    // 테마는 하루에도 여러 번 바꾸는 설정인데 설정 화면을 열어야만 닿았다. 상단바 메뉴는
    // 같은 저장소를 쓰므로 두 화면이 갈라지면 안 된다.
    await openRoute(page, "settings");
    await page.getByRole("button", { name: "라이트", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

    const trigger = page.getByRole("button", { name: /^화면 테마:/ });
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await trigger.click();
    const menu = page.getByRole("menu", { name: "화면 테마" });
    await expect(menu).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-expanded", "true");
    // 지금 값이 무엇인지 목록 안에서 읽힌다.
    await expect(menu.getByRole("menuitemradio", { name: "라이트" })).toHaveAttribute("aria-checked", "true");

    await menu.getByRole("menuitemradio", { name: "다크" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(menu).toBeHidden();
    // 설정 화면의 세 버튼이 같은 값을 가리킨다.
    await expect(page.getByRole("button", { name: "다크", exact: true })).toHaveAttribute("aria-pressed", "true");

    // Escape로 닫고 포커스가 트리거로 돌아온다.
    await trigger.click();
    await expect(page.getByRole("menu", { name: "화면 테마" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu", { name: "화면 테마" })).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("keyboard users can skip directly to the active route", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Keyboard contract is desktop-specific.");
    await openRoute(page, "briefing");
    await page.keyboard.press("Tab");
    const skipLink = page.getByRole("link", { name: "본문으로 건너뛰기" });
    await expect(skipLink).toBeFocused();
    await skipLink.press("Enter");
    await expect(page.locator(".react-route-host")).toBeFocused();
  });

  test("command palette traps focus and restores it when dismissed", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name.includes("mobile"), "Keyboard contract is desktop-specific.");
    await openRoute(page, "home");
    const trigger = page.getByRole("button", { name: "대시보드", exact: true });
    await trigger.focus();
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: "명령 팔레트" });
    const input = dialog.getByRole("textbox", { name: "명령 검색" });
    await expect(input).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.locator("button").last()).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(input).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("mobile public routes do not overflow the viewport and keep Agent collapsed", async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.includes("mobile"), "Mobile layout contract runs on the mobile project.");
    for (const route of PUBLIC_ROUTES) {
      await openRoute(page, route, "dark");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${route} horizontal overflow`).toBeLessThanOrEqual(1);
      if (route !== "home") {
        await expect(page.locator(".react-agent-dock")).toHaveClass(/is-closed/);
      }
    }
  });
});
