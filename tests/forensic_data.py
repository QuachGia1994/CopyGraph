from datetime import datetime, timedelta, timezone

from copygraph.models import PositionLifecycle


BASE = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


def position(
    account,
    position_id,
    *,
    symbol="EURUSD",
    side="BUY",
    open_s=0,
    close_s=120,
    volume=1.0,
    sl=1.09,
    tp=1.12,
):
    opened = BASE + timedelta(seconds=open_s)
    closed = None if close_s is None else BASE + timedelta(seconds=close_s)
    return PositionLifecycle(
        account_id=account,
        position_id=str(position_id),
        symbol=symbol,
        side=side,
        open_time=opened,
        close_time=closed,
        open_price=1.10,
        close_price=None if closed is None else 1.105,
        volume=volume,
        sl=sl,
        tp=tp,
        profit=10.0 if closed is not None else 0.0,
        tickets=(f"{account}-{position_id}",),
    )
