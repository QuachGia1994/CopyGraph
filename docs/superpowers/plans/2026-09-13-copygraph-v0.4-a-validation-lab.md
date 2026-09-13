# CopyGraph V0.4-A Validation Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, fail-closed Validation Lab around the unchanged V0.3 evidence engine so calibration candidates can be evaluated against hybrid ground truth, leakage-safe holdouts, multi-window alert consensus, subgroup stability gates, and explicit promotion policy.

**Architecture:** Add a new `copygraph.validation` package with one-way dependencies on the existing ingest/lifecycle/matching/calibration/forensics code. Keep the V0.3 raw matcher and scanner semantics unchanged. Validation artifacts are immutable canonical JSON objects keyed by hashes; training/cross-validation selects thresholds, frozen/recent holdouts only evaluate them, and promotion is a separate explicit operation.

**Tech Stack:** Python 3.11+, standard library only, existing CopyGraph `CalibrationModel`/`ScoredCase`/`fit_monotonic_calibrator()`/`apply_calibration()`, pytest, argparse CLI, deterministic SHA-256 canonical JSON.

**Spec:** `docs/superpowers/specs/2026-09-13-copygraph-v0.4-a-validation-lab-design.md`

## Global Constraints

- Do not change V0.3 raw matching weights or matching semantics.
- Do not add third-party runtime dependencies.
- `validation -> ingest/lifecycle/matching/calibration/forensics` only; raw matcher/scanner must not import validation.
- Hybrid labels are `confirmed_copy`, `suspected_copy`, `unrelated`, `uncertain`; primary fit uses `confirmed_copy/high` and `unrelated/high` only.
- `confirmed_copy` must preserve `real_confirmed` vs `controlled_confirmed` provenance.
- Splits are account-disjoint and strategy-family-disjoint; leakage audit is fail-closed.
- Windows are exactly `7d`, `30d`, and `full`; full-history cannot independently promote a pair to high confidence.
- `HIGH_CONFIDENCE` requires both 7d and 30d to meet `high_threshold`.
- Review-tier cumulative FPR counts both `REVIEW_QUEUE` and `HIGH_CONFIDENCE` as alerts.
- Promotion gates: high-confidence FPR <= 0.1%, cumulative review-tier FPR <= 1%, high-confidence recall >= 60%, combined recall >= 85%.
- A subgroup override requires sample floor + bootstrap stability + temporal stability; otherwise fallback to global.
- Core holdout and recent holdout must both pass; holdouts never tune thresholds in the same run.
- Phase 1 target is 300-500 reviewed relationships/cases for pipeline validation; no production-grade <=0.1% FPR claim until Phase 2 >=2,000 reviewed pairs with sufficient hard-negative coverage.
- Exported artifacts must not contain credentials, MT5 secrets, or raw absolute local paths.
- Package version remains `0.3.0` until the final V0.4 release gate.

---

## File Structure

Create these focused modules:

- `src/copygraph/validation/__init__.py` — public Validation Lab exports only.
- `src/copygraph/validation/models.py` — immutable dataclasses/enums for cases, revisions, policies, run rows, audits, promotion decisions.
- `src/copygraph/validation/serde.py` — canonical JSON serialization, schema validation, SHA-256 artifact hashes.
- `src/copygraph/validation/manifest.py` — immutable manifest construction and deterministic split assignment from leakage groups.
- `src/copygraph/validation/leakage.py` — fail-closed account/family/seed/lifecycle/source overlap audit.
- `src/copygraph/validation/consensus.py` — 7d/30d/full tier classification.
- `src/copygraph/validation/metrics.py` — pair-level and window-level confusion/alert metrics and threshold selection.
- `src/copygraph/validation/stability.py` — deterministic bootstrap and chronological temporal diagnostics.
- `src/copygraph/validation/hierarchy.py` — subgroup eligibility, local model diagnostics, global fallback.
- `src/copygraph/validation/review.py` — review/adjudication revisions and eligibility rules.
- `src/copygraph/validation/mining.py` — hard-negative ranking and false-positive registry rules.
- `src/copygraph/validation/collision.py` — deterministic controlled collision-suite generator.
- `src/copygraph/validation/runner.py` — end-to-end candidate evaluation pipeline.
- `src/copygraph/validation/promotion.py` — fail-closed promotion state machine and baseline regression check.
- `src/copygraph/validation/report.py` — immutable artifact bundle + self-contained HTML summary.
- Modify `src/copygraph/cli.py` — add narrow `copygraph validation ...` subcommands only.
- Modify `README.md` and `CHANGELOG.md` under `[Unreleased]`; do not bump version.

