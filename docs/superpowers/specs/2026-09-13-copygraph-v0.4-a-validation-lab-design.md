# CopyGraph V0.4-A Validation Lab Design

Date: 2026-09-13
Status: Approved design, implementation not started
Target release: 0.4.0

## Goal

V0.4-A adds a reproducible Validation Lab around the existing CopyGraph evidence engine so confidence thresholds can be evaluated against hybrid ground truth instead of synthetic behavior alone.

The primary objective is false-positive control on real MT5 histories while preserving enough recall to remain operationally useful. V0.4-A does not replace the raw V0.3 matching engine. It measures, calibrates, challenges, and promotes calibration artifacts around that engine.

The Validation Lab lives in the CopyGraph repository under a separate boundary such as `copygraph.validation`. The dependency direction is one-way:

`validation -> ingest/lifecycle/matching/calibration/forensics`

The raw matcher, scanner, and evidence engine must not import validation concepts.

## Success criteria

A calibration candidate may be promoted only when all mandatory gates pass on both frozen and recent holdouts:

- high-confidence pair-level FPR <= 0.1%;
- review-queue pair-level FPR <= 1%;
- high-confidence recall >= 60%;
- high-confidence plus review-queue recall >= 85%;
- leakage audit PASS;
- core holdout PASS;
- recent holdout PASS;
- subgroup-specific models may override the global model only when their stability gates PASS.

V0.4-A Phase 1 targets 300-500 reviewed pairs to validate the pipeline and policies. Production-grade claims such as FPR <= 0.1% must not be made until Phase 2 reaches at least 2,000 reviewed pairs with sufficient hard-negative coverage.

## Non-goals

V0.4-A does not:

- change raw matching weights or matching semantics;
- add cloud hosting, SaaS accounts, login, or team collaboration;
- add a new machine-learning classifier;
- add 1,000-account candidate pruning or scanner architecture changes;
- automatically claim that copying is proven;
- add a complex reviewer application beyond minimal reports/forms needed for dataset curation;
- store MT5 credentials, terminal secrets, or raw absolute local paths in exported validation artifacts.

## Ground-truth model

The dataset is hybrid by design.

### Ground-truth classes

`confirmed_copy` is eligible for calibration only when ground truth is strong enough. It has two provenance classes:

- `real_confirmed`: real master/slave linkage or equivalent internal confirmation;
- `controlled_confirmed`: a controlled replay/experiment with complete provenance.

`confirmed_copy` metrics must be reported separately for real and controlled cases as well as together.

`suspected_copy` means evidence is strong but independent confirmation is missing. It is challenge/evaluation data only and must not be used to fit calibration.

`unrelated` is a reviewed negative case.

`uncertain` is retained for audit and future adjudication but excluded from primary calibration and headline metrics.

### Label confidence

Label confidence is categorical: `high`, `medium`, or `low`.

Primary calibration training uses only policy-eligible labels, initially `confirmed_copy/high` and `unrelated/high`. Lower-confidence labels remain available for diagnostics and challenge suites.

## Core data contracts

### ValidationCase

A `ValidationCase` is the smallest reviewable unit. It identifies one account pair and one evaluation window.

Required fields include:

- stable `case_id`;
- stable `relationship_id` shared by the 7d/30d/full views of the same account relationship;
- `account_a` and `account_b` logical identifiers;
- `window_type`: `7d`, `30d`, or `full`;
- `source_kind`: `real` or `controlled`;
- `label`: `confirmed_copy`, `suspected_copy`, `unrelated`, or `uncertain`;
- `label_confidence`;
- `confirmed_kind` when label is `confirmed_copy`;
- manual `strategy_family_id` when known;
- provisional family identifier when inferred;
- broker, symbol, and session tags where available;
- `review_status`;
- provenance reference;
- evidence snapshot reference/hash;
- label revision identifier.

A case must be reproducible without depending on mutable UI state.

