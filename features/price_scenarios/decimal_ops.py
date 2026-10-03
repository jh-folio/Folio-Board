"""Exact input numbers and canonical input fingerprints."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext


def number(value) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("invalid_number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid_number") from exc
    if not result.is_finite():
        raise ValueError("invalid_number")
    return result


def source_number(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "—", "N/A"}:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return str(number(text))
    except ValueError:
        return None


def rounded(value, places=4) -> str:
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_HALF_EVEN
        result = number(value).quantize(Decimal(1).scaleb(-places))
        return format(abs(result) if result == 0 else result, "f")


def canonical(value) -> str:
    # Strings carry the original precision; never recode numeric strings here.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_source_json(raw: str | bytes) -> dict:
    """Decode original JSON without discarding the numeric lexical precision."""
    return json.loads(raw, parse_float=Decimal)


def fingerprint(inputs: dict) -> str:
    def validate(value):
        if isinstance(value, float):
            raise ValueError("input_numbers_must_be_decimal_strings")
        if isinstance(value, dict):
            for child in value.values():
                validate(child)
        elif isinstance(value, list):
            for child in value:
                validate(child)
    validate(inputs)
    return hashlib.sha256(canonical(inputs).encode("utf-8")).hexdigest()
