"""Calculation and read services for price snapshots (explicit `계산` only).

A calculation collects sources, assembles one snapshot and saves it. The save is
a fenced commit when a SharedJob owns it (receipt, recovery) and a plain
idempotent save otherwise. Anything that prevents a valid snapshot is recorded as
the instrument's last attempt (a small replaceable file, not evidence) and the
existing snapshot stays the latest one. Reads never collect, calculate or migrate.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
from copy import deepcopy
from concurrent.futures import CancelledError
from pathlib import Path

from features.common.atomic_replace import write_bytes_atomic

from .assemble import assemble
from .collect import Collector, CollectionError
from .decimal_ops import fingerprint
from .projection import project
from .store import PriceStore, PriceStoreError, snapshot_id

INSTRUMENT = re.compile(r"^(US|KR):([A-Z0-9.\-]{1,10})$")
ATTEMPTS_FILE = "price-attempts.json"
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_ATTEMPTS_LOCK = threading.Lock()


def _instrument_lock(instrument_id: str) -> threading.Lock:
    """One calculation per instrument at a time: a button press and a report generation never interleave."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(instrument_id, threading.Lock())


class CalculationNotStored(RuntimeError):
    """No valid snapshot could be built; `.code` is the stable reason."""

    def __init__(self, code: str, sub_code: str | None = None, source_diagnostic: dict | None = None):
        super().__init__(code)
        self.code, self.sub_code = code, sub_code
        self.source_diagnostic = source_diagnostic or {}


def parse_instrument(value) -> tuple[str, str]:
    match = INSTRUMENT.fullmatch(value) if isinstance(value, str) else None
    if match is None or (match.group(1) == "KR" and not re.fullmatch(r"[0-9][A-Z0-9]{5}", match.group(2))):
        raise ValueError("invalid_instrument_id")
    return match.group(1), match.group(2)


def store_for(root) -> PriceStore:
    return PriceStore(Path(root) / "market-memory.sqlite3")


# --- last attempt per instrument ------------------------------------------------

def read_attempt(root, instrument_id: str) -> dict | None:
    try:
        return json.loads((Path(root) / ATTEMPTS_FILE).read_text(encoding="utf-8")).get(instrument_id)
    except (OSError, ValueError, AttributeError):
        return None


def _write_attempt(root, instrument_id: str, record: dict) -> None:
    with _ATTEMPTS_LOCK:
        _write_attempt_locked(root, instrument_id, record)


