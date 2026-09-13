# CopyGraph V0.3 Design

Date: 2026-09-13
Status: Approved design, implementation not started
Target release: 0.3.0

## Goal

V0.3 makes CopyGraph trustworthy enough for real forensic use and efficient enough for repeated multi-account analysis. It is one release delivered through three internal milestones in this order:

1. V0.3-A Calibration and Explainability
2. V0.3-B Forensic Investigation
3. V0.3-C Incremental Large-scale Scanner

The milestones remain under one `Unreleased` release bucket until all three are complete. The release version is minted only when the full V0.3 acceptance gate passes.

## Non-goals

V0.3 does not add a hosted service, cloud database, account login automation, trade execution, remote credentials storage, real-time daemon, scheduler, or external ML dependency. V0.2 stateless commands remain supported.

## Architectural principle

The V0.2 pair-analysis core remains the raw evidence engine. V0.3 adds layers around it instead of replacing it in one step:

`MT5/files -> ingest -> lifecycle reconstruction -> V0.2 PairAnalysis -> calibration/explanation -> forensic report -> SQLite snapshot/cache -> dashboard/CLI`

This keeps current raw scoring reproducible while allowing calibrated confidence, richer evidence and incremental persistence to evolve independently.

## V0.3-A: Calibration and Explainability

### Problem

V0.2 confidence is a deterministic heuristic composed from timing, lifecycle, risk and volume similarities, followed by overlap and sample-size penalties. The score is useful but not calibrated against labeled real-history examples, so a value such as `0.82` is not yet an empirical probability or a threshold with known false-positive behavior.

### Design

Add a calibration layer that consumes labeled pair examples and leaves the V0.2 raw result intact.

A labeled case contains:
- stable `case_id`;
- expected class: `copy` or `unrelated`;
- expected orientation when known: `normal` or `reverse`;
- either `history_a` and `history_b` paths relative to the dataset file, or an embedded raw-analysis object using the current evidence schema.

The initial dataset format is JSON with a top-level `schema_version`, optional human-readable `name`, and `cases[]`. Relative history paths are resolved against the dataset file location. Absolute paths may be accepted as local inputs but are never copied into calibration outputs. Duplicate `case_id` values are invalid. A case cannot provide both history paths and an embedded analysis object.

Calibration output contains:
- `raw_confidence` from V0.2 unchanged;
- `calibrated_confidence` in `[0,1]`;
- selected operating threshold;
- precision, recall, false-positive rate and F1 at that threshold;
- threshold sweep table for auditability;
- calibration dataset summary and label counts.

The initial calibrator must be monotonic and standard-library-only. The implementation may use binned/isotonic-style monotonic fitting, but it must satisfy these invariants:
- a larger raw confidence cannot map to a lower calibrated confidence;
- identical labeled inputs produce identical output;
- no calibration dataset means no invented calibrated score; the result explicitly reports calibration unavailable;
- train/evaluate helpers must prevent evaluating a case against a model fitted with that same case unless the caller explicitly requests in-sample diagnostics.

### Explainability

Add an explanation schema derived from the pair analysis and matched lifecycles. It includes:
- raw score and confidence;
- calibrated confidence when available;
- contribution summaries for timing, lifecycle, risk and volume evidence;
- overlap factor and sample-size factor;
- orientation and lead/lag evidence;
- strongest supporting matches;
- weakest or contradicting matches;
- unmatched counts on both accounts;
- warnings for sparse samples, missing stop evidence, low overlap or unstable volume ratio.

Explanations must use facts already present in analysis/lifecycles. They do not invent causal claims such as "account B definitely copied account A". Wording remains evidence-first: likely relationship, supporting evidence, contradictory evidence and uncertainty.

### CLI

Planned commands:
- `copygraph calibrate <labeled-dataset> --output calibration.json`
- `copygraph explain <history-a> <history-b> [--calibration calibration.json] --output explanation.json`

The existing `analyze`, `batch`, `benchmark` and `mt5-export` behavior remains compatible.

### Acceptance

- Synthetic and labeled fixtures demonstrate threshold metrics deterministically.
- Calibrated confidence is monotonic.
- Raw V0.2 confidence remains available and unchanged.
- Sparse/unlabeled cases never receive false certainty.
- Full V0.2 regression suite stays green.

## V0.3-B: Forensic Investigation

### Problem

