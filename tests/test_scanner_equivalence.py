from copygraph.batch import analyze_histories
from copygraph.indexer import index_inputs
from copygraph.scanner import run_scan
from copygraph.store import open_store
from tests.batch_data import put, rows


def test_persistent_scan_batch_equals_stateless_analysis(tmp_path):
    histories = tmp_path / "histories"
    histories.mkdir()
    put(histories / "a.json", rows("a"))
    put(histories / "b.json", rows("b", delay=20))
    expected = analyze_histories([histories])

    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [histories])
    result = run_scan(conn)

    assert result.report["schema_version"] == "1.0"
    assert result.report["engine_version"] == "1"
    assert len(result.scan_id) == 64
    assert result.report["batch"] == expected
