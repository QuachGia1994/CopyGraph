from copygraph.indexer import index_inputs, load_current_account_versions
from copygraph.store import open_store
from tests.batch_data import put, rows


def test_index_reconstructs_position_split_across_two_sources(tmp_path):
    data = rows("a")
    open_source = tmp_path / "open.json"
    close_source = tmp_path / "close.json"
    put(open_source, [data[0]])
    put(close_source, [data[1]])
    conn = open_store(tmp_path / "copygraph.db")

    result = index_inputs(conn, [open_source, close_source])
    version = load_current_account_versions(conn)["a"]

    assert result.changed_accounts == ("a",)
    assert version.source_count == 2
    assert len(version.positions) == 1
    assert version.positions[0].close_time is not None
    assert version.latest_event_at == version.positions[0].close_time
