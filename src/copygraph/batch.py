from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from itertools import combinations
from datetime import timezone
from pathlib import Path
from typing import Sequence

from .evidence import analysis_to_evidence
from .graph import build_similarity_graph, connected_components
from .ingest import load_events
from .lifecycle import reconstruct_positions
from .matching import analyze_pair


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


def _iso_z(value):
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


def analyze_histories(inputs: Sequence[str | Path], min_confidence: float = 0.7):
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    files = discover_history_files(inputs)
    if not files:
        raise ValueError("No CSV or JSON history files found")
    grouped, sources, latest = _load_histories(files)
    positions = {key: reconstruct_positions(value) for key, value in grouped.items()}
    names = sorted(positions)
    analyses = [analyze_pair(positions[left], positions[right]) for left, right in combinations(names, 2)]
    summaries = []
    for name in names:
        summaries.append({"account_id": name, "position_count": len(positions[name]), "sources": sorted(sources[name], key=str.lower)})
    pairs = [analysis_to_evidence(item) for item in analyses]
    pairs.sort(key=lambda item: (-float(item["confidence"]), tuple(item["accounts"])))
    graph = build_similarity_graph(analyses, min_confidence=min_confidence)
    graph.nodes.update(names)
    edges = list(map(asdict, graph.edges))
    edges.sort(key=lambda item: (-float(item["confidence"]), item["account_a"], item["account_b"]))
    clusters = list(map(sorted, connected_components(graph)))
    return {
        "schema_version": "2.0",
        "generated_at": _iso_z(latest),
        "min_confidence": min_confidence,
        "accounts": summaries,
        "pairs": pairs,
        "graph": {"nodes": sorted(graph.nodes), "edges": edges},
        "clusters": clusters,
    }
