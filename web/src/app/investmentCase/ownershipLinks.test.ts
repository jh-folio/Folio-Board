import { describe, expect, it } from "vitest";
import { portfolioReturn } from "./ownershipTypes";

const route = (value: string) => `#/watchlist/ABC?${new URLSearchParams({ returnHash: value })}`;

describe("portfolio return route", () => {
  it("preserves the selected review and all encoded filter values on an owned route", () => {
    const query = new URLSearchParams({ tab: "review", date: "2026-09-20", filter: "검토 & 확인", selected: "US:ABC", next: "javascript:alert(1)" });
    const result = portfolioReturn(route(`#/portfolio?${query}`));
    expect(result).toBe(`#/portfolio?${query}`);
    const target = new URL(result!, "https://folio.example/");
    expect(target.origin).toBe("https://folio.example");
    expect(target.pathname).toBe("/");
    expect(target.hash.startsWith("#/portfolio?")).toBe(true);
  });

  it("supports the bare portfolio route and the legacy review return", () => {
    expect(portfolioReturn(route("#/portfolio"))).toBe("#/portfolio");
    expect(portfolioReturn("#/watchlist/ABC?returnTo=review&reviewDate=2026-10-01")).toBe("#/portfolio?tab=review&date=2026-10-01");
    expect(portfolioReturn("#/watchlist/ABC?tab=ownership")).toBeNull();
  });

  it.each(["javascript:alert(1)", "https://example.invalid/", "//example.invalid/", "#/portfolio/other", "#/portfoliophish", "#/portfolio#other", "#/portfolio?date=one\r\nnext=two"])("rejects a noncanonical return target: %s", value => {
    expect(portfolioReturn(route(value))).toBeNull();
  });
});
