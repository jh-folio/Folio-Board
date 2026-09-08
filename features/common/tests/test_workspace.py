"""워크스페이스 위치 결정.

기본은 **지금과 같아야 한다** — 앱 폴더. 아무것도 새로 만들지 않는다. 옮기는 것은
선택이고, 옮긴 뒤에 새 버전을 풀면 자료를 자동으로 다시 찾아야 한다. 그러지 못하면
옮긴 의미가 없다.
"""
from __future__ import annotations

import pytest

from features.common import workspace


@pytest.fixture
def app(tmp_path, monkeypatch):
    """배포 zip을 갓 푼 상태 — `data/`는 빈 폴더 껍데기만 있다."""
    root = tmp_path / "FolioOS-v0.5.1"
    for name in workspace.WORKSPACE_DIR_NAMES:
        (root / name).mkdir(parents=True)
    (root / "data" / "briefings").mkdir()
    monkeypatch.setattr(workspace, "APP_ROOT", root)
    monkeypatch.delenv("FOLIO_HOME", raising=False)
    # 실제 문서 폴더는 Windows에서 레지스트리로 결정된다(OneDrive 리디렉션). 테스트는
    # 그 조회를 건너뛰고 임시 폴더를 문서 폴더로 삼는다.
    monkeypatch.setattr(workspace, "documents_root", lambda: tmp_path / "home" / "Documents")
    # 판정은 프로세스당 1회 캐시된다. 테스트마다 환경을 바꾸므로 앞뒤로 비운다.
    workspace.reset_cache()
    yield root
    workspace.reset_cache()


def test_a_fresh_install_uses_the_app_folder(app):
    """기본값은 바뀌지 않는다. 새 폴더도 만들지 않는다."""
    assert workspace.workspace_root() == app
    assert workspace.data_dir() == app / "data"
    assert not workspace.is_outside_app_folder()
    assert not workspace.documents_workspace().exists()


def test_an_existing_install_keeps_using_the_app_folder(app):
    (app / "data" / "portfolio.json").write_text("{}", encoding="utf-8")
    assert workspace.workspace_root() == app
    assert not workspace.is_outside_app_folder()


def test_documents_is_found_after_an_update(app, tmp_path):
    """옮긴 사용자가 새 버전을 풀었을 때 자료를 자동으로 다시 찾는다.

    새로 푼 앱 폴더의 `data/`는 비어 있으므로 2번 규칙이 걸리지 않고, 문서 폴더의
    워크스페이스가 잡혀야 한다. 이 규칙이 이 기능의 전부다.
    """
    documents = tmp_path / "home" / "Documents" / "FolioOS"
    (documents / "data").mkdir(parents=True)
    (documents / "data" / "portfolio.json").write_text("{}", encoding="utf-8")

    assert workspace.workspace_root() == documents
    assert workspace.data_dir() == documents / "data"
    assert workspace.is_outside_app_folder()


def test_an_empty_new_name_documents_folder_does_not_shadow_the_legacy_one(app, tmp_path):
    """빈 `~/Documents/FolioBoard`가 어떤 이유로 생겨도 자료가 든
    `~/Documents/FolioOS`를 가리면 안 된다(§4.4) — `has_user_data()`가 아니라
    `.exists()`로 물으면 이 사고가 난다."""
    (tmp_path / "home" / "Documents" / "FolioBoard").mkdir(parents=True)
    legacy = tmp_path / "home" / "Documents" / "FolioOS"
    (legacy / "data").mkdir(parents=True)
    (legacy / "data" / "portfolio.json").write_text("{}", encoding="utf-8")

    assert workspace.workspace_root() == legacy
    assert workspace.discover_documents_workspace() == legacy


def test_both_documents_folders_populated_the_new_name_wins(app, tmp_path):
    """새 이름은 사용자가 새 버전에서 직접 옮겼을 때만 생기므로 더 최근의 의사다."""
    new_name = tmp_path / "home" / "Documents" / "FolioBoard"
    (new_name / "data").mkdir(parents=True)
    (new_name / "data" / "portfolio.json").write_text("{}", encoding="utf-8")
    legacy = tmp_path / "home" / "Documents" / "FolioOS"
    (legacy / "data").mkdir(parents=True)
    (legacy / "data" / "portfolio.json").write_text("{}", encoding="utf-8")

    assert workspace.workspace_root() == new_name
    assert workspace.discover_documents_workspace() == new_name


def test_documents_workspace_is_the_move_destination_only(app, tmp_path):
    """`documents_workspace()`는 옮기기 목적지(새 이름 하나)이고, 탐색과는 다른
    함수다 — 구 이름 폴더에만 자료가 있어도 목적지는 여전히 새 이름이다."""
    legacy = tmp_path / "home" / "Documents" / "FolioOS"
    (legacy / "data").mkdir(parents=True)
    (legacy / "data" / "portfolio.json").write_text("{}", encoding="utf-8")

    assert workspace.documents_workspace() == tmp_path / "home" / "Documents" / "FolioBoard"
    assert not workspace.documents_workspace().exists()


def test_the_app_folder_wins_when_both_have_content(app, tmp_path):
    """옮기기는 원본을 지우지 않는다. 옛 폴더를 직접 실행하면 그 자료를 쓴다."""
    (app / "data" / "portfolio.json").write_text("{}", encoding="utf-8")
    documents = tmp_path / "home" / "Documents" / "FolioOS"
    (documents / "data").mkdir(parents=True)
    (documents / "data" / "portfolio.json").write_text("{}", encoding="utf-8")

    assert workspace.workspace_root() == app


