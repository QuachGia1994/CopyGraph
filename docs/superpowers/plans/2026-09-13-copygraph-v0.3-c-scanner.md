# CopyGraph V0.3-C Incremental Large-scale Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local SQLite-backed index and pair cache so repeated multi-account scans recompute only affected pairs while preserving stateless analytical equivalence and immutable historical scan inspection.

**Architecture:** Persist normalized per-source events, derive immutable account versions keyed by analysis-relevant fingerprints, and cache pair evidence by the two account fingerprints. Refactor V0.2 batch report assembly so stateless and persistent scans share the same graph/report builder; SQLite is only persistence/orchestration, never a second scoring implementation.

**Tech Stack:** Python 3.11+, standard library (`sqlite3`, `hashlib`, `json`, `pathlib`, `dataclasses`, `datetime`, `itertools`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-copygraph-v0.3-design.md`

## Global Constraints

- Milestones A and B must be complete before this plan starts.
- SQLite is local-only; no server, daemon, scheduler, ORM, or external database dependency.
- V0.2 `batch` remains available and stateless.
- One `index` invocation is authoritative for the current source set: sources previously known to this DB but absent from the invocation become inactive; historical snapshots remain immutable.
- Content/account fingerprints derive from normalized analysis-relevant data, never from absolute path text.
- A privacy-safe internal `source_id` may hash the resolved path to recognize the same local source, but the raw absolute path is never persisted or exported; only basename/display name is stored.
- Historical scan inspection must use immutable account versions, not current account state.
- Database corruption/newer schema fails clearly; never delete/rebuild silently.
- Use parameterized SQL only.
- Keep package/module version `0.2.0` and CHANGELOG `[Unreleased]` until the final V0.3 release task.

---

### Task 1: Round-trip serialization for cached analyses and normalized records

**Files:**
- Create: `src/copygraph/serde.py`
- Modify: `src/copygraph/evidence.py`
- Create: `tests/test_serde.py`
- Modify: `tests/test_graph_evidence.py`

**Interfaces:**

```python
# serde.py
def trade_event_to_dict(event: TradeEvent) -> dict[str, object]: ...
def trade_event_from_dict(payload: Mapping[str, object]) -> TradeEvent: ...
def lifecycle_to_dict(position: PositionLifecycle) -> dict[str, object]: ...
def lifecycle_from_dict(payload: Mapping[str, object]) -> PositionLifecycle: ...

# evidence.py
def analysis_from_evidence(payload: Mapping[str, object]) -> PairAnalysis: ...
```

- [ ] **Step 1: Write failing round-trip tests**

```python
def test_trade_event_round_trip_preserves_utc_and_optional_risk():
    event = TradeEvent("a", "11", "7#2", "EURUSD", "SELL", 0.5, 1.1, BASE, "OPEN", 1.12, 1.05, 0.0)
    assert trade_event_from_dict(trade_event_to_dict(event)) == event


def test_pair_analysis_evidence_round_trip():
    left, right = copied_pair()
    analysis = analyze_pair(left, right)
    restored = analysis_from_evidence(analysis_to_evidence(analysis))
    assert restored == analysis
```

Add lifecycle round-trip and invalid schema tests.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_serde.py tests/test_graph_evidence.py::test_pair_analysis_evidence_round_trip`

Expected: missing APIs.

- [ ] **Step 3: Implement canonical JSON-friendly serializers**

Datetime format is UTC ISO with `Z`. Tuple `tickets` serializes as JSON list and restores as tuple. `analysis_from_evidence()` accepts evidence schema `1.0`, reconstructs every `MatchedTrade`, and requires the additive Milestone A fields `confidence_factors` plus `matching_window_s`; if older evidence lacks those fields, default factors/window to `0.0` only for backward reading and never for newly written cache rows.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_serde.py tests/test_graph_evidence.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/copygraph/serde.py src/copygraph/evidence.py tests/test_serde.py tests/test_graph_evidence.py
git commit -m "Serialize cached analysis records"
```

---

### Task 2: SQLite schema, migrations, and safe store boundary

**Files:**
- Create: `src/copygraph/store.py`
- Create: `tests/test_store.py`

**Interfaces:**

```python
CURRENT_SCHEMA_VERSION = 1

class StoreError(RuntimeError): ...
class StoreSchemaError(StoreError): ...

def open_store(path: str | Path) -> sqlite3.Connection: ...
def migrate_store(connection: sqlite3.Connection) -> None: ...
def get_schema_version(connection: sqlite3.Connection) -> int: ...
```

Schema V1 tables:

```sql
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0,1))
);
CREATE TABLE source_accounts (
    source_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    events_json TEXT NOT NULL,
    events_fingerprint TEXT NOT NULL,
    PRIMARY KEY (source_id, account_id),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
);
CREATE TABLE account_versions (
    account_id TEXT NOT NULL,
    analysis_fingerprint TEXT NOT NULL,
    snapshot_fingerprint TEXT NOT NULL,
    lifecycles_json TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    latest_event_at TEXT,
    PRIMARY KEY (account_id, snapshot_fingerprint)
);
CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    analysis_fingerprint TEXT NOT NULL,
    snapshot_fingerprint TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    present INTEGER NOT NULL CHECK (present IN (0,1))
);
CREATE TABLE pair_cache (
    account_a TEXT NOT NULL,
    account_b TEXT NOT NULL,
    analysis_fingerprint_a TEXT NOT NULL,
    analysis_fingerprint_b TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY (account_a, account_b, analysis_fingerprint_a, analysis_fingerprint_b, engine_version)
);
CREATE TABLE scans (
    scan_id TEXT PRIMARY KEY,
    sequence INTEGER NOT NULL UNIQUE,
    engine_version TEXT NOT NULL,
    min_confidence REAL NOT NULL,
    generated_at TEXT,
    report_json TEXT NOT NULL,
    completed INTEGER NOT NULL CHECK (completed IN (0,1))
);
CREATE TABLE scan_accounts (
    scan_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    snapshot_fingerprint TEXT NOT NULL,
    PRIMARY KEY (scan_id, account_id),
    FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
);
```

- [ ] **Step 1: Write failing schema/error tests**

```python
def test_open_store_creates_schema_once(tmp_path):
    db = tmp_path / "copygraph.db"
    conn = open_store(db)
    assert get_schema_version(conn) == 1
    conn.close()
    reopened = open_store(db)
    assert get_schema_version(reopened) == 1
