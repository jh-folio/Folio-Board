import { describe, expect, it } from "vitest";
import { transitionLabel } from "./verification";

describe("verification timeline display labels", () => {
  it("localizes narrative status transitions", () => {
    expect(transitionLabel("status", "overridden")).toBe("대체됨");
    expect(transitionLabel("status", "unexpected")).toBe("상태 정보 없음");
  });

  it("formats evidence-count JSON without leaking raw storage", () => {
    expect(transitionLabel("evidence_count", '{"d7":1,"d30":4,"d90":9}')).toBe("7일 1 · 30일 4 · 90일 9");
    expect(transitionLabel("evidence_count", "not-json")).toBe("근거 수 정보 없음");
  });
});
