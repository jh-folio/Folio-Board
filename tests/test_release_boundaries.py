from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
# 패키지에 들어가는 기본 설정은 사람이 검토한 바이트 그대로여야 한다. 핀을 옮기는
# 커밋이 곧 "다시 봤다"는 기록이므로, 기본값을 바꾸면 이 테스트가 빨개진다.
#
# 예전에는 config/의 blob과 비교했는데 config/는 .gitignore 대상이라 새 파일이
# 추적되지 않는다. 그래서 유럽/일본 구성종목 파일은 목록에도 못 들어가고 검사도
# 받지 못했다. 이제 defaults/ 자신의 검토 시점 blob과 비교한다.
# 2026-08-07 검토하고 옮김: 일본·유럽 구성종목에 `englishName`을 채우고(각 225·199건,
# yfinance longName) 한글 별칭 파일 `foreign_company_aliases.json`을 새로 넣었다.
# 자국 표기만 있으면 "Toyota"로 찾을 때 도쿄 상장이 후보에 아예 없었기 때문이다.
# 2026-08-09 검토하고 옮김: `rss_feeds.yaml`에서 `country`를 걷어내고 `language`를 53개
# 피드 전부로 넓혔다(예전에는 유럽·일본만 선언할 수 있었다). 일본 피드는 NHK·Asahi만
# 남기고 Diamond Online·Toyo Keizai·Kyodo News를 뺐다 — 앞의 둘은 사이트 전체 피드라
# 라이프·커리어 기사가 대부분이고, `kyodo.co.jp/feed/`는 뉴스 와이어가 아니라
# 共同通信PRワイヤー였다. 대신 日経 헤드라인을 받는 Google News 검색을 넣었다.
# 2026-08-12 검토하고 옮김: Handelsblatt와 manager magazin이 사이트 전체 헤드라인
# 피드를 받고 있어서 politik·karriere·video가 섞여 들어왔다(Handelsblatt 1,260건 중
# politik 421, finanzen 279). 그 기사들이 본문 장식에서 미국 대형주를 주워 1,247건이
# `US` 시장으로 찍혔다. 두 매체의 finanzen·unternehmen 섹션 피드로 바꾸고, 섹션이
# 섞여 오는 Het Financieele Dagblad에는 `url_sections` 필터를 걸었다.
# 2026-08-13 검토하고 옮김: 섹션 피드 4개에도 `url_sections`를 명시했다. 실측으로
# 자기 섹션만 내놓지만(20/20), 규칙이 설정에 있어야 이미 쌓인 자료를 정리하는 쪽이
# "지금 무엇을 수집하는가"를 피드 주소에서 추측하지 않는다.
# 2026-08-19 검토하고 옮김: KOSPI200 구성종목 199곳에 한글 정식명을 별칭으로 넣었다.
# 그 이름은 DART 상장 목록에만 있었는데 그 파일은 배포에 없고 API 키가 있어야 받아진다
# — 키 없이 설치하면 한국 기업이 수동 사전 8곳으로만 풀렸다. 같은 커밋에서
# company_master 의 `현대자동차` 별칭과, 배포본에만 빠져 있던 NAVER 항목을 맞췄다.
BASE_COMMIT = "352903faecac8091eac0da204e0099520150b71d"
sys.path.insert(0, str(ROOT))
from features.common.config_bootstrap import DEFAULT_CONFIG_NAMES  # noqa: E402

DEFAULT_NAMES = tuple(sorted(DEFAULT_CONFIG_NAMES))
sys.path.insert(0, str(ROOT / "scripts"))
import public_release_audit as release_audit  # noqa: E402


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


