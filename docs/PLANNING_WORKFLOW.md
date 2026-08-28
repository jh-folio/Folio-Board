# Planning Workflow

Folio OS work is tracked in two layers:

1. GitHub Issues for public, durable task tracking.
2. Local planning documents for detailed execution notes that may include private context.

## GitHub Issues

Use GitHub Issues as the source of record for work items that should be visible in the public repository:

- feature work
- bug fixes
- release tasks
- documentation work
- follow-up tasks discovered during implementation

Each issue should include:

- goal and user-visible outcome
- scope
- non-goals
- linked local plan path when one exists
- verification checklist
- release/security impact

Do not put private data, API keys, local filesystem details, research inbox contents, or unreleased personal notes in GitHub Issues.

## Local Planning Documents

Use local planning documents for detailed execution planning, investigation notes, private sequencing, and agent handoff notes.

When `plan/` exists, `plan/STATUS.md` is the single local entry point. Every active or historical local plan must be registered there with its actual status and target release; do not infer the current plan by comparing filenames or dates.

Default local locations:

- `plan/` for private product or execution plans. This folder is ignored and must not be included in public releases.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` only for public-safe design and implementation plans that are useful to retain in source history.

When a local plan corresponds to a GitHub Issue, include the issue number or URL near the top of the plan. When an issue refers to a private local plan, include only the local relative path and a public-safe summary.

## Operating Rules

- Start from a GitHub Issue for planned work unless the task is a tiny one-turn fix.
- Keep one local plan per substantial task.
- Put `GitHub Issue`, `Status`, `Target release`, `Owner`, and `Branch` at the top of every active local plan. If stages target different releases, split the plan or list the release per stage.
- Register a new plan in `plan/STATUS.md` immediately. Update the plan header and STATUS in the same change whenever work starts, completes, pauses, is deferred, or changes release.
- Use explicit implementation states: `complete`, `partial`, `shadow`, `unimplemented`, or `deferred`. A passing test suite does not make an entire plan complete, and code that remains shadow-by-default is not complete.
- Refresh release facts from the named branch and comparison ref when updating STATUS. Record the branch/ref and do not mix `master` divergence with release-candidate changes since a tag.
- Compare the STATUS in-progress section with all related tracked and untracked worktree changes. Split unrelated objectives instead of hiding them under one broad row.
- Maintain an open-Issue crosswalk in STATUS. Reconcile stale open Issues, mismatched titles or milestones, plans without Issues, and Issues without plans before release.
- Use current `plan/` paths in active documents. Historical documents may preserve old paths as history, but must not present `roadmap/` as the current location.
- Update the GitHub Issue when scope, status, or acceptance criteria changes.
- Update the local plan with implementation notes and verification details.
- Close the GitHub Issue only after the change is merged, verified, and release/security checks are complete.
- Never copy secrets or private research content from `data/`, `research-inbox/`, or local-only plans into GitHub Issues.
