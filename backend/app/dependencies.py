"""Process-wide singletons shared across API routes via FastAPI dependency injection."""

from __future__ import annotations

from .market.base import MarketDataSource
from .market.cache import PriceCache
from .market.factory import create_market_data_source

price_cache: PriceCache = PriceCache()
market_source: MarketDataSource = create_market_data_source()


def get_price_cache() -> PriceCache:
    return price_cache


def get_market_source() -> MarketDataSource:
    return market_source
