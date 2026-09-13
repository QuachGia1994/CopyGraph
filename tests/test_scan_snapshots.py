from copygraph.indexer import index_inputs
from copygraph.scanner import load_scan, load_scan_account_positions, run_scan
from copygraph.store import open_store
from tests.test_scanner_cache import indexed_three_accounts


def test_old_scan_remains_queryable_after_source_disappears(tmp_path):
    conn, paths = indexed_three_accounts(tmp_path)
    old = run_scan(conn)
    index_inputs(conn, [paths["a"], paths["b"]])
    new = run_scan(conn)

    assert len(old.report["batch"]["accounts"]) == 3
    assert len(new.report["batch"]["accounts"]) == 2
    assert load_scan(conn, old.scan_id) == old.report
    assert {position.account_id for position in load_scan_account_positions(conn, old.scan_id, "c")} == {"c"}


def test_completed_scan_survives_database_reopen(tmp_path):
    db = tmp_path / "copygraph.db"
    paths = []
    from tests.batch_data import put, rows
    for account, delay in (("a", 0), ("b", 20)):
        path = tmp_path / f"{account}.json"
        put(path, rows(account, delay=delay))
        paths.append(path)
    conn = open_store(db)
    index_inputs(conn, paths)
    completed = run_scan(conn)
    conn.close()

    reopened = open_store(db)
    assert load_scan(reopened, completed.scan_id) == completed.report
