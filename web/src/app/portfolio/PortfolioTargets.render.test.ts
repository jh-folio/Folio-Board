import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PortfolioTargets } from "./PortfolioTargets";

describe("PortfolioTargets initial render", () => {
  it("offers accessible first actions while the preset list loads", () => {
    const html = renderToStaticMarkup(createElement(PortfolioTargets, { revision: 0 }));
    expect(html).toContain("프리셋 만들기");
    expect(html).toContain("새 프리셋");
    expect(html).toContain("현재 보유에서 초안 만들기");
    expect(html).toContain('role="status"');
  });
});
