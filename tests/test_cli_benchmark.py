import json
from datetime import datetime, timedelta, timezone

from copygraph.benchmark import run_synthetic_benchmark
from copygraph.cli import analyze_paths, main


BASE = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def write_account(path, account, delay_s=0):
    rows = ["account,ticket,position,symbol,type,volume,price,time,entry,sl,tp,profit"]
    for index in range(4):
        opened = BASE + timedelta(minutes=index * 10, seconds=delay_s)
        closed = opened + timedelta(minutes=5)
        volume = 0.1 * (index + 1)
        rows.append(f"{account},{index * 2 + 1},{index},EURUSD,buy,{volume},1.1000,{opened.isoformat()},in,1.0900,1.1200,0")
        rows.append(f"{account},{index * 2 + 2},{index},EURUSD,sell,{volume},1.1100,{closed.isoformat()},out,,,10")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_synthetic_benchmark_separates_copy_from_unrelated_accounts():
    result = run_synthetic_benchmark()
    assert result["normal"]["confidence"] >= 0.75
    assert result["reverse"]["confidence"] >= 0.75
    assert result["unrelated"]["confidence"] < 0.25


def test_analyze_paths_returns_evidence_payload(tmp_path):
    master = tmp_path / "master.csv"
    slave = tmp_path / "slave.csv"
    write_account(master, "master", 0)
    write_account(slave, "slave", 20)
    evidence = analyze_paths(master, slave)
    assert evidence["orientation"] == "normal"
    assert evidence["confidence"] >= 0.75
    assert evidence["totals"]["matched"] == 4


def test_cli_analyze_prints_json_evidence(tmp_path, capsys):
    master = tmp_path / "master.csv"
    slave = tmp_path / "slave.csv"
    write_account(master, "master", 0)
    write_account(slave, "slave", 15)
    assert main(["analyze", str(master), str(slave)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["accounts"] == ["master", "slave"]
    assert payload["confidence"] >= 0.75
