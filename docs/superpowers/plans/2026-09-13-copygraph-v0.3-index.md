# CopyGraph V0.3 Implementation Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver CopyGraph 0.3.0 as three independently testable milestones: calibrated confidence/explainability, forensic investigation, then incremental SQLite-backed scanning.

**Architecture:** Keep V0.2 matching semantics as the raw evidence engine. Build V0.3 additively in dependency order A -> B -> C, with each milestone receiving its own TDD cycle, reviewer gate, and commit series; only the final release task mints `0.3.0`.

**Tech Stack:** Python 3.11+, Python standard library, `sqlite3`, optional official `MetaTrader5` package already used by V0.2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-copygraph-v0.3-design.md`

## Global Constraints

- Preserve V0.2 raw matching semantics and keep all V0.1/V0.2 tests green.
- Core V0.3 remains standard-library-only; do not add pandas, numpy, sklearn, web frameworks, or hosted services.
- Existing `analyze`, `batch`, `benchmark`, and `mt5-export` commands remain compatible.
- Keep package/module version at `0.2.0` and work under CHANGELOG `[Unreleased]` until A+B+C and the release gate pass.
- Calibration, explanation, forensic, and persistent scan schemas have explicit schema versions independent from the package version.
- No MT5 credentials, terminal login state, or absolute local source paths in exported JSON/HTML.
- User-controlled labels/account IDs are untrusted in HTML; continue JSON escaping plus safe DOM text/attribute APIs.
- Identical normalized data/configuration must produce deterministic analytical artifacts.
- Every feature/bugfix follows RED -> GREEN -> regression verification before commit.
- Preserve the current public `main` history; do not reset/revert/stash user work.

---

## Plan Set and Execution Order

1. `docs/superpowers/plans/2026-09-13-copygraph-v0.3-a-calibration.md`
   - Adds labeled-dataset parsing, monotonic calibration, cross-validated threshold metrics, additive raw-analysis factors, explanation JSON, and `calibrate`/`explain` CLI.
   - Completion gate: milestone A tests + all existing tests + reviewer Critical/Important fixes.

2. `docs/superpowers/plans/2026-09-13-copygraph-v0.3-b-forensics.md`
   - Adds deterministic forensic analytics, evidence traceability, stateless `inspect`, and a forensic HTML renderer that consumes JSON rather than recomputing metrics.
   - Depends only on public interfaces produced by A.
   - Completion gate: milestone B tests + full regression + reviewer Critical/Important fixes.

3. `docs/superpowers/plans/2026-09-13-copygraph-v0.3-c-scanner.md`
   - Adds SQLite persistence, source/account indexing, fingerprint invalidation, pair cache reuse, immutable scan snapshots, persistent `inspect`, and equivalence checks against stateless execution.
   - Depends on A explanation/calibration interfaces and B forensic report interface.
   - Completion gate: milestone C tests + full regression + transaction/corruption reviewer gate.

## Working Baseline

- Approved spec commit baseline: `d11705c3b094797d68916952d3ea90d1042f7e55`.
- Current released package: `0.2.0`.
- V0.2 release tag: `0.2.0`.
- Current full suite baseline before V0.3 implementation: 69 tests.

## Cross-Milestone Interface Freeze

Milestone A must publish these interfaces before B starts:

```python
# src/copygraph/calibration.py
@dataclass(frozen=True, slots=True)
class ScoredCase:
    case_id: str
    label: str
    expected_orientation: str | None
    raw_confidence: float
    observed_orientation: str

@dataclass(frozen=True, slots=True)
class CalibrationDataset:
    schema_version: str
    name: str | None
    cases: tuple[ScoredCase, ...]

@dataclass(frozen=True, slots=True)
class CalibrationBlock:
    max_raw: float
    probability: float
    count: int

@dataclass(frozen=True, slots=True)
class CalibrationModel:
    schema_version: str
    fitted_case_ids: tuple[str, ...]
    blocks: tuple[CalibrationBlock, ...]


def load_calibration_dataset(path: str | Path) -> CalibrationDataset: ...
def fit_monotonic_calibrator(cases: Sequence[ScoredCase]) -> CalibrationModel: ...
def apply_calibration(raw_confidence: float, model: CalibrationModel) -> float: ...
def cross_validated_predictions(cases: Sequence[ScoredCase]) -> list[dict[str, object]]: ...
def evaluate_calibrator(
    model: CalibrationModel,
    cases: Sequence[ScoredCase],
    *,
    allow_in_sample: bool = False,
) -> list[dict[str, object]]: ...
def build_calibration_report(dataset: CalibrationDataset) -> dict[str, object]: ...

