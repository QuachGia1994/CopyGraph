from copygraph.indexer import index_inputs
from copygraph.scanner import run_scan
from copygraph.store import open_store
from tests.batch_data import put, rows


def indexed_three_accounts(tmp_path):
    paths = {}
    for account, delay in (("a", 0), ("b", 20), ("c", 40)):
        path = tmp_path / f"{account}.json"
        put(path, rows(account, delay=delay))
        paths[account] = path
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, list(paths.values()))
    return conn, paths


def test_second_unchanged_scan_reuses_all_pairs(tmp_path):
    conn, _ = indexed_three_accounts(tmp_path)
    first = run_scan(conn)
    second = run_scan(conn)
    assert first.recomputed_pairs == 3
    assert first.reused_pairs == 0
    assert second.recomputed_pairs == 0
    assert second.reused_pairs == 3
    assert second.report == first.report


def test_changing_one_of_three_accounts_recomputes_exactly_n_minus_one(tmp_path):
    conn, paths = indexed_three_accounts(tmp_path)
    run_scan(conn)
    put(paths["b"], rows("b", delay=55))
    index_inputs(conn, list(paths.values()))
    result = run_scan(conn)
    assert result.recomputed_pairs == 2
    assert result.reused_pairs == 1
