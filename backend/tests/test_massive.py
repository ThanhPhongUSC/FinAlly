import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.market.cache import PriceCache
from app.market.massive import MassiveClient

SNAPSHOT_RESPONSE = {
    "tickers": [
        {"ticker": "AAPL", "day": {"c": 191.5}},
        {"ticker": "GOOGL", "day": {"c": 177.2}},
    ]
}


def test_validate_ticker_massive():
    client = MassiveClient(api_key="fake")
    assert client.validate_ticker("AAPL") is True
    assert client.validate_ticker("aapl") is False
    assert client.validate_ticker("TOOLONG") is False
    assert client.validate_ticker("123") is False


@pytest_asyncio.fixture
async def started_client():
    cache = PriceCache()
    client = MassiveClient(api_key="fake")
    await client.start(cache)
    yield client, cache
    await client.stop()


@pytest.mark.asyncio
async def test_poll_batch_updates_cache(started_client):
    client, cache = started_client
    cache.ensure_tracked(["AAPL", "GOOGL"])

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: SNAPSHOT_RESPONSE
    mock_resp.raise_for_status = lambda: None
    client._http.get = AsyncMock(return_value=mock_resp)

    await client._poll_batch(["AAPL", "GOOGL"])

    assert cache.price("AAPL") == 191.5
    assert cache.price("GOOGL") == 177.2


@pytest.mark.asyncio
async def test_poll_batch_ignores_entries_without_price(started_client):
    client, cache = started_client
    cache.ensure_tracked(["AAPL"])

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"tickers": [{"ticker": "AAPL", "day": {}}]}
    mock_resp.raise_for_status = lambda: None
    client._http.get = AsyncMock(return_value=mock_resp)

    await client._poll_batch(["AAPL"])

    assert cache.price("AAPL") == 0.0  # untouched sentinel


@pytest.mark.asyncio
async def test_poll_batch_swallows_http_errors_and_keeps_last_price(started_client):
    client, cache = started_client
    cache.update("AAPL", 100.0)

    client._http.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    await client._poll_batch(["AAPL"])  # must not raise

    assert cache.price("AAPL") == 100.0


@pytest.mark.asyncio
async def test_poll_batch_swallows_non_2xx_status(started_client):
    client, cache = started_client
    cache.update("AAPL", 100.0)

    def raise_for_status():
        raise httpx.HTTPStatusError("bad", request=None, response=None)

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = raise_for_status
    client._http.get = AsyncMock(return_value=mock_resp)

    await client._poll_batch(["AAPL"])  # must not raise

    assert cache.price("AAPL") == 100.0


@pytest.mark.asyncio
async def test_ticker_exists_true_on_200_with_ticker_field(started_client):
    client, _ = started_client
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"ticker": {"ticker": "AAPL"}}
    client._http.get = AsyncMock(return_value=mock_resp)

    assert await client.ticker_exists("AAPL") is True


@pytest.mark.asyncio
async def test_ticker_exists_false_on_404(started_client):
    client, _ = started_client
    mock_resp = AsyncMock()
    mock_resp.status_code = 404
    client._http.get = AsyncMock(return_value=mock_resp)

    assert await client.ticker_exists("ZZZZZ") is False


@pytest.mark.asyncio
async def test_ticker_exists_false_on_network_error(started_client):
    client, _ = started_client
    client._http.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

    assert await client.ticker_exists("AAPL") is False


@pytest.mark.asyncio
async def test_ticker_exists_before_start_raises():
    client = MassiveClient(api_key="fake")
    with pytest.raises(RuntimeError):
        await client.ticker_exists("AAPL")


@pytest.mark.asyncio
async def test_run_polls_tracked_tickers_in_batches():
    cache = PriceCache()
    cache.ensure_tracked(["AAPL"])
    client = MassiveClient(api_key="fake", poll_interval=0.01)

    poll_calls = []

    async def fake_poll_batch(tickers):
        poll_calls.append(tickers)

    # Patch before start() so the background loop's very first iteration uses it.
    client._poll_batch = fake_poll_batch
    await client.start(cache)
    await asyncio.sleep(0.05)
    await client.stop()

    assert len(poll_calls) >= 1
    assert poll_calls[0] == ["AAPL"]


@pytest.mark.asyncio
async def test_run_batches_large_ticker_lists():
    from app.market import massive as massive_module

    cache = PriceCache()
    many_tickers = [f"T{i:03d}" for i in range(120)]
    cache.ensure_tracked(many_tickers)
    client = MassiveClient(api_key="fake", poll_interval=0.01)

    seen_batches = []

    async def fake_poll_batch(tickers):
        seen_batches.append(list(tickers))

    client._poll_batch = fake_poll_batch
    await client.start(cache)
    await asyncio.sleep(0.05)
    await client.stop()

    assert len(seen_batches) >= 1
    assert all(len(b) <= massive_module.TICKER_BATCH_SIZE for b in seen_batches[0:3])