Tests mirror responsibilities under `tests/validation/` plus one Phase-1 scale fixture test.

---

### Task 1: Validation contracts, immutable revisions, and canonical serialization

**Files:**
- Create: `src/copygraph/validation/__init__.py`
- Create: `src/copygraph/validation/models.py`
- Create: `src/copygraph/validation/serde.py`
- Create: `tests/validation/test_models.py`
- Create: `tests/validation/test_serde.py`

**Interfaces:**
- Produces: `ValidationCase`, `CaseRevision`, `Provenance`, `DatasetManifest`, `ValidationPolicy`, `WindowScore`, `OperationalTier`, `LeakageAuditResult`, `ValidationRunResult`, `PromotionDecision`.
- Produces: `canonical_json(value) -> str`, `artifact_hash(value) -> str`, `case_to_dict()/case_from_dict()`, `manifest_to_dict()/manifest_from_dict()`.
- Consumes: no new project modules except Python stdlib.

- [ ] **Step 1: Write failing model invariant tests**

```python
from copygraph.validation.models import Provenance, ValidationCase


def test_validation_case_requires_relationship_and_supported_window():
    provenance = Provenance(
        source_hashes=("src-a",),
        normalized_fingerprints=("norm-a",),
        lifecycle_fingerprints=("life-a",),
        engine_version="1",
        calibration_version=None,
        scan_id=None,
        replay_recipe=None,
        replay_seed=None,
        reviewer_ids=("reviewer-1",),
        review_timestamps=("2026-09-13T00:00:00Z",),
        evidence_snapshot_hash="evidence-a",
        label_policy_version="1",
    )
    case = ValidationCase(
        case_id="pair-a:7d:r1",
        relationship_id="pair-a",
        revision_id="r1",
        account_a="a",
        account_b="b",
        window_type="7d",
        source_kind="real",
        label="confirmed_copy",
        label_confidence="high",
        confirmed_kind="real_confirmed",
        strategy_family_id="family-1",
        provisional_family_id=None,
        broker_tags=("broker-x",),
        symbol_tags=("XAUUSD",),
        session_tags=("london",),
        review_status="dual_reviewed",
        provenance=provenance,
        evidence_snapshot_hash="evidence-a",
    )
    assert case.relationship_id == "pair-a"
```

Also assert constructors reject unsupported `window_type`, label, confidence, mismatched `confirmed_kind`, identical account IDs, or empty revision IDs.

- [ ] **Step 2: Run the model tests and confirm RED**

Run: `python -m pytest -q tests/validation/test_models.py`
Expected: import failure because `copygraph.validation` does not exist.

- [ ] **Step 3: Implement immutable validation dataclasses and enums**

In `models.py`, use frozen/slots dataclasses. Define exact policy fields:

```python
@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    schema_version: str = "1.0"
    policy_version: str = "1"
    high_fpr_max: float = 0.001
    review_fpr_max: float = 0.01
    high_recall_min: float = 0.60
    combined_recall_min: float = 0.85
    subgroup_min_positive: int = 100
    subgroup_min_negative: int = 1000
    bootstrap_samples: int = 1000
    bootstrap_seed: int = 404
    near_threshold_band: float = 0.03
```

Define `OperationalTier` values exactly `INSUFFICIENT_EVIDENCE`, `NO_ALERT`, `REVIEW_QUEUE`, `HIGH_CONFIDENCE`.

- [ ] **Step 4: Write failing deterministic serialization tests**

```python
from copygraph.validation.serde import artifact_hash, canonical_json, case_from_dict, case_to_dict


def test_case_roundtrip_and_hash_are_deterministic(validation_case):
    payload = case_to_dict(validation_case)
    assert case_from_dict(payload) == validation_case
    assert canonical_json(payload) == canonical_json(dict(reversed(list(payload.items()))))
    assert artifact_hash(payload) == artifact_hash(case_to_dict(validation_case))
```

