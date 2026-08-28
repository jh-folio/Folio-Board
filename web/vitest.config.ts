import { defineConfig } from "vitest/config";

// 타임존을 고정한다.
//
// 날짜 판정(`daysUntil`·`ddayLabel`)은 **보는 사람의 로컬 하루** 기준이고 그것이
// 의도다 — 미국장 실적은 KST로 다음 날 새벽이라 한국 사용자에게는 내일 일정이 맞다.
// 그런데 그 예시를 검증하는 테스트가 실행 환경의 타임존을 그대로 쓰면, 개발 PC(KST)
// 에서는 통과하고 CI(UTC)에서는 실패한다 — 실측으로 `2026-08-20T21:00:00Z`가 KST에서는
// D-1, UTC에서는 D-DAY로 갈렸고 세 OS가 모두 실패했다.
//
// 코드가 아니라 테스트가 가정을 안 적어 둔 것이므로, 그 가정을 여기 적는다.
// 주변 값을 존중하지 않고 **덮어쓴다.** `||`로 두면 실행 환경이 계속 이겨서,
// 없애려던 비결정성이 그대로 남는다.
process.env.TZ = "Asia/Seoul";

export default defineConfig({
  test: {
    include: ["src/**/*.test.ts"],
  },
});
