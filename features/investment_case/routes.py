"""Thin HTTP boundary for exact, explicit personal-record actions."""
import sqlite3

from fastapi import APIRouter, Body, HTTPException
from features.agent_mode.report_delete import DeleteRecoveryRequiredError

from . import CaseError
from . import service, deletion


def call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except CaseError as error:
        raise HTTPException(error.status, detail={"code": error.code, **error.details}) from None
    except DeleteRecoveryRequiredError:
        raise HTTPException(409, detail={"code": "recovery_requires_confirmation"}) from None
    except (OSError, sqlite3.Error):
        raise HTTPException(503, detail={"code": "case_store_unavailable"}) from None
    except (ValueError, KeyError, TypeError, ArithmeticError):
        raise HTTPException(503, detail={"code": "case_source_invalid"}) from None


def create_case_router(data_root):
    router = APIRouter(tags=["investment-case"])

    @router.get("/api/investment-cases/operations/{operation_id}")
    def operation(operation_id: str):
        return call(service.get_operation, data_root, operation_id)

    @router.post("/api/investment-cases/operations/{operation_id}/recover")
    def recover(operation_id: str):
        return call(service.recover, data_root, operation_id)

    @router.post("/api/investment-cases/operations/{operation_id}/cancel")
    def cancel(operation_id: str, body: dict = Body(default={})):
        if set(body) - {"confirmed"} or type(body.get("confirmed", False)) is not bool:
            raise HTTPException(400, detail={"code": "invalid_confirmation"})
        return call(service.cancel, data_root, operation_id, confirmed=body.get("confirmed", False))

    @router.get("/api/investment-cases/{instrument_id}")
    def read(instrument_id: str):
        return call(service.read_case, data_root, instrument_id)

    @router.get("/api/decision-journals/{journal_id}")
    def journal(journal_id: str):
        return call(service.read_journal, data_root, journal_id)

    @router.post("/api/investment-cases/preview")
    def preview(body: dict = Body(...)):
        return call(service.preview, data_root, body)

    @router.post("/api/investment-cases/confirm")
    def confirm(body: dict = Body(...)):
        if set(body) != {"token", "operationId"}:
            raise HTTPException(400, detail={"code": "invalid_confirmation"})
        return call(service.confirm, data_root, body["token"], body["operationId"])

    @router.post("/api/decision-journals/{journal_id}/purge-preview")
    def purge_preview(journal_id: str, body: dict = Body(...)):
        saved = call(service.read_journal, data_root, journal_id, current=False)["journal"]
        return call(service.preview, data_root, {**body, "instrumentId": saved["instrumentId"], "action": "purge", "targetJournalId": journal_id})

    @router.post("/api/investment-cases/source-delete-preview")
    def source_delete(body: dict = Body(...)):
        return call(deletion.source_delete_preview, data_root, body)

    return router
