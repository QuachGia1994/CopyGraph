from copygraph.indexer import index_inputs
from copygraph.scanner import run_scan
from copygraph.store import open_store
from tests.batch_data import put, rows


def _all_accounts(shifted=None):
    payload = []
    for index in range(100):
        account = f"a{index:03d}"
        delay = 55 if account == shifted else 0
        payload.extend(rows(account, delay=delay)[:4])
    return payload


def test_incremental_scan_reuses_low_hundreds_pair_cache(tmp_path):
    source = tmp_path / "accounts.json"
    put(source, _all_accounts())
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [source])

    first = run_scan(conn)
    assert first.recomputed_pairs == 4950
    assert first.reused_pairs == 0

    second = run_scan(conn)
    assert second.recomputed_pairs == 0
    assert second.reused_pairs == 4950

    put(source, _all_accounts(shifted="a050"))
    index_inputs(conn, [source])
    third = run_scan(conn)
    assert third.recomputed_pairs == 99
    assert third.reused_pairs == 4851
