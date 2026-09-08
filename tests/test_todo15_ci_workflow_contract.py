from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

EXPECTED_OSES = {"windows-2022", "macos-14", "ubuntu-24.04"}
ACTION_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}
GITLEAKS_CHECKSUMS = {
    "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
    "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
}
LOCK_COMPILE = (
    "python -m uv pip compile --universal --python-version 3.12 --resolution highest "
    "--generate-hashes --exclude-newer 2026-08-08T00:00:00Z"
)
LOCK_COMPILE_FULL = f"{LOCK_COMPILE} --output-file requirements.lock.py312.txt requirements.txt"
TEST_LOCK_COMPILE_FULL = (
    f"{LOCK_COMPILE} --output-file requirements-test.lock.py312.txt requirements-test.txt"
)
HASH_INSTALL = "python -m uv pip install --system --require-hashes -r requirements-test.lock.py312.txt"
BOOTSTRAP_INSTALL = (
    "python -m pip install --require-hashes --no-deps -r requirements-bootstrap.lock.txt"
)


COMPLIANT_WORKFLOW = r"""name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test-matrix:
    name: Test (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [windows-2022, macos-14, ubuntu-24.04]
    env:
      UV_NO_CONFIG: "1"
      GITLEAKS_VERSION: "8.30.1"
      GITLEAKS_WINDOWS_SHA256: d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e
      GITLEAKS_LINUX_SHA256: 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
      GITLEAKS_DARWIN_X64_SHA256: dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709
      GITLEAKS_DARWIN_ARM64_SHA256: b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          fetch-depth: 0
          ref: ${{ github.sha }}
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.12.10"
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020
        with:
          node-version: "22.17.0"
      - name: Regenerate runtime and test locks twice, normalize LF, and byte-compare
        run: |
          python -m pip install --require-hashes --no-deps -r requirements-bootstrap.lock.txt
          python -c "from shutil import copyfile; copyfile('requirements.lock.py312.txt', 'requirements.lock.py312.committed.txt')"
          python -c "from shutil import copyfile; copyfile('requirements-test.lock.py312.txt', 'requirements-test.lock.py312.committed.txt')"
          python -m uv pip compile --universal --python-version 3.12 --resolution highest --generate-hashes --exclude-newer 2026-08-08T00:00:00Z --output-file requirements.lock.py312.txt requirements.txt
          python -m uv pip compile --universal --python-version 3.12 --resolution highest --generate-hashes --exclude-newer 2026-08-08T00:00:00Z --output-file requirements-test.lock.py312.txt requirements-test.txt
          python scripts/normalize_lock_lf.py requirements.lock.py312.txt
          python scripts/normalize_lock_lf.py requirements-test.lock.py312.txt
          python -c "from shutil import copyfile; copyfile('requirements.lock.py312.txt', 'requirements.lock.py312.first.txt')"
          python -c "from shutil import copyfile; copyfile('requirements-test.lock.py312.txt', 'requirements-test.lock.py312.first.txt')"
          python -m uv pip compile --universal --python-version 3.12 --resolution highest --generate-hashes --exclude-newer 2026-08-08T00:00:00Z --output-file requirements.lock.py312.txt requirements.txt
          python -m uv pip compile --universal --python-version 3.12 --resolution highest --generate-hashes --exclude-newer 2026-08-08T00:00:00Z --output-file requirements-test.lock.py312.txt requirements-test.txt
          python scripts/normalize_lock_lf.py requirements.lock.py312.txt
          python scripts/normalize_lock_lf.py requirements-test.lock.py312.txt
          python -c "from shutil import copyfile; copyfile('requirements.lock.py312.txt', 'requirements.lock.py312.second.txt')"
          python -c "from shutil import copyfile; copyfile('requirements-test.lock.py312.txt', 'requirements-test.lock.py312.second.txt')"
          python scripts/compare_lock_bytes.py requirements.lock.py312.committed.txt requirements.lock.py312.first.txt requirements.lock.py312.second.txt
          python scripts/compare_lock_bytes.py requirements-test.lock.py312.committed.txt requirements-test.lock.py312.first.txt requirements-test.lock.py312.second.txt
          python -m uv pip install --system --require-hashes -r requirements-test.lock.py312.txt
      - name: Install checksum-verified Gitleaks 8.30.1
        run: python scripts/install_gitleaks.py --version 8.30.1 --verify-checksum
      - name: Scan full Git history
        run: gitleaks git --redact=100 --report-path .qa/gitleaks/history.sarif
      - run: python -m pytest features tests -q
      - run: npm ci
        working-directory: web
      - run: npm run build
        working-directory: web

  release-package:
    name: Canonical Ubuntu release package
    needs: [test-matrix]
    runs-on: ubuntu-24.04
    env:
      GITLEAKS_VERSION: "8.30.1"
      GITLEAKS_LINUX_SHA256: 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          fetch-depth: 0
          ref: ${{ github.sha }}
      - name: Install checksum-verified Gitleaks 8.30.1
        run: python scripts/install_gitleaks.py --version 8.30.1 --verify-checksum
      - name: Build and verify canonical source-only package
        run: |
          python scripts/package_release.py --output dist/release
          python scripts/verify_release.py --release-dir dist/release/FolioBoard-v0.2.0 --expected-commit "${{ github.sha }}"
          gitleaks dir dist/release/FolioBoard-v0.2.0 --redact=100 --report-path .qa/gitleaks/artifact.sarif
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
        with:
          name: FolioBoard-v0.2.0
          path: dist/release/FolioBoard-v0.2.0.zip
"""


