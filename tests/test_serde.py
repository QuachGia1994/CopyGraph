from datetime import datetime, timezone

from copygraph.models import PositionLifecycle, TradeEvent
from copygraph.serde import (
    lifecycle_from_dict,
    lifecycle_to_dict,
    trade_event_from_dict,
    trade_event_to_dict,
)


BASE = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


def test_trade_event_round_trip_preserves_utc_and_optional_risk():
    event = TradeEvent("a", "11", "7#2", "EURUSD", "SELL", 0.5, 1.1, BASE, "OPEN", 1.12, 1.05, 0.0)
    payload = trade_event_to_dict(event)
    assert payload["timestamp"] == "2026-09-10T10:00:00Z"
    assert trade_event_from_dict(payload) == event


def test_lifecycle_round_trip_preserves_open_state_and_tickets_tuple():
    position = PositionLifecycle(
        account_id="a",
        position_id="7#2",
        symbol="XAUUSD",
        side="BUY",
        open_time=BASE,
        close_time=None,
        open_price=3500.0,
        close_price=None,
        volume=0.2,
        sl=None,
        tp=3520.0,
        profit=0.0,
        tickets=("11", "12"),
    )
    payload = lifecycle_to_dict(position)
    assert payload["close_time"] is None
    assert payload["tickets"] == ["11", "12"]
    assert lifecycle_from_dict(payload) == position