def _write_attempt_locked(root, instrument_id: str, record: dict) -> None:
    path = Path(root) / ATTEMPTS_FILE
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
        current = current if isinstance(current, dict) else {}
    except (OSError, ValueError):
        current = {}
    current[instrument_id] = record
    write_bytes_atomic(path, (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


# --- calculation ----------------------------------------------------------------

def calculate(root, instrument_id: str, *, job_id=None, progress=None, collector: Collector | None = None, now=None,
              cancel_check=None) -> dict:
    """Collect, assemble and save one snapshot. Raises CalculationNotStored when nothing valid exists."""
    from features.common.jobs import get_shared_job

    market, ticker = parse_instrument(instrument_id)
    clock = now or (lambda: dt.datetime.now(dt.timezone.utc))

    def cancel():
        if cancel_check:
            try:
                cancel_check()
            except RuntimeError as error:
                if str(error) == "cancelled":
                    raise RuntimeError("price_calculation_cancelled") from error
                raise
        if job_id:
            job = get_shared_job(job_id)
            if job is None or job.status.value in {"cancel_requested", "cancelled", "failed_restart"}:
                raise RuntimeError("price_calculation_cancelled")

    with _instrument_lock(instrument_id):
        started = clock().isoformat()
        try:
            cancel()
            collector = collector or Collector(root, now=clock, cancel=cancel, progress=progress)
            raw = collector.collect(market, ticker)
            built = assemble(raw)
            if built["status"] != "available":
                raise CalculationNotStored(built["reason"]["code"], built["reason"].get("subCode"))
            cancel()
            store = store_for(root)
            inputs, results, meta = built["inputs"], built["results"], built["meta"]
            new_id = snapshot_id(inputs["instrumentId"], inputs["asOf"], inputs["methodVersion"], fingerprint(inputs))
            write = lambda: store.save_snapshot(inputs, results, meta=meta)
            if job_id:
                from features.common.macro_data.schema import digest
                from features.common.macro_job_commit import commit
                saved = commit(root, job_id, [{"type": "price_snapshot", "id": new_id, "hash": digest({"inputs": inputs, "results": results})}],
                               write, saved_count=1)
            else:
                saved = write()
        except CancelledError:
            raise
        except CollectionError as error:
            _write_attempt(root, instrument_id, {"status": "failed", "reason": {**error.source_diagnostic, "code": error.code, **({"subCode": error.sub_code} if error.sub_code else {})},
                                                 "startedAt": started, "finishedAt": clock().isoformat()})
            raise CalculationNotStored(error.code, error.sub_code, error.source_diagnostic) from None
        except CalculationNotStored as error:
            _write_attempt(root, instrument_id, {"status": "failed", "reason": {"code": error.code, **({"subCode": error.sub_code} if error.sub_code else {})},
                                                 "startedAt": started, "finishedAt": clock().isoformat()})
            raise
        except PriceStoreError as error:
            _write_attempt(root, instrument_id, {"status": "failed", "reason": {"code": error.code}, "startedAt": started, "finishedAt": clock().isoformat()})
            raise CalculationNotStored(error.code) from None
        except RuntimeError as error:
            if str(error) == "price_calculation_cancelled":
                raise  # a cancelled job is not a failed calculation
            _write_attempt(root, instrument_id, {"status": "failed", "reason": {"code": "calculation_failed"}, "startedAt": started, "finishedAt": clock().isoformat()})
            raise CalculationNotStored("calculation_failed") from None
        except Exception:  # noqa: BLE001 - an unexpected source shape or database error must still leave a visible last attempt
            _write_attempt(root, instrument_id, {"status": "failed", "reason": {"code": "calculation_failed"}, "startedAt": started, "finishedAt": clock().isoformat()})
            raise CalculationNotStored("calculation_failed") from None
        _write_attempt(root, instrument_id, {"status": "saved", "snapshotId": saved["snapshotId"] if isinstance(saved, dict) else new_id,
                                             "startedAt": started, "finishedAt": clock().isoformat()})
        return {"snapshotId": new_id, "savedCount": 1, "instrumentId": instrument_id, "created": bool(saved.get("created", True)) if isinstance(saved, dict) else True}


# --- reads (never collect, calculate or write) ----------------------------------

def _summary(snapshot: dict) -> dict:
    results = snapshot["results"]
    return {"snapshotId": snapshot["snapshotId"], "instrumentId": snapshot["instrumentId"], "asOf": snapshot["asOf"],
            "computedAt": snapshot["computedAt"], "methodVersion": snapshot["inputs"]["methodVersion"],
            "supportStatus": results["support"]["status"]}


def overview(root, instrument_id: str) -> dict:
    parse_instrument(instrument_id)
    store = store_for(root)
    latest = store.latest(instrument_id)
    return {"instrumentId": instrument_id, "latest": _summary(latest) if latest else None,
            "history": store.history(instrument_id), "lastAttempt": read_attempt(root, instrument_id)}


def snapshot_view(root, snapshot_id_: str, *, include_inputs: bool = False, attribution_years: int = 5) -> dict | None:
    snapshot = store_for(root).get(snapshot_id_)
    if snapshot is None:
        return None
    from . import method_at_least
    from .blocks import not_applicable
    results = deepcopy(snapshot["results"])
    results.setdefault("referenceFacts", not_applicable("previous_method"))
    if not method_at_least(snapshot["inputs"]["methodVersion"], 4):
        results.update(returnParts=not_applicable("previous_method"), cashConversion=not_applicable("previous_method"))
    view = {**_summary(snapshot), "results": results,
            "inputSummary": {key: snapshot["inputs"].get(key) for key in ("asOf", "identity", "price", "classificationInputs")},
            "meta": snapshot["meta"]}
    if include_inputs:
        view["inputs"] = snapshot["inputs"]
    from .attribution import historical_attribution
    view["historicalReturnAttribution"] = historical_attribution(snapshot["inputs"], attribution_years)
    return view


def movement_view(root, instrument_id: str, start: str, end: str, snapshot_id_: str | None = None) -> dict:
    parse_instrument(instrument_id)
    store = store_for(root)
    snapshot = store.get(snapshot_id_) if snapshot_id_ else store.latest(instrument_id)
    if snapshot is None:
        return {"status": "not_applicable", "reason": {"code": "comparison_inputs_missing"}}
    if snapshot["instrumentId"] != instrument_id:
        raise PriceStoreError("snapshot_instrument_mismatch")
    from .attribution import movement
    return {**movement(snapshot["inputs"], start, end), "snapshotId": snapshot["snapshotId"],
            "inputFingerprint": snapshot["inputFingerprint"]}


def projection_view(root, snapshot_id_: str, *, criteria_revision_id: int | None = None, override_id: int | None = None,
                    today: dt.date | None = None) -> dict | None:
    store = store_for(root)
    snapshot = store.get(snapshot_id_)
    if snapshot is None:
        return None
    criteria = store.criteria(criteria_revision_id)
    if criteria_revision_id is not None and criteria is None:
        raise PriceStoreError("revision_not_found")
    override = store.override(snapshot["instrumentId"], override_id)
    if override_id is not None and override is None:
        raise PriceStoreError("override_not_found")
    return project(snapshot, criteria, override, store.reviews(snapshot_id_), today=today or dt.datetime.now(dt.timezone.utc).date())


# --- company analysis link ---------------------------------------------------------

def review_marker(root, snapshot_id_) -> dict | None:
    """The re-check rows a report's snapshot carries, for the report reader (spec §4.3). Read only; None without a stored snapshot."""
    if not isinstance(snapshot_id_, str) or not snapshot_id_:
        return None
    store = store_for(root)
    snapshot = store.get(snapshot_id_)
    if snapshot is None:
        return None
    return {"snapshotId": snapshot_id_, "asOf": snapshot["asOf"], "reviewNeeded": [dict(row) for row in store.reviews(snapshot_id_)]}


def snapshot_for_report(root, company: dict, *, calculator=None, progress=None, cancel=None) -> dict:
    """Calculate (or re-confirm) the snapshot a report is written from.

    Used by company-analysis generation, which owns the job: no second job is
    made. Always returns a plain dict: `{"status": "saved", "snapshotId", "view"}`
    or `{"status": "unavailable", "reason"}`. A report never gets a snapshot id
    that was not stored; when nothing valid exists it is written without one.
    """
    market, ticker = str(company.get("market") or "").upper(), str(company.get("ticker") or "").strip().upper()
    if market not in {"US", "KR"} or not ticker:
        return {"status": "unavailable", "reason": {"code": "instrument_not_supported"}}
    instrument = f"{market}:{ticker}"
    try:
        parse_instrument(instrument)
        if cancel:
            cancel()
        options = {"progress": progress, **({"cancel_check": cancel} if cancel else {})}
        out = (calculator or calculate)(root, instrument, **options)
    except ValueError:
        return {"status": "unavailable", "reason": {"code": "instrument_not_supported"}}
    except CalculationNotStored as error:
        return {"status": "unavailable", "reason": {**error.source_diagnostic, "code": error.code, **({"subCode": error.sub_code} if error.sub_code else {})}}
    view = snapshot_view(root, out["snapshotId"])
    if view is None:
        return {"status": "unavailable", "reason": {"code": "snapshot_not_readable"}}
    view["results"].pop("referenceFacts", None)
    view.pop("historicalReturnAttribution", None)
    return {"status": "saved", "snapshotId": out["snapshotId"], "view": view}
