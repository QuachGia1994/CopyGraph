import json

import copygraph.cli as cli


def test_cli_calibrate_writes_report(tmp_path, monkeypatch):
    report = {"schema_version": "1.0", "status": "ok", "selected_threshold": 0.7}
    dataset = object()
    monkeypatch.setattr(cli, "load_calibration_dataset", lambda path: dataset, raising=False)
    monkeypatch.setattr(cli, "build_calibration_report", lambda value: report, raising=False)
    output = tmp_path / "calibration.json"

    assert cli.main(["calibrate", "dataset.json", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_cli_explain_uses_optional_calibration(tmp_path, monkeypatch):
    analysis = object()
    left = [object()]
    right = [object()]
    model = object()
    explanation = {"schema_version": "1.0", "raw_confidence": 0.8, "calibrated_confidence": 0.9}
    captured = {}

    monkeypatch.setattr(cli, "analyze_pair_paths", lambda a, b: (analysis, left, right))
    monkeypatch.setattr(cli, "load_calibration_model", lambda path: model, raising=False)

    def fake_explain(value, account_a, account_b, calibration=None):
        captured["args"] = (value, account_a, account_b, calibration)
        return explanation

    monkeypatch.setattr(cli, "explain_pair", fake_explain, raising=False)
    output = tmp_path / "explanation.json"

    assert cli.main([
        "explain",
        "a.json",
        "b.json",
        "--calibration",
        "calibration.json",
        "--output",
        str(output),
    ]) == 0
    assert captured["args"] == (analysis, left, right, model)
    assert json.loads(output.read_text(encoding="utf-8")) == explanation
