# Planning Workflow

Folio Board is a solo project. Planning uses one local source of truth instead of mirroring the same work into GitHub Issues.

GitHub Issues are not a required planning layer. Do not create or maintain an Issue merely to mirror a local plan. Blank Issues may remain available for external bug reports or feedback, but they do not need a matching local-plan crosswalk.

## Local Planning Documents

Use local planning documents for detailed execution planning, investigation notes, private sequencing, and agent handoff notes.

When `plan/` exists, `plan/STATUS.md` is the single local entry point. Every active or historical local plan must be registered there with its actual status and target release; do not infer the current plan by comparing filenames or dates.

Default local locations:

- `plan/` for private product or execution plans. This folder is ignored and must not be included in public releases.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` only for public-safe design and implementation plans that are useful to retain in source history.

## Operating Rules

- Keep one local plan per substantial task.
- Put `Status`, `Target release`, `Owner`, and `Branch` at the top of every active local plan. If stages target different releases, split the plan or list the release per stage.
- Register a new plan in `plan/STATUS.md` immediately. Update the plan header and STATUS in the same change whenever work starts, completes, pauses, is deferred, or changes release.
- Use explicit implementation states: `complete`, `partial`, `shadow`, `unimplemented`, or `deferred`. A passing test suite does not make an entire plan complete, and code that remains shadow-by-default is not complete.
- Refresh release facts from the named branch and comparison ref when updating STATUS. Record the branch/ref and do not mix `master` divergence with release-candidate changes since a tag.
- Compare the STATUS in-progress section with all related tracked and untracked worktree changes. Split unrelated objectives instead of hiding them under one broad row.
- Use current `plan/` paths in active documents. Historical documents may preserve old paths as history, but must not present `roadmap/` as the current location.
- Update the local plan with implementation notes and verification details.
- Never copy secrets or private research content from `data/`, `research-inbox/`, or local-only plans into public documentation or external reports.
