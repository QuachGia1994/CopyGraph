from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import PositionLifecycle, TradeEvent


def _weighted_price(events: list[TradeEvent]) -> float | None:
    total_volume = sum(event.volume for event in events)
    if total_volume <= 0:
        return None
    return sum(event.price * event.volume for event in events) / total_volume


def _first_defined(events: list[TradeEvent], field: str) -> float | None:
    for event in events:
        value = getattr(event, field)
        if value is not None:
            return value
    return None


def reconstruct_positions(events: Iterable[TradeEvent]) -> list[PositionLifecycle]:
    grouped: dict[tuple[str, str], list[TradeEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.account_id, event.position_id)].append(event)

    positions: list[PositionLifecycle] = []
    for (account_id, position_id), deals in grouped.items():
        ordered = sorted(deals, key=lambda event: (event.timestamp, event.ticket))
        opens = [event for event in ordered if event.event == "OPEN"]
        if not opens:
            continue
        closes = [event for event in ordered if event.event == "CLOSE"]
        open_volume = sum(event.volume for event in opens)
        close_volume = sum(event.volume for event in closes)
        is_closed = bool(closes) and close_volume + 1e-9 >= open_volume
        positions.append(PositionLifecycle(
            account_id=account_id,
            position_id=position_id,
            symbol=opens[0].symbol,
            side=opens[0].side,
            open_time=min(event.timestamp for event in opens),
            close_time=max(event.timestamp for event in closes) if is_closed else None,
            open_price=float(_weighted_price(opens) or opens[0].price),
            close_price=_weighted_price(closes),
            volume=open_volume,
            sl=_first_defined(opens, "sl"),
            tp=_first_defined(opens, "tp"),
            profit=sum(event.profit for event in closes),
            tickets=tuple(event.ticket for event in ordered),
        ))
    return sorted(positions, key=lambda position: (position.account_id, position.open_time, position.position_id))
