"""Thin Portfolio API router."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query

from .service import (
    PortfolioRevisionConflict,
    PortfolioValidationError,
    PresetRevisionConflict,
    delete_portfolio_backtest,
    delete_portfolio_preset,
    get_portfolio,
    get_portfolio_backtest,
    list_portfolio_backtests,
    list_portfolio_presets,
    portfolio_analytics,
    portfolio_summary,
    preset_from_current_portfolio,
    resolve_portfolio_ticker,
    run_portfolio_backtest,
    run_portfolio_backtest_comparison,
    save_portfolio,
    save_portfolio_backtest_result,
    save_portfolio_preset,
    search_portfolio_tickers,
)
from .toss_import import TossHoldingsImport, TossImportError


def create_portfolio_router(data_dir: Path, toss_import: TossHoldingsImport | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
    imports = toss_import or TossHoldingsImport(data_dir)

    def toss_error(exc: TossImportError):
        detail = {"code": exc.code}
        if exc.latest is not None:
            detail["latest"] = exc.latest
        if exc.metadata_status:
            detail["metadataStatus"] = exc.metadata_status
        raise HTTPException(status_code=exc.status, detail=detail) from exc

    @router.get("")
    def read_portfolio():
        return imports.recover_portfolio()

    @router.post("")
    def write_portfolio(body: dict | None = Body(default=None)):
        try:
            return save_portfolio(body or {}, data_dir=data_dir)
        except PortfolioValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": "portfolio_validation_failed", "errors": exc.errors}) from exc
        except PortfolioRevisionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "portfolio_revision_conflict", "latest": exc.latest}) from exc

    @router.get("/toss/accounts")
    def toss_accounts():
        try:
            return imports.accounts()
        except TossImportError as exc:
            toss_error(exc)

    @router.post("/toss/preview")
    def toss_preview(body: dict | None = Body(default=None)):
        try:
            return imports.preview((body or {}).get("selectionId"))
        except TossImportError as exc:
            toss_error(exc)

    @router.post("/toss/confirm")
    def toss_confirm(body: dict | None = Body(default=None)):
        payload = body or {}
        try:
            return imports.confirm(payload.get("previewId"), payload.get("expectedRevision"))
        except TossImportError as exc:
            toss_error(exc)

    @router.get("/summary")
    def summary():
        return portfolio_summary()

    @router.get("/resolve")
    def resolve(ticker: str = "", market: str = ""):
        return resolve_portfolio_ticker(ticker, market)

    @router.get("/suggest")
    def suggest(q: str = "", limit: int = Query(default=8, ge=1, le=30)):
        return search_portfolio_tickers(q, limit)

    @router.get("/analytics")
    def analytics(presetId: str = ""):  # noqa: N803 - 쿼리 파라미터는 화면과 같은 표기를 쓴다
        return portfolio_analytics(presetId)

    @router.get("/presets")
    def presets():
        return list_portfolio_presets()

    @router.post("/presets")
    def save_preset(body: dict | None = Body(default=None)):
        try:
            return save_portfolio_preset(body or {})
        except PortfolioValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": "preset_validation_failed", "errors": exc.errors}) from exc
        except PresetRevisionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "preset_revision_conflict", "latest": exc.latest}) from exc

    @router.post("/presets/from-current")
    def preset_from_current(body: dict | None = Body(default=None)):
        return preset_from_current_portfolio((body or {}).get("name") or "현재 포트폴리오 목표 비중")

    @router.delete("/presets/{preset_id}")
    def delete_preset(preset_id: str, body: dict | None = Body(default=None)):
        try:
            return delete_portfolio_preset(preset_id, body or {})
        except PresetRevisionConflict as exc:
            raise HTTPException(status_code=409, detail={"code": "preset_revision_conflict", "latest": exc.latest}) from exc

    @router.get("/backtests")
    def backtests():
        return list_portfolio_backtests()

    @router.post("/backtests")
    def run_backtest(body: dict | None = Body(default=None)):
        return run_portfolio_backtest(body or {}, save_result=False)

    @router.post("/backtests/compare")
    def compare_backtests(body: dict | None = Body(default=None)):
        return run_portfolio_backtest_comparison(body or {})

    @router.post("/backtests/save")
    def save_backtest(body: dict | None = Body(default=None)):
        return save_portfolio_backtest_result(body or {})

    @router.get("/backtests/{backtest_id}")
    def read_backtest(backtest_id: str):
        result = get_portfolio_backtest(backtest_id)
        if not result:
            raise HTTPException(status_code=404, detail="Portfolio backtest not found")
        return result

    @router.delete("/backtests/{backtest_id}")
    def delete_backtest(backtest_id: str):
        result = delete_portfolio_backtest(backtest_id)
        if not result.get("deleted"):
            raise HTTPException(status_code=404, detail="Portfolio backtest not found")
        return result

    return router