### Provenance

Provenance records enough information to reconstruct and audit a case without exporting secrets.

It includes:

- source content hashes;
- normalized input fingerprints;
- account snapshot fingerprints where applicable;
- engine version;
- calibration version when a calibration artifact was used for display;
- scan ID when the case came from the persistent scanner;
- controlled replay recipe/version and seed when applicable;
- reviewer IDs as opaque internal identifiers;
- review timestamps;
- evidence snapshot hash;
- label-policy version.

Exported artifacts must not contain credentials, raw absolute paths, MT5 passwords, or server login data.

### ValidationDatasetManifest

A dataset manifest is immutable once used for official evaluation.

It contains:

- schema version;
- dataset ID and revision;
- exact case revision references;
- train/core-holdout/recent-holdout/challenge assignments;
- strategy-family and leakage-group assignments;
- engine version;
- label-policy version;
- split-policy version;
- calibration-policy version;
- dataset checksum;
- creation metadata.

Corrections produce a new manifest revision. Existing manifests are never edited in place.

### ValidationRun

A validation run is fully determined by its dataset manifest, policy, raw engine version, and candidate calibration configuration.

It records:

- run ID;
- manifest hash;
- engine version;
- candidate calibration hash;
- policy version;
- leakage-audit result;
- global metrics;
- subgroup diagnostics;
- bootstrap diagnostics;
- temporal diagnostics;
- core-holdout metrics;
- recent-holdout metrics;
- multi-window consensus metrics;
- promotion decision reference.

## Label revision and immutability

A case label change does not overwrite history. Review/adjudication creates a new label revision.

A manifest pins exact label revisions. Therefore an old validation run can always be reproduced even if later adjudication changes the current label.

## Strategy-family model

Strategy-family boundaries protect evaluation from hidden leakage.

Manual family assignments take precedence when provenance is known. Unknown cases may be auto-clustered into `provisional_family` groups using behavior such as symbol mix, timing pattern, side pattern, and other non-label evidence.

Provisional families are not ground truth about trading strategy. They are conservative anti-leakage boundaries.

If two accounts appear sufficiently similar to risk family leakage, they must be grouped together for splitting even when provenance is incomplete.

## LeakageGroup and split engine

The split engine operates on groups, never on individual pair rows alone.

A `LeakageGroup` contains accounts and related controlled variants that must remain in the same split.

A split must be account-disjoint and strategy-family-disjoint.

The main partitions are:

- `train`;
- `core_holdout`;
- `recent_holdout`;
- `challenge` for cases such as `suspected_copy` and policy-ineligible labels.

`core_holdout` is frozen across releases to support version-to-version comparison.

`recent_holdout` rotates by time to detect performance drift.

## LeakageAudit

Every evaluation run begins with a fail-closed leakage audit.

The audit must fail when it detects at least one of:

- an account present in more than one split;
- one manual or provisional strategy family crossing splits;
- overlapping controlled variants from the same replay seed crossing splits;
- identical normalized lifecycle fingerprints across train and holdout;
- suspiciously overlapping source provenance across train and holdout;
- any split assignment that violates the active split policy.

A failed leakage audit blocks final evaluation and promotion.

## Multi-window evaluation

Each account pair is evaluated independently over three windows:

- `7d`: early detection;
- `30d`: medium-term confirmation;
- `full`: long-term context and stability.

Scores from different windows are not averaged into a new raw score.

A consensus layer maps window outcomes into operational tiers:

### HIGH_CONFIDENCE

Requires both 7d and 30d to meet or exceed `high_threshold`.

Full-history evidence may support the explanation but cannot independently promote a pair to high confidence.

### REVIEW_QUEUE

Used when the pair is not already `HIGH_CONFIDENCE` and at least one policy-defined review condition is true, including:

- 7d or 30d meets or exceeds `review_threshold`;
- full-history meets or exceeds `high_threshold` while recent windows are not jointly high-confidence;
- evidence is otherwise policy-eligible for analyst review without satisfying high-confidence consensus.

