# Market Data Backend Design

## Overview

The market data subsystem is the real-time engine behind FinAlly. It provides a unified interface over two sources — a built-in GBM simulator and the Massive (Polygon.io) REST API — and feeds a shared in-memory price cache that SSE streams read from.

---

## 1. Directory Layout

```
backend/
├── app/
│   ├── market/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract interface + shared types
│   │   ├── cache.py         # In-memory price cache
│   │   ├── simulator.py     # GBM simulator implementation
│   │   ├── massive.py       # Massive (Polygon.io) REST client
│   │   ├── factory.py       # Selects implementation from env vars
│   │   └── stream.py        # SSE endpoint logic
│   ├── api/
│   │   └── stream.py        # FastAPI router for /api/stream/prices
│   └── main.py
```

---

## 2. Shared Types

```python
# backend/app/market/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class TickerPrice:
    ticker: str
    price: float
    prev_price: float          # price on the previous tick
    session_open: float        # first observed price this session
    timestamp: float           # Unix epoch seconds (float)

    @property
    def change_pct(self) -> float:
        if self.session_open == 0:
            return 0.0
        return (self.price - self.session_open) / self.session_open * 100

    @property
    def direction(self) -> str:
        if self.price > self.prev_price:
            return "up"
        if self.price < self.prev_price:
            return "down"
        return "flat"

    def to_sse_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": round(self.price, 2),
            "prev_price": round(self.prev_price, 2),
            "session_open": round(self.session_open, 2),
            "change_pct": round(self.change_pct, 4),
            "direction": self.direction,
            "timestamp": self.timestamp,
        }


class MarketDataSource(ABC):
    """All market data implementations must satisfy this interface."""

    @abstractmethod
    async def start(self, cache: "PriceCache") -> None:
        """Begin producing prices into the cache. Called once on app startup."""

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown."""

    @abstractmethod
    def validate_ticker(self, ticker: str) -> bool:
        """Return True if the ticker is acceptable for this source."""
```

---

## 3. Price Cache

The cache is the single source of truth for all live prices. It is updated only by the active `MarketDataSource` and read by the SSE stream and portfolio P&L calculations.

```python
# backend/app/market/cache.py
import time
from threading import Lock
from typing import Optional
from .base import TickerPrice


class PriceCache:
    """Thread-safe in-memory price cache."""

    def __init__(self) -> None:
        self._lock = Lock()
        # ticker -> TickerPrice
        self._data: dict[str, TickerPrice] = {}

    # ------------------------------------------------------------------ writes

    def update(self, ticker: str, new_price: float) -> TickerPrice:
        with self._lock:
            existing = self._data.get(ticker)
            session_open = existing.session_open if existing else new_price
            prev_price = existing.price if existing else new_price
            tp = TickerPrice(
                ticker=ticker,
                price=new_price,
                prev_price=prev_price,
                session_open=session_open,
                timestamp=time.time(),
            )
            self._data[ticker] = tp
            return tp

    def ensure_tracked(self, tickers: list[str]) -> None:
        """Add tickers to the cache with no price yet (price=0 sentinel)."""
        with self._lock:
            for t in tickers:
                if t not in self._data:
                    self._data[t] = TickerPrice(
                        ticker=t, price=0.0, prev_price=0.0,
                        session_open=0.0, timestamp=time.time(),
                    )

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._data.pop(ticker, None)

    # ------------------------------------------------------------------ reads

    def get(self, ticker: str) -> Optional[TickerPrice]:
        with self._lock:
            return self._data.get(ticker)

    def get_all(self) -> dict[str, TickerPrice]:
        with self._lock:
            return dict(self._data)

    def get_tickers(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def price(self, ticker: str) -> Optional[float]:
        tp = self.get(ticker)
        return tp.price if tp else None
```

**Cache lifecycle rules**:
- A ticker enters the cache when it is added to the watchlist OR when a position exists.
- A ticker is removed from the cache only when it leaves both the watchlist and the positions table.
- The background task (`MarketDataSource`) drives all price writes. No API handler ever writes directly to the cache.

---

## 4. GBM Simulator

Uses Geometric Brownian Motion:

```
S(t+dt) = S(t) * exp((μ - σ²/2)*dt + σ*sqrt(dt)*Z)
```

where `Z ~ N(0,1)`, `μ` is drift, and `σ` is volatility. This produces realistic log-normally distributed price paths.

### 4.1 Seed Prices & Correlation