```

```python
def test_newer_schema_is_rejected(tmp_path):
    db = tmp_path / "copygraph.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", ("schema_version", "99"))
    conn.commit()
    conn.close()
    with pytest.raises(StoreSchemaError, match="newer schema"):
        open_store(db)
```

Add a test creating a non-SQLite byte file and require `StoreError`, while asserting the file still exists afterward.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_store.py`

Expected: missing module/API.

- [ ] **Step 3: Implement safe connection/migration**

`open_store()` sets `row_factory = sqlite3.Row`, executes `PRAGMA foreign_keys = ON`, and calls `migrate_store`. Wrap `sqlite3.DatabaseError` as `StoreError` without deleting/replacing the file.

Migration behavior:
- no `meta` table -> create all V1 tables inside one transaction, then insert `schema_version=1`;
- version `1` -> no-op;
- version `> CURRENT_SCHEMA_VERSION` -> `StoreSchemaError(f"database uses newer schema version: {version}")`;
- any unsupported older version -> `StoreSchemaError(f"unsupported schema migration from version: {version}")` until a real future migration is added.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_store.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/copygraph/store.py tests/test_store.py
git commit -m "Add SQLite store schema"
```

---

### Task 3: Authoritative source indexing and immutable account versions

**Files:**
- Create: `src/copygraph/indexer.py`
- Create: `tests/test_indexer.py`
- Create: `tests/test_indexer_split_positions.py`

**Interfaces:**

```python
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


def index_inputs(connection: sqlite3.Connection, inputs: Sequence[str | Path]) -> IndexResult: ...
def load_current_account_versions(connection: sqlite3.Connection) -> dict[str, AccountVersion]: ...
```

- [ ] **Step 1: Write failing no-op/change/absence tests**

```python
def test_unchanged_reindex_is_noop(tmp_path):
    source = tmp_path / "a.json"
    put(source, rows("a"))
    conn = open_store(tmp_path / "copygraph.db")
    first = index_inputs(conn, [source])
    second = index_inputs(conn, [source])
    assert first.changed_accounts == ("a",)
    assert second.changed_accounts == ()
    assert second.unchanged_accounts == ("a",)
