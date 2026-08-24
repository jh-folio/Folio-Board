from __future__ import annotations

import os


def concentration_mode() -> str:
    value = str(os.environ.get("KR_BRIEFING_CONCENTRATION_MODE", "shadow") or "shadow").strip().lower()
    return value if value in {"off", "shadow", "active"} else "shadow"


def applies_to(*, market_scope: str, kind: str) -> bool:
    return str(market_scope or "").lower() == "kr" and str(kind or "daily").lower() == "daily"


__all__ = ["applies_to", "concentration_mode"]
