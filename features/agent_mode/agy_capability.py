"""agy가 **실제로** 팩 파일을 읽을 수 있는지 재서 기록한다.

**조회 파일은 반드시 실제 팩과 같은 폴더에 만든다.** 처음에는 `%TEMP%`에 만들었는데
그건 통과하고 진짜 팩은 거부당했다. 실측으로 갈린 것은 크기가 아니라 위치다:

    프로젝트 안 12바이트 파일  → 권한 거부
    %TEMP%의 5.2MB 파일        → 성공

agy headless는 프로젝트 안의 읽기를 거부한다. 바깥에 만든 파일로 재면 "된다"는 답을
받고 브리지를 열게 되는데, 그것이 정확히 지난번에 저지른 실수의 반복이다.

**버전 숫자로 판정하지 않는다.** 예전 게이트가 그랬다가 크게 틀렸다 — agy 1.0.10의
headless 출력 버그가 1.1.7에서 고쳐진 것을 짧은 프롬프트 하나로 확인하고 브리지를
열었는데, 정작 Folio Board의 Agent task는 전부 5.2MB 컨텍스트 팩 **파일을 읽는 것으로
시작**한다. 그 경로는 한 번도 돌려보지 않았다.

결과는 agy 1.1.12 headless가 파일 읽기 권한을 자동 거부하는 것이었고, 게이트를 연
뒤 실행된 Agent 잡 두 건이 모두 실패했다(그전까지 antigravity로 성공한 잡은 한 건도
없다). 버전 비교는 권한 문제를 **구조적으로** 볼 수 없다.

그래서 여기서는 임시 파일 하나를 만들고 **그것을 읽어 오라고 실제로 시킨다.** 통과해야
브리지를 연다. 모르면 막는다 — 열어 두고 예약 브리핑이 밤새 실패하는 쪽이 훨씬 나쁘다.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from features.common.utils import read_json, write_json, now_iso
from features.common.workspace import data_dir

CACHE_PATH = data_dir() / "agent-cli-capability.json"
# 진짜 컨텍스트 팩이 놓이는 곳. 조회도 여기서 해야 같은 조건이다.
PROBE_DIR = data_dir() / "agent-context"

# 조회는 모델을 한 번 부르는 일이라 오래 걸린다. 상태를 볼 때마다 치를 수 없어 캐시한다.
# 실측 20초.
PROBE_TIMEOUT_SECONDS = 120


def _load() -> dict:
    raw = read_json(CACHE_PATH, {}) or {}
    return raw if isinstance(raw, dict) else {}


def cached_file_reads(version: str) -> bool | None:
    """`True`/`False`는 그 버전으로 실제 재본 결과. `None`은 아직 안 재봤다는 뜻이다.

    **`None`을 "된다"로 읽지 않는다.** 모르는 것을 된다고 가정한 것이 지난 실수다.
    """
    row = _load().get("antigravity")
    if not isinstance(row, dict):
        return None
    if str(row.get("version") or "") != str(version or ""):
        # 판올림하면 다시 재야 한다. 고쳐졌을 수도, 새로 깨졌을 수도 있다.
        return None
    value = row.get("fileReads")
    return value if isinstance(value, bool) else None


def record(version: str, file_reads: bool, detail: str = "") -> None:
    data = _load()
    data["antigravity"] = {
        "version": str(version or ""),
        "fileReads": bool(file_reads),
        "checkedAt": now_iso(),
        "detail": str(detail or "")[:400],
    }
    try:
        write_json(CACHE_PATH, data)
    except Exception:
        # 기록에 실패해도 이번 판정은 유효하다. 다음에 다시 잴 뿐이다.
        pass


def probe_file_reads(executable: str, version: str, model: str = "") -> tuple[bool, str]:
    """임시 파일을 읽어 오라고 시켜 본다. 통과하면 브리지를 열어도 된다.

    팩을 통째로 읽히지 않고 한 줄짜리 파일로 확인한다 — 실측으로 막히는 지점은 크기가
    아니라 위치이고, 5MB를 읽히면 조회에 몇 분이 걸린다. 대신 **위치는 실제 팩과 같은
    폴더**여야 한다(§모듈 주석).
    """
    if not executable:
        return False, "실행 파일을 찾을 수 없습니다."
    token = f"FOLIO-{uuid.uuid4().hex[:12].upper()}"
    tmp = PROBE_DIR / f"folio-agy-probe-{uuid.uuid4().hex[:8]}.txt"
    try:
        PROBE_DIR.mkdir(parents=True, exist_ok=True)
        tmp.write_text(token, encoding="utf-8")
        command = [executable]
        if model:
            command.extend(["--model", model])
        command.extend([
            "--print",
            f"Read the file {tmp} and reply with only its contents. Do not add anything else.",
        ])
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        if token in (proc.stdout or ""):
            return True, ""
        detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[-300:]
        return False, detail
    except subprocess.TimeoutExpired:
        return False, f"조회가 {PROBE_TIMEOUT_SECONDS}초를 넘겼습니다."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:300]
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
