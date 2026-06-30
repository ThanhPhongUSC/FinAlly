"""SSE event generation that reads from the shared price cache."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from .cache import PriceCache

SSE_TICK_INTERVAL = 0.1  # how often the generator checks the cache for changes


async def price_event_generator(cache: PriceCache) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings, emitting a ticker only when its price changed
    since the last time it was emitted. Untracked-but-unseeded tickers (price=0
    sentinel from `ensure_tracked`) are skipped until a real price arrives.
    """
    last_emitted: dict[str, float] = {}

    while True:
        for ticker, tp in cache.get_all().items():
            if tp.price == 0.0:
                continue
            if last_emitted.get(ticker) != tp.price:
                last_emitted[ticker] = tp.price
                yield f"data: {json.dumps(tp.to_sse_dict())}\n\n"

        await asyncio.sleep(SSE_TICK_INTERVAL)
