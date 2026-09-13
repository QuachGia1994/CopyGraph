from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from itertools import combinations

from .batch import assemble_batch_report
from .calibration import CalibrationModel
from .evidence import analysis_from_evidence, analysis_to_evidence
from .forensics import build_forensic_report
from .indexer import AccountVersion, load_current_account_versions
from .matching import MatchedTrade, PairAnalysis, analyze_pair
from .models import PositionLifecycle
from .serde import lifecycle_from_dict
from .store import StoreError


RAW_ANALYSIS_ENGINE_VERSION = "1"


@dataclass(frozen=True, slots=True)
class ScanRunResult:
    scan_id: str
    report: dict[str, object]
    recomputed_pairs: int
    reused_pairs: int


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scan_id(versions: dict[str, AccountVersion], min_confidence: float) -> str:
    material = {
        "accounts": [
            (account_id, version.snapshot_fingerprint)
            for account_id, version in sorted(versions.items())
        ],
        "min_confidence": min_confidence,
        "batch_schema": "2.0",
        "engine_version": RAW_ANALYSIS_ENGINE_VERSION,
    }
    return hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def _load_cached_pair(
    connection: sqlite3.Connection,
    left: AccountVersion,
    right: AccountVersion,
) -> PairAnalysis | None:
    row = connection.execute(
        "SELECT evidence_json FROM pair_cache WHERE account_a = ? AND account_b = ? "
        "AND analysis_fingerprint_a = ? AND analysis_fingerprint_b = ? AND engine_version = ?",
        (
            left.account_id,
            right.account_id,
            left.analysis_fingerprint,
            right.analysis_fingerprint,
            RAW_ANALYSIS_ENGINE_VERSION,
        ),
    ).fetchone()
    if row is None:
        return None
    payload = json.loads(str(row["evidence_json"]))
    if not isinstance(payload, dict):
        raise StoreError("cached pair evidence is invalid")
    return analysis_from_evidence(payload)


def latest_scan_id(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT scan_id FROM scans WHERE completed = ? ORDER BY sequence DESC LIMIT 1",
        (1,),
    ).fetchone()
    return None if row is None else str(row["scan_id"])


def load_scan(connection: sqlite3.Connection, scan_id: str | None = None) -> dict[str, object]:
    resolved = scan_id if scan_id is not None else latest_scan_id(connection)
    if resolved is None:
        raise StoreError("no completed scan available")
    row = connection.execute(
        "SELECT report_json FROM scans WHERE scan_id = ? AND completed = ?",
        (resolved, 1),
    ).fetchone()
    if row is None:
        raise StoreError(f"scan not found: {resolved}")
    payload = json.loads(str(row["report_json"]))
    if not isinstance(payload, dict):
        raise StoreError("stored scan report is invalid")
    return payload


def load_scan_account_positions(
    connection: sqlite3.Connection,
    scan_id: str,
    account_id: str,
) -> list[PositionLifecycle]:
    row = connection.execute(
        "SELECT av.lifecycles_json FROM scan_accounts sa "
        "JOIN account_versions av ON av.account_id = sa.account_id "
        "AND av.snapshot_fingerprint = sa.snapshot_fingerprint "
        "WHERE sa.scan_id = ? AND sa.account_id = ?",
        (scan_id, account_id),
    ).fetchone()
    if row is None:
        scan = connection.execute(
            "SELECT 1 FROM scans WHERE scan_id = ? AND completed = ?",
            (scan_id, 1),
        ).fetchone()
        if scan is None:
            raise StoreError(f"scan not found: {scan_id}")
        raise StoreError(f"account not found in scan: {account_id}")
    payload = json.loads(str(row["lifecycles_json"]))
    if not isinstance(payload, list):
        raise StoreError("stored account lifecycles are invalid")
    return [lifecycle_from_dict(item) for item in payload]


def _load_scan_account_analysis_fingerprint(
    connection: sqlite3.Connection,
    scan_id: str,
    account_id: str,
) -> str:
    row = connection.execute(
        "SELECT av.analysis_fingerprint FROM scan_accounts sa "
        "JOIN account_versions av ON av.account_id = sa.account_id "
        "AND av.snapshot_fingerprint = sa.snapshot_fingerprint "
        "WHERE sa.scan_id = ? AND sa.account_id = ?",
        (scan_id, account_id),
    ).fetchone()
    if row is None:
        raise StoreError(f"account not found in scan: {account_id}")
    return str(row["analysis_fingerprint"])


def _reverse_analysis(analysis: PairAnalysis) -> PairAnalysis:
    return PairAnalysis(
        account_a=analysis.account_b,
        account_b=analysis.account_a,
        orientation=analysis.orientation,
        score=analysis.score,
        confidence=analysis.confidence,
        matches=[
            MatchedTrade(
                a_position_id=match.b_position_id,
                b_position_id=match.a_position_id,
                delay_s=-match.delay_s,
                time_similarity=match.time_similarity,
                lifecycle_similarity=match.lifecycle_similarity,
                risk_similarity=match.risk_similarity,
                volume_similarity=match.volume_similarity,
                rarity_weight=match.rarity_weight,
                score=match.score,
            )
            for match in analysis.matches
        ],
        volume_similarity=analysis.volume_similarity,
        lead_account=analysis.lead_account,
        median_delay_s=-analysis.median_delay_s,
        total_a=analysis.total_b,
        total_b=analysis.total_a,
        overlap_factor=analysis.overlap_factor,
        sample_factor=analysis.sample_factor,
        matching_window_s=analysis.matching_window_s,
    )


