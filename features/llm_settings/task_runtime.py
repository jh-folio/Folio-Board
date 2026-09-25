"""Runtime helpers for applying an immutable task AI policy snapshot.

The settings file is read at a producer boundary.  This module keeps the
result small and serializable and binds the CLI policy through a ContextVar
so nested feature calls inherit the same provider/model/effort.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any, Iterator, Mapping

from features.llm_settings.client import (
    ai_agent_enabled,
)
from features.llm_settings.task_policy import (
    canonical_task_key,
    resolve_task_policy,
)


_TASK_POLICY: ContextVar[dict[str, Any] | None] = ContextVar("folio_task_policy", default=None)


def task_snapshot(task_key: str, snapshot: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a defensive copy of an already resolved snapshot.

    ``snapshot`` is used by queued jobs and continuation paths.  It is never
    re-resolved there because doing so would apply a later settings edit to an
    already accepted request.
    """
    if snapshot is None:
        return resolve_task_policy(task_key)
    if not isinstance(snapshot, Mapping):
        raise ValueError("task_policy_snapshot_required")
    canonical = canonical_task_key(task_key)
    supplied_key = str(snapshot.get("taskKey") or canonical)
    if canonical_task_key(supplied_key) != canonical:
        raise ValueError("task_policy_snapshot_task_mismatch")
    result = deepcopy(dict(snapshot))
    result["taskKey"] = canonical
    generation_mode(result)
    return result


def generation_mode(snapshot: Mapping[str, Any]) -> str:
    """Map a resolved task snapshot to the public generation-mode enum."""
    if not bool(snapshot.get("enabled")):
        return "rules"
    mode = str(snapshot.get("mode") or "").strip().lower().replace("-", "_")
    if mode in {"api", "llm_api"}:
        from features.llm_settings.task_policy import TaskPolicyError
        raise TaskPolicyError("llm_api_removed", "이 작업의 API 설정을 CLI로 전환해 주세요.", status=409)
    if mode == "cli":
        return "llm_cli"
    return "rules"


def task_is_enabled(snapshot: Mapping[str, Any], *, recheck_global: bool = False) -> bool:
    """Check the frozen task decision and, optionally, the current global gate."""
    if not bool(snapshot.get("enabled")):
        return False
    return not recheck_global or bool(ai_agent_enabled())


def task_policy_metadata(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return the secret-free policy fields suitable for a report/job record."""
    return {
        "taskKey": str(snapshot.get("taskKey") or ""),
        "source": str(snapshot.get("source") or ""),
        "mode": generation_mode(snapshot),
        "provider": str(snapshot.get("provider") or ""),
        "model": str(snapshot.get("model") or ""),
        "reasoningEffort": str(snapshot.get("reasoningEffort") or "provider_default"),
        "policyRevision": int(snapshot.get("policyRevision") or 0),
    }


def current_task_policy() -> dict[str, Any] | None:
    """Return a defensive copy of the policy bound to this producer context."""
    current = _TASK_POLICY.get()
    return deepcopy(current) if isinstance(current, dict) else None


@contextmanager
def bind_task_policy(snapshot: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Apply one task snapshot to all nested CLI calls in this context."""
    frozen = task_snapshot(str(snapshot.get("taskKey") or ""), snapshot)
    policy_token = _TASK_POLICY.set(deepcopy(frozen))
    try:
        generation_mode(frozen)
        yield frozen
    finally:
        _TASK_POLICY.reset(policy_token)


__all__ = [
    "bind_task_policy",
    "current_task_policy",
    "generation_mode",
    "task_is_enabled",
    "task_policy_metadata",
    "task_snapshot",
]
