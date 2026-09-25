from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


REQUIRED_DOCS = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "README.ko.md",
    "installation.md",
    "SECURITY.md",
    "features/README.md",
    "features/topic_report/README.md",
    "features/agent_mode/README.md",
    "features/market_memory/README.md",
    "features/automation/README.md",
    "features/frontend_ui/README.md",
    "features/smart_collections/README.md",
    "features/common/research_library/README.md",
    "web/README.md",
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
    "docs/SMOKE_TESTS.md",
)

EXPECTED_ALLOWLIST = (
    "AGENTS.md\t^\\| 0\\.1 공개 릴리즈 \\|\thistorical roadmap milestone",
    "CLAUDE.md\t^\\| 0\\.1 공개 릴리즈 \\|\thistorical roadmap milestone",
    "SECURITY.md\t^\\| 0\\.1\\.x \\| No \\|$\thistorical unsupported release line",
)

CURRENT_CLAIM_PATHS = (
    "README.md",
    "README.ko.md",
    "installation.md",
    "SECURITY.md",
    ".env.example",
    "AGENTS.md",
    "CLAUDE.md",
    "web/README.md",
    "docs/PUBLIC_RELEASE_CHECKLIST.md",
)

HISTORICAL_VERSION = re.compile(r"(?<!\d)0\.1(?:\.x|\.\d+)?(?!\d)")
IPV4_LITERAL = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _exposure_issues(routes: str, shell: str, home: str, palette: str) -> list[str]:
    issues: list[str] = []
    if re.search(r'id: "deep-research"[^\n]+visibleInNav: false', routes):
        issues.append("deep_research_hidden")
    if 'routes: ["analysis", "deep-research"]' not in shell:
        issues.append("nav_missing")
    if 'data-qa="home-deep-research"' not in home:
        issues.append("home_missing")
    if '"command-deep-research"' not in palette:
        issues.append("palette_missing")
    return issues


def _current_claim_issues(files: dict[str, str]) -> list[str]:
    issues: list[str] = []
    for path, text in files.items():
        if path in {"README.md", "README.ko.md", "installation.md"} and "0.3" not in text:
            issues.append(f"{path}:version")
    return issues


def _historical_claim_issues(
    files: dict[str, str],
    allowlist: tuple[str, ...] = EXPECTED_ALLOWLIST,
) -> list[str]:
    allowed: dict[str, list[re.Pattern[str]]] = {}
    for entry in allowlist:
        path, pattern, _reason = entry.split("\t", 2)
        allowed.setdefault(path, []).append(re.compile(pattern))

    issues: list[str] = []
    for path, text in files.items():
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not HISTORICAL_VERSION.search(IPV4_LITERAL.sub("", line)):
                continue
            if not any(pattern.search(line) for pattern in allowed.get(path, [])):
                issues.append(f"{path}:{line_number}")
    return issues


def test_deep_research_exposure_contract() -> None:
    routes = _source("web/src/app/routes.ts")
    shell = _source("web/src/app/AppShell.tsx")
    home = _source("web/src/app/AgentHome.tsx")
    palette = _source("web/src/app/CommandPalette.tsx")

    assert re.search(r'id: "deep-research"[^\n]+group: "research"', routes)
    assert not re.search(r'id: "deep-research"[^\n]+visibleInNav: false', routes)
    assert 'routes: ["analysis", "deep-research"]' in shell
    assert 'data-qa="home-deep-research"' in home
    assert '"command-deep-research"' in palette
    assert "data-qa={item.qa}" in palette


def test_public_routes_are_exposed() -> None:
    routes = _source("web/src/app/routes.ts")
    shell = _source("web/src/app/AppShell.tsx")
    assert not re.search(r'id: "dashboard"[^\n]+visibleInNav: false', routes)
    assert not re.search(r'id: "watchlist"[^\n]+visibleInNav: false', routes)
    assert 'routes: ["home", "dashboard"]' in shell
    assert 'routes: ["watchlist", "portfolio"]' in shell
    assert 'id="folio-main-content"' in shell
    assert 'href="#folio-main-content"' in shell


def test_machine_version_authority_agrees_across_files() -> None:
    """VERSION을 권위로 삼는다.

    이전에는 버전 문자열을 하드코딩해서, 0.4.4 승격 때 이 파일만 0.4.3에 남아
    조용히 깨졌다(CI가 `features tests`만 돌려 드러나지 않았다).
    """
    version = _source("VERSION").strip()
    package = json.loads(_source("web/package.json"))
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    assert package["version"] == version


def test_documented_scope_matches_english_and_korean() -> None:
    for relative in REQUIRED_DOCS:
        assert (ROOT / relative).is_file(), relative

    english = _source("README.md")
    korean = _source("README.ko.md")
    # 제목에 버전을 박지 않는다 — 릴리즈마다 고쳐야 하는데 VERSION 파일과
    # 버전 이름이 붙은 배포 폴더가 이미 그 정보를 갖는다.
    assert "## What You Can Do" in english
    assert "## 할 수 있는 일" in korean
    assert not re.search(r"What You Can Do In \d", english), "제목에 버전을 넣지 않는다"
    for text in (english, korean):
        assert "Deep Research" in text
        assert "Smart Collection" in text
        assert "Work Log" in text
        assert "Dashboard" in text or "대시보드" in text
        assert "watchlist" in text.lower() or "워치리스트" in text


def test_historical_version_allowlist_is_exact() -> None:
    entries = tuple(_source("docs/version-reference-allowlist.txt").splitlines())
    assert entries == EXPECTED_ALLOWLIST
    claim_files = {path: _source(path) for path in CURRENT_CLAIM_PATHS}
    claim_files.update(
        {
            path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
            for path in (ROOT / "features").glob("**/README.md")
        }
    )
    assert _historical_claim_issues(claim_files, entries) == []
    for entry in entries:
        path, pattern, _reason = entry.split("\t", 2)
        matches = [
            line for line in claim_files[path].splitlines()
            if re.search(pattern, line)
        ]
        assert len(matches) == 1, entry


def test_topic_report_endpoint_inventory_has_no_public_save_route() -> None:
    topic = _source("features/topic_report/README.md")
    required = {
        "GET    /api/topic-reports/presets",
        "GET    /api/topic-reports",
        "POST   /api/topic-reports/plan",
        "POST   /api/topic-reports/confirm-degraded",
        "POST   /api/topic-reports",
        "GET    /api/topic-reports/{report_id}?includePersonal",
        "DELETE /api/topic-reports/{report_id}",
    }
    lines = topic.splitlines()
    assert all(any(line.startswith(endpoint) for line in lines) for endpoint in required)
    assert "/api/topic-reports/save" not in topic


def test_detects_version_drift() -> None:
    files = {"README.md": "Folio Board 0.1", "README.ko.md": "Folio Board 0.3", "installation.md": "Folio Board 0.3"}
    assert _current_claim_issues(files) == ["README.md:version"]


def test_detects_missing_nav() -> None:
    issues = _exposure_issues(
        _source("web/src/app/routes.ts"),
        _source("web/src/app/AppShell.tsx").replace('routes: ["analysis", "deep-research"]', 'routes: ["analysis"]'),
        _source("web/src/app/AgentHome.tsx"),
        _source("web/src/app/CommandPalette.tsx"),
    )
    assert issues == ["nav_missing"]


def test_rejects_unallowlisted_01() -> None:
    files = {"README.md": "## What You Can Do In 0.1"}
    assert _historical_claim_issues(files) == ["README.md:1"]
