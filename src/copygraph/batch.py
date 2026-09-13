from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from .evidence import analysis_to_evidence
from .graph import build_similarity_graph, connected_components
from .ingest import load_events
from .lifecycle import reconstruct_positions
from .matching import PairAnalysis, analyze_pair
from .models import PositionLifecycle


def discover_history_files(inputs: Sequence[str | Path]) -> list[Path]:
    found: dict[str, Path] = {}
    for raw in inputs:
        path = Path(raw).expanduser()
        candidates = path.rglob("*") if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in {".csv", ".json"}:
                continue
            resolved = candidate.resolve()
            found[str(resolved).lower()] = resolved
    return sorted(found.values(), key=lambda item: str(item).lower())


def _iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_histories(files: list[Path]):
    grouped = defaultdict(list)
    sources = defaultdict(set)
    latest = None
    for path in files:
        events = load_events(path)
        for event in events:
            grouped[event.account_id].append(event)
            sources[event.account_id].add(str(path))
            if latest is None or event.timestamp > latest:
                latest = event.timestamp
    return grouped, sources, latest


def build_pair_analyses(
    positions: Mapping[str, Sequence[PositionLifecycle]],
) -> list[PairAnalysis]:
    names = sorted(positions)
    return [analyze_pair(positions[left], positions[right]) for left, right in combinations(names, 2)]


def assemble_batch_report(
    positions: Mapping[str, Sequence[PositionLifecycle]],
    analyses: Sequence[PairAnalysis],
    source_counts: Mapping[str, int],
    generated_at: datetime | None,
    min_confidence: float = 0.7,
) -> dict[str, object]:
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    names = sorted(positions)
    summaries = [
        {
            "account_id": name,
            "position_count": len(positions[name]),
            "source_count": int(source_counts.get(name, 0)),
        }
        for name in names
    ]
    pairs = [analysis_to_evidence(item) for item in analyses]
    pairs.sort(key=lambda item: (-float(item["confidence"]), tuple(item["accounts"])))
    graph = build_similarity_graph(list(analyses), min_confidence=min_confidence)
    graph.nodes.update(names)
    edges = list(map(asdict, graph.edges))
    edges.sort(key=lambda item: (-float(item["confidence"]), item["account_a"], item["account_b"]))
    clusters = list(map(sorted, connected_components(graph)))
    return {
        "schema_version": "2.0",
        "generated_at": _iso_z(generated_at),
        "min_confidence": min_confidence,
        "accounts": summaries,
        "pairs": pairs,
        "graph": {"nodes": sorted(graph.nodes), "edges": edges},
        "clusters": clusters,
    }


def analyze_histories(inputs: Sequence[str | Path], min_confidence: float = 0.7):
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    files = discover_history_files(inputs)
    if not files:
        raise ValueError("No CSV or JSON history files found")
    grouped, sources, latest = _load_histories(files)
    positions = {key: reconstruct_positions(value) for key, value in grouped.items()}
    source_counts = {name: len(paths) for name, paths in sources.items()}
    analyses = build_pair_analyses(positions)
    return assemble_batch_report(
        positions,
        analyses,
        source_counts,
        latest,
        min_confidence=min_confidence,
    )