```

```python
def test_authoritative_index_marks_missing_account_absent(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    put(a, rows("a")); put(b, rows("b"))
    conn = open_store(tmp_path / "copygraph.db")
    index_inputs(conn, [a, b])
    result = index_inputs(conn, [a])
    assert result.absent_accounts == ("b",)
    assert set(load_current_account_versions(conn)) == {"a"}
```

- [ ] **Step 2: Add RED equivalence and failure-atomicity tests**

Construct one account whose OPEN event is in `open.json` and CLOSE event is in `close.json`. Assert indexing both files reconstructs one closed lifecycle, proving the store persists normalized events per source before account-level reconstruction.

Also add:

```python
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
```

Add a malformed-JSON variant: after a successful baseline index, pass one invalid `.json`; assert the parse error propagates and the prior current account set remains unchanged.

- [ ] **Step 3: Run RED verification**

Run: `py -3 -m pytest -q tests/test_indexer.py tests/test_indexer_split_positions.py`

Expected: missing module/API.

- [ ] **Step 4: Implement deterministic source/event fingerprints**

Internal source identity:

```python
source_id = hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()
```

Persist only `source_id` plus `path.name` as `display_name`, never the resolved path.

For each discovered CSV/JSON source: `load_events(path)`, group by account, serialize each event using `trade_event_to_dict`, sort canonical payload by `(timestamp, ticket, position_id)`, encode with `json.dumps(..., sort_keys=True, separators=(",", ":"))`, and SHA-256 that canonical JSON for `events_fingerprint`. Source `content_fingerprint` hashes the sorted `{account_id: events_fingerprint}` mapping.

- [ ] **Step 5: Implement authoritative transaction and account-version derivation**

First call `discover_history_files(inputs)`; if it returns empty, raise `ValueError("No CSV or JSON history files found")`. Load and normalize every discovered source into memory before mutating SQLite, so malformed input cannot deactivate the previous current set.

Then, inside one transaction:
1. mark all known sources inactive;
2. upsert current discovered sources active, delete the previous `source_accounts` rows for each seen source ID, then insert that source's newly normalized account-event rows;
3. read all active source-account events grouped by account;
4. reconstruct positions from the union of events for each account;
5. serialize sorted lifecycles canonically and hash them to `analysis_fingerprint`;
6. compute `latest_event_at` as the maximum normalized event timestamp for that account;
7. compute `snapshot_fingerprint = sha256(canonical_json({"analysis_fingerprint": analysis_fingerprint, "source_count": source_count, "latest_event_at": iso_z(latest_event_at)}))`;
8. `INSERT OR IGNORE` immutable `account_versions(account_id,analysis_fingerprint,snapshot_fingerprint,lifecycles_json,source_count,latest_event_at)`;
9. update current `accounts` pointers/present flags;
10. mark accounts absent when no active source contributes events.

`IndexResult.changed_accounts` means the current `snapshot_fingerprint` changed (analysis or exported metadata changed). Pair-cache reuse is governed only by `analysis_fingerprint`, so a source-count-only change creates a new scan snapshot without recomputing analytical pairs.

Return sorted tuples for changed/unchanged/absent account IDs.

- [ ] **Step 6: Run GREEN**

Run: `py -3 -m pytest -q tests/test_indexer.py tests/test_indexer_split_positions.py tests/test_batch_sources.py tests/test_reversal.py`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/copygraph/indexer.py tests/test_indexer.py tests/test_indexer_split_positions.py
git commit -m "Index immutable account versions"
```

---

### Task 4: Share batch report assembly between stateless and persistent scans

**Files:**
- Modify: `src/copygraph/batch.py`
- Create: `tests/test_batch_assembly.py`
- Modify: `tests/test_batch_deterministic.py`

**Interfaces:**

```python
def build_pair_analyses(positions: Mapping[str, Sequence[PositionLifecycle]]) -> list[PairAnalysis]: ...

def assemble_batch_report(
    positions: Mapping[str, Sequence[PositionLifecycle]],
    analyses: Sequence[PairAnalysis],
    source_counts: Mapping[str, int],
    generated_at: datetime | None,
    min_confidence: float = 0.7,
) -> dict[str, object]: ...
```

`analyze_histories()` becomes orchestration only: discover/load/reconstruct -> `build_pair_analyses()` -> `assemble_batch_report()`.

- [ ] **Step 1: Write failing equivalence test**

```python
def test_assembled_report_equals_stateless_batch(tmp_path):
    put(tmp_path / "a.json", rows("a"))
    put(tmp_path / "b.json", rows("b", delay=20))
    expected = analyze_histories([tmp_path])
    positions, source_counts, generated_at = load_test_positions_like_batch(tmp_path)
    analyses = build_pair_analyses(positions)
    actual = assemble_batch_report(positions, analyses, source_counts, generated_at)
    assert actual == expected
```

The test helper must use `load_events` + `reconstruct_positions` exactly like current batch grouping, not call `analyze_histories` internally.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_batch_assembly.py`

Expected: missing public assembly APIs.

- [ ] **Step 3: Extract without changing report schema**

Move existing combinations/analyze logic to `build_pair_analyses`; move summaries/pairs/graph/clusters/UTC generated_at logic to `assemble_batch_report`. Keep schema version `2.0` and existing ordering exactly.

- [ ] **Step 4: Run GREEN + full batch regression**

Run: `py -3 -m pytest -q tests/test_batch_assembly.py tests/test_batch.py tests/test_batch_scan.py tests/test_batch_deterministic.py tests/test_batch_sources.py`

Expected: PASS with byte-equivalent dicts for equivalent inputs.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/copygraph/batch.py tests/test_batch_assembly.py tests/test_batch_deterministic.py
git commit -m "Share batch report assembly"
```

---

### Task 5: Pair cache and incremental scan engine

**Files:**
- Create: `src/copygraph/scanner.py`
- Modify: `src/copygraph/store.py`
- Create: `tests/test_scanner_cache.py`
- Create: `tests/test_scanner_equivalence.py`

**Interfaces:**

```python
RAW_ANALYSIS_ENGINE_VERSION = "1"

@dataclass(frozen=True, slots=True)
class ScanRunResult:
    scan_id: str
    report: dict[str, object]
    recomputed_pairs: int
    reused_pairs: int


def run_scan(connection: sqlite3.Connection, min_confidence: float = 0.7) -> ScanRunResult: ...
def load_scan(connection: sqlite3.Connection, scan_id: str | None = None) -> dict[str, object]: ...
def latest_scan_id(connection: sqlite3.Connection) -> str | None: ...
```

Persistent scan artifact schema:

```json
{
  "schema_version": "1.0",
  "scan_id": "64-character lowercase SHA-256 hex string",
  "engine_version": "1",
  "batch": { "schema_version": "2.0" }
}
```

- [ ] **Step 1: Write failing cache-count tests**

```python
def test_second_unchanged_scan_reuses_all_pairs(tmp_path):
    conn, inputs = indexed_three_accounts(tmp_path)
    first = run_scan(conn)
    second = run_scan(conn)
    assert first.recomputed_pairs == 3
    assert second.recomputed_pairs == 0
    assert second.reused_pairs == 3
    assert second.report == first.report
```

```python
def test_changing_one_of_three_accounts_recomputes_exactly_n_minus_one(tmp_path):
    conn, paths = indexed_three_accounts(tmp_path)
    run_scan(conn)
    put(paths["b"], rows("b", delay=55))
    index_inputs(conn, list(paths.values()))
    result = run_scan(conn)
    assert result.recomputed_pairs == 2
    assert result.reused_pairs == 1
```

- [ ] **Step 2: Write failing stateless equivalence test**

After indexing the same input directory, compare `run_scan(conn).report["batch"]` exactly to `analyze_histories([input_dir])`.

- [ ] **Step 3: Run RED verification**

Run: `py -3 -m pytest -q tests/test_scanner_cache.py tests/test_scanner_equivalence.py`

Expected: missing scanner APIs.

- [ ] **Step 4: Implement pair cache lookup/store**

Normalize pair order lexicographically (`account_a < account_b`). Cache key is `(account_a, account_b, analysis_fingerprint_a, analysis_fingerprint_b, RAW_ANALYSIS_ENGINE_VERSION)`. On hit deserialize with `analysis_from_evidence`; on miss call the same `analyze_pair()` used by stateless execution and cache `analysis_to_evidence()` JSON with sorted keys/compact separators. `RAW_ANALYSIS_ENGINE_VERSION` is independent from package/schema versions and must be incremented in a future release whenever raw matching semantics change.

- [ ] **Step 5: Implement deterministic scan snapshot**

Load current `AccountVersion` objects. For all unordered pairs use cache/miss behavior, then call `assemble_batch_report` with identical positions/source counts/generated_at. Derive `generated_at` as the maximum non-null `AccountVersion.latest_event_at`; this matches stateless batch even when an open lifecycle has a later partial-close event.

Compute deterministic scan ID:

```python
account_material = [
    (account_id, version.snapshot_fingerprint)
    for account_id, version in sorted(current_versions.items())
]
scan_material = {
    "accounts": account_material,
    "min_confidence": min_confidence,
    "batch_schema": "2.0",
    "engine_version": RAW_ANALYSIS_ENGINE_VERSION,
}
scan_id = hashlib.sha256(canonical_json(scan_material).encode("utf-8")).hexdigest()
```

Wrap the batch report in persistent schema `1.0` and include `engine_version: RAW_ANALYSIS_ENGINE_VERSION`. Within one transaction, if this scan ID already exists return its stored report; otherwise assign `sequence = COALESCE(MAX(sequence),0)+1`, insert the same engine version into `scans`, insert completed scan + `scan_accounts`, and commit only after all pair analysis/report generation succeeds.

- [ ] **Step 6: Run GREEN**

Run: `py -3 -m pytest -q tests/test_scanner_cache.py tests/test_scanner_equivalence.py tests/test_batch_assembly.py`

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/copygraph/scanner.py src/copygraph/store.py tests/test_scanner_cache.py tests/test_scanner_equivalence.py
git commit -m "Cache incremental account scans"
```

---

### Task 6: Immutable historical scans, rollback, deleted-source behavior, and reopen determinism

**Files:**
- Modify: `src/copygraph/scanner.py`
- Modify: `src/copygraph/store.py`
- Create: `tests/test_scan_snapshots.py`
- Create: `tests/test_scan_transactions.py`

**Interfaces:**
- Uses `load_scan(connection, scan_id=None)` where `None` means latest completed by highest sequence.
- Adds `load_scan_account_positions(connection, scan_id: str, account_id: str) -> list[PositionLifecycle]`.

- [ ] **Step 1: Write failing immutable/deleted-source test**

```python
def test_old_scan_remains_queryable_after_source_disappears(tmp_path):
    conn, paths = indexed_three_accounts(tmp_path)
    old = run_scan(conn)
    index_inputs(conn, [paths["a"], paths["b"]])
    new = run_scan(conn)
    assert len(old.report["batch"]["accounts"]) == 3
    assert len(new.report["batch"]["accounts"]) == 2
    assert load_scan(conn, old.scan_id) == old.report
    assert {p.account_id for p in load_scan_account_positions(conn, old.scan_id, "c")} == {"c"}
```

- [ ] **Step 2: Write failing rollback test**

Create a completed baseline scan, change one account, monkeypatch `scanner.analyze_pair` to raise `RuntimeError("forced scan failure")`, call `run_scan`, assert the exception propagates and `latest_scan_id(conn)` still equals the baseline scan ID with no incomplete scan row persisted.

- [ ] **Step 3: Write failing DB reopen test**

Close connection after a completed scan, reopen using `open_store(db)`, and assert `load_scan(reopened, scan_id)` exactly equals the pre-close report.

- [ ] **Step 4: Run RED verification**

Run: `py -3 -m pytest -q tests/test_scan_snapshots.py tests/test_scan_transactions.py`

Expected: missing historical-position/rollback behavior.

- [ ] **Step 5: Implement historical position loading through `scan_accounts` -> `account_versions`**

Never read current `accounts` when loading a specific historical scan. Missing scan/account raises `StoreError` with the requested identifier.

- [ ] **Step 6: Ensure scan publication is atomic**

All cache writes for new fingerprints may remain reusable, but insertion into `scans` and `scan_accounts` must occur in one transaction after analytical work succeeds. A failure before publication leaves the prior latest completed sequence unchanged. No `completed=0` row is left behind.

- [ ] **Step 7: Run GREEN**

Run: `py -3 -m pytest -q tests/test_scan_snapshots.py tests/test_scan_transactions.py tests/test_scanner_cache.py`

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/copygraph/scanner.py src/copygraph/store.py tests/test_scan_snapshots.py tests/test_scan_transactions.py
git commit -m "Preserve immutable scan snapshots"
```

---

### Task 7: Persistent forensic inspect from an immutable scan

**Files:**
- Modify: `src/copygraph/scanner.py`
- Create: `tests/test_persistent_inspect.py`

**Interfaces:**

```python
def inspect_scan_pair(
    connection: sqlite3.Connection,
    account_a: str,
    account_b: str,
    scan_id: str | None = None,
    calibration: CalibrationModel | None = None,
) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing historical-inspect test**

Create/scan A+B, save old scan ID, mutate B and re-index/scan, then call `inspect_scan_pair(conn, "a", "b", scan_id=old_id)`. Assert returned forensic timeline IDs/timestamps match the old account-version data, not the current B version.

Add an order-preservation test: call `inspect_scan_pair(conn, "b", "a", scan_id=old_id)` and assert report `accounts == ["b", "a"]`, matched lifecycle IDs are swapped into requested sides, and every `delay_s`/`median_delay_s` sign is the negative of the canonical A->B cached analysis.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_persistent_inspect.py`

Expected: missing API.

- [ ] **Step 3: Implement persistent inspect using cached pair evidence**

Resolve requested/latest scan and read its stored `engine_version`. Load each account `snapshot_fingerprint` and immutable positions from that scan, then obtain each version's `analysis_fingerprint`. Load matching pair-cache evidence for the lexicographically canonical pair plus the scan's stored engine version and deserialize `PairAnalysis`. If the caller requested the reverse account order, create a metadata-equivalent reversed `PairAnalysis`: swap `account_a/account_b`, `total_a/total_b`, and every match's `a_position_id/b_position_id`; negate each match `delay_s` and `median_delay_s`; keep orientation, component similarities, scores, confidence factors, matching window, and `lead_account` account ID unchanged. Pass lifecycles in the caller's requested order to Milestone B `build_forensic_report`. If cache evidence is unexpectedly missing for a pair present in a completed scan, raise `StoreError("pair evidence missing from completed scan")`; never silently recompute historical evidence.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_persistent_inspect.py tests/test_forensics_timeline.py tests/test_forensics_evidence.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 7**

```bash
git add src/copygraph/scanner.py tests/test_persistent_inspect.py
git commit -m "Inspect immutable scan evidence"
```

---

### Task 8: `index`, `scan`, and dual-mode `inspect` CLI

**Files:**
- Modify: `src/copygraph/cli.py`
- Create: `tests/test_cli_v03_scanner.py`

**Interfaces:**
- `copygraph index <inputs...> --db copygraph.db`
- `copygraph scan --db copygraph.db --output report.json [--dashboard dashboard.html] [--min-confidence 0..1]`
- Stateless: `copygraph inspect <history-a> <history-b> [--calibration calibration.json] --output forensic.json [--dashboard forensic.html]`
- Persistent: `copygraph inspect ACCOUNT_A ACCOUNT_B --db copygraph.db [--scan-id ID] [--calibration calibration.json] --output forensic.json [--dashboard forensic.html]`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_index_prints_summary(tmp_path, monkeypatch, capsys):
    result = IndexResult(2, 3, ("a",), ("b", "c"), ())

    class FakeConnection:
        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(cli, "open_store", lambda path: connection)
    monkeypatch.setattr(cli, "index_inputs", lambda conn, inputs: result)
    assert cli.main(["index", "histories", "--db", str(tmp_path / "copygraph.db")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed_accounts"] == ["a"]
```

```python
def test_cli_inspect_db_mode_dispatches_account_ids(tmp_path, monkeypatch):
    report = {"schema_version": "1.0", "accounts": ["a", "b"]}

    class FakeConnection:
        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(cli, "open_store", lambda path: connection)
    monkeypatch.setattr(cli, "inspect_scan_pair", lambda conn, a, b, scan_id=None, calibration=None: report)
    output = tmp_path / "forensic.json"
    assert cli.main(["inspect", "a", "b", "--db", str(tmp_path / "copygraph.db"), "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == report
```

Also test scan dashboard receives the nested `report["batch"]`, invalid confidence is rejected, and stateless inspect from Milestone B still dispatches without opening SQLite.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_cli_v03_scanner.py`

Expected: parser/dispatch failures for new persistent commands/options.

- [ ] **Step 3: Add parser contracts**

`index` requires one or more inputs and `--db`. `scan` requires `--db` and `--output`, optional dashboard/min-confidence. Extend existing `inspect` parser with optional `--db` and `--scan-id`; reject `--scan-id` when `--db` is absent via `parser.error("--scan-id requires --db")`.

- [ ] **Step 4: Add dispatch and connection cleanup**

Open store only for persistent commands, close it in `finally`, print `IndexResult` as deterministic sorted-key JSON, write scan persistent envelope to output, pass only nested `batch` report to existing batch dashboard, and pass forensic report to forensic dashboard.

- [ ] **Step 5: Run GREEN + all CLI regressions**

Run: `py -3 -m pytest -q tests/test_cli_v03_scanner.py tests/test_cli_v03_forensics.py tests/test_cli_v03_calibration.py tests/test_cli_v02.py tests/test_cli_benchmark.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 8**

```bash
git add src/copygraph/cli.py tests/test_cli_v03_scanner.py
git commit -m "Add persistent scanner CLI"
```

---

### Task 9: Milestone C docs, scale/equivalence verification, and reviewer gate

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document persistent workflow and authoritative index semantics**

README must state that every `index` invocation defines the complete current source set for that DB, demonstrate `index -> scan -> inspect`, explain that old completed scans remain queryable, and explicitly say raw absolute paths/credentials are not exported.

- [ ] **Step 2: Update CHANGELOG `[Unreleased]`**

Add `Added` bullets for SQLite indexing, incremental pair reuse, immutable scans, persistent inspect, and CLI. Add `Changed` only if stateless internals were refactored without behavior change. Do not bump version.

- [ ] **Step 3: Add a deterministic low-hundreds scale test**

Create `tests/test_scanner_scale.py` with one JSON source containing 100 account IDs and exactly two positions per account (use the first four open/close rows from `tests.batch_data.rows(account)` for each account). First scan must produce exactly `100*99/2 = 4950` pair analyses. Second unchanged scan must report `recomputed_pairs == 0` and `reused_pairs == 4950`. Rewrite the same source changing only account `a050` by shifting its four event timestamps 55 seconds, re-index the complete source set, scan, and assert `recomputed_pairs == 99` and `reused_pairs == 4851`. Do not assert wall-clock performance.

- [ ] **Step 4: Run full verification**

Run in order:

```text
py -3 -m pytest
py -3 -m compileall -q src tests
py -3 -m copygraph benchmark
git diff --check
```

Expected: all tests PASS, compileall no output, benchmark raw V0.1 values unchanged.

- [ ] **Step 5: Request read-only reviewer**

Reviewer focus: SQL parameterization, migration/version handling, authoritative source disappearance, split-position equivalence, immutable historical data, fingerprint correctness, N-1 invalidation, pair-cache schema/readback, transaction rollback, corruption handling, stateless equivalence, CLI connection cleanup, privacy/path leakage.

- [ ] **Step 6: Fix accepted Critical/Important findings with RED/GREEN**

Add the narrowest regression test first, reproduce RED, fix minimally, rerun targeted tests and full suite.

- [ ] **Step 7: Commit Milestone C completion**

```bash
git add README.md CHANGELOG.md src tests
git diff --cached --check
git commit -m "Complete incremental scanner milestone"
```

Do not mint/push `0.3.0` until the final release task in the V0.3 index is explicitly authorized.
