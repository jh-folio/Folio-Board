"""Result block shapes shared by the pure calculations (spec §4.1)."""
from __future__ import annotations


def unavailable(code: str, sub_code: str | None = None) -> dict:
    return {"status": "unavailable", "reason": {"code": code, **({"subCode": sub_code} if sub_code else {})}}


def not_applicable(code: str) -> dict:
    return {"status": "not_applicable", "reason": {"code": code}}
