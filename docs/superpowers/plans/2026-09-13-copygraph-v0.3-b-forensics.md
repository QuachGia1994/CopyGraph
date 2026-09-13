# CopyGraph V0.3-B Forensic Investigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn calibrated pair evidence into a deterministic forensic report with traceable timelines, delay/volume/symbol diagnostics, contradictory evidence, and a self-contained investigation dashboard.

**Architecture:** Build one pure `forensics.py` analysis layer on top of Milestone A's `PairAnalysis`, lifecycles, explanation, and optional calibration model. Keep presentation separate in `forensic_dashboard.py`; JavaScript renders precomputed report fields only and never recomputes analytical metrics.

**Tech Stack:** Python 3.11+, standard library (`collections`, `datetime`, `json`, `math`, `pathlib`, `statistics`), pytest, plain self-contained HTML/JS/SVG.

**Spec:** `docs/superpowers/specs/2026-09-13-copygraph-v0.3-design.md`

## Global Constraints

- Milestone A must be complete and its interfaces frozen before this plan starts.
- Do not alter V0.2 raw matching semantics or Milestone A calibration math.
- Every forensic fact must trace to concrete lifecycle IDs/timestamps.
- Exported forensic JSON/HTML must not contain absolute source paths, MT5 credentials, terminal configuration, or unrelated account metadata.
- Keep dashboard self-contained with no CDN/network runtime dependency.
- Treat every report-derived string as untrusted HTML input.
- Keep package/module version at `0.2.0`; work under CHANGELOG `[Unreleased]`.

---

### Task 1: Traceable matched timeline and delay diagnostics

**Files:**
- Create: `src/copygraph/forensics.py`
- Create: `tests/forensic_data.py`
- Create: `tests/test_forensics_timeline.py`

**Interfaces:**

```python
def build_forensic_report(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]: ...
```

Report schema version: `1.0`.

- [ ] **Step 1: Create deterministic PositionLifecycle test fixtures and failing timeline tests**

Create `tests/forensic_data.py` with a focused constructor:

```python
from datetime import datetime, timedelta, timezone
from copygraph.models import PositionLifecycle

BASE = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


def position(account, position_id, *, symbol="EURUSD", side="BUY", open_s=0, close_s=120, volume=1.0, sl=1.09, tp=1.12):
    opened = BASE + timedelta(seconds=open_s)
    closed = None if close_s is None else BASE + timedelta(seconds=close_s)
    return PositionLifecycle(
        account_id=account,
        position_id=str(position_id),
        symbol=symbol,
        side=side,
        open_time=opened,
        close_time=closed,
        open_price=1.10,
        close_price=None if closed is None else 1.105,
        volume=volume,
        sl=sl,
        tp=tp,
        profit=10.0 if closed is not None else 0.0,
        tickets=(f"{account}-{position_id}",),
    )
```

Write:

```python
def test_forensic_timeline_is_chronological_and_traceable():
    left = [position("a", 1, open_s=0), position("a", 2, open_s=600)]
    right = [position("b", 1, open_s=20), position("b", 2, open_s=625)]
    analysis = analyze_pair(left, right)
    report = build_forensic_report(analysis, left, right)

    assert report["schema_version"] == "1.0"
    assert [row["a_position_id"] for row in report["timeline"]] == ["1", "2"]
    assert report["timeline"][0]["a_open_time"] == "2026-09-10T10:00:00Z"
    assert report["timeline"][0]["b_open_time"] == "2026-09-10T10:00:20Z"
    assert report["timeline"][0]["delay_s"] == 20.0
```

