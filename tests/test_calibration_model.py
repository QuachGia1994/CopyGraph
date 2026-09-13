import json

import pytest

from copygraph.calibration import (
    CalibrationBlock,
    CalibrationModel,
    ScoredCase,
    apply_calibration,
    calibration_model_from_dict,
    calibration_model_to_dict,
    fit_monotonic_calibrator,
    load_calibration_model,
)


def case(case_id, label, raw):
    return ScoredCase(case_id, label, None, raw, "normal")


def sample_cases():
    return [
        case("u1", "unrelated", 0.10),
        case("c1", "copy", 0.20),
        case("u2", "unrelated", 0.30),
        case("c2", "copy", 0.90),
    ]


def test_fit_monotonic_calibrator_merges_violating_adjacent_blocks():
    model = fit_monotonic_calibrator(sample_cases())
    probabilities = [block.probability for block in model.blocks]
    assert probabilities == sorted(probabilities)
    assert model.blocks == (
        CalibrationBlock(0.10, 0.0, 1),
        CalibrationBlock(0.30, 0.5, 2),
        CalibrationBlock(0.90, 1.0, 1),
    )
    assert apply_calibration(0.25, model) == pytest.approx(0.5)
    assert apply_calibration(0.95, model) == pytest.approx(1.0)


def test_fit_monotonic_calibrator_combines_identical_raw_scores():
    model = fit_monotonic_calibrator([
        case("a", "copy", 0.5),
        case("b", "unrelated", 0.5),
        case("c", "copy", 0.9),
    ])
    assert model.blocks[0] == CalibrationBlock(0.5, 0.5, 2)
    assert apply_calibration(0.5, model) == pytest.approx(0.5)


def test_fit_monotonic_calibrator_is_deterministic_across_input_order():
    cases = sample_cases()
    assert fit_monotonic_calibrator(cases) == fit_monotonic_calibrator(list(reversed(cases)))


def test_calibration_model_serialization_round_trip(tmp_path):
    model = fit_monotonic_calibrator(sample_cases())
    payload = calibration_model_to_dict(model)
    assert payload["schema_version"] == "1.0"
    assert calibration_model_from_dict(payload) == model

    bare = tmp_path / "model.json"
    bare.write_text(json.dumps(payload), encoding="utf-8")
    assert load_calibration_model(bare) == model

    report = tmp_path / "report.json"
    report.write_text(json.dumps({"schema_version": "1.0", "model": payload}), encoding="utf-8")
    assert load_calibration_model(report) == model


def test_load_calibration_model_rejects_report_without_model(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"schema_version": "1.0", "model": None}), encoding="utf-8")
    with pytest.raises(ValueError, match="calibration model unavailable"):
        load_calibration_model(report)


def test_fit_monotonic_calibrator_rejects_empty_cases():
    with pytest.raises(ValueError, match="at least one"):
        fit_monotonic_calibrator([])


def test_apply_calibration_rejects_raw_confidence_outside_unit_interval():
    model = fit_monotonic_calibrator(sample_cases())
    for raw in (-0.01, 1.01):
        with pytest.raises(ValueError, match="raw_confidence"):
            apply_calibration(raw, model)
