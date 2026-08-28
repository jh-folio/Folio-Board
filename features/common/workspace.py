"""워크스페이스(사용자 자료)가 어디 있는지 한 곳에서 정한다.

배포 zip은 `FolioOS-v0.5.0/` 처럼 **버전이 박힌 폴더**로 풀리고 `data/`는 빈 채로
나온다. 그래서 새 버전을 받으면 새 폴더에 빈 워크스페이스가 생기고 이전 자료는 옛
폴더에 남는다 — 실측으로 파일 191개·913MB였고, 그 사실을 알려주는 안내가 문서
어디에도 없었다. 코드와 자료가 한 폴더에 섞여 있는 것이 원인이다.

**기본값은 바꾸지 않는다**(2026-08-08 사용자 결정). 지금 쓰는 사람은 아무것도
달라지지 않고 새 폴더도 생기지 않는다 — 홈 폴더에 앱이 폴더를 만드는 것을 싫어하는
사용자가 있다. 자료를 앱 폴더 밖으로 옮기는 것은 **선택**이고, 목적지는 사용자가
찾을 수 있는 문서 폴더다.

찾는 순서:

1. `FOLIO_HOME` 환경변수 — 직접 정하고 싶은 사람용. 화면에 노출하지 않는다.
2. 앱 폴더의 `workspace.json` 표지 — 옮기기가 성공했을 때만 쓰인다.
3. 앱 폴더 `data/`에 파일이 있으면 앱 폴더 — 지금 쓰는 설치를 그대로 둔다.
4. `~/Documents/FolioOS`에 자료가 있으면 거기 — **옮긴 사용자가 새 버전을 풀었을
   때 자료를 자동으로 다시 찾는 지점이다.** 이 규칙이 없으면 옮겨도 업데이트 때
   빈 워크스페이스를 보게 되어 옮긴 의미가 없다.
5. 아니면 앱 폴더 — 기본값. 아무것도 새로 만들지 않는다.

2번(표지)이 필요한 이유: 옮기기는 **원본을 지우지 않는다**. 그래서 옮긴 직후에도
앱 폴더 `data/`에는 자료가 그대로 있고, 표지가 없으면 3번이 걸려 방금 옮긴 곳이
아니라 옛 자료를 계속 쓰게 된다. 옮기기가 아무 일도 하지 않는 것처럼 보인다.

3번이 4번보다 먼저인 이유: 표지 없는 옛 앱 폴더를 직접 실행했다면 그 폴더의 자료를
쓰는 것이 맞다. 표지는 배포 zip에 없으므로 새 버전 폴더에는 처음부터 없고, 그
경우 빈 `data/`를 지나 4번이 문서 폴더를 찾는다.
"""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

WORKSPACE_DIR_NAMES = ("data", "research-inbox", "config")
DOCUMENTS_FOLDER_NAME = "FolioOS"
MARKER_NAME = "workspace.json"


def app_root() -> Path:
    """코드가 있는 폴더. 버전마다 새로 받는 쪽이다."""
    return APP_ROOT


def marker_path() -> Path:
    """옮긴 위치를 적어두는 표지. 배포 zip에는 없다."""
    return APP_ROOT / MARKER_NAME


def documents_root() -> Path:
    """이 PC의 실제 문서 폴더.

    Windows에서 문서 폴더는 OneDrive로 리디렉션될 수 있고, 그때 `~/Documents`는
    존재하지 않거나 동기화되지 않는 다른 폴더다. 레지스트리가 진짜 위치를 안다.
    """
    if os.name == "nt":
        try:
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                raw, _ = winreg.QueryValueEx(handle, "Personal")
            resolved = os.path.expandvars(str(raw or "").strip())
            if resolved:
                return Path(resolved)
        except OSError:
            pass
    return Path.home() / "Documents"


def documents_workspace() -> Path:
    """옮기기를 선택했을 때의 목적지."""
    return documents_root() / DOCUMENTS_FOLDER_NAME


def _marker_target() -> Path | None:
    """표지가 가리키는 폴더. 없거나 못 읽거나 사라졌으면 None."""
    try:
        raw = marker_path().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # 인코딩 오류도 여기서 끝낸다. 이 함수는 import 시점에 불리므로 예외가 새면
        # 앱이 아예 켜지지 않는다 — 표지 하나 깨졌다고 그러면 안 된다.
        return None
    try:
        target = str(json.loads(raw).get("workspace") or "").strip()
    except (ValueError, AttributeError):
        return None
    if not target:
        return None
    candidate = Path(target).expanduser()
    # 사용자가 옮긴 폴더를 지웠을 수 있다. 그때는 표지를 무시하고 계속 찾는다 —
    # 없는 경로를 들고 시작하면 저장이 전부 실패한다.
    return candidate if candidate.is_dir() else None


# 사용자가 손대야만 생기는 것들. 서버가 스스로 만드는 파일은 넣지 않는다.
# `features/onboarding/service.py`가 첫 실행 판정에 쓰는 목록과 같은 뜻이며, 그쪽이
# 이 모듈을 import하므로 정의는 여기(의존성 없는 쪽)에 둔다.
USER_DATA_FILES = ("portfolio.json", "watchlist.json", "market-scope.json", "obsidian-settings.json")
USER_DATA_DIRS = ("briefings", "company-analysis", "topic-reports", "notes", "agent-threads", "investment-notes")
USER_INBOX_DIRS = ("rss", "articles", "reports", "filings", "links", "market-data")


def _has_any(directory: Path) -> bool:
    try:
        return any(directory.iterdir())
    except OSError:
        return False


