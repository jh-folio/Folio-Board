from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .chart_service import get_chart
from .fundamentals_service import get_fundamentals
from .earnings_service import get_earnings
from .toss_realtime_hub import TossRealtimeHub


def create_market_data_router(data_dir: Path, *, realtime_hub: TossRealtimeHub | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/market", tags=["market-data"])

    @router.get("/chart")
    def chart(symbol: str, range: str = "3m", interval: str = "1d"):  # noqa: A002 - public API contract
        try:
            return get_chart(data_dir, symbol=symbol, range_key=range, interval=interval)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.websocket("/realtime/chart")
    async def realtime_chart(websocket: WebSocket) -> None:
        """Credential-free one-symbol display stream.

        Contract: connect as ``/api/market/realtime/chart?symbol=005930.KS``
        (or one visible US stock). The client does not send subscription frames;
        it closes the socket to unsubscribe. This keeps an untrusted browser
        from selecting provider topics or receiving authentication material.
        """
        await websocket.accept()
        if realtime_hub is None:
            await websocket.send_json({"schemaVersion": 1, "type": "status", "status": "unavailable", "provider": "toss_open_api", "symbol": "", "market": "", "asOf": "", "price": None, "currency": "", "code": "provider_error"})
            await websocket.close()
            return
        subscription = await realtime_hub.subscribe(websocket.query_params.get("symbol", ""))
        queue_task: asyncio.Task[dict] | None = None
        receive_task: asyncio.Task[dict] | None = None
        try:
            while True:
                queue_task = asyncio.create_task(subscription.queue.get())
                receive_task = asyncio.create_task(websocket.receive())
                done, pending = await asyncio.wait({queue_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                for task in pending:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                if queue_task in done:
                    await websocket.send_json(queue_task.result())
                if receive_task in done:
                    message = receive_task.result()
                    if message.get("type") == "websocket.disconnect":
                        return
        except WebSocketDisconnect:
            return
        finally:
            if queue_task is not None:
                queue_task.cancel()
            if receive_task is not None:
                receive_task.cancel()
            await realtime_hub.unsubscribe(subscription.id)

    @router.get("/earnings")
    def earnings(ticker: str):
        """한 종목의 실적 패널. **상세를 열 때만** 부른다(티커당 provider 호출)."""
        try:
            return get_earnings(data_dir, ticker=ticker)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/fundamentals")
    def fundamentals(symbol: str):
        try:
            return get_fundamentals(data_dir, symbol=symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