```python
# backend/app/market/simulator.py
import asyncio
import math
import random
import time
from typing import Optional
from .base import MarketDataSource, TickerPrice
from .cache import PriceCache


# Realistic seed prices for the default watchlist
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

# Per-ticker annualised volatility (σ). Higher = more dramatic moves.
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
DEFAULT_DRIFT = 0.05          # annualised drift (μ)
TICK_INTERVAL = 0.5           # seconds between ticks
RANDOM_EVENT_PROB = 0.002     # probability per tick of a sudden 2-5% move

# Correlation structure: tech stocks move together
TECH = {"AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"}
MARKET_FACTOR_WEIGHT = 0.4    # fraction of each return driven by a common factor


def _seed_price(ticker: str) -> float:
    return SEED_PRICES.get(ticker, random.uniform(20.0, 500.0))


def _sigma(ticker: str) -> float:
    return VOLATILITY.get(ticker, DEFAULT_VOLATILITY)


def _gbm_step(price: float, sigma: float, dt: float, z: float, drift: float = DEFAULT_DRIFT) -> float:
    """One GBM step. z is a standard normal random draw."""
    return price * math.exp((drift - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z)


class GBMSimulator(MarketDataSource):

    def __init__(self, tick_interval: float = TICK_INTERVAL) -> None:
        self._tick_interval = tick_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
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

    # ------------------------------------------------------------ internal loop

    async def _run(self) -> None:
        dt = self._tick_interval / (252 * 6.5 * 3600)  # fraction of trading year

        while self._running:
            tickers = self._cache.get_tickers()

            # Initialise prices for any ticker not yet seeded
            for t in tickers:
                if t not in self._current_prices:
                    existing = self._cache.get(t)
                    if existing and existing.price > 0:
                        self._current_prices[t] = existing.price
                    else:
                        self._current_prices[t] = _seed_price(t)

            # Generate a shared market factor (tech correlation)
            market_z = random.gauss(0, 1)

            for t in tickers:
                price = self._current_prices[t]
                sigma = _sigma(t)

                # Idiosyncratic component
                idio_z = random.gauss(0, 1)

                # Blend market factor for tech tickers
                if t in TECH:
                    z = MARKET_FACTOR_WEIGHT * market_z + math.sqrt(1 - MARKET_FACTOR_WEIGHT**2) * idio_z
                else:
                    z = idio_z

                new_price = _gbm_step(price, sigma, dt, z)

                # Occasional random event: sudden 2-5% move
                if random.random() < RANDOM_EVENT_PROB:
                    shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
                    new_price *= (1 + shock)

                new_price = max(new_price, 0.01)
                self._current_prices[t] = new_price
                self._cache.update(t, new_price)

            await asyncio.sleep(self._tick_interval)
```

### 4.2 Simulator Usage Example

```python
from app.market.simulator import GBMSimulator
from app.market.cache import PriceCache

cache = PriceCache()
cache.ensure_tracked(["AAPL", "TSLA"])

sim = GBMSimulator(tick_interval=0.5)
await sim.start(cache)

# After 1 second:
print(cache.get("AAPL").to_sse_dict())
# {
#   "ticker": "AAPL",
#   "price": 190.23,
#   "prev_price": 190.0,
#   "session_open": 190.0,
#   "change_pct": 0.121,
#   "direction": "up",
#   "timestamp": 1751310000.5
# }
```

---

## 5. Massive API Client

Uses Polygon.io's REST snapshot endpoint. No WebSocket dependency — simpler and works on all tiers.

### 5.1 Polling Architecture

```
┌──────────────────────────────────────────────────────┐
│  MassiveClient._run() background task                │
│                                                      │
│  every POLL_INTERVAL seconds:                        │
│    tickers = cache.get_tickers()                     │
│    response = GET /v2/snapshot/locale/us/...         │
│    for each ticker in response:                      │
│        if price changed → cache.update(ticker, p)   │
└──────────────────────────────────────────────────────┘
```