### NO_ALERT

Used when alert conditions are not met.

### INSUFFICIENT_EVIDENCE

Used when sample size, overlap, or other evidence coverage is below the policy minimum for a reliable operational conclusion.

## Evaluation metrics

### Pair-level metrics

Pair-level FPR is the primary false-positive metric.

For each pair during the evaluation period, the highest operational tier reached by that pair is used to determine pair-level alert outcome.

Headline gates:

- high-confidence FPR <= 0.1%;
- review-tier cumulative FPR <= 1%, where every pair reaching `REVIEW_QUEUE` or `HIGH_CONFIDENCE` counts as an alert;
- high-confidence recall >= 60%;
- high-confidence plus review-queue recall >= 85%.

The two operational thresholds are explicit policy fields: `high_threshold` and `review_threshold`, with `review_threshold <= high_threshold`. They are selected from train/cross-validation data only.

### Window-level metrics

Window-level false-alert rate is reported separately for 7d, 30d, and full-history windows to measure operational alert spam.

Pair-level and window-level metrics must never be conflated.

### Required slices

Metrics are reported separately for at least:

- `real_confirmed`;
- `controlled_confirmed`;
- hard negatives;
- broker subgroups;
- symbol subgroups;
- session subgroups;
- strategy-family/provisional-family diagnostics where policy allows.

## Calibration hierarchy

A global calibration model is the production default.

Broker, symbol, and session-specific calibration models are optional overrides, not the primary architecture.

A subgroup may receive its own model only when all stability gates pass. Otherwise it falls back to the global model.

## Subgroup stability gates

A subgroup model requires all of the following.

### Sample floor

Initial policy floor:

- at least 100 confirmed positive cases;
- at least 1,000 reviewed negative cases.

These values are policy-controlled and versioned. They are not hard-coded scientific constants.

### Bootstrap stability

Bootstrap diagnostics use deterministic seeded resampling.

At minimum the run records:

- threshold distribution and IQR;
- FPR confidence interval and upper bound;
- recall confidence interval and lower bound;
- sample counts and seed/policy version.

A subgroup fails when the configured confidence bound violates the operational FPR/recall gate or threshold instability exceeds policy limits.

### Temporal stability

Data is evaluated across chronological blocks.

A subgroup fails temporal stability when:

- a time block materially breaches the FPR ceiling;
- performance shows persistent degradation beyond policy tolerance;
- coverage is too sparse to make a stable subgroup claim.

Any failed subgroup gate forces fallback to the global model.

## Calibration promotion lifecycle

Calibration artifacts have explicit states:

- `CANDIDATE`: fitted but not accepted;
- `EVALUATED`: holdout evaluation completed;
- `PROMOTED`: active default calibration;
- `REJECTED`: failed a mandatory promotion gate.

Evaluation never automatically promotes a model.

Promotion is a separate fail-closed operation.

## Promotion policy

A candidate may be promoted only when:

- leakage audit passes;
- core holdout passes all headline gates;
- recent holdout passes all headline gates;
- global high-confidence FPR <= 0.1%;
- global review-queue FPR <= 1%;
- high-confidence recall >= 60%;
- combined high-confidence plus review-queue recall >= 85%;
- no subgroup-specific model is activated without full stability approval;
- the new model does not regress core-holdout FPR relative to the currently promoted production model.

Average metric improvement is insufficient when a mandatory gate regresses.

## PromotionDecision artifact

Every promotion attempt emits an immutable decision artifact containing:

- candidate model hash;
- dataset manifest hash;
- engine version;
- policy version;
- all mandatory gate outcomes;
- baseline production metrics where applicable;
- final state: promoted or rejected;
- rejection/promotion reasons;
- timestamp.

The artifact must answer why a calibration became production default.

## Review workflow

Review status progresses through:

`unreviewed -> single_reviewed -> dual_reviewed -> adjudicated`

A single review is sufficient only for policy-defined clear cases.

A second reviewer is mandatory for:

- every `confirmed_copy` case;
- every disagreement;
- every case within the configured near-threshold review band.

Reviewer IDs are opaque internal identifiers in exported artifacts.

## Reviewer evidence presentation

Reviewers should see evidence rather than only a final confidence number.

A review report should expose at least:

- matched lifecycle timeline;
- open-delay distribution;
- close-delay consistency;
- lot-ratio stability/drift;
- risk-evidence coverage;
- unmatched and near-window collisions;
- orientation;
- 7d/30d/full-history evidence;
- source/provenance summary.

Where practical, the reviewer should make the label decision before seeing the final calibrated recommendation to reduce anchoring bias.

## Adjudication

When reviewers disagree, an `AdjudicationRecord` preserves:

- both original review decisions;
- reviewer rationale;
- evidence snapshot hash;
- adjudicator decision;
- final label and confidence;
- new label revision.

Original reviews are never overwritten.

## Hard-negative mining

Random unrelated pairs are not sufficient to validate low FPR.

The Validation Lab actively mines negatives likely to confuse the raw engine, including pairs with:

- similar symbol mix;
- similar active trading hours;
- close entry timing;
- similar directional bias;
- stable but independent lot-sizing patterns;
- same broker/session context;
- neighboring strategy-family behavior but independent provenance;
- high or near-threshold raw confidence despite independent review as unrelated.

Hard-negative pools are versioned.

## False-positive registry

A production false alert may be registered in a `false_positive_registry` with provenance and evidence snapshot.

It becomes a priority candidate for the next dataset revision.

It must not be used to tune a model and then be reused as evidence that the same model passes the frozen holdout. Holdout independence is preserved across generations.

## Collision suite

A controlled `collision_suite` intentionally generates independent histories that resemble copying on superficial dimensions, for example:

- same symbols;
- near-identical session times;
- similar lot ratios;
- similar directional mix;
- overlapping open-time distributions;
- no master/slave dependency.

The suite stress-tests false-positive controls while retaining known provenance.

## ValidationRun pipeline

The reproducible pipeline is:

`manifest + policy + engine version`
`-> leakage audit`
`-> train/cross-validation fit`
`-> global calibration diagnostics`
`-> subgroup diagnostics`
`-> bootstrap stability`
`-> temporal stability`
`-> core holdout evaluation`
`-> recent holdout evaluation`
`-> multi-window consensus metrics`
`-> promotion decision`
`-> immutable report bundle`

Threshold selection is performed using train/cross-validation data only.

Core and recent holdouts are not used to tune thresholds within the same run.

## CLI surface

The initial CLI should remain narrow:

- `copygraph validation build-manifest ...`
- `copygraph validation audit ...`
- `copygraph validation evaluate ...`
- `copygraph validation promote ...`
- `copygraph validation report ...`

`evaluate` produces candidate results only.

`promote` is a separate explicit operation and must fail closed when required artifacts or gates are missing.

## Validation artifact bundle

Each completed run may emit:

- `validation-run.json`;
- `metrics.json`;
- `leakage-audit.json`;
- `promotion-decision.json`;
- `subgroups.json`;
- `manifest.json`;
- optional self-contained `validation-report.html`.

All artifacts include version/hash references sufficient for reproduction.

## CI strategy

### PR CI

Runs deterministic unit/integration tests using synthetic and controlled fixtures.

### Periodic validation

Runs controlled cases and sanitized real-reviewed datasets when the environment is authorized to access them.

### Promotion CI

Runs only for a new calibration candidate. It verifies every required gate before the candidate can be marked promoted.

Promotion CI must not mutate the raw evidence engine or silently change thresholds.

## Testing requirements

The implementation must include tests for at least:

