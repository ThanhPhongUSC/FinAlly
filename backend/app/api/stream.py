"""FastAPI router for `GET /api/stream/prices`."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..dependencies import get_price_cache
from ..market.cache import PriceCache
from ..market.stream import price_event_generator

router = APIRouter()


@router.get("/api/stream/prices")
async def stream_prices(cache: PriceCache = Depends(get_price_cache)) -> StreamingResponse:
    return StreamingResponse(
        price_event_generator(cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if present
            "Connection": "keep-alive",
        },
    )
