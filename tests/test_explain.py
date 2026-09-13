import json
from datetime import datetime, timedelta, timezone

import pytest

from copygraph.calibration import CalibrationBlock, CalibrationModel
from copygraph.explain import explain_pair
from copygraph.matching import MatchingConfig, analyze_pair
from copygraph.models import PositionLifecycle


BASE = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def pos(account, pid, open_s=0, volume=1.0, sl=1.09, side="BUY"):
    opened = BASE + timedelta(seconds=open_s)
    return PositionLifecycle(
        account_id=account,
        position_id=str(pid),
        symbol="EURUSD",
        side=side,
        open_time=opened,
        close_time=opened + timedelta(minutes=5),
        open_price=1.10,
        close_price=1.11,
        volume=volume,
        sl=sl,
        tp=1.12,
        profit=10.0,
        tickets=(str(pid),),
    )


def copied_pair(count=4, delay=20, missing_stops=False):
    left = [pos("a", i, open_s=i * 600, volume=0.1 * (i + 1), sl=None if missing_stops else 1.09) for i in range(count)]
    right = [pos("b", i, open_s=i * 600 + delay, volume=0.2 * (i + 1), sl=None if missing_stops else 1.09) for i in range(count)]
    return left, right


def test_explanation_components_reconstruct_raw_score():
    left, right = copied_pair()
    analysis = analyze_pair(left, right)
    explanation = explain_pair(analysis, left, right)
    components = explanation["components"]
    assert sum(item["weighted_contribution"] for item in components.values()) == pytest.approx(analysis.score)
    assert explanation["raw_score"] == pytest.approx(analysis.score)
    assert explanation["raw_confidence"] == pytest.approx(analysis.confidence)
    assert explanation["confidence_factors"] == {
        "overlap": analysis.overlap_factor,
        "sample": analysis.sample_factor,
    }
    assert explanation["orientation"] == analysis.orientation
    assert explanation["lead_account"] == analysis.lead_account


def test_explanation_warns_for_sparse_missing_risk():
    left = [pos("a", 1, sl=None)]
    right = [pos("b", 1, open_s=10, sl=None)]
    analysis = analyze_pair(left, right)
    explanation = explain_pair(analysis, left, right)
    assert "sparse_sample" in explanation["warnings"]
    assert "missing_stop_evidence" in explanation["warnings"]


def test_explanation_applies_calibration_and_orders_matches():
    left, right = copied_pair()
    analysis = analyze_pair(left, right)
    model = CalibrationModel("1.0", ("fixture",), (
        CalibrationBlock(0.5, 0.2, 2),
        CalibrationBlock(1.0, 0.95, 2),
    ))
    explanation = explain_pair(analysis, left, right, model)
    assert explanation["calibrated_confidence"] == pytest.approx(0.95)
    strongest = explanation["strongest_matches"]
    weakest = explanation["weakest_matches"]
    assert strongest == sorted(strongest, key=lambda item: (-item["score"], item["a_position_id"], item["b_position_id"]))
    assert weakest == sorted(weakest, key=lambda item: (item["score"], item["a_position_id"], item["b_position_id"]))


def test_explanation_reports_unmatched_counts_and_low_overlap():
    left, right = copied_pair(count=4)
    right = right[:1]
    analysis = analyze_pair(left, right, MatchingConfig(min_matches=1))
    explanation = explain_pair(analysis, left, right)
    assert explanation["unmatched_counts"] == {"a": 3, "b": 0}
    assert "low_overlap" in explanation["warnings"]


def test_explanation_warns_for_unstable_volume_ratio():
    left = [pos("a", i, open_s=i * 600, volume=1.0) for i in range(3)]
    right = [
        pos("b", 0, open_s=20, volume=0.5),
        pos("b", 1, open_s=620, volume=1.0),
        pos("b", 2, open_s=1220, volume=2.0),
    ]
    explanation = explain_pair(analyze_pair(left, right), left, right)
    assert "unstable_volume_ratio" in explanation["warnings"]


def test_explanation_is_stable_json_data():
    left, right = copied_pair()
    analysis = analyze_pair(left, right)
    first = json.dumps(explain_pair(analysis, left, right), sort_keys=True, separators=(",", ":"))
    second = json.dumps(explain_pair(analysis, left, right), sort_keys=True, separators=(",", ":"))
    assert first == second