Also test that a `MatchedTrade` referring to a missing lifecycle ID raises `ValueError("matched lifecycle not found")` rather than silently dropping the row.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_forensics_timeline.py`

Expected: FAIL because `copygraph.forensics` is missing.

- [ ] **Step 3: Implement report shell, timeline, and sparse histogram**

Use position maps keyed by `position_id`. Serialize datetimes in UTC with `Z`. Each timeline row contains:

```python
{
    "a_position_id": match.a_position_id,
    "b_position_id": match.b_position_id,
    "symbol": left.symbol,
    "a_side": left.side,
    "b_side": right.side,
    "a_open_time": iso_z(left.open_time),
    "b_open_time": iso_z(right.open_time),
    "a_close_time": iso_z(left.close_time),
    "b_close_time": iso_z(right.close_time),
    "delay_s": match.delay_s,
    "close_delay_s": close_delay_s,
    "lot_ratio": right.volume / left.volume,
    "score": match.score,
    "components": {
        "time": match.time_similarity,
        "lifecycle": match.lifecycle_similarity,
        "risk": match.risk_similarity,
        "volume": match.volume_similarity,
    },
}
```

Sort timeline by `(a_open_time, b_open_time, a_position_id, b_position_id)`.

Histogram rule: 60-second sparse buckets using `lower = floor(delay_s / 60) * 60`, `upper = lower + 60`, sorted by lower bound. Report `delay_summary` includes min/max/median and buckets; empty matches yield `None` min/max/median and `[]` buckets.

For matched rows where both positions are closed, compute `close_delay_residual_s = close_delay_s - delay_s`. Let `covered_matches = len(close_residuals)` and `total_matches = len(timeline)`, then emit `close_delay_consistency = {"covered_matches": covered_matches, "coverage": covered_matches / total_matches if total_matches else 0.0, "median_abs_residual_s": statistics.median(abs(value) for value in close_residuals) if close_residuals else None, "max_abs_residual_s": max(abs(value) for value in close_residuals) if close_residuals else None}`. This measures whether close timing shifts consistently with the open-time lead/lag rather than merely repeating raw close delays.

Top-level report fields must include `accounts`, `orientation`, `raw_score`, `raw_confidence`, optional `calibrated_confidence`, `lead_account`, `median_delay_s`, `matching_window_s`, and `warnings`. Call Milestone A `explain_pair()` once, copy its warning list/calibrated confidence, and include the full payload under `explanation`.

- [ ] **Step 4: Run GREEN**

Run: `py -3 -m pytest -q tests/test_forensics_timeline.py tests/test_explain.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/copygraph/forensics.py tests/forensic_data.py tests/test_forensics_timeline.py
git commit -m "Add traceable forensic timeline"
```

---

### Task 2: Lot-ratio drift, symbol breakdown, and contradictory/unmatched evidence

**Files:**
- Modify: `src/copygraph/forensics.py`
- Create: `tests/test_forensics_evidence.py`

**Interfaces:**
- Extends `build_forensic_report()` only; no signature change.

- [ ] **Step 1: Write failing ratio/symbol/unmatched tests**

```python
def test_forensic_report_tracks_lot_ratio_drift():
    left = [
        position("a", 1, open_s=0, volume=1.0),
        position("a", 2, open_s=600, volume=1.0),
        position("a", 3, open_s=1200, volume=1.0),
    ]
    right = [
        position("b", 1, open_s=20, volume=1.0),
        position("b", 2, open_s=620, volume=1.5),
        position("b", 3, open_s=1220, volume=3.0),
    ]
    report = build_forensic_report(analyze_pair(left, right), left, right)
    assert report["lot_ratio"]["median"] == 1.5
    assert report["lot_ratio"]["drift_factor"] == 3.0
    assert [row["ratio"] for row in report["lot_ratio"]["series"]] == [1.0, 1.5, 3.0]
```

```python
def test_unmatched_near_window_is_reported_with_traceable_ids():
    left = [position("a", 1, open_s=0), position("a", 2, open_s=10)]
    right = [position("b", 1, open_s=20)]
    analysis = analyze_pair(left, right)
    report = build_forensic_report(analysis, left, right)
    assert report["unmatched_counts"] == {"a": 1, "b": 0}
    row = report["unmatched_near_window"][0]
    assert row["unmatched_account"] == "a"
    assert row["unmatched_position_id"] == "2"
    assert row["nearest_other_position_id"] == "1"
    assert row["nearest_other_was_matched"] is True
```

Add tests for per-symbol ordering, unrelated pair weak evidence, reverse orientation, and lifecycle IDs containing reversal segments such as `7#2`.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_forensics_evidence.py`

Expected: missing report sections.

- [ ] **Step 3: Implement lot-ratio and risk-evidence summaries**

For each matched timeline row with positive volumes, create series row `{a_open_time, a_position_id, b_position_id, ratio}`. Sort by `a_open_time`. `median` is `statistics.median(ratios)`. `drift_factor` is `max(ratios) / min(ratios)` when ratios exist and minimum > 0, otherwise `None`.

Using the lifecycle maps, let `covered_matches` be the number of matched pairs where both sides have non-null SL and `total_matches = len(analysis.matches)`. Emit `risk_evidence = {"covered_matches": covered_matches, "total_matches": total_matches, "coverage": covered_matches / total_matches if total_matches else 0.0}`. This is evidence coverage only; do not infer risk intent from absent stops.

- [ ] **Step 4: Implement symbol breakdown**

For every symbol present in either account, emit:

```python
{
    "symbol": symbol,
    "matched_count": matched_count,
    "unmatched_a": unmatched_a,
    "unmatched_b": unmatched_b,
    "mean_match_score": mean_score_or_none,
    "median_delay_s": median_delay_or_none,
}
```

Sort by `(-matched_count, symbol)`.

- [ ] **Step 5: Implement unmatched-near-window evidence**

