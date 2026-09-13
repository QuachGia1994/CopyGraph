# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Add labeled monotonic confidence calibration with leave-one-out threshold diagnostics for precision, recall, false-positive rate and F1.
- Add evidence-first confidence explanations with timing, lifecycle, risk and volume contributions, confidence penalties, match ordering and uncertainty warnings.
- Add forensic JSON with traceable matched timelines, delay/close consistency, lot-ratio drift, risk coverage, symbol breakdown, unmatched collisions, and supporting/contradictory evidence.
- Add a self-contained forensic dashboard and stateless `inspect` CLI with optional calibrated confidence.
- Add `calibrate` and `explain` CLI commands with optional calibrated confidence output.
- Add local SQLite indexing with authoritative source-set semantics, immutable account snapshots, and privacy-safe source identifiers.
- Add engine-versioned incremental pair caching, immutable historical scans, persistent forensic inspect, and `index`/`scan` CLI commands.

### Changed
- Expose overlap, sample and matching-window factors from raw pair analysis without changing V0.2 scoring semantics.
- Refactor stateless batch report assembly so persistent scans reuse the exact same graph/report pipeline.
- Define the V0.3 architecture for calibrated confidence, forensic evidence reports, and incremental SQLite-backed multi-account scanning.

## [0.2.0] - 2026-09-13

### Added
- Read-only history collection from an already configured local MetaTrader 5 terminal using the optional official MetaTrader5 Python package.
- Historical-order enrichment so normalized opening deals retain available SL/TP risk evidence.
- Deterministic N-account batch analysis across CSV/JSON files and directories, including all unordered pair evidence, similarity graph edges and connected clusters.
- Self-contained static HTML dashboard with embedded report JSON, ranked relationships, cluster summaries and an SVG account network.
- CLI commands `mt5-export` and `batch` with optional dashboard generation and configurable graph confidence threshold.

### Fixed
- Normalize unexpected MetaTrader5 bridge/history-record exceptions into `MT5Error`, validate timezone-aware positive history windows, and preserve primary failures if shutdown also fails.
- Prevent SL/TP enrichment from borrowing explicit-zero or future orders from the same position.
- Reconstruct MT5 netting reversals (`DEAL_ENTRY_INOUT`) as separate lifecycle segments and support `DEAL_ENTRY_OUT_BY` close semantics.
- Remove absolute local source paths from batch report account summaries; expose only `source_count`.

## [0.1.0] - 2026-09-13

### Added
- MT5 CSV/JSON ingest with common field aliases and symbol canonicalization.
- Position lifecycle reconstruction with partial-close handling.
- Trade DNA and normal/reverse copy matching.
- Timing, lifecycle, risk, volume and rarity-weighted similarity evidence.
- False-positive confidence controls and master/slave lead-lag inference.
- Similarity graph, evidence JSON, deterministic synthetic benchmark and CLI.
- Automated test suite covering 37 V0.1 behaviors.