def has_user_data(root: Path) -> bool:
    """이 폴더에서 사용자가 무언가를 한 적이 있는가.

    **파일이 하나라도 있는가로 물으면 안 된다.** 서버는 처음 켜질 때 스스로
    `index.json`과 빈 DB와 설정 기본값을 만든다(실측 5개). 그것을 "쓰던
    워크스페이스"로 세면, 옮긴 사용자가 새 버전을 한 번 잘못 켠 순간 앱 폴더가
    영구히 고정되고 문서 폴더 규칙은 다시는 실행되지 않는다.
    """
    data = root / "data"
    if any((data / name).is_file() for name in USER_DATA_FILES):
        return True
    if any(_has_any(data / name) for name in USER_DATA_DIRS):
        return True
    inbox = root / "research-inbox"
    return any(_has_any(inbox / name) for name in USER_INBOX_DIRS)


def _has_files(directory: Path) -> bool:
    """폴더에 파일이 하나라도 있는가. 사용자 자료 판정이 아니라 껍데기 판별용이다."""
    try:
        return any(item.is_file() for item in directory.rglob("*"))
    except OSError:
        return False


@functools.cache
def workspace_root() -> Path:
    """사용자 자료가 있는 폴더. 위 docstring의 순서를 따른다.

    한 프로세스에서 한 번만 정한다. 모듈 상수 수십 곳이 import 시점에 이 값을 읽으므로
    캐시가 없으면 그때마다 디렉터리를 훑고, 더 나쁘게는 import 도중 누군가 `data/`를
    만들면 앞뒤 모듈이 서로 다른 워크스페이스를 가리킬 수 있다. 옮기기는 재시작을
    요구하므로(설정 화면이 안내한다) 실행 중 값이 바뀔 일은 없다.
    """
    configured = str(os.environ.get("FOLIO_HOME", "") or "").strip()
    # cmd.exe의 `set VAR="값"`은 따옴표까지 값에 담는다. 따옴표는 NTFS 이름에 못 쓰는
    # 문자라 그대로 두면 모든 쓰기가 OS 층에서 실패하고, 화면은 "환경변수가 잡고 있음"만
    # 말해 원인을 짚어주지 못한다.
    configured = configured.strip('"').strip("'").strip()
    if configured:
        return Path(configured).expanduser()

    marked = _marker_target()
    if marked is not None:
        return marked

    if has_user_data(APP_ROOT):
        return APP_ROOT

    documents = documents_workspace()
    if has_user_data(documents):
        return documents

    # 사용자 자료가 어디에도 없다. 서버가 만든 파일이라도 있는 쪽을 이어 쓴다 —
    # 갓 푼 설치와 "쓰다가 자료를 다 지운 설치"를 가르는 마지막 단서다.
    if _has_files(APP_ROOT / "data"):
        return APP_ROOT

    return APP_ROOT


# 옮기기가 성공한 순간부터 재시작 전까지 True.
#
# 표지는 이미 디스크에 있으므로 지금 새로 뜨는 프로세스(수집 서브프로세스)는 **새** 폴더를
# 판정하는데, 이 프로세스의 모듈 상수 수십 곳은 import 시점의 **옛** 폴더를 그대로 들고
# 있다. 그 사이에 수집을 돌리면 Markdown은 옛 폴더에, evidence 행은 새 DB에 갈려 들어가고
# 재시작 뒤에는 파일 없는 행만 남아 그 기사가 조용히 사라진다(§6 절대 규칙 2). 정리도
# 마찬가지로 방금 복사한 사본을 지운다. 그래서 자료를 쓰는 작업은 재시작 전까지 쉰다.
_MOVED_PENDING_RESTART = False


def mark_moved_pending_restart() -> None:
    """옮기기가 표지를 쓴 직후 호출한다. 되돌리는 것은 재시작뿐이다."""
    global _MOVED_PENDING_RESTART
    _MOVED_PENDING_RESTART = True


def moved_pending_restart() -> bool:
    return _MOVED_PENDING_RESTART


def clear_moved_pending_restart() -> None:
    """옮기기가 표지를 쓰기 전에 실패했을 때만 부른다.

    복사 동안에도 수집을 쉬게 하려고 미리 표시하는데, 실패하면 워크스페이스는 하나
    그대로이므로 계속 쉬게 둘 이유가 없다.
    """
    global _MOVED_PENDING_RESTART
    _MOVED_PENDING_RESTART = False


def reset_cache() -> None:
    """테스트에서 환경을 바꾼 뒤 다시 판정하게 한다."""
    global _MOVED_PENDING_RESTART
    _MOVED_PENDING_RESTART = False
    workspace_root.cache_clear()


def workspace_dir(name: str) -> Path:
    """`data` / `research-inbox` / `config` 중 하나의 실제 경로."""
    if name not in WORKSPACE_DIR_NAMES:
        raise ValueError(f"unknown workspace directory: {name!r}")
    return workspace_root() / name


def data_dir() -> Path:
    return workspace_dir("data")


def research_inbox_dir() -> Path:
    return workspace_dir("research-inbox")


def config_dir() -> Path:
    return workspace_dir("config")


def is_outside_app_folder() -> bool:
    """자료가 앱 폴더 **밖**에 있는가. 업데이트 안내가 갈리는 기준이다.

    부등호로 물으면 앱 폴더 **안**의 하위 폴더도 "밖"이 된다. 그러면 버전 폴더 안에
    자료를 둔 사용자에게 "새 버전을 받아도 그대로 이어집니다"라고 말하게 되는데,
    다음 zip은 그 폴더째로 두고 간다 — 이 모듈이 막으려던 바로 그 결과다.
    """
    try:
        workspace_root().resolve().relative_to(APP_ROOT.resolve())
        return False
    except (ValueError, OSError):
        return True
