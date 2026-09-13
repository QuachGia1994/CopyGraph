from copygraph.indexer import index_inputs
from copygraph.scanner import inspect_scan_pair, run_scan
from copygraph.store import open_store
from tests.batch_data import put, rows


def _put_account(path, account, delay, position_offset):
    payload = rows(account, delay=delay)
    for row in payload:
        row["position_id"] = int(row["position_id"]) + position_offset
    put(path, payload)


def test_persistent_inspect_uses_immutable_historical_snapshot(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _put_account(a, "a", 0, 0)
    _put_account(b, "b", 20, 100)
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [a, b])
    old = run_scan(conn)

    _put_account(b, "b", 55, 100)
    index_inputs(conn, [a, b])
    run_scan(conn)

    report = inspect_scan_pair(conn, "a", "b", scan_id=old.scan_id)
    assert report["accounts"] == ["a", "b"]
    assert report["median_delay_s"] == 20.0
    assert report["timeline"][0]["a_position_id"] == "0"
    assert report["timeline"][0]["b_position_id"] == "100"
    assert report["timeline"][0]["delay_s"] == 20.0


def test_persistent_inspect_preserves_requested_account_order(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _put_account(a, "a", 0, 0)
    _put_account(b, "b", 20, 100)
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [a, b])
    scan = run_scan(conn)

    forward = inspect_scan_pair(conn, "a", "b", scan_id=scan.scan_id)
    reverse = inspect_scan_pair(conn, "b", "a", scan_id=scan.scan_id)

    assert reverse["accounts"] == ["b", "a"]
    assert reverse["median_delay_s"] == -forward["median_delay_s"]
    assert reverse["timeline"][0]["a_position_id"] == "100"
    assert reverse["timeline"][0]["b_position_id"] == "0"
    assert reverse["timeline"][0]["delay_s"] == -forward["timeline"][0]["delay_s"]