Add privacy validation that exported path-like fields are rejected from provenance payloads when they are absolute Windows or POSIX paths.

- [ ] **Step 5: Implement canonical serialization and schema validation**

`canonical_json()` uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`; `artifact_hash()` is SHA-256 over UTF-8 canonical JSON. All `*_from_dict` readers reject unknown schema versions and invalid enums instead of silently coercing.

- [ ] **Step 6: Run Task 1 tests GREEN**

Run: `python -m pytest -q tests/validation/test_models.py tests/validation/test_serde.py`
Expected: all PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/copygraph/validation tests/validation/test_models.py tests/validation/test_serde.py
git commit -m "Add validation data contracts"
```

---

### Task 2: Immutable manifest builder, leakage groups, and fail-closed audit

**Files:**
- Create: `src/copygraph/validation/manifest.py`
- Create: `src/copygraph/validation/leakage.py`
- Create: `tests/validation/test_manifest.py`
- Create: `tests/validation/test_leakage.py`

**Interfaces:**
- Consumes: `ValidationCase`, `DatasetManifest`, `artifact_hash` from Task 1.
- Produces: `build_manifest(cases, *, dataset_id, revision, engine_version, label_policy_version, split_policy_version, calibration_policy_version, explicit_split_by_relationship=None) -> DatasetManifest`.
- Produces: `build_leakage_groups(cases) -> dict[str, str]` mapping account ID to deterministic group ID.
- Produces: `audit_manifest(manifest, cases) -> LeakageAuditResult`.

- [ ] **Step 1: Write RED tests for account/family/replay grouping**

```python
def test_build_leakage_groups_unifies_manual_family_and_replay_seed(cases):
    groups = build_leakage_groups(cases)
    assert groups["a"] == groups["b"]
    assert groups["c"] == groups["d"]
```

Fixtures must cover manual strategy family, provisional family, and controlled replay seed. Use deterministic union-find ordering so the same input produces the same group IDs.

- [ ] **Step 2: Run RED**

Run: `python -m pytest -q tests/validation/test_manifest.py tests/validation/test_leakage.py`
Expected: missing manifest/leakage modules.

- [ ] **Step 3: Implement deterministic group construction and manifest hashing**

Manifest stores exact `(case_id, revision_id)` references, relationship split assignment, family/leakage group IDs, policy versions, engine version, and checksum. The checksum excludes its own checksum field.

Default deterministic split assignment is group-based and hash-bucketed with policy constants `train=70`, `core_holdout=15`, `recent_holdout=15`. Challenge-only labels (`suspected_copy`, `uncertain`) are assigned to `challenge` regardless of hash bucket. Explicit relationship splits are accepted for frozen holdout maintenance but still audited.

- [ ] **Step 4: Add RED leakage cases**

Add separate tests that force audit failure for:

```text
same account across train/core
manual family across train/recent
provisional family across train/core
same replay seed across train/core
same lifecycle fingerprint across train/holdout
same source hash across train/holdout when provenance policy marks it exclusive
missing referenced case revision
```

Each result must expose stable machine-readable violation codes, e.g. `ACCOUNT_CROSS_SPLIT`, `FAMILY_CROSS_SPLIT`, `REPLAY_SEED_CROSS_SPLIT`, `LIFECYCLE_CROSS_SPLIT`, `SOURCE_PROVENANCE_CROSS_SPLIT`, `MISSING_CASE_REVISION`.

- [ ] **Step 5: Implement fail-closed `audit_manifest()`**

`LeakageAuditResult.passed` is true only when violations are empty. Sort violations deterministically by `(code, relationship_id, detail)`.

- [ ] **Step 6: Run Task 2 GREEN**

