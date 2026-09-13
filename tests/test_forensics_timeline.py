from dataclasses import replace

import pytest

from copygraph.calibration import CalibrationBlock, CalibrationModel
from copygraph.forensics import build_forensic_report
from copygraph.matching import analyze_pair
from tests.forensic_data import position


def test_forensic_timeline_is_chronological_and_traceable():
    left = [position("a", 1, open_s=0), position("a", 2, open_s=600, close_s=720)]
    right = [position("b", 1, open_s=20, close_s=140), position("b", 2, open_s=625, close_s=745)]
    analysis = analyze_pair(left, right)
    report = build_forensic_report(analysis, left, right)

    assert report["schema_version"] == "1.0"
    assert [row["a_position_id"] for row in report["timeline"]] == ["1", "2"]
    assert report["timeline"][0]["a_open_time"] == "2026-09-10T10:00:00Z"
    assert report["timeline"][0]["b_open_time"] == "2026-09-10T10:00:20Z"
    assert report["timeline"][0]["delay_s"] == 20.0
    assert report["timeline"][0]["close_delay_s"] == 20.0
    assert report["timeline"][0]["close_delay_residual_s"] == 0.0
    assert report["delay_summary"]["median_s"] == pytest.approx(22.5)
    assert report["close_delay_consistency"]["coverage"] == pytest.approx(1.0)
    assert report["close_delay_consistency"]["median_abs_residual_s"] == pytest.approx(0.0)


def test_forensic_delay_histogram_uses_sorted_sparse_minute_buckets():
    left = [position("a", 1, open_s=0), position("a", 2, open_s=600), position("a", 3, open_s=1200)]
    right = [position("b", 1, open_s=20), position("b", 2, open_s=685), position("b", 3, open_s=1135)]
    report = build_forensic_report(analyze_pair(left, right), left, right)
    assert report["delay_summary"]["buckets"] == [
        {"lower_s": -120.0, "upper_s": -60.0, "count": 1},
        {"lower_s": 0.0, "upper_s": 60.0, "count": 1},
        {"lower_s": 60.0, "upper_s": 120.0, "count": 1},
    ]


def test_forensic_report_carries_explanation_and_calibration():
    left = [position("a", 1, open_s=0)]
    right = [position("b", 1, open_s=20)]
    analysis = analyze_pair(left, right)
    model = CalibrationModel("1.0", ("fixture",), (CalibrationBlock(1.0, 0.8, 2),))
    report = build_forensic_report(analysis, left, right, model)
    assert report["accounts"] == ["a", "b"]
    assert report["raw_score"] == pytest.approx(analysis.score)
    assert report["raw_confidence"] == pytest.approx(analysis.confidence)
    assert report["calibrated_confidence"] == pytest.approx(0.8)
    assert report["explanation"]["calibrated_confidence"] == pytest.approx(0.8)
    assert report["warnings"] == report["explanation"]["warnings"]


def test_forensic_report_rejects_match_with_missing_lifecycle_id():
    left = [position("a", 1, open_s=0)]
    right = [position("b", 1, open_s=20)]
    analysis = analyze_pair(left, right)
    analysis.matches[0] = replace(analysis.matches[0], a_position_id="missing")
    with pytest.raises(ValueError, match="matched lifecycle not found"):
        build_forensic_report(analysis, left, right)