- V0.3 raw benchmark values remain unchanged;
- account leakage detection;
- strategy-family leakage detection;
- replay-seed leakage detection;
- identical-lifecycle leakage detection;
- suspicious source-provenance overlap detection;
- multi-window consensus truth table;
- pair-level versus window-level metric separation;
- fixed-seed bootstrap determinism;
- temporal split correctness;
- subgroup sample-floor failure;
- subgroup fallback to global calibration;
- subgroup bootstrap gate failure;
- subgroup temporal gate failure;
- promotion boundary at exactly 0.1% FPR;
- promotion boundary at exactly 1% FPR;
- recall boundaries at exactly 60% and 85%;
- core and recent holdout both required;
- core FPR regression blocks promotion;
- manifest immutability;
- label-revision immutability;
- reproducibility for identical manifest/engine/policy inputs;
- false-positive registry does not contaminate the current frozen holdout;
- privacy: exported artifacts contain no raw absolute paths or credentials.

## Dataset growth plan

### Phase 1

Target 300-500 reviewed pairs.

Purpose:

- validate schemas and review flow;
- validate leakage controls;
- validate deterministic evaluation;
- validate multi-window consensus;
- validate promotion logic;
- validate hard-negative mining.

Phase 1 does not authorize a production-grade claim of <=0.1% FPR.

### Phase 2

Target at least 2,000 reviewed pairs with deliberate hard-negative and subgroup coverage.

Only after Phase 2 may CopyGraph consider publishing a production-grade low-FPR claim, and only if the frozen/recent holdout gates actually pass.

## Error handling and fail-closed behavior

Validation operations fail closed when:

- manifests reference missing case revisions;
- provenance required by policy is missing;
- leakage audit fails;
- holdout partitions are empty or invalid;
- a candidate calibration cannot be reproduced;
- subgroup evidence is insufficient;
- promotion inputs are incomplete;
- stored artifacts fail schema/hash validation.

A failed validation run may emit diagnostics, but it must not emit a promoted decision.

## Privacy and reproducibility

Privacy-safe identifiers and hashes are preferred over raw path disclosure.

The system retains enough local provenance to reproduce authorized runs but exported reports omit secrets and raw machine-specific filesystem paths.

Dataset and run artifacts must be deterministic for identical canonical inputs and fixed policies.

## Acceptance gate for V0.4-A

V0.4-A is implementation-complete when all of the following are true:

1. Hybrid dataset schema and provenance contracts are implemented.
2. Label revision and immutable manifest behavior are implemented.
3. Account- and strategy-family-disjoint split generation is implemented.
4. Fail-closed leakage audit is implemented.
5. 7d/30d/full multi-window evaluation and consensus are implemented.
6. Pair-level and window-level false-positive metrics are implemented separately.
7. Global calibration diagnostics and subgroup fallback are implemented.
8. Sample, bootstrap, and temporal subgroup stability gates are implemented.
9. Core frozen holdout and rolling recent holdout evaluation are implemented.
10. Promotion state machine and immutable PromotionDecision artifact are implemented.
11. Risk-based review/adjudication data contracts are implemented.
12. Hard-negative mining and collision-suite support are implemented.
13. Validation CLI and reproducible run artifact bundle are implemented.
14. Privacy checks and reproducibility tests pass.
15. Existing V0.3 raw matching benchmark remains unchanged.
16. A Phase-1 dataset of 300-500 pairs can run end-to-end through the Validation Lab.
17. Documentation explicitly states that production-grade <=0.1% FPR claims require Phase 2 with >=2,000 reviewed pairs and passing holdouts.

## Release discipline

V0.4-A must not silently alter the V0.3 raw scorer.

If implementation reveals a reason to change raw matching semantics, that becomes a separate approved design change and must first be evaluated through the Validation Lab rather than folded into V0.4-A opportunistically.

The target release remains `0.4.0`, but version bump/tag/release happens only after the implementation plan is completed and the final acceptance gate passes.