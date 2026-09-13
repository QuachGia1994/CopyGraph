import json

import copygraph.cli as cli


def test_cli_inspect_writes_forensic_json_and_dashboard(tmp_path, monkeypatch):
    analysis = object()
    left = [object()]
    right = [object()]
    report = {"schema_version": "1.0", "accounts": ["a", "b"]}
    captured = {}

    monkeypatch.setattr(cli, "analyze_pair_paths", lambda a, b: (analysis, left, right))
    monkeypatch.setattr(cli, "build_forensic_report", lambda x, y, z, calibration=None: report, raising=False)
    monkeypatch.setattr(cli, "write_forensic_dashboard", lambda payload, output: captured.setdefault("dashboard", payload), raising=False)

    output = tmp_path / "forensic.json"
    dashboard = tmp_path / "forensic.html"
    assert cli.main(["inspect", "a.json", "b.json", "--output", str(output), "--dashboard", str(dashboard)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert captured["dashboard"] == report


def test_cli_inspect_passes_optional_calibration_model(tmp_path, monkeypatch):
    analysis = object()
    left = [object()]
    right = [object()]
    model = object()
    report = {"schema_version": "1.0", "accounts": ["a", "b"]}
    captured = {}

    monkeypatch.setattr(cli, "analyze_pair_paths", lambda a, b: (analysis, left, right))
    monkeypatch.setattr(cli, "load_calibration_model", lambda path: model)

    def fake_build(x, y, z, calibration=None):
        captured["args"] = (x, y, z, calibration)
        return report

    monkeypatch.setattr(cli, "build_forensic_report", fake_build, raising=False)
    output = tmp_path / "forensic.json"
    assert cli.main([
        "inspect",
        "a.json",
        "b.json",
        "--calibration",
        "calibration.json",
        "--output",
        str(output),
    ]) == 0
    assert captured["args"] == (analysis, left, right, model)
