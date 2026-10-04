"""HTTP boundary for price snapshots, the person's criteria and assumptions.

Request bodies are validated here (types, extra fields); numeric ranges are the
store's. GETs never collect, calculate or write; only `calculate` starts work.
Errors carry stable enum codes, never provider text or local paths.
"""
import sqlite3
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from .service import calculate, overview, parse_instrument, projection_view, snapshot_view, store_for
from .service import movement_view
from .store import PriceStoreError

STATUS = {"invalid_number": 422, "out_of_range": 422, "invalid_holding_years": 422, "holding_years_required": 422,
          "revision_conflict": 409, "non_reproducible": 409, "snapshot_not_found": 404, "revision_not_found": 404,
          "override_not_found": 404, "snapshot_instrument_mismatch": 422, "method_version_not_writable": 422,
          "invalid_snapshot_identity": 422}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CalculateBody(Strict):
    instrumentId: StrictStr


class CriteriaBody(Strict):
    requiredReturn: StrictStr | None = None
    minMarginOfSafety: StrictStr | None = None
    holdingYears: StrictInt | None = None
    expectedRevisionId: StrictInt | None = None


class AssumptionBody(Strict):
    instrumentId: StrictStr
    basedOnSnapshotId: StrictStr
    growth: StrictStr | None = None
    exitPE: StrictStr | None = None
    payout: StrictStr | None = None
    expectedOverrideId: StrictInt | None = None


def _error(error: PriceStoreError) -> HTTPException:
    return HTTPException(STATUS.get(error.code, 400), detail={"code": error.code, **({"field": error.field} if error.field else {})})


def _unavailable() -> HTTPException:
    return HTTPException(503, detail="price_store_temporarily_unavailable")


def _instrument(value: str) -> str:
    try:
        parse_instrument(value)
    except ValueError:
        raise HTTPException(400, detail="invalid_instrument_id") from None
    return value


def create_price_router(data_root):
    router = APIRouter(tags=["price"])
    active: dict[str, str] = {}
    lock = threading.Lock()
    root = Path(data_root)

    @router.get("/api/price-movement")
    def read_movement(instrumentId: str, startDate: str, endDate: str, snapshotId: str | None = None):
        try:
            return movement_view(root, _instrument(instrumentId), startDate, endDate, snapshotId)
        except ValueError:
            raise HTTPException(422, detail={"code": "invalid_comparison_dates"}) from None
        except PriceStoreError as error:
            raise _error(error) from None
        except (OSError, sqlite3.Error):
            raise _unavailable() from None

    @router.post("/api/price-snapshots/calculate")
    def start_calculation(body: CalculateBody):
        from features.common.jobs import get_job, submit_job
        instrument = _instrument(body.instrumentId)
        with lock:
            current = get_job(active[instrument]) if instrument in active else None
            if current and current.get("status") in {"queued", "running", "cancel_requested", "committing"}:
                return current
            job = submit_job("price_scenario", "가격 시나리오 계산", calculate, root, instrument, pass_job_id=True, dedicated_thread=True)
            active[instrument] = job["id"]
            return job

    @router.get("/api/price-snapshots")
    def snapshots(instrumentId: str):
        try:
            return overview(root, _instrument(instrumentId))
        except (OSError, sqlite3.Error):
            raise _unavailable() from None

    @router.get("/api/price-snapshots/{snapshot_id}")
    def snapshot(snapshot_id: str, include: str = "", attributionYears: int = 5):
        try:
            view = snapshot_view(root, snapshot_id, include_inputs=include == "inputs", attribution_years=attributionYears)
        except ValueError:
            raise HTTPException(422, detail={"code": "invalid_attribution_years"}) from None
        except (OSError, sqlite3.Error):
            raise _unavailable() from None
        if view is None:
            raise HTTPException(404, detail="snapshot_not_found")
        return view

    @router.get("/api/price-snapshots/{snapshot_id}/projection")
    def projection(snapshot_id: str, criteriaRevisionId: int | None = None, overrideId: int | None = None):
        try:
            view = projection_view(root, snapshot_id, criteria_revision_id=criteriaRevisionId, override_id=overrideId)
        except PriceStoreError as error:
            raise _error(error) from None
        except (OSError, sqlite3.Error):
            raise _unavailable() from None
        if view is None:
            raise HTTPException(404, detail="snapshot_not_found")
        return view

    @router.get("/api/valuation/criteria")
    def read_criteria():
        try:
            return {"criteria": store_for(root).criteria()}
        except (OSError, sqlite3.Error):
            raise _unavailable() from None

    @router.post("/api/valuation/criteria")
    def write_criteria(body: CriteriaBody):
        try:
            return {"criteria": store_for(root).save_criteria(
                required_return=body.requiredReturn, min_margin_of_safety=body.minMarginOfSafety,
                holding_years=body.holdingYears, expected_revision_id=body.expectedRevisionId)}
        except PriceStoreError as error:
            raise _error(error) from None
        except (OSError, sqlite3.Error):
            raise _unavailable() from None

    @router.get("/api/valuation/assumptions")
    def read_assumption(instrumentId: str):
        try:
            return {"override": store_for(root).override(_instrument(instrumentId))}
        except (OSError, sqlite3.Error):
            raise _unavailable() from None

    @router.post("/api/valuation/assumptions")
    def write_assumption(body: AssumptionBody):
        try:
            return {"override": store_for(root).save_override(
                _instrument(body.instrumentId), body.basedOnSnapshotId, growth=body.growth, exit_pe=body.exitPE,
                payout=body.payout, expected_override_id=body.expectedOverrideId)}
        except PriceStoreError as error:
            raise _error(error) from None
        except (OSError, sqlite3.Error):
            raise _unavailable() from None

    return router
