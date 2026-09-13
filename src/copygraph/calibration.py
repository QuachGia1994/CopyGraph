from __future__ import annotations

import json
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
