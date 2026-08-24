"""Explicit per-run model call slots; no hidden retries."""
from __future__ import annotations

from dataclasses import dataclass, field


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


def deep_research_budget() -> CallBudget:
    return CallBudget({"initial": 1, "repair": 2})


def kr_briefing_budget() -> CallBudget:
    return CallBudget({"adjudication": 1, "generation": 1, "repair": 1})


__all__ = ["CallBudget", "deep_research_budget", "kr_briefing_budget"]
