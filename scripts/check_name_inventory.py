#!/usr/bin/env python3
"""Folio OS -> Folio Board rename: old-name inventory checker (Phase A tool).

Finds every occurrence of the old brand name ("Folio OS" and its spelling
variants: FolioOS, folio-os, folio_os, folioos, and the hyphenated
"Folio-OS" form used in User-Agent strings) in the repository and
classifies each one into exactly one of five buckets:

    replace     User-facing display/branding text, or descriptive prose
                that simply names the product. Swapped to the new name
                (Phase B/D of the rename); no backward-compatibility
                reading is required.
    dual-read   A stored or compared VALUE — a provenance `generated_by`
                value, or a `~/Documents/FolioOS` workspace-folder
                reference — where both the old and the new value must
                keep being recognized going forward.
    retain      A stable internal identifier that is not renamed at all
                (e.g. the OS keyring credential-store service name).
    historical  A citation inside a frozen/completed record (a
                docs/superpowers design doc, or a reference to a
                local-only or gitignored past-planning file) that is
                never retroactively edited.
    external    A surface outside this repository's control (a GitHub
                URL, or a mention of the separate FolioOS_Sites
                deployment repo).

This script is the durable, re-runnable record of the classification
decisions made in plan/FOLIO_BOARD_RENAME_PLAN.md §4 and §5 (that plan
is a local, gitignored planning document and is not part of this
worktree's tracked files — the CLASSIFICATION_RULES table below is the
source of truth once the plan folder is gone). Per plan §11.1 it is
meant to be run again after 0.6 work resumes, and again at the 0.6
release gate, to catch any old-name text introduced by habit after the
rename lands.

Two modes, two different questions, two different exit contracts:

    Gate A / default mode
        Question: "did every occurrence get classified?" Used while the
        old name is still everywhere on purpose (nothing has been
        renamed yet). A large `replace` count is expected and is NOT a
        failure — `replace` just means "this text will be swapped to
        the new name in a later phase." Exit code is non-zero iff
        `unclassified_count` > 0.

    --expect-clean mode
        Question: "is the old name gone from everywhere it was supposed
        to be renamed?" Used AFTER the rename has actually shipped, per
        plan §11.1, where a `replace`-bucket hit no longer means "will
        be renamed later" — it means "should already be gone and isn't"
        (old name reintroduced by habit, or a rename step missed). Exit
        code is non-zero if `unclassified_count` > 0 OR the `replace`
        bucket is non-empty. `dual-read` / `retain` / `historical` /
        `external` occurrences are expected to survive the rename
        permanently, so they are reported as informational counts and
        never fail this mode.

Usage (see docs/rename-inventory.md "Re-running this check" for the
three concrete run contexts and which mode each one uses):
    py -3 scripts/check_name_inventory.py                   # Gate A: human-readable
    py -3 scripts/check_name_inventory.py --json             # Gate A: machine-readable
    py -3 scripts/check_name_inventory.py --expect-clean     # post-rename: human-readable
    py -3 scripts/check_name_inventory.py --expect-clean --json  # post-rename: machine-readable

Run-context -> mode mapping:
    Gate A (Phase A, now — old name still everywhere on purpose)
        -> default mode, no flag.
    Rename merge (Phase F, first run — right after the rename branch
    merges into 0.6; plan §11.1 "리네이밍을 0.6에 병합할 때 한 번")
        -> --expect-clean
    0.6 release gate (Phase F, second run — after 0.6 work has resumed
    and shipped; plan §11.1 "0.6 발행 게이트에서 한 번 더")
        -> --expect-clean
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# The old-name pattern. Deliberately has NO word boundaries: it must also
# match inside identifiers like `folio_os_roadmap_post_v1.md` (a citation
# to a local planning file) and `.folio-qa-owned` markers, not just whole
# words. This is the same pattern used to build the manual inventory this
# script's rule table was validated against (376 occurrences / 135 files
# as of 2026-09-08 on branch codex/folio-board-rename).
OLD_NAME_PATTERN = re.compile(r"folio[ _-]?os", re.IGNORECASE)

BUCKETS = ("replace", "dual-read", "retain", "historical", "external")

# Directories/files never scanned: local planning notes (gitignored, absent
# from a fresh worktree), dependency trees, VCS internals, and QA output
# directories that are regenerated per run and never meant to be committed.
EXCLUDED_PATH_PREFIXES = (
    "plan/",
    "node_modules/",
    ".git/",
    "test-results/",
    "artifacts/",
    "review-captures/",
    "web/review-captures/",
    ".playwright-mcp/",
)

# This script's own two record files are exempt from the scan — deliberately,
# not by oversight. They are the durable, permanent record of where the old
# name lived and how each occurrence was classified: this file's own
# CLASSIFICATION_RULES table (rule ids, "reason" strings, and the
# OLD_NAME_PATTERN source itself all spell the old name on purpose), and
# docs/rename-inventory.md's occurrence tables and per-bucket prose. Neither
# file's old-name text is ever meant to be renamed:
#   - If they were scanned like ordinary source, every hit inside them would
#     fall to the `replace-default` rule (neither file matches any
#     dual-read/retain/historical/external content or path rule), inflating
#     the totals with the checker counting itself.
#   - Worse, that misclassification would poison --expect-clean (see main()):
#     a post-rename run would see this file's own "replace" hits and refuse
#     to exit 0 forever, demanding the classifier's rule table and the
#     historical inventory report be rewritten to erase the very record they
#     exist to preserve.
# Excluded by exact path (not a directory prefix), so any other file later
# added under scripts/ or docs/ is still scanned normally.
RENAME_RECORD_FILES = (
    "scripts/check_name_inventory.py",
    "docs/rename-inventory.md",
)


def is_excluded(rel_posix: str) -> bool:
    if rel_posix.startswith(".tmp-"):
        return True
    if rel_posix in RENAME_RECORD_FILES:
        return True
    for prefix in EXCLUDED_PATH_PREFIXES:
        if rel_posix == prefix.rstrip("/") or rel_posix.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Classification rules
#
# Rules are checked IN ORDER; the first rule whose conditions all hold wins.
# A rule matches when:
#   - path_exact is empty, OR the file's repo-relative posix path is in it; AND
#   - path_prefixes is empty, OR the path starts with one of them; AND
#   - content_pattern is None, OR it searches successfully against the
#     occurrence's line text (for a filename-only occurrence, the "line
#     text" is the relative path itself).
#
# Keep this table readable: one row per decision, with a short "why" that
# points back to the plan section it encodes. When the repo grows a new
# occurrence that no rule here covers, the script exits non-zero and
# names it — add a row rather than widening an existing one blindly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    id: str
    bucket: str
    reason: str
    path_exact: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    content_pattern: Optional[re.Pattern] = None

    def matches(self, rel_posix: str, line_text: str) -> bool:
        # path_exact and path_prefixes are OR'd together (either kind of
        # path match is sufficient) whenever at least one of them is set;
        # content_pattern, if set, is an additional AND condition on top.
        if self.path_exact or self.path_prefixes:
            path_ok = rel_posix in self.path_exact or any(
                rel_posix.startswith(p) for p in self.path_prefixes
            )
            if not path_ok:
                return False
        if self.content_pattern is not None and not self.content_pattern.search(line_text):
            return False
        return True


def _ci(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


CLASSIFICATION_RULES: tuple[Rule, ...] = (
    # -- Highest priority: frozen historical records, checked by path alone
    # so nothing inside them (even a generated_by/github.com/etc. line) is
    # ever retroactively touched. Plan §5 "역사 문서" row.
    Rule(
        id="historical-superpowers",
        bucket="historical",
        reason=(
            "Completed design/plan record under docs/superpowers/ — plan §5 "
            "'역사 문서' row: never retroactively edited, regardless of what "
            "old-name form it contains."
        ),
        path_prefixes=("docs/superpowers/",),
    ),
    # -- Content rules: a specific VALUE or context that changes the bucket
    # away from the plain-text default, wherever in the tree it appears.
    Rule(
        id="provenance-generated-by",
        bucket="dual-read",
        reason=(
            "generated_by provenance value (Obsidian/Notion export writer, "
            "importer self-reference classifier, Thesis Delta service, or "
            "the deepResearchPayload.ts::parseLedger comparison) — old and "
            "new self-generated markers must both keep being recognized "
            "(plan §4.3)."
        ),
        content_pattern=_ci(r"generated_?by"),
    ),
    Rule(
        id="provenance-compiled-marker",
        bucket="dual-read",
        reason=(
            "Bare 'folioos' literal in a minified comparison inside the "
            "committed build output (public/react/folio-react.js) — mirrors "
            "web/src/app/deepResearchPayload.ts::parseLedger's normalized "
            "alias check and must be rebuilt in step with it (plan §4.3)."
        ),
        content_pattern=re.compile(r"""["']folioos["']"""),
    ),
    Rule(
        id="external-github-url",
        bucket="external",
        reason=(
            "GitHub repository URL (jh-folio/FolioOS) — external hosting "
            "surface; the repo slug transfer is Phase E, performed at the "
            "same time as the display-name change but gated on its own "
            "checklist (plan §1, §6 Phase E)."
        ),
        content_pattern=_ci(r"github\.com"),
    ),
    Rule(
        id="external-folio-os-sites",
        bucket="external",
        reason=(
            "Mention of the separate FolioOS_Sites deployment repository — "
            "lives outside this repo; inventoried on its own at Phase E "
            "(plan §3 비목표, §6 Phase E), not part of this checklist's scope."
        ),
        content_pattern=re.compile(r"FolioOS_Sites"),
    ),
    Rule(
        id="historical-local-plan-citation",
        bucket="historical",
        reason=(
            "Citation to a local-only or gitignored past-planning file "
            "(.planning/... or folio_os_roadmap_post_v1.md) — the file "
            "itself is explicitly noted as not tracked in this repo, so the "
            "citation names a frozen record rather than live code (plan §5 "
            "'역사 문서' row)."
        ),
        content_pattern=re.compile(r"\.planning/|folio_os_roadmap_post_v1"),
    ),
    Rule(
        id="retain-keyring-service-name",
        bucket="retain",
        reason=(
            "OS keyring/credential-store service name literal — plan §4.2 "
            "keeps this so a rename does not orphan API keys users already "
            "stored under the old service name."
        ),
        content_pattern=re.compile(r"SECRET_STORE_SERVICE"),
    ),
    Rule(
        id="dual-read-documents-workspace-folder",
        bucket="dual-read",
        reason=(
            "~/Documents/FolioOS workspace-folder reference (discovery "
            "order, DOCUMENTS_FOLDER_NAME, documentsPath, or a workspace "
            "relocation test) — per plan §4.4, folder discovery must keep "
            "checking the old folder name after rename while the move "
            "destination becomes the new name only."
        ),
        content_pattern=re.compile(r"document", re.IGNORECASE),
    ),
    Rule(
        id="replace-user-agent",
        bucket="replace",
        reason=(
            "Network User-Agent identifier (HTTP header value, USER_AGENT "
            "constant, or the SEC_USER_AGENT example default) — plan §4.1 "
            "puts this in the immediately-changed display surfaces: new "
            "runs send FolioBoard/... from Phase D onward, with no need to "
            "keep recognizing the old string anywhere (plan §10 decision 2)."
        ),
        content_pattern=_ci(r"user[-_]?agent"),
    ),
    # -- Path-specific overrides for occurrences a content rule can't reach
    # (no 'document' text on the line, but the same workspace-relocation
    # test family).
    Rule(
        id="dual-read-index-cache-relocation-test",
        bucket="dual-read",
        reason=(
            "Indexing test exercises workspace_root() pointed at a "
            "relocated folder literally named 'FolioOS' — same "
            "workspace-relocation family as the Documents discovery tests "
            "in features/common/tests/, even on the one line that omits "
            "the 'Documents' path segment (plan §4.4)."
        ),
        path_exact=("features/common/research_library/indexing/tests/test_index_cache.py",),
    ),
    # -- Default: everything else under a directory/file family this
    # inventory has actually reviewed. A path that matches none of these
    # falls through to "unclassified" so a genuinely new location gets a
    # human decision instead of a silent guess.
    Rule(
        id="replace-default",
        bucket="replace",
        reason=(
            "Default: user-facing display text, screen-reader label, "
            "console/log message, docstring, code comment, LLM prompt "
            "text, or documentation prose that simply names the product — "
            "swapped to the new display name with the corresponding Phase "
            "B/D work; no backward-compatibility read was identified for "
            "this occurrence (plan §5)."
        ),
        path_prefixes=(
            "features/",
            "web/",
            "docs/",
            "scripts/",
            "tests/",
            "public/",
            ".github/",
        ),
        path_exact=(
            "README.md",
            "README.ko.md",
            "AGENTS.md",
            "CLAUDE.md",
            "SECURITY.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "installation.md",
            ".env.example",
            "app.py",
            "start.ps1",
            "start.sh",
            "release-manifest.json",
        ),
    ),
)