A single confidence score is insufficient for investigation. An auditor needs to understand when the suspected copying occurred, how lot scaling changed, which symbols support the conclusion, and which trades contradict it.

### Design

Add `forensics.py` as a pure analysis layer. It accepts pair analysis plus normalized position lifecycles and optional calibration output, and returns a stable forensic JSON schema.

The forensic report contains:
- account pair and orientation;
- raw and calibrated confidence;
- master/slave lead inference and median delay;
- chronological matched-trade timeline;
- open-delay distribution summary and histogram buckets;
- close-delay consistency summary;
- lot-ratio median and drift over time;
- per-symbol match counts, confidence contributions and unmatched counts;
- risk-evidence coverage;
- top supporting matches;
- top contradictory/weak matches;
- unmatched suspicious trades near the matching window;
- reversal/partial-close segment identifiers when relevant;
- explicit uncertainty/warning flags.

Every displayed forensic fact must trace back to concrete position IDs and timestamps in the normalized lifecycle data. Exported reports must not contain absolute source paths, MT5 credentials, terminal configuration or unrelated account metadata.

### Dashboard

Extend the existing self-contained dashboard to render forensic sections from the JSON schema rather than recomputing metrics in JavaScript. Planned panels:
- confidence and calibration summary;
- matched timeline;
- delay histogram;
- lot-ratio drift;
- symbol breakdown;
- supporting/contradictory evidence table;
- cluster/network view inherited from V0.2.

All report-derived DOM writes continue to use safe text/attribute APIs. No CDN or remote runtime dependency is introduced.

### CLI

Stateless forensic command:
- `copygraph inspect <history-a> <history-b> [--calibration calibration.json] --output forensic.json [--dashboard forensic.html]`

### Acceptance

- Normal-copy, reverse-copy, unrelated, partial-close and netting-reversal fixtures produce deterministic forensic output.
- Every evidence row maps to real lifecycle IDs/timestamps.
- Unrelated fixtures visibly expose contradictory/weak evidence rather than only a low score.
- Dashboard remains self-contained and XSS-safe.

## V0.3-C: Incremental Large-scale Scanner

### Problem

V0.2 `batch` is stateless and recomputes every unordered account pair on each run. For repeated scans of many accounts, this wastes ingestion and pair-analysis work.

### Design

Add `store.py` backed by Python's standard-library `sqlite3`. It remains a local artifact, not a service.

Core entities:
- schema metadata and migration version;
- source fingerprints;
- account snapshots;
- normalized lifecycle records;
- pair-analysis cache;
- forensic report cache where useful;
- scan snapshots and scan membership.

Each discovered source/account receives a deterministic content fingerprint derived from normalized analysis-relevant data, not absolute filesystem path. Re-indexing unchanged content is a no-op. If one account changes among `N` accounts, only its `N-1` pair relations are recomputed; unaffected pair cache entries are reused.

A `scan_id` identifies one immutable completed snapshot. Dashboard and forensic commands can read a completed scan without requiring original source files to remain present.

### Transaction and corruption rules

- Index updates and completed scan publication are transactional.
- A failed scan never replaces the last completed scan.
- Schema version is explicit and migrations are ordered/idempotent.
- Unknown/newer schema versions fail clearly.
- Database corruption or migration failure is reported; CopyGraph does not silently delete/rebuild the database.
- No credentials, terminal login state or absolute source paths are stored in exported reports.
- Internal local database source provenance may store a privacy-safe source identifier/hash and display name where needed, but exported artifacts use only non-sensitive identifiers/counts.

### Deleted and changed sources

Source disappearance is not treated as immediate account deletion. Indexing marks previously known source/account material as absent for the current index pass; a new scan snapshot includes only accounts selected/present for that scan. Historical completed scans remain immutable and queryable.

### CLI

Planned persistent workflow:
- `copygraph index <inputs...> --db copygraph.db`
- `copygraph scan --db copygraph.db --output report.json [--dashboard dashboard.html] [--min-confidence X]`
- `copygraph inspect ACCOUNT_A ACCOUNT_B --db copygraph.db --output forensic.json [--dashboard forensic.html]`

`inspect` has two explicit modes selected by the presence of `--db`: without `--db`, the two positional arguments are history files; with `--db`, they are account IDs in the selected completed/latest scan. Mixing file-path mode with `--db` is invalid rather than guessed.

V0.2 `batch` stays available as the stateless compatibility path.

### Scale target

