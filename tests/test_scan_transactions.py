import pytest

import copygraph.scanner as scanner
from copygraph.indexer import index_inputs
from copygraph.scanner import latest_scan_id, run_scan
from tests.batch_data import put, rows
from tests.test_scanner_cache import indexed_three_accounts


def test_failed_scan_does_not_replace_latest_completed_scan(tmp_path, monkeypatch):
    conn, paths = indexed_three_accounts(tmp_path)
    baseline = run_scan(conn)
    put(paths["b"], rows("b", delay=55))
    index_inputs(conn, list(paths.values()))

    def fail(*args, **kwargs):
        raise RuntimeError("forced scan failure")

    monkeypatch.setattr(scanner, "analyze_pair", fail)
    with pytest.raises(RuntimeError, match="forced scan failure"):
        run_scan(conn)

    assert latest_scan_id(conn) == baseline.scan_id
    incomplete = conn.execute("SELECT COUNT(*) FROM scans WHERE completed = ?", (0,)).fetchone()[0]
    assert incomplete == 0
