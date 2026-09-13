from datetime import datetime, timedelta, timezone

from copygraph.analysis import analyze_pair_paths, load_positions


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


def test_load_positions_reconstructs_history(tmp_path):
    history = tmp_path / "account.csv"
    write_account(history, "master")
    positions = load_positions(history)
    assert len(positions) == 4
    assert {position.account_id for position in positions} == {"master"}


def test_analyze_pair_paths_returns_analysis_and_lifecycles(tmp_path):
    master = tmp_path / "master.csv"
    slave = tmp_path / "slave.csv"
    write_account(master, "master", 0)
    write_account(slave, "slave", 20)

    analysis, left, right = analyze_pair_paths(master, slave)

    assert analysis.account_a == "master"
    assert analysis.account_b == "slave"
    assert analysis.orientation == "normal"
    assert len(left) == 4
    assert len(right) == 4
    assert len(analysis.matches) == 4
