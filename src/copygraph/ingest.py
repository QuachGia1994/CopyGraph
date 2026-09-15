from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .models import TradeEvent
from .symbols import canonicalize_symbol


def _normalized(record: Mapping[str, object]) -> dict[str, object]:
    return {str(key).strip().lower(): value for key, value in record.items()}


def _pick(record: Mapping[str, object], *names: str, default: object = None) -> object:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return default


def _finite_float(value: object) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric value: {value!r}")
    return number


def _optional_float(value: object, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    return _finite_float(value)


def _timestamp(value: object) -> datetime:
    if value in (None, ""):
        raise ValueError("timestamp is required")
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    text = str(value).strip()
    if text.isdigit():
        numeric = float(text)
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, "%Y.%m.%d %H:%M:%S")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _side(value: object) -> str:
    text = str(value).strip().lower()
    if text in {"0", "buy", "long"}:
        return "BUY"
    if text in {"1", "sell", "short"}:
        return "SELL"
    raise ValueError(f"unsupported side: {value}")


def _event(value: object) -> str:
    text = str(value if value not in (None, "") else "in").strip().lower()
    if text in {"0", "in", "open", "entry", "opening"}:
        return "OPEN"
    if text in {"2", "inout", "reverse", "reversal"}:
        return "REVERSE"
    if text in {"1", "3", "out", "out_by", "outby", "close", "exit", "closing"}:
        return "CLOSE"
    raise ValueError(f"unsupported event: {value}")


def parse_records(records: Iterable[Mapping[str, object]]) -> list[TradeEvent]:
    events: list[TradeEvent] = []
    for raw_record in records:
        record = _normalized(raw_record)
        raw_type = _pick(record, "side", "type", "direction")
        if str(raw_type).strip().lower() in {"balance", "credit"}:
            continue
        account = _pick(record, "account_id", "account", "login")
        ticket = _pick(record, "ticket", "deal", "ticket_id")
        position = _pick(record, "position_id", "position", "positionid", default=ticket)
        symbol = _pick(record, "symbol")
        if symbol in (None, ""):
            raise ValueError("symbol is required")
        volume = _pick(record, "volume", "lots", "lot")
        price = _pick(record, "price")
        timestamp = _pick(record, "timestamp", "time", "time_msc", "time_open")
        missing = [name for name, item in (("account", account), ("ticket", ticket), ("side", raw_type), ("volume", volume), ("price", price), ("timestamp", timestamp)) if item in (None, "")]
        if missing:
            raise ValueError(f"{missing[0]} is required")
        events.append(TradeEvent(
            account_id=str(account),
            ticket=str(ticket),
            position_id=str(position),
            symbol=canonicalize_symbol(symbol),
            side=_side(raw_type),
            volume=_finite_float(volume),
            price=_finite_float(price),
            timestamp=_timestamp(timestamp),
            event=_event(_pick(record, "event", "entry", "action")),
            sl=_optional_float(_pick(record, "sl", "stop_loss")),
            tp=_optional_float(_pick(record, "tp", "take_profit")),
            profit=float(_optional_float(_pick(record, "profit"), 0.0) or 0.0),
        ))
    return sorted(events, key=lambda event: (event.account_id, event.timestamp, event.ticket))


def load_events(path: str | Path) -> list[TradeEvent]:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return parse_records(csv.DictReader(handle))
    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("records", data.get("deals", data.get("history")))
        if not isinstance(data, list):
            raise ValueError("JSON input must contain a list of records")
        return parse_records(data)
    raise ValueError(f"unsupported input format: {source.suffix.lower()}")
