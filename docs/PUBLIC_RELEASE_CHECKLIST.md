# Folio Board Public Release Checklist

Use this checklist before changing the repository visibility to Public.

## Repository Hygiene

- [ ] `.env` is not present.
- [ ] `data/` is not present.
- [ ] `research-inbox/` is not present.
- [ ] `plan/` is not present.
- [ ] `README.dev.md` is not present.
- [ ] `.agents/`, `.claude/`, and `.superpowers/` are not present.
- [ ] local launcher variants such as `start-lan.ps1` and `start-lan.cmd` are not present.
- [ ] generated databases, logs, caches, and local reports are not present.

## Security

- [ ] `SECURITY.md` exists.
- [ ] `.env.example` contains placeholders only.
- [ ] Gitleaks scan passes.
- [ ] GitHub Secret scanning is enabled.
- [ ] GitHub Push protection is enabled.
- [ ] Dependabot alerts are enabled.
- [ ] Code scanning is enabled or CodeQL workflow is present.

## Documentation

- [ ] `README.md` explains local-first behavior.
- [ ] `README.md` warns against public internet exposure.
- [ ] `README.md` explains optional third-party service usage.
- [ ] `installation.md` points to the correct repository URL.
- [ ] License is present.

## Validation

Run these locally *before* pushing. Every item here has failed a real release at least
once; the order is cheapest-first so a failure stops you early.

- [ ] `python scripts/install_gitleaks.py --version 8.30.1 --verify-checksum`, then
      `gitleaks git --redact=100` over the full history passes. Run this first — a leak
      found after a push means rewriting history, not just fixing a file.
- [ ] `git status --porcelain` is clean and no build tool, binary, or downloaded artifact
      is tracked. `.tools/` and `dist/` must stay ignored.
- [ ] `python -m py_compile app.py` passes.
- [ ] Python tests pass.
- [ ] `py -3 scripts/public_release_audit.py` passes.
- [ ] `py -3 scripts/package_release.py --version v0.3.0` creates a verified ZIP under `dist/`.
- [ ] `py -3 scripts/verify_release.py --release-dir dist/FolioBoard-v0.3.0` passes.
- [ ] Web typecheck passes.
- [ ] Web tests pass.
- [ ] Web build passes.
- [ ] `npm run build` leaves `git status --porcelain -- public/react` empty. Any built
      file must be pinned to LF in `.gitattributes`, or Windows CI reports bundle drift.
- [ ] Chromium desktop/mobile theme, accessibility, keyboard, and overflow gates pass
      (`npm run test:ui`). This is the gate most often skipped locally and the one that
      catches route-contract regressions.
- [ ] GitHub Actions CI passes on all three operating systems, including the
      `Canonical Ubuntu release package` job.
- [ ] CodeQL analysis passes for both python and javascript-typescript.

## Release

- [ ] The repository starts as Private.
- [ ] The initial public release commit contains only clean files.
- [ ] Dashboard, Watchlist, and Deep Research are visible in the default navigation.
- [ ] Light, Dark, and System appearance work across every public route.
- [ ] The full 0.3 packaged Browser scenario set and privacy evidence are confirmed at the release SHA.
- [ ] The `v0.3.0` tag points to the clean release commit.
- [ ] Repository visibility is changed to Public only after all checks pass.

## After the release

These do not block the tag, but leaving them undone is how a repository rots.

- [ ] Triage every open Dependabot PR into one of three buckets: mergeable as-is,
      blocked by one of our own reproducibility gates, or superseded. The gates that
      block them are the pinned action SHAs in `tests/test_todo15_ci_workflow_contract.py`,
      the `--exclude-newer` lock cutoff, and the `public/react` bundle drift check —
      none of which Dependabot can satisfy on its own. Record any changed reasoning in
      this checklist or the relevant local release plan rather than re-deriving it.
- [ ] Merge the PRs that are genuinely green. Close the ones that can never be, with the
      reason, so the queue reflects reality.
- [ ] Update `plan/STATUS.md` and the relevant local plan for work that shipped, was cut,
      or was put on hold. The next session should not have to read the diff to find out.
- [ ] Confirm Dependabot alerts, secret scanning, and push protection are still enabled.
