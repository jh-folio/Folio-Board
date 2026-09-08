import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
# **버전을 박아 두지 않는다.** 여기서 검사하는 것은 패키징이 도는가이지 어떤 숫자인가가
# 아니다. 박아 두면 릴리즈마다 이 파일도 같이 고쳐야 하고, 잊으면 CI가 판올림 커밋에서
# 실패한다 — 0.5.3에서 실제로 세 건이 그렇게 실패했다. 버전 자체의 계약은
# `tests/test_version_contract.py`가 따로 지킨다.
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
sys.path.insert(0, str(ROOT / "scripts"))

import verify_release as verifier  # noqa: E402


CURRENT_RELEASE_INPUTS = (
    "release-manifest.json",
    "requirements-bootstrap.lock.txt",
    "requirements.lock.py312.txt",
    "scripts/package_release.py",
    "scripts/verify_release.py",
    "start.ps1",
    "start.sh",
)


def run_package(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/package_release.py", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_verifier(release_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/verify_release.py", "--release-dir", str(release_dir), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def load_manifest() -> dict:
    return json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))


def make_committed_release_workspace(tmp_path: Path) -> Path:
    archive = tmp_path / "source.zip"
    subprocess.run(
        ["git", "archive", "--format=zip", f"--output={archive}", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with zipfile.ZipFile(archive) as source:
        source.extractall(workspace)
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    for raw_rel in tracked:
        if not raw_rel:
            continue
        rel = raw_rel.decode("utf-8")
        if rel == ".env" or rel.startswith(("config/", "data/", "research-inbox/")):
            continue
        source = ROOT / rel
        target = workspace / rel
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        elif target.exists():
            target.unlink()
    for rel in CURRENT_RELEASE_INPUTS:
        source = ROOT / rel
        assert source.is_file(), f"missing current release input: {rel}"
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.email", "release-test@example.invalid"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Release Contract Test"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=workspace, check=True)
    return workspace


def run_workspace_script(workspace: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )


def make_minimal_package(tmp_path: Path) -> Path:
    manifest = load_manifest()
    package = tmp_path / "FolioBoard-test"
    package.mkdir()
    shutil.copy2(ROOT / "release-manifest.json", package / "release-manifest.json")
    for rel in manifest["runtimeFiles"]:
        path = package / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")
    for rel in manifest["runtimeDirectories"]:
        (package / rel).mkdir(parents=True, exist_ok=True)
    for rel in manifest["emptyDirectories"]:
        (package / rel).mkdir(parents=True, exist_ok=True)
    return package


def test_manifest_lists_only_relative_runtime_paths() -> None:
    manifest = load_manifest()
    for section in ("runtimeFiles", "runtimeDirectories", "emptyDirectories"):
        for value in manifest[section]:
            path = Path(value)
            assert not path.is_absolute()
            assert ".." not in path.parts


def test_manifest_includes_cross_platform_launchers() -> None:
    manifest = load_manifest()
    assert "start.ps1" in manifest["runtimeFiles"]
    assert "start.sh" in manifest["runtimeFiles"]


def test_package_defaults_to_version_file() -> None:
    result = run_package("--dry-run")

    assert result.returncode == 0, result.stderr
    assert f"FolioBoard-v{VERSION}" in result.stdout


def test_package_dry_run_requires_a_safe_version() -> None:
    result = run_package("--version", "../unsafe", "--dry-run")
    assert result.returncode != 0


def test_verifier_rejects_a_forbidden_env_file(tmp_path: Path) -> None:
    package = make_minimal_package(tmp_path)
    (package / ".env").write_text("not-a-real-secret", encoding="utf-8")
    result = run_verifier(package, "--skip-gitleaks")
    assert result.returncode != 0
    assert ".env" in result.stderr


def test_gitleaks_scan_uses_utf8_output_decoding(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(verifier.shutil, "which", lambda name: "gitleaks")

    def fake_run(args, **kwargs):
        calls.update(kwargs)
        if args[1] == "version":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="8.30.1\n", stderr="")
        report_arg = next(value for value in args if value.startswith("--report-path="))
        Path(report_arg.split("=", 1)[1]).write_text("[]", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="✓", stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    assert verifier.run_gitleaks_scan(tmp_path) == []
    assert calls["encoding"] == "utf-8"
    assert calls["errors"] == "replace"


def test_gitleaks_scan_redacts_all_secret_values(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(verifier.shutil, "which", lambda name: "gitleaks")

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[1] == "version":
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="8.30.1\n", stderr="")
        report_arg = next(value for value in args if value.startswith("--report-path="))
        Path(report_arg.split("=", 1)[1]).write_text("[]", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(verifier.subprocess, "run", fake_run)

    assert verifier.run_gitleaks_scan(tmp_path) == []
    assert calls
    assert all("--redact=100" in call for call in calls)


def test_package_build_creates_verified_zip(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    version = "test-release-tools"
    package_dir = workspace / "dist" / f"FolioBoard-{version}"
    package_zip = package_dir.with_suffix(".zip")

    result = run_workspace_script(workspace, "scripts/package_release.py", "--version", version, "--skip-gitleaks")
    assert result.returncode == 0, result.stderr
    assert (package_dir / "release-manifest.json").is_file()
    assert (package_dir / "defaults" / "config").is_dir()
    assert not (package_dir / "config").exists()
    # 목록을 손으로 적지 않는다. 0.5에서 유럽·일본 구성종목이 목록에서 빠져
    # 패키지에 안 들어간 채 나갈 뻔했고, 여기 리터럴이 그때 남은 잔재다.
    # 부트스트랩이 아는 파일과 패키지 내용이 갈라지면 첫 실행이 조용히 깨진다.
    from features.common.config_bootstrap import DEFAULT_CONFIG_NAMES

    assert set(DEFAULT_CONFIG_NAMES) == {path.name for path in (package_dir / "defaults" / "config").iterdir()}
    # 셸 스크립트가 CRLF면 shebang이 `#!/bin/bash` + CR이 되어 macOS·Linux에서
    # `bad interpreter: /bin/bash^M`으로 실행 자체가 실패한다. 0.5.0 패키지의
    # start.sh가 실제로 CRLF 27줄이었다 — Windows 작업 트리에서 그대로 복사됐다.
    for script in package_dir.rglob("*.sh"):
        raw = script.read_bytes()
        assert b"\r\n" not in raw, f"{script.name} must ship with LF endings"
        assert raw.startswith(b"#!"), f"{script.name} lost its shebang"

    # 배치 파일은 정확히 반대다. cmd.exe는 CRLF를 요구하고, 파일을 콘솔 OEM
    # 코드페이지로 파싱하므로 비ASCII 바이트가 lead byte 노릇을 해 줄을 가른다.
    # 한국어 Windows(CP949)에서 실측: UTF-8 한글 주석이 든 LF 파일이
    # `'?'은(는) 내부 또는 외부 명령...`을 두 번 찍고 나서야 런처가 돌았다.
    for script in [*package_dir.rglob("*.cmd"), *package_dir.rglob("*.bat")]:
        raw = script.read_bytes()
        assert b"\n" in raw, f"{script.name} lost its line breaks"
        assert raw.count(b"\r\n") == raw.count(b"\n"), f"{script.name} must ship with CRLF endings"
        assert raw.decode("ascii", errors="ignore").encode("ascii") == raw, (
            f"{script.name} must stay ASCII — cmd.exe parses it in the OEM codepage"
        )

    build = json.loads((package_dir / "BUILD.json").read_text(encoding="utf-8"))
    assert build["version"] == VERSION
    assert len(build["commit"]) == 40
    assert package_zip.is_file()
    with zipfile.ZipFile(package_zip) as archive:
        assert "FolioBoard-test-release-tools/release-manifest.json" in archive.namelist()


def test_verifier_rejects_build_commit_mismatch(tmp_path: Path) -> None:
    package = make_minimal_package(tmp_path)
    (package / "BUILD.json").write_text(
        json.dumps({"version": "placeholder", "commit": "0" * 40, "builtAt": "2026-07-16T00:00:00Z"}),
        encoding="utf-8",
    )

    issues = verifier.verify_release(
        package,
        ROOT / "release-manifest.json",
        run_gitleaks=False,
        expected_commit="1" * 40,
    )

    assert "BUILD.json commit does not match the expected source commit." in issues


def test_package_build_preserves_dotted_version_in_zip_name(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    version = "v0.1.1-smoke"
    package_dir = workspace / "dist" / f"FolioBoard-{version}"
    package_zip = workspace / "dist" / f"FolioBoard-{version}.zip"
    wrong_zip = workspace / "dist" / "FolioBoard-v0.1.zip"

    result = run_workspace_script(workspace, "scripts/package_release.py", "--version", version, "--skip-gitleaks")
    assert result.returncode == 0, result.stderr
    assert package_zip.is_file()
    assert not wrong_zip.exists()
    with zipfile.ZipFile(package_zip) as archive:
        assert f"FolioBoard-{version}/release-manifest.json" in archive.namelist()


def test_universal_lock_is_packaged_byte_for_byte(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    lock = workspace / "requirements.lock.py312.txt"
    bootstrap_lock = workspace / "requirements-bootstrap.lock.txt"

    assert lock.is_file(), "release source must contain the reviewed universal Python 3.12 lock"
    assert bootstrap_lock.is_file(), "release source must contain the hash-locked uv bootstrap"

    result = run_workspace_script(
        workspace,
        "scripts/package_release.py",
        "--version",
        "qa-lock-byte-equality",
        "--output",
        "dist/qa/lock-byte-equality",
        "--skip-gitleaks",
    )
    assert result.returncode == 0, result.stderr
    package = workspace / "dist/qa/lock-byte-equality/FolioBoard-qa-lock-byte-equality"
    assert (package / lock.name).read_bytes() == lock.read_bytes()
    assert (package / bootstrap_lock.name).read_bytes() == bootstrap_lock.read_bytes()


def test_package_accepts_required_qa_build_metadata_suffix() -> None:
    result = run_package("--version", "v0.2.0-qa+8b12ced7", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "FolioBoard-v0.2.0-qa+8b12ced7" in result.stdout


def test_real_zip_extracts_verifies_and_boots_on_first_run(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    result = run_workspace_script(
        workspace,
        "scripts/package_release.py",
        "--version",
        "qa-real-zip-first-run",
        "--output",
        "dist/qa/real-zip-first-run",
        "--skip-gitleaks",
    )
    assert result.returncode == 0, result.stderr
    package_zip = workspace / "dist/qa/real-zip-first-run/FolioBoard-qa-real-zip-first-run.zip"
    extracted_root = tmp_path / "extracted"
    with zipfile.ZipFile(package_zip) as archive:
        archive.extractall(extracted_root)
    package = extracted_root / "FolioBoard-qa-real-zip-first-run"
    expected_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    verify = run_workspace_script(
        workspace,
        "scripts/verify_release.py",
        "--release-dir",
        str(package),
        "--expected-commit",
        expected_commit,
        "--skip-gitleaks",
    )
    assert verify.returncode == 0, verify.stderr

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = os.environ.copy()
    # 워크스페이스를 푼 폴더로 못박는다. 갓 푼 패키지는 `data/`가 비어 있어 판정이
    # 문서 폴더까지 내려가는데, 개발자 PC에 `~/Documents/FolioOS`가 있으면 테스트
    # 서버가 그쪽을 쓰고 `config/`도 거기에 만든다 — 이 단언이 기계 상태에 좌우된다.
    # 실제로 옮기기가 실패하며 남긴 부분 복사본 때문에 빨개졌다.
    environment.update(
        PORT=str(port),
        FOLIO_HOST="127.0.0.1",
        FOLIO_WORKSPACE_IDENTITY="release-test",
        FOLIO_HOME=str(package),
    )
    server = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=package,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        health = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and server.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                    health = json.load(response)
                break
            except OSError:
                time.sleep(0.2)
        assert health is not None, server.stderr.read() if server.poll() is not None and server.stderr else ""
        assert health["version"] == VERSION
        assert health["commit"] == expected_commit
        assert (package / "config").is_dir()
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


@pytest.mark.parametrize("private_path", [".env", "config/private-canary.txt"])
def test_package_rejects_private_canaries_before_writing(tmp_path: Path, private_path: str) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    canary = "FOLIO_RELEASE_PRIVATE_CANARY_7d064395"
    path = workspace / private_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canary, encoding="utf-8")
    output_root = workspace / "dist/qa/private-rejection"

    result = run_workspace_script(
        workspace,
        "scripts/package_release.py",
        "--version",
        "qa-private-rejection",
        "--output",
        "dist/qa/private-rejection",
        "--skip-gitleaks",
    )

    assert result.returncode != 0
    assert not output_root.exists(), "private input must be rejected before any artifact write"
    assert canary not in result.stdout
    assert canary not in result.stderr


def test_package_rejects_dirty_tracked_runtime_before_writing(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    runtime = workspace / "app.py"
    runtime.write_bytes(runtime.read_bytes() + b"\n# RELEASE_AUDIT_DIRTY_RUNTIME_CANARY\n")
    output_root = workspace / "dist/qa/dirty-runtime"

    result = run_workspace_script(
        workspace,
        "scripts/package_release.py",
        "--version",
        "qa-dirty-runtime",
        "--output",
        "dist/qa/dirty-runtime",
        "--skip-gitleaks",
    )

    assert result.returncode != 0
    assert not output_root.exists(), "dirty tracked runtime must be rejected before artifact creation"


def test_package_rejects_output_exists_even_when_force_is_requested(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    output_root = workspace / "dist/qa/output-exists"
    package = output_root / "FolioBoard-qa-output-exists"
    package.mkdir(parents=True)
    sentinel = package / "owned-before-package.txt"
    sentinel.write_bytes(b"do-not-replace\n")

    result = run_workspace_script(
        workspace,
        "scripts/package_release.py",
        "--version",
        "qa-output-exists",
        "--output",
        "dist/qa/output-exists",
        "--force",
        "--skip-gitleaks",
    )

    assert result.returncode != 0
    assert sentinel.read_bytes() == b"do-not-replace\n"


def test_verifier_rejects_wrong_commit_without_optional_hint(tmp_path: Path) -> None:
    workspace = make_committed_release_workspace(tmp_path)
    result = run_workspace_script(
        workspace,
        "scripts/package_release.py",
        "--version",
        "qa-wrong-commit",
        "--output",
        "dist/qa/wrong-commit",
        "--skip-gitleaks",
    )
    assert result.returncode == 0, result.stderr
    package = workspace / "dist/qa/wrong-commit/FolioBoard-qa-wrong-commit"
    build_path = package / "BUILD.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    actual_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    wrong_commit = "0" * 40 if actual_head != "0" * 40 else "1" * 40
    build["commit"] = wrong_commit
    build_path.write_text(json.dumps(build), encoding="utf-8")

    verify = run_workspace_script(
        workspace,
        "scripts/verify_release.py",
        "--release-dir",
        str(package),
        "--skip-gitleaks",
    )

    assert verify.returncode != 0
    assert "commit" in verify.stderr.lower()
