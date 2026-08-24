import { describe, expect, it } from "vitest";
import { emptyMessage, engineMissing, summarizeChangeEvents } from "./ChangeFeed";
import type { ChangeEvent } from "../changeEvents";

function event(verdict: string, artifactKind = "briefing"): ChangeEvent {
  return {
    artifactKind,
    artifactId: "2026-08-20.us",
    changedItems: [{ id: "u1", kind: "market_driver", semanticVerdict: verdict }],
  };
}

/** `baseline_created`·`no_material_change`는 변화 단위가 비어 있다. */
function emptyEvent(artifactKind = "briefing"): ChangeEvent {
  return { artifactKind, artifactId: "2026-08-20.us", changedItems: [] };
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

  it("서버가 미판정으로 표시한 것만 센다", () => {
    // 자격은 서버가 정한다. 종류가 맞아도 대표 기사 제목이 없으면 서버는 아무 표시도
    // 남기지 않고 **영원히 판정하지 않는다** — 그것까지 세면 "다음 생성에서 판정합니다"가
    // 지키지 못할 약속이 된다.
    const { unjudged } = summarizeChangeEvents([event("not_evaluated"), event("")]);

    expect(unjudged).toBe(1);
  });

  it("판정할 변화 단위가 없으면 미판정이 아니다", () => {
    // 처음 만든 브리핑(`baseline_created`)과 정말로 안 바뀐 날(`no_material_change`)은
    // `changedItems`가 비어 있다. 그걸 미판정으로 세면 없애려던 문구가 그대로 돌아온다.
    const { confirmed, unjudged } = summarizeChangeEvents([emptyEvent(), emptyEvent()]);

    expect(confirmed).toHaveLength(0);
    expect(unjudged).toBe(0);
  });

  it("지표만 바뀐 건도 미판정이 아니다", () => {
    // 의미 판정은 `market_driver`·`issue_coverage`에만 걸린다(SEMANTIC_KINDS).
    const { unjudged } = summarizeChangeEvents([
      { artifactKind: "briefing", changedItems: [{ id: "m1", kind: "market_metric" }] },
    ]);

    expect(unjudged).toBe(0);
  });

  it("대표 기사 제목이 없어 판정될 수 없는 옛 기록은 미판정이 아니다", () => {
    // 서버는 종류가 맞고 `contextDocs`가 있는 단위에만 `not_evaluated`를 붙인다.
    // 화면이 종류만 보고 다시 세던 동안, 제목 보존 이전에 만들어진 기록이 영원히
    // "판정하지 못한 N건"으로 남았다.
    const { unjudged } = summarizeChangeEvents([
      { artifactKind: "briefing", changedItems: [{ id: "d1", kind: "market_driver" }] },
    ]);

    expect(unjudged).toBe(0);
  });

  it("의미 비교 대상이 아닌 아티팩트는 미판정으로 세지 않는다", () => {
    // 기업분석·테마·시장 내러티브에는 semanticVerdict가 없는 것이 정상이다.
    const { unjudged } = summarizeChangeEvents([
      event("", "company_analysis"), event("", "topic_report"), event("", "market_memory"),
    ]);

    expect(unjudged).toBe(0);
  });
});

describe("engineMissing", () => {
  it("서버가 남긴 사유로 엔진 부재를 읽는다", () => {
    // 예전에는 화면이 CLI 어댑터 목록만 보고 판단해, LLM API 키만 넣은 설치에서
    // 판정 엔진이 멀쩡한데도 "연결하세요"가 떴다.
    expect(engineMissing([{ semanticEvaluation: { reason: "llm_unavailable" } }])).toBe(true);
    expect(engineMissing([{ semanticEvaluation: { reason: "generation_rules_mode" } }])).toBe(true);
  });

  it("호출 실패나 정상 판정은 엔진 부재가 아니다", () => {
    expect(engineMissing([{ semanticEvaluation: { reason: "llm_failed" } }])).toBe(false);
    expect(engineMissing([{ semanticEvaluation: { status: "evaluated", reason: null } }])).toBe(false);
    expect(engineMissing([{ artifactKind: "briefing" }])).toBe(false);
  });
});

describe("emptyMessage", () => {
  it("판정이 다 끝났으면 변화가 없다고 말한다", () => {
    expect(emptyMessage(0, false)).toBe("아직 확인된 내용 변화가 없습니다.");
    expect(emptyMessage(0, true)).toBe("아직 확인된 내용 변화가 없습니다.");
  });

  it("엔진이 없을 때만 연결을 안내한다", () => {
    expect(emptyMessage(3, true)).toContain("연결하면");
  });

  it("엔진이 있으면 연결하라고 하지 않는다", () => {
    // 되어 있는 일을 다시 하게 만들면 안 된다.
    const message = emptyMessage(3, false);

    expect(message).not.toContain("연결하면");
    expect(message).toContain("다음 브리핑 생성");
  });
});