Run: `python -m pytest -q tests/validation/test_manifest.py tests/validation/test_leakage.py`
Expected: all PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/copygraph/validation/manifest.py src/copygraph/validation/leakage.py tests/validation/test_manifest.py tests/validation/test_leakage.py
git commit -m "Add leakage-safe validation manifests"
```

---

### Task 3: Multi-window consensus and separate pair/window metrics

**Files:**
- Create: `src/copygraph/validation/consensus.py`
- Create: `src/copygraph/validation/metrics.py`
- Create: `tests/validation/test_consensus.py`
- Create: `tests/validation/test_metrics.py`

**Interfaces:**
- Consumes: `WindowScore`, `OperationalTier`, `ValidationPolicy`.
- Produces: `classify_relationship(window_scores, *, high_threshold, review_threshold) -> OperationalTier`.
- Produces: `confusion_metrics(labels_and_alerts) -> ThresholdMetrics` using existing `copygraph.calibration.ThresholdMetrics` shape where useful.
- Produces: `select_operating_thresholds(rows, policy) -> tuple[float, float] | None` returning `(high_threshold, review_threshold)`.
- Produces: `evaluate_pair_metrics(relationship_outcomes) -> dict[str, float|int]` and `evaluate_window_metrics(window_rows) -> dict[str, object]`.

- [ ] **Step 1: Write the consensus truth table RED test**

```python
@pytest.mark.parametrize(
    "seven,thirty,full,expected",
    [
        (0.95, 0.96, 0.20, OperationalTier.HIGH_CONFIDENCE),
        (0.95, 0.40, 0.20, OperationalTier.REVIEW_QUEUE),
        (0.20, 0.30, 0.95, OperationalTier.REVIEW_QUEUE),
        (0.20, 0.30, 0.40, OperationalTier.NO_ALERT),
    ],
)
def test_multi_window_consensus(seven, thirty, full, expected):
    scores = make_scores(seven, thirty, full)
    assert classify_relationship(scores, high_threshold=0.9, review_threshold=0.7) is expected
```

Add an insufficient-evidence case where either required recent window has `eligible=False`.

- [ ] **Step 2: Run RED, then implement consensus exactly**

Rules:

```python
if not seven.eligible or not thirty.eligible:
    return OperationalTier.INSUFFICIENT_EVIDENCE
if seven.score >= high_threshold and thirty.score >= high_threshold:
    return OperationalTier.HIGH_CONFIDENCE
if seven.score >= review_threshold or thirty.score >= review_threshold or full.score >= high_threshold:
    return OperationalTier.REVIEW_QUEUE
return OperationalTier.NO_ALERT
```

Reject `review_threshold > high_threshold`.

- [ ] **Step 3: Write RED tests separating pair FPR from window false-alert rate**

Create two unrelated relationships where one produces repeated window alerts. Assert pair FPR counts that relationship once while window false-alert rate counts every alerted window.

- [ ] **Step 4: Implement deterministic threshold selection from train rows only**

Use calibrated-confidence candidate thresholds from unique observed scores plus `0.0` and `1.0`. For high threshold, choose the lowest threshold satisfying `FPR <= policy.high_fpr_max` and `recall >= policy.high_recall_min`; this maximizes recall under the FPR ceiling. For review threshold, restrict to `threshold <= high_threshold` and choose the lowest threshold satisfying cumulative `FPR <= policy.review_fpr_max` and recall `>= policy.combined_recall_min`. Return `None` when either tier cannot satisfy its gate.

- [ ] **Step 5: Add exact boundary tests**

Construct integer confusion tables that hit exactly 0.1%, 1%, 60%, and 85%; equality must PASS and any value above/below the required side must FAIL.

- [ ] **Step 6: Run Task 3 GREEN**

Run: `python -m pytest -q tests/validation/test_consensus.py tests/validation/test_metrics.py`
Expected: all PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/copygraph/validation/consensus.py src/copygraph/validation/metrics.py tests/validation/test_consensus.py tests/validation/test_metrics.py
git commit -m "Add multi-window validation metrics"
```

---

### Task 4: Bootstrap, temporal stability, and hierarchical subgroup fallback

**Files:**
- Create: `src/copygraph/validation/stability.py`
- Create: `src/copygraph/validation/hierarchy.py`
- Create: `tests/validation/test_stability.py`
- Create: `tests/validation/test_hierarchy.py`

**Interfaces:**
- Consumes: train rows, `ValidationPolicy`, existing `fit_monotonic_calibrator()` and `apply_calibration()`.
- Produces: `bootstrap_diagnostics(rows, *, threshold, policy, tier) -> BootstrapDiagnostics`.
- Produces: `temporal_diagnostics(rows, *, threshold, policy, tier) -> TemporalDiagnostics`.
- Produces: `evaluate_subgroup(name, rows, *, global_model, policy) -> SubgroupDecision` with `use_global: bool`.

