#!/usr/bin/env python3
"""Install the platform-pinned Gitleaks asset after SHA-256 verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "scripts" / "tool-versions.json"
ALLOWED_DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com"}
DOWNLOAD_TIMEOUT_SECONDS = 60
PROCESS_TIMEOUT_SECONDS = 15


def target_key() -> str:
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64" if machine in {"amd64", "x86_64"} else ""
    system = {"win32": "windows", "linux": "linux", "darwin": "darwin"}.get(sys.platform, "")
    if not system or not arch or (system in {"windows", "linux"} and arch != "x64"):
        raise RuntimeError("unsupported Gitleaks installation target")
    return f"{system}-{arch}"


def load_asset(version: str, target: str | None = None) -> dict[str, str]:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))["gitleaks"]
    if version != metadata["version"]:
        raise RuntimeError("requested Gitleaks version is not pinned")
    key = target or target_key()
    try:
        return metadata["assets"][key]
    except KeyError as exc:
        raise RuntimeError("Gitleaks asset metadata is missing for this target") from exc


def _safe_destination(root: Path, member: str) -> Path:
    destination = (root / member).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError("Gitleaks archive contains an unsafe path") from exc
    return destination


def extract_archive(archive: Path, destination: Path) -> None:
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                _safe_destination(destination, info.filename)
            source.extractall(destination)
    else:
        with tarfile.open(archive, "r:gz") as source:
            for member in source.getmembers():
                _safe_destination(destination, member.name)
                if member.issym() or member.islnk():
                    raise RuntimeError("Gitleaks archive links are not accepted")
            source.extractall(destination, filter="data")


def install_verified_executable(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_executable = destination.parent / f".{destination.name}.tmp"
    try:
        shutil.copy2(source, temporary_executable)
        if os.name != "nt":
            temporary_executable.chmod(0o755)
        os.replace(temporary_executable, destination)
    finally:
        temporary_executable.unlink(missing_ok=True)


def install_gitleaks(version: str, install_dir: Path) -> Path:
    asset = load_asset(version)
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "FolioBoard-release-bootstrap/0.2"})
    with tempfile.TemporaryDirectory(prefix="folio-gitleaks-") as temporary_name:
        temporary = Path(temporary_name)
        archive = temporary / asset["filename"]
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            final_host = (urllib.parse.urlparse(response.geturl()).hostname or "").lower()
            if final_host not in ALLOWED_DOWNLOAD_HOSTS:
                raise RuntimeError("Gitleaks download redirected to a forbidden host")
            with archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != asset["sha256"]:
            raise RuntimeError("Gitleaks asset checksum mismatch")
        extracted = temporary / "extracted"
        extracted.mkdir()
        extract_archive(archive, extracted)
        executable_name = "gitleaks.exe" if os.name == "nt" else "gitleaks"
        candidates = list(extracted.rglob(executable_name))
        if len(candidates) != 1 or not candidates[0].is_file():
            raise RuntimeError("verified Gitleaks archive did not contain one executable")
        destination = install_dir / executable_name
        install_verified_executable(candidates[0], destination)
    version_result = subprocess.run(
        [str(destination), "version", "--redact=100"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=PROCESS_TIMEOUT_SECONDS,
    )
    if version_result.returncode != 0 or version_result.stdout.strip() != version:
        destination.unlink(missing_ok=True)
        raise RuntimeError("installed Gitleaks executable failed version verification")
    return destination


def main() -> int:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))["gitleaks"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=metadata["version"])
    parser.add_argument("--install-dir", type=Path, default=ROOT / ".tools" / "gitleaks" / metadata["version"])
    parser.add_argument("--verify-checksum", action="store_true", help="Compatibility flag; verification is mandatory.")
    args = parser.parse_args()
    try:
        destination = install_gitleaks(args.version, args.install_dir.resolve())
    except (OSError, RuntimeError, subprocess.TimeoutExpired, urllib.error.URLError) as exc:
        parser.error(str(exc))
    print(f"Installed checksum-verified Gitleaks {args.version}: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
