from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.models.indicator import IndicatorResponse
from app.services import aaii, cbdc, onchain, openbb, tariff
from app.services.cache import CacheService, get_cache

router = APIRouter()


def _is_cache_fresh(as_of: datetime, ttl_seconds: int) -> bool:
    age_seconds = (datetime.now(timezone.utc) -
                   as_of.astimezone(timezone.utc)).total_seconds()
    return age_seconds <= ttl_seconds


async def _fetch_with_cache(
    cache: CacheService,
    name: str,
    ttl_seconds: int,
    fetcher: Callable[[], Awaitable[dict[str, Any]]],
) -> IndicatorResponse:
    cached = await cache.get(name)
    if cached and _is_cache_fresh(cached["as_of"], ttl_seconds):
        return IndicatorResponse(
            name=name,
            as_of=cached["as_of"],
            source=name,
            data=cached["payload"],
            cached=True,
        )

    payload = await fetcher()
    as_of = datetime.now(timezone.utc)
    await cache.set(name, as_of, payload)

    return IndicatorResponse(
        name=name,
        as_of=as_of,
        source=name,
        data=payload,
        cached=False,
    )


@router.get("/aaii", response_model=IndicatorResponse)
async def get_aaii() -> IndicatorResponse:
    cache = get_cache()

    async def fetcher() -> dict[str, Any]:
        return await run_in_threadpool(aaii.fetch_aaii_sentiment)

    return await _fetch_with_cache(cache, "aaii", 60 * 60 * 12, fetcher)


@router.get("/cbdc", response_model=IndicatorResponse)
async def get_cbdc() -> IndicatorResponse:
    cache = get_cache()

    async def fetcher() -> dict[str, Any]:
        return await run_in_threadpool(cbdc.fetch_cbdc_data)

    return await _fetch_with_cache(cache, "cbdc", 60 * 60 * 24, fetcher)


@router.get("/tariff", response_model=IndicatorResponse)
async def get_tariff() -> IndicatorResponse:
    cache = get_cache()

    async def fetcher() -> dict[str, Any]:
        return await run_in_threadpool(tariff.fetch_tariff_revenue)

    return await _fetch_with_cache(cache, "tariff", 60 * 60 * 24, fetcher)


@router.get("/onchain/{coin_id}", response_model=IndicatorResponse)
async def get_onchain(coin_id: str) -> IndicatorResponse:
    cache = get_cache()
    name = f"onchain:{coin_id}"

    async def fetcher() -> dict[str, Any]:
        return await run_in_threadpool(onchain.fetch_onchain_metrics, coin_id)

    return await _fetch_with_cache(cache, name, 60 * 60 * 12, fetcher)


@router.get("/openbb/fred/{series_id}", response_model=IndicatorResponse)
async def get_fred_series(series_id: str) -> IndicatorResponse:
    cache = get_cache()
    name = f"fred:{series_id}"

    async def fetcher() -> dict[str, Any]:
        return await run_in_threadpool(openbb.fetch_fred_series, series_id)

    return await _fetch_with_cache(cache, name, 60 * 60 * 24, fetcher)


@router.get("/openbb/fixedincome/{symbol}", response_model=IndicatorResponse)
async def get_fixedincome_rate(symbol: str) -> IndicatorResponse:
    cache = get_cache()
    name = f"fixedincome:{symbol}"

    async def fetcher() -> dict[str, Any]:
        return await run_in_threadpool(openbb.fetch_fixedincome_rate, symbol)

    return await _fetch_with_cache(cache, name, 60 * 60 * 6, fetcher)


@router.get("/openbb/indicator/{slug}", response_model=IndicatorResponse)
async def get_openbb_indicator(slug: str) -> IndicatorResponse:
    cache = get_cache()
    name = f"openbb:{slug}"

    async def fetcher() -> dict[str, Any]:
        try:
            return await run_in_threadpool(openbb.fetch_openbb_indicator, slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return await _fetch_with_cache(cache, name, 60 * 60 * 24, fetcher)
