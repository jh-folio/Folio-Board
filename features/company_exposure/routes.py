import sqlite3
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from .service import read, refresh, ticker_value


def create_exposure_router(data_root):
    router = APIRouter(prefix='/api/macro/exposures', tags=['macro'])
    active = {}
    lock = threading.Lock()

    @router.get('/{ticker}')
    def exposure(ticker: str):
        try:
            return read(data_root, ticker)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from None
        except (OSError, sqlite3.Error):
            raise HTTPException(503, detail='exposure_temporarily_unavailable') from None

    @router.post('/{ticker}/refresh')
    def update(ticker: str):
        from features.common.jobs import get_job, submit_job
        try:
            ticker = ticker_value(ticker)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from None
        with lock:
            current = get_job(active[ticker]) if ticker in active else None
            if current and current.get('status') in {'queued', 'running', 'cancel_requested', 'committing'}:
                return current
            job = submit_job('macro_exposure', '공시 노출 확인', refresh, Path(data_root), ticker,
                             pass_job_id=True, dedicated_thread=True)
            active[ticker] = job['id']
            return job

    return router
