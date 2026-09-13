# CopyGraph V0.3-A Calibration and Explainability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic labeled calibration, cross-validated threshold metrics, and evidence-first explanations while preserving V0.2 raw matching semantics.

**Architecture:** Extract one reusable pair-loading boundary, expose the confidence factors already computed by V0.2, then build a standard-library monotonic calibrator using pool-adjacent-violators (PAVA). Calibration remains a layer on top of raw `PairAnalysis`; explanations summarize existing matched-trade facts and never replace or reinterpret the raw score.

**Tech Stack:** Python 3.11+, standard library (`dataclasses`, `json`, `bisect`, `hashlib`, `pathlib`, `statistics`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-copygraph-v0.3-design.md`

## Global Constraints

- Preserve V0.2 scoring weights and matching behavior exactly.
- Keep `analyze`, `batch`, `benchmark`, and `mt5-export` compatible.
- No pandas/numpy/sklearn dependency.
- Keep package/module version at `0.2.0`; append implementation notes under CHANGELOG `[Unreleased]` only.
- Calibration outputs never copy absolute source paths.
- `raw_confidence` remains the V0.2 value; `calibrated_confidence` is additive.
- Calibration must be monotonic and deterministic.
- Default evaluation must never score a case with a model fitted on that same case.

---

### Task 1: Reusable pair-loading boundary and explicit confidence factors

**Files:**
- Create: `src/copygraph/analysis.py`
- Modify: `src/copygraph/matching.py`
- Modify: `src/copygraph/cli.py`
- Modify: `src/copygraph/evidence.py`
- Create: `tests/test_analysis.py`
- Modify: `tests/test_similarity.py`
- Modify: `tests/test_graph_evidence.py`

**Interfaces:**
- Produces: `load_positions(path: str | Path) -> list[PositionLifecycle]`
- Produces: `analyze_pair_paths(path_a: str | Path, path_b: str | Path, config: MatchingConfig | None = None) -> tuple[PairAnalysis, list[PositionLifecycle], list[PositionLifecycle]]`
- Extends `PairAnalysis` additively with `overlap_factor: float = 0.0`, `sample_factor: float = 0.0`, and `matching_window_s: float = 0.0`.
- Existing `cli.analyze_paths()` keeps returning evidence JSON and delegates to `analysis.analyze_pair_paths()`.

- [ ] **Step 1: Write failing pair-boundary tests**

```python
from copygraph.analysis import analyze_pair_paths, load_positions


def test_analyze_pair_paths_returns_analysis_and_lifecycles(tmp_path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    put(left, rows("left"))
    put(right, rows("right", delay=20))

    analysis, left_positions, right_positions = analyze_pair_paths(left, right)

    assert analysis.account_a == "left"
    assert analysis.account_b == "right"
    assert len(left_positions) == 4
    assert len(right_positions) == 4
```

Add a matching assertion to `tests/test_similarity.py`:

```python
def test_pair_analysis_exposes_confidence_factors():
    master, slave = copied_pair()
    analysis = analyze_pair(master, slave)
    assert analysis.overlap_factor == pytest.approx(len(analysis.matches) / max(len(master), len(slave)))
    assert analysis.sample_factor == 1.0
    assert analysis.matching_window_s == pytest.approx(MatchingConfig().time_tolerance_s * MatchingConfig().hard_time_factor)
    assert analysis.confidence == pytest.approx(analysis.score * analysis.overlap_factor * analysis.sample_factor)
```

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_analysis.py tests/test_similarity.py::test_pair_analysis_exposes_confidence_factors`

Expected: import/attribute failures because `analysis.py`, `overlap_factor`, and `sample_factor` do not exist.

- [ ] **Step 3: Implement the minimal shared boundary**

Create `src/copygraph/analysis.py`:

```python
from pathlib import Path

from .ingest import load_events
from .lifecycle import reconstruct_positions
from .matching import MatchingConfig, PairAnalysis, analyze_pair


def load_positions(path: str | Path):
    return reconstruct_positions(load_events(path))


def analyze_pair_paths(path_a: str | Path, path_b: str | Path, config: MatchingConfig | None = None):
    left = load_positions(path_a)
    right = load_positions(path_b)
    return analyze_pair(left, right, config), left, right
```

In `matching.PairAnalysis`, add:

```python
overlap_factor: float = 0.0
sample_factor: float = 0.0
matching_window_s: float = 0.0
```

Set `overlap_factor` and `sample_factor` from the already-existing local variables in `_analyze_orientation`; when there are no matches set both to `0.0`. Set `matching_window_s` to the already-computed `hard_window` in both matched and unmatched results. Do not alter any weighting formula.

In `evidence.analysis_to_evidence`, add without removing existing fields:

```python
"confidence_factors": {
    "overlap": analysis.overlap_factor,
    "sample": analysis.sample_factor,
},
"matching_window_s": analysis.matching_window_s,
```

Keep `cli.analyze_paths()` public and compatible:

```python
def analyze_paths(path_a: str | Path, path_b: str | Path) -> dict[str, object]:
    analysis, _, _ = analyze_pair_paths(path_a, path_b)
    return analysis_to_evidence(analysis)
```

- [ ] **Step 4: Run GREEN + V0.2 evidence regression**

Run: `py -3 -m pytest -q tests/test_analysis.py tests/test_similarity.py tests/test_graph_evidence.py tests/test_cli_benchmark.py`

Expected: PASS; existing evidence keys still present and raw benchmark behavior unchanged.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/copygraph/analysis.py src/copygraph/matching.py src/copygraph/cli.py src/copygraph/evidence.py tests/test_analysis.py tests/test_similarity.py tests/test_graph_evidence.py
git commit -m "Expose pair confidence factors"
```

---

### Task 2: Labeled calibration dataset parsing and case scoring

**Files:**
- Create: `src/copygraph/calibration.py`
- Create: `tests/test_calibration_dataset.py`
- Create: `tests/fixtures/calibration/left.json`
- Create: `tests/fixtures/calibration/right.json`

**Interfaces:**

```python
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


def load_calibration_dataset(path: str | Path) -> CalibrationDataset: ...
```

Dataset schema is exactly:

```json
{
  "schema_version": "1.0",
  "name": "optional display name",
  "cases": [
    {
      "case_id": "copy-1",
      "label": "copy",
      "orientation": "normal",
      "history_a": "left.json",
      "history_b": "right.json"
    },
    {
      "case_id": "unrelated-1",
      "label": "unrelated",
      "analysis": {
        "schema_version": "1.0",
        "orientation": "normal",
        "confidence": 0.04
      }
    }
  ]
}
```

Rules: `schema_version` must equal `1.0`; `case_id` unique/non-empty; label only `copy|unrelated`; orientation optional but only `normal|reverse`; each case supplies either both history paths or `analysis`, never both; relative paths resolve against dataset parent; outputs contain no input paths.

- [ ] **Step 1: Write failing parser tests**

```python
def test_load_calibration_dataset_scores_relative_histories(tmp_path):
    dataset = tmp_path / "dataset.json"
    put(tmp_path / "left.json", rows("left"))
    put(tmp_path / "right.json", rows("right", delay=20))
    dataset.write_text(json.dumps({
        "schema_version": "1.0",
        "cases": [{
            "case_id": "copy-1",
            "label": "copy",
            "orientation": "normal",
            "history_a": "left.json",
            "history_b": "right.json",
        }],
    }), encoding="utf-8")

    loaded = load_calibration_dataset(dataset)
    assert loaded.schema_version == "1.0"
    assert loaded.cases[0].case_id == "copy-1"
    assert loaded.cases[0].raw_confidence > 0.7
    assert loaded.cases[0].observed_orientation == "normal"
```

Also add tests rejecting duplicate IDs, invalid label/orientation, mixed history+analysis, missing pair path, and wrong schema version.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_calibration_dataset.py`

Expected: FAIL because `copygraph.calibration` is missing.

- [ ] **Step 3: Implement dataset parsing**

In `calibration.py`, define `ScoredCase` and helpers. For history cases call `analyze_pair_paths()`. For embedded analysis, require numeric `confidence` in `[0,1]` and orientation `normal|reverse`.

Use this validation shape:

```python
def _validate_case_id(value: object, seen: set[str]) -> str:
    case_id = str(value or "").strip()
    if not case_id:
        raise ValueError("case_id is required")
    if case_id in seen:
        raise ValueError(f"duplicate case_id: {case_id}")
    seen.add(case_id)
    return case_id
```

Return `CalibrationDataset(schema_version="1.0", name=str(data["name"]) if data.get("name") not in (None, "") else None, cases=tuple(scored_cases))`; never include resolved paths in the dataset object or its cases.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_calibration_dataset.py tests/test_analysis.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/copygraph/calibration.py tests/test_calibration_dataset.py tests/fixtures/calibration
git commit -m "Parse labeled calibration datasets"
```

---

### Task 3: Monotonic PAVA calibrator and serialization

**Files:**
- Modify: `src/copygraph/calibration.py`
- Create: `tests/test_calibration_model.py`

**Interfaces:**

```python
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


def fit_monotonic_calibrator(cases: Sequence[ScoredCase]) -> CalibrationModel: ...
def apply_calibration(raw_confidence: float, model: CalibrationModel) -> float: ...
def calibration_model_to_dict(model: CalibrationModel) -> dict[str, object]: ...
def calibration_model_from_dict(payload: Mapping[str, object]) -> CalibrationModel: ...
def load_calibration_model(path: str | Path) -> CalibrationModel: ...
```

- [ ] **Step 1: Write failing monotonicity/round-trip tests**

```python
def test_pava_calibration_is_monotonic():
    cases = [
        ScoredCase("a", "unrelated", None, 0.1, "normal"),
        ScoredCase("b", "copy", "normal", 0.2, "normal"),
        ScoredCase("c", "unrelated", None, 0.3, "normal"),
        ScoredCase("d", "copy", "normal", 0.9, "normal"),
    ]
    model = fit_monotonic_calibrator(cases)
    values = [apply_calibration(x / 20, model) for x in range(21)]
    assert values == sorted(values)


def test_calibration_model_round_trip():
    model = fit_monotonic_calibrator(sample_cases())
    restored = calibration_model_from_dict(calibration_model_to_dict(model))
    assert restored == model
```

Add tests that empty data and one-class data raise `ValueError`, and input confidence outside `[0,1]` is rejected.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_calibration_model.py`

Expected: FAIL for missing model APIs.

- [ ] **Step 3: Implement deterministic PAVA**

Use binary targets `copy=1.0`, `unrelated=0.0`. Sort cases by `(raw_confidence, case_id)`, first combine every identical `raw_confidence` value into one weighted block so equal raw scores cannot receive different calibrated probabilities, then merge adjacent blocks while previous mean > next mean. Each final `CalibrationBlock.max_raw` is the maximum raw confidence in that merged block; `probability` is positives/count; `count` is member count.

Application rule:

```python
def apply_calibration(raw_confidence: float, model: CalibrationModel) -> float:
    if not 0.0 <= raw_confidence <= 1.0:
        raise ValueError("raw_confidence must be between 0 and 1")
    for block in model.blocks:
        if raw_confidence <= block.max_raw:
            return block.probability
    return model.blocks[-1].probability
```

Serialization must sort/emit `fitted_case_ids` exactly as stored and use schema `1.0`. `load_calibration_model(path)` accepts either a bare model payload or a full `build_calibration_report()` payload; for a report it reads the nested `model` key and raises `ValueError("calibration model unavailable")` when that key is null/missing.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_calibration_model.py tests/test_calibration_dataset.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/copygraph/calibration.py tests/test_calibration_model.py
git commit -m "Add monotonic confidence calibration"
```

---

### Task 4: Leave-one-out diagnostics, threshold sweep, and deterministic threshold selection

**Files:**
- Modify: `src/copygraph/calibration.py`
- Create: `tests/test_calibration_metrics.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ThresholdMetrics:
    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    false_positive_rate: float
    f1: float


def evaluate_calibrator(
    model: CalibrationModel,
    cases: Sequence[ScoredCase],
    *,
    allow_in_sample: bool = False,
) -> list[dict[str, object]]: ...
def cross_validated_predictions(cases: Sequence[ScoredCase]) -> list[dict[str, object]]: ...
def threshold_sweep(predictions: Sequence[Mapping[str, object]]) -> list[ThresholdMetrics]: ...
def choose_threshold(metrics: Sequence[ThresholdMetrics]) -> ThresholdMetrics: ...
def build_calibration_report(dataset: CalibrationDataset) -> dict[str, object]: ...
```

- [ ] **Step 1: Write failing separation/metrics tests**

```python
def test_cross_validated_predictions_exclude_current_case_from_fit(monkeypatch):
    seen = []
    real_fit = calibration.fit_monotonic_calibrator

    def recording_fit(cases):
        seen.append(tuple(case.case_id for case in cases))
        return real_fit(cases)

    monkeypatch.setattr(calibration, "fit_monotonic_calibrator", recording_fit)
    predictions = calibration.cross_validated_predictions(sample_cases())
    for prediction, fitted_ids in zip(predictions, seen):
        assert prediction["case_id"] not in fitted_ids
```

```python
def test_choose_threshold_is_deterministic_on_ties():
    metrics = [
        ThresholdMetrics(0.5, 4, 1, 5, 0, 0.8, 1.0, 1/6, 8/9),
        ThresholdMetrics(0.7, 4, 1, 5, 0, 0.8, 1.0, 1/6, 8/9),
    ]
    assert choose_threshold(metrics).threshold == 0.7
```

Add exact confusion-matrix tests and zero-denominator tests. Add an orientation diagnostic test: among `copy` cases with non-null `expected_orientation`, `build_calibration_report()` must report `orientation_evaluated` as that case count, `orientation_correct` as the count where observed equals expected, and `orientation_accuracy = correct/evaluated` (or `None` when no case declares an expected orientation). The report `dataset_summary` must preserve `dataset.name`, total case count, sorted case IDs, and label counts. Add:

```python
def test_evaluate_calibrator_rejects_in_sample_cases_by_default():
    cases = sample_cases()
    model = fit_monotonic_calibrator(cases)
    with pytest.raises(ValueError, match="in-sample"):
        evaluate_calibrator(model, [cases[0]])
    result = evaluate_calibrator(model, [cases[0]], allow_in_sample=True)
    assert result[0]["case_id"] == cases[0].case_id
```

This is the public evaluation guard; `apply_calibration(raw_confidence, model)` remains a low-level scalar mapping primitive and is not described as an evaluation API.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_calibration_metrics.py`

Expected: FAIL for missing APIs.

- [ ] **Step 3: Implement diagnostics**

`evaluate_calibrator()` compares each requested case ID against `model.fitted_case_ids`; any overlap raises `ValueError("in-sample evaluation requires allow_in_sample=True")` unless the explicit flag is true. For cross-validation, each case is held out, the model is fit on all *other* cases, and the held-out case is passed through `evaluate_calibrator()` so the guard is exercised. If that fold lacks both classes, emit `calibrated_confidence: None` and `status: "insufficient_training_classes"`; never fit on the held-out case. `threshold_sweep` ignores unavailable predictions and evaluates deterministic candidate thresholds `{0.0, 1.0} U all available calibrated confidences` sorted ascending.

Metric rules:

```python
precision = tp / (tp + fp) if tp + fp else 0.0
recall = tp / (tp + fn) if tp + fn else 0.0
fpr = fp / (fp + tn) if fp + tn else 0.0
f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
```

Threshold selection maximizes this tuple exactly:

```python
(metric.f1, -metric.false_positive_rate, metric.precision, metric.threshold)
```

`build_calibration_report(dataset)` uses `dataset.cases` and fits the final deployment model on all cases only after cross-validated diagnostics are built. Output schema `1.0` contains `status`, class counts, `orientation_evaluated`, `orientation_correct`, `orientation_accuracy`, cross-validated predictions, threshold sweep, `selected_threshold`, `threshold_space: "calibrated_confidence"`, and serialized final model. If no fold can be evaluated, status is `calibration_unavailable` and selected threshold/model are `None` rather than invented.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_calibration_metrics.py tests/test_calibration_model.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/copygraph/calibration.py tests/test_calibration_metrics.py
git commit -m "Add calibration threshold diagnostics"
```

---

### Task 5: Evidence-first explanation schema

**Files:**
- Create: `src/copygraph/explain.py`
- Create: `tests/test_explain.py`

**Interfaces:**

```python
def explain_pair(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]: ...
```

Explanation schema version: `1.0`.

- [ ] **Step 1: Write failing contribution/warning tests**

```python
def test_explanation_components_reconstruct_raw_score():
    left, right = copied_pair()
    analysis = analyze_pair(left, right)
    explanation = explain_pair(analysis, left, right)
    components = explanation["components"]
    assert sum(item["weighted_contribution"] for item in components.values()) == pytest.approx(analysis.score)
    assert explanation["raw_confidence"] == pytest.approx(analysis.confidence)
    assert explanation["confidence_factors"] == {
        "overlap": analysis.overlap_factor,
        "sample": analysis.sample_factor,
    }
```

```python
def test_explanation_warns_for_sparse_missing_risk():
    left, right = copied_pair(count=1, with_stops=False)
    explanation = explain_pair(analyze_pair(left, right), left, right)
    assert "sparse_sample" in explanation["warnings"]
    assert "missing_stop_evidence" in explanation["warnings"]
```

Add tests for calibrated confidence application, strongest/weakest ordering, unmatched counts, and stable JSON serialization.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_explain.py`

Expected: FAIL because `copygraph.explain` is missing.

- [ ] **Step 3: Implement explanation math without changing matching**

For each component, compute the rarity-weighted mean across selected matches, then multiply by the existing V0.2 coefficient:

```python
weights = {
    "time": 0.40,
    "lifecycle": 0.25,
    "risk": 0.20,
    "volume": 0.15,
}
```

The four weighted contributions must sum to `analysis.score` within floating tolerance. Include `raw_confidence`, optional `calibrated_confidence`, factors, orientation, lead/lag, top 5 matches sorted by `(-score, a_position_id, b_position_id)`, weakest 5 sorted `(score, a_position_id, b_position_id)`, and unmatched counts.

Warnings are deterministic strings:
- `sparse_sample` when `sample_factor < 1.0`;
- `low_overlap` when `overlap_factor < 0.5`;
- `missing_stop_evidence` when fewer than half of matched pairs have SL on both sides;
- `unstable_volume_ratio` when at least 3 matches exist and max lot ratio / min lot ratio > 2.0.

Never emit source paths or prose asserting definite copying.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_explain.py tests/test_similarity.py`

Expected: PASS and V0.2 score tests unchanged.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/copygraph/explain.py tests/test_explain.py
git commit -m "Explain pair confidence evidence"
```

---

### Task 6: `calibrate` and `explain` CLI wiring

**Files:**
- Modify: `src/copygraph/cli.py`
- Create: `tests/test_cli_v03_calibration.py`

**Interfaces:**
- Command: `copygraph calibrate <dataset.json> --output calibration.json`
- Command: `copygraph explain <history-a> <history-b> [--calibration calibration.json] --output explanation.json`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_calibrate_writes_report(tmp_path, monkeypatch):
    report = {"schema_version": "1.0", "status": "ok", "selected_threshold": 0.7}
    dataset = object()
    monkeypatch.setattr(cli, "load_calibration_dataset", lambda path: dataset)
    monkeypatch.setattr(cli, "build_calibration_report", lambda value: report)
    output = tmp_path / "calibration.json"
    assert cli.main(["calibrate", "dataset.json", "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == report
```

```python
def test_cli_explain_uses_optional_calibration(tmp_path, monkeypatch):
    analysis = object()
    left = [object()]
    right = [object()]
    model = object()
    explanation = {"schema_version": "1.0", "raw_confidence": 0.8, "calibrated_confidence": 0.9}
    captured = {}

    monkeypatch.setattr(cli, "analyze_pair_paths", lambda a, b: (analysis, left, right))
    monkeypatch.setattr(cli, "load_calibration_model", lambda path: model)

    def fake_explain(value, account_a, account_b, calibration=None):
        captured["args"] = (value, account_a, account_b, calibration)
        return explanation

    monkeypatch.setattr(cli, "explain_pair", fake_explain)
    output = tmp_path / "explanation.json"
    assert cli.main(["explain", "a.json", "b.json", "--calibration", "calibration.json", "--output", str(output)]) == 0
    assert captured["args"] == (analysis, left, right, model)
    assert json.loads(output.read_text()) == explanation
```

This dispatch test must not call real MT5/filesystem history.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_cli_v03_calibration.py`

Expected: argparse rejects unknown commands.

- [ ] **Step 3: Add argparse/dispatch**

Add imports from `.analysis`, `.calibration`, `.explain`. Parser contracts:

```python
calibrate = subparsers.add_parser("calibrate")
calibrate.add_argument("dataset")
calibrate.add_argument("--output", type=Path, required=True)

explain = subparsers.add_parser("explain")
explain.add_argument("account_a")
explain.add_argument("account_b")
explain.add_argument("--calibration", type=Path)
explain.add_argument("--output", type=Path, required=True)
```

Dispatch `calibrate` to dataset loader + report builder. Dispatch `explain` to `analyze_pair_paths`, optional `load_calibration_model`, and `explain_pair`. Reuse the existing common JSON write/print path.

- [ ] **Step 4: Run GREEN + old CLI regression**

Run: `py -3 -m pytest -q tests/test_cli_v03_calibration.py tests/test_cli_v02.py tests/test_cli_benchmark.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add src/copygraph/cli.py tests/test_cli_v03_calibration.py
git commit -m "Add calibration and explanation CLI"
```

---

### Task 7: Milestone A docs, full verification, and reviewer gate

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update README with concrete V0.3-A examples**

Document the dataset schema, `calibrate`, `explain`, the difference between raw and calibrated confidence, and the rule that cross-validated diagnostics exclude the held-out case.

- [ ] **Step 2: Add truthful `[Unreleased]` entries**

Under `### Added`, add concise bullets for labeled monotonic calibration, threshold diagnostics, explainable confidence components, and new CLI commands. Do not rename `[Unreleased]` or bump version.

- [ ] **Step 3: Run complete Milestone A verification**

Run in order:

```text
py -3 -m pytest
py -3 -m compileall -q src tests
py -3 -m copygraph benchmark
git diff --check
```

Expected: all tests PASS; compileall no output; benchmark retains V0.1 normal/reverse confidence `0.9681481481481482` and unrelated `0.0`; diff check no errors.

- [ ] **Step 4: Request read-only reviewer**

Reviewer focus: no in-sample leakage in default diagnostics, PAVA monotonicity, threshold metric correctness, raw-confidence preservation, explanation component reconstruction, path/privacy leakage, CLI backward compatibility.

- [ ] **Step 5: Fix each accepted Critical/Important finding via RED/GREEN**

For every accepted finding, add one named regression test in the narrowest relevant test file, run it RED, implement the minimal fix, then rerun targeted tests plus full suite.

- [ ] **Step 6: Commit Milestone A docs/reviewer fixes**

```bash
git add README.md CHANGELOG.md src tests
git diff --cached --check
git commit -m "Complete calibrated confidence milestone"
```

Do not push or bump the package version unless separately authorized in the execution session.
