from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from .models import PositionLifecycle, TradeEvent


_EPSILON = 1e-9


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


def _segment_id(position_id: str, segment_number: int) -> str:
    return position_id if segment_number == 1 else f"{position_id}#{segment_number}"


def _build_position(
    account_id: str,
    position_id: str,
    opens: list[TradeEvent],
    closes: list[TradeEvent],
    *,
    closed: bool,
) -> PositionLifecycle:
    return PositionLifecycle(
        account_id=account_id,
        position_id=position_id,
        symbol=opens[0].symbol,
        side=opens[0].side,
        open_time=min(event.timestamp for event in opens),
        close_time=max(event.timestamp for event in closes) if closed and closes else None,
        open_price=float(_weighted_price(opens) or opens[0].price),
        close_price=_weighted_price(closes),
        volume=sum(event.volume for event in opens),
        sl=_first_defined(opens, "sl"),
        tp=_first_defined(opens, "tp"),
        profit=sum(event.profit for event in closes),
        tickets=tuple(event.ticket for event in opens + closes),
    )


def reconstruct_positions(events: Iterable[TradeEvent]) -> list[PositionLifecycle]:
    grouped: dict[tuple[str, str], list[TradeEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.account_id, event.position_id)].append(event)

    positions: list[PositionLifecycle] = []
    for (account_id, base_position_id), deals in grouped.items():
        ordered = sorted(deals, key=lambda event: (event.timestamp, event.ticket))
        opens: list[TradeEvent] = []
        closes: list[TradeEvent] = []
        remaining_volume = 0.0
        segment_number = 0

        def start_segment(event: TradeEvent, volume: float, ticket_suffix: str = "") -> None:
            nonlocal opens, closes, remaining_volume, segment_number
            segment_number += 1
            opens = [replace(event, event="OPEN", volume=volume, profit=0.0, ticket=f"{event.ticket}{ticket_suffix}")]
            closes = []
            remaining_volume = volume

        def finish_segment(*, closed: bool) -> None:
            nonlocal opens, closes, remaining_volume
            if not opens:
                return
            positions.append(_build_position(
                account_id,
                _segment_id(base_position_id, segment_number),
                opens,
                closes,
                closed=closed,
            ))
            opens = []
            closes = []
            remaining_volume = 0.0

        for event in ordered:
            if event.event == "OPEN":
                if not opens:
                    start_segment(event, event.volume)
                else:
                    opens.append(event)
                    remaining_volume += event.volume
                continue

            if event.event == "CLOSE":
                if not opens or remaining_volume <= _EPSILON:
                    continue
                close_volume = min(event.volume, remaining_volume)
                if close_volume <= _EPSILON:
                    continue
                closes.append(replace(event, volume=close_volume))
                remaining_volume -= close_volume
                if remaining_volume <= _EPSILON:
                    finish_segment(closed=True)
                continue

            if event.event == "REVERSE":
                if not opens or remaining_volume <= _EPSILON:
                    continue
                close_volume = min(event.volume, remaining_volume)
                if close_volume > _EPSILON:
                    closes.append(replace(event, event="CLOSE", volume=close_volume))
                residual_volume = max(0.0, event.volume - close_volume)
                finish_segment(closed=True)
                if residual_volume > _EPSILON:
                    start_segment(event, residual_volume, ticket_suffix="#open")
                continue

            raise ValueError(f"unsupported trade event: {event.event}")

        if opens:
            finish_segment(closed=False)

    return sorted(positions, key=lambda position: (position.account_id, position.open_time, position.position_id))
