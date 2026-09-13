import json

import pytest

import copygraph.cli as cli
from copygraph.indexer import IndexResult
from copygraph.scanner import ScanRunResult


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_cli_index_prints_summary_and_closes_connection(tmp_path, monkeypatch, capsys):
    connection = FakeConnection()
    result = IndexResult(2, 3, ("a",), ("b", "c"), ())
    monkeypatch.setattr(cli, "open_store", lambda path: connection)
    monkeypatch.setattr(cli, "index_inputs", lambda conn, inputs: result)
    assert cli.main(["index", "histories", "--db", str(tmp_path / "copygraph.db")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed_accounts"] == ["a"]
    assert payload["unchanged_accounts"] == ["b", "c"]
    assert connection.closed is True


def test_cli_scan_writes_envelope_and_batch_dashboard(tmp_path, monkeypatch):
    connection = FakeConnection()
    report = {"schema_version": "1.0", "scan_id": "abc", "engine_version": "1", "batch": {"schema_version": "2.0", "accounts": []}}
    monkeypatch.setattr(cli, "open_store", lambda path: connection)
    monkeypatch.setattr(cli, "run_scan", lambda conn, min_confidence=0.7: ScanRunResult("abc", report, 2, 1))
    captured = {}
    monkeypatch.setattr(cli, "write_dashboard", lambda payload, output: captured.setdefault("dashboard", payload))
    output = tmp_path / "scan.json"
    dashboard = tmp_path / "dashboard.html"
    assert cli.main(["scan", "--db", str(tmp_path / "copygraph.db"), "--output", str(output), "--dashboard", str(dashboard)]) == 0
    assert json.loads(output.read_text()) == report
    assert captured["dashboard"] == report["batch"]
    assert connection.closed is True


def test_cli_inspect_db_mode_dispatches_account_ids(tmp_path, monkeypatch):
    connection = FakeConnection()
    report = {"schema_version": "1.0", "accounts": ["a", "b"]}
    monkeypatch.setattr(cli, "open_store", lambda path: connection)
    monkeypatch.setattr(cli, "inspect_scan_pair", lambda conn, a, b, scan_id=None, calibration=None: report)
    output = tmp_path / "forensic.json"
    assert cli.main(["inspect", "a", "b", "--db", str(tmp_path / "copygraph.db"), "--scan-id", "old", "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == report
    assert connection.closed is True


def test_cli_stateless_inspect_does_not_open_store(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "open_store", lambda path: (_ for _ in ()).throw(AssertionError("SQLite must not open")))
    monkeypatch.setattr(cli, "analyze_pair_paths", lambda a, b: (object(), [object()], [object()]))
    report = {"schema_version": "1.0", "accounts": ["a", "b"]}
    monkeypatch.setattr(cli, "build_forensic_report", lambda x, y, z, calibration=None: report)
    output = tmp_path / "forensic.json"
    assert cli.main(["inspect", "a.json", "b.json", "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == report


def test_cli_scan_id_requires_db(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["inspect", "a", "b", "--scan-id", "old", "--output", str(tmp_path / "out.json")])


def test_cli_scan_rejects_invalid_confidence(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["scan", "--db", str(tmp_path / "copygraph.db"), "--output", str(tmp_path / "scan.json"), "--min-confidence", "1.5"])
