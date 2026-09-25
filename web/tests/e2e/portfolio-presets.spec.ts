import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const initial = [
  { id: "core", name: "장기 핵심", baseCurrency: "USD", revision: 2, weightTotal: 1, updatedAt: "2026-09-04T10:00:00", positions: [{ ticker: "AAPL", name: "Apple", weight: 0.6 }, { ticker: "MSFT", name: "Microsoft", weight: 0.4 }] },
  { id: "legacy", name: "분산 초안", baseCurrency: "KRW", weightTotal: 1, updatedAt: "2026-09-03T10:00:00", positions: [{ ticker: "SPY", name: "S&P 500", weight: 1 }] },
];

async function fixture(page: Page, theme: "light" | "dark", count = 2, thirds = false) {
  let presets: any[] = structuredClone(initial.slice(0, count));
  if (thirds) presets[0].positions = ["AAPL", "MSFT", "SPY"].map(ticker => ({ ticker, weight: 1 / 3 }));
  const calls: { path: string; method: string; body: any }[] = [];
  await page.route("**/*", async route => {
    const req = route.request(); const url = new URL(req.url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const send = (value: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
    const body = req.postData() ? req.postDataJSON() : {};
    calls.push({ path: url.pathname, method: req.method(), body });
    if (url.pathname === "/api/portfolio") return send({ schemaVersion: 3, revision: 4, positions: [], cash: [] });
    if (url.pathname === "/api/portfolio/presets") {
      if (req.method() === "POST") {
        const old = presets.find(p => p.id === body.id);
        if (body.id && (!old || body.expectedRevision !== (old.revision ?? 0))) return send({ detail: { code: "preset_revision_conflict", latest: old ?? null } }, 409);
        const total = body.positions.reduce((sum: number, p: any) => sum + Number(p.weightPercent), 0);
        const saved = { ...body, positions: body.positions.map((p: any) => ({ ticker: p.ticker, weight: Number(p.weightPercent) / (body.normalizeWeights ? total : 100) })), id: body.id || `new-${presets.length}`, revision: (old?.revision ?? 0) + 1, weightTotal: 1, updatedAt: "2026-09-04T11:00:00" };
        presets = [saved, ...presets.filter(p => p.id !== saved.id)]; return send(saved);
      }
      return send(presets.map(p => ({ ...p, revision: p.revision ?? 0 })));
    }
    if (url.pathname === "/api/portfolio/presets/from-current") return send({ name: "현재 포트폴리오 목표 비중", baseCurrency: "USD", positions: [{ ticker: "SPY", weight: 1 }], weightTotal: 1 });
    if (url.pathname.startsWith("/api/portfolio/presets/") && req.method() === "DELETE") {
      const id = decodeURIComponent(url.pathname.split("/").at(-1)!); const old = presets.find(p => p.id === id);
      if (!old || body.expectedRevision !== (old.revision ?? 0)) return send({ detail: { code: "preset_revision_conflict", latest: old ?? null } }, 409);
      presets = presets.filter(p => p.id !== id); return send({ deleted: true, id });
    }
    if (url.pathname === "/api/portfolio/analytics") {
      const selected = presets.find(p => p.id === url.searchParams.get("presetId"));
      return send({ positions: [], analytics: { targetWeights: { items: (selected?.positions || []).map((p: any) => ({ ticker: p.ticker, currentWeight: 0, targetWeight: p.weight, diffWeight: -p.weight, diffAmountUsd: 0 })), hasTargets: true } } });
    }
    return send({ detail: "isolated fixture" }, 404);
  });
  await page.addInitScript(selected => { localStorage.setItem("folio.themePreference.v1", selected); localStorage.setItem("folio.react.agentClosed", "1"); }, theme);
  await page.goto("/#/portfolio", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "프리셋", exact: true }).click();
  await expect(page.getByRole("heading", { name: "프리셋", exact: true })).toBeVisible();
  return { calls, change: (fn: (rows: any[]) => any[]) => { presets = fn(presets); } };
}

const writes = (calls: { path: string; method: string; body: any }[]) => calls.filter(c => c.path === "/api/portfolio/presets" && c.method === "POST");

test("edit same ID, currency and small percentage then reopen", async ({ page }) => {
  const { calls } = await fixture(page, "light");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("핵심 수정");
  await page.getByRole("region", { name: "프리셋 편집기", exact: true }).getByRole("combobox", { name: "기준 통화", exact: true }).selectOption("KRW");
  await page.getByLabel("목표 비중 1", { exact: true }).fill("0.5");
  await page.getByLabel("목표 비중 2", { exact: true }).fill("99.5");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 핵심 수정", exact: true })).toBeVisible();
  expect(writes(calls)[0].body).toMatchObject({ id: "core", expectedRevision: 2, baseCurrency: "KRW", positions: [{ ticker: "AAPL", weightPercent: "0.5" }, { ticker: "MSFT", weightPercent: "99.5" }] });
  await page.getByRole("button", { name: "편집 핵심 수정", exact: true }).click();
  await expect(page.getByLabel("목표 비중 1", { exact: true })).toHaveValue("0.5");
  expect(calls.filter(c => c.path === "/api/portfolio" && c.method !== "GET")).toHaveLength(0);
});

test("new draft validates rows and normalizes only with explicit choice", async ({ page }) => {
  const { calls } = await fixture(page, "light", 0);
  await page.getByRole("button", { name: "새 프리셋", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("새 분산");
  await page.getByRole("button", { name: "종목 추가", exact: true }).click();
  await page.getByLabel("종목 코드 1", { exact: true }).fill("AAPL");
  await page.getByLabel("목표 비중 1", { exact: true }).fill("-1");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByLabel("목표 비중 1", { exact: true })).toHaveAttribute("aria-invalid", "true");
  expect(writes(calls)).toHaveLength(0);
  await page.getByLabel("목표 비중 1", { exact: true }).fill("20");
  await page.getByRole("button", { name: "종목 추가", exact: true }).click();
  await page.getByLabel("종목 코드 2", { exact: true }).fill("AAPL");
  await page.getByLabel("목표 비중 2", { exact: true }).fill("30");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByLabel("종목 코드 2", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await page.getByLabel("종목 코드 2", { exact: true }).fill("MSFT");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  expect(writes(calls)).toHaveLength(0);
  await page.getByLabel("합계를 100%로 정규화하여 저장", { exact: true }).check();
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 새 분산", exact: true })).toBeVisible();
  expect(writes(calls)[0].body.id).toBeUndefined();
  expect(writes(calls)[0].body.normalizeWeights).toBe(true);
});

test("clone and save as preserve source and require explicit save", async ({ page }) => {
  const { calls } = await fixture(page, "dark");
  await page.getByRole("button", { name: "복제 장기 핵심", exact: true }).click();
  expect(writes(calls)).toHaveLength(0);
  await page.getByLabel("프리셋 이름", { exact: true }).fill("복제본");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 복제본", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("다른 이름");
  await page.getByRole("button", { name: "다른 이름으로 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 다른 이름", exact: true })).toBeVisible();
  expect(writes(calls)).toHaveLength(2);
  expect(writes(calls).every(c => !c.body.id && c.body.expectedRevision === undefined)).toBe(true);
  await expect(page.getByRole("button", { name: "편집 장기 핵심", exact: true })).toBeVisible();
});

test("dirty guard keeps draft on preset switch, cancel and tab exit", async ({ page }) => {
  const { calls } = await fixture(page, "light");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("저장 안 한 입력");
  for (const name of ["편집 분산 초안", "취소", "백테스트"]) {
    let shown = false;
    page.once("dialog", async dialog => { shown = true; await dialog.dismiss(); });
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("저장 안 한 입력");
    expect(shown).toBe(true);
  }
  expect(writes(calls)).toHaveLength(0);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "백테스트", exact: true }).click();
  await expect(page.getByRole("heading", { name: "백테스트", exact: true })).toBeVisible();
});

