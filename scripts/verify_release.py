#!/usr/bin/env python3
"""Verify a Folio Board release package artifact.

The verifier checks the packaged directory, not the repository checkout. It is
intentionally stricter than the packager so it can catch hand-edited artifacts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "release-manifest.json"
FORBIDDEN_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".log"}
FORBIDDEN_KEY_SUFFIXES = {".pem", ".key"}
EXCLUDED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
EXCLUDED_PARTS = {"tests"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
HOST_ONLY_QA_HELPERS = {"qa_server_supervisor.py", "qa_fault_proxy.py"}
GITLEAKS_VERSION = "8.30.1"
GITLEAKS_TIMEOUT_SECONDS = 120
GITLEAKS_REDACTION_MARKERS = {"REDACTED", "[REDACTED]"}


def _path_parts(rel: str) -> tuple[str, ...]:
    return Path(rel).parts


def _require_safe_relative(rel: str, section: str) -> None:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"Unsafe path in {section}: {rel}")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key in ("packageName", "runtimeFiles", "runtimeDirectories", "emptyDirectories", "forbiddenPaths"):
        if key not in manifest:
            raise SystemExit(f"Manifest missing required key: {key}")
    for section in ("runtimeFiles", "runtimeDirectories", "emptyDirectories", "forbiddenPaths"):
        if not isinstance(manifest[section], list):
            raise SystemExit(f"Manifest section must be a list: {section}")
        for rel in manifest[section]:
            _require_safe_relative(str(rel), section)
    return manifest


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_dev_or_cache_file(rel: str, path: Path) -> bool:
    parts = set(_path_parts(rel))
    return (
        bool(parts & EXCLUDED_DIR_NAMES)
        or bool(parts & EXCLUDED_PARTS)
        or path.name.endswith(".test.js")
        or path.suffix.lower() in EXCLUDED_SUFFIXES
    )


def find_missing_required_paths(release_dir: Path, manifest: dict) -> list[str]:
    issues: list[str] = []
    for rel in manifest["runtimeFiles"]:
        path = release_dir / rel
        if not path.is_file():
            issues.append(f"Missing required file: {rel}")
    for rel in manifest["runtimeDirectories"]:
        path = release_dir / rel
        if not path.is_dir():
            issues.append(f"Missing required directory: {rel}")
    for rel in manifest["emptyDirectories"]:
        path = release_dir / rel
        if not path.is_dir():
            issues.append(f"Missing empty runtime directory: {rel}")
    if not (release_dir / "release-manifest.json").is_file():
        issues.append("Missing copied release-manifest.json")
    if not (release_dir / "BUILD.json").is_file():
        issues.append("Missing BUILD.json")
    return issues


def find_forbidden_paths(release_dir: Path, manifest: dict) -> list[str]:
    issues: list[str] = []
    forbidden = set(str(path).replace("\\", "/").strip("/") for path in manifest["forbiddenPaths"])
    forbidden_names = {Path(path).name for path in forbidden if path != "config"}
    empty_roots = [release_dir / rel for rel in manifest["emptyDirectories"]]

    for rel in sorted(forbidden):
        if (release_dir / rel).exists():
            issues.append(f"Forbidden path exists: {rel}")

    for path in release_dir.rglob("*"):
        rel = _rel(path, release_dir)
        parts = set(path.parts)
        rel_parts = set(_path_parts(rel))
        if rel_parts & forbidden_names:
            issues.append(f"Forbidden path component exists: {rel}")
        if _is_dev_or_cache_file(rel, path):
            issues.append(f"Development/cache path exists: {rel}")
        if path.is_file():
            if path.name.lower() in HOST_ONLY_QA_HELPERS:
                issues.append(f"Host-only QA helper must not ship: {rel}")
            suffix = path.suffix.lower()
            if path.name.lower() == ".env":
                issues.append(f"Forbidden environment file exists: {rel}")
            if suffix in FORBIDDEN_SUFFIXES:
                issues.append(f"Forbidden generated/database/log file exists: {rel}")
            if suffix in FORBIDDEN_KEY_SUFFIXES:
                issues.append(f"Potential private key file exists: {rel}")
            if any(_is_under(path, root) for root in empty_roots):
                issues.append(f"Runtime data directory must be empty: {rel}")
    return sorted(set(issues))


def find_unexpected_files(release_dir: Path, manifest: dict) -> list[str]:
    issues: list[str] = []
    allowed_files = {str(rel).replace("\\", "/") for rel in manifest["runtimeFiles"]}
    allowed_files.add("release-manifest.json")
    allowed_files.add("BUILD.json")
    allowed_dirs = [release_dir / rel for rel in manifest["runtimeDirectories"]]

    for path in release_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = _rel(path, release_dir)
        if rel in allowed_files:
            continue
        if any(_is_under(path, root) for root in allowed_dirs):
            continue
        issues.append(f"Unexpected file in release artifact: {rel}")
    return issues


def _gitleaks_report_is_redacted(report: list[object]) -> bool:
    for finding in report:
        if not isinstance(finding, dict):
            return False
        secret = finding.get("Secret")
        match = finding.get("Match")
        if not isinstance(secret, str) or secret.strip().upper() not in GITLEAKS_REDACTION_MARKERS:
            return False
        if not isinstance(match, str) or not any(marker in match.upper() for marker in GITLEAKS_REDACTION_MARKERS):
            return False
    return True


def run_gitleaks_scan(release_dir: Path) -> list[str]:
    exe = shutil.which("gitleaks")
    if not exe:
        return ["Gitleaks is required for release verification but was not found on PATH."]
    try:
        version_result = subprocess.run(
            [exe, "version", "--redact=100"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=GITLEAKS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ["Gitleaks version verification timed out; release verification failed closed."]
    if version_result.returncode != 0 or version_result.stdout.strip() != GITLEAKS_VERSION:
        return [f"Gitleaks {GITLEAKS_VERSION} is required for release verification."]

    with tempfile.TemporaryDirectory(prefix="folio-gitleaks-report-") as temporary:
        attempt_directory = Path(temporary)
        (attempt_directory / ".folio-security-owned.json").write_text(
            json.dumps({"owner": "verify_release", "state": "scanning"}, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        report_path = attempt_directory / "findings.json"
        try:
            result = subprocess.run(
                [
                    exe,
                    "dir",
                    "--redact=100",
                    "--report-format=json",
                    f"--report-path={report_path}",
                    str(release_dir),
                ],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=GITLEAKS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return ["Gitleaks artifact scan timed out; release verification failed closed."]

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ["Gitleaks did not produce a valid sanitized JSON report; release verification failed closed."]
        if not isinstance(report, list):
            return ["Gitleaks JSON report has an invalid shape; release verification failed closed."]
        finding_count = len(report)
        if finding_count and not _gitleaks_report_is_redacted(report):
            return ["Gitleaks report failed redaction validation; release verification failed closed."]
        if result.returncode == 0 and finding_count == 0:
            return []
        if finding_count:
            return [f"Gitleaks found {finding_count} potential secret(s) in the release artifact."]
        return ["Gitleaks scan failed without actionable sanitized findings; release verification failed closed."]


def find_build_metadata_issues(release_dir: Path, expected_commit: str | None) -> list[str]:
    issues: list[str] = []
    version_path = release_dir / "VERSION"
    build_path = release_dir / "BUILD.json"
    if not version_path.is_file() or not build_path.is_file():
        return issues
    try:
        version = version_path.read_text(encoding="utf-8").strip()
        build = json.loads(build_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["BUILD.json or VERSION is unreadable."]
    if not isinstance(build, dict) or set(build) != {"version", "commit", "builtAt"}:
        return ["BUILD.json must contain exactly version, commit, and builtAt."]
    if build["version"] != version:
        issues.append("BUILD.json version does not match VERSION.")
    commit = str(build["commit"])
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        issues.append("BUILD.json commit is not a full lowercase Git SHA.")
    if expected_commit is not None and commit != expected_commit:
        issues.append("BUILD.json commit does not match the expected source commit.")
    built_at = str(build["builtAt"])
    try:
        parsed = dt.datetime.fromisoformat(built_at.removesuffix("Z") + "+00:00")
    except ValueError:
        issues.append("BUILD.json builtAt is not a UTC-Z instant.")
    else:
        if not built_at.endswith("Z") or parsed.utcoffset() != dt.timedelta(0):
            issues.append("BUILD.json builtAt is not a UTC-Z instant.")
    return issues


def derive_source_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            encoding="ascii",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    commit = result.stdout.strip().lower()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None
    return commit


def verify_release(
    release_dir: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    run_gitleaks: bool = True,
    expected_commit: str | None = None,
) -> list[str]:
    release_dir = release_dir.resolve()
    if not release_dir.is_dir():
        return [f"Release directory does not exist: {release_dir}"]
    manifest = load_manifest(manifest_path)
    issues = find_missing_required_paths(release_dir, manifest)
    issues.extend(find_forbidden_paths(release_dir, manifest))
    issues.extend(find_unexpected_files(release_dir, manifest))
    bound_commit = expected_commit or derive_source_commit()
    if bound_commit is None:
        issues.append("Unable to bind BUILD.json to the source workspace commit.")
    else:
        issues.extend(find_build_metadata_issues(release_dir, bound_commit))
    if run_gitleaks:
        issues.extend(run_gitleaks_scan(release_dir))
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a Folio Board release package directory.")
    parser.add_argument("--release-dir", type=Path, required=True, help="Release directory to verify.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Release manifest path.")
    parser.add_argument("--skip-gitleaks", action="store_true", help="Skip Gitleaks scan for tests or diagnostics.")
    parser.add_argument("--expected-commit", help="Require BUILD.json to identify this full Git SHA.")
    args = parser.parse_args()

    issues = verify_release(
        args.release_dir,
        args.manifest,
        run_gitleaks=not args.skip_gitleaks,
        expected_commit=args.expected_commit,
    )
    if issues:
        for issue in issues:
            print(issue, file=__import__("sys").stderr)
        return 1
    print(f"Verified release artifact: {args.release_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
