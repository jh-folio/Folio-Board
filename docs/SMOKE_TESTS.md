# Folio Board 0.3.0 Smoke Tests

Run these checks against a clean local workspace or a synthetic packaged fixture. Do not use real credentials, private notes, portfolio data, or provider transcripts as evidence.

## Startup and identity

1. Start Folio Board with `start.ps1`, `start.sh`, or `start-archive.cmd`.
2. Open `http://127.0.0.1:8787/api/health` and confirm `status=ok`, `version=0.3.0`, the expected commit, PID, and workspace identity.
3. Confirm Home, Dashboard, Watchlist, Briefing, RSS Feed, Market Memory, Company Analysis, Deep Research, and Settings are visible.

## Appearance and responsive navigation

1. In Settings > 화면, select Light, Dark, and System and confirm the active theme changes without a flash of the wrong theme after reload.
2. Confirm existing browser profiles without a saved theme start in Light and new profiles start in System mode.
3. At desktop width, confirm grouped left navigation and the Agent dock do not cover route content.
4. At tablet/mobile width, confirm navigation becomes one horizontally scrollable row and the Agent starts collapsed.
5. Use keyboard-only navigation to activate `본문으로 건너뛰기`, open and close the command palette, and reach every public route with a visible focus indicator.

## Deep Research exposure

At desktop, tablet, and mobile widths:

1. Select the left-nav `딥 리서치` item (`[data-qa=nav-deep-research]`) and confirm `#/deep-research`.
2. Return Home and select `[data-qa=home-deep-research]`; confirm the same route receives focus without horizontal overflow.
3. Open the command palette with Ctrl/Command+K, search for Deep Research, select `[data-qa=command-deep-research]`, and confirm the same route.
4. Check the browser console and failed network requests; both must be empty for the navigation flow.

## Question-first execution

1. Enter an investment question and optional hypothesis context.
2. Review the approved plan and evidence preview before generation.
3. If a Smart Collection is selected, confirm only its ID/revision is sent from the browser and the saved definition is resolved again by the server.
4. Execute once through Direct mode and once through a deterministic CLI fixture; both must use the same approved definition and resolved evidence.
5. If no usable external evidence exists, confirm generation is blocked until the evidence-limited fallback is explicitly approved.
6. Reopen the saved report and verify the approved plan, external evidence ledger, data gaps, quality, execution provenance, Market State, hypothesis context, and Personal Overlay are visibly separate.

## Agent lifecycle and privacy

1. Start an Agent task, poll the exact job ID, cancel it, and confirm the terminal state is `cancelled` with no report writeback.
2. Approve one revision proposal and confirm the Canonical revision increments exactly once; replay must not apply twice.
3. Reject another proposal and confirm the report hash is unchanged.
4. Inspect `/api/agent/work-log`: entries may contain only bounded task/status/timing/engine/artifact/proposal metadata. Prompts, replies, Markdown, diffs, attachments, paths, credentials, and raw provider output must be absent.
5. Restart the server and confirm the same saved report, proposal state, Smart Collection revision, and Work Log metadata reopen safely.

## Stage 0.3.0 integrated workflow matrix

Run every scenario with a **synthetic fixture root**. Never point these checks at
the real `data/`, `config/`, `research-inbox/`, `.env`, portfolio, watchlist, or
user-note locations.

### Note and Thesis Intelligence

1. Save a thought without Agent and confirm the original thought remains intact.
2. Disable Agent and confirm the deterministic fallback still exposes
   counter-evidence, contradictions, uncertainties, and controlled checkpoints.
3. Complete a revision-safe checkpoint update and verify the Canonical hash is unchanged.
4. Restart the synthetic runtime and confirm review state and checked checkpoints recover.

### Smart Collection workspace

1. Create the first snapshot, then resolve changed evidence and inspect the bounded change ledger.
2. Exercise empty, noisy, stale, source-unavailable, and revision-conflict states.
3. Invoke Agent only from the explicit action and hand the exact Collection ID/revision
   to Deep Research.
4. Restart and confirm the saved definition and snapshot history recover without mutation.

### Investment Context

1. Verify empty and populated portfolio/watchlist fixtures produce bounded personal links.
2. Create and check one watchlist checkpoint; note bodies, quantities, prices, and weights
   must not appear in unrelated responses.
3. Request the explicit Agent risk explanation and confirm fallback contains challenging
   evidence and limitations but no recommendation, target price, sizing, or execution copy.
4. Confirm Dashboard and Watchlist remain visible while unrelated screens expose only bounded portfolio/watchlist context.

### Browser viewport pass

At **1440 / 768 / 390** widths, capture Home/Market Memory Investment Context,
report-side Note and Thesis Intelligence, and the nested Smart Collection workspace.
For every capture, require no horizontal overflow, no console error, no failed unrelated
network response, correct hypothesis/evidence labels, and a complete cleanup receipt.

## Release checks

```powershell
py -3 -m pytest tests/test_version_contract.py web/tests/test_navigation_contract.py -q
npm --prefix web test
npm --prefix web run typecheck
npm --prefix web run build
npm --prefix web run test:ui
git diff --exit-code -- public/react/folio-react.js
```

Before publishing, also run the package, extraction, Gitleaks `--redact=100`, privacy-canary, and full packaged Browser gates in `docs/PUBLIC_RELEASE_CHECKLIST.md`.
