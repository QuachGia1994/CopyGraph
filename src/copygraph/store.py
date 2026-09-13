from __future__ import annotations

import sqlite3
from pathlib import Path


CURRENT_SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    pass


class StoreSchemaError(StoreError):
    pass


_SCHEMA_STATEMENTS = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE sources (source_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, content_fingerprint TEXT NOT NULL, active INTEGER NOT NULL CHECK (active IN (0,1)))",
    "CREATE TABLE source_accounts (source_id TEXT NOT NULL, account_id TEXT NOT NULL, events_json TEXT NOT NULL, events_fingerprint TEXT NOT NULL, PRIMARY KEY (source_id, account_id), FOREIGN KEY (source_id) REFERENCES sources(source_id))",
    "CREATE TABLE account_versions (account_id TEXT NOT NULL, analysis_fingerprint TEXT NOT NULL, snapshot_fingerprint TEXT NOT NULL, lifecycles_json TEXT NOT NULL, source_count INTEGER NOT NULL, latest_event_at TEXT, PRIMARY KEY (account_id, snapshot_fingerprint))",
    "CREATE TABLE accounts (account_id TEXT PRIMARY KEY, analysis_fingerprint TEXT NOT NULL, snapshot_fingerprint TEXT NOT NULL, source_count INTEGER NOT NULL, present INTEGER NOT NULL CHECK (present IN (0,1)))",
    "CREATE TABLE pair_cache (account_a TEXT NOT NULL, account_b TEXT NOT NULL, analysis_fingerprint_a TEXT NOT NULL, analysis_fingerprint_b TEXT NOT NULL, engine_version TEXT NOT NULL, evidence_json TEXT NOT NULL, PRIMARY KEY (account_a, account_b, analysis_fingerprint_a, analysis_fingerprint_b, engine_version))",
    "CREATE TABLE scans (scan_id TEXT PRIMARY KEY, sequence INTEGER NOT NULL UNIQUE, engine_version TEXT NOT NULL, min_confidence REAL NOT NULL, generated_at TEXT, report_json TEXT NOT NULL, completed INTEGER NOT NULL CHECK (completed IN (0,1)))",
    "CREATE TABLE scan_accounts (scan_id TEXT NOT NULL, account_id TEXT NOT NULL, snapshot_fingerprint TEXT NOT NULL, PRIMARY KEY (scan_id, account_id), FOREIGN KEY (scan_id) REFERENCES scans(scan_id))",
)


def _meta_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
        ("table", "meta"),
    ).fetchone()
    return row is not None


def get_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT value FROM meta WHERE key = ?", ("schema_version",)).fetchone()
    if row is None:
        raise StoreSchemaError("database schema_version is missing")
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise StoreSchemaError("database schema_version is invalid") from exc


def migrate_store(connection: sqlite3.Connection) -> None:
    if not _meta_exists(connection):
        try:
            connection.execute("BEGIN")
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO meta(key,value) VALUES(?,?)",
                ("schema_version", str(CURRENT_SCHEMA_VERSION)),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return

    version = get_schema_version(connection)
    if version == CURRENT_SCHEMA_VERSION:
        return
    if version > CURRENT_SCHEMA_VERSION:
        raise StoreSchemaError(f"database uses newer schema version: {version}")
    raise StoreSchemaError(f"unsupported schema migration from version: {version}")


def open_store(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(resolved)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        migrate_store(connection)
        return connection
    except StoreSchemaError:
        if connection is not None:
            connection.close()
        raise
    except sqlite3.DatabaseError as exc:
        if connection is not None:
            connection.close()
        raise StoreError(f"SQLite store error: {exc}") from exc