```python
# backend/app/market/massive.py
import asyncio
import os
import time
from typing import Optional
import httpx
from .base import MarketDataSource
from .cache import PriceCache


MASSIVE_BASE_URL = "https://api.polygon.io"
POLL_INTERVAL = 15.0    # seconds; free tier: 5 req/min
TICKER_BATCH_SIZE = 50  # snapshot endpoint accepts comma-separated list


class MassiveClient(MarketDataSource):

    def __init__(self, api_key: str, poll_interval: float = POLL_INTERVAL) -> None:
        self._api_key = api_key
        self._poll_interval = poll_interval
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._http: Optional[httpx.AsyncClient] = None

    def validate_ticker(self, ticker: str) -> bool:
        """Accept 1-5 uppercase alpha chars; real validation happens on first poll."""
        return bool(ticker) and 1 <= len(ticker) <= 5 and ticker.isalpha() and ticker.isupper()

    async def start(self, cache: PriceCache) -> None:
        self._cache = cache
        self._http = httpx.AsyncClient(
            base_url=MASSIVE_BASE_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=10.0,
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
        if self._http:
            await self._http.aclose()

    async def _run(self) -> None:
        while self._running:
            tickers = self._cache.get_tickers()
            if tickers:
                for i in range(0, len(tickers), TICKER_BATCH_SIZE):
                    batch = tickers[i : i + TICKER_BATCH_SIZE]
                    await self._poll_batch(batch)
            await asyncio.sleep(self._poll_interval)

    async def _poll_batch(self, tickers: list[str]) -> None:
        ticker_param = ",".join(tickers)
        try:
            resp = await self._http.get(
                f"/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ticker_param},
            )
            resp.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            # Log and continue — cache retains the last known price
            print(f"[MassiveClient] poll error: {exc}")
            return

        data = resp.json()
        tickers_data = data.get("tickers") or []
        for item in tickers_data:
            symbol = item.get("ticker")
            day = item.get("day") or {}
            price = day.get("c")   # closing/current price for the day
            if symbol and price is not None:
                self._cache.update(symbol, float(price))
```

### 5.2 Ticker Validation with Massive

When a user adds a ticker while `MASSIVE_API_KEY` is set, the API route can probe before adding:

```python
# backend/app/api/watchlist.py  (excerpt)
async def _ticker_exists_massive(ticker: str, client: MassiveClient) -> bool:
    try:
        resp = await client._http.get(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        )
        if resp.status_code == 200:
            data = resp.json()
            return bool(data.get("ticker"))
        return False
    except httpx.HTTPError:
        return False
```

If the probe returns no data, the API returns `400 {"detail": "Unknown ticker: XYZ"}`.

---

## 6. Factory

```python
# backend/app/market/factory.py
import os
from .base import MarketDataSource
from .simulator import GBMSimulator
from .massive import MassiveClient


def create_market_data_source() -> MarketDataSource:
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if api_key:
        poll_interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15"))
        return MassiveClient(api_key=api_key, poll_interval=poll_interval)
    return GBMSimulator()
```

---

## 7. SSE Stream

The SSE endpoint reads from the cache and emits only when a price has changed since the last emission for that ticker. This avoids sending redundant data and prevents spurious flash animations on the frontend.

```python
# backend/app/market/stream.py
import asyncio
import json
import time
from typing import AsyncGenerator
from .cache import PriceCache


SSE_TICK_INTERVAL = 0.1   # how often the generator checks the cache (seconds)


async def price_event_generator(cache: PriceCache) -> AsyncGenerator[str, None]:
    """
    Yields SSE-formatted strings. Emits a ticker only when its price changed
    since the last time we emitted it.
    """
    last_emitted: dict[str, float] = {}

    while True:
        all_prices = cache.get_all()
        events = []

        for ticker, tp in all_prices.items():
            if tp.price == 0.0:
                continue  # not yet seeded; skip
            last = last_emitted.get(ticker)
            if last is None or last != tp.price:
                last_emitted[ticker] = tp.price
                events.append(tp.to_sse_dict())

        for event in events:
            yield f"data: {json.dumps(event)}\n\n"

        await asyncio.sleep(SSE_TICK_INTERVAL)
```

```python
# backend/app/api/stream.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.market.stream import price_event_generator
from app.dependencies import get_price_cache   # injected singleton

router = APIRouter()


@router.get("/api/stream/prices")
async def stream_prices(cache=Depends(get_price_cache)):
    return StreamingResponse(
        price_event_generator(cache),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # disable nginx buffering if present
            "Connection": "keep-alive",
        },
    )
```

### SSE Event Format

Each event is a single `data:` line followed by a blank line (standard SSE):

```
data: {"ticker":"AAPL","price":190.23,"prev_price":190.0,"session_open":190.0,"change_pct":0.121,"direction":"up","timestamp":1751310000.5}

data: {"ticker":"TSLA","price":249.87,"prev_price":250.1,"session_open":248.5,"change_pct":0.552,"direction":"down","timestamp":1751310000.5}

```

---

## 8. App Startup & Lifecycle

The market data source and cache are created once at startup and injected throughout the application.

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.db.init import init_db, get_watchlist_tickers, get_position_tickers

