"""Explicit per-run model call slots; no hidden retries."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
import math
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar


_BRIEFING_BUDGET = ContextVar("briefing_repair_budget", default=None)


def current_briefing_budget():
    return _BRIEFING_BUDGET.get()


@contextmanager
def bind_briefing_budget(budget):
    token = _BRIEFING_BUDGET.set(budget)
    try:
        yield budget
    finally:
        _BRIEFING_BUDGET.reset(token)


@dataclass(slots=True)
class CallBudget:
    limits: dict[str, int]
    used: dict[str, int] = field(default_factory=dict)

    def claim(self, slot: str) -> None:
        limit = int(self.limits.get(slot, 0))
        current = int(self.used.get(slot, 0))
        if current >= limit:
            raise RuntimeError(f"call_budget_exhausted:{slot}")
        self.used[slot] = current + 1

    def snapshot(self) -> dict:
        return {
            "limits": dict(self.limits),
            "used": dict(self.used),
            "remaining": {key: max(0, int(limit) - int(self.used.get(key, 0))) for key, limit in self.limits.items()},
        }


class SharedRepairBudget:
    """One bounded repair slot shared by every briefing post-processor.

    Briefing generation can pass through concentration, the generic quality
    loop, and the final fact validator.  Those stages are deliberately not
    independent retry budgets: at most one repair may run for one generation
    input.  ``deadline`` is an optional monotonic deadline and ``cancelled``
    may be a callback or an Event-like object.  The class is thread-safe so
    the API builder's per-market workers cannot each claim the same slot.
    """

    def __init__(
        self,
        max_repairs: int = 1,
        *,
        deadline: float | None = None,
        cancelled: Callable[[], bool] | object | None = None,
    ) -> None:
        self.max_repairs = min(1, max(0, int(max_repairs)))
        if deadline is not None and not math.isfinite(float(deadline)):
            raise ValueError("repair_deadline_invalid")
        self.deadline = deadline
        self.cancelled = cancelled
        self.used = 0
        self.claims: list[str] = []
        self.reason = ""
        self._lock = threading.Lock()

    def _cancelled(self) -> bool:
        value = self.cancelled
        if value is None:
            return False
        try:
            return bool(value() if callable(value) else value.is_set())
        except Exception:
            # An unreadable cancellation signal must not authorize more work.
            return True

    def check_active(self) -> None:
        if self._cancelled():
            raise RuntimeError("cancelled")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError("deadline_expired")

    def remaining_seconds(self) -> float | None:
        self.check_active()
        return None if self.deadline is None else max(0.001, self.deadline - time.monotonic())

    def unavailable_reason(self) -> str:
        if self._cancelled():
            return "cancelled"
        if self.deadline is not None:
            try:
                if time.monotonic() >= float(self.deadline):
                    return "deadline_expired"
            except (TypeError, ValueError):
                pass
        if self.used >= self.max_repairs:
            return "shared_repair_budget_exhausted"
        return ""

    def claim(self, stage: str = "briefing_finalization") -> None:
        with self._lock:
            reason = self.unavailable_reason()
            if reason:
                self.reason = reason
                raise RuntimeError(reason)
            self.used += 1
            allowed = {"quality", "structure", "concentration", "briefing_finalization"}
            self.claims.append(stage if stage in allowed else "briefing_finalization")

    def snapshot(self) -> dict:
        return {
            "maxRepairs": self.max_repairs,
            "used": self.used,
            "remaining": max(0, self.max_repairs - self.used),
            "claims": list(self.claims),
            "reason": self.reason,
        }


def deep_research_budget() -> CallBudget:
    return CallBudget({"initial": 1, "repair": 2})


def kr_briefing_budget() -> CallBudget:
    return CallBudget({"adjudication": 1, "generation": 1, "repair": 1})


__all__ = [
    "CallBudget",
    "SharedRepairBudget",
    "deep_research_budget",
    "kr_briefing_budget",
]