- [ ] **Step 1: Write fixed-seed bootstrap determinism test**

Run the same 200-row fixture twice and assert byte-for-byte equal serialized diagnostics. Bootstrap sampling uses `random.Random(policy.bootstrap_seed)` and exactly `policy.bootstrap_samples` resamples.

- [ ] **Step 2: Implement percentile bootstrap diagnostics**

Record threshold, sample counts, FPR 2.5/50/97.5 percentiles, recall 2.5/50/97.5 percentiles, and threshold IQR when threshold is re-selected inside each resample. Do not import NumPy; use sorted lists and a deterministic linear/interpolated percentile helper owned by `stability.py`.

- [ ] **Step 3: Write temporal block RED tests**

Rows carry an ISO UTC `event_time`. Sort chronologically, partition into up to four non-empty contiguous blocks, and compute the same tier metrics per block. Test that a late block breaching the configured FPR ceiling fails temporal stability even when the aggregate passes.

- [ ] **Step 4: Implement temporal diagnostics and sparse-coverage failure**

If fewer than two non-empty blocks contain both positive and negative evaluable rows, return `passed=False` with reason `INSUFFICIENT_TEMPORAL_COVERAGE`.

- [ ] **Step 5: Write hierarchical subgroup tests**

Cover:

```text
99 positives / 1000 negatives -> fallback global
100 positives / 999 negatives -> fallback global
sample floor passes but bootstrap upper FPR CI fails -> fallback global
bootstrap passes but temporal gate fails -> fallback global
all gates pass -> subgroup model eligible
```

- [ ] **Step 6: Implement subgroup evaluator**

Fit subgroup `CalibrationModel` only after the sample floor passes. A subgroup override is active only if both stability diagnostics pass; otherwise keep diagnostics but set `use_global=True` and return the unchanged global model reference/hash.

- [ ] **Step 7: Run Task 4 GREEN**

Run: `python -m pytest -q tests/validation/test_stability.py tests/validation/test_hierarchy.py`
Expected: all PASS.

- [ ] **Step 8: Commit Task 4**

```bash
git add src/copygraph/validation/stability.py src/copygraph/validation/hierarchy.py tests/validation/test_stability.py tests/validation/test_hierarchy.py
git commit -m "Add calibration stability gates"
```

---

### Task 5: Review/adjudication revisions, hard-negative mining, false-positive registry, collision suite

**Files:**
- Create: `src/copygraph/validation/review.py`
- Create: `src/copygraph/validation/mining.py`
- Create: `src/copygraph/validation/collision.py`
- Create: `tests/validation/test_review.py`
- Create: `tests/validation/test_mining.py`
- Create: `tests/validation/test_collision.py`

**Interfaces:**
- Produces: `ReviewRecord`, `AdjudicationRecord`, `append_review_revision(case, review) -> CaseRevision`.
- Produces: `requires_second_review(case, *, calibrated_score, high_threshold, review_threshold, policy) -> bool`.
- Produces: `rank_hard_negatives(cases, evidence_by_case) -> tuple[str, ...]`.
- Produces: `register_false_positive(registry, case, run_id) -> FalsePositiveRegistry` without altering current manifest.
- Produces: `generate_collision_suite(*, relationship_count, seed) -> tuple[ValidationCase, ...]` plus controlled evidence fixtures.

- [ ] **Step 1: Write review policy RED tests**

Assert every `confirmed_copy` requires second review; any disagreement requires adjudication; any calibrated score within `policy.near_threshold_band` of either operating threshold requires second review. Clear unrelated/high cases far from thresholds may remain single-reviewed.

- [ ] **Step 2: Implement append-only review/adjudication records**

Never mutate the prior revision. New revisions receive deterministic IDs derived from previous revision hash + new review/adjudication payload. `original_review_ids` remain preserved in adjudication.

- [ ] **Step 3: Write hard-negative ranking tests**

Rank unrelated/high cases higher when they have more of: high raw confidence, close open timing, overlapping symbols, similar active sessions, stable independent lot ratio. Tie-break by `case_id`.

