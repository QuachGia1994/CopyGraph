from __future__ import annotations

from dataclasses import dataclass

from .models import PositionLifecycle
from .symbols import canonicalize_symbol


@dataclass(frozen=True, slots=True)
class TradeDNA:
    position_id: str
    symbol: str
    side: str
    open_epoch_s: int
    duration_s: float | None
    volume: float
    risk_distance: float
    reward_distance: float


def trade_dna(position: PositionLifecycle) -> TradeDNA:
    return TradeDNA(
        position_id=position.position_id,
        symbol=canonicalize_symbol(position.symbol),
        side=position.side,
        open_epoch_s=int(position.open_time.timestamp()),
        duration_s=position.duration_s,
        volume=position.volume,
        risk_distance=position.risk_distance,
        reward_distance=position.reward_distance,
    )