def test_an_empty_documents_folder_is_not_picked_up(app, tmp_path):
    """빈 폴더 껍데기를 워크스페이스로 오인하면 안 된다."""
    (tmp_path / "home" / "Documents" / "FolioOS" / "data").mkdir(parents=True)
    assert workspace.workspace_root() == app


def test_folio_home_overrides_everything(app, tmp_path, monkeypatch):
    (app / "data" / "portfolio.json").write_text("{}", encoding="utf-8")
    custom = tmp_path / "elsewhere"
    monkeypatch.setenv("FOLIO_HOME", str(custom))
    assert workspace.workspace_root() == custom
    assert workspace.is_outside_app_folder()


def test_the_decision_is_made_once_per_process(app):
    """모듈 상수 수십 곳이 import 시점에 읽으므로 매번 디렉터리를 훑으면 안 되고,
    import 도중 `data/`가 생겨도 앞뒤 모듈이 같은 답을 봐야 한다."""
    first = workspace.workspace_root()
    (app / "data" / "portfolio.json").write_text("{}", encoding="utf-8")
    assert workspace.workspace_root() is first

    workspace.reset_cache()
    assert workspace.workspace_root() == app


def test_unknown_directory_names_are_rejected(app):
    for name in workspace.WORKSPACE_DIR_NAMES:
        assert workspace.workspace_dir(name).name == name
    with pytest.raises(ValueError):
        workspace.workspace_dir("secrets")


def test_the_marker_filename_and_env_var_are_rename_compatibility_contracts():
    """리네이밍이 절대 건드리지 않는 두 이름을 고정한다(plan §4.2) — `workspace.json`은
    기존 설치의 표지 포맷이고, `FOLIO_HOME`은 사용자 환경·자동화가 이미 참조 중이다."""
    assert workspace.MARKER_NAME == "workspace.json"


class TestResolutionDoesNotStrandTheUser:
    """판정이 틀리면 사용자는 자료가 사라진 것으로 본다. 그 경로들의 회귀 테스트."""

    def test_server_bootstrap_files_do_not_pin_the_app_folder(self, tmp_path, monkeypatch):
        """서버는 처음 켤 때 스스로 파일을 만든다(실측 5개). 그것을 "쓰던 워크스페이스"로
        세면, 옮긴 사용자가 새 버전을 한 번 잘못 켠 순간 앱 폴더가 영구히 고정되고
        문서 폴더 규칙은 다시는 실행되지 않는다.
        """
        app = tmp_path / "FolioOS-v0.5.5"
        (app / "data").mkdir(parents=True)
        for name in ("index.json", "market-memory.sqlite3", "research-index.sqlite3"):
            (app / "data" / name).write_text("", encoding="utf-8")

        documents = tmp_path / "home" / "Documents"
        moved = documents / "FolioOS"
        (moved / "data" / "briefings").mkdir(parents=True)
        (moved / "data" / "briefings" / "2026-08-28.us.json").write_text("{}", encoding="utf-8")

        monkeypatch.setattr(workspace, "APP_ROOT", app)
        monkeypatch.setattr(workspace, "documents_root", lambda: documents)
        monkeypatch.delenv("FOLIO_HOME", raising=False)
        workspace.reset_cache()

        assert workspace.workspace_root() == moved

    def test_a_marker_saved_in_another_encoding_does_not_stop_the_app(self, tmp_path, monkeypatch):
        """`UnicodeDecodeError`는 `OSError`가 아니다. import 시점에 새면 앱이 안 켜진다."""
        app = tmp_path / "app"
        (app / "data").mkdir(parents=True)
        (app / "data" / "portfolio.json").write_text("{}", encoding="utf-8")
        (app / "workspace.json").write_bytes("﻿{}".encode("utf-16"))

        monkeypatch.setattr(workspace, "APP_ROOT", app)
        monkeypatch.delenv("FOLIO_HOME", raising=False)
        workspace.reset_cache()

        assert workspace.workspace_root() == app

    def test_a_workspace_inside_the_app_folder_is_not_reported_as_outside(self, tmp_path, monkeypatch):
        """부등호로 물으면 앱 폴더 **안**의 하위 폴더도 "밖"이 되어, 다음 zip이 두고 갈
        자료를 두고 "새 버전을 받아도 그대로 이어집니다"라고 말하게 된다.
        """
        app = tmp_path / "FolioOS-v0.5.5"
        nested = app / "workspace"
        (nested / "data").mkdir(parents=True)
        monkeypatch.setattr(workspace, "APP_ROOT", app)
        monkeypatch.setenv("FOLIO_HOME", str(nested))
        workspace.reset_cache()

        assert workspace.workspace_root() == nested
        assert workspace.is_outside_app_folder() is False

    def test_quotes_around_folio_home_are_stripped(self, tmp_path, monkeypatch):
        """cmd.exe의 `set VAR="값"`은 따옴표까지 값에 담는다. NTFS 이름에 못 쓰는 문자라
        그대로 두면 모든 쓰기가 OS 층에서 실패하고 화면은 원인을 짚어주지 못한다.
        """
        target = tmp_path / "Folio Data"
        target.mkdir()
        monkeypatch.setattr(workspace, "APP_ROOT", tmp_path / "app")
        monkeypatch.setenv("FOLIO_HOME", f'"{target}"')
        workspace.reset_cache()

        assert workspace.workspace_root() == target
