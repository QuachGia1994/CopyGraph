from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import run_synthetic_benchmark
from .evidence import analysis_to_evidence
from .ingest import load_events
from .lifecycle import reconstruct_positions
from .matching import analyze_pair


def analyze_paths(path_a: str | Path, path_b: str | Path) -> dict[str, object]:
    positions_a = reconstruct_positions(load_events(path_a))
    positions_b = reconstruct_positions(load_events(path_b))
    return analysis_to_evidence(analyze_pair(positions_a, positions_b))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="copygraph", description="Detect MT5 copy-trading similarity between account histories")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="Compare two MT5 CSV/JSON histories")
    analyze.add_argument("account_a")
    analyze.add_argument("account_b")
    analyze.add_argument("--output", type=Path)
    subparsers.add_parser("benchmark", help="Run the deterministic synthetic benchmark")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "benchmark":
        payload = run_synthetic_benchmark()
    else:
        payload = analyze_paths(args.account_a, args.account_b)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    output = getattr(args, "output", None)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0
