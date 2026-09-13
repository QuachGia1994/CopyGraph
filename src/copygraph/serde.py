from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from .models import PositionLifecycle, TradeEvent


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("datetime value must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime value must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def trade_event_to_dict(event: TradeEvent) -> dict[str, object]:
    return {
        "account_id": event.account_id,
        "ticket": event.ticket,
        "position_id": event.position_id,
        "symbol": event.symbol,
        "side": event.side,
        "volume": event.volume,
        "price": event.price,
        "timestamp": _iso_z(event.timestamp),
        "event": event.event,
        "sl": event.sl,
        "tp": event.tp,
        "profit": event.profit,
    }


def trade_event_from_dict(payload: Mapping[str, object]) -> TradeEvent:
    return TradeEvent(
        account_id=str(payload["account_id"]),
        ticket=str(payload["ticket"]),
        position_id=str(payload["position_id"]),
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        volume=float(payload["volume"]),
        price=float(payload["price"]),
        timestamp=_parse_datetime(payload["timestamp"]),
        event=str(payload["event"]),
        sl=None if payload.get("sl") is None else float(payload["sl"]),
        tp=None if payload.get("tp") is None else float(payload["tp"]),
        profit=float(payload.get("profit", 0.0)),
    )


def lifecycle_to_dict(position: PositionLifecycle) -> dict[str, object]:
    return {
        "account_id": position.account_id,
        "position_id": position.position_id,
        "symbol": position.symbol,
        "side": position.side,
        "open_time": _iso_z(position.open_time),
        "close_time": None if position.close_time is None else _iso_z(position.close_time),
        "open_price": position.open_price,
        "close_price": position.close_price,
        "volume": position.volume,
        "sl": position.sl,
        "tp": position.tp,
        "profit": position.profit,
        "tickets": list(position.tickets),
    }


def lifecycle_from_dict(payload: Mapping[str, object]) -> PositionLifecycle:
    tickets = payload.get("tickets")
    if not isinstance(tickets, list):
        raise ValueError("tickets must be a list")
    return PositionLifecycle(
        account_id=str(payload["account_id"]),
        position_id=str(payload["position_id"]),
        symbol=str(payload["symbol"]),
        side=str(payload["side"]),
        open_time=_parse_datetime(payload["open_time"]),
        close_time=None if payload.get("close_time") is None else _parse_datetime(payload["close_time"]),
        open_price=float(payload["open_price"]),
        close_price=None if payload.get("close_price") is None else float(payload["close_price"]),
        volume=float(payload["volume"]),
        sl=None if payload.get("sl") is None else float(payload["sl"]),
        tp=None if payload.get("tp") is None else float(payload["tp"]),
        profit=float(payload.get("profit", 0.0)),
        tickets=tuple(str(value) for value in tickets),
    )
