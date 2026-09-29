import sqlite3
from fastapi import APIRouter, HTTPException
from .service import summary, history


def create_state_router(data_root):
    router = APIRouter(prefix='/api/macro/state', tags=['macro'])

    @router.get('/history')
    def records():
        try:
            return history(data_root)
        except (OSError, sqlite3.Error):
            raise HTTPException(503, detail='macro_history_temporarily_unavailable') from None

    @router.get('')
    def current(market: str = 'US', date: str | None = None):
        try:
            return summary(data_root, market=market, date=date)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, detail='macro_state_temporarily_unavailable') from None

    return router
