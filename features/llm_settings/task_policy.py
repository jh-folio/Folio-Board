"""Per-task AI Agent settings.

The global Agent setting remains the execution gate.  This module only stores
small, non-secret task overrides and resolves an immutable, safe-to-log
configuration for a producer at its boundary.  Credentials are deliberately
read by the selected adapter at execution time; they never enter this file.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from features.common.atomic_replace import write_bytes_atomic
from features.common.canonical_report_io import artifact_lock
from features.common.workspace import data_dir
from features.llm_settings.reasoning import (
    REASONING_VALUES,
    is_supported_reasoning_effort,
    normalize_reasoning_effort,
    reasoning_choices,
    supported_reasoning_efforts,
)


SCHEMA_VERSION = 1
POLICY_FILE_NAME = "ai-agent-task-settings.json"
SUPPORTED_REASONING = REASONING_VALUES
CLI_PROVIDERS = ("codex", "claude", "antigravity")

# CLI effort is an adapter concern.  Keep this table close to the persisted
# policy validator so Settings rejects a value before a job can be queued,
# while the bridge owns the command-line spelling.  ``provider_default`` is
# accepted for every adapter and intentionally means that no override is sent.
#
# Codex exposes ``model_reasoning_effort`` through ``-c`` and currently
# advertises minimal/low/medium/high/xhigh (the task UI does not expose
# minimal). Claude Code exposes ``--effort``; Antigravity exposes the same
# flag but currently documents low/medium/high only.
CLI_REASONING_EFFORTS = {
    "codex": frozenset({"low", "medium", "high", "xhigh", "max", "ultra"}),
    "claude": frozenset({"low", "medium", "high", "xhigh", "max"}),
    "antigravity": frozenset({"low", "medium", "high"}),
}

# These are the only producer surfaces exposed in Settings.  Runtime aliases
# below are intentionally many-to-one: a market-memory update consists of two
# internal jobs, while it is one user-facing setting.
TASK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "daily_briefing": {"label": "브리핑", "runtimeTypes": ("briefing",)},
    "company_analysis": {"label": "기업분석", "runtimeTypes": ("company_analysis",)},
    "topic_report": {"label": "Deep Research", "runtimeTypes": ("topic_report",)},
    "market_memory": {
        "label": "시장 내러티브",
        "runtimeTypes": ("market_memory", "market_memory_llm", "market_state_snapshot", "market_memory_update"),
    },
    "thesis_review": {"label": "Thesis 검토", "runtimeTypes": ("thesis_review", "thesis_delta")},
    "investment_review": {"label": "투자 리뷰", "runtimeTypes": ("investment_review",)},
    "personal_overlay": {"label": "Personal Overlay", "runtimeTypes": ("personal_overlay",)},
}
TASK_KEYS = tuple(TASK_DEFINITIONS)
RUNTIME_TASK_ALIASES = {
    runtime: task
    for task, definition in TASK_DEFINITIONS.items()
    for runtime in definition["runtimeTypes"]
}

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class TaskPolicyError(ValueError):
    """Safe, user-facing task-policy failure with a stable error code."""

    def __init__(self, code: str, message: str, *, status: int = 400, latest: dict | None = None):
        self.code = str(code)
        self.status = int(status)
        self.latest = deepcopy(latest) if isinstance(latest, dict) else None
        super().__init__(message)


class TaskPolicyConflict(TaskPolicyError):
    def __init__(self, latest: dict):
        super().__init__(
            "task_policy_revision_conflict",
            "작업별 AI Agent 설정이 다른 화면에서 먼저 저장되었습니다. 최신 설정을 다시 불러오세요.",
            status=409,
            latest=latest,
        )


def task_policy_path(root: Path | None = None) -> Path:
    """Return the current workspace path without creating a file."""
    return (Path(root) if root is not None else data_dir()) / POLICY_FILE_NAME


def _empty_tasks() -> dict[str, dict[str, Any]]:
    return {key: {"enabled": False, "config": None} for key in TASK_KEYS}


def _empty_policy() -> dict[str, Any]:
    return {"schemaVersion": SCHEMA_VERSION, "revision": 0, "tasks": _empty_tasks()}


def _safe_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TaskPolicyError("task_policy_invalid", f"{field}는 0 이상의 정수여야 합니다.")
    return value


def _normalize_model(value: Any, *, field: str = "model") -> str:
    model = str(value or "").strip()
    if not _MODEL_RE.fullmatch(model):
        raise TaskPolicyError("task_policy_invalid_model", f"{field}을(를) 확인할 수 없습니다.")
    return model


def _normalize_reasoning(value: Any) -> str:
    try:
        reasoning = normalize_reasoning_effort(value)
    except ValueError as exc:
        raise TaskPolicyError("task_policy_invalid_reasoning", "지원하지 않는 추론 강도입니다.")
    return reasoning


def _normalize_config(config: Mapping[str, Any], *, field: str = "config") -> dict[str, str]:
    if not isinstance(config, Mapping):
        raise TaskPolicyError("task_policy_config_required", f"{field}를 모두 입력해야 합니다.")
    mode = str(config.get("mode") or "").strip().lower().replace("-", "_")
    if mode in {"llm_api", "api"}:
        mode = "api"
    elif mode in {"llm_cli", "cli", "agent"}:
        mode = "cli"
    else:
        raise TaskPolicyError("task_policy_invalid_mode", "실행 방식은 API 또는 CLI여야 합니다.")
    provider = str(config.get("provider") or "").strip().lower()
    if mode == "api":
        return {"mode": "api", "provider": provider,
                "model": str(config.get("model") or ""),
                "reasoningEffort": str(config.get("reasoningEffort") or "provider_default")}
    allowed = CLI_PROVIDERS
    if provider not in allowed:
        raise TaskPolicyError("task_policy_unsupported_combination", "지원하지 않는 CLI 제공자입니다.")
    model = _normalize_model(config.get("model"), field="model")
    reasoning = _normalize_reasoning(config.get("reasoningEffort", "provider_default"))
    if not is_supported_reasoning_effort(mode, provider, model, reasoning):
        raise TaskPolicyError("task_policy_unsupported_reasoning", "선택한 CLI 제공자와 모델은 이 추론 강도를 지원하지 않습니다.")
    return {
        "mode": mode,
        "provider": provider,
        "model": model,
        "reasoningEffort": reasoning,
    }


def _normalize_tasks(raw_tasks: Any, *, existing: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    if raw_tasks is None:
        raw_tasks = {}
    if not isinstance(raw_tasks, Mapping):
        raise TaskPolicyError("task_policy_invalid", "tasks는 객체여야 합니다.")
    previous = existing if isinstance(existing, Mapping) else {}
    unknown = [str(key) for key in raw_tasks if str(key) not in TASK_DEFINITIONS]
    if unknown:
        raise TaskPolicyError("task_policy_unknown_task", "지원하지 않는 작업 설정이 포함되어 있습니다.")
    result: dict[str, dict[str, Any]] = {}
    for key in TASK_KEYS:
        old = previous.get(key) if isinstance(previous.get(key), Mapping) else {}
        supplied = raw_tasks.get(key, old if old else {"enabled": False, "config": None})
        if not isinstance(supplied, Mapping):
            raise TaskPolicyError("task_policy_invalid", "작업 설정은 객체여야 합니다.")
        enabled = supplied.get("enabled", False)
        if not isinstance(enabled, bool):
            raise TaskPolicyError("task_policy_invalid", "enabled는 불리언이어야 합니다.")
        if "config" in supplied:
            config_value = supplied.get("config")
        else:
            config_value = old.get("config") if isinstance(old, Mapping) else None
        # Turning a row off is reversible.  Treat a UI null as "no new
        # override" so a previously saved config remains available when the
        # row is enabled again.
        if not enabled and config_value is None and isinstance(old, Mapping):
            config_value = old.get("config")
        normalized_config = None if config_value in (None, {}) else _normalize_config(config_value, field=f"{key}.config")
        if enabled and normalized_config is None:
            raise TaskPolicyError("task_policy_config_required", "별도 설정을 켠 작업은 실행 방식·제공자·모델·추론 강도를 모두 입력해야 합니다.")
        result[key] = {"enabled": enabled, "config": normalized_config}
    return result


def _normalize_policy(raw: Any, *, existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise TaskPolicyError("task_policy_corrupt", "작업별 AI Agent 설정 파일 형식이 올바르지 않습니다.", status=500)
    schema = raw.get("schemaVersion")
    if schema != SCHEMA_VERSION:
        raise TaskPolicyError("task_policy_schema_unsupported", "지원하지 않는 작업별 AI Agent 설정 버전입니다.", status=500)
    revision = _safe_int(raw.get("revision"), "revision")
    tasks = _normalize_tasks(raw.get("tasks"), existing=existing)
    return {"schemaVersion": SCHEMA_VERSION, "revision": revision, "tasks": tasks}


def _read_policy_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_policy()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise TaskPolicyError("task_policy_corrupt", "작업별 AI Agent 설정 파일을 읽을 수 없습니다.", status=500) from exc
    try:
        return _normalize_policy(raw)
    except TaskPolicyError as exc:
        # A malformed on-disk policy is a persisted configuration failure, not
        # a client validation error.  Preserve the stable code while exposing
        # it as a server-side settings problem.
        if exc.status >= 500:
            raise
        raise TaskPolicyError(exc.code, str(exc), status=500) from exc


def load_task_policy(*, root: Path | None = None) -> dict[str, Any]:
    """Read policy, projecting a missing file to all-off in memory only."""
    return _read_policy_file(task_policy_path(root))


def _public_projection(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Project a normalized policy without touching disk (also lock-safe)."""
    tasks = {}
    for key in TASK_KEYS:
        row = policy["tasks"][key]
        tasks[key] = {
            "label": TASK_DEFINITIONS[key]["label"],
            "enabled": bool(row["enabled"]),
            "config": deepcopy(row["config"]),
        }
    return {
        "schemaVersion": policy["schemaVersion"],
        "revision": policy["revision"],
        "tasks": tasks,
        # The generic list remains useful to older consumers; provider/model
        # specific controls use ``reasoning_choices`` below.
        "reasoningChoices": [{"value": value, "label": "제공자 기본값" if value == "provider_default" else value} for value in SUPPORTED_REASONING],
    }


