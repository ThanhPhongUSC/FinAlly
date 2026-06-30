"""Massive (Polygon.io) REST API client — polling, not WebSocket.

Polls the snapshot endpoint for the union of all tickers currently in the price
cache, on a configurable interval, and writes results into the shared cache.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .base import MarketDataSource
from .cache import PriceCache

logger = logging.getLogger(__name__)

MASSIVE_BASE_URL = "https://api.polygon.io"
POLL_INTERVAL = 15.0  # seconds; free tier allows 5 requests/min
TICKER_BATCH_SIZE = 50  # snapshot endpoint accepts a comma-separated list
REQUEST_TIMEOUT = 10.0


class MassiveClient(MarketDataSource):
    """Polls Polygon.io's REST snapshot endpoint for ticker prices."""

    def __init__(self, api_key: str, poll_interval: float = POLL_INTERVAL) -> None:
        self._api_key = api_key
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._cache: PriceCache | None = None
        self._http: httpx.AsyncClient | None = None

    # -------------------------------------------------------------- interface

    def validate_ticker(self, ticker: str) -> bool:
        """Syntactic check only; real existence is confirmed via `ticker_exists`."""
        return bool(ticker) and 1 <= len(ticker) <= 5 and ticker.isalpha() and ticker.isupper()

    async def start(self, cache: PriceCache) -> None:
        self._cache = cache
        self._http = httpx.AsyncClient(
            base_url=MASSIVE_BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=REQUEST_TIMEOUT,
        )
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._http:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------ public

    async def ticker_exists(self, ticker: str) -> bool:
        """Probe Massive for a single ticker, used to validate watchlist additions."""
        if self._http is None:
            raise RuntimeError("MassiveClient.start() must be called before ticker_exists()")
        try:
            resp = await self._http.get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
        except (httpx.HTTPError, httpx.TimeoutException):
            return False
        if resp.status_code != 200:
            return False
        data = resp.json()
        return bool(data.get("ticker"))

    # ------------------------------------------------------------ internal loop

    async def _run(self) -> None:
        while self._running:
            tickers = self._cache.get_tickers() if self._cache else []
            if tickers:
                for i in range(0, len(tickers), TICKER_BATCH_SIZE):
                    batch = tickers[i : i + TICKER_BATCH_SIZE]
                    await self._poll_batch(batch)
            await asyncio.sleep(self._poll_interval)

    async def _poll_batch(self, tickers: list[str]) -> None:
        assert self._http is not None
        assert self._cache is not None
        ticker_param = ",".join(tickers)
        try:
            resp = await self._http.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ticker_param},
            )
            resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            # Log and continue — the cache retains the last known price.
            logger.warning("MassiveClient poll error: %s", exc)
            return

        data = resp.json()
        for item in data.get("tickers") or []:
            symbol = item.get("ticker")
            day = item.get("day") or {}
            price = day.get("c")  # current/closing price for the day
            if symbol and price is not None:
                self._cache.update(symbol, float(price))
