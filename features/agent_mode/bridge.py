from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from features.agent_mode import schema
from features.agent_mode import service as agent_service
from features.agent_mode import job_runtime
from features.agent_mode.briefing_contract import briefing_contract_violations
from features.company_analysis.report_contract import (
    missing_sections as company_missing_sections,
    render_section_retry as company_section_retry,
)
from features.common.jobs import cancel_job, get_job, submit_job
from features.common.shared_jobs_schema import TaskType
from features.llm_settings.client import load_dotenv
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_SECONDS = 1800
MAX_OUTPUT_CHARS = 4_000_000
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
            raise RuntimeError(f"{requested} adapter unavailable: {detail}")
        return selected
    selected_id = status.get("selectedAdapter")
    selected = next((item for item in status["adapters"] if item["id"] == selected_id), None)
    if not selected:
        raise RuntimeError(status.get("message") or "Agent CLI를 사용할 수 없습니다.")
    return selected


def _agent_prompt(pack_path: Path, pack: dict) -> str:
    contract = pack.get("outputContract") or {}
    output_format = contract.get("format", "markdown")
    lines = [
        "Act as the final Folio OS report author for this single task.",
        f"Read the UTF-8 Agent Context Pack at: {pack_path}",
        "Follow agentInstructions, prompt, context, evidence boundaries, outputContract, and writeBackContract in that pack.",
        "Do not modify files, run the Folio OS writeback command, or expose credentials.",
    ]
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


