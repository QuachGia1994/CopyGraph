from __future__ import annotations

from pathlib import Path

from .ingest import load_events
from .lifecycle import reconstruct_positions
from .matching import MatchingConfig, PairAnalysis, analyze_pair
from .models import PositionLifecycle


def load_positions(path: str | Path) -> list[PositionLifecycle]:
    return reconstruct_positions(load_events(path))


def analyze_pair_paths(
    path_a: str | Path,
    path_b: str | Path,
    config: MatchingConfig | None = None,
) -> tuple[PairAnalysis, list[PositionLifecycle], list[PositionLifecycle]]:
    positions_a = load_positions(path_a)
    positions_b = load_positions(path_b)
    return analyze_pair(positions_a, positions_b, config), positions_a, positions_b
