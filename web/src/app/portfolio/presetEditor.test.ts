import { describe, expect, it } from "vitest";
import { blankPresetDraft, clonePresetDraft, draftFromPreset, presetSavePayload, validatePresetDraft } from "./presetEditor";
import type { Preset } from "./portfolioTypes";

const preset = (overrides: Partial<Preset> = {}): Preset => ({
  id: "core", revision: 3, name: "핵심", baseCurrency: "USD",
  positions: [{ ticker: "AAPL", weight: 0.5 }, { ticker: "MSFT", weight: 0.005 }],
  weightTotal: 0.505, updatedAt: "2026-09-04T00:00:00Z", ...overrides,
});

describe("preset editor percentage contract", () => {
  it("reads fractional weights as human percentage strings without float artefacts", () => {
    const draft = draftFromPreset(preset({ positions: [{ ticker: "SMALL", weight: 0.0000001 }, { ticker: "THIRD", weight: 1 / 3 }] }));
    expect(draft.rows.map((row) => row.weightPercent)).toEqual(["0.00001", "33.33333333333333"]);
  });

  it("writes only explicit percentage strings and retains per-preset CAS on an update", () => {
    const payload = presetSavePayload(draftFromPreset(preset()));
    expect(payload).toEqual({ id: "core", expectedRevision: 3, name: "핵심", baseCurrency: "USD", positions: [{ ticker: "AAPL", weightPercent: "50" }, { ticker: "MSFT", weightPercent: "0.5" }] });
    expect(JSON.stringify(payload)).not.toContain('"weight"');
  });

  it("keeps clone/save-as id-free and requires explicit normalization for a non-100 total", () => {
    const clone = clonePresetDraft(preset());
    expect(presetSavePayload(clone)).not.toHaveProperty("id");
    const invalid = validatePresetDraft({ ...blankPresetDraft(), name: "초안", rows: [{ key: "one", ticker: "AAPL", weightPercent: "80" }] });
    expect(invalid.errors.total).toContain("100%");
    const normalized = validatePresetDraft({ ...blankPresetDraft(), name: "초안", normalizeWeights: true, rows: [{ key: "one", ticker: "AAPL", weightPercent: "80" }] });
    expect(normalized.valid).toBe(true);
  });

  it("accepts fractional API thirds within the server's percentage tolerance without normalization", () => {
    const result = validatePresetDraft({
      ...blankPresetDraft(),
      name: "3등분",
      rows: ["one", "two", "three"].map((key) => ({ key, ticker: `T${key}`, weightPercent: "33.33333333333333" })),
    });
    expect(result.total).toBe("99.99999999999999");
    expect(result.valid).toBe(true);
    expect(result.errors.total).toBeUndefined();
  });

  it("detects equivalent ticker aliases before submit", () => {
    const result = validatePresetDraft({ ...blankPresetDraft(), name: "중복", rows: [{ key: "one", ticker: "BRK.B", weightPercent: "50" }, { key: "two", ticker: "BRK-B", weightPercent: "50" }] });
    expect(result.errors["row-1-ticker"]).toContain("같은 종목");
  });
});
