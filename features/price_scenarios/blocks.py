"""Result block shapes shared by the pure calculations (spec §4.1)."""
from __future__ import annotations


def unavailable(code: str | dict, sub_code: str | None = None) -> dict:
    """Carry the complete reason, including the range counts, through every consumer."""
    reason = dict(code) if isinstance(code, dict) else {"code": code}
    if sub_code:
        reason["subCode"] = sub_code
    return {"status": "unavailable", "reason": reason}


def not_applicable(code: str) -> dict:
    return {"status": "not_applicable", "reason": {"code": code}}
