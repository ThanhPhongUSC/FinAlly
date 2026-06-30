from app.market.base import TickerPrice


def test_change_pct_computed_from_session_open():
    tp = TickerPrice(ticker="AAPL", price=200.0, prev_price=190.0, session_open=190.0, timestamp=1.0)
    assert round(tp.change_pct, 4) == round((200.0 - 190.0) / 190.0 * 100, 4)


def test_change_pct_zero_session_open_does_not_raise():
    tp = TickerPrice(ticker="AAPL", price=0.0, prev_price=0.0, session_open=0.0, timestamp=1.0)
    assert tp.change_pct == 0.0


def test_direction_up_down_flat():
    up = TickerPrice(ticker="AAPL", price=101.0, prev_price=100.0, session_open=100.0, timestamp=1.0)
    down = TickerPrice(ticker="AAPL", price=99.0, prev_price=100.0, session_open=100.0, timestamp=1.0)
    flat = TickerPrice(ticker="AAPL", price=100.0, prev_price=100.0, session_open=100.0, timestamp=1.0)
    assert up.direction == "up"
    assert down.direction == "down"
    assert flat.direction == "flat"


def test_to_sse_dict_rounds_and_serializes():
    tp = TickerPrice(
        ticker="AAPL",
        price=190.23456,
        prev_price=190.0,
        session_open=190.0,
        timestamp=1751310000.5,
    )
    d = tp.to_sse_dict()
    assert d == {
        "ticker": "AAPL",
        "price": 190.23,
        "prev_price": 190.0,
        "session_open": 190.0,
        "change_pct": round((190.23456 - 190.0) / 190.0 * 100, 4),
        "direction": "up",
        "timestamp": 1751310000.5,
    }