def _job_blocks(source: str) -> dict[str, str]:
    jobs_match = re.search(r"(?m)^jobs:\s*$", source)
    if not jobs_match:
        return {}
    jobs_source = source[jobs_match.end() :]
    matches = list(re.finditer(r"(?m)^  ([A-Za-z0-9_-]+):\s*$", jobs_source))
    return {
        match.group(1): jobs_source[match.start() : matches[index + 1].start() if index + 1 < len(matches) else None]
        for index, match in enumerate(matches)
    }


def _inline_list(block: str, key: str) -> list[str]:
    match = re.search(rf"(?m)^\s+{re.escape(key)}:\s*\[([^\]]*)\]\s*$", block)
    if not match:
        return []
    return [item.strip().strip("'\"") for item in match.group(1).split(",") if item.strip()]


def workflow_contract_issues(source: str) -> list[str]:
    issues: list[str] = []
    jobs = _job_blocks(source)
    matrix_jobs = {job_id: block for job_id, block in jobs.items() if re.search(r"(?m)^\s+matrix:\s*$", block)}
    if len(matrix_jobs) != 1:
        issues.append("exactly one test matrix job is required")
        matrix_id, matrix = "", ""
    else:
        matrix_id, matrix = next(iter(matrix_jobs.items()))

    if set(_inline_list(matrix, "os")) != EXPECTED_OSES or len(_inline_list(matrix, "os")) != 3:
        issues.append("matrix OS set must be exactly windows-2022, macos-14, ubuntu-24.04")
    if not re.search(r"(?m)^\s+runs-on:\s*\$\{\{\s*matrix\.os\s*\}\}\s*$", matrix):
        issues.append("test matrix must run on matrix.os")

    release = jobs.get("release-package", "")
    if not release:
        issues.append("exact release-package job id is required")
    if not re.search(r"(?m)^\s+runs-on:\s*ubuntu-24\.04\s*$", release):
        issues.append("release-package must run on canonical ubuntu-24.04")
    needs = _inline_list(release, "needs")
    if not matrix_id or needs != [matrix_id]:
        issues.append("release-package must need the complete matrix job")

    for action, pin in ACTION_PINS.items():
        uses = re.findall(rf"(?m)^\s*-?\s*uses:\s*{re.escape(action)}@([^\s#]+)", source)
        if not uses or any(value != pin for value in uses):
            issues.append(f"{action} must use immutable pin {pin}")

    checkout_count = len(re.findall(r"(?m)^\s*-?\s*uses:\s*actions/checkout@", source))
    if checkout_count != 2:
        issues.append("matrix and release-package must each have exactly one checkout")
    for job_id, block in ((matrix_id, matrix), ("release-package", release)):
        if block and not re.search(r"(?m)^\s+fetch-depth:\s*0\s*$", block):
            issues.append(f"{job_id} checkout must fetch full history")
        if block and not re.search(r"(?m)^\s+ref:\s*\$\{\{\s*github\.sha\s*\}\}\s*$", block):
            issues.append(f"{job_id} checkout must pin the triggering github.sha")

    if not re.search(r'(?m)^\s+python-version:\s*["\']?3\.12\.10["\']?\s*$', matrix):
        issues.append("matrix Python must be exactly 3.12.10")
    if not re.search(r'(?m)^\s+node-version:\s*["\']?22\.17\.0["\']?\s*$', matrix):
        issues.append("matrix Node must be exactly 22.17.0")
    if not re.search(r'(?m)^\s+UV_NO_CONFIG:\s*["\']?1["\']?\s*$', matrix):
        issues.append("matrix lock generation must set UV_NO_CONFIG=1")
    if BOOTSTRAP_INSTALL not in matrix:
        issues.append("matrix must hash-install the uv bootstrap lock")
    if matrix.count(LOCK_COMPILE_FULL) != 2:
        issues.append("matrix must run the exact universal compile twice")
    if matrix.count(TEST_LOCK_COMPILE_FULL) != 2:
        issues.append("matrix must run the exact universal test-lock compile twice")
    if matrix.count("normalize_lock_lf.py requirements.lock.py312.txt") != 2 or (
        "compare_lock_bytes.py requirements.lock.py312.committed.txt "
        "requirements.lock.py312.first.txt requirements.lock.py312.second.txt"
    ) not in matrix:
        issues.append("matrix must normalize LF and byte-compare both regenerated locks")
    if matrix.count("normalize_lock_lf.py requirements-test.lock.py312.txt") != 2 or (
        "compare_lock_bytes.py requirements-test.lock.py312.committed.txt "
        "requirements-test.lock.py312.first.txt requirements-test.lock.py312.second.txt"
    ) not in matrix:
        issues.append("matrix must normalize LF and byte-compare both regenerated test locks")
    if HASH_INSTALL not in matrix:
        issues.append("matrix must install the universal lock with hashes")

    if not re.search(r'(?m)^\s+GITLEAKS_VERSION:\s*["\']?8\.30\.1["\']?\s*$', matrix):
        issues.append("matrix Gitleaks version must be exactly 8.30.1")
    missing_checksums = {checksum for checksum in GITLEAKS_CHECKSUMS if checksum not in source.lower()}
    if missing_checksums:
        issues.append("all four pinned Gitleaks asset checksums must be present")
    if matrix.count("--verify-checksum") != 1 or release.count("--verify-checksum") != 1:
        issues.append("matrix and release-package must verify the Gitleaks asset checksum")
    gitleaks_scans = re.findall(r"(?m)^\s*(?:run:\s*)?(gitleaks\s+(?:git|dir|detect)[^\n]*)$", source)
    if len(gitleaks_scans) < 2 or any("--redact=100" not in command for command in gitleaks_scans):
        issues.append("every Gitleaks scan must use literal --redact=100")
    if not any(command.startswith("gitleaks git ") for command in gitleaks_scans):
        issues.append("matrix must scan full Git history")
    if not any(command.startswith("gitleaks dir ") for command in gitleaks_scans):
        issues.append("release-package must scan the extracted artifact")

    upload_jobs = [job_id for job_id, block in jobs.items() if "actions/upload-artifact@" in block]
    if upload_jobs != ["release-package"]:
        issues.append("release-package must be the one and only artifact uploader")
    if "python scripts/package_release.py --output dist/release" not in release:
        issues.append("release-package must build the canonical package once")
    if release.count("python scripts/package_release.py") != 1:
        issues.append("release-package must contain exactly one package build")
    if "--expected-commit \"${{ github.sha }}\"" not in release:
        issues.append("release verification must bind BUILD identity to github.sha")
    if "--force" in release or re.search(r"git\s+(?:status|diff)[^\n]*(?:commit|sha)", release, re.IGNORECASE):
        issues.append("release packaging must be independent of dirty-worktree/status-derived identity")
    return issues