- [ ] **Step 4: Implement false-positive registry contamination guard**

Registry insertion stores `case_id`, `revision_id`, originating run, evidence hash, and discovered timestamp. Provide `assert_not_in_manifest_holdout(registry_entry, manifest)` that raises if a newly registered false positive is inserted into the same frozen holdout revision being used to claim improvement.

- [ ] **Step 5: Write collision-suite reproducibility tests**

Generate at least 20 controlled unrelated relationships with same/near symbols, sessions, timing distributions, and lot ratios but independent seeds. Same generator seed must produce identical canonical output; a different seed must change output.

- [ ] **Step 6: Implement collision generator without touching matching semantics**

Reuse existing normalized history shapes from test helpers or create validation-only JSON event fixtures. The generator labels every relationship `unrelated/high`, `source_kind="controlled"`, and records recipe version + independent replay seeds in provenance.

- [ ] **Step 7: Run Task 5 GREEN**

Run: `python -m pytest -q tests/validation/test_review.py tests/validation/test_mining.py tests/validation/test_collision.py`
Expected: all PASS.

- [ ] **Step 8: Commit Task 5**

```bash
git add src/copygraph/validation/review.py src/copygraph/validation/mining.py src/copygraph/validation/collision.py tests/validation/test_review.py tests/validation/test_mining.py tests/validation/test_collision.py
git commit -m "Add reviewed validation challenge data"
```

---

### Task 6: End-to-end ValidationRun and fail-closed promotion state machine

**Files:**
- Create: `src/copygraph/validation/runner.py`
- Create: `src/copygraph/validation/promotion.py`
- Create: `tests/validation/test_runner.py`
- Create: `tests/validation/test_promotion.py`

**Interfaces:**
- Consumes: manifest, exact case revisions, V0.3 `fit_monotonic_calibrator()` and `apply_calibration()`, Tasks 2-5 diagnostics.
- Produces: `run_validation(manifest, cases, policy, *, current_production=None) -> ValidationRunResult`.
- Produces: `decide_promotion(run, *, current_production=None) -> PromotionDecision`.

- [ ] **Step 1: Write RED runner test with train/core/recent/challenge data**

Build a small deterministic fixture where train can fit a monotonic model and select both thresholds, then assert:

```python
run = run_validation(manifest, cases, policy)
assert run.leakage_audit.passed
assert run.high_threshold is not None
assert run.review_threshold is not None
assert set(run.holdouts) == {"core_holdout", "recent_holdout"}
assert "challenge" in run.diagnostics
```

- [ ] **Step 2: Implement training conversion without changing V0.3 calibration**

Map eligible validation cases to existing `ScoredCase`:

```python
label = "copy" if case.label == "confirmed_copy" else "unrelated"
ScoredCase(
    case_id=case.case_id,
    label=label,
    expected_orientation=None,
    raw_confidence=case.raw_confidence,
    observed_orientation=case.observed_orientation,
)
```

Store `raw_confidence` and `observed_orientation` in validation score input/evidence snapshot, not by altering `ScoredCase` itself.

- [ ] **Step 3: Enforce run order and fail-closed behavior**

`run_validation()` order is exactly: resolve revisions -> leakage audit -> train fit -> train threshold selection -> subgroup diagnostics -> bootstrap/temporal diagnostics -> core evaluation -> recent evaluation -> consensus metrics -> candidate run artifact. If leakage or threshold selection fails, return/raise a validation error with diagnostics and never create a promotable result.

- [ ] **Step 4: Write promotion boundary and regression RED tests**

Cover exact gate equality, a core pass/recent fail, recent pass/core fail, missing diagnostics, subgroup override without stability, and candidate core FPR worse than current production even when recall improves.

- [ ] **Step 5: Implement promotion lifecycle**

Use states `CANDIDATE`, `EVALUATED`, `PROMOTED`, `REJECTED`. `decide_promotion()` never modifies a calibration file in place; it emits an immutable `PromotionDecision`. When current production is supplied, reject if candidate core high-confidence or cumulative review-tier FPR is worse than baseline.

- [ ] **Step 6: Prove holdout cannot tune thresholds**

