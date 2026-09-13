from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .matching import PairAnalysis, analyze_pair
from .models import PositionLifecycle


_BASE = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def _position(account: str, index: int, delay_s: int = 0, side: str = "BUY", volume_scale: float = 1.0, symbol: str = "EURUSD", far_offset_s: int = 0) -> PositionLifecycle:
    opened = _BASE + timedelta(minutes=index * 10, seconds=delay_s + far_offset_s)
    closed = opened + timedelta(minutes=5)
    volume = 0.1 * (index + 1) * volume_scale
    return PositionLifecycle(
        account_id=account,
        position_id=str(index),
        symbol=symbol,
        side=side,
        open_time=opened,
        close_time=closed,
        open_price=1.10,
        close_price=1.11,
        volume=volume,
        sl=1.09,
        tp=1.12,
        profit=10.0,
        tickets=(str(index),),
    )


def _summary(analysis: PairAnalysis) -> dict[str, object]:
    return {
        "orientation": analysis.orientation,
        "score": analysis.score,
        "confidence": analysis.confidence,
        "matches": len(analysis.matches),
        "lead_account": analysis.lead_account,
        "median_delay_s": analysis.median_delay_s,
    }


def run_synthetic_benchmark() -> dict[str, dict[str, object]]:
    delays = [5, 12, 20, 30, 45, 60]
    master = [_position("master", index) for index in range(len(delays))]
    normal = [_position("normal_slave", index, delay_s=delay, volume_scale=2.5) for index, delay in enumerate(delays)]
    reverse = [_position("reverse_slave", index, delay_s=delay, side="SELL", volume_scale=1.7) for index, delay in enumerate(delays)]
    unrelated = [_position("unrelated", index, symbol="USDJPY", far_offset_s=20_000 + index * 100) for index in range(len(delays))]
    return {
        "normal": _summary(analyze_pair(master, normal)),
        "reverse": _summary(analyze_pair(master, reverse)),
        "unrelated": _summary(analyze_pair(master, unrelated)),
    }
