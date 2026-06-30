from fastapi.testclient import TestClient

from app.main import DEFAULT_WATCHLIST, app


def test_health_check():
    with TestClient(app) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_lifespan_seeds_default_watchlist_into_cache():
    from app.dependencies import price_cache

    with TestClient(app):
        tracked = set(price_cache.get_tickers())
        assert set(DEFAULT_WATCHLIST).issubset(tracked)
