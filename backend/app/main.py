"""FastAPI app entrypoint: wires the market data source/cache into the app lifespan."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.stream import router as stream_router
from .dependencies import market_source, price_cache

# Default watchlist seed (see planning/PLAN.md section 7). Primes the cache until
# the database-backed watchlist/positions are wired in.
DEFAULT_WATCHLIST = [
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    price_cache.ensure_tracked(DEFAULT_WATCHLIST)
    await market_source.start(price_cache)
    yield
    await market_source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(stream_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