Add a test where only holdout scores change. Assert selected `high_threshold` and `review_threshold` remain identical because selection reads train rows only.

- [ ] **Step 7: Run Task 6 GREEN**

Run: `python -m pytest -q tests/validation/test_runner.py tests/validation/test_promotion.py`
Expected: all PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add src/copygraph/validation/runner.py src/copygraph/validation/promotion.py tests/validation/test_runner.py tests/validation/test_promotion.py
git commit -m "Add validation run promotion gates"
```

---

### Task 7: Reproducible artifact bundle and self-contained report

**Files:**
- Create: `src/copygraph/validation/report.py`
- Create: `tests/validation/test_report.py`

**Interfaces:**
- Produces: `write_validation_bundle(run, manifest, output_dir, *, promotion=None) -> dict[str, Path]`.
- Produces: `write_validation_report(run, manifest, output_path, *, promotion=None) -> Path`.
- Consumes: `safe_json_for_html()` from existing `copygraph.htmlutil`.

- [ ] **Step 1: Write RED artifact contract test**

Assert bundle contains exactly the applicable files: `validation-run.json`, `metrics.json`, `leakage-audit.json`, `subgroups.json`, `manifest.json`, and `promotion-decision.json` only when promotion was attempted.

- [ ] **Step 2: Implement atomic deterministic writes**

Write each JSON to a temporary sibling then `replace()` it. Sort keys and terminate with newline. Include schema/version/hash references in every top-level artifact.

- [ ] **Step 3: Write RED privacy and HTML injection tests**

Feed account/broker tags containing `<script>` and Windows path-like strings. Assert HTML contains escaped JSON/text only, no executable injected markup, and exported JSON contains no raw absolute source path fields.

- [ ] **Step 4: Implement self-contained HTML report**

No CDN. Render summary gates, core/recent metrics, subgroup fallback reasons, leakage violations, bootstrap/temporal diagnostics, hard-negative coverage, and promotion status. Use `textContent` for report-derived strings and `safe_json_for_html()` for embedded data.

- [ ] **Step 5: Run Task 7 GREEN**

Run: `python -m pytest -q tests/validation/test_report.py`
Expected: all PASS.

- [ ] **Step 6: Commit Task 7**

```bash
git add src/copygraph/validation/report.py tests/validation/test_report.py
git commit -m "Add validation report artifacts"
```

---

### Task 8: Validation CLI surface with explicit evaluate/promote separation

**Files:**
- Modify: `src/copygraph/cli.py`
- Create: `tests/validation/test_cli.py`

**Interfaces:**
- Adds commands:
  - `copygraph validation build-manifest CASES.json --output manifest.json`
  - `copygraph validation audit manifest.json CASES.json --output audit.json`
  - `copygraph validation evaluate manifest.json CASES.json --output-dir validation-run`
  - `copygraph validation promote validation-run/validation-run.json --output promotion-decision.json [--current-production production-run.json]`
  - `copygraph validation report validation-run/validation-run.json manifest.json --output validation-report.html [--promotion promotion-decision.json]`

- [ ] **Step 1: Write parser RED tests for every subcommand**

Use `main([...])` with temp files. Assert `evaluate` does not write a promotion decision and `promote` requires an evaluated run artifact.

- [ ] **Step 2: Add nested argparse parser**

Under the existing root parser create `validation = subparsers.add_parser("validation")`, then nested required subcommands. Keep existing `analyze`, `batch`, `calibrate`, `explain`, `inspect`, `index`, `scan`, `benchmark`, `mt5-export` behavior unchanged.

- [ ] **Step 3: Implement command dispatch with file closure and fail-closed errors**

Load canonical JSON through validation serde functions; create output parents explicitly; return non-zero via raised/parser errors for invalid manifests, leakage failures, missing candidate artifacts, or failed promotion prerequisites.

- [ ] **Step 4: Add stateless regression test**

Monkeypatch validation store/runner entry points to fail if touched, invoke an existing stateless command such as `copygraph benchmark`, and assert it still succeeds without importing/initializing validation runtime state beyond normal module import.

- [ ] **Step 5: Run Task 8 GREEN plus existing CLI tests**

Run: `python -m pytest -q tests/validation/test_cli.py tests/test_cli.py tests/test_cli_calibration.py tests/test_cli_inspect.py tests/test_cli_v03_scanner.py`
Expected: all PASS.

- [ ] **Step 6: Commit Task 8**

```bash
git add src/copygraph/cli.py tests/validation/test_cli.py
git commit -m "Add validation lab CLI"
```

---

### Task 9: Phase-1 scale fixture, V0.3 invariants, documentation, and full gate

**Files:**
- Create: `tests/validation/test_phase1_scale.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Optionally create: `examples/validation/phase1-schema-example.json` if a small example materially improves README clarity; do not commit real reviewed histories.

