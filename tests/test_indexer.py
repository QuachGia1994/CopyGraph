import json

import pytest

from copygraph.indexer import index_inputs, load_current_account_versions
from copygraph.store import open_store
from tests.batch_data import put, rows


def test_unchanged_reindex_is_noop(tmp_path):
    source = tmp_path / "a.json"
    put(source, rows("a"))
    conn = open_store(tmp_path / "copygraph.db")
    first = index_inputs(conn, [source])
    second = index_inputs(conn, [source])
    assert first.changed_accounts == ("a",)
    assert second.changed_accounts == ()
    assert second.unchanged_accounts == ("a",)
    assert second.source_count == 1
    assert second.account_count == 1


def test_authoritative_index_marks_missing_account_absent(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    put(a, rows("a"))
    put(b, rows("b"))
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [a, b])
    result = index_inputs(conn, [a])
    assert result.absent_accounts == ("b",)
    assert set(load_current_account_versions(conn)) == {"a"}


def test_index_rejects_empty_source_set_without_deactivating_current_accounts(tmp_path):
    source = tmp_path / "a.json"
    put(source, rows("a"))
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [source])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No CSV or JSON history files"):
        index_inputs(conn, [empty])
    assert set(load_current_account_versions(conn)) == {"a"}


def test_index_malformed_source_keeps_prior_current_accounts(tmp_path):
    source = tmp_path / "a.json"
    put(source, rows("a"))
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [source])
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        index_inputs(conn, [bad])
    assert set(load_current_account_versions(conn)) == {"a"}


def test_index_persists_only_privacy_safe_source_metadata(tmp_path):
    source = tmp_path / "secret-parent" / "a.json"
    source.parent.mkdir()
    put(source, rows("a"))
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [source])
    row = conn.execute("SELECT source_id, display_name FROM sources").fetchone()
    assert row["display_name"] == "a.json"
    assert str(source.resolve()) not in row["source_id"]
