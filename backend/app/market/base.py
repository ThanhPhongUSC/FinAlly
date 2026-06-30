"""Shared types and the abstract interface every market data source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cache import PriceCache


@dataclass
class TickerPrice:
    """A single ticker's latest known price state."""

    ticker: str
    price: float
    prev_price: float
    session_open: float
    timestamp: float

    @property
    def change_pct(self) -> float:
        """Percent change from the session-open price."""
        if self.session_open == 0:
            return 0.0
        return (self.price - self.session_open) / self.session_open * 100

    @property
    def direction(self) -> str:
        """'up' / 'down' / 'flat' relative to the previous tick."""
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
    """All market data implementations (simulator, Massive, ...) satisfy this interface."""

    @abstractmethod
    async def start(self, cache: "PriceCache") -> None:
        """Begin producing prices into the cache. Called once on app startup."""

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown of any background work started in `start`."""

    @abstractmethod
    def validate_ticker(self, ticker: str) -> bool:
        """Return True if the ticker is syntactically acceptable for this source."""