# src/copygraph/explain.py
def explain_pair(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]: ...
```

Milestone A also extends `PairAnalysis` additively with `overlap_factor`, `sample_factor`, and `matching_window_s`; B/C may rely on those names but must not change their meaning.

Milestone B must publish these interfaces before C starts:

```python
# src/copygraph/forensics.py
def build_forensic_report(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]: ...

# src/copygraph/forensic_dashboard.py
def render_forensic_dashboard(report: Mapping[str, object]) -> str: ...
def write_forensic_dashboard(report: Mapping[str, object], output: str | Path) -> Path: ...
```

Milestone C must keep the stateless interfaces above unchanged and add persistent APIs only.

## Milestone Checkpoint Protocol

At the end of each plan:

- [ ] Run that milestone's targeted tests.
- [ ] Run `py -3 -m pytest` and record the exact pass count.
- [ ] Run `py -3 -m compileall -q src tests`.
- [ ] Run `py -3 -m copygraph benchmark` and confirm V0.1 normal/reverse/unrelated outputs are unchanged.
- [ ] Run `git diff --check`.
- [ ] Request a read-only reviewer focused on that milestone's risk areas.
- [ ] Reproduce each accepted Critical/Important finding with a failing regression test before fixing it.
- [ ] Commit the milestone in small imperative commits; do not bump the version or create a release tag.
- [ ] Update CHANGELOG `[Unreleased]` only with behavior that actually exists and passed verification.

## Self-review Coverage Matrix

- Calibration dataset schema, monotonic fitting, no in-sample leakage, threshold metrics, orientation diagnostics: Plan A Tasks 2-4.
- Raw-score preservation, factor exposure, explainable component math, sparse/missing-risk warnings: Plan A Tasks 1 and 5.
- `calibrate`/`explain` CLI and V0.2 command compatibility: Plan A Task 6.
- Timeline traceability, open/close delay diagnostics, lot-ratio drift, symbol/risk breakdown, reverse/reversal IDs, contradictory/unmatched evidence: Plan B Tasks 1-2.
- Self-contained/XSS-safe forensic HTML and pair network without inventing cluster membership: Plan B Task 3.
- Stateless `inspect` compatibility: Plan B Task 4.
- JSON/analysis serialization, explicit SQLite schema version, corruption/newer-version errors: Plan C Tasks 1-2.
- Authoritative source indexing, split-position equivalence, immutable account snapshots, absence handling: Plan C Task 3.
- Shared stateless/persistent report assembly and analytical equivalence: Plan C Tasks 4-5.
- N-1 cache invalidation, engine-versioned pair cache, deterministic scan IDs, rollback, historical scan reopening: Plan C Tasks 5-6.
- Historical persistent forensic inspect and request-order preservation: Plan C Task 7.
- `index`/`scan`/dual-mode `inspect` CLI and connection cleanup: Plan C Task 8.
- Low-hundreds scale target and 100-account incremental cache proof: Plan C Task 9.
- Version remains `0.2.0` throughout implementation; final `0.3.0` mint/tag/GitHub Release happens only in the release task below.

Self-review result: no uncovered approved-spec requirement, no unresolved placeholder, and cross-plan interface names are consistent.

## Final V0.3 Release Task

Run only after plans A, B, and C are fully complete.

- [ ] Re-read `pyproject.toml`, `src/copygraph/__init__.py`, CHANGELOG, remote tags, and GitHub Releases to derive release state cold.
- [ ] Run the full pytest suite, compileall, benchmark, secret scan, and diff hygiene on a clean worktree.
- [ ] Run an optional live read-only MT5 probe without writing history into the repository.
- [ ] Rename top CHANGELOG `[Unreleased]` to `[0.3.0] - YYYY-MM-DD` using the actual calendar date on which post-release verification is performed.
- [ ] Change `pyproject.toml` project version and `copygraph.__version__` from `0.2.0` to `0.3.0` in the same release commit.
- [ ] Re-run full verification after the version-only changes.
- [ ] Commit `Release 0.3.0`.
- [ ] Create bare tag `0.3.0` (never `v0.3.0`) and push `main` plus the tag only after explicit push authorization in the execution session.
- [ ] Create GitHub Release title `v0.3.0: calibrated forensic scanner`, using user-facing notes derived from the final CHANGELOG and a full-changelog link from `0.2.0...0.3.0`.
- [ ] Verify local HEAD = remote `main` = tag target, GitHub Release is Latest, repository remains PUBLIC/default `main`, worktree clean, and full suite passes after release.
