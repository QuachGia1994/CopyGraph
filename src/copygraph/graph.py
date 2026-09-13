from __future__ import annotations

from dataclasses import dataclass, field

from .matching import PairAnalysis


@dataclass(frozen=True, slots=True)
class SimilarityEdge:
    account_a: str
    account_b: str
    confidence: float
    score: float
    orientation: str
    lead_account: str | None


@dataclass(slots=True)
class SimilarityGraph:
    nodes: set[str] = field(default_factory=set)
    edges: list[SimilarityEdge] = field(default_factory=list)


def build_similarity_graph(analyses, min_confidence: float = 0.7) -> SimilarityGraph:
    graph = SimilarityGraph()
    for analysis in analyses:
        if analysis.account_a is not None:
            graph.nodes.add(analysis.account_a)
        if analysis.account_b is not None:
            graph.nodes.add(analysis.account_b)
        if analysis.account_a is None or analysis.account_b is None or analysis.confidence < min_confidence:
            continue
        graph.edges.append(SimilarityEdge(
            account_a=analysis.account_a,
            account_b=analysis.account_b,
            confidence=analysis.confidence,
            score=analysis.score,
            orientation=analysis.orientation,
            lead_account=analysis.lead_account,
        ))
    return graph


def connected_components(graph: SimilarityGraph) -> list[set[str]]:
    adjacency = {node: set() for node in graph.nodes}
    for edge in graph.edges:
        adjacency.setdefault(edge.account_a, set()).add(edge.account_b)
        adjacency.setdefault(edge.account_b, set()).add(edge.account_a)
    remaining = set(adjacency)
    components: list[set[str]] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        component: set[str] = set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency.get(node, ()))
        remaining.difference_update(component)
        components.append(component)
    return components
