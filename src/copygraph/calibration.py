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
