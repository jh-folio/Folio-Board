from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from .chart_service import get_chart
from .fundamentals_service import get_fundamentals
from .earnings_service import get_earnings


def create_market_data_router(data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api/market", tags=["market-data"])

    @router.get("/chart")
    def chart(symbol: str, range: str = "3m", interval: str = "1d"):  # noqa: A002 - public API contract
        try:
            return get_chart(data_dir, symbol=symbol, range_key=range, interval=interval)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