V0.3 optimizes repeated scans, not distributed computing. Acceptance should prove correct incremental recomputation for dozens to low hundreds of accounts on one machine. No promise is made for thousands of simultaneously active accounts in V0.3.

### Acceptance

- Unchanged re-index performs no account recomputation.
- One changed account recomputes exactly the affected pair set.
- Cached persistent results are equivalent to stateless V0.2/V0.3 analysis for the same data.
- Reopening the database produces the same completed scan output.
- Deleted-source handling preserves old scan snapshots and excludes absent material from new snapshots unless explicitly selected from stored data.
- Transaction failure leaves the prior completed scan usable.

## Cross-cutting schemas and compatibility

V0.3 introduces explicit schema versions for calibration, explanation, forensic and persistent scan outputs. Schema identifiers are independent from package version so future package releases can maintain backward-compatible artifact schemas.

Raw V0.2 fields used by existing consumers are not silently repurposed. New calibrated/explanation fields are additive where practical. Any unavoidable artifact-breaking change requires a new schema version and explicit migration/compatibility behavior.

## Security and privacy

- MT5 access remains read-only and uses an already configured terminal session.
- No login/password/server credentials are persisted.
- Exported JSON/HTML does not contain absolute local paths by default.
- Dashboard data remains embedded locally and self-contained.
- SQLite uses parameterized queries only.
- User-controlled labels and account IDs are treated as untrusted strings in HTML.
- Calibration labels describe pair relationships only; they must not contain secrets.

## Determinism

For identical normalized histories, calibration dataset, configuration and database state, CopyGraph must produce byte-equivalent JSON aside from explicitly excluded operational metadata. Exported timestamps come from source/scan state rather than arbitrary wall-clock values wherever reproducibility matters.

## Testing strategy

Each milestone follows TDD and gets its own reviewer gate.

V0.3-A tests cover:
- threshold sweep metrics;
- monotonic calibration;
- train/evaluation separation;
- score contribution math;
- sparse/missing-risk warnings;
- unchanged V0.2 raw confidence.

V0.3-B tests cover:
- timeline ordering;
- histogram bucketing;
- ratio drift;
- symbol breakdown;
- supporting and contradictory evidence;
- reverse-copy, partial-close and reversal traces;
- dashboard XSS/self-contained output.

V0.3-C tests cover:
- schema creation/migration;
- parameterized persistence;
- unchanged index no-op;
- single-account invalidation;
- pair-cache equivalence;
- immutable scan snapshots;
- transaction rollback;
- deleted source behavior;
- DB reopen determinism.

Before V0.3 release:
- full V0.1/V0.2/V0.3 pytest suite passes;
- compileall passes;
- V0.1 deterministic benchmark remains unchanged unless an explicitly approved calibration-only presentation layer is being exercised;
- stateless V0.2 batch results remain compatible;
- secret scan and diff hygiene pass;
- reviewer Critical/Important findings are fixed with regression tests;
- optional live MT5 read-only probe is repeated without storing history in the repository.

## Delivery sequence

### Milestone A: Calibration and Explainability

Implement calibration dataset parsing, metrics, monotonic calibrator, explanation schema, CLI and tests. Keep work under CHANGELOG `[Unreleased]` and do not bump package version.

### Milestone B: Forensic Investigation

Implement forensic schema, analytics, inspect CLI and dashboard extensions on top of Milestone A outputs. Run a separate reviewer gate before proceeding.

### Milestone C: Incremental Scanner

Implement SQLite schema/migrations, index/invalidation, cached scans and persistent inspect flow. Verify equivalence against stateless analysis.

### Release 0.3.0

Only after all three milestones and the full release gate pass: close `[Unreleased]`, bump package/module version from `0.2.0` to `0.3.0`, cut the bare `0.3.0` tag, push, create the GitHub Release and verify remote artifacts.

## Success criteria

V0.3 is successful when CopyGraph can answer three separate questions with evidence:

1. **How trustworthy is this confidence threshold?** Calibration reports known precision/recall/FPR/F1 on labeled data while preserving raw V0.2 confidence.
2. **Why was this relationship flagged?** Forensic output traces the conclusion to concrete timings, symbols, risk evidence, lot scaling and individual lifecycle IDs.
3. **Can I repeat this over many accounts efficiently?** Persistent indexing avoids recomputing unchanged accounts/pairs and reproduces the same analytical result as stateless execution.
