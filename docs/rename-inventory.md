# Folio OS → Folio Board: Name Inventory (Phase A)

Status: **Phase A complete — Gate A passed.** This document records the
result of classifying every occurrence of the old brand name found in the
repository, produced by [`scripts/check_name_inventory.py`](../scripts/check_name_inventory.py).
No renaming happened in this phase; see `plan/FOLIO_BOARD_RENAME_PLAN.md`
(local, gitignored) §6 Phase B onward for the actual rename work.

Re-run the check with:

```powershell
py -3 scripts/check_name_inventory.py          # human-readable
py -3 scripts/check_name_inventory.py --json   # machine-readable
```

Exit code is `0` iff every occurrence found landed in one of the five
buckets below. Per plan §11.1 this script is meant to be run again after
0.6 work resumes (to catch old-name text reintroduced by habit) and again
at the 0.6 release gate.

## Totals (as of 2026-09-08, branch `codex/folio-board-rename` @ `ceedbf1`)

| Bucket | Occurrences | Files |
|---|---:|---:|
| `replace` | 280 | 113 |
| `dual-read` | 45 | 24 |
| `retain` | 1 | 1 |
| `historical` | 48 | 12 |
| `external` | 4 | 3 |
| **Total** | **378** | **135** |

378 occurrences = 376 pattern matches inside file content + 2 matches
where the old name appears in a **filename itself**
(`docs/superpowers/plans/2026-07-02-agentic-folio-os-foundation.md` and
`docs/superpowers/specs/2026-07-02-agentic-folio-os-roadmap-design.md`,
both already `historical` by path). 135 files matched, which agrees with
the plan's own 2026-09-08 measurement (135 files / 376 occurrences).

Pattern matched: `folio[ _-]?os`, case-insensitive, no word boundaries —
covers `Folio OS`, `FolioOS`, `folio-os`, `folio_os`, `folioos`, and the
`Folio-OS` User-Agent form, and deliberately also matches inside compound
identifiers like `folio_os_roadmap_post_v1.md` and `.folio-qa-owned` so
those citations aren't silently missed.

## Per-bucket breakdown

### `replace` (280 occurrences / 113 files) — swap to the new name, no compat concern

The dominant bucket by far: display strings, screen-reader labels,
console/startup messages, FastAPI title, package/CI naming, LLM prompt
text, docstrings, and documentation prose that simply names the product.
Notable groups:

- **Core docs**: `README.md`, `README.ko.md`, `AGENTS.md`, `CLAUDE.md`,
  `SECURITY.md`, `THIRD_PARTY_NOTICES.md`, `installation.md`,
  `docs/PUBLIC_RELEASE_CHECKLIST.md`, `docs/SMOKE_TESTS.md`,
  `docs/PLANNING_WORKFLOW.md` — all active (not under `docs/superpowers/`),
  so treated as live text to update in Phase B.
- **Screen/UI**: `public/index.html`, `public/favicon.svg` (both `<title>`
  and `aria-label`), `web/src/app/AppShell.tsx` (nav `aria-label`),
  `web/src/app/FolioWordmark.tsx` (`sr-only` name + a comment describing
  the wordmark convention), `web/src/app/agentWorkspace/AgentComposer.tsx`
  (adapter-label fallback string — this is the one plan §6 Phase B calls
  out by name as easy to miss because it doesn't render on the happy
  path), `web/src/app/reportReader/FolioNotePanel.tsx`.
- **Compiled bundle**: `public/react/folio-react.js` — 4 of its 5 hits
  mirror the TSX source strings above (mechanically regenerated once
  `web/src/` changes and the project rebuilds); its 5th hit
  (line 12484) is the one exception, routed to `dual-read` (see below).
- **Server/CLI messages**: `app.py` (FastAPI title + already-running /
  port-in-use console messages), `start.ps1`, `start.sh`.
