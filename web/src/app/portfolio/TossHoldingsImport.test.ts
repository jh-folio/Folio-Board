import { describe, expect, it } from "vitest";
import { draftAllowsImport, importIssueCopy, importStatusCopy, isBlockingPreview } from "./TossHoldingsImport";
import type { TossImportPreview } from "../../api";

const preview = (patch: Partial<TossImportPreview> = {}): TossImportPreview => ({
  previewId: "opaque", expectedRevision: 4, canConfirm: true, status: "ready", provider: "toss_open_api", openApiVersion: "1.2.14",
  buckets: { additions: ["US:USD:AAPL"], updates: [], preservedManual: [], unchanged: [], conflicts: [], unsupported: [] },
  details: [],
  ...patch,
});

describe("Toss holdings import UI contract", () => {
  it("keeps provider failures bounded and explains manual fallback", () => {
    expect(importStatusCopy("credentials_missing")).toContain("수동 Portfolio");
    expect(importStatusCopy("provider_contract_invalid")).toContain("응답 형식");
    expect(importStatusCopy("unknown_provider_internal_code")).not.toContain("unknown_provider_internal_code");
  });

  it("only enables confirmation for a non-blocking server preview", () => {
    expect(isBlockingPreview(preview())).toBe(false);
    expect(isBlockingPreview(preview({ canConfirm: false }))).toBe(true);
    expect(isBlockingPreview(preview({ buckets: { ...preview().buckets, conflicts: [{ positionKey: "US:USD:AAPL", issueCodes: ["duplicate"] }] } }))).toBe(true);
    expect(isBlockingPreview(null)).toBe(true);
  });

  it("projects provider issue codes to bounded Korean copy", () => {
    expect(importIssueCopy("precision_unsupported")).toContain("정확하게");
    expect(importIssueCopy("provider_private_stack_trace")).not.toContain("provider_private_stack_trace");
    expect(importStatusCopy("draft_unsaved")).toContain("저장");
    expect(draftAllowsImport(false)).toBe(true);
    expect(draftAllowsImport(true)).toBe(false);
  });
});