price_cache: PriceCache = PriceCache()
market_source = create_market_data_source()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialise database (create schema + seed if needed)
    await init_db()

    # 2. Prime the cache with persisted watchlist + open positions
    tracked = await get_watchlist_tickers() + await get_position_tickers()
    price_cache.ensure_tracked(list(set(tracked)))

    # 3. Start the market data background task
    await market_source.start(price_cache)

    yield

    # Shutdown
    await market_source.stop()


app = FastAPI(lifespan=lifespan)
```

### Dependency Injection

```python
# backend/app/dependencies.py
from app.main import price_cache, market_source

def get_price_cache() -> PriceCache:
    return price_cache

def get_market_source() -> MarketDataSource:
    return market_source
```

---

## 9. Watchlist Integration

When the user (or AI) adds or removes a ticker, the API handler must keep the cache in sync.

```python
# backend/app/api/watchlist.py  (excerpt)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.dependencies import get_price_cache, get_market_source

router = APIRouter()


class AddTickerRequest(BaseModel):
    ticker: str


@router.post("/api/watchlist")
async def add_ticker(
    req: AddTickerRequest,
    cache=Depends(get_price_cache),
    source=Depends(get_market_source),
    db=Depends(get_db),
):
    ticker = req.ticker.upper().strip()
    if not source.validate_ticker(ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")

    # With Massive, probe the API to confirm the ticker exists
    if isinstance(source, MassiveClient):
        exists = await _ticker_exists_massive(ticker, source)
        if not exists:
            raise HTTPException(status_code=400, detail=f"Unknown ticker: {ticker}")

    await db_add_to_watchlist(db, ticker)
    # Add to cache so the simulator/poller starts generating prices for it
    cache.ensure_tracked([ticker])
    return {"ticker": ticker}


@router.delete("/api/watchlist/{ticker}")
async def remove_ticker(
    ticker: str,
    cache=Depends(get_price_cache),
    db=Depends(get_db),
):
    ticker = ticker.upper()
    await db_remove_from_watchlist(db, ticker)

    # Only remove from cache if no open position exists
    position = await db_get_position(db, ticker)
    if position is None or position.quantity == 0:
        cache.remove(ticker)

    return {"ticker": ticker}
```

---

## 10. Portfolio P&L Integration

Portfolio endpoints use the cache directly to calculate unrealized P&L without an extra database read.

```python
# backend/app/api/portfolio.py  (excerpt)
@router.get("/api/portfolio")
async def get_portfolio(cache=Depends(get_price_cache), db=Depends(get_db)):
    profile = await db_get_profile(db)
    positions = await db_get_positions(db)

    position_rows = []
    total_market_value = 0.0

    for pos in positions:
        current_price = cache.price(pos.ticker) or pos.avg_cost
        market_value = pos.quantity * current_price
        unrealized_pnl = (current_price - pos.avg_cost) * pos.quantity
        total_market_value += market_value
        position_rows.append({
            "ticker": pos.ticker,
            "quantity": pos.quantity,
            "avg_cost": round(pos.avg_cost, 2),
            "current_price": round(current_price, 2),
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round((current_price - pos.avg_cost) / pos.avg_cost * 100, 2),
        })

    total_value = profile.cash_balance + total_market_value
    return {
        "cash_balance": round(profile.cash_balance, 2),
        "total_value": round(total_value, 2),
        "positions": position_rows,
    }
```

---

## 11. Trade Execution & Cache Sync

After a trade, if a new ticker enters or leaves positions, the cache must be updated.

```python
# backend/app/api/portfolio.py  (excerpt)
@router.post("/api/portfolio/trade")
async def execute_trade(req: TradeRequest, cache=Depends(get_price_cache), db=Depends(get_db)):
    ticker = req.ticker.upper()
    current_price = cache.price(ticker)
    if current_price is None:
        raise HTTPException(status_code=400, detail=f"No price available for {ticker}")

    if req.side == "buy":
        cost = current_price * req.quantity
        profile = await db_get_profile(db)
        if profile.cash_balance < cost:
            raise HTTPException(status_code=400, detail="Insufficient cash")

        await db_execute_buy(db, ticker, req.quantity, current_price)
        # Ensure ticker stays in cache (already there if on watchlist)
        cache.ensure_tracked([ticker])

    elif req.side == "sell":
        position = await db_get_position(db, ticker)
        if position is None or position.quantity < req.quantity:
            raise HTTPException(status_code=400, detail="Insufficient shares")

        remaining = await db_execute_sell(db, ticker, req.quantity, current_price)
        # If fully sold and not on watchlist, remove from cache
        if remaining == 0:
            on_watchlist = await db_ticker_in_watchlist(db, ticker)
            if not on_watchlist:
                cache.remove(ticker)

    return {"status": "ok", "price": round(current_price, 2)}
```

---

## 12. Configuration Reference

| Env Var | Default | Description |
|---|---|---|
| `MASSIVE_API_KEY` | _(empty)_ | If set, uses Massive REST API; otherwise simulator |
| `MASSIVE_POLL_INTERVAL` | `15` | Seconds between Massive polls (free tier: ≥15) |

No additional configuration is needed for the simulator. Its parameters (`TICK_INTERVAL`, `VOLATILITY`, `SEED_PRICES`, `RANDOM_EVENT_PROB`) are module-level constants in `simulator.py` and can be adjusted there.

---

## 13. Testing

### Unit: Simulator price generation

```python
# backend/tests/test_simulator.py
import asyncio
import pytest
from app.market.simulator import GBMSimulator, _gbm_step
from app.market.cache import PriceCache


def test_gbm_step_positive():
    """Price never goes below 0.01."""
    for _ in range(1000):
        p = _gbm_step(100.0, sigma=0.30, dt=0.001, z=random.gauss(0, 1))
        assert p > 0


@pytest.mark.asyncio
async def test_simulator_updates_cache():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL", "TSLA"])
    sim = GBMSimulator(tick_interval=0.05)
    await sim.start(cache)
    await asyncio.sleep(0.2)
    await sim.stop()

    aapl = cache.get("AAPL")
    assert aapl is not None
    assert aapl.price > 0
    assert aapl.session_open > 0
    assert aapl.direction in ("up", "down", "flat")
```

### Unit: Cache behaviour

```python
# backend/tests/test_cache.py
from app.market.cache import PriceCache


def test_session_open_never_changes():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("AAPL", 195.0)
    cache.update("AAPL", 188.0)
    tp = cache.get("AAPL")
    assert tp.session_open == 190.0   # first observed price
    assert tp.price == 188.0
    assert tp.prev_price == 195.0


def test_remove_cleans_cache():
    cache = PriceCache()
    cache.update("TSLA", 250.0)
    cache.remove("TSLA")
    assert cache.get("TSLA") is None


def test_change_pct():
    cache = PriceCache()
    cache.update("NVDA", 875.0)
    cache.update("NVDA", 900.0)
    tp = cache.get("NVDA")
    assert round(tp.change_pct, 2) == round((900.0 - 875.0) / 875.0 * 100, 2)
```

### Unit: Massive response parsing

```python
# backend/tests/test_massive.py
import pytest
from unittest.mock import AsyncMock, patch
from app.market.massive import MassiveClient
from app.market.cache import PriceCache

MOCK_RESPONSE = {
    "tickers": [
        {"ticker": "AAPL", "day": {"c": 191.5}},
        {"ticker": "GOOGL", "day": {"c": 177.2}},
    ]
}


@pytest.mark.asyncio
async def test_poll_updates_cache():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL", "GOOGL"])
    client = MassiveClient(api_key="fake")

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_RESPONSE
    mock_resp.raise_for_status = lambda: None

    with patch.object(client._http, "get", return_value=mock_resp):
        await client._poll_batch(["AAPL", "GOOGL"])

    assert cache.price("AAPL") == 191.5
    assert cache.price("GOOGL") == 177.2


def test_validate_ticker_massive():
    client = MassiveClient(api_key="fake")
    assert client.validate_ticker("AAPL") is True
    assert client.validate_ticker("aapl") is False
    assert client.validate_ticker("TOOLONG") is False
    assert client.validate_ticker("123") is False
```

### Unit: SSE generator emits only on change

```python
# backend/tests/test_stream.py
import asyncio
import pytest
from app.market.cache import PriceCache
from app.market.stream import price_event_generator


@pytest.mark.asyncio
async def test_no_duplicate_events():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    gen = price_event_generator(cache)
    first = await gen.__anext__()
    assert "AAPL" in first

    # Without a price change, no second event should arrive within 0.2s
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(gen.__anext__(), timeout=0.2)

    # After a price update, a new event should arrive
    cache.update("AAPL", 191.0)
    second = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
    assert "191.0" in second
```

---

## 14. Implementation Order

1. `base.py` — types and abstract class
2. `cache.py` — price cache
3. `simulator.py` — GBM engine
4. `factory.py` — env-var selection
5. Wire into `main.py` lifespan
6. `stream.py` — SSE generator
7. `api/stream.py` — FastAPI SSE route
8. Watchlist/portfolio cache sync in API handlers
9. `massive.py` — Massive client (once simulator is verified)
10. Unit tests

The simulator can be running and serving SSE before the Massive client is written, so frontend development is unblocked early.