Build matched ID sets from `analysis.matches`. Evaluate unmatched positions symmetrically. For each unmatched A position, search all B positions; for each unmatched B position, search all A positions. Candidate must have the same symbol, satisfy the analysis orientation (`same side` for normal, `opposite side` for reverse), and fall within `analysis.matching_window_s`. Already-matched candidates stay eligible because they expose one-to-one collisions. Emit rows with `unmatched_account` (`"a"` or `"b"`), `unmatched_position_id`, `nearest_other_position_id`, signed `delay_s` always defined as `b.open_time - a.open_time`, and `nearest_other_was_matched`. Pick one nearest candidate by `(abs(delay), other.open_time, other.position_id)` and sort all rows by `(abs(delay_s), unmatched_account, unmatched_position_id, nearest_other_position_id)`.

The report's `supporting_matches` is top 5 timeline rows by `(-score, a_position_id, b_position_id)`. `contradictory_matches` is bottom 5 by `(score, a_position_id, b_position_id)`. Add `contradictory_evidence` summary rows: emit `{"kind": "no_matched_trades", "count": 1}` when no matches exist; emit `{"kind": "unmatched_positions", "a": unmatched_a_count, "b": unmatched_b_count}` when either unmatched count is non-zero; and for each near-window row emit `{"kind": "near_window_collision", "unmatched_account": row["unmatched_account"], "unmatched_position_id": row["unmatched_position_id"], "nearest_other_position_id": row["nearest_other_position_id"], "delay_s": row["delay_s"], "nearest_other_was_matched": row["nearest_other_was_matched"]}`. This makes unrelated cases visibly contradictory without inventing matched evidence.

- [ ] **Step 6: Run GREEN**

Run: `py -3 -m pytest -q tests/test_forensics_evidence.py tests/test_forensics_timeline.py tests/test_reversal.py`

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/copygraph/forensics.py tests/test_forensics_evidence.py
git commit -m "Add forensic evidence diagnostics"
```

---

### Task 3: Shared safe HTML JSON boundary and forensic dashboard

**Files:**
- Create: `src/copygraph/htmlutil.py`
- Modify: `src/copygraph/dashboard.py`
- Create: `src/copygraph/forensic_dashboard.py`
- Create: `tests/test_forensic_dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**

```python
# htmlutil.py
def safe_json_for_html(report: Mapping[str, object]) -> str: ...

# forensic_dashboard.py
def render_forensic_dashboard(report: Mapping[str, object]) -> str: ...
def write_forensic_dashboard(report: Mapping[str, object], output: str | Path) -> Path: ...
```

- [ ] **Step 1: Write failing safe-render tests**

```python
def test_forensic_dashboard_is_self_contained_and_escapes_script_close():
    report = {
        "schema_version": "1.0",
        "accounts": ["</script><img src=x onerror=alert(1)>", "b"],
        "raw_confidence": 0.8,
        "calibrated_confidence": None,
        "warnings": [],
        "timeline": [],
        "delay_summary": {"buckets": []},
        "lot_ratio": {"series": []},
        "symbol_breakdown": [],
        "supporting_matches": [],
        "contradictory_matches": [],
        "contradictory_evidence": [],
    }
    html = render_forensic_dashboard(report)
    assert "https://" not in html
    assert "http://" not in html
    assert "</script><img" not in html
    assert "\\u003c/script>" in html
```

```python
def test_existing_batch_dashboard_keeps_safe_embedding():
    html = render_dashboard({"accounts": [{"account_id": "</script>"}], "pairs": [], "graph": {"nodes": [], "edges": []}, "clusters": []})
    assert "\\u003c/script>" in html
```

