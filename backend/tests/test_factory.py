from app.market.factory import create_market_data_source
from app.market.massive import MassiveClient
from app.market.simulator import GBMSimulator


def test_factory_defaults_to_simulator_when_no_api_key(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    source = create_market_data_source()
    assert isinstance(source, GBMSimulator)


def test_factory_treats_blank_api_key_as_unset(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "   ")
    source = create_market_data_source()
    assert isinstance(source, GBMSimulator)


def test_factory_uses_massive_when_api_key_set(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "secret-key")
    source = create_market_data_source()
    assert isinstance(source, MassiveClient)
    assert source._api_key == "secret-key"
    assert source._poll_interval == 15.0


def test_factory_respects_custom_poll_interval(monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "secret-key")
    monkeypatch.setenv("MASSIVE_POLL_INTERVAL", "5")
    source = create_market_data_source()
    assert isinstance(source, MassiveClient)
    assert source._poll_interval == 5.0
