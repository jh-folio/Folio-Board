from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from features.common.jobs import submit_job
from features.llm_settings.client import load_dotenv, write_env_values
from features.llm_settings.model_catalog import CLI_DEFAULT_MODELS, CLI_MODEL_FALLBACKS, choices_from_catalog, discover_cli_models, normalize_model_id
from features.llm_settings.reasoning import reasoning_choices

ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = {"codex", "claude", "antigravity"}
ADAPTER_ORDER = ("codex", "claude", "antigravity")

# adapter id → 실제 실행 바이너리 이름(PATH 탐색용).
BINARY_NAMES = {"codex": "codex", "claude": "claude", "antigravity": "agy"}

MODEL_CHOICES = CLI_MODEL_FALLBACKS

INSTALL_INFO = {
    "codex": {
        "label": "Codex CLI",
        "docsUrl": "https://developers.openai.com/codex/cli/",
        "windowsCommand": "$env:CODEX_NON_INTERACTIVE=1; irm https://chatgpt.com/codex/install.ps1 | iex",
    },
    "claude": {
        "label": "Claude Code CLI",
        "docsUrl": "https://code.claude.com/docs/en/setup",
        "windowsCommand": "irm https://claude.ai/install.ps1 | iex",
    },
    "antigravity": {
        "label": "Antigravity CLI",
        "docsUrl": "https://antigravity.google/product/antigravity-cli",
        "windowsCommand": "irm https://antigravity.google/cli/install.ps1 | iex",
    },
}


def normalize_adapter(value: str) -> str:
    adapter = str(value or "").strip().lower()
    if adapter not in ADAPTERS:
        raise ValueError(f"Unsupported CLI provider: {value}")
    return adapter


def configured_model(adapter: str) -> str:
    load_dotenv()
    adapter = normalize_adapter(adapter)
    configured = str(os.environ.get(f"FOLIO_AGENT_{adapter.upper()}_MODEL", "") or "").strip()
    if configured:
        return normalize_model_id(adapter, configured)
    return CLI_DEFAULT_MODELS.get(adapter, MODEL_CHOICES[adapter][0]["value"])


def configured_provider() -> str:
    load_dotenv()
    value = str(os.environ.get("AGENT_CLI_PROVIDER", "auto") or "auto").strip().lower()
    return value if value in {"auto", *ADAPTERS} else "auto"


def settings_payload(*, refresh: bool = False) -> dict:
    from features.agent_mode.bridge import bridge_status

    if refresh:
        # 사용자가 명시적으로 누른 새로고침에서만 agy를 실제로 재본다. 상태를 볼 때마다
        # 모델을 부를 수는 없다(실측 20초). 이 경로는 원래도 CLI마다 모델을 물어 느리고,
        # 화면이 그 사실을 먼저 말한다.
        _verify_agy_file_reads()

    status = bridge_status(refresh=refresh)
    adapters = []
    for item in status.get("adapters") or []:
        adapter = item.get("id")
        bridge_supported = adapter in ADAPTERS and item.get("bridgeSupported") is not False
        catalog = discover_cli_models(adapter, executable=str(item.get("executable") or ""), refresh=refresh) if bridge_supported else {}
        model_choices = choices_from_catalog(catalog) if bridge_supported else []
        configured = configured_model(adapter) if bridge_supported else ""
        reasoning_by_model = {
            str(choice.get("value")): reasoning_choices("cli", adapter, str(choice.get("value")))
            for choice in model_choices
            if isinstance(choice, dict) and choice.get("value")
        }
        if configured and configured not in reasoning_by_model:
            reasoning_by_model[configured] = reasoning_choices("cli", adapter, configured)
        adapters.append({
            **item,
            "model": configured,
            "modelChoices": model_choices,
            "reasoningChoices": reasoning_choices("cli", adapter, configured) if bridge_supported else [],
            "reasoningByModel": reasoning_by_model,
            "modelDiscovery": {k: v for k, v in catalog.items() if k != "modelChoices"} if bridge_supported else {},
            "docsUrl": INSTALL_INFO.get(adapter, {}).get("docsUrl", ""),
            "installCommand": INSTALL_INFO.get(adapter, {}).get("windowsCommand", "") if bridge_supported and os.name == "nt" else "",
            "bridgeSupported": bridge_supported,
            "installSupported": bridge_supported and os.name == "nt",
            "loginSupported": bridge_supported,
        })
    return {
        **status,
        "provider": configured_provider(),
        "adapters": adapters,
        "platform": os.name,
    }


def _verify_agy_file_reads() -> None:
    """agy가 팩 파일을 읽을 수 있는지 실제로 시켜 보고 결과를 남긴다.

    **버전으로 판정하지 않는다**(§agy_capability). 재본 적이 없으면 브리지를 열지
    않으므로, 이 확인이 유일한 개통 경로다.
    """
    from features.agent_mode import agy_capability, bridge

    try:
        row = next(
            (item for item in bridge.bridge_status(refresh=True).get("adapters") or []
             if item.get("id") == "antigravity"),
            None,
        )
        if not row or not row.get("installed"):
            return
        version = str(row.get("version") or "")
        if agy_capability.cached_file_reads(version) is not None:
            return  # 이 버전은 이미 재봤다. 20초를 다시 쓰지 않는다.
        ok, detail = agy_capability.probe_file_reads(
            str(row.get("executable") or ""), version, configured_model("antigravity")
        )
        agy_capability.record(version, ok, detail)
        bridge.reset_agy_permission_state()
        bridge.invalidate_bridge_status()
    except Exception:
        # 확인에 실패해도 설정 화면은 떠야 한다. 못 재면 계속 막힌 상태로 남는다.
        pass