test("conflict retains draft until explicit latest reload", async ({ page }) => {
  const { calls, change } = await fixture(page, "light");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("내 수정");
  change(rows => rows.map(p => p.id === "core" ? { ...p, revision: 3, name: "다른 탭 수정" } : p));
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "최신 저장본 불러오기", exact: true })).toBeVisible();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("내 수정");
  expect(writes(calls)[0].body.expectedRevision).toBe(2);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "최신 저장본 불러오기", exact: true }).click();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("다른 탭 수정");
});

test("current holdings is unsaved draft and legacy save uses revision zero", async ({ page }) => {
  const { calls } = await fixture(page, "dark");
  await page.getByRole("button", { name: "현재 보유에서 초안 만들기", exact: true }).click();
  await expect(page.getByLabel("종목 코드 1", { exact: true })).toHaveValue("SPY");
  expect(writes(calls)).toHaveLength(0);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "편집 분산 초안", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("이전 프리셋 수정");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 이전 프리셋 수정", exact: true })).toBeVisible();
  expect(writes(calls)[0].body).toMatchObject({ id: "legacy", expectedRevision: 0 });
});

test("server validation and transport failure keep editable draft", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("보존할 입력");
  let mode = "validation";
  await page.route("**/api/portfolio/presets", async route => {
    if (route.request().method() !== "POST") return route.fallback();
    if (mode === "network") return route.abort();
    return route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: { code: "preset_validation_failed", errors: [{ row: 0, field: "ticker", code: "duplicate_ticker", message: "같은 종목은 한 번만 넣을 수 있습니다." }] } }) });
  });
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByLabel("종목 코드 1", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("보존할 입력");
  mode = "network";
  await page.getByLabel("종목 코드 1", { exact: true }).fill("GOOGL");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("보존할 입력");
  await expect(page.getByRole("button", { name: "프리셋 저장", exact: true })).toBeEnabled();
});

