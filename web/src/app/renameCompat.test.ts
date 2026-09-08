import { describe, expect, it } from "vitest";
import { HOME_PREFERENCE_KEY, CHARACTER_PREFERENCE_KEY, MOTION_PREFERENCE_KEY, UI_PREFERENCE_EVENT } from "./homePreference";
import { PROPOSAL_LIFECYCLE_EVENT } from "./agentProposalLifecycle";
import { ANALYSIS_HANDOFF_KEY } from "./watchlist/EarningsPanel";

// The Folio OS -> Folio Board rename (plan §3 비목표) explicitly excludes `folio:*`
// CustomEvent names and `folio.*` localStorage keys — they are internal runtime
// contracts, not display strings, and other code (and a viewer's already-stored
// localStorage) depends on the literal values. This pins the exported constants so
// a future editor doesn't "helpfully" rename these alongside the display name.
describe("rename compatibility: internal folio:*/folio.* keys are untouched", () => {
  it("folio.* localStorage keys keep their exact names", () => {
    expect(HOME_PREFERENCE_KEY).toBe("folio.homePreference.v1");
    expect(CHARACTER_PREFERENCE_KEY).toBe("folio.agentCharacter.v1");
    expect(MOTION_PREFERENCE_KEY).toBe("folio.motionPreference.v1");
    expect(ANALYSIS_HANDOFF_KEY).toBe("folio:analysis-query");
  });

  it("folio:* CustomEvent names keep their exact names", () => {
    expect(UI_PREFERENCE_EVENT).toBe("folio:ui-preferences-updated");
    expect(PROPOSAL_LIFECYCLE_EVENT).toBe("folio:proposal-lifecycle");
  });
});