**Interfaces:**
- Consumes all prior tasks.
- Produces no new production API; this task proves acceptance and documents use.

- [ ] **Step 1: Write a 360-relationship Phase-1 synthetic/controlled pipeline test**

Generate 360 deterministic relationships with three windows each: controlled confirmed positives, easy unrelated negatives, and hard/collision negatives. Keep runtime bounded by embedding precomputed raw confidence/evidence rows rather than generating MT5 history for every relationship. Assert the manifest, leakage audit, train fit, holdouts, consensus, subgroup fallback, and report bundle all execute end-to-end.

- [ ] **Step 2: Add raw-engine invariant assertion**

Run existing deterministic benchmark and assert exact unchanged values:

```text
normal confidence = 0.9681481481481482
reverse confidence = 0.9681481481481482
unrelated confidence = 0.0
```

Do not update these expected values to make a regression pass.

- [ ] **Step 3: Document V0.4-A workflow and claim limits**

README must show the five validation commands, explain hybrid labels, frozen/recent holdouts, 7d/30d/full consensus, and explicitly state that Phase 1 validates the pipeline only. CHANGELOG `[Unreleased]` records Validation Lab additions. Keep package version `0.3.0`.

- [ ] **Step 4: Run validation package tests**

Run: `python -m pytest -q tests/validation`
Expected: all PASS.

- [ ] **Step 5: Run the complete non-scale suite**

If a one-shot run exceeds the connector timeout, partition tests without overlap and report each partition. Do not infer PASS from partial output.

Run: `python -m pytest -q --ignore=tests/validation/test_phase1_scale.py --ignore=tests/test_scanner_scale.py`
Expected: all PASS.

- [ ] **Step 6: Run scale tests separately**

Run: `python -m pytest -q -rA tests/test_scanner_scale.py tests/validation/test_phase1_scale.py`
Expected: both PASS.

- [ ] **Step 7: Compile and benchmark**

Run: `python -m compileall -q src tests`
Expected: no output.

Run: `python -m copygraph benchmark`
Expected raw values exactly match the V0.3 invariant values above.

- [ ] **Step 8: Run diff/privacy hygiene**

Run: `git diff --check`
Expected: no whitespace errors.

Search validation artifacts/fixtures for raw drive paths, passwords, tokens, and server credentials; test fixtures may contain explicit fake sentinel strings only where privacy rejection is under test.

- [ ] **Step 9: Commit Task 9**

```bash
git add README.md CHANGELOG.md tests/validation/test_phase1_scale.py examples/validation
git commit -m "Complete V0.4-A validation lab"
```

- [ ] **Step 10: Final V0.4-A acceptance review before release work**

Verify all 17 acceptance items in the spec have direct passing evidence. Do not bump to `0.4.0`, tag, push, or create a GitHub Release until a separate release gate confirms implementation complete and the user authorizes release/push.

---

## Dependency Order

Execute strictly in this order:

`Task 1 contracts -> Task 2 manifest/leakage -> Task 3 consensus/metrics -> Task 4 stability/hierarchy -> Task 5 review/mining -> Task 6 runner/promotion -> Task 7 artifacts -> Task 8 CLI -> Task 9 full gate`

Each task must follow RED -> minimal GREEN -> regression tests -> commit. Do not batch unrelated task commits.

## Review Gates

After each task, prefer a fresh read-only reviewer focused only on that task's contract. Reviewer unavailability is not a PASS; record it as infrastructure unavailable and continue only with explicit test/self-audit evidence. Before claiming V0.4-A complete, use `superpowers:verification-before-completion` and run the final gate from Task 9.