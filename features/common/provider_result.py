"""Private E0 payloads. Never put these objects in report JSON or diagnostics.

Offsets are Python character offsets into the exact returned text, not source
document offsets. Remapping is deliberately conservative: edited or duplicated
anchors lose their position instead of being attached to another claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from threading import Lock
import time


@dataclass(frozen=True, slots=True, repr=False)
class Citation:
    block_index: int
    start: int | None = None
    end: int | None = None
    source_id: str | None = None
    url: str | None = None
    title: str | None = None
    cited_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_unit: str | None = None

    def remap(self, before: str, after: str) -> Citation:
        if self.start is None or self.end is None or not 0 <= self.start < self.end <= len(before):
            return replace(self, start=None, end=None)
        if before == after:
            return self
        anchor = before[self.start:self.end]
        first_before, first_after = before.find(anchor), after.find(anchor)
        if (first_after < 0 or before.find(anchor, first_before + 1) >= 0
                or after.find(anchor, first_after + 1) >= 0):
            return replace(self, start=None, end=None)
        start = after.index(anchor)
        return replace(self, start=start, end=start + len(anchor))


@dataclass(frozen=True, slots=True, repr=False)
class ResponseBlock:
    kind: str
    text: str | None = None
    identifier: str | None = None


class ContinuationLease:
    """A single-consumer, owner-bound capability with an explicit memory TTL.

    This is not a provider resume command. An adapter must explicitly support
    resumption before constructing an available lease. Closing/cancelling or
    expiring it clears the private token; process restart intentionally loses it.
    """
    def __init__(self, token: str, *, owner: str, ttl_seconds: float, clock=time.monotonic):
        if not token or not owner or not 0 < ttl_seconds <= 3600:
            raise ValueError("invalid_continuation_lease")
        self._token = token
        self._owner = owner
        self._clock = clock
        self._deadline = clock() + ttl_seconds
        self._state = "available"
        self._lock = Lock()

    def _expire(self):
        if self._state == "available" and self._clock() >= self._deadline:
            self._token = ""
            self._state = "expired"

    @property
    def state(self):
        with self._lock:
            self._expire()
            return self._state

    def claim(self, *, owner: str) -> str:
        with self._lock:
            self._expire()
            if owner != self._owner or self._state != "available":
                raise ValueError("continuation_unavailable")
            token, self._token = self._token, ""
            self._state = "consumed"
            return token

    def cancel(self):
        with self._lock:
            if self._state == "available":
                self._token = ""
                self._state = "cancelled"


@dataclass(frozen=True, slots=True, repr=False)
class ProviderPayload:
    adapter: str = "unknown"
    model: str | None = None
    raw_stop_reason: str | None = None
    blocks: tuple[ResponseBlock, ...] = ()
    citations: tuple[Citation, ...] = ()
    citation_capability: str = "unknown"
    continuation_state: str = "unknown"
    continuation_capability: str = "unsupported"
    session_id: str | None = None
    continuation: ContinuationLease | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.adapter not in {"codex", "claude", "antigravity", "unknown"}:
            raise ValueError("invalid_provider_adapter")
        if self.citation_capability not in {"observed", "unknown", "unsupported"}:
            raise ValueError("invalid_citation_capability")
        if self.continuation_state not in {"none", "paused", "tool_pending", "unknown"}:
            raise ValueError("invalid_continuation_state")
        if self.continuation_capability not in {"supported", "unsupported", "unknown"}:
            raise ValueError("invalid_continuation_capability")
        if self.continuation is not None and self.continuation_capability != "supported":
            raise ValueError("unsupported_continuation")

    def remap(self, before: str, after: str) -> ProviderPayload:
        return replace(self, citations=tuple(c.remap(before, after) for c in self.citations))
