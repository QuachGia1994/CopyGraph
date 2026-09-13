# CopyGraph

CopyGraph is a Python CLI for detecting likely copy-trading relationships between MetaTrader 5 account histories, including normal-direction and reverse-copy behavior across brokers with different symbol naming conventions.

## V0.1 scope

- MT5 CSV/JSON history ingest with common field aliases
- Broker symbol canonicalization for Forex, XAUUSD/GOLD and common index aliases
- Position lifecycle reconstruction from deals, including partial closes and out-of-order rows
- Trade DNA extraction
- Normal and reverse copy matching
- Open/close timing, risk and scale-invariant lot-volume similarity
- Rarity weighting
- False-positive controls using overlap and minimum-sample confidence penalties
- Master/slave lead-lag inference
- Similarity graph and connected components
- JSON evidence payloads with per-trade facts
- Deterministic synthetic benchmark and CLI

CopyGraph outputs similarity evidence. Confidence should be interpreted together with the per-trade facts and sample size.

## Requirements

Python 3.11 or newer. Runtime uses only the Python standard library.

```bash
python -m pip install -e .
```

For development tests:

```bash
python -m pytest
```

## Input

CSV and JSON are supported. Common MT5 aliases are accepted. A minimal record needs account/login, ticket/deal, position id, symbol, side/type, volume/lots, price, timestamp/time and entry/event.

Example CSV:

```csv
account,ticket,position,symbol,type,volume,price,time,entry,sl,tp,profit
1001,11,7,EURUSDm,buy,0.10,1.1000,2026-09-12T10:00:00Z,in,1.0950,1.1100,0
1001,12,7,EURUSDm,sell,0.10,1.1050,2026-09-12T10:05:00Z,out,,,50
```

## CLI

Compare two account-history exports:

```bash
copygraph analyze master.csv slave.csv
```

Write evidence JSON to a file:

```bash
copygraph analyze master.csv slave.csv --output evidence.json
```

Run the deterministic synthetic benchmark:

```bash
copygraph benchmark
```

## Matching model

CopyGraph canonicalizes symbols and reconstructs complete position lifecycles before comparing accounts. Candidate trades must share the canonical symbol and either the same side for normal copy or the opposite side for reverse copy. Matching is one-to-one within a bounded time window.

Each matched trade contributes timing, lifecycle, risk and volume-consistency evidence. Volume similarity is based on consistency around the median lot ratio, so a slave account using a stable multiplier such as 0.5x or 3x can still score highly. Rarity weights reduce the influence of frequently repeated patterns. Final confidence also includes overlap and sample-size penalties to limit false positives from one or two coincidental trades.

Lead-lag inference uses the median signed open-time delay of matched trades. Positive delay means account A led account B; negative delay means account B led account A.

## Roadmap

V0.2 is intentionally outside this release: direct real MT5 history workflow, multi-account batch scanning and a dashboard.
