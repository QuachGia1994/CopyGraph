from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict

from .calibration import CalibrationModel, apply_calibration
from .matching import PairAnalysis
from .models import PositionLifecycle


def _weighted_mean(analysis: PairAnalysis, attribute: str) -> float:
    total = sum(match.rarity_weight for match in analysis.matches)
    if not total:
        return 0.0
    return sum(float(getattr(match, attribute)) * match.rarity_weight for match in analysis.matches) / total


def _component_summary(analysis: PairAnalysis) -> dict[str, dict[str, float]]:
    weights = {
        "time": ("time_similarity", 0.40),
        "lifecycle": ("lifecycle_similarity", 0.25),
        "risk": ("risk_similarity", 0.20),
        "volume": ("volume_similarity", 0.15),
    }
    output: dict[str, dict[str, float]] = {}
    for name, (attribute, coefficient) in weights.items():
        similarity = _weighted_mean(analysis, attribute)
        output[name] = {
            "coefficient": coefficient,
            "similarity": similarity,
            "weighted_contribution": coefficient * similarity,
        }
    return output


def _warnings(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
) -> list[str]:
    warnings: list[str] = []
    if analysis.sample_factor < 1.0:
        warnings.append("sparse_sample")
    if analysis.overlap_factor < 0.5:
        warnings.append("low_overlap")

    by_a = {position.position_id: position for position in account_a}
    by_b = {position.position_id: position for position in account_b}
    risk_covered = 0
    ratios: list[float] = []
    for match in analysis.matches:
        left = by_a.get(match.a_position_id)
        right = by_b.get(match.b_position_id)
        if left is None or right is None:
            continue
        if left.sl is not None and right.sl is not None:
            risk_covered += 1
        if left.volume > 0 and right.volume > 0:
            ratios.append(right.volume / left.volume)

    if analysis.matches and risk_covered * 2 < len(analysis.matches):
        warnings.append("missing_stop_evidence")
    if len(ratios) >= 3 and min(ratios) > 0 and max(ratios) / min(ratios) > 2.0:
        warnings.append("unstable_volume_ratio")
    return warnings


def explain_pair(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]:
    strongest = sorted(
        (asdict(match) for match in analysis.matches),
        key=lambda item: (-float(item["score"]), str(item["a_position_id"]), str(item["b_position_id"])),
    )[:5]
    weakest = sorted(
        (asdict(match) for match in analysis.matches),
        key=lambda item: (float(item["score"]), str(item["a_position_id"]), str(item["b_position_id"])),
    )[:5]
    matched_a = {match.a_position_id for match in analysis.matches}
    matched_b = {match.b_position_id for match in analysis.matches}

    return {
        "schema_version": "1.0",
        "accounts": [analysis.account_a, analysis.account_b],
        "orientation": analysis.orientation,
        "lead_account": analysis.lead_account,
        "median_delay_s": analysis.median_delay_s,
        "matching_window_s": analysis.matching_window_s,
        "raw_score": analysis.score,
        "raw_confidence": analysis.confidence,
        "calibrated_confidence": None if calibration is None else apply_calibration(analysis.confidence, calibration),
        "confidence_factors": {
            "overlap": analysis.overlap_factor,
            "sample": analysis.sample_factor,
        },
        "components": _component_summary(analysis),
        "strongest_matches": strongest,
        "weakest_matches": weakest,
        "unmatched_counts": {
            "a": max(0, len(account_a) - len(matched_a)),
            "b": max(0, len(account_b) - len(matched_b)),
        },
        "warnings": _warnings(analysis, account_a, account_b),
    }
