from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_machine_versions_derive_release_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "web" / "package-lock.json").read_text(encoding="utf-8"))
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert version == "0.5.4"
    assert package["version"] == version
    assert lock["version"] == version
    assert lock["packages"][""]["version"] == version
    assert re.search(r"APP_VERSION\s*=.*VERSION", app_source)
    assert re.search(r"FastAPI\([^)]*version=APP_VERSION", app_source, re.DOTALL)


def test_release_cli_defaults_to_version_file() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/package_release.py", "--dry-run"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "FolioBoard-v0.5.4" in result.stdout


def test_public_research_navigation_is_exposed_for_043() -> None:
    route_source = (ROOT / "web" / "src" / "app" / "routes.ts").read_text(encoding="utf-8")
    shell_source = (ROOT / "web" / "src" / "app" / "AppShell.tsx").read_text(encoding="utf-8")
    home_source = (ROOT / "web" / "src" / "app" / "AgentHome.tsx").read_text(encoding="utf-8")
    palette_source = (ROOT / "web" / "src" / "app" / "CommandPalette.tsx").read_text(encoding="utf-8")

    assert re.search(r'id: "deep-research"[^\n]+group: "research"', route_source)
    assert not re.search(r'id: "deep-research"[^\n]+visibleInNav: false', route_source)
    assert 'routes: ["analysis", "deep-research"]' in shell_source
    assert 'runQuickAction("deep-research")' in home_source
    assert 'data-qa="home-deep-research"' in home_source
    assert 'command-deep-research' in palette_source
    assert "host.focus({ preventScroll: true })" in shell_source
    assert 'tabIndex={-1}' in shell_source

    assert not re.search(r'id: "dashboard"[^\n]+visibleInNav: false', route_source)
    assert not re.search(r'id: "watchlist"[^\n]+visibleInNav: false', route_source)
    assert 'routes: ["home", "dashboard"]' in shell_source
    assert 'routes: ["watchlist", "portfolio"]' in shell_source
