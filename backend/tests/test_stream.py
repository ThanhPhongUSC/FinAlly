import asyncio
import json

import pytest

from app.market.cache import PriceCache
from app.market.stream import price_event_generator


@pytest.mark.asyncio
async def test_first_tick_emits_event_for_seeded_ticker():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    gen = price_event_generator(cache)
    first = await asyncio.wait_for(gen.__anext__(), timeout=0.5)

    assert first.startswith("data: ")
    payload = json.loads(first.removeprefix("data: ").strip())
    assert payload["ticker"] == "AAPL"
    assert payload["price"] == 190.0


@pytest.mark.asyncio
async def test_no_duplicate_events_without_a_price_change():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    gen = price_event_generator(cache)
    await asyncio.wait_for(gen.__anext__(), timeout=0.5)  # consume the first event

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(gen.__anext__(), timeout=0.3)


@pytest.mark.asyncio
async def test_emits_again_after_price_change():
    cache = PriceCache()
    cache.update("AAPL", 190.0)

    gen = price_event_generator(cache)
    await asyncio.wait_for(gen.__anext__(), timeout=0.5)  # consume the first event

    cache.update("AAPL", 191.0)
    second = await asyncio.wait_for(gen.__anext__(), timeout=0.5)

    payload = json.loads(second.removeprefix("data: ").strip())
    assert payload["price"] == 191.0


@pytest.mark.asyncio
async def test_unseeded_sentinel_tickers_are_skipped():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL"])  # price=0.0 sentinel, not yet seeded

    gen = price_event_generator(cache)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(gen.__anext__(), timeout=0.3)

    cache.update("AAPL", 190.0)
    event = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
    assert "AAPL" in event


@pytest.mark.asyncio
async def test_emits_independently_per_ticker():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("TSLA", 250.0)

    gen = price_event_generator(cache)
    seen_tickers = set()
    for _ in range(2):
        event = await asyncio.wait_for(gen.__anext__(), timeout=0.5)
        payload = json.loads(event.removeprefix("data: ").strip())
        seen_tickers.add(payload["ticker"])

    assert seen_tickers == {"AAPL", "TSLA"}