def inspect_scan_pair(
    connection: sqlite3.Connection,
    account_a: str,
    account_b: str,
    scan_id: str | None = None,
    calibration: CalibrationModel | None = None,
) -> dict[str, object]:
    resolved = scan_id if scan_id is not None else latest_scan_id(connection)
    if resolved is None:
        raise StoreError("no completed scan available")
    scan_row = connection.execute(
        "SELECT engine_version FROM scans WHERE scan_id = ? AND completed = ?",
        (resolved, 1),
    ).fetchone()
    if scan_row is None:
        raise StoreError(f"scan not found: {resolved}")
    if account_a == account_b:
        raise ValueError("account_a and account_b must be different")

    requested_positions_a = load_scan_account_positions(connection, resolved, account_a)
    requested_positions_b = load_scan_account_positions(connection, resolved, account_b)
    fingerprints = {
        account_a: _load_scan_account_analysis_fingerprint(connection, resolved, account_a),
        account_b: _load_scan_account_analysis_fingerprint(connection, resolved, account_b),
    }
    left_name, right_name = sorted((account_a, account_b))
    row = connection.execute(
        "SELECT evidence_json FROM pair_cache WHERE account_a = ? AND account_b = ? "
        "AND analysis_fingerprint_a = ? AND analysis_fingerprint_b = ? AND engine_version = ?",
        (
            left_name,
            right_name,
            fingerprints[left_name],
            fingerprints[right_name],
            str(scan_row["engine_version"]),
        ),
    ).fetchone()
    if row is None:
        raise StoreError("pair evidence missing from completed scan")
    payload = json.loads(str(row["evidence_json"]))
    if not isinstance(payload, dict):
        raise StoreError("cached pair evidence is invalid")
    analysis = analysis_from_evidence(payload)
    if (account_a, account_b) != (left_name, right_name):
        analysis = _reverse_analysis(analysis)
    return build_forensic_report(
        analysis,
        requested_positions_a,
        requested_positions_b,
        calibration,
    )


def run_scan(connection: sqlite3.Connection, min_confidence: float = 0.7) -> ScanRunResult:
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    versions = load_current_account_versions(connection)
    names = sorted(versions)
    analyses: list[PairAnalysis] = []
    pending_cache: list[tuple[AccountVersion, AccountVersion, PairAnalysis]] = []
    recomputed = 0
    reused = 0

    for left_name, right_name in combinations(names, 2):
        left = versions[left_name]
        right = versions[right_name]
        cached = _load_cached_pair(connection, left, right)
        if cached is None:
            cached = analyze_pair(left.positions, right.positions)
            pending_cache.append((left, right, cached))
            recomputed += 1
        else:
            reused += 1
        analyses.append(cached)

    positions = {account_id: version.positions for account_id, version in versions.items()}
    source_counts = {account_id: version.source_count for account_id, version in versions.items()}
    generated_at = max(
        (version.latest_event_at for version in versions.values() if version.latest_event_at is not None),
        default=None,
    )
    batch = assemble_batch_report(
        positions,
        analyses,
        source_counts,
        generated_at,
        min_confidence=min_confidence,
    )
    scan_id = _scan_id(versions, min_confidence)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "scan_id": scan_id,
        "engine_version": RAW_ANALYSIS_ENGINE_VERSION,
        "batch": batch,
    }

    with connection:
        for left, right, analysis in pending_cache:
            connection.execute(
                "INSERT OR REPLACE INTO pair_cache(account_a,account_b,analysis_fingerprint_a,analysis_fingerprint_b,engine_version,evidence_json) VALUES(?,?,?,?,?,?)",
                (
                    left.account_id,
                    right.account_id,
                    left.analysis_fingerprint,
                    right.analysis_fingerprint,
                    RAW_ANALYSIS_ENGINE_VERSION,
                    _canonical_json(analysis_to_evidence(analysis)),
                ),
            )
        existing = connection.execute(
            "SELECT report_json FROM scans WHERE scan_id = ? AND completed = ?",
            (scan_id, 1),
        ).fetchone()
        if existing is None:
            row = connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM scans").fetchone()
            sequence = int(row["next_sequence"])
            connection.execute(
                "INSERT INTO scans(scan_id,sequence,engine_version,min_confidence,generated_at,report_json,completed) VALUES(?,?,?,?,?,?,?)",
                (
                    scan_id,
                    sequence,
                    RAW_ANALYSIS_ENGINE_VERSION,
                    min_confidence,
                    batch["generated_at"],
                    _canonical_json(report),
                    1,
                ),
            )
            for account_id, version in sorted(versions.items()):
                connection.execute(
                    "INSERT INTO scan_accounts(scan_id,account_id,snapshot_fingerprint) VALUES(?,?,?)",
                    (scan_id, account_id, version.snapshot_fingerprint),
                )
        else:
            stored = json.loads(str(existing["report_json"]))
            if not isinstance(stored, dict):
                raise StoreError("stored scan report is invalid")
            report = stored

    return ScanRunResult(
        scan_id=scan_id,
        report=report,
        recomputed_pairs=recomputed,
        reused_pairs=reused,
    )
