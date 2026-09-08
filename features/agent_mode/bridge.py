from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import CancelledError
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from pathlib import Path

from features.agent_mode import schema
from features.agent_mode import service as agent_service
from features.agent_mode import job_runtime
from features.common.quality_generation.call_budget import SharedRepairBudget, bind_briefing_budget, current_briefing_budget
from features.agent_mode.briefing_contract import briefing_contract_violations
from features.company_analysis.report_contract import (
    missing_sections as company_missing_sections,
    render_section_retry as company_section_retry,
)
from features.common.jobs import (
    cancel_job,
    diagnostic_execution,
    diagnostic_stage_end,
    diagnostic_stage_failure,
    diagnostic_stage_start,
    get_job,
    submit_job,
)
from features.common.shared_jobs_schema import TaskType
from features.llm_settings.client import load_dotenv
from features.common.workspace import data_dir
from features.llm_settings.reasoning import is_supported_reasoning_effort
from features.llm_settings.task_policy import CLI_REASONING_EFFORTS, TaskPolicyError
from features.llm_settings.task_runtime import (
    bind_task_policy,
    current_task_policy,
    generation_mode as task_generation_mode,
    task_is_enabled,
    task_policy_metadata,
    task_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_SECONDS = 1800
MAX_OUTPUT_CHARS = 4_000_000
# 어댑터 사용량 한도. 코드 결함과 대처가 완전히 다르므로(기다리면 된다 vs 고쳐야 한다)
# 일반 실행 실패와 구분해 올린다 — 예전에는 잡에 `adapter_failed`만 남아 CLI 세션
# 기록을 직접 열어야만 429였다는 사실을 알 수 있었다.
_RATE_LIMIT_MARKS = (
    "hit your session limit",
    "hit your usage limit",
    "hit your weekly limit",
    "rate_limit",
    "rate limit",
    "429",
)


class AgentRateLimitError(RuntimeError):
    """어댑터 사용량 한도. `resetHint`는 CLI가 알려 준 리셋 시각 문구."""

    def __init__(self, message: str, reset_hint: str = "") -> None:
        super().__init__(message)
        self.reset_hint = reset_hint


class AgentProcessError(RuntimeError):
    """A completed CLI process returned no usable successful result."""


class AgentAdapterUnavailableError(RuntimeError):
    """The selected, already-inspected adapter was not ready to execute."""


class AgentOutputValidationError(RuntimeError):
    """The bridge's own closed output-contract validator rejected a result."""


def rate_limit_hint(text: str) -> str | None:
    """사용량 한도 표지가 있으면 리셋 시각 문구(없으면 빈 문자열)를 돌려준다."""
    blob = str(text or "")
    folded = blob.casefold()
    if not any(mark in folded for mark in _RATE_LIMIT_MARKS):
        return None
    lowered = blob.lower()
    at = lowered.find("resets")
    if at < 0:
        return ""
    # 줄 하나만 본다. CLI가 "resets 9pm (Asia/Seoul)"처럼 알려 준다.
    tail = blob[at:].splitlines()[0]
    return " ".join(tail.split())[:80]


ADAPTERS = ("codex", "claude", "antigravity")
STATUS_ADAPTERS = ADAPTERS
# adapter id → 실제 실행 바이너리 이름.
BINARY_NAMES = {"codex": "codex", "claude": "claude", "antigravity": "agy"}

# agy headless가 파일 읽기를 거부했다는 표시. Folio OS의 Agent task는 **전부** 컨텍스트
# 팩 파일을 읽는 것으로 시작하므로(팩이 5MB라 프롬프트에 넣을 수 없다), 이 권한이 없으면
# 브리핑·기업분석 같은 task를 아예 만들 수 없다. 대화처럼 파일을 안 읽는 호출은 된다.
AGY_PERMISSION_DENIED_MARK = 'the "read_file" permission'
AGY_PERMISSION_HELP = (
    "Antigravity(agy)의 headless 모드가 파일 읽기 권한을 자동 거부했습니다. Folio OS의 "
    "브리핑·기업분석은 컨텍스트 팩 파일을 읽어야 하므로 이 상태에서는 만들 수 없습니다. "
    "설정에서 Codex나 Claude CLI로 바꾸거나, "
    "`~/.gemini/antigravity-cli/settings.json`의 permissions.allow에 read_file 규칙을 "
    "추가하세요."
)

AGY_UNVERIFIED_HELP = (
    "Antigravity(agy)가 컨텍스트 팩 파일을 읽을 수 있는지 아직 확인하지 않았습니다. "
    "Folio OS의 브리핑·기업분석은 팩 파일을 읽어야 하므로 확인 전에는 열지 않습니다. "
    "설정 > AI Agent에서 `상태 새로고침`을 누르면 실제로 확인합니다(약 20초). "
    "그동안은 Codex나 Claude CLI를 사용하세요."
)

# 한 번 거부당하면 같은 실행에서 다시 시도하지 않는다. 예약 브리핑이 매번 팩을 만들고
# 수 분을 버린 뒤 같은 곳에서 실패했다(실측 8분 30초).
_AGY_FILE_READS_BLOCKED = False

_STATUS_CACHE: tuple[float, dict] | None = None
_STATUS_LOCK = threading.Lock()
_PROCESS_LOCK = threading.Lock()
_RUNNING_PROCESSES: dict[str, subprocess.Popen] = {}
_RUN_SEMAPHORE = threading.Semaphore(1)


def _queued_task_snapshot(task_type: str, params: dict) -> dict | None:
    """Resolve a user-visible task policy once when a bridge job is accepted."""
    try:
        existing = params.get("_task_policy_snapshot")
        return task_snapshot(task_type, existing if isinstance(existing, dict) else None)
    except TaskPolicyError as error:
        # Internal bridge jobs (quality repair, planner helpers, and legacy
        # tasks) are intentionally outside the user-visible task list.
        if error.code == "task_policy_unknown_task":
            return None
        raise


def _bridge_task_gate(snapshot: dict | None) -> dict | None:
    """Return a no-engine result when the global gate was turned off in queue."""
    if snapshot is None or task_is_enabled(snapshot, recheck_global=True):
        return None
    return {
        "generationMode": "rules",
        "artifactType": str(snapshot.get("runtimeTaskType") or snapshot.get("taskKey") or "agent_task"),
        "policy": task_policy_metadata(snapshot),
        "message": "전역 AI Agent가 꺼져 있어 이 작업은 실행하지 않았습니다.",
    }


def _prepare_bridge_params(task_type: str, params: dict | None, adapter: str) -> tuple[dict, str, dict | None]:
    payload = dict(params) if isinstance(params, dict) else {}
    snapshot = _queued_task_snapshot(task_type, payload)
    if snapshot is None:
        return payload, str(adapter or ""), None
    payload["_task_policy_snapshot"] = snapshot
    selected_adapter = str(snapshot.get("provider") or adapter or "")
    return payload, selected_adapter, snapshot

# A briefing child should not inherit desktop browser/computer-use channels.  The
# policy is intentionally task-local: ContextVar keeps a concurrent Agent task
# (or a later ordinary chat) on its own tool policy.
_BRIEFING_CODEX_TOOL_POLICY: ContextVar[tuple[str, ...]] = ContextVar(
    "briefing_codex_tool_policy", default=()
)
_BRIEFING_DISABLED_CODEX_FEATURES = (
    "plugins",
    "browser_use",
    "browser_use_external",
    "computer_use",
)
# `node_repl` can be configured as either stdio or URL transport.  Add only its
# enable override after the CLI itself resolves whether that legacy server exists;
# replacing its table would corrupt URL transport settings.
_BRIEFING_DISABLED_NODE_REPL = "mcp_servers.node_repl.enabled=false"
_BRIEFING_MCP_DISCOVERY_TIMEOUT_SECONDS = 8


@contextmanager
def _diagnostic_boundary(stage_code: str, boundary: str):
    """Observe a concrete bridge boundary without changing bridge behavior."""
    recorder, stage_id = diagnostic_stage_start(stage_code)
    try:
        yield
    except Exception as error:
        diagnostic_stage_failure(
            recorder,
            error,
            stage_id=stage_id,
            stage_code=stage_code if stage_id is not None else None,
            boundary=boundary,
        )
        raise
    else:
        diagnostic_stage_end(recorder, stage_id, stage_code)


@contextmanager
def _observed_tool_policy(task_type: str, selected: dict):
    """Enter the concrete tool policy under a short preflight observation."""
    recorder, stage_id = diagnostic_stage_start("preflight")
    entered = False
    try:
        with _briefing_codex_tool_policy(task_type, selected):
            entered = True
            diagnostic_stage_end(recorder, stage_id, "preflight")
            yield
    except Exception as error:
        # Only policy entry belongs to preflight.  Failures from the enclosed
        # task already have their own context/generate/validate/commit stage.
        if not entered:
            diagnostic_stage_failure(
                recorder,
                error,
                stage_id=stage_id,
                stage_code="preflight" if stage_id is not None else None,
                boundary="adapter",
            )
            diagnostic_stage_end(recorder, stage_id, "preflight")
        raise


def _briefing_mcp_server_names(adapter: dict) -> frozenset[str]:
    """Ask Codex which non-plugin MCP servers this child would inherit.

    This is configuration discovery only: no model, MCP server, browser, or
    computer-use tool is started.  Keep failures terse because CLI output may
    contain user configuration details.
    """
    command = [
        adapter["executable"], "mcp", "list", "--json",
        "-c", "features.plugins=false",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_child_environment(),
            timeout=_BRIEFING_MCP_DISCOVERY_TIMEOUT_SECONDS,
            creationflags=_creation_flags(),
        )
        if result.returncode != 0:
            raise RuntimeError("nonzero")
        payload = json.loads(result.stdout or "")
        if isinstance(payload, list):
            servers = payload
        elif isinstance(payload, dict):
            servers = payload.get("mcp_servers", payload.get("servers"))
        else:
            servers = None
        if not isinstance(servers, list):
            raise ValueError("invalid_mcp_list")
        names: set[str] = set()
        for server in servers:
            if not isinstance(server, dict):
                raise ValueError("invalid_mcp_server")
            name = server.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("invalid_mcp_server_name")
            names.add(name.strip())
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError, ValueError, RuntimeError):
        raise RuntimeError("브리핑용 Codex MCP 구성을 확인하지 못했습니다. 다시 시도하세요.") from None
    return frozenset(names)


