import json
from datetime import datetime, timedelta, timezone

BASE = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


def rows(account, symbol="EURUSD", delay=0):
    out = []
    for i in range(4):
        opened = BASE + timedelta(minutes=i * 10, seconds=delay)
        closed = opened + timedelta(minutes=5)
        out.append({"account_id": account, "ticket": i * 2 + 1, "position_id": i, "symbol": symbol, "type": "buy", "volume": i + 1, "price": 1.1, "time": opened.isoformat(), "entry": "in", "sl": 1.09, "tp": 1.12})
        out.append({"account_id": account, "ticket": i * 2 + 2, "position_id": i, "symbol": symbol, "type": "sell", "volume": i + 1, "price": 1.11, "time": closed.isoformat(), "entry": "out"})
    return out


def put(path, data):
    path.write_text(json.dumps({"records": data}), encoding="utf-8")
