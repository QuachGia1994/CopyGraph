from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

import pytest

from copygraph.mt5 import MT5Error, collect_mt5_history


AccountInfo = namedtuple("AccountInfo", "login")
Deal = namedtuple("Deal", "ticket order time type entry position_id volume price profit symbol")
Order = namedtuple("Order", "ticket position_id time_setup sl tp")


class FakeMT5:
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    DEAL_ENTRY_IN = 0
    DEAL_ENTRY_OUT = 1

    def __init__(self, *, initialize_ok=True, deals=(), orders=(), account_login=123456):
        self.initialize_ok = initialize_ok
        self.deals = deals
        self.orders = orders
        self.account_login = account_login
        self.initialize_args = None
        self.shutdown_calls = 0
        self.error = (-1, "fake error")

    def initialize(self, *args, **kwargs):
        self.initialize_args = (args, kwargs)
        return self.initialize_ok

    def shutdown(self):
        self.shutdown_calls += 1

    def account_info(self):
        return AccountInfo(self.account_login)

    def history_deals_get(self, date_from, date_to):
        return self.deals

    def history_orders_get(self, date_from, date_to):
        return self.orders

    def last_error(self):
        return self.error


FROM = datetime(2026, 9, 1, tzinfo=timezone.utc)
TO = datetime(2026, 9, 13, tzinfo=timezone.utc)


def test_collect_mt5_history_normalizes_deals_and_enriches_open_risk_levels():
    deals = (
        Deal(11, 101, 1_757_000_000, 0, 0, 7, 0.2, 1.1000, 0.0, "EURUSDm"),
        Deal(12, 102, 1_757_000_300, 1, 1, 7, 0.2, 1.1100, 25.0, "EURUSDm"),
        Deal(13, 103, 1_757_000_400, 2, 0, 0, 0.0, 0.0, 1000.0, ""),
    )
    orders = (
        Order(101, 7, 1_756_999_990, 1.0900, 1.1200),
        Order(102, 7, 1_757_000_290, 0.0, 0.0),
    )
    mt5 = FakeMT5(deals=deals, orders=orders)

    payload = collect_mt5_history(FROM, TO, mt5_module=mt5)

    assert payload["schema_version"] == "1.0"
    assert payload["account_id"] == "123456"
    assert len(payload["records"]) == 2
    opened, closed = payload["records"]
    assert opened == {
        "account_id": "123456",
        "ticket": 11,
        "position_id": 7,
        "symbol": "EURUSDm",
        "type": 0,
        "volume": 0.2,
        "price": 1.1,
        "time": 1_757_000_000,
        "entry": 0,
        "sl": 1.09,
        "tp": 1.12,
        "profit": 0.0,
    }
    assert closed["ticket"] == 12
    assert closed["entry"] == 1
    assert closed["profit"] == 25.0
    assert "sl" not in closed and "tp" not in closed
    assert mt5.shutdown_calls == 1


def test_collect_mt5_history_falls_back_to_position_order_risk_levels():
    deals = (Deal(11, 999, 1_757_000_000, 0, 0, 7, 0.2, 1.1000, 0.0, "EURUSD"),)
    orders = (
        Order(100, 7, 1_756_999_000, 0.0, 0.0),
        Order(101, 7, 1_756_999_500, 1.0800, 1.1300),
    )
    payload = collect_mt5_history(FROM, TO, mt5_module=FakeMT5(deals=deals, orders=orders))
    assert payload["records"][0]["sl"] == 1.08
    assert payload["records"][0]["tp"] == 1.13


def test_collect_mt5_history_passes_explicit_terminal_path():
    mt5 = FakeMT5()
    terminal = Path(r"C:\MT5\terminal64.exe")
    collect_mt5_history(FROM, TO, terminal_path=terminal, mt5_module=mt5)
    assert mt5.initialize_args == ((str(terminal),), {})