def _briefing_codex_tool_policy_overrides(adapter: dict) -> tuple[str, ...]:
    args: list[str] = []
    for feature in _BRIEFING_DISABLED_CODEX_FEATURES:
        args.extend(["-c", f"features.{feature}=false"])
    if "node_repl" in _briefing_mcp_server_names(adapter):
        args.extend(["-c", _BRIEFING_DISABLED_NODE_REPL])
    return tuple(args)


@contextmanager
def _briefing_codex_tool_policy(task_type: str, adapter: dict):
    """Limit only Codex invocations belonging to one briefing task."""
    token = None
    if task_type == "briefing" and str(adapter.get("id") or "").strip().lower() == "codex":
        token = _BRIEFING_CODEX_TOOL_POLICY.set(_briefing_codex_tool_policy_overrides(adapter))
    try:
        yield
    finally:
        if token is not None:
            _BRIEFING_CODEX_TOOL_POLICY.reset(token)


def _briefing_codex_tool_policy_args() -> list[str]:
    """Return per-invocation overrides for the active briefing context only."""
    return list(_BRIEFING_CODEX_TOOL_POLICY.get())


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _configured_executable(adapter: str) -> str:
    load_dotenv()
    env_name = f"FOLIO_AGENT_{adapter.upper()}_COMMAND"
    configured = str(os.environ.get(env_name, "") or "").strip().strip('"')
    if configured:
        return configured
    discovered = shutil.which(BINARY_NAMES.get(adapter, adapter)) or ""
    if adapter == "codex" and "\\windowsapps\\openai.codex_" in discovered.lower():
        # The desktop app bundles a private codex.exe that is not the standalone
        # CLI and can fail with Access denied when invoked by the bridge.
        return ""
    return discovered


