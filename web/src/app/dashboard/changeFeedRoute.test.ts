import { describe, expect, it } from "vitest";
import { changeEventRoute } from "./ChangeFeed";

describe("changeEventRoute", () => {
  it("시장이 붙은 브리핑 id는 그 시장 브리핑을 연다", () => {
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "2026-08-04.us" })).toBe("#/briefing/2026-08-04/us/daily");
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "2026-08-04.kr" })).toBe("#/briefing/2026-08-04/kr/daily");
  });

  it("시장이 없는 예전 이벤트는 lineage에서 시장을 읽는다", () => {
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "2026-08-04", lineageId: "briefing:us" }))
      .toBe("#/briefing/2026-08-04/us/daily");
  });

  it("시장을 알 수 없을 때만 종합 브리핑으로 간다", () => {
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "2026-08-04", lineageId: "briefing:both" }))
      .toBe("#/briefing/2026-08-04/both/daily");
  });

  it("날짜가 아니면 브리핑 목록으로 간다", () => {
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "draft" })).toBe("#/briefing");
  });

  it("다른 산출물은 각자의 화면으로 간다", () => {
    expect(changeEventRoute({ artifactKind: "company_analysis", artifactId: "NVDA:2026-08-04" })).toBe("#/analysis");
    expect(changeEventRoute({ artifactKind: "topic_report", artifactId: "t1" })).toBe("#/deep-research");
    expect(changeEventRoute({ artifactKind: "market_memory", artifactId: "mss_1" })).toBe("#/market-memory");
  });
});

describe("changeEventRoute — 주간", () => {
  it("주간 변화 이벤트는 주간 보고서를 연다", () => {
    // 종류가 없으면 같은 날 일간이 열린다 — 두 보고서가 나란히 저장되기 때문이다.
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "2026-08-23.us.weekly" }))
      .toBe("#/briefing/2026-08-23/us/weekly");
  });

  it("종류 접미사가 시장 판정을 가리지 않는다", () => {
    // `endsWith(".us")`로만 보면 `.weekly`로 끝나는 id는 시장을 못 찾아 통합 뷰로 떨어졌다.
    expect(changeEventRoute({ artifactKind: "briefing", artifactId: "2026-08-23.kr.weekly" }))
      .toBe("#/briefing/2026-08-23/kr/weekly");
  });

  it("주간 계보에서도 시장과 종류를 읽는다", () => {
    expect(changeEventRoute({
      artifactKind: "briefing", artifactId: "2026-08-23", lineageId: "briefing:europe:weekly",
    })).toBe("#/briefing/2026-08-23/europe/weekly");
  });
});