test("deleted elsewhere never recreates on ordinary save", async ({ page }) => {
  const { calls, change } = await fixture(page, "dark");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("삭제 전 입력");
  change(rows => rows.filter(p => p.id !== "core"));
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("alert").first()).toBeVisible();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("삭제 전 입력");
  expect(writes(calls)[0].body.id).toBe("core");
  await page.getByRole("button", { name: "다른 이름으로 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 삭제 전 입력", exact: true })).toBeVisible();
  expect(writes(calls)[1].body.id).toBeUndefined();
});

test("global navigation preserves the mounted preset draft on return", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("떠나기 전 입력");
  let dialogs = 0;
  page.on("dialog", dialog => { dialogs += 1; return dialog.dismiss(); });
  await page.getByRole("button", { name: "홈", exact: true }).click();
  await expect(page).toHaveURL(/#\/home$/);
  await page.getByRole("button", { name: "포트폴리오", exact: true }).click();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue("떠나기 전 입력");
  await expect(page).toHaveURL(/#\/portfolio$/);
  expect(dialogs).toBe(0);
  page.removeAllListeners("dialog");
});

test("populated clone draft warns before subtab exit without manual edits", async ({ page }) => {
  await fixture(page, "light");
  await page.getByRole("button", { name: "복제 장기 핵심", exact: true }).click();
  const original = await page.getByLabel("프리셋 이름", { exact: true }).inputValue();
  let shown = false;
  page.once("dialog", async dialog => { shown = true; await dialog.dismiss(); });
  await page.getByRole("button", { name: "백테스트", exact: true }).click();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toHaveValue(original);
  expect(shown).toBe(true);
});

test("delete confirms, preserves unrelated draft on cancel and sends latest revision", async ({ page }) => {
  const { calls } = await fixture(page, "dark");
  page.once("dialog", dialog => dialog.dismiss());
  await page.getByRole("button", { name: "삭제 장기 핵심", exact: true }).click();
  expect(calls.filter(c => c.method === "DELETE")).toHaveLength(0);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "삭제 장기 핵심", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 장기 핵심", exact: true })).toHaveCount(0);
  expect(calls.find(c => c.method === "DELETE")?.body.expectedRevision).toBe(2);
  await expect(page.getByRole("button", { name: "편집 분산 초안", exact: true })).toBeVisible();
});

test("saving blocks duplicate submission and edits until response", async ({ page }) => {
  const { calls } = await fixture(page, "light");
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("저장 중 입력 보호");
  let resume: () => void = () => {};
  const held = new Promise<void>(resolve => { resume = resolve; });
  await page.route("**/api/portfolio/presets", async route => {
    if (route.request().method() === "POST") await held;
    await route.fallback();
  });
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByLabel("프리셋 이름", { exact: true })).toBeDisabled();
  await expect(page.getByLabel("목표 비중 1", { exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "저장 중", exact: true })).toBeDisabled();
  resume();
  await expect(page.getByRole("button", { name: "편집 저장 중 입력 보호", exact: true })).toBeVisible();
  expect(writes(calls)).toHaveLength(1);
});

