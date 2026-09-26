from pathlib import Path
import sqlite3

from fastapi import APIRouter,Body,HTTPException,Query
from .service import map_snapshot
from .operations import current_job,save_settings,settings,submit_refresh


def create_macro_router(data_root:Path):
    router=APIRouter(prefix='/api/macro',tags=['macro'])

    def call(fn,*args,**kwargs):
        try:return fn(*args,**kwargs)
        except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from None
        except (OSError,RuntimeError,sqlite3.Error):raise HTTPException(status_code=503,detail='macro_temporarily_unavailable') from None

    @router.get('')
    def snapshot(market:str='US',mode:str='latest_revised',date:str|None=None,series:str|None=None,period:str|None=None,years:int=Query(5,ge=1,le=50)):
        return call(map_snapshot,data_root,market=market,mode=mode,date=date,series_id=series,period=period,years=years)

    @router.get('/settings')
    def configuration():return call(settings,data_root)

    @router.post('/settings')
    def configure(body:dict=Body(...)):return call(save_settings,data_root,body)

    @router.post('/refresh')
    def refresh():return call(submit_refresh,data_root)

    @router.get('/refresh')
    def refresh_status():return {'job':call(current_job,data_root)}

    return router
