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

Python 3.11 or newer. The core runtime uses only the Python standard library.

```bash
python -m pip install -e .
```

For direct collection from a local MetaTrader 5 terminal on Windows, install the optional official MetaQuotes integration:

```bash
python -m pip install -e ".[mt5]"
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

Export recent history from the MT5 terminal that is already configured and logged in on the machine:

```bash
copygraph mt5-export --days 30 --output account-history.json
```

If several terminal installations exist, select one explicitly without storing credentials in CopyGraph:

```bash
copygraph mt5-export --days 30 --terminal "C:\\Program Files\\MetaTrader 5\\terminal64.exe" --output account-history.json
```

Scan every account found across files or directories. Directories are searched recursively for `.csv` and `.json` histories, and account identity comes from each record rather than the filename:

```bash
copygraph batch histories/ account-history.json --output report.json --dashboard dashboard.html
```

Use `--min-confidence 0.8` to change the graph-edge threshold. The batch JSON contains account summaries, every unordered pair analysis, the thresholded similarity graph, and connected clusters. The optional dashboard is one self-contained local HTML file with embedded report data and no CDN or server dependency.

## Matching model

CopyGraph canonicalizes symbols and reconstructs complete position lifecycles before comparing accounts. Candidate trades must share the canonical symbol and either the same side for normal copy or the opposite side for reverse copy. Matching is one-to-one within a bounded time window.

Each matched trade contributes timing, lifecycle, risk and volume-consistency evidence. Volume similarity is based on consistency around the median lot ratio, so a slave account using a stable multiplier such as 0.5x or 3x can still score highly. Rarity weights reduce the influence of frequently repeated patterns. Final confidence also includes overlap and sample-size penalties to limit false positives from one or two coincidental trades.

Lead-lag inference uses the median signed open-time delay of matched trades. Positive delay means account A led account B; negative delay means account B led account A.

## V0.2 workflow

The V0.2 path remains local and read-only with respect to trading. `mt5-export` initializes the official MetaTrader5 Python bridge, reads historical deals and orders for the requested UTC window, enriches opening and reversal deals with historical SL/TP where available, writes normalized JSON, and shuts the bridge down. It validates timezone-aware positive windows, does not place, modify, or close trades, and does not persist login/password/server credentials.

`batch` then reuses the V0.1 ingest, lifecycle reconstruction, matching and graph engine across every discovered account. Netting reversals (`DEAL_ENTRY_INOUT`) are segmented into the closing leg and the residual opposite-side lifecycle; `DEAL_ENTRY_OUT_BY` is treated as a close. Identical inputs produce deterministic pair ordering, graph nodes/clusters and report timestamps derived from the latest event in the input data. Account summaries report only a source count rather than absolute local paths.

The generated dashboard uses the same report only. Account-controlled strings are carried as escaped JSON and written into the DOM with `textContent`; the HTML has no external runtime resources.

## V0.3-A calibration and explainability

V0.3-A keeps the V0.2 raw matching engine unchanged and adds calibration as a separate evidence layer. A labeled calibration dataset is JSON with schema `1.0`, an optional `name`, and `cases[]`. Each case has a unique `case_id`, a `label` of `copy` or `unrelated`, optional expected `orientation`, and either relative `history_a`/`history_b` paths or an embedded raw analysis object. Resolved local paths are not copied into calibration output.

Example dataset:

```json
{
  "schema_version": "1.0",
  "name": "reviewed MT5 pairs",
  "cases": [
    {
      "case_id": "copy-001",
      "label": "copy",
      "orientation": "normal",
      "history_a": "master.json",
      "history_b": "slave.json"
    },
    {
      "case_id": "control-001",
      "label": "unrelated",
      "analysis": {
        "schema_version": "1.0",
        "orientation": "normal",
        "confidence": 0.08
      }
    }
  ]
}
```

Fit and evaluate calibration:

```bash
copygraph calibrate calibration-dataset.json --output calibration.json
```

Diagnostics use leave-one-out evaluation: the held-out case is never scored by a model fitted on that same case. The report includes precision, recall, false-positive rate, F1, orientation diagnostics, a deterministic selected threshold in `calibrated_confidence` space, and a monotonic deployment model fitted only after cross-validated diagnostics are built. If the dataset cannot support valid held-out evaluation, CopyGraph reports calibration unavailable rather than inventing a score.

Explain one account pair, optionally applying a calibration model:

```bash
copygraph explain master.json slave.json --calibration calibration.json --output explanation.json
```

`raw_confidence` remains the exact V0.2 confidence. `calibrated_confidence` is additive and optional. Explanation JSON exposes timing, lifecycle, risk and volume contribution summaries, overlap/sample confidence factors, lead/lag evidence, strongest and weakest matched trades, unmatched counts, and explicit uncertainty warnings such as sparse samples or missing stop evidence. It remains evidence-first and does not claim that copying is proven.

## Roadmap

The remaining V0.3 milestones add forensic investigation views and an incremental SQLite-backed scanner while preserving the local, read-only workflow.
