import { afterEach, expect, it, vi } from "vitest";
import { activateReactAgentContextScope, openReactAgentDock, resetReactAgentContextScope } from "./agentContext";

afterEach(() => { resetReactAgentContextScope("chart-test"); vi.unstubAllGlobals(); });

it("sends chart references only to the explicit action and never persists them in screen context", () => {
  const opened = vi.fn();
  vi.stubGlobal("window", { FolioBridge: { openAgentDock: opened } });
  activateReactAgentContextScope("chart-test", { surface: "watchlist", viewId: "AAPL" });
  const selection = { instrumentId: "US:AAPL", snapshotId: "fixed-price", startDate: "2025-01-01", endDate: "2025-12-31" };
  openReactAgentDock({ chartMovement: selection, prompt: "이 움직임 물어보기", autoSubmit: true });
  expect(opened.mock.calls[0][0].chartMovement).toEqual(selection);
  expect(window.FolioAgent?.currentContext?.chartMovement).toBeUndefined();
  expect(activateReactAgentContextScope("chart-test").chartMovement).toBeUndefined();
  openReactAgentDock({ prompt: "일반 질문" });
  expect(opened.mock.calls[1][0].chartMovement).toBeUndefined();
});
