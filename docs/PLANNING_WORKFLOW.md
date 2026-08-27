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

Default local locations:

- `plan/` for private product or execution plans. This folder is ignored and must not be included in public releases.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` only for public-safe design and implementation plans that are useful to retain in source history.

When a local plan corresponds to a GitHub Issue, include the issue number or URL near the top of the plan. When an issue refers to a private local plan, include only the local relative path and a public-safe summary.

## Operating Rules

- Start from a GitHub Issue for planned work unless the task is a tiny one-turn fix.
- Keep one local plan per substantial task.
- Update the GitHub Issue when scope, status, or acceptance criteria changes.
- Update the local plan with implementation notes and verification details.
- Close the GitHub Issue only after the change is merged, verified, and release/security checks are complete.
- Never copy secrets or private research content from `data/`, `research-inbox/`, or local-only plans into GitHub Issues.
