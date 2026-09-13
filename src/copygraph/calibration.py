from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .analysis import analyze_pair_paths


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


def _score_history_case(base: Path, item: dict[str, object]) -> ScoredCase:
    if "analysis" in item:
        return _score_embedded_case(item)
    pair, _, _ = analyze_pair_paths(base / str(item["history_a"]), base / str(item["history_b"]))
    return ScoredCase(
        case_id=str(item["case_id"]),
        label=str(item["label"]),
        expected_orientation=item.get("orientation") if isinstance(item.get("orientation"), str) else None,
        raw_confidence=pair.confidence,
        observed_orientation=pair.orientation,
    )


def _score_embedded_case(item: dict[str, object]) -> ScoredCase:
    embedded = item["analysis"]
    if not isinstance(embedded, dict):
        raise ValueError("analysis must be an object")
    if embedded.get("schema_version") != "1.0":
        raise ValueError("embedded schema version must be 1.0")
    observed_orientation = embedded.get("orientation")
    if observed_orientation not in {"normal", "reverse"}:
        raise ValueError("embedded analysis orientation must be normal or reverse")
    confidence = float(embedded["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("embedded analysis confidence must be between 0 and 1")
    return ScoredCase(
        case_id=str(item["case_id"]),
        label=str(item["label"]),
        expected_orientation=item.get("orientation") if isinstance(item.get("orientation"), str) else None,
        raw_confidence=confidence,
        observed_orientation=str(observed_orientation),
    )


def _validate_case(item: dict[str, object], seen: set[str]) -> str:
    case_id = str(item.get("case_id", "")).strip()
    if not case_id:
        raise ValueError("case_id must be non-empty")
    if case_id in seen:
        raise ValueError(f"duplicate case_id: {case_id}")
    label = item.get("label")
    if label not in {"copy", "unrelated"}:
        raise ValueError("label must be copy or unrelated")
    orientation = item.get("orientation")
    if orientation is not None and orientation not in {"normal", "reverse"}:
        raise ValueError("orientation must be normal or reverse")
    has_a = "history_a" in item
    has_b = "history_b" in item
    has_analysis = "analysis" in item
    if has_analysis and (has_a or has_b):
        raise ValueError("case must provide either histories or analysis")
    if has_a != has_b:
        raise ValueError("history_a and history_b must be provided together")
    if not has_analysis and not (has_a and has_b):
        raise ValueError("case must provide either histories or analysis")
    seen.add(case_id)
    return case_id


def load_calibration_dataset(path: str | Path) -> CalibrationDataset:
    resolved = Path(path)
    if not resolved.is_file():
        raise ValueError(f"calibration dataset not found: {resolved}")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("calibration schema_version must be 1.0")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("cases must be a list")
    seen: set[str] = set()
    scored_cases: list[ScoredCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("each calibration case must be an object")
        _validate_case(item, seen)
        scored_cases.append(_score_history_case(resolved.parent, item))
    name = str(data["name"]) if data.get("name") not in (None, "") else None
    return CalibrationDataset(schema_version="1.0", name=name, cases=tuple(scored_cases))


def _label_value(case: ScoredCase) -> float:
    if case.label == "copy":
        return 1.0
    if case.label == "unrelated":
        return 0.0
    raise ValueError(f"unsupported calibration label: {case.label}")


def fit_monotonic_calibrator(cases: Sequence[ScoredCase]) -> CalibrationModel:
    ordered = sorted(cases, key=lambda case: (case.raw_confidence, case.case_id))
    if not ordered:
        raise ValueError("at least one calibration case is required")

    grouped: list[list[float]] = []
    for case in ordered:
        raw = float(case.raw_confidence)
        if not 0.0 <= raw <= 1.0:
            raise ValueError("raw_confidence must be between 0 and 1")
        target = _label_value(case)
        if grouped and raw == grouped[-1][0]:
            grouped[-1][1] += target
            grouped[-1][2] += 1.0
        else:
            grouped.append([raw, target, 1.0])

    pooled: list[list[float]] = []
    for raw, positives, count in grouped:
        pooled.append([raw, positives, count])
        while len(pooled) >= 2:
            left = pooled[-2]
            right = pooled[-1]
            if left[1] / left[2] <= right[1] / right[2]:
                break
            pooled[-2:] = [[right[0], left[1] + right[1], left[2] + right[2]]]

    blocks = tuple(
        CalibrationBlock(max_raw=raw, probability=positives / count, count=int(count))
        for raw, positives, count in pooled
    )
    return CalibrationModel(
        schema_version="1.0",
        fitted_case_ids=tuple(sorted(case.case_id for case in ordered)),
        blocks=blocks,
    )


def apply_calibration(raw_confidence: float, model: CalibrationModel) -> float:
    if not model.blocks:
        raise ValueError("calibration model has no blocks")
    raw = float(raw_confidence)
    if not 0.0 <= raw <= 1.0:
        raise ValueError("raw_confidence must be between 0 and 1")
    for block in model.blocks:
        if raw <= block.max_raw:
            return block.probability
    return model.blocks[-1].probability


def calibration_model_to_dict(model: CalibrationModel) -> dict[str, object]:
    return {
        "schema_version": model.schema_version,
        "fitted_case_ids": list(model.fitted_case_ids),
        "blocks": [
            {"max_raw": block.max_raw, "probability": block.probability, "count": block.count}
            for block in model.blocks
        ],
    }


def calibration_model_from_dict(payload: Mapping[str, object]) -> CalibrationModel:
    if payload.get("schema_version") != "1.0":
        raise ValueError("calibration model schema_version must be 1.0")
    raw_ids = payload.get("fitted_case_ids")
    raw_blocks = payload.get("blocks")
    if not isinstance(raw_ids, list) or not isinstance(raw_blocks, list):
        raise ValueError("invalid calibration model payload")
    blocks: list[CalibrationBlock] = []
    for item in raw_blocks:
        if not isinstance(item, Mapping):
            raise ValueError("invalid calibration block")
        blocks.append(CalibrationBlock(
            max_raw=float(item["max_raw"]),
            probability=float(item["probability"]),
            count=int(item["count"]),
        ))
    if not blocks:
        raise ValueError("calibration model has no blocks")
    return CalibrationModel(
        schema_version="1.0",
        fitted_case_ids=tuple(str(value) for value in raw_ids),
        blocks=tuple(blocks),
    )


def load_calibration_model(path: str | Path) -> CalibrationModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid calibration model payload")
    if "blocks" in payload:
        model_payload = payload
    else:
        model_payload = payload.get("model")
        if not isinstance(model_payload, dict):
            raise ValueError("calibration model unavailable")
    return calibration_model_from_dict(model_payload)


def evaluate_calibrator(
    model: CalibrationModel,
    cases: Sequence[ScoredCase],
    *,
    allow_in_sample: bool = False,
) -> list[dict[str, object]]:
    fitted = set(model.fitted_case_ids)
    requested = {case.case_id for case in cases}
    if not allow_in_sample and fitted.intersection(requested):
        raise ValueError("in-sample evaluation requires allow_in_sample=True")
    rows: list[dict[str, object]] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        rows.append({
            "case_id": case.case_id,
            "label": case.label,
            "expected_orientation": case.expected_orientation,
            "observed_orientation": case.observed_orientation,
            "raw_confidence": case.raw_confidence,
            "calibrated_confidence": apply_calibration(case.raw_confidence, model),
            "status": "ok",
        })
    return rows


def cross_validated_predictions(cases: Sequence[ScoredCase]) -> list[dict[str, object]]:
    ordered = sorted(cases, key=lambda item: item.case_id)
    rows: list[dict[str, object]] = []
    for held_out in ordered:
        training = [case for case in ordered if case.case_id != held_out.case_id]
        labels = {case.label for case in training}
        if labels != {"copy", "unrelated"}:
            rows.append({
                "case_id": held_out.case_id,
                "label": held_out.label,
                "expected_orientation": held_out.expected_orientation,
                "observed_orientation": held_out.observed_orientation,
                "raw_confidence": held_out.raw_confidence,
                "calibrated_confidence": None,
                "status": "insufficient_training_classes",
            })
            continue
        model = fit_monotonic_calibrator(training)
        rows.extend(evaluate_calibrator(model, [held_out]))
    return rows


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def threshold_sweep(predictions: Sequence[Mapping[str, object]]) -> list[ThresholdMetrics]:
    available = [row for row in predictions if row.get("calibrated_confidence") is not None]
    if not available:
        return []
    thresholds = sorted({0.0, 1.0, *(float(row["calibrated_confidence"]) for row in available)})
    output: list[ThresholdMetrics] = []
    for threshold in thresholds:
        tp = fp = tn = fn = 0
        for row in available:
            predicted_copy = float(row["calibrated_confidence"]) >= threshold
            actual_copy = row.get("label") == "copy"
            if predicted_copy and actual_copy:
                tp += 1
            elif predicted_copy:
                fp += 1
            elif actual_copy:
                fn += 1
            else:
                tn += 1
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        false_positive_rate = _safe_ratio(fp, fp + tn)
        f1 = _safe_ratio(2 * tp, 2 * tp + fp + fn)
        output.append(ThresholdMetrics(
            threshold=threshold,
            true_positive=tp,
            false_positive=fp,
            true_negative=tn,
            false_negative=fn,
            precision=precision,
            recall=recall,
            false_positive_rate=false_positive_rate,
            f1=f1,
        ))
    return output


def choose_threshold(metrics: Sequence[ThresholdMetrics]) -> ThresholdMetrics:
    if not metrics:
        raise ValueError("no threshold metrics available")
    return max(metrics, key=lambda item: (item.f1, -item.false_positive_rate, item.precision, item.threshold))


def _metrics_to_dict(item: ThresholdMetrics) -> dict[str, object]:
    return {
        "threshold": item.threshold,
        "true_positive": item.true_positive,
        "false_positive": item.false_positive,
        "true_negative": item.true_negative,
        "false_negative": item.false_negative,
        "precision": item.precision,
        "recall": item.recall,
        "false_positive_rate": item.false_positive_rate,
        "f1": item.f1,
    }


def _orientation_diagnostics(cases: Sequence[ScoredCase]) -> tuple[int, int, float | None]:
    evaluated = [case for case in cases if case.label == "copy" and case.expected_orientation is not None]
    correct = sum(case.expected_orientation == case.observed_orientation for case in evaluated)
    accuracy = correct / len(evaluated) if evaluated else None
    return len(evaluated), correct, accuracy


def build_calibration_report(dataset: CalibrationDataset) -> dict[str, object]:
    cases = list(dataset.cases)
    predictions = cross_validated_predictions(cases)
    metrics = threshold_sweep(predictions)
    label_counts = {
        "copy": sum(case.label == "copy" for case in cases),
        "unrelated": sum(case.label == "unrelated" for case in cases),
    }
    evaluated, correct, accuracy = _orientation_diagnostics(cases)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "dataset_summary": {
            "name": dataset.name,
            "case_count": len(cases),
            "case_ids": sorted(case.case_id for case in cases),
            "label_counts": label_counts,
        },
        "class_counts": label_counts,
        "orientation_evaluated": evaluated,
        "orientation_correct": correct,
        "orientation_accuracy": accuracy,
        "predictions": predictions,
        "threshold_sweep": [_metrics_to_dict(item) for item in metrics],
        "threshold_space": "calibrated_confidence",
    }
    if not metrics:
        report.update({"status": "calibration_unavailable", "selected_threshold": None, "selected_metrics": None, "model": None})
        return report
    selected = choose_threshold(metrics)
    report.update({
        "status": "ok",
        "selected_threshold": selected.threshold,
        "selected_metrics": _metrics_to_dict(selected),
        "model": calibration_model_to_dict(fit_monotonic_calibrator(cases)),
    })
    return report
