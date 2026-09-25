import { describe, expect, it } from "vitest";
import { isOverdue, safeReportRoute, sortReviewPositions } from "./investmentReviewUi";

describe("investment review UI projections", () => {
  it("keeps date-only deadlines open through their Korea calendar day", () => {
    expect(isOverdue("2026-09-04", "2026-09-04T14:59:59Z")).toBe(false); // 23:59:59 KST
    expect(isOverdue("2026-09-04", "2026-09-04T15:00:00Z")).toBe(true); // next KST day
    expect(isOverdue("2026-09-04T01:00:00Z", "2026-09-04T01:00:01Z")).toBe(true);
    expect(isOverdue("2026-09-04T10:00:00", "2026-09-04T10:00:00")).toBe(true); // timezone-less = KST, inclusive
  });

  it("orders display-only review attention before normal positions", () => {
    expect(sortReviewPositions([
      { ticker: "Z", thesisVerdict: "maintained" },
      { ticker: "M", thesisVerdict: "weakened" },
      { ticker: "A", thesisVerdict: "broken" },
      { ticker: "N", thesisVerdict: "insufficient_evidence", thesisPresent: false },
    ], "2026-09-05T00:00:00Z").map((row) => row.ticker)).toEqual(["A", "M", "N", "Z"]);
  });

  it("accepts only known internal report routes", () => {
    expect(safeReportRoute({ kind: "briefing", id: "2026-09-04.us", marketScope: "us", reportKind: "weekly" })).toBe("#/briefing/2026-09-04/us/weekly");
    expect(safeReportRoute({ kind: "briefing", id: "2026-09-04.us.weekly", marketScope: "us" })).toBe("#/briefing/2026-09-04/us/weekly");
    expect(safeReportRoute({ kind: "briefing", id: "2026-09-04.untrusted" })).toBe("");
    expect(safeReportRoute({ kind: "company_analysis", id: "NVDA:2026-09-04" })).toBe("#/analysis/NVDA%3A2026-09-04");
    expect(safeReportRoute({ kind: "topic_report", id: "topic-1" })).toBe("#/deep-research/topic-1");
    expect(safeReportRoute({ kind: "unknown", id: "https://example.invalid" })).toBe("");
  });
});
