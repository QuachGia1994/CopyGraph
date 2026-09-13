import json
from datetime import timezone

import pytest

from copygraph.ingest import load_events, parse_records
from copygraph.lifecycle import reconstruct_positions
from copygraph.symbols import canonicalize_symbol


def test_canonicalize_forex_suffix():
    assert canonicalize_symbol("EURUSD.pro") == "EURUSD"


def test_canonicalize_forex_prefix():
    assert canonicalize_symbol("mGBPJPY") == "GBPJPY"


def test_canonicalize_gold_alias():
    assert canonicalize_symbol("GOLDm") == "XAUUSD"


def test_canonicalize_index_alias():
    assert canonicalize_symbol("USTEC.cash") == "NAS100"


def test_canonicalize_rejects_empty():
    with pytest.raises(ValueError):
        canonicalize_symbol("  ")


def test_load_csv_accepts_mt5_aliases(tmp_path):
    path = tmp_path / "history.csv"
    path.write_text(
        "login,deal,position,symbol,type,lots,price,time,entry,sl,tp,profit\n"
        "1001,11,7,EURUSDm,buy,0.10,1.1000,2026.09.12 10:00:00,in,1.0950,1.1100,0\n",
        encoding="utf-8",
    )
    events = load_events(path)
    assert len(events) == 1
    assert events[0].account_id == "1001"
    assert events[0].symbol == "EURUSD"
    assert events[0].side == "BUY"
    assert events[0].event == "OPEN"


def test_load_json_accepts_records_list(tmp_path):
    path = tmp_path / "history.json"
    path.write_text(
        json.dumps([
            {"account_id": "a", "ticket": 1, "position_id": 9, "symbol": "xauusd", "side": "sell", "volume": 1, "price": 2500, "timestamp": "2026-09-12T10:00:00Z", "event": "open"}
        ]),
        encoding="utf-8",
    )
    events = load_events(path)
    assert events[0].symbol == "XAUUSD"
    assert events[0].side == "SELL"


def test_parse_timestamp_without_zone_assumes_utc():
    event = parse_records([
        {"account": "a", "ticket": 1, "position": 1, "symbol": "EURUSD", "type": "buy", "volume": 1, "price": 1.1, "time": "2026-09-12T10:00:00", "entry": "in"}
    ])[0]
    assert event.timestamp.tzinfo == timezone.utc


def test_parse_side_numeric_aliases():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 1, "symbol": "EURUSD", "type": 0, "volume": 1, "price": 1.1, "time": 1_757_672_000, "entry": 0},
        {"account": "a", "ticket": 2, "position": 2, "symbol": "EURUSD", "type": 1, "volume": 1, "price": 1.1, "time": 1_757_672_001, "entry": 0},
    ])
    assert [event.side for event in events] == ["BUY", "SELL"]


def test_parse_records_rejects_missing_required_field():
    with pytest.raises(ValueError, match="symbol"):
        parse_records([{"account": "a", "ticket": 1}])


def test_reconstructs_basic_position_lifecycle():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 7, "symbol": "EURUSD", "type": "buy", "volume": 1, "price": 1.10, "time": "2026-09-12T10:00:00Z", "entry": "in", "sl": 1.09, "tp": 1.12},
        {"account": "a", "ticket": 2, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 1, "price": 1.11, "time": "2026-09-12T10:05:00Z", "entry": "out", "profit": 100},
    ])
    position = reconstruct_positions(events)[0]
    assert position.side == "BUY"
    assert position.open_price == pytest.approx(1.10)
    assert position.close_price == pytest.approx(1.11)
    assert position.duration_s == 300
    assert position.profit == pytest.approx(100)


def test_reconstructs_partial_closes_with_weighted_price():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 7, "symbol": "EURUSD", "type": "buy", "volume": 1, "price": 1.10, "time": "2026-09-12T10:00:00Z", "entry": "in"},
        {"account": "a", "ticket": 2, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 0.4, "price": 1.11, "time": "2026-09-12T10:03:00Z", "entry": "out"},
        {"account": "a", "ticket": 3, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 0.6, "price": 1.12, "time": "2026-09-12T10:05:00Z", "entry": "out"},
    ])
    position = reconstruct_positions(events)[0]
    assert position.close_price == pytest.approx(1.116)
    assert position.close_time is not None


def test_reconstructs_still_open_position():
    event = parse_records([
        {"account": "a", "ticket": 1, "position": 7, "symbol": "GBPUSD", "type": "sell", "volume": 1, "price": 1.30, "time": "2026-09-12T10:00:00Z", "entry": "in"}
    ])
    position = reconstruct_positions(event)[0]
    assert position.close_time is None
    assert position.duration_s is None


def test_reconstruction_sorts_out_of_order_deals():
    events = parse_records([
        {"account": "a", "ticket": 2, "position": 7, "symbol": "EURUSD", "type": "sell", "volume": 1, "price": 1.11, "time": "2026-09-12T10:05:00Z", "entry": "out"},
        {"account": "a", "ticket": 1, "position": 7, "symbol": "EURUSD", "type": "buy", "volume": 1, "price": 1.10, "time": "2026-09-12T10:00:00Z", "entry": "in"},
    ])
    position = reconstruct_positions(events)[0]
    assert position.open_time < position.close_time


def test_ingest_ignores_balance_rows():
    events = parse_records([
        {"account": "a", "ticket": 1, "position": 1, "symbol": "EURUSD", "type": "buy", "volume": 1, "price": 1.1, "time": "2026-09-12T10:00:00Z", "entry": "in"},
        {"account": "a", "ticket": 2, "type": "balance", "profit": 1000, "time": "2026-09-12T10:01:00Z"},
    ])
    assert len(events) == 1
