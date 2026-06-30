"""Built-in market data simulator using Geometric Brownian Motion (GBM).

S(t+dt) = S(t) * exp((mu - sigma^2 / 2) * dt + sigma * sqrt(dt) * Z),  Z ~ N(0, 1)

Runs continuously regardless of real-world market hours so the demo always shows
movement, with correlated moves across tech tickers and occasional event shocks.
"""

from __future__ import annotations

import asyncio
import math
import random

from .base import MarketDataSource
from .cache import PriceCache

# Realistic seed prices for the default watchlist.
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 415.0,
    "AMZN": 185.0,
    "TSLA": 250.0,
    "NVDA": 875.0,
    "META": 515.0,
    "JPM": 200.0,
    "V": 275.0,
    "NFLX": 630.0,
}

# Per-ticker annualised volatility (sigma). Higher = more dramatic moves.
VOLATILITY: dict[str, float] = {
    "AAPL": 0.25,
    "GOOGL": 0.28,
    "MSFT": 0.24,
    "AMZN": 0.30,
    "TSLA": 0.65,
    "NVDA": 0.60,
    "META": 0.40,
    "JPM": 0.22,
    "V": 0.20,
    "NFLX": 0.38,
}
DEFAULT_VOLATILITY = 0.30
DEFAULT_DRIFT = 0.05  # annualised drift (mu)
TICK_INTERVAL = 0.5  # seconds between ticks
RANDOM_EVENT_PROB = 0.002  # probability per tick of a sudden 2-5% move
SEED_PRICE_MIN = 20.0
SEED_PRICE_MAX = 500.0

# Correlation structure: tech stocks move together via a shared market factor.
TECH = {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"}
MARKET_FACTOR_WEIGHT = 0.4  # fraction of a tech ticker's return driven by the common factor

# Trading-year seconds, used to convert a wall-clock tick interval into a GBM dt.
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600


def seed_price(ticker: str) -> float:
    """Realistic starting price: looked up for known tickers, random otherwise."""
    return SEED_PRICES.get(ticker, random.uniform(SEED_PRICE_MIN, SEED_PRICE_MAX))


def sigma_for(ticker: str) -> float:
    return VOLATILITY.get(ticker, DEFAULT_VOLATILITY)


def gbm_step(price: float, sigma: float, dt: float, z: float, drift: float = DEFAULT_DRIFT) -> float:
    """One GBM step. `z` is a standard normal random draw."""
    return price * math.exp((drift - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z)


class GBMSimulator(MarketDataSource):
    """Generates correlated, log-normally distributed price paths in-process."""

    def __init__(self, tick_interval: float = TICK_INTERVAL) -> None:
        self._tick_interval = tick_interval
        self._task: asyncio.Task | None = None
        self._running = False
        self._cache: PriceCache | None = None
        self._current_prices: dict[str, float] = {}

    # -------------------------------------------------------------- interface

    def validate_ticker(self, ticker: str) -> bool:
        """Accept any 1-5 character uppercase A-Z symbol."""
        return bool(ticker) and 1 <= len(ticker) <= 5 and ticker.isalpha() and ticker.isupper()

    async def start(self, cache: PriceCache) -> None:
        self._cache = cache
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

    # ------------------------------------------------------------ internal loop

    async def _run(self) -> None:
        assert self._cache is not None
        dt = self._tick_interval / TRADING_SECONDS_PER_YEAR

        while self._running:
            self._tick(dt)
            await asyncio.sleep(self._tick_interval)

    def _tick(self, dt: float) -> None:
        assert self._cache is not None
        tickers = self._cache.get_tickers()

        # Seed prices for any ticker not yet tracked by this simulator instance.
        for t in tickers:
            if t not in self._current_prices:
                existing = self._cache.get(t)
                if existing and existing.price > 0:
                    self._current_prices[t] = existing.price
                else:
                    self._current_prices[t] = seed_price(t)

        # Shared market factor drives correlated moves across tech tickers.
        market_z = random.gauss(0, 1)

        for t in tickers:
            price = self._current_prices[t]
            sigma = sigma_for(t)

            idio_z = random.gauss(0, 1)
            if t in TECH:
                z = MARKET_FACTOR_WEIGHT * market_z + math.sqrt(1 - MARKET_FACTOR_WEIGHT**2) * idio_z
            else:
                z = idio_z

            new_price = gbm_step(price, sigma, dt, z)

            # Occasional random event: a sudden 2-5% move, for drama.
            if random.random() < RANDOM_EVENT_PROB:
                shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
                new_price *= 1 + shock

            new_price = max(new_price, 0.01)
            self._current_prices[t] = new_price
            self._cache.update(t, new_price)
