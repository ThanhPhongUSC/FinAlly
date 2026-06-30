import asyncio
import math
import random

import pytest

from app.market.cache import PriceCache
from app.market.simulator import (
    SEED_PRICE_MAX,
    SEED_PRICE_MIN,
    SEED_PRICES,
    GBMSimulator,
    gbm_step,
    seed_price,
    sigma_for,
)


def test_gbm_step_stays_positive():
    random.seed(42)
    p = 100.0
    for _ in range(2000):
        p = gbm_step(p, sigma=0.30, dt=0.001, z=random.gauss(0, 1))
        assert p > 0


def test_gbm_step_zero_volatility_is_pure_drift():
    p = gbm_step(100.0, sigma=0.0, dt=1.0, z=0.0, drift=0.05)
    assert p == pytest.approx(100.0 * math.exp(0.05))


def test_gbm_step_zero_z_no_volatility_term():
    # With z=0 the random shock term vanishes regardless of sigma.
    p = gbm_step(100.0, sigma=0.5, dt=0.01, z=0.0, drift=0.0)
    assert p == pytest.approx(100.0 * math.exp(-0.5 * 0.5**2 * 0.01))


def test_seed_price_known_ticker_uses_lookup_table():
    assert seed_price("AAPL") == SEED_PRICES["AAPL"]
    assert seed_price("NFLX") == SEED_PRICES["NFLX"]


def test_seed_price_unknown_ticker_is_plausible_random():
    random.seed(1)
    p = seed_price("ZZZZ")
    assert SEED_PRICE_MIN <= p <= SEED_PRICE_MAX


def test_sigma_for_known_vs_default():
    assert sigma_for("TSLA") == 0.65
    assert sigma_for("UNKNOWN_TICKER") == 0.30


def test_validate_ticker_accepts_one_to_five_upper_alpha():
    sim = GBMSimulator()
    assert sim.validate_ticker("V") is True
    assert sim.validate_ticker("AAPL") is True
    assert sim.validate_ticker("NFLX") is True


def test_validate_ticker_rejects_invalid_forms():
    sim = GBMSimulator()
    assert sim.validate_ticker("") is False
    assert sim.validate_ticker("aapl") is False  # lowercase
    assert sim.validate_ticker("TOOLONG") is False  # > 5 chars
    assert sim.validate_ticker("123") is False  # not alpha
    assert sim.validate_ticker("BRK.B") is False  # punctuation


def test_tick_initializes_seed_prices_for_tracked_tickers():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL", "TSLA"])
    sim = GBMSimulator()
    dt = 0.5 / (252 * 6.5 * 3600)

    sim._tick(dt)

    assert cache.price("AAPL") > 0
    assert cache.price("TSLA") > 0
    assert sim._current_prices["AAPL"] > 0


def test_tick_picks_up_existing_cache_price_instead_of_reseeding():
    cache = PriceCache()
    cache.update("AAPL", 123.45)
    sim = GBMSimulator()
    dt = 0.5 / (252 * 6.5 * 3600)

    sim._tick(dt)

    # Seeded from the existing cache price (123.45), not the SEED_PRICES lookup (190.0).
    assert sim._current_prices["AAPL"] != SEED_PRICES["AAPL"]


def test_tick_never_drives_price_below_floor():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL"])
    sim = GBMSimulator()
    sim._current_prices["AAPL"] = 0.001
    # Huge dt forces an extreme move; the floor must still hold.
    sim._tick(dt=10.0)
    assert cache.price("AAPL") >= 0.01


@pytest.mark.asyncio
async def test_simulator_updates_cache_over_time():
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


@pytest.mark.asyncio
async def test_simulator_stop_cancels_background_task():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL"])
    sim = GBMSimulator(tick_interval=0.05)
    await sim.start(cache)
    await sim.stop()
    assert sim._task is None
