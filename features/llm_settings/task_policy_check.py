"""Read-only capability checks for a draft task-policy configuration."""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping

from features.agent_mode.bridge import bridge_status
from features.llm_settings.task_policy import CLI_PROVIDERS, TaskPolicyError, _normalize_config


def _checked_at() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _cli_check(config: Mapping[str, str]) -> dict:
    provider = str(config["provider"])
    model = str(config["model"])
    status = bridge_status(refresh=False)
    adapter = next(
        (row for row in status.get("adapters") or [] if isinstance(row, Mapping) and row.get("id") == provider),
        None,
    )
    if not adapter:
        return {
            "mode": "cli",
            "provider": provider,
            "model": model,
            "status": "cli_unavailable",
            "available": False,
            "modelAccessVerified": False,
            "generationAttempted": False,
            "message": "선택한 CLI를 확인할 수 없습니다.",
            "checkedAt": _checked_at(),
        }
    available = bool(adapter.get("available")) and bool(adapter.get("bridgeSupported", True))
    if available:
        message = f"{adapter.get('label') or provider} 설치·로그인을 확인했습니다. 선택한 모델 접근은 확인하지 않았습니다."
        result_status = "cli_ready_model_unverified"
    else:
        detail = str(adapter.get("error") or "설치와 로그인 상태를 확인하세요.").strip()
        message = f"{adapter.get('label') or provider}: {detail}"
        result_status = "cli_unavailable"
    return {
        "mode": "cli",
        "provider": provider,
        "model": model,
        "status": result_status,
        "available": available,
        "modelAccessVerified": False,
        "generationAttempted": False,
        "message": message,
        "checkedAt": _checked_at(),
    }


def check_task_policy(config: Mapping[str, object] | None) -> dict:
    """Check a draft config without saving it or invoking model generation."""
    if not isinstance(config, Mapping):
        raise TaskPolicyError("task_policy_config_required", "작업별 설정을 모두 입력해야 합니다.")
    normalized = _normalize_config(config, field="config")
    if normalized["mode"] == "api":
        raise TaskPolicyError("llm_api_removed", "API 연결 검사는 지원하지 않습니다. CLI를 선택해 주세요.", status=409)
    if normalized["provider"] not in CLI_PROVIDERS:
        raise TaskPolicyError("task_policy_unsupported_combination", "선택한 실행 방식과 제공자 조합을 지원하지 않습니다.")
    return _cli_check(normalized)
