"""Create a clean Folio Board user release package.

The package is driven by release-manifest.json. Only the explicit runtime
surface is copied, empty first-run data directories are created, the result is
verified, and then a cross-platform ZIP is written under dist/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from verify_release import load_manifest, verify_release

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from features.common.config_bootstrap import DEFAULT_CONFIG_NAMES  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "dist"
DEFAULT_MANIFEST = ROOT / "release-manifest.json"
RELEASE_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
DEFAULT_VERSION = f"v{RELEASE_VERSION}"

# 두 목록은 config_bootstrap에서 파생한다. 손으로 관리하던 시절 유럽/일본
# 구성종목 파일이 여기에만 빠져서, 부트스트랩은 그 파일을 아는데 패키지에는
# 없는 상태로 0.5가 나갈 뻔했다.
ADDITIONAL_SOURCE_FILES = {
    "features/common/config_bootstrap.py",
    *(f"defaults/config/{name}" for name in DEFAULT_CONFIG_NAMES),
}

ALLOWED_LOCAL_CONFIG_PATHS = set(DEFAULT_CONFIG_NAMES)

EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}

EXCLUDED_PARTS = {
    "tests",
    # Pixel Office는 보류 상태다. 소스는 저장소에 남기지만 릴리즈 패키지에는 넣지 않는다.
    # 사용자가 도달할 수 없는 기능의 백엔드와 0.87MB짜리 스프라이트를 배포할 이유가 없다.
    "pixel_office",
    "pixel-office",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if path.name in EXCLUDED_DIR_NAMES:
        return True
    if parts & EXCLUDED_PARTS:
        return True
    if path.name.endswith(".test.js"):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return False


def copy_tree(src: Path, dst: Path, *, dry_run: bool, copied: list[str]) -> None:
    relative_source = _relative(src)
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", relative_source],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Unable to enumerate tracked package inputs: {relative_source}")
    source_files = {
        ROOT / rel.decode("utf-8")
        for rel in result.stdout.split(b"\0")
        if rel
    }
    source_files.update(
        ROOT / rel
        for rel in ADDITIONAL_SOURCE_FILES
        if rel == relative_source or rel.startswith(f"{relative_source}/")
    )
    for item in sorted(source_files):
        if not item.is_file():
            raise SystemExit(f"Required tracked package input is missing: {_relative(item)}")
        if should_skip(item):
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_runtime_file(item, target)
        copied.append(_relative(item))


def validate_version(version: str) -> str:
    version = str(version or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", version):
        raise SystemExit("Version must contain only letters, numbers, dots, dashes, plus signs, or underscores.")
    if "/" in version or "\\" in version:
        raise SystemExit("Version must not contain path separators.")
    return version


def validate_output_root(output_root: Path) -> Path:
    allowed_root = DEFAULT_OUTPUT_ROOT.resolve()
    resolved = output_root.resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        raise SystemExit("Output must be inside the repository dist/ directory.")
    return resolved


def validate_artifact_path(output: Path) -> Path:
    resolved = output.resolve()
    allowed_root = (ROOT / "dist").resolve()
    if resolved == ROOT.resolve():
        raise SystemExit("Refusing to package into the repository root.")
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        raise SystemExit("Output must be inside the repository dist/ directory.")
    return resolved


def _ensure_output_absent(package_dir: Path, package_zip: Path) -> None:
    if package_dir.exists():
        raise SystemExit(f"Output already exists: {package_dir}.")
    if package_zip.exists():
        raise SystemExit(f"Output already exists: {package_zip}.")


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="ascii",
        capture_output=True,
        check=False,
    )
    commit = result.stdout.strip().lower()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit("Unable to derive the full release commit.")
    return commit


def _require_clean_release_inputs(manifest: dict) -> str:
    if (ROOT / ".env").exists():
        raise SystemExit("Private/local release input is present; refusing to package.")

    config_root = ROOT / "config"
    if config_root.exists():
        local_paths = {
            path.relative_to(config_root).as_posix()
            for path in config_root.rglob("*")
            if path.is_file()
        }
        has_nested_directory = any(path.is_dir() for path in config_root.rglob("*"))
        if has_nested_directory or not local_paths.issubset(ALLOWED_LOCAL_CONFIG_PATHS):
            raise SystemExit("Private/local release input is present; refusing to package.")

    package_inputs = [
        "release-manifest.json",
        *manifest["runtimeFiles"],
        *manifest["runtimeDirectories"],
    ]
    input_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *package_inputs],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if input_status.returncode != 0:
        raise SystemExit("Unable to audit tracked release inputs.")
    if input_status.stdout:
        raise SystemExit("Tracked release inputs are dirty or unreviewed; refusing to package.")
    return _git_head()


# 셸 스크립트는 반드시 LF로 담는다. Windows 작업 트리에서 CRLF로 체크아웃된 파일을
# 그대로 복사하면 shebang이 `#!/bin/bash` + CR이 되어 macOS·Linux에서 실행 자체가
# 실패한다(`bad interpreter: /bin/bash^M`). 실측: 0.5.0 패키지의 start.sh가 CRLF
# 27줄이었다 — 그 플랫폼 사용자는 런처가 아예 돌지 않았을 수 있다.
# `.gitattributes`에도 규칙을 넣었지만, 릴리즈가 개발자의 git 설정에 의존하면 안 되므로
# 패키저에서 한 번 더 고정한다.
LF_ONLY_SUFFIXES = {".sh"}
# 배치 파일은 반대다. cmd.exe는 CRLF를 요구하고, 콘솔 OEM 코드페이지로 파싱하므로
# 비ASCII가 들어가면 줄이 갈라져 가짜 명령이 실행된다(한국어 Windows에서 실측).
CRLF_ONLY_SUFFIXES = {".cmd", ".bat"}


def _copy_runtime_file(src: Path, target: Path) -> None:
    if src.suffix in LF_ONLY_SUFFIXES:
        target.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
        shutil.copystat(src, target)
        return
    if src.suffix in CRLF_ONLY_SUFFIXES:
        body = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        target.write_bytes(body)
        shutil.copystat(src, target)
        return
    shutil.copy2(src, target)


def _copy_manifest_entries(manifest: dict, package_dir: Path, *, dry_run: bool, copied: list[str]) -> None:
    for rel in manifest["runtimeFiles"]:
        src = ROOT / rel
        if not src.is_file():
            raise SystemExit(f"Required file is missing: {rel}")
        if not dry_run:
            target = package_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_runtime_file(src, target)
        copied.append(rel)

    for rel in manifest["runtimeDirectories"]:
        src = ROOT / rel
        if not src.is_dir():
            raise SystemExit(f"Required directory is missing: {rel}")
        if not dry_run:
            (package_dir / rel).mkdir(parents=True, exist_ok=True)
        copy_tree(src, package_dir / rel, dry_run=dry_run, copied=copied)

    for rel in manifest["emptyDirectories"]:
        if not dry_run:
            (package_dir / rel).mkdir(parents=True, exist_ok=True)
        copied.append(rel + "/")


def write_zip(package_dir: Path, package_zip: Path) -> None:
    with zipfile.ZipFile(package_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            archive_name = path.relative_to(package_dir.parent).as_posix()
            if path.is_dir():
                archive.writestr(archive_name.rstrip("/") + "/", b"")
            elif path.is_file():
                archive.write(path, archive_name)


def build_package(
    version: str | None,
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    dry_run: bool,
    skip_gitleaks: bool,
) -> tuple[list[str], Path, Path]:
    manifest = load_manifest(manifest_path)
    safe_version = validate_version(version or DEFAULT_VERSION)
    output_root = validate_output_root(output_root)
    package_dir = output_root / f"{manifest['packageName']}-{safe_version}"
    package_zip = package_dir.parent / f"{package_dir.name}.zip"
    validate_artifact_path(package_dir)
    validate_artifact_path(package_zip)

    copied: list[str] = []

    if dry_run:
        _copy_manifest_entries(manifest, package_dir, dry_run=True, copied=copied)
        return copied, package_dir, package_zip

    _ensure_output_absent(package_dir, package_zip)
    commit = _require_clean_release_inputs(manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".tmp-", dir=output_root))
    staging_package = staging_root / package_dir.name
    staging_zip = staging_root / package_zip.name
    try:
        staging_package.mkdir()
        _copy_manifest_entries(manifest, staging_package, dry_run=False, copied=copied)
        built_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        build = {"version": RELEASE_VERSION, "commit": commit, "builtAt": built_at}
        (staging_package / "BUILD.json").write_text(
            json.dumps(build, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        copied.append("BUILD.json")
        shutil.copy2(manifest_path, staging_package / "release-manifest.json")
        copied.append("release-manifest.json")
        issues = verify_release(
            staging_package,
            manifest_path,
            run_gitleaks=not skip_gitleaks,
            expected_commit=commit,
        )
        if issues:
            for issue in issues:
                print(issue)
            raise SystemExit("Release verification failed.")
        write_zip(staging_package, staging_zip)
        promoted_directory = False
        try:
            staging_package.replace(package_dir)
            promoted_directory = True
            staging_zip.replace(package_zip)
        except BaseException:
            if promoted_directory and package_dir.exists():
                shutil.rmtree(package_dir, ignore_errors=True)
            if package_zip.exists():
                package_zip.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    return copied, package_dir, package_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Folio Board runtime files from tracked inputs.")
    parser.add_argument("--version", default=DEFAULT_VERSION, help=f"Package version suffix (default: {DEFAULT_VERSION}).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Output root under dist/.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Release manifest path.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be packaged without writing files.")
    parser.add_argument("--skip-gitleaks", action="store_true", help="Skip Gitleaks scan for tests or diagnostics.")
    args = parser.parse_args()

    copied, package_dir, package_zip = build_package(
        args.version,
        output_root=args.output,
        manifest_path=args.manifest,
        dry_run=args.dry_run,
        skip_gitleaks=args.skip_gitleaks,
    )
    action = "Would package" if args.dry_run else "Packaged"
    print(f"{action} {len(copied)} paths into {package_dir}")
    if not args.dry_run:
        print(f"Wrote ZIP: {package_zip}")
    for rel in copied[:80]:
        print(f"  {rel}")
    if len(copied) > 80:
        print(f"  ... {len(copied) - 80} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