Add deterministic output and UTF-8 file-write tests.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_forensic_dashboard.py tests/test_dashboard.py`

Expected: import failure for new modules/functions.

- [ ] **Step 3: Extract safe JSON helper**

Move the existing `json.dumps(... sort_keys=True)` plus `<`/`&` escaping into `htmlutil.safe_json_for_html`. Change V0.2 `dashboard.render_dashboard` to call it; do not alter V0.2 visible sections or JS behavior.

- [ ] **Step 4: Implement forensic renderer using report fields only**

HTML sections must include IDs:
- `forensic-summary`
- `forensic-warnings`
- `forensic-timeline`
- `delay-histogram`
- `lot-ratio-drift`
- `symbol-breakdown`
- `supporting-evidence`
- `contradictory-evidence`
- `forensic-network`

Embed one `<script type="application/json" id="copygraph-forensic-data">` payload. Every report-derived textual value must be assigned through `textContent`; SVG coordinates are computed only from numeric report values and set with `setAttribute`. Do not use `innerHTML` for report-derived content. `forensic-network` reuses the V0.2 visual language but renders only the investigated pair: two account nodes and one edge labeled with raw/calibrated confidence. Multi-account cluster context remains the responsibility of the existing batch dashboard, so no cluster membership is invented in a pair-only report.

- [ ] **Step 5: Run GREEN**

Run: `py -3 -m pytest -q tests/test_forensic_dashboard.py tests/test_dashboard.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add src/copygraph/htmlutil.py src/copygraph/dashboard.py src/copygraph/forensic_dashboard.py tests/test_forensic_dashboard.py tests/test_dashboard.py
git commit -m "Render forensic investigation dashboard"
```

---

### Task 4: Stateless `inspect` CLI

**Files:**
- Modify: `src/copygraph/cli.py`
- Create: `tests/test_cli_v03_forensics.py`

**Interfaces:**
- Command: `copygraph inspect <history-a> <history-b> [--calibration calibration.json] --output forensic.json [--dashboard forensic.html]`
- Persistent `--db` mode is *not* added in this milestone; Plan C adds it without changing stateless behavior.

- [ ] **Step 1: Write failing dispatch test**

```python
def test_cli_inspect_writes_forensic_json_and_dashboard(tmp_path, monkeypatch):
    analysis = object()
    left = [object()]
    right = [object()]
    report = {"schema_version": "1.0", "accounts": ["a", "b"]}
    captured = {}

    monkeypatch.setattr(cli, "analyze_pair_paths", lambda a, b: (analysis, left, right))
    monkeypatch.setattr(cli, "build_forensic_report", lambda x, y, z, calibration=None: report)
    monkeypatch.setattr(cli, "write_forensic_dashboard", lambda payload, output: captured.setdefault("dashboard", payload))

    output = tmp_path / "forensic.json"
    dashboard = tmp_path / "forensic.html"
    assert cli.main(["inspect", "a.json", "b.json", "--output", str(output), "--dashboard", str(dashboard)]) == 0
    assert json.loads(output.read_text()) == report
    assert captured["dashboard"] == report
```

Add one test that `--calibration` loads a model and passes it to `build_forensic_report`.

- [ ] **Step 2: Run RED verification**

Run: `py -3 -m pytest -q tests/test_cli_v03_forensics.py`

Expected: argparse rejects `inspect`.

- [ ] **Step 3: Wire parser and dispatch**

Parser:

```python
inspect = subparsers.add_parser("inspect", help="Build a forensic report for two histories")
inspect.add_argument("account_a")
inspect.add_argument("account_b")
inspect.add_argument("--calibration", type=Path)
inspect.add_argument("--output", type=Path, required=True)
inspect.add_argument("--dashboard", type=Path)
```

Dispatch: analyze pair paths, load optional calibration model, build forensic report, optionally write forensic dashboard, then use the common JSON output path.

- [ ] **Step 4: Run GREEN + all CLI regressions**

Run: `py -3 -m pytest -q tests/test_cli_v03_forensics.py tests/test_cli_v03_calibration.py tests/test_cli_v02.py tests/test_cli_benchmark.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/copygraph/cli.py tests/test_cli_v03_forensics.py
git commit -m "Add stateless forensic inspection CLI"
```

---

### Task 5: Milestone B docs, full verification, and reviewer gate

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document forensic workflow**

README must show `copygraph inspect master.json slave.json --output forensic.json --dashboard forensic.html`, explain each forensic section, and state that evidence traces to lifecycle IDs/timestamps without proving causation.

- [ ] **Step 2: Update CHANGELOG `[Unreleased]`**

Add concise `Added` bullets for forensic JSON, timeline/delay/ratio/symbol diagnostics, contradictory evidence, and forensic dashboard/inspect CLI. Do not bump version.

- [ ] **Step 3: Run complete Milestone B verification**

Run:

```text
py -3 -m pytest
py -3 -m compileall -q src tests
py -3 -m copygraph benchmark
git diff --check
```

Expected: all tests PASS; compileall no output; V0.1 benchmark unchanged.

- [ ] **Step 4: Request read-only reviewer**

Reviewer focus: lifecycle traceability, reverse orientation, partial-close/reversal IDs, unmatched-near-window correctness, deterministic bucket/ratio ordering, path/privacy leakage, dashboard XSS, and no analytical recomputation in JavaScript.

- [ ] **Step 5: Fix accepted Critical/Important findings with regression tests**

Each fix must first reproduce the finding in `tests/test_forensics_*.py` or `tests/test_forensic_dashboard.py`, run RED, then implement and run GREEN plus full suite.

- [ ] **Step 6: Commit Milestone B completion**

```bash
git add README.md CHANGELOG.md src tests
git diff --cached --check
git commit -m "Complete forensic investigation milestone"
```

Do not push or mint `0.3.0` unless separately authorized in the execution session.
