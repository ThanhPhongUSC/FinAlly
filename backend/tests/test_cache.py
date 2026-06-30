from app.market.cache import PriceCache


def test_first_update_sets_session_open_and_flat_direction():
    cache = PriceCache()
    tp = cache.update("AAPL", 190.0)
    assert tp.session_open == 190.0
    assert tp.prev_price == 190.0
    assert tp.price == 190.0
    assert tp.direction == "flat"


def test_session_open_never_changes_across_updates():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("AAPL", 195.0)
    tp = cache.update("AAPL", 188.0)
    assert tp.session_open == 190.0  # first observed price
    assert tp.price == 188.0
    assert tp.prev_price == 195.0


def test_change_pct_matches_session_open_baseline():
    cache = PriceCache()
    cache.update("NVDA", 875.0)
    cache.update("NVDA", 900.0)
    tp = cache.get("NVDA")
    assert round(tp.change_pct, 2) == round((900.0 - 875.0) / 875.0 * 100, 2)


def test_remove_cleans_cache():
    cache = PriceCache()
    cache.update("TSLA", 250.0)
    cache.remove("TSLA")
    assert cache.get("TSLA") is None


def test_remove_missing_ticker_is_a_noop():
    cache = PriceCache()
    cache.remove("DOES_NOT_EXIST")  # should not raise


def test_ensure_tracked_seeds_sentinel_with_no_price():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL", "TSLA"])
    aapl = cache.get("AAPL")
    assert aapl.price == 0.0
    assert "AAPL" in cache.get_tickers()
    assert "TSLA" in cache.get_tickers()


def test_ensure_tracked_does_not_clobber_existing_price():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.ensure_tracked(["AAPL"])
    assert cache.price("AAPL") == 190.0


def test_first_real_update_after_sentinel_sets_session_open():
    """ensure_tracked() seeds price=0.0; the first real update must treat that as
    the session-open price, not silently inherit the 0.0 sentinel."""
    cache = PriceCache()
    cache.ensure_tracked(["AAPL"])
    tp = cache.update("AAPL", 190.0)
    assert tp.session_open == 190.0
    assert tp.prev_price == 190.0
    assert tp.direction == "flat"


def test_price_helper_returns_none_for_unknown_ticker():
    cache = PriceCache()
    assert cache.price("NOPE") is None


def test_get_all_returns_a_copy():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    snapshot = cache.get_all()
    snapshot.pop("AAPL")
    assert "AAPL" in cache.get_tickers()  # mutation of the snapshot must not affect the cache
