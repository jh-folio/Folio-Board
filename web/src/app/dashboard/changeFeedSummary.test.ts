import { describe, expect, it } from "vitest";
import { emptyMessage, summarizeChangeEvents } from "./ChangeFeed";
import type { ChangeEvent } from "../changeEvents";

function event(verdict: string, artifactKind = "briefing"): ChangeEvent {
  return {
    artifactKind,
    artifactId: "2026-08-20.us",
    changedItems: [{ id: "u1", kind: "market_driver", semanticVerdict: verdict }],
  };
}

describe("summarizeChangeEvents", () => {
  it("내용 변화로 세는 판정만 카드가 된다", () => {
    const { confirmed } = summarizeChangeEvents([
      event("new_information"), event("reversal"), event("trend_development"),
      event("no_new_information"),
    ]);

    expect(confirmed).toHaveLength(3);
  });

  it("정상 판정된 '변화 없음'은 미판정이 아니다", () => {
    // 예전에는 confirmed가 아닌 것을 전부 미판정으로 세서, 판정이 멀쩡히 끝난 날에도
    // "판정하지 못했다"고 말하고 이미 연결된 Agent를 연결하라고 안내했다.
    const { confirmed, unjudged } = summarizeChangeEvents([
      event("coverage_shift_only"), event("no_new_information"),
    ]);

    expect(confirmed).toHaveLength(0);
    expect(unjudged).toBe(0);
  });

  it("진짜 미판정만 센다", () => {
    const { unjudged } = summarizeChangeEvents([event("not_evaluated"), event("")]);

    expect(unjudged).toBe(2);
  });

  it("의미 비교 대상이 아닌 아티팩트는 미판정으로 세지 않는다", () => {
    // 기업분석·테마·시장 내러티브에는 semanticVerdict가 없는 것이 정상이다.
    const { unjudged } = summarizeChangeEvents([
      event("", "company_analysis"), event("", "topic_report"), event("", "market_memory"),
    ]);

    expect(unjudged).toBe(0);
  });
});

describe("emptyMessage", () => {
  it("판정이 다 끝났으면 변화가 없다고 말한다", () => {
    expect(emptyMessage(0, false)).toBe("아직 확인된 내용 변화가 없습니다.");
    expect(emptyMessage(0, true)).toBe("아직 확인된 내용 변화가 없습니다.");
  });

  it("Agent가 없을 때만 연결을 안내한다", () => {
    expect(emptyMessage(3, false)).toContain("AI Agent를 연결하면");
  });

  it("이미 연결돼 있으면 연결하라고 하지 않는다", () => {
    // 되어 있는 일을 다시 하게 만들면 안 된다.
    const message = emptyMessage(3, true);

    expect(message).not.toContain("연결하면");
    expect(message).toContain("다음 브리핑 생성");
  });
});
