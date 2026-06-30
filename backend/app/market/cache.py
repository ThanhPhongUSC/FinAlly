"""Thread-safe in-memory price cache shared by all market data sources and readers."""

from __future__ import annotations

import time
from threading import Lock

from .base import TickerPrice


class PriceCache:
    """Single source of truth for all live prices.

    Written to only by the active `MarketDataSource` background task; read by the
    SSE stream and portfolio P&L calculations.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._data: dict[str, TickerPrice] = {}

    # ------------------------------------------------------------------ writes

    def update(self, ticker: str, new_price: float) -> TickerPrice:
        """Record a new price for `ticker`, deriving prev_price/session_open."""
        with self._lock:
            existing = self._data.get(ticker)
            # A sentinel entry (price == 0.0, from ensure_tracked) hasn't been
            # priced yet, so this update establishes the session-open baseline.
            has_real_price = existing is not None and existing.price > 0
            session_open = existing.session_open if has_real_price else new_price
            prev_price = existing.price if has_real_price else new_price
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
                        ticker=t,
                        price=0.0,
                        prev_price=0.0,
                        session_open=0.0,
                        timestamp=time.time(),
                    )

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._data.pop(ticker, None)

    # ------------------------------------------------------------------ reads

    def get(self, ticker: str) -> TickerPrice | None:
        with self._lock:
            return self._data.get(ticker)

    def get_all(self) -> dict[str, TickerPrice]:
        with self._lock:
            return dict(self._data)

    def get_tickers(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def price(self, ticker: str) -> float | None:
        tp = self.get(ticker)
        return tp.price if tp else None
