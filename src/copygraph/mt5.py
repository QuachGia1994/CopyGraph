from __future__ import annotations

import importlib
from collections import defaultdict
from datetime import datetime, timezone
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


def _normalize_window(date_from: datetime, date_to: datetime) -> tuple[datetime, datetime]:
    if date_from.tzinfo is None or date_from.utcoffset() is None or date_to.tzinfo is None or date_to.utcoffset() is None:
        raise ValueError("date_from and date_to must be timezone-aware")
    start = date_from.astimezone(timezone.utc)
    end = date_to.astimezone(timezone.utc)
    if start >= end:
        raise ValueError("date_from must be before date_to")
    return start, end


def _call_mt5(mt5: object, operation: str, *args: object) -> object:
    try:
        return getattr(mt5, operation)(*args)
    except Exception as exc:
        raise MT5Error(f"MetaTrader5 {operation} raised: {exc}; last_error={_last_error(mt5)}") from exc


def _risk_orders_by_position(orders: tuple[object, ...] | list[object]) -> dict[object, list[object]]:
    grouped: dict[object, list[object]] = defaultdict(list)
    for order in orders:
        sl, tp = _risk_values(order)
        if sl is not None or tp is not None:
            grouped[getattr(order, "position_id", None)].append(order)
    for position_orders in grouped.values():
        position_orders.sort(key=lambda item: (getattr(item, "time_setup", 0), getattr(item, "ticket", 0)))
    return grouped


def _latest_prior_risk_order(orders_by_position: dict[object, list[object]], position_id: object, deal_time: object) -> object | None:
    candidates = [
        order
        for order in orders_by_position.get(position_id, [])
        if getattr(order, "time_setup", 0) <= deal_time
    ]
    return candidates[-1] if candidates else None


def collect_mt5_history(
    date_from: datetime,
    date_to: datetime,
    terminal_path: str | Path | None = None,
    mt5_module: object | None = None,
) -> dict[str, object]:
    date_from, date_to = _normalize_window(date_from, date_to)
    mt5 = mt5_module or _load_mt5()
    initialized = False
    failure: Exception | None = None
    try:
        initialize_args = () if terminal_path is None else (str(terminal_path),)
        initialized = bool(_call_mt5(mt5, "initialize", *initialize_args))
        if not initialized:
            raise MT5Error(f"MetaTrader5 initialize failed: {_last_error(mt5)}")

        account = _call_mt5(mt5, "account_info")
        if account is None:
            raise MT5Error(f"MetaTrader5 account_info failed: {_last_error(mt5)}")

        deals = _call_mt5(mt5, "history_deals_get", date_from, date_to)
        if deals is None:
            raise MT5Error(f"MetaTrader5 history_deals_get failed: {_last_error(mt5)}")
        orders = _call_mt5(mt5, "history_orders_get", date_from, date_to)
        if orders is None:
            raise MT5Error(f"MetaTrader5 history_orders_get failed: {_last_error(mt5)}")

        order_by_ticket = {getattr(order, "ticket", None): order for order in orders}
        risk_orders_by_position = _risk_orders_by_position(list(orders))
        buy_type = getattr(mt5, "DEAL_TYPE_BUY", 0)
        sell_type = getattr(mt5, "DEAL_TYPE_SELL", 1)
        entry_in = getattr(mt5, "DEAL_ENTRY_IN", 0)
        entry_inout = getattr(mt5, "DEAL_ENTRY_INOUT", 2)
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
            if getattr(deal, "entry", None) in {entry_in, entry_inout}:
                deal_order_ticket = getattr(deal, "order", None)
                risk_order = order_by_ticket.get(deal_order_ticket)
                if risk_order is None:
                    risk_order = _latest_prior_risk_order(
                        risk_orders_by_position,
                        getattr(deal, "position_id", None),
                        getattr(deal, "time", 0),
                    )
                sl, tp = _risk_values(risk_order)
                if sl is not None:
                    record["sl"] = sl
                if tp is not None:
                    record["tp"] = tp
            records.append(record)

        return {"schema_version": "1.0", "account_id": account_id, "records": records}
    except MT5Error as exc:
        failure = exc
        raise
    except Exception as exc:
        wrapped = MT5Error(f"MetaTrader5 history normalization failed: {exc}")
        failure = wrapped
        raise wrapped from exc
    finally:
        if initialized:
            try:
                _call_mt5(mt5, "shutdown")
            except MT5Error as shutdown_error:
                if failure is None:
                    raise
                failure.add_note(str(shutdown_error))
