"""워크스페이스 위치 조회와 옮기기.

`workspace.py`는 모듈 37곳이 import 시점에 읽으므로 의존성 없이 순수 판정만 둔다.
무겁거나 부수효과가 있는 것(용량 집계, 복사, 탐색기 열기)은 여기에 있다.

**원본을 지우지 않는다.** 복사하고 검증한 뒤 앱 폴더에 표지를 남길 뿐이다. 913MB를
옮기다 중간에 실패했을 때 사용자에게 남는 것이 반쪽짜리 사본 하나뿐이면 안 된다.
지운 자료는 되돌릴 수 없고, 남겨둔 자료는 사용자가 언제든 지울 수 있다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from features.common import workspace
from features.common.atomic_replace import write_bytes_atomic
from features.common.workspace import (
    APP_ROOT,
    WORKSPACE_DIR_NAMES,
    is_outside_app_folder,
    marker_path,
    reset_cache,
    workspace_root,
)

# 위치를 알아내는 함수는 이름으로 가져오지 않고 모듈을 통해 부른다. 이름으로 가져오면
# 여기에 사본 바인딩이 생겨, 테스트가 `workspace.documents_root`를 갈아끼워도 이 파일만
# 진짜 레지스트리를 읽는다 — 두 함수가 서로 다른 문서 폴더를 보게 된다.


class WorkspaceMoveError(Exception):
    """옮기기를 시작할 수 없거나 검증에 실패했다."""


# SQLite가 옆에 두는 파생 파일. 복사하지도 검증하지도 않는다.
#
# 이것 때문에 옮기기가 **항상** 실패했다. 서버가 도는 동안 WAL은 쉬지 않고 커지는데
# (실측 120초에 117MB → 469MB), 1GB 복사는 몇 분이 걸린다. 복사가 끝난 뒤 원본을
# 다시 재는 `_verify`는 그 사이 달라진 WAL을 보고 "복사한 자료가 원본과 다릅니다"를
# 냈다. 파일이 실제로 상한 적은 없다.
#
# 게다가 살아 있는 WAL을 그대로 복사하면 목적지 DB가 어중간한 상태가 된다. 복사 전에
# 체크포인트해서 본체 파일로 접어 넣고, 곁다리는 두고 간다 — SQLite가 다시 만든다.
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def _is_sqlite_sidecar(path: Path) -> bool:
    return path.name.endswith(SQLITE_SIDECAR_SUFFIXES)


def _checkpoint_sqlite(root: Path) -> list[str]:
    """WAL을 본체 파일로 접어 넣어 복사본이 그 자체로 완결되게 한다.

    **`PRAGMA wal_checkpoint`는 실패해도 예외를 던지지 않는다.** 접지 못하면
    `(busy, log, checkpointed)`의 `busy=1`로 *돌려줄* 뿐이다. 그 행을 읽지 않으면
    "성공"으로 보이고, 곁다리는 복사에서 빠지므로 아직 WAL에만 있던 커밋이 통째로
    사라진다(실측: 리더가 스냅샷을 쥔 상태에서 `(1, 6, 2)`를 받고, 복사본을 열면
    `no such table`). 서버가 살아 있는 채로 설정 화면에서 누르는 것이 정상 사용법이라
    busy는 예외가 아니라 기본값이다.

    그래서 몇 번 물러나며 다시 시도하고, 끝내 접지 못한 DB는 이름을 돌려준다.
    호출부가 그것을 보고 옮기기를 **중단한다** — 반쪽 DB를 성공이라고 말하지 않는다.
    """
    import sqlite3
    import time

    failed: list[str] = []
    for name in WORKSPACE_DIR_NAMES:
        directory = root / name
        if not directory.is_dir():
            continue
        for db in directory.rglob("*.sqlite3"):
            busy = True
            try:
                conn = sqlite3.connect(str(db), timeout=10)
                try:
                    for attempt in range(5):
                        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                        busy = bool(row[0]) if row else False
                        if not busy:
                            break
                        time.sleep(0.2 * (attempt + 1))
                finally:
                    conn.close()
            except Exception:  # noqa: BLE001 - 못 연 DB도 접지 못한 것으로 센다
                busy = True
            if busy:
                failed.append(db.name)
    return failed


def _clear_destination_sidecars(target: Path) -> None:
    """복사한 본체 옆에 남아 있던 **목적지의** 곁다리를 지운다.

    `copytree`는 목적지에서 아무것도 지우지 않고, 곁다리는 원본 목록에서 빠져 있으므로
    예전 크래시가 남긴 `-wal`이 그대로 살아남는다. 그러면 SQLite가 다음 시작에 그것을
    **새로 복사한 본체 위에 재생해** 옛 자료로 되돌린다 — `integrity_check`도 `_verify`도
    통과하므로, 사용자가 "새 위치를 확인"하는 화면이 옛 자료다.
    """
    for name in WORKSPACE_DIR_NAMES:
        directory = target / name
        if not directory.is_dir():
            continue
        for db in directory.rglob("*.sqlite3"):
            for suffix in SQLITE_SIDECAR_SUFFIXES:
                sidecar = db.with_name(db.name + suffix)
                try:
                    sidecar.unlink()
                except OSError:
                    continue


def _usage(root: Path) -> tuple[int, int]:
    """(파일 수, 바이트). 세는 도중 파일이 사라져도 죽지 않는다.

    SQLite 곁다리도 센다. 복사에서는 빼지만 디스크에 실제로 차지하는 바이트이고,
    공간 검사에서는 넉넉히 잡는 쪽이 안전하다 — WAL에 든 내용은 체크포인트 뒤
    본체 파일로 옮겨 가므로 빼고 세면 필요한 공간을 과소평가한다(실측: 1.8MB WAL을
    빼자 총량이 1.88MB에서 9KB로 떨어졌다).
    """
    files = 0
    total = 0
    for name in WORKSPACE_DIR_NAMES:
        directory = root / name
        if not directory.is_dir():
            continue
        for item in directory.rglob("*"):
            try:
                if item.is_file():
                    files += 1
                    total += item.stat().st_size
            except OSError:
                continue
    return files, total


def _is_onedrive(path: Path) -> bool:
    """OneDrive 아래인가.

    동기화 폴더에 700MB SQLite를 두면 저장할 때마다 업로드가 돌고, 두 PC에서 같은
    파일을 열면 충돌 사본이 생긴다. 막지는 않되 무슨 일이 생길지는 먼저 말한다.
    """
    marks = {str(os.environ.get("OneDrive", "") or ""), str(os.environ.get("OneDriveCommercial", "") or "")}
    text = str(path).replace("/", "\\").lower()
    for mark in marks:
        if mark and text.startswith(mark.replace("/", "\\").lower()):
            return True
    return "\\onedrive" in text


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _env_pinned() -> bool:
    """`FOLIO_HOME`이 위치를 잡고 있는가.

    이 경우 옮기기는 의미가 없다. 표지를 써도 다음 시작에서 환경변수가 이긴다 —
    "옮겼으니 재시작하세요"라고 말해놓고 재시작하면 그대로인 것은 거짓말이다.
    """
    return bool(str(os.environ.get("FOLIO_HOME", "") or "").strip())


def workspace_payload() -> dict:
    """설정 화면이 읽는 현재 상태."""
    root = workspace_root()
    files, total = _usage(root)
    # 자료가 있는 문서 폴더(새 이름 우선, 구 이름 폴백)를 먼저 본다. 이동 목적지
    # 함수(`documents_workspace()`)만 쓰면 구 문서 폴더를 쓰는 사용자에게 자신이
    # 쓰지 않는 `~/Documents/FolioBoard`를 보여주게 된다(§4.4) — 아무 후보에도
    # 자료가 없을 때만(즉 옮기기가 아직 실행된 적이 없을 때만) 목적지로 폴백한다.
    documents = workspace.discover_documents_workspace() or workspace.documents_workspace()
    pinned = _env_pinned()
    return {
        "path": str(root),
        "appFolder": str(APP_ROOT),
        "outsideAppFolder": is_outside_app_folder(),
        "fileCount": files,
        "totalBytes": total,
        "documentsPath": str(documents),
        "documentsAvailable": workspace.documents_root().is_dir(),
        "documentsIsOneDrive": _is_onedrive(documents),
        "envPinned": pinned,
        "canMoveToDocuments": not pinned and not is_outside_app_folder(),
        "canMoveToAppFolder": not pinned and is_outside_app_folder(),
        "directories": list(WORKSPACE_DIR_NAMES),
    }


def _write_marker(target: Path) -> None:
    payload = json.dumps({"workspace": str(target)}, ensure_ascii=False, indent=2) + "\n"
    write_bytes_atomic(marker_path(), payload.encode("utf-8"))


def _clear_marker() -> None:
    """표지를 지운다. 실패는 삼키지 않는다.

    쓰기는 `write_bytes_atomic`이 `PermissionError`를 여섯 번 물러나며 재시도하는데
    삭제만 첫 거절에 포기하면, 백신이 잠깐 잡은 것만으로 표지가 살아남는다. 그러면
    "앱 폴더로 되돌렸습니다"라고 말해 놓고 재시작 뒤에도 문서 폴더를 쓰게 되고,
    화면 안내대로 원본을 지운 사용자는 **살아 있는 워크스페이스를 지운다**.
    """
    path = marker_path()
    for attempt in range(6):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.01 * (2**attempt))
        except OSError as exc:
            raise WorkspaceMoveError(f"이전 위치 표지를 지우지 못했습니다: {exc}") from exc
    raise WorkspaceMoveError(
        "이전 위치 표지(workspace.json)를 지우지 못했습니다. 다른 프로그램이 잡고 있을 수 "
        "있습니다. 잠시 뒤 다시 시도하거나 파일을 직접 지운 뒤 재시작하세요."
    )


def _verify(source: Path, target: Path) -> list[str]:
    """원본의 모든 파일이 같은 크기로 도착했는지 확인한다.

    복사가 조용히 반쪽만 되는 경우가 있다 — 디스크가 차거나 백신이 파일 하나를
    잡거나. 표지를 쓰기 전에 확인하지 않으면 사용자는 자료가 사라진 것처럼 본다.
    """
    problems: list[str] = []
    for name in WORKSPACE_DIR_NAMES:
        origin = source / name
        if not origin.is_dir():
            continue
        for item in origin.rglob("*"):
            try:
                if not item.is_file() or _is_sqlite_sidecar(item):
                    continue
                expected = item.stat().st_size
            except OSError:
                continue
            copy = target / name / item.relative_to(origin)
            try:
                if copy.stat().st_size != expected:
                    problems.append(str(item.relative_to(source)))
            except OSError:
                problems.append(str(item.relative_to(source)))
            if len(problems) >= 10:
                return problems
    return problems


def move_workspace(destination: str, *, merge: bool = False) -> dict:
    """자료를 복사하고 검증한 뒤 표지를 남긴다. 원본은 그대로 둔다.

    `destination`은 `documents` 또는 `app`이다. 임의 경로를 받지 않는다 — 화면에
    폴더 선택기가 없고, 서버가 받은 문자열로 아무 데나 쓰게 두면 곤란하다.

    목적지에 이미 자료가 있으면 `merge` 없이는 진행하지 않는다. 옮기기는 덮어쓰기가
    아니라 합치기라서, 목적지에만 있던 파일은 그대로 남는다 — 앱 폴더로 되돌릴 때
    예전에 지운 보고서가 되살아난다. 조용히 그러면 안 된다.
    """
    if _env_pinned():
        raise WorkspaceMoveError(
            "FOLIO_HOME 환경변수가 자료 위치를 정하고 있어 여기서 옮길 수 없습니다. "
            "환경변수를 지운 뒤 다시 시도하세요."
        )

    source = workspace_root()
    if destination == "documents":
        target = workspace.documents_workspace()
    elif destination == "app":
        target = APP_ROOT
    else:
        raise WorkspaceMoveError(f"알 수 없는 목적지입니다: {destination!r}")

    if target.resolve() == source.resolve():
        raise WorkspaceMoveError("이미 그 위치를 쓰고 있습니다.")
    if _inside(target, source):
        raise WorkspaceMoveError("자료 폴더 안으로는 옮길 수 없습니다.")

    existing, _ = _usage(target)
    if existing and not merge:
        raise WorkspaceMoveError(
            f"그 위치에 이미 자료 {existing}개가 있습니다. 합치면 **이름이 같은 파일은 "
            "지금 자료로 덮어씁니다**(되돌릴 수 없습니다). 그쪽에만 있던 파일은 그대로 "
            "남습니다."
        )

    files, total = _usage(source)
    free = shutil.disk_usage(target.parent if not target.exists() else target).free
    # 여유를 조금 둔다. 딱 맞게 남았다면 복사 도중 다른 프로그램이 먼저 채운다.
    if free < total * 1.1:
        raise WorkspaceMoveError(
            f"공간이 부족합니다. {_human(total)}가 필요한데 {_human(free)}가 남아 있습니다."
        )

    # 복사가 시작되기 **전에** 자료를 쓰는 작업을 쉬게 한다. 예전에는 검증까지 끝난 뒤에
    # 표시해서, 매시 수집이 복사 도중에 끼어들면 (a) 그 파일들이 원본에만 남고 — 화면은
    # 곧 원본을 지우라고 안내한다 — (b) `_verify`가 복사 뒤 늘어난 원본과 대조해 900MB를
    # 옮기고도 "원본과 다릅니다"로 중단됐다.
    workspace.mark_moved_pending_restart()
    try:
        # 복사 전에 WAL을 본체로 접어 넣는다. 그래야 목적지 DB가 그 자체로 완결된다.
        checkpoint_failed = _checkpoint_sqlite(source)
        if checkpoint_failed:
            # 접지 못한 WAL을 두고 본체만 복사하면 그 안의 커밋이 통째로 사라진다.
            # 성공이라고 말하고 원본을 지우게 하느니 여기서 멈춘다.
            raise WorkspaceMoveError(
                "데이터베이스를 정리하지 못해 옮기기를 중단했습니다. 다른 작업이 자료를 쓰고 "
                "있을 수 있습니다. 서버를 재시작한 뒤 바로 다시 시도하면 대부분 해결됩니다. "
                f"({', '.join(checkpoint_failed)})"
            )

        target.mkdir(parents=True, exist_ok=True)
        copied = []
        ignore = shutil.ignore_patterns(*(f"*{suffix}" for suffix in SQLITE_SIDECAR_SUFFIXES))
        for name in WORKSPACE_DIR_NAMES:
            origin = source / name
            if not origin.is_dir():
                continue
            try:
                shutil.copytree(origin, target / name, dirs_exist_ok=True, ignore=ignore)
            except OSError as exc:
                # `shutil.Error`는 `OSError`라서 그대로 두면 라우터가 잡지 못하고 500이 된다.
                # 사용자가 알아야 할 것은 셋이다: 원본은 그대로다, 목적지에 반쪽이 남았다,
                # 다시 시도하려면 그것을 지워야 한다.
                raise WorkspaceMoveError(
                    f"복사 도중 실패했습니다: {exc}. 원본({source})은 그대로 있습니다. "
                    f"목적지({target})에 복사하다 만 파일이 남아 있으니 지운 뒤 다시 시도하세요."
                ) from exc
            copied.append(name)

        # 목적지에 남아 있던 남의 곁다리를 치운다. 두면 다음 시작에 그것이 새 본체 위로
        # 재생되어 옛 자료로 되돌아간다.
        _clear_destination_sidecars(target)

        problems = _verify(source, target)
        if problems:
            raise WorkspaceMoveError(
                "복사한 자료가 원본과 다릅니다. 원본은 그대로 있으니 다시 시도해 주세요. "
                f"({len(problems)}개 이상: {', '.join(problems[:3])})"
            )

        if destination == "app":
            _clear_marker()
        else:
            _write_marker(target)
    except Exception:
        # 표지를 쓰지 못했으니 워크스페이스는 하나 그대로다. 계속 쉬게 둘 이유가 없다.
        workspace.clear_moved_pending_restart()
        raise

    reset_cache()
    # 표지를 쓴 순간부터 이 프로세스는 두 워크스페이스를 동시에 본다 — 모듈 상수는 옛
    # 폴더, 새로 판정하는 경로와 수집 서브프로세스는 새 폴더다. 재시작 전까지 자료를
    # 쓰는 작업(수집·정리)을 쉬게 해서 새 자료가 두 폴더로 갈리지 않게 한다.
    # (`reset_cache()`가 플래그를 지우므로 그 뒤에 다시 표시한다.)
    workspace.mark_moved_pending_restart()

    return {
        "path": str(target),
        "previousPath": str(source),
        "fileCount": files,
        "totalBytes": total,
        "copied": copied,
        # 재시작 전까지 RSS 수집과 보관 기간 정리가 쉰다. 화면이 재시작을 안내한다.
        "collectionPausedUntilRestart": True,
        # 접어 넣지 못한 DB가 있으면 알린다. 자료가 상한 것은 아니지만(SQLite가 목적지에서
        # 복구한다) 무슨 일이 있었는지는 숨기지 않는다.
        "checkpointFailed": checkpoint_failed,
        "restartRequired": True,
    }


def reveal_workspace() -> dict:
    """자료 폴더를 파일 탐색기에서 연다."""
    root = workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(root))  # noqa: S606 - 사용자 자신의 폴더다
        elif sys.platform == "darwin":
            subprocess.run(["open", str(root)], check=True)
        else:
            subprocess.run(["xdg-open", str(root)], check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceMoveError(f"폴더를 열지 못했습니다: {exc}") from exc
    return {"path": str(root)}


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
