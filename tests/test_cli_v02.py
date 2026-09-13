import json

import pytest

from copygraph import cli


def test_cli_mt5_export_writes_normalized_json(tmp_path, monkeypatch, capsys):
    output = tmp_path / "mt5.json"
    captured = {}

    def fake_collect(date_from, date_to, terminal_path=None):
        captured["days"] = (date_to - date_from).total_seconds() / 86400
        captured["terminal"] = terminal_path
        return {"schema_version": "1.0", "account_id": "123", "records": []}

    monkeypatch.setattr(cli, "collect_mt5_history", fake_collect)
    assert cli.main(["mt5-export", "--days", "7", "--terminal", "C:/MT5/terminal64.exe", "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["account_id"] == "123"
    assert captured["days"] == pytest.approx(7.0)
    assert captured["terminal"] == "C:/MT5/terminal64.exe"
    assert json.loads(capsys.readouterr().out)["schema_version"] == "1.0"


def test_cli_batch_writes_report_and_dashboard(tmp_path, monkeypatch, capsys):
    output = tmp_path / "report.json"
    dashboard = tmp_path / "dashboard.html"
    report = {
        "schema_version": "2.0",
        "generated_at": "2026-09-13T09:00:00Z",
        "min_confidence": 0.8,
        "accounts": [],
        "pairs": [],
        "graph": {"nodes": [], "edges": []},
        "clusters": [],
    }
    captured = {}

    def fake_analyze(inputs, min_confidence=0.7):
        captured["inputs"] = list(inputs)
        captured["threshold"] = min_confidence
        return report

    def fake_dashboard(value, path):
        captured["dashboard_report"] = value
        path.write_text("dashboard", encoding="utf-8")
        return path

    monkeypatch.setattr(cli, "analyze_histories", fake_analyze)
    monkeypatch.setattr(cli, "write_dashboard", fake_dashboard)
    assert cli.main(["batch", "a.json", "folder", "--min-confidence", "0.8", "--output", str(output), "--dashboard", str(dashboard)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert dashboard.read_text(encoding="utf-8") == "dashboard"
    assert captured["inputs"] == ["a.json", "folder"]
    assert captured["threshold"] == pytest.approx(0.8)
    assert captured["dashboard_report"] == report
    assert json.loads(capsys.readouterr().out) == report


def test_cli_batch_rejects_confidence_outside_unit_interval(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["batch", "a.json", "--min-confidence", "1.5", "--output", str(tmp_path / "out.json")])


def test_cli_mt5_export_requires_positive_days(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["mt5-export", "--days", "0", "--output", str(tmp_path / "out.json")])


def test_cli_batch_requires_at_least_one_input(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["batch", "--output", str(tmp_path / "out.json")])


def test_cli_existing_benchmark_still_works(capsys):
    assert cli.main(["benchmark"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["normal"]["confidence"] >= 0.75