- **Agent/LLM context** (plan §5 "Agent/LLM 문맥" row): all of
  `features/agent_mode/*.py` (11 files — system prompts, CLI descriptions,
  bridge status/error strings), `features/market_memory/snapshot.py`,
  `features/daily_briefing/service.py`, `features/thesis_tracking/delta_prompt.md`,
  `features/topic_report/{prompt.md,approved_generation_support.py}`,
  `features/common/quality_generation/llm_section_rewrite.py`,
  `features/portfolio/import_image.py` (user-facing consent notices).
- **Packaging/CI naming** (plan §5 "패키징·CI" row, Phase D scope):
  `release-manifest.json` (`packageName`), `.github/workflows/ci.yml`,
  `.github/dependabot.yml`, `scripts/{package_release,verify_release,
  install_gitleaks,qa_020,qa_server_supervisor}.py`, and the release/CI
  test suite (`tests/test_qa_020_contract.py`, `tests/test_release_boundaries.py`,
  `tests/test_release_tools.py`, `tests/test_todo14_ci_health_contract.py`,
  `tests/test_todo15_ci_workflow_contract.py`, `tests/test_version_contract.py`)
  — these assert the *current* `FolioOS-vX.Y.Z` package/zip naming
  convention and will need updating together with Phase D, but have no
  backward-compat requirement (nothing reads an old already-shipped zip
  name back into the running app).
- **Network User-Agent strings** (own rule, `replace-user-agent`, 10 hits):
  `.env.example` (`SEC_USER_AGENT` example default), `THIRD_PARTY_NOTICES.md`,
  4× `Mozilla/5.0 Folio-OS/1.0` in `features/common/market_data/*.py`,
  `features/common/research_library/rss/fetch.py` (`FEED_USER_AGENT`),
  `features/common/research_library/signals/adapters/generic_rss.py`,
  `features/daily_briefing/web_evidence.py`, `scripts/install_gitleaks.py`.
  Per plan §4.1/§10 decision 2, these rename in one direction only —
  nothing needs to keep recognizing the old UA string.
- **Dev package metadata**: `web/package.json` and `web/package-lock.json`
  (`"name": "folio-os-web"`, description) — plan §6 Phase D proposes
  `folio-board-web`, contingent on confirming no external consumer (see
  Notable/ambiguous below).
- **Test fixtures using a plausible release-folder name**: several tests
  build a temp `tmp_path / "FolioOS-vX.Y.Z"` or `tmp_path / "FolioOS-test"`
  purely as an arbitrary app-root folder name, unrelated to the
  `~/Documents/FolioOS` dual-read mechanism (`features/common/tests/test_workspace.py`
  lines 17/111/145, `features/common/tests/test_workspace_service.py:20`,
  `features/onboarding/tests/test_service.py:17`). These are cosmetic and
  update alongside Phase D naming, same as the packaging tests above.

### `dual-read` (45 occurrences / 24 files) — old and new value both stay readable

Two families, both driven by content rules rather than file location:

1. **Provenance `generated_by`** (21 hits, rule `provenance-generated-by`):
   the Obsidian/Notion export writer (`features/obsidian/export/service.py`
   — 5 occurrences), `features/thesis_tracking/service.py:356`, the
   importer/self-reference classifier and its docs
   (`features/obsidian/{README.md,importer/__init__.py,importer/parser.py,
   importer/service.py,importer/tests/test_parser.py,workflow/{validator.py,
   tests/test_validator.py}}`), `features/thesis_tracking/README.md:111`,
   `docs/agent-guides/{obsidian-export.md,obsidian-workflow.md}`, and the
   two root docs (`AGENTS.md:121`, `CLAUDE.md:121`, principle 5). Plan
   §4.3 requires the importer/self-reference filters to keep recognizing
   the old value permanently, and the new export writer to also start
   writing the new value — both sides of that change belong in the same
   commit.