def _probe_adapter(adapter: str) -> dict:
    executable = _configured_executable(adapter)
    labels = {
        "codex": "Codex CLI",
        "claude": "Claude Code CLI",
        "antigravity": "Antigravity CLI",
    }
    result = {
        "id": adapter,
        "label": labels.get(adapter, f"{adapter.capitalize()} CLI"),
        "available": False,
        "installed": False,
        "authenticated": False,
        "executable": executable,
        "version": "",
        "error": "",
        "bridgeSupported": True,
    }
    if not executable:
        result["error"] = "CLI를 찾을 수 없습니다."
        return result
    try:
        proc = subprocess.run(
            [executable, "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=_creation_flags(),
        )
        version = (proc.stdout or proc.stderr or "").strip().splitlines()
        result["version"] = version[0][:200] if version else ""
        if proc.returncode == 0:
            result["installed"] = True
        else:
            result["error"] = f"버전 확인 실패 (exit {proc.returncode})"
            return result

        if adapter == "antigravity":
            # **재본 결과로만 연다.** 예전에는 버전 숫자로 판정했는데, 버전 비교는
            # 권한 문제를 구조적으로 볼 수 없다 — 그래서 열어 둔 뒤 Agent 잡 두 건이
            # 모두 실패했다. 모르면(None) 막는다.
            #
            # 플랫폼으로 가르지 않는다. 거부를 실측한 것은 Windows지만 macOS/Linux를
            # 재본 것도 아니다 — 안 재본 것을 된다고 가정하는 것이 바로 지난 실수다.
            # 조회는 어느 플랫폼에서든 같은 방식으로 사실을 확인한다.
            from features.agent_mode import agy_capability

            # 플래그가 서 있으면 방금 거부당했다는 뜻이다 — `False`이지 `None`이 아니다.
            # `None`으로 읽으면 "아직 안 재봤다" 문구가 나가 무엇이 막혔는지 못 말한다.
            can_read = False if _AGY_FILE_READS_BLOCKED else agy_capability.cached_file_reads(result["version"])
            if can_read is not True:
                result["bridgeSupported"] = False
                result["available"] = False
                result["error"] = AGY_PERMISSION_HELP if can_read is False else AGY_UNVERIFIED_HELP
                return result

        if adapter == "antigravity":
            # agy는 비대화형 로그인 상태 확인 서브커맨드를 제공하지 않는다. 설치되어 있으면
            # 사용 가능으로 보고, 실제 인증 여부는 실행 시점의 오류로 사용자에게 노출한다.
            result["authenticated"] = True
            result["available"] = True
            return result

        auth_command = [executable, "login", "status"] if adapter == "codex" else [executable, "auth", "status"]

        auth = subprocess.run(
            auth_command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            creationflags=_creation_flags(),
        )
        if auth.returncode == 0:
            result["authenticated"] = True
            result["available"] = True
        else:
            result["error"] = "로그인이 필요합니다."
    except Exception:
        result["error"] = "CLI 상태를 확인하지 못했습니다."
    return result


def invalidate_bridge_status() -> None:
    global _STATUS_CACHE
    with _STATUS_LOCK:
        _STATUS_CACHE = None


# 예전에는 여기에 버전 게이트(`AGY_HEADLESS_FIXED = (1, 1, 7)`)가 있었다. 지웠다 —
# **버전 숫자로 능력을 판정하지 않는다.** agy 1.0.10의 headless 출력 버그가 1.1.7에서
# 고쳐진 것을 짧은 프롬프트 하나로 확인하고 브리지를 열었는데, 정작 Agent task는 전부
# 컨텍스트 팩 파일을 읽는 것으로 시작한다. 그 경로는 재보지 않았고, 1.1.12는 그 읽기를
# 거부한다. 버전 비교로는 볼 수 없는 종류의 문제였다. 지금은 `agy_capability`가 실제로
# 파일을 읽혀 보고 그 결과로만 연다. 게이트를 둘 두면 "재봤더니 되는데 버전 때문에
# 막는" 모순이 생기므로 하나만 남긴다.


def bridge_status(*, refresh: bool = False) -> dict:
    global _STATUS_CACHE
    load_dotenv()
    if refresh:
        # 사용자가 새로고침을 눌렀다면 설정을 고쳤을 수 있다. 한 번 막혔다고 영영
        # 막아두면 고치고도 되돌릴 방법이 화면에 없다.
        reset_agy_permission_state()
    with _STATUS_LOCK:
        if not refresh and _STATUS_CACHE and time.monotonic() - _STATUS_CACHE[0] < 15:
            return _STATUS_CACHE[1]
        adapters = [_probe_adapter(adapter) for adapter in STATUS_ADAPTERS]
        preferred = str(os.environ.get("AGENT_CLI_PROVIDER", "auto") or "auto").strip().lower()
        available = [item for item in adapters if item["available"]]
        selected = next((item for item in available if item["id"] == preferred), None)
        if preferred == "auto" and not selected and available:
            selected = available[0]
        installed = [item for item in adapters if item.get("installed")]
        payload = {
            "available": bool(selected),
            "selectedAdapter": selected["id"] if selected else "",
            "adapters": adapters,
            "message": (
                f"{selected['label']} 사용 가능"
                if selected
                else (
                    f"선택한 {preferred} CLI를 사용할 수 없습니다. 설치 및 로그인 상태를 확인하세요."
                    if preferred in ADAPTERS
                    else "CLI가 설치되어 있지만 로그인이 필요합니다."
                    if installed
                    else "실행 가능한 Codex/Claude CLI가 없습니다. CLI 설치 상태를 확인하세요."
                )
            ),
        }
        _STATUS_CACHE = (time.monotonic(), payload)
        return payload


def agent_preflight(adapter: str = "") -> dict:
    """Return structured readiness checks for the CLI bridge.

    `bridge_status()` is optimized for quick availability display.  Preflight is
    a release-facing diagnostic contract: every failure should map to something
    the UI can show without exposing shell logs or secrets.
    """
    requested = str(adapter or "").strip().lower()
    if requested and requested not in ADAPTERS:
        raise ValueError(f"Unsupported agent adapter: {requested}")
    status = bridge_status(refresh=True)
    checks: list[dict] = []

    def add(check_id: str, label: str, ok: bool, message: str, *, severity: str = "error", detail: str = "") -> None:
        checks.append({
            "id": check_id,
            "label": label,
            "ok": bool(ok),
            "severity": "info" if ok else severity,
            "message": message,
            "detail": str(detail or "")[:500],
        })

    workspace_data = data_dir()
    add(
        "workspace",
        "Workspace",
        ROOT.exists() and (ROOT / "app.py").exists(),
        "Folio OS workspace를 확인했습니다." if ROOT.exists() else "Folio OS workspace를 찾을 수 없습니다.",
        detail=str(ROOT),
    )
    add(
        "data_dir",
        "Data Directory",
        workspace_data.exists() or os.access(str(ROOT), os.W_OK),
        "data 폴더를 사용할 수 있습니다." if workspace_data.exists() else "첫 실행 시 data 폴더를 생성할 수 있습니다.",
        detail=str(workspace_data),
    )

    selected_id = requested or str(status.get("selectedAdapter") or "")
    selected = next((item for item in status.get("adapters") or [] if item.get("id") == selected_id), None)
    if not selected:
        add(
            "adapter_selected",
            "CLI Provider",
            False,
            status.get("message") or "사용 가능한 Agent CLI가 없습니다.",
        )
        return {
            "ok": False,
            "adapter": selected_id,
            "selectedAdapter": selected_id,
            "checks": checks,
            "status": status,
        }

    add(
        "adapter_installed",
        "CLI Installed",
        bool(selected.get("installed")),
        f"{selected.get('label') or selected_id} 설치를 확인했습니다."
        if selected.get("installed")
        else f"{selected.get('label') or selected_id} 설치가 필요합니다.",
        detail=selected.get("executable", ""),
    )
    add(
        "adapter_version",
        "CLI Version",
        bool(selected.get("version")),
        f"버전: {selected.get('version')}" if selected.get("version") else "CLI 버전을 확인하지 못했습니다.",
    )
    add(
        "adapter_auth",
        "CLI Auth",
        bool(selected.get("authenticated")),
        "CLI 로그인 상태를 확인했습니다." if selected.get("authenticated") else "CLI 로그인이 필요합니다.",
        detail=selected.get("error", ""),
    )
    add(
        "bridge_supported",
        "Bridge Support",
        bool(selected.get("bridgeSupported", True)),
        "이 CLI는 Folio OS Direct Bridge에서 지원됩니다."
        if selected.get("bridgeSupported", True)
        else selected.get("error") or "이 CLI는 현재 Direct Bridge에서 지원되지 않습니다.",
    )

    ok = all(item["ok"] for item in checks)
    return {
        "ok": ok,
        "adapter": selected_id,
        "selectedAdapter": selected_id,
        "checks": checks,
        "status": status,
    }


def _select_adapter(requested: str = "") -> dict:
    status = bridge_status(refresh=True)
    requested = str(requested or "").strip().lower()
    if requested and requested not in ADAPTERS:
        raise ValueError(f"Unsupported agent adapter: {requested}")
    if requested:
        selected = next((item for item in status["adapters"] if item["id"] == requested), None)
        if not selected or not selected["available"]:
            detail = (selected or {}).get("error") or "CLI를 사용할 수 없습니다."
            raise AgentAdapterUnavailableError(f"{requested} adapter unavailable: {detail}")
        return selected
    selected_id = status.get("selectedAdapter")
    selected = next((item for item in status["adapters"] if item["id"] == selected_id), None)
    if not selected:
        raise AgentAdapterUnavailableError(status.get("message") or "Agent CLI를 사용할 수 없습니다.")
    return selected


def _agent_prompt(pack_path: Path, pack: dict, *, inline_briefing: bool = False) -> str:
    contract = pack.get("outputContract") or {}
    output_format = contract.get("format", "markdown")
    lines = [
        "Act as the final Folio OS report author for this single task.",
        ("Use the prepared briefing input below; no file or shell lookup is needed."
         if inline_briefing else f"Read the UTF-8 Agent Context Pack at: {pack_path}"),
        "Follow agentInstructions, prompt, context, evidence boundaries, outputContract, and writeBackContract in the supplied input.",
        "Do not modify files, run the Folio OS writeback command, or expose credentials.",
        "Complete the requested payload now. Do not enter plan mode, write a plan, or ask for approval to start drafting.",
    ]
    if pack.get("taskType") == "briefing":
        lines.append(
            "This briefing must use the local Context Pack and must not open or control a browser, "
            "external browser, or computer UI."
        )
    if sum(1 for section in (contract.get("requiredSections") or []) if section == "Source & Data Notes") > 1:
        lines.append(
            "Each market block must end with its own '## Source & Data Notes' covering ONLY that market. "
            "Do not write a combined tail section (notes or references) that spans multiple markets."
        )
    required = contract.get("requiredSections") or []
    expected_titles = [
        str(value).strip() for value in (contract.get("expectedTitles") or {}).values()
        if str(value).strip()
    ]
    expected_leaders = contract.get("expectedLeadingCompanies") or {}
    title_instruction = (
        "Market title H1 lines must exactly match: " + " / ".join(f"'# {title}'" for title in expected_titles) + "."
        if expected_titles
        else "Each market title must be an H1 with a session date and status, like '# US Market Briefing — YYYY.MM.DD 마감' or '# Korea Market Briefing — YYYY.MM.DD 장중'."
    )
    if required:
        lines.extend([
            "Do not summarize, shorten, merge, or omit required report sections (필수 섹션을 축약하지 마세요).",
            f"Minimum report length: {int(contract.get('minimumCharacters') or 0)} characters.",
            f"Minimum '**한 줄 결론:**' count: {int(contract.get('minimumOneLineConclusions') or 0)}.",
            f"Minimum middle-dot summary line count: {int(contract.get('minimumMiddleDotBullets') or 0)}.",
            title_instruction,
            "After each market title, start immediately with the matching '## 0. 오늘의 ... 성격' section. Do not add market-scope notes, source-date explanations, blockquotes, or any preamble.",
            "Leading company headings must include the concrete company name after an em dash, e.g. '## 3. 미국장을 주도한 기업 ① — NVIDIA'. Never leave '[기업명]' or omit the company name.",
            *(
                ["Leading company names and order must exactly match: " + " / ".join(
                    f"{market.upper()}={', '.join(names)}" for market, names in expected_leaders.items()
                ) + "."]
                if expected_leaders else []
            ),
            "Required Markdown heading fragments, in contract order:",
            *(f"- {section}" for section in required),
        ])
    if inline_briefing:
        # The shared context builder already pins the writer evidence, market
        # facts, manifest IDs and control hints. Do not make a read-only author
        # parse megabytes of draft charts/internal staging data with a shell.
        for key in ("agentInstructions", "prompt", "context", "outputContract", "writeBackContract"):
            value = pack.get(key) or ({} if key.endswith("Contract") else "")
            lines.extend([f"\n--- {key} ---", value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)])
    lines.append(f"Return only the final {output_format} payload. Do not wrap it in commentary or Markdown fences.")
    return "\n".join(lines)