def save_settings(body: dict | None = None) -> dict:
    from features.agent_mode.bridge import invalidate_bridge_status

    data = body if isinstance(body, dict) else {}
    provider = str(data.get("provider") or "auto").strip().lower()
    if provider not in {"auto", *ADAPTERS}:
        raise ValueError(f"Unsupported CLI provider: {provider}")
    updates = {"AGENT_CLI_PROVIDER": provider}
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    for adapter in ADAPTERS:
        if adapter not in models:
            continue
        model = normalize_model_id(adapter, models.get(adapter, ""))
        if not model:
            continue
        if len(model) > 120 or any(ch.isspace() for ch in model):
            raise ValueError(f"Unsupported {adapter} model: {model}")
        updates[f"FOLIO_AGENT_{adapter.upper()}_MODEL"] = model
        models[adapter] = model
    write_env_values(updates)
    invalidate_bridge_status()
    # 실제 상태를 다시 재서 돌려준다. 예전에는 탐지 비용을 아끼려고 모든 어댑터를
    # `installed: False`로 채운 자리표시자를 냈는데, 화면은 그것을 그대로 "미설치"로
    # 그렸다 — 저장을 누를 때마다 설치돼 있는 CLI가 사라졌다 나타났다.
    #
    # `refresh=False`다. 바로 위에서 캐시를 버렸으므로 설치/로그인 상태는 다시 재고(1초),
    # 모델 목록은 캐시를 쓴다. `refresh=True`로 두면 CLI마다 모델을 다시 물어 20초가
    # 걸린다 — 저장 버튼이 20초 동안 멈춘다.
    return settings_payload(refresh=False)


def _windows_install_command(adapter: str) -> list[str]:
    adapter = normalize_adapter(adapter)
    if os.name != "nt":
        raise RuntimeError("웹 설치는 현재 Windows에서만 지원합니다. 공식 설치 문서를 이용하세요.")
    script = INSTALL_INFO[adapter]["windowsCommand"]
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell을 찾을 수 없습니다.")
    return [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


def _installed_path_candidates(adapter: str) -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    home = Path.home()
    if adapter == "codex":
        return [local / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"]
    if adapter == "antigravity":
        # 설치 경로가 공개되어 있지 않으므로 PATH의 `agy`를 우선 사용한다.
        return [home / ".local" / "bin" / "agy.exe", local / "Programs" / "Antigravity" / "agy.exe"]
    return [home / ".local" / "bin" / "claude.exe", local / "Programs" / "Claude" / "claude.exe"]


def install_cli(adapter: str, *, progress=None, job_id: str = "") -> dict:
    from features.agent_mode.bridge import invalidate_bridge_status

    adapter = normalize_adapter(adapter)
    progress = progress or (lambda *args, **kwargs: None)
    progress(f"{INSTALL_INFO[adapter]['label']} 공식 설치 스크립트를 실행하고 있습니다.", 10)
    command = _windows_install_command(adapter)
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if proc.returncode != 0:
        error = (proc.stderr or proc.stdout or "installation failed").strip()[-3000:]
        raise RuntimeError(f"{INSTALL_INFO[adapter]['label']} 설치 실패: {error}")
    updates = {}
    candidates = list(_installed_path_candidates(adapter))
    discovered = shutil.which(BINARY_NAMES.get(adapter, adapter))
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.exists():
            updates[f"FOLIO_AGENT_{adapter.upper()}_COMMAND"] = str(candidate)
            break
    if updates:
        write_env_values(updates)
    invalidate_bridge_status()
    progress("설치가 완료되었습니다. 로그인 상태를 확인하세요.", 100)
    return {
        "ok": True,
        "adapter": adapter,
        "message": f"{INSTALL_INFO[adapter]['label']} 설치가 완료되었습니다.",
        "settings": settings_payload(refresh=True),
    }


def submit_install(adapter: str) -> dict:
    adapter = normalize_adapter(adapter)
    return submit_job(
        "agent_cli_install",
        f"{INSTALL_INFO[adapter]['label']} 설치",
        install_cli,
        adapter,
        pass_job_id=True,
        dedicated_thread=True,
    )


def launch_login(adapter: str) -> dict:
    from features.agent_mode.bridge import bridge_status, invalidate_bridge_status

    adapter = normalize_adapter(adapter)
    status = bridge_status(refresh=True)
    item = next((row for row in status.get("adapters") or [] if row.get("id") == adapter), None)
    executable = str((item or {}).get("executable") or "")
    if not executable or not (item or {}).get("installed"):
        raise RuntimeError(f"{INSTALL_INFO[adapter]['label']}가 설치되어 있지 않거나 실행할 수 없습니다.")
    if adapter == "codex":
        args = [executable, "login"]
    elif adapter == "antigravity":
        # agy는 인자 없이 실행하면 브라우저 OAuth 로그인 흐름을 연다.
        args = [executable]
    else:
        args = [executable, "auth", "login"]
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    subprocess.Popen(args, cwd=ROOT, creationflags=creationflags)
    invalidate_bridge_status()
    return {
        "ok": True,
        "adapter": adapter,
        "message": "로그인 창을 열었습니다. 로그인 완료 후 상태 새로고침을 누르세요.",
    }
