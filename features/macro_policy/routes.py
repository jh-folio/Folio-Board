import sqlite3

from fastapi import APIRouter, Body, HTTPException
from .service import PolicyStore, preview


def create_policy_router(data_root):
    router = APIRouter(prefix='/api/macro/policies', tags=['macro'])
    store = PolicyStore(data_root)

    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, detail=str(exc)) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, detail='policy_temporarily_unavailable') from None

    @router.get('')
    def events():
        return {'items': call(store.list)}

    @router.post('/preview')
    def draft(body: dict = Body(...)):
        return call(store.preview, body)

    @router.get('/targets/{ticker}')
    def company_targets(ticker: str):
        from .links import targets
        return call(targets, data_root, ticker)

    @router.post('/confirm')
    def confirm(body: dict = Body(...)):
        if set(body) != {'draft', 'previewId', 'userConfirmed', 'officialSourceConfirmed'}:
            raise HTTPException(400, detail='policy_invalid_confirmation')
        return call(store.confirm, body['draft'], preview_id=body['previewId'],
                    user_confirmed=body['userConfirmed'], official_source_confirmed=body['officialSourceConfirmed'])

    return router