@pytest.fixture
def audit_repo(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "features").mkdir()
    (root / "defaults" / "config").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "data").mkdir()
    (root / "research-inbox").mkdir()
    (root / ".gitignore").write_text("/config/\n/data/\n/research-inbox/\n", encoding="utf-8")
    manifest = {
        "packageName": "FolioBoard",
        "runtimeFiles": ["VERSION"],
        "runtimeDirectories": ["features", "defaults"],
        "emptyDirectories": ["data", "research-inbox"],
        "forbiddenPaths": ["config", ".env"],
    }
    (root / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    (root / "features" / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
    assert _git(root, "init").returncode == 0
    assert _git(root, "config", "user.email", "test@example.invalid").returncode == 0
    assert _git(root, "config", "user.name", "Release Test").returncode == 0
    assert _git(root, "add", ".").returncode == 0
    assert _git(root, "commit", "-m", "fixture").returncode == 0
    (root / "config" / "sentinel.json").write_bytes(b"private-config")
    (root / "data" / "sentinel.json").write_bytes(b"private-data")
    (root / "research-inbox" / "sentinel.md").write_bytes(b"private-research")
    return root


def _audit(root: Path) -> list[str]:
    audit = getattr(release_audit, "audit_repository", None)
    assert callable(audit), "metadata-only release audit contract is missing"
    return audit(root)


def test_defaults_are_exact_reviewed_git_blobs() -> None:
    for name in DEFAULT_NAMES:
        result = subprocess.run(
            ["git", "cat-file", "blob", f"{BASE_COMMIT}:defaults/config/{name}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{name} is not in the reviewed pin {BASE_COMMIT}"
        assert (ROOT / "defaults" / "config" / name).read_bytes() == result.stdout


def test_every_bootstrapped_config_ships_and_is_reviewed() -> None:
    """부트스트랩이 아는 파일과 패키지·검토 목록이 갈라지면 안 된다.

    갈라졌을 때 조용히 깨진다: 첫 실행이 defaults에서 파일을 읽는데 패키지에
    그 파일이 없다. 0.5의 유럽/일본 구성종목이 그 상태였다.
    """
    import package_release

    for name in DEFAULT_CONFIG_NAMES:
        assert (ROOT / "defaults" / "config" / name).exists(), name
        assert f"defaults/config/{name}" in package_release.ADDITIONAL_SOURCE_FILES, name
        assert name in package_release.ALLOWED_LOCAL_CONFIG_PATHS, name
        assert name in DEFAULT_NAMES, name


def test_audit_refuses_to_read_user_roots(
    audit_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = {"config", "data", "research-inbox"}
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text

    def guard_bytes(path: Path) -> bytes:
        if path.is_relative_to(audit_repo) and path.relative_to(audit_repo).parts[0] in protected:
            raise AssertionError(f"protected root opened: {path}")
        return original_read_bytes(path)

    def guard_text(
        path: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        if path.is_relative_to(audit_repo) and path.relative_to(audit_repo).parts[0] in protected:
            raise AssertionError(f"protected root opened: {path}")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_bytes", guard_bytes)
    monkeypatch.setattr(Path, "read_text", guard_text)

    issues = _audit(audit_repo)

    assert issues == ["Local config status is release-forbidden: config/"]
    assert all("private-config" not in issue for issue in issues)


def test_audit_rejects_untracked_runtime_canary(audit_repo: Path) -> None:
    (audit_repo / "features" / "runtime-canary.txt").write_text("canary", encoding="utf-8")

    issues = _audit(audit_repo)

    assert any("runtime-canary.txt" in issue for issue in issues)


def test_audit_rejects_dirty_config_from_status_without_opening_it(audit_repo: Path) -> None:
    tracked = audit_repo / "config" / "tracked.json"
    tracked.write_text("base", encoding="utf-8")
    assert _git(audit_repo, "add", "-f", "config/tracked.json").returncode == 0
    assert _git(audit_repo, "commit", "-m", "tracked config fixture").returncode == 0
    tracked.write_text("dirty-private-value", encoding="utf-8")

    issues = _audit(audit_repo)

    assert any("config/tracked.json" in issue for issue in issues)


def test_manifest_keeps_both_config_roots_forbidden_from_the_same_package() -> None:
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))

    assert "defaults" in manifest["runtimeDirectories"]
    assert "config" not in manifest["runtimeDirectories"]
    assert "config" in manifest["forbiddenPaths"]