def public_task_policy(*, root: Path | None = None) -> dict[str, Any]:
    """Return a UI-safe projection including labels and capability choices."""
    return _public_projection(load_task_policy(root=root))


def _body_tasks(body: Mapping[str, Any]) -> Any:
    tasks = body.get("tasks")
    if tasks is not None:
        return tasks
    # Accepting a direct task map keeps the small endpoint convenient while
    # retaining the canonical persisted shape.
    return {key: body[key] for key in TASK_KEYS if key in body}


def save_task_policy(body: Mapping[str, Any] | None, *, root: Path | None = None) -> dict[str, Any]:
    """Revision-safe atomic policy write; returns the UI-safe projection."""
    payload = body if isinstance(body, Mapping) else {}
    path = task_policy_path(root)
    with artifact_lock(path):
        latest = _read_policy_file(path)
        if "expectedRevision" not in payload:
            raise TaskPolicyError("task_policy_expected_revision_required", "저장 전 최신 revision이 필요합니다.")
        expected = _safe_int(payload.get("expectedRevision"), "expectedRevision")
        if expected != latest["revision"]:
            raise TaskPolicyConflict(_public_projection(latest))
        next_policy = {
            "schemaVersion": SCHEMA_VERSION,
            "revision": latest["revision"] + 1,
            "tasks": _normalize_tasks(_body_tasks(payload), existing=latest["tasks"]),
        }
        for key, row in next_policy["tasks"].items():
            if (row.get("config") or {}).get("mode") == "api":
                old = latest["tasks"][key]
                if row.get("enabled") or row.get("config") != old.get("config"):
                    raise TaskPolicyError("llm_api_removed", "API 설정은 저장할 수 없습니다. CLI를 선택해 주세요.", status=409)
        encoded = (json.dumps(next_policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        write_bytes_atomic(path, encoded)
    return public_task_policy(root=root)


def canonical_task_key(task_key: str) -> str:
    raw = str(task_key or "").strip().lower().replace("-", "_")
    canonical = RUNTIME_TASK_ALIASES.get(raw, raw)
    if canonical not in TASK_DEFINITIONS:
        raise TaskPolicyError("task_policy_unknown_task", "지원하지 않는 작업입니다.")
    return canonical


def _global_config() -> dict[str, str]:
    """Resolve current global settings without returning credentials."""
    from features.llm_settings.client import ai_agent_enabled, ai_agent_mode, configured_global_reasoning_effort, load_dotenv, selected_cli_config

    mode = ai_agent_mode()
    if mode == "api":
        raise TaskPolicyError("llm_api_removed", "설정에서 CLI로 전환하거나 AI를 꺼 주세요.", status=409)
    from features.agent_mode.setup import configured_model, configured_provider

    provider = configured_provider()
    if provider == "auto":
        # bridge_status is a read-only capability probe.  It is needed only
        # when an override inherits the global CLI setting; no credentials are
        # returned or persisted.
        from features.agent_mode.bridge import bridge_status

        provider = str((bridge_status(refresh=False) or {}).get("selectedAdapter") or "").strip().lower()
        if not provider:
            raise TaskPolicyError("task_policy_auto_provider_unresolved", "전역 CLI 제공자 auto를 확정할 수 없습니다.")
    if provider not in CLI_PROVIDERS:
        raise TaskPolicyError("task_policy_unsupported_combination", "전역 CLI 제공자를 확인할 수 없습니다.")
    config = {
        "mode": "cli",
        "provider": provider,
        "model": configured_model(provider),
        "reasoningEffort": configured_global_reasoning_effort(
            mode="cli",
            provider=provider,
            model=configured_model(provider),
            runtime=True,
        ),
    }
    return {**_normalize_config(config), "enabled": "1" if ai_agent_enabled() else "0"}


def resolve_task_policy(
    task_key: str,
    *,
    policy: Mapping[str, Any] | None = None,
    global_enabled: bool | None = None,
    global_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve one task at the producer boundary into a secret-free snapshot."""
    canonical = canonical_task_key(task_key)
    current = _normalize_policy(policy) if policy is not None else load_task_policy()
    task = current["tasks"][canonical]
    override = task.get("config") if task.get("enabled") else None
    # The global switch is the only global fact needed before selecting an
    # explicit task override.  In particular, an explicit API task must not be
    # blocked by an unrelated global CLI ``auto`` provider that cannot resolve.
    if global_enabled is None:
        from features.llm_settings.client import ai_agent_enabled

        effective_global_enabled = bool(ai_agent_enabled())
    else:
        effective_global_enabled = bool(global_enabled)
    if override or not effective_global_enabled:
        global_cfg = {}
    elif global_config is not None:
        global_cfg = _normalize_config(global_config)
    else:
        global_cfg = _global_config()
    selected = deepcopy(override or global_cfg)
    if effective_global_enabled and selected.get("mode") == "api":
        raise TaskPolicyError("llm_api_removed", "이 작업의 API 설정을 CLI로 전환해 주세요.", status=409)
    result = {
        "taskKey": canonical,
        "runtimeTaskType": str(task_key),
        "source": "task" if override else "global",
        "policyRevision": current["revision"],
        "enabled": bool(effective_global_enabled),
        "mode": selected.get("mode") if effective_global_enabled else "rules",
        "provider": selected.get("provider", ""),
        "model": selected.get("model", ""),
        "reasoningEffort": selected.get("reasoningEffort", "provider_default"),
        "configuredMode": selected.get("mode", ""),
        "config": {
            "mode": selected.get("mode", ""),
            "provider": selected.get("provider", ""),
            "model": selected.get("model", ""),
            "reasoningEffort": selected.get("reasoningEffort", "provider_default"),
        },
    }
    return result


# Names used by producers and test harnesses can read naturally while the
# canonical function remains singular and easy to locate.
resolve_for_task = resolve_task_policy
task_policy_snapshot = resolve_task_policy
read_task_policy = load_task_policy
save_task_policies = save_task_policy
normalize_task_config = _normalize_config
normalize_task_policies = _normalize_policy


__all__ = [
    "API_PROVIDERS",
    "CLI_PROVIDERS",
    "CLI_REASONING_EFFORTS",
    "RUNTIME_TASK_ALIASES",
    "SCHEMA_VERSION",
    "SUPPORTED_REASONING",
    "TASK_DEFINITIONS",
    "TASK_KEYS",
    "TaskPolicyConflict",
    "TaskPolicyError",
    "canonical_task_key",
    "load_task_policy",
    "public_task_policy",
    "resolve_for_task",
    "resolve_task_policy",
    "task_policy_snapshot",
    "normalize_task_config",
    "normalize_task_policies",
    "save_task_policy",
    "save_task_policies",
    "task_policy_path",
]
