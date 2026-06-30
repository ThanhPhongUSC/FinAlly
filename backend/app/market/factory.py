"""Selects the active market data implementation from environment variables."""

from __future__ import annotations

import os

from .base import MarketDataSource
from .massive import MassiveClient
from .simulator import GBMSimulator


def create_market_data_source() -> MarketDataSource:
    """Massive REST API if `MASSIVE_API_KEY` is set and non-empty; simulator otherwise."""
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if api_key:
        poll_interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15"))
        return MassiveClient(api_key=api_key, poll_interval=poll_interval)
    return GBMSimulator()
