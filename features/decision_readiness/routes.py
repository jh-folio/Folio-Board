"""HTTP validation only. Quotes require an explicit basis request; all other actions read or calculate."""
import sqlite3
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictStr, StrictInt

from . import DecisionError
from .inputs import LATEST
from .service import comparison, readiness
from .portfolio_fit import BasisCache, capture_basis, preview


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Candidate(Strict):
    instrumentId: StrictStr
    snapshotId: StrictStr | None = None


class Comparison(Strict):
    candidates: list[Candidate]
    criteriaRevisionId: StrictInt | None = None
    attributionYears: StrictInt = 5
    evaluatedAt: StrictStr | None = None
    referenceSet: dict[str, Any] | None = None
    portfolioBasisId: StrictStr | None = None


class Basis(Strict):
    instrumentId: StrictStr


class Preview(Basis):
    basisId: StrictStr
    candidateWeightPercent: StrictStr


def create_decision_router(data_root):
    router = APIRouter(tags=["decision-readiness"])
    cache = BasisCache()

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DecisionError as error:
            raise HTTPException(error.status, detail={"code": error.code}) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, detail={"code": "decision_store_unavailable"}) from None
        except (ValueError, KeyError, TypeError, ArithmeticError):
            raise HTTPException(503, detail={"code": "decision_source_invalid"}) from None

    @router.get("/api/decision-readiness/{instrument_id}")
    def read(instrument_id: str, snapshotId: str | None = None, criteriaRevisionId: int | None = None):
        return call(readiness, data_root, instrument_id, snapshot_id=snapshotId or LATEST, criteria_revision=criteriaRevisionId if criteriaRevisionId is not None else LATEST)

    @router.post("/api/opportunity-comparison")
    def compare(body: Comparison):
        basis_id = body.portfolioBasisId
        if basis_id is None and body.referenceSet is not None:
            basis_id = body.referenceSet.get("portfolioBasisId")
        if basis_id is not None and not isinstance(basis_id, str):
            raise HTTPException(422, detail={"code": "invalid_reference_set"})
        captured = call(cache.get, data_root, basis_id) if basis_id else None
        return call(comparison, data_root, [item.model_dump(exclude_unset=True) for item in body.candidates],
                    criteria_revision=body.criteriaRevisionId if "criteriaRevisionId" in body.model_fields_set else LATEST,
                    at=body.evaluatedAt, reference_set=body.referenceSet, attribution_years=body.attributionYears,
                    portfolio_basis=captured, portfolio_basis_id=basis_id)

    @router.post("/api/portfolio/decision-preview/basis")
    def basis(body: Basis):
        captured = call(capture_basis, data_root, body.instrumentId)
        return cache.put(data_root, captured)

    @router.post("/api/portfolio/decision-preview")
    def weight(body: Preview):
        captured = call(cache.get, data_root, body.basisId)
        return call(preview, captured, body.instrumentId, body.candidateWeightPercent)

    return router
