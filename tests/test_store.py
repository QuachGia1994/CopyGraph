import sqlite3

import pytest

from copygraph.store import StoreError, StoreSchemaError, get_schema_version, open_store


def test_open_store_creates_schema_once_and_enables_foreign_keys(tmp_path):
    db = tmp_path / "copygraph.db"
    conn = open_store(db)
    assert get_schema_version(conn) == 1
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()

    reopened = open_store(db)
    assert get_schema_version(reopened) == 1
    tables = {row[0] for row in reopened.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "sources", "source_accounts", "account_versions", "accounts", "pair_cache", "scans", "scan_accounts"} <= tables
    reopened.close()


def test_newer_schema_is_rejected(tmp_path):
    db = tmp_path / "copygraph.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("schema_version", "99"))
    conn.commit()
    conn.close()
    with pytest.raises(StoreSchemaError, match="newer schema"):
        open_store(db)


def test_unsupported_older_schema_is_rejected(tmp_path):
    db = tmp_path / "copygraph.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("schema_version", "0"))
    conn.commit()
    conn.close()
    with pytest.raises(StoreSchemaError, match="unsupported schema migration"):
        open_store(db)


def test_corrupt_database_is_not_deleted_or_rebuilt(tmp_path):
    db = tmp_path / "copygraph.db"
    original = b"not-a-sqlite-database"
    db.write_bytes(original)
    with pytest.raises(StoreError):
        open_store(db)
    assert db.exists()
    assert db.read_bytes() == original