2. **`~/Documents/FolioOS` workspace-folder discovery** (22 hits, rule
   `dual-read-documents-workspace-folder`, plus 1 more via a path-specific
   override — see below): `features/common/workspace.py` (`DOCUMENTS_FOLDER_NAME`
   and the docstring's discovery-order list), `docs/agent-guides/workspace.md:10`,
   `features/common/README.md:42`, `installation.md:181`,
   `tests/test_release_tools.py:354`, and the bulk of
   `features/common/tests/{test_workspace.py,test_workspace_service.py}`
   (13 hits) which exercise the discovery order, move destination, and
   `workspace_payload().documentsPath` field the plan calls out explicitly
   in §4.4 as a derived value that must reflect the folder actually in use.

Two occurrences needed a rule beyond simple content matching:

- `public/react/folio-react.js:12484` and `web/src/app/deepResearchPayload.ts:300`
  — the minified bundle and its TypeScript source both compare a
  normalized alias against the bare literal `"folioos"` (no `generated_by`
  substring in the minified line, since the variable is renamed by the
  build). Plan §4.3 identifies this exact line as **the one place that
  compares the provenance value directly rather than just checking for
  presence** — if this comparison isn't updated to accept the new alias
  in the same commit as the export writer, freshly-exported self-notes
  stop being filtered out of the source ledger.
- `features/common/research_library/indexing/tests/test_index_cache.py:153`
  — `moved = tmp_path / "FolioOS"` has no literal "Documents" on that
  line, but it's the same `workspace_root()`-relocation test family as
  line 142 in the same file. Handled by an explicit path-specific rule
  rather than a content rule (flagged below as a judgment call).

### `retain` (1 occurrence / 1 file)

`features/llm_settings/client.py:29` — `SECRET_STORE_SERVICE = "Folio OS"`,
the OS keyring credential-store service name. Plan §4.2 prefers keeping
this exact string so a rename doesn't orphan API keys users already
stored under it; a future migration (new-first, legacy-fallback,
copy-on-success) is left as an open decision in plan §10.

**Why this bucket is so small**: the other identifiers plan §4.2 lists as
"retain" — `FOLIO_HOME` and other `FOLIO_*` env vars, `folio:*`
CustomEvent names, `folio.*` localStorage keys, `/api/*` routes — do not
literally spell `Folio`+`OS` adjacently (e.g. `FOLIO_HOME` has `H`, not
`O`, right after the underscore), so they never match the search pattern
and correctly never appear in this inventory at all. This is expected,
not a gap: this script inventories occurrences of the *old brand name*,
not every `folio`-prefixed identifier in the codebase.

### `historical` (48 occurrences / 12 files) — frozen records, never retroactively edited

- **45 occurrences across 10 files under `docs/superpowers/`** (both
  `plans/` and `specs/`), matched by path alone regardless of content —
  plan §5 is explicit that these are never edited retroactively. This
  includes 2 occurrences where the old name is in the **filename**
  itself, not just the content.
- **3 occurrences citing a local-only or gitignored past-planning file**:
  `docs/agent-guides/agent-threads.md:20` cites
  `.planning/folio-os-0.4-x-research-intelligence/task_plan.md`;
  `features/common/research_schema/README.md:6` and
  `features/investment_review/README.md:88` both cite
  `folio_os_roadmap_post_v1.md`, explicitly noted in-line as "저장소에
  포함하지 않는다" (not included in the repository). These name a frozen
  record rather than live code, so they're historical even though they
  sit outside `docs/superpowers/`.

### `external` (4 occurrences / 3 files) — outside this repo's control

- **GitHub URL** (2): `installation.md:24` and `:76` —
  `https://github.com/jh-folio/FolioOS`. Repo slug transfer is Phase E,
  performed at the same time as the display-name change but gated on its
  own checklist (plan §1, §6 Phase E). Note: `installation.md:77`
  (`cd FolioOS`, the local directory name after cloning) is **not** in
  this bucket — it lands in `replace` since it names a local folder, not
  a URL — but it is still coupled to the Phase E repo rename timing (see
  Notable/ambiguous below).
- **`FolioOS_Sites` mentions** (2): `features/agent_mode/schema.py:232`
  and `features/agent_mode/tests/test_pack_roots_follow_workspace.py:7`.
  Both are incident-report comments/docstrings describing a real
  `FOLIO_HOME`-boundary bug discovered because a *separate* repository
  (`FolioOS_Sites`) runs against this checkout. That repo is out of this
  inventory's scope entirely — plan §3/§6 Phase E defer it to its own
  investigation when Sites work is approved.

## Notable / ambiguous — reviewer should decide, not silently assumed

- **`LICENSE:3` — `Copyright (c) 2026, Folio OS contributors`.** Classified
  `replace` by the generic default rule, but a license copyright-holder
  line is a legal continuity question, not a purely mechanical rename.
  Worth an explicit yes/no before Phase B touches it.
- **`web/package.json` / `web/package-lock.json` (`"folio-os-web"`).**
  Bucketed `replace`, but plan §6 Phase D makes the rename to
  `folio-board-web` conditional on confirming there's no external
  consumer of the current package name first. The inventory doesn't
  verify that; Phase D still needs to.
- **`installation.md:77` (`cd FolioOS`).** Falls into `replace` (it's a
  local directory name, not a URL) rather than `external`, but it only
  makes sense once the GitHub repo is actually renamed (Phase E) — a
  reviewer should not treat its `replace` bucket as "do this in Phase B
  independent of the repo transfer."
- **`features/thesis_tracking/delta.py:248` — `"source": "Folio OS"`.**
  Classified `replace` (a display citation label on a synthesized
  counter-evidence item), not `dual-read`, because nothing filters on
  this specific field's value the way the importer filters on
  `generated_by`. Same file's `service.py:356` *does* write
  `generated_by` and is correctly `dual-read`. Flagging the distinction
  in case a reviewer disagrees that this particular field is purely
  cosmetic.
- **`features/common/research_library/indexing/tests/test_index_cache.py:153`.**
  Routed to `dual-read` via an explicit path-specific rule
  (`dual-read-index-cache-relocation-test`) rather than a content match,
  on the judgment that it belongs to the same workspace-relocation test
  family as line 142 in the same file. This is a script-author inference,
  not something the plan states directly — worth a second look.
- **`scripts/qa_deep_research_execution.py:702`.** Contains a hardcoded
  absolute path (`D:\Project\Personal\FolioOS_Public\...`) tied to one
  developer's machine. Bucketed `replace` along with the rest of that
  file's QA-harness marker strings, but the hardcoded path is a
  pre-existing portability smell independent of the rename — noting it
  here rather than fixing it, since that's out of Phase A's scope.
- **`docs/SMOKE_TESTS.md:1` (`# Folio OS 0.3.0 Smoke Tests`) and
  `docs/PUBLIC_RELEASE_CHECKLIST.md:48` (`dist/FolioOS-v0.3.0` example).**
  Both are active (non-`docs/superpowers/`) docs that still cite a
  long-superseded version number (0.3.0). Bucketed `replace` since
  they're not historical records, but the stale version number is a
  pre-existing documentation-freshness issue the rename didn't create and
  Phase A isn't fixing.
- **Two occurrences with no `generated_by` on the line but adjacent to
  provenance discussion**: `features/obsidian/importer/parser.py:24`
  (`# Folio OS가 생성·내보낸 노트 타입 (self-reference 방지 — import 제외)`) and
  `features/obsidian/workflow/validator.py:52` (a `reuse_as_evidence`
  warning message). Both fell to the `replace` default since they don't
  literally contain `generated_by`, even though they're one line away
  from code that does. Consistent with the rule design, but a reviewer
  skimming the `dual-read` bucket for "everything about self-reference"
  won't find these two.

## Re-running this check

The classification table lives in `CLASSIFICATION_RULES` at the top of
`scripts/check_name_inventory.py`, ordered by priority with a `reason`
string on every rule. If a future run reports unclassified hits, add a
rule (or, if it's truly a new display string, let it fall through to the
existing default-prefix rules) rather than special-casing individual
lines — the existing rules already cover every directory family present
in this repo as of Phase A.
