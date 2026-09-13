from __future__ import annotations

import importlib
from datetime import datetime
from pathlib import Path
from typing import Any


class MT5Error(RuntimeError):
    pass


def _load_mt5() -> object:
    try:
        return importlib.import_module("MetaTrader5")
    except ImportError as exc:
        raise MT5Error("MetaTrader5 package is not installed; install copygraph[mt5]") from exc


def _last_error(mt5: object) -> object:
    try:
        return mt5.last_error()
    except Exception:
        return "unknown"


def _risk_values(order: object | None) -> tuple[float | None, float | None]:
    if order is None:
        return None, None
    sl = float(getattr(order, "sl", 0.0) or 0.0)
    tp = float(getattr(order, "tp", 0.0) or 0.0)
    return (sl or None), (tp or None)


def _position_risk_orders(orders: tuple[object, ...] | list[object]) -> dict[object, object]:
    selected: dict[object, object] = {}
    for order in sorted(orders, key=lambda item: (getattr(item, "time_setup", 0), getattr(item, "ticket", 0))):
        position_id = getattr(order, "position_id", None)
        if position_id in selected:
            continue
        sl, tp = _risk_values(order)
        if sl is not None or tp is not None:
            selected[position_id] = order
    return selected


def collect_mt5_history(
    date_from: datetime,
    date_to: datetime,
    terminal_path: str | Path | None = None,
    mt5_module: object | None = None,
) -> dict[str, object]:
    mt5 = mt5_module or _load_mt5()
    initialized = False
    try:
        if terminal_path is None:
            initialized = bool(mt5.initialize())
        else:
            initialized = bool(mt5.initialize(str(terminal_path)))
        if not initialized:
            raise MT5Error(f"MetaTrader5 initialize failed: {_last_error(mt5)}")

        account = mt5.account_info()
        if account is None:
            raise MT5Error(f"MetaTrader5 account_info failed: {_last_error(mt5)}")

        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            raise MT5Error(f"MetaTrader5 history_deals_get failed: {_last_error(mt5)}")
        orders = mt5.history_orders_get(date_from, date_to)
        if orders is None:
            raise MT5Error(f"MetaTrader5 history_orders_get failed: {_last_error(mt5)}")

        order_by_ticket = {getattr(order, "ticket", None): order for order in orders}
        order_by_position = _position_risk_orders(list(orders))
        buy_type = getattr(mt5, "DEAL_TYPE_BUY", 0)
        sell_type = getattr(mt5, "DEAL_TYPE_SELL", 1)
        entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
        records: list[dict[str, Any]] = []
        account_id = str(getattr(account, "login"))

        for deal in deals:
            deal_type = getattr(deal, "type", None)
            if deal_type not in {buy_type, sell_type}:
                continue
            record: dict[str, Any] = {
                "account_id": account_id,
                "ticket": getattr(deal, "ticket"),
                "position_id": getattr(deal, "position_id"),
                "symbol": getattr(deal, "symbol"),
                "type": deal_type,
                "volume": float(getattr(deal, "volume")),
                "price": float(getattr(deal, "price")),
                "time": getattr(deal, "time"),
                "entry": getattr(deal, "entry"),
                "profit": float(getattr(deal, "profit", 0.0) or 0.0),
            }
            if getattr(deal, "entry", None) == entry_in:
                risk_order = order_by_ticket.get(getattr(deal, "order", None))
                sl, tp = _risk_values(risk_order)
                if sl is None and tp is None:
                    sl, tp = _risk_values(order_by_position.get(getattr(deal, "position_id", None)))
                if sl is not None:
                    record["sl"] = sl
                if tp is not None:
                    record["tp"] = tp
            records.append(record)

        return {"schema_version": "1.0", "account_id": account_id, "records": records}
    finally:
        if initialized:
            mt5.shutdown()
