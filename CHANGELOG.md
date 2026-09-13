# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- Read-only history collection from an already configured local MetaTrader 5 terminal using the optional official MetaTrader5 Python package.
- Historical-order enrichment so normalized opening deals retain available SL/TP risk evidence.
- Deterministic N-account batch analysis across CSV/JSON files and directories, including all unordered pair evidence, similarity graph edges and connected clusters.
- Self-contained static HTML dashboard with embedded report JSON, ranked relationships, cluster summaries and an SVG account network.
- CLI commands `mt5-export` and `batch` with optional dashboard generation and configurable graph confidence threshold.

## [0.1.0] - 2026-09-13

### Added
- MT5 CSV/JSON ingest with common field aliases and symbol canonicalization.
- Position lifecycle reconstruction with partial-close handling.
- Trade DNA and normal/reverse copy matching.
- Timing, lifecycle, risk, volume and rarity-weighted similarity evidence.
- False-positive confidence controls and master/slave lead-lag inference.
- Similarity graph, evidence JSON, deterministic synthetic benchmark and CLI.
- Automated test suite covering 37 V0.1 behaviors.
