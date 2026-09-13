from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TradeEvent:
    account_id: str
    ticket: str
    position_id: str
    symbol: str
    side: str
    volume: float
    price: float
    timestamp: datetime
    event: str
    sl: float | None = None
    tp: float | None = None
    profit: float = 0.0


@dataclass(frozen=True, slots=True)
class PositionLifecycle:
    account_id: str
    position_id: str
    symbol: str
    side: str
    open_time: datetime
    close_time: datetime | None
    open_price: float
    close_price: float | None
    volume: float
    sl: float | None
    tp: float | None
    profit: float
    tickets: tuple[str, ...]

    @property
    def duration_s(self) -> float | None:
        if self.close_time is None:
            return None
        return (self.close_time - self.open_time).total_seconds()

    @property
    def risk_distance(self) -> float:
        if self.sl is None:
            return 0.0
        return abs(self.open_price - self.sl)

    @property
    def reward_distance(self) -> float:
        if self.tp is None:
            return 0.0
        return abs(self.tp - self.open_price)