# 어댑터별 웹 검색 인자. 확인된 것만 넣는다 — 지원하지 않는 어댑터에 조용히 넘기면
# "설정은 켜져 있는데 아무 일도 안 하는" 상태가 다시 생긴다.
#
# codex: `tools.web_search`는 모델 쪽 도구라 `--sandbox read-only`와 함께 쓸 수 있다(실측).
# claude: `--allowedTools WebSearch`로 도구를 허용한다.
# antigravity: 확인된 방법이 없다.
WEB_SEARCH_ARGS: dict[str, list[str]] = {
    "codex": ["-c", "tools.web_search=true"],
    "claude": ["--allowedTools", "WebSearch"],
}


def adapter_supports_web_search(adapter_id: str) -> bool:
    return str(adapter_id or "").strip().lower() in WEB_SEARCH_ARGS


def _cli_reasoning_effort(adapter_id: str, value: str = "", *, model: str = "") -> str:
    """Normalize a task effort and fail closed before spawning a CLI.

    The persisted task policy is validated when it is saved, but callers such
    as a resumed job can carry an older snapshot.  Rechecking here prevents a
    stale or hand-built snapshot from silently losing its requested effort.
    ``provider_default`` is represented by an omitted adapter argument.
    """
    effort = str(value or "").strip().lower().replace("-", "_")
    if effort in {"", "default", "providerdefault", "provider_default"}:
        return ""
    adapter = str(adapter_id or "").strip().lower()
    supported = CLI_REASONING_EFFORTS.get(adapter, frozenset())
    if effort not in supported or not is_supported_reasoning_effort("cli", adapter, model, effort):
        raise ValueError(f"Unsupported reasoning effort for CLI adapter: {adapter_id}/{effort}")
    return effort


def adapter_supports_reasoning(adapter_id: str, value: str) -> bool:
    """Return whether a non-default effort has a known adapter transport."""
    try:
        _cli_reasoning_effort(adapter_id, value)
    except ValueError:
        return False
    return True


def _adapter_command(
    adapter: dict,
    prompt: str = "",
    model_override: str = "",
    *,
    web_search: bool = False,
    reasoning_effort: str = "",
) -> list[str]:
    from features.agent_mode.setup import configured_model

    executable = adapter["executable"]
    model = str(model_override or "").strip() or configured_model(adapter["id"])
    effort = _cli_reasoning_effort(adapter.get("id", ""), reasoning_effort, model=model)
    if adapter["id"] == "antigravity":
        # agy는 단일 프롬프트를 인자(--print <prompt>)로 받아 비대화형 실행한다. 단, Windows
        # headless는 출력을 stdout으로 내지 못하므로 _invoke_agent_cli에서 Windows를 사전 차단한다.
        command = [executable]
        if model:
            command.extend(["--model", model])
        if effort:
            command.extend(["--effort", effort])
        command.extend(["--print", prompt])
        return command
    if adapter["id"] == "codex":
        command = [
            executable,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
        ]
        if model:
            command.extend(["--model", model])
        if effort:
            # Codex's `-c` override is scoped to this process and therefore
            # does not mutate the user's global config.toml.
            command.extend(["-c", f"model_reasoning_effort={effort}"])
        command.extend(_briefing_codex_tool_policy_args())
        if _BRIEFING_CODEX_TOOL_POLICY.get():
            # Explicitly override inherited cached/live search during writing.
            # The separate lookup pass alone may enable native web search.
            command.extend(["-c", 'web_search="live"' if web_search else 'web_search="disabled"'])
        if web_search:
            command.extend(WEB_SEARCH_ARGS["codex"])
        command.append("-")
        return command
    if adapter["id"] == "claude":
        # Planning is not a filesystem sandbox: it makes the author stop for
        # approval instead of returning the report. Deny prompts and expose
        # only the read tools needed by this bridge; never inherit write tools.
        read_tools = ["Read", "Glob", "Grep"]
        if web_search:
            read_tools.append("WebSearch")
        command = [
            executable,
            "--print",
            "--output-format",
            "text",
            "--permission-mode",
            "dontAsk",
            "--tools", ",".join(read_tools),
            "--allowedTools", ",".join(read_tools),
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        ]
        if model:
            command.extend(["--model", model])
        if effort:
            command.extend(["--effort", effort])
        return command
    raise ValueError(f"Unsupported adapter: {adapter['id']}")


