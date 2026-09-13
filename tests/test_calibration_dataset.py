import json
from datetime import datetime, timedelta, timezone

import pytest

from copygraph.calibration import CalibrationDataset, ScoredCase, load_calibration_dataset


BASE = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def write_account(path, account, delay_s=0, side="buy"):
    rows = ["account,ticket,position,symbol,type,volume,price,time,entry,sl,tp,profit"]
    for index in range(4):
        opened = BASE + timedelta(minutes=index * 10, seconds=delay_s)
        closed = opened + timedelta(minutes=5)
        volume = 0.1 * (index + 1)
        close_side = "sell" if side == "buy" else "buy"
        rows.append(f"{account},{index * 2 + 1},{index},EURUSD,{side},{volume},1.1000,{opened.isoformat()},in,1.0900,1.1200,0")
        rows.append(f"{account},{index * 2 + 2},{index},EURUSD,{close_side},{volume},1.1100,{closed.isoformat()},out,,,10")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_dataset(path, cases, name="fixture calibration", schema_version="1.0"):
    path.write_text(json.dumps({"schema_version": schema_version, "name": name, "cases": cases}), encoding="utf-8")


def test_load_calibration_dataset_scores_relative_histories(tmp_path):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    write_account(left, "master")
    write_account(right, "slave", delay_s=20)
    dataset = tmp_path / "dataset.json"
    write_dataset(dataset, [{"case_id": "copy-1", "label": "copy", "orientation": "normal", "history_a": "left.csv", "history_b": "right.csv"}])

    loaded = load_calibration_dataset(dataset)

    assert isinstance(loaded, CalibrationDataset)
    assert loaded.schema_version == "1.0"
    assert loaded.name == "fixture calibration"
    assert len(loaded.cases) == 1
    case = loaded.cases[0]
    assert isinstance(case, ScoredCase)
    assert case.case_id == "copy-1"
    assert case.label == "copy"
    assert case.expected_orientation == "normal"
    assert case.observed_orientation == "normal"
    assert case.raw_confidence > 0.7
    assert not hasattr(case, "history_a")
    assert str(tmp_path) not in repr(case)


def test_load_calibration_dataset_accepts_embedded_analysis(tmp_path):
    dataset = tmp_path / "dataset.json"
    write_dataset(dataset, [{
        "case_id": "unrelated-1",
        "label": "unrelated",
        "analysis": {"schema_version": "1.0", "orientation": "normal", "confidence": 0.12},
    }], name="")

    loaded = load_calibration_dataset(dataset)

    assert loaded.name is None
    assert loaded.cases == (ScoredCase("unrelated-1", "unrelated", None, 0.12, "normal"),)


def test_load_calibration_dataset_rejects_duplicate_case_ids(tmp_path):
    dataset = tmp_path / "dataset.json"
    analysis = {"schema_version": "1.0", "orientation": "normal", "confidence": 0.8}
    write_dataset(dataset, [
        {"case_id": "same", "label": "copy", "analysis": analysis},
        {"case_id": "same", "label": "unrelated", "analysis": analysis},
    ])
    with pytest.raises(ValueError, match="duplicate case_id"):
        load_calibration_dataset(dataset)


def test_load_calibration_dataset_rejects_invalid_label_and_orientation(tmp_path):
    dataset = tmp_path / "dataset.json"
    analysis = {"schema_version": "1.0", "orientation": "normal", "confidence": 0.8}
    write_dataset(dataset, [{"case_id": "x", "label": "maybe", "analysis": analysis}])
    with pytest.raises(ValueError, match="label"):
        load_calibration_dataset(dataset)
    write_dataset(dataset, [{"case_id": "x", "label": "copy", "orientation": "sideways", "analysis": analysis}])
    with pytest.raises(ValueError, match="orientation"):
        load_calibration_dataset(dataset)


def test_load_calibration_dataset_rejects_ambiguous_or_incomplete_sources(tmp_path):
    dataset = tmp_path / "dataset.json"
    analysis = {"schema_version": "1.0", "orientation": "normal", "confidence": 0.8}
    write_dataset(dataset, [{"case_id": "x", "label": "copy", "history_a": "a.csv", "history_b": "b.csv", "analysis": analysis}])
    with pytest.raises(ValueError, match="either histories or analysis"):
        load_calibration_dataset(dataset)
    write_dataset(dataset, [{"case_id": "x", "label": "copy", "history_a": "a.csv"}])
    with pytest.raises(ValueError, match="history_a and history_b"):
        load_calibration_dataset(dataset)


def test_load_calibration_dataset_rejects_wrong_schema_and_bad_embedded_confidence(tmp_path):
    dataset = tmp_path / "dataset.json"
    write_dataset(dataset, [], schema_version="2.0")
    with pytest.raises(ValueError, match="schema_version"):
        load_calibration_dataset(dataset)
    write_dataset(dataset, [{"case_id": "x", "label": "copy", "analysis": {"schema_version": "1.0", "orientation": "normal", "confidence": 1.5}}])
    with pytest.raises(ValueError, match="confidence"):
        load_calibration_dataset(dataset)

