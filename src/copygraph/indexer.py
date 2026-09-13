from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .batch import discover_history_files
from .ingest import load_events
from .lifecycle import reconstruct_positions
from .models import PositionLifecycle, TradeEvent
from .serde import lifecycle_from_dict, lifecycle_to_dict, trade_event_from_dict, trade_event_to_dict


@dataclass(frozen=True, slots=True)
class AccountVersion:
    account_id: str
    analysis_fingerprint: str
    snapshot_fingerprint: str
    positions: tuple[PositionLifecycle, ...]
    source_count: int
    latest_event_at: datetime | None


@dataclass(frozen=True, slots=True)
class IndexResult:
    source_count: int
    account_count: int
    changed_accounts: tuple[str, ...]
    unchanged_accounts: tuple[str, ...]
    absent_accounts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SourcePayload:
    source_id: str
    display_name: str
    content_fingerprint: str
    accounts: dict[str, tuple[str, str]]


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_z(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def _source_id(path: Path) -> str:
    return _sha256_text(str(path.resolve()).casefold())


def _event_payload(events: Sequence[TradeEvent]) -> tuple[str, str]:
    rows = [trade_event_to_dict(event) for event in events]
    rows.sort(key=lambda item: (str(item["timestamp"]), str(item["ticket"]), str(item["position_id"])))
    rendered = _canonical_json(rows)
    return rendered, _sha256_text(rendered)


def _preload_source(path: Path) -> _SourcePayload:
    grouped: dict[str, list[TradeEvent]] = defaultdict(list)
    for event in load_events(path):
        grouped[event.account_id].append(event)
    accounts: dict[str, tuple[str, str]] = {}
    fingerprints: dict[str, str] = {}
    for account_id in sorted(grouped):
        events_json, fingerprint = _event_payload(grouped[account_id])
        accounts[account_id] = (events_json, fingerprint)
        fingerprints[account_id] = fingerprint
    return _SourcePayload(
        source_id=_source_id(path),
        display_name=path.name,
        content_fingerprint=_sha256_text(_canonical_json(fingerprints)),
        accounts=accounts,
    )


def _serialize_positions(positions: Sequence[PositionLifecycle]) -> tuple[str, str]:
    rows = [lifecycle_to_dict(position) for position in positions]
    rows.sort(key=lambda item: (str(item["open_time"]), str(item["position_id"])))
    rendered = _canonical_json(rows)
    return rendered, _sha256_text(rendered)


def index_inputs(connection: sqlite3.Connection, inputs: Sequence[str | Path]) -> IndexResult:
    files = discover_history_files(inputs)
    if not files:
        raise ValueError("No CSV or JSON history files found")

    preloaded = [_preload_source(path) for path in files]
    previous_rows = connection.execute(
        "SELECT account_id, snapshot_fingerprint, present FROM accounts"
    ).fetchall()
    previous_present = {
        str(row["account_id"]): str(row["snapshot_fingerprint"])
        for row in previous_rows
        if int(row["present"]) == 1
    }

    with connection:
        connection.execute("UPDATE sources SET active = ?", (0,))
        for source in preloaded:
            connection.execute(
                "INSERT INTO sources(source_id,display_name,content_fingerprint,active) VALUES(?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET display_name=excluded.display_name, content_fingerprint=excluded.content_fingerprint, active=excluded.active",
                (source.source_id, source.display_name, source.content_fingerprint, 1),
            )
            connection.execute("DELETE FROM source_accounts WHERE source_id = ?", (source.source_id,))
            for account_id in sorted(source.accounts):
                events_json, events_fingerprint = source.accounts[account_id]
                connection.execute(
                    "INSERT INTO source_accounts(source_id,account_id,events_json,events_fingerprint) VALUES(?,?,?,?)",
                    (source.source_id, account_id, events_json, events_fingerprint),
                )

        active_rows = connection.execute(
            "SELECT sa.source_id, sa.account_id, sa.events_json "
            "FROM source_accounts sa JOIN sources s ON s.source_id = sa.source_id "
            "WHERE s.active = ? ORDER BY sa.account_id, sa.source_id",
            (1,),
        ).fetchall()
        events_by_account: dict[str, list[TradeEvent]] = defaultdict(list)
        sources_by_account: dict[str, set[str]] = defaultdict(set)
        for row in active_rows:
            account_id = str(row["account_id"])
            raw_events = json.loads(str(row["events_json"]))
            if not isinstance(raw_events, list):
                raise ValueError("stored events_json must be a list")
            events_by_account[account_id].extend(trade_event_from_dict(item) for item in raw_events)
            sources_by_account[account_id].add(str(row["source_id"]))

        current_versions: dict[str, AccountVersion] = {}
        connection.execute("UPDATE accounts SET present = ?", (0,))
        for account_id in sorted(events_by_account):
            events = events_by_account[account_id]
            positions = tuple(reconstruct_positions(events))
            lifecycles_json, analysis_fingerprint = _serialize_positions(positions)
            source_count = len(sources_by_account[account_id])
            latest_event_at = max((event.timestamp for event in events), default=None)
            snapshot_fingerprint = _sha256_text(_canonical_json({
                "analysis_fingerprint": analysis_fingerprint,
                "source_count": source_count,
                "latest_event_at": _iso_z(latest_event_at),
            }))
            version = AccountVersion(
                account_id=account_id,
                analysis_fingerprint=analysis_fingerprint,
                snapshot_fingerprint=snapshot_fingerprint,
                positions=positions,
                source_count=source_count,
                latest_event_at=latest_event_at,
            )
            current_versions[account_id] = version
            connection.execute(
                "INSERT OR IGNORE INTO account_versions(account_id,analysis_fingerprint,snapshot_fingerprint,lifecycles_json,source_count,latest_event_at) VALUES(?,?,?,?,?,?)",
                (account_id, analysis_fingerprint, snapshot_fingerprint, lifecycles_json, source_count, _iso_z(latest_event_at)),
            )
            connection.execute(
                "INSERT INTO accounts(account_id,analysis_fingerprint,snapshot_fingerprint,source_count,present) VALUES(?,?,?,?,?) "
                "ON CONFLICT(account_id) DO UPDATE SET analysis_fingerprint=excluded.analysis_fingerprint, snapshot_fingerprint=excluded.snapshot_fingerprint, source_count=excluded.source_count, present=excluded.present",
                (account_id, analysis_fingerprint, snapshot_fingerprint, source_count, 1),
            )

    current_ids = set(current_versions)
    changed = sorted(
        account_id
        for account_id, version in current_versions.items()
        if previous_present.get(account_id) != version.snapshot_fingerprint
    )
    unchanged = sorted(
        account_id
        for account_id, version in current_versions.items()
        if previous_present.get(account_id) == version.snapshot_fingerprint
    )
    absent = sorted(set(previous_present) - current_ids)
    return IndexResult(
        source_count=len(preloaded),
        account_count=len(current_versions),
        changed_accounts=tuple(changed),
        unchanged_accounts=tuple(unchanged),
        absent_accounts=tuple(absent),
    )


def load_current_account_versions(connection: sqlite3.Connection) -> dict[str, AccountVersion]:
    rows = connection.execute(
        "SELECT a.account_id, a.analysis_fingerprint, a.snapshot_fingerprint, a.source_count, av.lifecycles_json, av.latest_event_at "
        "FROM accounts a JOIN account_versions av ON av.account_id = a.account_id AND av.snapshot_fingerprint = a.snapshot_fingerprint "
        "WHERE a.present = ? ORDER BY a.account_id",
        (1,),
    ).fetchall()
    output: dict[str, AccountVersion] = {}
    for row in rows:
        raw_positions = json.loads(str(row["lifecycles_json"]))
        if not isinstance(raw_positions, list):
            raise ValueError("stored lifecycles_json must be a list")
        account_id = str(row["account_id"])
        output[account_id] = AccountVersion(
            account_id=account_id,
            analysis_fingerprint=str(row["analysis_fingerprint"]),
            snapshot_fingerprint=str(row["snapshot_fingerprint"]),
            positions=tuple(lifecycle_from_dict(item) for item in raw_positions),
            source_count=int(row["source_count"]),
            latest_event_at=_parse_iso_z(None if row["latest_event_at"] is None else str(row["latest_event_at"])),
        )
    return output