def _child_environment() -> dict:
    env = dict(os.environ)
    for key in [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "CODEX_API_KEY",
    ]:
        env.pop(key, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _strip_outer_fence(text: str) -> str:
    value = str(text or "").strip()
    match = re.fullmatch(r"```(?:markdown|md|json)?\s*\n?(.*?)\n?```", value, re.I | re.S)
    return match.group(1).strip() if match else value


def _json_payload(text: str) -> dict:
    value = _strip_outer_fence(text)
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Agent CLI did not return a JSON object")
        payload = json.loads(value[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Agent CLI JSON output must be an object")
    return payload


def _result_summary(task_type: str, pack: dict, result: dict, adapter: str) -> dict:
    draft = pack.get("draftArtifact") or {}
    summary = {
        "generationMode": "llm_cli",
        "adapter": adapter,
        "artifactType": pack.get("artifactType") or task_type,
        "artifactId": result.get("id") or pack.get("artifactId"),
        "title": result.get("title") or result.get("headline") or pack.get("title"),
    }
    if task_type == "briefing":
        summary["date"] = result.get("date") or draft.get("date") or pack.get("artifactId")
    elif task_type == "company_analysis":
        summary["reportId"] = result.get("id") or pack.get("artifactId")
        summary["filename"] = result.get("filename", "")
        summary["analysisStyle"] = draft.get("analysisStyle") or (pack.get("metadata") or {}).get("analysisStyle", "")
    elif task_type == "topic_report":
        summary["reportId"] = result.get("id") or pack.get("artifactId")
        summary["filename"] = result.get("filename", "")
    elif task_type == "personal_overlay":
        internal = pack.get("internal") or {}
        summary["reportKind"] = internal.get("reportKind", "")
        summary["reportId"] = (draft.get("canonical") or {}).get("id", "")
    elif task_type == "thesis_delta":
        summary["ticker"] = ((pack.get("internal") or {}).get("thesis") or {}).get("ticker", "")
    elif task_type == "market_memory_llm":
        summary["savedCount"] = len(result.get("saved") or [])
        summary["date"] = pack.get("artifactId")
    elif task_type == "market_state_snapshot":
        snapshot = result.get("snapshot") or {}
        summary["snapshotId"] = snapshot.get("id", "")
        summary["title"] = snapshot.get("headline") or summary.get("title")
        summary["date"] = pack.get("artifactId")
        summary["statusMessage"] = "AI Agent 시장 상태 스냅샷을 저장했습니다."
    elif task_type == "quality_repair":
        internal = pack.get("internal") or {}
        summary["targetArtifactType"] = internal.get("targetArtifactType", "")
        summary["targetArtifactId"] = internal.get("targetArtifactId", "")
    elif task_type == "investment_review":
        summary["date"] = result.get("date") or pack.get("artifactId")
    return summary


def _mark_agy_file_reads_blocked(version: str = "", detail: str = "") -> None:
    global _AGY_FILE_READS_BLOCKED
    _AGY_FILE_READS_BLOCKED = True
    if version:
        # 재시작해도 막혀 있어야 한다. 모듈 플래그만 두면 다음 실행이 또 한 번 실패한다.
        from features.agent_mode import agy_capability

        agy_capability.record(version, False, detail)
    invalidate_bridge_status()


def reset_agy_permission_state() -> None:
    """설정을 고친 뒤 다시 시도할 수 있게 한다(상태 새로고침이 부른다)."""
    global _AGY_FILE_READS_BLOCKED
    _AGY_FILE_READS_BLOCKED = False


def _prompt_needs_file_read(prompt: str) -> bool:
    """컨텍스트 팩을 읽으라는 프롬프트인가.

    대화처럼 파일을 안 읽는 호출은 권한 없이도 정상 동작한다(실측으로 짧은 프롬프트는
    20초에 응답했다). 그것까지 막으면 도크가 통째로 죽는다.
    """
    return "Agent Context Pack" in prompt


def _invoke_agent_cli(
    selected: dict,
    prompt: str,
    timeout: int,
    job_id: str = "",
    model_override: str = "",
    *,
    web_search: bool = False,
    reasoning_effort: str = "",
) -> str:
    is_antigravity = selected.get("id") == "antigravity"
    if is_antigravity and _AGY_FILE_READS_BLOCKED and _prompt_needs_file_read(prompt):
        # 이미 거부당한 것을 알고 있다. 팩을 만들고 수 분을 버린 뒤 같은 곳에서
        # 실패하게 두지 않는다.
        raise RuntimeError(AGY_PERMISSION_HELP)
    command = _adapter_command(
        selected,
        prompt,
        model_override=model_override,
        web_search=bool(web_search) and adapter_supports_web_search(selected.get("id", "")),
        reasoning_effort=reasoning_effort,
    )
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_child_environment(),
        creationflags=_creation_flags(),
    )
    if job_id:
        with _PROCESS_LOCK:
            _RUNNING_PROCESSES[job_id] = proc
    try:
        # antigravity는 프롬프트를 명령 인자(--print <prompt>)로 받으므로 stdin으로 중복 전달하지
        # 않는다(중복 입력 시 빈 출력). codex/claude는 stdin으로 받는다.
        stdin_data = None if is_antigravity else prompt
        stdout, stderr = proc.communicate(stdin_data, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise TimeoutError(f"Agent CLI 실행 시간이 {timeout}초를 초과했습니다.")
    finally:
        if job_id:
            with _PROCESS_LOCK:
                _RUNNING_PROCESSES.pop(job_id, None)
    if proc.returncode != 0:
        error = (stderr or stdout or f"exit {proc.returncode}").strip()[-2000:]
        hint = rate_limit_hint(error)
        if hint is not None:
            raise AgentRateLimitError(f"Agent CLI 사용량 한도에 걸렸습니다. {hint}".strip(), hint)
        raise AgentProcessError(f"Agent CLI 실행 실패 (exit {proc.returncode}): {error}")
    output = _strip_outer_fence(stdout)
    if not output:
        detail = (stderr or "").strip()[-500:]
        if is_antigravity and AGY_PERMISSION_DENIED_MARK in (stderr or ""):
            # agy는 이 경우 exit 0에 빈 stdout으로 끝난다. 일반 "빈 결과"로 보고하면
            # 사용자는 무엇을 고쳐야 할지 알 수 없다 — 실제로 예약 브리핑이 며칠 동안
            # `internal_error`로만 남았다.
            _mark_agy_file_reads_blocked(selected.get("version", ""), detail)
            raise RuntimeError(AGY_PERMISSION_HELP)
        hint = rate_limit_hint(detail)
        if hint is not None:
            # 한도는 exit 0 + 빈 stdout으로도 온다. 일반 "빈 결과"로 보고하면 사용자는
            # 무엇을 기다려야 하는지 알 수 없다.
            raise AgentRateLimitError(f"Agent CLI 사용량 한도에 걸렸습니다. {hint}".strip(), hint)
        raise AgentProcessError(
            "Agent CLI가 최종 결과를 반환하지 않았습니다." + (f" (stderr: {detail})" if detail else "")
        )
    if len(output) > MAX_OUTPUT_CHARS:
        raise RuntimeError("Agent CLI 결과가 허용 크기를 초과했습니다.")
    return output


def _briefing_correction_prompt(base_prompt: str, violations: list[str], contract: dict) -> str:
    required = "\n".join(f"- {section}" for section in contract.get("requiredSections") or [])
    problems = "\n".join(f"- {violation}" for violation in violations)
    expected_titles = [
        str(value).strip() for value in (contract.get("expectedTitles") or {}).values()
        if str(value).strip()
    ]
    title_reminder = (
        "- Market title H1 lines must exactly match: " + " / ".join(f"'# {title}'" for title in expected_titles) + "."
        if expected_titles
        else "- Market titles must include the session date and status: '# US Market Briefing — YYYY.MM.DD 마감' and/or '# Korea Market Briefing — YYYY.MM.DD 장중'."
    )
    return "\n".join([
        base_prompt,
        "",
        "The previous briefing output violated the Folio OS API-parity contract.",
        "Regenerate the complete report from the same context pack. Do not patch or 축약하지 마세요.",
        "Contract violations:",
        problems,
        "Hard format reminders:",
        title_reminder,
        "- The line after each market title must be the matching '## 0. 오늘의 ... 성격' heading; no preamble or blockquote.",
        "- Section 3 and 4 leading-company headings must include a concrete company name after '—'.",
        "Required heading fragments:",
        required,
        "Return a complete replacement Markdown report only.",
    ])


def _used_web_search(selected: dict, requested: bool) -> bool:
    """요청했고 그 어댑터가 실제로 지원할 때만 참. 화면이 이 값을 그대로 말한다."""
    return bool(requested) and adapter_supports_web_search(selected.get("id", ""))


def _task_cli_kwargs(task_policy: dict | None) -> dict[str, str]:
    """Turn a frozen task policy into bridge-only CLI kwargs.

    Empty/default fields are omitted so the existing global CLI behavior and
    lightweight test seams remain unchanged.  Explicit values are carried to
    the adapter process; they are never written to the user's CLI config.
    """
    if not isinstance(task_policy, dict):
        return {}
    kwargs: dict[str, str] = {}
    model = str(task_policy.get("model") or "").strip()
    if model:
        kwargs["model_override"] = model
    effort = _cli_reasoning_effort(
        str(task_policy.get("provider") or ""),
        str(task_policy.get("reasoningEffort") or ""),
        model=model,
    )
    if effort:
        kwargs["reasoning_effort"] = effort
    return kwargs


def _invoke_task_cli(
    selected: dict,
    prompt: str,
    timeout: int,
    job_id: str = "",
    *,
    task_policy: dict | None = None,
    web_search: bool = False,
) -> str:
    """Invoke a task's selected adapter with its immutable model/effort."""
    kwargs = _task_cli_kwargs(task_policy)
    if web_search:
        kwargs["web_search"] = True
    return _invoke_agent_cli(selected, prompt, timeout, job_id, **kwargs)


def run_agent_prompt(
    prompt: str, *, adapter: str = "", model: str = "", timeout: int = 0, job_id: str = "",
    serialize: bool = True, web_search: bool = False, reasoning_effort: str = "",
    diagnostic_primary: bool = True,
) -> dict:
    """단일 프롬프트를 Agent CLI로 실행하고 텍스트 결과만 돌려준다(파일 쓰기 없음).

    Agent 채팅처럼 context pack/writeback이 필요 없는 read-only 호출용이다.

    `serialize=False`는 **이미 `_RUN_SEMAPHORE`를 쥔 호출자 전용**이다. 그 세마포어는
    `threading.Semaphore(1)`이라 재진입이 안 되고 acquire에 타임아웃도 없다 — 잡 스레드
    안에서 다시 부르면 그 잡이 영원히 멈춘다. 브리핑 생성 잡의 커밋 단계에서 도는
    의미 비교가 정확히 그 자리다(`run_agent_task`가 커밋까지 통째로 감싼다).
    """
    effective_timeout = timeout or max(30, int(os.environ.get("AGENT_CHAT_TIMEOUT_SECONDS", 300)))
    bound_policy = current_task_policy()
    if isinstance(bound_policy, dict):
        # Nested calls made while a producer is running inherit its frozen
        # model/effort.  Explicit arguments remain available for Agent Dock
        # conversations and other read-only callers.
        if not str(model or "").strip():
            model = str(bound_policy.get("model") or "")
        if not str(reasoning_effort or "").strip():
            reasoning_effort = str(bound_policy.get("reasoningEffort") or "")
    budget = current_briefing_budget()
    if budget:
        effective_timeout = min(effective_timeout, budget.remaining_seconds() or effective_timeout)
    if not serialize:
        selected = _select_adapter(adapter)
        diagnostic_execution(attempted_engine="cli", adapter=str(selected["id"]), primary=diagnostic_primary)
        with _diagnostic_boundary("generate", "adapter"):
            kwargs = {"model_override": model, "web_search": web_search}
            if _cli_reasoning_effort(selected.get("id", ""), reasoning_effort, model=model):
                kwargs["reasoning_effort"] = _cli_reasoning_effort(selected.get("id", ""), reasoning_effort, model=model)
            output = _invoke_agent_cli(selected, prompt, effective_timeout, job_id, **kwargs)
        diagnostic_execution(final_engine="cli", adapter=str(selected["id"]), primary=diagnostic_primary)
        if budget:
            budget.check_active()
        return {"output": output, "adapter": selected["id"], "webSearch": _used_web_search(selected, web_search)}
    recorder, stage_id = diagnostic_stage_start("wait_engine")
    acquired = _RUN_SEMAPHORE.acquire(timeout=budget.remaining_seconds()) if budget else _RUN_SEMAPHORE.acquire()
    if not acquired:
        error = TimeoutError("deadline_expired")
        diagnostic_stage_failure(recorder, error, stage_id=stage_id, stage_code="wait_engine", boundary="adapter")
        diagnostic_stage_end(recorder, stage_id, "wait_engine")
        raise error
    try:
        diagnostic_stage_end(recorder, stage_id, "wait_engine")
        selected = _select_adapter(adapter)
        diagnostic_execution(attempted_engine="cli", adapter=str(selected["id"]), primary=diagnostic_primary)
        with _diagnostic_boundary("generate", "adapter"):
            kwargs = {"model_override": model, "web_search": web_search}
            if _cli_reasoning_effort(selected.get("id", ""), reasoning_effort, model=model):
                kwargs["reasoning_effort"] = _cli_reasoning_effort(selected.get("id", ""), reasoning_effort, model=model)
            output = _invoke_agent_cli(selected, prompt, effective_timeout, job_id, **kwargs)
        diagnostic_execution(final_engine="cli", adapter=str(selected["id"]), primary=diagnostic_primary)
    except Exception as error:
        # Acquisition is the only wait-engine boundary.  Once acquired, the
        # exact selector/process boundary records the failure instead.
        if stage_id is not None and not any(
            event.stage_id == stage_id and event.event_code == "end"
            for event in (recorder.record.events if recorder is not None else ())
        ):
            diagnostic_stage_failure(recorder, error, stage_id=stage_id, stage_code="wait_engine", boundary="adapter")
            diagnostic_stage_end(recorder, stage_id, "wait_engine")
        raise
    finally:
        _RUN_SEMAPHORE.release()
    if budget:
        budget.check_active()
    return {"output": output, "adapter": selected["id"], "webSearch": _used_web_search(selected, web_search)}


def _run_agent_task_locked(
    task_type: str,
    params: dict,
    *,
    selected: dict,
    durable: bool,
    progress,
    job_id: str,
    task_policy: dict | None = None,
) -> dict:
    """Run one task while the caller owns `_RUN_SEMAPHORE`."""
    # Start before pack preparation and keep it through writeback: pack
    # enrichment and commit-time semantic/concentration repairs may make nested
    # `run_agent_prompt(..., serialize=False)` calls.
    budget = SharedRepairBudget(
        deadline=time.monotonic() + max(30, int(os.environ.get("AGENT_CLI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))),
        cancelled=lambda: bool(job_id) and (get_job(job_id) or {}).get("status") in {"cancelled", "cancel_requested"},
    ) if task_type == "briefing" else None
    policy_context = bind_task_policy(task_policy) if isinstance(task_policy, dict) else nullcontext()
    with policy_context, _observed_tool_policy(task_type, selected), (bind_briefing_budget(budget) if budget else nullcontext()):
        progress("Agent context pack을 구성하고 있습니다.", 10, adapter=selected["id"])
        # The immutable policy travels with the job parameters but is a
        # bridge concern; feature pack builders should receive only their
        # declared task arguments.
        prepare_params = {
            key: value for key, value in params.items() if key != "_task_policy_snapshot"
        }
        if durable:
            prepare_params["owner_job_id"] = job_id
        if task_type == "briefing":
            from features.agent_mode.setup import configured_model
            semantic_model = (
                str(task_policy.get("model") or "")
                if isinstance(task_policy, dict) and task_policy.get("model")
                else configured_model(selected["id"])
            )
            prepare_params = {**prepare_params, "semantic_adapter": selected["id"], "semantic_model": semantic_model}
        with _diagnostic_boundary("context", "generic"):
            pack, pack_path = agent_service.prepare_pack(task_type, **prepare_params)
        progress("Agent CLI를 실행하고 있습니다.", 25, contextPackPath=str(pack_path), adapter=selected["id"])
        agent_prompt = _agent_prompt(
            pack_path, pack,
            inline_briefing=task_type == "briefing" and selected["id"] == "claude",
        )
        # 실제로 실행한 어댑터를 pack에 남긴다. 저장물의 generation.model이 자리표
        # (`current-agent-session`)뿐이면 나중에 품질 편차를 어느 엔진 탓인지 귀속할
        # 수 없다(브리핑 유보 밀도 이분포에서 실측).
        pack["executedAdapter"] = selected["id"]
        diagnostic_execution(attempted_engine="cli", adapter=str(selected["id"]))
        timeout = max(30, int(os.environ.get("AGENT_CLI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
        if budget:
            timeout = budget.remaining_seconds()
        try:
            # **본문 생성에는 어댑터 웹 도구를 켜지 않는다(`web_search=` 없음).** 누락이
            # 아니라 실측으로 도달한 설계다 — 쓰기 과제에 "필요하면 검색도 하라"를 얹는
            # 방식은 딥 리서치에서 네 번 모두 실패했다(새 URL 0~1건). 모델은 팩에 근거가
            # 있으면 충분하다고 판단한다. 웹은 별도 **찾기 과제**로 분리해야 작동하며,
            # 그 자리에서 `run_agent_prompt(..., web_search=True)`로 켠다
            # (`company_analysis/engine_calls.py`, `topic_report/web_lookup.py`).
            with _diagnostic_boundary("generate", "adapter"):
                output = _invoke_task_cli(
                    selected,
                    agent_prompt,
                    timeout,
                    job_id,
                    task_policy=task_policy,
                )
            diagnostic_execution(final_engine="cli", adapter=str(selected["id"]))
            output_format = (pack.get("outputContract") or {}).get("format", "markdown")
            briefing_contract_failed = False
            if task_type == "briefing" and output_format == "markdown":
                contract = pack.get("outputContract") or {}
                with _diagnostic_boundary("validate", "validation"):
                    violations = briefing_contract_violations(output, contract)
                retries = max(0, int(contract.get("retryOnViolation") or 0))
                if violations and retries:
                    budget.claim("structure")
                    previous_output = output
                    progress("CLI 브리핑 구조를 보완해 다시 작성하고 있습니다.", 60, adapter=selected["id"])
                    correction_prompt = _briefing_correction_prompt(agent_prompt, violations, contract)
                    with _diagnostic_boundary("generate", "adapter"):
                        output = _invoke_task_cli(
                            selected,
                            correction_prompt,
                            budget.remaining_seconds(),
                            job_id,
                            task_policy=task_policy,
                        )
                    from features.common.quality_generation.repair_grounding import preserves_briefing_input
                    if not preserves_briefing_input(previous_output, output, pack.get("sources") or []):
                        raise AgentOutputValidationError("briefing_repair_outside_input")
                    with _diagnostic_boundary("validate", "validation"):
                        violations = briefing_contract_violations(output, contract)
                if violations:
                    _dump_contract_violation(job_id, output, violations)
                    if not durable:
                        # 비-durable 경로는 규칙 대체를 태울 커밋 경로가 없다.
                        # 잘못된 브리핑을 writeback 하느니 여기서 끝낸다.
                        with _diagnostic_boundary("validate", "validation"):
                            raise AgentOutputValidationError(
                                "Agent CLI 브리핑이 출력 계약을 충족하지 못했습니다: "
                                + "; ".join(violations)
                            )
                    # durable 잡은 여기서 죽지 않는다.  토큰을 쓴 실행을 통째로
                    # 버리는 대신, 같은 팩의 고정 자료로 규칙 기반 보고서를 만들어
                    # 동일한 최종 검증·원자적 커밋 경로에 한 번만 태운다
                    # (§daily_briefing README "계약 또는 최종 사실 검증").
                    with _diagnostic_boundary("validate", "validation"):
                        diagnostic_execution(final_engine="rules", fallback_reason="engine_failed")
                    briefing_contract_failed = True
            elif task_type == "company_analysis" and output_format == "markdown":
                # 초안이 고정 9섹션을 어기면 **쓰기만** 한 번 더 시킨다. 브리핑이 이미
                # 같은 자리에서 같은 일을 한다 — 앞의 자료 수집·웹 조회는 재사용된다.
                # 브리핑과 달리 **실패로 끝내지 않는다.** 기업분석은 섹션 하나가 빠져도
                # 나머지가 쓸모 있고, 계약 결함으로 남으면 점수 상한이 그것을 말한다.
                try:
                    with _diagnostic_boundary("validate", "validation"):
                        missing = company_missing_sections(output)
                except (KeyboardInterrupt, SystemExit, CancelledError):
                    raise
                except Exception:
                    # Keep the exact output when optional structural
                    # observation itself fails. The shared finalizer receives
                    # this marker through the draft artifact and reports an
                    # unassessed warning without blocking writeback.
                    pack.setdefault("draftArtifact", {})["validationStatus"] = "unassessed"
                    missing = []
                if missing:
                    progress("CLI 기업분석 구조를 보완해 다시 작성하고 있습니다.", 60, adapter=selected["id"])
                    try:
                        with _diagnostic_boundary("generate", "adapter"):
                            retry = _invoke_task_cli(
                                selected,
                                agent_prompt + "\n\n" + company_section_retry(missing),
                                timeout,
                                job_id,
                                task_policy=task_policy,
                            )
                        # 재시도가 더 낫지 않으면 처음 것을 쓴다. 나쁜 초안이라도 없는 것보다 낫다.
                        if len(company_missing_sections(retry)) < len(missing):
                            output = retry
                    except (KeyboardInterrupt, SystemExit, CancelledError):
                        # Explicit cancellation/interruption is never a usable
                        # report and must not fall through to writeback.
                        raise
                    except Exception:
                        # Structural repair is optional. Preserve the exact
                        # first draft when the retry times out or fails.
                        pass
            if task_type == "company_analysis" and job_id and (get_job(job_id) or {}).get("status") in {"cancel_requested", "cancelled"}:
                schema.update_pack_status(
                    pack_path,
                    status="cancelled",
                    result={"cancelled": True},
                )
                return {"cancelled": True, "artifactType": task_type}
        except Exception:
            schema.update_pack_status(pack_path, status="failed", result={"error": "agent_task_failed"})
            raise
        progress("Agent 결과를 기존 저장소에 반영하고 있습니다.", 85, adapter=selected["id"])
        output_format = (pack.get("outputContract") or {}).get("format", "markdown")
        if output_format == "json":
            with _diagnostic_boundary("validate", "validation"):
                payload = _json_payload(output)
        else:
            payload = None
        if durable:
            schema.update_pack_status(pack_path, status="committing")
            parsed_task = TaskType(task_type)
            # Shared JSON/SQL lifecycles own the commit stage because they can
            # close it at the proof boundary immediately before terminal
            # authority persistence.  An outer stage here would otherwise end
            # after the terminal observer and leave a false open stage.
            if parsed_task == TaskType.THESIS_DELTA:
                summary = job_runtime.commit_thesis_output(job_id, pack, payload or {})
            elif parsed_task == TaskType.MARKET_MEMORY_LLM:
                summary = job_runtime.commit_market_memory_output(job_id, pack, payload or {})
            elif parsed_task == TaskType.MARKET_STATE_SNAPSHOT:
                summary = job_runtime.commit_market_state_output(job_id, pack, payload or {})
            else:
                summary = job_runtime.commit_json_output(
                    job_id,
                    parsed_task,
                    pack,
                    markdown=output if output_format != "json" else None,
                    payload=payload,
                    contract_failed=briefing_contract_failed,
                )
            summary = {
                "generationMode": "llm_cli",
                "adapter": selected["id"],
                "artifactType": task_type,
                **({"policy": task_policy_metadata(task_policy)} if isinstance(task_policy, dict) else {}),
                **summary,
            }
            progress("Agent 결과 저장을 완료했습니다.", 100, **summary)
            return summary
        with _diagnostic_boundary("commit", "save"):
            if output_format == "json":
                result = agent_service.writeback_pack(pack, payload=payload)
            else:
                result = agent_service.writeback_pack(pack, markdown=output)
        summary = _result_summary(task_type, pack, result, selected["id"])
        schema.update_pack_status(pack_path, status="done", result=summary)
        progress("Agent 결과 저장을 완료했습니다.", 100, **summary)
        return summary


def _dump_contract_violation(job_id: str, output: str, violations: list[str]) -> None:
    """Write one contract-violating CLI output to a local file when asked.

    계약 위반은 위반 목록만 남기고 산출물을 버린다.  CLI가 왜 그런 것을 냈는지
    (짧은 거절문인지, 잘린 응답인지) 알 방법이 없어 원인을 좁힐 수 없었다.
    `BRIEFING_REJECTION_DUMP_DIR`을 설정한 실행에서만 쓴다.
    """
    import os

    target = str(os.environ.get("BRIEFING_REJECTION_DUMP_DIR") or "").strip()
    if not target:
        return
    try:
        import json
        from datetime import datetime
        from pathlib import Path

        directory = Path(target)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        payload = {"jobId": job_id, "violations": list(violations), "output": output}
        (directory / f"contract-{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        return


def run_agent_task(
    task_type: str,
    params: dict | None = None,
    *,
    adapter: str = "",
    progress=None,
    job_id: str = "",
) -> dict:
    params = params if isinstance(params, dict) else {}
    progress = progress or (lambda *args, **kwargs: None)
    task_policy = params.get("_task_policy_snapshot")
    if isinstance(task_policy, dict):
        task_policy = task_snapshot(task_type, task_policy)
        blocked = _bridge_task_gate(task_policy)
        if blocked is not None:
            progress(blocked["message"], 100, **blocked)
            return blocked
        if task_generation_mode(task_policy) != "llm_cli":
            result = {
                "generationMode": task_generation_mode(task_policy),
                "artifactType": task_type,
                "policy": task_policy_metadata(task_policy),
                "message": "이 작업은 현재 설정된 API 경로로 실행해야 합니다.",
            }
            progress(result["message"], 100, **result)
            return result
        # A queued task's provider is part of the immutable snapshot.  The
        # caller's legacy one-off adapter is ignored once the snapshot exists.
        adapter = str(task_policy.get("provider") or adapter)
    recorder, stage_id = diagnostic_stage_start("wait_engine")
    try:
        _RUN_SEMAPHORE.acquire()
    except Exception as error:
        diagnostic_stage_failure(
            recorder,
            error,
            stage_id=stage_id,
            stage_code="wait_engine" if stage_id is not None else None,
            boundary="adapter",
        )
        diagnostic_stage_end(recorder, stage_id, "wait_engine")
        raise
    diagnostic_stage_end(recorder, stage_id, "wait_engine")
    try:
        durable = job_runtime.is_durable_job(job_id)
        if job_id and (get_job(job_id) or {}).get("status") == "cancelled":
            return {"cancelled": True, "artifactType": task_type}
        with _diagnostic_boundary("preflight", "adapter"):
            selected = _select_adapter(adapter)
        return _run_agent_task_locked(
            task_type,
            params,
            selected=selected,
            durable=durable,
            progress=progress,
            job_id=job_id,
            task_policy=task_policy,
        )
    finally:
        _RUN_SEMAPHORE.release()


def _phase_progress(progress, label: str, start: int, end: int):
    span = max(0, end - start)

    def _progress(message, progress_value=None, **extra):
        scaled = None
        if progress_value is not None:
            try:
                scaled = start + int(round((float(progress_value) / 100.0) * span))
            except (TypeError, ValueError):
                scaled = start
        progress(f"{label} {message}", scaled, **extra)

    return _progress


def run_market_memory_update_task(
    params: dict | None = None,
    *,
    adapter: str = "",
    progress=None,
    job_id: str = "",
) -> dict:
    params = params if isinstance(params, dict) else {}
    date = str(params.get("date") or "").strip()
    task_params = {"date": date} if date else {}
    task_policy = params.get("_task_policy_snapshot")
    if isinstance(task_policy, dict):
        task_policy = task_snapshot("market_memory_update", task_policy)
        blocked = _bridge_task_gate(task_policy)
        if blocked is not None:
            progress(blocked["message"], 100, **blocked)
            return blocked
        if task_generation_mode(task_policy) != "llm_cli":
            result = {
                "generationMode": task_generation_mode(task_policy),
                "artifactType": "market_memory_update",
                "policy": task_policy_metadata(task_policy),
                "message": "이 작업은 현재 설정된 API 경로로 실행해야 합니다.",
            }
            progress(result["message"], 100, **result)
            return result
        task_params["_task_policy_snapshot"] = task_policy
        adapter = str(task_policy.get("provider") or adapter)
    progress = progress or (lambda *args, **kwargs: None)
    if job_runtime.is_durable_job(job_id):
        wait_recorder, wait_stage = diagnostic_stage_start("wait_engine")
        try:
            _RUN_SEMAPHORE.acquire()
        except Exception as error:
            diagnostic_stage_failure(
                wait_recorder, error, stage_id=wait_stage,
                stage_code="wait_engine" if wait_stage is not None else None,
                boundary="adapter",
            )
            diagnostic_stage_end(wait_recorder, wait_stage, "wait_engine")
            raise
        diagnostic_stage_end(wait_recorder, wait_stage, "wait_engine")
        try:
            with _diagnostic_boundary("preflight", "adapter"):
                selected = _select_adapter(adapter)
            diagnostic_execution(attempted_engine="cli", adapter=str(selected["id"]))
            timeout = max(30, int(os.environ.get("AGENT_CLI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
            pack_params = {
                key: value for key, value in task_params.items() if key != "_task_policy_snapshot"
            }
            with _diagnostic_boundary("context", "generic"):
                memory_pack, memory_path = agent_service.prepare_pack(
                    "market_memory_llm",
                    **pack_params,
                    owner_job_id=job_id,
                )
            progress("1/2 중기 메모리: Agent CLI를 실행하고 있습니다.", 20, adapter=selected["id"])
            try:
                with _diagnostic_boundary("generate", "adapter"):
                    memory_output = _invoke_task_cli(
                        selected,
                        _agent_prompt(memory_path, memory_pack),
                        timeout,
                        job_id,
                        task_policy=task_policy,
                    )
                with _diagnostic_boundary("validate", "validation"):
                    memory_payload = _json_payload(memory_output)
                    memory_prepared = agent_service.prepare_market_memory_writeback(memory_pack, memory_payload)
                schema.update_pack_status(memory_path, status="prepared")
                if (get_job(job_id) or {}).get("status") == "cancel_requested":
                    return {"cancelled": True, "artifactType": "market_memory_update"}
                with _diagnostic_boundary("context", "generic"):
                    snapshot_pack, snapshot_path = agent_service.prepare_pack(
                        "market_state_snapshot",
                        **pack_params,
                        owner_job_id=job_id,
                    )
                progress("2/2 시장 상태: Agent CLI를 실행하고 있습니다.", 65, adapter=selected["id"])
                with _diagnostic_boundary("generate", "adapter"):
                    snapshot_output = _invoke_task_cli(
                        selected,
                        _agent_prompt(snapshot_path, snapshot_pack),
                        timeout,
                        job_id,
                        task_policy=task_policy,
                    )
                with _diagnostic_boundary("validate", "validation"):
                    snapshot_payload = agent_service.prepare_market_state_snapshot_writeback(
                        snapshot_pack,
                        _json_payload(snapshot_output),
                    )
                schema.update_pack_status(memory_path, status="committing")
                schema.update_pack_status(snapshot_path, status="committing")
                from features.market_memory.service import finalize_role_classification

                # This fact belongs to the CLI work already completed above.
                # It must be recorded before the combined authority proof
                # terminalizes diagnostics, but it must not reorder role SQL.
                diagnostic_execution(final_engine="cli", adapter=str(selected["id"]))
                committed = job_runtime.commit_combined_market_output(
                    job_id,
                    tuple(memory_prepared["entries"]),
                    lambda _projected: snapshot_payload,
                )
                # Keep the established post-commit order and exception
                # semantics: a failed combined transaction must not create
                # independent role writes.
                role_classification = finalize_role_classification(
                    memory_prepared.get("roleSelection") or {},
                    memory_payload,
                    db_path=agent_service.MARKET_MEMORY_DB_PATH,
                )
            except Exception:
                for path in (locals().get("memory_path"), locals().get("snapshot_path")):
                    if isinstance(path, Path) and path.exists():
                        schema.update_pack_status(path, status="failed", result={"error": "agent_task_failed"})
                raise
        finally:
            _RUN_SEMAPHORE.release()
        result = {
            "generationMode": "llm_cli",
            "adapter": selected["id"],
            "artifactType": "market_memory_update",
            **({"policy": task_policy_metadata(task_policy)} if isinstance(task_policy, dict) else {}),
            "artifactId": date or str(snapshot_pack.get("artifactId") or ""),
            "title": str(snapshot_payload.get("headline") or "Market Memory Update"),
            "date": date or str(snapshot_pack.get("artifactId") or ""),
            **committed,
            "roleClassification": role_classification,
            "message": "시장 메모리와 화면용 시장 상태 스냅샷을 모두 업데이트했습니다.",
        }
        progress("시장 메모리 업데이트를 완료했습니다.", 100, **result)
        return result
    memory = run_agent_task(
        "market_memory_llm",
        task_params,
        adapter=adapter,
        progress=_phase_progress(progress, "1/2 중기 메모리:", 0, 50),
        job_id=job_id,
    )
    snapshot = run_agent_task(
        "market_state_snapshot",
        task_params,
        adapter=adapter,
        progress=_phase_progress(progress, "2/2 시장 상태:", 50, 100),
        job_id=job_id,
    )
    return {
        "generationMode": "llm_cli",
        "adapter": snapshot.get("adapter") or memory.get("adapter") or adapter or "auto",
        **({"policy": task_policy_metadata(task_policy)} if isinstance(task_policy, dict) else {}),
        "artifactType": "market_memory_update",
        "artifactId": date or snapshot.get("date") or memory.get("date") or "",
        "title": snapshot.get("title") or "Market Memory Update",
        "date": date or snapshot.get("date") or memory.get("date") or "",
        "savedCount": memory.get("savedCount", 0),
        "snapshotId": snapshot.get("snapshotId", ""),
        "memory": memory,
        "snapshot": snapshot,
        "message": "시장 메모리와 화면용 시장 상태 스냅샷을 모두 업데이트했습니다.",
    }


def submit_agent_task(task_type: str, params: dict | None = None, *, adapter: str = "") -> dict:
    params, effective_adapter, task_policy = _prepare_bridge_params(task_type, params, adapter)
    label = {
        "briefing": "LLM CLI 브리핑 생성",
        "company_analysis": "LLM CLI 기업 분석",
        "topic_report": "LLM CLI 테마 분석",
        "personal_overlay": "LLM CLI Personal Overlay",
        "thesis_delta": "LLM CLI Thesis Delta",
        "market_memory_llm": "LLM CLI 시장 내러티브 정리",
        "market_state_snapshot": "LLM CLI 시장 상태 정리",
        "quality_repair": "LLM CLI 품질 개선",
        "investment_review": "LLM CLI 투자 리뷰",
    }.get(task_type, f"LLM CLI {task_type}")
    job = submit_job(
        "agent_bridge",
        label,
        run_agent_task,
        task_type,
        params,
        adapter=effective_adapter,
        pass_job_id=True,
        dedicated_thread=True,
    )
    job["generationMode"] = task_generation_mode(task_policy) if task_policy else "llm_cli"
    job["adapter"] = effective_adapter or "auto"
    if task_policy:
        job["taskPolicy"] = task_policy_metadata(task_policy)
    return job


def submit_market_memory_update(params: dict | None = None, *, adapter: str = "") -> dict:
    params, effective_adapter, task_policy = _prepare_bridge_params("market_memory_update", params, adapter)
    job = submit_job(
        "agent_bridge",
        "LLM CLI 시장 메모리 업데이트",
        run_market_memory_update_task,
        params,
        adapter=effective_adapter,
        pass_job_id=True,
        dedicated_thread=True,
    )
    job["generationMode"] = task_generation_mode(task_policy) if task_policy else "llm_cli"
    job["adapter"] = effective_adapter or "auto"
    if task_policy:
        job["taskPolicy"] = task_policy_metadata(task_policy)
    return job


def cancel_agent_task(job_id: str) -> dict:
    result = cancel_job(job_id)
    if not result.get("cancelled"):
        return result
    with _PROCESS_LOCK:
        proc = _RUNNING_PROCESSES.get(str(job_id))
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            # The child can exit after poll() and before terminate(). The
            # durable cancellation request has already been accepted.
            pass
    return result
