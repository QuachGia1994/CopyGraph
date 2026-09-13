import pytest

from copygraph.forensics import build_forensic_report
from copygraph.matching import analyze_pair
from tests.forensic_data import position


def test_forensic_report_tracks_lot_ratio_drift_and_risk_coverage():
    left = [
        position("a", 1, open_s=0, volume=1.0),
        position("a", 2, open_s=600, volume=1.0),
        position("a", 3, open_s=1200, volume=1.0),
    ]
    right = [
        position("b", 1, open_s=20, volume=1.0),
        position("b", 2, open_s=620, volume=1.5),
        position("b", 3, open_s=1220, volume=3.0, sl=None),
    ]
    report = build_forensic_report(analyze_pair(left, right), left, right)
    assert report["lot_ratio"]["median"] == 1.5
    assert report["lot_ratio"]["drift_factor"] == 3.0
    assert [row["ratio"] for row in report["lot_ratio"]["series"]] == [1.0, 1.5, 3.0]
    assert report["risk_evidence"] == {"covered_matches": 2, "total_matches": 3, "coverage": pytest.approx(2 / 3)}


def test_unmatched_near_window_is_reported_with_traceable_ids():
    left = [position("a", 1, open_s=15), position("a", 2, open_s=0)]
    right = [position("b", 1, open_s=20)]
    analysis = analyze_pair(left, right)
    report = build_forensic_report(analysis, left, right)
    assert report["unmatched_counts"] == {"a": 1, "b": 0}
    row = report["unmatched_near_window"][0]
    assert row["unmatched_account"] == "a"
    assert row["unmatched_position_id"] == "2"
    assert row["nearest_other_position_id"] == "1"
    assert row["nearest_other_was_matched"] is True
    assert any(item["kind"] == "near_window_collision" for item in report["contradictory_evidence"])


def test_symbol_breakdown_is_ranked_by_matched_count_then_symbol():
    left = [
        position("a", 1, symbol="EURUSD", open_s=0),
        position("a", 2, symbol="EURUSD", open_s=600),
        position("a", 3, symbol="USDJPY", open_s=1200),
    ]
    right = [
        position("b", 1, symbol="EURUSD", open_s=20),
        position("b", 2, symbol="EURUSD", open_s=620),
        position("b", 4, symbol="GBPUSD", open_s=1800),
    ]
    report = build_forensic_report(analyze_pair(left, right), left, right)
    assert [item["symbol"] for item in report["symbol_breakdown"]] == ["EURUSD", "GBPUSD", "USDJPY"]
    eurusd = report["symbol_breakdown"][0]
    assert eurusd["matched_count"] == 2
    assert eurusd["unmatched_a"] == 0
    assert eurusd["unmatched_b"] == 0


def test_unrelated_pair_exposes_contradictory_evidence_without_fake_matches():
    left = [position("a", 1, symbol="EURUSD", open_s=0)]
    right = [position("b", 1, symbol="USDJPY", open_s=20)]
    report = build_forensic_report(analyze_pair(left, right), left, right)
    assert report["supporting_matches"] == []
    assert report["contradictory_matches"] == []
    assert {item["kind"] for item in report["contradictory_evidence"]} >= {"no_matched_trades", "unmatched_positions"}


def test_reverse_orientation_near_window_requires_opposite_side():
    left = [position("a", 1, side="BUY", open_s=15), position("a", 2, side="BUY", open_s=0)]
    right = [position("b", 1, side="SELL", open_s=20)]
    analysis = analyze_pair(left, right)
    assert analysis.orientation == "reverse"
    report = build_forensic_report(analysis, left, right)
    assert report["unmatched_near_window"][0]["unmatched_position_id"] == "2"


def test_reversal_segment_ids_survive_forensic_evidence():
    left = [position("a", "7#2", open_s=0)]
    right = [position("b", "9#2", open_s=20)]
    report = build_forensic_report(analyze_pair(left, right), left, right)
    assert report["timeline"][0]["a_position_id"] == "7#2"
    assert report["supporting_matches"][0]["b_position_id"] == "9#2"