def _adapter_command(
    adapter: dict, prompt: str = "", model_override: str = "", *, web_search: bool = False
) -> list[str]:
    from features.agent_mode.setup import configured_model

    executable = adapter["executable"]
    model = str(model_override or "").strip() or configured_model(adapter["id"])
    if adapter["id"] == "antigravity":
        # agy는 단일 프롬프트를 인자(--print <prompt>)로 받아 비대화형 실행한다. 단, Windows
        # headless는 출력을 stdout으로 내지 못하므로 _invoke_agent_cli에서 Windows를 사전 차단한다.
        command = [executable]
        if model:
            command.extend(["--model", model])
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
        if web_search:
            command.extend(WEB_SEARCH_ARGS["codex"])
        command.append("-")
        return command
    if adapter["id"] == "claude":
        command = [
            executable,
            "--print",
            "--output-format",
            "text",
            "--permission-mode",
            "plan",
        ]
        if model:
            command.extend(["--model", model])
        if web_search:
            command.extend(WEB_SEARCH_ARGS["claude"])
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
        raise RuntimeError(f"Agent CLI 실행 실패 (exit {proc.returncode}): {error}")
    output = _strip_outer_fence(stdout)
    if not output:
        detail = (stderr or "").strip()[-500:]
        if is_antigravity and AGY_PERMISSION_DENIED_MARK in (stderr or ""):
            # agy는 이 경우 exit 0에 빈 stdout으로 끝난다. 일반 "빈 결과"로 보고하면
            # 사용자는 무엇을 고쳐야 할지 알 수 없다 — 실제로 예약 브리핑이 며칠 동안
            # `internal_error`로만 남았다.
            _mark_agy_file_reads_blocked(selected.get("version", ""), detail)
            raise RuntimeError(AGY_PERMISSION_HELP)
        raise RuntimeError(
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


def run_agent_prompt(
    prompt: str, *, adapter: str = "", model: str = "", timeout: int = 0, job_id: str = "",
    serialize: bool = True, web_search: bool = False,
) -> dict:
    """단일 프롬프트를 Agent CLI로 실행하고 텍스트 결과만 돌려준다(파일 쓰기 없음).

    Agent 채팅처럼 context pack/writeback이 필요 없는 read-only 호출용이다.

    `serialize=False`는 **이미 `_RUN_SEMAPHORE`를 쥔 호출자 전용**이다. 그 세마포어는
    `threading.Semaphore(1)`이라 재진입이 안 되고 acquire에 타임아웃도 없다 — 잡 스레드
    안에서 다시 부르면 그 잡이 영원히 멈춘다. 브리핑 생성 잡의 커밋 단계에서 도는
    의미 비교가 정확히 그 자리다(`run_agent_task`가 커밋까지 통째로 감싼다).
    """
    effective_timeout = timeout or max(30, int(os.environ.get("AGENT_CHAT_TIMEOUT_SECONDS", 300)))
    if not serialize:
        selected = _select_adapter(adapter)
        output = _invoke_agent_cli(
            selected, prompt, effective_timeout, job_id, model_override=model, web_search=web_search
        )
        return {"output": output, "adapter": selected["id"], "webSearch": _used_web_search(selected, web_search)}
    with _RUN_SEMAPHORE:
        selected = _select_adapter(adapter)
        output = _invoke_agent_cli(
            selected, prompt, effective_timeout, job_id, model_override=model, web_search=web_search
        )
    return {"output": output, "adapter": selected["id"], "webSearch": _used_web_search(selected, web_search)}


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
    with _RUN_SEMAPHORE:
        durable = job_runtime.is_durable_job(job_id)
        if job_id and (get_job(job_id) or {}).get("status") == "cancelled":
            return {"cancelled": True, "artifactType": task_type}
        selected = _select_adapter(adapter)
        progress("Agent context pack을 구성하고 있습니다.", 10, adapter=selected["id"])
        prepare_params = {**params, "owner_job_id": job_id} if durable else params
        pack, pack_path = agent_service.prepare_pack(task_type, **prepare_params)
        progress("Agent CLI를 실행하고 있습니다.", 25, contextPackPath=str(pack_path), adapter=selected["id"])
        agent_prompt = _agent_prompt(pack_path, pack)
        timeout = max(30, int(os.environ.get("AGENT_CLI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
        try:
            # **본문 생성에는 어댑터 웹 도구를 켜지 않는다(`web_search=` 없음).** 누락이
            # 아니라 실측으로 도달한 설계다 — 쓰기 과제에 "필요하면 검색도 하라"를 얹는
            # 방식은 딥 리서치에서 네 번 모두 실패했다(새 URL 0~1건). 모델은 팩에 근거가
            # 있으면 충분하다고 판단한다. 웹은 별도 **찾기 과제**로 분리해야 작동하며,
            # 그 자리에서 `run_agent_prompt(..., web_search=True)`로 켠다
            # (`company_analysis/engine_calls.py`, `topic_report/web_lookup.py`).
            output = _invoke_agent_cli(selected, agent_prompt, timeout, job_id)
            output_format = (pack.get("outputContract") or {}).get("format", "markdown")
            if task_type == "briefing" and output_format == "markdown":
                contract = pack.get("outputContract") or {}
                violations = briefing_contract_violations(output, contract)
                retries = max(0, int(contract.get("retryOnViolation") or 0))
                if violations and retries:
                    progress("CLI 브리핑 구조를 보완해 다시 작성하고 있습니다.", 60, adapter=selected["id"])
                    correction_prompt = _briefing_correction_prompt(agent_prompt, violations, contract)
                    output = _invoke_agent_cli(selected, correction_prompt, timeout, job_id)
                    violations = briefing_contract_violations(output, contract)
                if violations:
                    raise RuntimeError(
                        "Agent CLI 브리핑이 출력 계약을 충족하지 못했습니다: "
                        + "; ".join(violations)
                    )
            elif task_type == "company_analysis" and output_format == "markdown":
                # 초안이 고정 9섹션을 어기면 **쓰기만** 한 번 더 시킨다. 브리핑이 이미
                # 같은 자리에서 같은 일을 한다 — 앞의 자료 수집·웹 조회는 재사용된다.
                # 브리핑과 달리 **실패로 끝내지 않는다.** 기업분석은 섹션 하나가 빠져도
                # 나머지가 쓸모 있고, 계약 결함으로 남으면 점수 상한이 그것을 말한다.
                missing = company_missing_sections(output)
                if missing:
                    progress("CLI 기업분석 구조를 보완해 다시 작성하고 있습니다.", 60, adapter=selected["id"])
                    retry = _invoke_agent_cli(
                        selected,
                        agent_prompt + "\n\n" + company_section_retry(missing),
                        timeout,
                        job_id,
                    )
                    # 재시도가 더 낫지 않으면 처음 것을 쓴다. 나쁜 초안이라도 없는 것보다 낫다.
                    if len(company_missing_sections(retry)) < len(missing):
                        output = retry
        except Exception:
            schema.update_pack_status(pack_path, status="failed", result={"error": "agent_task_failed"})
            raise
        progress("Agent 결과를 기존 저장소에 반영하고 있습니다.", 85, adapter=selected["id"])
        output_format = (pack.get("outputContract") or {}).get("format", "markdown")
        payload = _json_payload(output) if output_format == "json" else None
        if durable:
            schema.update_pack_status(pack_path, status="committing")
            parsed_task = TaskType(task_type)
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
                )
            summary = {
                "generationMode": "llm_cli",
                "adapter": selected["id"],
                "artifactType": task_type,
                **summary,
            }
            progress("Agent 결과 저장을 완료했습니다.", 100, **summary)
            return summary
        if output_format == "json":
            result = agent_service.writeback_pack(pack, payload=payload)
        else:
            result = agent_service.writeback_pack(pack, markdown=output)
        summary = _result_summary(task_type, pack, result, selected["id"])
        schema.update_pack_status(pack_path, status="done", result=summary)
        progress("Agent 결과 저장을 완료했습니다.", 100, **summary)
        return summary


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
    progress = progress or (lambda *args, **kwargs: None)
    if job_runtime.is_durable_job(job_id):
        with _RUN_SEMAPHORE:
            selected = _select_adapter(adapter)
            timeout = max(30, int(os.environ.get("AGENT_CLI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
            memory_pack, memory_path = agent_service.prepare_pack(
                "market_memory_llm",
                **task_params,
                owner_job_id=job_id,
            )
            progress("1/2 중기 메모리: Agent CLI를 실행하고 있습니다.", 20, adapter=selected["id"])
            try:
                memory_output = _invoke_agent_cli(
                    selected,
                    _agent_prompt(memory_path, memory_pack),
                    timeout,
                    job_id,
                )
                memory_payload = _json_payload(memory_output)
                memory_prepared = agent_service.prepare_market_memory_writeback(memory_pack, memory_payload)
                schema.update_pack_status(memory_path, status="prepared")
                if (get_job(job_id) or {}).get("status") == "cancel_requested":
                    return {"cancelled": True, "artifactType": "market_memory_update"}
                snapshot_pack, snapshot_path = agent_service.prepare_pack(
                    "market_state_snapshot",
                    **task_params,
                    owner_job_id=job_id,
                )
                progress("2/2 시장 상태: Agent CLI를 실행하고 있습니다.", 65, adapter=selected["id"])
                snapshot_output = _invoke_agent_cli(
                    selected,
                    _agent_prompt(snapshot_path, snapshot_pack),
                    timeout,
                    job_id,
                )
                snapshot_payload = agent_service.prepare_market_state_snapshot_writeback(
                    snapshot_pack,
                    _json_payload(snapshot_output),
                )
                schema.update_pack_status(memory_path, status="committing")
                schema.update_pack_status(snapshot_path, status="committing")
                committed = job_runtime.commit_combined_market_output(
                    job_id,
                    tuple(memory_prepared["entries"]),
                    lambda _projected: snapshot_payload,
                )
            except Exception:
                for path in (locals().get("memory_path"), locals().get("snapshot_path")):
                    if isinstance(path, Path) and path.exists():
                        schema.update_pack_status(path, status="failed", result={"error": "agent_task_failed"})
                raise
        result = {
            "generationMode": "llm_cli",
            "adapter": selected["id"],
            "artifactType": "market_memory_update",
            "artifactId": date or str(snapshot_pack.get("artifactId") or ""),
            "title": str(snapshot_payload.get("headline") or "Market Memory Update"),
            "date": date or str(snapshot_pack.get("artifactId") or ""),
            **committed,
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
        params or {},
        adapter=adapter,
        pass_job_id=True,
        dedicated_thread=True,
    )
    job["generationMode"] = "llm_cli"
    job["adapter"] = adapter or "auto"
    return job


def submit_market_memory_update(params: dict | None = None, *, adapter: str = "") -> dict:
    job = submit_job(
        "agent_bridge",
        "LLM CLI 시장 메모리 업데이트",
        run_market_memory_update_task,
        params or {},
        adapter=adapter,
        pass_job_id=True,
        dedicated_thread=True,
    )
    job["generationMode"] = "llm_cli"
    job["adapter"] = adapter or "auto"
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