def test_validator_accepts_exact_compliant_workflow_shape() -> None:
    assert workflow_contract_issues(COMPLIANT_WORKFLOW) == []


@pytest.mark.parametrize(
    ("case", "mutated"),
    [
        ("extra_os", COMPLIANT_WORKFLOW.replace("ubuntu-24.04]", "ubuntu-24.04, ubuntu-latest]", 1)),
        (
            "multiple_upload_jobs",
            COMPLIANT_WORKFLOW.replace("      - run: python -m pytest features tests -q", "      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a\n      - run: python -m pytest features tests -q"),
        ),
        ("mutable_checkout", COMPLIANT_WORKFLOW.replace(f"actions/checkout@{ACTION_PINS['actions/checkout']}", "actions/checkout@v4", 1)),
        ("mutable_setup_python", COMPLIANT_WORKFLOW.replace(f"actions/setup-python@{ACTION_PINS['actions/setup-python']}", "actions/setup-python@v6")),
        ("broad_python", COMPLIANT_WORKFLOW.replace('python-version: "3.12.10"', 'python-version: "3.12"')),
        ("broad_node", COMPLIANT_WORKFLOW.replace('node-version: "22.17.0"', 'node-version: "22"')),
        ("mutable_setup_node", COMPLIANT_WORKFLOW.replace(f"actions/setup-node@{ACTION_PINS['actions/setup-node']}", "actions/setup-node@v6")),
        ("mutable_upload", COMPLIANT_WORKFLOW.replace(f"actions/upload-artifact@{ACTION_PINS['actions/upload-artifact']}", "actions/upload-artifact@v4")),
        ("mutable_gitleaks", COMPLIANT_WORKFLOW.replace('GITLEAKS_VERSION: "8.30.1"', 'GITLEAKS_VERSION: "latest"', 1)),
        ("checksum_missing", COMPLIANT_WORKFLOW.replace(next(iter(GITLEAKS_CHECKSUMS)), "0" * 64)),
        ("redaction_missing", COMPLIANT_WORKFLOW.replace("gitleaks git --redact=100", "gitleaks git")),
        ("misleading_job_name", COMPLIANT_WORKFLOW.replace("  release-package:\n", "  release-package-looking:\n")),
        ("noncanonical_packager", COMPLIANT_WORKFLOW.replace("    runs-on: ubuntu-24.04\n    env:\n      GITLEAKS_VERSION", "    runs-on: ubuntu-latest\n    env:\n      GITLEAKS_VERSION")),
        ("matrix_need_missing", COMPLIANT_WORKFLOW.replace("    needs: [test-matrix]\n", "")),
        ("same_sha_missing", COMPLIANT_WORKFLOW.replace("          ref: ${{ github.sha }}\n", "", 1)),
        ("single_lock_regeneration", COMPLIANT_WORKFLOW.replace(f"          {LOCK_COMPILE_FULL}\n", "", 1)),
        ("test_lock_missing", COMPLIANT_WORKFLOW.replace(f"          {TEST_LOCK_COMPILE_FULL}\n", "", 1)),
        ("unhashed_install", COMPLIANT_WORKFLOW.replace("pip install --system --require-hashes", "pip install --system")),
        ("no_byte_compare", COMPLIANT_WORKFLOW.replace("compare_lock_bytes.py", "accept_lock_without_compare.py")),
        ("dirty_worktree_force", COMPLIANT_WORKFLOW.replace("package_release.py --output dist/release", "package_release.py --force --output dist/release")),
    ],
    ids=lambda value: value if isinstance(value, str) and "\n" not in value else "workflow",
)
def test_validator_rejects_malformed_workflow_variants(case: str, mutated: str) -> None:
    assert mutated != COMPLIANT_WORKFLOW, case
    assert workflow_contract_issues(mutated), case


def test_current_ci_workflow_satisfies_todo15_contract() -> None:
    issues = workflow_contract_issues(WORKFLOW.read_text(encoding="utf-8"))
    assert issues == [], "Todo 15 immutable CI contract gaps:\n- " + "\n- ".join(issues)


def test_test_dependency_input_includes_runtime_and_pytest() -> None:
    source = (ROOT / "requirements-test.txt").read_text(encoding="utf-8").splitlines()
    assert "-r requirements.txt" in source
    assert any(line.startswith("pytest==") for line in source)
