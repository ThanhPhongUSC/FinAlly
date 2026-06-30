from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.stream import router
from app.dependencies import get_price_cache
from app.market.cache import PriceCache


def build_test_app(cache: PriceCache) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_price_cache] = lambda: cache
    return app


def test_stream_prices_route_emits_sse_event_for_seeded_ticker():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    app = build_test_app(cache)

    with TestClient(app) as client, client.stream("GET", "/api/stream/prices") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        data_line = None
        for line in response.iter_lines():
            if line.startswith("data:"):
                data_line = line
                break

        assert data_line is not None
        assert "AAPL" in data_line
        assert "190.0" in data_line
