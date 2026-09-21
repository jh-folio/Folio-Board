# Briefing Leader Chart Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bind each leading-company chart to the company named in the final briefing heading across rules and CLI generation.

**Architecture:** Parse final Markdown headings into market/ordinal company subjects, pass them as explicit overrides to visual collection, and reconcile CLI draft company visuals during writeback without touching index or heatmap snapshots.

**Tech Stack:** Python 3, pytest, existing company lookup and market history providers.

---

### Task 1: Parse final leading-company headings

- [x] Add failing tests in `features/daily_briefing/tests/test_visuals.py` for US/KR headings, aliases, ordinals, and unknown companies.
- [x] Implement `leading_company_subjects_from_markdown()` in `features/daily_briefing/visuals.py` using local company lookup.
- [x] Run the focused visual tests.

### Task 2: Override company visual collection

- [x] Add a failing test proving explicit Markdown leaders override group-derived candidates.
- [x] Extend `collect_briefing_visuals()` with `leader_subjects` and `include_market_visuals` parameters.
- [x] Add a pure helper that removes old leading-company snapshots/recommendations and appends aligned replacements.
- [x] Run visual tests and commit.

### Task 3: Connect rules and CLI writeback

- [x] Add failing builder and Agent writeback tests for NVIDIA/Alphabet and SK hynix/Samsung alignment.
- [x] Pass parsed final leaders from `builder.py` into visual collection.
- [x] Store minimal CLI visual scope metadata in the pack, collect company-only visuals at writeback, and replace draft candidates.
- [x] Verify unknown companies remove mismatched charts instead of falling back by ordinal.

### Task 4: Verify and document

- [x] Update daily briefing and Agent Mode README files.
- [x] Run `py -3 -m pytest -q`, Python compile checks, frontend tests, JavaScript checks, and `git diff --check`.
- [x] Commit only code, tests, and docs; do not stage `data/` or generated context packs.
