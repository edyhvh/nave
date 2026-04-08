from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from trading.services import COTService

router = APIRouter()
service = COTService()


@router.get("/cot/latest")
async def cot_latest(
    coins: str = "BTC ETH",
    report_type: str = "futures_and_options",
    include_micro: bool = False,
    include_price_context: bool = True,
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            service.get_latest_summary,
            coins=coins,
            report_type=report_type,
            include_micro=include_micro,
            include_price_context=include_price_context,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cot/history/{months}")
async def cot_history(
    months: int,
    coins: str = "BTC ETH",
    report_type: str = "futures_and_options",
    include_micro: bool = False,
) -> dict[str, Any]:
    if not (1 <= months <= 12):
        raise HTTPException(status_code=400, detail="months must be between 1 and 12")
    try:
        return await run_in_threadpool(
            service.get_historical_variation,
            months=months,
            coins=coins,
            report_type=report_type,
            include_micro=include_micro,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cot/weekly-plan")
async def cot_weekly_plan(
    coins: str = "BTC ETH",
    capital_usd: float = 2000.0,
    leverage: float = 10.0,
    wallet: str = "hermes",
    testnet: bool = True,
    include_micro: bool = False,
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            service.get_weekly_plan,
            coins=coins,
            capital_usd=capital_usd,
            leverage=leverage,
            wallet=wallet,
            testnet=testnet,
            include_micro=include_micro,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
