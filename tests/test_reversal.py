import pytest

from copygraph.ingest import parse_records
from copygraph.lifecycle import reconstruct_positions


def test_parse_mt5_inout_as_reverse_and_out_by_as_close():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 2, "price": 1.09, "time": "2026-09-12T10:05:00Z", "entry": 2},
        {"account": "a", "ticket": 2, "position": 8, "symbol": "EURUSD", "type": "sell", "volume": 1, "price": 1.09, "time": "2026-09-12T10:06:00Z", "entry": 3},
    ])
    assert [event.event for event in events] == ["REVERSE", "CLOSE"]


def test_reversal_splits_one_mt5_position_identifier_into_two_lifecycles():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 7, "symbol": "EURUSD", "type": "buy", "volume": 1, "price": 1.10, "time": "2026-09-12T10:00:00Z", "entry": 0, "sl": 1.08, "tp": 1.14},
        {"account": "a", "ticket": 2, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 2, "price": 1.09, "time": "2026-09-12T10:05:00Z", "entry": 2, "sl": 1.11, "tp": 1.05, "profit": -10},
    ])
    positions = reconstruct_positions(events)
    assert len(positions) == 2
    first, second = positions
    assert first.position_id == "7"
    assert first.side == "BUY"
    assert first.volume == pytest.approx(1.0)
    assert first.close_price == pytest.approx(1.09)
    assert first.profit == pytest.approx(-10.0)
    assert second.position_id == "7#2"
    assert second.side == "SELL"
    assert second.volume == pytest.approx(1.0)
    assert second.open_price == pytest.approx(1.09)
    assert second.sl == pytest.approx(1.11)
    assert second.tp == pytest.approx(1.05)
    assert second.close_time is None


def test_reversal_uses_remaining_volume_after_partial_close():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 7, "symbol": "EURUSD", "type": "buy", "volume": 2, "price": 1.10, "time": "2026-09-12T10:00:00Z", "entry": 0},
        {"account": "a", "ticket": 2, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 0.5, "price": 1.11, "time": "2026-09-12T10:03:00Z", "entry": 1, "profit": 5},
        {"account": "a", "ticket": 3, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 2, "price": 1.09, "time": "2026-09-12T10:05:00Z", "entry": 2, "profit": -15},
    ])
    first, second = reconstruct_positions(events)
    assert first.close_time is not None
    assert first.close_price == pytest.approx((0.5 * 1.11 + 1.5 * 1.09) / 2.0)
    assert first.profit == pytest.approx(-10.0)
    assert second.side == "SELL"
    assert second.volume == pytest.approx(0.5)
