import json

from copygraph.evidence import analysis_to_evidence
from copygraph.graph import build_similarity_graph, connected_components
from copygraph.matching import MatchedTrade, PairAnalysis


def analysis(a, b, confidence, orientation="normal"):
    match = MatchedTrade(
        a_position_id="a1",
        b_position_id="b1",
        delay_s=12.0,
        time_similarity=0.95,
        lifecycle_similarity=1.0,
        risk_similarity=0.9,
        volume_similarity=1.0,
        rarity_weight=0.8,
        score=0.96,
    )
    return PairAnalysis(
        account_a=a,
        account_b=b,
        orientation=orientation,
        score=0.96,
        confidence=confidence,
        matches=[match],
        volume_similarity=1.0,
        lead_account=a,
        median_delay_s=12.0,
        total_a=4,
        total_b=4,
        overlap_factor=0.75,
        sample_factor=1.0,
        matching_window_s=360.0,
    )


def test_graph_only_keeps_edges_above_confidence_threshold():
    graph = build_similarity_graph([analysis("a", "b", 0.9), analysis("a", "c", 0.3)], min_confidence=0.7)
    assert {(edge.account_a, edge.account_b) for edge in graph.edges} == {("a", "b")}
    assert graph.nodes == {"a", "b", "c"}


def test_connected_components_group_transitive_copy_cluster():
    graph = build_similarity_graph([analysis("a", "b", 0.9), analysis("b", "c", 0.85), analysis("x", "y", 0.95)])
    components = {frozenset(component) for component in connected_components(graph)}
    assert frozenset({"a", "b", "c"}) in components
    assert frozenset({"x", "y"}) in components


def test_evidence_payload_is_json_serializable_and_versioned():
    payload = analysis_to_evidence(analysis("a", "b", 0.9))
    assert payload["schema_version"] == "1.0"
    assert json.loads(json.dumps(payload))["accounts"] == ["a", "b"]


def test_evidence_contains_per_trade_match_facts():
    payload = analysis_to_evidence(analysis("a", "b", 0.9))
    assert payload["matches"][0]["a_position_id"] == "a1"
    assert payload["matches"][0]["delay_s"] == 12.0


def test_evidence_preserves_reverse_copy_orientation():
    payload = analysis_to_evidence(analysis("a", "b", 0.91, orientation="reverse"))
    assert payload["orientation"] == "reverse"
    assert payload["lead_account"] == "a"


def test_evidence_exposes_confidence_factors_and_matching_window():
    payload = analysis_to_evidence(analysis("a", "b", 0.9))
    assert payload["confidence_factors"] == {"overlap": 0.75, "sample": 1.0}
    assert payload["matching_window_s"] == 360.0
