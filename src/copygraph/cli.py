from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .analysis import analyze_pair_paths
from .batch import analyze_histories
from .benchmark import run_synthetic_benchmark
from .calibration import build_calibration_report, load_calibration_dataset, load_calibration_model
from .dashboard import write_dashboard
from .evidence import analysis_to_evidence
from .explain import explain_pair
from .forensic_dashboard import write_forensic_dashboard
from .forensics import build_forensic_report
from .indexer import index_inputs
from .mt5 import collect_mt5_history
from .scanner import inspect_scan_pair, run_scan
from .store import open_store


def analyze_paths(path_a: str | Path, path_b: str | Path) -> dict[str, object]:
    analysis, _, _ = analyze_pair_paths(path_a, path_b)
    return analysis_to_evidence(analysis)


def _unit_interval(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="copygraph", description="Detect MT5 copy-trading similarity between account histories")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="Compare two MT5 CSV/JSON histories")
    analyze.add_argument("account_a")
    analyze.add_argument("account_b")
    analyze.add_argument("--output", type=Path)
    subparsers.add_parser("benchmark", help="Run the deterministic synthetic benchmark")
    mt5_export = subparsers.add_parser("mt5-export", help="Export normalized history from the configured MT5 terminal")
    mt5_export.add_argument("--days", type=_positive_int, required=True)
    mt5_export.add_argument("--terminal")
    mt5_export.add_argument("--output", type=Path, required=True)
    batch = subparsers.add_parser("batch", help="Compare all accounts found in CSV/JSON histories")
    batch.add_argument("inputs", nargs="+")
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--dashboard", type=Path)
    batch.add_argument("--min-confidence", type=_unit_interval, default=0.7)
    calibrate = subparsers.add_parser("calibrate", help="Fit and evaluate labeled confidence calibration")
    calibrate.add_argument("dataset")
    calibrate.add_argument("--output", type=Path, required=True)
    explain = subparsers.add_parser("explain", help="Explain the evidence behind a pair analysis")
    explain.add_argument("account_a")
    explain.add_argument("account_b")
    explain.add_argument("--calibration", type=Path)
    explain.add_argument("--output", type=Path, required=True)
    inspect = subparsers.add_parser("inspect", help="Build a forensic report for two histories")
    inspect.add_argument("account_a")
    inspect.add_argument("account_b")
    inspect.add_argument("--calibration", type=Path)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--dashboard", type=Path)
    inspect.add_argument("--db", type=Path)
    inspect.add_argument("--scan-id")
    index = subparsers.add_parser("index", help="Index the authoritative current set of MT5 histories")
    index.add_argument("inputs", nargs="+")
    index.add_argument("--db", type=Path, required=True)
    scan = subparsers.add_parser("scan", help="Run an incremental scan from the local index")
    scan.add_argument("--db", type=Path, required=True)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--dashboard", type=Path)
    scan.add_argument("--min-confidence", type=_unit_interval, default=0.7)
    return parser


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "inspect" and args.scan_id is not None and args.db is None:
        parser.error("--scan-id requires --db")
    connection = None
    try:
        if args.command == "benchmark":
            payload = run_synthetic_benchmark()
        elif args.command == "analyze":
            payload = analyze_paths(args.account_a, args.account_b)
        elif args.command == "mt5-export":
            now = datetime.now(timezone.utc)
            payload = collect_mt5_history(now - timedelta(days=args.days), now, terminal_path=args.terminal)
        elif args.command == "batch":
            payload = analyze_histories(args.inputs, min_confidence=args.min_confidence)
            if args.dashboard is not None:
                write_dashboard(payload, args.dashboard)
        elif args.command == "calibrate":
            payload = build_calibration_report(load_calibration_dataset(args.dataset))
        elif args.command == "explain":
            analysis, positions_a, positions_b = analyze_pair_paths(args.account_a, args.account_b)
            calibration = load_calibration_model(args.calibration) if args.calibration is not None else None
            payload = explain_pair(analysis, positions_a, positions_b, calibration)
        elif args.command == "index":
            connection = open_store(args.db)
            result = index_inputs(connection, args.inputs)
            payload = {
                "source_count": result.source_count,
                "account_count": result.account_count,
                "changed_accounts": list(result.changed_accounts),
                "unchanged_accounts": list(result.unchanged_accounts),
                "absent_accounts": list(result.absent_accounts),
            }
        elif args.command == "scan":
            connection = open_store(args.db)
            result = run_scan(connection, min_confidence=args.min_confidence)
            payload = result.report
            if args.dashboard is not None:
                write_dashboard(payload["batch"], args.dashboard)
        else:
            calibration = load_calibration_model(args.calibration) if args.calibration is not None else None
            if args.db is not None:
                connection = open_store(args.db)
                payload = inspect_scan_pair(
                    connection,
                    args.account_a,
                    args.account_b,
                    scan_id=args.scan_id,
                    calibration=calibration,
                )
            else:
                analysis, positions_a, positions_b = analyze_pair_paths(args.account_a, args.account_b)
                payload = build_forensic_report(analysis, positions_a, positions_b, calibration)
            if args.dashboard is not None:
                write_forensic_dashboard(payload, args.dashboard)
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        output = getattr(args, "output", None)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    finally:
        if connection is not None:
            connection.close()
