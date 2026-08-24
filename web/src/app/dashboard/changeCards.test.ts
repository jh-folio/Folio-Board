import { describe, expect, it } from "vitest";
import type { ChangeEvent } from "../changeEvents";
import { agentQuestionForEvent, baselineRoute, primaryChangedItem } from "./ChangeFeed";

const EVENT: ChangeEvent = {
  artifactKind: "briefing",
  artifactId: "2026-08-04.us",
  lineageId: "briefing:us",
  status: "major_change",
  baselineRef: { id: "2026-08-01.us" },
  changedItems: [
    {
      id: "metric", kind: "market_metric", subject: "^GSPC", change: "changed",
      previousValue: 6388.64, currentValue: 6401.2,
    },
    {
      id: "semis", kind: "market_driver", subject: "반도체/AI", change: "changed",
      previousValue: { rank: 3, share: 0.18 }, currentValue: { rank: 1, share: 0.31 },
      semanticVerdict: "new_information",
      semanticNote: "화웨이 어센드 투자 확대로 경쟁 변수가 추가됐습니다.",
      previousContextDocs: ["엔비디아 실적 기대"], contextDocs: ["화웨이 어센드 AI 칩 투자 확대"],
    },
  ],
};

describe("primaryChangedItem", () => {
  it("의미 verdict가 강한 항목이 첫 항목보다 우선한다", () => {
    expect(primaryChangedItem(EVENT)?.subject).toBe("반도체/AI");
  });

  it("verdict가 없으면 첫 항목이다", () => {
    const bare: ChangeEvent = { changedItems: [{ subject: "금리", kind: "market_driver" }] };
    expect(primaryChangedItem(bare)?.subject).toBe("금리");
  });
});

describe("baselineRoute", () => {
  it("기준 브리핑을 그 시장으로 연다", () => {
    // 경로에 종류가 들어간다(0.5.4). 같은 날 일간과 주간이 나란히 저장되므로
    // 종류 없이는 어느 쪽을 열지 정할 수 없다.
    expect(baselineRoute(EVENT)).toBe("#/briefing/2026-08-01/us/daily");
  });

  it("기준이 없으면 빈 문자열", () => {
    expect(baselineRoute({ artifactKind: "briefing" })).toBe("");
  });

  it("브리핑이 아니면 빈 문자열", () => {
    expect(baselineRoute({ artifactKind: "company_analysis", baselineRef: { id: "NVDA:2026-08-01" } })).toBe("");
  });
});

describe("agentQuestionForEvent", () => {
  it("카드가 아는 사실(전/후·분류·근거 제목·기준)을 전부 담는다", () => {
    const question = agentQuestionForEvent(EVENT);
    expect(question).toContain("반도체/AI");
    expect(question).toContain("3순위 · 비중 18% → 1순위 · 비중 31%");
    expect(question).toContain("의미 분류: 새 정보");
    expect(question).toContain("직전: 엔비디아 실적 기대");
    expect(question).toContain("현재: 화웨이 어센드 AI 칩 투자 확대");
    expect(question).toContain("비교 기준: 2026-08-01.us");
  });

  it("없는 사실은 지어내지 않는다", () => {
    const question = agentQuestionForEvent({ artifactKind: "briefing", changedItems: [{ subject: "금리", kind: "market_driver" }] });
    expect(question).not.toContain("의미 분류");
    expect(question).not.toContain("대표 기사");
  });
});
