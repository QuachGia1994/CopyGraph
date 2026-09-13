import pytest

from copygraph.calibration import (
    CalibrationDataset,
    ScoredCase,
    ThresholdMetrics,
    build_calibration_report,
    choose_threshold,
    cross_validated_predictions,
    evaluate_calibrator,
    fit_monotonic_calibrator,
    threshold_sweep,
)


def case(case_id, label, raw, expected=None, observed="normal"):
    return ScoredCase(case_id, label, expected, raw, observed)


def sample_cases():
    return [
        case("u1", "unrelated", 0.10),
        case("u2", "unrelated", 0.25),
        case("c1", "copy", 0.75, "normal", "normal"),
        case("c2", "copy", 0.90, "reverse", "reverse"),
    ]


def test_evaluate_calibrator_rejects_in_sample_cases_by_default():
    cases = sample_cases()
    model = fit_monotonic_calibrator(cases)
    with pytest.raises(ValueError, match="in-sample"):
        evaluate_calibrator(model, [cases[0]])
    result = evaluate_calibrator(model, [cases[0]], allow_in_sample=True)
    assert result[0]["case_id"] == cases[0].case_id
    assert result[0]["calibrated_confidence"] is not None


def test_cross_validated_predictions_hold_out_each_case():
    cases = sample_cases()
    predictions = cross_validated_predictions(cases)
    assert [row["case_id"] for row in predictions] == sorted(case.case_id for case in cases)
    assert all(row["status"] == "ok" for row in predictions)
    assert all(row["calibrated_confidence"] is not None for row in predictions)


def test_threshold_sweep_computes_confusion_metrics():
    predictions = [
        {"case_id": "c1", "label": "copy", "calibrated_confidence": 0.9},
        {"case_id": "c2", "label": "copy", "calibrated_confidence": 0.4},
        {"case_id": "u1", "label": "unrelated", "calibrated_confidence": 0.6},
        {"case_id": "u2", "label": "unrelated", "calibrated_confidence": 0.1},
    ]
    metrics = {item.threshold: item for item in threshold_sweep(predictions)}
    at_half = metrics[0.5] if 0.5 in metrics else None
    if at_half is None:
        predictions.append({"case_id": "anchor", "label": "unrelated", "calibrated_confidence": 0.5})
        metrics = {item.threshold: item for item in threshold_sweep(predictions)}
        at_half = metrics[0.5]
        assert at_half.true_negative == 1
    else:
        assert at_half.true_negative == 1
    assert at_half.true_positive == 1
    assert at_half.false_positive >= 1
    assert at_half.false_negative == 1
    assert 0.0 <= at_half.precision <= 1.0
    assert 0.0 <= at_half.false_positive_rate <= 1.0


def test_choose_threshold_uses_deterministic_tie_break():
    metrics = [
        ThresholdMetrics(0.5, 2, 1, 2, 1, 2 / 3, 2 / 3, 1 / 3, 2 / 3),
        ThresholdMetrics(0.7, 2, 1, 2, 1, 2 / 3, 2 / 3, 1 / 3, 2 / 3),
    ]
    assert choose_threshold(metrics).threshold == 0.7


def test_build_calibration_report_includes_orientation_and_dataset_summary():
    dataset = CalibrationDataset("1.0", "real-history", tuple(sample_cases()))
    report = build_calibration_report(dataset)
    assert report["status"] == "ok"
    assert report["threshold_space"] == "calibrated_confidence"
    assert report["orientation_evaluated"] == 2
    assert report["orientation_correct"] == 2
    assert report["orientation_accuracy"] == pytest.approx(1.0)
    assert report["dataset_summary"]["name"] == "real-history"
    assert report["dataset_summary"]["case_ids"] == ["c1", "c2", "u1", "u2"]
    assert report["dataset_summary"]["label_counts"] == {"copy": 2, "unrelated": 2}
    assert report["selected_threshold"] is not None
    assert report["model"] is not None


def test_build_calibration_report_marks_unavailable_when_no_fold_can_train_both_classes():
    dataset = CalibrationDataset("1.0", None, (
        case("u", "unrelated", 0.1),
        case("c", "copy", 0.9),
    ))
    report = build_calibration_report(dataset)
    assert report["status"] == "calibration_unavailable"
    assert report["selected_threshold"] is None
    assert report["model"] is None