test("saved thirds can be renamed without another normalization", async ({ page }) => {
  const { calls } = await fixture(page, "light", 2, true);
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("프리셋 이름", { exact: true }).fill("삼등분 이름 수정");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 삼등분 이름 수정", exact: true })).toBeVisible();
  expect(writes(calls)[0].body.normalizeWeights).not.toBe(true);
});

test("saving selected preset refreshes the current holdings comparison", async ({ page }) => {
  await fixture(page, "dark");
  const comparison = page.getByRole("table").first();
  await expect(comparison.getByText("60.0%", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  await page.getByLabel("목표 비중 1", { exact: true }).fill("10");
  await page.getByLabel("목표 비중 2", { exact: true }).fill("90");
  await page.getByRole("button", { name: "프리셋 저장", exact: true }).click();
  await expect(comparison.getByText("10.0%", { exact: true })).toBeVisible();
});

test("editor fits a small phone and landscape without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await fixture(page, "light", 1);
  await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
  for (const viewport of [{ width: 375, height: 812 }, { width: 812, height: 375 }]) {
    await page.setViewportSize(viewport);
    await expect(page.getByLabel("목표 비중 1", { exact: true })).toBeVisible();
    const overflow = await page.locator(".portfolio-preset-editor").evaluate(el => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  }
});

for (const theme of ["light", "dark"] as const) {
  test(`preset captures ${theme}`, async ({ page }, info) => {
    await fixture(page, theme);
    await expect(page.getByText("장기 핵심", { exact: true }).first()).toBeVisible();
    await page.screenshot({ path: `../.planning/portfolio-u-presets/${process.env.U2_BASELINE ? "before" : "after"}-${info.project.name.includes("mobile") ? "mobile" : "desktop"}-${theme}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    if (!process.env.U2_BASELINE) {
      await page.getByRole("button", { name: "편집 장기 핵심", exact: true }).click();
      await expect(page.getByLabel("목표 비중 1", { exact: true })).toBeVisible();
      await page.getByLabel("프리셋 이름", { exact: true }).fill("핵심 비중 검토");
      await page.screenshot({ path: `../.planning/portfolio-u-presets/editor-${info.project.name.includes("mobile") ? "mobile" : "desktop"}-${theme}.png`, fullPage: true });
      await page.locator(".portfolio-preset-editor").screenshot({ path: `../.planning/portfolio-u-presets/editor-detail-${info.project.name.includes("mobile") ? "mobile" : "desktop"}-${theme}.png` });
      await page.getByRole("button", { name: "다른 이름으로 저장", exact: true }).focus();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "프리셋 저장", exact: true })).toBeFocused();
      expect(await page.getByRole("button", { name: "프리셋 저장", exact: true }).evaluate(el => getComputedStyle(el).outlineStyle)).not.toBe("none");
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      const results = await new AxeBuilder({ page }).include(".portfolio-targets").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      expect(results.violations.filter(v => ["serious", "critical"].includes(v.impact || ""))).toEqual([]);
      if (info.project.name.includes("mobile")) {
        for (const label of ["프리셋 이름", "기준 통화", "종목 코드 1", "목표 비중 1"]) {
          const box = await (label === "기준 통화" ? page.getByRole("region", { name: "프리셋 편집기", exact: true }).getByRole("combobox", { name: label, exact: true }) : page.getByLabel(label, { exact: true })).boundingBox();
          expect(box!.height).toBeGreaterThanOrEqual(44);
          expect(box!.width).toBeGreaterThan(100);
        }
        expect((await page.getByRole("button", { name: "프리셋 저장", exact: true }).boundingBox())!.height).toBeGreaterThanOrEqual(44);
      }
    }
  });
}