@dataclass
class Occurrence:
    path: str
    line_no: Optional[int]  # None for a filename-only occurrence
    line_text: str
    matched: str
    bucket: Optional[str] = None
    rule_id: Optional[str] = None
    reason: Optional[str] = None

    def location(self) -> str:
        if self.line_no is None:
            return f"{self.path}:<filename>"
        return f"{self.path}:{self.line_no}"


def classify(path: str, line_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    for rule in CLASSIFICATION_RULES:
        if rule.matches(path, line_text):
            return rule.bucket, rule.id, rule.reason
    return None, None, None


def list_tracked_files() -> list[str]:
    """Return repo-relative posix paths, preferring `git ls-files`.

    Falls back to a plain filesystem walk (with a conservative exclude
    list covering the same gitignored/personal-data directories) if git
    is unavailable, so the script still runs outside a git checkout.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        raw = result.stdout.decode("utf-8", errors="surrogateescape")
        return [p for p in raw.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        pass

    fallback_exclude_dirs = {
        ".git",
        "node_modules",
        "plan",
        "data",
        "research-inbox",
        "config",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "dist",
        "test-results",
        "artifacts",
        "review-captures",
        ".playwright-mcp",
        ".agents",
        ".claude",
        ".superpowers",
        ".gjc",
        ".planning",
        ".tools",
    }
    paths: list[str] = []
    for candidate in REPO_ROOT.rglob("*"):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(REPO_ROOT)
        if any(part in fallback_exclude_dirs or part.startswith(".tmp-") for part in rel.parts):
            continue
        paths.append(rel.as_posix())
    return paths


def read_text_lines(abs_path: Path) -> Optional[list[str]]:
    try:
        raw = abs_path.read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.splitlines()


def scan_repo() -> list[Occurrence]:
    occurrences: list[Occurrence] = []
    for rel_posix in sorted(list_tracked_files()):
        if is_excluded(rel_posix):
            continue

        # Filename occurrence (path itself spells the old name).
        for match in OLD_NAME_PATTERN.finditer(rel_posix):
            occurrences.append(
                Occurrence(path=rel_posix, line_no=None, line_text=rel_posix, matched=match.group(0))
            )

        abs_path = REPO_ROOT / rel_posix
        lines = read_text_lines(abs_path)
        if not lines:
            continue
        for line_no, line_text in enumerate(lines, start=1):
            for match in OLD_NAME_PATTERN.finditer(line_text):
                occurrences.append(
                    Occurrence(path=rel_posix, line_no=line_no, line_text=line_text, matched=match.group(0))
                )

    for occ in occurrences:
        bucket, rule_id, reason = classify(occ.path, occ.line_text)
        occ.bucket = bucket
        occ.rule_id = rule_id
        occ.reason = reason

    return occurrences


def build_report(occurrences: list[Occurrence]) -> dict:
    by_bucket: dict[str, list[Occurrence]] = {b: [] for b in BUCKETS}
    unclassified: list[Occurrence] = []
    for occ in occurrences:
        if occ.bucket is None:
            unclassified.append(occ)
        else:
            by_bucket[occ.bucket].append(occ)

    files_by_bucket = {
        bucket: sorted({occ.path for occ in occs}) for bucket, occs in by_bucket.items()
    }

    return {
        "total_occurrences": len(occurrences),
        "total_files": len({occ.path for occ in occurrences}),
        "bucket_counts": {b: len(by_bucket[b]) for b in BUCKETS},
        "bucket_file_counts": {b: len(files_by_bucket[b]) for b in BUCKETS},
        "unclassified_count": len(unclassified),
        "occurrences": occurrences,
        "by_bucket": by_bucket,
        "files_by_bucket": files_by_bucket,
        "unclassified": unclassified,
    }


def print_human_report(report: dict, expect_clean: bool) -> None:
    mode_label = "--expect-clean (post-rename verification)" if expect_clean else "default (Gate A)"
    print(f"Folio OS name inventory — {report['total_occurrences']} occurrences across {report['total_files']} files")
    print(f"Mode: {mode_label}\n")
    width = max(len(b) for b in BUCKETS)
    for bucket in BUCKETS:
        count = report["bucket_counts"][bucket]
        file_count = report["bucket_file_counts"][bucket]
        print(f"  {bucket.ljust(width)} : {count:>4} occurrences in {file_count:>3} files")

    if report["unclassified_count"]:
        print(f"\nUNCLASSIFIED: {report['unclassified_count']} occurrence(s) matched no rule.\n")
        for occ in report["unclassified"]:
            snippet = occ.line_text.strip()
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            print(f"  {occ.location()}: {snippet}")
        print(
            "\nAdd a CLASSIFICATION_RULES entry (or extend an existing default "
            "prefix) in scripts/check_name_inventory.py for the location(s) above."
        )

    if expect_clean:
        replace_count = report["bucket_counts"]["replace"]
        survivors = ", ".join(
            f"{b}={report['bucket_counts'][b]}" for b in ("dual-read", "retain", "historical", "external")
        )
        print(
            f"\n{survivors} are expected to survive the rename permanently and "
            "are informational only — they do not fail --expect-clean."
        )
        if replace_count or report["unclassified_count"]:
            print(
                f"\n--expect-clean: FAIL. {replace_count} `replace`-bucket "
                f"occurrence(s) (old-name text that should already have been "
                f"renamed away) and {report['unclassified_count']} unclassified "
                "occurrence(s) found. Run without --json to see `replace` rows, "
                "or --json for the full occurrence list."
            )
        else:
            print("\n--expect-clean: PASS. No `replace`-bucket or unclassified occurrences remain.")
    else:
        if report["unclassified_count"]:
            print("\nGate A: FAIL. See UNCLASSIFIED occurrences above.")
        else:
            print("\nAll occurrences classified. Gate A: PASS.")


def occurrence_to_json(occ: Occurrence) -> dict:
    return {
        "path": occ.path,
        "line": occ.line_no,
        "matched": occ.matched,
        "line_text": occ.line_text,
        "bucket": occ.bucket,
        "rule_id": occ.rule_id,
        "reason": occ.reason,
    }


def print_json_report(report: dict, expect_clean: bool) -> None:
    payload = {
        "mode": "expect-clean" if expect_clean else "gate-a",
        "total_occurrences": report["total_occurrences"],
        "total_files": report["total_files"],
        "bucket_counts": report["bucket_counts"],
        "bucket_file_counts": report["bucket_file_counts"],
        "unclassified_count": report["unclassified_count"],
        "occurrences": [occurrence_to_json(o) for o in report["occurrences"]],
    }
    if expect_clean:
        # In this mode, dual-read/retain/historical/external are expected to
        # survive the rename permanently and are informational only; only
        # `replace` (old-name text that should already be gone) and
        # unclassified occurrences make `passed` false. See module docstring.
        payload["passed"] = not (report["bucket_counts"]["replace"] or report["unclassified_count"])
    else:
        payload["passed"] = not report["unclassified_count"]
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def main() -> int:
    # Windows consoles often default to a legacy code page (e.g. cp949/cp1252)
    # that cannot encode the em dashes used in this file's report text and
    # rule reasons. Reconfigure stdout/stderr to UTF-8 where possible so the
    # script behaves the same on Windows and POSIX terminals.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of the human report.")
    parser.add_argument(
        "--expect-clean",
        action="store_true",
        help=(
            "Post-rename verification mode (plan §11.1): exit non-zero if any "
            "occurrence is in the `replace` bucket or unclassified. "
            "dual-read/retain/historical/external occurrences are expected to "
            "survive the rename permanently and are reported as informational "
            "counts, never a failure. Use this at the rename-merge check and "
            "again at the 0.6 release gate. Without this flag, the default "
            "Gate A mode only checks that every occurrence was classified — "
            "a large `replace` count is expected there and is not a failure."
        ),
    )
    args = parser.parse_args()

    occurrences = scan_repo()
    report = build_report(occurrences)

    if args.json:
        print_json_report(report, expect_clean=args.expect_clean)
    else:
        print_human_report(report, expect_clean=args.expect_clean)

    if args.expect_clean:
        failed = report["unclassified_count"] or report["bucket_counts"]["replace"]
        return 1 if failed else 0
    return 1 if report["unclassified_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