def test_collect_mt5_history_raises_on_initialize_failure_without_shutdown():
    mt5 = FakeMT5(initialize_ok=False)
    with pytest.raises(MT5Error, match="initialize"):
        collect_mt5_history(FROM, TO, mt5_module=mt5)
    assert mt5.shutdown_calls == 0


def test_collect_mt5_history_raises_on_deal_history_error_and_shuts_down():
    mt5 = FakeMT5(deals=None, orders=())
    with pytest.raises(MT5Error, match="history_deals_get"):
        collect_mt5_history(FROM, TO, mt5_module=mt5)
    assert mt5.shutdown_calls == 1


def test_collect_mt5_history_raises_on_order_history_error_and_shuts_down():
    mt5 = FakeMT5(deals=(), orders=None)
    with pytest.raises(MT5Error, match="history_orders_get"):
        collect_mt5_history(FROM, TO, mt5_module=mt5)
    assert mt5.shutdown_calls == 1


def test_collect_mt5_history_wraps_runtime_api_exceptions_and_shuts_down():
    class RaisingMT5(FakeMT5):
        def history_deals_get(self, date_from, date_to):
            raise RuntimeError("bridge exploded")

    mt5 = RaisingMT5()
    with pytest.raises(MT5Error, match="history_deals_get"):
        collect_mt5_history(FROM, TO, mt5_module=mt5)
    assert mt5.shutdown_calls == 1


def test_collect_mt5_history_rejects_naive_datetimes_before_initialize():
    mt5 = FakeMT5()
    naive = datetime(2026, 9, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        collect_mt5_history(naive, TO, mt5_module=mt5)
    assert mt5.initialize_args is None


def test_collect_mt5_history_rejects_non_positive_window_before_initialize():
    mt5 = FakeMT5()
    with pytest.raises(ValueError, match="date_from"):
        collect_mt5_history(TO, FROM, mt5_module=mt5)
    assert mt5.initialize_args is None


def test_collect_mt5_history_does_not_replace_explicit_zero_risk_order_with_other_position_order():
    deals = (Deal(11, 101, 1_757_000_000, 0, 0, 7, 0.2, 1.1000, 0.0, "EURUSD"),)
    orders = (
        Order(100, 7, 1_756_999_500, 1.0800, 1.1300),
        Order(101, 7, 1_756_999_990, 0.0, 0.0),
    )
    payload = collect_mt5_history(FROM, TO, mt5_module=FakeMT5(deals=deals, orders=orders))
    assert "sl" not in payload["records"][0]
    assert "tp" not in payload["records"][0]


def test_collect_mt5_history_position_fallback_never_uses_future_order():
    deals = (Deal(11, 999, 1_757_000_000, 0, 0, 7, 0.2, 1.1000, 0.0, "EURUSD"),)
    orders = (Order(101, 7, 1_757_000_100, 1.0800, 1.1300),)
    payload = collect_mt5_history(FROM, TO, mt5_module=FakeMT5(deals=deals, orders=orders))
    assert "sl" not in payload["records"][0]
    assert "tp" not in payload["records"][0]


def test_collect_mt5_history_wraps_malformed_history_records():
    deals = (Deal(11, 101, 1_757_000_000, 0, 0, 7, 0.2, 1.1000, 0.0, "EURUSD"),)
    orders = (Order(101, 7, 1_756_999_990, "invalid", 1.1300),)
    with pytest.raises(MT5Error, match="normalization"):
        collect_mt5_history(FROM, TO, mt5_module=FakeMT5(deals=deals, orders=orders))


def test_collect_mt5_history_enriches_reverse_deal_risk_levels():
    deals = (Deal(11, 101, 1_757_000_000, 1, 2, 7, 2.0, 1.0900, -10.0, "EURUSD"),)
    orders = (Order(101, 7, 1_756_999_990, 1.1100, 1.0500),)
    payload = collect_mt5_history(FROM, TO, mt5_module=FakeMT5(deals=deals, orders=orders))
    record = payload["records"][0]
    assert record["entry"] == 2
    assert record["sl"] == pytest.approx(1.11)
    assert record["tp"] == pytest.approx(1.05)
