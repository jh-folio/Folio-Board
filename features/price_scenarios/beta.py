"""Beta input measured once per calculation and then stored as an input.

The provider gives a current value with no observation date. It is stored as
{value, source, providerSymbol, basis}; the retrieval time stays outside the
input (unfingerprinted metadata) so a stored snapshot replays from stored values.
Absent or implausible values stay unmeasured and keep the DCF on its fallback.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Callable

BETA_SOURCE = "yfinance_info_beta"
BETA_BASIS = "provider_current_value"
MAX_ABS_BETA = 10.0


def unmeasured(reason: str) -> dict:
    return {"value": None, "source": "not_measured", "reason": reason}


def _fetch_info(provider_symbol: str) -> dict:
    # The exact provider symbol only. No `.KS`/`.KQ` candidate guessing.
    import yfinance as yf

    return yf.Ticker(provider_symbol).info or {}


def measure_beta(provider_symbol: str, *, fetch_info: Callable[[str], dict] | None = None,
                 now: Callable[[], dt.datetime] | None = None) -> dict:
    """Return {"beta": input dict, "fetchedAt": iso} and never raise on provider trouble."""
    clock = now or (lambda: dt.datetime.now(dt.timezone.utc))
    fetched_at = clock().isoformat()
    if not isinstance(provider_symbol, str) or not provider_symbol.strip():
        return {"beta": unmeasured("provider_symbol_missing"), "fetchedAt": fetched_at}
    try:
        info = (fetch_info or _fetch_info)(provider_symbol)
    except Exception:  # noqa: BLE001 - a provider failure is a state, not a crash
        return {"beta": unmeasured("provider_error"), "fetchedAt": fetched_at}
    if not isinstance(info, dict):
        return {"beta": unmeasured("provider_shape_unrecognized"), "fetchedAt": fetched_at}
    echoed = info.get("symbol")
    if isinstance(echoed, str) and echoed.strip() and echoed.strip().upper() != provider_symbol.strip().upper():
        return {"beta": unmeasured("provider_symbol_mismatch"), "fetchedAt": fetched_at}
    raw = info.get("beta")
    if isinstance(raw, bool) or raw is None:
        return {"beta": unmeasured("beta_not_provided"), "fetchedAt": fetched_at}
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return {"beta": unmeasured("beta_not_numeric"), "fetchedAt": fetched_at}
    if not math.isfinite(value) or abs(value) > MAX_ABS_BETA:
        return {"beta": unmeasured("beta_out_of_range"), "fetchedAt": fetched_at}
    return {"beta": {"value": repr(value), "source": BETA_SOURCE, "providerSymbol": provider_symbol.strip(),
                     "basis": BETA_BASIS}, "fetchedAt": fetched_at}
